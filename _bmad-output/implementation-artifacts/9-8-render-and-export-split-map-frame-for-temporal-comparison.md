# Story 9.8: Render and Export Split Map Frame for Temporal Comparison

Status: review

## Story

As an Operator,
I want the final map output to show two selected time points in one split map frame,
so that the exported report can compare target imagery across time without manual PowerPoint editing.

## Acceptance Criteria

1. Given comparison mode is disabled, when preview or final render runs, then the renderer uses the existing single-map `RenderSpec` behavior.
2. Given comparison mode is enabled with valid Pane A and Pane B selections, when preview render runs, then the GIS canvas shows the map frame split according to the selected orientation, and each pane renders only the selected image/layer set for its configured time point.
3. Given comparison mode is enabled, when final render/export runs, then the exported map image uses the same comparison state as Review/Edit preview, and PPTX export inserts the split comparison render into the existing map placeholder.
4. Given comparison mode is enabled, when grid/frame rendering is applied, then each pane has clear map-frame boundaries and coordinate context.

## Tasks / Subtasks

- [x] Extend render spec for temporal comparison (AC: 1, 2, 3)
  - [x] Add comparison pane refs to `RenderSpec` with default disabled behavior.
  - [x] Validate selected Pane A/B layer IDs during `build_render_spec()`.
  - [x] Preserve `visible_layers` behavior when comparison mode is off.
- [x] Render split map panes in shared render core (AC: 2, 4)
  - [x] Split the inner map rect vertically or horizontally.
  - [x] Render Pane A only with Pane A selected layer and Pane B only with Pane B selected layer.
  - [x] Draw a clear pane divider without relying on color-only status.
  - [x] Keep existing map surround/grid frame behavior when comparison is disabled.
- [x] Ensure final render/export uses comparison state (AC: 3)
  - [x] Confirm final render spec hash includes comparison state.
  - [x] Confirm final render/export path uses the same `build_render_spec()` output.
  - [x] Keep PPTX placeholder insertion unchanged because the split render is still one map image.
- [x] Add focused tests and regressions (AC: 1, 2, 3, 4)
  - [x] Test disabled comparison produces legacy spec behavior.
  - [x] Test enabled comparison spec contains Pane A/B refs.
  - [x] Test vertical/horizontal split renders only selected pane layers.
  - [x] Test final render hash changes when comparison state changes.

## Dev Notes

### Scope

Story 9.8 consumes the temporal comparison state created in Story 9.7. Keep changes inside render/export boundaries; do not change Review/Edit controls beyond what is needed to consume the persisted state.

### Architecture Requirements

- `build_render_spec()` remains the single bridge from workspace state to preview/final render.
- Renderer must keep comparison disabled behavior byte/contract compatible where possible.
- Export/PPTX should continue to insert one final map image into the existing map placeholder.
- Do not create separate PPTX placeholders or manual PowerPoint edits.
- Memory checks and cancellation behavior in render core must remain intact.

### Previous Story Intelligence

- Story 9.7 added `Composition.temporal_compare` with `enabled`, `orientation`, and Pane A/B layer IDs.
- `render_map_with_cache()` is used by Review/Edit preview.
- `render_final_png()` and export preparation consume the same `RenderSpec`, so a spec-level comparison state covers final/export.
- `FinalRenderLog` hashes the full spec JSON, so comparison state in `RenderSpec` naturally invalidates stale final renders.

### References

- `_bmad-output/planning-artifacts/epics.md` - Story 9.8 acceptance criteria.
- `src/thucthengay/render/spec.py` - `RenderSpec` and `build_render_spec()`.
- `src/thucthengay/render/core.py` - map surround render pipeline.
- `src/thucthengay/render/final.py` - final render hash/log.
- `src/thucthengay/export/final_render.py` - export final render spec path.
- `tests/unit/test_render_spec.py`, `tests/unit/test_render_core.py`, `tests/unit/test_final_render.py`.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env python -m pytest tests\unit\test_render_spec.py tests\unit\test_render_core.py tests\unit\test_final_render.py -q`
- `conda run -n ttn-env python -m ruff check src\thucthengay\render tests\unit\test_render_spec.py tests\unit\test_render_core.py tests\unit\test_final_render.py`
- `conda run -n ttn-env python -m pytest -q`
- `conda run -n ttn-env python -m ruff check .`
- `conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Story context created from Epic 9 requirements and Story 9.7 implementation.
- Added `RenderComparisonSpec`/`RenderComparisonPane` with default disabled behavior.
- `build_render_spec()` now validates and carries Pane A/B layer refs when temporal comparison is enabled.
- Render core now splits the inner map vertically or horizontally and renders each pane with only its selected layer.
- Added a clear pane divider while preserving existing map surround/grid frame behavior.
- Final render hash includes comparison state, so export final renders are invalidated when pane/orientation changes.
- PPTX export remains unchanged because the split comparison output is still one final map image.
- After review, comparison panes are split directly from the original inner map. Each pane remains a raster canvas sized from that split, with a config-driven gap between panes that defaults to 8px; pane-specific DMS ticks/labels are drawn as an overlay on the original map surround, and internal ticks use the same length as the pane gap.
- Compare mode no longer draws a shared inner-map outline or divider through the pane gap, so the two panes remain visually separated instead of connected along pane edges.
- Pane raster backgrounds continue to use each target's `map_background_color`; the gap between panes now uses `defaults.grid.style.temporal_compare_gap_color`, defaulting to white.
- Internal pane ticks extend outward into the pane gap, including the top/bottom shared edges used by horizontal comparison.

### File List

- `_bmad-output/implementation-artifacts/9-8-render-and-export-split-map-frame-for-temporal-comparison.md`
- `src/thucthengay/render/spec.py`
- `src/thucthengay/render/core.py`
- `src/thucthengay/render/__init__.py`
- `tests/unit/test_render_spec.py`
- `tests/unit/test_render_core.py`
- `tests/unit/test_final_render.py`

## Change Log

- 2026-06-09: Created story context for implementation.
- 2026-06-09: Implemented split comparison render spec/core path; status moved to review.
- 2026-06-10: Aligned temporal compare pane coordinate labels/ticks with the standard map-surround design without nesting a second map frame inside each pane.
- 2026-06-10: Changed temporal compare pane gap to config-driven `defaults.grid.style.temporal_compare_pane_gap_px`, defaulting to 8px when absent.
- 2026-06-10: Removed shared inner outline/divider in temporal compare mode so pane edges do not connect across the gap.
- 2026-06-10: Added configurable temporal compare gap color and kept pane backgrounds tied to target `map_background_color`.
- 2026-06-10: Corrected horizontal comparison internal tick direction so ticks point outward into the gap.
