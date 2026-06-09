# Story 9.5: Validate and Repair Historical Image Paths

Status: review

## Story

As an Operator,
I want missing historical paths to be detected and repairable,
so that moved LAN/local imagery can be reused without corrupting the current workspace.

## Acceptance Criteria

1. Given a historical image path no longer exists, when historical loading validates registry entries, then the app creates a structured warning issue with target, image, path, Vietnamese message, and remediation, and the missing image is not copied into workspace cache until repaired.
2. Given a historical image path exists but cannot be opened as a usable GeoTIFF, when validation runs, then the app creates a structured warning or error issue based on whether review/export can safely continue.
3. Given the Operator repairs one missing image path, when the selected replacement file is accepted, then the app revalidates the file, updates the registry path in a transaction, and refreshes the affected workspace issue.
4. Given many historical paths share an old prefix, when the Operator applies a bulk path-prefix replacement, then the app previews affected rows and requires explicit confirmation before updating the registry.

## Tasks / Subtasks

- [x] Validate selected historical records before cache copy (AC: 1, 2)
  - [x] Add structured issue creation for missing source paths.
  - [x] Add usable GeoTIFF validation for existing paths.
  - [x] Ensure invalid historical images are skipped before workspace cache copy.
  - [x] Preserve current-session ingestion behavior when historical loading is disabled.
- [x] Add registry repair APIs behind `HistoryService` (AC: 3, 4)
  - [x] Add single image path repair by registry image id with validation before transaction update.
  - [x] Add bulk old-prefix/new-prefix preview.
  - [x] Require explicit confirmation before bulk prefix update.
  - [x] Keep all SQLite writes parameterized and transactional.
- [x] Wire validation results into ingestion job output (AC: 1, 2)
  - [x] Include historical path issues in `IngestionJobResult.issues`.
  - [x] Count skipped historical images in loading result.
  - [x] Keep valid historical records flowing into `populate_workspace_cache()`.
- [x] Add focused tests and regressions (AC: 1, 2, 3, 4)
  - [x] Test missing path warning and skip.
  - [x] Test unreadable GeoTIFF warning and skip.
  - [x] Test single path repair validates and updates registry transactionally.
  - [x] Test bulk prefix preview and confirmation gate.

## Dev Notes

### Scope

Story 9.5 owns core validation and repair mechanics for historical registry paths. Do not implement the full Review/Edit status presentation; Story 9.6 surfaces historical status in summary, layer stack, and warnings UI.

### Architecture Requirements

- SQLite query/update logic stays inside `HistoryService`.
- Path validation may live in `history` because it validates registry records, but must not import `editor` or PySide.
- Ingestion must not copy invalid historical records into the workspace cache.
- User-facing issues must use shared `Issue` with Vietnamese message/remediation.
- Bulk path updates must have an explicit confirmation parameter.
- Current-session imagery scanning and matching must remain unchanged.

### Previous Story Intelligence

- Story 9.4 added `HistoricalImageRecord`, `HistoricalLoadingResult`, and `HistoryService.load_historical_images()`.
- Story 9.4 wires `run_ingestion_job()` to convert valid historical records to `CacheImageInput`.
- `populate_workspace_cache()` already returns `cache.copy_failed` warnings; Story 9.5 should catch historical missing/unreadable paths earlier so they are not copied.
- `HistoryService.record_included_composition()` seeds registry rows and should remain the preferred test setup path.

### References

- `_bmad-output/planning-artifacts/epics.md` - Story 9.5 acceptance criteria.
- `_bmad-output/implementation-artifacts/9-4-load-historical-imagery-into-new-workspace-ingestion.md` - historical loading/copy path.
- `src/thucthengay/history/service.py` - SQLite service boundary.
- `src/thucthengay/history/loading.py` - historical loading record/result contracts.
- `src/thucthengay/jobs/ingestion_job.py` - ingestion orchestration and issue propagation.
- `src/thucthengay/ingestion/scanner.py` - existing GeoTIFF usability validation pattern.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env python -m pytest tests\unit\test_history_service.py -q`
- `conda run -n ttn-env python -m pytest tests\unit\test_history_service.py tests\unit\test_ingestion_job.py -q`
- `conda run -n ttn-env python -m ruff check src\thucthengay\history src\thucthengay\jobs\ingestion_job.py tests\unit\test_history_service.py tests\unit\test_ingestion_job.py`
- `conda run -n ttn-env python -m pytest -q`
- `conda run -n ttn-env python -m ruff check .`
- `conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Story context created from Epic 9 requirements and Story 9.4 implementation.
- Added `image_asset_id` to historical records so individual registry images can be repaired safely.
- Added historical path validation during `HistoryService.load_historical_images()`.
- Missing/unreadable/unusable historical GeoTIFFs now produce structured Vietnamese `Issue`s and are skipped before cache copy.
- Added single image path repair with validation before transactional SQLite update.
- Added bulk prefix replacement preview and confirmation-gated transactional update.
- Verified ingestion propagates historical path issues and does not create compositions from invalid historical records.

### File List

- `_bmad-output/implementation-artifacts/9-5-validate-and-repair-historical-image-paths.md`
- `src/thucthengay/history/__init__.py`
- `src/thucthengay/history/loading.py`
- `src/thucthengay/history/service.py`
- `tests/unit/test_history_service.py`
- `tests/unit/test_ingestion_job.py`

## Change Log

- 2026-06-09: Created story context for implementation.
- 2026-06-09: Implemented historical path validation and registry repair APIs; status moved to review.
