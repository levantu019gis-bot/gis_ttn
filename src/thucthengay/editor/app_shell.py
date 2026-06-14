"""Qt application shell."""

from __future__ import annotations

import sys
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from thucthengay.config import ConfigLoadResult, load_project_config
from thucthengay.download import SatelliteDownloadRequest, SatelliteDownloadResult
from thucthengay.editor.download_worker import DownloadRunner, DownloadWorker
from thucthengay.editor.ingestion_worker import IngestionWorker
from thucthengay.editor.modes.download_mode import DownloadMode
from thucthengay.editor.modes.export_mode import ExportMode
from thucthengay.editor.modes.review_edit_mode import ReviewEditMode
from thucthengay.editor.modes.setup_mode import SetupMode, SetupPaths
from thucthengay.editor.preferences import PreferencesService, RecentProjectEntry
from thucthengay.history import HistoryService
from thucthengay.jobs import (
    IngestionJobResult,
    IngestionSummary,
    JobControl,
    JobState,
    run_satellite_download_job,
)
from thucthengay.models import Issue, IssueScope
from thucthengay.utils.path_safety import is_absolute_path_text
from thucthengay.workspace import WorkspaceError, WorkspaceService


class AppShell(QMainWindow):
    """Top-level desktop window for the application."""

    def __init__(
        self,
        *,
        preferences_service: PreferencesService | None = None,
        download_runner: DownloadRunner = run_satellite_download_job,
    ) -> None:
        super().__init__()
        self.setWindowTitle("3.ThucTheNgay")
        self.preferences_service = preferences_service or PreferencesService()
        self._download_runner = download_runner
        self.setup_mode = SetupMode()
        self.review_edit_mode = ReviewEditMode(preferences_service=self.preferences_service)
        self.export_mode = ExportMode(preferences_service=self.preferences_service)
        self.download_mode = DownloadMode()
        from thucthengay.editor.modes.config_mode import ConfigMode

        self.config_mode = ConfigMode()
        self._ingestion_thread: QThread | None = None
        self._ingestion_worker: IngestionWorker | None = None
        self._ingestion_control: JobControl | None = None
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None
        self._download_control: JobControl | None = None
        self._active_setup_paths: SetupPaths | None = None

        self.mode_tabs = QTabWidget()
        self.mode_tabs.setObjectName("modeTabs")
        self.mode_tabs.addTab(self.setup_mode, "Setup")
        self.mode_tabs.addTab(self.review_edit_mode, "Review/Edit")
        self.mode_tabs.addTab(self.export_mode, "Export")
        self.mode_tabs.addTab(self.download_mode, "Download")
        self.mode_tabs.addTab(self.config_mode, "Config")
        self.setup_mode.ingestRequested.connect(self._run_ingestion)
        self.setup_mode.openWorkspaceRequested.connect(self._open_existing_workspace)
        self.setup_mode.pauseRequested.connect(self._pause_ingestion)
        self.setup_mode.resumeRequested.connect(self._resume_ingestion)
        self.setup_mode.stopRequested.connect(self._stop_ingestion)
        self.setup_mode.recentProjectRemoveRequested.connect(self._remove_recent_project)
        self.export_mode.jumpRequested.connect(self._jump_to_review_context)
        self.download_mode.downloadRequested.connect(self._run_download)
        self.download_mode.cancelRequested.connect(self._stop_download)
        self.config_mode.configSaved.connect(self._config_saved)

        self.setCentralWidget(self.mode_tabs)
        self.setup_mode.set_recent_projects(self.preferences_service.preferences.recent_projects)
        self._restore_setup_parameters()
        self._restore_download_parameters()
        for row in self.setup_mode.path_rows:
            row.validationChanged.connect(self._persist_setup_parameters)
        self._connect_download_parameter_persistence()
        saved_window_size = self.preferences_service.preferences.ui.window_size
        if saved_window_size and len(saved_window_size) == 2:
            self.resize(saved_window_size[0], saved_window_size[1])
        else:
            self.resize(1280, 720)

    def _run_ingestion(self, setup_paths: SetupPaths) -> None:
        if self._ingestion_thread is not None:
            return

        self._active_setup_paths = setup_paths
        workspace_service = WorkspaceService(setup_paths.workspace_folder)
        job_id = f"ingestion-{uuid4().hex}"
        control = JobControl()
        thread = QThread(self)
        worker = IngestionWorker(
            job_id=job_id,
            config_file=setup_paths.config_file,
            imagery_folder=setup_paths.imagery_input_folder,
            workspace_service=workspace_service,
            control=control,
            historical_loading_enabled=setup_paths.historical_loading_enabled,
            historical_image_selection=setup_paths.historical_image_selection,
            clear_existing=setup_paths.clear_existing_workspace,
            clear_confirmed=setup_paths.clear_workspace_confirmed,
            merge_existing=setup_paths.override_existing_workspace,
        )
        worker.moveToThread(thread)

        self._ingestion_thread = thread
        self._ingestion_worker = worker
        self._ingestion_control = control
        self.setup_mode.start_ingestion_progress()

        thread.started.connect(worker.run)
        worker.progress.connect(self.setup_mode.show_ingestion_progress)
        worker.finished.connect(self._finish_ingestion)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_ingestion_worker)
        thread.start()

    def _pause_ingestion(self) -> None:
        if self._ingestion_control is None:
            return
        self._ingestion_control.request_pause()
        self.setup_mode.mark_ingestion_paused()

    def _resume_ingestion(self) -> None:
        if self._ingestion_control is None:
            return
        self._ingestion_control.resume()
        self.setup_mode.mark_ingestion_resumed()

    def _stop_ingestion(self) -> None:
        if self._ingestion_control is None:
            return
        self._ingestion_control.request_cancel()
        self.setup_mode.mark_ingestion_stopping()

    def _clear_ingestion_worker(self) -> None:
        self._ingestion_thread = None
        self._ingestion_worker = None
        self._ingestion_control = None
        self._active_setup_paths = None

    def _run_download(self, request: SatelliteDownloadRequest) -> None:
        if self._download_thread is not None:
            return

        job_id = f"download-{uuid4().hex}"
        control = JobControl()
        thread = QThread(self)
        worker = DownloadWorker(
            job_id=job_id,
            request=request,
            control=control,
            runner=self._download_runner,
        )
        worker.moveToThread(thread)

        self._download_thread = thread
        self._download_worker = worker
        self._download_control = control
        self.download_mode.start_download_progress()

        thread.started.connect(worker.run)
        worker.progress.connect(self.download_mode.show_download_progress)
        worker.finished.connect(self._finish_download)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_download_worker)
        thread.start()

    def _stop_download(self) -> None:
        if self._download_control is None:
            return
        self._download_control.request_cancel()
        self.download_mode.mark_download_stopping()

    def _finish_download(self, result: SatelliteDownloadResult) -> None:
        self.download_mode.show_download_summary(result)

    def _clear_download_worker(self) -> None:
        self._download_thread = None
        self._download_worker = None
        self._download_control = None

    def _finish_ingestion(
        self,
        result: IngestionJobResult,
        config_result: ConfigLoadResult,
        workspace_service: WorkspaceService,
    ) -> None:
        summary = IngestionSummary.from_job_result(
            result,
            workspace_path=workspace_service.paths.root,
        )
        self.setup_mode.show_ingestion_summary(summary)
        if result.state not in {JobState.SUCCESS, JobState.WARNING}:
            return

        if self._active_setup_paths is not None:
            self._record_recent_project(
                config_path=self._active_setup_paths.config_file,
                imagery_folder=self._active_setup_paths.imagery_input_folder,
                workspace_folder=workspace_service.paths.root,
            )

        history_service = _history_service_from_config(config_result)
        self.review_edit_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
        )
        self.review_edit_mode.set_history_service(history_service)
        self.export_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
            template_issues=_export_template_issues(config_result),
            history_service=history_service,
        )
        self.mode_tabs.setCurrentWidget(self.review_edit_mode)

    def _open_existing_workspace(self, workspace_folder: Path) -> None:
        workspace_service = WorkspaceService(workspace_folder)
        try:
            manifest = workspace_service.load_manifest()
        except WorkspaceError as error:
            self.setup_mode.show_workspace_open_error(str(error))
            return

        config_path = _manifest_config_path(manifest.config_path, workspace_service.paths.root)
        config_result = load_project_config(config_path)
        if not config_result.ok:
            self.setup_mode.show_workspace_open_error(_config_issue_summary(config_result))
            return

        try:
            composition_count = len(workspace_service.list_compositions())
        except WorkspaceError as error:
            self.setup_mode.show_workspace_open_error(str(error))
            return

        history_service = _history_service_from_config(config_result)
        self.review_edit_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
        )
        self.review_edit_mode.set_history_service(history_service)
        self.export_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
            template_issues=_export_template_issues(config_result),
            history_service=history_service,
        )
        self.setup_mode.config_row.set_path(config_path)
        self.setup_mode.show_workspace_opened(workspace_service.paths.root, composition_count)
        self._record_recent_project(
            config_path=config_path,
            imagery_folder=self.setup_mode.imagery_row.selected_path,
            workspace_folder=workspace_service.paths.root,
        )
        self.mode_tabs.setCurrentWidget(self.review_edit_mode)

    def _jump_to_review_context(
        self,
        target_id: str,
        composition_id: str,
        layer_id: str,
    ) -> None:
        self.mode_tabs.setCurrentWidget(self.review_edit_mode)
        self.review_edit_mode._handle_issue_jump(target_id, composition_id, layer_id)

    def _record_recent_project(
        self,
        *,
        config_path: Path,
        workspace_folder: Path,
        imagery_folder: Path | None = None,
    ) -> None:
        self.preferences_service.record_recent_project(
            config_path=config_path,
            imagery_folder=imagery_folder,
            workspace_folder=workspace_folder,
        )
        self.setup_mode.set_recent_projects(self.preferences_service.preferences.recent_projects)

    def _config_saved(self, config_path: Path) -> None:
        self.setup_mode.config_row.set_path(config_path)
        config_result = load_project_config(config_path)
        if not config_result.ok or config_result.config is None:
            self.config_mode.downstream_label.setText(
                "Đã lưu config nhưng chưa reload downstream vì config còn lỗi. "
                f"{_config_issue_summary(config_result)}"
            )
            return
        history_service = _history_service_from_config(config_result)
        self.review_edit_mode.set_history_service(history_service)
        self.export_mode.set_history_service(history_service)
        self.review_edit_mode.refresh_config_targets(config_result.enabled_targets)
        self.export_mode.refresh_config_targets(
            config_result.enabled_targets,
            template_issues=_export_template_issues(config_result),
        )
        self.config_mode.downstream_label.setText(
            "Đã lưu config và reload target list cho Review/Edit, Export. "
            "Nếu geometry/enabled/defaults/patterns đổi, hãy chạy lại ingestion/"
            "validation/preflight khi cần."
        )

    def _remove_recent_project(self, project: RecentProjectEntry) -> None:
        self.preferences_service.remove_recent_project(project.workspace_folder)
        self.setup_mode.set_recent_projects(self.preferences_service.preferences.recent_projects)

    def _restore_setup_parameters(self) -> None:
        self.setup_mode.apply_recent_parameters(self.preferences_service.preferences.setup)

    def _persist_setup_parameters(self, *_args: object) -> None:
        self.preferences_service.update_setup_parameters(
            config_path=self.setup_mode.config_row.path_field.full_text,
            imagery_folder=self.setup_mode.imagery_row.path_field.full_text,
            workspace_folder=self.setup_mode.workspace_row.path_field.full_text,
        )

    def _restore_download_parameters(self) -> None:
        self.download_mode.apply_recent_parameters(self.preferences_service.preferences.download)

    def _connect_download_parameter_persistence(self) -> None:
        self.download_mode.geojson_files.pathsChanged.connect(self._persist_download_parameters)
        self.download_mode.image_folders.pathsChanged.connect(self._persist_download_parameters)
        self.download_mode.output_row.validationChanged.connect(self._persist_download_parameters)
        self.download_mode.overwrite_checkbox.toggled.connect(self._persist_download_parameters)
        self.download_mode.dry_run_checkbox.toggled.connect(self._persist_download_parameters)
        self.download_mode.include_boundary_checkbox.toggled.connect(
            self._persist_download_parameters
        )
        self.download_mode.preserve_tree_checkbox.toggled.connect(
            self._persist_download_parameters
        )
        self.download_mode.write_manifest_checkbox.toggled.connect(
            self._persist_download_parameters
        )
        self.download_mode.cloud_filter_checkbox.toggled.connect(self._persist_download_parameters)
        self.download_mode.cloud_filter_spin.valueChanged.connect(self._persist_download_parameters)
        self.download_mode.scan_workers_spin.valueChanged.connect(self._persist_download_parameters)

    def _persist_download_parameters(self, *_args: object) -> None:
        self.preferences_service.update_download_parameters(
            **self.download_mode.preference_payload()
        )

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self.preferences_service.update_window_size(self.width(), self.height())
        super().closeEvent(event)


