# Story 7.3: Auto-Resolve PPTX Placeholders from Shape Metadata

Status: done

## Story

As an Operator,
I want the app to recover template placeholder mappings when PowerPoint changes shape ids,
So that changing a PPTX template does not require manually repairing every target config id.

## Acceptance Criteria

1. Given config contains stale element ids and PPTX shapes are named `ttn:<field>`, when project config loads, then derived template metadata resolves placeholders to current PPTX element ids.
2. Given an explicit placeholder selector is configured, when project config loads, then selector matching is attempted before conventional `ttn:<field>` matching.
3. Given two shapes match the same required placeholder, when config loads, then the loader emits a blocking ambiguity issue instead of guessing.
4. Given a legacy template still has valid configured ids, when no stable selector/name match exists, then configured ids remain supported.

## Implementation Evidence

- Detailed implementation artifact: `_bmad-output/implementation-artifacts/spec-pptx-placeholder-auto-match.md`.
- Primary code: `src/thucthengay/export/template_analyzer.py`, `src/thucthengay/export/template_loader.py`, `src/thucthengay/models/template.py`, `src/thucthengay/export/pptx_exporter.py`, `src/thucthengay/export/final_render.py`.
- Primary tests: `tests/unit/test_models.py`, `tests/unit/test_config_service.py`, `tests/unit/test_pptx_exporter.py`, `tests/unit/test_export_final_render.py`.

## Current State Notes

- Completed as a post-MVP export hardening story.
- Replacement still happens by resolved PPTX element id; stable names/selectors are used to repair volatile ids during config/template load.

## Change Log

- 2026-06-03: Recast completed post-MVP spec into BMAD Epic 7 story structure.
