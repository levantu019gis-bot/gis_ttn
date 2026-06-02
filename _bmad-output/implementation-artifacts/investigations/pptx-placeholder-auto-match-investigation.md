# Investigation: PPTX Placeholder Auto Match

## Hand-off Brief

1. **What happened.** Confirmed: current config stores PPTX placeholder bindings as raw `element_id`, so a template edit that changes shape IDs can break export and require manual config edits.
2. **Where the case stands.** Concluded with medium-high confidence: the project already extracts PPTX metadata during config load, so the lowest-risk solution is a resolver that turns stable selectors/fingerprints into the current `element_id` before render/export.
3. **What's needed next.** Implement an export-owned `template_analyzer`/resolver and gradually migrate config from ID-only mappings to selector-plus-resolved-ID mappings.

## Case Info

| Field | Value |
| ----- | ----- |
| Ticket | N/A |
| Date opened | 2026-06-02 |
| Status | Concluded |
| System | Python 3.11 project, `python-pptx>=1.0`, desktop PySide6 app |
| Evidence sources | `config.json`, `src/thucthengay/models/template.py`, `src/thucthengay/export/template_loader.py`, `src/thucthengay/export/pptx_exporter.py`, `src/thucthengay/config/service.py`, `examples/templates/target_001.template.pptx`, architecture artifact |

## Problem Statement

User reports that each target in `config.json` stores PPTX template element IDs under `export.placeholders`; when the PPTX template changes, PowerPoint may change element IDs and the config must be updated manually.

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| `config.json:69` | Available | Target export config points at one PPTX file and stores `placeholders[].element_id` values. |
| `_bmad-output/planning-artifacts/architecture.md:415` | Available | MVP architecture says export loads element-id mapping from target config. |
| `_bmad-output/planning-artifacts/architecture.md:424` | Available | Architecture explicitly made element ID authoritative and shape names diagnostic only. |
| `src/thucthengay/models/template.py:30` | Available | `TemplatePlaceholder` requires `field`, `element_id`, and `kind`; no stable selector exists. |
| `src/thucthengay/export/template_loader.py:48` | Available | Config load already opens the PPTX and derives `TemplateMetadata`. |
| `src/thucthengay/config/service.py:271` | Available | `load_project_config()` calls `load_target_template()` for every enabled target. |
| `src/thucthengay/export/pptx_exporter.py:81` | Available | Final replacement still uses resolved `template.placeholders` and `element_id`. |
| `examples/templates/target_001.template.pptx` | Available | Current template has usable shape signals: IDs 65-68 for map/title/time/comment, names/text/geometry also present. |

## Confirmed Findings

### Finding 1: Element ID is currently the binding key

**Evidence:** `config.json:72`, `src/thucthengay/models/template.py:35`, `src/thucthengay/export/pptx_exporter.py:81`

**Detail:** Config stores placeholder rows with `field` and `element_id`; the model requires positive `element_id`; export iterates `template.placeholders` and replaces by `placeholder.element_id`.

### Finding 2: The loader is already the right interception point

**Evidence:** `src/thucthengay/config/service.py:271`, `src/thucthengay/export/template_loader.py:74`, `src/thucthengay/config/service.py:278`

**Detail:** `load_project_config()` resolves each target template path, `load_target_template()` reads the actual PPTX slide, and then stores derived `template_metadata` into `target.metadata`.

### Finding 3: The current PPTX exposes multiple matching signals

**Evidence:** direct PPTX inventory command on `examples/templates/target_001.template.pptx`

**Detail:** Shapes include IDs 65-68; shape names such as `Picture 2`, `TextBox 6`, `Rectangle 13`, `TextBox 1`; text such as `NAME, TIME`, `time`, `comment`; and strong geometry differences between the map image and small logo.

## Deduced Conclusions

### Deduction 1: Runtime auto-resolve can be added without changing export replacement mechanics

**Based on:** Findings 1 and 2.

**Reasoning:** Export consumes `target.metadata["template_metadata"]`, and config load already builds that metadata from the PPTX. If the loader resolves placeholder selectors into current IDs, export can continue to use `element_id`.

**Conclusion:** Add resolution before metadata creation; keep low-level slide copy/replacement unchanged.

### Deduction 2: ID-only matching should become a cache, not the source of truth

**Based on:** Findings 1 and 3.

