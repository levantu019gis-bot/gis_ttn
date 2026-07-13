"""Composition readiness validation rules."""

from __future__ import annotations

from collections.abc import Iterable

from thucthengay.models import (
    Composition,
    GridConfig,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    MetadataStatus,
    TemplateMetadata,
)
from thucthengay.validation.service import ValidationContext, ValidationResult


def validate_composition_readiness(context: ValidationContext) -> ValidationResult:
    """Validate whether a composition is eligible for ready/include/export decisions."""
    return ValidationResult.from_issues(composition_readiness_issues(context))


def composition_readiness_issues(context: ValidationContext) -> tuple[Issue, ...]:
    """Return blocking readiness issues for the current validation context."""
    composition = context.composition
    if composition is None:
        return (
            Issue(
                issue_id="composition.missing",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.COMPOSITION,
                message="Không có composition để kiểm tra readiness.",
                remediation="Chọn lại composition hoặc tải lại workspace trước khi validate.",
            ),
        )

    issues: list[Issue] = []
    issues.extend(_layer_stack_issues(composition))
    issues.extend(_metadata_issues(composition))
    issues.extend(_view_issues(composition))
    issues.extend(_grid_issues(composition))
    issues.extend(_template_issues(context))
    issues.extend(_stale_validation_issues(context))
    return tuple(issues)


def _layer_stack_issues(composition: Composition) -> Iterable[Issue]:
    if any(layer.visible for layer in composition.layers):
        return ()
    return (
        Issue(
            issue_id="composition.no_visible_layer",
            severity=IssueSeverity.ERROR,
            scope=IssueScope.COMPOSITION,
            target_id=composition.target_id,
            composition_id=composition.composition_id,
            message="Composition không có layer nào đang bật.",
            remediation="Bật ít nhất một layer hợp lệ trong layer stack trước khi ready/export.",
        ),
    )


def _metadata_issues(composition: Composition) -> Iterable[Issue]:
    issues: list[Issue] = []
    for layer in composition.layers:
        if not layer.visible:
            continue
        if _layer_timestamp_invalid(layer):
            issues.append(
                Issue(
                    issue_id="layer.capture_timestamp_invalid",
                    severity=IssueSeverity.ERROR,
                    scope=IssueScope.LAYER,
                    target_id=composition.target_id,
                    composition_id=composition.composition_id,
                    layer_id=layer.layer_id,
                    message="Layer đang bật thiếu ngày hoặc giờ chụp hợp lệ.",
                    remediation="Mở metadata editor để sửa ngày/giờ chụp của layer này.",
                )
            )
        elif layer.metadata_status in {
            MetadataStatus.UNKNOWN,
            MetadataStatus.NEEDS_CORRECTION,
            MetadataStatus.NEEDS_MANUAL_CORRECTION,
        }:
            issues.append(
                Issue(
                    issue_id="layer.metadata_needs_correction",
                    severity=IssueSeverity.ERROR,
                    scope=IssueScope.LAYER,
                    target_id=composition.target_id,
                    composition_id=composition.composition_id,
                    layer_id=layer.layer_id,
                    message="Layer đang bật có metadata chưa được xác nhận hợp lệ.",
                    remediation="Mở metadata editor để xác nhận hoặc sửa metadata layer.",
                )
            )
    return tuple(issues)


def _layer_timestamp_invalid(layer: ImageLayer) -> bool:
    return layer.capture_date is None or layer.capture_time is None


def _view_issues(composition: Composition) -> Iterable[Issue]:
    center = composition.view.center
    center_invalid = (
        len(center) != 2
        or center[0] < -180
        or center[0] > 180
        or center[1] < -90
        or center[1] > 90
    )
    if not center_invalid and composition.view.scale > 0:
        return ()
    return (
        Issue(
            issue_id="composition.view_invalid",
            severity=IssueSeverity.ERROR,
            scope=IssueScope.COMPOSITION,
            target_id=composition.target_id,
            composition_id=composition.composition_id,
            message="View center hoặc scale của composition không hợp lệ.",
            remediation="Sửa lại tâm bản đồ và mẫu số tỷ lệ trong Review/Edit.",
        ),
    )


