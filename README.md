# 3.ThucTheNgay

Ứng dụng desktop Python/PySide6 hỗ trợ chuẩn bị dữ liệu ảnh vệ tinh, review bố cục và xuất báo cáo.

## 1. Các Thành Phần Chính

Dự án có các nhóm thành phần sau:

- `src/thucthengay`: mã nguồn chính của ứng dụng.
- `config.json`: file cấu hình mẫu ở root project.
- `data/config.json`: file cấu hình dữ liệu thật theo bố cục thư mục `data`.
- `environment.yml`: danh sách dependency để tạo môi trường conda.
- `run_windows.ps1`, `run_windows.bat`, `run_ubuntu.sh`: script chạy app từ source code.
- `scripts/build_windows_exe.ps1`: script tạo app `.exe` bằng PyInstaller.
- `scripts/build_windows_installer.ps1`: script tạo file cài đặt `.exe` bằng Inno Setup.
- `docs/windows-installer.md`: hướng dẫn build installer chi tiết hơn.

## 2. Yêu Cầu Môi Trường Development

Dự án dùng:

- Python `>=3.11,<3.12`.
- Conda environment tên mặc định là `ttn-env`.
- Dependency GIS/native như `gdal`, `rasterio`, `pyproj`, `shapely`.
- `uv` để chạy command trong môi trường project.

Khuyến nghị trên Windows: dùng **Anaconda Prompt** hoặc **Miniconda Prompt** để lệnh `conda` có sẵn.

## 3. Cài Môi Trường Development

Mở terminal tại thư mục project, ví dụ:

```powershell
cd D:\Working\3.ThucTheNgay
```

Nếu chưa có môi trường `ttn-env`, chạy:

```powershell
conda env create -f environment.yml
```

Nếu đã có môi trường và chỉ muốn cập nhật dependency:

```powershell
conda env update -n ttn-env -f environment.yml
```

## 4. Chạy Ứng Dụng Từ Source Code

### Windows PowerShell

```powershell
.\run_windows.ps1
```

### Windows Command Prompt

```bat
run_windows.bat
```

### Ubuntu/Linux

```bash
chmod +x ./run_ubuntu.sh
./run_ubuntu.sh
```

Các launcher trên mặc định dùng conda environment `ttn-env`. Nếu muốn dùng environment khác:

```powershell
$env:TTN_CONDA_ENV = "ten-env-khac"
.\run_windows.ps1
```

## 5. `PYTHONPATH=src` Là Gì?

`PYTHONPATH=src` không phải là phần mềm cần cài. Đây là biến môi trường cho Python biết nơi tìm mã nguồn của project.

Trong dự án này package chính nằm ở:

```text
src/thucthengay
```

Khi chạy:

```powershell
python -m thucthengay
```

Python cần tìm thấy package `thucthengay`. Vì package nằm trong thư mục `src`, ta đặt:

```text
PYTHONPATH=src
```

Nghĩa là: “Python hãy tìm package trong thư mục `src`”.

Thông thường bạn không cần tự set biến này vì các file launcher đã làm sẵn. Ví dụ `run_windows.ps1` sẽ set `PYTHONPATH=src` trước khi chạy app.

Nếu muốn chạy thủ công:

```powershell
$env:PYTHONPATH = "src"
conda run -n ttn-env python -m thucthengay
```

Với bản đã đóng gói thành `.exe`, người dùng cuối không cần `PYTHONPATH=src`, không cần Python và không cần conda.

## 6. Kiểm Tra Source Code

Trên Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
conda run -n ttn-env python -m pytest
conda run -n ttn-env ruff check .
conda run -n ttn-env python -m thucthengay --smoke
```

Trên Linux/macOS:

```bash
export PYTHONPATH=src
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv run --no-sync pytest
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv run --no-sync python -m thucthengay --smoke
```

Smoke check thành công sẽ in:

```text
3.ThucTheNgay app ready.
```

## 7. Tạo Config Từ Dữ Liệu GeoJSON

File config dữ liệu thật có thể được tạo từ một GeoJSON `Feature` cho mỗi target trong:

```text
webapp_geojson/output_geojson
```

Mỗi `properties.center` trong GeoJSON được đọc theo dạng `[lat, lon]` và ghi vào `coordinate` trong config theo dạng `[lon, lat]`. `properties` và `geometry` gốc được giữ trong `metadata`.

Ví dụ:

```powershell
conda run -n ttn-env python scripts\generate_template_metadata.py `
  examples\templates\target_001.template.pptx `
  --output examples\templates\target_001.template.json

conda run -n ttn-env python scripts\generate_config_from_geojson.py `
  webapp_geojson\output_geojson `
  --output config.json `
  --template-pptx examples\templates\target_001.template.pptx `
  --map-element-id 1026
