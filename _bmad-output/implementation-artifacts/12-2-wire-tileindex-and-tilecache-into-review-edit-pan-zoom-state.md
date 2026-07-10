# Story 12.2: Wire TileIndex and TileCache into Review/Edit Pan/Zoom State

Status: review

## Implementation Notes

- Added Review/Edit-owned `TileCache` and `TileScheduler` state.
- Recreates tile state when workspace/config reloads, preserving stale-source safety.
- Added `render_tile_preview_map` to derive tile coverage from the frame-safe inner `RenderSpec`.
- Tile keys still include the source file signature through Epic 11 `TileIndex`, so changed raster files invalidate cached tiles.

## Guardrail

Tile coverage is derived after the existing map-surround layout resolves the inner map, so no new frame dimensions or aspect rules are introduced.

## Verification

- `pytest tests/unit/test_render_tile_preview.py`
