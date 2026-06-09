# Story 9.4: Load Historical Imagery into New Workspace Ingestion

Status: review

## Story

As an Operator,
I want new workspaces to include relevant historical imagery for targets in scope,
so that I can compare current and previous satellite scenes in the same review queue.

## Acceptance Criteria

1. Given current-session imagery has been matched to targets, when historical loading runs with `target_scope=targets_with_current_matches`, then history is queried only for targets that have at least one current-session match.
2. Given historical loading runs with `target_scope=all_enabled_targets`, when ingestion creates composition inputs, then history is queried for every enabled target in the loaded config.
3. Given `image_selection.mode=latest_date`, when history is queried for a target, then all available historical images from that target's latest capture date are loaded.
4. Given `image_selection.mode=latest_images`, when `limit_per_target` is set, then only the newest N historical images for each target are loaded.
5. Given `image_selection.mode=date_range`, when `start_date` and `end_date` are set, then only historical images with capture dates inside the inclusive range are loaded.
6. Given `image_selection.mode=lookback_days`, when an anchor is configured as `today` or `current_session_latest_date`, then only historical images inside the computed lookback window are loaded.
7. Given a historical image is also present in current-session matches, when composition inputs are merged, then the image appears only once for the same target/date.

## Tasks / Subtasks

- [x] Add history query API behind `HistoryService` (AC: 1, 2, 3, 4, 5, 6)
  - [x] Add historical image record/result types for query output.
  - [x] Query only target ids present in the resolved `HistoricalLoadingPlan`.
  - [x] Implement `latest_date`, `latest_images`, `date_range`, and `lookback_days` selection.
  - [x] Keep SQLite access parameterized and inside short service calls.
- [x] Merge historical imagery into ingestion cache inputs (AC: 7)
  - [x] Extend cache population with additional pre-matched historical image inputs.
  - [x] Copy historical image files into the current workspace cache before composition creation.
  - [x] Deduplicate by target/date/source path so current-session and historical duplicates produce one layer.
- [x] Wire default ingestion loading path (AC: 1, 2)
  - [x] When historical loading is enabled, default to `HistoryService.load_historical_images()` if no test hook is supplied.
  - [x] Preserve Story 9.3 disabled behavior: no query and no SQLite file creation when disabled.
- [x] Add focused tests and regressions (AC: 1, 2, 3, 4, 5, 6, 7)
  - [x] Test selection modes through `HistoryService`.
  - [x] Test target scope is honored by the ingestion plan/query.
  - [x] Test historical records are copied into cache and produce compositions.
  - [x] Test current-session duplicate source path is not duplicated after merge.

## Dev Notes

### Scope

Story 9.4 loads available historical rows into the new workspace ingestion pipeline. Do not implement path repair UI, detailed historical status in Review/Edit, or temporal compare controls; those are Stories 9.5 through 9.8.

### Architecture Requirements

- SQLite queries stay in `HistoryService`.
- Ingestion owns merging query output into cache/composition inputs.
- Historical image files should be copied into workspace cache before review/render/export.
- Workspace JSON remains source of truth after ingestion creates compositions.
- Missing/unreadable path repair belongs to Story 9.5; this story may surface existing cache-copy warnings without adding repair flows.

### Existing Code Patterns To Preserve

- `populate_workspace_cache()` already deduplicates by `(target_id, date_key, source_path)`.
- `create_target_date_compositions()` consumes `CachePopulationResult.layers_by_target_date`.
- `run_ingestion_job()` now builds `HistoricalLoadingPlan` after target matching.
- Tests should seed SQLite using existing `HistoryService.record_included_composition()` or direct service helpers only through public service behavior.

### References

- `_bmad-output/planning-artifacts/epics.md` - Story 9.4 acceptance criteria.
- `_bmad-output/implementation-artifacts/9-3-configure-historical-loading-mode-for-ingestion.md` - historical loading plan and gate.
- `src/thucthengay/history/service.py` - SQLite service boundary.
- `src/thucthengay/history/loading.py` - ingestion loading plan/result contracts.
- `src/thucthengay/ingestion/cache_builder.py` - workspace cache copy and dedupe.
- `src/thucthengay/jobs/ingestion_job.py` - orchestration.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env python -m pytest tests\unit\test_history_service.py tests\unit\test_ingestion_job.py -q`
- `conda run -n ttn-env python -m ruff check src\thucthengay\history src\thucthengay\ingestion src\thucthengay\jobs\ingestion_job.py tests\unit\test_history_service.py tests\unit\test_ingestion_job.py`
- `conda run -n ttn-env python -m pytest -q`
- `conda run -n ttn-env python -m ruff check .`
- `conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Story context created from Epic 9 requirements and Story 9.3 implementation.
- Added historical image record query output and `HistoryService.load_historical_images()`.
- Implemented per-target `latest_date`, `latest_images`, `date_range`, and `lookback_days` query modes.
- Extended cache population with additional historical image inputs and reused existing target/date/source dedupe.
- Wired ingestion to default to `HistoryService.load_historical_images()` when historical loading is enabled and no test hook is supplied.
- Verified historical-only ingestion creates cached workspace compositions and current/history duplicate source paths produce one layer.

### File List

- `_bmad-output/implementation-artifacts/9-4-load-historical-imagery-into-new-workspace-ingestion.md`
- `src/thucthengay/history/__init__.py`
- `src/thucthengay/history/loading.py`
- `src/thucthengay/history/service.py`
- `src/thucthengay/ingestion/__init__.py`
- `src/thucthengay/ingestion/cache_builder.py`
- `src/thucthengay/jobs/ingestion_job.py`
- `tests/unit/test_history_service.py`
- `tests/unit/test_ingestion_job.py`

## Change Log

- 2026-06-09: Created story context and started implementation.
- 2026-06-09: Implemented historical query and ingestion merge/copy path; status moved to review.
