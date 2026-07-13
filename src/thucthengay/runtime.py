"""Runtime environment setup for GIS dependencies.

This module intentionally avoids importing rasterio, GDAL, or pyproj. It only
sets environment hints early enough that those libraries discover the intended
Conda/PyInstaller data directories instead of unrelated system installs.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_PROJ_DB_MINOR = 6


@dataclass(frozen=True)
class GisRuntimeStatus:
    """Resolved GIS runtime paths for diagnostics and tests."""

    proj_data: str | None
    proj_lib: str | None
    gdal_data: str | None
    path_prefixes: tuple[str, ...]


def initialize_gis_runtime() -> GisRuntimeStatus:
    """Initialize GDAL/PROJ environment variables when a trusted path is known."""

    path_prefixes = _prepend_runtime_path()
    proj_path = _select_proj_path()
    if proj_path is not None:
        _set_or_replace_gis_path("PROJ_DATA", proj_path, validator=_valid_proj_path)
        _set_or_replace_gis_path("PROJ_LIB", proj_path, validator=_valid_proj_path)

    gdal_path = _select_gdal_path()
    if gdal_path is not None:
        _set_or_replace_gis_path("GDAL_DATA", gdal_path, validator=lambda path: path.exists())

    return GisRuntimeStatus(
        proj_data=os.environ.get("PROJ_DATA"),
        proj_lib=os.environ.get("PROJ_LIB"),
        gdal_data=os.environ.get("GDAL_DATA"),
        path_prefixes=path_prefixes,
    )


def gis_runtime_diagnostics() -> dict[str, object]:
    """Return actionable runtime diagnostics without importing GIS libraries."""

    status = initialize_gis_runtime()
    proj_path = Path(status.proj_data) if status.proj_data else None
    return {
        "PROJ_DATA": status.proj_data,
        "PROJ_LIB": status.proj_lib,
        "GDAL_DATA": status.gdal_data,
        "proj_db_valid": bool(proj_path and _valid_proj_path(proj_path)),
        "path_prefixes": status.path_prefixes,
    }


def _prepend_runtime_path() -> tuple[str, ...]:
    prefixes = [
        Path(sys.prefix) / "Library" / "bin",
        _bundle_root(),
        _bundle_root() / "Library" / "bin",
    ]
    existing = os.environ.get("PATH", "")
    existing_parts = existing.split(os.pathsep) if existing else []
    to_prepend = [
        str(path)
        for path in prefixes
        if path.exists() and str(path) not in existing_parts
    ]
    if to_prepend:
        os.environ["PATH"] = os.pathsep.join([*to_prepend, existing])
    return tuple(to_prepend)


def _select_proj_path() -> Path | None:
    return _first_valid_path(_proj_candidates(), _valid_proj_path)


def _select_gdal_path() -> Path | None:
    return _first_valid_path(_gdal_candidates(), lambda path: path.exists())


def _proj_candidates() -> list[Path]:
    roots = _runtime_roots()
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            [
                root / "Library" / "share" / "proj",
                root / "share" / "proj",
                root / "pyproj" / "proj_dir" / "share" / "proj",
            ]
        )
    return _deduplicate(candidates)


def _gdal_candidates() -> list[Path]:
    roots = _runtime_roots()
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            [
                root / "Library" / "share" / "gdal",
                root / "share" / "gdal",
                root / "rasterio" / "gdal_data",
                root / "osgeo" / "data" / "gdal",
            ]
        )
    return _deduplicate(candidates)


def _runtime_roots() -> list[Path]:
    roots = [
        Path(os.environ["CONDA_PREFIX"]) if os.environ.get("CONDA_PREFIX") else None,
        Path(sys.prefix),
        _bundle_root(),
        Path(sys.executable).resolve().parent,
    ]
    return _deduplicate([root for root in roots if root is not None])


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()


def _set_or_replace_gis_path(
    name: str,
    selected: Path,
    *,
    validator,
) -> None:  # noqa: ANN001
    current = os.environ.get(name)
    if current:
        current_path = Path(current)
        if validator(current_path) and not _looks_like_external_postgis_path(current_path):
            return
    os.environ[name] = str(selected)


def _first_valid_path(paths: list[Path], validator) -> Path | None:  # noqa: ANN001
    for path in paths:
        if validator(path):
            return path
    return None


def _valid_proj_path(path: Path) -> bool:
    proj_db = path / "proj.db"
    if not proj_db.exists():
        return False
    if _looks_like_external_postgis_path(path):
        return False
    return _proj_db_minor_version(proj_db) >= MIN_PROJ_DB_MINOR


def _proj_db_minor_version(proj_db: Path) -> int:
    try:
        with sqlite3.connect(f"file:{proj_db}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = ?",
                ("DATABASE.LAYOUT.VERSION.MINOR",),
            ).fetchone()
    except sqlite3.Error:
        return -1
    if row is None:
        return -1
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return -1


def _looks_like_external_postgis_path(path: Path) -> bool:
    text = str(path).lower()
    return "postgresql" in text or "postgis" in text


def _deduplicate(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve()) if path.exists() else str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique
