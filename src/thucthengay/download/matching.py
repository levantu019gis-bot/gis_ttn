"""Explicit GeoJSON to source GeoTIFF matching for satellite downloads."""

from __future__ import annotations

import json
import os
import re
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
from shapely.wkt import loads as load_wkt

from thucthengay.download.cache import RasterMetadataCache
from thucthengay.download.filename import parse_filename_metadata, should_skip_for_cloud
from thucthengay.download.models import (
    DownloadFilenameMetadata,
    DownloadGeoJsonArea,
    DownloadImageFolder,
    DownloadImageMatch,
    DownloadMatchedGeometry,
    DownloadMatchResult,
    DownloadOutputStructure,
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

DISCOVERY_PROGRESS_INITIAL_FILES = 10
DISCOVERY_PROGRESS_FILE_INTERVAL = 1000
SIDECAR_METADATA_CRS = "EPSG:4326"
THE_GEOM_PATTERN = re.compile(r"(?ms)^the_geom:\s*(.*?)(?=^[A-Za-z_][A-Za-z0-9_]*:\s|\Z)")
YAML_BLOCK_SCALAR_MARKERS = frozenset({"|", ">", "|-", "|+", ">-", ">+"})


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
                sidecar_metadata = read_sidecar_raster_metadata(candidate.path)
                if sidecar_metadata is not None:
                    scanned_images += 1
                    _process_metadata_result(
                        areas,
                        candidate,
                        sidecar_metadata,
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
        or request.output_structure == DownloadOutputStructure.GEOJSON_SOURCE_GEOMETRY
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
    matched_names, matched_paths = _unique_geojson_matches(matched_areas)
    matched_geometries = tuple(
        DownloadMatchedGeometry(
            geojson_name=area.name,
            geojson_path=area.path,
            geometry_name=area.geometry_name,
        )
        for area in matched_areas
    )
    matches.append(
        DownloadImageMatch(
            source_folder=candidate.source_folder,
            path=candidate.path,
            raster=metadata,
            matched_geojson_names=matched_names,
            matched_geojson_paths=matched_paths,
            matched_geometries=matched_geometries,
        )
    )
    return matched_names


def _unique_geojson_matches(
    matched_areas: list[DownloadGeoJsonArea],
) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    names: list[str] = []
    paths: list[Path] = []
    seen: set[Path] = set()
    for area in matched_areas:
        key = area.path.resolve()
        if key in seen:
            continue
        seen.add(key)
        names.append(area.name)
        paths.append(area.path)
    return tuple(names), tuple(paths)


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
            crs = _crs_from_geojson(raw)
            name = unique_name(safe_name(path.stem), used_names)
            file_areas = _areas_from_geojson(raw, name=name, path=path, crs=crs)
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

        if not file_areas:
            raise SatelliteDownloadConfigError(
                f"GeoJSON không có geometry hợp lệ: {path}",
                field_name=f"geojson_files[{index}]",
            )

        areas.extend(file_areas)

    return tuple(areas)


def _areas_from_geojson(
    raw: dict[str, Any],
    *,
    name: str,
    path: Path,
    crs: str,
) -> list[DownloadGeoJsonArea]:
    geojson_type = raw.get("type")
    if geojson_type == "FeatureCollection":
        features = raw.get("features")
        if not isinstance(features, list):
            msg = "FeatureCollection phải có danh sách features."
            raise ValueError(msg)
        areas = [
            _area_from_feature(feature, name=name, path=path, crs=crs, index=index)
            for index, feature in enumerate(features, start=1)
            if isinstance(feature, dict) and feature.get("geometry") is not None
        ]
        if not areas:
            msg = "FeatureCollection không có geometry."
            raise ValueError(msg)
        return _dedupe_geometry_names(areas)
    if geojson_type == "Feature":
        return _dedupe_geometry_names(
            [_area_from_feature(raw, name=name, path=path, crs=crs, index=1)]
        )
    return [
        DownloadGeoJsonArea(
            name=name,
            path=path,
            crs=crs,
            geometry=_validated_area_geometry(shape(raw)),
            geometry_name="geometry_001",
        )
    ]


def _area_from_feature(
    feature: dict[str, Any],
    *,
    name: str,
    path: Path,
    crs: str,
    index: int,
) -> DownloadGeoJsonArea:
    geometry = feature.get("geometry")
    if geometry is None:
        msg = "Feature không có geometry."
        raise ValueError(msg)
    return DownloadGeoJsonArea(
        name=name,
        path=path,
        crs=crs,
        geometry=_validated_area_geometry(shape(geometry)),
        geometry_name=_feature_geometry_name(feature, index),
    )


def _feature_geometry_name(feature: dict[str, Any], index: int) -> str:
    properties = feature.get("properties")
    raw_name = None
    if isinstance(properties, dict):
        raw_name = properties.get("name")
    if raw_name is not None and str(raw_name).strip():
        return safe_name(str(raw_name))
    return f"geometry_{index:03d}"


def _dedupe_geometry_names(areas: list[DownloadGeoJsonArea]) -> list[DownloadGeoJsonArea]:
    used_names: set[str] = set()
    deduped: list[DownloadGeoJsonArea] = []
    for area in areas:
        deduped.append(
            DownloadGeoJsonArea(
                name=area.name,
                path=area.path,
                crs=area.crs,
                geometry=area.geometry,
                geometry_name=unique_name(area.geometry_name, used_names),
            )
        )
    return deduped


def _validated_area_geometry(geometry: BaseGeometry) -> BaseGeometry:
    geometry = _validated_geometry(geometry)
    if geometry.is_empty or not geometry.is_valid:
        msg = "GeoJSON không có geometry hợp lệ."
        raise ValueError(msg)
    return geometry


def discover_raster_candidates(
    request: ResolvedSatelliteDownloadRequest,
    *,
    on_progress: DownloadDiscoveryProgress | None = None,
    checkpoint: Checkpoint | None = None,
) -> tuple[DownloadRasterCandidate, ...]:
    """Recursively discover configured GeoTIFF candidates under each source folder."""

    candidates: list[DownloadRasterCandidate] = []
    scanned_file_count = 0
    last_progress_count = 0
    last_scanned_folder: DownloadImageFolder | None = None
    last_scanned_path: Path | None = None
    for image_folder in request.image_folders:
        pending_dirs = [image_folder.path]
        while pending_dirs:
            current_dir = pending_dirs.pop()
            try:
                with os.scandir(current_dir) as scan_entries:
                    for entry in scan_entries:
                        if checkpoint is not None:
                            checkpoint()
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                pending_dirs.append(Path(entry.path))
                                continue
                        except OSError as error:
                            raise SatelliteDownloadConfigError(
                                "Khong doc duoc metadata file trong "
                                f"{current_dir}: {entry.name} | {error}",
                                field_name="image_folders",
                            ) from error
                        scanned_file_count += 1
                        last_scanned_folder = image_folder
                        last_scanned_path = Path(entry.path)
                        is_candidate = os.path.splitext(entry.name)[1].lower() in request.extensions
                        should_report = _should_report_discovery_progress(
                            scanned_file_count,
                            last_progress_count,
                        )
                        if is_candidate:
                            try:
                                if not entry.is_file(follow_symlinks=False):
                                    continue
                                stat_result = entry.stat(follow_symlinks=False)
                            except OSError as error:
                                raise SatelliteDownloadConfigError(
                                    "Khong doc duoc metadata file trong "
                                    f"{current_dir}: {entry.name} | {error}",
                                    field_name="image_folders",
                                ) from error
                            candidates.append(
                                DownloadRasterCandidate(
                                    source_folder=image_folder,
                                    path=last_scanned_path.resolve(),
                                    size=stat_result.st_size,
                                    mtime_ns=stat_result.st_mtime_ns,
                                )
                            )
                        if on_progress is not None and should_report:
                            on_progress(
                                scanned_file_count,
                                len(candidates),
                                image_folder,
                                last_scanned_path,
                            )
                            last_progress_count = scanned_file_count
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
    if (
        on_progress is not None
        and scanned_file_count
        and last_progress_count != scanned_file_count
        and last_scanned_folder is not None
        and last_scanned_path is not None
    ):
        on_progress(
            scanned_file_count,
            len(candidates),
            last_scanned_folder,
            last_scanned_path,
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.source_folder.name.casefold(),
                str(candidate.path).casefold(),
            ),
        )
    )


