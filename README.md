# MS41 BSL Unbricker

In-circuit recovery tool for the BMW **MS41.x** ECU (Siemens **SAB 80C166** CPU + a
2/4 Mbit boot-block flash). It reprograms the **entire** flash over the 80C166
**bootstrap loader (BSL)** — no desoldering the FLASH, no diagnostic session, every block
including the boot/reset vectors.

Supported flash: the original Intel **28F200** (Intel command set, needs 12 V) and the
AMD/JEDEC **29F200 / 29F400** family (AMD unlock-cycle command set, single-supply — e.g. a
retrofit). Pick it with `--chip` (see *Flash chip & regions* below); `id` auto-detects.

The BSL lives in CPU silicon and runs regardless of flash contents, so this
recovers a fully corrupt, cross-flashed, or **blank** chip — the cases where the
normal diagnostic flash path can't help.

---

## How it works

- **BSL entry** is forced in hardware at reset, then a tiny loader is sent over the
  CPU's serial port (ASC0) into RAM and run from there. A small RAM *monitor*
  provides read / erase / program / verify primitives; the host drives the flash's
  command set through it — Intel (28F200) or AMD/JEDEC unlock-cycle (29F200/29F400),
  selected with `--chip`.
- **Address mapping.** The board's GAL maps flash `A13 = !CPU A14`, so a file/chip
  image is the CPU image XOR `0x4000` per 16 KB block (a `.bin` read on a bench
  programmer is in *file* order; the tool converts automatically).
- **BSL shadow.** In bootstrap mode the CPU's `0x0–0x7FFF` is overlaid by the
  bootstrap ROM. The low blocks are reached through a `+0x40000` address-wrap alias
  (the external bus wraps within 256 KB), so erase/program/verify still hit real
  flash. The tool detects the shadow and routes those blocks automatically.

## Flash chip & regions (`--chip`)

