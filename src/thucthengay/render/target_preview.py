"""Target overview preview spec builder.

The target preview is a small, non-persisted overview of all raster coverage for
one target-date composition. It is independent from the editable slide view
center/scale and uses raster metadata bounds only while building the overview.
"""

from __future__ import annotations

from collections.abc import Iterable

import rasterio
from pydantic import ValidationError
from rasterio.errors import RasterioError

from thucthengay.gis.crs import Bbox, dataset_geographic_bbox
from thucthengay.models import Composition, Issue, IssueScope, IssueSeverity, TargetConfig
from thucthengay.models.template import MapFrame, TemplateMetadata
from thucthengay.render.raster import DatasetOpener
from thucthengay.render.spec import (
    MAX_RENDER_PIXELS,
    GeoWindow,
    RenderBackground,
    RenderLayerRef,
    RenderSpec,
    RenderSpecError,
    target_render_background,
)

DEFAULT_TARGET_PREVIEW_WIDTH = 420
DEFAULT_TARGET_PREVIEW_HEIGHT = 180
_BBOX_PADDING_RATIO = 0.02


def build_target_preview_spec(
    *,
    composition: Composition,
    target: TargetConfig,
    template: TemplateMetadata | None = None,
    template_metadata_file: str = "",
    output_width: int = DEFAULT_TARGET_PREVIEW_WIDTH,
    output_height: int = DEFAULT_TARGET_PREVIEW_HEIGHT,
    dataset_opener: DatasetOpener = rasterio.open,
) -> RenderSpec:
    """Build a render spec covering all raster bounds for one target-date composition."""
    issues: list[Issue] = []
    if composition.target_id != target.id:
        issues.append(
            _issue(
                "target_preview.target_mismatch",
                "Composition và target không khớp.",
                "Chọn đúng target trước khi tạo Target Preview.",
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )

    layers = sorted(composition.layers, key=lambda layer: (layer.order, layer.layer_id))
    if not layers:
        issues.append(
            _issue(
                "target_preview.no_layers",
                "Composition không có layer để tạo Target Preview.",
                "Chạy lại ingestion hoặc kiểm tra composition JSON.",
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )

    if output_width <= 0 or output_height <= 0:
        issues.append(
            _issue(
                "target_preview.output_size_invalid",
                "Kích thước Target Preview phải dương.",
                "Cung cấp output_width và output_height lớn hơn 0.",
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )
    elif output_width * output_height > MAX_RENDER_PIXELS:
        issues.append(
            _issue(
                "target_preview.output_size_too_large",
                "Kích thước Target Preview vượt giới hạn an toàn bộ nhớ.",
                "Giảm kích thước preview trước khi render lại.",
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )

    if issues:
        raise RenderSpecError(issues)

    bboxes: list[Bbox] = []
    bbox_issues: list[Issue] = []
    for layer in layers:
        path = layer.cache_path or layer.source_path
        try:
            with dataset_opener(path) as dataset:
                bboxes.append(dataset_geographic_bbox(dataset))
        except (RasterioError, OSError, ValueError) as exc:
            bbox_issues.append(
                _issue(
                    "target_preview.layer_bounds_unreadable",
                    f"Không đọc được bounds của layer '{layer.layer_id}': {exc}",
                    "Kiểm tra GeoTIFF có CRS/transform hợp lệ và có thể mở được.",
                    target_id=target.id,
                    composition_id=composition.composition_id,
                    layer_id=layer.layer_id,
                )
            )

    if not bboxes:
        raise RenderSpecError(
            bbox_issues
            or [
                _issue(
                    "target_preview.no_bounds",
                    "Không xác định được vùng ảnh cho Target Preview.",
                    "Kiểm tra lại metadata bounds của các GeoTIFF trong composition.",
                    target_id=target.id,
                    composition_id=composition.composition_id,
                )
            ]
        )

    try:
        geo_window = GeoWindow.model_validate(_padded_bbox(_union_bbox(bboxes)))
    except (ValidationError, ValueError) as exc:
        raise RenderSpecError(
            [
                _issue(
                    "target_preview.geo_window_invalid",
                    "Không tạo được vùng Target Preview hợp lệ từ bounds raster.",
                    f"Kiểm tra bounds/CRS của GeoTIFF. Chi tiết: {exc}",
                    target_id=target.id,
                    composition_id=composition.composition_id,
                )
            ]
        ) from exc

    width, height = _fit_output_size(
        output_width=output_width,
        output_height=output_height,
        geo_window=geo_window,
    )
    map_frame = (
        template.map_frame
        if template is not None
        else MapFrame(x=0, y=0, width=float(width), height=float(height))
    )

    layer_refs = [
        RenderLayerRef(
            layer_id=layer.layer_id,
            source_path=layer.source_path,
            cache_path=layer.cache_path,
            order=layer.order,
        )
        for layer in layers
    ]

    return RenderSpec(
        composition_id=composition.composition_id,
        target_id=target.id,
        output_width=width,
        output_height=height,
        view_center=[
            (geo_window.min_lon + geo_window.max_lon) / 2,
            (geo_window.min_lat + geo_window.max_lat) / 2,
        ],
        view_scale=composition.view.scale,
        map_frame=map_frame,
        map_frame_aspect=map_frame.width / map_frame.height,
        geo_window=geo_window,
        visible_layers=layer_refs,
        grid=composition.grid_override or target.grid,
        background=_target_preview_background(target),
        template_metadata_file=template_metadata_file or target.export.template_metadata_file,
        template_pptx=template.template_pptx if template is not None else "",
        slide_index=template.slide_index if template is not None else 0,
    )


def _issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    target_id: str,
    composition_id: str,
    layer_id: str | None = None,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=target_id,
        composition_id=composition_id,
        layer_id=layer_id,
        message=message,
        remediation=remediation,
    )


def _union_bbox(bboxes: Iterable[Bbox]) -> dict[str, float]:
    items = list(bboxes)
    min_lon = min(bbox[0] for bbox in items)
    min_lat = min(bbox[1] for bbox in items)
    max_lon = max(bbox[2] for bbox in items)
    max_lat = max(bbox[3] for bbox in items)
    return {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
    }


def _padded_bbox(bbox: dict[str, float]) -> dict[str, float]:
    lon_span = bbox["max_lon"] - bbox["min_lon"]
    lat_span = bbox["max_lat"] - bbox["min_lat"]
    lon_pad = max(lon_span * _BBOX_PADDING_RATIO, 1e-9)
    lat_pad = max(lat_span * _BBOX_PADDING_RATIO, 1e-9)
    return {
        "min_lon": max(-180.0, bbox["min_lon"] - lon_pad),
        "min_lat": max(-90.0, bbox["min_lat"] - lat_pad),
        "max_lon": min(180.0, bbox["max_lon"] + lon_pad),
        "max_lat": min(90.0, bbox["max_lat"] + lat_pad),
    }


def _fit_output_size(
    *,
    output_width: int,
    output_height: int,
    geo_window: GeoWindow,
) -> tuple[int, int]:
    max_width = max(1, output_width)
    max_height = max(1, output_height)
    geo_aspect = (geo_window.max_lon - geo_window.min_lon) / (
        geo_window.max_lat - geo_window.min_lat
    )
    frame_aspect = max_width / max_height
    if geo_aspect >= frame_aspect:
        width = max_width
        height = max(1, int(round(width / geo_aspect)))
    else:
        height = max_height
        width = max(1, int(round(height * geo_aspect)))
    return width, height


def _target_preview_background(target: TargetConfig) -> RenderBackground:
    metadata = target.metadata
    candidate = (
        metadata.get("target_preview_background")
        or metadata.get("preview_background")
        or metadata.get("map_background")
    )
    color = None
    if isinstance(candidate, dict):
        raw = candidate.get("color") or candidate.get("background") or candidate.get("fill")
        if isinstance(raw, str):
            color = raw
    elif isinstance(candidate, str):
        color = candidate

    if color:
        try:
            return RenderBackground(color=color)
        except ValueError:
            pass
    return target_render_background(target)
