# Investigation: Review/Edit Compare No Effect

## Hand-off Brief

1. **What happened.** User asked whether Review/Edit Compare has cases where clicking it produces no visible effect.
2. **Where the case stands.** Confirmed no-effect branches were found and patched in Review/Edit UI/render request.
3. **What's needed next.** Run full regression and keep a real GUI workspace check as optional visual verification.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-10 |
| Status | Concluded |
| System | Windows, conda env `ttn-env`, PySide6 desktop app |
| Evidence sources | Source code, unit tests, static grep |

## Problem Statement

Người dùng hỏi: "kiểm tra lại pipeline, có case nào mà bấm vào \"compare\" tuy nhiên không có hiệu ứng gì không".

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| Review/Edit UI source | Available | `src/thucthengay/editor/modes/review_edit_mode.py` |
| Workspace state service | Available | `src/thucthengay/workspace/service.py` |
| Render spec builder | Available | `src/thucthengay/render/spec.py` |
| Tests | Available | `tests/unit/test_review_edit_mode.py`, `tests/unit/test_render_spec.py` |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --- | --- | --- | --- |
| 1 | Compare click event to persisted state | High | Done | Missing two time points disabled the checkbox |
| 2 | Persisted state to render request | High | Done | Render spec errors now surface on the canvas |
| 3 | Render spec to canvas result | Medium | Done | Existing render worker errors already surface via `_apply_canvas_render()` |

## Timeline of Events

| Time | Event | Source | Confidence |
| --- | --- | --- | --- |
| 2026-06-10 | Compare changed from layer-based pane selection to composition-based pane selection | Current working tree | Confirmed |
| 2026-06-10 | No-effect branches were patched and covered by focused tests | Source/tests | Confirmed |

## Confirmed Findings

### Finding 1: Compare with fewer than two time points could be clicked and then reverted

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:1520`

**Detail:** Before the patch, `_persist_temporal_compare_controls()` handled `enabled and count < 2` by setting the checkbox back to unchecked and returning. That produced a visible status message, but the main user action had no map effect.

### Finding 2: Save-selection errors were immediately overwritten

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:1549`

**Detail:** The error branch set `compare_status_label`, then reloaded the controls. Reloading the controls replaced the error message with the normal comparison status text.

### Finding 3: Render spec failures after Compare state was saved were silent

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:802`

**Detail:** `_request_canvas_render()` caught `RenderSpecError` and `ValidationError` and returned without setting a GIS canvas error. A stale/invalid Compare state could therefore leave the canvas stale instead of explaining why no split render appeared.

## Deduced Conclusions

### Deduction 1: There were reachable "click Compare but no visible split" cases

**Based on:** Findings 1-3

**Reasoning:** Compare UI could accept/revert invalid input, hide persistence errors, or abort preview creation after state was saved. In all three cases, the map pane would not visibly switch to split render.

**Conclusion:** The user's concern is valid for edge cases, especially incomplete data, invalid stored comparison state, and render-spec validation failures.

## Hypothesized Paths

### Hypothesis 1: Render request silently aborts after Compare state is saved

**Status:** Confirmed

**Theory:** Some branches in `_request_canvas_render()` return without updating the canvas error/status after the user clicks Compare.

**Supporting indicators:** The render request catches `RenderSpecError` and `ValidationError` and returns without setting UI feedback.

**Would confirm:** Source trace showing reachable Compare-enabled state that hits a silent return.

**Would refute:** Tests or code proving every Compare-enabled failure path updates visible UI status.

**Resolution:** Confirmed by source trace and covered by `test_review_edit_compare_render_spec_error_surfaces_on_canvas`.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | --- | --- |
| Real GUI click with real workspace | Confirms visual effect end-to-end | Run app with sample workspace and observe canvas |

## Source Code Trace

| Element | Detail |
| --- | --- |
| Error origin | `src/thucthengay/editor/modes/review_edit_mode.py:802` |
| Trigger | User toggles `reviewCompareEnabled` |
| Condition | Fewer than two usable compositions, invalid/missing pane IDs, or render spec validation failure |
| Related files | Review/Edit mode, workspace service, render spec |

## Conclusion

**Confidence:** High

There were real no-effect cases around the Compare pipeline. They were fixed by disabling the checkbox when fewer than two time points are available, preserving save errors after control reload, and surfacing render-spec failures on the GIS canvas.

## Recommended Next Steps

### Fix direction

Patch Review/Edit guardrails only; no render-core change needed.

### Diagnostic

Focused tests: `conda run -n ttn-env python -m pytest tests\unit\test_review_edit_mode.py tests\unit\test_render_spec.py -q`.

## Reproduction Plan

Use a workspace with one target and fewer than two compositions: Compare checkbox should be disabled with a status message. Use a workspace with invalid persisted pane composition id: canvas should enter ERROR with a render-spec message.

## Side Findings

- None yet.
