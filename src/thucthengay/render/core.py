"""Composed map rendering pipeline."""

from __future__ import annotations

import math

import numpy as np
import rasterio

from thucthengay.models.issue import Issue, IssueScope, IssueSeverity
from thucthengay.render.frame import (
    MapSurroundLayout,
    PixelRect,
    build_map_surround_layout,
    draw_map_surround_frame,
)
from thucthengay.render.raster import (
    CancelCallback,
    DatasetOpener,
    RasterRenderResult,
    RenderError,
    render_raster_layers_to_size,
)
from thucthengay.render.spec import MAX_RENDER_PIXELS, GeoWindow, RenderSpec

_MIN_LON = -180.0
_MAX_LON = 180.0
_MIN_LAT = -90.0
_MAX_LAT = 90.0
_ASPECT_EPSILON = 1e-10


def _cancelled_issue(spec: RenderSpec) -> Issue:
    return Issue(
        issue_id="render.cancelled",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=spec.target_id,
        composition_id=spec.composition_id,
        message="Render da bi huy.",
        remediation="Thuc hien lai render khi khong con thao tac moi hon dang cho.",
    )


def _too_large_issue(spec: RenderSpec) -> Issue:
    return Issue(
        issue_id="render.output.too_large",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=spec.target_id,
        composition_id=spec.composition_id,
        message="Kích thước render vượt giới hạn an toàn bộ nhớ.",
        remediation=(
            f"Giảm kích thước output để tổng pixel không vượt {MAX_RENDER_PIXELS:,}; "
            "với bản final lớn cần dùng luồng render chia tile."
        ),
    )


def _memory_issue(spec: RenderSpec) -> Issue:
    return Issue(
        issue_id="render.output.memory_error",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=spec.target_id,
        composition_id=spec.composition_id,
        message="Không đủ bộ nhớ để tạo canvas render.",
        remediation="Giảm kích thước output hoặc đóng bớt ứng dụng trước khi render lại.",
    )


def _peak_too_large_issue(spec: RenderSpec) -> Issue:
    return Issue(
        issue_id="render.output.peak_too_large",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=spec.target_id,
        composition_id=spec.composition_id,
        message="Kích thước render vượt giới hạn an toàn bộ nhớ.",
        remediation=(
            "Giảm kích thước output; render map-surround cần bộ nhớ cho raster trong, "
            "canvas ngoài và buffer vẽ frame."
        ),
    )


def _invalid_background_issue(spec: RenderSpec) -> Issue:
    return Issue(
        issue_id="render.background.invalid",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=spec.target_id,
        composition_id=spec.composition_id,
        message="Màu nền render không hợp lệ.",
        remediation="Sửa màu nền về định dạng #RRGGBB trước khi render.",
    )


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) != 6:
        msg = f"Background color must be #RRGGBB, got {value!r}"
        raise ValueError(msg)
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _estimated_peak_pixels(*, output_pixels: int, inner_pixels: int) -> int:
    # Full canvas + inner raster + PIL frame conversion/copy of the full canvas.
    return output_pixels * 2 + inner_pixels


def _centered_span(
    *,
    current_min: float,
    current_max: float,
    desired_span: float,
    lower_bound: float,
    upper_bound: float,
) -> tuple[float, float]:
    domain_span = upper_bound - lower_bound
    span = min(desired_span, domain_span)
    center = (current_min + current_max) / 2.0
    new_min = center - span / 2.0
    new_max = center + span / 2.0
    if new_min < lower_bound:
        shift = lower_bound - new_min
        new_min += shift
        new_max += shift
    if new_max > upper_bound:
        shift = new_max - upper_bound
        new_min -= shift
        new_max -= shift
    return max(lower_bound, new_min), min(upper_bound, new_max)


