"""Headless TXT report export service."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from thucthengay.export.txt_values import resolve_txt_line
from thucthengay.models import (
    Composition,
    ExportedTxtLine,
    ExportTxtResult,
    ExportTxtSummary,
    Issue,
    IssueScope,
    IssueSeverity,
    TargetConfig,
)
from thucthengay.workspace import WorkspaceService


def export_txt_report(
    workspace_service: WorkspaceService,
    targets: Iterable[TargetConfig],
    *,
    output_path: str | Path,
) -> ExportTxtResult:
    """Write a UTF-8 TXT report line for each included composition."""
    target_map = {target.id: target for target in targets}
    included = [
        composition
        for composition in workspace_service.list_compositions()
        if composition.include
    ]
    included.sort(key=_export_sort_key)

    issues = _pre_write_issues(included, target_map)
    if issues:
        return _blocked(issues)

    exported: list[ExportedTxtLine] = []
    for line_number, composition in enumerate(included, start=1):
        target = target_map[composition.target_id]
        resolution = resolve_txt_line(
            target.export.template_txt_value or "",
            composition,
            target,
            slide_number=line_number,
        )
        if resolution.problems:
            issues.extend(
                _problem_issue(problem.issue_id, problem.field, composition)
                for problem in resolution.problems
            )
            continue
        exported.append(
            ExportedTxtLine(
                composition_id=composition.composition_id,
                target_id=composition.target_id,
                line_number=line_number,
                text=resolution.text,
            )
        )

    if issues:
        return _blocked(issues)

    try:
        resolved_output = _resolve_output_path(workspace_service, output_path)
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(
            "".join(f"{row.text}\n" for row in exported),
            encoding="utf-8",
        )
    except (OSError, ValueError) as error:
        return _blocked([_write_issue(f"Khong ghi duoc file TXT export: {error}")])
    relative_output = _workspace_relative(workspace_service, resolved_output)
    return ExportTxtResult(
        ok=True,
        txt_path=relative_output,
        exported=exported,
        summary=ExportTxtSummary(
            line_count=len(exported),
            target_count=len({row.target_id for row in exported}),
        ),
    )


def _pre_write_issues(
    compositions: list[Composition],
    target_map: dict[str, TargetConfig],
) -> list[Issue]:
    issues: list[Issue] = []
    for line_number, composition in enumerate(compositions, start=1):
        target = target_map.get(composition.target_id)
        if target is None:
            issues.append(
                _issue(
                    "export.target_missing",
                    "Khong tim thay target cua composition khi export TXT.",
                    "Kiem tra lai config target va workspace composition.",
                    composition=composition,
                )
            )
            continue
        if composition.review_order is None:
            issues.append(
                _issue(
                    "export.review_order_missing",
                    "Composition include chua co review_order de export TXT.",
                    "Quay lai Review/Edit va Include/Validate lai composition nay.",
                    composition=composition,
                )
            )
        if not composition.ready or composition.needs_revalidation:
            issues.append(
                _issue(
                    "export.composition_not_ready",
                    "Composition include chua san sang de export TXT.",
                    "Chay Include/Validate lai hoac bo include composition nay.",
                    composition=composition,
                )
            )
        if not target.export.template_txt_value:
            issues.append(
                _issue(
                    "export.txt_template_missing",
                    "Target chua cau hinh template_txt_value.",
                    "Bo sung `export.template_txt_value` cho target truoc khi export TXT.",
                    composition=composition,
                )
            )
            continue
        resolution = resolve_txt_line(
            target.export.template_txt_value,
            composition,
            target,
            slide_number=line_number,
        )
        issues.extend(
            _problem_issue(problem.issue_id, problem.field, composition)
            for problem in resolution.problems
        )
    return issues


def _problem_issue(issue_id: str, field: str, composition: Composition) -> Issue:
    if issue_id == "export.txt_placeholder_unknown":
        message = f"TXT template dung placeholder chua ho tro: {field}."
        remediation = "Sua template_txt_value de chi dung cac placeholder da ho tro."
    elif issue_id == "export.txt_time_label_unresolved":
        message = "TXT template can time_label nhung khong co layer visible hop le co thoi gian."
        remediation = (
            "Quay lai Review/Edit Metadata de sua capture_time va metadata_status cua layer "
            "visible, hoac danh dau placeholder la optional bang `{time_label?}`."
        )
    else:
        message = f"TXT template khong resolve duoc placeholder: {field}."
        remediation = "Sua metadata/composition/target config de co gia tri truoc khi export."
    return _issue(issue_id, message, remediation, composition=composition)


def _resolve_output_path(workspace_service: WorkspaceService, output_path: str | Path) -> Path:
    path = Path(output_path)
    if not path.is_absolute():
        path = workspace_service.paths.root / path
    resolved = path.resolve()
    root = workspace_service.paths.root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        msg = f"TXT output path must stay inside workspace: {output_path!r}"
        raise ValueError(msg) from error
    return resolved


def _workspace_relative(workspace_service: WorkspaceService, path: Path) -> str:
    return path.resolve().relative_to(workspace_service.paths.root.resolve()).as_posix()


def _blocked(issues: list[Issue]) -> ExportTxtResult:
    return ExportTxtResult(
        ok=False,
        issues=issues,
        summary=ExportTxtSummary(
            error_count=sum(1 for issue in issues if issue.severity == IssueSeverity.ERROR),
            warning_count=sum(1 for issue in issues if issue.severity == IssueSeverity.WARNING),
        ),
    )


def _issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    composition: Composition,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=IssueScope.EXPORT,
        target_id=composition.target_id,
        composition_id=composition.composition_id,
        message=message,
        remediation=remediation,
    )


def _write_issue(message: str) -> Issue:
    return Issue(
        issue_id="export.txt_write_failed",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.EXPORT,
        message=message,
        remediation=(
            "Chon duong dan TXT trong workspace, dong file dang khoa, "
            "kiem tra quyen ghi, roi chay export lai."
        ),
    )


def _export_sort_key(composition: Composition) -> tuple[int, int, str]:
    return (
        1 if composition.review_order is None else 0,
        composition.review_order or 0,
        composition.composition_id,
    )
