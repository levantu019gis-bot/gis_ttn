# Story 12.3: Run Tile Decode Queue from Review/Edit Workers

Status: review

## Implementation Notes

- Review/Edit tile preview runs inside the existing `RenderWorker`, keeping decode off the UI thread.
- Missing tiles are scheduled through Epic 11 `TileScheduler.queue_missing`.
- Tile decode uses `decode_tile_job`, including cancellation checks and stale scheduler revision.
- Decode is synchronous within the worker for this story; the UI thread remains protected by the existing worker lifecycle.
- Added `TilePreviewWorker` for progressive tile preview frames. It emits `frameReady` after cached/decoded tile composition, then emits `finished` for the terminal frame.
- Progressive tile preview now supports both normal preview and temporal compare panes.

## Guardrail

If tile decode fails, the preview request falls back to the current full-frame renderer.

## Verification

- `pytest tests/unit/test_render_tile_preview.py`
- `pytest tests/unit/test_review_edit_mode.py::test_review_edit_applies_progressive_tile_preview_frame`
