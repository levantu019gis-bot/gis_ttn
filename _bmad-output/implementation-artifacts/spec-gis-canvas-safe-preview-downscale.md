---
title: 'GIS Canvas Safe Preview Downscale'
type: 'feature'
created: '2026-06-03'
status: 'done'
baseline_commit: 'b2a2eaeaa91f43658c814fc7ea03cce889868e7b'
context:
  - '_bmad-output/project-context.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The previous GIS canvas preview optimization changed `RenderSpec.output_width/output_height`, which can change map-surround geometry because the render engine uses those dimensions to build frame layout, ticks, labels, and inset map bounds.

**Approach:** Keep GIS canvas `RenderSpec` at final/template size so map-frame geometry remains identical to final render, then downscale only the rendered image stored by the canvas widget for display.

## Boundaries & Constraints

**Always:** Preserve final/template render dimensions in `ReviewEditMode._request_canvas_render()`. Keep frame/layout math inside `render/` unchanged. Keep display-only downscale inside the Qt widget layer.

**Ask First:** Splitting `RenderSpec` into separate `layout_size` and `preview_output_size`, changing final export dimensions, or adding user-configurable preview quality.

**Never:** Do not reduce GIS canvas `RenderSpec.output_width/output_height` as a preview shortcut. Do not change map-frame constants or config defaults to compensate for preview size.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Final-size canvas render | Worker returns a large final-layout numpy canvas | Widget stores a downscaled pixmap for display while the rendered frame geometry is already final-layout | Existing stale token rejection remains in force |
| Small canvas render | Worker returns a canvas below the display max width | Widget preserves original size | Existing export/display behavior remains unchanged |

</frozen-after-approval>

## Code Map

- `src/thucthengay/editor/widgets/gis_canvas.py` -- owns display pixmap storage and exported displayed image.
- `src/thucthengay/editor/modes/review_edit_mode.py` -- remains responsible for building final/template-sized GIS canvas render specs.
- `tests/unit/test_review_edit_mode.py` -- existing GIS canvas widget tests plus focused downscale coverage.

## Tasks & Acceptance

**Execution:**
- [x] `src/thucthengay/editor/widgets/gis_canvas.py` -- add display-only max-width downscale when applying render results.
- [x] `tests/unit/test_review_edit_mode.py` -- cover large preview downscale and verify small rendered images keep original dimensions.

**Acceptance Criteria:**
- Given a final-size GIS canvas render result, when it is applied to the widget, then the stored/displayed pixmap is capped to preview width without changing render-spec dimensions.
- Given a small GIS canvas render result, when it is applied to the widget, then the displayed/exported image keeps its original size.

## Completion Notes

- Chosen as the safe fix after the earlier spec-resize approach affected map-frame structure.
- This reduces Qt display pixmap memory and display cost, but does not yet reduce core render time; deeper render acceleration requires a future layout/output-size separation.

## Verification

**Commands:**
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_review_edit_mode.py -q`
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync ruff check src/thucthengay/editor/widgets/gis_canvas.py tests/unit/test_review_edit_mode.py`
