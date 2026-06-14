# Story 10.6: Add Satellite Download Tab UI

Status: review

## Story

As an Operator,
I want a dedicated tab for satellite image download next to Config,
so that I can configure and run downloads without editing JSON or running a batch script.

## Acceptance Criteria

1. Given the app shell renders top-level tabs, when the satellite download feature is available, then a new tab is shown at the outer edge adjacent to `Config` and the tab label clearly identifies the download function.
2. Given the Operator opens the download tab, when the form is rendered, then it provides explicit controls to add/remove/clear multiple GeoJSON files and it does not show a GeoJSON folder picker for the primary workflow.
3. Given the Operator configures source imagery, when source inputs are rendered, then the UI allows adding/removing/clearing multiple image folders and each row shows a validation indicator, middle-elided path, and full-path tooltip.
4. Given the Operator configures output, when output input is rendered, then the UI provides one output folder picker and the form explains through labels/status that copied images will be grouped by GeoJSON name then source folder name.
5. Given required inputs are missing or invalid, when the Operator views the primary action, then the Download action is disabled or blocked with a visible Vietnamese reason and status does not rely on color alone.

## Tasks / Subtasks

- [x] Add a reusable multi-path list control for download inputs (AC: 2, 3, 5)
  - [x] Support file mode for explicit `.geojson`/`.json` files without adding a GeoJSON folder picker.
  - [x] Support folder mode for multiple source imagery folders.
  - [x] Render each row with middle-elided path text, full tooltip, and text validation state.
  - [x] Provide add/remove/clear controls and keep validation recomputed after each change.
- [x] Add Satellite Download mode UI (AC: 2, 3, 4, 5)
  - [x] Create `DownloadMode` under `src/thucthengay/editor/modes/`.
  - [x] Provide sections for GeoJSON files, source image folders, output folder, and core options already supported by `SatelliteDownloadRequest`.
  - [x] Build a `SatelliteDownloadRequest` only when all required inputs are valid.
  - [x] Disable or block the Download action with a visible Vietnamese reason when input is incomplete or invalid.
- [x] Add the new top-level tab to the app shell (AC: 1)
  - [x] Instantiate `DownloadMode` in `AppShell`.
  - [x] Add it adjacent to `Config` at the outer edge, preserving the existing Setup/Review/Edit/Export flow.
  - [x] Do not mutate workspace, config, history SQLite, or ingestion state from this tab.
- [x] Add focused UI tests (AC: 1, 2, 3, 4, 5)
  - [x] Test shell tab order/labels include the new download tab next to `Config`.
  - [x] Test missing inputs disable Download and show a Vietnamese blocker reason.
  - [x] Test multiple GeoJSON files and multiple image folders produce a valid request.
  - [x] Test invalid file/folder rows remain visible with text status and tooltips.

## Dev Notes

### Scope

Story 10.6 is a UI composition story. It adds the tab, path-list controls, validation, and request construction. It must not run the long download job, show completion summaries, mutate workspace folders, update historical SQLite, or copy files. Story 10.7 wires run results, summary, and app-boundary messaging.

### Technical Requirements

- UI code belongs under `src/thucthengay/editor/`; business rules remain in `src/thucthengay/download/` and `src/thucthengay/jobs/`.
- Reuse `SatelliteDownloadRequest`, `DownloadImageFolder`, and `DownloadFilenameFormatRule` from `src/thucthengay/download/models.py`; do not duplicate dataclasses in the UI.
- Existing reusable path UI is `PathPickerRow` / `ElidedPathField` in `src/thucthengay/editor/widgets/path_picker.py`. Extend or create a sibling widget instead of copying the elision/validation behavior.
- The output folder is a single folder path and should be writable/creatable enough for `SatelliteDownloadRequest` validation. The tab should call request construction for final validation and surface `SatelliteDownloadConfigError` as Vietnamese visible status.
- Required inputs for enabling the primary action: at least one valid GeoJSON file, at least one valid source imagery folder, one valid output folder.
- Primary GeoJSON workflow must be explicit files only; no folder picker labelled or behaving as "GeoJSON folder".
- Each path row must show a text state such as `Hop le`, `Loi`, or `Chua chon`; color can be additional only.
- Use object names on important widgets so tests can find them, following existing patterns (`setupIngestButton`, `modeTabs`, etc.).
- The tab must not import or call `WorkspaceService`, `HistoryService`, ingestion, render, or export services.

### Previous Story Intelligence

