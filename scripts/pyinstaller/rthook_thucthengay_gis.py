"""Runtime environment hints for the packaged GIS stack."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _set_if_missing(name: str, paths: list[Path]) -> None:
    if os.environ.get(name):
        return
    path = _first_existing(paths)
    if path is not None:
        os.environ[name] = str(path)


def _prepend_path(paths: list[Path]) -> None:
    existing = os.environ.get("PATH", "")
    prefix = [str(path) for path in paths if path.exists()]
    if prefix:
        os.environ["PATH"] = os.pathsep.join([*prefix, existing])


root = _bundle_root()

_prepend_path([root, root / "Library" / "bin"])

proj_candidates = [
    root / "Library" / "share" / "proj",
    root / "pyproj" / "proj_dir" / "share" / "proj",
    root / "share" / "proj",
]
_set_if_missing("PROJ_DATA", proj_candidates)
_set_if_missing("PROJ_LIB", proj_candidates)

_set_if_missing(
    "GDAL_DATA",
    [
        root / "Library" / "share" / "gdal",
        root / "rasterio" / "gdal_data",
        root / "osgeo" / "data" / "gdal",
        root / "share" / "gdal",
    ],
)
