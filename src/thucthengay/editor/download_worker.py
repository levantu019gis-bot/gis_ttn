"""Qt worker adapter for satellite download jobs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from thucthengay.download import (
    DownloadRunStatus,
    SatelliteDownloadRequest,
    SatelliteDownloadResult,
)
from thucthengay.jobs import JobControl, JobState, ProgressEvent, run_satellite_download_job
from thucthengay.models import Issue, IssueScope, IssueSeverity

DownloadRunner = Callable[..., SatelliteDownloadResult]


class DownloadWorker(QObject):
    """Run a satellite download job off the UI thread."""

    progress = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        *,
        job_id: str,
        request: SatelliteDownloadRequest,
        control: JobControl,
        runner: DownloadRunner = run_satellite_download_job,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.job_id = job_id
        self.request = request
        self.control = control
        self.runner = runner

    @Slot()
    def run(self) -> None:
        """Worker entry point invoked by QThread."""
        try:
            result = self.runner(
                job_id=self.job_id,
                request=self.request,
                control=self.control,
                publish=self.progress.emit,
            )
        except Exception as error:  # pragma: no cover - defensive UI boundary
            issue = Issue(
                issue_id="satellite_download.unhandled_error",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.PROJECT,
                message=f"Loi khong mong muon khi tai anh ve tinh: {error}",
                remediation=(
                    "Kiem tra log ky thuat, duong dan input/output, quyen truy cap "
                    "va chay lai."
                ),
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
            result = SatelliteDownloadResult(
                status=DownloadRunStatus.ERROR,
                output_dir=Path(self.request.output_dir),
                issues=(issue,),
                message=issue.message,
            )
        self.finished.emit(result)
