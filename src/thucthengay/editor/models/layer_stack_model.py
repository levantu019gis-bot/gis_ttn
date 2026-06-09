"""Qt table model for Review/Edit layer stack controls."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time
from enum import IntEnum
from pathlib import PurePath
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt

from thucthengay.models import (
    Composition,
    ImageLayer,
    ImageLayerSourceKind,
    Issue,
    IssueSeverity,
    MetadataStatus,
)


class LayerStackColumn(IntEnum):
    """Columns shown by the Review/Edit layer stack table."""

    VISIBILITY = 0
    ORDER = 1
    TIMESTAMP = 2
    CLOUD = 3
    METADATA = 4
    FILENAME = 5
    ISSUE = 6
    ACTIONS = 7


class LayerStackRole(IntEnum):
    """Custom roles exposed by the layer stack model."""

    LAYER_ID = int(Qt.ItemDataRole.UserRole) + 1
    FULL_PATH = int(Qt.ItemDataRole.UserRole) + 2
    VISIBLE = int(Qt.ItemDataRole.UserRole) + 3
    NO_VISIBLE_WARNING = int(Qt.ItemDataRole.UserRole) + 4
    ORDER_VALUE = int(Qt.ItemDataRole.UserRole) + 5
    METADATA_STATUS = int(Qt.ItemDataRole.UserRole) + 6
    SOURCE_KIND = int(Qt.ItemDataRole.UserRole) + 7


class LayerStackModel(QAbstractTableModel):
    """Projection of composition layers for visibility/order review controls."""

    HEADERS = ("Hiện", "Thứ tự", "Thời gian", "Mây", "Metadata", "File", "Lỗi", "Menu")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._composition_id: str | None = None
        self._layers: list[ImageLayer] = []
        self._layer_issue_severity: dict[str, IssueSeverity] = {}
        self._layer_issue_messages: dict[str, list[str]] = {}

    @property
    def composition_id(self) -> str | None:
        """Composition whose layers are currently shown."""
        return self._composition_id

    def set_composition(self, composition: Composition | None) -> None:
        """Replace table contents from a selected composition."""
        self.beginResetModel()
        self._composition_id = composition.composition_id if composition is not None else None
        self._layers = (
            sorted(composition.layers, key=lambda layer: (layer.order, layer.layer_id))
            if composition is not None
            else []
        )
        self._layer_issue_severity = {}
        self._layer_issue_messages = {}
        self.endResetModel()

    def set_issues(self, issues: Iterable[Issue]) -> None:
        """Update per-layer issue indicators from current validation issues."""
        severity_rank = {
            IssueSeverity.INFO: 1,
            IssueSeverity.WARNING: 2,
            IssueSeverity.ERROR: 3,
        }
        self._layer_issue_severity = {}
        self._layer_issue_messages = {}
        for issue in issues:
            if issue.layer_id is None:
                continue
            lid = issue.layer_id
            current = self._layer_issue_severity.get(lid)
            if current is None or severity_rank[issue.severity] > severity_rank[current]:
                self._layer_issue_severity[lid] = issue.severity
            msg = issue.message
            if issue.remediation:
                msg = f"{msg} — {issue.remediation}"
            self._layer_issue_messages.setdefault(lid, []).append(msg)
        if self._layers:
            self.dataChanged.emit(
                self.index(0, int(LayerStackColumn.ISSUE)),
                self.index(len(self._layers) - 1, int(LayerStackColumn.ISSUE)),
            )

    def rowCount(self, _parent: QModelIndex | None = None) -> int:
        return len(self._layers)

    def columnCount(self, _parent: QModelIndex | None = None) -> int:
        return len(LayerStackColumn)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == int(Qt.ItemDataRole.DisplayRole)
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        if not index.isValid():
            return None

        layer = self._layers[index.row()]
        column = LayerStackColumn(index.column())

        if role == int(Qt.ItemDataRole.DisplayRole):
            if column is LayerStackColumn.ISSUE:
                return _issue_display_text(self._layer_issue_severity.get(layer.layer_id))
            return _display_text(layer, column, index.row())
        if role == int(Qt.ItemDataRole.ToolTipRole):
            if column is LayerStackColumn.ISSUE:
                messages = self._layer_issue_messages.get(layer.layer_id)
                return "\n".join(messages) if messages else None
            return _tooltip(layer)
        if role == int(Qt.ItemDataRole.CheckStateRole) and column is LayerStackColumn.VISIBILITY:
            return Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked
        if role == int(Qt.ItemDataRole.TextAlignmentRole):
            if column in {
                LayerStackColumn.VISIBILITY,
                LayerStackColumn.ORDER,
                LayerStackColumn.CLOUD,
                LayerStackColumn.ACTIONS,
            }:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == LayerStackRole.LAYER_ID:
            return layer.layer_id
        if role == LayerStackRole.FULL_PATH:
            return _full_path(layer)
        if role == LayerStackRole.VISIBLE:
            return layer.visible
        if role == LayerStackRole.NO_VISIBLE_WARNING:
            return self.has_no_visible_layers()
        if role == LayerStackRole.ORDER_VALUE:
            return layer.order
        if role == LayerStackRole.METADATA_STATUS:
            return layer.metadata_status
        if role == LayerStackRole.SOURCE_KIND:
            return layer.source_kind
        return None

    def setData(
        self,
        index: QModelIndex,
        value: Any,
        role: int = int(Qt.ItemDataRole.EditRole),
    ) -> bool:
        if (
            not index.isValid()
            or LayerStackColumn(index.column()) is not LayerStackColumn.VISIBILITY
            or role != int(Qt.ItemDataRole.CheckStateRole)
        ):
            return False

        check_state = _coerce_check_state(value)
        if check_state is None:
            return False

        visible = check_state == Qt.CheckState.Checked
        layer = self._layers[index.row()]
        if layer.visible == visible:
            return False

        self._layers[index.row()] = layer.model_copy(update={"visible": visible})
        self.dataChanged.emit(index, index, [role, LayerStackRole.VISIBLE])
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemNeverHasChildren
        )
        if LayerStackColumn(index.column()) is LayerStackColumn.VISIBILITY:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def layer_id_for_index(self, index: QModelIndex) -> str | None:
        """Return the layer id for a table index, if valid."""
        if not index.isValid():
            return None
        return self._layers[index.row()].layer_id

    def visible_for_row(self, row: int) -> bool:
        """Return current local visibility for a row."""
        return self._layers[row].visible

    def ordered_layer_ids(self) -> list[str]:
        """Return current visible table order as layer ids."""
        return [layer.layer_id for layer in self._layers]

    def move_layer(self, layer_id: str, offset: int) -> list[str] | None:
        """Return a new layer id order with one layer moved, or None if not movable."""
        layer_ids = self.ordered_layer_ids()
        try:
            index = layer_ids.index(layer_id)
        except ValueError:
            return None

        new_index = index + offset
        if new_index < 0 or new_index >= len(layer_ids):
            return None

        layer_ids[index], layer_ids[new_index] = layer_ids[new_index], layer_ids[index]
        return layer_ids

    def has_no_visible_layers(self) -> bool:
        """Return true when selected composition has layers but none are visible."""
        return bool(self._layers) and not any(layer.visible for layer in self._layers)


def _display_text(layer: ImageLayer, column: LayerStackColumn, row: int) -> str:
    if column is LayerStackColumn.VISIBILITY:
        return "Hiện" if layer.visible else "Ẩn"
    if column is LayerStackColumn.ORDER:
        return f"{row + 1}"
    if column is LayerStackColumn.TIMESTAMP:
        return _timestamp_text(layer.capture_date, layer.capture_time)
    if column is LayerStackColumn.CLOUD:
        return "--" if layer.cloud_percent is None else f"{layer.cloud_percent:.0f}%"
    if column is LayerStackColumn.METADATA:
        return _metadata_status_label(layer.metadata_status)
    if column is LayerStackColumn.FILENAME:
        return f"{_source_kind_label(layer.source_kind)} | {_short_filename(layer.source_path)}"
    if column is LayerStackColumn.ACTIONS:
        return "..."
    return ""


def _coerce_check_state(value: Any) -> Qt.CheckState | None:
    try:
        return value if isinstance(value, Qt.CheckState) else Qt.CheckState(value)
    except (TypeError, ValueError):
        return None


def _issue_display_text(severity: IssueSeverity | None) -> str:
    if severity is IssueSeverity.ERROR:
        return "✗ ERROR"
    if severity is IssueSeverity.WARNING:
        return "⚠ WARN"
    if severity is IssueSeverity.INFO:
        return "ℹ INFO"
    return ""


def _timestamp_text(capture_date: date | None, capture_time: time | None) -> str:
    if capture_date is None and capture_time is None:
        return "--"
    if capture_date is None:
        return capture_time.strftime("%H:%M") if capture_time is not None else "--"
    if capture_time is None:
        return capture_date.isoformat()
    return f"{capture_date.isoformat()} {capture_time.strftime('%H:%M')}"


def _metadata_status_label(status: MetadataStatus) -> str:
    labels = {
        MetadataStatus.UNKNOWN: "Chưa rõ",
        MetadataStatus.VALID: "Hợp lệ",
        MetadataStatus.NEEDS_CORRECTION: "Cần sửa",
        MetadataStatus.NEEDS_MANUAL_CORRECTION: "Cần nhập tay",
    }
    return labels[status]


def _short_filename(source_path: str) -> str:
    filename = PurePath(source_path).name or source_path
    if len(filename) <= 42:
        return filename
    return f"{filename[:18]}...{filename[-21:]}"


def _full_path(layer: ImageLayer) -> str:
    if layer.cache_path:
        return f"{layer.source_path}\nCache: {layer.cache_path}"
    return layer.source_path


def _source_kind_label(source_kind: ImageLayerSourceKind) -> str:
    if source_kind is ImageLayerSourceKind.HISTORICAL:
        return "Historical"
    return "Current"


def _tooltip(layer: ImageLayer) -> str:
    return (
        f"Layer: {layer.layer_id}\n"
        f"Source: {_source_kind_label(layer.source_kind)}\n"
        f"File: {_full_path(layer)}\n"
        f"Metadata: {_metadata_status_label(layer.metadata_status)} "
        f"({layer.metadata_source.value})"
    )
