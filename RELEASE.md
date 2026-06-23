# Releasing

How to cut a new release of the MS41 BSL Unbricker.

## 1. Version + changelog
- Bump `__version__` in `bsl_unbrick.py` ([SemVer](https://semver.org/): PATCH = bugfix,
  MINOR = new feature, MAJOR = breaking change). `pyproject.toml` reads this automatically.
- Add a `## [x.y.z] — DATE` section to `CHANGELOG.md`.

## 2. Build the artifacts
From the repo root (a fresh virtualenv is recommended):
```bash
python -m pip install --upgrade build pyinstaller

# pip package -> dist/ms41_bsl_unbrick-<ver>-py3-none-any.whl + .tar.gz
python -m build

# standalone Windows exe -> dist/bsl_unbrick.exe   (must be built on Windows)
pyinstaller --onefile --name bsl_unbrick --console --noconfirm bsl_unbrick.py
```
Smoke-test:
```bash
./dist/bsl_unbrick.exe --version          # -> MS41 BSL Unbricker x.y.z
```

## 3. Commit, tag, push
```bash
git add -A
git commit -m "Release x.y.z"
git tag -a vx.y.z -m "MS41 BSL Unbricker x.y.z"
git push origin main
git push origin vx.y.z
```

## 4. GitHub Release
- **github.com/CAATZ/MS41-BSL-Unbricker/releases/new** → choose tag `vx.y.z`
- Title `MS41 BSL Unbricker x.y.z`; notes from the matching `CHANGELOG.md` section
- Attach `dist/bsl_unbrick.exe`, the `.whl`, and the `.tar.gz`
- Publish

Or with the GitHub CLI:
```bash
gh release create vx.y.z --title "MS41 BSL Unbricker x.y.z" --notes-file notes.md \
    dist/bsl_unbrick.exe dist/*.whl dist/*.tar.gz
```

## Notes
- The `.exe` is **Windows-x64 only** (PyInstaller builds per-platform); other OSes use the wheel.
- PyInstaller exes can trigger antivirus / SmartScreen false positives.
- `dist/` and `build/` are git-ignored — artifacts ship on the Release, not in the repo.