`id` auto-detects the chip. For `flash` you state it with `--chip` (the erase geometry
differs, so it can't be guessed): `--chip 28f200` (Intel, needs **12 V**) or `--chip 29f200`
/ `--chip 29f400` (AMD/JEDEC, **single-supply, no 12 V**). `--chip auto` (the default) is for
`id` only and assumes 28F200 for `flash`.

**28F200 regions** (CPU addresses; `--chip 28f200`). The MS41's **AB28F200BX-B** is *bottom-boot*
(16 KB BOOT block at chip `0x0`), but the GAL scrambles addresses by XOR-`0x4000` per 16 KB block,
so the datasheet blocks land at different CPU addresses: the CPU's reset vectors sit in the chip's
first parameter block (CPU `0x0` = `boot`), while the chip's 16 KB BOOT block is at CPU `0x4000`
(= `program-mid`). All 28F200 erase/program needs **12 V on VPP**.

| region | CPU range | size | notes (chip block; file = CPU XOR 0x4000) |
|---|---|---|---|
| `boot` | `0x00000–0x01FFF` | 8 KB | chip **PARAM 1** (file 0x4000) — holds the CPU reset/trap vectors; low, via alias |
| `program-low` | `0x02000–0x03FFF` | 8 KB | chip **PARAM 2** (file 0x6000); low, via alias |
| `program-mid` | `0x04000–0x07FFF` | 16 KB | chip's **16 KB BOOT block** (file 0x0) — HW-lockable, needs RP#=12 V; low, via alias |
| `tune` | `0x08000–0x1FFFF` | 96 KB | chip **MAIN 96 KB** (file 0x8000) — calibration / tune |
| `program-high` | `0x20000–0x3FFFF` | 128 KB | chip **MAIN 128 KB** (file 0x20000) — program code |

**29F400 — upper half (default, factory A17-high strap).** A 4 Mbit 29F400 on this 256 KB board
has its top address line (A17) tied high, so the CPU sees the chip's **upper** 256 KB half =
**four uniform 64 KB sectors (SA7–SA10)** (the chip's small boot sectors sit in the unused lower
half). The boot area is therefore a single `low` unit (SA7), erased as one 64 KB sector via the alias:

| region | CPU range | size | notes |
|---|---|---|---|
| `low` | `0x00000–0x0FFFF` | 64 KB (SA7) | boot + program-low + bootloader + drivers (in the low 32 KB; upper 32 KB = gap/hole); flashed together via alias |
| `tune` | `0x10000–0x1FFFF` | 64 KB (SA8) | calibration / tune |
| `program-high` | `0x20000–0x3FFFF` | 2 × 64 KB (SA9+SA10) | program code |

**29F200, or 29F400 with `--half lower` — bottom-boot fine sectors.** A genuine **29F200** is a
256 KB bottom-boot chip with **no A17 pin**, so it presents these fine sectors natively — it *is*
the 29F400's lower half, and `--chip 29f200` selects this map automatically (no `--half`). On a
**29F400** the same layout is reached by rewiring A17 **low** (see the note below) and passing
`--half lower`. Either way `boot`, `program-low` and `program-mid` are **separate** sectors that
erase individually (no 64 KB group erase), matching the 28F200's region names. 

| region | CPU range | size | notes (chip sector; file = CPU XOR 0x4000) |
|---|---|---|---|
| `boot` | `0x00000–0x01FFF` | 8 KB | chip **SA1** (file 0x4000) — holds the CPU reset/trap vectors; low, via alias |
| `program-low` | `0x02000–0x03FFF` | 8 KB | chip **SA2** (file 0x6000); low, via alias |
| `program-mid` | `0x04000–0x07FFF` | 16 KB | chip **SA0** (file 0x0) — bottom-boot block, WP#-protectable; low, via alias |
| `tune` | `0x10000–0x1FFFF` | 64 KB | chip **SA4** — calibration / tune |
| `program-high` | `0x20000–0x3FFFF` | 2 × 64 KB | chip **SA5 + SA6** — program code |

> CPU `0x08000–0x0FFFF` (chip SA3, 32 KB) is the unused gap/hole on this firmware and is not in
> the region map.

> **Reaching the 29F400 lower half — A17 rewire + GAL.** The board's GAL uses A17 (flash pin 3,
> held high by a pull-up) as a decode input: the SRAM and CAN chip-selects are gated by it, so
> simply tying A17 **low** deasserts RAM/CAN and **kills the ECU**. To use `--half lower` on a
> 29F400 you must first **either reprogram the GAL** so its decode no longer depends on A17, **or
> cut the trace between flash pin 3 (A17) and the GAL before the pull-up resistor** so the GAL keeps seeing the high it expects
> while A17 alone is pulled low. A genuine **29F200 needs none of this** — it has no A17 pin. Note
> that selecting the lower half points the CPU at a (possibly blank) half, so the image must
> already be present there.

---

## Hardware setup

The connections below are made at the DME PCB test points shown here (The image was upscaled using AI, so the text on the ICs got obliterated, I apologize for that):

![MS41 DME PCB — test points for the serial tap, BSL-entry straps, reset, and 12V](images/PCB_TP.PNG)

1. **Serial:** a direct TTL tap on ASC0 — **TxD0 (P3.10)** and **RxD0 (P3.11)** — to a
   3.3 V/5 V USB-serial adapter (FT232). Full-duplex direct tap is the only mode.
2. Connect GND from the adapter to DME GND.   
3. **Force BSL at reset:** **ALE (pin 25) HIGH through a 2.2K resistor to +5V** and
   **Connect ALE (pin 25) and NMI# (pin 29) together**.
4. Wire RSTIN# to the adapter's DTR and let the tool pulse it with `--reset-line dtr` (active-low;
   add `--reset-invert` if a transistor inverts the line).
