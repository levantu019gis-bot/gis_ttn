# Epic 11 Context: Render Pipeline Performance Refactor

<!-- Created from SOLUTION.md and current render architecture analysis. Edit freely as implementation discoveries change. -->

## Goal

Epic 11 improves Review/Edit GIS canvas responsiveness for large satellite imagery by moving from whole-frame preview rerendering toward measured, tile-based, reusable render work.

Epic 11 is strictly a performance/refactor epic. It must not change the map-frame visual/layout contract.

The guiding principle is:

```text
separate decoded spatial raster data from the current frame/viewport
```

Pan/zoom should reuse data that has already been decoded for the same map-space tile, and should decode only newly exposed or newly required tiles.

## Source Roadmap

Primary roadmap:

- `SOLUTION.md`

The roadmap phases are mapped into stories:

- Phase 0 diagnostics -> Story 11.1
- Phase 1 COG/overview readiness -> Story 11.2
- Phase 2 TileIndex/TileCache/Scheduler -> Stories 11.3 and 11.4
- Phase 3 partial repaint -> Story 11.5
- Phase 4 GPU reassessment -> Story 11.6
- Phase 5 progressive LOD -> Story 11.6

## Existing Render Baseline

The codebase already has useful foundations:

- `src/thucthengay/render/raster.py` reads raster windows with `rasterio`, `out_shape`, and `WarpedVRT` when CRS differs.
- `src/thucthengay/render/core.py` has `RasterBaseCache`, `FrameOverlayCache`, `FullMapCache`, and `MapRenderCache`.
- `src/thucthengay/editor/modes/review_edit_mode.py` renders GIS canvas previews through background `QThread` workers.
- `src/thucthengay/editor/widgets/gis_canvas.py` rejects stale async render results with `RenderRequestToken`.
- `src/thucthengay/jobs/render_job.py` already has preview quality concepts: `INTERACTIVE_LOW_RES` and `SETTLED_HIGH_RES`.

These foundations should be reused. Epic 11 should not duplicate raster business logic inside PySide widgets.

## Why Existing Cache Is Not Enough

Current preview cache keys are frame/spec oriented. That helps when the exact render spec repeats, but small pan/zoom changes can still force expensive recomputation because the decoded output is tied to the whole viewport/frame.

Epic 11 moves reuse down to stable map-space tiles:

```text
file signature + lod/overview level + tile coordinate + relevant style params
```

The tile key should survive small pan movements, so the canvas can reuse most previously decoded tiles.

## Technical Direction

### Diagnostics First

Before changing render architecture, add measurement for:

- raster window read time
- resampling/scaling time
- QImage conversion time
- QPixmap conversion time
- paint/composite time
- cache hit/miss counts
- number of `rasterio.read()` calls during pan/zoom
- overview availability per raster

The baseline determines whether COG/overview work or tile cache work has the highest immediate ROI.

### COG / Overview Readiness

Do not assume overviews are missing. Current `rasterio.read(..., out_shape=...)` may already benefit from GDAL overviews when they exist.

Story 11.2 should:

- detect overview levels and raster layout
- warn when large rasters lack overview pyramids
- cache overview metadata by path/size/mtime
- provide tooling guidance for COG or external overviews
- avoid mutating original source imagery without explicit action

### Tile Index and Cache

`TileIndex` should be deterministic and testable without Qt. It maps viewport/scale to tile keys in a fixed map-space grid.

`TileCache` should be byte-budgeted and LRU-based, similar in spirit to existing render caches, but keyed by tile rather than full frame.

Initial implementation can keep tile pixels as `numpy.ndarray` or `QImage`; choose the representation that keeps core render testability and UI conversion costs measurable.

### Tile Scheduler and Decode Queue

Missing visible tiles should decode asynchronously. Scheduling should prioritize center tiles first and reject obsolete results when a newer viewport request supersedes them.

Use existing stale-result and cancellation ideas from:

- `RenderRequestToken`
- `PreviewRenderRequest`
- background `RenderWorker`

Do not block the UI thread on raster decode.

### Compositor and Partial Repaint

After tile decode is stable, compose the GIS canvas from cached tiles. Small pans should move existing cached imagery immediately and decode only newly exposed bands where possible.

Partial repaint should come after tile cache stability, not before.

### Progressive LOD and GPU Decision

Progressive LOD is a UX refinement: show lower-resolution cached tiles first, then replace with correct-resolution tiles.

GPU/OpenGL is not part of the default Epic 11 implementation path. It should be considered only after Story 11.6 diagnostics show that raster decode/resampling is no longer the bottleneck and composition/upload cost dominates.

## Cross-Story Dependencies

Story 11.1 produces the baseline and instrumentation used to judge all later changes.

Story 11.2 can proceed independently after 11.1 and informs tile LOD selection.

Story 11.3 defines tile contracts and should stay mostly pure/core with deterministic tests.

Story 11.4 depends on Story 11.3 and adds async scheduling/decode behavior.

Story 11.5 depends on Stories 11.3 and 11.4 and changes GIS canvas composition behavior.

Story 11.6 depends on stable tile rendering and uses diagnostics to decide whether a later GPU-specific epic is justified.

## Guardrails

- Mandatory: preserve the current map frame exactly. No Epic 11 change may alter frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Performance optimizations may change when/how raster pixels are decoded and displayed, but not the frame, label, gap, or layout contract that determines the map output appearance.
- Keep final export output stable unless a story explicitly changes and verifies the final render contract.
- Keep render core testable without PySide widgets.
- Use generated raster fixtures in tests.
- Do not depend on production LAN paths or real imagery.
- Preserve existing compare-mode render behavior while improving preview performance.
- Keep user-facing diagnostics/status Vietnamese where surfaced in the app.
