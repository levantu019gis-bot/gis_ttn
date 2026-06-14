# Story 10.5: Run Satellite Download as a Progress Job

Status: review

## Story

As an Operator,
I want long download runs to show progress and allow safe cancellation,
so that scanning large LAN imagery folders does not freeze the application.

## Acceptance Criteria

1. Given a download run is started from the UI, when the job runs, then it executes through the existing headless job/progress pattern and exposes typed progress events that a Qt worker can publish outside the main thread.
2. Given images are being scanned or copied, when progress events are emitted, then they include percentage when computable, stage, activity text, total images, scanned images, matched images, downloaded/copied images, skipped existing, skipped cloud, failed images, metadata cache hits/misses, current source folder, and current GeoJSON or match context when known.
3. Given the Operator cancels the job, when cancellation is observed between candidates, then the job stops after the current safe unit of work and returns cancelled state with partial counters, partial output rows, and manifest path if written.
4. Given a non-fatal raster or copy error occurs, when the job continues, then progress and final summary include the failure count and detailed error is available through manifest rows or issue/status detail.

## Tasks / Subtasks

- [x] Add download job orchestration using the existing job/progress pattern (AC: 1, 2)
  - [x] Add a headless `run_satellite_download_job` adapter under the jobs layer.
  - [x] Reuse `JobControl`, `JobCancelled`, `JobState`, and `ProgressEvent`; do not introduce PySide dependencies.
  - [x] Orchestrate request resolution, GeoJSON/raster matching, filename/cloud filtering, output copying, and manifest writing.
- [x] Add progress and cancellation hooks to the download pipeline (AC: 2, 3)
  - [x] Emit scan progress between raster candidates with current source folder and match context.
  - [x] Emit filter/copy/manifest progress with accepted, skipped-cloud, skipped-existing, copied, failed, and cache counters.
  - [x] Observe cancellation between candidates/rows and return a cancelled result instead of raising to UI.
- [x] Preserve non-fatal error detail and partial output reporting (AC: 3, 4)
  - [x] Keep failed raster/copy rows in final result/manifest without aborting other candidates.
  - [x] Return partial output rows and manifest path when cancellation happens after output processing has started.
  - [x] Convert setup/config/runtime failures into Vietnamese `Issue` details with remediation.
- [x] Add focused tests (AC: 1, 2, 3, 4)
  - [x] Test successful job progress counters and terminal state.
  - [x] Test cancellation before/while processing returns cancelled with partial counters.
  - [x] Test non-fatal raster/copy failures are counted and represented in detail.
  - [x] Test core import boundaries still pass.

## Dev Notes

### Scope

Story 10.5 is a headless job/orchestration story. It must not add the new download tab UI, Qt worker classes, path picker widgets, workspace ingestion mutations, historical SQLite writes, or config screen changes. Story 10.6 will consume this job API from the UI.

### Technical Requirements

- Add job wrapper under `src/thucthengay/jobs/` and keep core download logic under `src/thucthengay/download/`.
- Existing progress pattern is `JobControl`, `JobCancelled`, `JobState`, `ProgressEvent`, and `QueuedProgressDispatcher` in `src/thucthengay/jobs/`.
- `ProgressEvent` can be extended with optional download-specific counters only if defaults preserve all existing ingestion/render tests.
- `run_satellite_download_job` should accept `SatelliteDownloadRequest`, optional `JobControl`, and optional progress publisher callable.
- Terminal result should reuse `SatelliteDownloadResult` / `DownloadRunStatus` from `src/thucthengay/download/models.py`.
- Cancellation is cooperative: check between raster candidates and output rows; never leave a half-copied file intentionally unhandled.
- The output stage may need optional hooks so it can return partial rows on cancellation and still write a manifest if rows exist.
- User-facing setup/runtime issues must be Vietnamese and include remediation.
- Core and jobs modules must remain headless and must not import `PySide6` or `thucthengay.editor`.

### Previous Story Intelligence

