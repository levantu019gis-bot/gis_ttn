"""Headless final-render preparation for export."""

from __future__ import annotations

from collections.abc import Iterable
from math import ceil

from pydantic import ValidationError

from thucthengay.models import (
    Composition,
    ExportFinalRenderResult,
    ExportFinalRenderRow,
    ExportFinalRenderStatus,
    ExportFinalRenderSummary,
    Issue,
    IssueScope,
    IssueSeverity,
    TargetConfig,
    TemplateMetadata,
)
from thucthengay.render import (
    RenderSpec,
    RenderSpecError,
    is_final_render_current,
    render_final_png,
    render_spec_hash,
)
from thucthengay.render.final import FinalRenderFunction
from thucthengay.render.raster import CancelCallback
from thucthengay.render.spec import MAX_RENDER_PIXELS, build_render_spec
from thucthengay.workspace import WorkspaceError, WorkspaceService

DEFAULT_FINAL_RENDER_DPI = 200


def ensure_final_renders_for_export(
    workspace_service: WorkspaceService,
    targets: Iterable[TargetConfig],
    *,
    render: FinalRenderFunction | None = None,
    is_cancelled: CancelCallback | None = None,
    final_dpi: int = DEFAULT_FINAL_RENDER_DPI,
) -> ExportFinalRenderResult:
    """Ensure every included composition has a current final PNG for export."""
    target_map = {target.id: target for target in targets}
    included = [
        composition
        for composition in workspace_service.list_compositions()
        if composition.include
    ]
    included.sort(key=_export_sort_key)

    rows = [
        _ensure_composition_final_render(
            workspace_service,
            composition,
            target_map.get(composition.target_id),
            render=render,
            is_cancelled=is_cancelled,
            final_dpi=final_dpi,
        )
        for composition in included
    ]
    issues = [issue for row in rows for issue in row.issues]
    return ExportFinalRenderResult(rows=rows, issues=issues, summary=_summary(rows))


def build_export_final_render_spec(
    composition: Composition,
    target: TargetConfig,
    *,
    final_dpi: int = DEFAULT_FINAL_RENDER_DPI,
) -> RenderSpec:
    """Build the canonical final ``RenderSpec`` used by export preparation."""
    template = _template_metadata(target)
    width, height = final_render_output_size(template, final_dpi=final_dpi)
    return build_render_spec(
        composition=composition,
        target=target,
        template=template,
        template_metadata_file=target.export.template_metadata_file,
        output_width=width,
        output_height=height,
    )


def final_render_output_size(
    template: TemplateMetadata,
    *,
    final_dpi: int = DEFAULT_FINAL_RENDER_DPI,
) -> tuple[int, int]:
    """Convert a PowerPoint point-sized map frame into final render pixels."""
    if placeholder_size := _template_map_placeholder_image_size(template):
        return _cap_render_size(*placeholder_size)

    dpi = max(1, final_dpi)
    width = max(1, ceil(template.map_frame.width / 72 * dpi))
    height = max(1, ceil(template.map_frame.height / 72 * dpi))
    return _cap_render_size(width, height)


def _cap_render_size(width: int, height: int) -> tuple[int, int]:
    if width * height > MAX_RENDER_PIXELS:
        ratio = (MAX_RENDER_PIXELS / (width * height)) ** 0.5
        width = max(1, int(width * ratio))
        height = max(1, int(height * ratio))
    return width, height


def _template_map_placeholder_image_size(template: TemplateMetadata) -> tuple[int, int] | None:
    map_placeholder_ids = {
        str(placeholder.element_id)
        for placeholder in template.placeholders
        if placeholder.kind == "map_image"
    }
    if not map_placeholder_ids:
        return None

    selected_slide = template.metadata.get("selected_slide")
    if not isinstance(selected_slide, dict):
        return None
    shapes = selected_slide.get("shapes")
    if not isinstance(shapes, list):
        return None

    for shape in shapes:
        if not isinstance(shape, dict) or str(shape.get("id")) not in map_placeholder_ids:
            continue
        picture = shape.get("picture")
        if not isinstance(picture, dict):
            continue
        media = picture.get("media")
        if not isinstance(media, dict):
            continue
        image = media.get("image")
        if not isinstance(image, dict):
            continue
        try:
            width = int(image.get("width_px"))
            height = int(image.get("height_px"))
        except (TypeError, ValueError):
            continue
        if width > 0 and height > 0:
            return width, height
    return None


def final_render_currentness_issue(
    *,
    workspace_service: WorkspaceService,
    composition: Composition,
    target: TargetConfig | None,
    final_dpi: int = DEFAULT_FINAL_RENDER_DPI,
) -> Issue | None:
    """Return a blocking issue when an existing final render is not current."""
    if not composition.artifacts.final_render_path:
        return _issue(
            "export.final_render_missing",
            "Composition chua co PNG final render de dua vao PPTX.",
            "Chay buoc render final cho composition nay truoc khi export.",
            composition=composition,
        )
    if not composition.artifacts.render_log_path:
        return _issue(
            "export.final_render_log_missing",
            "Composition chua co render log de xac minh PNG final.",
            "Render lai final PNG de tao log va hash hien tai.",
            composition=composition,
        )
    if target is None:
        return None

    render_composition = workspace_service.resolve_composition_layer_paths(composition)
    try:
        spec = build_export_final_render_spec(
            render_composition,
            target,
            final_dpi=final_dpi,
        )
    except (RenderSpecError, ValueError) as error:
        return _issue(
            "export.final_render_spec_invalid",
            "Khong tao duoc render spec de xac minh PNG final.",
            f"Kiem tra composition, target va template metadata. Chi tiet: {error}",
            composition=composition,
        )

    currentness = is_final_render_current(
        workspace_root=workspace_service.paths.root,
        output_path=composition.artifacts.final_render_path,
        log_path=composition.artifacts.render_log_path,
        spec=spec,
    )
    if currentness.current:
        return None
    return _issue(
        "export.final_render_stale",
        "PNG final render khong con khop voi composition hien tai.",
        f"Render lai PNG final truoc khi export. Ly do: {currentness.reason}.",
        composition=composition,
    )


