"""Typed contracts for the satellite image download workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from thucthengay.models import Issue

DEFAULT_DOWNLOAD_EXTENSIONS = frozenset({".tif", ".tiff"})


@dataclass(frozen=True)
class DownloadFilenameFormatRule:
    """Filename metadata rule ported from the standalone download script."""

    raw_format: str
    name: str = "format_1"
    max_cloud_percent: float | None = None


@dataclass(frozen=True)
class DownloadImageFolder:
    """Resolved image source folder with a safe unique branch name."""

    name: str
    path: Path


@dataclass(frozen=True)
class DownloadGeoJsonArea:
    """Prepared AOI loaded from one explicit GeoJSON file."""

    name: str
    path: Path
    crs: str
    geometry: Any


@dataclass(frozen=True)
class DownloadRasterCandidate:
    """Source GeoTIFF candidate discovered under a selected image folder."""

    source_folder: DownloadImageFolder
    path: Path
    size: int | None = None
    mtime_ns: int | None = None


@dataclass(frozen=True)
class DownloadRasterMetadata:
    """Raster metadata needed for AOI intersection."""

    crs: str
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class DownloadImageMatch:
    """One scanned source image and all GeoJSON files it intersects."""

    source_folder: DownloadImageFolder
    path: Path
    raster: DownloadRasterMetadata
    matched_geojson_names: tuple[str, ...]
    matched_geojson_paths: tuple[Path, ...]


@dataclass(frozen=True)
class DownloadFilenameMetadata:
    """Metadata parsed from a source image filename."""

    matched_format: bool
    matched_format_name: str | None = None
    capture_datetime: datetime | None = None
    cloud_percent: float | None = None
    max_cloud_percent: float | None = None


@dataclass(frozen=True)
class PreparedDownloadImage:
    """Matched image accepted for later copy/manifest stages."""

    match: DownloadImageMatch
    metadata: DownloadFilenameMetadata


@dataclass(frozen=True)
class SkippedCloudDownloadImage:
    """Matched image skipped because parsed cloud percent exceeds the rule threshold."""

    match: DownloadImageMatch
    metadata: DownloadFilenameMetadata
    reason: str
    status: str = "skipped_cloud"


@dataclass(frozen=True)
class SkippedCloudDownloadCandidate:
    """Source image skipped by cloud metadata before raster scanning."""

    source_folder: DownloadImageFolder
    path: Path
    metadata: DownloadFilenameMetadata
    reason: str
    status: str = "skipped_cloud"


@dataclass(frozen=True)
class SkippedExistingDownloadImage:
    """Source image skipped before raster scanning because output already exists."""

    source_folder: DownloadImageFolder
    path: Path
    existing_path: Path
    metadata: DownloadFilenameMetadata
    reason: str
    status: str = "skipped_existing_name"


@dataclass(frozen=True)
class FailedDownloadImage:
    """One source image that could not be scanned safely."""

    source_folder: DownloadImageFolder
    path: Path
    error: str


@dataclass
class SatelliteDownloadRequest:
    """Raw operator request for a satellite image download run."""

    geojson_files: list[str | Path]
    image_folders: list[str | Path]
    output_dir: str | Path
    base_dir: str | Path | None = None
    extensions: list[str] = field(default_factory=lambda: sorted(DEFAULT_DOWNLOAD_EXTENSIONS))
    filename_formats: list[DownloadFilenameFormatRule] = field(default_factory=list)
    overwrite: bool = False
    dry_run: bool = False
    include_boundary_touch: bool = True
    preserve_source_tree: bool = True
    write_manifest: bool = True
    scan_workers: int = 4


@dataclass(frozen=True)
class ResolvedSatelliteDownloadRequest:
    """Validated request with absolute paths and normalized options."""

    geojson_files: tuple[Path, ...]
    image_folders: tuple[DownloadImageFolder, ...]
    output_dir: Path
    extensions: frozenset[str]
    filename_formats: tuple[DownloadFilenameFormatRule, ...]
    overwrite: bool
    dry_run: bool
    include_boundary_touch: bool
    preserve_source_tree: bool
    write_manifest: bool
    scan_workers: int = 4


@dataclass(frozen=True)
class DownloadStats:
    """Counters shared by download progress and result objects."""

    total_images: int = 0
    scanned_images: int = 0
    matched_images: int = 0
    downloaded_images: int = 0
    skipped_existing: int = 0
    skipped_cloud: int = 0
    failed_images: int = 0
    metadata_cache_hits: int = 0
    metadata_cache_misses: int = 0


@dataclass(frozen=True)
class SatelliteDownloadProgress:
    """Progress event shape for future download job adapters."""

    stage: str
    message: str
    stats: DownloadStats = field(default_factory=DownloadStats)
    current: int | None = None
    total: int | None = None
    current_source_folder: str | None = None
    current_geojson: str | None = None

    @property
    def percent(self) -> int | None:
        """Return rounded percent when current/total are known."""
        if self.current is None or self.total in (None, 0):
            return None
        return max(0, min(100, round((self.current / self.total) * 100)))


class DownloadRunStatus(StrEnum):
    """Terminal and active states for the download engine."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True)
class SatelliteDownloadResult:
    """Final outcome of a satellite image download run."""

    status: DownloadRunStatus
    stats: DownloadStats = field(default_factory=DownloadStats)
    output_dir: Path | None = None
    manifest_path: Path | None = None
    output_rows: tuple[DownloadManifestRow, ...] = ()
    issues: tuple[Issue, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class DownloadMatchResult:
    """Output of Story 10.2 matching before cloud filtering/copying."""

    matches: tuple[DownloadImageMatch, ...]
    failed_images: tuple[FailedDownloadImage, ...]
    stats: DownloadStats
    skipped_cloud_images: tuple[SkippedCloudDownloadCandidate, ...] = ()
    skipped_existing_images: tuple[SkippedExistingDownloadImage, ...] = ()


@dataclass(frozen=True)
class DownloadFilenameFilterResult:
    """Output of filename metadata parsing and cloud filtering before copy/manifest."""

    accepted_matches: tuple[PreparedDownloadImage, ...]
    skipped_cloud_images: tuple[SkippedCloudDownloadImage | SkippedCloudDownloadCandidate, ...]
    failed_images: tuple[FailedDownloadImage, ...]
    warnings: tuple[str, ...]
    stats: DownloadStats
    skipped_existing_images: tuple[SkippedExistingDownloadImage, ...] = ()


@dataclass(frozen=True)
class DownloadManifestRow:
    """One row written to the satellite download CSV manifest."""

    status: str
    source_folder: str
    source_path: Path
    destination_path: Path | None
    matched_geojson: str
    metadata: DownloadFilenameMetadata
    error: str = ""


@dataclass(frozen=True)
class DownloadOutputResult:
    """Output of copy/dry-run/manifest processing."""

    rows: tuple[DownloadManifestRow, ...]
    stats: DownloadStats
    output_dir: Path
    manifest_path: Path | None = None
    cancelled: bool = False
