"""Composed map rendering pipeline."""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Hashable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import rasterio

from thucthengay.models import TemporalCompareOrientation
from thucthengay.models.issue import Issue, IssueScope, IssueSeverity
from thucthengay.render.diagnostics import RenderDiagnostics
from thucthengay.render.frame import (
    MapSurroundLayout,
    PixelRect,
    build_map_surround_layout,
    draw_map_surround_frame,
    draw_map_surround_outline,
    draw_map_surround_pane_frame,
)
from thucthengay.render.raster import (
    CancelCallback,
    DatasetOpener,
    RasterRenderResult,
    RenderError,
    render_raster_layers_to_size,
)
from thucthengay.render.spec import (
    MAX_RENDER_PIXELS,
    GeoWindow,
    RenderComparisonPane,
    RenderComparisonSpec,
    RenderLayerRef,
    RenderSpec,
)

_MIN_LON = -180.0
_MAX_LON = 180.0
_MIN_LAT = -90.0
_MAX_LAT = 90.0
_ASPECT_EPSILON = 1e-10
_DEFAULT_RASTER_BASE_CACHE_BYTES = 256 * 1024 * 1024
_DEFAULT_FRAME_OVERLAY_CACHE_BYTES = 64 * 1024 * 1024
_DEFAULT_FULL_MAP_CACHE_BYTES = 256 * 1024 * 1024
_DEFAULT_TEMPORAL_COMPARE_PANE_GAP_PX = 8


@dataclass(frozen=True)
class _CachedRasterBase:
    canvas: np.ndarray
    issues: tuple[Issue, ...]
    painted_layer_ids: tuple[str, ...]
    nbytes: int


@dataclass(frozen=True)
class _CachedFrameOverlay:
    pixels: np.ndarray
    mask: np.ndarray
    nbytes: int


@dataclass(frozen=True)
class _CachedFullMap:
    canvas: np.ndarray
    issues: tuple[Issue, ...]
    painted_layer_ids: tuple[str, ...]
    nbytes: int


class _ByteBudgetCache:
    def __init__(self, *, max_bytes: int) -> None:
        self.max_bytes = max(0, max_bytes)
        self._used_bytes = 0
        self._lock = Lock()

    @property
    def used_bytes(self) -> int:
        with self._lock:
            return self._used_bytes


class RasterBaseCache(_ByteBudgetCache):
    """Small LRU cache for inner raster canvases used by preview rendering."""

    def __init__(self, *, max_bytes: int = _DEFAULT_RASTER_BASE_CACHE_BYTES) -> None:
        super().__init__(max_bytes=max_bytes)
        self._entries: OrderedDict[tuple[Hashable, ...], _CachedRasterBase] = OrderedDict()

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._used_bytes = 0

    def get(self, key: tuple[Hashable, ...]) -> RasterRenderResult | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return RasterRenderResult(
                canvas=entry.canvas.copy(),
                issues=entry.issues,
                painted_layer_ids=entry.painted_layer_ids,
            )

    def put(self, key: tuple[Hashable, ...], result: RasterRenderResult) -> None:
        nbytes = int(result.canvas.nbytes)
        if self.max_bytes <= 0 or nbytes > self.max_bytes:
            return
        entry = _CachedRasterBase(
            canvas=result.canvas.copy(),
            issues=tuple(result.issues),
            painted_layer_ids=tuple(result.painted_layer_ids),
            nbytes=nbytes,
        )
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._used_bytes -= old.nbytes
            self._entries[key] = entry
            self._used_bytes += nbytes
            self._evict_locked()

    def _evict_locked(self) -> None:
        while self._used_bytes > self.max_bytes and self._entries:
            _old_key, old = self._entries.popitem(last=False)
            self._used_bytes -= old.nbytes


