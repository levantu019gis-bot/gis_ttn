# Story 9.6: Surface Historical Imagery Status in Review/Edit and Ingest Summary

Status: review

## Story

As an Operator,
I want historical imagery to be visibly distinguishable from current-session imagery,
so that I understand which layers are new, historical, missing, or repaired while reviewing.

## Acceptance Criteria

1. Given ingestion completes with historical loading enabled, when the summary is shown, then it displays current images scanned, current images matched, historical images loaded, historical images skipped, and historical path issues.
2. Given a composition contains historical layers, when the layer stack is rendered, then each layer shows a text/icon source indicator such as current or historical, and status does not rely on color alone.
3. Given historical path issues exist, when the Warnings panel is rendered, then issue rows identify the affected target/composition/layer and offer navigation or repair where available.
4. Given historical settings produce no matching historical imagery, when ingestion completes, then the app reports that no historical images matched the configured target scope and image selection, and this is informational rather than blocking.

## Tasks / Subtasks

- [x] Persist source kind on image layers (AC: 2)
  - [x] Add backward-compatible layer source enum/default.
  - [x] Mark historical layers created from registry as historical.
  - [x] Keep current-session layers defaulting to current.
- [x] Extend ingestion job and summary contracts (AC: 1, 4)
  - [x] Add historical loaded/skipped/path issue counters to job result.
  - [x] Add historical counters and informational empty state to summary model.
  - [x] Render historical counters in ingestion summary widget.
- [x] Surface source and historical issues in Review/Edit widgets (AC: 2, 3)
  - [x] Show current/historical source text in layer stack rows.
  - [x] Include source kind in tooltip/role for tests and delegates.
  - [x] Make historical path issue rows mention repair availability while preserving navigation data.
- [x] Add focused tests and regressions (AC: 1, 2, 3, 4)
  - [x] Test summary historical counters and no-historical informational message.
  - [x] Test summary widget renders historical counters.
  - [x] Test layer stack shows current/historical source text.
  - [x] Test warnings panel identifies historical path issues and repair availability.

## Dev Notes

### Scope

Story 9.6 surfaces historical status already produced by Stories 9.4 and 9.5. Do not implement temporal compare selectors or split-map rendering; those belong to Stories 9.7 and 9.8.

### Architecture Requirements

- Workspace JSON remains source of truth for review state.
- `ImageLayer` can gain a backward-compatible default field because layers are persisted workspace data.
- UI widgets consume models/results; they must not query SQLite or read config JSON directly.
- Historical path issue detection stays in `HistoryService`; widgets only present structured `Issue`s.
- Do not use color-only status indicators.

### Previous Story Intelligence

- Story 9.4 loads historical registry records into workspace cache and creates layers.
- Story 9.5 validates historical paths before cache copy and returns structured issues plus loaded/skipped counters.
- `IngestionSummary.from_job_result()` is the handoff point from job layer to setup summary UI.
- `LayerStackModel` already centralizes layer row display text and tooltip.
- `WarningsPanelWidget` already preserves target/composition/layer navigation data.

### References

- `_bmad-output/planning-artifacts/epics.md` - Story 9.6 acceptance criteria.
- `_bmad-output/implementation-artifacts/9-5-validate-and-repair-historical-image-paths.md` - historical path validation result contract.
- `src/thucthengay/models/layer.py` - persisted image layer schema.
- `src/thucthengay/jobs/ingestion_job.py` - historical load counters.
- `src/thucthengay/jobs/ingestion_summary.py` - post-ingest summary model.
- `src/thucthengay/editor/widgets/ingestion_summary.py` - summary widget.
- `src/thucthengay/editor/models/layer_stack_model.py` - Review/Edit layer stack display.
- `src/thucthengay/editor/widgets/warnings_panel.py` - issue rows and navigation.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env python -m pytest tests\unit\test_models.py tests\unit\test_ingestion_summary.py tests\unit\test_warnings_panel_and_issue_ui.py tests\unit\test_ingestion_job.py -q`
- `conda run -n ttn-env python -m ruff check src\thucthengay\models src\thucthengay\jobs src\thucthengay\editor\models\layer_stack_model.py src\thucthengay\editor\widgets\ingestion_summary.py src\thucthengay\editor\widgets\warnings_panel.py tests\unit\test_models.py tests\unit\test_ingestion_summary.py tests\unit\test_warnings_panel_and_issue_ui.py tests\unit\test_ingestion_job.py`
- `conda run -n ttn-env python -m pytest -q`
- `conda run -n ttn-env python -m ruff check .`
- `conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Story context created from Epic 9 requirements and Story 9.5 implementation.
- Added backward-compatible `ImageLayerSourceKind` with default `current`.
- Marked layers loaded from historical registry as `historical`.
- Added historical loaded/skipped/path issue counters to ingestion job and summary models.
- Added informational summary message when historical loading is enabled but no historical rows match.
- Rendered historical counters in ingestion summary widget.
- Displayed Current/Historical source text and tooltip data in layer stack.
- Added repair availability hint for historical path issues in warnings panel while preserving jump data.

### File List

- `_bmad-output/implementation-artifacts/9-6-surface-historical-imagery-status-in-review-edit-and-ingest-summary.md`
- `src/thucthengay/models/layer.py`
- `src/thucthengay/models/__init__.py`
- `src/thucthengay/jobs/ingestion_job.py`
- `src/thucthengay/jobs/ingestion_summary.py`
- `src/thucthengay/editor/widgets/ingestion_summary.py`
- `src/thucthengay/editor/models/layer_stack_model.py`
- `src/thucthengay/editor/widgets/warnings_panel.py`
- `tests/unit/test_models.py`
- `tests/unit/test_ingestion_summary.py`
- `tests/unit/test_warnings_panel_and_issue_ui.py`
- `tests/unit/test_ingestion_job.py`

## Change Log

- 2026-06-09: Created story context for implementation.
- 2026-06-09: Implemented historical imagery status surfacing; status moved to review.
