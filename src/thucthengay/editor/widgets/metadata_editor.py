"""Metadata editor dialog for manual capture date/time/cloud correction."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from thucthengay.models import ImageLayer, MetadataSource, MetadataStatus

_STATE_LABELS = {
    MetadataStatus.VALID: "Đã parse",
    MetadataStatus.NEEDS_CORRECTION: "Cần xem lại",
    MetadataStatus.NEEDS_MANUAL_CORRECTION: "Cần nhập tay",
    MetadataStatus.UNKNOWN: "Chưa rõ",
}

_SOURCE_LABELS = {
    MetadataSource.FILENAME: "Filename",
    MetadataSource.SIDECAR: "Sidecar",
    MetadataSource.EMBEDDED: "Embedded",
    MetadataSource.MANUAL: "Đã sửa thủ công",
    MetadataSource.UNKNOWN: "Chưa rõ",
}


class MetadataEditorDialog(QDialog):
    """Modal dialog letting the operator correct a layer's capture metadata."""

    metadataSaved = Signal(str, dict)  # (layer_id, payload)

    def __init__(self, layer: ImageLayer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metadataEditorDialog")
        self.setWindowTitle("Sửa metadata layer")
        self._layer = layer

        self._source_path_edit = QLineEdit(layer.source_path)
        self._source_path_edit.setObjectName("metadataSourcePathEdit")
        self._source_path_edit.setMinimumWidth(360)
        self._source_path_browse_button = QPushButton("Chọn")
        self._source_path_browse_button.setObjectName("metadataSourcePathBrowse")
        self._source_path_browse_button.clicked.connect(self._browse_source_path)
        self._parsed_source_label = QLabel(_SOURCE_LABELS[layer.metadata_source])
        self._state_label = QLabel(_state_pill_text(layer))
        self._state_label.setObjectName("metadataStatePill")

        self._capture_date_checkbox = QCheckBox("Có ngày")
        self._capture_date_edit = QDateEdit()
        self._capture_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._capture_date_edit.setCalendarPopup(True)
        if layer.capture_date is not None:
            self._capture_date_checkbox.setChecked(True)
            self._capture_date_edit.setDate(
                QDate(layer.capture_date.year, layer.capture_date.month, layer.capture_date.day)
            )
        else:
            self._capture_date_checkbox.setChecked(False)
            self._capture_date_edit.setDate(QDate.currentDate())
        self._capture_date_edit.setEnabled(self._capture_date_checkbox.isChecked())
        self._capture_date_checkbox.toggled.connect(self._capture_date_edit.setEnabled)

        self._capture_time_checkbox = QCheckBox("Có giờ")
        self._capture_time_edit = QTimeEdit()
        self._capture_time_edit.setDisplayFormat("HH:mm")
        if layer.capture_time is not None:
            self._capture_time_checkbox.setChecked(True)
            self._capture_time_edit.setTime(
                QTime(layer.capture_time.hour, layer.capture_time.minute)
            )
        else:
            self._capture_time_checkbox.setChecked(False)
            self._capture_time_edit.setTime(QTime(8, 0))
        self._capture_time_edit.setEnabled(self._capture_time_checkbox.isChecked())
        self._capture_time_checkbox.toggled.connect(self._capture_time_edit.setEnabled)

        self._cloud_checkbox = QCheckBox("Có % mây")
        self._cloud_spin = QDoubleSpinBox()
        self._cloud_spin.setRange(0.0, 100.0)
        self._cloud_spin.setDecimals(1)
        self._cloud_spin.setSuffix(" %")
        if layer.cloud_percent is not None:
            self._cloud_checkbox.setChecked(True)
            self._cloud_spin.setValue(layer.cloud_percent)
        else:
            self._cloud_checkbox.setChecked(False)
            self._cloud_spin.setValue(0.0)
        self._cloud_spin.setEnabled(self._cloud_checkbox.isChecked())
        self._cloud_checkbox.toggled.connect(self._cloud_spin.setEnabled)

        self._validation_label = QLabel("")
        self._validation_label.setObjectName("metadataEditorValidation")
        self._validation_label.setWordWrap(True)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Save).setText("Lưu")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Hủy")
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("File:", self._build_source_path_row())
        form.addRow("Nguồn parse:", self._parsed_source_label)
        form.addRow("Trạng thái:", self._state_label)
        form.addRow(self._capture_date_checkbox, self._capture_date_edit)
        form.addRow(self._capture_time_checkbox, self._capture_time_edit)
        form.addRow(self._cloud_checkbox, self._cloud_spin)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._validation_label)
        layout.addWidget(button_box)

    @property
    def validation_text(self) -> str:
        """Current Vietnamese validation message, if any."""
        return self._validation_label.text()

    def _on_save(self) -> None:
        payload = self._collect_payload()
        error = self._validate(payload)
        if error is not None:
            self._validation_label.setText(error)
            return

        payload["metadata_status"] = MetadataStatus.VALID
        payload["metadata_source"] = MetadataSource.MANUAL

        self._validation_label.setText("")
        self.metadataSaved.emit(self._layer.layer_id, payload)
        self.accept()

    def _collect_payload(self) -> dict[str, Any]:
        capture_date: date | None = None
        if self._capture_date_checkbox.isChecked():
            qd = self._capture_date_edit.date()
            capture_date = date(qd.year(), qd.month(), qd.day())

        capture_time: time | None = None
        if self._capture_time_checkbox.isChecked():
            qt = self._capture_time_edit.time()
            capture_time = time(qt.hour(), qt.minute())

        cloud_percent: float | None = None
        if self._cloud_checkbox.isChecked():
            cloud_percent = float(self._cloud_spin.value())

        return {
            "source_path": self._source_path_edit.text().strip(),
            "capture_date": capture_date,
            "capture_time": capture_time,
            "cloud_percent": cloud_percent,
        }

    @staticmethod
    def _validate(payload: dict[str, Any]) -> str | None:
        if not str(payload.get("source_path") or "").strip():
            return "Cần nhập file nguồn."
        cloud = payload.get("cloud_percent")
        if cloud is not None and (cloud < 0 or cloud > 100):
            return "Giá trị mây phải trong 0–100."
        if payload.get("capture_date") is None:
            return "Cần nhập ngày chụp."
        if payload.get("capture_time") is None:
            return "Cần nhập giờ chụp."
        return None

    def _build_source_path_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._source_path_edit, 1)
        layout.addWidget(self._source_path_browse_button)
        return row

    def _browse_source_path(self) -> None:
        current_text = self._source_path_edit.text().strip()
        current_path = Path(current_text).expanduser() if current_text else Path.cwd()
        start_dir = current_path.parent if current_path.suffix else current_path
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Chọn file nguồn",
            str(start_dir),
            "GeoTIFF (*.tif *.tiff);;All files (*)",
        )
        if selected:
            self._source_path_edit.setText(selected)