def _ensure_composition_final_render(
    workspace_service: WorkspaceService,
    composition: Composition,
    target: TargetConfig | None,
    *,
    render: FinalRenderFunction | None,
    is_cancelled: CancelCallback | None,
    final_dpi: int,
) -> ExportFinalRenderRow:
    if target is None:
        return _row(
            composition,
            ExportFinalRenderStatus.FAILED,
            [
                _issue(
                    "export.target_missing",
                    "Khong tim thay target cua composition.",
                    "Kiem tra config target va workspace composition.",
                    composition=composition,
                )
            ],
        )
    if is_cancelled is not None and is_cancelled():
        return _row(
            composition,
            ExportFinalRenderStatus.SKIPPED,
            [
                _issue(
                    "export.final_render_cancelled",
                    "Da huy tao PNG final cho export.",
                    "Chay lai export preparation khi san sang.",
                    composition=composition,
                )
            ],
        )

    render_composition = workspace_service.resolve_composition_layer_paths(composition)
    try:
        spec = build_export_final_render_spec(
            render_composition,
            target,
            final_dpi=final_dpi,
        )
    except (RenderSpecError, ValueError) as error:
        return _row(
            composition,
            ExportFinalRenderStatus.FAILED,
            [
                _issue(
                    "export.final_render_spec_invalid",
                    "Khong tao duoc render spec cho export.",
                    f"Kiem tra composition, target va template metadata. Chi tiet: {error}",
                    composition=composition,
                )
            ],
        )

    current_issue = final_render_currentness_issue(
        workspace_service=workspace_service,
        composition=composition,
        target=target,
        final_dpi=final_dpi,
    )
    if current_issue is None:
        return _row(
            composition,
            ExportFinalRenderStatus.CURRENT,
            [],
            final_render_path=composition.artifacts.final_render_path,
            render_log_path=composition.artifacts.render_log_path,
            render_spec_hash=render_spec_hash(spec),
        )

    kwargs = {
        "workspace_root": workspace_service.paths.root,
        "is_cancelled": is_cancelled,
    }
    if render is not None:
        kwargs["render"] = render
    result = render_final_png(spec, **kwargs)
    if result.output_path is None:
        return _row(
            composition,
            ExportFinalRenderStatus.FAILED,
            result.issues or [current_issue],
            render_log_path=result.log_path,
            render_spec_hash=result.render_spec_hash,
        )

    try:
        updated = workspace_service.record_final_render_artifacts(
            composition.composition_id,
            final_render_path=result.output_path,
            render_log_path=result.log_path,
        )
    except (WorkspaceError, OSError, ValueError) as error:
        return _row(
            composition,
            ExportFinalRenderStatus.FAILED,
            [
                _issue(
                    "export.final_render_artifact_persist_failed",
                    "Khong ghi duoc duong dan PNG final vao workspace.",
                    f"Kiem tra quyen ghi workspace va thu lai. Chi tiet: {error}",
                    composition=composition,
                )
            ],
            render_log_path=result.log_path,
            render_spec_hash=result.render_spec_hash,
        )

    return _row(
        updated,
        ExportFinalRenderStatus.RENDERED,
        [],
        final_render_path=result.output_path,
        render_log_path=result.log_path,
        render_spec_hash=result.render_spec_hash,
    )


def _template_metadata(target: TargetConfig) -> TemplateMetadata:
    try:
        return TemplateMetadata.model_validate(target.metadata["template_metadata"])
    except (KeyError, ValidationError) as error:
        msg = "target is missing derived template_metadata"
        raise ValueError(msg) from error


def _row(
    composition: Composition,
    status: ExportFinalRenderStatus,
    issues: list[Issue],
    *,
    final_render_path: str | None = None,
    render_log_path: str | None = None,
    render_spec_hash: str | None = None,
) -> ExportFinalRenderRow:
    return ExportFinalRenderRow(
        composition_id=composition.composition_id,
        target_id=composition.target_id,
        review_order=composition.review_order,
        status=status,
        final_render_path=final_render_path,
        render_log_path=render_log_path,
        render_spec_hash=render_spec_hash,
        issues=issues,
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
        scope=IssueScope.RENDER,
        target_id=composition.target_id,
        composition_id=composition.composition_id,
        message=message,
        remediation=remediation,
    )


def _export_sort_key(composition: Composition) -> tuple[int, int, str]:
    return (
        1 if composition.review_order is None else 0,
        composition.review_order or 0,
        composition.composition_id,
    )


def _summary(rows: list[ExportFinalRenderRow]) -> ExportFinalRenderSummary:
    return ExportFinalRenderSummary(
        included_count=len(rows),
        current_count=sum(1 for row in rows if row.status == ExportFinalRenderStatus.CURRENT),
        rendered_count=sum(1 for row in rows if row.status == ExportFinalRenderStatus.RENDERED),
        skipped_count=sum(1 for row in rows if row.status == ExportFinalRenderStatus.SKIPPED),
        error_count=sum(1 for row in rows if row.status == ExportFinalRenderStatus.FAILED),
    )
