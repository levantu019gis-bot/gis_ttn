"""Qt worker adapter for background preview render jobs."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from thucthengay.jobs import PreviewRenderRequest, run_preview_render_job
from thucthengay.jobs.render_job import RenderFunction


class RenderWorker(QObject):
    """Run a preview render off the UI thread and emit the result."""

    finished = Signal(object)

    def __init__(
        self,
        request: PreviewRenderRequest,
        *,
        render: RenderFunction | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._request = request
        self._render = render
        self._cancelled = False

    def cancel(self) -> None:
        """Request cooperative cancellation for the running render."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    @Slot()
    def run(self) -> None:
        """Worker entry point invoked by QThread."""
        if self._render is None:
            result = run_preview_render_job(self._request, is_cancelled=self.is_cancelled)
        else:
            result = run_preview_render_job(
                self._request,
                render=self._render,
                is_cancelled=self.is_cancelled,
            )
        self.finished.emit(result)