def _state_pill_text(layer: ImageLayer) -> str:
    if layer.metadata_source is MetadataSource.MANUAL:
        return "Đã sửa thủ công"
    return _STATE_LABELS.get(layer.metadata_status, "Chưa rõ")


def confirm_date_change_dialog(
    layer_id: str,
    source_composition_id: str,
    new_composition_id: str,
    parent: QWidget | None = None,
) -> bool:
    """Show a Vietnamese confirmation dialog before moving a layer to a new composition.

    Default action is Cancel for safety. Returns True only on explicit confirm.
    """
    box = QMessageBox(parent)
    box.setObjectName("dateChangeConfirmDialog")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Xác nhận đổi ngày")
    box.setText(
        f"Layer '{layer_id}' sẽ được chuyển từ composition "
        f"'{source_composition_id}' sang '{new_composition_id}'."
    )
    box.setInformativeText(
        "Hành động này sẽ regroup layer và đánh dấu cả hai composition cần revalidate. "
        "Tiếp tục?"
    )
    confirm_button = box.addButton("Chuyển", QMessageBox.ButtonRole.AcceptRole)
    cancel_button = box.addButton("Hủy", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    box.exec()
    return box.clickedButton() is confirm_button


def open_metadata_editor(
    layer: ImageLayer,
    parent: QWidget | None = None,
) -> MetadataEditorDialog:
    """Helper to create the modal dialog; caller connects metadataSaved and exec()s."""
    dialog = MetadataEditorDialog(layer, parent=parent)
    dialog.setModal(True)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    return dialog
