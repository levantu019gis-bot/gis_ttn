"""Qt worker adapter for full export jobs."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from thucthengay.export.pipeline import FullExportResult, run_full_export
from thucthengay.models import Issue, TargetConfig
from thucthengay.workspace import WorkspaceService

ExportRunner = Callable[..., FullExportResult]


class ExportWorker(QObject):
    """Run final render and export off the UI thread."""

    finished = Signal(object)

    def __init__(
        self,
        workspace_service: WorkspaceService,
        targets: list[TargetConfig],
        *,
        output_stem: str,
        template_issues: list[Issue] | None = None,
        runner: ExportRunner = run_full_export,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_service = workspace_service
        self._targets = targets
        self._output_stem = output_stem
        self._template_issues = list(template_issues or [])
        self._runner = runner
        self._cancelled = False

    def cancel(self) -> None:
        """Request cooperative cancellation for the running export."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    @Slot()
    def run(self) -> None:
        """Worker entry point invoked by QThread."""
        result = self._runner(
            self._workspace_service,
            self._targets,
            output_stem=self._output_stem,
            is_cancelled=self.is_cancelled,
            template_issues=self._template_issues,
        )
        self.finished.emit(result)
