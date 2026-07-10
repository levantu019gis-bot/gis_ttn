# Story 12.6: Measure Tile Preview Performance and Decide Progressive/GPU Next Steps

Status: review

## Implementation Notes

- Added diagnostics buckets for tile preview layout, coverage, queue, decode, and compose.
- Added counters for visible tiles, decode jobs, used/missing tiles, partial repaint, and full recompose.
- Added tile cache hit/miss reporting under the `tile_preview` cache name.
- Added progressive UI update path: Review/Edit applies intermediate tile frames via `frameReady` before the terminal `finished` result.
- Added compare-pane diagnostics counters for tile coverage per pane.
- GPU remains out of scope. No GPU path was added because diagnostics evidence should be gathered from real Review/Edit sessions first.

## Guardrail

Measurement hooks do not alter visual output. Progressive LOD and GPU remain follow-up decisions.
Progressive updates use the same render token guard as full-frame preview, so stale frames from older pan/zoom requests are rejected.

## Verification

- `pytest tests/unit/test_render_tile_preview.py`
- `pytest tests/unit/test_review_edit_mode.py::test_review_edit_applies_progressive_tile_preview_frame`