**Reasoning:** Raw IDs are volatile across template edits. Shape name, alt text/description, marker text, type, geometry, and image size provide a richer fingerprint. A resolver can use those to find the current shape and then emit the current ID.

**Conclusion:** Preserve `element_id` for backward compatibility and diagnostics, but add a stable selector/fingerprint contract.

## Hypothesized Paths

### Hypothesis 1: Stable PowerPoint shape names/alt text can be the highest-confidence selector

**Status:** Open

**Theory:** If templates name shapes `ttn:map_image`, `ttn:title`, `ttn:time`, `ttn:comment` in Selection Pane or Alt Text, matching becomes deterministic.

**Supporting indicators:** `python-pptx` exposes `shape.name`; lxml access can read XML non-visual properties for description/title if needed.

**Would confirm:** Tests creating PPTX shapes with assigned names/alt text and validating resolver output after inserting/deleting other shapes.

**Would refute:** PowerPoint workflows used by the team routinely strip/reset both name and alt text.

### Hypothesis 2: Geometry/text fallback can safely repair current templates

**Status:** Open

**Theory:** Current templates can be matched with map = largest picture/shape near known map-frame aspect/area, text = exact text marker or field name.

**Supporting indicators:** Current PPTX has a large map picture and small logo; text boxes contain `time` and `comment`.

**Would confirm:** Inventory of all real target templates shows the same distinguishable structure.

**Would refute:** Multiple large image placeholders or repeated text markers create ambiguous candidates.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| Inventory of all real PPTX templates | Determines whether geometry/text fallback is safe globally | Run analyzer over every configured `template_pptx_file` |
| Team's template editing workflow | Determines whether shape names/alt text are preserved | Edit sample template in the normal workflow and compare extracted inventory |
| Preferred UX | Determines whether loader should auto-repair silently, warn, or require user approval | Decide product behavior for high-confidence and ambiguous matches |

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Error origin | Missing ID currently surfaces from `load_target_template()` and export preflight. |
| Trigger | User changes PPTX template so configured `element_id` no longer exists or points to the wrong shape. |
| Condition | `TemplatePlaceholder` has no stable selector/fingerprint, only `element_id`. |
| Related files | `models/template.py`, `export/template_loader.py`, `config/service.py`, `export/pptx_exporter.py`, `export/final_render.py`, `tests/unit/test_config_service.py`, `tests/unit/test_pptx_exporter.py` |

## Conclusion

**Confidence:** Medium-High

The best solution is feasible: add automatic placeholder resolution during template loading. The resolver should extract a shape inventory from PPTX, match each configured placeholder by stable selector/fingerprint, produce current `element_id`s in derived `TemplateMetadata`, and block only when confidence is low or ambiguous.

## Recommended Next Steps

### Fix direction

1. Add `export/template_analyzer.py` to extract slide shape inventory: ID, name, type, text, geometry, z-order, group path, image pixel size, and XML alt text/description where available.
2. Extend `TemplatePlaceholder` with optional stable matching fields, while preserving old config:
   - `selector`: `{ "name": "ttn:map_image" }`
   - `selector`: `{ "alt_text": "ttn:map_image" }`
   - `selector`: `{ "text": "time" }`
   - optional geometry/image hints.
3. Make `element_id` optional in config or treat it as a cached prior ID. During load:
   - If ID exists and fingerprint still matches, use it.
   - If ID missing/stale and selector has one high-confidence candidate, update derived metadata.
   - If multiple candidates match, emit blocking issue with candidate list.
4. Add a `sync_template_placeholders(config_path)` command/service to optionally persist the newly resolved IDs back to `config.json`, while export can work from derived metadata without requiring manual edits.
5. Update templates/examples to use explicit markers: shape names or alt text like `ttn:map_image`, `ttn:title`, `ttn:time`, `ttn:comment`.

### Diagnostic

Run analyzer inventory on every configured PPTX and compare candidate scores for `map_image`, `title`, `time`, and `comment`.

## Reproduction Plan

1. Create a one-slide PPTX with markers and placeholder config.
2. Load config and assert the resolver finds IDs.
3. Insert/delete/reorder unrelated shapes so PowerPoint changes IDs.
4. Reload config and assert the resolver still maps fields to the intended shapes.
5. Add an ambiguous duplicate marker and assert a blocking issue is emitted.

## Side Findings

- Confirmed: architecture originally scoped this as MVP ID mapping; changing to selector-based resolution is a post-MVP reliability improvement, not a contradiction.
