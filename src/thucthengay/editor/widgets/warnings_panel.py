"""Warnings panel widget showing structured validation issues."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from thucthengay.models import Issue, IssueSeverity


class WarningsPanelWidget(QWidget):
    """Panel listing validation issues with severity indicators and jump navigation."""

    jumpRequested = Signal(str, str, str)  # (target_id, composition_id, layer_id)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("warningsPanel")

        self._header = QLabel("Validation Issues")
        self._header.setObjectName("warningsPanelHeader")

        self._list = QListWidget()
        self._list.setObjectName("warningsIssueList")
        self._list.setWordWrap(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._header)
        layout.addWidget(self._list, 1)

    def set_issues(
        self,
        issues: Iterable[Issue],
        *,
        composition_id: str = "",
        target_id: str = "",
    ) -> None:
        """Populate the panel with current validation issues."""
        self._list.clear()
        issue_list = list(issues)
        if not issue_list:
            item = QListWidgetItem("Không có vấn đề nào.")
            item.setData(1000, ("", "", ""))
            self._list.addItem(item)
            return

        for issue in issue_list:
            ref_parts = []
            if issue.target_id:
                ref_parts.append(f"target:{issue.target_id}")
            elif target_id:
                ref_parts.append(f"target:{target_id}")
            if issue.composition_id:
                ref_parts.append(f"comp:{issue.composition_id}")
            elif composition_id:
                ref_parts.append(f"comp:{composition_id}")
            if issue.layer_id:
                ref_parts.append(f"layer:{issue.layer_id}")

            ref_text = " | ".join(ref_parts)
            severity_label = issue.severity.value.upper()
            text = f"[{severity_label}] {issue.scope.value}: {issue.message}"
            if ref_text:
                text = f"{text} | {ref_text}"
            if issue.remediation:
                text = f"{text}\n  → {issue.remediation}"
            text = f"{text}\n  → điều hướng"

            if _is_historical_path_issue(issue):
                text = f"{text}\n  -> sua duong dan"

            item = QListWidgetItem(text)
            item.setIcon(_severity_icon(issue.severity))
            resolved_target = issue.target_id or target_id
            resolved_comp = issue.composition_id or composition_id
            resolved_layer = issue.layer_id or ""
            item.setData(1000, (resolved_target, resolved_comp, resolved_layer))
            self._list.addItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(1000)
        if data is None:
            return
        target_id, composition_id, layer_id = data
        self.jumpRequested.emit(target_id, composition_id, layer_id)


def _severity_icon(severity: IssueSeverity) -> QIcon:
    app = QApplication.instance()
    if app is None:
        return QIcon()
    style = app.style()
    if severity is IssueSeverity.ERROR:
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
    if severity is IssueSeverity.WARNING:
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
    return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)


def _is_historical_path_issue(issue: Issue) -> bool:
    return issue.issue_id in {
        "historical.path_missing",
        "historical.geotiff_unreadable",
        "historical.geotiff_unusable",
    }
