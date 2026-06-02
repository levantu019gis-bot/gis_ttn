# Investigation: GIS Editor render slow after click, pan, zoom

## Hand-off Brief

1. **What happened.** User reports GIS Editor render is slow after selecting a composition and especially after pan/zoom; code evidence confirms selection and view edits trigger workspace/UI refresh plus render lifecycle work.
2. **Where the case stands.** Status: Active; likely bottlenecks are full-size GIS canvas render, immediate persistence/queue refresh after view edits, lack of two-stage GIS preview, and non-cooperative render cancellation.
3. **What's needed next.** Implement low-risk render lifecycle optimization before touching map frame geometry: debounce/persist view edits, reuse cached preview, and add two-stage GIS preview.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-02 |
| Status | Active |
| System | PySide6 desktop app, Python project, conda env `ttn-env` |
| Evidence sources | `review_edit_mode.py`, `gis_canvas.py`, `render_job.py`, `render/core.py`, `render/raster.py`, `workspace/service.py`, unit tests |

## Problem Statement

User-reported description: GIS Editor render speed is still very slow after clicking a composition, especially after pan and zoom. Need detailed assessment of current implementation and best optimization strategies.

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| Source code | Available | Main code paths traced in Review/Edit mode, GIS canvas, render job, raster render, workspace service. |
| Tests | Available | Tests assert GIS canvas uses final template render size, not viewport size. |
| Runtime profiling | Missing | No wall-clock timing, layer count, raster file size, CRS distribution, or thread timing captured yet. |
| User reproduction video/log | Missing | User observation is credible but not quantified. |

## Confirmed Findings

### Finding 1: GIS canvas requests final-template-size renders

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:635` uses `final_render_output_size(context.template_metadata)`, and `tests/unit/test_review_edit_mode.py:725` asserts expected size `(3306, 2340)`.

**Detail:** This preserves final map frame geometry, but it means an editor preview can render millions of pixels even when displayed much smaller.

### Finding 2: Selection runs validation persistence and detail-panel update

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:443` reads the composition, `:446-451` runs validation and saves summary, and `:456-460` updates panels and emits selection.

**Detail:** A click is not just a UI selection; it can read/write JSON, validate, update multiple widgets, and start render requests.

### Finding 3: Pan/zoom persists view and refreshes the queue projection

**Evidence:** `src/thucthengay/editor/widgets/gis_canvas.py:263-264` emits view edit after drag release, `:274-275` emits on wheel zoom, `src/thucthengay/editor/modes/review_edit_mode.py:1028-1046` persists view then calls `_update_detail_panels()` and `_refresh_workspace_projection()`.

**Detail:** Each completed pan/zoom writes composition JSON, marks stale, refreshes UI, and may reset selection.

### Finding 4: GIS canvas does not use the existing two-stage preview controller

**Evidence:** `src/thucthengay/jobs/render_job.py:67-122` defines interactive/settled two-stage requests, but `src/thucthengay/editor/modes/review_edit_mode.py:647-656` creates only one `SETTLED_HIGH_RES` canvas request.

**Detail:** GIS Editor has no low-res immediate preview path and no debounce-settled path, even though the architecture exists.

### Finding 5: Render cancellation is not cooperative in the Qt worker path

**Evidence:** `src/thucthengay/editor/render_worker.py:30-33` calls `run_preview_render_job()` without passing `is_cancelled`; `src/thucthengay/editor/modes/review_edit_mode.py:750-753` calls `quit()`/`wait(2000)` on the thread.

**Detail:** A running raster render cannot be interrupted inside raster reads/frame drawing from the UI path; new interactions may wait for old work or allow stale heavy jobs to finish.

### Finding 6: Raster core is already windowed/decimated

**Evidence:** `src/thucthengay/render/raster.py:254-259` uses `window=` and `out_shape=`, with bilinear resampling.

**Detail:** The likely issue is not full-raster loading, but how often and how large the preview renders are requested.

