"""Qt worker for progressive tile preview frames."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from thucthengay.jobs import JobState, PreviewRenderJobResult, PreviewRenderRequest
from thucthengay.models import Issue, IssueScope, IssueSeverity
from thucthengay.render import (
    MapRenderCache,
    TileCache,
    TilePreviewSettings,
    TilePreviewState,
    TileScheduler,
    iter_tile_preview_frames,
    render_map_with_cache,
)
from thucthengay.render.raster import RenderError


class TilePreviewWorker(QObject):
    """Run tile preview off the UI thread and emit progressive frames."""

    frameReady = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        request: PreviewRenderRequest,
        *,
        tile_cache: TileCache,
        tile_scheduler: TileScheduler,
        render_cache: MapRenderCache,
        previous_state: TilePreviewState,
        settings: TilePreviewSettings,
        fallback_to_full_render: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._request = request
        self._tile_cache = tile_cache
        self._tile_scheduler = tile_scheduler
        self._render_cache = render_cache
        self._previous_state = previous_state
        self._settings = settings
        self._fallback_to_full_render = fallback_to_full_render
        self._cancelled = False

    def cancel(self) -> None:
        """Request cooperative cancellation for the running tile preview."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    @Slot()
    def run(self) -> None:
        """Worker entry point invoked by QThread."""
        last_result: PreviewRenderJobResult | None = None
        try:
            for frame in iter_tile_preview_frames(
                self._request.spec,
                tile_cache=self._tile_cache,
                tile_scheduler=self._tile_scheduler,
                render_cache=self._render_cache,
                previous_state=self._previous_state,
                settings=self._settings,
                is_cancelled=self.is_cancelled,
                diagnostics=self._request.diagnostics,
            ):
                if self.is_cancelled():
                    break
                result = self._result(
                    state=JobState.SUCCESS,
                    message=frame.message,
                    canvas=frame.result.canvas,
                    issues=frame.result.issues,
                    tile_state=frame.state,
                )
                last_result = result
                self.frameReady.emit(result)
            if self.is_cancelled():
                last_result = self._error_result([_cancelled_issue(self._request)])
            if last_result is None:
                last_result = self._error_result([_empty_issue(self._request)])
        except Exception as exc:  # noqa: BLE001 - tile preview has a safe fallback path.
            if not self._fallback_to_full_render:
                if isinstance(exc, RenderError):
                    last_result = self._error_result(list(exc.issues))
                else:
                    last_result = self._error_result([_unexpected_issue(self._request, exc)])
            else:
                last_result = self._fallback_result()
        self.finished.emit(last_result)

    def _fallback_result(self) -> PreviewRenderJobResult:
        try:
            render_result = render_map_with_cache(
                self._request.spec,
                render_cache=self._render_cache,
                is_cancelled=self.is_cancelled,
                diagnostics=self._request.diagnostics,
            )
        except RenderError as exc:
            return self._error_result(list(exc.issues))
        except Exception as exc:  # noqa: BLE001 - convert worker failure into UI-safe payload.
            return self._error_result([_unexpected_issue(self._request, exc)])
        return self._result(
            state=JobState.SUCCESS,
            message="Tile preview fallback sang render day du.",
            canvas=render_result.canvas,
            issues=render_result.issues,
            tile_state=self._previous_state,
        )

    def _result(
        self,
        *,
        state: JobState,
        message: str,
        canvas,
        issues: tuple[Issue, ...],
        tile_state: TilePreviewState,
    ) -> PreviewRenderJobResult:
        result = PreviewRenderJobResult(
            job_id=self._request.job_id,
            composition_id=self._request.composition_id,
            revision=self._request.revision,
            quality=self._request.quality,
            state=state,
            output_width=self._request.spec.output_width,
            output_height=self._request.spec.output_height,
            message=message,
            issues=tuple(issues),
            canvas=canvas,
            tile_preview_state=tile_state,
        )
        return result

    def _error_result(self, issues: list[Issue]) -> PreviewRenderJobResult:
        message = issues[0].message if issues else "Khong tao duoc tile preview."
        return self._result(
            state=JobState.ERROR,
            message=message,
            canvas=None,
            issues=tuple(issues),
            tile_state=self._previous_state,
        )


def _cancelled_issue(request: PreviewRenderRequest) -> Issue:
    return Issue(
        issue_id="preview.tile.cancelled",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        composition_id=request.composition_id,
        message="Tile preview da bi huy vi co yeu cau moi hon.",
        remediation="Cho preview moi nhat hoan tat hoac tiep tuc chinh sua de render lai.",
    )


def _empty_issue(request: PreviewRenderRequest) -> Issue:
    return Issue(
        issue_id="preview.tile.empty",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        composition_id=request.composition_id,
        message="Tile preview khong tao ra frame nao.",
        remediation="Fallback ve render preview day du hoac kiem tra cau hinh raster.",
    )


def _unexpected_issue(request: PreviewRenderRequest, error: Exception) -> Issue:
    return Issue(
        issue_id="preview.tile.failed",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        composition_id=request.composition_id,
        message=f"Khong tao duoc tile preview: {error}",
        remediation="Kiem tra du lieu raster/cau hinh render roi thu cap nhat preview lai.",
    )
