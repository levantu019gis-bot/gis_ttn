"""Explicit GeoJSON to source GeoTIFF matching for satellite downloads."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import rasterio
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError
from rasterio.errors import RasterioIOError
from shapely.errors import ShapelyError
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from thucthengay.download.cache import RasterMetadataCache
from thucthengay.download.filename import parse_filename_metadata, should_skip_for_cloud
from thucthengay.download.models import (
    DownloadFilenameMetadata,
    DownloadGeoJsonArea,
    DownloadImageFolder,
    DownloadImageMatch,
    DownloadMatchResult,
    DownloadRasterCandidate,
    DownloadRasterMetadata,
    DownloadStats,
    FailedDownloadImage,
    ResolvedSatelliteDownloadRequest,
    SkippedCloudDownloadCandidate,
    SkippedExistingDownloadImage,
)
from thucthengay.download.service import SatelliteDownloadConfigError, safe_name, unique_name

DownloadMatchProgress = Callable[
    [DownloadStats, DownloadRasterCandidate, tuple[str, ...]],
    None,
]
DownloadDiscoveryProgress = Callable[[int, int, DownloadImageFolder, Path], None]
Checkpoint = Callable[[], None]


def match_source_images(
    request: ResolvedSatelliteDownloadRequest,
    *,
    on_progress: DownloadMatchProgress | None = None,
    on_discovery_progress: DownloadDiscoveryProgress | None = None,
    checkpoint: Checkpoint | None = None,
) -> DownloadMatchResult:
    """Scan selected image folders and match GeoTIFF footprints to explicit GeoJSON files."""

    areas = load_geojson_areas(request.geojson_files)
    candidates = discover_raster_candidates(
        request,
        on_progress=on_discovery_progress,
        checkpoint=checkpoint,
    )
    scan_candidates, skipped_cloud, skipped_existing = _prefilter_candidates(
        request,
        candidates,
        checkpoint=checkpoint,
    )
    matches: list[DownloadImageMatch] = []
    failed_images: list[FailedDownloadImage] = []
    scanned_images = 0
    metadata_cache_hits = 0
    metadata_cache_misses = 0
    geometry_cache: dict[tuple[str, str, str], BaseGeometry] = {}
    union_geometry = unary_union([area.geometry for area in areas])

    with RasterMetadataCache(_metadata_cache_path(request.output_dir)) as metadata_cache:
        pending: dict[Future[DownloadRasterMetadata], DownloadRasterCandidate] = {}
        executor = ThreadPoolExecutor(max_workers=request.scan_workers)
        try:
            for candidate in scan_candidates:
                if checkpoint is not None:
                    checkpoint()
                size, mtime_ns = _candidate_file_identity(candidate)
                cached = metadata_cache.get(candidate.path, size=size, mtime_ns=mtime_ns)
                if cached is not None:
                    metadata_cache_hits += 1
                    scanned_images += 1
                    _process_metadata_result(
                        areas,
                        candidate,
                        cached,
                        matches,
                        include_boundary_touch=request.include_boundary_touch,
                        union_geometry=union_geometry,
                        geometry_cache=geometry_cache,
                    )
                    if on_progress is not None:
                        on_progress(
                            _progress_stats(
                                candidates,
                                scanned_images,
                                matches,
                                failed_images,
                                skipped_cloud=skipped_cloud,
                                skipped_existing=skipped_existing,
                                metadata_cache_hits=metadata_cache_hits,
                                metadata_cache_misses=metadata_cache_misses,
                            ),
                            candidate,
                            _matched_names_for_candidate(matches, candidate),
                        )
                    continue
                pending[executor.submit(read_raster_metadata, candidate.path)] = candidate

            for future in as_completed(pending):
                if checkpoint is not None:
                    checkpoint()
                candidate = pending[future]
                scanned_images += 1
                matched_names: tuple[str, ...] = ()
                try:
                    metadata = future.result()
                    size, mtime_ns = _candidate_file_identity(candidate)
                    metadata_cache.put(
                        candidate.path,
                        size=size,
                        mtime_ns=mtime_ns,
                        metadata=metadata,
                    )
                    metadata_cache_misses += 1
                    matched_names = _process_metadata_result(
                        areas,
                        candidate,
                        metadata,
                        matches,
                        include_boundary_touch=request.include_boundary_touch,
                        union_geometry=union_geometry,
                        geometry_cache=geometry_cache,
                    )
                except (RasterioIOError, ValueError, OSError, CRSError, ProjError) as error:
                    failed_images.append(
                        FailedDownloadImage(
                            source_folder=candidate.source_folder,
                            path=candidate.path,
                            error=f"{candidate.path}: {error}",
                        )
                    )
                if on_progress is not None:
                    on_progress(
                        _progress_stats(
                            candidates,
                            scanned_images,
                            matches,
                            failed_images,
                            skipped_cloud=skipped_cloud,
                            skipped_existing=skipped_existing,
                            metadata_cache_hits=metadata_cache_hits,
                            metadata_cache_misses=metadata_cache_misses,
                        ),
                        candidate,
                        matched_names,
                    )
        finally:
            executor.shutdown(cancel_futures=True)

    return DownloadMatchResult(
        matches=tuple(matches),
        failed_images=tuple(failed_images),
        stats=_progress_stats(
            candidates,
            scanned_images,
            matches,
            failed_images,
            skipped_cloud=skipped_cloud,
            skipped_existing=skipped_existing,
            metadata_cache_hits=metadata_cache_hits,
            metadata_cache_misses=metadata_cache_misses,
        ),
        skipped_cloud_images=tuple(skipped_cloud),
        skipped_existing_images=tuple(skipped_existing),
    )


def _metadata_cache_path(output_dir: Path) -> Path:
    return output_dir / ".satellite_input_metadata_cache.sqlite3"


def get_raster_metadata(
    candidate: DownloadRasterCandidate,
    cache: RasterMetadataCache,
) -> tuple[DownloadRasterMetadata, bool]:
    """Read raster metadata through the persistent SQLite cache."""

    size = candidate.size
    mtime_ns = candidate.mtime_ns
    if size is None or mtime_ns is None:
        stat_result = candidate.path.stat()
        size = stat_result.st_size
        mtime_ns = stat_result.st_mtime_ns

    cached = cache.get(candidate.path, size=size, mtime_ns=mtime_ns)
    if cached is not None:
        return cached, True

    metadata = read_raster_metadata(candidate.path)
    cache.put(candidate.path, size=size, mtime_ns=mtime_ns, metadata=metadata)
    return metadata, False


def _prefilter_candidates(
    request: ResolvedSatelliteDownloadRequest,
    candidates: tuple[DownloadRasterCandidate, ...],
    *,
    checkpoint: Checkpoint | None,
) -> tuple[
    tuple[DownloadRasterCandidate, ...],
    list[SkippedCloudDownloadCandidate],
    list[SkippedExistingDownloadImage],
]:
    active: list[DownloadRasterCandidate] = []
    skipped_cloud: list[SkippedCloudDownloadCandidate] = []
    skipped_existing: list[SkippedExistingDownloadImage] = []
    existing_output_files = (
        {}
        if request.overwrite
        else _discover_existing_output_files(request.output_dir, request.extensions)
    )

    for candidate in candidates:
        if checkpoint is not None:
            checkpoint()
        metadata = parse_filename_metadata(candidate.path, request.filename_formats)
        if should_skip_for_cloud(metadata):
            skipped_cloud.append(
                SkippedCloudDownloadCandidate(
                    source_folder=candidate.source_folder,
                    path=candidate.path,
                    metadata=metadata,
                    reason=_cloud_skip_reason(metadata),
                )
            )
            continue

        existing_path = existing_output_files.get(candidate.path.name)
        if existing_path is not None:
            skipped_existing.append(
                SkippedExistingDownloadImage(
                    source_folder=candidate.source_folder,
                    path=candidate.path,
                    existing_path=existing_path,
                    metadata=metadata,
                    reason="same filename already exists in output_dir",
                )
            )
            continue
        active.append(candidate)

    return tuple(active), skipped_cloud, skipped_existing


def _cloud_skip_reason(metadata: DownloadFilenameMetadata) -> str:
    cloud_text = f"{metadata.cloud_percent:g}" if metadata.cloud_percent is not None else "unknown"
    max_text = (
        f"{metadata.max_cloud_percent:g}" if metadata.max_cloud_percent is not None else "unknown"
    )
    return (
        "Cloud percent "
        f"{cloud_text} vuot nguong cho phep {max_text} "
        f"cua rule {metadata.matched_format_name}."
    )


def _discover_existing_output_files(
    output_dir: Path,
    extensions: frozenset[str],
) -> dict[str, Path]:
    if not output_dir.is_dir():
        return {}

    existing: dict[str, Path] = {}
    try:
        for path in output_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensions:
                existing.setdefault(path.name, path)
    except OSError as error:
        raise SatelliteDownloadConfigError(
            f"Khong scan duoc output_dir {output_dir}: {error}",
            field_name="output_dir",
        ) from error
    return existing


def _candidate_file_identity(candidate: DownloadRasterCandidate) -> tuple[int, int]:
    size = candidate.size
    mtime_ns = candidate.mtime_ns
    if size is None or mtime_ns is None:
        stat_result = candidate.path.stat()
        return stat_result.st_size, stat_result.st_mtime_ns
    return size, mtime_ns


def _process_metadata_result(
    areas: tuple[DownloadGeoJsonArea, ...],
    candidate: DownloadRasterCandidate,
    metadata: DownloadRasterMetadata,
    matches: list[DownloadImageMatch],
    *,
    include_boundary_touch: bool,
    union_geometry: BaseGeometry,
    geometry_cache: dict[tuple[str, str, str], BaseGeometry],
) -> tuple[str, ...]:
    matched_areas = _matched_areas(
        areas,
        metadata,
        include_boundary_touch=include_boundary_touch,
        union_geometry=union_geometry,
        geometry_cache=geometry_cache,
    )
    if not matched_areas:
        return ()
    matched_names = tuple(area.name for area in matched_areas)
    matches.append(
        DownloadImageMatch(
            source_folder=candidate.source_folder,
            path=candidate.path,
            raster=metadata,
            matched_geojson_names=matched_names,
            matched_geojson_paths=tuple(area.path for area in matched_areas),
        )
    )
    return matched_names


def _matched_names_for_candidate(
    matches: list[DownloadImageMatch],
    candidate: DownloadRasterCandidate,
) -> tuple[str, ...]:
    for match in reversed(matches):
        if match.path == candidate.path:
            return match.matched_geojson_names
    return ()


def _progress_stats(
    candidates: tuple[DownloadRasterCandidate, ...],
    scanned_images: int,
    matches: list[DownloadImageMatch],
    failed_images: list[FailedDownloadImage],
    *,
    skipped_cloud: list[SkippedCloudDownloadCandidate] | None = None,
    skipped_existing: list[SkippedExistingDownloadImage] | None = None,
    metadata_cache_hits: int = 0,
    metadata_cache_misses: int = 0,
) -> DownloadStats:
    return DownloadStats(
        total_images=len(candidates),
        scanned_images=scanned_images,
        matched_images=len(matches),
        skipped_existing=0 if skipped_existing is None else len(skipped_existing),
        skipped_cloud=0 if skipped_cloud is None else len(skipped_cloud),
        failed_images=len(failed_images),
        metadata_cache_hits=metadata_cache_hits,
        metadata_cache_misses=metadata_cache_misses,
    )


def load_geojson_areas(geojson_files: tuple[Path, ...]) -> tuple[DownloadGeoJsonArea, ...]:
    """Load AOIs from explicit GeoJSON files."""

    areas: list[DownloadGeoJsonArea] = []
    used_names: set[str] = set()
    detected_crs: str | None = None

    for index, path in enumerate(geojson_files, start=1):
        raw = _read_geojson(path, index)
        try:
            geometry = _geometry_from_geojson(raw)
            crs = _crs_from_geojson(raw)
        except (TypeError, ValueError, CRSError, ShapelyError) as error:
            raise SatelliteDownloadConfigError(
                f"GeoJSON không hợp lệ: {path}. Chi tiết: {error}",
                field_name=f"geojson_files[{index}]",
            ) from error

        if detected_crs is None:
            detected_crs = crs
        elif crs != detected_crs:
            raise SatelliteDownloadConfigError(
                "Các file GeoJSON đang dùng CRS khác nhau. Hãy đưa về cùng CRS "
                f"hoặc tách lượt tải. File lỗi: {path}",
                field_name=f"geojson_files[{index}]",
            )

        if geometry.is_empty or not geometry.is_valid:
            raise SatelliteDownloadConfigError(
                f"GeoJSON không có geometry hợp lệ: {path}",
                field_name=f"geojson_files[{index}]",
            )

        areas.append(
            DownloadGeoJsonArea(
                name=unique_name(safe_name(path.stem), used_names),
                path=path,
                crs=crs,
                geometry=geometry,
            )
        )

    return tuple(areas)


def discover_raster_candidates(
    request: ResolvedSatelliteDownloadRequest,
    *,
    on_progress: DownloadDiscoveryProgress | None = None,
    checkpoint: Checkpoint | None = None,
) -> tuple[DownloadRasterCandidate, ...]:
    """Recursively discover configured GeoTIFF candidates under each source folder."""

    candidates: list[DownloadRasterCandidate] = []
    scanned_file_count = 0
    for image_folder in request.image_folders:
        pending_dirs = [image_folder.path]
        while pending_dirs:
            current_dir = pending_dirs.pop()
            try:
                with os.scandir(current_dir) as scan_entries:
                    entries = sorted(scan_entries, key=lambda entry: entry.name)
                    for entry in entries:
                        if checkpoint is not None:
                            checkpoint()
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                pending_dirs.append(Path(entry.path))
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            stat_result = entry.stat(follow_symlinks=False)
                        except OSError as error:
                            raise SatelliteDownloadConfigError(
                                "Khong doc duoc metadata file trong "
                                f"{current_dir}: {entry.name} | {error}",
                                field_name="image_folders",
                            ) from error
                        path = Path(entry.path)
                        scanned_file_count += 1
                        if path.suffix.lower() in request.extensions:
                            candidates.append(
                                DownloadRasterCandidate(
                                    source_folder=image_folder,
                                    path=path.resolve(),
                                    size=stat_result.st_size,
                                    mtime_ns=stat_result.st_mtime_ns,
                                )
                            )
                        if on_progress is not None:
                            on_progress(
                                scanned_file_count,
                                len(candidates),
                                image_folder,
                                path,
                            )
            except OSError as error:
                raise SatelliteDownloadConfigError(
                    f"Khong scan duoc folder anh ({image_folder.name}): {current_dir} | {error}",
                    field_name="image_folders",
                ) from error
    if not candidates:
        raise SatelliteDownloadConfigError(
            "Khong tim thay anh phu hop voi extensions trong cac folder input.",
            field_name="image_folders",
        )
    return tuple(candidates)


def read_raster_metadata(path: Path) -> DownloadRasterMetadata:
    """Read raster CRS and bounds for matching."""

    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            msg = "Raster không có CRS; không thể so sánh với GeoJSON."
            raise ValueError(msg)
        bounds = dataset.bounds
        return DownloadRasterMetadata(
            crs=str(dataset.crs),
            bounds=(
                float(bounds.left),
                float(bounds.bottom),
                float(bounds.right),
                float(bounds.top),
            ),
        )


def _read_geojson(path: Path, index: int) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as error:
        raise SatelliteDownloadConfigError(
            f"Không đọc được GeoJSON: {path}. Chi tiết: {error}",
            field_name=f"geojson_files[{index}]",
        ) from error
    if not isinstance(raw, dict):
        raise SatelliteDownloadConfigError(
            f"GeoJSON không hợp lệ: {path}. Root phải là JSON object.",
            field_name=f"geojson_files[{index}]",
        )
    return raw


def _geometry_from_geojson(raw: dict[str, Any]) -> BaseGeometry:
    geojson_type = raw.get("type")
    if geojson_type == "FeatureCollection":
        features = raw.get("features")
        if not isinstance(features, list):
            msg = "FeatureCollection phải có danh sách features."
            raise ValueError(msg)
        geometries = [
            shape(feature["geometry"])
            for feature in features
            if isinstance(feature, dict) and feature.get("geometry") is not None
        ]
        if not geometries:
            msg = "FeatureCollection không có geometry."
            raise ValueError(msg)
        return unary_union([_validated_geometry(geometry) for geometry in geometries])
    if geojson_type == "Feature":
        geometry = raw.get("geometry")
        if geometry is None:
            msg = "Feature không có geometry."
            raise ValueError(msg)
        return _validated_geometry(shape(geometry))
    return _validated_geometry(shape(raw))


def _validated_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    return geometry


def _crs_from_geojson(raw: dict[str, Any]) -> str:
    crs = raw.get("crs")
    if isinstance(crs, dict):
        properties = crs.get("properties")
        if isinstance(properties, dict) and properties.get("name"):
            return str(CRS.from_user_input(properties["name"]))
    return "EPSG:4326"


def _matched_areas(
    areas: tuple[DownloadGeoJsonArea, ...],
    metadata: DownloadRasterMetadata,
    *,
    include_boundary_touch: bool,
    union_geometry: BaseGeometry,
    geometry_cache: dict[tuple[str, str, str], BaseGeometry],
) -> list[DownloadGeoJsonArea]:
    raster_bounds = box(*metadata.bounds)
    comparable_union = _transform_geometry_cached(
        union_geometry,
        source_crs=areas[0].crs,
        target_crs=metadata.crs,
        geometry_cache=geometry_cache,
        cache_key="union",
    )
    if not _intersects(raster_bounds, comparable_union, include_boundary_touch):
        return []

    matched: list[DownloadGeoJsonArea] = []
    for area in areas:
        transformed = _transform_geometry_cached(
            area.geometry,
            source_crs=area.crs,
            target_crs=metadata.crs,
            geometry_cache=geometry_cache,
            cache_key=str(area.path),
        )
        if _intersects(raster_bounds, transformed, include_boundary_touch):
            matched.append(area)
    return matched


def _transform_geometry_cached(
    geometry: BaseGeometry,
    *,
    source_crs: str,
    target_crs: str,
    geometry_cache: dict[tuple[str, str, str], BaseGeometry],
    cache_key: str,
) -> BaseGeometry:
    key = (cache_key, source_crs, target_crs)
    cached = geometry_cache.get(key)
    if cached is not None:
        return cached
    transformed = _transform_geometry(
        geometry,
        source_crs=source_crs,
        target_crs=target_crs,
    )
    geometry_cache[key] = transformed
    return transformed


def _transform_geometry(
    geometry: BaseGeometry,
    *,
    source_crs: str,
    target_crs: str,
) -> BaseGeometry:
    source = CRS.from_user_input(source_crs)
    target = CRS.from_user_input(target_crs)
    if source == target:
        return geometry
    transformer = Transformer.from_crs(source, target, always_xy=True)
    return transform(transformer.transform, geometry)


def _intersects(
    raster_bounds: BaseGeometry,
    geometry: BaseGeometry,
    include_boundary_touch: bool,
) -> bool:
    intersects = raster_bounds.intersects(geometry)
    if intersects and not include_boundary_touch:
        return raster_bounds.intersection(geometry).area > 0
    return intersects
