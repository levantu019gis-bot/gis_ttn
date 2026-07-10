# Story 11.6: Add Progressive LOD and Reassess GPU Path

Status: review

## Story

As an Operator,
I want fast pan/zoom to show useful lower-resolution imagery first and refine automatically,
So that Review/Edit remains usable even when high-resolution tiles are still decoding.

## Acceptance Criteria

1. Given high-resolution visible tiles are missing but lower-resolution cached tiles cover the same area, when the canvas repaints during fast pan/zoom, then it displays the lower-resolution tiles as temporary imagery and replaces them when correct-resolution tiles arrive.
2. Given progressive LOD is active, when lower-quality imagery is shown, then the UI exposes a clear render-quality/loading status without blocking review actions or relying on color alone.
3. Given progressive LOD or a future GPU path is evaluated, when imagery is temporarily lower quality or rendered through another compositor, then only raster imagery quality/timing may vary; map-frame geometry, labels, gaps, pane boundaries, and surrounding layout remain unchanged.
4. Given tile cache, scheduler, compositor, and partial repaint are stable, when diagnostics are rerun, then the team can compare baseline versus optimized metrics for CPU, read count, cache hit rate, and perceived latency.
5. Given diagnostics show the remaining bottleneck is not raster decode/resampling, when GPU/OpenGL is considered, then the decision record states whether to keep QPainter/QImage or create a later GPU-specific epic/story, with evidence from the measured metrics.

## Tasks / Subtasks

- [x] Add progressive LOD tile selection contracts (AC: 1, 2, 3)
  - [x] Prefer exact LOD tiles and fall back to lower LOD tiles covering the same map-space tile.
  - [x] Keep missing exact tiles queued for refinement.
  - [x] Return clear quality/loading status text without blocking review actions.
- [x] Add progressive composition helper (AC: 1, 3)
  - [x] Compose exact/fallback cached tiles into the requested canvas dimensions.
  - [x] Preserve frame/layout invariance by staying frame-agnostic.
- [x] Add GPU/QPainter decision record helper from diagnostics (AC: 4, 5)
  - [x] Compare timing buckets, read counts, cache activity, and latency signals.
  - [x] Recommend keeping QPainter by default unless diagnostics justify a later GPU-specific epic.
- [x] Add focused unit tests (AC: 1, 2, 3, 4, 5)
  - [x] Verify fallback lower LOD display and exact replacement behavior.
  - [x] Verify status message and non-blocking review flag.
  - [x] Verify GPU decision evidence from diagnostic summaries.
- [x] Run focused quality gates
  - [x] `pytest tests/unit/test_render_tile_progressive.py`

## Dev Notes

- Epic 11 is a performance/refactor epic only. This story must not alter the map-frame visual/layout contract: frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- GPU/OpenGL is not part of the default implementation path. This story may only create an evidence-based decision record for a later GPU-specific epic/story.
- Keep progressive LOD headless and testable. UI wiring can surface the returned status string later.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.6]
- [Source: _bmad-output/implementation-artifacts/epic-11-context.md#Progressive LOD and GPU Decision]
- [Source: SOLUTION.md]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile_progressive.py` - passed (`5 passed`).
- `$env:PYTHONPATH='src'; conda run -n ttn-env ruff check src/thucthengay/render/tile_progressive.py src/thucthengay/render/__init__.py tests/unit/test_render_tile_progressive.py` - passed.
- `$env:PYTHONPATH='src'; conda run -n ttn-env ruff check src/thucthengay/render/tile.py src/thucthengay/render/tile_scheduler.py src/thucthengay/render/tile_compositor.py src/thucthengay/render/tile_progressive.py src/thucthengay/render/__init__.py tests/unit/test_render_tile.py tests/unit/test_render_tile_scheduler.py tests/unit/test_render_tile_compositor.py tests/unit/test_render_tile_progressive.py` - passed.
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile.py tests/unit/test_render_tile_scheduler.py tests/unit/test_render_tile_compositor.py tests/unit/test_render_tile_progressive.py tests/unit/test_render_overview_readiness.py tests/unit/test_render_diagnostics.py tests/unit/test_render_core.py tests/unit/test_render_raster.py` - passed (`65 passed`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest` - passed (`592 passed`).

### Completion Notes List

- Added progressive LOD selection that prefers exact cached tiles and uses lower-LOD cached tiles as temporary imagery when exact tiles are missing.
- Progressive plans keep missing exact tiles in the refinement queue and expose clear non-blocking status messages.
- Added progressive composition helper that composes exact/fallback tiles into the requested canvas without touching frame/layout code.
- Added GPU/QPainter decision record helper based on render diagnostics; GPU remains a future epic/story decision, not a default code path.

### File List

- `_bmad-output/implementation-artifacts/11-6-add-progressive-lod-and-reassess-gpu-path.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `src/thucthengay/render/tile_progressive.py`
- `src/thucthengay/render/__init__.py`
- `tests/unit/test_render_tile_progressive.py`
