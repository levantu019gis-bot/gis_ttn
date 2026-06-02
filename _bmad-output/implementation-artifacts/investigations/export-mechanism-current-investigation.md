# Investigation: Cơ chế export hiện tại

## Hand-off Brief

1. **What happened.** Người dùng yêu cầu kiểm tra cơ chế export đang triển khai; evidence cho thấy hiện có hai nhánh export riêng: xuất ảnh GIS Editor từ pixmap hiện tại và export headless final/PPTX/TXT/log.
2. **Where the case stands.** Kết luận đủ tự tin: service headless cho final/PPTX/TXT đã có, nhưng tab Export UI hiện chỉ preflight và chưa nối action xuất thật.
3. **What's needed next.** Nếu mục tiêu là xuất cuối từ UI, cần nối `ExportMode.export_button` tới pipeline `ensure_final_renders_for_export -> export_combined_pptx -> export_txt_report -> write_export_summary_and_trace_log`.

## Case Info

| Field | Value |
| --- | --- |
| Ticket | N/A |
| Date opened | 2026-06-02 |
| Status | Concluded |
| System | PySide6 desktop app, conda env `ttn-env` |
| Evidence sources | Source code, unit tests, root `config.json` load result |

## Problem Statement

Kiểm tra cơ chế export đang được triển khai, đặc biệt trong bối cảnh GIS Editor và yêu cầu ảnh nhẹ `.jpg` DPI 200.

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| `src/thucthengay/editor/widgets/gis_canvas.py` | Available | GIS Editor image export uses `_rendered_pixmap`, JPEG, DPI 200. |
| `src/thucthengay/editor/modes/review_edit_mode.py` | Available | Review/Edit export button selects `.jpg` path and calls canvas export. |
| `src/thucthengay/render/final.py` | Available | Final render writes `.jpg`, 200 DPI, quality 90, atomic replace, render log. |
| `src/thucthengay/export/final_render.py` | Available | Export final render spec uses template-derived output size and currentness checks. |
| `src/thucthengay/export/pptx_exporter.py` | Available | Headless PPTX exporter exists and replaces map image placeholders. |
| `src/thucthengay/export/txt_exporter.py` | Available | Headless TXT exporter exists and validates placeholders. |
| `src/thucthengay/editor/modes/export_mode.py` | Available | UI currently preflight-only; final export button disabled. |
| Unit tests | Available | Focused export/review suite: 57 passed. |

## Confirmed Findings

### Finding 1: GIS Editor export saves only rendered map pixmap, not full editor scene

**Evidence:** `src/thucthengay/editor/widgets/gis_canvas.py:116`

**Detail:** `export_displayed_image()` returns false if `_rendered_pixmap` is missing, converts that pixmap to RGB, sets 200 DPI via dots-per-meter, and saves as JPG quality 90. This bypasses `_displayed_image()` and does not render the QGraphicsScene chrome.

