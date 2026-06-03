# Investigation: Grid Save Config Update

## Hand-off Brief

1. **What happened.** Initially confirmed: bấm "Lưu Grid" chỉ lưu interval/scale vào composition workspace, chưa ghi trực tiếp vào `config.json`.
2. **Where the case stands.** Updated 2026-06-03: code đã đổi để cả "Lưu Grid" và Include/Validate đều chốt interval/scale vào đúng target trong `config.json`.
3. **What's needed next.** Không còn hành động bắt buộc; nếu đổi UX tiếp, cân nhắc tách thông báo thành công/thất bại rõ hơn theo từng bước.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-03 |
| Status | Concluded - Fixed |
| System | Local repo, conda env `ttn-env` |
| Evidence sources | Source code, unit tests |

## Problem Statement

Người dùng cần kiểm tra sau khi điều chỉnh Grid Interval và Scale của từng target rồi bấm "Lưu Grid", các giá trị đó đã được cập nhật đầy đủ và đúng target vào file config chưa.

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| `src/thucthengay/editor/modes/review_edit_mode.py` | Available | UI handlers for Save Grid and Include/Validate |
| `src/thucthengay/config/service.py` | Available | Function that writes target alignment defaults to config |
| `tests/unit/test_review_edit_mode.py` | Available | Tests for save-grid workspace behavior and include-to-config behavior |
| `tests/unit/test_config_service.py` | Available | Test for updating one target without touching another target |

## Confirmed Findings

### Finding 1: Original Save Grid wrote workspace composition, not config

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:1156`

**Detail:** `_save_grid_override()` parses grid and scale, then calls workspace methods `update_grid_override()` and `update_view_state()`. It does not call `update_target_alignment_defaults()`.

### Finding 2: Include/Validate writes reviewed interval/scale back to target config

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:557`

**Detail:** `_include_selected()` calls `_persist_included_target_alignment(updated)` only after validation passes and include transition succeeds.

### Finding 3: Config update is target-id scoped

**Evidence:** `src/thucthengay/config/service.py:157`

**Detail:** `update_target_alignment_defaults()` scans `targets`, selects the dict whose `id` equals `target_id`, then writes `scale` and `grid.interval` only to that target.

### Finding 4: Tests confirm both stages

**Evidence:** `tests/unit/test_review_edit_mode.py:1485`, `tests/unit/test_review_edit_mode.py:1766`, `tests/unit/test_config_service.py:443`

**Detail:** Tests verify "Lưu Grid" persists workspace override/scale; Include/Validate then persists `scale` and `grid.interval` to config; config service keeps other targets unchanged.

### Finding 5: Updated Save Grid now persists target config immediately

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:1185`

**Detail:** `_save_grid_override()` now calls `_persist_included_target_alignment(updated)` after workspace save succeeds, then refreshes UI and reports "Đã lưu grid và cập nhật config target."

### Finding 6: Updated Save Grid now requests canvas rerender

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:1196`

**Detail:** `_save_grid_override()` now calls `_request_canvas_render(updated)` after the detail panels and workspace tree refresh. This mirrors the pan/zoom path, which already requested a render after persisting the updated view.

## Conclusion

**Confidence:** High

Hiện trạng sau fix: bấm "Lưu Grid" cập nhật `grid_override`/`view.scale` trong workspace, ghi `scale` + `grid.interval` vào đúng target trong `config.json`, rồi yêu cầu GIS canvas render lại ngay. Include/Validate vẫn tiếp tục gọi cùng cơ chế ghi config, nên cả hai thao tác đều chốt thông tin target.

## Recommended Next Steps

### Fix direction

Done: bổ sung call `_persist_included_target_alignment()` vào sau `_save_grid_override()` thành công, kèm thông báo UI rõ rằng target config đã được cập nhật. Done: bổ sung `_request_canvas_render(updated)` để canvas tự render lại sau khi lưu grid.

### Diagnostic

Đã chạy targeted tests:

```bash
pytest tests/unit/test_config_service.py::test_update_target_alignment_defaults_persists_scale_and_grid_interval \
  tests/unit/test_review_edit_mode.py::test_review_edit_grid_controls_show_defaults_save_override_and_mark_stale \
  tests/unit/test_review_edit_mode.py::test_review_edit_grid_controls_reject_invalid_values_without_write \
  tests/unit/test_review_edit_mode.py::test_review_edit_include_persists_target_interval_and_scale_to_config -q
```

Kết quả: `4 passed`.
