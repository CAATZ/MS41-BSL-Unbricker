"""
ms41_variant.py — minimal MS41 variant / CAL-ID detection (offline, from a .bin).

Just enough of the MS41 ROM-image model for bsl_unbrick.py's variant guard:
decide whether an image is MS41.0 / .1 / .2 / .3 and read its CAL ID, so the
flasher can refuse a cross-variant calibration (the classic way to brick an ECU).

Identification (RomRaider MS41 definitions + verified against real dumps):
  CAL ID  — ASCII at 0x1400E (full ROM) / 0x0000E (24 KB tune file); the first two
            chars give the family (60=MS41.1, 12=MS41.2, 41/42/59/85=MS41.0).
  MS41.3  — shares the "12" CAL ID prefix with MS41.2, so it is detected first by
            an "SS1" marker at 0x173BB (full ROM) / 0x033BB (24 KB tune).
  ECU ID  — 7 ASCII digits at 0x6025 (full ROM only), e.g. "1437806".
"""

# CAL ID location and family mapping.
CALID_ADDR_256K = 0x1400E   # full 256 KB ROM
CALID_ADDR_24K  = 0x0000E   # 24 KB tune-region file
CALID_VARIANT = {
    "60": "MS41.1", "12": "MS41.2",
    "41": "MS41.0", "42": "MS41.0", "59": "MS41.0", "85": "MS41.0",
}

# MS41.3 shares the "12" CAL ID prefix with MS41.2; an "SS1" marker disambiguates.
MS41_3_MARKER_256K   = 0x173BB
MS41_3_MARKER_24K    = 0x033BB
MS41_3_MARKER_PREFIX = b"SS1"

# BMW DME ECU ID — 7 ASCII digits at 0x6025 (full ROM only).
ECU_ID_ADDR = 0x6025

# MS41.3 program-region identity marker (outside the calibration area, so a
# calibration-only edit can't forge it) — lets check_hybrid catch a ROM whose
# program and calibration come from different variants.
MS41_3_PROG_MARKER_ADDR   = 0x11F60
MS41_3_PROG_MARKER_STRING = b"ABHISHEK"

# Program-region ECU IDs that map to a known variant.
_PROG_ECU_ID_MAP = {
    "1437806": "MS41.1", "1438068": "MS41.1",
    "1406464": "MS41.2",
    "1429861": "MS41.0", "1432401": "MS41.0",
    "1429373": "MS41.0", "1438137": "MS41.0",
}

# Calibration-family label per variant (MS41.2 and MS41.3 share "ID12").
_VARIANT_FAMILY = {
    "MS41.0": "ID41", "MS41.1": "ID60", "MS41.2": "ID12", "MS41.3": "ID12",
}


class MS41ECU:
    """MS41 ROM-image variant utilities (static; operate on a .bin, not a live ECU)."""

    FULL_ROM_SIZE = 256 * 1024   # 262144 bytes (Intel 28F200)
    TUNE_SIZE     = 24 * 1024    # 24576 bytes (calibration partial)

    @staticmethod
    def read_calid(data):
        """Return the ASCII CAL ID (e.g. "60011110"), or None if not found.
        Located at 0x1400E in a full ROM, 0x000E in a 24 KB tune file; a valid
        CAL ID is printable ASCII whose first two characters are digits."""
        for addr in (CALID_ADDR_256K, CALID_ADDR_24K):
            if addr + 8 <= len(data):
                chunk = bytes(data[addr:addr + 8])
                if all(0x30 <= b <= 0x7E for b in chunk) and chunk[:2].isdigit():
                    return chunk.decode("ascii")
        return None

    @staticmethod
    def detect_variant(data):
        """Detect 'MS41.0'/'.1'/'.2'/'.3' from a ROM or tune image, or None.
        MS41.3 is checked first via its SS1 marker (it shares MS41.2's "12" prefix)."""
        for addr in (MS41_3_MARKER_256K, MS41_3_MARKER_24K):
            if addr + len(MS41_3_MARKER_PREFIX) <= len(data) and \
               bytes(data[addr:addr + len(MS41_3_MARKER_PREFIX)]) == MS41_3_MARKER_PREFIX:
                return "MS41.3"
        calid = MS41ECU.read_calid(data)
        if calid:
            return CALID_VARIANT.get(calid[:2])
        return None

    @staticmethod
    def read_ecu_id(data):
        """Return the 7-digit BMW DME ECU ID from a full-ROM image, or None."""
        if len(data) >= ECU_ID_ADDR + 7:
            s = bytes(data[ECU_ID_ADDR:ECU_ID_ADDR + 7])
            if s.isdigit():
                return s.decode("ascii")
        return None

    @staticmethod
    def detect_program_variant(data):
        """Detect the variant of the PROGRAM region of a 256 KB full ROM, or None.
        Reads only outside the calibration area, so it identifies the program even
        in a hybrid ROM whose program and calibration are different variants."""
        if len(data) < MS41ECU.FULL_ROM_SIZE:
            return None
        end = MS41_3_PROG_MARKER_ADDR + len(MS41_3_PROG_MARKER_STRING)
        if bytes(data[MS41_3_PROG_MARKER_ADDR:end]) == MS41_3_PROG_MARKER_STRING:
            return "MS41.3"
        return _PROG_ECU_ID_MAP.get(MS41ECU.read_ecu_id(data))

    @staticmethod
    def check_hybrid(data):
        """Return a description string if a 256 KB ROM mixes program and calibration
        from incompatible variants (flashing such a ROM bricks the ECU), else None
        (consistent, or not identifiable)."""
        if len(data) < MS41ECU.FULL_ROM_SIZE:
            return None
        prog_v = MS41ECU.detect_program_variant(data)
        cal_v = MS41ECU.detect_variant(data)
        if prog_v is None or cal_v is None or prog_v == cal_v:
            return None
        pf = _VARIANT_FAMILY.get(prog_v, "?")
        cf = _VARIANT_FAMILY.get(cal_v, "?")
        kind = "cross-family" if pf != cf else "cross-variant within same family"
        return (f"Program region: {prog_v} ({pf})  -  "
                f"Calibration region: {cal_v} ({cf})  [{kind}]")
