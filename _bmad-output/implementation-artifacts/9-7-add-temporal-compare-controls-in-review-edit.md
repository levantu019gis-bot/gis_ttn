# Story 9.7: Add Temporal Compare Controls in Review/Edit

Status: review

## Story

As an Operator,
I want to enable a two-time comparison for the selected target,
so that I can choose which current or historical image appears in each map pane.

## Acceptance Criteria

1. Given a composition is selected in Review/Edit, when comparison mode is off, then the GIS canvas, layer stack, grid controls, Include/Validate behavior, and export preview remain the current single-map workflow.
2. Given comparison mode is enabled, when the comparison control panel is shown, then it exposes only these primary controls: enable/disable comparison, split orientation, Pane A image/time, and Pane B image/time.
3. Given comparison mode is enabled, when the Operator selects split orientation, then `vertical` shows left/right panes and `horizontal` shows top/bottom panes.
4. Given current and historical imagery are available for the selected target, when the Operator opens the Pane A or Pane B selector, then options are grouped or labelled by capture date/time, and each option shows current/historical source, cloud percent where available, and missing/unreadable status where relevant.
5. Given fewer than two usable images are available for the selected target, when comparison mode is enabled, then the UI explains that two usable time points are required, and this does not block normal single-map review when comparison mode is disabled.
6. Given the Operator changes comparison pane selection or orientation, when the change is saved, then the comparison state is persisted in workspace/composition state through `WorkspaceService`, and the composition is marked for revalidation when the change affects render/export output.

## Tasks / Subtasks

- [x] Add persisted temporal comparison state (AC: 1, 3, 6)
  - [x] Add backward-compatible comparison state models/enums to composition schema.
  - [x] Add `WorkspaceService` update API that validates pane layer IDs.
  - [x] Mark composition stale when enabled/orientation/pane selections change.
- [x] Add Review/Edit comparison controls (AC: 2, 3, 4, 5)
  - [x] Add enable checkbox/toggle, orientation selector, Pane A selector, Pane B selector.
  - [x] Populate pane options from current composition layers with date/time/source/cloud labels.
  - [x] Show two-time-points-required message when fewer than two usable layers exist.
  - [x] Keep controls non-invasive when comparison is off.
- [x] Add focused tests and regressions (AC: 1, 2, 3, 4, 5, 6)
  - [x] Test composition comparison defaults and JSON round-trip.
  - [x] Test workspace update persists comparison state and marks stale.
  - [x] Test Review/Edit controls show options and persist changes.
  - [x] Test fewer-than-two-images message while single-map workflow remains usable.

## Dev Notes

### Scope

Story 9.7 persists and edits comparison state only. Do not render the split map frame or change PPTX/export output; Story 9.8 consumes this state for preview/final render/export.

### Architecture Requirements

- Persist comparison state in `Composition` because workspace JSON is source of truth.
- Review/Edit must use `WorkspaceService` for writes; no direct JSON mutation.
- Default comparison off must preserve all current single-map behavior.
- Use layer IDs for pane selections so render/export can resolve selected layers later.
- Changing comparison state affects render/export output and must mark composition stale.

### Previous Story Intelligence

- Story 9.6 added `ImageLayer.source_kind` so selectors can label current vs historical.
- `LayerStackModel` already exposes current/historical text for layers.
- `ReviewEditMode._update_detail_panels()` is the central place to refresh selected composition UI.
- `WorkspaceService` already has edit APIs that mark compositions stale after render-affecting changes.

### References

- `_bmad-output/planning-artifacts/epics.md` - Story 9.7 acceptance criteria.
- `src/thucthengay/models/composition.py` - persisted composition state.
- `src/thucthengay/workspace/service.py` - workspace write boundary.
- `src/thucthengay/editor/modes/review_edit_mode.py` - Review/Edit controls.
- `tests/unit/test_models.py` - schema round-trip tests.
- `tests/unit/test_review_edit_mode.py` - Review/Edit workflow tests.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env python -m pytest tests\unit\test_models.py tests\unit\test_review_edit_mode.py -q`
- `conda run -n ttn-env python -m ruff check src\thucthengay\models\composition.py src\thucthengay\models\__init__.py src\thucthengay\workspace\service.py src\thucthengay\editor\modes\review_edit_mode.py tests\unit\test_models.py tests\unit\test_review_edit_mode.py`
- `conda run -n ttn-env python -m pytest -q`
- `conda run -n ttn-env python -m ruff check .`
- `conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Story context created from Epic 9 requirements and Story 9.6 implementation.
- Added backward-compatible `TemporalCompareState` and `TemporalCompareOrientation`.
- Added `WorkspaceService.update_temporal_compare_state()` with pane layer validation and stale marking.
- Added Review/Edit compare controls for enable, split orientation, Pane A, and Pane B.
- Pane selectors now label options with capture date/time, current/historical source, and cloud percent.
- Fewer-than-two-layer case reports a two-time-points-required message without blocking single-map workflow.

### File List

- `_bmad-output/implementation-artifacts/9-7-add-temporal-compare-controls-in-review-edit.md`
- `src/thucthengay/models/composition.py`
- `src/thucthengay/models/__init__.py`
- `src/thucthengay/workspace/service.py`
- `src/thucthengay/editor/modes/review_edit_mode.py`
- `tests/unit/test_models.py`
- `tests/unit/test_review_edit_mode.py`

## Change Log

- 2026-06-09: Created story context for implementation.
- 2026-06-09: Implemented temporal compare state and Review/Edit controls; status moved to review.
