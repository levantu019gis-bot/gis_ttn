# Lộ trình Refactor Render Pipeline — Chi tiết từng bước

## Nguyên tắc chỉ đạo

Toàn bộ lộ trình xoay quanh một mục tiêu duy nhất: **tách "dữ liệu đã decode theo không gian" ra khỏi "khung hình hiện tại"**, để pan/zoom không bao giờ phải tính toán lại thứ đã tính rồi. Làm đúng thứ tự dưới đây — không nhảy cóc sang GPU/OpenGL trước khi Tile Cache ổn định, vì sẽ tối ưu nhầm chỗ.

---

## Giai đoạn 0 — Chẩn đoán trước khi sửa (1-2 ngày)

Trước khi viết code mới, xác nhận nguyên nhân bằng dữ liệu thật:

1. Chạy `gdalinfo` trên vài GeoTIFF đang dùng, kiểm tra có mục `Overviews` không. Nếu không có → đây có thể là nguyên nhân đơn lẻ lớn nhất, cần xử lý trước tiên.
2. Đo thời gian thực tế của từng bước trong pipeline khi pan (dùng `time.perf_counter()` quanh: window read, resample, QImage convert, QPixmap convert, paint event). Ghi log ra file, không đoán.
3. Đếm số lần `rasterio.read()` được gọi trong 1 giây pan liên tục, và so sánh với số vùng thực sự mới lộ ra (để định lượng mức độ "tính lại không cần thiết").

Kết quả bước này quyết định bạn nên bắt đầu ở Giai đoạn 1 hay 2 trước — nếu thiếu overview thì làm Giai đoạn 1 trước, nếu đã có overview đầy đủ thì Giai đoạn 2 mang lại ROI cao hơn ngay.

---

## Giai đoạn 1 — Pyramid / COG (ROI cao nhất, làm trước) — 3-5 ngày

**Việc cần làm:**

1. Viết script batch chuyển toàn bộ GeoTIFF hiện có sang COG bằng `gdal_translate` với driver COG, hoặc nếu không muốn convert file gốc thì tạo external overview bằng `gdaladdo`.
2. Số level overview: tính theo `ceil(log2(max(width, height) / 256))`. Ví dụ ảnh 20000x20000px → cần khoảng 7 level.
3. Resampling method cho overview: `average` cho ảnh liên tục (quang học), `nearest` cho ảnh phân loại/categorical.
4. Sửa code render: trước khi gọi `rasterio.windows.from_bounds()`, tính tỷ lệ `screen_px / map_units` hiện tại, chọn overview level gần nhất bằng cách so sánh với `dataset.overviews(band_index)`, rồi đọc trực tiếp từ level đó thay vì luôn đọc từ band gốc.
5. Cập nhật metadata cache (SQLite) hiện có để lưu thêm danh sách overview level có sẵn cho mỗi file, tránh phải mở lại dataset để hỏi GDAL mỗi lần.

**Kết quả kỳ vọng:** giảm 70-80% CPU khi zoom out, vì không còn resample từ full-res mỗi lần.

---

## Giai đoạn 2 — Tile Index & Tile Cache (cốt lõi của toàn bộ refactor) — 2-3 tuần

Đây là phần quan trọng nhất, cần thiết kế cẩn thận.

### 2.1 Tile Index

- Định nghĩa lưới tile cố định trong không gian bản đồ (không phụ thuộc viewport), tương tự chuẩn XYZ/TMS: `tile_size = 256px`, mỗi tile có tọa độ `(zoom_level, col, row)`.
- Với dữ liệu raster gốc theo CRS tùy ý (không phải Web Mercator), vẫn có thể dùng lưới nội bộ riêng theo CRS gốc thay vì ép về EPSG:3857 — miễn là lưới đó **cố định qua các frame**, không tính lại theo viewport.
- Viết class `TileIndex` chịu trách nhiệm: cho viewport + zoom level hiện tại → trả về danh sách `(col, row)` cần hiển thị.

### 2.2 Tile Cache

- Thay thế hoàn toàn `FrameOverlayCache` và `FullMapCache` bằng một cache duy nhất, key = `(file_hash, level, col, row)`, value = `QImage` hoặc `numpy array` đã decode.
- Dùng `OrderedDict` hoặc `functools.lru_cache` kiểu tùy biến làm LRU, giới hạn theo số lượng tile hoặc theo dung lượng RAM (ví dụ tối đa 500MB cache).
- **Quan trọng:** cache này KHÔNG invalid khi pan/zoom, chỉ invalid khi file signature đổi (cách bạn đang làm cho RasterBaseCache là đúng, chỉ cần áp dụng logic đó cho từng tile riêng thay vì cho cả frame).

### 2.3 Tile Scheduler

- Khi viewport thay đổi (pan/zoom), Scheduler tính danh sách tile cần hiển thị qua Tile Index.
- Với mỗi tile: nếu đã có trong Tile Cache → dùng ngay, không decode lại. Nếu chưa có → đẩy vào hàng đợi decode.
- Ưu tiên tile gần trung tâm viewport trước, tile ở rìa sau (giống cách QGIS và hầu hết tile-based renderer làm).
- Hủy các tile trong hàng đợi mà không còn nằm trong viewport hiện tại (tái sử dụng `RenderRequestToken` bạn đã có, áp dụng ở cấp độ tile thay vì cấp độ frame).

