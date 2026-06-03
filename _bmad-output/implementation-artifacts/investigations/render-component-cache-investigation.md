# Investigation: Render Component Cache

## Hand-off Brief

1. **What happened.** Confirmed: GIS canvas preview currently renders the complete map-surround output on every render request.
2. **Where the case stands.** Updated 2026-06-03: Phase 1 raster base cache, Phase 2 frame/label overlay cache, and Phase 3 full-map preview cache have been implemented for GIS Canvas Preview; final export remains uncached.
3. **What's needed next.** Measure real-world preview latency and memory use on large workspaces before changing cache budgets.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-03 |
| Status | Concluded - Phase 1/2/3 Implemented |
| System | Local repo, conda env `ttn-env` |
| Evidence sources | `render/core.py`, `render/raster.py`, `render/frame.py`, `render/spec.py`, `jobs/render_job.py`, `review_edit_mode.py` |

## Problem Statement

Xác định các thành phần thay đổi trong quá trình rendering và đề xuất cơ chế cache các thành phần không đổi để tăng hiệu suất, đặc biệt khi người dùng chỉnh Grid Interval/Scale trong GIS Canvas Preview.

## Confirmed Findings

### Finding 1: GIS canvas renders full map-surround output per request

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:668`, `src/thucthengay/jobs/render_job.py:149`, `src/thucthengay/render/core.py:188`

**Detail:** `_request_canvas_render()` builds a full `RenderSpec` and `RenderWorker` runs `render_map()` by default.

### Finding 2: `render_map()` always recomputes layout, raster base, canvas composition, and frame overlay

**Evidence:** `src/thucthengay/render/core.py:199`, `src/thucthengay/render/core.py:217`, `src/thucthengay/render/core.py:235`, `src/thucthengay/render/core.py:247`

**Detail:** Each call builds `MapSurroundLayout`, calls `render_raster_layers_to_size()`, allocates a full canvas, pastes raster, then calls `draw_map_surround_frame()`.

### Finding 3: Raster rendering is keyed by geo window, output size, background, and visible layers

**Evidence:** `src/thucthengay/render/raster.py:353`, `src/thucthengay/render/raster.py:386`, `src/thucthengay/render/raster.py:404`, `src/thucthengay/render/raster.py:418`

**Detail:** Raster composite allocates a canvas, opens each visible raster, reads only the overlapping window, and composites layers by order.

### Finding 4: Frame overlay is keyed by grid, geo window, layout, and style

**Evidence:** `src/thucthengay/render/frame.py:616`, `src/thucthengay/render/frame.py:620`, `src/thucthengay/render/frame.py:669`, `src/thucthengay/render/frame.py:735`

**Detail:** Frame drawing derives interval/label format/style, layout, tick positions from `geo_window`, then draws outer/inner frame, ticks, and labels.

### Finding 5: RenderSpec selects grid from composition override before target default

**Evidence:** `src/thucthengay/render/spec.py:281`

**Detail:** Grid-only edits should be able to reuse a raster base if view, visible layers, template output/layout, and background stay unchanged.

## Component Dependency Matrix

| Component | Current work | Changes when | Cache candidate |
| --- | --- | --- | --- |
| Template/final output size | Reads template metadata, computes output size in UI/export layer | template PPTX/metadata/DPI changes | Yes, tiny metadata cache |
| Map-surround layout | `build_map_surround_layout(output_width, output_height, grid.style)` | output size or frame style geometry keys change | Yes, cheap but useful as shared key |
| Inner render spec / fitted geo window | `_spec_for_inner_map()` fits `geo_window` to inner aspect | center, scale, template map frame, output size/layout changes | Yes, as derived metadata |
| Raster base | `render_raster_layers_to_size()` opens rasters and reads windows | visible layers/order/path/mtime, center, scale, template frame/aspect, output size, background changes | Highest-value cache |
| Full white/background canvas | allocates full RGB canvas and pastes inner raster | output size, background, inner rect, raster base changes | Yes, cheap memory cache or reconstruct from raster |
| Outer/inner frame strokes | drawn by PIL in `draw_map_surround_frame()` | output size, layout style colors/stroke widths, frame geometry changes | Yes, overlay alpha cache |
| Tick positions | `_tick_values()` and lon/lat-to-pixel mapping | geo window, grid interval, layout changes | Yes, small computed geometry cache |
| Labels | DMS formatting, font sizing, text halo/rotation | geo window, interval, label format, font/style, layout bands change | Yes, overlay cache |
| Final composite | full RGB output | any dependency changes | Maybe; preview memory-limited only |

## Recommended Cache Design

### Phase 1: Preview-scoped raster base cache

Status: Implemented in `src/thucthengay/render/core.py` via `RasterBaseCache` and `render_map_with_cache()`, and wired into GIS Canvas Preview from `ReviewEditMode`.

Create a cache object owned by Review/Edit preview rendering, not persisted to workspace.

Key: composition id, output size, inner map rect, fitted geo window, background color, visible layer refs `(layer_id, order, resolved path, file size, mtime_ns)`.

Value: inner raster RGB array, issues, painted layer ids.

Behavior: when only `grid.interval`, `grid.label_format`, or label/style keys change, reuse cached raster and redraw frame only.

Implementation note: the current key uses composition id, target id, inner raster size, fitted geo window, background color, visible layer refs, and path signatures `(size, mtime_ns)` when files exist. Cache values copy arrays on read/write to avoid mutation leaks across render calls.

### Phase 2: Frame/label overlay cache

Status: Implemented in `src/thucthengay/render/core.py` via `FrameOverlayCache` inside `MapRenderCache`.

Add a render-core helper that draws frame/tick/label onto a transparent RGBA overlay or a copied full canvas. Prefer an RGBA overlay only if tests prove pixel parity with current RGB compositing.

Key: output size, layout, fitted geo window, full `grid` object/style keys affecting frame, label font availability/version.

Value: overlay image/array plus frame issues.

This helps repeated renders with identical grid after raster changes, but the main win remains Phase 1.

Implementation note: the current implementation builds an RGB overlay by drawing frame/tick/label over a deterministic white/background base, then stores the changed-pixel mask plus pixels. Applying the overlay replaces only changed frame pixels on the raster composite.

### Phase 3: Full preview result cache

Status: Implemented in `src/thucthengay/render/core.py` via `FullMapCache` inside `MapRenderCache`.

Small LRU keyed by preview `RenderSpec` minus volatile job id/revision. Useful when selecting back and forth between compositions, but memory must be capped.

Suggested cap: 2-3 full previews plus 2-3 raster bases, or a byte budget such as 256-512 MB.

Implementation note: the key uses the JSON render spec plus visible-layer path signatures, so file changes invalidate cached full canvases.

## Invalidation Rules

- Grid-only change: invalidate frame overlay/full composite; keep raster base if view/output/layers/background unchanged.
- Grid style geometry change (`reference_*`, stroke widths, frame gap): invalidate layout, raster base, frame overlay.
- Frame color/label color/label format/interval/font change: invalidate frame overlay only.
- Pan/zoom/scale/center change: invalidate raster base and frame overlay.
- Visible layer toggle/reorder/path/mtime/size change: invalidate raster base and full composite.
- Template map frame/output size change: invalidate layout, raster base, frame overlay.
- Background color change: invalidate raster base if raster canvas includes background fill; otherwise only full composite if background is separated.

## Risks

- Cache must not change map-frame geometry. `layout_size` and final output dimensions must remain source of truth.
- Cache arrays are large; use explicit byte budget and copy-on-read or immutable ownership to avoid mutation leaks.
- Worker-thread cache access needs locking or single-owner design. Safer first implementation: create cache lookup on main thread and pass cached raster snapshot to worker/render function.
- Final export should initially bypass preview cache unless the final spec hash matches exactly and output artifact currentness remains authoritative.

## Suggested Tests

- Grid interval change rerenders frame without calling raster reader when raster cache key is unchanged.
- Pan/zoom invalidates raster cache and rereads raster.
- Layer visibility/order/path mtime change invalidates raster cache.
- Cached and uncached render outputs are pixel-identical for the same spec.
- Cache byte cap evicts older entries deterministically.

## Conclusion

**Confidence:** High

The safest high-impact optimization is a preview-scoped raster base cache inside the GIS canvas render path. It directly addresses the current slow case: changing grid interval/labels currently rereads and recomposites raster even though the raster pixels are unchanged.

## Follow-up: 2026-06-03

### Implemented

- Added `RasterBaseCache` LRU with byte budget and locking in `render/core.py`.
- Added `FrameOverlayCache`, `FullMapCache`, and `MapRenderCache` to bundle preview caches.
- Added `render_map_with_cache()` while leaving `render_map()` unchanged for final export/default callers.
- Wired `ReviewEditMode` GIS canvas workers to use `render_map_with_cache()` with a preview-owned cache.
- Clear preview render cache when loading a workspace.

### Verification

- Added tests proving grid-only changes reuse raster base and geo-window changes invalidate it.
- Added tests proving layer-only changes reuse frame overlay, identical specs reuse full-map cache, and cached pixels match uncached pixels.
- Targeted verification passed:
  - `pytest tests/unit/test_render_core.py tests/unit/test_review_edit_mode.py tests/unit/test_export_final_render.py tests/unit/test_core_import_boundaries.py -q`
  - `ruff check src/thucthengay/render/core.py src/thucthengay/render/__init__.py src/thucthengay/editor/modes/review_edit_mode.py tests/unit/test_render_core.py`
  - `ruff check .`
  - `python -m thucthengay --smoke`
- Full `pytest -q` still native-aborts in the PySide/Qt test region after about 50 tests; this matches the pre-existing suite behavior seen before the cache phases and does not produce a Python assertion tied to render cache code.
