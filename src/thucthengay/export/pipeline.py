"""End-to-end headless export orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from thucthengay.export.final_render import ensure_final_renders_for_export
from thucthengay.export.log_writer import write_export_summary_and_trace_log
from thucthengay.export.pptx_exporter import export_combined_pptx
from thucthengay.export.preflight import build_export_preflight_plan
from thucthengay.export.txt_exporter import export_txt_report
from thucthengay.models import (
    ExportFinalRenderResult,
    ExportLogWriteResult,
    ExportPptxResult,
    ExportPreflightPlan,
    ExportTxtResult,
    Issue,
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
) -> FullExportResult:
    """Render missing final images, export PPTX/TXT, and write a trace log."""
    target_list = list(targets)
    initial_plan = build_export_preflight_plan(workspace_service, target_list)
    final_render_result = ensure_final_renders_for_export(
        workspace_service,
        target_list,
        render=render,
        is_cancelled=is_cancelled,
    )
    final_plan = build_export_preflight_plan(workspace_service, target_list)
    pptx_path, txt_path, log_path = _output_paths(workspace_service, output_stem)

    if any(issue.blocking for issue in final_plan.issues):
        pptx_result = ExportPptxResult()
        txt_result = ExportTxtResult()
    else:
        pptx_result = export_combined_pptx(
            workspace_service,
            target_list,
            output_path=pptx_path,
        )
        txt_result = export_txt_report(
            workspace_service,
            target_list,
            output_path=txt_path,
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
