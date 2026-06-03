# Thiết Kế Chi Tiết Tab Config Manager

**Dự án:** 3.ThucTheNgay  
**Artifact liên quan:** `config-manager-ui-mockup.html`  
**Mục tiêu:** Mô tả chi tiết tab `Config` để giao diện hóa việc tạo, đọc, chỉnh sửa và kiểm tra `config.json`.

## 1. Vai Trò Của Tab Config

Tab `Config` là màn hình quản trị cấu hình dự án. Người dùng có thể mở file config, kiểm tra tính hợp lệ, chỉnh sửa target, group, default grid/export, filename patterns, import/export GeoJSON geometry và lưu lại cấu hình mà không cần thao tác trực tiếp với JSON thô.

Tab này nằm trong luồng chính của app:

`Setup | Config | Review/Edit | Export`

Vị trí này phản ánh đúng vai trò của config: là dữ liệu nền trước ingest/review/export, nhưng vẫn có thể được mở lại để sửa khi phát hiện lỗi cấu hình.

## 2. Nguyên Tắc Thiết Kế

- **Không bắt người dùng sửa JSON trực tiếp:** UI phải là đường chính; Raw JSON chỉ dùng để xem/kiểm tra nâng cao.
- **Config phải luôn có trạng thái rõ:** đang hợp lệ, có warning, có lỗi, hay có thay đổi chưa lưu.
- **Target là đơn vị chỉnh sửa chính:** bảng target ở giữa, inspector bên phải hiển thị target đang chọn.
- **Group là đơn vị điều hướng:** cột trái giúp lọc target theo nhóm nghiệp vụ.
- **Action nguy hiểm phải có xác nhận:** xóa target, ghi đè config, import geometry thay thế geometry hiện có.
- **UI không tự làm source of truth:** khi triển khai PySide, UI gọi service thuộc module `config/`; UI không đọc/ghi JSON trực tiếp.

## 3. Cấu Trúc Tổng Thể

Màn hình được chia thành 5 vùng:

1. **Top App Tabs:** hiển thị các tab chính của app.
2. **Config Toolbar:** mở, reload, backup, lưu, lưu thành, tìm kiếm, validate.
3. **Summary Stats:** thống kê nhanh trạng thái config.
4. **Main Workspace:** gồm group sidebar, workarea trung tâm và target inspector bên phải.
5. **Validation Issues:** panel lỗi/cảnh báo phía dưới.

Layout desktop mặc định:

- Cột trái `Groups`: khoảng 260 px.
- Vùng giữa `Workarea`: co giãn chính.
- Cột phải `Target Inspector`: khoảng 360 px.
- Panel dưới `Validation Issues`: chiều cao khoảng 168 px.

Trên viewport nhỏ, layout xếp dọc theo thứ tự: stats, groups, workarea, inspector, issues.

## 4. Config Toolbar

Toolbar nằm ngay dưới top tabs.

### 4.1. Actions

- `Mở config`: chọn file `.json` để load.
- `Tải lại`: reload file hiện tại từ disk.
- `Backup`: tạo bản sao backup của config hiện tại.
- `Lưu`: ghi thay đổi vào file config hiện tại.
- `Lưu thành`: lưu sang đường dẫn mới.
- `Validate`: chạy kiểm tra toàn bộ config.

### 4.2. Search

Ô search có placeholder:

`Tìm target, group, template, geometry`

Search lọc dữ liệu theo:

- `target.id`
- `target.name`
- `target.alias`
- `group.key`
- `group.title`
- `export.template_pptx_file`
- trạng thái geometry/template nếu có.

### 4.3. Status Pills

Toolbar hiển thị các pill trạng thái:

- `Có thay đổi chưa lưu`: xuất hiện khi form khác dữ liệu đã load.
- `Config hợp lệ`: trạng thái sau validate.
- Khi có lỗi blocking, pill đổi sang `Config lỗi`.
- Khi chỉ có warning, pill đổi sang `Có cảnh báo`.

## 5. Summary Stats

Vùng stats gồm các ô:

- `Targets`: tổng số target.
- `Enabled`: số target đang bật.
- `Groups`: số group có trong config.
- `Template PPTX`: số template PPTX duy nhất đang được dùng.
- `Geometry`: số target có `metadata.geojson_geometry`.
- `Warnings`: số cảnh báo hiện tại.

Stats phải cập nhật sau các thao tác:

