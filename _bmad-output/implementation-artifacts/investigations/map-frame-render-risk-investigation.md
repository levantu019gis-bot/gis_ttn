# Investigation: Map Frame Render Risk

## Hand-off Brief

1. **What happened.** User requested a risk review of current map-frame rendering from config/template/state, including multiple target PPTX templates and repeated include/back/skip flows.
2. **Where the case stands.** Source trace is complete enough for a risk assessment; the strongest risks are silent fallback of untyped grid style and semantic PPTX template mismatches that are valid numerically.
3. **What's needed next.** Add targeted validation/tests if these risks need to be hardened: grid style schema/preflight, template geometry compatibility, and template reload/currentness against edited PPTX files.

## Case Info

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Ticket           | N/A                                                                   |
| Date opened      | 2026-06-13                                                            |
| Status           | Active                                                                |
| System           | Windows PowerShell, conda env `ttn-env`, PySide6 desktop application |
| Evidence sources | Source code, root `config.json`, prior investigation files            |

## Problem Statement

Người dùng yêu cầu kiểm tra cơ chế vẽ khung bản đồ hiện tại: cách đọc kích thước/vị trí từ config, rủi ro sai vị trí/kích thước/label, ảnh hưởng của mỗi target có PPTX template riêng, và việc include/back/skip nhiều lần trên một target có thể ảnh hưởng logic render khung bản đồ hay không.

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| `config.json` | Available | Contains defaults grid style, target scale/grid/export placeholders. |
| Source code | Partial | Need targeted trace of config, render, workspace, export paths. |
| Runtime logs/export logs | Missing | No fresh failing export/render log supplied for this specific question. |
| Runtime template inspection | Available | `data/templates/target_001.template.pptx` and `target_002` have same slide size and `ttn:*` geometry in this checkout. |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | Config model/load path for grid/template metadata | High | Done | Established input contract. |
| 2 | Render spec/map-frame geometry path | High | Done | Established how width/height/position are derived. |
| 3 | Grid/frame/label drawing path | High | Done | Identified style fallback risks. |
| 4 | PPTX export placement across different templates | High | Done | Identified cross-template risks and existing guards. |
| 5 | Include/back/skip/final render state path | Medium | Done | Stale artifact invalidation traced. |

## Timeline of Events

| Time | Event | Source | Confidence |
| ---- | ----- | ------ | ---------- |
| 2026-06-13 | Investigation opened from user request | conversation | Confirmed |

## Confirmed Findings

### Finding 1: Template map shape, not config `reference_outer_frame`, defines the PowerPoint map placeholder position and size.

**Evidence:** `src/thucthengay/export/template_loader.py:124` reads the resolved map shape and `src/thucthengay/export/template_loader.py:126` builds `MapFrame` from `left/top/width/height`; `src/thucthengay/render/spec.py:300` uses `template.map_frame` to compute the geo window.

**Detail:** Config `grid.style.reference_outer_frame` controls the rendered coordinate surround inside the output image, not the final PPTX placement rectangle.

### Finding 2: Stale configured element ids can be repaired by `ttn:*` shape names during config load.

**Evidence:** `src/thucthengay/export/template_analyzer.py:80` matches conventional names like `ttn:{field}` before falling back to configured element id at `src/thucthengay/export/template_analyzer.py:96`; runtime load of root `config.json` resolved `map_image/title/time/comment` to element ids `48/49/50/51`.

**Detail:** This protects the current config, where many targets declare `65-68`, because the actual template shapes are named `ttn:map_image`, `ttn:title`, `ttn:time`, `ttn:comment`.

### Finding 3: Grid style is intentionally flexible and not schema-validated beyond the renderer's fallback logic.

**Evidence:** `src/thucthengay/models/config.py:39` defines `GridConfig.style` as `dict[str, Any]`; `src/thucthengay/render/frame.py:290` falls back when `reference_outer_frame` is invalid; `src/thucthengay/render/frame.py:225` silently falls back for invalid colors; `src/thucthengay/render/frame.py:198` falls back to PIL default font when the font cannot be opened.

**Detail:** This avoids crashes but can produce a different frame/label layout without a blocking config issue.

### Finding 4: Export has row-level isolation after final render.

**Evidence:** `src/thucthengay/export/pipeline.py:89` generates final renders before PPTX/TXT; `src/thucthengay/export/pipeline.py:157` exports only rows where `not row.blocking`.

**Detail:** One bad composition should be skipped from final PPTX/TXT instead of causing a cascade, assuming its issue is attached to the row.

### Finding 5: PPTX image replacement preserves the placeholder rectangle.

