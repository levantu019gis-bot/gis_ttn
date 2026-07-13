"""Runtime environment hints for the packaged GIS stack."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import sqlite3


MIN_PROJ_DB_MINOR = 6


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _set_if_missing(name: str, paths: list[Path]) -> None:
    current = os.environ.get(name)
    if current and _valid_existing_path(name, Path(current)):
        return
    path = _first_existing(paths)
    if path is not None:
        os.environ[name] = str(path)


def _valid_existing_path(name: str, path: Path) -> bool:
    if not path.exists():
        return False
    if name in {"PROJ_DATA", "PROJ_LIB"}:
        return _valid_proj_path(path)
    return True


def _valid_proj_path(path: Path) -> bool:
    text = str(path).lower()
    if "postgresql" in text or "postgis" in text:
        return False
    proj_db = path / "proj.db"
    if not proj_db.exists():
        return False
    try:
        with sqlite3.connect(f"file:{proj_db}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = ?",
                ("DATABASE.LAYOUT.VERSION.MINOR",),
            ).fetchone()
    except sqlite3.Error:
        return False
    try:
        return row is not None and int(row[0]) >= MIN_PROJ_DB_MINOR
    except (TypeError, ValueError):
        return False


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