- thêm/xóa target;
- bật/tắt target;
- đổi group;
- import geometry;
- validate config;
- sửa template/export/defaults.

## 6. Group Sidebar

Sidebar hiển thị danh sách group theo thứ tự nghiệp vụ.

Mỗi group row gồm:

- `group.title`
- `key <group.key>`
- số lượng target trong group

Các group hiện tại trong mockup:

- `1.1 - Không người Hoàng Sa`
- `1.2 - Không người Trường Sa`
- `2.1 - Có người Hoàng Sa`
- `2.2.1 - Có người Trường Sa TQ`
- `2.2.2 - Có người Trường Sa PLP`
- `2.2.3 - Có người Trường Sa Malaysia`
- `2.2.4 - Có người Trường Sa ĐL`
- `0 - Chưa phân nhóm`

### 6.1. Filter

Combobox filter gồm:

- `Tất cả target`
- `Enabled only`
- `Có cảnh báo`

### 6.2. Group Selection

Khi chọn group:

- row group được highlight;
- bảng target trung tâm lọc theo group đó;
- pill trong bảng hiển thị group đang chọn, ví dụ `Group 1.1`;
- nếu group không có target, bảng hiển thị empty state.

### 6.3. Thêm Group

Nút `+` ở header group sidebar dùng để thêm group mới.

Dialog thêm group cần các trường:

- `key`
- `title`

Validation:

- `key` không trùng group hiện có;
- `title` không rỗng;
- key dạng số phân cấp như `2.2.4` được ưu tiên, nhưng hệ thống vẫn có thể lưu dạng string.

## 7. Workarea Trung Tâm

Workarea có các tab con:

- `Targets`
- `Defaults`
- `Filename Patterns`
- `Raw JSON`

## 8. Tab Targets

Tab `Targets` là màn hình thao tác chính cho danh sách target.

### 8.1. Toolbar Của Targets

Hiện chỉ có một action:

- `Thêm target`

Các action đã loại bỏ khỏi thiết kế:

- `Nhân bản`
- `Đánh lại sort_order`
- `Di chuyển group`

Lý do: giảm nguy cơ thao tác hàng loạt nhầm; việc đổi group/sort order thực hiện trong inspector của từng target.

### 8.2. Bảng Target

Cột bảng:

- `Bật`: switch `enabled`.
- `Order`: `sort_order` trong phạm vi group.
- `ID`: `target.id`.
- `Tên hiển thị`: `target.name`.
- `Alias`: `target.alias`.
- `Scale`: hiển thị `1:<scale>`.
- `Grid`: tóm tắt `target.grid.interval`.
- `Status`: trạng thái validate của target.

### 8.3. Row Selection

Khi chọn một row:

- row được highlight;
- inspector bên phải cập nhật theo target;
- các action trong inspector áp dụng cho target đó;
- nếu target có issue, issue liên quan được highlight trong panel dưới.

### 8.4. Enabled Switch

Switch ở cột `Bật` chỉnh `target.enabled`.

Hành vi đề xuất:

- Bật/tắt trong bảng cập nhật dữ liệu nháp ngay.
- Nếu chuyển từ `true` sang `false`, hiển thị confirm nhẹ nếu target đang có composition trong workspace đang mở.
- Target disabled vẫn tồn tại trong config, nhưng không tham gia ingestion/review/export sau khi reload config.

### 8.5. Thêm Target

Nút `Thêm target` mở dialog hoặc tạo row nháp trong inspector.

Trường tối thiểu:

- `id`
- `name`
- `alias`
- `group.key`
- `sort_order`
- `coordinate`
- `scale`
- `grid.interval`
- `export.template_pptx_file`
- `export.template_txt_value`
- `metadata.geojson_geometry`

Sau khi tạo:

- target mới được chọn ngay;
- status là warning/error cho đến khi đủ geometry/template hợp lệ;
- `sort_order` mặc định là cuối group đang chọn.

## 9. Tab Defaults

Tab `Defaults` quản lý các giá trị dùng chung trong `defaults`.

### 9.1. Quản Lý Default Grid

Block `Quản lý Default Grid` gồm:

- `label_format`
- `supported_formats`
- `default_label_font`
- `frame_color`
- `label_color`
- `label_font_size`
- `tick_length_px`
- `reference_label_font_size`

Các field này tương ứng với `defaults.grid.label_format` và `defaults.grid.style`.

