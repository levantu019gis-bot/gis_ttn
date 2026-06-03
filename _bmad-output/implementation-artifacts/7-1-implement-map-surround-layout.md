# Story 7.1: Implement Map Surround Layout

Status: done

## Story

As an Operator,
I want preview and final map output to use the same map-surround structure as the PPTX template,
So that exported map images align visually with the intended report design.

## Acceptance Criteria

1. Given a valid render spec, when `render_map()` returns, then the canvas dimensions still equal the requested output size and include a white surround, coordinate frame, inner raster panel, and DMS labels.
2. Given partial raster coverage, when rendering completes, then uncovered inner-map pixels use the configured background while surround pixels remain white.
3. Given GIS Editor displays a completed render, when the pixmap is shown, then it displays the full map-surround image without adding a duplicate overlay frame.

## Implementation Evidence

- Detailed implementation artifact: `_bmad-output/implementation-artifacts/spec-map-surround-layout.md`.
- Primary code: `src/thucthengay/render/frame.py`, `src/thucthengay/render/core.py`, `src/thucthengay/render/raster.py`, `src/thucthengay/editor/widgets/gis_canvas.py`.
- Primary tests: `tests/unit/test_render_frame.py`, `tests/unit/test_render_core.py`, `tests/unit/test_review_edit_mode.py`.

## Current State Notes

- Completed as a post-MVP hardening story after Epic 6.
- Full-suite verification has known unrelated blockers documented in the linked spec.

## Change Log

- 2026-06-03: Recast completed post-MVP spec into BMAD Epic 7 story structure.
