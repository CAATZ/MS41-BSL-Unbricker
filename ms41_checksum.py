"""
ms41_checksum.py — BMW MS41 ROM checksum verification + correction (offline, from a .bin).

There are THREE checksum systems in a 256 KB MS41 image, all CRC-16 (poly 0xA001,
reflected, table-driven), computed directly on FILE offsets, stored little-endian:

  1. Boot-sector  : CRC of file[0x4000:0x5C14], init 0x4711, stored at file[0x5C80].
  2. Program      : init = big-endian uint16 at file[0x6066]; CRC chained through
                    file[0x6100:trim_ff(0x7FFF)], file[0x0:trim_ff(0x3FFF)], and the
                    upper 128 KB rearranged into a linear buffer (adjacent 0x4000 block
                    pairs swapped) trimmed of trailing 0xFF; stored at file[0x6050].
  3. Calibration  : the "4E 00 FF FF" block holds a table of uint16 offsets, each
                    pointing to a stored 2-byte checksum; the region runs from the
                    previous slot to that slot.  init = big-endian uint16 at block+0x0E.

The three systems cover disjoint regions and none include their own stored bytes, so
they correct independently.  Two disable switches exist in the calibration control bytes:
  * Program CRC : file 0x605C  (0x30 = ECU verifies / stock, 0xFF = verification off).
  * Cal CRC     : cal-region control byte 7 bit 4 (0x10 set = cal CRC check off).

MS41.3 ships with the program checksum invalid but the program CRC switch disabled, so it
still boots — the cal table is the one a tune edit must keep valid.  MS41.3's program-
checksum *layout* is not confirmed, so correct_checksums(correct_program=False) leaves it.
"""

import struct

FULL_ROM_SIZE = 256 * 1024     # 262144
TUNE_SIZE     = 24 * 1024      # 24576

CHECKSUM_SWITCH_ADDR = 0x605C  # program CRC verify switch (full ROM only)
CK_ENABLED  = 0x30
CK_DISABLED = 0xFF
CAL_BASE_FULL = 0x14000        # cal control bytes at CAL_BASE+4..+8 (full ROM); +0 in a partial
CAL_CRC_DISABLE_BIT = 0x10     # cal control byte 7 bit 4: set = cal CRC check disabled

_BOOT_REGION = (0x4000, 0x5C14)
_BOOT_INIT   = 0x4711
_BOOT_STORE  = 0x5C80
_PROG_INIT_AT = 0x6066         # big-endian uint16
_PROG_STORE   = 0x6050
_CAL_MAGIC    = b"\x4E\x00\xFF\xFF"

# ── CRC-16 (poly 0xA001) ──────────────────────────────────────────────────────
_POLY = 0xA001
_TABLE = []
for _i in range(256):
    _n = 0; _n2 = _i
    for _j in range(8):
        _n = ((_n >> 1) ^ _POLY) if (_n2 ^ _n) & 1 else (_n >> 1)
        _n2 >>= 1
    _TABLE.append(_n)


def _crc(buf, init):
    s = init
    for b in buf:
        s = (s >> 8) ^ _TABLE[(s ^ b) & 0xFF]
    return s

def _u16le(d, a): return d[a] | (d[a + 1] << 8)
def _be16(d, a):  return (d[a] << 8) | d[a + 1]

def _find_end(buf, start):
    """Scan downward from `start` while bytes are 0xFF; return first-kept index."""
    while start > 0 and buf[start] == 0xFF:
        start -= 1
    return start + 1


# ── Individual checksums ──────────────────────────────────────────────────────
def _boot_calc(d):
    return _crc(d[_BOOT_REGION[0]:_BOOT_REGION[1]], _BOOT_INIT)

def _prog_calc(d):
    init = _be16(d, _PROG_INIT_AT)
    s = _crc(d[0x6100:_find_end(d, 0x7FFF)], init)
    s = _crc(d[0x0000:_find_end(d, 0x3FFF)], s)
    buf = bytearray(0x20000)
    for src, dst in ((0x24000, 0x00000), (0x20000, 0x04000), (0x2C000, 0x08000),
                     (0x28000, 0x0C000), (0x34000, 0x10000), (0x30000, 0x14000),
                     (0x3C000, 0x18000), (0x38000, 0x1C000)):
        buf[dst:dst + 0x4000] = d[src:src + 0x4000]
    s = _crc(buf[0x00000:_find_end(buf, 0x1FFFF)], s)
    return s

def _cal_entries(d):
    """Yield (store_addr, calc_value) for each calibration-table checksum."""
    start = d.find(_CAL_MAGIC)
    if start < 0:
        return
    init = _be16(d, start + 0x0E)
    pos = start
    for _ in range(20):
        ss = _u16le(d, pos)
        if ss == 0xFFFF:
            break
        store = start + ss
        if store + 2 > len(d) or store < pos:
            break
        yield store, _crc(d[pos:store], init)
        pos = store + 2

def _cal_verify(d):
    """Return (all_ok, n_ok, n_total) for the calibration checksum table."""
    cal = list(_cal_entries(d))
    n_ok = sum(1 for a, c in cal if _u16le(d, a) == c)
    return (n_ok == len(cal) and len(cal) > 0), n_ok, len(cal)


