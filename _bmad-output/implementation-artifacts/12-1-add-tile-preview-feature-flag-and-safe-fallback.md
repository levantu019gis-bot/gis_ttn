# Story 12.1: Add Tile Preview Feature Flag and Safe Fallback

Status: review

## Implementation Notes

- Added `defaults.render_preview.tile_preview` config models with defaults disabled.
- Passed render preview config from `AppShell` into `ReviewEditMode`.
- Added Review/Edit routing so disabled config preserves the existing full-frame renderer.
- Added safe fallback: when tile preview is enabled but fails, Review/Edit falls back to `render_map_with_cache` unless `fallback_to_full_render` is explicitly false.
- Temporal compare currently stays on the full-frame renderer to preserve pane geometry until a dedicated compare-tile path is reviewed.

## Guardrail

The story does not change map-frame geometry, labels, gaps, or final export rendering.

## Verification

- `pytest tests/unit/test_config_service.py::test_load_project_config_applies_shared_defaults_with_target_overrides`
- `pytest tests/unit/test_review_edit_mode.py::test_review_edit_tile_preview_flag_falls_back_to_full_frame_renderer`
- `pytest tests/unit/test_review_edit_mode.py::test_review_edit_tile_preview_disabled_uses_full_frame_renderer`
