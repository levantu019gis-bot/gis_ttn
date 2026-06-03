# Investigation: Rotated Side Label Clipping

## Hand-off Brief

1. **What happened.** Left/right map-surround labels could lose bottom glyph pixels because the rotated text layer was sized from `textbbox` dimensions but drawn without compensating for the font bbox offset.
2. **Where the case stands.** Root cause is confirmed and fixed in `src/thucthengay/render/frame.py`.
3. **What's needed next.** Visually inspect a freshly rendered map output if pixel-perfect production appearance needs human approval.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-03 |
| Status | Concluded |
| System | Python/Pillow render path in conda env `ttn-env` |
| Evidence sources | User screenshot, `src/thucthengay/render/frame.py`, focused unit test |

## Problem Statement

User reported that labels on the left and right sides of the map frame do not display fully, with the lower pixel row of these rotated labels apparently hidden or missing.

## Confirmed Findings

### Finding 1: Rotated labels were rendered through a temporary RGBA layer

**Evidence:** `src/thucthengay/render/frame.py:556`

**Detail:** `_draw_rotated_text_with_halo` creates a text layer, draws text and halo into it, rotates that layer, then pastes the rotated result onto the map image.

### Finding 2: The temporary layer ignored the text bbox origin

**Evidence:** `src/thucthengay/render/frame.py:566`

**Detail:** Before the fix, layer size used `bbox[2] - bbox[0]` and `bbox[3] - bbox[1]`, but drawing used fixed origin `(2, 2)`. For Arial Bold size 72, `16°40'00"N` measured as `(0, 13, 372, 67)`, so drawing at y=2 put the ink bottom at 69 while the layer height was only 58.

## Conclusion

**Confidence:** High

The side labels were clipped before they were pasted onto the final canvas. The fix draws the label at `(padding - bbox[0], padding - bbox[1])` inside a padded layer, so positive font bbox offsets no longer push glyph pixels outside the temporary layer.

## Recommended Next Steps

### Fix direction

Already applied: compensate for font bbox offsets when drawing rotated label text, and add a regression test that captures the pre-rotation alpha layer to ensure ink stays within padding.

### Diagnostic

Verification commands run:

- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_render_frame.py -q`
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync ruff check src/thucthengay/render/frame.py tests/unit/test_render_frame.py`
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync python -m thucthengay --smoke`