5. Bridge K-Line input to 5V. This will trigger current protection and release RX line for FULL-Duplex.
6. **Programming voltage (28F200 only):** **12 V on the 28F200 VPP pin** is required for any
   erase/program. On this ECU VPP and RP# share a net, so that one 12 V supply also unlocks
   the HW-locked boot block (`program-mid`). The **29F200/29F400 is single-supply** — it makes
   its own program voltage, so **no 12 V** is needed (the tool drives only WR#).

Note: A FTDI232 adapter is recommended.

Note 2: You can optionally add a 0603 resistor on the white box marked in the picture. That would replace a full size 2.2K resistor between ALE and +5V.

---

## Install

Pick one — all three take the **same arguments**:

**1. Standalone Windows executable** (no Python needed). Download `bsl_unbrick.exe` from the
[latest release](https://github.com/CAATZ/MS41-BSL-Unbricker/releases) and run it from a terminal:
```bash
bsl_unbrick.exe --port COM4 --reset-line dtr id
```
First run may trip Windows SmartScreen / antivirus — a known PyInstaller false positive; click
*More info → Run anyway*.

**2. pip** (any OS, Python 3.8+). Install the wheel from the release; it pulls in pyserial and
adds an `ms41-bsl-unbrick` command:
```bash
pip install ms41_bsl_unbrick-1.1.0-py3-none-any.whl
ms41-bsl-unbrick --port COM4 --reset-line dtr id
```

**3. From source** (Python 3.8+):
```bash
pip install -r requirements.txt      # just pyserial
python bsl_unbrick.py --port COM4 --reset-line dtr id
```

---

## Usage

The `flash` command is **safe by default**. Without `--arm` it's a **dry run**: it prints
the full plan — which block it will erase, the exact program window, and the variant
check — and **does not open the serial port or touch the ECU at all**. Review the plan,
then re-run the *same* command with `--arm` to actually erase + program + verify.

> The examples use `python bsl_unbrick.py`; if you installed the **exe** or the **pip package**,
> swap in `bsl_unbrick.exe` or `ms41-bsl-unbrick` instead — the arguments are identical.

```bash
# confirm BSL entry (0x55) + that loaded code runs (0xA5) — no flash risk
python bsl_unbrick.py --port COM4 --reset-line dtr sync

# identify the flash chip (manufacturer + device ID; non-destructive, no 12V)
python bsl_unbrick.py --port COM4 --reset-line dtr id

# dump the whole chip to a file-order .bin (bench-flashable layout — now the DEFAULT)
python bsl_unbrick.py --port COM4 --reset-line dtr dump dump.bin
#   ...add --cpu-order for the raw physical/CPU image (NOT directly re-flashable)
#   ...or --partial to dump just the 24 KB cal/tune partition (flashable via `flash tune`)

# preview a flash — DRY RUN: prints the plan, opens nothing, touches nothing
python bsl_unbrick.py --port COM4 --reset-line dtr flash tune --ref image.bin

# ...looks right? run the SAME command with --arm to actually do it
python bsl_unbrick.py --port COM4 --reset-line dtr flash tune --ref image.bin --arm

# flash the WHOLE chip — for a corrupt/virgin flash (add --arm to execute)
python bsl_unbrick.py --port COM4 --reset-line dtr --speed mid flash all --ref image.bin --arm

# same, but for a 29F400 (AMD command set; no 12V needed) — factory A17-high upper half
python bsl_unbrick.py --port COM4 --reset-line dtr --chip 29f400 --speed mid flash all --ref image.bin --arm

# a 29F200 retrofit — native bottom-boot fine sectors (no A17, no --half)
python bsl_unbrick.py --port COM4 --reset-line dtr --chip 29f200 --speed mid flash all --ref image.bin --arm

# a 29F400 rewired to the lower half (needs the A17/GAL change — see Flash chip & regions)
python bsl_unbrick.py --port COM4 --reset-line dtr --chip 29f400 --half lower flash all --ref image.bin --arm
```

- **`--chip`** selects the flash command set: `28f200` (Intel, needs 12 V) or
  `29f200`/`29f400` (AMD/JEDEC, no 12 V). Default `auto` assumes 28F200 for `flash`. See
  *Flash chip & regions* above (the AMD chips use a different region map).
- **`--ref`** is a full file-order 256 KB image for any region, **or** a 24 KB
  calibration partial for `tune` — the partial is **CPU/DS2 order** (DS2 `0x10000–0x15FFF`),
  **not** a file slice `full[0x14000:0x1A000]` (that layout drops the swapped-half cal —
  file = CPU XOR `0x4000` per 16 KB). A partial this tool reads back is already correct.
- **`--speed slow|mid|fast`** = 9600 / 19200 / 38400 baud. The ECU's bootstrap
  auto-baud sets the ceiling; `mid` (19200) is the reliable sweet spot. If a faster
  preset returns a garbled sync, drop down one.
- **Variant guard:** flashing a calibration checks the reference's MS41 variant
  against the ECU's and **refuses a mismatch** (the classic brick). A **blank/virgin
  ECU** has no variant to compare, so it is allowed — you can flash a fresh/erased
  chip. Override a mismatch with `--force` only if you are certain.
- **Checksum guard:** before flashing, the reference's MS41 checksums (boot, program,
  calibration) are verified. The tool **respects the ECU's disable switches** — a bad
  checksum whose verification is *off* only warns (e.g. MS41.3 ships with an invalid
  program checksum but program verification disabled at `0x605C`, which is fine). A bad
  checksum whose verification is *on* is **refused**; either:
    - add **`--fix-checksums`** to recompute and correct it in memory before flashing
      (only the stored checksum bytes change; for MS41.3 the program checksum is left
      as-is since it's disabled), or
    - add **`--force`** to flash anyway.
- A read-back **verify** runs after every program; a backup of each block is saved
  before erasing (skip with `--no-backup`).

Run `python bsl_unbrick.py --help` for the full option list.

---

## Warnings

- Erasing/programming with the wrong or incomplete image can leave the ECU
  unbootable. Because BSL is independent of flash contents, you can always re-run to
  recover — but don't power-cycle into "run the engine" until a flash reports
  `MATCH`.
- For a 28F200, keep the 12 V VPP supply stable during erase/program. (A 29F200/29F400 is
  single-supply and needs no 12 V.)
- For research / educational use and recovery of your own ECU. No warranty.

---

## Acknowledgements

This tool stands on public hardware documentation and prior community work:

- **Infineon / Siemens** — the *SAB 80C166* datasheet and the *80C166 Bootstrap Loader*
  application note: the BSL entry sequence, ASC0 serial protocol, and the half-duplex caveat.
- **Intel** — the *28F200BX* flash datasheet: the Intel command set (erase / program / Read-ID),
  block map, status register, and identifier codes.
- **AMD** — the *Am29F400B* flash datasheet: the JEDEC unlock-cycle command set (sector erase /
  word program / autoselect), the sector map, and DQ6/DQ7/DQ5 status polling — the basis for the
  29F200/29F400 support.
- **[RomRaider](https://www.romraider.com/)** — MS41 ROM definitions and community reverse
  engineering, used for variant / CAL-ID identification and the checksum-disable control bits.
- **[Siemens_MS41_Checksum](https://github.com/kimfreding/Siemens_MS41_Checksum)** (kimfreding)
  and **[pyms41](https://github.com/OpenMS41/pyms41)** (jpiccari) — the MS41 CRC-16 checksum
  work that `ms41_checksum.py` builds on.
- **[Siemens-MS41](https://github.com/ba114/Siemens-MS41)** (ba114) — MS41 reverse-engineering ECU definitions.
- **[c166-ghidra-module](https://github.com/keyhana/c166-ghidra-module)** (keyhana) — the C166
  SLEIGH processor module for **[Ghidra](https://github.com/NationalSecurityAgency/ghidra)**,
  used to disassemble and assemble the RAM monitor and the 0xFA40 stubs.

Thanks also to **[grantUser](https://github.com/grantUser)** for collaborative ideation.

---

## License

MIT — see [LICENSE](LICENSE).