class FrameOverlayCache(_ByteBudgetCache):
    """LRU cache for frame/tick/label overlays."""

    def __init__(self, *, max_bytes: int = _DEFAULT_FRAME_OVERLAY_CACHE_BYTES) -> None:
        super().__init__(max_bytes=max_bytes)
        self._entries: OrderedDict[tuple[Hashable, ...], _CachedFrameOverlay] = OrderedDict()

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._used_bytes = 0

    def get(self, key: tuple[Hashable, ...]) -> tuple[np.ndarray, np.ndarray] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry.pixels.copy(), entry.mask.copy()

    def put(self, key: tuple[Hashable, ...], pixels: np.ndarray, mask: np.ndarray) -> None:
        nbytes = int(pixels.nbytes + mask.nbytes)
        if self.max_bytes <= 0 or nbytes > self.max_bytes:
            return
        entry = _CachedFrameOverlay(
            pixels=pixels.copy(),
            mask=mask.copy(),
            nbytes=nbytes,
        )
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._used_bytes -= old.nbytes
            self._entries[key] = entry
            self._used_bytes += nbytes
            self._evict_locked()

    def _evict_locked(self) -> None:
        while self._used_bytes > self.max_bytes and self._entries:
            _old_key, old = self._entries.popitem(last=False)
            self._used_bytes -= old.nbytes


class FullMapCache(_ByteBudgetCache):
    """LRU cache for complete preview canvases."""

    def __init__(self, *, max_bytes: int = _DEFAULT_FULL_MAP_CACHE_BYTES) -> None:
        super().__init__(max_bytes=max_bytes)
        self._entries: OrderedDict[tuple[Hashable, ...], _CachedFullMap] = OrderedDict()

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._used_bytes = 0

    def get(self, key: tuple[Hashable, ...]) -> RasterRenderResult | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return RasterRenderResult(
                canvas=entry.canvas.copy(),
                issues=entry.issues,
                painted_layer_ids=entry.painted_layer_ids,
            )

    def put(self, key: tuple[Hashable, ...], result: RasterRenderResult) -> None:
        nbytes = int(result.canvas.nbytes)
        if self.max_bytes <= 0 or nbytes > self.max_bytes:
            return
        entry = _CachedFullMap(
            canvas=result.canvas.copy(),
            issues=tuple(result.issues),
            painted_layer_ids=tuple(result.painted_layer_ids),
            nbytes=nbytes,
        )
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._used_bytes -= old.nbytes
            self._entries[key] = entry
            self._used_bytes += nbytes
            self._evict_locked()

    def _evict_locked(self) -> None:
        while self._used_bytes > self.max_bytes and self._entries:
            _old_key, old = self._entries.popitem(last=False)
            self._used_bytes -= old.nbytes


class MapRenderCache:
    """Preview cache bundle for raster bases, frame overlays, and full maps."""

    def __init__(
        self,
        *,
        raster_base_bytes: int = _DEFAULT_RASTER_BASE_CACHE_BYTES,
        frame_overlay_bytes: int = _DEFAULT_FRAME_OVERLAY_CACHE_BYTES,
        full_map_bytes: int = _DEFAULT_FULL_MAP_CACHE_BYTES,
    ) -> None:
        self.raster_bases = RasterBaseCache(max_bytes=raster_base_bytes)
        self.frame_overlays = FrameOverlayCache(max_bytes=frame_overlay_bytes)
        self.full_maps = FullMapCache(max_bytes=full_map_bytes)

    def clear(self) -> None:
        self.raster_bases.clear()
        self.frame_overlays.clear()
        self.full_maps.clear()


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


def _render_layout_for_spec(spec: RenderSpec) -> tuple[RenderSpec, MapSurroundLayout]:
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
    return render_spec, layout


def _render_raster_base_cache_key(
    spec: RenderSpec,
    *,
    output_width: int,
    output_height: int,
) -> tuple[Hashable, ...]:
    return (
        spec.composition_id,
        spec.target_id,
        output_width,
        output_height,
        spec.background.color,
        _geo_window_key(spec.geo_window),
        tuple(_layer_key(layer) for layer in spec.visible_layers),
    )


