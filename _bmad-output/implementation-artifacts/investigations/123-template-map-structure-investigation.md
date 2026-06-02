# Investigation: 123 Template Map Structure

## Hand-off Brief

1. **What happened.** User wants GIS Editor and exported map image to match `examples/templates/123.jpg`; the sample image is a full map-surround image, not only a raw raster canvas.
2. **Where the case stands.** Confirmed measurements show an outer coordinate frame and an inset raster/map panel inside a white surround; current render code draws raster and coordinate labels on the same full canvas.
3. **What's needed next.** Implement a layout-aware map surround renderer that composites raster into the inner panel, then draws the outer/inner frames and DMS labels around it.

## Case Info

| Field            | Value |
| ---------------- | ----- |
| Ticket           | N/A |
| Date opened      | 2026-06-02 |
| Status           | Active |
| System           | 3.ThucTheNgay, PySide6 desktop app, render core Qt-free |
| Evidence sources | `examples/templates/123.jpg`, `examples/templates/target_001.template.json`, `src/thucthengay/render/core.py`, `src/thucthengay/render/frame.py`, `src/thucthengay/render/raster.py`, `src/thucthengay/editor/widgets/gis_canvas.py` |

## Problem Statement

The requested output should have the same visual structure as `examples/templates/123.jpg`: a white page/map surround, outer coordinate frame, DMS labels on all edges, and satellite imagery placed inside the inner map panel.

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| `examples/templates/123.jpg` | Available | Image size is `3306x2340`; measured outer frame approx `x=244..3271`, `y=165..2306`; measured inner panel approx `x=292..3223`, `y=213..2258`. |
| `examples/templates/target_001.template.json` | Available | PPTX map placeholder uses image `3306x2340`; map frame aspect is approximately `1.4128`. |
| `src/thucthengay/render/core.py` | Available | `render_map()` renders raster first, then calls `draw_coordinate_frame(result.canvas, spec)`. |
| `src/thucthengay/render/frame.py` | Available | `draw_coordinate_frame()` draws frame/ticks/labels directly on the full canvas edge. |
| `src/thucthengay/render/raster.py` | Available | `render_raster_layers_result()` creates a canvas of `spec.output_width x spec.output_height` and paints raster into that same canvas based on `spec.geo_window`. |
| `src/thucthengay/editor/widgets/gis_canvas.py` | Available | GIS Canvas currently draws a centered frame and scales the rendered pixmap into it, without the white surround layout from `123.jpg`. |

## Confirmed Findings

### Finding 1: The sample is a full map-surround image

**Evidence:** Pixel measurement of `examples/templates/123.jpg`.

**Detail:** The image has a white background, an outer black frame, DMS labels around the edges, and an inner dark map panel. The inner panel is not the full image.

### Finding 2: Current render places labels/frame on the raster canvas

**Evidence:** `src/thucthengay/render/core.py`, `src/thucthengay/render/frame.py`, `src/thucthengay/render/raster.py`.

**Detail:** `render_map()` passes the same raster canvas to `draw_coordinate_frame()`, so the frame and labels are drawn over the rendered canvas rather than around an inset map panel.

## Deduced Conclusions

### Deduction 1: The current renderer cannot exactly match `123.jpg` by aspect changes alone

**Based on:** Finding 1 and Finding 2.

**Reasoning:** Matching aspect only fixes the outer canvas ratio. The sample requires separate coordinate-surround margins and an inner raster viewport.

**Conclusion:** The correct fix is layout-aware compositing, not another resize/scale adjustment.

## Recommended Next Steps

### Fix direction

Add a map-surround layout to render core:

- Render raster into an inner panel size derived from the sample/template ratios.
- Composite the raster panel onto a white full-canvas page.
- Draw outer frame, inner frame, ticks, and DMS labels in the surround.
- Update GIS Canvas to preview the same structure, so editor preview and exported image use the same spatial contract.

### Diagnostic

Create focused tests that assert:

- Outer canvas keeps `3306/2340`-like aspect when using template metadata.
- Raster content is inside the inner panel, not painted under the label margins.
- DMS labels remain outside the raster panel.

## Conclusion

**Confidence:** High

The requested structure is a layout change: `123.jpg` is the complete map image placeholder, while current renderer treats the placeholder as a single raster canvas with frame labels overlaid on its edges.
