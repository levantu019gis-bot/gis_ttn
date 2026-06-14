# Story 10.8: Add Download Engine and UI Regression Tests

Status: review

## Story

As a Developer,
I want focused tests for the download tab workflow,
so that future changes do not break GeoJSON-file selection, output structure, progress, or app boundaries.

## Acceptance Criteria

1. Given generated GeoTIFF and GeoJSON fixtures are available in a temp test directory, when the download engine runs against intersecting and non-intersecting rasters, then tests verify matching, CRS transform behavior where practical, copied output structure, cloud skip behavior, and manifest rows.
2. Given one image intersects two GeoJSON files, when the engine writes outputs, then tests verify that each matched GeoJSON branch receives or reports the image according to the configured output behavior.
3. Given a run uses multiple source image folders, when output branches are generated, then tests verify safe/unique source folder branch naming and preserve-source-tree behavior.
4. Given the job wrapper is tested without a real Qt event loop, when progress events are collected, then tests verify counters and stage messages include enough detail for the UI progress panel.
5. Given UI tests instantiate the download tab, when GeoJSON files, image folders, and output folder are added or removed, then tests verify control state, disabled reasons, and that no workspace service write is triggered by the download workflow.

## Tasks / Subtasks

- [x] Add full-pipeline engine regression fixtures (AC: 1, 2)
  - [x] Generate temp GeoTIFFs and explicit GeoJSON files in tests; no real LAN paths or network.
  - [x] Cover intersecting, non-intersecting, CRS-transform, and cloud-skip cases in a single job/engine-level regression.
  - [x] Assert copied output tree and manifest rows include accepted and skipped-cloud rows.
- [x] Add multi-GeoJSON and multi-source output branch regressions (AC: 2, 3)
  - [x] Verify one source image matched to two GeoJSON files produces one output/report row per GeoJSON branch.
  - [x] Verify duplicate sanitized source folder names get stable unique branch names.
  - [x] Verify preserve-source-tree keeps nested relative paths under each source branch.
- [x] Strengthen progress/job wrapper regression coverage (AC: 4)
  - [x] Collect `ProgressEvent` values without a Qt event loop.
  - [x] Assert stage sequence, percent/counter fields, source folder, current GeoJSON, and match context are UI-usable.
- [x] Strengthen download tab UI regression coverage (AC: 5)
  - [x] Test add/remove/clear flows for GeoJSON file list and image folder list.
  - [x] Test control state and disabled reason after rows are removed.
  - [x] Keep/import boundary guard that download UI/worker do not call workspace/history/ingestion/render/export services.
- [x] Run validation gates and update artifacts
  - [x] Run focused download regression tests in conda env `ttn-env`.
  - [x] Run scoped ruff on changed files.
  - [x] Run full pytest, full ruff, and app smoke; record known unrelated failures if any remain.

## Dev Notes

### Scope

Story 10.8 is primarily a test-hardening story. Do not change production download behavior unless the new regression tests expose a real bug directly tied to Epic 10 acceptance criteria. Keep changes focused on `tests/unit/` unless a minimal production fix is required.

### Technical Requirements

- Use generated fixtures under `tmp_path`: small rasterio GeoTIFFs and JSON-written GeoJSON files.
- No tests may depend on real folders under `0.Download_Img`, LAN shares, downloaded imagery, or network access.
- Prefer calling `run_satellite_download_job()` for full pipeline regressions because it exercises request resolution, matching, filename filtering, output writing, manifest writing, counters, and progress in one contract.
- Use existing public contracts from `thucthengay.download` and `thucthengay.jobs`; avoid importing private functions unless test locality demands it.
- Keep Qt UI tests offscreen using the existing pattern in `tests/unit/test_download_mode.py`.
- Core import boundary must remain: `src/thucthengay/download` and `src/thucthengay/jobs` must not import PySide6 or editor modules.
- Do not mutate workspace `manifest.json`, `cache/`, `compositions/`, `renders/`, `exports/`, or historical SQLite from download tests.
- No new dependencies.

### Existing Test Coverage to Reuse

- `tests/unit/test_download_contract.py` covers request validation and safe unique source folder names at resolve time.
- `tests/unit/test_download_matching.py` covers explicit GeoJSON loading, CRS transform, multi-GeoJSON matches, and failed rasters.
- `tests/unit/test_download_filename_filter.py` covers filename metadata and cloud filtering.
- `tests/unit/test_download_output.py` covers output tree, manifest fields, dry-run, skipped existing, and failed rows.
- `tests/unit/test_download_job.py` covers job stages, cancellation, partial manifests, and nonfatal raster failures.
- `tests/unit/test_download_mode.py` covers tab insertion, request construction, progress/summary UI, app-shell worker wiring, and current boundary guard.

### Previous Story Intelligence

