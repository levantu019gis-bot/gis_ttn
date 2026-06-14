"""SQLite-backed raster metadata cache for satellite downloads."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType

from pyproj import CRS

from thucthengay.download.models import DownloadRasterMetadata
from thucthengay.download.service import SatelliteDownloadConfigError


class RasterMetadataCache:
    """Persist raster CRS/bounds keyed by source path, size and mtime."""

    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(cache_path)
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS raster_metadata (
                    path TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    crs_wkt TEXT NOT NULL,
                    left REAL NOT NULL,
                    bottom REAL NOT NULL,
                    right REAL NOT NULL,
                    top REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        except (OSError, sqlite3.Error) as error:
            raise SatelliteDownloadConfigError(
                f"Khong mo duoc metadata cache {cache_path}: {error}",
                field_name="output_dir",
            ) from error

    def __enter__(self) -> RasterMetadataCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close(commit=exc_type is None)

    def get(self, path: Path, *, size: int, mtime_ns: int) -> DownloadRasterMetadata | None:
        """Return cached metadata only when file identity still matches."""

        try:
            row = self.connection.execute(
                """
                SELECT size, mtime_ns, crs_wkt, left, bottom, right, top
                FROM raster_metadata
                WHERE path = ?
                """,
                (str(path),),
            ).fetchone()
        except sqlite3.Error as error:
            raise SatelliteDownloadConfigError(
                f"Khong doc duoc metadata cache {self.cache_path}: {error}",
                field_name="output_dir",
            ) from error

        if row is None:
            return None
        cached_size, cached_mtime_ns, crs_wkt, left, bottom, right, top = row
        if cached_size != size or cached_mtime_ns != mtime_ns:
            return None

        try:
            crs = CRS.from_wkt(crs_wkt)
        except Exception:
            self.delete(path)
            return None
        return DownloadRasterMetadata(
            crs=str(crs),
            bounds=(float(left), float(bottom), float(right), float(top)),
        )

    def put(
        self,
        path: Path,
        *,
        size: int,
        mtime_ns: int,
        metadata: DownloadRasterMetadata,
    ) -> None:
        """Store metadata after a successful raster read."""

        left, bottom, right, top = metadata.bounds
        try:
            crs_wkt = CRS.from_user_input(metadata.crs).to_wkt()
            self.connection.execute(
                """
                INSERT OR REPLACE INTO raster_metadata (
                    path, size, mtime_ns, crs_wkt, left, bottom, right, top, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(path),
                    size,
                    mtime_ns,
                    crs_wkt,
                    left,
                    bottom,
                    right,
                    top,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        except sqlite3.Error as error:
            raise SatelliteDownloadConfigError(
                f"Khong ghi duoc metadata cache {self.cache_path}: {error}",
                field_name="output_dir",
            ) from error

    def delete(self, path: Path) -> None:
        """Remove one stale or invalid cache row."""

        try:
            self.connection.execute(
                "DELETE FROM raster_metadata WHERE path = ?",
                (str(path),),
            )
        except sqlite3.Error as error:
            raise SatelliteDownloadConfigError(
                f"Khong cap nhat duoc metadata cache {self.cache_path}: {error}",
                field_name="output_dir",
            ) from error

    def close(self, *, commit: bool = True) -> None:
        """Close the SQLite connection."""

        try:
            if commit:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()
