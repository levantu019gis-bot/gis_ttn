# Story 10.4: Write Output Tree and Manifest Per Download Run

Status: review

## Story

As an Operator,
I want downloaded imagery organized by GeoJSON and source folder,
so that each AOI output can be inspected or used as an input folder later.

## Acceptance Criteria

1. Given a selected GeoJSON file named `all_processed.geojson` and a source folder named `20260613`, when an intersecting image is copied, then its destination starts with `<output>/all_processed/20260613/`, and when preserve-source-tree is enabled, the image's relative path under the source folder is preserved below that branch.
2. Given two selected GeoJSON files or source folders have the same sanitized name, when output branches are built, then the engine assigns stable unique safe names using suffixes, and the manifest records the source path and matched GeoJSON so the branch remains traceable.
3. Given the destination file already exists and overwrite is disabled, when the engine would copy the file, then it records `skipped_existing`, and it does not overwrite the existing file.
4. Given dry-run is enabled, when the engine processes matching images, then it records the destination path that would be used, and it does not create or overwrite image files.
5. Given write-manifest is enabled, when the run finishes or is cancelled after processing at least one candidate, then a CSV manifest is written in the output folder, and the manifest includes status, source folder, source path, destination path, matched GeoJSON, filename-format fields, capture datetime, cloud percent, max cloud percent, and error.

## Tasks / Subtasks

- [x] Add output destination planning and safe unique GeoJSON branches (AC: 1, 2)
  - [x] Build one output row per accepted image and matched GeoJSON.
  - [x] Use `<output>/<geojson_name>/<source_folder_name>/...` for destination paths.
  - [x] Preserve source-relative path only when `preserve_source_tree=true`; otherwise use filename only.
  - [x] Keep GeoJSON/source branch names stable and unique using the existing `safe_name`/`unique_name` pattern.
- [x] Add copy/dry-run/skipped-existing handling (AC: 3, 4)
  - [x] Copy accepted rows with `shutil.copy2` only when not dry-run.
  - [x] Record `skipped_existing` without overwriting when overwrite is disabled.
  - [x] Record dry-run destination without creating image files.
  - [x] Convert copy `OSError` into failed manifest rows without aborting other rows.
- [x] Add CSV manifest writing (AC: 2, 5)
  - [x] Write manifest only when `write_manifest=true` and there is at least one processed row.
  - [x] Include copied, dry-run, skipped-existing, skipped-cloud, and failed rows where present.
  - [x] Include required columns for status, source folder, source path, destination path, matched GeoJSON, filename-format metadata, cloud thresholds, and error.
- [x] Add focused tests (AC: 1, 2, 3, 4, 5)
  - [x] Test output tree with GeoJSON/source branches and preserved relative path.
  - [x] Test duplicate safe names use suffixes and manifest remains traceable.
  - [x] Test skipped-existing and dry-run do not overwrite/create image files.
  - [x] Test manifest contains accepted, skipped-cloud, and failed rows with filename metadata.

## Dev Notes

### Scope

Story 10.4 consumes the headless matching/filtering contracts from Stories 10.2 and 10.3. It may copy files and write a CSV manifest under the selected output folder. It must not add job progress/cancellation adapters, PySide UI, workspace ingestion mutations, workspace manifest writes, historical SQLite writes, or config UI.

### Technical Requirements

- Build under `src/thucthengay/download/`.
- Reuse existing contracts:
  - `ResolvedSatelliteDownloadRequest` for output/options.
  - `DownloadFilenameFilterResult` for accepted, skipped-cloud, failed, warning, and stats input.
  - `DownloadImageMatch.matched_geojson_names` and `matched_geojson_paths` for per-AOI output branches.
  - `DownloadFilenameMetadata` for manifest fields.
- Output structure must follow Epic 10, not the old script's simpler source-folder-only structure: `<output>/<geojson_name>/<source_folder_name>/...`.
- Core download modules must remain headless and must not import `PySide6` or `thucthengay.editor`.
- Manifest writing should use Python standard-library `csv` and UTF-8.
- Preserve file metadata with `shutil.copy2` for actual copies.
- Do not scan or delete existing output trees; check only the destination path for the row being processed.

### Previous Story Intelligence

- Story 10.1 established request/result/progress models, path validation, `safe_name`, and `unique_name`.
- Story 10.2 established explicit GeoJSON matching and records all matched GeoJSON names/paths per source image.
- Story 10.3 established `PreparedDownloadImage`, `SkippedCloudDownloadImage`, `DownloadFilenameFilterResult`, and filename metadata for manifest output.
- Full pytest currently has 5 known pre-existing failures in editor/metadata/isolated Qt tests outside the download module; focused download tests and ruff should still pass.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.4 and SDT-FR4/FR6/FR7/FR8/FR10/FR13.
- `_bmad-output/implementation-artifacts/10-1-extract-reusable-satellite-download-engine.md`
- `_bmad-output/implementation-artifacts/10-2-match-source-geotiffs-against-explicit-geojson-files.md`
- `_bmad-output/implementation-artifacts/10-3-parse-filename-metadata-and-apply-cloud-filters.md`
- `D:/0.TU_KHONG_XOA/1.NCPT/1.TTN/0.Download_Img/download_satellite_images_by_geojson.py` - source behavior for copy status and CSV manifest field names.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-06-14: RED `conda run -n ttn-env pytest tests/unit/test_download_output.py -q --basetemp=.pytest_tmp_codex_download_10_4_red` failed as expected because `write_download_outputs` API did not exist.
- 2026-06-14: GREEN focused `conda run -n ttn-env pytest tests/unit/test_download_output.py -q --basetemp=.pytest_tmp_codex_download_10_4` passed: 4 passed.
- 2026-06-14: Regression scope `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_download_output.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_4_group` passed: 25 passed.
- 2026-06-14: `conda run -n ttn-env ruff check src/thucthengay/download tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_download_output.py tests/unit/test_core_import_boundaries.py` passed.
- 2026-06-14: `conda run -n ttn-env ruff check .` passed with the existing Windows access warning while scanning temp folders.
- 2026-06-14: Full suite with UTF-8 output `conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_4_full_utf8` reported 514 passed, 5 failed in pre-existing editor/metadata/isolated Qt tests outside download scope.
- 2026-06-14: Smoke `$env:PYTHONPATH='src'; conda run -n ttn-env python -m thucthengay --smoke` passed: `3.ThucTheNgay app ready.`

### Implementation Plan

- Added a headless output stage that consumes `DownloadFilenameFilterResult` after matching/cloud filtering.
- Added manifest row/result contracts for later job/UI stories.
- Kept output writes scoped to selected output folder; no workspace/cache/composition/history mutation.

### Completion Notes List

- Implemented `write_download_outputs()` to create one processed row per accepted image and matched GeoJSON.
- Implemented destination planning as `<output>/<geojson_name>/<source_folder_name>/...`, including source-relative preservation when enabled.
- Implemented actual copy with `shutil.copy2`, dry-run rows, skipped-existing rows, copy failure rows, and stats updates.
- Implemented CSV manifest writing with required traceability and filename metadata columns.
- Added focused tests covering all Story 10.4 acceptance criteria.

### File List

- src/thucthengay/download/__init__.py
- src/thucthengay/download/models.py
- src/thucthengay/download/output.py
- tests/unit/test_download_output.py
- _bmad-output/implementation-artifacts/10-4-write-output-tree-and-manifest-per-download-run.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-14: Created Story 10.4 context and moved status to in-progress.
- 2026-06-14: Implemented output tree planning, copy/dry-run/skipped handling, CSV manifest writing, focused tests, and moved story to review.
