"""Qt application shell."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from thucthengay.config import ConfigLoadResult, load_project_config
from thucthengay.editor.ingestion_worker import IngestionWorker
from thucthengay.editor.modes.export_mode import ExportMode
from thucthengay.editor.modes.review_edit_mode import ReviewEditMode
from thucthengay.editor.modes.setup_mode import SetupMode, SetupPaths
from thucthengay.jobs import IngestionJobResult, IngestionSummary, JobControl, JobState
from thucthengay.workspace import WorkspaceError, WorkspaceService


class AppShell(QMainWindow):
    """Top-level desktop window for the application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("3.ThucTheNgay")
        self.setup_mode = SetupMode()
        self.review_edit_mode = ReviewEditMode()
        self.export_mode = ExportMode()
        self._ingestion_thread: QThread | None = None
        self._ingestion_worker: IngestionWorker | None = None
        self._ingestion_control: JobControl | None = None

        self.mode_tabs = QTabWidget()
        self.mode_tabs.setObjectName("modeTabs")
        self.mode_tabs.addTab(self.setup_mode, "Setup")
        self.mode_tabs.addTab(self.review_edit_mode, "Review/Edit")
        self.mode_tabs.addTab(self.export_mode, "Export")
        self.setup_mode.ingestRequested.connect(self._run_ingestion)
        self.setup_mode.openWorkspaceRequested.connect(self._open_existing_workspace)
        self.setup_mode.pauseRequested.connect(self._pause_ingestion)
        self.setup_mode.resumeRequested.connect(self._resume_ingestion)
        self.setup_mode.stopRequested.connect(self._stop_ingestion)
        self.export_mode.jumpRequested.connect(self._jump_to_review_context)

        self.setCentralWidget(self.mode_tabs)
        self.resize(1280, 720)

    def _run_ingestion(self, setup_paths: SetupPaths) -> None:
        if self._ingestion_thread is not None:
            return

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

        self.review_edit_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
        )
        self.export_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
        )
        self.mode_tabs.setCurrentWidget(self.review_edit_mode)

    def _open_existing_workspace(self, workspace_folder: Path) -> None:
        workspace_service = WorkspaceService(workspace_folder)
        try:
            manifest = workspace_service.load_manifest()
        except WorkspaceError as error:
            self.setup_mode.show_workspace_open_error(str(error))
            return

        config_result = load_project_config(
            _manifest_config_path(manifest.config_path, workspace_service.paths.root)
        )
        if not config_result.ok:
            self.setup_mode.show_workspace_open_error(_config_issue_summary(config_result))
            return

        try:
            composition_count = len(workspace_service.list_compositions())
        except WorkspaceError as error:
            self.setup_mode.show_workspace_open_error(str(error))
            return

        self.review_edit_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
        )
        self.export_mode.load_workspace(
            workspace_service,
            targets=config_result.enabled_targets,
        )
        self.setup_mode.show_workspace_opened(workspace_service.paths.root, composition_count)
        self.mode_tabs.setCurrentWidget(self.review_edit_mode)

    def _jump_to_review_context(
        self,
        target_id: str,
        composition_id: str,
        layer_id: str,
    ) -> None:
        self.mode_tabs.setCurrentWidget(self.review_edit_mode)
        self.review_edit_mode._handle_issue_jump(target_id, composition_id, layer_id)


def run_gui(argv: list[str] | None = None) -> int:
    """Run the Qt app shell."""
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    shell = AppShell()
    shell.show()
    return app.exec()


def _manifest_config_path(config_path: str, workspace_root: Path) -> Path:
    path = Path(config_path).expanduser()
    if path.is_absolute():
        return path
    workspace_relative = workspace_root / path
    if workspace_relative.exists():
        return workspace_relative
    return path.resolve()


def _config_issue_summary(config_result: ConfigLoadResult) -> str:
    if not config_result.issues:
        return "Config trong manifest không hợp lệ."
    issue = config_result.issues[0]
    if issue.remediation:
        return f"{issue.message} {issue.remediation}"
    return issue.message
