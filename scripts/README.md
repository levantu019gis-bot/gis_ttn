# Scripts README

Huong dan nhanh cho cac script build/chay cong cu trong thu muc nay.

## Build Windows runtime app

Theo BMad architecture cua du an, app la local desktop runtime. Cach build uu tien la
`onedir` vi PySide6/GDAL/rasterio on dinh hon khi di kem DLL va GIS data trong
cung mot thu muc.

Output chinh:

```text
dist\ThucTheNgay\ThucTheNgay.exe
```

Thu muc can copy/phat hanh:

```text
dist\ThucTheNgay\
```

Khong copy rieng `ThucTheNgay.exe` ra ngoai thu muc nay, vi app co the thieu
DLL hoac data cua PySide6/GDAL/rasterio.

## Cach build bang CMD / Anaconda Prompt

Mo **Anaconda Prompt** hoac **Miniconda Prompt**, sau do chay:

```bat
cd /d D:\0.TU_KHONG_XOA\1.NCPT\1.TTN\1.Source_Code

conda env update -n ttn-env -f environment.yml

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows_exe.ps1 -Mode onedir -InstallMissingTools
```

Test runtime sau khi build:

```bat
dist\ThucTheNgay\ThucTheNgay.exe --smoke
dist\ThucTheNgay\ThucTheNgay.exe
```

## Cach build bang PowerShell

Mo **Anaconda/Miniconda PowerShell Prompt**, sau do chay:

```powershell
Set-Location 'D:\0.TU_KHONG_XOA\1.NCPT\1.TTN\1.Source_Code'

conda env update -n ttn-env -f environment.yml

.\scripts\build_windows_exe.ps1 -Mode onedir -InstallMissingTools
```

Neu PowerShell chan script, chay lenh nay trong terminal hien tai:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Hoac tu CMD/PowerShell goi truc tiep:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows_exe.ps1 -Mode onedir -InstallMissingTools
```

## Tuy chon build

Build nhanh, bo qua smoke test:

```powershell
.\scripts\build_windows_exe.ps1 -Mode onedir -SkipSmoke
```

Build bang conda env khac:

```powershell
.\scripts\build_windows_exe.ps1 -EnvName my-env -Mode onedir
```

Build single-file exe de thu nghiem:

```powershell
.\scripts\build_windows_exe.ps1 -Mode onefile -InstallMissingTools
```

Luu y: `onefile` khong phai lua chon phat hanh mac dinh cua du an nay. Nen dung
`onedir` cho runtime app chinh.

## Build installer

Neu muon tao file cai dat `.exe`, can cai **Inno Setup 6** truoc.

```powershell
.\scripts\build_windows_installer.ps1
```

Output installer:

```text
dist\installer\ThucTheNgay-Setup-<version>.exe
```

Neu da build runtime `dist\ThucTheNgay` roi va chi muon build lai installer:

```powershell
.\scripts\build_windows_installer.ps1 -SkipExeBuild
```

## Troubleshooting

### `conda was not found in PATH`

Mo dung **Anaconda Prompt** hoac **Miniconda Prompt**, hoac them Conda vao PATH.

Kiem tra:

```bat
where conda
conda env list
```

### Khong co env `ttn-env`

Tao env tu file cua du an:

```bat
cd /d D:\0.TU_KHONG_XOA\1.NCPT\1.TTN\1.Source_Code
conda env create -f environment.yml
```

Neu env da ton tai, cap nhat lai:

```bat
conda env update -n ttn-env -f environment.yml
```

### Loi PyInstaller chua cai

Dung `-InstallMissingTools` khi build:

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows_exe.ps1 -Mode onedir -InstallMissingTools
```

Hoac cai thu cong:

```bat
conda install -y -n ttn-env -c conda-forge pyinstaller
```

### Loi PowerShell execution policy

Dung cach goi co `-ExecutionPolicy Bypass`:

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows_exe.ps1 -Mode onedir -InstallMissingTools
```

### Loi lien quan GDAL/PROJ/rasterio khi chay exe

Build lai bang `onedir` va dam bao env da update:

```bat
conda env update -n ttn-env -f environment.yml
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows_exe.ps1 -Mode onedir -InstallMissingTools
```

Sau do test:

```bat
dist\ThucTheNgay\ThucTheNgay.exe --smoke
```

## File lien quan

- `build_windows_exe.ps1`: build runtime app bang PyInstaller.
- `build_windows_installer.ps1`: build installer bang Inno Setup.
- `pyinstaller\thucthengay_windows.spec`: cau hinh PyInstaller.
- `installer\thucthengay_inno.iss`: cau hinh Inno Setup.
- `..\docs\windows-installer.md`: huong dan build installer chi tiet hon.
- `..\_bmad-output\planning-artifacts\architecture.md`: quyet dinh BMad ve packaging/runtime.
