# Investigation: PPTX Export With Multiple Templates

## Hand-off Brief

1. **What happened.** User requested a risk review of PPTX export behavior, especially when targets use different PPTX templates.
2. **Where the case stands.** Concluded for source review: exporter uses target-specific templates per slide, but several mixed-template risks are not surfaced or tested.
3. **What's needed next.** Add mixed-template validation/tests, especially slide-size/base-template compatibility propagation into Export preflight.

## Case Info

| Field            | Value                                                 |
| ---------------- | ----------------------------------------------------- |
| Ticket           | N/A                                                   |
| Date opened      | 2026-06-12                                            |
| Status           | Concluded                                             |
| System           | Windows, conda env `ttn-env`, project `3.ThucTheNgay` |
| Evidence sources | Source code, tests, BMad project context              |

## Problem Statement

User asks: review and assess potential PPTX export failures, especially when targets use different PPTX templates.

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| BMad project context | Available | Module ownership and workspace/source-of-truth rules loaded. |
| Export source code | Available | `export_combined_pptx` traced through pipeline/UI calls. |
| Tests | Available | Selected PPTX/preflight/pipeline tests pass; no direct multi-template PPTX export test found. |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | PPTX export module | High | Done | Target-specific template is loaded per included composition. |
| 2 | Composition/template data model | High | Done | Template metadata is attached to `TargetConfig.metadata` at config load. |
| 3 | Editor export trigger | Medium | Done | Export UI passes only target list, not config template compatibility issues. |
| 4 | Unit tests | Medium | Done | Current selected tests pass; multi-template combined PPTX export is not covered. |

## Timeline of Events

| Time | Event | Source | Confidence |
| ---- | ----- | ------ | ---------- |
| 2026-06-12 | Investigation opened from user request. | User message | Confirmed |
| 2026-06-12 | `pytest tests/unit/test_pptx_exporter.py tests/unit/test_export_preflight_plan.py tests/unit/test_export_pipeline.py -q` passed. | Local command | Confirmed |

## Confirmed Findings

### Finding 1: PPTX export uses each target's own template per slide

**Evidence:** `src/thucthengay/export/pptx_exporter.py:71`

**Detail:** The exporter iterates included compositions, resolves `target = target_map[composition.target_id]`, loads `template = _template_metadata(target)`, and opens `Presentation(template.template_pptx)` for that composition's slide.

### Finding 2: Combined PPTX slide size is taken only from the first exported slide's template

**Evidence:** `src/thucthengay/export/pptx_exporter.py:74`

**Detail:** The destination presentation width/height are set only when `slide_number == 1`. Later slides copy shape geometry from their own templates into the same destination deck without a slide-size compatibility check.

### Finding 3: Config load can detect multi-template compatibility risk, but Export preflight does not receive it

**Evidence:** `src/thucthengay/config/service.py:151`, `src/thucthengay/editor/modes/export_mode.py:135`, `src/thucthengay/export/pipeline.py:79`

**Detail:** `load_project_config()` appends `template_compatibility_issues(...)`, while ExportMode and `run_full_export()` call `build_export_preflight_plan(...)` with only workspace service and targets. The optional `template_issues` parameter is not passed in these production paths.

### Finding 4: Slide copying copies shapes and relationships, not full slide/master/theme semantics

**Evidence:** `src/thucthengay/export/pptx_slide_copy.py:21`

**Detail:** `copy_only_slide()` creates a blank destination slide and deep-copies source shape XML. This preserves many shape-level details but does not import the source slide size as a per-slide property and does not explicitly merge source masters/themes/layouts.

### Finding 5: Current export tests do not cover combined export with different target templates

**Evidence:** `tests/unit/test_pptx_exporter.py:211`, `tests/unit/test_export_preflight_plan.py:130`

**Detail:** PPTX exporter tests cover one-template export, placeholder replacement, ordering, and blocking cases. Preflight tests cover two targets for ordering, but not actual combined PPTX generation from different PPTX template files.

