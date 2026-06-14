"""Export-owned synchronization of historical image registry state."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from thucthengay.history import HistoryRecordError, HistoryService
from thucthengay.models import (
    Composition,
    ExportPreflightPlan,
    Issue,
    IssueScope,
    IssueSeverity,
    TargetConfig,
)
from thucthengay.workspace import WorkspaceError, WorkspaceService

HistorySyncProgressCallback = Callable[[str, str, int, int, bool], None]


@dataclass(frozen=True)
class ExportHistorySyncRow:
    """One composition considered for export history synchronization."""

    composition_id: str
    target_id: str
    recorded_layers: int = 0
    include_events: int = 0
    existing_layers: int = 0


@dataclass(frozen=True)
class ExportHistorySyncResult:
    """Summary returned after syncing export-visible compositions into history."""

    enabled: bool
    rows: tuple[ExportHistorySyncRow, ...] = ()
    issues: tuple[Issue, ...] = ()

    @property
    def recorded_layers(self) -> int:
        return sum(row.recorded_layers for row in self.rows)

    @property
    def include_events(self) -> int:
        return sum(row.include_events for row in self.rows)

    @property
    def existing_layers(self) -> int:
        return sum(row.existing_layers for row in self.rows)


def sync_export_history(
    workspace_service: WorkspaceService,
    targets: Iterable[TargetConfig],
    preflight_plan: ExportPreflightPlan,
    *,
    history_service: HistoryService | None = None,
    on_progress: HistorySyncProgressCallback | None = None,
) -> ExportHistorySyncResult:
    """Record only compositions that survive final preflight into historical SQLite."""
    service = history_service or HistoryService.disabled()
    enabled = bool(getattr(service, "enabled", False))
    if not enabled:
        return ExportHistorySyncResult(enabled=False)

    target_map = {target.id: target for target in targets}
    rows: list[ExportHistorySyncRow] = []
    issues: list[Issue] = []
    seen: set[str] = set()
    exportable_composition_ids = _exportable_composition_ids(preflight_plan)
    total = len(exportable_composition_ids)
    for index, composition_id in enumerate(exportable_composition_ids, start=1):
        try:
            composition = workspace_service.read_composition(composition_id)
        except WorkspaceError as error:
            issues.append(
                _issue(
                    "export.history_composition_missing",
                    "Khong doc duoc composition de cap nhat database history.",
                    f"Kiem tra workspace/compositions roi export lai. Chi tiet: {error}",
                    composition_id=composition_id,
                )
            )
            if on_progress is not None:
                on_progress("", composition_id, index, total, True)
            continue
        if on_progress is not None:
            on_progress(composition.target_id, composition.composition_id, index, total, False)
        history_compositions, pane_issues = _history_compositions_for_export(
            workspace_service,
            composition,
        )
        issues.extend(pane_issues)
        for history_composition in history_compositions:
            if history_composition.composition_id in seen:
                continue
            seen.add(history_composition.composition_id)
            target = target_map.get(history_composition.target_id)
            if target is None:
                issues.append(
                    _issue(
                        "export.history_target_missing",
                        "Khong tim thay target de cap nhat database history.",
                        "Kiem tra config target va workspace composition roi export lai.",
                        composition=history_composition,
                    )
                )
                continue
            try:
                result = service.record_exported_composition(
                    history_composition,
                    target=target,
                    workspace_path=workspace_service.paths.root,
                )
            except (HistoryRecordError, OSError, ValueError) as error:
                issues.append(
                    _issue(
                        "export.history_record_failed",
                        "Khong cap nhat duoc database history cho composition export.",
                        (
                            "Kiem tra duong dan SQLite, quyen ghi file database va layer visible "
                            f"roi export lai. Chi tiet: {error}"
                        ),
                        composition=history_composition,
                    )
                )
                continue
            rows.append(
                ExportHistorySyncRow(
                    composition_id=history_composition.composition_id,
                    target_id=history_composition.target_id,
                    recorded_layers=result.recorded_layers,
                    include_events=result.include_events,
                    existing_layers=result.existing_layers,
                )
            )
        if on_progress is not None:
            on_progress(composition.target_id, composition.composition_id, index, total, True)
    return ExportHistorySyncResult(enabled=True, rows=tuple(rows), issues=tuple(issues))


def _exportable_composition_ids(preflight_plan: ExportPreflightPlan) -> list[str]:
    return [row.composition_id for row in preflight_plan.rows if not row.blocking]


def _history_compositions_for_export(
    workspace_service: WorkspaceService,
    composition: Composition,
) -> tuple[list[Composition], list[Issue]]:
    if not composition.temporal_compare.enabled:
        return [composition], []
    state = composition.temporal_compare
    pane_ids = [state.pane_a_composition_id, state.pane_b_composition_id]
    if not all(pane_ids):
        return [composition], []

    compositions: list[Composition] = []
    issues: list[Issue] = []
    for pane_id in pane_ids:
        try:
            compositions.append(workspace_service.read_composition(str(pane_id)))
        except WorkspaceError as error:
            issues.append(
                _issue(
                    "export.history_compare_pane_missing",
                    "Khong doc duoc composition pane compare de cap nhat database history.",
                    (
                        "Kiem tra cau hinh compare cua composition export roi export lai. "
                        f"Chi tiet: {error}"
                    ),
                    composition=composition,
                )
            )
    return compositions, issues


def _issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    composition: Composition | None = None,
    composition_id: str | None = None,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.WARNING,
        scope=IssueScope.EXPORT,
        target_id=composition.target_id if composition is not None else None,
        composition_id=composition.composition_id if composition is not None else composition_id,
        message=message,
        remediation=remediation,
    )
