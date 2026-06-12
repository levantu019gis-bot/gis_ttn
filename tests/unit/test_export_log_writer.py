from __future__ import annotations

import json
from pathlib import Path

from thucthengay.export import write_export_summary_and_trace_log
from thucthengay.models import (
    ExportCompletionState,
    ExportedComposition,
    ExportedTxtLine,
    ExportPlanRow,
    ExportPptxResult,
    ExportPptxSummary,
    ExportPreflightPlan,
    ExportPreflightSummary,
    ExportTxtResult,
    ExportTxtSummary,
    Issue,
    IssueScope,
    IssueSeverity,
)
from thucthengay.workspace import WorkspaceService


def _workspace(tmp_path: Path) -> WorkspaceService:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    return service


def _plan(*rows: ExportPlanRow, issues: list[Issue] | None = None) -> ExportPreflightPlan:
    return ExportPreflightPlan(
        rows=list(rows),
        issues=issues or [],
        summary=ExportPreflightSummary(
            included_slide_count=len(rows),
            target_count=len({row.target_id for row in rows}),
            warning_count=sum(
                1 for issue in issues or [] if issue.severity == IssueSeverity.WARNING
            ),
            error_count=sum(1 for issue in issues or [] if issue.severity == IssueSeverity.ERROR),
        ),
    )


def _row(
    composition_id: str,
    *,
    target_id: str = "alpha",
    slide_number: int | None = 1,
    issues: list[Issue] | None = None,
) -> ExportPlanRow:
    return ExportPlanRow(
        composition_id=composition_id,
        target_id=target_id,
        slide_number=slide_number,
        review_order=slide_number,
        target_label=target_id.upper(),
        date_label="2026-05-25",
        time_label="08:30:00",
        template_status="OK",
        final_render_path=f"renders/{composition_id}.png",
        issues=issues or [],
    )


def _warning(composition_id: str) -> Issue:
    return Issue(
        issue_id="export.template_warning",
        severity=IssueSeverity.WARNING,
        scope=IssueScope.EXPORT,
        target_id="alpha",
        composition_id=composition_id,
        message="Canh bao export.",
        remediation="Kiem tra lai canh bao export.",
    )


def _error(composition_id: str) -> Issue:
    return Issue(
        issue_id="render.raster.no_overlap",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id="alpha",
        composition_id=composition_id,
        message="Khong co layer visible nao phu vung ban do can render.",
        remediation="Kiem tra lai tam ban do, scale hoac du lieu raster.",
    )


def _pptx_result(*composition_ids: str) -> ExportPptxResult:
    exported = [
        ExportedComposition(
            composition_id=composition_id,
            target_id="alpha",
            slide_number=index,
            render_path=f"renders/{composition_id}.png",
        )
        for index, composition_id in enumerate(composition_ids, start=1)
    ]
    return ExportPptxResult(
        ok=True,
        pptx_path="exports/report.pptx",
        exported=exported,
        summary=ExportPptxSummary(slide_count=len(exported), target_count=1),
    )


def _txt_result(*composition_ids: str) -> ExportTxtResult:
    exported = [
        ExportedTxtLine(
            composition_id=composition_id,
            target_id="alpha",
            line_number=index,
            text=f"{index}|{composition_id}",
        )
        for index, composition_id in enumerate(composition_ids, start=1)
    ]
    return ExportTxtResult(
        ok=True,
        txt_path="exports/report.txt",
        exported=exported,
        summary=ExportTxtSummary(line_count=len(exported), target_count=1),
    )


