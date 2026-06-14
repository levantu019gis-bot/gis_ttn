# Story 10.7: Wire Download Run Results, Summary, and App Boundaries

Status: review

## Story

As an Operator,
I want clear completion evidence after a download run,
so that I know what was copied, skipped, failed, and where to use the output next.

## Acceptance Criteria

1. Given a download run succeeds, when the job finishes, then the tab shows a completion summary with total scanned, matched, copied/downloaded, skipped existing, skipped cloud, failed, cache hits/misses, output folder, and manifest path.
2. Given the run finishes with warnings or failed images, when the summary is shown, then it identifies the failure count and provides Vietnamese remediation to inspect the manifest and verify unreadable paths, permissions, CRS, filename rules, or disk space.
3. Given the run is cancelled, when the summary is shown, then it clearly states that output may be partial and still reports partial counters and manifest path if available.
4. Given the download tab writes output files, when the run completes, then it does not mutate workspace `manifest.json`, `cache/`, `compositions/`, `renders/`, `exports/`, or historical SQLite state, and the Operator can later choose the output branch as an imagery input folder through the existing ingest workflow.

## Tasks / Subtasks

- [x] Add a Qt worker boundary for satellite download jobs (AC: 1, 2, 3)
  - [x] Create an editor-layer worker that runs `run_satellite_download_job` in a `QThread`.
  - [x] Reuse `JobControl` for cancellation and emit existing `ProgressEvent` / `SatelliteDownloadResult` objects.
  - [x] Convert unexpected worker exceptions to a terminal result/status instead of crashing the UI thread.
- [x] Wire `DownloadMode` action/progress/cancel behavior (AC: 1, 2, 3)
  - [x] Start the worker from `DownloadMode.downloadRequested` through `AppShell`.
  - [x] Disable conflicting form controls while a run is active and expose a safe Cancel button.
  - [x] Show progress percentage, current activity text, counters, source folder, GeoJSON, and match context when available.
- [x] Add completion summary and remediation text (AC: 1, 2, 3)
  - [x] Show summary counters for scanned, matched, copied, skipped existing, skipped cloud, failed, cache hits/misses.
  - [x] Show output folder and manifest path when available.
  - [x] For warning/error/cancelled states, show Vietnamese remediation covering manifest inspection, unreadable paths, permissions, CRS, filename rules, and disk space.
  - [x] For cancelled state, explicitly state that output may be partial.
- [x] Preserve app boundaries (AC: 4)
  - [x] Keep the download tab independent from workspace manifest/cache/compositions/renders/exports and historical SQLite.
  - [x] Do not import or call `WorkspaceService`, `HistoryService`, ingestion, render, or export from `DownloadMode` or the download worker.
  - [x] Make summary text clear that the output branch can be selected later as an imagery input folder in Setup.
- [x] Add focused tests (AC: 1, 2, 3, 4)
  - [x] Test a successful finished result renders all required counters and output/manifest paths.
  - [x] Test warning/failed-image result renders failure count and Vietnamese remediation.
  - [x] Test cancelled result renders partial-output warning and partial counters.
  - [x] Test app-shell wiring starts/cancels a download run through the worker boundary without mutating workspace/history services.

## Dev Notes

### Scope

Story 10.7 wires the existing headless download job to the UI. It must not change matching, filename parsing, output copy semantics, manifest columns, workspace ingestion, historical SQLite, render, or export logic unless a test exposes a direct integration bug in this story.

### Technical Requirements

- UI/threading code belongs in `src/thucthengay/editor/`; headless job orchestration remains in `src/thucthengay/jobs/download_job.py`.
- Add a worker sibling to `IngestionWorker` / `ExportWorker`, for example `src/thucthengay/editor/download_worker.py`.
- `DownloadMode` should expose methods like `start_download_progress()`, `show_download_progress(event)`, `show_download_summary(result)`, and `mark_download_stopping()` rather than putting thread management inside the widget.
- `AppShell` should own `QThread`, worker, and `JobControl`, matching the ingestion pattern already used in `src/thucthengay/editor/app_shell.py`.
- Existing request creation remains `DownloadMode.selected_request()` from Story 10.6.
- Existing progress contract is `ProgressEvent` with download counters and `percent`.
- Existing final result contract is `SatelliteDownloadResult` with `DownloadRunStatus`, `DownloadStats`, `output_dir`, `manifest_path`, `output_rows`, `issues`, and `message`.
- Summary/remediation must be visible text, not color-only status.
- The download tab must not import or call `WorkspaceService`, `HistoryService`, ingestion, render, or export services.
- No new dependencies.

### Previous Story Intelligence

