# Story 7.4: Package Windows Executable Tooling

Status: review

## Story

As an Operator,
I want a repeatable Windows `.exe` packaging command,
So that the desktop app can be prepared for use outside the development shell.

## Acceptance Criteria

1. Given the project is checked out on Windows with Miniconda, when `scripts/build_windows_exe.ps1` runs in `ttn-env`, then PyInstaller builds `dist\ThucTheNgay\ThucTheNgay.exe` by default.
2. Given `-Mode onefile` is passed, when the build runs, then PyInstaller attempts a single-file `dist\ThucTheNgay.exe` build.
3. Given the app depends on PySide6/GDAL/rasterio, when the executable starts, then bundled PROJ/GDAL data and relevant native DLL paths are configured before runtime imports.
4. Given packaging completes, when smoke verification runs, then `ThucTheNgay.exe --smoke` succeeds unless the caller explicitly passed `-SkipSmoke`.

## Tasks / Subtasks

- [x] Add Windows packaging script.
- [x] Add PyInstaller spec for one-folder and one-file modes.
- [x] Add runtime hook for GDAL/PROJ path setup.
- [x] Add PyInstaller to `environment.yml`.
- [x] Document Windows packaging command in `README.md`.
- [x] Run actual Windows PyInstaller build.
- [x] Verify packaged `ThucTheNgay.exe --smoke` on Windows.
- [x] Verify packaged GUI startup does not exit immediately.

## Implementation Evidence

- Primary code: `scripts/build_windows_exe.ps1`, `scripts/pyinstaller/thucthengay_windows.spec`, `scripts/pyinstaller/rthook_thucthengay_gis.py`.
- Supporting docs/config: `README.md`, `environment.yml`.

## Current State Notes

- Story remains in `review` pending code review, but Windows PyInstaller build and smoke verification have now been run on Windows.
- One-folder output remains the preferred packaging mode until representative Windows GIS/export workflows are tested.
- 2026-06-04 investigation found the initial `.exe` closed immediately because PyInstaller executed `src/thucthengay/app.py`, which did not call `main()` when run as a script. The spec now uses `src/thucthengay/__main__.py`, and `app.py` also has a direct-script guard.

## Verification To Date

- `uv lock --check` passed after keeping PyInstaller in conda `environment.yml` rather than `pyproject.toml`.
- PyInstaller spec Python syntax check passed.
- Runtime hook `py_compile` passed.
- App smoke passed with `python -m thucthengay --smoke`.
- 2026-06-04: `conda run -n ttn-env python -m pytest tests\unit\test_pyinstaller_entrypoint.py` passed.
- 2026-06-04: `conda run -n ttn-env ruff check src\thucthengay\app.py tests\unit\test_pyinstaller_entrypoint.py` passed.
- 2026-06-04: `conda run -n ttn-env python -m thucthengay --smoke` passed.
- 2026-06-04: `PYTHONPATH=src conda run -n ttn-env python src\thucthengay\app.py --smoke` passed.
- 2026-06-04: `.\scripts\build_windows_exe.ps1` built `dist\ThucTheNgay\ThucTheNgay.exe` and packaged smoke printed `3.ThucTheNgay app ready.`
- 2026-06-04: launching `dist\ThucTheNgay\ThucTheNgay.exe` without args stayed running after 5 seconds; the verification process was then stopped manually.

## Change Log

- 2026-06-03: Added BMAD story wrapper for Windows executable packaging tooling.