def _fit_geo_window_to_aspect(window: GeoWindow, aspect: float) -> GeoWindow:
    """Expand the geo window so raster pixels fill a target aspect without bitmap scaling."""
    if not math.isfinite(aspect) or aspect <= 0:
        return window

    lon_span = window.max_lon - window.min_lon
    lat_span = window.max_lat - window.min_lat
    current_aspect = lon_span / lat_span
    if abs(current_aspect - aspect) <= _ASPECT_EPSILON:
        return window

    if current_aspect < aspect:
        min_lon, max_lon = _centered_span(
            current_min=window.min_lon,
            current_max=window.max_lon,
            desired_span=lat_span * aspect,
            lower_bound=_MIN_LON,
            upper_bound=_MAX_LON,
        )
        return GeoWindow(
            min_lon=min_lon,
            min_lat=window.min_lat,
            max_lon=max_lon,
            max_lat=window.max_lat,
        )

    min_lat, max_lat = _centered_span(
        current_min=window.min_lat,
        current_max=window.max_lat,
        desired_span=lon_span / aspect,
        lower_bound=_MIN_LAT,
        upper_bound=_MAX_LAT,
    )
    return GeoWindow(
        min_lon=window.min_lon,
        min_lat=min_lat,
        max_lon=window.max_lon,
        max_lat=max_lat,
    )


def _spec_for_inner_map(spec: RenderSpec, inner_map: PixelRect) -> RenderSpec:
    inner_aspect = inner_map.width / inner_map.height
    geo_window = _fit_geo_window_to_aspect(spec.geo_window, inner_aspect)
    return spec.model_copy(
        update={
            "geo_window": geo_window,
            "map_frame_aspect": inner_aspect,
        }
    )


def render_map(
    spec: RenderSpec,
    *,
    dataset_opener: DatasetOpener = rasterio.open,
    is_cancelled: CancelCallback | None = None,
) -> RasterRenderResult:
    """Render a full map-surround image with raster inside the inset map panel."""
    output_pixels = spec.output_width * spec.output_height
    if output_pixels > MAX_RENDER_PIXELS:
        raise RenderError([_too_large_issue(spec)])

    base_layout = build_map_surround_layout(
        spec.output_width,
        spec.output_height,
        spec.grid.style,
    )
    inner = base_layout.inner_map
    render_spec = _spec_for_inner_map(spec, inner)
    layout = MapSurroundLayout(
        outer_frame=base_layout.outer_frame,
        inner_map=inner,
        geo_map=inner,
    )
    inner_pixels = inner.width * inner.height
    if _estimated_peak_pixels(output_pixels=output_pixels, inner_pixels=inner_pixels) > (
        MAX_RENDER_PIXELS * 2
    ):
        raise RenderError([_peak_too_large_issue(spec)])

    result = render_raster_layers_to_size(
        render_spec,
        output_width=inner.width,
        output_height=inner.height,
        dataset_opener=dataset_opener,
        is_cancelled=is_cancelled,
    )
    if is_cancelled is not None and is_cancelled():
        raise RenderError([*result.issues, _cancelled_issue(spec)])

    try:
        bg = _parse_hex_color(spec.background.color)
    except ValueError as exc:
        raise RenderError([*result.issues, _invalid_background_issue(spec)]) from exc

    if is_cancelled is not None and is_cancelled():
        raise RenderError([*result.issues, _cancelled_issue(spec)])

    try:
        canvas = np.empty((spec.output_height, spec.output_width, 3), dtype=np.uint8)
    except MemoryError as exc:
        raise RenderError([*result.issues, _memory_issue(spec)]) from exc

    canvas[:, :] = (255, 255, 255)
    canvas[inner.top : inner.bottom, inner.left : inner.right, :] = bg
    canvas[inner.top : inner.bottom, inner.left : inner.right, :] = result.canvas

    try:
        if is_cancelled is not None and is_cancelled():
            raise RenderError([_cancelled_issue(spec)])
        draw_map_surround_frame(canvas, render_spec, layout, is_cancelled=is_cancelled)
    except MemoryError as exc:
        raise RenderError([*result.issues, _memory_issue(spec)]) from exc
    except RenderError as exc:
        raise RenderError([*result.issues, *exc.issues]) from exc

    return RasterRenderResult(
        canvas=canvas,
        issues=result.issues,
        painted_layer_ids=result.painted_layer_ids,
    )