def _geo_window_key(window: GeoWindow) -> tuple[float, float, float, float]:
    return (
        window.min_lon,
        window.min_lat,
        window.max_lon,
        window.max_lat,
    )


def _layer_key(layer: RenderLayerRef) -> tuple[Hashable, ...]:
    path = layer.cache_path or layer.source_path
    return (
        layer.layer_id,
        layer.order,
        layer.source_path,
        layer.cache_path,
        _path_signature(path),
    )


def _full_map_cache_key(spec: RenderSpec) -> tuple[Hashable, ...]:
    return (
        "full-map",
        _freeze_jsonish(spec.model_dump(mode="json")),
        tuple(_layer_key(layer) for layer in spec.visible_layers),
    )


def _frame_overlay_cache_key(
    spec: RenderSpec,
    layout: MapSurroundLayout,
) -> tuple[Hashable, ...]:
    return (
        "frame-overlay",
        spec.output_width,
        spec.output_height,
        _rect_key(layout.outer_frame),
        _rect_key(layout.inner_map),
        _rect_key(layout.map_view),
        _geo_window_key(spec.geo_window),
        _freeze_jsonish(spec.grid.model_dump(mode="json")),
    )


def _rect_key(rect: PixelRect) -> tuple[int, int, int, int]:
    return rect.left, rect.top, rect.right, rect.bottom


