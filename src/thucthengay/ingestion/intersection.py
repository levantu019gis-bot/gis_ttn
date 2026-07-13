"""Target boundary loading and raster footprint intersection."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError
from shapely.errors import ShapelyError
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from thucthengay.config.service import ConfigLoadResult
from thucthengay.ingestion.scanner import RasterMetadata, ScannedGeoTiff
from thucthengay.models import Issue, IssueScope, IssueSeverity, TargetConfig


@dataclass(frozen=True)
class TargetBoundary:
    """Prepared target boundary geometry loaded from GeoJSON."""

    target: TargetConfig
    path: Path
    geometry: BaseGeometry
    crs: str


@dataclass(frozen=True)
class ImageryTargetMatch:
    """One scanned GeoTIFF intersecting one target boundary."""

    target_id: str
    image: ScannedGeoTiff


@dataclass(frozen=True)
class TargetMatchingResult:
    """Target matching output without workspace side effects."""

    matches: dict[str, list[ImageryTargetMatch]]
    issues: list[Issue]
    unmatched_images: list[ScannedGeoTiff] | None = None


TargetMatchProgressCallback = Callable[[int, int, TargetConfig, int], None]
CheckpointCallback = Callable[[], None]


def match_imagery_to_targets(
    images: list[ScannedGeoTiff],
    config_result: ConfigLoadResult,
    *,
    on_target_progress: TargetMatchProgressCallback | None = None,
    checkpoint: CheckpointCallback | None = None,
) -> TargetMatchingResult:
    """Match valid scanned GeoTIFFs to enabled target boundaries."""
    matches: dict[str, list[ImageryTargetMatch]] = {
        target.id: [] for target in config_result.enabled_targets
    }
    issues: list[Issue] = []
    total_targets = len(config_result.enabled_targets)

    for target_index, target in enumerate(config_result.enabled_targets, start=1):
        if checkpoint is not None:
            checkpoint()
        target_paths = config_result.target_paths.get(target.id)
        if target_paths is None:
            issues.append(
                _target_issue(
                    "target.geojson_missing",
                    target.id,
                    f"Không có đường dẫn GeoJSON đã resolve cho target `{target.id}`.",
                    "Tải lại config và kiểm tra `geojson_file` của target.",
                )
            )
            if on_target_progress is not None:
                on_target_progress(target_index, total_targets, target, 0)
            continue

        if target_paths.geojson_file is None:
            boundary, issue = load_target_boundary_from_metadata(target)
        else:
            boundary, issue = load_target_boundary(target, target_paths.geojson_file)
        if issue is not None:
            issues.append(issue)
            if on_target_progress is not None:
                on_target_progress(target_index, total_targets, target, 0)
            continue
        if boundary is None:
            if on_target_progress is not None:
                on_target_progress(target_index, total_targets, target, 0)
            continue

        for image in images:
            if checkpoint is not None:
                checkpoint()
            intersects, issue = _image_intersects_target(image, boundary)
            if issue is not None:
                issues.append(issue)
                break
            if intersects:
                matches[target.id].append(
                    ImageryTargetMatch(target_id=target.id, image=image)
                )
        if on_target_progress is not None:
            on_target_progress(
                target_index,
                total_targets,
                target,
                len(matches[target.id]),
            )
        if checkpoint is not None:
            checkpoint()

    matched_paths = {
        match.image.path
        for target_matches in matches.values()
        for match in target_matches
    }
    unmatched_images = [image for image in images if image.path not in matched_paths]
    return TargetMatchingResult(
        matches=matches,
        issues=issues,
        unmatched_images=unmatched_images,
    )


def load_target_boundary(
    target: TargetConfig,
    geojson_path: str | Path,
) -> tuple[TargetBoundary | None, Issue | None]:
    """Load a target boundary geometry from a config-resolved GeoJSON path."""
    path = Path(geojson_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, _target_issue(
            "target.geojson_missing",
            target.id,
            f"Không tìm thấy GeoJSON của target `{target.id}`: {path}",
            "Kiểm tra lại `geojson_file` trong config.",
        )
    except (OSError, JSONDecodeError) as error:
        return None, _target_issue(
            "target.geojson_invalid",
            target.id,
            f"Không đọc được GeoJSON của target `{target.id}`: {path}",
            f"Sửa file GeoJSON hoặc quyền truy cập. Chi tiết kỹ thuật: {error}",
        )

    try:
        geometry = _geometry_from_geojson(raw)
        crs = _crs_from_geojson(raw)
    except (TypeError, ValueError, CRSError, ShapelyError) as error:
        return None, _target_issue(
            "target.geojson_invalid",
            target.id,
            f"GeoJSON của target `{target.id}` không hợp lệ: {path}",
            f"Sửa hình học/CRS trong GeoJSON. Chi tiết kỹ thuật: {error}",
        )

    if geometry.is_empty or not geometry.is_valid:
        return None, _target_issue(
            "target.geojson_invalid",
            target.id,
            f"GeoJSON của target `{target.id}` không có geometry hợp lệ: {path}",
            "Kiểm tra polygon/geometry của target.",
        )

    return TargetBoundary(target=target, path=path, geometry=geometry, crs=crs), None


def load_target_boundary_from_metadata(
    target: TargetConfig,
) -> tuple[TargetBoundary | None, Issue | None]:
    """Load a target boundary geometry embedded in target config metadata."""
    raw_geometry = target.metadata.get("geojson_geometry")
    if not isinstance(raw_geometry, dict):
        return None, _target_issue(
            "target.geojson_missing",
            target.id,
            f"Target `{target.id}` không có `metadata.geojson_geometry` hợp lệ.",
            "Bổ sung geometry GeoJSON vào metadata hoặc khôi phục `geojson_file`.",
        )

    source = f"config:{target.id}:metadata.geojson_geometry"
    try:
        geometry = _geometry_from_geojson(raw_geometry)
    except (TypeError, ValueError, ShapelyError) as error:
        return None, _target_issue(
            "target.geojson_invalid",
            target.id,
            f"Geometry trong config của target `{target.id}` không hợp lệ.",
            f"Sửa `metadata.geojson_geometry`. Chi tiết kỹ thuật: {error}",
        )

    if geometry.is_empty or not geometry.is_valid:
        return None, _target_issue(
            "target.geojson_invalid",
            target.id,
            f"Geometry trong config của target `{target.id}` không hợp lệ.",
            "Kiểm tra polygon/geometry của target.",
        )

    return (
        TargetBoundary(target=target, path=Path(source), geometry=geometry, crs="EPSG:4326"),
        None,
    )


def _image_intersects_target(
    image: ScannedGeoTiff,
    boundary: TargetBoundary,
) -> tuple[bool, Issue | None]:
    image_footprint = _raster_footprint(image.raster)
    try:
        target_geometry = _transform_geometry(
            boundary.geometry,
            source_crs=boundary.crs,
            target_crs=image.raster.crs,
        )
    except (CRSError, ProjError) as error:
        return False, _target_issue(
            "target.geojson_transform_failed",
            boundary.target.id,
            f"Không thể transform GeoJSON của target `{boundary.target.id}` sang CRS ảnh.",
            f"Kiểm tra CRS của target và GeoTIFF. Chi tiết kỹ thuật: {error}",
        )
    return image_footprint.intersects(target_geometry), None


def _raster_footprint(raster: RasterMetadata) -> BaseGeometry:
    return box(
        raster.bounds.left,
        raster.bounds.bottom,
        raster.bounds.right,
        raster.bounds.top,
    )


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


def _geometry_from_geojson(raw: dict[str, Any]) -> BaseGeometry:
    if not isinstance(raw, dict):
        msg = "GeoJSON root must be an object"
        raise ValueError(msg)

    geojson_type = raw.get("type")
    if geojson_type == "FeatureCollection":
        features = raw.get("features")
        if not isinstance(features, list):
            msg = "FeatureCollection must contain a features list"
            raise ValueError(msg)
        geometries = [
            shape(feature["geometry"])
            for feature in features
            if isinstance(feature, dict) and feature.get("geometry") is not None
        ]
        if not geometries:
            msg = "FeatureCollection contains no geometries"
            raise ValueError(msg)
        return unary_union(geometries)
    if geojson_type == "Feature":
        geometry = raw.get("geometry")
        if geometry is None:
            msg = "Feature contains no geometry"
            raise ValueError(msg)
        return shape(geometry)
    return shape(raw)


def _crs_from_geojson(raw: dict[str, Any]) -> str:
    crs = raw.get("crs")
    if isinstance(crs, dict):
        properties = crs.get("properties")
        if isinstance(properties, dict) and properties.get("name"):
            return str(CRS.from_user_input(properties["name"]))
    return "EPSG:4326"


def _target_issue(issue_id: str, target_id: str, message: str, remediation: str) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=IssueScope.TARGET,
        target_id=target_id,
        message=message,
        remediation=remediation,
    )
