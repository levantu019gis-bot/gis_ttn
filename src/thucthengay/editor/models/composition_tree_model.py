"""Qt model for Review/Edit target-composition navigation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

from thucthengay.models import Composition, PersistedValidationState, TargetConfig


class TreeNodeKind(StrEnum):
    """Node types exposed by the composition tree."""

    TARGET = "target"
    COMPOSITION = "composition"


class QueueFilter(StrEnum):
    """Review/Edit queue filters shown above the composition tree."""

    ALL = "all"
    UNREVIEWED = "unreviewed"
    READY = "ready"
    INCLUDE = "include"
    WARNING = "warning"
    ERROR = "error"


class CompositionTreeRole(IntEnum):
    """Custom roles consumed by Review/Edit views and tests."""

    NODE_KIND = int(Qt.ItemDataRole.UserRole) + 1
    TARGET_ID = int(Qt.ItemDataRole.UserRole) + 2
    COMPOSITION_ID = int(Qt.ItemDataRole.UserRole) + 3
    STATUS_TEXT = int(Qt.ItemDataRole.UserRole) + 4
    SEVERITY_TEXT = int(Qt.ItemDataRole.UserRole) + 5
    ISSUE_COUNT = int(Qt.ItemDataRole.UserRole) + 6


@dataclass
class _TreeNode:
    kind: TreeNodeKind | None
    label: str
    parent: _TreeNode | None = None
    target_id: str | None = None
    composition: Composition | None = None
    children: list[_TreeNode] = field(default_factory=list)

    def append_child(self, child: _TreeNode) -> None:
        child.parent = self
        self.children.append(child)

    @property
    def row(self) -> int:
        if self.parent is None:
            return 0
        return self.parent.children.index(self)


class CompositionTreeModel(QAbstractItemModel):
    """Projection of workspace compositions grouped by reporting target."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = _TreeNode(kind=None, label="root")
        self._all_compositions: list[Composition] = []
        self._targets: list[TargetConfig] = []
        self._active_filter = QueueFilter.ALL
        self._filter_counts: dict[QueueFilter, int] = {
            queue_filter: 0 for queue_filter in QueueFilter
        }

    def set_compositions(
        self,
        compositions: list[Composition],
        *,
        targets: list[TargetConfig] | None = None,
    ) -> None:
        """Replace model contents from workspace compositions and optional config targets."""
        self.beginResetModel()
        self._all_compositions = list(compositions)
        self._targets = list(targets or [])
        self._filter_counts = _filter_counts(self._all_compositions)
        self._rebuild_tree()
        self.endResetModel()

    def replace_composition(self, composition: Composition) -> bool:
        """Replace one composition in the current projection source."""
        updated: list[Composition] = []
        found = False
        for existing in self._all_compositions:
            if existing.composition_id == composition.composition_id:
                updated.append(composition)
                found = True
            else:
                updated.append(existing)
        if not found:
            return False

        self.beginResetModel()
        self._all_compositions = updated
        self._filter_counts = _filter_counts(self._all_compositions)
        self._rebuild_tree()
        self.endResetModel()
        return True

    @property
    def active_queue_filter(self) -> QueueFilter:
        """Current queue filter applied to visible tree rows."""
        return self._active_filter

    def set_queue_filter(self, queue_filter: QueueFilter) -> None:
        """Apply a queue filter while preserving the full composition source list."""
        if queue_filter == self._active_filter:
            return

        self.beginResetModel()
        self._active_filter = queue_filter
        self._rebuild_tree()
        self.endResetModel()

    def filter_counts(self) -> dict[QueueFilter, int]:
        """Return aggregate counts for each queue filter from the full queue."""
        return dict(self._filter_counts)

    def visible_composition_count(self) -> int:
        """Return the number of visible compositions after filtering."""
        return sum(len(target.children) for target in self._root.children)

    def has_visible_compositions(self) -> bool:
        """Return whether the active filter leaves at least one composition visible."""
        return self.visible_composition_count() > 0

    def is_composition_visible(self, composition_id: str) -> bool:
        """Return whether a composition id is visible in the active projection."""
        return self.index_for_composition_id(composition_id).isValid()

    def index_for_composition_id(self, composition_id: str) -> QModelIndex:
        """Return the model index for a visible composition id, otherwise an invalid index."""
        for target_row, target_node in enumerate(self._root.children):
            for composition_row, composition_node in enumerate(target_node.children):
                composition = composition_node.composition
                if composition is not None and composition.composition_id == composition_id:
                    target_index = self.index(target_row, 0)
                    return self.index(composition_row, 0, target_index)
        return QModelIndex()

    def index_for_target_id(self, target_id: str) -> QModelIndex:
        """Return the model index for a visible target id, otherwise an invalid index."""
        for target_row, target_node in enumerate(self._root.children):
            if target_node.target_id == target_id:
                return self.index(target_row, 0)
        return QModelIndex()

    def _rebuild_tree(self) -> None:
        self._root = _TreeNode(kind=None, label="root")
        target_lookup = {target.id: target for target in self._targets}

        grouped: dict[str, list[Composition]] = {}
        for composition in self._filtered_compositions():
            grouped.setdefault(composition.target_id, []).append(composition)

        for target_id in sorted(
            grouped,
            key=lambda item: (
                target_lookup[item].sort_order if item in target_lookup else 10_000,
                item,
            ),
        ):
            target = target_lookup.get(target_id)
            target_node = _TreeNode(
                kind=TreeNodeKind.TARGET,
                label=_target_label(target_id, target),
                target_id=target_id,
            )
            self._root.append_child(target_node)

            for composition in sorted(grouped[target_id], key=_composition_sort_key):
                target_node.append_child(
                    _TreeNode(
                        kind=TreeNodeKind.COMPOSITION,
                        label=composition.composition_id,
                        target_id=target_id,
                        composition=composition,
                    )
                )

    def _filtered_compositions(self) -> list[Composition]:
        return [
            composition
            for composition in self._all_compositions
            if _matches_filter(composition, self._active_filter)
        ]

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex | None = None,
    ) -> QModelIndex:
        if column != 0 or row < 0:
            return QModelIndex()

        parent_node = self._node_from_index(parent)
        if row >= len(parent_node.children):
            return QModelIndex()

        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        node = self._node_from_index(index)
        parent_node = node.parent
        if parent_node is None or parent_node is self._root:
            return QModelIndex()

        return self.createIndex(parent_node.row, 0, parent_node)

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._node_from_index(parent).children)

    def columnCount(self, _parent: QModelIndex | None = None) -> int:
        return 1

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        if not index.isValid():
            return None

        node = self._node_from_index(index)
        if node.kind is TreeNodeKind.TARGET:
            return self._target_data(node, role)
        if node.kind is TreeNodeKind.COMPOSITION and node.composition is not None:
            return self._composition_data(node.composition, role)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        flags = Qt.ItemFlag.ItemIsEnabled
        node = self._node_from_index(index)
        if node.kind is TreeNodeKind.COMPOSITION:
            flags |= Qt.ItemFlag.ItemIsSelectable
        return flags

    def composition_id_for_index(self, index: QModelIndex) -> str | None:
        """Return composition id for a composition row, otherwise None."""
        if not index.isValid():
            return None
        node = self._node_from_index(index)
        if node.kind is not TreeNodeKind.COMPOSITION or node.composition is None:
            return None
        return node.composition.composition_id

    def _target_data(self, node: _TreeNode, role: int) -> Any:
        issue_count = sum(_issue_count(child.composition) for child in node.children)
        severity = _highest_severity(child.composition for child in node.children)
        if role == int(Qt.ItemDataRole.DisplayRole):
            suffix = f" - {len(node.children)} composition"
            if len(node.children) != 1:
                suffix += "s"
            issue_text = "1 vấn đề" if issue_count == 1 else f"{issue_count} vấn đề"
            return f"[{severity}] {node.label}{suffix} | {issue_text}"
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return (
                f"Target: {node.label}\n"
                f"Compositions: {len(node.children)}\n"
                f"Issues: {issue_count}"
            )
        if role == int(Qt.ItemDataRole.DecorationRole):
            return _standard_icon(severity)
        if role == CompositionTreeRole.NODE_KIND:
            return TreeNodeKind.TARGET
        if role == CompositionTreeRole.TARGET_ID:
            return node.target_id
        if role == CompositionTreeRole.SEVERITY_TEXT:
            return severity
        if role == CompositionTreeRole.ISSUE_COUNT:
            return issue_count
        return None

    def _composition_data(self, composition: Composition, role: int) -> Any:
        status = _status_text(composition)
        severity = _severity_text(composition)
        issue_count = _issue_count(composition)
        if role == int(Qt.ItemDataRole.DisplayRole):
            issue_text = "1 vấn đề" if issue_count == 1 else f"{issue_count} vấn đề"
            date_text = composition.capture_date.isoformat()
            return (
                f"[{severity}] {composition.composition_id} | {date_text} "
                f"{_capture_time_text(composition)} | {status} | {issue_text}"
            )
        if role == int(Qt.ItemDataRole.ToolTipRole):
            summary = composition.validation_summary
            layer_note = (
                "\nLayer issue: Không có layer đang bật."
                if _has_no_visible_layers(composition)
                else ""
            )
            return (
                f"Composition: {composition.composition_id}\n"
                f"Status: {status}\n"
                f"Validation: {composition.persisted_validation_state.value}\n"
                f"Info: {summary.info_count}; Warnings: {summary.warning_count}; "
                f"Errors: {summary.error_count}\n"
                f"Layers: {len(composition.layers)}"
                f"{layer_note}"
            )
        if role == int(Qt.ItemDataRole.DecorationRole):
            return _standard_icon(severity)
        if role == CompositionTreeRole.NODE_KIND:
            return TreeNodeKind.COMPOSITION
        if role == CompositionTreeRole.TARGET_ID:
            return composition.target_id
        if role == CompositionTreeRole.COMPOSITION_ID:
            return composition.composition_id
        if role == CompositionTreeRole.STATUS_TEXT:
            return status
        if role == CompositionTreeRole.SEVERITY_TEXT:
            return severity
        if role == CompositionTreeRole.ISSUE_COUNT:
            return issue_count
        return None

    def _node_from_index(self, index: QModelIndex | None) -> _TreeNode:
        if index is None or not index.isValid():
            return self._root
        node = index.internalPointer()
        if isinstance(node, _TreeNode):
            return node
        return self._root


