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
) -> FullExportResult:
    """Render missing final images, export PPTX/TXT, and write a trace log."""
    target_list = list(targets)
    template_issue_list = _export_template_issues(template_issues)
    initial_plan = build_export_preflight_plan(
        workspace_service,
        target_list,
        template_issues=template_issue_list,
    )
    final_render_result = ensure_final_renders_for_export(
        workspace_service,
        target_list,
        render=render,
        is_cancelled=is_cancelled,
    )
    final_plan = _attach_final_render_issues(
        build_export_preflight_plan(
            workspace_service,
            target_list,
            template_issues=template_issue_list,
        ),
        final_render_result,
    )
    history_sync_result = sync_export_history(
        workspace_service,
        target_list,
        final_plan,
        history_service=history_service,
    )
    final_plan = _attach_history_sync_issues(final_plan, history_sync_result)
    pptx_path, txt_path, log_path = _output_paths(workspace_service, output_stem)
    exportable_composition_ids = _exportable_composition_ids(final_plan)

    if not exportable_composition_ids:
        pptx_result = ExportPptxResult()
        txt_result = ExportTxtResult()
    else:
        pptx_result = export_combined_pptx(
            workspace_service,
            target_list,
            output_path=pptx_path,
            template_issues=template_issue_list,
            composition_ids=exportable_composition_ids,
        )
        txt_result = export_txt_report(
            workspace_service,
            target_list,
            output_path=txt_path,
            composition_ids=exportable_composition_ids,
        )

    log_result = write_export_summary_and_trace_log(
        workspace_service,
        preflight_plan=final_plan,
        pptx_result=pptx_result,
        txt_result=txt_result,
        output_path=log_path,
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