# ── Disable switches ──────────────────────────────────────────────────────────
def program_check_disabled(data):
    """True if the ECU's program/full-ROM CRC verification is off (file 0x605C = 0xFF)."""
    return len(data) == FULL_ROM_SIZE and data[CHECKSUM_SWITCH_ADDR] == CK_DISABLED

def cal_check_disabled(data):
    """True if the calibration CRC check is disabled (cal control byte 7 bit 4)."""
    base = CAL_BASE_FULL if len(data) == FULL_ROM_SIZE else (0 if len(data) == TUNE_SIZE else None)
    if base is None or base + 8 > len(data):
        return False
    return bool(data[base + 7] & CAL_CRC_DISABLE_BIT)


# ── Public verify / status / correct ──────────────────────────────────────────
def verify_checksum(data):
    """Verify MS41 checksums.  Returns (all_ok, [detail strings]).
    256 KB ROM: boot + program + cal + switch state.  24 KB partial: cal table only."""
    d = bytearray(data); size = len(d)
    if size == FULL_ROM_SIZE:
        details = []; ok = True
        bc, bs = _boot_calc(d), _u16le(d, _BOOT_STORE)
        details.append(f"Boot-sector  : stored 0x{bs:04X} / calc 0x{bc:04X}  "
                       f"{'OK' if bc == bs else 'MISMATCH'}")
        ok &= (bc == bs)
        pc, ps = _prog_calc(d), _u16le(d, _PROG_STORE)
        details.append(f"Program      : stored 0x{ps:04X} / calc 0x{pc:04X}  "
                       f"{'OK' if pc == ps else 'MISMATCH'}  (verify "
                       f"{'OFF' if program_check_disabled(d) else 'ON'})")
        ok &= (pc == ps)
        cal_ok, n_ok, n_tot = _cal_verify(d)
        details.append(f"Calibration  : {n_ok}/{n_tot} checksums OK  (verify "
                       f"{'OFF' if cal_check_disabled(d) else 'ON'})")
        ok &= cal_ok
        return ok, details
    if size == TUNE_SIZE:
        cal_ok, n_ok, n_tot = _cal_verify(d)
        if n_tot == 0:
            return False, ["24 KB partial: no calibration checksum table ('4E 00 FF FF') found."]
        return cal_ok, [f"24 KB partial — calibration: {n_ok}/{n_tot} OK  (verify "
                        f"{'OFF' if cal_check_disabled(d) else 'ON'})"]
    return False, [f"File size {size} bytes is not a recognised MS41 image (need 262144 or 24576)."]


def checksum_status(data):
    """Per-system status dict: keys boot/program/cal are True/False/None (None = not in this
    image kind); prog_disabled/cal_disabled are bools."""
    d = bytearray(data); size = len(d)
    if size == FULL_ROM_SIZE:
        cal_ok, _, n_tot = _cal_verify(d)
        return {"boot": _boot_calc(d) == _u16le(d, _BOOT_STORE),
                "program": _prog_calc(d) == _u16le(d, _PROG_STORE),
                "cal": (cal_ok if n_tot else None),
                "prog_disabled": program_check_disabled(d), "cal_disabled": cal_check_disabled(d)}
    if size == TUNE_SIZE:
        cal_ok, _, n_tot = _cal_verify(d)
        return {"boot": None, "program": None, "cal": (cal_ok if n_tot else None),
                "prog_disabled": False, "cal_disabled": cal_check_disabled(d)}
    return {"boot": None, "program": None, "cal": None,
            "prog_disabled": False, "cal_disabled": False}


def correct_checksums(data, correct_program=True):
    """Recompute and write MS41 checksums (only the stored checksum bytes change).
    256 KB ROM: boot + cal + (program, unless correct_program=False).  24 KB partial: cal.
    Pass correct_program=False for an MS41.3 full ROM (program-checksum layout unconfirmed).
    Returns (corrected_copy, [detail strings])."""
    out = bytearray(data); size = len(out)
    if size not in (FULL_ROM_SIZE, TUNE_SIZE):
        return out, [f"Checksum correction needs a 256 KB ROM or 24 KB partial (got {size})."]
    details = []; fixed = 0
    if size == FULL_ROM_SIZE:
        bc = _boot_calc(out); bs = _u16le(out, _BOOT_STORE)
        if bc != bs:
            struct.pack_into("<H", out, _BOOT_STORE, bc); fixed += 1
            details.append(f"Boot-sector corrected: 0x{bs:04X} -> 0x{bc:04X}")
    for store, calc in _cal_entries(out):
        if _u16le(out, store) != calc:
            struct.pack_into("<H", out, store, calc); fixed += 1
            details.append(f"Cal checksum @0x{store:05X} corrected -> 0x{calc:04X}")
    if size == FULL_ROM_SIZE and correct_program:
        pc = _prog_calc(out); ps = _u16le(out, _PROG_STORE)
        if pc != ps:
            struct.pack_into("<H", out, _PROG_STORE, pc); fixed += 1
            details.append(f"Program corrected: 0x{ps:04X} -> 0x{pc:04X}")
    details.append(f"{fixed} checksum(s) corrected." if fixed else "All checksums already valid.")
    return out, details
