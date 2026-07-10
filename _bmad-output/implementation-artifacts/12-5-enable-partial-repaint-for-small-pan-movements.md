# Story 12.5: Enable Partial Repaint for Small Pan Movements

Status: review

## Implementation Notes

- Review/Edit stores the previous tile-composed inner frame.
- `render_tile_preview_map` passes the previous frame into Epic 11 `compose_cached_tiles`.
- Small pan reuse is reported through diagnostics counters.
- Zoom, composition reload, config reload, and fallback reset the previous tile frame.
- Tile preview state now stores separate previous frames for normal mode and compare panes A/B.

## Guardrail

Partial repaint is restricted to the inner raster composition. The surrounding map frame is still produced by the existing render core.
Compare partial repaint is pane-scoped and never changes pane split/gap geometry.

## Verification

- `pytest tests/unit/test_render_tile_preview.py`
