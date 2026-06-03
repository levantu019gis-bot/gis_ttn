# Current BMAD Development State - 2026-06-03

## Summary

The project is in BMad implementation phase. Epics 1-6 are complete according to their original MVP scope. Epic 7 has been opened to represent post-MVP hardening and distribution-readiness work that was implemented after the initial report export epic.

## Epic Status

| Epic | Status | Evidence |
| --- | --- | --- |
| Epic 1: Project Setup, Schemas, and Workspace Foundation | done | `models/`, `config/`, `workspace/`, launchers, pytest/ruff config |
| Epic 2: Data Ingestion to Composition Workspace | done | `ingestion/`, `jobs/ingestion_job.py`, ingestion unit tests |
| Epic 3: Review/Edit Workstation Core | done | `editor/modes/review_edit_mode.py`, tree/layer/canvas/widgets tests |
| Epic 4: Validation, Warnings, and Metadata Correction | done | `validation/`, warnings panel, metadata editor, readiness tests |
| Epic 5: Rendering Pipeline and Map Output Fidelity | done | `render/`, `jobs/render_job.py`, render/final/alignment tests |
| Epic 6: Report Export and Completion Evidence | done | `export/`, PPTX/TXT/log/final render/export mode tests |
| Epic 7: Post-MVP Hardening and Distribution Readiness | in-progress | Stories 7.1-7.3 done; Story 7.4 awaits Windows executable verification |

## Post-MVP Story Status

| Story | Status | Notes |
| --- | --- | --- |
| 7.1 Implement Map Surround Layout | done | Full map-surround render structure implemented and documented in `spec-map-surround-layout.md`. |
| 7.2 Expose Frame Render Defaults in Config | done | Frame constants moved into `defaults.grid.style` with render fallbacks. |
| 7.3 Auto-Resolve PPTX Placeholders from Shape Metadata | done | Template loader resolves stale ids from selectors/shape names before export. |
| 7.4 Package Windows Executable Tooling | review | Tooling exists; actual Windows `.exe` build and packaged smoke are still pending. |

## Current As-Built Notes

- Runtime config still supports direct `export.template_pptx_file` per target.
- PPTX export replacement uses resolved `element_id`; stable selectors and shape names repair volatile ids during config/template load.
- Preferred PPTX shape naming convention is `ttn:<field>`, for example `ttn:map_image`, `ttn:title`, `ttn:time`, and `ttn:comment`.
- `sort_order` controls enabled target ordering after config load; export slide order is driven by composition `review_order`.
- Windows packaging is prepared through PyInstaller scripts, but must be run on Windows because PyInstaller cannot cross-compile a Windows `.exe` from Linux.

## Verification Snapshot

- Latest focused checks for post-MVP specs are recorded in their spec artifacts.
- `python -m thucthengay --smoke` passes in the current conda workflow.
- Known historical full-suite blockers remain documented in `spec-configurable-frame-defaults.md`: full `ruff check .` has an unrelated `test_render_alignment.py` lint issue, and full `pytest` has a native abort in an export-mode test.

## Updated Artifacts

- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/epics.md`
- `_bmad-output/planning-artifacts/architecture.md`
- `_bmad-output/implementation-artifacts/7-1-implement-map-surround-layout.md`
- `_bmad-output/implementation-artifacts/7-2-expose-frame-render-defaults-in-config.md`
- `_bmad-output/implementation-artifacts/7-3-auto-resolve-pptx-placeholders-from-shape-metadata.md`
- `_bmad-output/implementation-artifacts/7-4-package-windows-executable-tooling.md`
