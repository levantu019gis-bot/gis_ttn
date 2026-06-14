"""End-to-end headless export orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from thucthengay.export.final_render import ensure_final_renders_for_export
from thucthengay.export.history_sync import ExportHistorySyncResult, sync_export_history
from thucthengay.export.log_writer import write_export_summary_and_trace_log
from thucthengay.export.pptx_exporter import export_combined_pptx
from thucthengay.export.preflight import build_export_preflight_plan
from thucthengay.export.progress import ExportProgress, ExportProgressCallback
from thucthengay.export.txt_exporter import export_txt_report
from thucthengay.history import HistoryService
from thucthengay.models import (
    ExportFinalRenderResult,
    ExportLogWriteResult,
    ExportPptxResult,
    ExportPreflightPlan,
    ExportPreflightState,
    ExportPreflightSummary,
    ExportTxtResult,
    Issue,
    IssueScope,
    IssueSeverity,
    TargetConfig,
)
from thucthengay.render.final import FinalRenderFunction
from thucthengay.render.raster import CancelCallback
from thucthengay.utils.path_safety import safe_filename_component
from thucthengay.workspace import WorkspaceService

AUTO_RENDER_PREP_ISSUE_IDS = {
    "export.final_render_missing",
    "export.final_render_log_missing",
    "export.final_render_stale",
}
DEFAULT_EXPORT_STEM = "report"


@dataclass(frozen=True)
class FullExportResult:
    """Combined result for final render, PPTX, TXT, and trace-log export."""

    initial_preflight_plan: ExportPreflightPlan
    final_render_result: ExportFinalRenderResult
    history_sync_result: ExportHistorySyncResult
    preflight_plan: ExportPreflightPlan
    pptx_result: ExportPptxResult
    txt_result: ExportTxtResult
    log_result: ExportLogWriteResult | None = None

    @property
    def ok(self) -> bool:
        return self.log_result is not None and self.log_result.ok

    @property
    def issues(self) -> list[Issue]:
        issues: list[Issue] = []
        for source in (
            self.initial_preflight_plan.issues,
            self.final_render_result.issues,
            self.history_sync_result.issues,
            self.preflight_plan.issues,
            self.pptx_result.issues,
            self.txt_result.issues,
            self.log_result.issues if self.log_result is not None else (),
        ):
            for issue in source:
                if issue not in issues:
                    issues.append(issue)
        return issues


def run_full_export(
    workspace_service: WorkspaceService,
    targets: Iterable[TargetConfig],
    *,
    output_stem: str = DEFAULT_EXPORT_STEM,
    render: FinalRenderFunction | None = None,
    is_cancelled: CancelCallback | None = None,
    template_issues: Iterable[Issue] = (),
    history_service: HistoryService | None = None,
    on_progress: ExportProgressCallback | None = None,
) -> FullExportResult:
    """Render missing final images, export PPTX/TXT, and write a trace log."""
    target_list = list(targets)
    template_issue_list = _export_template_issues(template_issues)
    _publish_progress(
        on_progress,
        stage="preflight",
        completed=0,
        message="Đang chạy preflight export ban đầu.",
    )
    initial_plan = build_export_preflight_plan(
        workspace_service,
        target_list,
        template_issues=template_issue_list,
    )
    _publish_progress(
        on_progress,
        stage="preflight",
        completed=5,
        message=(
            "Đã preflight export ban đầu: "
            f"{len(initial_plan.rows)} mục tiêu trong danh sách export."
        ),
        current=len(initial_plan.rows),
        item_total=len(initial_plan.rows),
    )
    final_render_result = ensure_final_renders_for_export(
        workspace_service,
        target_list,
        render=render,
        is_cancelled=is_cancelled,
        on_progress=_final_render_progress_callback(on_progress),
    )
    _publish_progress(
        on_progress,
        stage="preflight",
        completed=50,
        message="Đang chạy preflight lại sau khi render final image.",
    )
    final_plan = _attach_final_render_issues(
        build_export_preflight_plan(
            workspace_service,
            target_list,
            template_issues=template_issue_list,
        ),
        final_render_result,
    )
    _publish_progress(
        on_progress,
        stage="preflight",
        completed=55,
        message=(
            "Đã preflight lại sau render: "
            f"{len(_exportable_composition_ids(final_plan))}/{len(final_plan.rows)} "
            "mục tiêu có thể export."
        ),
        current=len(_exportable_composition_ids(final_plan)),
        item_total=len(final_plan.rows),
    )
    history_sync_result = sync_export_history(
        workspace_service,
        target_list,
        final_plan,
        history_service=history_service,
        on_progress=_history_sync_progress_callback(on_progress),
    )
    if not history_sync_result.enabled:
        _publish_progress(
            on_progress,
            stage="history",
            completed=80,
            message="Bỏ qua ghi DB history vì SQLite history chưa được bật.",
        )
    elif not _exportable_composition_ids(final_plan):
        _publish_progress(
            on_progress,
            stage="history",
            completed=80,
            message="Không có mục tiêu export được để ghi DB history.",
        )
    final_plan = _attach_history_sync_issues(final_plan, history_sync_result)
    pptx_path, txt_path, log_path = _output_paths(workspace_service, output_stem)
    exportable_composition_ids = _exportable_composition_ids(final_plan)

    if not exportable_composition_ids:
        _publish_progress(
            on_progress,
            stage="pptx",
            completed=90,
            message="Không có mục tiêu export được; bỏ qua tạo file PPTX.",
        )
        pptx_result = ExportPptxResult()
        _publish_progress(
            on_progress,
            stage="txt",
            completed=97,
            message="Không có mục tiêu export được; bỏ qua tạo file TXT.",
        )
        txt_result = ExportTxtResult()
    else:
        _publish_progress(
            on_progress,
            stage="pptx",
            completed=80,
            message=(
                "Đang tạo file PPTX "
                f"({len(exportable_composition_ids)} mục tiêu export được)."
            ),
            current=0,
            item_total=len(exportable_composition_ids),
        )
        pptx_result = export_combined_pptx(
            workspace_service,
            target_list,
            output_path=pptx_path,
            template_issues=template_issue_list,
            composition_ids=exportable_composition_ids,
        )
        _publish_progress(
            on_progress,
            stage="pptx",
            completed=90,
            message=f"Đã tạo file PPTX: {pptx_result.summary.slide_count} slide.",
            current=pptx_result.summary.slide_count,
            item_total=len(exportable_composition_ids),
        )
        _publish_progress(
            on_progress,
            stage="txt",
            completed=90,
            message=(
                "Đang tạo file TXT "
                f"({len(exportable_composition_ids)} mục tiêu export được)."
            ),
            current=0,
            item_total=len(exportable_composition_ids),
        )
        txt_result = export_txt_report(
            workspace_service,
            target_list,
            output_path=txt_path,
            composition_ids=exportable_composition_ids,
        )
        _publish_progress(
            on_progress,
            stage="txt",
            completed=97,
            message=f"Đã tạo file TXT: {txt_result.summary.line_count} dòng.",
            current=txt_result.summary.line_count,
            item_total=len(exportable_composition_ids),
        )

    _publish_progress(
        on_progress,
        stage="log",
        completed=97,
        message="Đang ghi export log.",
    )
    log_result = write_export_summary_and_trace_log(
        workspace_service,
        preflight_plan=final_plan,
        pptx_result=pptx_result,
        txt_result=txt_result,
        output_path=log_path,
    )
    _publish_progress(
        on_progress,
        stage="done",
        completed=100,
        message="Xong quá trình export.",
    )
    return FullExportResult(
        initial_preflight_plan=initial_plan,
        final_render_result=final_render_result,
        history_sync_result=history_sync_result,
        preflight_plan=final_plan,
        pptx_result=pptx_result,
        txt_result=txt_result,
        log_result=log_result,
    )


def preflight_allows_auto_export(plan: ExportPreflightPlan) -> bool:
    """Return true when remaining preflight errors can be fixed by final rendering."""
    errors = [
        issue
        for issue in plan.issues
        if issue.severity == IssueSeverity.ERROR and issue.blocking
    ]
    if not errors:
        return True
    return all(issue.issue_id in AUTO_RENDER_PREP_ISSUE_IDS for issue in errors)


def _export_template_issues(issues: Iterable[Issue]) -> list[Issue]:
    return [issue for issue in issues if issue.scope == IssueScope.TEMPLATE]


def _exportable_composition_ids(plan: ExportPreflightPlan) -> set[str]:
    return {row.composition_id for row in plan.rows if not row.blocking}


def _attach_final_render_issues(
    plan: ExportPreflightPlan,
    final_render_result: ExportFinalRenderResult,
) -> ExportPreflightPlan:
    render_issues_by_composition: dict[str, list[Issue]] = {}
    for row in final_render_result.rows:
        if row.issues:
            render_issues_by_composition[row.composition_id] = list(row.issues)
    if not render_issues_by_composition:
        return plan

    rows = []
    all_issues = list(plan.issues)
    for row in plan.rows:
        row_issues = list(row.issues)
        for issue in render_issues_by_composition.get(row.composition_id, ()):
            if issue not in row_issues:
                row_issues.append(issue)
            if issue not in all_issues:
                all_issues.append(issue)
        rows.append(row.model_copy(update={"issues": row_issues}))
    return plan.model_copy(
        update={
            "rows": rows,
            "issues": all_issues,
            "summary": _summary(rows, all_issues),
        }
    )


def _final_render_progress_callback(
    on_progress: ExportProgressCallback | None,
):
    if on_progress is None:
        return None

    def _callback(composition, index: int, total: int, finished: bool) -> None:  # noqa: ANN001
        completed = _scaled_progress(
            start=5,
            end=50,
            current=index if finished else index - 1,
            total=total,
        )
        done_count = index if finished else index - 1
        verb = "Đã xử lý" if finished else "Đang render final image"
        _publish_progress(
            on_progress,
            stage="render",
            completed=completed,
            message=(
                f"{verb} (mục tiêu {composition.target_id}, "
                f"đã xử lý {done_count}/{total} mục tiêu)."
            ),
            current=done_count,
            item_total=total,
            target_id=composition.target_id,
            composition_id=composition.composition_id,
        )

    return _callback


def _history_sync_progress_callback(
    on_progress: ExportProgressCallback | None,
):
    if on_progress is None:
        return None

    def _callback(
        target_id: str,
        composition_id: str,
        index: int,
        total: int,
        finished: bool,
    ) -> None:
        completed = _scaled_progress(
            start=55,
            end=80,
            current=index if finished else index - 1,
            total=total,
        )
        done_count = index if finished else index - 1
        verb = "Đã ghi DB history" if finished else "Đang ghi DB history"
        target_text = target_id or composition_id
        _publish_progress(
            on_progress,
            stage="history",
            completed=completed,
            message=(
                f"{verb} (mục tiêu {target_text}, "
                f"đã ghi {done_count}/{total} mục tiêu)."
            ),
            current=done_count,
            item_total=total,
            target_id=target_id or None,
            composition_id=composition_id,
        )

    return _callback


def _scaled_progress(*, start: int, end: int, current: int, total: int) -> int:
    if total <= 0:
        return end
    bounded_current = max(0, min(current, total))
    return round(start + (end - start) * bounded_current / total)


def _publish_progress(
    on_progress: ExportProgressCallback | None,
    *,
    stage: str,
    completed: int,
    message: str,
    current: int | None = None,
    item_total: int | None = None,
    target_id: str | None = None,
    composition_id: str | None = None,
) -> None:
    if on_progress is None:
        return
    on_progress(
        ExportProgress(
            stage=stage,
            message=message,
            completed=max(0, min(100, completed)),
            total=100,
            current=current,
            item_total=item_total,
            target_id=target_id,
            composition_id=composition_id,
        )
    )


def _attach_history_sync_issues(
    plan: ExportPreflightPlan,
    history_sync_result: ExportHistorySyncResult,
) -> ExportPreflightPlan:
    if not history_sync_result.issues:
        return plan
    all_issues = list(plan.issues)
    for issue in history_sync_result.issues:
        if issue not in all_issues:
            all_issues.append(issue)
    rows = []
    for row in plan.rows:
        row_issues = list(row.issues)
        for issue in history_sync_result.issues:
            if issue.composition_id == row.composition_id and issue not in row_issues:
                row_issues.append(issue)
        rows.append(row.model_copy(update={"issues": row_issues}))
    return plan.model_copy(
        update={
            "rows": rows,
            "issues": all_issues,
            "summary": _summary(rows, all_issues),
        }
    )


def _summary(rows: list, issues: list[Issue]) -> ExportPreflightSummary:
    warning_count = sum(1 for issue in issues if issue.severity == IssueSeverity.WARNING)
    error_count = sum(1 for issue in issues if issue.severity == IssueSeverity.ERROR)
    state = ExportPreflightState.READY
    if error_count:
        state = ExportPreflightState.BLOCKED
    elif warning_count:
        state = ExportPreflightState.WARNING
    return ExportPreflightSummary(
        included_slide_count=len(rows),
        target_count=len({row.target_id for row in rows}),
        skipped_count=sum(1 for row in rows if row.blocking),
        warning_count=warning_count,
        error_count=error_count,
        state=state,
    )


def _output_paths(
    workspace_service: WorkspaceService,
    output_stem: str,
) -> tuple[Path, Path, Path]:
    safe_stem = safe_filename_component(
        Path(output_stem.strip()).stem,
        fallback=DEFAULT_EXPORT_STEM,
    )
    output_dir = workspace_service.paths.exports
    return (
        output_dir / f"{safe_stem}.pptx",
        output_dir / f"{safe_stem}.txt",
        output_dir / f"{safe_stem}.export-log.json",
    )
