# Export Config Strategy Investigation

## Scope

Read `config.json` and current export code to define the intended export strategy.

## Confirmed Evidence

- `config.json` contains 70 targets and every target has an `export` block.
- Every target export block currently contains `template_pptx_file`, `template_txt_value`, `date_format`, `time_format`, and `placeholders`.
- Example target `DaBac` maps `map_image` to element id `1026`, title to element ids `7` and `2`, and time to element id `14`.
- `examples/templates/target_001.template.json` shows element id `1026` is a picture with embedded image size `3306x2340`.
- Current model code expects `txt_line_template` and placeholder `kind`; it rejects `template_txt_value`, `date_format`, `time_format`, and placeholder `value`.
- Loading the current root `config.json` through `load_project_config` returns `ok False` with 560 validation issues caused by that schema mismatch.

## Deduced Model

The source of truth for export should be `targets[].export` from root `config.json`.

Each included composition should:

1. Resolve its target.
2. Load that target's one-slide PPTX template.
3. Resolve final map image for the composition.
4. Replace the configured `map_image` element with that final image.
5. Replace each configured text/rectangle placeholder by `value` when present, otherwise by a field resolver.
6. Write one TXT line from `template_txt_value`.
7. Append the produced slide to the combined PPTX in review/export order.

## Key Strategy

- Extend config models to accept the real schema:
  - `template_txt_value`
  - `date_format`
  - `time_format`
  - placeholder `value`
  - inferred placeholder kind when `kind` is absent.
- Keep `txt_line_template` as a backward-compatible alias only, not the canonical field for root `config.json`.
- Add one shared export value resolver used by both PPTX and TXT.
- Implement format conversion for config tokens such as `dd.MM.yy` and `HH.mm/dd.MM.yy`.
- Preserve template geometry and only replace content by element id.
- Ensure final render exists before PPTX export, but do not change the target-template-per-slide export mechanism.

## Implementation Risk

The biggest risk is preserving formatting inside PowerPoint text shapes. Current `replace_text` assigns `shape.text`, which can collapse run-level formatting. If template formatting must be preserved, replacement should update paragraph/run text while retaining the existing text frame style.