### 9.2. Grid Preview

Mockup có vùng `Default grid preview` để mô phỏng kết quả style. Khi triển khai thật, preview này có thể là:

- preview tĩnh bằng widget custom;
- hoặc chỉ là summary nếu chưa cần render preview.

Preview không cần giống final render tuyệt đối; mục tiêu là giúp người dùng nhận biết style đang chỉnh.

### 9.3. Target Grid Override Policy

Block này giải thích và điều khiển quan hệ giữa default grid và grid riêng của target.

Các dòng hiện tại:

- `target interval`: mỗi target vẫn có `grid.interval` riêng.
- `target style`: style target merge với `defaults.grid.style`.
- `save behavior`: chỉ ghi field khác default khi tối ưu config.
- `bulk action`: lựa chọn thao tác hàng loạt liên quan grid.

Ghi chú triển khai:

- Các field policy có thể là text/help trong MVP, không nhất thiết là editable data.
- Bulk action nên để sau MVP nếu muốn giảm rủi ro.

### 9.4. Frame Reference

Block `Frame Reference` gồm:

- `reference_width`
- `reference_height`
- `reference_outer_frame`
- `reference_frame_gap`

Đây là nhóm field kỹ thuật, ảnh hưởng trực tiếp tới khung bản đồ và layout surround.

### 9.5. Advanced Grid Style

Block `Advanced Grid Style` gồm:

- `max_frame_ticks`
- `epsilon`
- `surround_tick_length`
- `surround_stroke`

Các field nâng cao nên có tooltip hoặc mô tả ngắn trong app thật để tránh chỉnh nhầm.

### 9.6. Export Defaults

Block `Export Defaults` gồm:

- `date_format`
- `time_format`
- `map_background_color`

Các field này áp dụng cho target export nếu target không override.

## 10. Tab Filename Patterns

Tab này quản lý `filename_patterns`, dùng khi app trích xuất metadata từ tên ảnh.

### 10.1. Actions

- `Thêm pattern`
- `Kiểm tra pattern`

### 10.2. Bảng Pattern

Cột bảng:

- `Tên`
- `Pattern`
- `Separator`
- `Trích xuất`

Ví dụ:

- `PlanetScope PSScene`
- `PlanetScope simple`

### 10.3. Test Filename

Vùng `Test Filename` cho nhập tên file mẫu và xem kết quả:

- `filename`
- `capture_date`
- `capture_time`
- `cloud_percent`

Thiết kế hiển thị pill:

`UTC filename + 7 giờ`

Ý nghĩa: nếu ngày/giờ được lấy từ tên file, app cộng thêm 7 giờ để hiển thị giờ địa phương.

## 11. Tab Raw JSON

Tab `Raw JSON` dùng để xem cấu trúc JSON sau khi UI map dữ liệu.

Vai trò:

- kiểm tra nhanh field persisted;
- đối chiếu với config thật;
- hỗ trợ debug.

Khuyến nghị triển khai:

- MVP: read-only.
- Giai đoạn sau: có thể cho edit advanced, nhưng phải validate trước khi apply.

Raw JSON không nên là luồng chỉnh sửa chính.

## 12. Target Inspector

Inspector bên phải hiển thị và chỉnh target đang chọn.

Header gồm:

- tên target;
- id target;
- group title;
- trạng thái enabled;
- actions: `Xóa target`, `Reset`, `Apply`.

### 12.1. Actions

`Xóa target`

- Action nguy hiểm, dùng màu đỏ.
- Phải mở confirm dialog.
- Confirm cần nói rõ target id/name.
- Nếu workspace đang mở và có composition liên quan target này, cảnh báo rõ hậu quả: config mới sẽ không còn target để reload/review/export composition đó.
- Sau khi xóa, target biến mất khỏi bảng; stats và issue panel cập nhật.

`Reset`

- Khôi phục form inspector về dữ liệu target đã load hoặc dữ liệu sau lần Apply gần nhất.
- Không reload toàn bộ config.

`Apply`

- Ghi thay đổi trong inspector vào draft config trong bộ nhớ.
- Chưa ghi ra disk cho đến khi bấm `Lưu`.
- Chạy validate target cục bộ sau apply.

## 13. Inspector: Thông Tin

Các field:

- `id`
- `enabled`
- `group.key`
- `sort_order`
- `name`
- `alias`
- `coordinate`
- `scale`

