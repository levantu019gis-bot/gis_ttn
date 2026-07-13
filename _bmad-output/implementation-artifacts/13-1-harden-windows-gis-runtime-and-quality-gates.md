# Story 13.1: Harden Windows GIS Runtime and Quality Gates

Status: done

## Story

As a Developer,
I want the Windows runtime to consistently use the intended Conda/PyInstaller GDAL/PROJ resources,
So that raster, CRS, ingestion, render, and packaged executable workflows do not fail because another installed GIS stack is found first.

## Acceptance Criteria

1. Given the app starts from source or packaged executable on Windows, when `rasterio`, `pyproj`, or GDAL initialize, then they use the project/runtime PROJ data directory instead of a PostgreSQL/PostGIS `proj.db`.
2. Given tests spawn subprocesses, when isolated Qt or config-mode smoke tests run, then `PYTHONPATH`/runtime paths are available and `ModuleNotFoundError: thucthengay` does not occur.
3. Given quality gates run, when `ruff check src tests` executes, then import ordering and lint checks pass.
4. Given full or focused GIS tests run in the configured environment, when CRS/raster fixtures are created, then failures caused by wrong external PROJ database paths are prevented or reported with actionable diagnostics.
5. Given PyInstaller build scripts run, when the app is packaged, then required GDAL/PROJ data paths are bundled or initialized explicitly.

## Tasks / Subtasks

- [x] Add runtime initialization for GIS data paths before raster/CRS imports are used.
- [x] Harden PyInstaller runtime hook/build scripts for GDAL/PROJ data discovery.
- [x] Fix current Ruff import-order failure.
- [x] Ensure subprocess-based tests inherit the needed package path/runtime environment.
- [x] Add or update tests for path initialization and smoke execution.
- [x] Document Windows GIS runtime troubleshooting in README/docs.

## Dev Notes

- The review failure showed `proj.db` being loaded from `C:\Program Files\PostgreSQL\18\share\contrib\postgis-3.6\proj\proj.db`.
- Prefer explicit environment setup at app entrypoint/runtime hook over relying on user PATH ordering.
- This story should not alter render output, map-frame geometry, or export content.

## Verification

- `ruff check src tests`
- Focused CRS/raster tests after runtime path setup
- Smoke app startup from source
- PyInstaller smoke if packaging dependencies are available