## Deduced Conclusions

### Deduction 1: Different template dimensions can silently produce a visually wrong deck

**Based on:** Findings 1, 2, and 4.

**Reasoning:** Each target can supply a different PPTX file, but the output deck has a single global slide size from the first template. PowerPoint presentations cannot maintain independent slide sizes per slide, so later templates with different dimensions will be copied into the first template's coordinate system.

**Conclusion:** Mixed target templates are supported only when they are layout-compatible enough for a single destination deck; this is not enforced at export time.

### Deduction 2: Users may not see an Export-mode warning for mixed templates

**Based on:** Finding 3.

**Reasoning:** Compatibility warnings are generated during config load but are not persisted into ExportMode state or passed into export preflight/pipeline.

**Conclusion:** Export can appear clean even when config load detected multiple PPTX templates with unknown/different base/theme/master compatibility.

## Hypothesized Paths

### Hypothesis 1: Mixed target templates may be flattened into one export template

**Status:** Refuted

**Theory:** If exporter receives a single global template path while selected compositions were built from different target templates, export may silently use the wrong template for some slides.

**Resolution:** Refuted by `src/thucthengay/export/pptx_exporter.py:71`; template is selected per composition target.

### Hypothesis 2: Multi-template compatibility warnings are dropped before Export preflight

**Status:** Confirmed

**Theory:** `target.template_compatibility_unknown` exists in config load result but is not shown in Export preflight.

**Resolution:** Confirmed by `src/thucthengay/editor/app_shell.py:154`, `src/thucthengay/editor/modes/export_mode.py:135`, and `src/thucthengay/export/pipeline.py:79`.

### Hypothesis 3: Different slide sizes are not validated

**Status:** Confirmed

**Theory:** The exporter/preflight does not reject or warn when template slide dimensions differ.

**Resolution:** Confirmed by source trace; compatibility signature in `template_loader.py` does not include slide dimensions.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| Actual PPTX templates used in user's data | Needed to reproduce visual/layout mismatch | Inspect workspace/config or create targeted test fixtures. |
| PowerPoint rendering verification | Needed to prove whether copied theme/master differences render incorrectly in Microsoft PowerPoint | Open generated multi-template deck manually or via visual regression tooling. |

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Error origin | `export_combined_pptx`, `copy_only_slide`, ExportMode preflight |
| Trigger | User starts PPTX export |
| Condition | Selected targets/compositions may use different templates |
| Related files | `src/thucthengay/export/pptx_exporter.py`, `src/thucthengay/export/pptx_slide_copy.py`, `src/thucthengay/export/preflight.py`, `src/thucthengay/config/service.py`, `src/thucthengay/editor/modes/export_mode.py`, `src/thucthengay/export/pipeline.py` |

## Conclusion

**Confidence:** Medium

The exporter does not flatten all slides to one target template; it selects each target's template per slide. The main confirmed risks are that the combined deck uses the first template's slide size, mixed-template compatibility warnings are generated but not propagated to Export preflight/pipeline, and no test covers actual PPTX generation from multiple different target templates.

## Recommended Next Steps

### Fix direction

Add a source-of-truth path for config/template compatibility issues into ExportMode and `run_full_export`, then add preflight checks for slide width/height compatibility and a regression test for two included targets with different PPTX templates.

### Diagnostic

Create two one-slide PPTX templates with different slide dimensions or base/theme/master signatures; include one composition per target; run Export preflight and combined PPTX export; verify the warning/error appears and output slide count/order remains correct.

## Reproduction Plan

1. Build workspace with two included compositions: `alpha__YYYYMMDD` and `beta__YYYYMMDD`.
2. Configure `alpha` and `beta` with distinct `template_pptx_file` values.
3. Run `build_export_preflight_plan()` through the same path as ExportMode.
4. Run `run_full_export()` and inspect output PPTX dimensions and generated export log.

## Side Findings

- Confirmed: selected test group passes in `ttn-env`: `13 passed in 1.37s`.
