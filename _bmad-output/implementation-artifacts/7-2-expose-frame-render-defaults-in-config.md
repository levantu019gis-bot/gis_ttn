# Story 7.2: Expose Frame Render Defaults in Config

Status: done

## Story

As an Operator,
I want frame layout and label defaults visible in `config.json`,
So that render defaults can be reviewed and tuned without editing private Python constants.

## Acceptance Criteria

1. Given `config.json` has `defaults.grid.style`, when target grid style is resolved, then frame defaults are available to the render pipeline.
2. Given target-level style overrides are present, when config models normalize targets, then target style overrides merge over default style values.
3. Given a minimal config omits frame style values, when rendering resolves frame settings, then safe fallback defaults preserve existing behavior.

## Implementation Evidence

- Detailed implementation artifact: `_bmad-output/implementation-artifacts/spec-configurable-frame-defaults.md`.
- Primary code: `src/thucthengay/models/config.py`, `src/thucthengay/render/frame.py`, `src/thucthengay/render/core.py`.
- Primary tests: `tests/unit/test_render_frame.py`, `tests/unit/test_render_core.py`.

## Current State Notes

- Completed as a post-MVP hardening story.
- `config.json` now carries frame defaults under `defaults.grid.style`.

## Change Log

- 2026-06-03: Recast completed post-MVP spec into BMAD Epic 7 story structure.
