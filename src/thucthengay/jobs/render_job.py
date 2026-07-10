"""Headless preview render job contracts and stale-result control."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4

import numpy as np

from thucthengay.jobs.progress import JobState, ProgressEvent
from thucthengay.models import Issue, IssueScope, IssueSeverity
from thucthengay.render import render_map
from thucthengay.render.diagnostics import RenderDiagnostics
from thucthengay.render.raster import RasterRenderResult, RenderError
from thucthengay.render.spec import RenderSpec


class PreviewRenderQuality(StrEnum):
    """Preview render stages used by the Review/Edit UI."""

    INTERACTIVE_LOW_RES = "interactive_low_res"
    SETTLED_HIGH_RES = "settled_high_res"


@dataclass(frozen=True)
class PreviewRenderRequest:
    """A single preview render request bound to a composition revision."""

    job_id: str
    composition_id: str
    revision: int
    quality: PreviewRenderQuality
    spec: RenderSpec
    diagnostics: RenderDiagnostics | None = field(default=None, compare=False)


@dataclass(frozen=True)
class PreviewRenderPlan:
    """Two-stage preview plan: immediate interactive render plus debounced settled render."""

    interactive: PreviewRenderRequest
    settled: PreviewRenderRequest
    settled_delay_ms: int


@dataclass(frozen=True)
class PreviewRenderJobResult:
    """Terminal preview job payload for UI adapters."""

    job_id: str
    composition_id: str
    revision: int
    quality: PreviewRenderQuality
    state: JobState
    output_width: int
    output_height: int
    message: str
    issues: tuple[Issue, ...] = ()
    canvas: np.ndarray | None = field(default=None, compare=False)


RenderFunction = Callable[..., RasterRenderResult]
ProgressPublisher = Callable[[ProgressEvent], None]
CancelCallback = Callable[[], bool]


class PreviewRenderController:
    """Main-thread preview state model that creates two-stage requests and filters stale results."""

    def __init__(
        self,
        *,
        debounce_ms: int,
        interactive_max_width: int = 480,
        settled_max_width: int = 960,
    ) -> None:
        self.debounce_ms = max(0, debounce_ms)
        self.interactive_max_width = max(1, interactive_max_width)
        self.settled_max_width = max(1, settled_max_width)
        self._revision = 0
        self._active_composition_id: str | None = None
        self._active_job_ids: set[str] = set()
        self._accepted_quality_rank = -1

    @property
    def revision(self) -> int:
        return self._revision

    def request_preview(self, spec: RenderSpec) -> PreviewRenderPlan:
        """Create a new preview revision with immediate and debounced render requests."""
        self._revision += 1
        self._active_composition_id = spec.composition_id

        interactive = PreviewRenderRequest(
            job_id=_job_id(
                spec.composition_id,
                self._revision,
                PreviewRenderQuality.INTERACTIVE_LOW_RES,
            ),
            composition_id=spec.composition_id,
            revision=self._revision,
            quality=PreviewRenderQuality.INTERACTIVE_LOW_RES,
            spec=_resize_spec(spec, max_width=self.interactive_max_width),
        )
        settled = PreviewRenderRequest(
            job_id=_job_id(
                spec.composition_id,
                self._revision,
                PreviewRenderQuality.SETTLED_HIGH_RES,
            ),
            composition_id=spec.composition_id,
            revision=self._revision,
            quality=PreviewRenderQuality.SETTLED_HIGH_RES,
            spec=_resize_spec(spec, max_width=self.settled_max_width),
        )
        self._active_job_ids = {interactive.job_id, settled.job_id}
        self._accepted_quality_rank = -1
        return PreviewRenderPlan(
            interactive=interactive,
            settled=settled,
            settled_delay_ms=self.debounce_ms,
        )

    def accepts_result(self, result: PreviewRenderJobResult) -> bool:
        """Return true only for results belonging to the latest preview revision."""
        matches_active = (
            result.revision == self._revision
            and result.composition_id == self._active_composition_id
            and result.job_id in self._active_job_ids
        )
        if not matches_active:
            return False
        quality_rank = _quality_rank(result.quality)
        if result.state in {JobState.SUCCESS, JobState.WARNING}:
            if quality_rank < self._accepted_quality_rank:
                return False
            self._accepted_quality_rank = quality_rank
        return True

    def is_stale(self, request: PreviewRenderRequest) -> bool:
        """Return true when a worker should stop because the request is obsolete."""
        return (
            request.revision != self._revision
            or request.composition_id != self._active_composition_id
            or request.job_id not in self._active_job_ids
        )


def run_preview_render_job(
    request: PreviewRenderRequest,
    *,
    publish: ProgressPublisher | None = None,
    render: RenderFunction = render_map,
    is_cancelled: CancelCallback | None = None,
) -> PreviewRenderJobResult:
    """Run one preview render request and return a terminal payload."""
    _publish(
        request,
        publish,
        state=JobState.RUNNING,
        message=_running_message(request.quality),
    )
    if is_cancelled is not None and is_cancelled():
        return _error_result(request, [_cancelled_issue(request)], publish=publish)

    try:
        render_kwargs = {"is_cancelled": is_cancelled}
        if request.diagnostics is not None:
            render_kwargs["diagnostics"] = request.diagnostics
        render_result = render(request.spec, **render_kwargs)
    except RenderError as exc:
        return _error_result(request, exc.issues, publish=publish)
    except Exception as exc:  # noqa: BLE001 - convert worker failures into UI-safe payloads.
        return _error_result(request, [_unexpected_issue(request, exc)], publish=publish)

    if is_cancelled is not None and is_cancelled():
        return _error_result(request, [_cancelled_issue(request)], publish=publish)

    result = PreviewRenderJobResult(
        job_id=request.job_id,
        composition_id=request.composition_id,
        revision=request.revision,
        quality=request.quality,
        state=JobState.SUCCESS,
        output_width=request.spec.output_width,
        output_height=request.spec.output_height,
        message=_success_message(request.quality),
        issues=tuple(render_result.issues),
        canvas=render_result.canvas,
    )
    _publish(
        request,
        publish,
        state=JobState.SUCCESS,
        message=result.message,
        issues=result.issues,
    )
    return result


def _resize_spec(spec: RenderSpec, *, max_width: int) -> RenderSpec:
    if spec.output_width <= max_width:
        return spec
    ratio = max_width / spec.output_width
    height = max(1, int(round(spec.output_height * ratio)))
    return spec.model_copy(update={"output_width": max_width, "output_height": height})


def _job_id(
    composition_id: str,
    revision: int,
    quality: PreviewRenderQuality,
) -> str:
    return f"preview:{composition_id}:{revision}:{quality.value}:{uuid4().hex}"


def _publish(
    request: PreviewRenderRequest,
    publish: ProgressPublisher | None,
    *,
    state: JobState,
    message: str,
    issues: tuple[Issue, ...] | list[Issue] = (),
) -> None:
    if publish is None:
        return
    publish(
        ProgressEvent(
            job_id=request.job_id,
            stage=f"preview.{request.quality.value}",
            state=state,
            current=1 if state != JobState.RUNNING else 0,
            total=1,
            message=message,
            issues=list(issues),
        )
    )


def _error_result(
    request: PreviewRenderRequest,
    issues: list[Issue],
    *,
    publish: ProgressPublisher | None,
) -> PreviewRenderJobResult:
    message = _failure_message(issues)
    result = PreviewRenderJobResult(
        job_id=request.job_id,
        composition_id=request.composition_id,
        revision=request.revision,
        quality=request.quality,
        state=JobState.ERROR,
        output_width=request.spec.output_width,
        output_height=request.spec.output_height,
        message=message,
        issues=tuple(issues),
        canvas=None,
    )
    _publish(request, publish, state=JobState.ERROR, message=message, issues=result.issues)
    return result


def _failure_message(issues: list[Issue]) -> str:
    if not issues:
        return "Khong tao duoc preview. Tiep tuc chinh sua roi render lai."
    first = issues[0]
    remediation = first.remediation.strip()
    if remediation:
        return f"{first.message.strip()} {remediation}"
    return first.message.strip() or "Khong tao duoc preview. Tiep tuc chinh sua roi render lai."


def _running_message(quality: PreviewRenderQuality) -> str:
    if quality == PreviewRenderQuality.INTERACTIVE_LOW_RES:
        return "Dang tao preview nhanh do phan giai thap."
    return "Dang tao preview sac net sau debounce."


def _success_message(quality: PreviewRenderQuality) -> str:
    if quality == PreviewRenderQuality.INTERACTIVE_LOW_RES:
        return "Preview nhanh da cap nhat."
    return "Preview sac net da cap nhat."


def _quality_rank(quality: PreviewRenderQuality) -> int:
    if quality == PreviewRenderQuality.SETTLED_HIGH_RES:
        return 1
    return 0


def _cancelled_issue(request: PreviewRenderRequest) -> Issue:
    return Issue(
        issue_id="preview.render.cancelled",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        composition_id=request.composition_id,
        message="Preview da bi huy vi co yeu cau moi hon.",
        remediation="Cho preview moi nhat hoan tat hoac tiep tuc chinh sua de render lai.",
    )


def _unexpected_issue(request: PreviewRenderRequest, error: Exception) -> Issue:
    return Issue(
        issue_id="preview.render.failed",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        composition_id=request.composition_id,
        message=f"Khong tao duoc preview: {error}",
        remediation="Kiem tra du lieu raster/cau hinh render roi thu cap nhat preview lai.",
    )
