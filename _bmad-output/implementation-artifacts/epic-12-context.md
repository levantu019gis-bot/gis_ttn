# Epic 12 Context: Wire Tile Preview Pipeline into Review/Edit UI

Epic 12 activates the Epic 11 tile-rendering foundation inside the Review/Edit preview experience. The objective is to make pan/zoom visibly faster by reusing decoded map-space tiles instead of triggering whole-frame preview renders for every viewport movement.

This epic follows `SOLUTION.md` directly:

- Giai đoạn 2: Tile Index, Tile Cache, Tile Scheduler, Decode Queue, Compositor
- Giai đoạn 3: Partial Repaint for small pans
- Giai đoạn 4: Measure again before any GPU decision
- Giai đoạn 5: Progressive LOD only after the tile path is stable

## Current Foundation from Epic 11

The following headless/core pieces already exist and should be reused rather than reimplemented:

- `thucthengay.render.diagnostics.RenderDiagnostics`
- `thucthengay.render.overview` readiness/preparation helpers
- `thucthengay.render.tile.TileIndex`
- `thucthengay.render.tile.TileCache`
- `thucthengay.render.tile_scheduler.TileScheduler`
- `thucthengay.render.tile_scheduler.decode_tile_job`
- `thucthengay.render.tile_compositor.compose_cached_tiles`
- `thucthengay.render.tile_progressive.compose_progressive_tiles`
- `thucthengay.render.tile_progressive.assess_gpu_path`

## Required Direction

Epic 12 must wire these foundations into Review/Edit UI behavior:

1. Add an explicit tile-preview feature flag and fallback to the current full-frame preview renderer.
2. On pan/zoom, derive visible tile coverage from the current `RenderSpec.geo_window` and map scale.
3. Reuse cached tile imagery immediately when keys are present.
4. Queue only missing tiles for off-UI-thread decode.
5. Reject stale tile results when a newer viewport or composition request supersedes them.
6. Compose cached tiles into the GIS canvas without redefining frame or pane geometry.
7. Add partial repaint only after cached-tile composition is stable.
8. Measure before/after with diagnostics.
9. Evaluate progressive LOD and GPU only after tile preview is stable.

## Mandatory Guardrails

- Preserve the current map-frame visual/layout contract exactly.
- Do not change frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Do not change final export rendering. Final PNG/PPTX output remains governed by the existing final render path.
- Keep a safe fallback to the current preview renderer.
- Keep user-facing status text Vietnamese where surfaced in the UI.
- Do not depend on production LAN paths or real imagery in tests.
- Use generated raster fixtures and headless tests for tile behavior.

## Story Sequencing

Story 12.1 should be implemented first. It establishes feature flag, fallback, and safe UI boundaries.

Story 12.2 wires tile coverage/cache state into pan/zoom without decoding workers yet.

Story 12.3 adds off-UI-thread tile decode and stale-result rejection.

Story 12.4 replaces preview raster composition with cached tile composition when the flag is enabled.

Story 12.5 adds partial repaint for small pans after the tile compositor is stable.

Story 12.6 runs diagnostics, evaluates progressive LOD, and records GPU/QPainter decision evidence.

## Non-Goals

- No GPU/OpenGL implementation in Epic 12 unless a separate later epic/story is created from diagnostics evidence.
- No final export path replacement.
- No redesign of the GIS canvas frame, coordinate labels, grid labels, pane gap, or map-surround layout.
- No broad UI redesign or new landing/marketing screens.
