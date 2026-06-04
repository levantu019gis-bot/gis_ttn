# Hướng Dẫn Build File Cài Đặt Windows

Tài liệu này mô tả quy trình tạo file cài đặt `ThucTheNgay-Setup-<version>.exe` trên Windows. Dự án dùng hai lớp đóng gói:

1. PyInstaller tạo app runtime dạng thư mục tại `dist\ThucTheNgay\ThucTheNgay.exe`.
2. Inno Setup gói toàn bộ thư mục runtime đó thành một file installer `.exe`.

Cách này ổn định hơn `onefile` cho stack PySide6, rasterio, GDAL, pyproj và shapely vì các DLL/native data được giữ nguyên trong thư mục cài đặt.

## 1. Chuẩn Bị Máy Build

Yêu cầu máy build:

- Windows 10/11 64-bit.
- Anaconda hoặc Miniconda.
- Inno Setup 6, bản có `ISCC.exe`.
- Mã nguồn dự án đã checkout đầy đủ.

Khuyến nghị mở **Anaconda/Miniconda PowerShell Prompt** để conda có sẵn trong `PATH`.

Tạo hoặc cập nhật môi trường:

```powershell
conda env update -n ttn-env -f environment.yml
```

Nếu chưa có môi trường:

```powershell
conda env create -f environment.yml
```

Kiểm tra app chạy được từ source:

```powershell
.\run_windows.ps1
```

## 2. Build App Runtime Bằng PyInstaller

Lệnh build runtime:

```powershell
.\scripts\build_windows_exe.ps1
```

Output mặc định:

```text
dist\ThucTheNgay\ThucTheNgay.exe
```

Script sẽ chạy smoke check:

```powershell
dist\ThucTheNgay\ThucTheNgay.exe --smoke
```

Nếu cần build nhanh khi đang debug installer:

```powershell
.\scripts\build_windows_exe.ps1 -SkipSmoke
```

Không khuyến nghị dùng `-Mode onefile` cho bản phát hành chính thức vì GIS/native DLL thường ổn định hơn ở chế độ `onedir`.

## 3. Build File Installer `.exe`

Sau khi đã cài Inno Setup 6:

```powershell
.\scripts\build_windows_installer.ps1
```

Script này sẽ:

- Build lại app runtime ở chế độ `onedir`.
- Đọc version từ `pyproject.toml`.
- Tìm `ISCC.exe` trong `PATH` hoặc thư mục cài Inno Setup phổ biến.
- Tạo installer tại `dist\installer`.

Output:

```text
dist\installer\ThucTheNgay-Setup-0.1.0.exe
```

Các tùy chọn thường dùng:

```powershell
.\scripts\build_windows_installer.ps1 -SkipExeBuild
.\scripts\build_windows_installer.ps1 -AppVersion 0.1.1
.\scripts\build_windows_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
.\scripts\build_windows_installer.ps1 -InstallMissingPyInstaller
```

`-SkipExeBuild` chỉ nên dùng khi chắc chắn `dist\ThucTheNgay\ThucTheNgay.exe` đã được build từ source hiện tại.

## 4. Cấu Trúc Installer

File cấu hình installer nằm tại:

```text
scripts\installer\thucthengay_inno.iss
```

Installer sẽ cài vào:

```text
C:\Program Files\ThucTheNgay
```

Các shortcut được tạo:

- Start Menu: luôn tạo.
- Desktop: người dùng chọn trong wizard.

Installer chỉ đóng gói app runtime trong `dist\ThucTheNgay`. Không đóng gói `config.json`, workspace, ảnh đầu vào, cache hoặc output export vào `Program Files`.

Lý do: các dữ liệu này là dữ liệu dự án/người dùng, cần đặt ở thư mục có quyền ghi như `Documents`, ổ dữ liệu nội bộ hoặc thư mục dự án riêng. App sẽ lưu preferences ở `%APPDATA%\3.ThucTheNgay\preferences.json`.

## 5. Quy Ước Dữ Liệu Khi Chạy Bản Cài

Trên máy người dùng, nên tổ chức dữ liệu như sau:

```text
D:\ThucTheNgayProjects\ProjectA\
  config.json
  data\
    templates\
    geojson\
  imagery\
  workspace\
```

Trong `config.json`, ưu tiên path tương đối theo vị trí file config:

```json
{
  "export": {
    "template_pptx_file": "data/templates/target_001.template.pptx"
  }
}
```

Tránh đặt workspace hoặc config trong `C:\Program Files\ThucTheNgay` vì Windows có thể chặn ghi file nếu không chạy bằng quyền admin.

## 6. Checklist Kiểm Thử Trước Khi Gửi Installer

Chạy trên máy build:

```powershell
.\scripts\build_windows_installer.ps1
dist\ThucTheNgay\ThucTheNgay.exe --smoke
```

Sau đó kiểm thử trên một máy Windows sạch hoặc Windows Sandbox:

1. Chạy `dist\installer\ThucTheNgay-Setup-<version>.exe`.
2. Mở app từ Start Menu.
3. Chọn một `config.json` thật ở thư mục dự án người dùng.
4. Chọn thư mục ảnh và workspace nằm ngoài `Program Files`.
5. Chạy ingestion với dữ liệu nhỏ.
6. Mở lại app, kiểm tra recent project còn hoạt động.
7. Export thử PPTX/TXT nếu dữ liệu mẫu có đủ template.
8. Uninstall app, kiểm tra app bị gỡ khỏi Start Menu và thư mục cài đặt.

## 7. Xử Lý Lỗi Thường Gặp

### Không tìm thấy `conda`

Mở lại bằng **Anaconda/Miniconda PowerShell Prompt** hoặc thêm conda vào `PATH`.

### Không tìm thấy `ISCC.exe`

Cài Inno Setup 6, sau đó chạy:

```powershell
.\scripts\build_windows_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

### Smoke check lỗi GDAL/PROJ

Kiểm tra môi trường được tạo bằng `environment.yml` và build lại:

```powershell
conda env update -n ttn-env -f environment.yml
.\scripts\build_windows_exe.ps1
```

PyInstaller spec hiện đã đưa `Library\share\proj`, `Library\share\gdal` và các DLL GIS phổ biến vào bundle.

### App chạy được trên máy build nhưng lỗi trên máy khác

Ưu tiên kiểm tra:

- Có build bằng `onedir` không.
- Thư mục `dist\ThucTheNgay` có đầy đủ DLL và data folder không.
- Người dùng có đặt config/workspace ở thư mục có quyền ghi không.
- Antivirus có quarantine DLL hoặc file exe không.

## 8. Quy Trình Release Đề Xuất

1. Cập nhật version trong `pyproject.toml`.
2. Chạy test/ruff trên source.
3. Build installer trên Windows:

```powershell
.\scripts\build_windows_installer.ps1
```

4. Test installer trên Windows sạch.
5. Lưu file `dist\installer\ThucTheNgay-Setup-<version>.exe` làm artifact phát hành.

Không commit các thư mục `build`, `dist`, workspace, cache hoặc output export.
