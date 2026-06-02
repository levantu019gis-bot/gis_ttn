---
title: 'Map Surround Layout'
type: 'feature'
created: '2026-06-02'
status: 'done'
baseline_commit: '46db17ba05da1493022402296a526d034eb306ac'
context:
  - '_bmad-output/project-context.md'
  - '_bmad-output/implementation-artifacts/investigations/123-template-map-structure-investigation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The current GIS Editor and render output treat the whole map image as a raster canvas with coordinate labels drawn on its edges. The reference `examples/templates/123.jpg` instead uses a full map-surround layout: white surround, outer coordinate frame, DMS labels around the map, and satellite imagery inside an inset inner map panel.

**Approach:** Add a layout-aware map-surround render path that keeps the public `RenderSpec` contract but renders raster into the inner panel and composites it onto a full white map image. Update the GIS Editor canvas to request and display the same full map image so preview and output share the same structure.

## Boundaries & Constraints

**Always:** Keep render core Qt-free and owned by `render/`. Preserve `view.center` and `view.scale` as the source of truth for `geo_window`; do not switch composition view state back to bbox extent. Keep raster reading windowed/decimated through existing raster code, and keep structured `RenderError` issue behavior. Base default layout ratios on the measured `123.jpg` geometry: full image `3306x2340`, outer frame near `244..3271 / 165..2306`, and inner map panel near `292..3223 / 213..2258`.

**Ask First:** Ask before changing persisted JSON schemas, template metadata format, PPTX export mechanics, final output dimensions, or any workspace/cache/composition data. Ask before deleting or rewriting the reference image, temporary lock file, or investigation artifact.

**Never:** Do not import PySide6/editor modules into `render/`. Do not add north arrow, scale bar, boundary overlay, or internal map grid mesh. Do not use real operator GeoTIFFs/PPTX/network in tests. Do not solve perceived image shrinkage by distorting aspect ratio or stretching raster non-uniformly.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full map render | Valid spec with visible raster layers | Returned canvas keeps `spec.output_width/output_height`; white surround and frames are visible; raster pixels appear only inside the inner map panel | Preserve non-fatal raster issues |
| Uncovered raster area | Raster covers part of `geo_window` | Inner map panel uncovered pixels use configured background color; surround stays white | Invalid background remains structured `RenderError` |
| No visible layer | Valid spec with empty visible layers | Full map image still renders with background-filled inner panel and coordinate surround | No layer-specific error |
| Invalid grid | Unsupported label format or dense interval | Rendering fails with existing structured frame issue ids | Preserve prior raster issues where applicable |

</frozen-after-approval>

## Code Map

- `src/thucthengay/render/frame.py` -- coordinate-frame drawing; needs layout-aware outer/inner frame rendering and DMS placement around the inner panel.
- `src/thucthengay/render/raster.py` -- raster compositing canvas factory; should support rendering to an inner panel size without changing geospatial math.
- `src/thucthengay/render/core.py` -- composed render entry point; should render inner raster then compose the full map-surround output.
- `src/thucthengay/render/__init__.py` -- public render API exports if a layout helper becomes public for tests/UI.
- `src/thucthengay/editor/widgets/gis_canvas.py` -- GIS Editor preview surface; should display the full map-surround image and keep frame sizing consistent with template aspect.
- `src/thucthengay/editor/modes/review_edit_mode.py` -- render request sizing caller; should continue to request the visible map-frame output size.
- `tests/unit/test_render_frame.py` -- focused frame/layout tests.
- `tests/unit/test_render_core.py` -- composed map render behavior tests.
- `tests/unit/test_review_edit_mode.py` -- GIS Canvas sizing/preview contract tests if needed.

## Tasks & Acceptance

**Execution:**
- [x] `src/thucthengay/render/frame.py` -- add a `MapSurroundLayout`/rect helper and layout-aware frame drawing -- gives a single reusable contract for outer frame, inner panel, and labels.
- [x] `src/thucthengay/render/raster.py` -- allow raster layers to render into a supplied output size while preserving existing background, cancellation, issue, and memory checks -- lets `render_map()` create an inner raster panel safely.
- [x] `src/thucthengay/render/core.py` -- compose full white surround plus inner raster panel and draw layout-aware coordinate frame -- makes output match `123.jpg` structure.
- [x] `src/thucthengay/editor/widgets/gis_canvas.py` -- preview full rendered map image without adding another decorative frame/grid on top -- aligns GIS Editor with output.
- [x] `tests/unit/test_render_frame.py` and `tests/unit/test_render_core.py` -- add tests for inner panel placement, white surround, label/frame pixels, invalid grid preservation, and no internal mesh -- protects the new spatial contract.

**Acceptance Criteria:**
- Given a valid render spec, when `render_map()` returns, then the canvas dimensions still equal `spec.output_width x spec.output_height` and the map image structure includes a white surround, outer frame, inner frame, and raster/background inside the inner panel.
- Given the same spec is displayed in GIS Editor, when the preview render finishes, then the displayed pixmap is the full map-surround image rather than a second-framed crop of the raster area.
- Given raster coverage only partially overlaps `geo_window`, when rendering completes, then uncovered pixels inside the inner map panel use `spec.background.color` while pixels outside the inner panel remain white.
- Given MVP exclusions remain in force, when render tests inspect the output, then no north arrow, scale bar, boundary overlay, or internal map grid mesh is introduced.

## Spec Change Log

## Design Notes

The measured reference ratios can be expressed relative to the full output size to avoid hard-coding one pixel size:

```text
outer: left 244/3306, top 165/2340, right 3271/3306, bottom 2306/2340
inner: left 292/3306, top 213/2340, right 3223/3306, bottom 2258/2340
```

The renderer should treat the inner panel as the geographic viewport for raster and tick positioning. Labels live in the surround bands so they do not cover satellite pixels.

## Verification

**Commands:**
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_render_frame.py tests/unit/test_render_core.py tests/unit/test_review_edit_mode.py -q` -- expected: focused tests pass.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest -q` -- expected: full suite passes.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync ruff check .` -- expected: no lint findings.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync python -m thucthengay --smoke` -- expected: app smoke succeeds.

## Suggested Review Order

**Render Composition**

- Entry point now composes full surround around an aspect-safe raster viewport.
  [`core.py:104`](../../src/thucthengay/render/core.py#L104)

- Peak-memory preflight accounts for inner raster and frame buffers.
  [`core.py:99`](../../src/thucthengay/render/core.py#L99)

**Layout Contract**

- Reference-derived rectangles define outer frame, inner panel, and geo viewport.
  [`frame.py:56`](../../src/thucthengay/render/frame.py#L56)

- Aspect fitting prevents raster geography from stretching inside the sample frame.
  [`frame.py:101`](../../src/thucthengay/render/frame.py#L101)

- Surround frame uses map-view ticks and suppresses labels that would spill inward.
  [`frame.py:397`](../../src/thucthengay/render/frame.py#L397)

**Raster Boundary**

- Alternate-size raster rendering validates derived dimensions before compositing.
  [`raster.py:308`](../../src/thucthengay/render/raster.py#L308)

**GIS Preview**

- GIS canvas stops drawing decorative overlays on top of completed render pixmaps.
  [`gis_canvas.py:287`](../../src/thucthengay/editor/widgets/gis_canvas.py#L287)

**Tests**

- Core render tests assert white surround, background fill, and aspect-safe samples.
  [`test_render_core.py:107`](../../tests/unit/test_render_core.py#L107)

- Frame tests lock sample geometry and guard against label spill into the inner map.
  [`test_render_frame.py:139`](../../tests/unit/test_render_frame.py#L139)