def _freeze_jsonish(value: Any) -> Hashable:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze_jsonish(item)) for key, item in value.items()))
    if isinstance(value, list | tuple):
        return tuple(_freeze_jsonish(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted(_freeze_jsonish(item) for item in value))
    return value


def _path_signature(path: str) -> tuple[int, int] | None:
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _render_raster_base(
    render_spec: RenderSpec,
    *,
    output_width: int,
    output_height: int,
    dataset_opener: DatasetOpener,
    is_cancelled: CancelCallback | None,
    raster_cache: RasterBaseCache | None,
    diagnostics: RenderDiagnostics | None,
) -> RasterRenderResult:
    if raster_cache is None:
        if diagnostics is not None:
            diagnostics.record_cache_miss("raster_base")
        return _render_raster_layers_to_size_optional_diagnostics(
            render_spec,
            output_width=output_width,
            output_height=output_height,
            dataset_opener=dataset_opener,
            is_cancelled=is_cancelled,
            diagnostics=diagnostics,
        )

    key = _render_raster_base_cache_key(
        render_spec,
        output_width=output_width,
        output_height=output_height,
    )
    cached = raster_cache.get(key)
    if cached is not None:
        if diagnostics is not None:
            diagnostics.record_cache_hit("raster_base")
        return cached
    if diagnostics is not None:
        diagnostics.record_cache_miss("raster_base")

    result = _render_raster_layers_to_size_optional_diagnostics(
        render_spec,
        output_width=output_width,
        output_height=output_height,
        dataset_opener=dataset_opener,
        is_cancelled=is_cancelled,
        diagnostics=diagnostics,
    )
    if is_cancelled is None or not is_cancelled():
        raster_cache.put(key, result)
    return result


def _render_raster_layers_to_size_optional_diagnostics(
    render_spec: RenderSpec,
    *,
    output_width: int,
    output_height: int,
    dataset_opener: DatasetOpener,
    is_cancelled: CancelCallback | None,
    diagnostics: RenderDiagnostics | None,
) -> RasterRenderResult:
    kwargs: dict[str, Any] = {
        "output_width": output_width,
        "output_height": output_height,
        "dataset_opener": dataset_opener,
        "is_cancelled": is_cancelled,
    }
    if diagnostics is not None:
        kwargs["diagnostics"] = diagnostics
    return render_raster_layers_to_size(render_spec, **kwargs)


def render_map(
    spec: RenderSpec,
    *,
    dataset_opener: DatasetOpener = rasterio.open,
    is_cancelled: CancelCallback | None = None,
    diagnostics: RenderDiagnostics | None = None,
) -> RasterRenderResult:
    """Render a full map-surround image with raster inside the inset map panel."""
    return _render_map(
        spec,
        dataset_opener=dataset_opener,
        is_cancelled=is_cancelled,
        diagnostics=diagnostics,
    )


def render_map_with_cache(
    spec: RenderSpec,
    *,
    render_cache: MapRenderCache | None = None,
    raster_cache: RasterBaseCache | None = None,
    dataset_opener: DatasetOpener = rasterio.open,
    is_cancelled: CancelCallback | None = None,
    diagnostics: RenderDiagnostics | None = None,
) -> RasterRenderResult:
    """Render a map-surround image while reusing unchanged inner raster bases."""
    if render_cache is None and raster_cache is None:
        render_cache = MapRenderCache()
    return _render_map(
        spec,
        dataset_opener=dataset_opener,
        is_cancelled=is_cancelled,
        raster_cache=render_cache.raster_bases if render_cache is not None else raster_cache,
        frame_cache=render_cache.frame_overlays if render_cache is not None else None,
        full_cache=render_cache.full_maps if render_cache is not None else None,
        diagnostics=diagnostics,
    )


def _render_map(
    spec: RenderSpec,
    *,
    dataset_opener: DatasetOpener,
    is_cancelled: CancelCallback | None,
    raster_cache: RasterBaseCache | None = None,
    frame_cache: FrameOverlayCache | None = None,
    full_cache: FullMapCache | None = None,
    diagnostics: RenderDiagnostics | None = None,
) -> RasterRenderResult:
    if diagnostics is not None:
        diagnostics.record_render_spec(spec)
    with diagnostics.time("render.total") if diagnostics is not None else nullcontext():
        return _render_map_inner(
            spec,
            dataset_opener=dataset_opener,
            is_cancelled=is_cancelled,
            raster_cache=raster_cache,
            frame_cache=frame_cache,
            full_cache=full_cache,
            diagnostics=diagnostics,
        )


def _render_map_inner(
    spec: RenderSpec,
    *,
    dataset_opener: DatasetOpener,
    is_cancelled: CancelCallback | None,
    raster_cache: RasterBaseCache | None,
    frame_cache: FrameOverlayCache | None,
    full_cache: FullMapCache | None,
    diagnostics: RenderDiagnostics | None,
) -> RasterRenderResult:
    output_pixels = spec.output_width * spec.output_height
    if output_pixels > MAX_RENDER_PIXELS:
        raise RenderError([_too_large_issue(spec)])

    full_key = _full_map_cache_key(spec) if full_cache is not None else None
    if full_cache is not None and full_key is not None:
        cached_full = full_cache.get(full_key)
        if cached_full is not None:
            if diagnostics is not None:
                diagnostics.record_cache_hit("full_map")
            return cached_full
        if diagnostics is not None:
            diagnostics.record_cache_miss("full_map")

    with diagnostics.time("render.layout") if diagnostics is not None else nullcontext():
        render_spec, layout = _render_layout_for_spec(spec)
    inner = layout.inner_map
    inner_pixels = inner.width * inner.height
    if _estimated_peak_pixels(output_pixels=output_pixels, inner_pixels=inner_pixels) > (
        MAX_RENDER_PIXELS * 2
    ):
        raise RenderError([_peak_too_large_issue(spec)])

    if render_spec.temporal_compare.enabled:
        result = _render_temporal_compare_base(
            render_spec,
            inner,
            dataset_opener=dataset_opener,
            is_cancelled=is_cancelled,
            raster_cache=raster_cache,
            diagnostics=diagnostics,
        )
    else:
        result = _render_raster_base(
            render_spec,
            output_width=inner.width,
            output_height=inner.height,
            dataset_opener=dataset_opener,
            is_cancelled=is_cancelled,
            raster_cache=raster_cache,
            diagnostics=diagnostics,
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
        timer = (
            diagnostics.time("render.canvas_allocate")
            if diagnostics is not None
            else nullcontext()
        )
        with timer:
            canvas = np.empty((spec.output_height, spec.output_width, 3), dtype=np.uint8)
    except MemoryError as exc:
        raise RenderError([*result.issues, _memory_issue(spec)]) from exc

    with diagnostics.time("render.composite") if diagnostics is not None else nullcontext():
        canvas[:, :] = (255, 255, 255)
        canvas[inner.top : inner.bottom, inner.left : inner.right, :] = bg
        canvas[inner.top : inner.bottom, inner.left : inner.right, :] = result.canvas

    try:
        if is_cancelled is not None and is_cancelled():
            raise RenderError([_cancelled_issue(spec)])
        if render_spec.temporal_compare.enabled:
            if diagnostics is not None:
                diagnostics.record_cache_miss("frame_overlay")
            timer = (
                diagnostics.time("render.frame_overlay")
                if diagnostics is not None
                else nullcontext()
            )
            with timer:
                draw_map_surround_outline(canvas, render_spec, layout, draw_inner=False)
                _draw_temporal_compare_pane_frames(
                    canvas,
                    render_spec,
                    layout,
                    is_cancelled=is_cancelled,
                )
        else:
            _apply_map_surround_frame(
                canvas,
                render_spec,
                layout,
                background=bg,
                frame_cache=frame_cache,
                is_cancelled=is_cancelled,
                diagnostics=diagnostics,
            )
    except MemoryError as exc:
        raise RenderError([*result.issues, _memory_issue(spec)]) from exc
    except RenderError as exc:
        raise RenderError([*result.issues, *exc.issues]) from exc

    rendered = RasterRenderResult(
        canvas=canvas,
        issues=result.issues,
        painted_layer_ids=result.painted_layer_ids,
    )
    if full_cache is not None and full_key is not None and (
        is_cancelled is None or not is_cancelled()
    ):
        full_cache.put(full_key, rendered)
    return rendered


def _apply_map_surround_frame(
    canvas: np.ndarray,
    spec: RenderSpec,
    layout: MapSurroundLayout,
    *,
    background: tuple[int, int, int],
    frame_cache: FrameOverlayCache | None,
    is_cancelled: CancelCallback | None,
    diagnostics: RenderDiagnostics | None,
) -> None:
    if frame_cache is None:
        if diagnostics is not None:
            diagnostics.record_cache_miss("frame_overlay")
        with diagnostics.time("render.frame_overlay") if diagnostics is not None else nullcontext():
            draw_map_surround_frame(canvas, spec, layout, is_cancelled=is_cancelled)
        return

    key = _frame_overlay_cache_key(spec, layout)
    cached = frame_cache.get(key)
    if cached is None:
        if diagnostics is not None:
            diagnostics.record_cache_miss("frame_overlay")
        with diagnostics.time("render.frame_overlay") if diagnostics is not None else nullcontext():
            pixels, mask = _build_frame_overlay(
                spec,
                layout,
                background=background,
                is_cancelled=is_cancelled,
            )
        if is_cancelled is None or not is_cancelled():
            frame_cache.put(key, pixels, mask)
    else:
        if diagnostics is not None:
            diagnostics.record_cache_hit("frame_overlay")
        pixels, mask = cached

    with diagnostics.time("render.frame_composite") if diagnostics is not None else nullcontext():
        canvas[mask] = pixels[mask]


def _render_temporal_compare_base(
    spec: RenderSpec,
    inner: PixelRect,
    *,
    dataset_opener: DatasetOpener,
    is_cancelled: CancelCallback | None,
    raster_cache: RasterBaseCache | None,
    diagnostics: RenderDiagnostics | None,
) -> RasterRenderResult:
    comparison = spec.temporal_compare
    pane_gap_px = _temporal_compare_pane_gap_px(spec)
    pane_a_rect, pane_b_rect = _split_compare_inner_map(
        inner,
        comparison.orientation,
        gap_px=pane_gap_px,
    )
    gap_color = _temporal_compare_gap_color(spec)
    canvas = np.empty((inner.height, inner.width, 3), dtype=np.uint8)
    canvas[:, :] = gap_color
    issues: list[Issue] = []
    painted_layer_ids: list[str] = []

    for pane_rect, pane in (
        (pane_a_rect, comparison.pane_a),
        (pane_b_rect, comparison.pane_b),
    ):
        pane_result = _render_temporal_compare_pane(
            spec,
            pane,
            pane_rect,
            dataset_opener=dataset_opener,
            is_cancelled=is_cancelled,
            raster_cache=raster_cache,
            diagnostics=diagnostics,
        )
        issues.extend(pane_result.issues)
        painted_layer_ids.extend(pane_result.painted_layer_ids)
        top = pane_rect.top - inner.top
        bottom = pane_rect.bottom - inner.top
        left = pane_rect.left - inner.left
        right = pane_rect.right - inner.left
        canvas[top:bottom, left:right, :] = pane_result.canvas

    return RasterRenderResult(
        canvas=canvas,
        issues=tuple(issues),
        painted_layer_ids=tuple(dict.fromkeys(painted_layer_ids)),
    )


def _draw_temporal_compare_pane_frames(
    canvas: np.ndarray,
    spec: RenderSpec,
    layout: MapSurroundLayout,
    *,
    is_cancelled: CancelCallback | None,
) -> None:
    comparison = spec.temporal_compare
    pane_gap_px = _temporal_compare_pane_gap_px(spec)
    pane_a_rect, pane_b_rect = _split_compare_inner_map(
        layout.inner_map,
        comparison.orientation,
        gap_px=pane_gap_px,
    )
    internal_gap_px = _compare_pane_gap(pane_a_rect, pane_b_rect, comparison.orientation)
    for pane_rect, pane in (
        (pane_a_rect, comparison.pane_a),
        (pane_b_rect, comparison.pane_b),
    ):
        pane_spec = _spec_for_compare_pane(spec, pane, pane_rect)
        draw_map_surround_pane_frame(
            canvas,
            pane_spec,
            layout,
            pane_rect,
            is_cancelled=is_cancelled,
            internal_gap_px=internal_gap_px,
        )


def _render_temporal_compare_pane(
    spec: RenderSpec,
    pane: RenderComparisonPane,
    pane_rect: PixelRect,
    *,
    dataset_opener: DatasetOpener,
    is_cancelled: CancelCallback | None,
    raster_cache: RasterBaseCache | None,
    diagnostics: RenderDiagnostics | None,
) -> RasterRenderResult:
    pane_spec = _spec_for_compare_pane(spec, pane, pane_rect)
    return _render_raster_base(
        pane_spec,
        output_width=pane_rect.width,
        output_height=pane_rect.height,
        dataset_opener=dataset_opener,
        is_cancelled=is_cancelled,
        raster_cache=raster_cache,
        diagnostics=diagnostics,
    )


def _spec_for_compare_pane(
    spec: RenderSpec,
    pane: RenderComparisonPane,
    pane_rect: PixelRect,
) -> RenderSpec:
    updates: dict[str, object] = {
        "visible_layers": pane.layers,
        "temporal_compare": RenderComparisonSpec(),
    }
    if pane.geo_window is not None:
        updates["geo_window"] = pane.geo_window
    if pane.view_center is not None:
        updates["view_center"] = pane.view_center
    if pane.view_scale is not None:
        updates["view_scale"] = pane.view_scale
    return _spec_for_inner_map(spec.model_copy(update=updates), pane_rect)


def _split_compare_inner_map(
    inner: PixelRect,
    orientation: TemporalCompareOrientation,
    *,
    gap_px: int | None = None,
) -> tuple[PixelRect, PixelRect]:
    resolved_gap_px = _compare_gap_px(inner, orientation, gap_px=gap_px)
    if orientation == TemporalCompareOrientation.HORIZONTAL:
        mid = inner.top + inner.height // 2
        pane_a_bottom = mid - resolved_gap_px // 2
        pane_b_top = pane_a_bottom + resolved_gap_px
        return (
            PixelRect(
                left=inner.left,
                top=inner.top,
                right=inner.right,
                bottom=pane_a_bottom,
            ),
            PixelRect(
                left=inner.left,
                top=pane_b_top,
                right=inner.right,
                bottom=inner.bottom,
            ),
        )
    mid = inner.left + inner.width // 2
    pane_a_right = mid - resolved_gap_px // 2
    pane_b_left = pane_a_right + resolved_gap_px
    return (
        PixelRect(
            left=inner.left,
            top=inner.top,
            right=pane_a_right,
            bottom=inner.bottom,
        ),
        PixelRect(
            left=pane_b_left,
            top=inner.top,
            right=inner.right,
            bottom=inner.bottom,
        ),
    )


def _compare_gap_px(
    inner: PixelRect,
    orientation: TemporalCompareOrientation,
    *,
    gap_px: int | None = None,
) -> int:
    split_size = (
        inner.height
        if orientation == TemporalCompareOrientation.HORIZONTAL
        else inner.width
    )
    requested_gap_px = (
        _DEFAULT_TEMPORAL_COMPARE_PANE_GAP_PX if gap_px is None else max(0, gap_px)
    )
    return min(requested_gap_px, max(0, split_size - 2))


def _compare_pane_gap(
    pane_a: PixelRect,
    pane_b: PixelRect,
    orientation: TemporalCompareOrientation,
) -> int:
    if orientation == TemporalCompareOrientation.HORIZONTAL:
        return max(0, pane_b.top - pane_a.bottom)
    return max(0, pane_b.left - pane_a.right)


def _temporal_compare_pane_gap_px(spec: RenderSpec) -> int:
    value = spec.grid.style.get("temporal_compare_pane_gap_px")
    if isinstance(value, bool):
        return _DEFAULT_TEMPORAL_COMPARE_PANE_GAP_PX
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float) and math.isfinite(value):
        return max(0, int(round(value)))
    if isinstance(value, str):
        try:
            return max(0, int(round(float(value.strip()))))
        except ValueError:
            return _DEFAULT_TEMPORAL_COMPARE_PANE_GAP_PX
    return _DEFAULT_TEMPORAL_COMPARE_PANE_GAP_PX


def _temporal_compare_gap_color(spec: RenderSpec) -> tuple[int, int, int]:
    value = spec.grid.style.get("temporal_compare_gap_color", "#FFFFFF")
    if not isinstance(value, str):
        return (255, 255, 255)
    try:
        return _parse_hex_color(value)
    except ValueError:
        return (255, 255, 255)


def _build_frame_overlay(
    spec: RenderSpec,
    layout: MapSurroundLayout,
    *,
    background: tuple[int, int, int],
    is_cancelled: CancelCallback | None,
) -> tuple[np.ndarray, np.ndarray]:
    base = np.empty((spec.output_height, spec.output_width, 3), dtype=np.uint8)
    base[:, :] = (255, 255, 255)
    inner = layout.inner_map
    base[inner.top : inner.bottom, inner.left : inner.right, :] = background
    pixels = base.copy()
    draw_map_surround_frame(pixels, spec, layout, is_cancelled=is_cancelled)
    mask = np.any(pixels != base, axis=2)
    return pixels, mask
