# Story 13.5: Add History, Metadata, and Filename Management Tools

Status: done

## Story

As an Operator,
I want tools to inspect and repair history images, filename parsing, metadata, bands, and symbology,
So that data problems can be corrected before Review/Edit and export.

## Acceptance Criteria

1. Given historical registry is enabled, when the user opens management tools, then active historical images can be listed by target, date, source path, and status.
2. Given historical image paths moved, when the user previews and confirms a prefix repair, then affected records are updated transactionally.
3. Given filename patterns are configured, when a sample filename is tested, then the UI shows matched pattern, capture date/time, cloud percent, and unmatched reasons.
4. Given layers have multiple bands, when metadata is edited, then R/G/B/Alpha comboboxes and symbology settings remain discoverable and validated.
5. Given many layers require similar corrections, when batch metadata edits are applied, then changes are persisted safely and compositions are marked stale for revalidation.

## Tasks / Subtasks

- [x] Add a History Manager view or dialog for target image records and path repair.
- [x] Add filename pattern tester to Config or metadata tools.
- [x] Add batch metadata edit workflow for selected layers/compositions.
- [x] Ensure band/symbology controls use discovered raster band metadata.
- [x] Add tests for prefix repair, pattern tester, batch edit validation, and stale-state marking.

## Dev Notes

- Reuse `HistoryService.preview_path_prefix_replacement()` and `apply_path_prefix_replacement()`.
- Keep unmatched/outside-geometry imagery grouped distinctly.
- Batch edits must avoid silently overwriting unrelated fields.

## Verification

- History service tests
- Metadata editor tests
- Config filename pattern tests
- Workspace stale-state tests