```

`config.json` trỏ tới template PPTX thông qua trường `export.template_pptx_file`. Script `scripts/generate_template_metadata.py` chỉ dùng để soi thông tin shape id/text trong template; app không cần file JSON metadata này khi chạy.

## 8. Tạo File `.exe` Trên Windows

Có hai loại `.exe` cần phân biệt rõ:

- App runtime `.exe`: file chạy app trực tiếp, nằm trong thư mục `dist\ThucTheNgay`.
- Installer `.exe`: file cài đặt để gửi cho người dùng, nằm trong `dist\installer`.

Với người mới, nên tạo **installer `.exe`** vì dễ phát hành hơn.

### 8.1. Chuẩn Bị Trên Máy Build Windows

Cần cài:

1. Miniconda hoặc Anaconda.
2. Inno Setup 6 nếu muốn tạo installer.
3. Source code dự án này.

Mở **Anaconda/Miniconda PowerShell Prompt**, sau đó vào thư mục project:

```powershell
cd D:\Working\3.ThucTheNgay
```

Cập nhật môi trường:

```powershell
conda env update -n ttn-env -f environment.yml
```

Nếu máy chưa có env `ttn-env`:

```powershell
conda env create -f environment.yml
```

Kiểm tra app chạy được từ source:

```powershell
.\run_windows.ps1
```

### 8.2. Tạo App Runtime `.exe`

Chạy:

```powershell
.\scripts\build_windows_exe.ps1
```

Kết quả:

```text
dist\ThucTheNgay\ThucTheNgay.exe
```

Đây là dạng `onedir`: file `.exe` đi kèm nhiều DLL/file phụ trong cùng thư mục. Đây là lựa chọn ổn định nhất cho PySide6/GDAL/rasterio.

Không nên chỉ copy riêng `ThucTheNgay.exe` ra ngoài thư mục này, vì app có thể thiếu DLL hoặc data GIS.

Nếu cần thử dạng một file duy nhất:

```powershell
.\scripts\build_windows_exe.ps1 -Mode onefile
```

Nhưng bản phát hành chính thức nên ưu tiên `onedir`.

### 8.3. Tạo File Cài Đặt Installer `.exe`

Đảm bảo đã cài Inno Setup 6. Sau đó chạy:

```powershell
.\scripts\build_windows_installer.ps1
```

Script này sẽ tự:

1. Build app runtime bằng PyInstaller.
2. Đọc version từ `pyproject.toml`.
3. Tìm chương trình Inno Setup Compiler `ISCC.exe`.
4. Gói thư mục `dist\ThucTheNgay` thành installer.

Kết quả:

```text
dist\installer\ThucTheNgay-Setup-0.1.0.exe
```

Tên file có thể thay đổi theo version trong `pyproject.toml`.

Nếu Inno Setup không nằm trong `PATH`, chỉ rõ đường dẫn:

```powershell
.\scripts\build_windows_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

Nếu đã build `dist\ThucTheNgay` rồi và chỉ muốn build lại installer:

```powershell
.\scripts\build_windows_installer.ps1 -SkipExeBuild
```

### 8.4. Cài Thử Installer

Sau khi có file:

```text
dist\installer\ThucTheNgay-Setup-0.1.0.exe
```

Chạy file này trên Windows. Installer sẽ cài app vào:

```text
C:\Program Files\ThucTheNgay
```

Sau đó mở app từ Start Menu hoặc desktop shortcut nếu đã chọn tạo shortcut.

Lưu ý: không đặt `config.json`, workspace, ảnh đầu vào hoặc output export trong `C:\Program Files\ThucTheNgay`. Đây là thư mục cài phần mềm, thường không phù hợp để ghi dữ liệu người dùng.

Nên đặt dữ liệu dự án ở thư mục riêng, ví dụ:

```text
D:\ThucTheNgayProjects\ProjectA
  config.json
  data
  imagery
  workspace
```

### 8.5. Checklist Sau Khi Build Installer

Trước khi gửi file cài đặt cho người dùng:

1. Chạy `.\scripts\build_windows_installer.ps1`.
2. Kiểm tra tồn tại file `dist\installer\ThucTheNgay-Setup-<version>.exe`.
3. Cài thử trên máy Windows sạch hoặc Windows Sandbox.
4. Mở app từ Start Menu.
5. Chọn `config.json` thật.
6. Chọn thư mục ảnh và workspace nằm ngoài `Program Files`.
7. Chạy ingestion với dữ liệu nhỏ.
8. Thử export nếu có đủ dữ liệu/template.
9. Gỡ cài đặt để kiểm tra uninstall hoạt động.

Xem thêm tài liệu chi tiết tại:

```text
docs/windows-installer.md
```

## 9. Lỗi Thường Gặp Khi Build `.exe`

### Không tìm thấy `conda`

Hãy mở đúng **Anaconda/Miniconda PowerShell Prompt**. Nếu vẫn lỗi, cần thêm conda vào `PATH`.

### Không tìm thấy `ISCC.exe`

Cài Inno Setup 6 hoặc truyền đường dẫn thủ công:

```powershell
.\scripts\build_windows_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

### Lỗi GDAL/PROJ/rasterio khi chạy file `.exe`

Thường do môi trường build thiếu dependency native hoặc build sai mode. Hãy chạy lại:

```powershell
conda env update -n ttn-env -f environment.yml
.\scripts\build_windows_exe.ps1
```

Ưu tiên dùng output dạng thư mục:

```text
dist\ThucTheNgay
```

### App chạy trên máy build nhưng lỗi trên máy khác

Kiểm tra:

- Có gửi/cài bằng installer không.
- Có copy thiếu file trong thư mục `dist\ThucTheNgay` không.
- Antivirus có chặn file `.exe` hoặc DLL không.
- Dữ liệu người dùng có nằm trong thư mục có quyền ghi không.

## 10. Ghi Chú Về GDAL Và Conda

`rasterio` là lớp truy cập raster/GDAL chính của app. Với môi trường development, nên dùng `environment.yml` để conda-forge giải quyết đồng bộ các package native như GDAL, rasterio, pyproj và shapely.

Khi dùng conda environment, tránh để `uv sync` thay thế package native của conda-forge bằng wheel từ PyPI. Nếu cần cài package app vào env hiện tại:

```bash
conda env create -f environment.yml
conda activate ttn-env
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv pip install --no-deps -e .
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv run --no-sync pytest
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv run --no-sync python -m thucthengay
```

`uv pip install --no-deps -e .` chỉ cài package ứng dụng này. Conda vẫn chịu trách nhiệm chính cho GDAL, rasterio, pyproj, shapely, Pillow và python-pptx.
