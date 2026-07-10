# Story 12.4: Compose Review/Edit GIS Canvas from Cached Tiles

Status: review

## Implementation Notes

- Added `render_map_with_raster_base` in render core to compose a pre-rendered raster base through the existing map-surround frame path.
- `render_tile_preview_map` composes cached/decoded tiles into the inner raster and then applies the current frame, labels, ticks, and overlay logic.
- Temporal compare now uses tile composition per pane. Pane geometry, pane gap, outer frame, pane frame, ticks, and labels are still derived from the existing render core helpers.
- Added `temporal_compare_render_plan` in render core so tile compare reuses the same pane split logic as the full renderer.
- Final export path is unchanged.

## Guardrail

The tile path never returns a bare raster to the GIS canvas. It always passes through the existing full map-surround composition helper.
Compare mode composes the full inner compare raster first, then asks the existing frame renderer to draw outline and pane frames.

## Verification

- `pytest tests/unit/test_render_tile_preview.py`