- Story 10.7 added `DownloadWorker`, AppShell thread ownership, progress/cancel UI, summary/remediation text, and an injected `download_runner` for tests.
- Story 10.7 focused tests passed, while full pytest still had known pre-existing failures in Review/Edit metadata/date-change and isolated Config Qt import tests outside download scope.
- Existing full-suite command should use `--basetemp` inside the repo to avoid Windows temp permission errors.

### Project Structure Notes

- Expected test additions:
  - `tests/unit/test_download_regression.py` for pipeline/output/progress regressions.
  - Extend `tests/unit/test_download_mode.py` only for UI add/remove/clear regressions if needed.
- Production source should remain unchanged unless tests expose a direct Epic 10 defect.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.8 and SDT-FR2/FR3/FR6/FR7/FR9/FR10/FR13/SDT-AR4.
- `_bmad-output/implementation-artifacts/10-1-extract-reusable-satellite-download-engine.md`
- `_bmad-output/implementation-artifacts/10-2-match-source-geotiffs-against-explicit-geojson-files.md`
- `_bmad-output/implementation-artifacts/10-3-parse-filename-metadata-and-apply-cloud-filters.md`
- `_bmad-output/implementation-artifacts/10-4-write-output-tree-and-manifest-per-download-run.md`
- `_bmad-output/implementation-artifacts/10-5-run-satellite-download-as-a-progress-job.md`
- `_bmad-output/implementation-artifacts/10-6-add-satellite-download-tab-ui.md`
- `_bmad-output/implementation-artifacts/10-7-wire-download-run-results-summary-and-app-boundaries.md`
- `_bmad-output/project-context.md`

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-06-14: Started implementation and moved status to in-progress.
- 2026-06-14: Focused RED/GREEN `conda run -n ttn-env pytest tests/unit/test_download_regression.py tests/unit/test_download_mode.py -q --basetemp=.pytest_tmp_codex_download_10_8_focus` initially failed on two over-strict test expectations: terminal complete progress has no percent and `QWidget.isVisible()` depends on parent show state. Adjusted tests to assert scan percent and `isHidden()` visibility flag.
- 2026-06-14: Focused `conda run -n ttn-env pytest tests/unit/test_download_regression.py tests/unit/test_download_mode.py -q --basetemp=.pytest_tmp_codex_download_10_8_focus2` passed: 13 passed.
- 2026-06-14: Scoped ruff `conda run -n ttn-env ruff check tests/unit/test_download_regression.py tests/unit/test_download_mode.py` passed.
- 2026-06-14: Download regression group `conda run -n ttn-env pytest tests/unit/test_setup_mode.py tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_download_output.py tests/unit/test_download_job.py tests/unit/test_download_mode.py tests/unit/test_download_regression.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_8_group` passed: 60 passed.
- 2026-06-14: Full pytest `$env:PYTHONIOENCODING='utf-8'; $env:CONDA_REPORT_ERRORS='false'; conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_8_full` reported 531 passed, 5 failed in known pre-existing Review/Edit metadata/date-change and isolated Config Qt import tests outside Story 10.8 scope.
- 2026-06-14: Full ruff `conda run -n ttn-env ruff check .` passed with existing Windows access warning while scanning temp paths.
- 2026-06-14: Smoke `$env:PYTHONPATH='src'; conda run -n ttn-env python -m thucthengay --smoke` passed: `3.ThucTheNgay app ready.`

### Implementation Plan

- Add a dedicated regression test module that exercises the full download job with generated GeoTIFF/GeoJSON fixtures.
- Extend existing download UI tests for add/remove/clear state transitions.
- Keep production code unchanged unless the regression tests expose an Epic 10 defect.

### Completion Notes List

- Added full-pipeline download regression tests using generated GeoTIFF/GeoJSON fixtures under `tmp_path`.
- Covered one accepted image copied to two GeoJSON branches, one cloud-skipped image reported to both branches, and one non-intersecting image excluded from output/manifest rows.
- Covered CRS transform from GeoJSON EPSG:4326 to raster EPSG:3857, duplicate source folder safe names, and preserve-source-tree nested output paths.
- Strengthened job progress assertions for stage sequence, percent during scan, counters, current source folder, current GeoJSON, and match context.
- Extended download tab UI tests for add/remove/clear flows, disabled reasons, and empty-state visibility flags.
- No production code changes were required.

### File List

- tests/unit/test_download_regression.py
- tests/unit/test_download_mode.py
- _bmad-output/implementation-artifacts/10-8-add-download-engine-and-ui-regression-tests.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-14: Created Story 10.8 context from Epic 10 and prior download stories.
- 2026-06-14: Started implementation and moved status to in-progress.
- 2026-06-14: Added download engine/job/UI regression tests, ran validation gates, and moved story to review.