def run_gui(argv: list[str] | None = None) -> int:
    """Run the Qt app shell."""
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    shell = AppShell()
    shell.show()
    return app.exec()


def _manifest_config_path(config_path: str, workspace_root: Path) -> Path:
    path = Path(config_path).expanduser()
    if is_absolute_path_text(config_path):
        if path.exists():
            return path
        fallback = _fallback_manifest_config_path(config_path, workspace_root)
        if fallback is not None:
            return fallback
        return path
    workspace_relative = workspace_root / path
    if workspace_relative.exists():
        return workspace_relative
    return path.resolve()


def _history_service_from_config(config_result: ConfigLoadResult) -> HistoryService:
    config = config_result.config
    if (
        config is None
        or not config.historical_registry.enabled
        or config_result.historical_database_path is None
    ):
        return HistoryService.disabled()
    return HistoryService(config_result.historical_database_path)


def _export_template_issues(config_result: ConfigLoadResult) -> list[Issue]:
    return [issue for issue in config_result.issues if issue.scope == IssueScope.TEMPLATE]


def _fallback_manifest_config_path(config_path: str, workspace_root: Path) -> Path | None:
    config_name = (
        PureWindowsPath(config_path).name
        if "\\" in config_path
        else Path(config_path).name
    )
    if not config_name:
        return None
    candidates = (
        workspace_root / config_name,
        workspace_root / "data" / config_name,
        workspace_root.parent / config_name,
        workspace_root.parent / "data" / config_name,
        workspace_root.parent.parent / config_name,
        workspace_root.parent.parent / "data" / config_name,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _config_issue_summary(config_result: ConfigLoadResult) -> str:
    if not config_result.issues:
        return "Config trong manifest không hợp lệ."
    issue = config_result.issues[0]
    if issue.remediation:
        return f"{issue.message} {issue.remediation}"
    return issue.message
