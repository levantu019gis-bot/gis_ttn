"""Export summary and trace-log writer."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from thucthengay.models import (
    ExportCompletionState,
    ExportCompletionSummary,
    ExportIssueSummary,
    ExportLog,
    ExportLogWriteResult,
    ExportPlanRow,
    ExportPptxResult,
    ExportPreflightPlan,
    ExportTraceEntry,
    ExportTraceStatus,
    ExportTxtResult,
    Issue,
    IssueScope,
    IssueSeverity,
    SkippedComposition,
)
from thucthengay.workspace import WorkspaceService


def write_export_summary_and_trace_log(
    workspace_service: WorkspaceService,
    *,
    preflight_plan: ExportPreflightPlan,
    pptx_result: ExportPptxResult,
    txt_result: ExportTxtResult,
    output_path: str | Path,
) -> ExportLogWriteResult:
    """Write a JSON export log containing summary metrics and per-composition trace rows."""
    path_result = _resolve_output_path(workspace_service, output_path)
    if isinstance(path_result, Issue):
        summary = _summary(
            preflight_plan=preflight_plan,
            pptx_result=pptx_result,
            txt_result=txt_result,
            log_path=None,
            entries=[],
        issues=[
            *_plan_issues(preflight_plan),
            *pptx_result.issues,
            *txt_result.issues,
            path_result,
        ],
        )
        summary = summary.model_copy(update={"state": ExportCompletionState.FAILURE})
        return ExportLogWriteResult(ok=False, summary=summary, issues=[path_result])

    entries, trace_issues = _trace_entries(preflight_plan, pptx_result, txt_result)
    issues = [*_plan_issues(preflight_plan), *pptx_result.issues, *txt_result.issues, *trace_issues]
    log_path = _workspace_relative(workspace_service, path_result)
    summary = _summary(
        preflight_plan=preflight_plan,
        pptx_result=pptx_result,
        txt_result=txt_result,
        log_path=log_path,
        entries=entries,
        issues=issues,
    )
    issue_summary = _issue_summary(issues)
    log = ExportLog(
        pptx_path=pptx_result.pptx_path,
        txt_path=txt_result.txt_path,
        log_path=log_path,
        slide_count=summary.slide_count,
        txt_line_count=summary.txt_line_count,
        target_count=summary.target_count,
        skipped_count=summary.skipped_count,
        warning_count=summary.warning_count,
        error_count=summary.error_count,
        exported=pptx_result.exported,
        skipped=[
            SkippedComposition(
                composition_id=entry.composition_id,
                reason=entry.skipped_reason or entry.status.value,
            )
            for entry in entries
            if entry.status != ExportTraceStatus.EXPORTED
        ],
        entries=entries,
        issue_summary=issue_summary,
        issues=issues,
    )

    payload = {
        "summary": summary.model_dump(mode="json"),
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "issue_summary": [item.model_dump(mode="json") for item in issue_summary],
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }
    try:
        path_result.parent.mkdir(parents=True, exist_ok=True)
        path_result.write_text(
            _json_dumps(payload),
            encoding="utf-8",
        )
    except OSError as error:
        issue = _write_issue(f"Khong ghi duoc export log: {error}")
        failed_summary = summary.model_copy(
            update={
                "state": ExportCompletionState.FAILURE,
                "log_path": None,
                "error_count": summary.error_count + 1,
            }
        )
        return ExportLogWriteResult(ok=False, summary=failed_summary, log=None, issues=[issue])

    return ExportLogWriteResult(
        ok=summary.state != ExportCompletionState.FAILURE,
        summary=summary,
        log=log,
        issues=issues,
    )


def _trace_entries(
    preflight_plan: ExportPreflightPlan,
    pptx_result: ExportPptxResult,
    txt_result: ExportTxtResult,
) -> tuple[list[ExportTraceEntry], list[Issue]]:
    pptx_rows = {row.composition_id: row for row in pptx_result.exported}
    txt_rows = {row.composition_id: row for row in txt_result.exported}
    result_issues = [*pptx_result.issues, *txt_result.issues]
    entries: list[ExportTraceEntry] = []
    issues: list[Issue] = []
    for row in preflight_plan.rows:
        pptx_row = pptx_rows.get(row.composition_id)
        txt_row = txt_rows.get(row.composition_id)
        if row.blocking:
            entries.append(
                _skipped_entry(
                    row,
                    status=ExportTraceStatus.SKIPPED,
                    reason=_row_issue_reason(row),
                )
            )
            continue
        if pptx_row is None or txt_row is None:
            known_reason = _result_issue_reason(row, result_issues)
            if known_reason:
                entries.append(
                    _skipped_entry(
                        row,
                        status=ExportTraceStatus.SKIPPED,
                        reason=known_reason,
                    )
                )
                continue
            entries.append(
                _skipped_entry(
                    row,
                    status=ExportTraceStatus.FAILED,
                    reason="Composition khong co day du dong PPTX/TXT trong ket qua export.",
                )
            )
            issues.append(_missing_output_issue(row))
            continue
        entries.append(
            ExportTraceEntry(
                composition_id=row.composition_id,
                target_id=row.target_id,
                status=ExportTraceStatus.EXPORTED,
                pptx_slide_number=pptx_row.slide_number,
                txt_line_number=txt_row.line_number,
            )
        )
    return entries, issues


def _result_issue_reason(row: ExportPlanRow, issues: list[Issue]) -> str | None:
    for issue in issues:
        if issue.composition_id == row.composition_id:
            return issue.message
    for issue in issues:
        if issue.composition_id is None and issue.target_id == row.target_id:
            return issue.message
    return None


def _plan_issues(preflight_plan: ExportPreflightPlan) -> list[Issue]:
    issues = list(preflight_plan.issues)
    for row in preflight_plan.rows:
        issues.extend(issue for issue in row.issues if issue not in issues)
    return issues


def _summary(
    *,
    preflight_plan: ExportPreflightPlan,
    pptx_result: ExportPptxResult,
    txt_result: ExportTxtResult,
    log_path: str | None,
    entries: list[ExportTraceEntry],
    issues: list[Issue],
) -> ExportCompletionSummary:
    warning_count = sum(1 for issue in issues if issue.severity == IssueSeverity.WARNING)
    error_count = sum(1 for issue in issues if issue.severity == IssueSeverity.ERROR)
    skipped_count = sum(1 for entry in entries if entry.status != ExportTraceStatus.EXPORTED)
    trace_error_count = sum(1 for entry in entries if entry.status == ExportTraceStatus.FAILED)
    target_ids = {row.target_id for row in preflight_plan.rows}
    target_ids.update(row.target_id for row in pptx_result.exported)
    target_ids.update(row.target_id for row in txt_result.exported)
    state = ExportCompletionState.SUCCESS
    if trace_error_count or not pptx_result.ok or not txt_result.ok:
        state = ExportCompletionState.FAILURE
    elif warning_count or error_count or skipped_count:
        state = ExportCompletionState.SUCCESS_WITH_WARNINGS
    return ExportCompletionSummary(
        state=state,
        slide_count=pptx_result.summary.slide_count,
        txt_line_count=txt_result.summary.line_count,
        target_count=len(target_ids),
        skipped_count=skipped_count,
        warning_count=warning_count,
        error_count=error_count,
        pptx_path=pptx_result.pptx_path,
        txt_path=txt_result.txt_path,
        log_path=log_path,
    )


def _issue_summary(issues: list[Issue]) -> list[ExportIssueSummary]:
    counts = Counter((issue.issue_id, issue.severity) for issue in issues)
    return [
        ExportIssueSummary(issue_id=issue_id, severity=severity, count=count)
        for (issue_id, severity), count in sorted(
            counts.items(),
            key=lambda item: (item[0][1].value, item[0][0]),
        )
    ]


def _skipped_entry(
    row: ExportPlanRow,
    *,
    status: ExportTraceStatus,
    reason: str,
) -> ExportTraceEntry:
    return ExportTraceEntry(
        composition_id=row.composition_id,
        target_id=row.target_id,
        status=status,
        skipped_reason=reason,
    )


def _row_issue_reason(row: ExportPlanRow) -> str:
    if not row.issues:
        return "Composition bi bo qua trong preflight."
    return "; ".join(issue.message for issue in row.issues[:3])


def _missing_output_issue(row: ExportPlanRow) -> Issue:
    return Issue(
        issue_id="export.output_row_missing",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.EXPORT,
        target_id=row.target_id,
        composition_id=row.composition_id,
        message="Composition khong co day du dong PPTX/TXT trong ket qua export.",
        remediation="Chay lai export sau khi kiem tra PPTX/TXT exporter va preflight.",
    )


def _resolve_output_path(
    workspace_service: WorkspaceService,
    output_path: str | Path,
) -> Path | Issue:
    path = Path(output_path)
    if not path.is_absolute():
        path = workspace_service.paths.root / path
    resolved = path.resolve()
    root = workspace_service.paths.root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return _write_issue("Duong dan export log phai nam trong workspace.")
    return resolved


def _workspace_relative(workspace_service: WorkspaceService, path: Path) -> str:
    return path.resolve().relative_to(workspace_service.paths.root.resolve()).as_posix()


def _write_issue(message: str) -> Issue:
    return Issue(
        issue_id="export.log_write_failed",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.EXPORT,
        message=message,
        remediation=(
            "Chon thu muc export trong workspace, dong file dang khoa, "
            "roi chay export lai."
        ),
    )


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