- Story 10.1 added request/result/progress contracts and path validation.
- Story 10.2 added explicit GeoJSON/raster matching and non-fatal failed raster rows.
- Story 10.3 added filename metadata parsing, skipped-cloud rows, and overlap warnings.
- Story 10.4 added output tree writing and CSV manifest rows; its output function currently runs synchronously and may need progress/cancel hooks.
- Full pytest has known pre-existing failures in editor/metadata/isolated Qt tests outside download scope; focused download/job tests and ruff should pass.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.5 and SDT-FR9/FR11/FR12/SDT-AR2/UX-DR14.
- `src/thucthengay/jobs/progress.py`
- `src/thucthengay/jobs/control.py`
- `src/thucthengay/jobs/ingestion_job.py`
- `src/thucthengay/download/matching.py`
- `src/thucthengay/download/filename.py`
- `src/thucthengay/download/output.py`
- `_bmad-output/implementation-artifacts/10-4-write-output-tree-and-manifest-per-download-run.md`

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-06-14: RED `conda run -n ttn-env pytest tests/unit/test_download_job.py -q --basetemp=.pytest_tmp_codex_download_10_5_red` failed as expected because `run_satellite_download_job` was not exported.
- 2026-06-14: GREEN focused `conda run -n ttn-env pytest tests/unit/test_download_job.py -q --basetemp=.pytest_tmp_codex_download_10_5` passed: 4 passed.
- 2026-06-14: Regression scope `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_download_output.py tests/unit/test_download_job.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_5_group` passed: 29 passed.
- 2026-06-14: Scoped ruff `conda run -n ttn-env ruff check src/thucthengay/download src/thucthengay/jobs tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_download_output.py tests/unit/test_download_job.py tests/unit/test_core_import_boundaries.py` passed.
- 2026-06-14: Full suite with UTF-8 output `conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_5_full_utf8` reported 518 passed, 5 failed in pre-existing editor/metadata/isolated Qt tests outside download scope.
- 2026-06-14: First full ruff attempt ran in parallel with smoke and hit the known Windows `conda run` temp activation-file conflict; rerun standalone passed.
- 2026-06-14: `conda run -n ttn-env ruff check .` passed with the existing Windows access warning while scanning temp folders.
- 2026-06-14: Smoke `$env:PYTHONPATH='src'; conda run -n ttn-env python -m thucthengay --smoke` passed: `3.ThucTheNgay app ready.`

### Implementation Plan

- Added a headless satellite download job adapter under `jobs` that orchestrates the Story 10.1-10.4 pipeline.
- Extended existing progress contracts with optional download counters while preserving existing ingestion tests.
- Added cooperative progress/cancel hooks to matching, filename filtering, and output writing.
- Kept UI/thread creation out of scope; Story 10.6 can run this job from a Qt worker and drain events through the existing dispatcher.

### Completion Notes List

- Implemented `run_satellite_download_job()` with setup, scan, filter, output, manifest, complete/cancel/error stages.
- Added progress fields for copied/downloaded, skipped existing, skipped cloud, failed images, metadata cache counters, current source folder, current GeoJSON, match context, and percent.
- Added cooperative cancellation during scan/filter/output. Cancellation during output returns partial output rows and writes a partial manifest when rows exist.
- Preserved non-fatal raster/copy failures in final stats, warning issues, and manifest rows.
- Added tests covering success progress, scan cancellation, output cancellation with partial manifest, and non-fatal raster failure reporting.

### File List

- src/thucthengay/download/filename.py
- src/thucthengay/download/matching.py
- src/thucthengay/download/models.py
- src/thucthengay/download/output.py
- src/thucthengay/jobs/__init__.py
- src/thucthengay/jobs/download_job.py
- src/thucthengay/jobs/progress.py
- tests/unit/test_download_job.py
- _bmad-output/implementation-artifacts/10-5-run-satellite-download-as-a-progress-job.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-14: Created Story 10.5 context from Epic 10 and previous download stories.
- 2026-06-14: Started implementation and moved status to in-progress.
- 2026-06-14: Implemented progress job orchestration, cooperative cancellation, partial manifest handling, focused tests, and moved story to review.
