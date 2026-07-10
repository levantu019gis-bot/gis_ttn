# Story 11.5: Compose GIS Canvas from Cached Tiles and Support Partial Repaint

Status: review

## Story

As an Operator,
I want the GIS canvas to reuse already-decoded tiles while panning,
So that the map follows interaction quickly instead of waiting for a full viewport rerender.

## Acceptance Criteria

1. Given visible tiles are already cached, when the Operator pans a small distance, then the canvas repositions cached tiles immediately and queues only newly exposed tiles.
2. Given a previous composed frame exists, when pan delta is below the configured threshold, then partial repaint reuses the previous frame buffer and repaints only exposed bands where practical.
3. Given zoom changes or pan delta is too large, when the canvas updates, then the compositor falls back to a full recomposite without corrupting tile cache state.
4. Given cached tiles or partial repaint are used, when the map is displayed in normal or temporal-compare mode, then the compositor preserves the existing frame shape, dimensions, labels, ticks, pane gaps, pane boundaries, and spacing exactly.
5. Given final export runs, when preview tile rendering has been used in Review/Edit, then final render output remains governed by the existing final render contract unless this story explicitly verifies a shared tile path.

## Tasks / Subtasks

- [x] Add Qt-free tile compositor contracts (AC: 1, 3, 4, 5)
  - [x] Compose cached tile pixels into a requested canvas without touching frame/layout code.
  - [x] Report missing tile coverage so scheduler can queue only newly exposed tiles.
- [x] Add partial repaint support (AC: 2, 3)
  - [x] Reuse and shift a previous frame buffer when dimensions, scale, and pan delta are compatible.
  - [x] Fall back to full recomposite for zoom changes or large pan deltas.
- [x] Add focused tests (AC: 1, 2, 3, 4, 5)
  - [x] Verify cached tile repositioning and newly missing tiles.
  - [x] Verify partial repaint path and full fallback path.
  - [x] Verify normal and compare-like coverage composition preserves requested canvas dimensions.
  - [x] Verify final render APIs are not wired to tile preview compositor.
- [x] Run focused quality gates
  - [x] `pytest tests/unit/test_render_tile_compositor.py`

## Dev Notes

- Epic 11 is a performance/refactor epic only. This story must not alter the map-frame visual/layout contract: frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Keep compositor headless and frame-agnostic. It composes raster imagery into an already-defined canvas size and viewport.
- Final export remains on the existing final render path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.5]
- [Source: _bmad-output/implementation-artifacts/epic-11-context.md#Compositor and Partial Repaint]
- [Source: SOLUTION.md]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile_compositor.py` - passed (`4 passed`).
- `$env:PYTHONPATH='src'; conda run -n ttn-env ruff check src/thucthengay/render/tile_compositor.py src/thucthengay/render/__init__.py tests/unit/test_render_tile_compositor.py` - passed.
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile.py tests/unit/test_render_tile_scheduler.py tests/unit/test_render_tile_compositor.py tests/unit/test_render_tile_progressive.py tests/unit/test_render_overview_readiness.py tests/unit/test_render_diagnostics.py tests/unit/test_render_core.py tests/unit/test_render_raster.py` - passed (`65 passed`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest` - passed (`592 passed`).

### Completion Notes List

- Added frame-agnostic cached tile compositor that draws cached tiles into an already requested canvas size and reports missing coverage.
- Added partial repaint support that shifts a compatible previous frame buffer for small pan deltas and falls back to full recomposite for zoom/large pan/dimension changes.
- Added compare-like composition coverage tests to verify requested canvas dimensions remain unchanged.
- Kept final export untouched; tile composition remains a preview-side headless contract.

### File List

- `_bmad-output/implementation-artifacts/11-5-compose-gis-canvas-from-cached-tiles-and-support-partial-repaint.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `src/thucthengay/render/tile_compositor.py`
- `src/thucthengay/render/__init__.py`
- `tests/unit/test_render_tile_compositor.py`
