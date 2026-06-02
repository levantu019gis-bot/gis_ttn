---
title: 'PPTX placeholder auto match'
type: 'feature'
created: '2026-06-03'
status: 'done'
baseline_commit: 'd13dd1fff8a738119d27c10857b0e1fa47ca6e79'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/investigations/pptx-placeholder-auto-match-investigation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `config.json` currently stores raw PPTX `element_id` values for map/text replacement; after the user edits a template, PowerPoint can regenerate IDs and the config must be repaired by hand.

**Approach:** Resolve placeholders from the actual PPTX during config load by using stable selectors first, especially shape names such as `ttn:map_image`, `ttn:title`, `ttn:time`, and `ttn:comment`, then emit current `element_id` values into derived `template_metadata` so the existing export path can keep replacing by ID.

## Boundaries & Constraints

**Always:** Keep PPTX logic in `export/`; keep config path resolution in `config/`; preserve old ID-only configs; use Vietnamese blocking issues; keep low-level slide copy/replacement unchanged.

**Ask First:** Persisting rewritten `element_id` values back into `config.json`; changing the PPTX template file itself; replacing python-pptx.

**Never:** Silently choose among ambiguous matches; import UI/Qt from core export/config modules; remove support for existing `element_id` mappings.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Renamed template shapes | Config has stale IDs, PPTX shapes are named `ttn:<field>` | Loader resolves placeholders to current IDs in `template_metadata`; export/render use resolved IDs | N/A |
| Legacy template | Config ID still exists, no selector/name convention | Loader keeps configured ID | Existing validation remains |
| Missing/stale ID and no match | Required placeholder ID is absent and no selector/name/text fallback matches | Config load blocks | `target.template_element_missing` |
| Ambiguous match | Two shapes match the same selector/name convention | Config load blocks | `target.template_element_ambiguous` |

</frozen-after-approval>

## Code Map

- `src/thucthengay/models/template.py` -- placeholder schema currently requires `element_id`; add optional selector metadata while preserving ID use.
- `src/thucthengay/export/template_loader.py` -- config-load hook that reads PPTX and creates derived `TemplateMetadata`.
- `src/thucthengay/export/pptx_exporter.py` -- export consumer of resolved metadata; should guard unresolved metadata cleanly.
- `src/thucthengay/export/final_render.py` -- uses map placeholder ID to derive picture pixel size.
- `tests/unit/test_config_service.py` -- best focused coverage for config load and PPTX metadata resolution.
- `tests/unit/test_models.py` -- schema round-trip coverage for selector fields.

## Tasks & Acceptance

**Execution:**
- [x] `src/thucthengay/models/template.py` -- add selector model and make placeholders capable of carrying selector-first mappings.
- [x] `src/thucthengay/export/template_analyzer.py` -- add PPTX shape inventory and deterministic placeholder matching.
- [x] `src/thucthengay/export/template_loader.py` -- resolve configured placeholders before validating map frame and metadata.
- [x] `src/thucthengay/export/pptx_exporter.py`, `src/thucthengay/export/final_render.py` -- guard against unresolved placeholder IDs in manually supplied metadata.
- [x] `tests/unit/test_models.py`, `tests/unit/test_config_service.py` -- cover selector schema, stale-ID repair, selector-only repair, and ambiguity blocking.

**Acceptance Criteria:**
- Given `examples/templates/target_001.template.pptx` has shapes named `ttn:map_image`, `ttn:title`, `ttn:time`, and `ttn:comment`, when `load_project_config("config.json")` runs with stale IDs 65-68, then derived metadata resolves those placeholders to current IDs 48-51.
- Given a legacy template where configured IDs still exist and no selector is supplied, when config loads, then current behavior remains valid.
- Given two shapes match the same required placeholder selector, when config loads, then a blocking issue names the ambiguity instead of guessing.

## Verification

**Commands:**
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_models.py tests/unit/test_config_service.py tests/unit/test_pptx_exporter.py tests/unit/test_export_final_render.py -q` -- expected: focused tests pass.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync ruff check src/thucthengay/models/template.py src/thucthengay/export/template_analyzer.py src/thucthengay/export/template_loader.py src/thucthengay/export/pptx_exporter.py src/thucthengay/export/final_render.py tests/unit/test_models.py tests/unit/test_config_service.py` -- expected: no lint errors.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync python -m thucthengay --smoke` -- expected: app smoke succeeds.

## Suggested Review Order

**Resolver Entry**

- Loader now resolves placeholders before map-frame validation.
  [`template_loader.py:80`](../../src/thucthengay/export/template_loader.py#L80)

- Metadata records both shape inventory and ID resolution trace.
  [`template_loader.py:145`](../../src/thucthengay/export/template_loader.py#L145)

**Matching Logic**

- Placeholder matching prefers explicit selector, then `ttn:<field>`, then legacy ID.
  [`template_analyzer.py:69`](../../src/thucthengay/export/template_analyzer.py#L69)

- Selector fields support name, title, description/alt text, and text marker.
  [`template_analyzer.py:185`](../../src/thucthengay/export/template_analyzer.py#L185)

**Schema And Guards**

- Placeholder IDs are optional so selector-only configs can load.
  [`template.py:30`](../../src/thucthengay/models/template.py#L30)

- Export surfaces unresolved manual metadata as a blocking placeholder issue.
  [`pptx_exporter.py:180`](../../src/thucthengay/export/pptx_exporter.py#L180)

**Tests**

- Stale IDs are repaired from renamed `ttn:<field>` shapes.
  [`test_config_service.py:236`](../../tests/unit/test_config_service.py#L236)

- Selector-only and ambiguous selector behavior are covered.
  [`test_config_service.py:278`](../../tests/unit/test_config_service.py#L278)