def _target_label(target_id: str, target: TargetConfig | None) -> str:
    if target is None:
        return target_id
    if target.alias:
        return f"{target.alias} - {target.name}"
    return target.name


def _composition_sort_key(composition: Composition) -> tuple[int, int, str, str]:
    review_bucket = 0 if composition.review_order is not None else 1
    review_order = composition.review_order or 0
    return (
        review_bucket,
        review_order,
        composition.capture_date.isoformat(),
        composition.composition_id,
    )


def _status_text(composition: Composition) -> str:
    if _has_no_visible_layers(composition):
        return "Không có layer bật"
    if composition.needs_revalidation:
        return "Cần kiểm tra lại"
    if composition.include and composition.ready:
        return "Include"
    if composition.ready:
        return "Ready"
    if composition.reviewed:
        return "Skip"
    return "Chưa duyệt"


def queue_filter_label(queue_filter: QueueFilter) -> str:
    """Return the Vietnamese label for a queue filter."""
    labels = {
        QueueFilter.ALL: "Tất cả",
        QueueFilter.UNREVIEWED: "Chưa duyệt",
        QueueFilter.READY: "Ready",
        QueueFilter.INCLUDE: "Include",
        QueueFilter.WARNING: "Có warning",
        QueueFilter.ERROR: "Có error",
    }
    return labels[queue_filter]