- Story 10.1 created typed request/result models and request validation.
- Story 10.2 requires explicit GeoJSON file selection and recursive source folder matching.
- Story 10.3 added optional filename format/cloud filtering. This UI can expose basic fields if lightweight, but must not block core path workflow on filename-rule editing.
- Story 10.4 fixed output structure as `<output>/<geojson_name>/<source_folder_name>/...`; the UI must state this behavior in Vietnamese.
- Story 10.5 added `run_satellite_download_job`, progress events, and cancellation, but this story only needs to emit/build requests for later wiring.
- Full pytest currently has known pre-existing failures in editor metadata/date-change and isolated Qt import tests outside download scope; focused new tests and scoped regression should pass.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.6 and SDT-FR1/FR2/FR3/FR4/FR8/SDT-UX1/UX2/UX3.
- `src/thucthengay/editor/app_shell.py`
- `src/thucthengay/editor/modes/setup_mode.py`
- `src/thucthengay/editor/widgets/path_picker.py`
- `src/thucthengay/download/models.py`
- `src/thucthengay/download/service.py`
- `_bmad-output/implementation-artifacts/10-5-run-satellite-download-as-a-progress-job.md`

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-06-14: RED `conda run -n ttn-env pytest tests/unit/test_download_mode.py -q --basetemp=.pytest_tmp_codex_download_10_6_red` failed as expected because `thucthengay.editor.modes.download_mode` did not exist.
- 2026-06-14: Focused `conda run -n ttn-env pytest tests/unit/test_download_mode.py tests/unit/test_review_edit_mode.py::test_review_edit_layout_and_app_shell_expose_review_mode -q --basetemp=.pytest_tmp_codex_download_10_6_focus` passed: 5 passed.
- 2026-06-14: Scoped ruff `conda run -n ttn-env ruff check src/thucthengay/editor/app_shell.py src/thucthengay/editor/modes/download_mode.py src/thucthengay/editor/widgets/multi_path_list.py src/thucthengay/editor/widgets/path_picker.py tests/unit/test_download_mode.py tests/unit/test_review_edit_mode.py` passed.
- 2026-06-14: Regression group `conda run -n ttn-env pytest tests/unit/test_setup_mode.py tests/unit/test_download_mode.py tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_download_output.py tests/unit/test_download_job.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_6_group` passed: 51 passed.
- 2026-06-14: Full pytest first rerun found one new stale tab-count assertion in `tests/unit/test_export_mode.py`; updated it and focused rerun passed.
- 2026-06-14: Full suite `$env:PYTHONIOENCODING='utf-8'; $env:CONDA_REPORT_ERRORS='false'; conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_6_full_utf8_rerun` reported 522 passed, 5 failed in pre-existing editor metadata/date-change and isolated Qt import tests outside Story 10.6 scope.
- 2026-06-14: `conda run -n ttn-env ruff check .` passed with the existing Windows access warning while scanning temp folders.
- 2026-06-14: Smoke `$env:PYTHONPATH='src'; conda run -n ttn-env python -m thucthengay --smoke` passed: `3.ThucTheNgay app ready.`
- 2026-06-14: Final cleanup checks passed: `conda run -n ttn-env ruff check src/thucthengay/editor/modes/download_mode.py` and `conda run -n ttn-env pytest tests/unit/test_download_mode.py -q --basetemp=.pytest_tmp_codex_download_10_6_final_focus`.

### Implementation Plan

- Added a reusable multi-path list widget that reuses existing elided path display and path validation patterns.
- Added `DownloadMode` with explicit GeoJSON file list, source folder list, output folder, core request options, blockers, and request construction.
- Added the top-level `Download` tab to `AppShell` directly before `Config`.
- Added UI tests for tab order, blockers, valid request construction, and invalid row visibility.

### Completion Notes List

- Implemented explicit multi-file GeoJSON selection; no GeoJSON folder picker is exposed in the primary workflow.
- Implemented multiple source folder rows with validation text, middle-elided display, and full-path tooltip.
- Implemented output folder picker plus visible output structure hint: `output/ten_geojson/ten_folder_anh/...`.
- Implemented `DownloadMode.selected_request()` that returns a validated `SatelliteDownloadRequest` and never mutates workspace/config/history state.
- Updated stale shell tab tests for the new 5-tab layout.

### File List

- src/thucthengay/editor/app_shell.py
- src/thucthengay/editor/modes/download_mode.py
- src/thucthengay/editor/widgets/multi_path_list.py
- src/thucthengay/editor/widgets/path_picker.py
- tests/unit/test_download_mode.py
- tests/unit/test_export_mode.py
- tests/unit/test_review_edit_mode.py
- _bmad-output/implementation-artifacts/10-6-add-satellite-download-tab-ui.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-14: Created Story 10.6 context from Epic 10 and previous download stories.
- 2026-06-14: Implemented Download tab UI, multi-path controls, request validation, tests, and moved story to review.