def _should_report_discovery_progress(
    scanned_file_count: int,
    last_progress_count: int,
) -> bool:
    if scanned_file_count <= DISCOVERY_PROGRESS_INITIAL_FILES:
        return True
    return scanned_file_count - last_progress_count >= DISCOVERY_PROGRESS_FILE_INTERVAL


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


def read_sidecar_raster_metadata(path: Path) -> DownloadRasterMetadata | None:
    """Read fast footprint metadata from a same-stem YAML sidecar when available."""

    sidecar_path = _sidecar_metadata_path(path)
    if sidecar_path is None:
        return None
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    wkt_text = _extract_the_geom_wkt(text)
    if wkt_text is None:
        return None
    try:
        footprint = _validated_geometry(load_wkt(wkt_text))
    except (ShapelyError, ValueError, TypeError):
        return None
    if footprint.is_empty:
        return None
    left, bottom, right, top = (float(value) for value in footprint.bounds)
    return DownloadRasterMetadata(
        crs=SIDECAR_METADATA_CRS,
        bounds=(left, bottom, right, top),
        footprint=footprint,
    )


def _sidecar_metadata_path(path: Path) -> Path | None:
    for suffix in (".yaml", ".yml"):
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def _extract_the_geom_wkt(text: str) -> str | None:
    match = THE_GEOM_PATTERN.search(text)
    if match is None:
        return None
    value = match.group(1).strip()
    if not value:
        return None
    lines = value.splitlines()
    if lines and lines[0].strip() in YAML_BLOCK_SCALAR_MARKERS:
        value = "\n".join(lines[1:]).strip()
    value = _strip_yaml_scalar_quotes(value)
    normalized = " ".join(value.split())
    return normalized or None


def _strip_yaml_scalar_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


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
    raster_geometry = (
        metadata.footprint if metadata.footprint is not None else box(*metadata.bounds)
    )
    comparable_union = _transform_geometry_cached(
        union_geometry,
        source_crs=areas[0].crs,
        target_crs=metadata.crs,
        geometry_cache=geometry_cache,
        cache_key="union",
    )
    if not _intersects(raster_geometry, comparable_union, include_boundary_touch):
        return []

    matched: list[DownloadGeoJsonArea] = []
    for area in areas:
        transformed = _transform_geometry_cached(
            area.geometry,
            source_crs=area.crs,
            target_crs=metadata.crs,
            geometry_cache=geometry_cache,
            cache_key=f"{area.path}#{area.geometry_name}",
        )
        if _intersects(raster_geometry, transformed, include_boundary_touch):
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
