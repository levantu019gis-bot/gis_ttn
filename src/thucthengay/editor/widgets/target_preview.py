"""Target preview panel for Review/Edit mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from thucthengay.models import Composition, ImageLayer


class TargetPreviewState(StrEnum):
    """Display states for the target preview panel."""

    EMPTY = "empty"
    NEEDS_UPDATE = "needs_update"
    LOADING = "loading"
    RENDERED = "rendered"
    RENDER_ERROR = "render_error"
    NO_LAYER = "no_layer"


@dataclass(frozen=True)
class TargetPreviewKey:
    """Stable identity for the overview coverage being displayed."""

    target_id: str
    capture_date: date
    layer_signature: tuple[tuple[str, int, bool], ...]


@dataclass(frozen=True)
class TargetPreviewRequestToken:
    """Generation token used to ignore stale async target preview results."""

    generation: int
    key: TargetPreviewKey | None


@dataclass(frozen=True)
class TargetPreviewViewportOverlay:
    """One GIS editor viewport rectangle drawn over the target overview."""

    bbox: tuple[float, float, float, float]
    color: str
    label: str = ""


class TargetPreviewWidget(QWidget):
    """Small fixed overview of all imagery coverage for the selected target/day."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reviewTargetPreview")
        self.setMinimumHeight(172)
        self._generation = 0
        self._key: TargetPreviewKey | None = None
        self._composition_id: str | None = None
        self._layer_count = 0
        self._state = TargetPreviewState.EMPTY
        self._state_message = "Chưa chọn composition."
        self._detail_message = ""
        self._pixmap: QPixmap | None = None
        self._preview_geo_window: tuple[float, float, float, float] | None = None
        self._viewport_overlays: tuple[TargetPreviewViewportOverlay, ...] = ()

        self.status_label = QLabel(self._state_message)
        self.status_label.setObjectName("reviewTargetPreviewSummary")
        self.status_label.setWordWrap(True)
        self.image_label = QLabel()
        self.image_label.setObjectName("reviewTargetPreviewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(96)
        self.image_label.setStyleSheet(
            "QLabel#reviewTargetPreviewImage { background: #20262d; color: #f4f7fb; }"
        )
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("reviewTargetPreviewDetails")
        self.detail_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.status_label)
        layout.addWidget(self.image_label, 1)
        layout.addWidget(self.detail_label)
        self._refresh_labels()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def key(self) -> TargetPreviewKey | None:
        return self._key

    def state(self) -> TargetPreviewState:
        return self._state

    def state_text(self) -> str:
        return self.status_label.text()

    def detail_text(self) -> str:
        return self.detail_label.text()

    def render_width(self) -> int:
        return max(self.image_label.width(), 320)

    def render_height(self) -> int:
        return max(self.image_label.height(), 140)

    def viewport_overlays(self) -> tuple[TargetPreviewViewportOverlay, ...]:
        return self._viewport_overlays

    def set_composition(self, composition: Composition | None) -> bool:
        """Load selection context and return true when a new target/day needs rendering."""
        if composition is None:
            self._clear("Chưa chọn composition.")
            return False

        next_key = TargetPreviewKey(
            target_id=composition.target_id,
            capture_date=composition.capture_date,
            layer_signature=_layer_signature(composition.layers),
        )
        if next_key == self._key:
            return False

        self._key = next_key
        self._composition_id = composition.composition_id
        self._layer_count = len(composition.layers)
        self._pixmap = None
        self._preview_geo_window = None
        self._viewport_overlays = ()
        self._bump_generation()

        if not composition.layers:
            self._state = TargetPreviewState.NO_LAYER
            self._state_message = "Không có layer để tạo Target Preview."
            self._detail_message = "Chạy lại ingestion hoặc kiểm tra composition JSON."
            self._refresh_labels()
            return False

        if not any(layer.visible for layer in composition.layers):
            self._state = TargetPreviewState.NO_LAYER
            self._state_message = "Không có layer đang bật để tạo Target Preview."
            self._detail_message = "Bật ít nhất một layer trước khi cập nhật Target Preview."
            self._refresh_labels()
            return False

        self._state = TargetPreviewState.NEEDS_UPDATE
        self._state_message = "Target Preview cần cập nhật."
        self._detail_message = self._overview_text()
        self._refresh_labels()
        return True

    def set_preview_geo_window(self, bbox: tuple[float, float, float, float] | None) -> None:
        self._preview_geo_window = bbox
        self._refresh_pixmap()

    def set_viewport_overlays(
        self,
        overlays: tuple[TargetPreviewViewportOverlay, ...],
    ) -> None:
        self._viewport_overlays = overlays
        self._refresh_pixmap()

    def set_loading(
        self,
        message: str = "Đang render Target Preview...",
    ) -> TargetPreviewRequestToken:
        self._state = TargetPreviewState.LOADING
        self._state_message = message
        self._detail_message = self._overview_text()
        token = self.begin_render_request()
        self._refresh_labels()
        return token

    def set_error(self, token: TargetPreviewRequestToken, message: str) -> bool:
        if token != self.begin_render_request():
            return False
        self._state = TargetPreviewState.RENDER_ERROR
        self._state_message = "Target Preview lỗi render."
        self._detail_message = (
            f"{message.strip() or 'Không tạo được Target Preview.'} "
            "Chọn target/composition khác hoặc kiểm tra raster rồi thử lại."
        )
        self._pixmap = None
        self._refresh_labels()
        return True

    def begin_render_request(self) -> TargetPreviewRequestToken:
        return TargetPreviewRequestToken(generation=self._generation, key=self._key)

    def apply_render_result(
        self,
        token: TargetPreviewRequestToken,
        label: str,
        *,
        canvas: np.ndarray | None,
        issue_count: int = 0,
    ) -> bool:
        if token != self.begin_render_request():
            return False
        if canvas is not None:
            self._pixmap = _numpy_to_pixmap(canvas)
        self._state = TargetPreviewState.RENDERED
        self._state_message = "Target Preview đã cập nhật."
        issue_text = f"; issues: {issue_count}" if issue_count else ""
        self._detail_message = f"{self._overview_text()}\n{label}{issue_text}"
        self._refresh_labels()
        return True

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _clear(self, message: str) -> None:
        self._key = None
        self._composition_id = None
        self._layer_count = 0
        self._state = TargetPreviewState.EMPTY
        self._state_message = message
        self._detail_message = ""
        self._pixmap = None
        self._preview_geo_window = None
        self._viewport_overlays = ()
        self._bump_generation()
        self._refresh_labels()

    def _overview_text(self) -> str:
        if self._key is None:
            return ""
        return (
            f"Target: {self._key.target_id}; ngày {self._key.capture_date.isoformat()}\n"
            f"Composition: {self._composition_id or '-'}; layers: {self._layer_count}"
        )

    def _refresh_labels(self) -> None:
        self.status_label.setText(self._state_message)
        self.detail_label.setText(self._detail_message)
        if self._pixmap is None:
            self.image_label.setText(self._empty_image_text())
            self.image_label.clear()
            self.image_label.setText(self._empty_image_text())
            return
        self.image_label.setText("")
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled = self._pixmap_with_viewport_overlays(scaled)
        self.image_label.setPixmap(scaled)

    def _pixmap_with_viewport_overlays(self, pixmap: QPixmap) -> QPixmap:
        if not self._viewport_overlays or self._preview_geo_window is None:
            return pixmap
        decorated = QPixmap(pixmap)
        painter = QPainter(decorated)
        try:
            for overlay, rect in zip(
                self._viewport_overlays,
                self._overlay_rects_for_size(decorated.width(), decorated.height()),
                strict=False,
            ):
                if rect.isEmpty():
                    continue
                pen = QPen(QColor(overlay.color), 2)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
                if overlay.label:
                    painter.drawText(rect.adjusted(4, 4, -4, -4), overlay.label)
        finally:
            painter.end()
        return decorated

    def _overlay_rects_for_size(self, width: int, height: int) -> list[QRectF]:
        if self._preview_geo_window is None or width <= 0 or height <= 0:
            return []
        min_lon, min_lat, max_lon, max_lat = self._preview_geo_window
        lon_span = max_lon - min_lon
        lat_span = max_lat - min_lat
        if lon_span <= 0 or lat_span <= 0:
            return []

        image_rect = QRectF(0, 0, width, height)
        rects: list[QRectF] = []
        for overlay in self._viewport_overlays:
            box_min_lon, box_min_lat, box_max_lon, box_max_lat = overlay.bbox
            left = (box_min_lon - min_lon) / lon_span * width
            right = (box_max_lon - min_lon) / lon_span * width
            top = (max_lat - box_max_lat) / lat_span * height
            bottom = (max_lat - box_min_lat) / lat_span * height
            rect = QRectF(
                min(left, right),
                min(top, bottom),
                abs(right - left),
                abs(bottom - top),
            ).intersected(image_rect)
            rects.append(rect)
        return rects

    def _empty_image_text(self) -> str:
        if self._state == TargetPreviewState.LOADING:
            return "Đang render..."
        if self._state == TargetPreviewState.NO_LAYER:
            return "Không có dữ liệu"
        if self._state == TargetPreviewState.RENDER_ERROR:
            return "Lỗi preview"
        return "Chưa có ảnh preview"

    def _bump_generation(self) -> None:
        self._generation += 1


def _numpy_to_pixmap(canvas: np.ndarray) -> QPixmap:
    height, width = canvas.shape[:2]
    if canvas.ndim == 2:
        image = QImage(canvas.data, width, height, width, QImage.Format.Format_Grayscale8)
    elif canvas.shape[2] == 3:
        rgb = np.ascontiguousarray(canvas)
        image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
    else:
        rgba = np.ascontiguousarray(canvas[:, :, :4])
        image = QImage(rgba.data, width, height, 4 * width, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(image.copy())


def _layer_signature(layers: list[ImageLayer]) -> tuple[tuple[str, int, bool], ...]:
    return tuple(
        (layer.layer_id, layer.order, layer.visible)
        for layer in sorted(layers, key=lambda item: (item.order, item.layer_id))
    )
