# Story 11.4: Decode Tiles with Scheduler and Cooperative Cancellation

Status: review

## Story

As a Developer,
I want missing visible tiles decoded asynchronously with cancellation and prioritization,
So that pan/zoom remains responsive while expensive raster work happens off the UI thread.

## Acceptance Criteria

1. Given a viewport requests tiles and some are missing from cache, when the tile scheduler runs, then missing tiles are queued by priority, with tiles nearer the viewport center scheduled before edge tiles.
2. Given the viewport changes before queued tile work completes, when obsolete tile jobs finish, then their results are rejected and do not overwrite the current view.
3. Given a tile decode job reads raster data, when an appropriate overview/LOD level is available, then the job reads the smallest practical raster window/decimation for that tile instead of full-frame raster data.
4. Given cancellation is requested, when the decode worker reaches cancellation checkpoints, then it exits cleanly and leaves cache/state consistent.

## Tasks / Subtasks

- [x] Add Qt-free tile scheduler request/result contracts (AC: 1, 2, 4)
  - [x] Prioritize missing tiles by distance to viewport center.
  - [x] Include request revision/generation so stale results can be rejected.
- [x] Add tile decode worker contract (AC: 3, 4)
  - [x] Decode raster tiles using geographic windows and target tile out-shape.
  - [x] Use cancellation checkpoints before and after expensive raster reads.
- [x] Add scheduler result application against `TileCache` (AC: 2, 4)
  - [x] Cache only results matching the current request generation.
  - [x] Keep cache consistent when cancelled or stale jobs complete.
- [x] Add focused unit tests (AC: 1, 2, 3, 4)
  - [x] Verify center-first ordering.
  - [x] Verify stale result rejection.
  - [x] Verify cancellation exits without caching partial tiles.
  - [x] Verify raster reads use windows/out-shape rather than full-frame.
- [x] Run focused quality gates
  - [x] `pytest tests/unit/test_render_tile_scheduler.py`

## Dev Notes

- Epic 11 is a performance/refactor epic only. This story must not alter the map-frame visual/layout contract: frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Keep the initial scheduler headless and Qt-free. UI wiring and partial repaint belong to Story 11.5.
- Decode should use generated raster fixtures in tests and must not depend on production imagery.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.4]
- [Source: _bmad-output/implementation-artifacts/epic-11-context.md#Tile Scheduler and Decode Queue]
- [Source: SOLUTION.md]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile_scheduler.py` - passed (`6 passed`).
- `$env:PYTHONPATH='src'; conda run -n ttn-env ruff check src/thucthengay/render/tile_scheduler.py src/thucthengay/render/__init__.py tests/unit/test_render_tile_scheduler.py` - passed.
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile.py tests/unit/test_render_tile_scheduler.py tests/unit/test_render_tile_compositor.py tests/unit/test_render_tile_progressive.py tests/unit/test_render_overview_readiness.py tests/unit/test_render_diagnostics.py tests/unit/test_render_core.py tests/unit/test_render_raster.py` - passed (`65 passed`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest` - passed (`592 passed`).

### Completion Notes List

- Added headless `TileScheduler` with request revision tracking, stale-result filtering, and center-first missing-tile prioritization.
- Added `TileDecodeJob`/`TileDecodeResult` contracts and `decode_tile_job()` with cancellation checkpoints.
- Tile decode reads raster data with tile geographic bounds, a rasterio window, and target tile `out_shape` rather than full-frame reads.
- Successful current results are applied to `TileCache`; stale, cancelled, skipped, or errored results leave cache state unchanged.
- Kept scheduler/decode code outside UI/frame layout code, preserving the existing map-frame contract.

### File List

- `_bmad-output/implementation-artifacts/11-4-decode-tiles-with-scheduler-and-cooperative-cancellation.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `src/thucthengay/render/tile_scheduler.py`
- `src/thucthengay/render/__init__.py`
- `tests/unit/test_render_tile_scheduler.py`
