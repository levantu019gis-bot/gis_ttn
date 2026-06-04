# Investigation: PPTX time placeholder rectangle does not fit replaced text

## Hand-off Brief

1. **What happened.** User reported that the `time` element in the PPTX template did not expand after the app replaced it with a longer time string.
2. **Where the case stands.** Root cause confirmed in export code: text replacement preserved runs but did not set PowerPoint text-frame auto-fit behavior.
3. **What's needed next.** Rebuild/export again with the patched source; time placeholders now set `SHAPE_TO_FIT_TEXT` and disable wrapping.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-04 |
| Status | Concluded, fix verified |
| System | PowerPoint export path |
| Evidence sources | `pptx_exporter.py`, `pptx_slide_copy.py`, focused PPTX export tests |

## Problem Statement

After export replaces the `time` placeholder text in a rectangle shape, the rectangle remains at its original template size instead of resizing to fit the replacement text.

## Confirmed Findings

### Finding 1: Text replacement did not configure auto-fit

**Evidence:** `replace_text()` in `src/thucthengay/export/pptx_slide_copy.py` only cleared existing runs and wrote replacement text.

**Detail:** The function did not set `shape.text_frame.auto_size`, so the resulting PPTX preserved the template's original text-frame sizing behavior.

### Finding 2: Time value can be longer than template token

**Evidence:** `config.json` uses `defaults.export.time_format` = `HH.mm/dd.MM.yy`, so `{time}` resolves to values such as `08.30/25.05.26`.

**Detail:** The replacement string is materially longer than the template placeholder text `time`, so fixed-size rectangles can clip or wrap.

## Conclusion

**Confidence:** High

The app needed to explicitly set PowerPoint auto-fit behavior after replacing the time placeholder.

## Fix Applied

- `src/thucthengay/export/pptx_slide_copy.py`: `replace_text()` now accepts `fit_shape_to_text` and sets `MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT` plus `word_wrap=False` when requested.
- `src/thucthengay/export/pptx_exporter.py`: only `time` and `time_label` placeholders request shape-to-fit behavior.
- `tests/unit/test_pptx_exporter.py`: adds a rectangle-shaped time placeholder regression test.

## Verification Results

| Check | Result |
| --- | --- |
| `conda run -n ttn-env python -m pytest tests\unit\test_pptx_exporter.py` | Passed |
| `conda run -n ttn-env ruff check src\thucthengay\export\pptx_slide_copy.py src\thucthengay\export\pptx_exporter.py tests\unit\test_pptx_exporter.py` | Passed |
