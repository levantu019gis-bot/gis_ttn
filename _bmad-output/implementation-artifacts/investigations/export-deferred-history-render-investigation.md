# Investigation: Export Deferred History And Render

## Hand-off Brief

1. **What happened.** Confirmed: Review/Edit currently writes historical SQLite during include/skip, while export already runs final render preparation inside the export pipeline.
2. **Where the case stands.** Active: source trace is sufficient to plan the requested change; implementation is not started.
3. **What's needed next.** Move historical database side-effects into export preparation and adjust preflight/final-render gating so export owns the final commit point.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-13 |
| Status | Active |
| System | Windows PowerShell, conda env `ttn-env` |
| Evidence sources | `review_edit_mode.py`, `history/service.py`, `export/preflight.py`, `export/pipeline.py`, `export/final_render.py`, `export_mode.py` |

## Problem Statement

User asks to assess and plan a change: database updates and final image rendering should happen only when the user presses export PPTX/TXT. Single-pane export records target/composition history from the post-preflight list. Compare export checks both pane compositions per target and records any composition not already present in the database.

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| Review/Edit history writes | Available | Include/skip calls history service directly. |
| Export pipeline | Available | Export runs preflight, final-render preparation, second preflight, PPTX/TXT/log. |
| Compare render path | Available | Final render resolves pane A/B compositions for render. |
| SQLite schema/upsert | Partial | Existing record method upserts by target/image asset, not explicit composition existence. |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --- | --- | --- | --- |
| 1 | Define exact "composition exists in database" semantics | High | Open | Current schema stores latest composition id per target-image row and include events. |
| 2 | Add export-owned history sync result models/tests | High | Open | Needed before implementation. |
| 3 | Decide preflight handling for auto-renderable final-render issues | Medium | Open | Current UX already allows export when only missing/stale render blocks. |

## Confirmed Findings

### Finding 1: Review/Edit writes SQLite immediately

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:761`, `src/thucthengay/editor/modes/review_edit_mode.py:791`, `src/thucthengay/editor/modes/review_edit_mode.py:892`

**Detail:** Include records history after `apply_include_transition`; skip removes active rows when the previous composition was included.

### Finding 2: Export already performs final render preparation

**Evidence:** `src/thucthengay/export/pipeline.py:84`, `src/thucthengay/export/pipeline.py:89`, `src/thucthengay/export/final_render.py:37`

**Detail:** `run_full_export` builds an initial preflight plan, runs `ensure_final_renders_for_export`, rebuilds preflight, then exports PPTX/TXT.

### Finding 3: Preflight currently treats missing/stale final render as a blocking issue, but the UI allows export when that is the only blocking issue

**Evidence:** `src/thucthengay/export/preflight.py:152`, `src/thucthengay/export/pipeline.py:32`, `src/thucthengay/export/pipeline.py:141`, `src/thucthengay/editor/modes/export_mode.py:158`

**Detail:** `preflight_allows_auto_export` permits export only when blocking errors are final-render missing/log/stale.

### Finding 4: Compare final render uses both pane composition ids

**Evidence:** `src/thucthengay/export/final_render.py:346`, `src/thucthengay/render/spec.py:414`

**Detail:** When `temporal_compare.enabled`, final render resolves `pane_a_composition_id` and `pane_b_composition_id` and passes both into render-spec construction.

## Conclusion

**Confidence:** High

The requested behavior is not fully implemented. Final render is already export-owned, but database history is still Review/Edit-owned. The compare-specific database requirement is also absent: include only records the selected composition, not both pane compositions referenced by a compare state.

## Recommended Next Steps

### Fix direction

Create an export history sync step after the final preflight identifies exportable rows and before PPTX/TXT generation. Remove/disable SQLite writes from Review/Edit include/skip, preserving only workspace JSON state changes and UI messaging.

### Diagnostic

Add unit tests for single-pane export history sync, compare export history sync with one pre-existing pane, and no Review/Edit SQLite writes.

## Reproduction Plan

Use unit tests with fake workspace/history services: include compositions in workspace, run export pipeline, assert history writes occur only from export and only for exportable rows.
