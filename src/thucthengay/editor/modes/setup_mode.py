"""Setup mode for selecting project input paths."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from thucthengay.config import read_historical_loading_settings
from thucthengay.editor.preferences import RecentProjectEntry, SetupPreferences
from thucthengay.editor.widgets.ingestion_progress import IngestionProgressWidget
from thucthengay.editor.widgets.ingestion_summary import IngestionSummaryWidget
from thucthengay.editor.widgets.path_picker import PathKind, PathPickerRow
from thucthengay.editor.widgets.workspace_confirmation import (
    ExistingWorkspaceAction,
    choose_existing_workspace_action,
)
from thucthengay.jobs import IngestionSummary, ProgressEvent
from thucthengay.models import HistoricalImageSelectionConfig, HistoricalSelectionMode
from thucthengay.workspace import WorkspaceService

_HISTORICAL_MODE_LATEST_DATE = "latest_date"
_HISTORICAL_MODE_DATE_RANGE = "date_range"


@dataclass(frozen=True)
class SetupPaths:
    """Validated paths selected in Setup mode."""

    config_file: Path
    imagery_input_folder: Path
    workspace_folder: Path
    historical_loading_enabled: bool = False
    historical_image_selection: HistoricalImageSelectionConfig | None = None
    include_unmatched_images: bool = False
    clear_existing_workspace: bool = False
    clear_workspace_confirmed: bool = False
    override_existing_workspace: bool = False


class SetupMode(QWidget):
    """Setup screen containing required project path pickers."""

    ingestRequested = Signal(object)
    openWorkspaceRequested = Signal(object)
    pauseRequested = Signal()
    resumeRequested = Signal()
    stopRequested = Signal()
    recentProjectRemoveRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._recent_projects: list[RecentProjectEntry] = []
        self.config_row = PathPickerRow("Config JSON", PathKind.CONFIG_FILE)
        self.imagery_row = PathPickerRow("Thư mục ảnh", PathKind.INPUT_FOLDER)
        self.workspace_row = PathPickerRow("Workspace", PathKind.WORKSPACE_FOLDER)
        self.recent_project_combo = QComboBox()
        self.recent_project_combo.setObjectName("setupRecentProjectCombo")
        self.recent_project_combo.setMinimumWidth(260)
        self.apply_recent_button = QPushButton("Áp dụng")
        self.apply_recent_button.setObjectName("setupApplyRecentProject")
        self.remove_recent_button = QPushButton("Xóa")
        self.remove_recent_button.setObjectName("setupRemoveRecentProject")
        self.ingest_button = QPushButton("Lấy dữ liệu")
        self.ingest_button.setObjectName("setupIngestButton")
        self.open_workspace_button = QPushButton("Mở workspace")
        self.open_workspace_button.setObjectName("setupOpenWorkspaceButton")
        self.historical_loading_checkbox = QCheckBox("Load historical images")
        self.historical_loading_checkbox.setObjectName("setupHistoricalLoadingEnabled")
        self.historical_loading_checkbox.setToolTip(
            "When enabled, ingestion also loads eligible images from the configured "
            "SQLite historical registry."
        )
        self.include_unmatched_checkbox = QCheckBox("Load images outside configured geometry")
        self.include_unmatched_checkbox.setObjectName("setupIncludeUnmatchedImages")
        self.include_unmatched_checkbox.setToolTip(
            "Keep valid GeoTIFFs that do not intersect any enabled target geometry and "
            "show them in a separate Review/Edit group."
        )
        self.historical_mode_combo = QComboBox()
        self.historical_mode_combo.setObjectName("setupHistoricalLoadingMode")
        self.historical_mode_combo.addItem(
            "Latest date",
            _HISTORICAL_MODE_LATEST_DATE,
        )
        self.historical_mode_combo.addItem(
            "Date range",
            _HISTORICAL_MODE_DATE_RANGE,
        )
        self.historical_start_date_edit = QDateEdit()
        self.historical_start_date_edit.setObjectName("setupHistoricalStartDate")
        self.historical_start_date_edit.setCalendarPopup(True)
        self.historical_start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.historical_end_date_edit = QDateEdit()
        self.historical_end_date_edit.setObjectName("setupHistoricalEndDate")
        self.historical_end_date_edit.setCalendarPopup(True)
        self.historical_end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._set_historical_date_range(
            QDate.currentDate().addMonths(-1),
            QDate.currentDate(),
        )
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
        form.addRow("Historical images", self.historical_loading_checkbox)
        form.addRow("Historical mode", self._build_historical_mode_row())
        form.addRow("Outside geometry", self.include_unmatched_checkbox)

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
        self.config_row.validationChanged.connect(self._sync_historical_loading_from_config)
        self.historical_loading_checkbox.toggled.connect(
            self._update_historical_controls_state
        )
        self.historical_mode_combo.currentIndexChanged.connect(
            self._update_historical_controls_state
        )
        self.historical_start_date_edit.dateChanged.connect(self._sync_historical_date_bounds)
        self.historical_end_date_edit.dateChanged.connect(self._sync_historical_date_bounds)
        self.ingest_button.clicked.connect(self._emit_ingest_requested)
        self.open_workspace_button.clicked.connect(self._emit_open_workspace_requested)
        self.apply_recent_button.clicked.connect(self._apply_current_recent_project)
        self.remove_recent_button.clicked.connect(self._emit_remove_current_recent_project)
        self.pause_button.clicked.connect(self._toggle_pause_requested)
        self.stop_button.clicked.connect(self._emit_stop_requested)
        self.set_recent_projects([])
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
            historical_loading_enabled=self.historical_loading_checkbox.isChecked(),
            historical_image_selection=self._selected_historical_image_selection(),
            include_unmatched_images=self.include_unmatched_checkbox.isChecked(),
        )

    def selected_workspace_folder(self) -> Path | None:
        """Return the selected workspace folder when it is valid."""
        return self.workspace_row.selected_path

    def set_recent_projects(self, recent_projects: list[RecentProjectEntry]) -> None:
        """Refresh the recent project picker from persisted user preferences."""
        self._recent_projects = list(recent_projects)
        self.recent_project_combo.blockSignals(True)
        self.recent_project_combo.clear()
        for index, project in enumerate(self._recent_projects):
            self.recent_project_combo.addItem(project.label, index)
            self.recent_project_combo.setItemData(
                index,
                _recent_project_tooltip(project),
                Qt.ItemDataRole.ToolTipRole,
            )
        self.recent_project_combo.blockSignals(False)

        has_projects = bool(self._recent_projects)
        if not has_projects:
            self.recent_project_combo.addItem("Không có")
        self.recent_project_combo.setEnabled(has_projects)
        self.apply_recent_button.setEnabled(has_projects)
        self.remove_recent_button.setEnabled(has_projects)

    def apply_recent_project(self, project: RecentProjectEntry) -> None:
        """Fill Setup path pickers from a recent project entry."""
        self.config_row.set_path(project.config_path)
        if project.imagery_folder:
            self.imagery_row.set_path(project.imagery_folder)
        self.workspace_row.set_path(project.workspace_folder)

    def apply_recent_parameters(self, parameters: SetupPreferences) -> None:
        """Fill Setup path pickers from the most recently used raw parameters."""
        if parameters.last_config_path:
            self.config_row.set_path(parameters.last_config_path)
        if parameters.last_imagery_folder:
            self.imagery_row.set_path(parameters.last_imagery_folder)
        if parameters.last_workspace_folder:
            self.workspace_row.set_path(parameters.last_workspace_folder)

    def _update_action_state(self, *_args: object) -> None:
        self.ingest_button.setEnabled(self.is_ready and not self._ingestion_running)
        self.historical_loading_checkbox.setEnabled(not self._ingestion_running)
        self.include_unmatched_checkbox.setEnabled(not self._ingestion_running)
        self._update_historical_controls_state()
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

    def _build_recent_project_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.recent_project_combo, 1)
        layout.addWidget(self.apply_recent_button)
        layout.addWidget(self.remove_recent_button)
        return row

    def _build_historical_mode_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.historical_mode_combo)
        layout.addWidget(QLabel("From"))
        layout.addWidget(self.historical_start_date_edit)
        layout.addWidget(QLabel("To"))
        layout.addWidget(self.historical_end_date_edit)
        layout.addStretch(1)
        return row

    def _current_recent_project(self) -> RecentProjectEntry | None:
        data = self.recent_project_combo.currentData()
        if not isinstance(data, int):
            return None
        if data < 0 or data >= len(self._recent_projects):
            return None
        return self._recent_projects[data]

    def _apply_current_recent_project(self) -> None:
        project = self._current_recent_project()
        if project is None:
            return
        self.apply_recent_project(project)

    def _emit_remove_current_recent_project(self) -> None:
        project = self._current_recent_project()
        if project is None:
            return
        self.recentProjectRemoveRequested.emit(project)

    def _emit_ingest_requested(self) -> None:
        selected_paths = self.selected_paths()
        if selected_paths is None:
            return

        workspace_service = WorkspaceService(selected_paths.workspace_folder)
        if workspace_service.has_app_owned_data():
            action = choose_existing_workspace_action(self, workspace_service.clear_plan())
            if action is ExistingWorkspaceAction.CANCEL:
                return
            if action is ExistingWorkspaceAction.CLEAR:
                selected_paths = replace(
                    selected_paths,
                    clear_existing_workspace=True,
                    clear_workspace_confirmed=True,
                )
            elif action is ExistingWorkspaceAction.OVERRIDE:
                selected_paths = replace(selected_paths, override_existing_workspace=True)

        self.ingestRequested.emit(selected_paths)

    def _sync_historical_loading_from_config(self, *_args: object) -> None:
        config_file = self.config_row.selected_path
        if config_file is None:
            self.historical_loading_checkbox.setChecked(False)
            self.historical_mode_combo.setCurrentIndex(0)
            self._update_historical_controls_state()
            return

        settings = read_historical_loading_settings(config_file)
        self.historical_loading_checkbox.setChecked(settings.enabled)
        if settings.image_selection.mode == HistoricalSelectionMode.DATE_RANGE:
            self.historical_mode_combo.setCurrentIndex(
                max(0, self.historical_mode_combo.findData(_HISTORICAL_MODE_DATE_RANGE))
            )
            if (
                settings.image_selection.start_date is not None
                and settings.image_selection.end_date is not None
            ):
                self._set_historical_date_range(
                    _qdate_from_date(settings.image_selection.start_date),
                    _qdate_from_date(settings.image_selection.end_date),
                )
        else:
            self.historical_mode_combo.setCurrentIndex(
                max(0, self.historical_mode_combo.findData(_HISTORICAL_MODE_LATEST_DATE))
            )
        self._update_historical_controls_state()

    def _update_historical_controls_state(self, *_args: object) -> None:
        enabled = self.historical_loading_checkbox.isChecked() and not self._ingestion_running
        date_range = self.historical_mode_combo.currentData() == _HISTORICAL_MODE_DATE_RANGE
        self.historical_mode_combo.setEnabled(enabled)
        self.historical_start_date_edit.setEnabled(enabled and date_range)
        self.historical_end_date_edit.setEnabled(enabled and date_range)

    def _sync_historical_date_bounds(self, *_args: object) -> None:
        start = self.historical_start_date_edit.date()
        end = self.historical_end_date_edit.date()
        if start <= end:
            return

        changed = self.sender()
        if changed is self.historical_start_date_edit:
            self.historical_end_date_edit.setDate(start)
            return
        self.historical_start_date_edit.setDate(end)

    def _set_historical_date_range(self, start: QDate, end: QDate) -> None:
        if start > end:
            start, end = end, start
        self.historical_start_date_edit.setDate(start)
        self.historical_end_date_edit.setDate(end)

    def _selected_historical_image_selection(self) -> HistoricalImageSelectionConfig:
        if self.historical_mode_combo.currentData() == _HISTORICAL_MODE_DATE_RANGE:
            return HistoricalImageSelectionConfig(
                mode=HistoricalSelectionMode.DATE_RANGE,
                start_date=_date_from_qdate(self.historical_start_date_edit.date()),
                end_date=_date_from_qdate(self.historical_end_date_edit.date()),
            )
        return HistoricalImageSelectionConfig(
            mode=HistoricalSelectionMode.LATEST_DATE,
        )

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


def _recent_project_tooltip(project: RecentProjectEntry) -> str:
    parts = [
        f"Config: {project.config_path}",
        f"Workspace: {project.workspace_folder}",
    ]
    if project.imagery_folder:
        parts.append(f"Ảnh: {project.imagery_folder}")
    return "\n".join(parts)


def _qdate_from_date(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _date_from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())
