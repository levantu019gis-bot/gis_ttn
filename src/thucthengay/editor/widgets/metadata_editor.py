"""Metadata editor dialog for manual capture date/time/cloud correction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Any

import rasterio
from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from rasterio.enums import ColorInterp

from thucthengay.models import (
    ImageLayer,
    LayerRenderBands,
    LayerSymbology,
    MetadataSource,
    MetadataStatus,
)

_STRETCH_MODE_LABELS = {
    "none": "None",
    "dtype": "Data type",
    "min_max": "Min / max",
    "percent_clip": "Percent clip",
    "stddev": "Stddev",
    "manual": "Manual",
}

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


@dataclass(frozen=True)
class _BandOption:
    index: int
    label: str
    colorinterp: ColorInterp | None = None


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
        self._source_path_edit.editingFinished.connect(self._refresh_band_combos)
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

        self._red_band_combo = QComboBox()
        self._red_band_combo.setObjectName("metadataRedBandCombo")
        self._green_band_combo = QComboBox()
        self._green_band_combo.setObjectName("metadataGreenBandCombo")
        self._blue_band_combo = QComboBox()
        self._blue_band_combo.setObjectName("metadataBlueBandCombo")
        self._alpha_band_combo = QComboBox()
        self._alpha_band_combo.setObjectName("metadataAlphaBandCombo")
        self._band_status_label = QLabel("")
        self._band_status_label.setObjectName("metadataBandStatus")

        symbology = layer.symbology or LayerSymbology()
        self._stretch_mode_combo = QComboBox()
        self._stretch_mode_combo.setObjectName("metadataStretchModeCombo")
        for mode, label in _STRETCH_MODE_LABELS.items():
            self._stretch_mode_combo.addItem(label, mode)
        _set_combo_data(self._stretch_mode_combo, symbology.stretch_mode)
        self._lower_percentile_spin = _double_spin(
            "metadataLowerPercentileSpin",
            minimum=0.0,
            maximum=100.0,
            value=symbology.lower_percentile,
            decimals=2,
            suffix=" %",
        )
        self._upper_percentile_spin = _double_spin(
            "metadataUpperPercentileSpin",
            minimum=0.0,
            maximum=100.0,
            value=symbology.upper_percentile,
            decimals=2,
            suffix=" %",
        )
        self._stddev_factor_spin = _double_spin(
            "metadataStddevFactorSpin",
            minimum=0.1,
            maximum=10.0,
            value=symbology.stddev_factor,
            decimals=2,
        )
        self._manual_min_edit = QLineEdit(_format_float_list(symbology.manual_min))
        self._manual_min_edit.setObjectName("metadataManualMinEdit")
        self._manual_max_edit = QLineEdit(_format_float_list(symbology.manual_max))
        self._manual_max_edit.setObjectName("metadataManualMaxEdit")
        self._gamma_spin = _double_spin(
            "metadataGammaSpin",
            minimum=0.1,
            maximum=5.0,
            value=symbology.gamma,
            decimals=2,
        )
        self._brightness_spin = _double_spin(
            "metadataBrightnessSpin",
            minimum=-255.0,
            maximum=255.0,
            value=symbology.brightness,
            decimals=1,
        )
        self._contrast_spin = _double_spin(
            "metadataContrastSpin",
            minimum=0.0,
            maximum=10.0,
            value=symbology.contrast,
            decimals=2,
        )
        self._per_channel_checkbox = QCheckBox("Per channel")
        self._per_channel_checkbox.setObjectName("metadataPerChannelCheck")
        self._per_channel_checkbox.setChecked(symbology.per_channel)
        self._symbology_enabled_checkbox = QCheckBox("Enable symbology")
        self._symbology_enabled_checkbox.setObjectName("metadataSymbologyEnabledCheck")
        self._symbology_enabled_checkbox.setChecked(
            layer.symbology is not None and symbology.enabled
        )

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
        form.addRow("Red band:", self._red_band_combo)
        form.addRow("Green band:", self._green_band_combo)
        form.addRow("Blue band:", self._blue_band_combo)
        form.addRow("Alpha band:", self._alpha_band_combo)
        form.addRow("Bands:", self._band_status_label)
        form.addRow(self._symbology_enabled_checkbox)
        form.addRow("Stretch:", self._stretch_mode_combo)
        form.addRow("Lower clip:", self._lower_percentile_spin)
        form.addRow("Upper clip:", self._upper_percentile_spin)
        form.addRow("Stddev factor:", self._stddev_factor_spin)
        form.addRow("Manual min:", self._manual_min_edit)
        form.addRow("Manual max:", self._manual_max_edit)
        form.addRow("Gamma:", self._gamma_spin)
        form.addRow("Brightness:", self._brightness_spin)
        form.addRow("Contrast:", self._contrast_spin)
        form.addRow(self._per_channel_checkbox)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._validation_label)
        layout.addWidget(button_box)
        self._refresh_band_combos()

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

        payload["render_bands"] = _render_bands_from_payload(payload)
        payload["symbology"] = _symbology_from_payload(payload)
        payload.pop("_red_band", None)
        payload.pop("_green_band", None)
        payload.pop("_blue_band", None)
        payload.pop("_alpha_band", None)
        payload.pop("_symbology", None)
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
            "_red_band": self._red_band_combo.currentData(),
            "_green_band": self._green_band_combo.currentData(),
            "_blue_band": self._blue_band_combo.currentData(),
            "_alpha_band": self._alpha_band_combo.currentData(),
            "_symbology": {
                "enabled": self._symbology_enabled_checkbox.isChecked(),
                "stretch_mode": self._stretch_mode_combo.currentData(),
                "lower_percentile": float(self._lower_percentile_spin.value()),
                "upper_percentile": float(self._upper_percentile_spin.value()),
                "stddev_factor": float(self._stddev_factor_spin.value()),
                "manual_min": self._manual_min_edit.text(),
                "manual_max": self._manual_max_edit.text(),
                "gamma": float(self._gamma_spin.value()),
                "brightness": float(self._brightness_spin.value()),
                "contrast": float(self._contrast_spin.value()),
                "per_channel": self._per_channel_checkbox.isChecked(),
            },
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
        try:
            _render_bands_from_payload(payload)
            _symbology_from_payload(payload)
        except ValueError as exc:
            return str(exc)
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
            self._refresh_band_combos()

    def _refresh_band_combos(self) -> None:
        options, status = _read_band_options(self._source_path_edit.text().strip())
        if not options and self._layer.render_bands is not None:
            options = _options_for_existing_bands(self._layer.render_bands)
            status = f"{status} Dang dung band da luu."
        defaults = self._layer.render_bands or _default_render_bands(options)
        _populate_band_combo(self._red_band_combo, options, defaults.red if defaults else None)
        _populate_band_combo(
            self._green_band_combo,
            options,
            defaults.green if defaults else None,
        )
        _populate_band_combo(self._blue_band_combo, options, defaults.blue if defaults else None)
        _populate_band_combo(
            self._alpha_band_combo,
            options,
            defaults.alpha if defaults else None,
            include_none=True,
        )
        self._band_status_label.setText(status)


def _state_pill_text(layer: ImageLayer) -> str:
    if layer.metadata_source is MetadataSource.MANUAL:
        return "Đã sửa thủ công"
    return _STATE_LABELS.get(layer.metadata_status, "Chưa rõ")


def _render_bands_from_payload(payload: dict[str, Any]) -> LayerRenderBands | None:
    red = payload.get("_red_band")
    green = payload.get("_green_band")
    blue = payload.get("_blue_band")
    alpha = payload.get("_alpha_band")
    if red is None and green is None and blue is None and alpha is None:
        return None
    if red is None or green is None or blue is None:
        msg = "Can chon du 3 kenh Red, Green, Blue."
        raise ValueError(msg)
    try:
        red_band = int(red)
        green_band = int(green)
        blue_band = int(blue)
        alpha_band = int(alpha) if alpha is not None else None
    except ValueError as exc:
        msg = "Render bands khong hop le."
        raise ValueError(msg) from exc
    try:
        return LayerRenderBands(
            red=red_band,
            green=green_band,
            blue=blue_band,
            alpha=alpha_band,
        )
    except ValueError as exc:
        msg = f"Render bands khong hop le: {exc}"
        raise ValueError(msg) from exc


def _symbology_from_payload(payload: dict[str, Any]) -> LayerSymbology | None:
    raw = dict(payload.get("_symbology") or {})
    if not bool(raw.get("enabled", False)):
        return None
    if raw.get("stretch_mode") != "manual":
        raw["manual_min"] = None
        raw["manual_max"] = None
        try:
            return LayerSymbology.model_validate(raw)
        except ValueError as exc:
            msg = f"Symbology khong hop le: {exc}"
            raise ValueError(msg) from exc
    try:
        raw["manual_min"] = _parse_float_list(str(raw.get("manual_min") or ""))
        raw["manual_max"] = _parse_float_list(str(raw.get("manual_max") or ""))
    except ValueError as exc:
        msg = f"Symbology khong hop le: {exc}"
        raise ValueError(msg) from exc
    try:
        return LayerSymbology.model_validate(raw)
    except ValueError as exc:
        msg = f"Symbology khong hop le: {exc}"
        raise ValueError(msg) from exc


def _parse_float_list(text: str) -> list[float] | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    values: list[float] = []
    for part in cleaned.replace(";", ",").split(","):
        item = part.strip()
        if not item:
            continue
        try:
            values.append(float(item))
        except ValueError as exc:
            msg = "Manual min/max phai la so, cach nhau bang dau phay."
            raise ValueError(msg) from exc
    return values or None


def _format_float_list(values: list[float] | None) -> str:
    if not values:
        return ""
    return ", ".join(f"{value:g}" for value in values)


def _double_spin(
    object_name: str,
    *,
    minimum: float,
    maximum: float,
    value: float,
    decimals: int,
    suffix: str = "",
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setObjectName(object_name)
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setValue(value)
    if suffix:
        spin.setSuffix(suffix)
    return spin


def _read_band_options(source_path: str) -> tuple[list[_BandOption], str]:
    if not source_path:
        return [], "Chua co file nguon."
    try:
        with rasterio.open(source_path) as dataset:
            descriptions = tuple(dataset.descriptions or ())
            colorinterp = tuple(dataset.colorinterp or ())
            options = [
                _BandOption(
                    index=index,
                    label=_band_label(index, descriptions, colorinterp),
                    colorinterp=colorinterp[index - 1] if index <= len(colorinterp) else None,
                )
                for index in range(1, int(dataset.count) + 1)
            ]
    except (OSError, rasterio.errors.RasterioError) as exc:
        return [], f"Khong doc duoc band tu file nguon: {exc}"
    if not options:
        return [], "File nguon khong co band raster."
    return options, f"Da doc {len(options)} band tu file nguon."


def _band_label(
    index: int,
    descriptions: tuple[str | None, ...],
    colorinterp: tuple[ColorInterp, ...],
) -> str:
    parts = [f"Band {index}"]
    if index <= len(colorinterp):
        interp = colorinterp[index - 1]
        if interp is not ColorInterp.undefined:
            parts.append(str(interp.name))
    if index <= len(descriptions) and descriptions[index - 1]:
        parts.append(str(descriptions[index - 1]))
    return " - ".join(parts)


def _default_render_bands(options: list[_BandOption]) -> LayerRenderBands | None:
    if not options:
        return None
    red = _index_for_colorinterp(options, ColorInterp.red)
    green = _index_for_colorinterp(options, ColorInterp.green)
    blue = _index_for_colorinterp(options, ColorInterp.blue)
    alpha = _index_for_colorinterp(options, ColorInterp.alpha)
    indexes = [option.index for option in options]
    return LayerRenderBands(
        red=red or indexes[0],
        green=green or (indexes[1] if len(indexes) >= 2 else indexes[0]),
        blue=blue or (indexes[2] if len(indexes) >= 3 else indexes[0]),
        alpha=alpha,
    )


def _options_for_existing_bands(render_bands: LayerRenderBands) -> list[_BandOption]:
    indexes = sorted(
        {
            render_bands.red,
            render_bands.green,
            render_bands.blue,
            *({render_bands.alpha} if render_bands.alpha is not None else set()),
        }
    )
    return [_BandOption(index=index, label=f"Band {index}") for index in indexes]


def _index_for_colorinterp(options: list[_BandOption], interp: ColorInterp) -> int | None:
    for option in options:
        if option.colorinterp == interp:
            return option.index
    return None


def _populate_band_combo(
    combo: QComboBox,
    options: list[_BandOption],
    selected: int | None,
    *,
    include_none: bool = False,
) -> None:
    combo.blockSignals(True)
    combo.clear()
    if include_none:
        combo.addItem("None", None)
    for option in options:
        combo.addItem(option.label, option.index)
    _set_combo_data(combo, selected)
    combo.setEnabled(bool(options))
    combo.blockSignals(False)


def _set_combo_data(combo: QComboBox, value: object | None) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return
    if combo.count():
        combo.setCurrentIndex(0)


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
