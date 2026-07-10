# Story 11.3: Introduce Fixed Tile Index and Tile Cache Contracts

Status: review

## Story

As a Developer,
I want a deterministic tile index and byte-budgeted tile cache contract,
So that decoded map-space data can survive pan/zoom changes and be reused across frames.

## Acceptance Criteria

1. Given a viewport, map scale, tile size, and map-space extent, when `TileIndex` resolves visible tiles, then it returns deterministic tile keys independent from the current widget frame and stable across small pan movements.
2. Given two nearby pan positions overlap, when visible tile keys are compared, then shared map-space tiles keep identical keys and only newly exposed tiles are new.
3. Given a tile cache is configured with a byte budget, when tiles are inserted beyond the budget, then least-recently-used entries are evicted deterministically without evicting unrelated current entries prematurely.
4. Given a raster file changes size or mtime, when tile keys are built, then the file signature changes and stale tile entries are not reused.
5. Given tile keys and cache entries are introduced, when the renderer derives the map-space tile coverage, then it uses the existing render spec/map-frame geometry as input and does not redefine frame size, label placement, pane gap, or map-surround layout.

## Tasks / Subtasks

- [x] Add Qt-free tile identity and coverage data structures (AC: 1, 2, 4, 5)
  - [x] Include map-space tile coordinates, LOD/scale bucket, layer id, and raster file signature in tile keys.
  - [x] Return deterministic tile coverage with bounds derived from a fixed map-space grid.
- [x] Add `TileIndex` visible-tile resolver (AC: 1, 2, 5)
  - [x] Resolve keys from viewport, map scale, tile size, and map extent only.
  - [x] Keep behavior independent of widget dimensions and frame drawing/layout internals.
- [x] Add byte-budgeted LRU `TileCache` contract (AC: 3)
  - [x] Store entries by tile key, track bytes, copy numpy arrays on put/get, and evict oldest unused entries deterministically.
- [x] Add focused unit tests (AC: 1, 2, 3, 4, 5)
  - [x] Verify deterministic keys and small-pan overlap.
  - [x] Verify LRU eviction order and current entries are preserved after access.
  - [x] Verify file signature changes produce different tile keys.
- [x] Run focused quality gates
  - [x] `pytest tests/unit/test_render_tile.py`

## Dev Notes

- Epic 11 is a performance/refactor epic only. This story must not alter the map-frame visual/layout contract: frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Tile contracts should be testable without Qt and should not decode raster pixels yet. Decode scheduling belongs to Story 11.4.
- Tile coverage should use current render spec/map-space bounds as input. Do not introduce alternate frame sizing or label placement logic.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.3]
- [Source: _bmad-output/implementation-artifacts/epic-11-context.md#Tile Index and Cache]
- [Source: SOLUTION.md]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile.py` - passed (`6 passed`).
- `$env:PYTHONPATH='src'; conda run -n ttn-env ruff check src/thucthengay/render/tile.py src/thucthengay/render/__init__.py tests/unit/test_render_tile.py` - passed.
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_tile.py tests/unit/test_render_overview_readiness.py tests/unit/test_render_diagnostics.py tests/unit/test_render_core.py tests/unit/test_render_raster.py` - passed (`50 passed`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest` - passed (`577 passed`).

### Completion Notes List

- Added `TileGrid`, `TileIndex`, `TileKey`, and `TileCoverage` contracts for deterministic map-space tile coverage.
- Tile keys include layer id, LOD bucket, x/y tile coordinates, and raster file signature so changed raster size/mtime produces different keys.
- Added `TileCache`, a thread-safe byte-budgeted LRU cache that copies numpy arrays on put/get and evicts deterministically.
- Added render-spec coverage helper using the existing `RenderSpec.geo_window` and visible layers without changing frame geometry, labels, pane gaps, or map-surround layout.

### File List

- `_bmad-output/implementation-artifacts/11-3-introduce-fixed-tile-index-and-tile-cache-contracts.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `src/thucthengay/render/tile.py`
- `src/thucthengay/render/__init__.py`
- `tests/unit/test_render_tile.py`
