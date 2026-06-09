# Story 9.2: Record Included Compositions into History

Status: review

## Story

As an Operator,
I want included compositions to be saved into historical registry,
so that images I approved can appear in future workspaces.

## Acceptance Criteria

1. Given a composition passes validation and Include/Validate succeeds, when the include transition is persisted, then the app records target id/name/alias, composition id, capture date/time, cloud percent, source path, cache path, and workspace path for each included layer.
2. Given a composition is skipped or validation fails, when review actions complete, then no included-history event is recorded for that composition.
3. Given the same target/image is included again later, when the registry write runs, then the existing target-image link is updated with latest inclusion metadata, and a separate include event is appended for traceability.
4. Given history recording fails after workspace include succeeds, when the app reports the action result, then the composition remains included in the workspace, and the Operator sees a non-blocking warning explaining that history was not updated.

## Tasks / Subtasks

- [x] Add history recording API in `HistoryService` (AC: 1, 3)
  - [x] Add domain result/error types for included-composition recording.
  - [x] Upsert target identity and image asset records in one transaction.
  - [x] Upsert target-image link with latest workspace/composition/included metadata.
  - [x] Append include events for traceability.
- [x] Preserve disabled/default behavior (AC: 2)
  - [x] Disabled `HistoryService` remains no-op and creates no database.
  - [x] Skip and failed validation flows do not call history recording.
- [x] Hook Review/Edit Include/Validate through service boundary (AC: 1, 2, 4)
  - [x] Inject optional `HistoryService` into `ReviewEditMode`, default disabled.
  - [x] Call history recording only after `WorkspaceService.apply_include_transition()` succeeds.
  - [x] If history recording fails, do not rollback workspace include; show non-blocking Vietnamese warning.
- [x] Add focused tests and regressions (AC: 1, 2, 3, 4)
  - [x] Test registry rows and include events after a successful record call.
  - [x] Test repeated include updates the link and appends a new event.
  - [x] Test Review/Edit does not record on validation failure or skip.
  - [x] Test Review/Edit keeps workspace include when history recording fails.

## Dev Notes

### Scope

Story 9.2 only records approved/current workspace imagery into the registry. Do not query registry during ingestion, do not add historical loading UI, and do not create comparison controls.

### Architecture Requirements

- `HistoryService` remains the only SQLite boundary.
- `ReviewEditMode` may call `HistoryService` but must not import or use `sqlite3`.
- Workspace include state is authoritative. History recording is a best-effort side effect after include succeeds.
- History recording failure must be non-blocking: no rollback of `reviewed=true`, `ready=true`, `include=true`, or `review_order`.
- Disabled service must be a no-op so existing Review/Edit behavior remains unchanged.

### Recording Rules

- Record visible layers from the included composition. Hidden layers are not part of the approved map output and should not seed future history as approved imagery.
- Use `layer.capture_date` when available; otherwise use `composition.capture_date`.
- Use `layer.capture_time` when available; otherwise store null.
- Store paths as strings exactly as supplied by composition/workspace state. Path repair and path validation belong to later stories.
- Use UTC ISO text for `included_at`/`created_at`/`updated_at`.

### Existing Code Patterns To Preserve

- Include flow is currently in `ReviewEditMode._include_selected()` and persists state through `WorkspaceService.apply_include_transition()`.
- Validation failure currently saves validation summary, refreshes issues, and does not call include transition.
- Skip uses `WorkspaceService.apply_skip_transition()` and must not write history.
- Core tests should not require a Qt event loop unless testing `ReviewEditMode`.

### References

- `_bmad-output/planning-artifacts/epics.md` - Story 9.2 and HIR-FR1/HIR-FR8.
- `_bmad-output/implementation-artifacts/9-1-add-sqlite-history-service-and-registry-schema.md` - service/schema foundation.
- `_bmad-output/implementation-artifacts/epic-9-context.md` - Review include flow and failure handling.
- `src/thucthengay/editor/modes/review_edit_mode.py` - Include/Validate UI flow.
- `src/thucthengay/workspace/service.py` - include/skip transitions and workspace source of truth.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `C:\Users\Admin\.conda\envs\ttn-env\python.exe -m pytest tests\unit\test_history_service.py tests\unit\test_review_edit_mode.py -q`
- `C:\Users\Admin\.conda\envs\ttn-env\python.exe -m ruff check src\thucthengay\history src\thucthengay\editor\modes\review_edit_mode.py tests\unit\test_history_service.py tests\unit\test_review_edit_mode.py`
- `C:\Users\Admin\.conda\envs\ttn-env\python.exe -m ruff check .`
- `C:\Users\Admin\.conda\envs\ttn-env\python.exe -m thucthengay --smoke`
- `conda run -n ttn-env python -m pytest -q`

### Completion Notes List

- Added `HistoryService.record_included_composition()` with enabled/no-op behavior and `HistoryRecordResult`/`HistoryRecordError`.
- Recorded visible included layers by upserting target history, image assets, target-image links, and appending include events in one transaction.
- Updated Review/Edit to accept optional `HistoryService`, default disabled, and call it only after workspace include succeeds.
- Kept history failures non-blocking: workspace include remains persisted and the action summary reports that history was not updated.
- Added tests for successful history rows/events, repeated include traceability, disabled no-op, validation-fail/skip no-record behavior, and UI failure handling.

### File List

- `src/thucthengay/editor/modes/review_edit_mode.py`
- `src/thucthengay/history/__init__.py`
- `src/thucthengay/history/service.py`
- `tests/unit/test_history_service.py`
- `tests/unit/test_review_edit_mode.py`

## Change Log

- 2026-06-09: Created story context and started implementation.
- 2026-06-09: Implemented included-composition history recording; status moved to review.
