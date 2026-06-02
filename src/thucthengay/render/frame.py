"""Coordinate frame drawing for map renders.

Story 5.3 renders an outer coordinate frame with edge ticks and labels. It
intentionally does not draw an internal grid mesh across the raster area.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from thucthengay.models.config import GridConfig
from thucthengay.models.issue import Issue, IssueScope, IssueSeverity
from thucthengay.render.raster import RenderError
from thucthengay.render.spec import GeoWindow, RenderSpec

_FALLBACK_FRAME_SETTINGS: dict[str, object] = {
    "supported_label_formats": ("dms_full", "dms_short"),
    "epsilon": 1e-10,
    "max_frame_ticks_per_axis": 2000,
    "reference_width": 3306,
    "reference_height": 2340,
    "reference_outer_frame": (244, 144, 3272, 2286),
    "reference_frame_gap": 42,
    "surround_outer_stroke_width": 6,
    "surround_inner_stroke_width": 4,
    "surround_tick_length": 14,
    "surround_tick_stroke_width": 4,
    "reference_label_font_size": 72,
    "default_label_font": "fonts/arial-bold/Arial Bold/Arial Bold.ttf",
}


@dataclass(frozen=True)
class PixelRect:
    """Exclusive pixel rectangle used by map surround layout."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_x(self) -> int:
        return self.left + self.width // 2

    @property
    def center_y(self) -> int:
        return self.top + self.height // 2


@dataclass(frozen=True)
class MapSurroundLayout:
    """Pixel layout for the full map image and its inset raster panel."""

    outer_frame: PixelRect
    inner_map: PixelRect
    geo_map: PixelRect | None = None

    @property
    def map_view(self) -> PixelRect:
        return self.geo_map or self.inner_map


@dataclass(frozen=True)
class FrameStyle:
    """Resolved visual style for the coordinate frame."""

    frame_color: tuple[int, int, int] = (0, 0, 0)
    label_color: tuple[int, int, int] = (0, 0, 0)
    label_halo_color: tuple[int, int, int] = (255, 255, 255)
    tick_length: int = 3
    label_padding: int = 3


def build_map_surround_layout(
    width: int,
    height: int,
    style: Mapping[str, object] | None = None,
) -> MapSurroundLayout:
    """Build a ``123.jpg``-style map surround layout for a full output canvas."""
    if width <= 1 or height <= 1:
        return MapSurroundLayout(
            outer_frame=PixelRect(0, 0, max(1, width), max(1, height)),
            inner_map=PixelRect(0, 0, max(1, width), max(1, height)),
        )

    outer = _scale_reference_rect(_reference_outer_frame(style), width, height, style)
    inner = _inner_from_outer_frame(outer, style)
    inner = PixelRect(
        left=max(outer.left + 1, min(inner.left, outer.right - 2)),
        top=max(outer.top + 1, min(inner.top, outer.bottom - 2)),
        right=min(outer.right - 1, max(inner.right, outer.left + 2)),
        bottom=min(outer.bottom - 1, max(inner.bottom, outer.top + 2)),
    )
    if inner.width <= 0 or inner.height <= 0:
        inner = PixelRect(outer.left, outer.top, outer.right, outer.bottom)
    return MapSurroundLayout(outer_frame=outer, inner_map=inner)


def _inner_from_outer_frame(
    outer: PixelRect,
    style: Mapping[str, object] | None = None,
) -> PixelRect:
    inset = _surround_outer_stroke_width(style) + _reference_frame_gap(style)
    return PixelRect(
        left=outer.left + inset,
        top=outer.top + inset,
        right=outer.right - inset,
        bottom=outer.bottom - inset,
    )


def fit_rect_to_aspect(
    rect: PixelRect,
    aspect: float,
    style: Mapping[str, object] | None = None,
) -> PixelRect:
    """Return the largest centered sub-rect preserving ``aspect``."""
    if rect.width <= 0 or rect.height <= 0 or not math.isfinite(aspect) or aspect <= 0:
        return rect

    rect_aspect = rect.width / rect.height
    if abs(rect_aspect - aspect) <= _epsilon(style):
        return rect
    if rect_aspect > aspect:
        width = max(1, int(round(rect.height * aspect)))
        left = rect.left + (rect.width - width) // 2
        return PixelRect(left=left, top=rect.top, right=left + width, bottom=rect.bottom)

    height = max(1, int(round(rect.width / aspect)))
    top = rect.top + (rect.height - height) // 2
    return PixelRect(left=rect.left, top=top, right=rect.right, bottom=top + height)


