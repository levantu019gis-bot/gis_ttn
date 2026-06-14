"""Reusable multi-path picker used by the satellite download tab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from thucthengay.editor.widgets.path_picker import (
    ElidedPathField,
    PathKind,
    PathValidation,
    validate_selected_path,
)


class MultiPathRow(QWidget):
    """One selected path row with validation text and a remove action."""

    removeRequested = Signal(object)

    def __init__(self, path: str | Path, kind: PathKind, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.path_field = ElidedPathField()
        self.status_label = QLabel()
        self.remove_button = QPushButton("Xoa")
        self.status_label.setObjectName("downloadPathRowStatus")
        self.remove_button.setObjectName("downloadPathRowRemove")
        self.status_label.setMinimumWidth(72)
        self.remove_button.setToolTip("Loai bo dong nay.")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.path_field, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.remove_button)

        self.validation = PathValidation(status=validate_selected_path("", kind).status, message="")
        self.set_path(path)
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self))

    @property
    def selected_path(self) -> Path | None:
        return self.validation.path if self.validation.ok else None

    def set_path(self, path: str | Path) -> None:
        text = str(path)
        self.path_field.set_full_text(text)
        self.validation = validate_selected_path(text, self.kind)
        self._render_validation()

    def _render_validation(self) -> None:
        self.path_field.setToolTip(self.path_field.full_text)
        self.status_label.setToolTip(self.validation.message)
        if self.validation.ok:
            self.status_label.setText("Hop le")
            self.status_label.setProperty("state", "valid")
            return
        self.status_label.setText("Loi")
        self.status_label.setProperty("state", "invalid")


class MultiPathListWidget(QWidget):
    """Path list with add/remove/clear controls and validation helpers."""

    pathsChanged = Signal()

    def __init__(
        self,
        title: str,
        kind: PathKind,
        *,
        add_button_text: str,
        empty_message: str,
        dialog_caption: str,
        file_filter: str = "All files (*)",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.empty_message = empty_message
        self.dialog_caption = dialog_caption
        self.file_filter = file_filter
        self.title_label = QLabel(title)
        self.add_button = QPushButton(add_button_text)
        self.clear_button = QPushButton("Xoa tat ca")
        self.empty_label = QLabel(empty_message)
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)

        self.title_label.setObjectName("downloadPathListTitle")
        self.add_button.setObjectName("downloadPathListAdd")
        self.clear_button.setObjectName("downloadPathListClear")
        self.empty_label.setObjectName("downloadPathListEmpty")
        self.empty_label.setWordWrap(True)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.add_button)
        header.addWidget(self.clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.rows_container)
        layout.addWidget(self.empty_label)

        self.add_button.clicked.connect(self.browse)
        self.clear_button.clicked.connect(self.clear_paths)
        self._refresh_empty_state()

    def row_widgets(self) -> list[MultiPathRow]:
        rows: list[MultiPathRow] = []
        for index in range(self.rows_layout.count()):
            item = self.rows_layout.itemAt(index)
            widget = item.widget()
            if isinstance(widget, MultiPathRow):
                rows.append(widget)
        return rows

    def selected_paths(self) -> list[Path]:
        return [path for row in self.row_widgets() if (path := row.selected_path) is not None]

    def blockers(self) -> list[str]:
        rows = self.row_widgets()
        if not rows:
            return [self.empty_message]
        return [row.validation.message for row in rows if not row.validation.ok]

    def add_path(self, path: str | Path) -> None:
        row = MultiPathRow(path, self.kind)
        row.removeRequested.connect(self._remove_row)
        self.rows_layout.addWidget(row)
        self._refresh_empty_state()
        self.pathsChanged.emit()

    def add_paths(self, paths: list[str] | tuple[str, ...]) -> None:
        for path in paths:
            self.add_path(path)

    def clear_paths(self) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._refresh_empty_state()
        self.pathsChanged.emit()

    def browse(self) -> None:
        if self.kind == PathKind.GEOJSON_FILE:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                self.dialog_caption,
                "",
                self.file_filter,
            )
            self.add_paths(paths)
            return

        path = QFileDialog.getExistingDirectory(self, self.dialog_caption)
        if path:
            self.add_path(path)

    def _remove_row(self, row: object) -> None:
        if not isinstance(row, MultiPathRow):
            return
        row.setParent(None)
        row.deleteLater()
        self._refresh_empty_state()
        self.pathsChanged.emit()

    def _refresh_empty_state(self) -> None:
        has_rows = bool(self.row_widgets())
        self.empty_label.setVisible(not has_rows)
        self.clear_button.setEnabled(has_rows)
