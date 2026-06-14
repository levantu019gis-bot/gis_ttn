# Story 10.1: Extract Reusable Satellite Download Engine

Status: review

## Story

As a Developer,
I want the existing satellite download script logic extracted into a reusable core service,
so that the app can run the same scan/intersection/copy workflow without embedding business logic in PySide widgets.

## Acceptance Criteria

1. Given the app needs to run satellite download from UI and tests, when the reusable download module is added, then it exposes typed request/result/progress models for GeoJSON files, image folders, output folder, extensions, filename format rules, overwrite, dry-run, include-boundary-touch, preserve-source-tree, and write-manifest options, and the core module does not import PySide6 or `thucthengay.editor`.
2. Given a download request is built, when paths are relative or absolute, then the service resolves and validates selected GeoJSON files, source image folders, and output folder consistently, and invalid initial configuration returns a clear error before scanning starts.
3. Given the old CLI script remains available in `0.Download_Img`, when the app implementation is added, then the implementation either reuses extracted logic or ports it into `src/thucthengay/download/` with equivalent behavior covered by tests, and no production test depends on the real LAN folders from the script config.

## Tasks / Subtasks

- [x] Add core download module contract (AC: 1, 3)
  - [x] Create `src/thucthengay/download/` with public exports.
  - [x] Add typed request/result/progress models for selected GeoJSON files, image folders, output folder, extensions, filename format rules, overwrite, dry-run, include-boundary-touch, preserve-source-tree, and write-manifest.
  - [x] Keep all download code headless: no PySide6 and no `thucthengay.editor` imports.
- [x] Add request path resolution and validation service (AC: 2)
  - [x] Resolve relative paths against an optional base directory while preserving absolute paths.
  - [x] Validate at least one GeoJSON file, at least one image folder, and an output folder path.
  - [x] Return structured Vietnamese configuration errors before scanning starts.
  - [x] Ensure output folder is not equal to or inside any source image folder.
- [x] Add tests and boundary guard (AC: 1, 2, 3)
  - [x] Test valid request resolution for relative and absolute inputs.
  - [x] Test invalid request failures for missing GeoJSON, missing image folder, empty lists, invalid extensions, duplicate-safe source names, and unsafe output location.
  - [x] Add `download` to the core import-boundary test.

## Dev Notes

### Scope

Story 10.1 is the foundation only. Do not implement GeoJSON geometry loading, raster metadata cache, raster intersection, filename parsing, output copying, manifest writing, job worker, or UI tab in this story. Those are Stories 10.2 through 10.7.

### Source Script Intelligence

- Existing script: `D:/0.TU_KHONG_XOA/1.NCPT/1.TTN/0.Download_Img/download_satellite_images_by_geojson.py`.
- Useful script concepts to port over time: `RunConfig`, `ImageFolder`, filename format rules, `safe_name`, `unique_name`, path validation, metadata cache, raster scan, CRS transform, copy, manifest.
- Story 10.1 should establish app-native contracts in `src/thucthengay/download/` rather than import the script from outside the package. Later stories can port behavior from the script into the service.

### Architecture Requirements

- New owner module: `src/thucthengay/download/`.
- The module is a core module and must not import PySide6 or `thucthengay.editor`.
- UI will call this module through a worker/job adapter in later stories.
- Do not mutate workspace state, historical SQLite registry, or config JSON.
- Use stdlib dataclasses/enums or Pydantic models consistently with local patterns. Persisted JSON is not introduced in this story.
- Do not add dependencies.

### Proposed Contract

Core types should support:

- `DownloadImageFolder`: source folder display/safe name and resolved path.
- `DownloadFilenameFormatRule`: name, raw format string, optional `max_cloud_percent`.
- `SatelliteDownloadRequest`: `geojson_files`, `image_folders`, `output_dir`, `extensions`, `filename_formats`, `overwrite`, `dry_run`, `include_boundary_touch`, `preserve_source_tree`, `write_manifest`, optional `base_dir`.
- `ResolvedSatelliteDownloadRequest`: validated/resolved paths and safe/unique source names.
- `SatelliteDownloadProgress`: stage, message, current/total, percent, counters and current source/geojson fields for later stories.
- `SatelliteDownloadResult`: status, counters, issues/errors, output/manifest paths.
- `SatelliteDownloadConfigError`: typed exception carrying Vietnamese message and optional field name.

### Existing Code Patterns To Preserve

- Tests belong in `tests/unit/`.
- Use `conda run -n ttn-env ...` for test/lint commands.
- Import-boundary guard currently lives in `tests/unit/test_core_import_boundaries.py`; add `download` to `CORE_PACKAGES`.
- Keep line length <= 100 and ruff rules green.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.1, SDT-FR5, SDT-FR8, SDT-FR13, SDT-AR1, SDT-AR4.
- `_bmad-output/project-context.md` - module ownership, core/UI boundary, testing rules.
- `D:/0.TU_KHONG_XOA/1.NCPT/1.TTN/0.Download_Img/download_satellite_images_by_geojson.py` - source download script behavior.
- `src/thucthengay/jobs/progress.py` - progress model pattern for long-running jobs.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_core_import_boundaries.py -q`
- `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_1`
- `conda run -n ttn-env ruff check src/thucthengay/download tests/unit/test_download_contract.py tests/unit/test_core_import_boundaries.py`
- `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_core_import_boundaries.py tests/unit/test_ingestion_scanner.py -q --basetemp=.pytest_tmp_codex_download_10_1_related`
- `conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_1_full`
- `conda run -n ttn-env ruff check .`
- `PYTHONPATH=src conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Added `thucthengay.download` as a headless core module with typed request, resolved request, filename format rule, image folder, progress, stats, result, and run status contracts.
- Added `resolve_download_request()` and `SatelliteDownloadConfigError` for pre-scan path/option validation with Vietnamese messages and field names.
- Implemented config-style path resolution with optional base directory, safe/unique source folder naming, extension normalization, and output-folder safety checks.
- Added unit tests for valid path resolution, invalid configuration failures, output safety, non-creation of output folders, and core import boundaries.
- Full regression run reached 501 passed and 5 failures in pre-existing UI/metadata tests unrelated to Story 10.1; targeted and related tests pass.

### File List

- `src/thucthengay/download/__init__.py`
- `src/thucthengay/download/models.py`
- `src/thucthengay/download/service.py`
- `tests/unit/test_download_contract.py`
- `tests/unit/test_core_import_boundaries.py`
- `_bmad-output/implementation-artifacts/10-1-extract-reusable-satellite-download-engine.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-06-14: Created Story 10.1 context and moved status to in-progress.
- 2026-06-14: Implemented Story 10.1 download core contracts and request validation; status moved to review.
