"""Create workspace compositions from cached target/date imagery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, time

from thucthengay.ingestion.cache_builder import UNKNOWN_DATE_KEY, CachePopulationResult
from thucthengay.models import (
    Composition,
    CompositionArtifacts,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    MetadataStatus,
    TargetConfig,
    ViewState,
)
from thucthengay.workspace import WorkspaceError, WorkspaceService

CheckpointCallback = Callable[[], None]


@dataclass(frozen=True)
class CompositionCreationResult:
    """Composition creation output."""

    composition_ids: list[str]
    issues: list[Issue]


def create_target_date_compositions(
    cache_result: CachePopulationResult,
    targets_by_id: dict[str, TargetConfig],
    workspace_service: WorkspaceService,
    *,
    merge_existing: bool = False,
    checkpoint: CheckpointCallback | None = None,
) -> CompositionCreationResult:
    """Create one workspace composition per target/date group."""
    composition_ids: list[str] = []
    issues: list[Issue] = []

    for (target_id, date_key), layers in cache_result.layers_by_target_date.items():
        if checkpoint is not None:
            checkpoint()
        target = targets_by_id.get(target_id)
        if target is None:
            issues.append(
                _composition_issue(
                    "composition.target_missing",
                    target_id,
                    f"Không tìm thấy target config cho nhóm ảnh `{target_id}`.",
                    "Tải lại config và chạy lại bước match trước khi tạo composition.",
                )
            )
            continue

        capture_date = _capture_date_from_key(target_id, date_key, issues)
        if capture_date is None:
            continue

        composition_id = _composition_id(target_id, date_key)
        initial_layers = _initial_layers(layers)
        if merge_existing and workspace_service.paths.composition_file(composition_id).exists():
            composition = _merge_existing_composition(
                workspace_service,
                composition_id=composition_id,
                target_id=target_id,
                capture_date=capture_date,
                incoming_layers=initial_layers,
            )
        else:
            composition = Composition(
                composition_id=composition_id,
                target_id=target_id,
                capture_date=capture_date,
                layers=initial_layers,
                view=ViewState(center=target.coordinate, scale=target.scale),
                grid_override=None,
            )
        workspace_service.write_composition(composition)
        composition_ids.append(composition.composition_id)
        if checkpoint is not None:
            checkpoint()

    return CompositionCreationResult(composition_ids=composition_ids, issues=issues)


def _initial_layers(layers: list[ImageLayer]) -> list[ImageLayer]:
    sorted_layers = sorted(
        layers,
        key=lambda layer: (
            layer.capture_time is not None,
            layer.capture_time or time.min,
            layer.layer_id,
        ),
        reverse=True,
    )
    return [
        _layer_with_initial_order(layer, order)
        for order, layer in enumerate(sorted_layers)
    ]


def _layer_with_initial_order(layer: ImageLayer, order: int) -> ImageLayer:
    metadata_status = layer.metadata_status
    if layer.capture_time is None:
        metadata_status = MetadataStatus.NEEDS_MANUAL_CORRECTION
    return layer.model_copy(update={"order": order, "metadata_status": metadata_status})


def _merge_existing_composition(
    workspace_service: WorkspaceService,
    *,
    composition_id: str,
    target_id: str,
    capture_date: date,
    incoming_layers: list[ImageLayer],
) -> Composition:
    existing = workspace_service.read_composition(composition_id)
    if existing.target_id != target_id or existing.capture_date != capture_date:
        msg = (
            f"Composition co san {composition_id} khong khop target/ngay voi du lieu ingest moi."
        )
        raise WorkspaceError(msg)

    merged_layers = _merge_layers(existing.layers, incoming_layers)
    if _layers_json(merged_layers) == _layers_json(existing.layers):
        return existing

    updated = Composition.model_validate(
        {
            **existing.model_dump(mode="python"),
            "layers": merged_layers,
            "artifacts": _stale_artifacts(existing.artifacts),
            "needs_revalidation": True,
            "ready": False,
            "include": False,
            "review_order": None,
        }
    )
    return updated


def _merge_layers(
    existing_layers: list[ImageLayer],
    incoming_layers: list[ImageLayer],
) -> list[ImageLayer]:
    incoming_by_id = {layer.layer_id: layer for layer in incoming_layers}
    merged: list[ImageLayer] = []
    for existing_layer in sorted(existing_layers, key=lambda layer: layer.order):
        incoming = incoming_by_id.pop(existing_layer.layer_id, None)
        if incoming is None:
            merged.append(existing_layer)
            continue
        merged.append(
            incoming.model_copy(
                update={
                    "visible": existing_layer.visible,
                    "order": existing_layer.order,
                }
            )
        )

    existing_ids = {layer.layer_id for layer in existing_layers}
    for incoming in incoming_layers:
        if incoming.layer_id not in existing_ids:
            merged.append(incoming)

    return [
        layer.model_copy(update={"order": order})
        for order, layer in enumerate(merged)
    ]


def _stale_artifacts(artifacts: CompositionArtifacts) -> CompositionArtifacts:
    return artifacts.model_copy(
        update={
            "final_render_path": None,
            "render_log_path": None,
        }
    )


def _layers_json(layers: list[ImageLayer]) -> list[dict[str, object]]:
    return [layer.model_dump(mode="json") for layer in layers]


def _capture_date_from_key(
    target_id: str,
    date_key: str,
    issues: list[Issue],
) -> date | None:
    if date_key == UNKNOWN_DATE_KEY:
        issues.append(
            _composition_issue(
                "composition.capture_date_missing",
                target_id,
                f"Không thể tạo composition cho target `{target_id}` vì thiếu ngày chụp.",
                "Sửa metadata ngày chụp trước khi tạo composition target-date.",
            )
        )
        return None

    try:
        return date.fromisoformat(f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}")
    except ValueError:
        issues.append(
            _composition_issue(
                "composition.capture_date_invalid",
                target_id,
                f"Ngày chụp `{date_key}` của target `{target_id}` không hợp lệ.",
                "Kiểm tra metadata ngày chụp và chạy lại ingest.",
            )
        )
        return None


def _composition_id(target_id: str, date_key: str) -> str:
    return f"{target_id}__{date_key}"


def _composition_issue(
    issue_id: str,
    target_id: str,
    message: str,
    remediation: str,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.WARNING,
        scope=IssueScope.COMPOSITION,
        target_id=target_id,
        message=message,
        remediation=remediation,
    )
