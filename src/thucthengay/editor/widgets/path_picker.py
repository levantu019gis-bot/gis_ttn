"""Reusable path picker row for Setup mode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class PathKind(StrEnum):
    """Supported path expectations for Setup mode."""

    CONFIG_FILE = "config_file"
    GEOJSON_FILE = "geojson_file"
    INPUT_FOLDER = "input_folder"
    OUTPUT_FOLDER = "output_folder"
    WORKSPACE_FOLDER = "workspace_folder"


class PathStatus(StrEnum):
    """Validation states rendered by path picker rows."""

    EMPTY = "empty"
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class PathValidation:
    """Result of validating a selected path."""

    status: PathStatus
    message: str
    path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.status == PathStatus.VALID


def validate_selected_path(path_text: str, kind: PathKind) -> PathValidation:
    """Validate a user-selected path against its expected Setup role."""
    if not path_text.strip():
        return PathValidation(PathStatus.EMPTY, "Chưa chọn đường dẫn.")

    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        return PathValidation(PathStatus.INVALID, f"Không tìm thấy: {path}", path)

    if kind == PathKind.CONFIG_FILE:
        return _validate_config_file(path)
    if kind == PathKind.GEOJSON_FILE:
        return _validate_geojson_file(path)
    if kind == PathKind.INPUT_FOLDER:
        return _validate_folder(path, "Thư mục ảnh không hợp lệ.", require_writable=False)
    if kind == PathKind.OUTPUT_FOLDER:
        return _validate_folder(path, "Thu muc output khong hop le.", require_writable=True)
    if kind == PathKind.WORKSPACE_FOLDER:
        return _validate_folder(path, "Thư mục workspace không hợp lệ.", require_writable=True)

    return PathValidation(PathStatus.INVALID, "Loại đường dẫn không được hỗ trợ.", path)


def _validate_config_file(path: Path) -> PathValidation:
    if not path.is_file():
        return PathValidation(PathStatus.INVALID, "Config phải là file JSON.", path)
    if path.suffix.lower() != ".json":
        return PathValidation(PathStatus.INVALID, "Config phải có phần mở rộng .json.", path)
    if not os.access(path, os.R_OK):
        return PathValidation(PathStatus.INVALID, "Không thể đọc file config.", path)
    return PathValidation(PathStatus.VALID, "Hợp lệ.", path)


def _validate_geojson_file(path: Path) -> PathValidation:
    if not path.is_file():
        return PathValidation(PathStatus.INVALID, "GeoJSON phai la file.", path)
    if path.suffix.lower() not in {".geojson", ".json"}:
        return PathValidation(
            PathStatus.INVALID,
            "File GeoJSON phai co phan mo rong .geojson hoac .json.",
            path,
        )
    if not os.access(path, os.R_OK):
        return PathValidation(PathStatus.INVALID, "Khong the doc file GeoJSON.", path)
    return PathValidation(PathStatus.VALID, "Hop le.", path)


def _validate_folder(
    path: Path,
    wrong_type_message: str,
    *,
    require_writable: bool,
) -> PathValidation:
    if not path.is_dir():
        return PathValidation(PathStatus.INVALID, wrong_type_message, path)
    if not os.access(path, os.R_OK):
        return PathValidation(PathStatus.INVALID, "Không thể đọc thư mục.", path)
    if require_writable and not os.access(path, os.W_OK):
        return PathValidation(PathStatus.INVALID, "Không thể ghi vào thư mục workspace.", path)
    return PathValidation(PathStatus.VALID, "Hợp lệ.", path)


class ElidedPathField(QLineEdit):
    """Read-only path field that middle-elides long display text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setReadOnly(True)

    @property
    def full_text(self) -> str:
        return self._full_text

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._refresh_elided_text()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_elided_text()

    def _refresh_elided_text(self) -> None:
        available_width = max(self.width() - 12, 0)
        display = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideMiddle,
            available_width,
        )
        self.setText(display)


class PathPickerRow(QWidget):
    """One labeled path picker with browse action and validation indicator."""

    validationChanged = Signal(object)

    def __init__(
        self,
        label: str,
        kind: PathKind,
        *,
        dialog_caption: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.dialog_caption = dialog_caption or label
        self.validation = PathValidation(PathStatus.EMPTY, "Chưa chọn đường dẫn.")

        self.label = QLabel(label)
        self.path_field = ElidedPathField()
        self.browse_button = QPushButton("Chọn...")
        self.status_label = QLabel("Chưa chọn")

        self.label.setObjectName("pathPickerLabel")
        self.path_field.setObjectName("pathPickerField")
        self.browse_button.setObjectName("pathPickerBrowseButton")
        self.status_label.setObjectName("pathPickerStatus")

        self.status_label.setMinimumWidth(96)
        self.browse_button.clicked.connect(self.browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.label)
        layout.addWidget(self.path_field, 1)
        layout.addWidget(self.browse_button)
        layout.addWidget(self.status_label)

        self._render_validation()

    @property
    def selected_path(self) -> Path | None:
        return self.validation.path if self.validation.ok else None

    def set_path(self, path: str | Path) -> None:
        path_text = str(path)
        self.path_field.set_full_text(path_text)
        self.validation = validate_selected_path(path_text, self.kind)
        self._render_validation()
        self.validationChanged.emit(self.validation)

    def clear(self) -> None:
        self.path_field.set_full_text("")
        self.validation = validate_selected_path("", self.kind)
        self._render_validation()
        self.validationChanged.emit(self.validation)

    def browse(self) -> None:
        if self.kind == PathKind.CONFIG_FILE:
            path, _ = QFileDialog.getOpenFileName(
                self,
                self.dialog_caption,
                "",
                "JSON files (*.json);;All files (*)",
            )
        else:
            path = QFileDialog.getExistingDirectory(self, self.dialog_caption)

        if path:
            self.set_path(path)

    def _render_validation(self) -> None:
        self.path_field.setToolTip(self.path_field.full_text)
        self.status_label.setToolTip(self.validation.message)

        if self.validation.status == PathStatus.VALID:
            self.status_label.setText("Hợp lệ")
            self.status_label.setProperty("state", "valid")
            return
        if self.validation.status == PathStatus.INVALID:
            self.status_label.setText("Lỗi")
            self.status_label.setProperty("state", "invalid")
            return

        self.status_label.setText("Chưa chọn")
        self.status_label.setProperty("state", "empty")
