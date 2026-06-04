# Investigation: Packaged exe closes immediately

## Hand-off Brief

1. **What happened.** Confirmed: `dist\ThucTheNgay\ThucTheNgay.exe` exited with code 0 within 5 seconds instead of keeping the GUI process alive.
2. **Where the case stands.** Root cause confirmed: PyInstaller executed `src/thucthengay/app.py` as a script, but that file only defined `main()` and did not call it when run as `__main__`.
3. **What's needed next.** Rebuild the executable and verify normal startup keeps the GUI process running.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-04 |
| Status | Concluded, fix verified |
| System | Windows PowerShell, PyInstaller onedir output |
| Evidence sources | User report, local packaged exe, PyInstaller spec, app entrypoint |

## Problem Statement

User reported that after following README section 8.2 and building `dist\ThucTheNgay\ThucTheNgay.exe`, double-clicking the executable produced no visible result and the app appeared to close immediately.

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| `dist\ThucTheNgay\ThucTheNgay.exe` | Available | Running without args exited with code 0 within 5 seconds. |
| `scripts/pyinstaller/thucthengay_windows.spec` | Available | Analysis entrypoint pointed at `src/thucthengay/app.py`. |
| `src/thucthengay/app.py` | Available | Defines `main()` but previously had no `if __name__ == "__main__"` guard. |
| `src/thucthengay/__main__.py` | Available | Correct package entrypoint calls `main()` via `raise SystemExit(main())`. |

## Confirmed Findings

### Finding 1: Packaged GUI process exits immediately

**Evidence:** PowerShell start probe returned `EXITED=0` after launching `dist\ThucTheNgay\ThucTheNgay.exe`.

**Detail:** A healthy GUI launch should leave the Qt event loop running until the window is closed.

### Finding 2: PyInstaller entrypoint did not call `main()`

**Evidence:** `scripts/pyinstaller/thucthengay_windows.spec` previously used `app.py` as the script entrypoint, while `app.py` only defined `main()`.

**Detail:** Executing such a file as a script completes top-level definitions and exits successfully without opening the GUI.

## Deduced Conclusions

### Deduction 1: The exe did not crash; it completed without starting the app

**Based on:** Finding 1 and Finding 2.

**Reasoning:** The process exit code was 0, and there was no Windows Application Error event. The PyInstaller script target had no top-level call into the app.

**Conclusion:** The observed double-click behavior is caused by a missing script entrypoint, not by a runtime crash in Qt/GDAL.

## Conclusion

**Confidence:** High

Root cause is confirmed. The packaged executable closed immediately because PyInstaller was executing a module that did not call `main()`.

## Recommended Next Steps

### Fix direction

Use `src/thucthengay/__main__.py` as the PyInstaller script entrypoint and add a direct-script guard to `src/thucthengay/app.py`. This fix has been applied.

### Diagnostic

After rebuilding, `ThucTheNgay.exe --smoke` exited 0 and launching `ThucTheNgay.exe` without args left the process running after 5 seconds.

## Verification Results

| Check | Result |
| --- | --- |
| `conda run -n ttn-env python -m pytest tests\unit\test_pyinstaller_entrypoint.py` | Passed |
| `conda run -n ttn-env ruff check src\thucthengay\app.py tests\unit\test_pyinstaller_entrypoint.py` | Passed |
| `conda run -n ttn-env python -m thucthengay --smoke` | Passed |
| `PYTHONPATH=src conda run -n ttn-env python src\thucthengay\app.py --smoke` | Passed |
| `.\scripts\build_windows_exe.ps1` | Passed |
| `dist\ThucTheNgay\ThucTheNgay.exe --smoke` | Passed |
| GUI startup probe | Passed: process stayed running after 5 seconds |

## Reproduction Plan

1. Build with `.\scripts\build_windows_exe.ps1`.
2. Run `dist\ThucTheNgay\ThucTheNgay.exe --smoke`.
3. Launch `dist\ThucTheNgay\ThucTheNgay.exe` without args.
4. Confirm the process remains alive after 5 seconds.
