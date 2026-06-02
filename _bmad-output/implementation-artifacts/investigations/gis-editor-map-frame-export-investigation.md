# Investigation: GIS Editor Map Frame Export

## Hand-off Brief

1. **What happened.** User reported GIS Editor image export produced a `865x423` PNG and captured the whole editor space instead of only the white map-frame canvas.
2. **Where the case stands.** Confirmed code path now exports the rendered map pixmap rather than scene chrome, and PPTX template loading now preserves the map picture's source pixel dimensions.
3. **What's needed next.** Run the app and export one real composition image from GIS Editor to confirm the saved PNG is `3306x2340` and visually contains only the white map-surround canvas.

## Case Info

| Field | Value |
| ----- | ----- |
| Ticket | N/A |
| Date opened | 2026-06-02 |
| Status | Concluded |
| System | Linux workspace, conda env `ttn-env`, Qt offscreen tests |
| Evidence sources | Source code, git diff, config loader probe, focused pytest runs |

## Problem Statement

User-reported hypotheses:

1. GIS Editor export currently saves only `865x423` px.
2. GIS Editor export captures the whole GIS Editor area instead of only the white canvas containing the map frame.

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| `src/thucthengay/editor/widgets/gis_canvas.py` | Available | Export path writes `_rendered_pixmap`, not the QGraphicsScene screenshot. |
| `src/thucthengay/editor/modes/review_edit_mode.py` | Available | Canvas render request uses `final_render_output_size(context.template_metadata)`. |
| `src/thucthengay/export/final_render.py` | Available | Output size prefers `selected_slide.shapes[].picture.media.image.width_px/height_px` when present. |
| `src/thucthengay/export/template_loader.py` | Available | Previously did not populate selected-slide image pixel metadata from PPTX; fixed in this investigation. |
| Runtime probe | Available | Before fix, `config.json` loaded `DaBac` as `(3305, 2339)` due to fallback. After fix, it loads `(3306, 2340)`. |

## Confirmed Findings

### Finding 1: Scene/widget-sized export explains the reported `865x423`

**Evidence:** `src/thucthengay/editor/widgets/gis_canvas.py:114`

**Detail:** The desired export API is `export_displayed_image()`. In the current worktree it saves `_rendered_pixmap` directly, which excludes QGraphicsView scene chrome. A `865x423` output is consistent with a viewport/frame-sized capture path, not the final render-size path.

### Finding 2: GIS canvas render size is intended to come from final template output size

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:635`

**Detail:** `_request_canvas_render()` calls `final_render_output_size(context.template_metadata)` before building the `RenderSpec`. This means the GIS canvas should render a full map-surround image at template output dimensions rather than widget dimensions.

### Finding 3: PPTX-loaded metadata lacked embedded map image pixel dimensions

**Evidence:** `src/thucthengay/export/template_loader.py:122`

**Detail:** Before this investigation, `load_target_template()` only saved `source` and `element_names` into `TemplateMetadata.metadata`. Therefore `final_render_output_size()` could not use the placeholder image's `3306x2340` dimensions and fell back to converting map-frame points to pixels.

### Finding 4: The loader now preserves picture dimensions

**Evidence:** `src/thucthengay/export/template_loader.py:119`

**Detail:** The loader now records `metadata.selected_slide.shapes[0].picture.media.image.width_px/height_px` when the map placeholder is a PPTX picture.

## Deduced Conclusions

### Deduction 1: Two mechanisms combined into the reported behavior

**Based on:** Findings 1, 2, and 3.

**Reasoning:** Capturing the scene or displayed widget yields viewport-scale output and can include editor chrome. Rendering/exporting the map pixmap at `final_render_output_size()` yields the white map-surround canvas. Missing PPTX pixel metadata made the final-size calculation less exact.

**Conclusion:** The correct export should use the rendered map pixmap and PPTX picture dimensions; both conditions are now covered in code and tests.

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Error origin | `GisCanvasWidget.export_displayed_image()` and PPTX metadata loading |
| Trigger | User clicks GIS Editor export button |
| Condition | Export must use current map render artifact, not the QGraphicsView scene; template metadata must carry source picture size |
| Related files | `review_edit_mode.py`, `gis_canvas.py`, `final_render.py`, `template_loader.py`, `test_config_service.py`, `test_review_edit_mode.py` |

## Conclusion

**Confidence:** High

The evidence shows the `865x423` symptom comes from a viewport/display export path, while the target behavior requires saving the rendered map canvas at template image dimensions. Current code now exports the rendered pixmap and the PPTX loader now provides `3306x2340` image dimensions to the final-size calculation.

## Recommended Next Steps

### Fix direction

Keep GIS Editor export bound to the rendered map pixmap, and keep final output size driven by PPTX picture pixel metadata when available. The code changes in this case implement the metadata side and preserve existing export-widget behavior.

### Diagnostic

Run the desktop app, open a composition with a rendered GIS canvas, click `Xuất ảnh`, and inspect the saved PNG dimensions and content.

## Reproduction Plan

1. Load `config.json` through `load_project_config()`.
2. Confirm `final_render_output_size(result.template_metadata["DaBac"]) == (3306, 2340)`.
3. In GIS Editor, select a composition with visible raster layers.
4. Export the GIS image and verify the saved PNG is `3306x2340`, white canvas only, with the map frame and raster content.

## Side Findings

- The earlier fallback after PPTX loading produced `(3305, 2339)`, one pixel short on each axis, because the loader exposed only shape points and not the embedded picture's source pixels.