Validation:

- `id` không rỗng, không trùng, nên dùng ASCII/ký tự an toàn vì được dùng trong composition id và tên file.
- `coordinate` đúng dạng `[lon, lat]`, lon trong `[-180, 180]`, lat trong `[-90, 90]`.
- `scale` là số nguyên dương.
- `sort_order` là số nguyên, nên duy nhất trong cùng group.
- `group.key` phải map được sang `group.title`; nếu key mới, cần cho nhập title hoặc tạo group trước.

## 14. Inspector: Grid

Mục `Grid` chỉnh `target.grid.interval`.

Các ô:

- `degrees`
- `minutes`
- `seconds`

Validation:

- tất cả không âm;
- `minutes` và `seconds` nhỏ hơn 60;
- ít nhất một trong ba giá trị lớn hơn 0.

Hiển thị trong bảng target:

- `1 phút`
- `3 phút`
- `30 giây`
- hoặc dạng tổng hợp nếu interval phức tạp.

## 15. Inspector: Export

Các field:

- `template`: `export.template_pptx_file`
- `TXT`: `export.template_txt_value`
- `date/time`: tóm tắt hoặc chỉnh `date_format` và `time_format`

Validation:

- `template` phải trỏ tới file PPTX một slide, resolve relative theo config file.
- `TXT` không rỗng nếu target cần export TXT.
- placeholder trong TXT phải thuộc tập hỗ trợ như `{time_label}`, `{capture_date}`, `{target_name}`, `{target_alias}`.

## 16. Inspector: Placeholders

Bảng `Placeholders` chỉ gồm:

- `field`
- `value`

Không còn cột `id`.

Các row mẫu:

- `map_image`
- `title`
- `time`
- `comment`

Cột `value` là editable input.

Ý nghĩa thiết kế:

- Người dùng chủ yếu cần sửa nội dung text cho `title`, `comment`, hoặc trạng thái/tín hiệu cho placeholder.
- `element_id` là chi tiết kỹ thuật nên không hiển thị ở thiết kế hiện tại.
- Mapping kỹ thuật có thể được app tự resolve từ shape name/selector của PPTX hoặc nằm ở luồng nâng cao khác.

Validation:

- `map_image` phải tồn tại và required.
- `title/comment` có thể chứa placeholder text hợp lệ.
- `time` có thể để `auto`.
- Nếu cần element id thật trong backend, UI không nhất thiết expose trực tiếp ở màn hình này.

## 17. Inspector: Geometry

Mục `Geometry` chỉ có hai nút:

- `Import GeoJSON`
- `Export GeoJSON`

Không có:

- khung preview geometry;
- nút copy geometry.

### 17.1. Import GeoJSON

Hành vi:

- mở file picker chọn `.geojson` hoặc `.json`;
- đọc geometry từ Feature hoặc FeatureCollection;
- nếu file có nhiều feature, cần yêu cầu người dùng chọn một feature hoặc báo không hỗ trợ trong MVP;
- ghi geometry vào `metadata.geojson_geometry` của target đang chọn;
- validate geometry ngay sau import.

Confirm:

- nếu target đã có geometry, hỏi xác nhận thay thế.

### 17.2. Export GeoJSON

Hành vi:

- xuất `metadata.geojson_geometry` của target đang chọn thành file GeoJSON;
- gợi ý tên file theo `target.id`;
- nếu target chưa có geometry, disable nút hoặc báo lỗi rõ.

## 18. Validation Issues Panel

Panel dưới cùng hiển thị các issue của config.

Mỗi row gồm:

- severity: `OK`, `WARN`, `ERROR`
- issue id
- message
- context/remediation

Ví dụ trong mockup:

- `group.unknown`: Group `2.2.4` chưa có target.
- `target.group.0`: 2 target đang ở nhóm chưa phân nhóm.
- `template.loaded`: PPTX template đã parse được placeholder cần thiết.

Tương tác:

- click issue target-related thì chọn target tương ứng;
- click issue group-related thì chọn group tương ứng;
- error blocking nên nổi bật hơn warning.

## 19. Trạng Thái Dữ Liệu

Tab Config cần phân biệt 3 lớp dữ liệu:

1. **Persisted config:** dữ liệu đang nằm trên disk.
2. **Draft config:** dữ liệu đã chỉnh trong UI nhưng chưa lưu.
3. **Validated config:** draft đã qua validate toàn bộ hoặc validate cục bộ.