def _scale_reference_rect(
    rect: tuple[int, int, int, int],
    width: int,
    height: int,
    style: Mapping[str, object] | None = None,
) -> PixelRect:
    left, top, right, bottom = rect
    reference_width = _reference_width(style)
    reference_height = _reference_height(style)
    scaled = PixelRect(
        left=int(round(width * left / reference_width)),
        top=int(round(height * top / reference_height)),
        right=int(round(width * right / reference_width)),
        bottom=int(round(height * bottom / reference_height)),
    )
    return PixelRect(
        left=max(0, min(width - 1, scaled.left)),
        top=max(0, min(height - 1, scaled.top)),
        right=max(1, min(width, scaled.right)),
        bottom=max(1, min(height, scaled.bottom)),
    )


def _scale_reference_value(
    value: int,
    width: int,
    height: int,
    style: Mapping[str, object] | None = None,
    *,
    min_value: int = 1,
) -> int:
    scale = min(width / _reference_width(style), height / _reference_height(style))
    return max(min_value, int(round(value * scale)))


def _styled_dimension(
    style: Mapping[str, object],
    key: str,
    reference_value: int,
    width: int,
    height: int,
    *,
    min_value: int = 1,
) -> int:
    if key in style:
        return _positive_int(style.get(key), fallback=min_value, min_value=min_value)
    return _scale_reference_value(reference_value, width, height, style, min_value=min_value)


def _label_font(size: int, style: Mapping[str, object] | None = None) -> ImageFont.ImageFont:
    try:
        font_path = Path(__file__).resolve().parents[3] / _default_label_font(style)
        return ImageFont.truetype(font_path, size=size)
    except OSError:
        return ImageFont.load_default()


def _issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    composition_id: str,
    target_id: str,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=target_id,
        composition_id=composition_id,
        message=message,
        remediation=remediation,
    )


def _parse_hex_color(value: object, *, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not isinstance(value, str):
        return fallback
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return fallback


def _positive_int(value: object, *, fallback: int, min_value: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= min_value else fallback


def _positive_float(value: object, *, fallback: float, min_value: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) and parsed >= min_value else fallback


def _frame_setting(style: Mapping[str, object] | None, key: str) -> object:
    if style is not None and key in style:
        return style[key]
    return _FALLBACK_FRAME_SETTINGS[key]


def _supported_label_formats(style: Mapping[str, object] | None) -> frozenset[str]:
    fallback = _FALLBACK_FRAME_SETTINGS["supported_label_formats"]
    assert isinstance(fallback, tuple)
    implemented = frozenset(fallback)
    value = _frame_setting(style, "supported_label_formats")
    if not isinstance(value, (list, tuple, set, frozenset)):
        value = fallback
    formats = frozenset(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    ) & implemented
    if formats:
        return formats
    return implemented


def _epsilon(style: Mapping[str, object] | None) -> float:
    return _positive_float(_frame_setting(style, "epsilon"), fallback=1e-10)


def _max_frame_ticks_per_axis(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "max_frame_ticks_per_axis"), fallback=2000)


def _reference_width(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "reference_width"), fallback=3306)


def _reference_height(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "reference_height"), fallback=2340)


def _reference_outer_frame(style: Mapping[str, object] | None) -> tuple[int, int, int, int]:
    value = _frame_setting(style, "reference_outer_frame")
    fallback = _FALLBACK_FRAME_SETTINGS["reference_outer_frame"]
    assert isinstance(fallback, tuple)
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return fallback
    try:
        left, top, right, bottom = (int(item) for item in value)
    except (TypeError, ValueError):
        return fallback
    if right <= left or bottom <= top:
        return fallback
    return left, top, right, bottom


def _reference_frame_gap(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "reference_frame_gap"), fallback=42, min_value=0)


def _surround_outer_stroke_width(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "surround_outer_stroke_width"), fallback=6)


def _surround_inner_stroke_width(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "surround_inner_stroke_width"), fallback=4)


def _surround_tick_length(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "surround_tick_length"), fallback=14)


def _surround_tick_stroke_width(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "surround_tick_stroke_width"), fallback=4)