### 2.4 Decode Queue

- Dùng lại `QThread`/`RenderWorker` hiện có, nhưng đơn vị công việc giờ là **một tile**, không phải toàn viewport.
- Mỗi worker: đọc window tương ứng tile bằng `rasterio.windows.from_bounds()` (từ overview level đã chọn ở Giai đoạn 1), resample, convert sang QImage, đẩy vào Tile Cache, emit signal báo tile sẵn sàng.
- Vì tile độc lập với nhau, có thể decode song song nhiều tile cùng lúc bằng thread pool, không bị chặn bởi tile chậm nhất.

### 2.5 Compositor (thay thế phần vẽ hiện tại)

- Khi paint event xảy ra: lấy danh sách tile cần từ Scheduler, với mỗi tile có trong cache thì vẽ trực tiếp lên canvas tại đúng vị trí tính từ viewport hiện tại.
- Tile chưa decode xong: vẽ tạm bằng tile ở zoom level thấp hơn (đã có sẵn) phóng to tạm thời, hoặc để trống, rồi vẽ đè lên khi decode xong (đây chính là progressive rendering tự nhiên có được từ kiến trúc tile).
- Khi pan: không xóa canvas rồi vẽ lại từ đầu — chỉ dịch chuyển hệ tọa độ vẽ theo delta pan, các tile cũ vẫn ở nguyên cache, chỉ vị trí vẽ trên canvas thay đổi.

**Kết quả kỳ vọng:** giảm 60-70% CPU khi pan, tăng 3-5 lần tốc độ phản hồi vì phần lớn tile được tái sử dụng từ cache thay vì decode lại.

---

## Giai đoạn 3 — Partial Repaint thực sự — 1 tuần

Sau khi có Tile Cache, bổ sung tối ưu vẽ:

1. Giữ lại `QPixmap` của frame trước làm buffer.
2. Khi pan với delta nhỏ: `QPainter.drawPixmap()` dịch pixmap cũ theo offset, chỉ vẽ dải tile mới lộ ra ở mép (không vẽ lại toàn bộ viewport).
3. Chỉ trigger full recomposite khi zoom level đổi hoặc delta pan vượt quá một ngưỡng (ví dụ pan quá nhanh làm lộ vùng quá lớn).

---

## Giai đoạn 4 — Đo lại và quyết định có cần GPU không — 3-5 ngày

Sau Giai đoạn 1-3, đo lại toàn bộ pipeline như Giai đoạn 0. Trong đa số trường hợp, đến đây tốc độ đã gần tương đương QGIS vì bottleneck chính (tính toán lại không cần thiết) đã được giải quyết.

Chỉ tiến hành chuyển sang `QOpenGLWidget` nếu:
- Đã đo và xác nhận bottleneck còn lại nằm ở bước upload QPixmap lên GPU (chi phí convert format lặp lại), không phải ở decode raster.
- Cần giữ nhiều trăm tile texture thường trực trên GPU để tránh convert lại mỗi frame.

Nếu chuyển: giữ nguyên toàn bộ Tile Cache/Scheduler ở Giai đoạn 2, chỉ thay lớp lưu trữ tile từ `QImage` sang `QOpenGLTexture`, và thay Compositor từ `QPainter` sang shader vẽ texture theo tọa độ tile.

---

## Giai đoạn 5 — Progressive/LOD refinement (tùy chọn, cải thiện UX chứ không giảm CPU) — 3-5 ngày

- Khi zoom nhanh hoặc pan nhanh, hiển thị ngay tile từ overview level thấp hơn (đã có trong cache) phóng to tạm, sau đó thay bằng tile độ phân giải đúng khi decode xong.
- Đây là bonus cuối cùng, không phải nơi tạo ra cải thiện hiệu năng lớn — chỉ làm sau khi 4 giai đoạn trên đã ổn định.

---

## Tổng thời gian & thứ tự ưu tiên tuyệt đối

| Giai đoạn | Thời gian | Bắt buộc? |
|---|---|---|
| 0. Chẩn đoán | 1-2 ngày | Có |
| 1. Pyramid/COG | 3-5 ngày | Có — làm trước tiên |
| 2. Tile Index/Cache/Scheduler | 2-3 tuần | Có — phần lõi |
| 3. Partial Repaint | 1 tuần | Có |
| 4. GPU (nếu cần) | 3-5 ngày | Tùy, đo trước khi quyết định |
| 5. Progressive/LOD | 3-5 ngày | Không bắt buộc |

**Không bỏ qua Giai đoạn 1 và 2** — đây là hai việc tạo ra 80% cải thiện. Giai đoạn 4 (GPU) chỉ nên làm sau cùng và chỉ khi dữ liệu đo được xác nhận cần thiết, tránh việc đầu tư công sức lớn vào OpenGL trong khi bottleneck thật vẫn còn ở tầng dữ liệu.