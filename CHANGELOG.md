# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project uses
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

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

[1.0.0]: https://semver.org/