- Story 10.5 implemented `run_satellite_download_job(job_id, request, control=None, publish=None)` with setup, scan, filter, output, manifest, complete/cancel/error progress.
- Story 10.5 cancellation is cooperative and returns partial rows/manifest when cancellation happens after output begins.
- Story 10.6 implemented the top-level `DownloadMode` tab, explicit GeoJSON file rows, multiple source folders, output folder, request options, blockers, and `downloadRequested` signal. It intentionally did not run the job.
- Story 10.6 test patterns instantiate Qt widgets with `QT_QPA_PLATFORM=offscreen` and use `PreferencesService(tmp_path / "preferences.json")`.
- Full pytest currently has known pre-existing failures in editor metadata/date-change and isolated Qt import tests outside download scope; focused download tests and scoped regressions must pass.

### Project Structure Notes

- New worker: `src/thucthengay/editor/download_worker.py`.
- Modify UI: `src/thucthengay/editor/modes/download_mode.py`.
- Modify shell wiring: `src/thucthengay/editor/app_shell.py`.
- Tests: extend `tests/unit/test_download_mode.py` and add focused tests if needed.
- Keep core import boundary tests green: core download/jobs modules must remain free of `PySide6` and editor imports.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.7 and SDT-FR10/FR11/FR12/FR13/SDT-UX2/SDT-UX3.
- `_bmad-output/implementation-artifacts/10-5-run-satellite-download-as-a-progress-job.md`
- `_bmad-output/implementation-artifacts/10-6-add-satellite-download-tab-ui.md`
- `src/thucthengay/editor/app_shell.py`
- `src/thucthengay/editor/ingestion_worker.py`
- `src/thucthengay/editor/export_worker.py`
- `src/thucthengay/editor/modes/download_mode.py`
- `src/thucthengay/jobs/download_job.py`
- `src/thucthengay/jobs/progress.py`
- `src/thucthengay/download/models.py`

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-06-14: RED `conda run -n ttn-env pytest tests/unit/test_download_mode.py -q --basetemp=.pytest_tmp_codex_download_10_7_red` failed as expected: `DownloadMode` had no progress/summary methods and `AppShell` had no `download_runner` wiring.
- 2026-06-14: Focused `conda run -n ttn-env pytest tests/unit/test_download_mode.py -q --basetemp=.pytest_tmp_codex_download_10_7_green2` passed: 9 passed after implementing worker/progress/summary.
- 2026-06-14: Added boundary guard and final focused `conda run -n ttn-env pytest tests/unit/test_download_mode.py -q --basetemp=.pytest_tmp_codex_download_10_7_focus_final` passed: 10 passed.
- 2026-06-14: Scoped ruff `conda run -n ttn-env ruff check src/thucthengay/editor/download_worker.py src/thucthengay/editor/modes/download_mode.py src/thucthengay/editor/app_shell.py tests/unit/test_download_mode.py` passed.
- 2026-06-14: Regression group `conda run -n ttn-env pytest tests/unit/test_setup_mode.py tests/unit/test_download_mode.py tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_download_output.py tests/unit/test_download_job.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_7_group2` passed: 57 passed.
- 2026-06-14: Full suite `$env:PYTHONIOENCODING='utf-8'; $env:CONDA_REPORT_ERRORS='false'; conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_7_full` reported 528 passed, 5 failed in pre-existing Review/Edit metadata/date-change and isolated Config Qt import tests outside Story 10.7 scope.
- 2026-06-14: Full ruff `conda run -n ttn-env ruff check .` passed with existing Windows access warning while scanning temp folders.
- 2026-06-14: Smoke `$env:PYTHONPATH='src'; conda run -n ttn-env python -m thucthengay --smoke` passed: `3.ThucTheNgay app ready.`

### Implementation Plan

- Added a Qt `DownloadWorker` sibling to existing ingestion/export workers.
- Let `AppShell` own download `QThread`, `JobControl`, worker lifecycle, cancellation, and result handoff.
- Kept `DownloadMode` responsible only for request UI, progress rendering, cancellation signal, and final summary text.
- Added focused UI tests with an injected fake runner so no real raster/network paths are needed.

### Completion Notes List

- Implemented `DownloadWorker` that runs `run_satellite_download_job`, publishes existing progress events, and converts unexpected errors into a terminal `SatelliteDownloadResult`.
- Wired `DownloadMode.downloadRequested` and `cancelRequested` in `AppShell`.
- Added progress bar/detail text for percent, counters, current source folder, GeoJSON, and match context.
- Added summary text for success, warning/error, and cancelled states, including output folder, manifest path, partial-output warning, and Vietnamese remediation.
- Added a boundary guard test that `DownloadMode` and `DownloadWorker` do not import workspace/history/ingestion/render/export services.

### File List

- src/thucthengay/editor/app_shell.py
- src/thucthengay/editor/download_worker.py
- src/thucthengay/editor/modes/download_mode.py
- tests/unit/test_download_mode.py
- _bmad-output/implementation-artifacts/10-7-wire-download-run-results-summary-and-app-boundaries.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-14: Created Story 10.7 context from Epic 10 and previous download stories.
- 2026-06-14: Started implementation and moved status to in-progress.
- 2026-06-14: Implemented download worker wiring, progress/cancel UI, result summary/remediation, tests, and moved story to review.