## Deduced Conclusions

### Deduction 1: The slow feel is likely dominated by lifecycle churn plus full-size preview

**Based on:** Findings 1, 2, 3, 4, 5.

**Reasoning:** Selecting or editing a view can perform validation, JSON persistence, tree rebuild, widget reset, render cancellation, and a high-resolution render. Because cancellation is not cooperative, obsolete renders can consume time after the user has moved on.

**Conclusion:** Best optimizations should reduce render frequency and output size for interactive preview while preserving final-size geometry for export/final render.

## Hypothesized Paths

### Hypothesis 1: Full-size GIS preview is the largest direct CPU/memory cost

**Status:** Open

**Theory:** Rendering `(3306, 2340)` for an editor viewport costs more than needed.

**Would confirm:** Timing logs show `_request_canvas_render`/`render_map` dominates click/pan/zoom latency.

**Would refute:** Timings show workspace JSON/tree refresh dominates while render finishes quickly.

### Hypothesis 2: Workspace refresh after pan/zoom causes visible UI lag

**Status:** Open

**Theory:** `_persist_canvas_view()` causes repeated full queue reload/rebuild work after view edits.

**Would confirm:** Timing logs around `update_view_state`, `_update_detail_panels`, `_refresh_workspace_projection`.

**Would refute:** These calls are negligible compared with raster render.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | --- | --- |
| Per-stage timings | Needed to rank bottlenecks precisely | Add temporary timing logs around selection, validation, workspace writes, target preview, canvas render, raster layers, frame drawing. |
| Data size profile | Needed for cache strategy | Log visible layer count, CRS, raster dimensions, cache paths, output size, render window. |
| User workflow frequency | Needed for debounce thresholds | Observe how often wheel/drag events are triggered in normal editing. |

## Source Code Trace

| Element | Detail |
| --- | --- |
| Error origin | No crash/error; performance issue originates in render lifecycle and state refresh. |
| Trigger | Composition selection, drag release, wheel zoom. |
| Condition | Valid composition with visible layers and template metadata; GIS canvas render requested at final output size. |
| Related files | `src/thucthengay/editor/modes/review_edit_mode.py`, `src/thucthengay/editor/widgets/gis_canvas.py`, `src/thucthengay/editor/render_worker.py`, `src/thucthengay/jobs/render_job.py`, `src/thucthengay/render/core.py`, `src/thucthengay/render/raster.py`, `src/thucthengay/workspace/service.py` |

## Conclusion

**Confidence:** Medium

The evidence confirms multiple expensive operations are chained to click/pan/zoom. The most likely primary bottleneck is final-size GIS canvas render combined with non-cooperative cancellation; the most likely secondary bottleneck is immediate workspace persistence plus full tree refresh after view edits. Runtime timing is still needed to quantify the exact split.

## Recommended Next Steps

### Fix direction

1. Add timing instrumentation first, behind a debug flag or logger.
2. Implement two-stage GIS canvas preview: low-res interactive render, debounced final-size or medium-size settled render.
3. Debounce pan/zoom persistence and avoid full queue refresh when only selected composition view changed.
4. Add cooperative cancellation token to `RenderWorker` and pass it into `run_preview_render_job`.
5. Add preview cache keyed by render spec identity and reuse existing pixmap while stale.

### Diagnostic

Capture timings for: select composition, validation, save validation summary, target preview spec build, target preview render, canvas spec build, canvas render, raster layer read, frame drawing, QPixmap conversion, workspace list/rebuild.

## Reproduction Plan

1. Open Review/Edit mode with a workspace containing a ready composition with visible raster layer(s).
2. Select the composition.
3. Pan the GIS canvas by dragging, release mouse.
4. Zoom with wheel several times.
5. Compare timings before/after optimization for UI responsiveness and render completion.

## Side Findings

- Export JPEG/DPI settings affect output file size, but do not address interactive render latency unless export is invoked.
