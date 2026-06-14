"""Recursive GeoTIFF scanner for ingestion input folders."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any

import rasterio
from rasterio.errors import RasterioIOError

from thucthengay.ingestion.metadata_parser import parse_business_metadata
from thucthengay.models import (
    FilenamePatternConfig,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    MetadataSource,
    MetadataStatus,
)

SUPPORTED_GEOTIFF_SUFFIXES = frozenset({".tif", ".tiff"})


@dataclass(frozen=True)
class RasterBounds:
    """Serializable raster bounds in the raster CRS."""

    left: float
    bottom: float
    right: float
    top: float


@dataclass(frozen=True)
class RasterMetadata:
    """Rasterio metadata required before target matching and rendering."""

    crs: str
    bounds: RasterBounds
    transform: tuple[float, ...]
    width: int
    height: int
    band_count: int
    nodata: float | int | None
    tags: dict[str, Any]


@dataclass(frozen=True)
class ScannedGeoTiff:
    """Valid GeoTIFF scan output that can continue to target matching."""

    path: Path
    raster: RasterMetadata
    layer: ImageLayer
    source_identifier: str | None
    metadata_field_sources: dict[str, MetadataSource]


@dataclass(frozen=True)
class ImageryScanResult:
    """Complete scan output: valid rasters plus non-blocking warnings."""

    rasters: list[ScannedGeoTiff]
    warnings: list[Issue]


ScanProgressCallback = Callable[[int, int, int], None]
CheckpointCallback = Callable[[], None]


_DEFAULT_SCAN_WORKERS = min(8, (os.cpu_count() or 4))


def scan_imagery_folder(
    folder: str | Path,
    *,
    on_progress: ScanProgressCallback | None = None,
    checkpoint: CheckpointCallback | None = None,
    max_workers: int | None = None,
    filename_patterns: list[FilenamePatternConfig] | None = None,
) -> ImageryScanResult:
    """Recursively scan an imagery folder for usable GeoTIFFs.

    Uses a thread pool to overlap rasterio I/O across files.
    """
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        msg = f"Imagery folder is not a directory: {root}"
        raise NotADirectoryError(msg)

    geotiff_paths = discover_geotiffs(root)
    total = len(geotiff_paths)
    if on_progress is not None:
        on_progress(0, total, 0)
    if not geotiff_paths:
        return ImageryScanResult(rasters=[], warnings=[])

    workers = max_workers if max_workers is not None else _DEFAULT_SCAN_WORKERS
    if workers <= 1 or total == 1:
        return _scan_sequential(
            geotiff_paths, on_progress=on_progress, checkpoint=checkpoint,
            filename_patterns=filename_patterns,
        )

    return _scan_parallel(
        geotiff_paths, workers=workers, on_progress=on_progress, checkpoint=checkpoint,
        filename_patterns=filename_patterns,
    )


def _scan_sequential(
    paths: list[Path],
    *,
    on_progress: ScanProgressCallback | None,
    checkpoint: CheckpointCallback | None,
    filename_patterns: list[FilenamePatternConfig] | None,
) -> ImageryScanResult:
    rasters: list[ScannedGeoTiff] = []
    warnings: list[Issue] = []
    total = len(paths)

    for index, geotiff_path in enumerate(paths, start=1):
        if checkpoint is not None:
            checkpoint()
        scanned, issue = _scan_geotiff(geotiff_path, filename_patterns)
        if issue is not None:
            warnings.append(issue)
        if scanned is not None:
            rasters.append(scanned)
            missing_issue = _missing_metadata_warning(scanned)
            if missing_issue is not None:
                warnings.append(missing_issue)
        if on_progress is not None:
            on_progress(index, total, len(rasters))
        if checkpoint is not None:
            checkpoint()

    return ImageryScanResult(rasters=rasters, warnings=warnings)


def _scan_parallel(
    paths: list[Path],
    *,
    workers: int,
    on_progress: ScanProgressCallback | None,
    checkpoint: CheckpointCallback | None,
    filename_patterns: list[FilenamePatternConfig] | None,
) -> ImageryScanResult:
    rasters: list[ScannedGeoTiff] = []
    warnings: list[Issue] = []
    total = len(paths)
    scanned_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: list[Future[tuple[ScannedGeoTiff | None, Issue | None]]] = [
            executor.submit(_scan_geotiff, p, filename_patterns) for p in paths
        ]
        try:
            for future in as_completed(futures):
                if checkpoint is not None:
                    checkpoint()
                scanned, issue = future.result()
                scanned_count += 1
                if issue is not None:
                    warnings.append(issue)
                if scanned is not None:
                    rasters.append(scanned)
                    missing_issue = _missing_metadata_warning(scanned)
                    if missing_issue is not None:
                        warnings.append(missing_issue)
                if on_progress is not None:
                    on_progress(scanned_count, total, len(rasters))
        except BaseException:
            for f in futures:
                f.cancel()
            raise

    rasters.sort(key=lambda s: s.path)
    return ImageryScanResult(rasters=rasters, warnings=warnings)


def discover_geotiffs(folder: str | Path) -> list[Path]:
    """Return supported GeoTIFF files under folder in deterministic order."""
    root = Path(folder).expanduser().resolve()
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_GEOTIFF_SUFFIXES
    )


def scan_geotiff_file(
    path: str | Path,
    *,
    filename_patterns: list[FilenamePatternConfig] | None = None,
) -> ScannedGeoTiff:
    """Validate and parse one usable GeoTIFF file."""
    geotiff_path = Path(path).expanduser().resolve()
    if geotiff_path.suffix.lower() not in SUPPORTED_GEOTIFF_SUFFIXES:
        msg = f"File không phải GeoTIFF được hỗ trợ: {geotiff_path}"
        raise ValueError(msg)
    scanned, issue = _scan_geotiff(geotiff_path, filename_patterns)
    if scanned is None:
        msg = issue.message if issue is not None else f"Không đọc được GeoTIFF: {geotiff_path}"
        raise ValueError(msg)
    return scanned


def _scan_geotiff(
    path: Path,
    filename_patterns: list[FilenamePatternConfig] | None = None,
) -> tuple[ScannedGeoTiff | None, Issue | None]:
    try:
        raster = _read_raster_metadata(path)
    except RasterioIOError as error:
        return None, _warning_issue(
            "imagery.geotiff_unreadable",
            path,
            f"Không thể mở GeoTIFF `{path}`: {error}",
            "Bỏ qua file này và kiểm tra lại định dạng hoặc quyền truy cập.",
        )

    if not _has_valid_footprint(raster):
        return None, _warning_issue(
            "imagery.invalid_footprint",
            path,
            f"GeoTIFF `{path}` không có footprint không gian hợp lệ.",
            "Kiểm tra CRS, transform và bounds của file trước khi chạy ingest lại.",
        )

    business_metadata = parse_business_metadata(
        path, embedded_tags=raster.tags, filename_patterns=filename_patterns,
    )
    metadata_status = (
        MetadataStatus.NEEDS_MANUAL_CORRECTION
        if business_metadata.capture_date is None or business_metadata.capture_time is None
        else MetadataStatus.VALID
    )
    layer = ImageLayer(
        layer_id=_layer_id_for_path(path),
        source_path=str(path),
        order=0,
        capture_date=business_metadata.capture_date,
        capture_time=business_metadata.capture_time,
        cloud_percent=business_metadata.cloud_percent,
        metadata_status=metadata_status,
        metadata_source=business_metadata.primary_source,
    )

    return (
        ScannedGeoTiff(
            path=path,
            raster=raster,
            layer=layer,
            source_identifier=business_metadata.source_identifier,
            metadata_field_sources=business_metadata.field_sources,
        ),
        None,
    )


def _read_raster_metadata(path: Path) -> RasterMetadata:
    with rasterio.open(path) as dataset:
        bounds = dataset.bounds
        return RasterMetadata(
            crs=str(dataset.crs) if dataset.crs else "",
            bounds=RasterBounds(
                left=float(bounds.left),
                bottom=float(bounds.bottom),
                right=float(bounds.right),
                top=float(bounds.top),
            ),
            transform=tuple(float(value) for value in dataset.transform),
            width=dataset.width,
            height=dataset.height,
            band_count=dataset.count,
            nodata=dataset.nodata,
            tags=dict(dataset.tags()),
        )


def _layer_id_for_path(path: Path) -> str:
    path_hash = sha1(str(path).encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{path.stem}__{path_hash}"


def _has_valid_footprint(raster: RasterMetadata) -> bool:
    bounds = raster.bounds
    values = (bounds.left, bounds.bottom, bounds.right, bounds.top)
    return (
        raster.width > 0
        and raster.height > 0
        and raster.band_count > 0
        and bool(raster.crs)
        and all(math.isfinite(value) for value in values)
        and bounds.right > bounds.left
        and bounds.top > bounds.bottom
    )


def _missing_metadata_warning(scanned: ScannedGeoTiff) -> Issue | None:
    missing_fields: list[str] = []
    if scanned.layer.capture_date is None:
        missing_fields.append("capture_date")
    if scanned.layer.capture_time is None:
        missing_fields.append("capture_time")
    if scanned.layer.cloud_percent is None:
        missing_fields.append("cloud_percent")
    if not missing_fields:
        return None

    missing_text = ", ".join(missing_fields)
    return _warning_issue(
        "imagery.metadata_missing",
        scanned.path,
        f"GeoTIFF `{scanned.path}` thiếu metadata nghiệp vụ: {missing_text}.",
        "File vẫn được giữ để match target nếu footprint hợp lệ; "
        "bổ sung metadata trong bước chỉnh sửa thủ công trước khi export.",
    )


def _warning_issue(issue_id: str, path: Path, message: str, remediation: str) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.WARNING,
        scope=IssueScope.LAYER,
        layer_id=str(path),
        message=message,
        remediation=remediation,
    )