def _reference_label_font_size(style: Mapping[str, object] | None) -> int:
    return _positive_int(_frame_setting(style, "reference_label_font_size"), fallback=72)


def _default_label_font(style: Mapping[str, object] | None) -> Path:
    value = _frame_setting(style, "default_label_font")
    if isinstance(value, str) and value.strip():
        return Path(value.strip())
    return Path("fonts/arial-bold/Arial Bold/Arial Bold.ttf")


def _frame_style(grid: GridConfig) -> FrameStyle:
    style = grid.style
    default = FrameStyle()
    tick_length = style.get("tick_length", style.get("tick_length_px"))
    return FrameStyle(
        frame_color=_parse_hex_color(style.get("frame_color"), fallback=default.frame_color),
        label_color=_parse_hex_color(style.get("label_color"), fallback=default.label_color),
        label_halo_color=_parse_hex_color(
            style.get("label_halo_color"), fallback=default.label_halo_color
        ),
        tick_length=_positive_int(tick_length, fallback=default.tick_length),
        label_padding=_positive_int(
            style.get("label_padding"), fallback=default.label_padding, min_value=0
        ),
    )


def _interval_degrees(spec: RenderSpec) -> float:
    interval = spec.grid.interval
    value = (
        float(interval.degrees)
        + float(interval.minutes) / 60.0
        + float(interval.seconds) / 3600.0
    )
    if not math.isfinite(value) or value <= 0.0:
        raise RenderError(
            [
                _issue(
                    "render.frame.interval_invalid",
                    "Khoang coordinate frame khong hop le.",
                    "Sua grid.interval de tong do/phut/giay lon hon 0 truoc khi render.",
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            ]
        )
    return value


def _frame_issue(
    spec: RenderSpec,
    issue_id: str,
    message: str,
    remediation: str,
) -> RenderError:
    return RenderError(
        [
            _issue(
                issue_id,
                message,
                remediation,
                composition_id=spec.composition_id,
                target_id=spec.target_id,
            )
        ]
    )


def _validate_label_format(spec: RenderSpec) -> str:
    label_format = "dms_full" if spec.grid.label_format is None else spec.grid.label_format.strip()
    supported_formats = _supported_label_formats(spec.grid.style)
    if label_format not in supported_formats:
        supported_text = " hoac ".join(f"'{item}'" for item in sorted(supported_formats))
        raise _frame_issue(
            spec,
            "render.frame.label_format_invalid",
            "Dinh dang nhan coordinate frame khong duoc ho tro.",
            f"Dung label_format la {supported_text} truoc khi render.",
        )
    return label_format


def _tick_values(
    min_value: float, max_value: float, interval: float, spec: RenderSpec
) -> list[float]:
    epsilon = _epsilon(spec.grid.style)
    first = math.ceil((min_value - epsilon) / interval) * interval
    if first > max_value + epsilon:
        return []

    tick_count = math.floor((max_value - first + epsilon) / interval) + 1
    max_ticks = _max_frame_ticks_per_axis(spec.grid.style)
    if tick_count > max_ticks:
        raise _frame_issue(
            spec,
            "render.frame.interval_too_dense",
            "Khoang coordinate frame qua day de render an toan.",
            (
                "Tang grid.interval de so tick tren moi truc khong vuot "
                f"{max_ticks}."
            ),
        )

    values: list[float] = []
    current = first
    for _ in range(tick_count):
        if current >= min_value - epsilon:
            values.append(round(current, 10))
        current += interval
    return values


def _lon_to_x(window: GeoWindow, width: int, lon: float) -> int:
    ratio = (lon - window.min_lon) / (window.max_lon - window.min_lon)
    return max(0, min(width - 1, int(round(ratio * (width - 1)))))


def _lat_to_y(window: GeoWindow, height: int, lat: float) -> int:
    ratio = (window.max_lat - lat) / (window.max_lat - window.min_lat)
    return max(0, min(height - 1, int(round(ratio * (height - 1)))))


def _lon_to_rect_x(window: GeoWindow, rect: PixelRect, lon: float) -> int:
    ratio = (lon - window.min_lon) / (window.max_lon - window.min_lon)
    return max(rect.left, min(rect.right - 1, int(round(rect.left + ratio * (rect.width - 1)))))


def _lat_to_rect_y(window: GeoWindow, rect: PixelRect, lat: float) -> int:
    ratio = (window.max_lat - lat) / (window.max_lat - window.min_lat)
    return max(rect.top, min(rect.bottom - 1, int(round(rect.top + ratio * (rect.height - 1)))))


def _format_dms(value: float, *, axis: str, label_format: str) -> str:
    hemisphere = ("E" if value >= 0 else "W") if axis == "lon" else ("N" if value >= 0 else "S")
    absolute = abs(value)
    degrees = int(math.floor(absolute))
    minutes_float = (absolute - degrees) * 60.0
    minutes = int(math.floor(minutes_float))
    seconds = int(round((minutes_float - minutes) * 60.0))
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        degrees += 1

    if label_format == "dms_short":
        return f"{degrees:02d}d{minutes:02d}m{hemisphere}"
    return f"{degrees:02d}°{minutes:02d}'{seconds:02d}\"{hemisphere}"


def _draw_text_with_halo(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    halo: tuple[int, int, int],
) -> None:
    x, y = xy
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((x + dx, y + dy), text, font=font, fill=halo)
    draw.text((x, y), text, font=font, fill=fill)


def _clamped_text_origin(
    draw: ImageDraw.ImageDraw,
    text: str,
    desired: tuple[int, int],
    *,
    font: ImageFont.ImageFont,
    width: int,
    height: int,
) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    max_x = max(0, width - text_w - 1)
    max_y = max(0, height - text_h - 1)
    return max(0, min(desired[0], max_x)), max(0, min(desired[1], max_y))


def _text_size(
    draw: ImageDraw.ImageDraw, text: str, *, font: ImageFont.ImageFont
) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_label_padding(style: FrameStyle, label_band: int) -> int:
    if label_band <= 0:
        return 0
    return min(style.label_padding, max(0, label_band // 8))


def _fit_label_font_size(
    draw: ImageDraw.ImageDraw,
    *,
    requested_size: int,
    max_label_height: int,
    labels: tuple[str, ...],
    style: Mapping[str, object] | None = None,
) -> int:
    if max_label_height <= 0:
        return requested_size

    min_size = min(4, requested_size)
    for size in range(requested_size, min_size - 1, -1):
        font = _label_font(size, style)
        if all(_text_size(draw, label, font=font)[1] <= max_label_height for label in labels):
            return size
    return min_size


def _centered_text_origin(
    draw: ImageDraw.ImageDraw,
    text: str,
    center: tuple[int, int],
    *,
    font: ImageFont.ImageFont,
    width: int,
    height: int,
) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    x = center[0] - (bbox[0] + bbox[2]) // 2
    y = center[1] - (bbox[1] + bbox[3]) // 2
    return _clamped_text_origin(draw, text, (x, y), font=font, width=width, height=height)


def _draw_rotated_text_with_halo(
    image: Image.Image,
    center: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    halo: tuple[int, int, int],
    angle: int,
) -> None:
    bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    layer = Image.new("RGBA", (text_w + 4, text_h + 4), (255, 255, 255, 0))
    layer_draw = ImageDraw.Draw(layer)
    _draw_text_with_halo(layer_draw, (2, 2), text, font=font, fill=fill, halo=halo)
    rotated = layer.rotate(angle, expand=True)
    x = max(0, min(image.width - rotated.width, center[0] - rotated.width // 2))
    y = max(0, min(image.height - rotated.height, center[1] - rotated.height // 2))
    image.paste(rotated.convert("RGB"), (x, y), rotated)


def _cancelled_render_error(spec: RenderSpec) -> RenderError:
    return _frame_issue(
        spec,
        "render.cancelled",
        "Render da bi huy.",
        "Thuc hien lai render khi khong con thao tac moi hon dang cho.",
    )


def draw_map_surround_frame(
    canvas: np.ndarray,
    spec: RenderSpec,
    layout: MapSurroundLayout | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> np.ndarray:
    """Draw a 123.jpg-style outer frame, inner map frame, ticks, and labels."""
    if canvas.ndim != 3 or canvas.shape[2] != 3:
        raise RenderError(
            [
                _issue(
                    "render.frame.canvas_invalid",
                    "Canvas render khong dung dinh dang RGB.",
                    "Render frame can canvas numpy co shape (height, width, 3).",
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            ]
        )

    height, width = canvas.shape[:2]
    if width <= 1 or height <= 1:
        raise _frame_issue(
            spec,
            "render.frame.canvas_too_small",
            "Canvas render qua nho de ve coordinate frame.",
            "Tang output_width/output_height truoc khi render.",
        )

    interval = _interval_degrees(spec)
    label_format = _validate_label_format(spec)
    style = _frame_style(spec.grid)
    frame_style = spec.grid.style
    layout = layout or build_map_surround_layout(width, height, frame_style)
    outer = layout.outer_frame
    inner = layout.inner_map
    map_view = layout.map_view
    label_font_size = _styled_dimension(
        frame_style,
        "label_font_size",
        _reference_label_font_size(frame_style),
        width,
        height,
        min_value=8,
    )

    image = Image.fromarray(canvas, mode="RGB")
    draw = ImageDraw.Draw(image)
    sample_lon_label = _format_dms(spec.geo_window.min_lon, axis="lon", label_format=label_format)
    sample_lat_label = _format_dms(spec.geo_window.min_lat, axis="lat", label_format=label_format)
    vertical_label_band = min(inner.top - outer.top, outer.bottom - inner.bottom)
    horizontal_label_band = min(inner.left - outer.left, outer.right - inner.right)
    label_padding = _fit_label_padding(style, min(vertical_label_band, horizontal_label_band))
    label_font_size = _fit_label_font_size(
        draw,
        requested_size=label_font_size,
        max_label_height=min(vertical_label_band - 2, horizontal_label_band - 4)
        - 2 * label_padding,
        labels=(sample_lon_label, sample_lat_label),
        style=frame_style,
    )
    font = _label_font(label_font_size, frame_style)
    _lon_label_w, lon_label_h = _text_size(draw, sample_lon_label, font=font)
    _lat_label_w, lat_label_h = _text_size(draw, sample_lat_label, font=font)

    draw.rectangle(
        (outer.left, outer.top, outer.right - 1, outer.bottom - 1),
        outline=style.frame_color,
        width=_surround_outer_stroke_width(frame_style),
    )
    draw.rectangle(
        (inner.left, inner.top, inner.right - 1, inner.bottom - 1),
        outline=style.frame_color,
        width=_surround_inner_stroke_width(frame_style),
    )

    top_label_y = max(outer.top + label_padding, (outer.top + inner.top) // 2)
    bottom_label_y = min(
        outer.bottom - 1 - label_padding,
        (inner.bottom + outer.bottom - 1) // 2,
    )
    draw_lon_labels = vertical_label_band >= (lon_label_h + 2 + 2 * label_padding)
    for lon in _tick_values(spec.geo_window.min_lon, spec.geo_window.max_lon, interval, spec):
        if is_cancelled is not None and is_cancelled():
            raise _cancelled_render_error(spec)
        x = _lon_to_rect_x(spec.geo_window, map_view, lon)
        if inner.top > outer.top:
            draw.line(
                (x, max(outer.top, inner.top - _surround_tick_length(frame_style)), x, inner.top),
                fill=style.frame_color,
                width=_surround_tick_stroke_width(frame_style),
            )
        if outer.bottom > inner.bottom:
            draw.line(
                (
                    x,
                    inner.bottom - 1,
                    x,
                    min(
                        outer.bottom - 1,
                        inner.bottom - 1 + _surround_tick_length(frame_style),
                    ),
                ),
                fill=style.frame_color,
                width=_surround_tick_stroke_width(frame_style),
            )
        if not draw_lon_labels:
            continue
        label = _format_dms(lon, axis="lon", label_format=label_format)
        top_origin = _centered_text_origin(
            draw,
            label,
            (x, top_label_y),
            font=font,
            width=width,
            height=height,
        )
        bottom_origin = _centered_text_origin(
            draw,
            label,
            (x, bottom_label_y),
            font=font,
            width=width,
            height=height,
        )
        _draw_text_with_halo(
            draw,
            top_origin,
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
        )
        _draw_text_with_halo(
            draw,
            bottom_origin,
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
        )

    left_label_x = max(outer.left + label_padding, (outer.left + inner.left) // 2)
    right_label_x = min(
        outer.right - 1 - label_padding,
        (inner.right + outer.right - 1) // 2,
    )
    draw_lat_labels = horizontal_label_band >= (lat_label_h + 4 + 2 * label_padding)
    for lat in _tick_values(spec.geo_window.min_lat, spec.geo_window.max_lat, interval, spec):
        if is_cancelled is not None and is_cancelled():
            raise _cancelled_render_error(spec)
        y = _lat_to_rect_y(spec.geo_window, map_view, lat)
        if inner.left > outer.left:
            draw.line(
                (
                    max(outer.left, inner.left - _surround_tick_length(frame_style)),
                    y,
                    inner.left,
                    y,
                ),
                fill=style.frame_color,
                width=_surround_tick_stroke_width(frame_style),
            )
        if outer.right > inner.right:
            draw.line(
                (
                    inner.right - 1,
                    y,
                    min(
                        outer.right - 1,
                        inner.right - 1 + _surround_tick_length(frame_style),
                    ),
                    y,
                ),
                fill=style.frame_color,
                width=_surround_tick_stroke_width(frame_style),
            )
        if not draw_lat_labels:
            continue
        label = _format_dms(lat, axis="lat", label_format=label_format)
        _draw_rotated_text_with_halo(
            image,
            (left_label_x, y),
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
            angle=90,
        )
        _draw_rotated_text_with_halo(
            image,
            (right_label_x, y),
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
            angle=90,
        )

    np.copyto(canvas, np.asarray(image, dtype=np.uint8))
    return canvas


def draw_coordinate_frame(canvas: np.ndarray, spec: RenderSpec) -> np.ndarray:
    """Draw an outer coordinate frame over ``canvas`` and return the same array."""
    if canvas.ndim != 3 or canvas.shape[2] != 3:
        raise RenderError(
            [
                _issue(
                    "render.frame.canvas_invalid",
                    "Canvas render khong dung dinh dang RGB.",
                    "Render frame can canvas numpy co shape (height, width, 3).",
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            ]
        )

    height, width = canvas.shape[:2]
    if width <= 1 or height <= 1:
        raise RenderError(
            [
                _issue(
                    "render.frame.canvas_too_small",
                    "Canvas render qua nho de ve coordinate frame.",
                    "Tang output_width/output_height truoc khi render.",
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            ]
        )

    interval = _interval_degrees(spec)
    label_format = _validate_label_format(spec)
    style = _frame_style(spec.grid)

    image = Image.fromarray(canvas, mode="RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, height - 1), outline=style.frame_color, width=1)

    tick_len = min(style.tick_length, max(1, min(width, height) // 4))
    for lon in _tick_values(spec.geo_window.min_lon, spec.geo_window.max_lon, interval, spec):
        x = _lon_to_x(spec.geo_window, width, lon)
        draw.line((x, 0, x, tick_len), fill=style.frame_color, width=1)
        draw.line((x, height - 1 - tick_len, x, height - 1), fill=style.frame_color, width=1)
        label = _format_dms(lon, axis="lon", label_format=label_format)
        origin = _clamped_text_origin(
            draw,
            label,
            (x + style.label_padding, style.label_padding),
            font=font,
            width=width,
            height=height,
        )
        _draw_text_with_halo(
            draw,
            origin,
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
        )
        bottom_origin = _clamped_text_origin(
            draw,
            label,
            (x + style.label_padding, height - style.label_padding),
            font=font,
            width=width,
            height=height,
        )
        _draw_text_with_halo(
            draw,
            bottom_origin,
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
        )

    for lat in _tick_values(spec.geo_window.min_lat, spec.geo_window.max_lat, interval, spec):
        y = _lat_to_y(spec.geo_window, height, lat)
        draw.line((0, y, tick_len, y), fill=style.frame_color, width=1)
        draw.line((width - 1 - tick_len, y, width - 1, y), fill=style.frame_color, width=1)
        label = _format_dms(lat, axis="lat", label_format=label_format)
        origin = _clamped_text_origin(
            draw,
            label,
            (style.label_padding, y + style.label_padding),
            font=font,
            width=width,
            height=height,
        )
        _draw_text_with_halo(
            draw,
            origin,
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
        )
        right_origin = _clamped_text_origin(
            draw,
            label,
            (width - style.label_padding, y + style.label_padding),
            font=font,
            width=width,
            height=height,
        )
        _draw_text_with_halo(
            draw,
            right_origin,
            label,
            font=font,
            fill=style.label_color,
            halo=style.label_halo_color,
        )

    np.copyto(canvas, np.asarray(image, dtype=np.uint8))
    return canvas