**Evidence:** `src/thucthengay/export/pptx_slide_copy.py:49` finds the placeholder by element id, stores `left/top/width/height` at `src/thucthengay/export/pptx_slide_copy.py:56`, and inserts the rendered picture with those exact dimensions at `src/thucthengay/export/pptx_slide_copy.py:58`.

**Detail:** The export placement itself is deterministic once the correct placeholder is selected; wrong placement comes from wrong/stale placeholder resolution or template geometry, not from arbitrary image insertion.

### Finding 6: View/grid/compare edits invalidate final render artifacts; include/skip do not.

**Evidence:** `src/thucthengay/workspace/service.py:492`, `src/thucthengay/workspace/service.py:611`, and `src/thucthengay/workspace/service.py:585` route edits through `_mark_composition_edit_stale`; that function clears final render/log and un-includes at `src/thucthengay/workspace/service.py:775`. Include and skip transitions at `src/thucthengay/workspace/service.py:638` and `src/thucthengay/workspace/service.py:663` update review state only.

**Detail:** Back/edit after include is safe if all edits go through these service methods. Skip after include does not delete the final image, but export ignores it because `include=false`.

## Deduced Conclusions

### Deduction 1: Template geometry mismatches that are valid PPTX shapes are the main remaining export-position risk.

**Based on:** Findings 1, 2, 5, and `src/thucthengay/export/preflight.py:188`.

**Reasoning:** Preflight blocks different slide sizes across templates, but it does not block different `map_frame` positions/sizes when slide size is the same. A target template can therefore be technically valid but place the final render in a different part of the slide or at a different aspect.

**Conclusion:** Current guards catch missing/invalid map frame and slide-size mismatch, but not same-size templates with semantically different map placeholder geometry.

### Deduction 2: Repeated include/back/skip is unlikely to corrupt frame render state, but it can leave stale image files on disk by design.

**Based on:** Finding 5 and final render currentness hash checks in `src/thucthengay/render/final.py:151`.

**Reasoning:** Edits clear the persisted final render references and mark the composition not include-ready. Skip clears include/review order. Existing files under `renders/` may remain but are not export candidates unless referenced and current.

**Conclusion:** The main risk is orphaned disk files, not wrong export, provided no code path mutates composition JSON outside `WorkspaceService`.

## Hypothesized Paths

### Hypothesis 1: Per-target template differences can cause wrong export placement if config placeholders reference element ids that exist but have different geometry.

**Status:** Confirmed

**Theory:** Template compatibility may validate metadata but not fully guarantee semantic equivalence of map placeholder size/location across target templates.

**Supporting indicators:** User has targets using different template PPTX files; preflight checks slide size mismatch but not same-slide map placeholder geometry mismatch.

**Would confirm:** Code shows map-frame render/export geometry is taken from placeholder metadata without enforcing consistent placeholder dimensions when templates differ.

**Would refute:** Code enforces per-target template geometry consistently from each template and final render dimensions match each placeholder.

**Resolution:** Confirmed as a potential risk, not observed in current two real templates. Runtime inspection shows `target_001` and `target_002` currently share slide size and `ttn:*` geometry.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| Full visual inspection of exported PPTX | Would catch semantic differences not visible from numeric guards | Generate a sample export and inspect slide output |

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Error origin | N/A; exploration case |
| Trigger | Config load, review edit render, final export |
| Condition | Multiple template geometries and repeated state changes |
| Related files | `config/service.py`, `export/template_loader.py`, `render/spec.py`, `render/frame.py`, `export/final_render.py`, `export/pptx_exporter.py`, `workspace/service.py` |

## Conclusion

**Confidence:** Medium

Current implementation has good hard guards for invalid map frame, missing placeholder, slide-count mismatch, slide-size mismatch, and stale final renders. Remaining risks are mostly semantic: invalid `grid.style` silently falling back, same-slide-size PPTX templates with different map placeholder geometry, changed PPTX files whose loaded metadata is stale until config reload, and orphaned render files after repeated include/back/skip.

## Recommended Next Steps

### Fix direction

Recommended hardening:

1. Add a config/preflight warning when included targets use different `template.map_frame` geometry, not only different slide size.
2. Add explicit validation/issue reporting for malformed `grid.style` keys instead of silent fallback for critical layout values.
3. Add a test that edits a view/grid after include and verifies final render references are cleared and export skips until rerender.
4. Add a template reload/currentness guard if users can edit PPTX files while the app is running.

### Diagnostic

Run a targeted export smoke with both template files and compare exported slide dimensions/shape placement, then add a unit test for mismatched same-size map placeholders.

## Reproduction Plan

Create two one-slide PPTX templates with identical slide size but different `ttn:map_image` rectangle; include two target compositions; assert preflight currently allows it except warning, then decide whether to block or warn.

## Side Findings