def test_write_export_summary_and_trace_log_success_json(tmp_path: Path) -> None:
    service = _workspace(tmp_path)

    result = write_export_summary_and_trace_log(
        service,
        preflight_plan=_plan(_row("alpha__20260525")),
        pptx_result=_pptx_result("alpha__20260525"),
        txt_result=_txt_result("alpha__20260525"),
        output_path=service.paths.exports / "report.export-log.json",
    )

    assert result.ok is True
    assert result.summary.state == ExportCompletionState.SUCCESS
    assert result.summary.slide_count == 1
    assert result.summary.target_count == 1
    assert result.summary.skipped_count == 0
    assert result.summary.pptx_path == "exports/report.pptx"
    assert result.summary.txt_path == "exports/report.txt"
    assert result.summary.log_path == "exports/report.export-log.json"
    assert result.log.entries[0].composition_id == "alpha__20260525"
    assert result.log.entries[0].pptx_slide_number == 1
    assert result.log.entries[0].txt_line_number == 1

    payload = json.loads((service.paths.exports / "report.export-log.json").read_text("utf-8"))
    assert payload["summary"]["state"] == "success"
    assert payload["entries"][0]["status"] == "exported"


def test_write_export_summary_and_trace_log_warning_state_and_issue_summary(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path)
    warning = _warning("alpha__20260525")

    result = write_export_summary_and_trace_log(
        service,
        preflight_plan=_plan(_row("alpha__20260525", issues=[warning]), issues=[warning]),
        pptx_result=_pptx_result("alpha__20260525"),
        txt_result=_txt_result("alpha__20260525"),
        output_path=service.paths.exports / "warning.export-log.json",
    )

    assert result.ok is True
    assert result.summary.state == ExportCompletionState.SUCCESS_WITH_WARNINGS
    assert result.summary.warning_count == 1
    assert result.log.issue_summary[0].issue_id == "export.template_warning"
    assert result.log.issue_summary[0].count == 1


def test_write_export_summary_and_trace_log_marks_missing_output_row_failed(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path)

    result = write_export_summary_and_trace_log(
        service,
        preflight_plan=_plan(_row("alpha__20260525"), _row("alpha__20260526", slide_number=2)),
        pptx_result=_pptx_result("alpha__20260525"),
        txt_result=_txt_result("alpha__20260525"),
        output_path=service.paths.exports / "failed-row.export-log.json",
    )

    assert result.ok is False
    assert result.summary.state == ExportCompletionState.FAILURE
    assert result.summary.skipped_count == 1
    failed = result.log.entries[1]
    assert failed.composition_id == "alpha__20260526"
    assert failed.status == "failed"
    assert "PPTX/TXT" in (failed.skipped_reason or "")


def test_write_export_summary_and_trace_log_skips_blocked_rows_without_cascade(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path)
    skipped_issue = _error("alpha__20260526")

    result = write_export_summary_and_trace_log(
        service,
        preflight_plan=_plan(
            _row("alpha__20260525"),
            _row("alpha__20260526", slide_number=2, issues=[skipped_issue]),
            issues=[skipped_issue],
        ),
        pptx_result=_pptx_result("alpha__20260525"),
        txt_result=_txt_result("alpha__20260525"),
        output_path=service.paths.exports / "partial.export-log.json",
    )

    assert result.ok is True
    assert result.summary.state == ExportCompletionState.SUCCESS_WITH_WARNINGS
    assert result.summary.skipped_count == 1
    assert result.summary.error_count == 1
    assert result.log.entries[1].status == "skipped"
    assert "Khong co layer visible" in (result.log.entries[1].skipped_reason or "")
    assert "export.output_row_missing" not in {issue.issue_id for issue in result.log.issues}


def test_write_export_summary_and_trace_log_rejects_out_of_workspace_path(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path)

    result = write_export_summary_and_trace_log(
        service,
        preflight_plan=_plan(_row("alpha__20260525")),
        pptx_result=_pptx_result("alpha__20260525"),
        txt_result=_txt_result("alpha__20260525"),
        output_path=tmp_path / "outside.export-log.json",
    )

    assert result.ok is False
    assert result.summary.state == ExportCompletionState.FAILURE
    assert result.log is None
    assert "export.log_write_failed" in {issue.issue_id for issue in result.issues}
    assert not (tmp_path / "outside.export-log.json").exists()
