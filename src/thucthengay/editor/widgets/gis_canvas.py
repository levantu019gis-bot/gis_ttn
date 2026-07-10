"""QGraphicsView GIS canvas for Review/Edit view controls."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from thucthengay.gis import pan_center_by_viewport_pixels
from thucthengay.models import Composition, ImageLayer, TemporalCompareOrientation
from thucthengay.render.diagnostics import RenderDiagnostics


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
        self._render_diagnostics: RenderDiagnostics | None = None
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

    def set_composition(self, composition: Composition | None) -> None:
        """Load the selected composition into the canvas without emitting edits."""
        self._last_applied_render_label = None
        self._rendered_pixmap = None
        self._rendered_export_image = None
        self._clear_compare_context()
        if composition is None:
            self._composition_id = None
            self._visible_layers = []
            self._state = GisCanvasState.EMPTY
            self._state_message = "Chưa chọn composition."
            self._bump_generation()
            self._redraw()
            return

        self._composition_id = composition.composition_id
        self._center = list(composition.view.center)
        self._scale = composition.view.scale
        self._visible_layers = sorted(
            (layer for layer in composition.layers if layer.visible),
            key=lambda layer: (layer.order, layer.layer_id),
        )
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
            self._rendered_pixmap = _image_to_pixmap(
                self._rendered_export_image,
                max_width=self.DISPLAY_IMAGE_MAX_WIDTH,
                diagnostics=self._render_diagnostics,
            )
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
        self._mark_interaction_stale()
        self.viewInteractionChanged.emit(list(self._center), self._scale)
        if emit:
            self._emit_view_edit()
        self._redraw()

    def zoom_by_factor(self, factor: float, *, emit: bool = True) -> None:
        """Zoom the view by changing the scale denominator."""
        if self._composition_id is None or not isfinite(factor) or factor <= 0:
            return
        scale = int(round(self._scale * factor))
        self._scale = int(_clamp(scale, self.MIN_SCALE, self.MAX_SCALE))
        self._mark_interaction_stale()
        self.viewInteractionChanged.emit(list(self._center), self._scale)
        if emit:
            self._emit_view_edit()
        self._redraw()

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
        self._emit_interaction_view_changed(self._drag_target)
        self._drag_last_pos = pos
        self._drag_changed = True
        self._mark_interaction_stale()
        self._redraw()

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
        self._mark_interaction_stale()
        self._emit_interaction_view_changed(updated)
        self._emit_interaction_view_edit(updated)
        self._redraw()

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
        pane_a, pane_b = self._compare_pane_rects(frame)
        if pane_a.contains(point):
            return "A", pane_a
        if pane_b.contains(point):
            return "B", pane_b
        return None, None

    def _compare_pane_rects(self, frame: QRectF) -> tuple[QRectF, QRectF]:
        if self._compare_orientation == TemporalCompareOrientation.HORIZONTAL:
            half_height = frame.height() / 2
            return (
                QRectF(frame.left(), frame.top(), frame.width(), half_height),
                QRectF(frame.left(), frame.top() + half_height, frame.width(), half_height),
            )
        half_width = frame.width() / 2
        return (
            QRectF(frame.left(), frame.top(), half_width, frame.height()),
            QRectF(frame.left() + half_width, frame.top(), half_width, frame.height()),
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
        self._rendered_pixmap = None
        self._rendered_export_image = None
        self._bump_generation()

    def _bump_generation(self) -> None:
        self._generation += 1

    def _redraw(self) -> None:
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
            scaled = self._rendered_pixmap.scaled(
                int(frame.width()),
                int(frame.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            px = frame.x() + (frame.width() - scaled.width()) / 2
            py = frame.y() + (frame.height() - scaled.height()) / 2
            self._scene.addPixmap(scaled).setPos(px, py)
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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
