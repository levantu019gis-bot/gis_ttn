# Story 13.6: Improve Export Preflight, Template Resilience, and Partial Success

Status: done

## Story

As an Operator,
I want export to preflight template problems clearly and continue with valid slides,
So that one bad target/template does not hide usable output from other targets.

## Acceptance Criteria

1. Given targets use different normal/compare PPTX templates, when export preflight runs, then slide size, shape ids/selectors, required placeholders, and map image placeholders are validated per target/template.
2. Given one included composition has unresolved placeholders or invalid template mapping, when export runs, then only that slide is skipped and the output/log clearly reports the skipped reason.
3. Given all included compositions fail, when export runs, then no misleading empty PPTX is produced and the summary explains that no slide was exportable.
4. Given compare mode is enabled, when placeholders such as `time_label_pane_A` and `time_label_pane_B` are required, then preflight explains which data or mapping is missing before export begins.
5. Given templates contain many line/shape objects, when slides are copied/exported, then map-frame geometry, label positions, and shape sizes are preserved and verified.

## Tasks / Subtasks

- [x] Strengthen template metadata validation per target and compare mode.
- [x] Add slide-size compatibility diagnostics with target/template names.
- [x] Ensure PPTX/TXT/log summaries represent partial success accurately.
- [x] Add tests for one bad slide among valid slides, all slides failing, and compare placeholders missing.
- [x] Add regression checks for shape/frame geometry preservation.

## Dev Notes

- Preserve the current behavior that valid targets should export when possible.
- Do not weaken required-placeholder validation; make failure scoped per composition.
- This story should integrate with existing export log and issue summary structures.

## Verification

- Export preflight tests
- PPTX exporter tests
- Export pipeline partial-success tests