def _filter_counts(compositions: list[Composition]) -> dict[QueueFilter, int]:
    return {
        queue_filter: sum(
            1 for composition in compositions if _matches_filter(composition, queue_filter)
        )
        for queue_filter in QueueFilter
    }


def _matches_filter(composition: Composition, queue_filter: QueueFilter) -> bool:
    if queue_filter is QueueFilter.ALL:
        return True
    if queue_filter is QueueFilter.UNREVIEWED:
        return not composition.reviewed
    if queue_filter is QueueFilter.READY:
        return composition.ready and not composition.include
    if queue_filter is QueueFilter.INCLUDE:
        return composition.ready and composition.include
    if queue_filter is QueueFilter.WARNING:
        return (
            composition.persisted_validation_state is PersistedValidationState.WARNING
            or composition.validation_summary.warning_count > 0
        )
    if queue_filter is QueueFilter.ERROR:
        return (
            _has_no_visible_layers(composition)
            or composition.persisted_validation_state is PersistedValidationState.ERROR
            or composition.validation_summary.error_count > 0
        )
    return False


def _severity_text(composition: Composition) -> str:
    if _has_no_visible_layers(composition):
        return "ERROR"
    state = composition.persisted_validation_state
    if state is PersistedValidationState.ERROR:
        return "ERROR"
    if state is PersistedValidationState.WARNING:
        return "WARN"
    if state is PersistedValidationState.STALE:
        return "STALE"
    if composition.validation_summary.info_count > 0:
        return "INFO"
    return "OK"


def _highest_severity(compositions: Any) -> str:
    rank = {"ERROR": 4, "WARN": 3, "STALE": 2, "INFO": 1, "OK": 0}
    highest = "OK"
    for composition in compositions:
        if composition is None:
            continue
        severity = _severity_text(composition)
        if rank[severity] > rank[highest]:
            highest = severity
    return highest


def _issue_count(composition: Composition | None) -> int:
    if composition is None:
        return 0
    summary = composition.validation_summary
    layer_issue_count = 1 if _has_no_visible_layers(composition) else 0
    return summary.info_count + summary.warning_count + summary.error_count + layer_issue_count


def _capture_time_text(composition: Composition) -> str:
    times = [layer.capture_time for layer in composition.layers if layer.capture_time is not None]
    if not times:
        return "--:--"
    return min(times).strftime("%H:%M")


def _has_no_visible_layers(composition: Composition) -> bool:
    return bool(composition.layers) and not any(layer.visible for layer in composition.layers)


def _standard_icon(severity: str) -> QIcon:
    app = QApplication.instance()
    if app is None:
        return QIcon()

    style = app.style()
    if severity == "ERROR":
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
    if severity in {"WARN", "STALE"}:
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
    if severity == "INFO":
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
    return style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
