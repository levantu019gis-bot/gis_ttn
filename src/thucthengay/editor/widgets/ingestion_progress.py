"""Qt widget for live ingestion progress."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from thucthengay.jobs import JobState, ProgressEvent


class IngestionProgressWidget(QWidget):
    """Render live Setup ingestion progress from headless progress events."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.status_label = QLabel("Chưa lấy dữ liệu")
        self.image_count_label = QLabel("Ảnh đã scan: 0/0")
        self.target_count_label = QLabel("Target đã scan: 0/0")
        self.workspace_count_label = QLabel("Workspace: 0/0")
        self.prepare_count_label = QLabel("Prepare raster: 0/0")
        self.current_target_label = QLabel("Target hiện tại: -")

        self.image_progress = QProgressBar()
        self.target_progress = QProgressBar()
        self.workspace_progress = QProgressBar()
        self.prepare_progress = QProgressBar()

        self.status_label.setObjectName("ingestionProgressStatus")
        self.image_count_label.setObjectName("ingestionProgressImageCount")
        self.target_count_label.setObjectName("ingestionProgressTargetCount")
        self.workspace_count_label.setObjectName("ingestionProgressWorkspaceCount")
        self.prepare_count_label.setObjectName("ingestionProgressPrepareCount")
        self.current_target_label.setObjectName("ingestionProgressCurrentTarget")
        self.image_progress.setObjectName("ingestionImageProgress")
        self.target_progress.setObjectName("ingestionTargetProgress")
        self.workspace_progress.setObjectName("ingestionWorkspaceProgress")
        self.prepare_progress.setObjectName("ingestionPrepareProgress")

        for label in (
            self.status_label,
            self.image_count_label,
            self.target_count_label,
            self.workspace_count_label,
            self.prepare_count_label,
            self.current_target_label,
        ):
            label.setWordWrap(True)

        self.progress_body = QWidget()
        self.progress_body.setObjectName("ingestionProgressBody")
        grid = QGridLayout(self.progress_body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("Anh"), 0, 0)
        grid.addWidget(self.image_progress, 0, 1)
        grid.addWidget(self.image_count_label, 0, 2)
        grid.addWidget(QLabel("Target"), 1, 0)
        grid.addWidget(self.target_progress, 1, 1)
        grid.addWidget(self.target_count_label, 1, 2)
        grid.addWidget(QLabel("Workspace"), 2, 0)
        grid.addWidget(self.workspace_progress, 2, 1)
        grid.addWidget(self.workspace_count_label, 2, 2)
        grid.addWidget(QLabel("Prepare"), 3, 0)
        grid.addWidget(self.prepare_progress, 3, 1)
        grid.addWidget(self.prepare_count_label, 3, 2)
        grid.addWidget(self.current_target_label, 4, 1, 1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_body)

        self.setVisible(False)
        self.progress_body.setVisible(False)
        self._reset_progress_bars()

    def start(self) -> None:
        """Reset and show progress for a new ingestion run."""
        self.status_label.setText("Đang khởi tạo lấy dữ liệu.")
        self.image_count_label.setText("Ảnh đã scan: 0/0")
        self.target_count_label.setText("Target đã scan: 0/0")
        self.workspace_count_label.setText("Workspace: 0/0")
        self.prepare_count_label.setText("Prepare raster: 0/0")
        self.current_target_label.setText("Target hiện tại: -")
        self._reset_progress_bars()
        self.progress_body.setVisible(False)
        self.setVisible(True)

    def apply_event(self, event: ProgressEvent) -> None:
        """Apply a job event without reading workspace state."""
        self.status_label.setText(_status_prefix(event.state, event.message))
        if event.stage != "setup":
            self.progress_body.setVisible(True)

        self._apply_image_progress(event)
        self._apply_target_progress(event)
        self._apply_workspace_progress(event)
        self._apply_prepare_progress(event)
        self._apply_current_target(event)
        self.setVisible(True)

    def show_review_loading(self, composition_count: int) -> None:
        """Show the main-thread workspace load phase before switching tabs."""
        self.status_label.setText("Dang nap workspace vao Review/Edit.")
        self.progress_body.setVisible(True)
        self._set_progress(self.workspace_progress, 7, 7)
        self.workspace_count_label.setText(
            f"Workspace: load Review/Edit ({composition_count} composition)"
        )
        self.setVisible(True)

    def _reset_progress_bars(self) -> None:
        self._set_progress(self.image_progress, 0, 0)
        self._set_progress(self.target_progress, 0, 0)
        self._set_progress(self.workspace_progress, 0, 0)
        self._set_progress(self.prepare_progress, 0, 0)
        self.prepare_progress.setVisible(False)
        self.prepare_count_label.setVisible(False)

    def _apply_image_progress(self, event: ProgressEvent) -> None:
        image_total = event.total_image_count or event.total or 0
        image_current = event.scanned_file_count
        if event.stage == "scan" and event.current is not None:
            image_current = event.current
        self._set_progress(self.image_progress, image_current, image_total)
        self.image_count_label.setText(
            f"Ảnh đã scan: {image_current}/{image_total} "
            f"(hợp lệ: {event.scanned_image_count})"
        )

    def _apply_target_progress(self, event: ProgressEvent) -> None:
        target_total = event.total_target_count
        target_current = event.processed_target_count
        if event.stage == "match" and event.current is not None and event.total is not None:
            target_current = event.current
            target_total = event.total
        self._set_progress(self.target_progress, target_current, target_total)
        self.target_count_label.setText(f"Target đã scan: {target_current}/{target_total}")

    def _apply_workspace_progress(self, event: ProgressEvent) -> None:
        current, total, label = _workspace_progress_for_event(event)
        self._set_progress(self.workspace_progress, current, total)
        self.workspace_count_label.setText(f"Workspace: {label} ({current}/{total})")

    def _apply_prepare_progress(self, event: ProgressEvent) -> None:
        total = event.total_prepare_raster_count
        current = event.prepared_raster_count
        should_show = total > 0
        self.prepare_progress.setVisible(should_show)
        self.prepare_count_label.setVisible(should_show)
        if not should_show:
            self._set_progress(self.prepare_progress, 0, 0)
            self.prepare_count_label.setText("Prepare raster: 0/0")
            return
        self._set_progress(self.prepare_progress, current, total)
        self.prepare_count_label.setText(f"Prepare raster: {current}/{total}")

    def _apply_current_target(self, event: ProgressEvent) -> None:
        if event.current_target_name:
            self.current_target_label.setText(
                f"Target hiện tại: {event.current_target_name} - "
                f"đã lấy {event.current_target_matched_count} ảnh"
            )
        elif event.total_target_count == 0:
            self.current_target_label.setText("Target hiện tại: chưa có target bật")

    @staticmethod
    def _set_progress(progress: QProgressBar, current: int, total: int) -> None:
        progress.setMinimum(0)
        progress.setMaximum(max(total, 0))
        progress.setValue(min(max(current, 0), max(total, 0)))
        progress.setFormat(f"{current}/{total}" if total else "0/0")


def _workspace_progress_for_event(event: ProgressEvent) -> tuple[int, int, str]:
    total = 7
    phase_map = {
        "setup": (0, "setup"),
        "scan": (1, "scan imagery"),
        "match": (2, "match targets"),
        "history": (3, "load history"),
        "cache": (4, "copy cache"),
        "prepare": (5, "prepare raster"),
        "composition": (6, "create compositions"),
        "review_load": (7, "load Review/Edit"),
        "complete": (7, "complete"),
    }
    current, label = phase_map.get(event.stage, (0, event.stage or "idle"))
    return current, total, label


def _status_prefix(state: JobState, message: str) -> str:
    if state == JobState.CANCELLED:
        return f"Đã dừng lấy dữ liệu: {message}"
    if state == JobState.ERROR:
        return f"Lấy dữ liệu thất bại: {message}"
    if state == JobState.WARNING:
        return f"Lấy dữ liệu hoàn tất với cảnh báo: {message}"
    if state == JobState.SUCCESS:
        return f"Lấy dữ liệu thành công: {message}"
    return message
