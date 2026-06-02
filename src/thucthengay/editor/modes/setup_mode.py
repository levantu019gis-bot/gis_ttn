"""Setup mode for selecting project input paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from thucthengay.editor.widgets.ingestion_progress import IngestionProgressWidget
from thucthengay.editor.widgets.ingestion_summary import IngestionSummaryWidget
from thucthengay.editor.widgets.path_picker import PathKind, PathPickerRow
from thucthengay.editor.widgets.workspace_confirmation import confirm_workspace_clear
from thucthengay.jobs import IngestionSummary, ProgressEvent
from thucthengay.workspace import WorkspaceService


@dataclass(frozen=True)
class SetupPaths:
    """Validated paths selected in Setup mode."""

    config_file: Path
    imagery_input_folder: Path
    workspace_folder: Path


class SetupMode(QWidget):
    """Setup screen containing required project path pickers."""

    ingestRequested = Signal(object)
    openWorkspaceRequested = Signal(object)
    pauseRequested = Signal()
    resumeRequested = Signal()
    stopRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config_row = PathPickerRow("Config JSON", PathKind.CONFIG_FILE)
        self.imagery_row = PathPickerRow("Thư mục ảnh", PathKind.INPUT_FOLDER)
        self.workspace_row = PathPickerRow("Workspace", PathKind.WORKSPACE_FOLDER)
        self.ingest_button = QPushButton("Lấy dữ liệu")
        self.ingest_button.setObjectName("setupIngestButton")
        self.open_workspace_button = QPushButton("Mở workspace")
        self.open_workspace_button.setObjectName("setupOpenWorkspaceButton")
        self.pause_button = QPushButton("Tạm dừng")
        self.pause_button.setObjectName("setupPauseButton")
        self.stop_button = QPushButton("Dừng")
        self.stop_button.setObjectName("setupStopButton")
        self.workspace_status_label = QLabel("Chưa mở workspace.")
        self.workspace_status_label.setObjectName("setupWorkspaceStatus")
        self.workspace_status_label.setWordWrap(True)
        self.progress_widget = IngestionProgressWidget()
        self.summary_widget = IngestionSummaryWidget()
        self._ingestion_running = False
        self._ingestion_paused = False
        self._ingestion_stopping = False

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.addRow(self.config_row)
        form.addRow(self.imagery_row)
        form.addRow(self.workspace_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addWidget(self.progress_widget)
        layout.addWidget(self.summary_widget)
        layout.addStretch(1)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.ingest_button)
        actions.addWidget(self.open_workspace_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.stop_button)
        layout.addLayout(actions)
        layout.addWidget(self.workspace_status_label)

        for row in self.path_rows:
            row.validationChanged.connect(self._update_action_state)
        self.ingest_button.clicked.connect(self._emit_ingest_requested)
        self.open_workspace_button.clicked.connect(self._emit_open_workspace_requested)
        self.pause_button.clicked.connect(self._toggle_pause_requested)
        self.stop_button.clicked.connect(self._emit_stop_requested)
        self._update_action_state()

    @property
    def path_rows(self) -> tuple[PathPickerRow, PathPickerRow, PathPickerRow]:
        return (self.config_row, self.imagery_row, self.workspace_row)

    @property
    def blockers(self) -> list[str]:
        return [row.validation.message for row in self.path_rows if not row.validation.ok]

    @property
    def is_ready(self) -> bool:
        return not self.blockers

    def selected_paths(self) -> SetupPaths | None:
        if not self.is_ready:
            return None

        config_file = self.config_row.selected_path
        imagery_folder = self.imagery_row.selected_path
        workspace_folder = self.workspace_row.selected_path
        if config_file is None or imagery_folder is None or workspace_folder is None:
            return None

        return SetupPaths(
            config_file=config_file,
            imagery_input_folder=imagery_folder,
            workspace_folder=workspace_folder,
        )

    def selected_workspace_folder(self) -> Path | None:
        """Return the selected workspace folder when it is valid."""
        return self.workspace_row.selected_path

    def _update_action_state(self, *_args: object) -> None:
        self.ingest_button.setEnabled(self.is_ready and not self._ingestion_running)
        self.open_workspace_button.setEnabled(
            self.workspace_row.validation.ok and not self._ingestion_running
        )
        self.pause_button.setVisible(self._ingestion_running)
        self.stop_button.setVisible(self._ingestion_running)
        self.pause_button.setEnabled(self._ingestion_running and not self._ingestion_stopping)
        self.stop_button.setEnabled(self._ingestion_running and not self._ingestion_stopping)
        self.pause_button.setText("Tiếp tục" if self._ingestion_paused else "Tạm dừng")
        if self._ingestion_running:
            self.ingest_button.setToolTip("Đang lấy dữ liệu.")
            self.pause_button.setToolTip(
                "Tiếp tục lấy dữ liệu." if self._ingestion_paused else "Tạm dừng lấy dữ liệu."
            )
            self.stop_button.setToolTip(
                "Đang yêu cầu dừng." if self._ingestion_stopping else "Dừng lấy dữ liệu."
            )
            self.open_workspace_button.setToolTip("Không thể mở workspace khi đang lấy dữ liệu.")
            return
        if self.workspace_row.validation.ok:
            self.open_workspace_button.setToolTip(
                "Mở workspace đã có và tiếp tục Review/Edit."
            )
        else:
            self.open_workspace_button.setToolTip(self.workspace_row.validation.message)
        if self.is_ready:
            self.ingest_button.setToolTip("Sẵn sàng lấy dữ liệu.")
            return

        first_blocker = self.blockers[0] if self.blockers else "Chưa đủ đường dẫn hợp lệ."
        self.ingest_button.setToolTip(first_blocker)

    def _emit_ingest_requested(self) -> None:
        selected_paths = self.selected_paths()
        if selected_paths is None:
            return

        workspace_service = WorkspaceService(selected_paths.workspace_folder)
        if workspace_service.has_app_owned_data():
            clear_confirmed = confirm_workspace_clear(self, workspace_service.clear_plan())
            if not clear_confirmed:
                return

        self.ingestRequested.emit(selected_paths)

    def _emit_open_workspace_requested(self) -> None:
        workspace_folder = self.selected_workspace_folder()
        if workspace_folder is None:
            return

        self.openWorkspaceRequested.emit(workspace_folder)

    def _toggle_pause_requested(self) -> None:
        if not self._ingestion_running or self._ingestion_stopping:
            return
        if self._ingestion_paused:
            self.resumeRequested.emit()
            return
        self.pauseRequested.emit()

    def _emit_stop_requested(self) -> None:
        if not self._ingestion_running or self._ingestion_stopping:
            return
        self.stopRequested.emit()

    def start_ingestion_progress(self) -> None:
        """Show live progress and lock the ingest action during a run."""
        self._ingestion_running = True
        self._ingestion_paused = False
        self._ingestion_stopping = False
        self.progress_widget.start()
        self._update_action_state()

    def mark_ingestion_paused(self) -> None:
        """Reflect that the active ingestion job is paused."""
        if not self._ingestion_running:
            return
        self._ingestion_paused = True
        self.progress_widget.status_label.setText("Đã tạm dừng lấy dữ liệu.")
        self._update_action_state()

    def mark_ingestion_resumed(self) -> None:
        """Reflect that the active ingestion job has resumed."""
        if not self._ingestion_running:
            return
        self._ingestion_paused = False
        self.progress_widget.status_label.setText("Đang tiếp tục lấy dữ liệu.")
        self._update_action_state()

    def mark_ingestion_stopping(self) -> None:
        """Reflect that the active ingestion job is stopping."""
        if not self._ingestion_running:
            return
        self._ingestion_stopping = True
        self._ingestion_paused = False
        self.progress_widget.status_label.setText("Đang dừng lấy dữ liệu.")
        self._update_action_state()

    def show_ingestion_progress(self, event: ProgressEvent) -> None:
        """Show one live ingestion progress event."""
        self.progress_widget.apply_event(event)
        if event.terminal:
            self._ingestion_running = False
            self._ingestion_paused = False
            self._ingestion_stopping = False
            self._update_action_state()

    def show_ingestion_summary(self, summary: IngestionSummary) -> None:
        """Show the latest ingestion summary in Setup mode."""
        self._ingestion_running = False
        self._ingestion_paused = False
        self._ingestion_stopping = False
        self._update_action_state()
        self.summary_widget.show_summary(summary)

    def show_workspace_opened(self, workspace_folder: Path, composition_count: int) -> None:
        """Show that an existing workspace has been loaded into Review/Edit."""
        self.workspace_status_label.setText(
            f"Đã mở workspace: {workspace_folder} ({composition_count} composition)."
        )

    def show_workspace_open_error(self, message: str) -> None:
        """Show why an existing workspace could not be opened."""
        self.workspace_status_label.setText(
            f"Không mở được workspace: {message.strip() or 'Lỗi chưa xác định.'}"
        )
