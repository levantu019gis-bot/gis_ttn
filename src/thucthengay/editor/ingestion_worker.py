"""Qt worker adapter for background ingestion jobs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from thucthengay.config import (
    ConfigLoadResult,
    apply_historical_loading_override,
    load_project_config,
)
from thucthengay.jobs import (
    IngestionJobResult,
    JobControl,
    JobState,
    ProgressEvent,
    run_ingestion_job,
)
from thucthengay.models import Issue, IssueScope, IssueSeverity
from thucthengay.models.config import HistoricalImageSelectionConfig
from thucthengay.workspace import WorkspaceService


class IngestionWorker(QObject):
    """Run ingestion off the UI thread and emit plain Python job objects."""

    progress = Signal(object)
    finished = Signal(object, object, object)

    def __init__(
        self,
        *,
        job_id: str,
        config_file: Path,
        imagery_folder: Path,
        workspace_service: WorkspaceService,
        control: JobControl,
        historical_loading_enabled: bool,
        historical_image_selection: HistoricalImageSelectionConfig | None = None,
        clear_existing: bool = False,
        clear_confirmed: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.job_id = job_id
        self.config_file = config_file
        self.imagery_folder = imagery_folder
        self.workspace_service = workspace_service
        self.control = control
        self.historical_loading_enabled = historical_loading_enabled
        self.historical_image_selection = historical_image_selection
        self.clear_existing = clear_existing
        self.clear_confirmed = clear_confirmed

    @Slot()
    def run(self) -> None:
        """Worker entry point invoked by QThread."""
        config_result = ConfigLoadResult(config_path=self.config_file)
        try:
            config_result = load_project_config(self.config_file)
            config_result = apply_historical_loading_override(
                config_result,
                enabled=self.historical_loading_enabled,
                image_selection=self.historical_image_selection,
            )
            result = run_ingestion_job(
                job_id=self.job_id,
                config_result=config_result,
                imagery_folder=self.imagery_folder,
                workspace_service=self.workspace_service,
                control=self.control,
                publish=self.progress.emit,
                clear_existing=self.clear_existing,
                clear_confirmed=self.clear_confirmed,
            )
        except Exception as error:  # pragma: no cover - defensive UI boundary
            issue = Issue(
                issue_id="ingestion.unhandled_error",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.PROJECT,
                message=f"Lỗi không mong muốn khi lấy dữ liệu: {error}",
                remediation="Kiểm tra log kỹ thuật, dữ liệu đầu vào và chạy lại.",
            )
            result = IngestionJobResult(
                job_id=self.job_id,
                state=JobState.ERROR,
                issues=[issue],
                scanned_image_count=0,
                matched_image_count=0,
                targets_with_images_count=0,
                composition_ids=[],
            )
            self.progress.emit(
                ProgressEvent(
                    job_id=self.job_id,
                    stage="error",
                    state=JobState.ERROR,
                    message=issue.message,
                    issues=[issue],
                    warning_count=1,
                )
            )
        self.finished.emit(result, config_result, self.workspace_service)