### Finding 2: Review/Edit export path is `.jpg` under workspace renders by default

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:1127`, `src/thucthengay/editor/modes/review_edit_mode.py:1148`

**Detail:** `_export_canvas_image()` calls `gis_canvas.export_displayed_image()`. Default path is `workspace/renders/{composition_id}.gis-editor.jpg`; file dialog filter accepts `.jpg/.jpeg` and appends `.jpg` when suffix is different.

### Finding 3: GIS canvas render request uses final template size, not viewport size

**Evidence:** `src/thucthengay/editor/modes/review_edit_mode.py:657`

**Detail:** `_request_canvas_render()` calls `final_render_output_size(context.template_metadata)` and passes those dimensions to `build_render_spec()`. For root `config.json`, direct config load returned `ok=True`, 70 metadata entries, and unique output size `(3306, 2340)`.

### Finding 4: Final render export now writes JPEG at 200 DPI and verifies currentness by hash, size, and DPI

**Evidence:** `src/thucthengay/render/final.py:46`, `src/thucthengay/render/final.py:254`, `src/thucthengay/render/final.py:305`

**Detail:** `render_final_png()` is still named for compatibility, but writes final JPEG paths as `renders/{composition_id}.{hash}.jpg`. It saves with `dpi=(200, 200)`, `quality=90`, `optimize=True`, `subsampling=0`; currentness rejects stale output when spec hash, size, path, log, or DPI no longer match.

### Finding 5: Headless final export preparation exists and persists artifact paths

**Evidence:** `src/thucthengay/export/final_render.py:37`, `src/thucthengay/export/final_render.py:69`, `src/thucthengay/workspace/service.py:224`

**Detail:** `ensure_final_renders_for_export()` processes included compositions, builds canonical specs, skips current renders, renders missing/stale items, and records `final_render_path` plus `render_log_path` back into workspace JSON.

### Finding 6: PPTX/TXT export services exist, but Export tab UI does not call them yet

**Evidence:** `src/thucthengay/export/pptx_exporter.py:46`, `src/thucthengay/export/txt_exporter.py:22`, `src/thucthengay/editor/modes/export_mode.py:101`

**Detail:** `export_combined_pptx()` and `export_txt_report()` are implemented headless services. `ExportMode.run_preflight()` always disables the export button; when preflight passes it sets text saying final export is not implemented.

## Deduced Conclusions

### Deduction 1: Có hai loại export khác nhau đang cùng tồn tại

**Based on:** Findings 1, 2, 4, 5, 6

**Reasoning:** Review/Edit exports the current GIS canvas pixmap for inspection. Export services prepare final render artifacts and can build PPTX/TXT outputs, but the Export tab only exposes preflight.

**Conclusion:** Người dùng bấm “Xuất ảnh” trong GIS Editor sẽ nhận `.jpg` preview/final-size map image; người dùng bấm tab Export chưa thể xuất PPTX/TXT thật từ UI.

### Deduction 2: Output size 3306x2340 phụ thuộc vào config/template metadata, không hard-code trong export button

**Based on:** Finding 3

**Reasoning:** GIS canvas render and final render both derive size from `final_render_output_size()`. Với root `config.json`, metadata cho toàn bộ target resolve về `(3306, 2340)`.

**Conclusion:** Nếu app đang load đúng root `config.json`, ảnh GIS Editor export sau khi render xong phải là 3306x2340. Nếu load một config path không resolve template metadata, render/export canvas có thể không chạy hoặc không có pixmap mới.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | --- | --- |
| Chưa chạy thao tác GUI thật trong app | Không xác nhận được UX end-to-end bằng click thật | Mở app trong môi trường GUI và export một composition cụ thể |
| Chưa inspect file export thực tế mới nhất của người dùng | Không xác nhận được file ngoài workspace hiện đang sai/đúng size | Kiểm tra image metadata của file người dùng vừa export |

## Conclusion

**Confidence:** High

Cơ chế export hiện tại đã chuyển ảnh GIS Editor và final render sang JPEG 200 DPI. Luồng headless final/PPTX/TXT có đủ service và test pass, nhưng Export tab UI chưa thực hiện final export, chỉ preflight. Với root `config.json`, kích thước render/export được resolve là 3306x2340 cho 70 target.

## Recommended Next Steps

### Fix direction

Nếu cần xuất cuối từ UI: nối `ExportMode.export_button` với pipeline headless hiện có, tạo output paths trong `workspace/exports`, chạy final render nếu thiếu/stale, rồi xuất PPTX/TXT/log.

Nếu chỉ cần GIS Editor export: giữ cơ chế hiện tại nhưng nên disable nút “Xuất ảnh” khi `_rendered_pixmap` chưa sẵn sàng để tránh bấm ra thông báo “Không xuất được ảnh GIS editor.”

### Diagnostic

- Chạy root config: `load_project_config(Path("config.json"))` và kiểm tra `final_render_output_size()` trả `(3306, 2340)`.
- Sau khi export GIS Editor, mở file bằng Pillow kiểm tra `image.size == (3306, 2340)` và `round(dpi) == 200`.

## Reproduction Plan

1. Load app bằng root `config.json`.
2. Chọn composition không stale, có visible raster.
3. Chờ GIS canvas render xong.
4. Bấm “Xuất ảnh”.
5. Kiểm tra file `.jpg`: kích thước 3306x2340, DPI 200.

## Side Findings

- `examples/config.json` load trực tiếp trong repo trả `ok=False` và không có `template_metadata`; root `config.json` load `ok=True`. Đây có thể gây nhầm nếu chạy app với config ở sai vị trí.
- Focused test suite đã chạy: `pytest tests/unit/test_export_final_render.py tests/unit/test_pptx_exporter.py tests/unit/test_export_preflight_plan.py tests/unit/test_export_mode.py tests/unit/test_review_edit_mode.py -q` trả 57 passed.

## Follow-up: 2026-06-02

### New Evidence

- Chạy preflight bằng root `config.json` và `WorkspaceService("examples/w1")` trả 27 rows, 54 errors: `export.final_render_missing` 27 lần và `export.txt_placeholder_unknown` 27 lần.
- Row đầu tiên `DaBac__20260526` có đúng 2 issue: thiếu final render và `TXT template dung placeholder chua ho tro: capture_time`.

### Additional Findings

1. `export.final_render_missing` xuất hiện vì các included composition trong `examples/w1/compositions/*.json` đang có `artifacts.final_render_path = null` và `artifacts.render_log_path = null`. Preflight chỉ kiểm tra currentness, không tự render final.
2. `export.txt_placeholder_unknown` xuất hiện vì root `config.json` dùng `txt_line_template = "{target_alias} {capture_date} {capture_time}"`, trong khi `SUPPORTED_TXT_FIELDS` chỉ hỗ trợ `time_label`, không hỗ trợ `capture_time`.

### Updated Conclusion

Hai issue lặp lại là hành vi đúng theo code hiện tại, không phải lỗi hiển thị của bảng Preflight. Nguyên nhân là pipeline export thật chưa được nối vào UI để tạo final render trước/sau preflight, và cấu hình TXT đang dùng placeholder chưa nằm trong contract hiện có.
