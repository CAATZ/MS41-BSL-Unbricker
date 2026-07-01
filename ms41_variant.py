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

# MS41.3 identity marker (developer credit "ABHISHEK").  ⚠ CAL-RESIDENT: file 0x11F60 =
# DS2 0x15F60 = cal 0x5F60, inside the tune partition (DS2 0x10000-0x15FFF) — a tune write
# overwrites it.  A reliable MS41.3 DISCRIMINATOR but cal-based; kept for reference.  For the
# PROGRAM half use MS41_3_PROG_CODE_RANGE below (a genuine program-region marker).
MS41_3_PROG_MARKER_ADDR   = 0x11F60
MS41_3_PROG_MARKER_STRING = b"ABHISHEK"

# ★ TRUE program-region MS41.3 marker: SS1v2 fills the program tail 0x39A9A-0x39B69 with code
# where stock MS41.2 leaves 0xFF.  It lives in the PROGRAM sector (SA5/6), so a cal/tune flash
# never touches it — unlike ABHISHEK it identifies the PROGRAM half and survives a cal reflash.
# Ends at 0x39B6A (clear of add-on code caves).  ⚠ Validated against MS41.2 and MS41.3 reads so
# far — widen against more stock images before trusting blindly.
MS41_3_PROG_CODE_RANGE = (0x39A9A, 0x39B6A)   # [lo, hi) file offsets
MS41_3_PROG_CODE_MIN   = 64                    # non-FF bytes to call it SS1v2 (.2 -> 0, .3 -> 208)

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
    def has_ss1v2_program(data):
        """True if the program tail carries SS1v2 code — the genuine MS41.3 PROGRAM marker.
        Stock MS41.2 leaves MS41_3_PROG_CODE_RANGE (file 0x39A9A-0x39B69) as 0xFF; SS1v2 fills
        it with ~208 B of code.  In the program sector (SA5/6), so a cal/tune flash never
        touches it — this identifies the PROGRAM half, not the cal."""
        lo, hi = MS41_3_PROG_CODE_RANGE
        if len(data) < hi:
            return False
        return sum(1 for i in range(lo, hi) if data[i] != 0xFF) >= MS41_3_PROG_CODE_MIN

    @staticmethod
    def detect_program_variant(data):
        """Detect the variant of the PROGRAM region of a 256 KB full ROM, or None.

        MS41.3 is detected by the genuine program-region SS1v2 marker (has_ss1v2_program);
        every other variant maps the ECU ID (file 0x6025, boot/param).  Both are true
        program-region reads (unaffected by a cal reflash) — unlike the cal-resident ABHISHEK
        proxy this actually identifies the PROGRAM half.  (MS41.3 shares MS41.2's ECU ID
        1406464, so the ECU-ID fallback alone would report .3 programs as .2 — the program-code
        marker is what separates them.)"""
        if len(data) < MS41ECU.FULL_ROM_SIZE:
            return None
        if MS41ECU.has_ss1v2_program(data):
            return "MS41.3"
        return _PROG_ECU_ID_MAP.get(MS41ECU.read_ecu_id(data))

    @staticmethod
    def check_hybrid(data):
        """Return a description string if a 256 KB ROM mixes program and calibration from
        incompatible variants, else None (consistent, or not identifiable).

        Cross-FAMILY pairings (MS41.0/.1 vs .2/.3) brick the ECU; an MS41.2<->MS41.3 mismatch
        mis-runs (the .3 program expects SS1v2 cal features the .2 cal lacks, and vice-versa).
        Catches BOTH via the genuine program-region SS1v2 marker (detect_program_variant) vs
        the SS1 cal marker (detect_variant) — the old cal-resident ABHISHEK proxy missed
        cross-family-with-.3-cal and all MS41.2<->MS41.3 hybrids."""
        if len(data) < MS41ECU.FULL_ROM_SIZE:
            return None
        prog_v = MS41ECU.detect_program_variant(data)   # genuine program-region read
        cal_v = MS41ECU.detect_variant(data)            # cal (SS1 marker / CAL ID)
        if prog_v is None or cal_v is None or prog_v == cal_v:
            return None
        pf = _VARIANT_FAMILY.get(prog_v, "?")
        cf = _VARIANT_FAMILY.get(cal_v, "?")
        kind = "cross-family (brick risk)" if pf != cf else "MS41.2/.3 program-cal mismatch"
        return (f"Program region: {prog_v} ({pf})  -  "
                f"Calibration region: {cal_v} ({cf})  [{kind}]")

    @staticmethod
    def looks_cpu_order(data):
        """True if a 256 KB image appears to be CPU/physical order (byte-swapped per 16 KB)
        instead of the expected file/chip order — e.g. a `dump` taken with --cpu-order.

        Such an image must NOT be flashed: the writer descrambles a FILE-order ref, so a
        CPU-order ref would be double-scrambled and brick the ECU.  Signal: the CAL-ID sits at
        the CPU-order offset 0x1000E (= 0x1400E XOR 0x4000) and NOT at the file-order 0x1400E.
        Conservative — a valid file-order full always has its CAL-ID at 0x1400E, so it is never
        flagged (no false positives)."""
        if len(data) != MS41ECU.FULL_ROM_SIZE:
            return False

        def _is_calid(off):
            c = bytes(data[off:off + 8])
            return len(c) == 8 and all(0x30 <= b <= 0x7E for b in c) and c[:2].isdigit()

        return _is_calid(0x1000E) and not _is_calid(0x1400E)
