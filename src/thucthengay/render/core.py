"""Composed map rendering pipeline."""

from __future__ import annotations

import numpy as np
import rasterio

from thucthengay.models.issue import Issue, IssueScope, IssueSeverity
from thucthengay.render.frame import (
    MapSurroundLayout,
    build_map_surround_layout,
    draw_map_surround_frame,
    fit_rect_to_aspect,
)
from thucthengay.render.raster import (
    CancelCallback,
    DatasetOpener,
    RasterRenderResult,
    RenderError,
    render_raster_layers_to_size,
)
from thucthengay.render.spec import MAX_RENDER_PIXELS, RenderSpec


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

    base_layout = build_map_surround_layout(spec.output_width, spec.output_height)
    geo_map = fit_rect_to_aspect(base_layout.inner_map, spec.map_frame_aspect)
    layout = MapSurroundLayout(
        outer_frame=base_layout.outer_frame,
        inner_map=base_layout.inner_map,
        geo_map=geo_map,
    )
    inner_pixels = geo_map.width * geo_map.height
    if _estimated_peak_pixels(output_pixels=output_pixels, inner_pixels=inner_pixels) > (
        MAX_RENDER_PIXELS * 2
    ):
        raise RenderError([_peak_too_large_issue(spec)])

    result = render_raster_layers_to_size(
        spec,
        output_width=geo_map.width,
        output_height=geo_map.height,
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
    inner = layout.inner_map
    canvas[inner.top : inner.bottom, inner.left : inner.right, :] = bg
    canvas[geo_map.top : geo_map.bottom, geo_map.left : geo_map.right, :] = result.canvas

    try:
        if is_cancelled is not None and is_cancelled():
            raise RenderError([_cancelled_issue(spec)])
        draw_map_surround_frame(canvas, spec, layout, is_cancelled=is_cancelled)
    except MemoryError as exc:
        raise RenderError([*result.issues, _memory_issue(spec)]) from exc
    except RenderError as exc:
        raise RenderError([*result.issues, *exc.issues]) from exc

    return RasterRenderResult(
        canvas=canvas,
        issues=result.issues,
        painted_layer_ids=result.painted_layer_ids,
    )
