"""QGraphicsView GIS canvas for Review/Edit view controls."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QRegion
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from thucthengay.gis import pan_center_by_viewport_pixels
from thucthengay.models import Composition, ImageLayer, TemporalCompareOrientation
from thucthengay.render.diagnostics import RenderDiagnostics
from thucthengay.render.frame import MapSurroundLayout, PixelRect, build_map_surround_layout


class GisCanvasState(StrEnum):
    """Display states for the Review/Edit GIS canvas."""

    EMPTY = "empty"
    NO_VISIBLE_LAYER = "no_visible_layer"
    LOADING = "loading"
    ERROR = "error"
    STALE = "stale"
    READY = "ready"


@dataclass(frozen=True)
class RenderRequestToken:
    """Generation token used to reject stale async render results."""

    generation: int
    center: tuple[float, float]
    scale: int


@dataclass
class _InteractiveViewState:
    composition_id: str
    center: list[float]
    scale: int


@dataclass(frozen=True)
class _InteractionTarget:
    composition_id: str
    center: list[float]
    scale: int
    viewport_rect: QRectF
    compare_pane: bool
    pane_key: str | None = None


@dataclass
class _LivePreviewTransform:
    offset_x: float = 0.0
    offset_y: float = 0.0
    zoom: float = 1.0
    pane_offsets: dict[str, tuple[float, float]] = field(default_factory=dict)

    def is_identity(self) -> bool:
        return (
            abs(self.offset_x) < 0.5
            and abs(self.offset_y) < 0.5
            and abs(self.zoom - 1.0) < 0.001
            and all(abs(x) < 0.5 and abs(y) < 0.5 for x, y in self.pane_offsets.values())
        )


class GisCanvasWidget(QGraphicsView):
    """Minimal map canvas that edits persisted view center/scale."""

    viewEditCompleted = Signal(object, int)
    viewInteractionChanged = Signal(object, int)
    compositionViewEditCompleted = Signal(str, object, int)
    comparePaneViewEditCompleted = Signal(str, object)
    comparePaneViewInteractionChanged = Signal(str, object)

    DEFAULT_FRAME_ASPECT = 16 / 9
    EXPORT_DPI = 200
    EXPORT_JPEG_QUALITY = 90
    DISPLAY_IMAGE_MAX_WIDTH = 960
    MAP_FRAME_FILL_RATIO = 0.90
    DEFAULT_MAP_FRAME_WIDTH_POINTS = 640.0
    DEFAULT_MAP_FRAME_HEIGHT_POINTS = 360.0
    MIN_SCALE = 1000
    MAX_SCALE = 20_000_000

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setObjectName("reviewGisCanvas")
        self.setMinimumSize(520, 320)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._composition_id: str | None = None
        self._center: list[float] = [0.0, 0.0]
        self._scale = 50_000
        self._visible_layers: list[ImageLayer] = []
        self._frame_aspect = self.DEFAULT_FRAME_ASPECT
        self._map_frame_width_points = self.DEFAULT_MAP_FRAME_WIDTH_POINTS
        self._map_frame_height_points = self.DEFAULT_MAP_FRAME_HEIGHT_POINTS
        self._state = GisCanvasState.EMPTY
        self._state_message = "Chưa chọn composition."
        self._generation = 0
        self._drag_last_pos: QPoint | None = None
        self._drag_target: _InteractionTarget | None = None
        self._drag_changed = False
        self._last_frame_rect = QRectF()
        self._last_applied_render_label: str | None = None
        self._rendered_pixmap: QPixmap | None = None
        self._rendered_export_image: QImage | None = None
        self._rendered_canvas_size: tuple[int, int] | None = None
        self._render_diagnostics: RenderDiagnostics | None = None
        self._live_preview_transform = _LivePreviewTransform()
        self._live_preview_max_fps = 30
        self._live_redraw_pending = False
        self._live_redraw_timer = QTimer(self)
        self._live_redraw_timer.setSingleShot(True)
        self._live_redraw_timer.timeout.connect(self._flush_live_redraw)
        self._live_static_item: QGraphicsPixmapItem | None = None
        self._live_clip_item: QGraphicsRectItem | None = None
        self._live_raster_item: QGraphicsPixmapItem | None = None
        self._live_overlay_key: tuple[int, int, int, int, int] | None = None
        self._map_surround_style: dict[str, object] = {}
        self._compare_orientation = TemporalCompareOrientation.VERTICAL
        self._compare_panes: dict[str, _InteractiveViewState] = {}
        self._redraw()

    @property
    def composition_id(self) -> str | None:
        return self._composition_id

    @property
    def center(self) -> list[float]:
        return list(self._center)

    @property
    def scale(self) -> int:
        return self._scale

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def last_applied_render_label(self) -> str | None:
        return self._last_applied_render_label

    @property
    def rendered_image_size(self) -> tuple[int, int] | None:
        if self._rendered_pixmap is None:
            return None
        return self._rendered_pixmap.width(), self._rendered_pixmap.height()

    def set_render_diagnostics(self, diagnostics: RenderDiagnostics | None) -> None:
        """Attach an optional diagnostics collector for conversion and paint timings."""
        self._render_diagnostics = diagnostics

    def set_live_preview_max_fps(self, fps: int) -> None:
        self._live_preview_max_fps = int(_clamp(fps, 1, 120))

    def state(self) -> GisCanvasState:
        return self._state

    def state_text(self) -> str:
        return self._state_message

    def frame_aspect(self) -> float:
        if self._last_frame_rect.height() <= 0:
            return self._frame_aspect
        return self._last_frame_rect.width() / self._last_frame_rect.height()

    def visible_layer_count(self) -> int:
        return len(self._visible_layers)

    def map_frame_size_points(self) -> tuple[float, float]:
        return self._map_frame_width_points, self._map_frame_height_points

    def compare_pane_centers(self) -> dict[str, list[float]]:
        return {key: list(pane.center) for key, pane in self._compare_panes.items()}

    def render_output_size(self) -> tuple[int, int]:
        """Return the pixel size that should be rendered for the visible map frame."""
        frame = self._frame_rect()
        return max(1, int(frame.width())), max(1, int(frame.height()))

    def export_displayed_image(self, output_path: str | Path) -> bool:
        """Save the current rendered map image, excluding the editor scene chrome."""
        if self._rendered_export_image is None:
            return False
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image = self._rendered_export_image.convertToFormat(QImage.Format.Format_RGB888)
        dots_per_meter = round(self.EXPORT_DPI / 0.0254)
        image.setDotsPerMeterX(dots_per_meter)
        image.setDotsPerMeterY(dots_per_meter)
        return image.save(str(path), "JPG", self.EXPORT_JPEG_QUALITY)

    def set_frame_aspect(self, aspect: float) -> None:
        """Set map-frame aspect from template metadata when available."""
        if not isfinite(aspect) or aspect <= 0:
            return
        self._frame_aspect = aspect
        self._redraw()

    def set_map_frame_size(self, width_points: float, height_points: float) -> None:
        """Set the PPT map-frame size used to convert drag pixels into ground distance."""
        if not isfinite(width_points) or not isfinite(height_points):
            return
        if width_points <= 0 or height_points <= 0:
            return
        self._map_frame_width_points = float(width_points)
        self._map_frame_height_points = float(height_points)
        self._frame_aspect = self._map_frame_width_points / self._map_frame_height_points
        self._redraw()

    def set_map_surround_style(self, style: Mapping[str, object] | None) -> None:
        """Set frame layout style used to locate the rendered inner map on screen."""
        self._map_surround_style = dict(style or {})
        self._redraw()

    def set_composition(
        self,
        composition: Composition | None,
        *,
        preserve_render: bool = False,
    ) -> None:
        """Load the selected composition into the canvas without emitting edits."""
        previous_composition_id = self._composition_id
        previous_visible_layers = _visible_layer_signature(self._visible_layers)
        previous_compare_context = _compare_context_signature(
            self._compare_panes,
            self._compare_orientation,
        )
        previous_pixmap = self._rendered_pixmap
        previous_canvas_size = self._rendered_canvas_size
        previous_live_transform = self._live_preview_transform

        self._last_applied_render_label = None
        self._rendered_export_image = None
        if composition is None:
            self._composition_id = None
            self._visible_layers = []
            self._clear_compare_context()
            self._rendered_pixmap = None
            self._rendered_canvas_size = None
            self._reset_live_preview_transform()
            self._state = GisCanvasState.EMPTY
            self._state_message = "Chưa chọn composition."
            self._bump_generation()
            self._redraw()
            return

        self._composition_id = composition.composition_id
        self._center = list(composition.view.center)
        self._scale = composition.view.scale
        visible_layers = sorted(
            (layer for layer in composition.layers if layer.visible),
            key=lambda layer: (layer.order, layer.layer_id),
        )
        should_preserve_render = (
            preserve_render
            and previous_composition_id == composition.composition_id
            and previous_pixmap is not None
            and previous_visible_layers == _visible_layer_signature(visible_layers)
            and previous_compare_context == _composition_compare_signature(composition)
        )
        self._visible_layers = visible_layers
        if should_preserve_render:
            self._rendered_pixmap = previous_pixmap
            self._rendered_canvas_size = previous_canvas_size
            self._live_preview_transform = previous_live_transform
        else:
            self._clear_compare_context()
            self._rendered_pixmap = None
            self._rendered_canvas_size = None
            self._reset_live_preview_transform()
        if not self._visible_layers:
            self._state = GisCanvasState.NO_VISIBLE_LAYER
            self._state_message = "Không có layer đang bật để hiển thị trên canvas."
        elif composition.needs_revalidation:
            self._state = GisCanvasState.STALE
            self._state_message = "Canvas đã tải. Preview cần cập nhật sau thay đổi view."
        else:
            self._state = GisCanvasState.READY
            self._state_message = "Canvas đã tải layer hiển thị."
        self._bump_generation()
        self._redraw()

    def set_compare_context(
        self,
        composition: Composition,
        *,
        pane_a: Composition | None,
        pane_b: Composition | None,
    ) -> None:
        """Set editable pane view state for temporal comparison interactions."""
        state = composition.temporal_compare
        if (
            not state.enabled
            or pane_a is None
            or pane_b is None
            or not state.pane_a_composition_id
            or not state.pane_b_composition_id
        ):
            self._clear_compare_context()
            return
        self._compare_orientation = state.orientation
        self._compare_panes = {
            "A": _InteractiveViewState(
                composition_id=pane_a.composition_id,
                center=list(state.pane_a_center or pane_a.view.center),
                scale=self._scale,
            ),
            "B": _InteractiveViewState(
                composition_id=pane_b.composition_id,
                center=list(state.pane_b_center or pane_b.view.center),
                scale=self._scale,
            ),
        }

    def set_loading(self, message: str = "Đang render canvas...") -> RenderRequestToken:
        """Mark the canvas loading and return the current render token."""
        self._state = GisCanvasState.LOADING
        self._state_message = message
        token = self.begin_render_request()
        if self._rendered_pixmap is None:
            self._redraw()
        return token

    def set_error(self, message: str) -> None:
        self._state = GisCanvasState.ERROR
        self._state_message = message
        self._redraw()

    def begin_render_request(self) -> RenderRequestToken:
        """Capture the current generation and view for async render application."""
        return RenderRequestToken(
            generation=self._generation,
            center=(self._center[0], self._center[1]),
            scale=self._scale,
        )

    def apply_render_result(
        self,
        token: RenderRequestToken,
        label: str,
        canvas: np.ndarray | None = None,
    ) -> bool:
        """Apply a render result only if it matches the latest view generation."""
        current = self.begin_render_request()
        if token != current:
            return False

        if canvas is not None:
            self._rendered_export_image = _numpy_to_image(
                canvas,
                diagnostics=self._render_diagnostics,
            )
            self._rendered_canvas_size = (int(canvas.shape[1]), int(canvas.shape[0]))
            self._rendered_pixmap = _image_to_pixmap(
                self._rendered_export_image,
                max_width=self.DISPLAY_IMAGE_MAX_WIDTH,
                diagnostics=self._render_diagnostics,
            )
        self._reset_live_preview_transform()
        self._state = GisCanvasState.READY
        self._state_message = f"Canvas đã cập nhật: {label}"
        self._last_applied_render_label = label
        self._redraw()
        return True

    def pan_by_pixels(self, dx: float, dy: float, *, emit: bool = True) -> None:
        """Pan the view center by a viewport-space pixel delta."""
        if self._composition_id is None:
            return
        frame = self._frame_rect()
        self._center = self._panned_center(
            center=self._center,
            scale=self._scale,
            viewport_rect=frame,
            dx=dx,
            dy=dy,
        )
        self._note_live_pan(dx, dy)
        self._mark_interaction_stale()
        self.viewInteractionChanged.emit(list(self._center), self._scale)
        if emit:
            self._emit_view_edit()
        self._request_live_redraw()

    def zoom_by_factor(self, factor: float, *, emit: bool = True) -> None:
        """Zoom the view by changing the scale denominator."""
        if self._composition_id is None or not isfinite(factor) or factor <= 0:
            return
        scale = int(round(self._scale * factor))
        self._scale = int(_clamp(scale, self.MIN_SCALE, self.MAX_SCALE))
        self._note_live_zoom(factor)
        self._mark_interaction_stale()
        self.viewInteractionChanged.emit(list(self._center), self._scale)
        if emit:
            self._emit_view_edit()
        self._request_live_redraw()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._redraw()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.MouseButton.LeftButton and self._composition_id is not None:
            self._begin_drag_at(event.pos())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._drag_last_pos is not None:
            self._move_drag_to(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag_last_pos is not None:
            self._end_drag()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._composition_id is None:
            super().wheelEvent(event)
            return
        factor = 0.85 if event.angleDelta().y() > 0 else 1.15
        if self._compare_panes:
            self.zoom_by_factor(factor)
        else:
            self._zoom_interaction_target(
                self._interaction_target_at(event.position()),
                factor,
            )
        event.accept()

    def _emit_view_edit(self) -> None:
        self.viewEditCompleted.emit(list(self._center), self._scale)

    def _clear_compare_context(self) -> None:
        self._compare_panes = {}

    def _begin_drag_at(self, pos: QPoint) -> None:
        self._drag_last_pos = pos
        self._drag_target = self._interaction_target_at(pos)
        self._drag_changed = False

    def _move_drag_to(self, pos: QPoint) -> None:
        if self._drag_last_pos is None or self._drag_target is None:
            return
        delta = pos - self._drag_last_pos
        if not delta.x() and not delta.y():
            return
        target = self._drag_target
        center = self._panned_center(
            center=target.center,
            scale=target.scale,
            viewport_rect=target.viewport_rect,
            dx=delta.x(),
            dy=delta.y(),
        )
        self._drag_target = _InteractionTarget(
            composition_id=target.composition_id,
            center=center,
            scale=target.scale,
            viewport_rect=target.viewport_rect,
            compare_pane=target.compare_pane,
            pane_key=target.pane_key,
        )
        self._apply_interaction_view_state(self._drag_target)
        self._note_live_pan(delta.x(), delta.y(), pane_key=target.pane_key)
        self._emit_interaction_view_changed(self._drag_target)
        self._drag_last_pos = pos
        self._drag_changed = True
        self._mark_interaction_stale()
        self._request_live_redraw()

    def _end_drag(self) -> None:
        target = self._drag_target
        changed = self._drag_changed
        self._drag_last_pos = None
        self._drag_target = None
        self._drag_changed = False
        if target is not None and changed:
            self._emit_interaction_view_edit(target)

    def _zoom_interaction_target(self, target: _InteractionTarget, factor: float) -> None:
        if not isfinite(factor) or factor <= 0:
            return
        scale = int(round(target.scale * factor))
        updated = _InteractionTarget(
            composition_id=target.composition_id,
            center=list(target.center),
            scale=int(_clamp(scale, self.MIN_SCALE, self.MAX_SCALE)),
            viewport_rect=target.viewport_rect,
            compare_pane=target.compare_pane,
            pane_key=target.pane_key,
        )
        self._apply_interaction_view_state(updated)
        self._note_live_zoom(factor)
        self._mark_interaction_stale()
        self._emit_interaction_view_changed(updated)
        self._emit_interaction_view_edit(updated)
        self._request_live_redraw()

    def _interaction_target_at(self, pos: QPoint | QPointF) -> _InteractionTarget:
        pane_key, pane_rect = self._compare_pane_at(pos)
        if pane_key is not None and pane_rect is not None:
            pane = self._compare_panes[pane_key]
            return _InteractionTarget(
                composition_id=pane.composition_id,
                center=list(pane.center),
                scale=self._scale,
                viewport_rect=pane_rect,
                compare_pane=True,
                pane_key=pane_key,
            )
        return _InteractionTarget(
            composition_id=self._composition_id or "",
            center=list(self._center),
            scale=self._scale,
            viewport_rect=self._frame_rect(),
            compare_pane=False,
            pane_key=None,
        )

    def _compare_pane_at(self, pos: QPoint | QPointF) -> tuple[str | None, QRectF | None]:
        if set(self._compare_panes) != {"A", "B"}:
            return None, None
        frame = self._frame_rect()
        point = QPointF(pos)
        if not frame.contains(point):
            return None, None
        inner = self._display_inner_map_rect(frame)
        if not inner.contains(point):
            return None, None
        pane_a, pane_b = self._compare_pane_rects(inner)
        if pane_a.contains(point):
            return "A", pane_a
        if pane_b.contains(point):
            return "B", pane_b
        return None, None

    def _compare_pane_rects(self, frame: QRectF) -> tuple[QRectF, QRectF]:
        return _split_compare_rect(
            frame,
            self._compare_orientation,
            gap_px=_temporal_compare_pane_gap_px(self._map_surround_style),
        )

    def _panned_center(
        self,
        *,
        center: list[float],
        scale: int,
        viewport_rect: QRectF,
        dx: float,
        dy: float,
    ) -> list[float]:
        lon, lat = pan_center_by_viewport_pixels(
            center_lon=center[0],
            center_lat=center[1],
            scale_denom=scale,
            map_frame_width_points=self._map_frame_width_points,
            map_frame_height_points=self._map_frame_height_points,
            viewport_width_px=max(viewport_rect.width(), 1.0),
            viewport_height_px=max(viewport_rect.height(), 1.0),
            dx_px=dx,
            dy_px=dy,
        )
        return [round(lon, 8), round(lat, 8)]

    def _apply_interaction_view_state(self, target: _InteractionTarget) -> None:
        if target.compare_pane:
            if target.pane_key is not None and target.pane_key in self._compare_panes:
                pane = self._compare_panes[target.pane_key]
                pane.center = list(target.center)
                pane.scale = target.scale
        elif target.composition_id == self._composition_id:
            self._center = list(target.center)
            self._scale = target.scale

    def _emit_interaction_view_edit(self, target: _InteractionTarget) -> None:
        if target.compare_pane:
            if target.pane_key is not None:
                self.comparePaneViewEditCompleted.emit(target.pane_key, list(target.center))
            return
        self.viewEditCompleted.emit(list(target.center), target.scale)

    def _emit_interaction_view_changed(self, target: _InteractionTarget) -> None:
        if target.compare_pane:
            if target.pane_key is not None:
                self.comparePaneViewInteractionChanged.emit(
                    target.pane_key,
                    list(target.center),
                )
            return
        self.viewInteractionChanged.emit(list(target.center), target.scale)

    def _mark_interaction_stale(self) -> None:
        if self._visible_layers:
            self._state = GisCanvasState.STALE
            self._state_message = "View đã thay đổi. Preview cần cập nhật."
        else:
            self._state = GisCanvasState.NO_VISIBLE_LAYER
            self._state_message = "Không có layer đang bật để hiển thị trên canvas."
        self._last_applied_render_label = None
        # Keep the display pixmap available for immediate pan/zoom feedback. The
        # export image is cleared because it no longer matches the current view.
        self._rendered_export_image = None
        self._bump_generation()

    def _note_live_pan(self, dx: float, dy: float, *, pane_key: str | None = None) -> None:
        if self._rendered_pixmap is None:
            return
        if pane_key is None:
            self._live_preview_transform.offset_x += dx
            self._live_preview_transform.offset_y += dy
            return
        current_x, current_y = self._live_preview_transform.pane_offsets.get(
            pane_key,
            (0.0, 0.0),
        )
        self._live_preview_transform.pane_offsets[pane_key] = (
            current_x + dx,
            current_y + dy,
        )

    def _note_live_zoom(self, factor: float) -> None:
        if self._rendered_pixmap is None or not isfinite(factor) or factor <= 0:
            return
        self._live_preview_transform.zoom /= factor

    def _reset_live_preview_transform(self) -> None:
        self._live_preview_transform = _LivePreviewTransform()

    def _bump_generation(self) -> None:
        self._generation += 1

    def _redraw(self) -> None:
        self._live_redraw_pending = False
        self._live_redraw_timer.stop()
        self._discard_live_preview_items()
        diagnostics = self._render_diagnostics
        with diagnostics.time("qt.paint_composite") if diagnostics is not None else nullcontext():
            self._scene.clear()
            width = max(self.viewport().width(), 640)
            height = max(self.viewport().height(), 360)
            self._scene.setSceneRect(0, 0, width, height)
            self._scene.setBackgroundBrush(QColor("#242a31"))

            frame = self._frame_rect()
            self._draw_layers(frame)
            if self._rendered_pixmap is None:
                self._draw_frame(frame)
                self._draw_state_text(width)

    def _request_live_redraw(self) -> None:
        if self._live_redraw_pending:
            return
        self._live_redraw_pending = True
        interval_ms = max(1, round(1000 / max(1, self._live_preview_max_fps)))
        self._live_redraw_timer.start(interval_ms)

    def _flush_live_redraw(self) -> None:
        if not self._live_redraw_pending:
            return
        self._live_redraw_pending = False
        if self._update_fast_live_preview_items():
            return
        self._redraw()

    def _discard_live_preview_items(self) -> None:
        self._live_static_item = None
        self._live_clip_item = None
        self._live_raster_item = None
        self._live_overlay_key = None

    def _update_fast_live_preview_items(self) -> bool:
        if (
            self._rendered_pixmap is None
            or self._live_static_item is None
            or self._compare_panes
            or self._live_preview_transform.is_identity()
        ):
            return False
        frame = self._frame_rect()
        width = max(1, int(round(frame.width())))
        height = max(1, int(round(frame.height())))
        base = self._rendered_pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        local_base_rect = _centered_pixmap_rect(base, width=width, height=height)
        base_rect = local_base_rect.translated(frame.topLeft())
        raster_rect = self._display_inner_raster_rect(base_rect)
        raster_source_rect = _relative_rect(raster_rect, base_rect)
        key = (
            int(round(frame.left())),
            int(round(frame.top())),
            width,
            height,
            int(self._rendered_pixmap.cacheKey()),
        )
        if (
            self._live_clip_item is None
            or self._live_raster_item is None
            or self._live_overlay_key != key
        ):
            self._live_overlay_key = key
            static = _static_preview_pixmap(
                base,
                width,
                height,
                local_base_rect,
                (_relative_rect(raster_rect, frame),),
            )
            self._live_static_item.setPixmap(static)
            if self._live_clip_item is not None:
                self._scene.removeItem(self._live_clip_item)
            self._live_clip_item = self._scene.addRect(
                raster_rect,
                QPen(Qt.PenStyle.NoPen),
                QColor(0, 0, 0, 0),
            )
            self._live_clip_item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape,
                True,
            )
            self._live_clip_item.setZValue(10)
            self._live_raster_item = QGraphicsPixmapItem(
                base.copy(_to_qrect(raster_source_rect)),
                self._live_clip_item,
            )
            self._live_raster_item.setTransformationMode(
                Qt.TransformationMode.FastTransformation
            )
        else:
            self._live_clip_item.setRect(raster_rect)
            self._live_raster_item.setPixmap(base.copy(_to_qrect(raster_source_rect)))

        dest = _scaled_destination_rect(
            raster_rect,
            zoom=self._live_preview_transform.zoom,
            offset_x=self._live_preview_transform.offset_x,
            offset_y=self._live_preview_transform.offset_y,
        )
        zoom = max(0.001, self._live_preview_transform.zoom)
        self._live_raster_item.setScale(zoom)
        self._live_raster_item.setPos(dest.left(), dest.top())
        return True

    def _displayed_image(self) -> QImage:
        scene_rect = self._scene.sceneRect()
        width = max(1, int(scene_rect.width()))
        height = max(1, int(scene_rect.height()))
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#242a31"))
        painter = QPainter(image)
        try:
            diagnostics = self._render_diagnostics
            with diagnostics.time("qt.scene_render") if diagnostics is not None else nullcontext():
                self._scene.render(
                    painter,
                    QRectF(0, 0, width, height),
                    scene_rect,
                )
        finally:
            painter.end()
        return image

    def _frame_rect(self) -> QRectF:
        width = max(self.viewport().width(), 640)
        height = max(self.viewport().height(), 360)
        frame_width = width * self.MAP_FRAME_FILL_RATIO
        frame_height = frame_width / self._frame_aspect
        if frame_height > height * self.MAP_FRAME_FILL_RATIO:
            frame_height = height * self.MAP_FRAME_FILL_RATIO
            frame_width = frame_height * self._frame_aspect
        x = (width - frame_width) / 2
        y = (height - frame_height) / 2
        self._last_frame_rect = QRectF(x, y, frame_width, frame_height)
        return self._last_frame_rect

    def _draw_layers(self, frame: QRectF) -> None:
        if not self._visible_layers:
            return
        if self._rendered_pixmap is not None:
            scaled = self._live_preview_pixmap(frame)
            px = frame.x()
            py = frame.y()
            item = self._scene.addPixmap(scaled)
            item.setPos(px, py)
            if not self._compare_panes:
                self._live_static_item = item
            return
        colors = ["#637f5f", "#7d8e9c", "#8e7d58", "#596a84"]
        base_rect = frame.adjusted(-54, -34, 54, 34)
        for index, layer in enumerate(self._visible_layers):
            offset = QPointF(index * 10, index * 7)
            rect = base_rect.translated(offset)
            item = self._scene.addRect(
                rect,
                QPen(QColor("#303840"), 1),
                QColor(colors[index % len(colors)]),
            )
            item.setOpacity(0.58)
            label = self._scene.addText(_short_layer_name(layer))
            label.setDefaultTextColor(QColor("#f4f7fb"))
            label.setPos(rect.left() + 12, rect.top() + 10 + index * 18)

    def _live_preview_pixmap(self, frame: QRectF) -> QPixmap:
        width = max(1, int(round(frame.width())))
        height = max(1, int(round(frame.height())))
        base = self._rendered_pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        base_rect = _centered_pixmap_rect(base, width=width, height=height)
        transform = self._live_preview_transform
        output = QPixmap(width, height)
        output.fill(Qt.GlobalColor.transparent)
        painter = QPainter(output)
        try:
            if transform.is_identity():
                painter.drawPixmap(base_rect.topLeft(), base)
            else:
                if self._compare_panes:
                    self._paint_live_compare_preview(
                        painter,
                        base,
                        width,
                        height,
                        base_rect,
                        transform,
                    )
                else:
                    raster_rect = self._display_inner_raster_rect(base_rect)
                    self._paint_live_raster_preview(
                        painter,
                        base,
                        width,
                        height,
                        base_rect,
                        raster_rect,
                        transform,
                    )
        finally:
            painter.end()
        return output

    def _display_inner_map_rect(self, base_rect: QRectF) -> QRectF:
        layout, source_width, source_height = self._source_layout_for_display(base_rect)
        return _scale_source_rect(layout.inner_map, base_rect, source_width, source_height)

    def _display_inner_raster_rect(self, base_rect: QRectF) -> QRectF:
        layout, source_width, source_height = self._source_layout_for_display(base_rect)
        inner = layout.inner_map
        stroke_width = _positive_int_setting(
            self._map_surround_style,
            "surround_inner_stroke_width",
            fallback=4,
        )
        scale_x = base_rect.width() / max(1, source_width)
        scale_y = base_rect.height() / max(1, source_height)
        inner_width = inner.width * scale_x
        inner_height = inner.height * scale_y
        # The rendered pixmap already contains the coordinate frame. Keep the
        # inner border in the static layer so only raster pixels move live.
        inset_x = min(
            inner_width / 2,
            (stroke_width + 1) * scale_x,
        )
        inset_y = min(
            inner_height / 2,
            (stroke_width + 1) * scale_y,
        )
        return QRectF(
            base_rect.left() + (inner.left * scale_x) + inset_x,
            base_rect.top() + (inner.top * scale_y) + inset_y,
            max(1.0, inner_width - inset_x * 2),
            max(1.0, inner_height - inset_y * 2),
        )

    def _source_layout_for_display(
        self,
        base_rect: QRectF,
    ) -> tuple[MapSurroundLayout, int, int]:
        if self._rendered_canvas_size is None:
            source_width = max(1, int(round(base_rect.width())))
            source_height = max(1, int(round(base_rect.height())))
        else:
            source_width, source_height = self._rendered_canvas_size
        layout = build_map_surround_layout(
            source_width,
            source_height,
            self._map_surround_style,
        )
        return layout, source_width, source_height

    def _display_compare_pane_rects(
        self,
        base_rect: QRectF,
    ) -> tuple[QRectF, QRectF]:
        layout, source_width, source_height = self._source_layout_for_display(base_rect)
        source_inner = _pixel_rect_to_qrectf(layout.inner_map)
        source_pane_a, source_pane_b = _split_compare_rect(
            source_inner,
            self._compare_orientation,
            gap_px=_temporal_compare_pane_gap_px(self._map_surround_style),
        )
        return (
            _scale_source_qrect(source_pane_a, base_rect, source_width, source_height),
            _scale_source_qrect(source_pane_b, base_rect, source_width, source_height),
        )

    def _paint_live_raster_preview(
        self,
        painter: QPainter,
        base: QPixmap,
        width: int,
        height: int,
        base_rect: QRectF,
        inner_rect: QRectF,
        transform: _LivePreviewTransform,
    ) -> None:
        _draw_static_preview_regions(
            painter,
            base,
            width,
            height,
            base_rect,
            (inner_rect,),
        )
        painter.save()
        try:
            painter.setClipRect(_to_qrect(inner_rect))
            dest = _scaled_destination_rect(
                inner_rect,
                zoom=transform.zoom,
                offset_x=transform.offset_x,
                offset_y=transform.offset_y,
            )
            painter.drawPixmap(dest, base, _relative_rect(inner_rect, base_rect))
        finally:
            painter.restore()

    def _paint_live_compare_preview(
        self,
        painter: QPainter,
        base: QPixmap,
        width: int,
        height: int,
        base_rect: QRectF,
        transform: _LivePreviewTransform,
    ) -> None:
        pane_a, pane_b = self._display_compare_pane_rects(base_rect)
        _draw_static_preview_regions(
            painter,
            base,
            width,
            height,
            base_rect,
            (pane_a, pane_b),
        )
        for pane_key, pane_rect in (("A", pane_a), ("B", pane_b)):
            painter.save()
            try:
                painter.setClipRect(_to_qrect(pane_rect))
                pane_dx, pane_dy = transform.pane_offsets.get(pane_key, (0.0, 0.0))
                dest = _scaled_destination_rect(
                    pane_rect,
                    zoom=transform.zoom,
                    offset_x=transform.offset_x + pane_dx,
                    offset_y=transform.offset_y + pane_dy,
                )
                painter.drawPixmap(dest, base, _relative_rect(pane_rect, base_rect))
            finally:
                painter.restore()

    def _draw_frame(self, frame: QRectF) -> None:
        shadow_pen = QPen(QColor(0, 0, 0, 110), 34)
        self._scene.addRect(frame, shadow_pen, QColor(0, 0, 0, 0))
        frame_pen = QPen(QColor("#e8f3ff"), 2)
        self._scene.addRect(frame, frame_pen, QColor(0, 0, 0, 0))
        grid_pen = QPen(QColor(255, 255, 255, 70), 1)
        for column in range(1, 4):
            x = frame.left() + frame.width() * column / 4
            self._scene.addLine(x, frame.top(), x, frame.bottom(), grid_pen)
        for row in range(1, 3):
            y = frame.top() + frame.height() * row / 3
            self._scene.addLine(frame.left(), y, frame.right(), y, grid_pen)

    def _draw_state_text(self, width: int) -> None:
        text = (
            f"{self._state_message}\n"
            f"Center: {self._center[0]:.6f}, {self._center[1]:.6f} | "
            f"Scale 1:{self._scale:,} | Rotation 0"
        )
        item = self._scene.addText(text)
        item.setDefaultTextColor(QColor("#ffffff"))
        item.setTextWidth(width - 40)
        item.setPos(20, 16)


def _short_layer_name(layer: ImageLayer) -> str:
    path = layer.cache_path or layer.source_path
    name = path.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1]
    return name if len(name) <= 42 else f"{name[:18]}...{name[-18:]}"


def _visible_layer_signature(layers: list[ImageLayer]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            layer.layer_id,
            layer.source_path,
            layer.cache_path,
            layer.visible,
            layer.order,
        )
        for layer in layers
    )


def _compare_context_signature(
    panes: dict[str, _InteractiveViewState],
    orientation: TemporalCompareOrientation,
) -> tuple[object, ...]:
    if set(panes) != {"A", "B"}:
        return (False,)
    pane_a = panes["A"]
    pane_b = panes["B"]
    return (
        True,
        orientation,
        pane_a.composition_id,
        pane_b.composition_id,
        _center_signature(pane_a.center),
        _center_signature(pane_b.center),
    )


def _composition_compare_signature(composition: Composition) -> tuple[object, ...]:
    state = composition.temporal_compare
    if (
        not state.enabled
        or not state.pane_a_composition_id
        or not state.pane_b_composition_id
    ):
        return (False,)
    return (
        True,
        state.orientation,
        state.pane_a_composition_id,
        state.pane_b_composition_id,
        _center_signature(state.pane_a_center),
        _center_signature(state.pane_b_center),
    )


def _center_signature(center: list[float] | None) -> tuple[float, float] | None:
    if center is None or len(center) < 2:
        return None
    return (round(float(center[0]), 8), round(float(center[1]), 8))


def _numpy_to_image(
    canvas: np.ndarray,
    *,
    diagnostics: RenderDiagnostics | None = None,
) -> QImage:
    height, width = canvas.shape[:2]
    with diagnostics.time("qt.qimage_conversion") if diagnostics is not None else nullcontext():
        if canvas.ndim == 2:
            image = QImage(canvas.data, width, height, width, QImage.Format.Format_Grayscale8)
        elif canvas.shape[2] == 3:
            rgb = np.ascontiguousarray(canvas)
            image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
        else:
            rgba = np.ascontiguousarray(canvas[:, :, :4])
            image = QImage(
                rgba.data, width, height, 4 * width, QImage.Format.Format_RGBA8888
            )
        owned = image.copy()
    return owned


def _image_to_pixmap(
    image: QImage,
    *,
    max_width: int | None = None,
    diagnostics: RenderDiagnostics | None = None,
) -> QPixmap:
    with diagnostics.time("qt.qpixmap_conversion") if diagnostics is not None else nullcontext():
        display = image
        if max_width is not None and max_width > 0 and image.width() > max_width:
            scaled_height = max(1, int(round(image.height() * max_width / image.width())))
            display = image.scaled(
                max_width,
                scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return QPixmap.fromImage(display)


def _scaled_destination_rect(
    rect: QRectF,
    *,
    zoom: float,
    offset_x: float,
    offset_y: float,
) -> QRectF:
    scaled_width = rect.width() * zoom
    scaled_height = rect.height() * zoom
    x = rect.left() + (rect.width() - scaled_width) / 2 + offset_x
    y = rect.top() + (rect.height() - scaled_height) / 2 + offset_y
    return QRectF(x, y, scaled_width, scaled_height)


def _centered_pixmap_rect(pixmap: QPixmap, *, width: int, height: int) -> QRectF:
    x = (width - pixmap.width()) / 2
    y = (height - pixmap.height()) / 2
    return QRectF(x, y, pixmap.width(), pixmap.height())


def _scale_source_rect(
    rect: PixelRect,
    base_rect: QRectF,
    source_width: int,
    source_height: int,
) -> QRectF:
    return QRectF(
        base_rect.left() + rect.left * base_rect.width() / source_width,
        base_rect.top() + rect.top * base_rect.height() / source_height,
        rect.width * base_rect.width() / source_width,
        rect.height * base_rect.height() / source_height,
    )


def _scale_source_qrect(
    rect: QRectF,
    base_rect: QRectF,
    source_width: int,
    source_height: int,
) -> QRectF:
    return QRectF(
        base_rect.left() + rect.left() * base_rect.width() / source_width,
        base_rect.top() + rect.top() * base_rect.height() / source_height,
        rect.width() * base_rect.width() / source_width,
        rect.height() * base_rect.height() / source_height,
    )


def _pixel_rect_to_qrectf(rect: PixelRect) -> QRectF:
    return QRectF(rect.left, rect.top, rect.width, rect.height)


def _split_compare_rect(
    rect: QRectF,
    orientation: TemporalCompareOrientation,
    *,
    gap_px: float,
) -> tuple[QRectF, QRectF]:
    split_size = (
        rect.height() if orientation == TemporalCompareOrientation.HORIZONTAL else rect.width()
    )
    gap = min(max(0.0, gap_px), max(0.0, split_size - 2.0))
    if orientation == TemporalCompareOrientation.HORIZONTAL:
        pane_height = (rect.height() - gap) / 2.0
        pane_b_top = rect.top() + pane_height + gap
        return (
            QRectF(rect.left(), rect.top(), rect.width(), pane_height),
            QRectF(rect.left(), pane_b_top, rect.width(), rect.bottom() - pane_b_top),
        )

    pane_width = (rect.width() - gap) / 2.0
    pane_b_left = rect.left() + pane_width + gap
    return (
        QRectF(rect.left(), rect.top(), pane_width, rect.height()),
        QRectF(pane_b_left, rect.top(), rect.right() - pane_b_left, rect.height()),
    )


def _temporal_compare_pane_gap_px(style: Mapping[str, object]) -> float:
    value = style.get("temporal_compare_pane_gap_px")
    if isinstance(value, bool):
        return 8.0
    if isinstance(value, int | float) and isfinite(float(value)):
        return max(0.0, float(value))
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return 8.0
        return max(0.0, parsed) if isfinite(parsed) else 8.0
    return 8.0


def _relative_rect(rect: QRectF, origin: QRectF) -> QRectF:
    return QRectF(
        rect.left() - origin.left(),
        rect.top() - origin.top(),
        rect.width(),
        rect.height(),
    )


def _draw_static_preview_regions(
    painter: QPainter,
    base: QPixmap,
    width: int,
    height: int,
    base_rect: QRectF,
    dynamic_rects: tuple[QRectF, ...],
) -> None:
    static_region = QRegion(0, 0, width, height)
    for rect in dynamic_rects:
        static_region = static_region.subtracted(QRegion(_to_qrect(rect)))
    painter.save()
    try:
        painter.setClipRegion(static_region)
        painter.drawPixmap(base_rect.topLeft(), base)
    finally:
        painter.restore()


def _static_preview_pixmap(
    base: QPixmap,
    width: int,
    height: int,
    base_rect: QRectF,
    dynamic_rects: tuple[QRectF, ...],
) -> QPixmap:
    output = QPixmap(width, height)
    output.fill(Qt.GlobalColor.transparent)
    painter = QPainter(output)
    try:
        _draw_static_preview_regions(
            painter,
            base,
            width,
            height,
            base_rect,
            dynamic_rects,
        )
    finally:
        painter.end()
    return output


def _positive_int_setting(
    settings: Mapping[str, object],
    key: str,
    *,
    fallback: int,
) -> int:
    value = settings.get(key)
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int | float) and isfinite(float(value)):
        return max(0, int(round(float(value))))
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return fallback
        if isfinite(parsed):
            return max(0, int(round(parsed)))
    return fallback


def _to_qrect(rect: QRectF) -> QRect:
    return QRect(
        int(round(rect.left())),
        int(round(rect.top())),
        max(1, int(round(rect.width()))),
        max(1, int(round(rect.height()))),
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
