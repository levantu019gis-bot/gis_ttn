# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


ROOT = Path.cwd().resolve()
SRC = ROOT / "src"
ONEFILE = os.environ.get("TTN_PYINSTALLER_ONEFILE", "").lower() in {"1", "true", "yes"}


def _add_tree(collection: list[tuple[str, str]], source: Path, destination: str) -> None:
    if source.exists():
        collection.append((str(source), destination))


def _add_conda_share(collection: list[tuple[str, str]], name: str) -> None:
    source = Path(sys.prefix) / "Library" / "share" / name
    _add_tree(collection, source, f"Library/share/{name}")


def _add_conda_dlls(collection: list[tuple[str, str]]) -> None:
    bin_dir = Path(sys.prefix) / "Library" / "bin"
    if not bin_dir.exists():
        return

    patterns = (
        "gdal*.dll",
        "geos*.dll",
        "proj*.dll",
        "sqlite*.dll",
        "spatialite*.dll",
        "tiff*.dll",
        "geotiff*.dll",
        "jpeg*.dll",
        "libjpeg*.dll",
        "png*.dll",
        "zlib*.dll",
        "zstd*.dll",
        "lzma*.dll",
        "expat*.dll",
        "curl*.dll",
        "iconv*.dll",
        "webp*.dll",
        "xml2*.dll",
    )
    seen: set[Path] = set()
    for pattern in patterns:
        for dll in bin_dir.glob(pattern):
            if dll not in seen:
                collection.append((str(dll), "."))
                seen.add(dll)


datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []

_add_tree(datas, ROOT / "fonts", "fonts")
_add_conda_share(datas, "proj")
_add_conda_share(datas, "gdal")

for package in ("rasterio", "pyproj", "shapely"):
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)
    hiddenimports += collect_submodules(package)

_add_conda_dlls(binaries)

a = Analysis(
    [str(SRC / "thucthengay" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "scripts" / "pyinstaller" / "rthook_thucthengay_gis.py")],
    excludes=["tkinter", "unittest", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="ThucTheNgay",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ThucTheNgay",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="ThucTheNgay",
    )
