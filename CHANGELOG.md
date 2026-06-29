# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project uses
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## [1.1.0] — 2026-06-28

Adds in-circuit recovery of the AMD/JEDEC **29F200 / 29F400** flash family alongside the
original Intel **28F200** — a single-supply (no 12 V) retrofit path. Hardware-proven on an
MS41.3 (S52).

### Added
- **`--chip {auto,28f200,29f200,29f400}`** — selects the flash command set: Intel (28F200,
  needs 12 V) or AMD/JEDEC unlock-cycle (29F200/29F400, single-supply). `auto` (default)
  auto-detects for `id` and assumes 28F200 for `flash`.
- **29F400 region map (upper half)** — the board straps the chip's top half (A17 high),
  exposing four uniform 64 KB sectors (SA7–SA10): `low` / `tune` / `program-high`.
  DQ6/DQ7/DQ5 status polling for erase/program.
- **29F200 / 29F400-lower region map (bottom-boot fine sectors)** — `boot` (SA1) /
  `program-low` (SA2) / `program-mid` (SA0) / `tune` (SA4) / `program-high` (SA5+SA6),
  each erasable individually. A 29F200 has no A17, so `--chip 29f200` selects this map
  automatically.
- **`--half {upper,lower}`** (29F400 only) — `lower` flashes the chip's real bottom-boot
  small sectors when A17 is rewired low (requires a GAL change — drop its A17 decode
  dependency or cut the flash-pin-3-to-GAL trace — or RAM/CAN deassert and the ECU dies).
- `id` honors `--chip` and auto-detects the AMD autoselect manufacturer/device ID.

### Changed
- README documents the AMD chip support, the per-chip region maps, and updated hardware
  notes (no 12 V for the 29F family).

## [1.0.0] — 2026-06-22

First release. In-circuit recovery of the entire Intel **28F200** flash on a BMW **MS41**
ECU over the 80C166 **bootstrap loader (BSL)** — no desoldering, no diagnostic session.
Hardware-proven on an MS41.3 (S52): all five blocks erased + programmed + read-back
verified; flash ID confirmed Intel 28F200BX-B.

### Added
- **`flash <region|all>`** — erase + program + verify any block (`boot`, `program-low`,
  `program-mid`, `tune`, `program-high`) or the whole chip, from a full file-order image
  or a 24 KB calibration partial. **Dry-run by default; `--arm` to execute.**
- **Variant guard** — refuses a cross-variant calibration; allows a blank/virgin chip.
- **Checksum guard** — verifies boot/program/cal checksums, respects the ECU's disable
  switches (a bad-but-disabled checksum only warns), `--fix-checksums` to correct,
  `--force` to override.
- Read-back **verify** after every program; automatic **backup** before erase.
- Shadowed low blocks (CPU `0x0–0x7FFF`) auto-routed through the **+0x40000** alias.
- Diagnostics: `sync`, **`id`** (flash manufacturer/device ID), `read`, `write`,
  `dump` (raw or `--file-order`), `verify-alias`, `vpp-on`, `businfo`.
- Baud presets (`--speed slow|mid|fast`), FTDI auto-reset into BSL (`--reset-line`),
  progress bars, and FT232-stall auto-recovery.
- `--version`.

[1.1.0]: https://semver.org/
[1.0.0]: https://semver.org/
