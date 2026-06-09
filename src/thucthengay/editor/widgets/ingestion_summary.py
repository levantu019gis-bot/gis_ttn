"""Qt widget for post-ingestion summary and warning rows."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from thucthengay.jobs import IngestionSummary, IngestionWarningItem, JobState


class IngestionSummaryWidget(QWidget):
    """Render the latest ingestion result without reading workspace JSON."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.status_label = QLabel("")
        self.empty_state_label = QLabel("")
        self.historical_empty_state_label = QLabel("")
        self.workspace_label = QLabel("")
        self.warning_list = QListWidget()

        self.status_label.setObjectName("ingestionSummaryStatus")
        self.empty_state_label.setObjectName("ingestionSummaryEmptyState")
        self.historical_empty_state_label.setObjectName("ingestionSummaryHistoricalEmptyState")
        self.workspace_label.setObjectName("ingestionSummaryWorkspace")
        self.warning_list.setObjectName("ingestionWarningList")

        self.empty_state_label.setWordWrap(True)
        self.historical_empty_state_label.setWordWrap(True)
        self.workspace_label.setWordWrap(True)

        self.scanned_label = QLabel("0")
        self.matched_label = QLabel("0")
        self.targets_label = QLabel("0")
        self.compositions_label = QLabel("0")
        self.warnings_label = QLabel("0")
        self.historical_loaded_label = QLabel("0")
        self.historical_skipped_label = QLabel("0")
        self.historical_path_issues_label = QLabel("0")
        for label in (
            self.scanned_label,
            self.matched_label,
            self.targets_label,
            self.compositions_label,
            self.warnings_label,
            self.historical_loaded_label,
            self.historical_skipped_label,
            self.historical_path_issues_label,
        ):
            label.setMinimumWidth(72)

        counters = QGridLayout()
        counters.setContentsMargins(0, 0, 0, 0)
        counters.setHorizontalSpacing(12)
        counters.setVerticalSpacing(6)
        counters.addWidget(QLabel("Ảnh quét"), 0, 0)
        counters.addWidget(self.scanned_label, 0, 1)
        counters.addWidget(QLabel("Ảnh khớp"), 0, 2)
        counters.addWidget(self.matched_label, 0, 3)
        counters.addWidget(QLabel("Target có ảnh"), 1, 0)
        counters.addWidget(self.targets_label, 1, 1)
        counters.addWidget(QLabel("Composition"), 1, 2)
        counters.addWidget(self.compositions_label, 1, 3)
        counters.addWidget(QLabel("Cảnh báo"), 2, 0)
        counters.addWidget(self.warnings_label, 2, 1)
        self.historical_loaded_title = QLabel("Historical loaded")
        self.historical_skipped_title = QLabel("Historical skipped")
        self.historical_path_issues_title = QLabel("Historical path issues")
        counters.addWidget(self.historical_loaded_title, 3, 0)
        counters.addWidget(self.historical_loaded_label, 3, 1)
        counters.addWidget(self.historical_skipped_title, 3, 2)
        counters.addWidget(self.historical_skipped_label, 3, 3)
        counters.addWidget(self.historical_path_issues_title, 4, 0)
        counters.addWidget(self.historical_path_issues_label, 4, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.status_label)
        layout.addLayout(counters)
        layout.addWidget(self.workspace_label)
        layout.addWidget(self.empty_state_label)
        layout.addWidget(self.historical_empty_state_label)
        layout.addWidget(self.warning_list)

        self.setVisible(False)

    def show_summary(self, summary: IngestionSummary) -> None:
        """Render a summary produced by the ingestion job layer."""
        self.status_label.setText(_status_text(summary.state))
        self.status_label.setProperty("state", summary.state.value)
        self.scanned_label.setText(str(summary.scanned_image_count))
        self.matched_label.setText(str(summary.matched_image_count))
        self.targets_label.setText(str(summary.targets_with_images_count))
        self.compositions_label.setText(str(summary.created_composition_count))
        self.warnings_label.setText(str(summary.warning_count))
        self.historical_loaded_label.setText(str(summary.historical_loaded_image_count))
        self.historical_skipped_label.setText(str(summary.historical_skipped_image_count))
        self.historical_path_issues_label.setText(str(summary.historical_path_issue_count))
        self.workspace_label.setText(f"Workspace: {summary.workspace_path}")

        self.empty_state_label.setText(summary.empty_state_message or "")
        self.empty_state_label.setVisible(summary.empty)
        self.historical_empty_state_label.setText(summary.historical_empty_message or "")
        self.historical_empty_state_label.setVisible(summary.historical_empty_message is not None)
        self._set_historical_counters_visible(summary.historical_loading_enabled)

        self.warning_list.clear()
        for warning in summary.warnings:
            self.warning_list.addItem(_warning_text(warning))
        self.warning_list.setVisible(bool(summary.warnings))
        self.setVisible(True)

    def _set_historical_counters_visible(self, visible: bool) -> None:
        for widget in (
            self.historical_loaded_title,
            self.historical_loaded_label,
            self.historical_skipped_title,
            self.historical_skipped_label,
            self.historical_path_issues_title,
            self.historical_path_issues_label,
        ):
            widget.setVisible(visible)


def _status_text(state: JobState) -> str:
    if state == JobState.SUCCESS:
        return "Lấy dữ liệu thành công"
    if state == JobState.WARNING:
        return "Lấy dữ liệu hoàn tất với cảnh báo"
    if state == JobState.CANCELLED:
        return "Đã dừng lấy dữ liệu"
    if state == JobState.ERROR:
        return "Lấy dữ liệu thất bại"
    if state == JobState.RUNNING:
        return "Đang lấy dữ liệu"
    return "Chưa lấy dữ liệu"


def _warning_text(warning: IngestionWarningItem) -> str:
    affected = warning.affected_object or "Không xác định"
    text = f"{warning.scope.value}: {affected} - {warning.message}"
    if warning.remediation:
        text = f"{text}\nCách xử lý: {warning.remediation}"
    return text