def _grid_issues(composition: Composition) -> Iterable[Issue]:
    if composition.grid_override is None or _grid_interval_positive(composition.grid_override):
        return ()
    return (
        Issue(
            issue_id="composition.grid_override_invalid",
            severity=IssueSeverity.ERROR,
            scope=IssueScope.COMPOSITION,
            target_id=composition.target_id,
            composition_id=composition.composition_id,
            message="Grid override của composition không hợp lệ.",
            remediation="Sửa grid interval để lớn hơn 0 hoặc xóa override để dùng cấu hình target.",
        ),
    )


def _grid_interval_positive(grid: GridConfig) -> bool:
    interval = grid.interval
    return interval.degrees > 0 or interval.minutes > 0 or interval.seconds > 0


def _template_issues(context: ValidationContext) -> Iterable[Issue]:
    composition = context.composition
    if composition is not None:
        target_id = composition.target_id
    elif context.target is not None:
        target_id = context.target.id
    else:
        target_id = None
    composition_id = composition.composition_id if composition is not None else None

    if context.target is None:
        if target_id is not None and _is_unmatched_target_id(target_id):
            return ()
        return (
            Issue(
                issue_id="target.missing",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.TARGET,
                target_id=target_id,
                composition_id=composition_id,
                message="Không tìm thấy cấu hình target cho composition.",
                remediation="Kiểm tra lại project config và target của composition.",
            ),
        )

    if not getattr(context.target.export, "template_pptx_file", ""):
        return (
            Issue(
                issue_id="template.pptx_path_missing",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.TEMPLATE,
                target_id=context.target.id,
                composition_id=composition_id,
                message="Target chưa cấu hình PPTX template.",
                remediation="Bổ sung `export.template_pptx_file` trỏ tới PPTX template một slide.",
            ),
        )

    if context.template_metadata_error:
        return (
            Issue(
                issue_id="template.metadata_invalid",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.TEMPLATE,
                target_id=context.target.id,
                composition_id=composition_id,
                message="PPTX template hoặc mapping element id của target không hợp lệ.",
                remediation=(
                    "Sửa `export.template_pptx_file` hoặc `export.placeholders` rồi validate lại."
                ),
            ),
        )

    if context.template_metadata is None:
        return (
            Issue(
                issue_id="template.metadata_missing",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.TEMPLATE,
                target_id=context.target.id,
                composition_id=composition_id,
                message="Chưa có metadata PPTX đã parse cho target.",
                remediation="Nạp PPTX template của target trước khi ready/export.",
            ),
        )

    return tuple(_map_frame_issues(context.template_metadata, context.target.id, composition_id))


def _is_unmatched_target_id(target_id: str) -> bool:
    return target_id.startswith("__unmatched__")


def _map_frame_issues(
    template_metadata: TemplateMetadata,
    target_id: str,
    composition_id: str | None,
) -> Iterable[Issue]:
    frame = template_metadata.map_frame
    if frame.width > 0 and frame.height > 0 and frame.x >= 0 and frame.y >= 0:
        return ()
    return (
        Issue(
            issue_id="template.map_frame_invalid",
            severity=IssueSeverity.ERROR,
            scope=IssueScope.TEMPLATE,
            target_id=target_id,
            composition_id=composition_id,
            message="Map frame trong PPTX template không hợp lệ.",
            remediation=(
                "Sửa shape map image trong PPTX template để có vị trí và kích thước hợp lệ."
            ),
        ),
    )


def _stale_validation_issues(context: ValidationContext) -> Iterable[Issue]:
    composition = context.composition
    if (
        composition is None
        or not context.require_current_validation
        or not composition.needs_revalidation
    ):
        return ()
    return (
        Issue(
            issue_id="composition.needs_revalidation",
            severity=IssueSeverity.ERROR,
            scope=IssueScope.COMPOSITION,
            target_id=composition.target_id,
            composition_id=composition.composition_id,
            message="Composition đã thay đổi và cần revalidate trước khi được coi là ready.",
            remediation="Chạy Revalidate hoặc Include/Validate để tính lại validation summary.",
        ),
    )
