"""QGraphicsView GIS canvas for Review/Edit view controls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from thucthengay.models import Composition, ImageLayer


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


class GisCanvasWidget(QGraphicsView):
    """Minimal map canvas that edits persisted view center/scale."""

    viewEditCompleted = Signal(object, int)

    DEFAULT_FRAME_ASPECT = 16 / 9
    MAP_FRAME_FILL_RATIO = 0.90
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
        self._state = GisCanvasState.EMPTY
        self._state_message = "Chưa chọn composition."
        self._generation = 0
        self._drag_last_pos: QPoint | None = None
        self._drag_changed = False
        self._last_frame_rect = QRectF()
        self._last_applied_render_label: str | None = None
        self._rendered_pixmap: QPixmap | None = None
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

    def render_output_size(self) -> tuple[int, int]:
        """Return the pixel size that should be rendered for the visible map frame."""
        frame = self._frame_rect()
        return max(1, int(frame.width())), max(1, int(frame.height()))

    def set_frame_aspect(self, aspect: float) -> None:
        """Set map-frame aspect from template metadata when available."""
        if not isfinite(aspect) or aspect <= 0:
            return
        self._frame_aspect = aspect
        self._redraw()

    def set_composition(self, composition: Composition | None) -> None:
        """Load the selected composition into the canvas without emitting edits."""
        self._last_applied_render_label = None
        self._rendered_pixmap = None
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
            self._rendered_pixmap = _numpy_to_pixmap(canvas)
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
        lon_span = min(360.0, max(0.0001, self._scale / 1_000_000))
        lat_span = min(180.0, lon_span / self._frame_aspect)
        lon_per_pixel = lon_span / max(frame.width(), 1.0)
        lat_per_pixel = lat_span / max(frame.height(), 1.0)
        lon = _clamp(self._center[0] - dx * lon_per_pixel, -180.0, 180.0)
        lat = _clamp(self._center[1] + dy * lat_per_pixel, -90.0, 90.0)
        self._center = [round(lon, 8), round(lat, 8)]
        self._mark_interaction_stale()
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
        if emit:
            self._emit_view_edit()
        self._redraw()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._redraw()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.MouseButton.LeftButton and self._composition_id is not None:
            self._drag_last_pos = event.pos()
            self._drag_changed = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._drag_last_pos is not None:
            delta = event.pos() - self._drag_last_pos
            if delta.x() or delta.y():
                self.pan_by_pixels(delta.x(), delta.y(), emit=False)
                self._drag_last_pos = event.pos()
                self._drag_changed = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag_last_pos is not None:
            self._drag_last_pos = None
            self.unsetCursor()
            if self._drag_changed:
                self._emit_view_edit()
            self._drag_changed = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._composition_id is None:
            super().wheelEvent(event)
            return
        factor = 0.85 if event.angleDelta().y() > 0 else 1.15
        self.zoom_by_factor(factor)
        event.accept()

    def _emit_view_edit(self) -> None:
        self.viewEditCompleted.emit(list(self._center), self._scale)

    def _mark_interaction_stale(self) -> None:
        if self._visible_layers:
            self._state = GisCanvasState.STALE
            self._state_message = "View đã thay đổi. Preview cần cập nhật."
        else:
            self._state = GisCanvasState.NO_VISIBLE_LAYER
            self._state_message = "Không có layer đang bật để hiển thị trên canvas."
        self._last_applied_render_label = None
        self._rendered_pixmap = None
        self._bump_generation()

    def _bump_generation(self) -> None:
        self._generation += 1

    def _redraw(self) -> None:
        self._scene.clear()
        width = max(self.viewport().width(), 640)
        height = max(self.viewport().height(), 360)
        self._scene.setSceneRect(0, 0, width, height)
        self._scene.setBackgroundBrush(QColor("#242a31"))

        frame = self._frame_rect()
        self._draw_layers(frame)
        self._draw_frame(frame)
        self._draw_state_text(width)

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


def _numpy_to_pixmap(canvas: np.ndarray) -> QPixmap:
    height, width = canvas.shape[:2]
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
    return QPixmap.fromImage(image.copy())


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