Các trạng thái UI:

- Không có config: toolbar chỉ cho `Mở config` hoặc tạo mới nếu sau này bổ sung.
- Config loaded clean: không có thay đổi chưa lưu.
- Dirty draft: có pill `Có thay đổi chưa lưu`.
- Validated OK: `Config hợp lệ`.
- Warning: vẫn cho lưu nhưng hiển thị cảnh báo.
- Error: không cho ingest/reload downstream nếu lỗi blocking.

## 20. Save/Reload/Backup

### 20.1. Lưu

Khi bấm `Lưu`:

- validate draft;
- nếu có error blocking, hỏi xác nhận hoặc chặn lưu tùy loại lỗi;
- tạo backup nếu option backup tự động được bật;
- ghi JSON bằng atomic write;
- clear dirty state.

### 20.2. Lưu thành

Cho chọn đường dẫn mới.

Sau khi lưu thành công:

- session path cập nhật sang config mới;
- trạng thái dirty được clear.

### 20.3. Tải lại

Nếu có dirty draft:

- hỏi xác nhận bỏ thay đổi chưa lưu.

Sau khi reload:

- load lại từ disk;
- cập nhật stats, group list, target table, inspector và issues.

### 20.4. Backup

Tạo bản backup cùng thư mục hoặc thư mục người dùng chọn.

Tên gợi ý:

`config.backup.YYYYMMDD-HHMMSS.json`

## 21. Tác Động Tới Các Tab Khác

Sau khi lưu config:

- Nếu workspace đang mở, app nên cho người dùng reload config vào Review/Edit và Export.
- Nếu target bị tắt/xóa, composition đã có trong workspace có thể không còn target config tương ứng.
- Nếu sửa group/sort_order, cây Review/Edit cần reload để phản ánh thứ tự mới.
- Nếu sửa geometry hoặc enabled, người dùng nên chạy lại ingestion để dữ liệu match target đúng.
- Nếu sửa export/template/placeholders/defaults, preflight/export nên chạy lại.

## 22. Mapping Sang PySide

Các component gợi ý:

- App tab: dùng `QTabWidget` hiện có trong `AppShell`.
- Toolbar: `QHBoxLayout`, `QPushButton`, `QLineEdit`, status `QLabel`.
- Stats: các `QFrame`/`QLabel` nhỏ.
- Group sidebar: `QTreeView` hoặc `QListView`.
- Target table: `QTableView` với model riêng.
- Inspector: `QScrollArea` chứa form sections.
- Defaults/Patterns/Raw JSON: tab con bằng `QTabWidget` hoặc segmented buttons.
- Validation issues: `QTableView` hoặc custom list model.

Service đề xuất:

- `ConfigEditorService` trong `src/thucthengay/config/`
- UI gọi service để load, validate, mutate draft, save.
- Service chịu trách nhiệm atomic write, path resolve, import/export geometry, validation.

## 23. MVP Đề Xuất

MVP nên bao gồm:

- mở config;
- validate config;
- hiển thị stats;
- group sidebar;
- bảng target;
- inspector sửa thông tin target, grid, export, placeholder value;
- import/export GeoJSON;
- xóa target có confirm;
- lưu/lưu thành/backup;
- tab Defaults;
- tab Filename Patterns;
- Raw JSON read-only.

Chưa cần trong MVP:

- drag/drop sort;
- batch edit;
- preview geometry;
- edit Raw JSON trực tiếp;
- phân tích PPTX nâng cao ngay trong UI.

## 24. Tiêu Chí Chấp Nhận Thiết Kế

- Người dùng có thể hiểu config hiện có bao nhiêu target/group/warning ngay khi mở tab.
- Người dùng có thể chọn group và chỉnh target trong inspector mà không đọc JSON.
- Người dùng có thể sửa `name`, `alias`, `group.key`, `sort_order`, `coordinate`, `scale`, `grid.interval`, export TXT và placeholder value.
- Người dùng có thể import/export geometry bằng hai nút rõ ràng.
- Người dùng có thể xóa target từ inspector và được confirm trước khi xóa.
- Người dùng nhìn thấy lỗi/cảnh báo config trong panel dưới và biết item nào bị ảnh hưởng.
- Người dùng có thể lưu config an toàn, có backup và không mất thay đổi ngoài ý muốn.

