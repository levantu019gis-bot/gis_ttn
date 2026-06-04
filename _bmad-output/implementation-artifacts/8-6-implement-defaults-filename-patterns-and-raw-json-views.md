---
title: 'Story 8.6: Implement Defaults, Filename Patterns, and Raw JSON Views'
type: 'feature'
created: '2026-06-04'
status: 'done'
baseline_commit: '0565df54a7cbf30f81e353e93cae1a1ecf5bf93d'
context:
  - '{project-root}/_bmad-output/project-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Epic 8 already has a Config tab, but its Defaults view exposes only a small subset of the shared config defaults. Operators still cannot inspect or edit key grid defaults required by the approved Config Manager design, especially label format, reference frame values, and advanced grid style values that affect map-surround rendering.

**Approach:** Extend the existing Config tab and `ConfigEditorService` paths in place so Story 8.6 covers the remaining Defaults requirements while preserving the current Filename Patterns and read-only Raw JSON behavior. Keep this scoped to draft config editing and UI refresh; do not alter render/export behavior.

## Boundaries & Constraints

**Always:** Keep config mutation behind `ConfigEditorService`; UI widgets must update the draft through service methods. Preserve read-only template/font picker behavior already implemented. User-facing labels/remediation stay Vietnamese where they are user-visible. Defaults edits must refresh status, summary, raw JSON, validation issues, and downstream cue consistently with existing Config tab behavior.

**Ask First:** Ask before changing config schema/model validation rules, adding bulk target default propagation actions, or introducing a live render preview for defaults.

**Never:** Do not make Raw JSON editable. Do not remove existing template/font asset-copy safeguards. Do not silently overwrite target-level `grid.interval` or target `grid.style` overrides when editing shared defaults. Do not revive removed bulk actions such as duplicate targets, renumber sort order, or move group.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Defaults load | Config draft has `defaults.grid.label_format`, `defaults.grid.style.reference_width`, `reference_height`, `reference_outer_frame`, `reference_frame_gap`, `max_frame_ticks_per_axis`, `epsilon`, and surround style values | Defaults tab shows these fields in grouped sections; Raw JSON remains read-only and mirrors the draft | Missing values show blank/default-safe UI text without crashing |
| Defaults edit | Operator edits shared default fields and clicks `Apply defaults` | Draft `defaults` updates only at the edited default paths; target-level `grid.interval` and target overrides remain untouched; validation/status/raw JSON refresh | Invalid typed values surface through existing validation issue flow |
| Filename pattern test | Operator enters sample filename and clicks pattern test | Existing UTC filename + 7 giờ result remains visible with parsed date, time, and cloud percent | If patterns are invalid, result fields remain empty instead of crashing |
| Raw JSON view | Draft changes through Defaults or Filename Patterns | Raw JSON view updates and remains non-editable | N/A |

</frozen-after-approval>

## Code Map

- `src/thucthengay/editor/modes/config_mode.py` -- Config tab UI; owns Defaults/Patterns/Raw JSON widgets and refresh/apply flows.
- `src/thucthengay/config/editor_service.py` -- Draft config service; already supports dotted `update_defaults`, filename pattern updates, font import, raw JSON, and validation.
- `src/thucthengay/models/config.py` -- Config schema and project-default merge behavior; should not need schema changes for existing `style: dict`.
- `tests/unit/test_ui_config_mode.py` -- Isolated Qt smoke test covering Config tab UI behavior.
- `tests/unit/test_config_editor_service.py` -- Service tests for draft updates, filename parsing, and asset import behavior.
- `_bmad-output/planning-artifacts/config-manager-tab-design.md` -- Approved Config Manager design details for Defaults fields.

## Tasks & Acceptance

**Execution:**
- [x] `src/thucthengay/editor/modes/config_mode.py` -- Expand `_build_defaults_tab` field specs into grouped sections for Default Grid, Frame Reference, Advanced Grid Style, and Export Defaults -- satisfies Story 8.6 field coverage without changing service boundaries.
- [x] `src/thucthengay/editor/modes/config_mode.py` -- Add concise helper/summary text that distinguishes shared defaults from per-target grid interval/style overrides -- prevents operators from assuming defaults edits rewrite target-specific settings.
- [x] `src/thucthengay/editor/modes/config_mode.py` -- Ensure `_apply_defaults` keeps existing scalar parsing and refreshes downstream cue/status/raw JSON/issues consistently after defaults changes -- preserves current draft workflow.
- [x] `tests/unit/test_ui_config_mode.py` -- Update Config tab smoke assertions so required Defaults fields are present, editable where appropriate, and font path remains Browse-managed/read-only -- locks the new UI contract.
- [x] `tests/unit/test_config_editor_service.py` -- Add or adjust focused service coverage for `update_defaults` on label format/reference/advanced style fields and confirm target grid overrides remain untouched -- verifies service-level behavior independent of Qt.

**Acceptance Criteria:**
- Given the Config tab is open, when the Defaults tab renders, then it exposes shared grid label format/style fields, frame reference fields, advanced grid style fields, and export defaults from the Epic 8 design.
- Given a target has its own `grid.interval` or `grid.style`, when shared defaults are edited and applied, then only `defaults.*` changes and target overrides remain unchanged.
- Given a draft defaults value changes, when the Config tab refreshes, then summary/status, validation issues, and read-only Raw JSON reflect the draft.
- Given filename pattern testing and Raw JSON already work, when this story is complete, then both behaviors still pass their existing tests.

## Spec Change Log

## Design Notes

Keep the Defaults UI intentionally form-based for this story. The design artifact allows the default grid preview to be a summary in MVP, so a short explanatory label is sufficient and avoids adding renderer/UI coupling to Config mode.

## Verification

**Commands:**
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_config_editor_service.py tests/unit/test_ui_config_mode.py` -- expected: focused Config service/UI tests pass.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync ruff check src/thucthengay/editor/modes/config_mode.py src/thucthengay/config/editor_service.py tests/unit/test_config_editor_service.py tests/unit/test_ui_config_mode.py` -- expected: lint passes for touched files.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync python -m thucthengay --smoke` -- expected: application smoke passes.

## Suggested Review Order

**Defaults UI Contract**

- Start here: field coverage and policy text define the operator-facing behavior.
  [`config_mode.py:490`](../../src/thucthengay/editor/modes/config_mode.py#L490)

- Defaults refresh now formats list values for readable editing.
  [`config_mode.py:900`](../../src/thucthengay/editor/modes/config_mode.py#L900)

- Apply path updates only draft defaults and shows override-safe cue.
  [`config_mode.py:1154`](../../src/thucthengay/editor/modes/config_mode.py#L1154)

- List parsing supports frame rectangles and supported label formats.
  [`config_mode.py:1444`](../../src/thucthengay/editor/modes/config_mode.py#L1444)

**Verification**

- UI smoke locks required Defaults fields and read-only font picker behavior.
  [`test_ui_config_mode.py:48`](../../tests/unit/test_ui_config_mode.py#L48)

- Service test confirms target grid overrides survive defaults edits.
  [`test_config_editor_service.py:245`](../../tests/unit/test_config_editor_service.py#L245)

**BMAD Tracking**

- Epic 8 tracking is opened while Story 8.6 awaits independent review.
  [`sprint-status.yaml:98`](sprint-status.yaml#L98)
