from __future__ import annotations

from datetime import date, time
from pathlib import Path

import numpy as np
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches

from thucthengay.export import run_full_export
from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    MapFrame,
    MetadataStatus,
    PlaceholderType,
    TargetConfig,
    TemplateMetadata,
    TemplatePlaceholder,
    ViewState,
)
from thucthengay.render import RasterRenderResult, RenderError, RenderSpec
from thucthengay.workspace import WorkspaceService


def test_run_full_export_renders_final_images_and_writes_outputs(tmp_path: Path) -> None:
    map_id = _write_template(tmp_path / "templates" / "alpha.pptx")
    target = _target(tmp_path / "templates" / "alpha.pptx", map_id)
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(_composition())

    result = run_full_export(
        service,
        [target],
        output_stem="report",
        render=_success_render,
    )

    updated = service.read_composition("alpha__20260525")
    assert result.ok is True
    assert updated.artifacts.final_render_path is not None
    assert updated.artifacts.final_render_path.endswith(".jpg")
    assert (service.paths.root / updated.artifacts.final_render_path).is_file()
    assert (service.paths.exports / "report.pptx").is_file()
    assert (service.paths.exports / "report.txt").read_text("utf-8").strip() == (
        "1|alpha|2026-05-25|08:30:00"
    )
    assert (service.paths.exports / "report.export-log.json").is_file()
    assert result.preflight_plan.summary.error_count == 0


def test_run_full_export_sanitizes_output_stem_for_windows(tmp_path: Path) -> None:
    map_id = _write_template(tmp_path / "templates" / "alpha.pptx")
    target = _target(tmp_path / "templates" / "alpha.pptx", map_id)
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(_composition())

    result = run_full_export(
        service,
        [target],
        output_stem='daily:report*bad',
        render=_success_render,
    )

    assert result.ok is True
    assert (service.paths.exports / "daily_report_bad.pptx").is_file()
    assert (service.paths.exports / "daily_report_bad.txt").is_file()


def test_run_full_export_carries_template_issues_into_preflight_and_pptx_result(
    tmp_path: Path,
) -> None:
    map_id = _write_template(tmp_path / "templates" / "alpha.pptx")
    target = _target(tmp_path / "templates" / "alpha.pptx", map_id)
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(_composition())
    warning = Issue(
        issue_id="target.template_compatibility_unknown",
        severity=IssueSeverity.WARNING,
        scope=IssueScope.TEMPLATE,
        message="Nhieu PPTX template co base/theme/master khac nhau.",
        remediation="Kiem tra base/theme/master truoc khi export.",
    )

    result = run_full_export(
        service,
        [target],
        output_stem="report",
        render=_success_render,
        template_issues=[warning],
    )

    assert result.ok is True
    assert "target.template_compatibility_unknown" in {
        issue.issue_id for issue in result.preflight_plan.issues
    }
    assert "target.template_compatibility_unknown" in {
        issue.issue_id for issue in result.pptx_result.issues
    }


def test_run_full_export_skips_failed_final_render_without_cascading(
    tmp_path: Path,
) -> None:
    map_id = _write_template(tmp_path / "templates" / "alpha.pptx")
    target = _target(tmp_path / "templates" / "alpha.pptx", map_id)
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(_composition())
    service.write_composition(
        _composition(
            composition_id="alpha__20260526",
            capture_date=date(2026, 5, 26),
            review_order=2,
        )
    )

    result = run_full_export(
        service,
        [target],
        output_stem="partial",
        render=_render_with_no_overlap_failure,
    )

    assert result.ok is True
    assert result.pptx_result.ok is True
    assert result.txt_result.ok is True
    assert [row.composition_id for row in result.pptx_result.exported] == ["alpha__20260525"]
    assert [row.composition_id for row in result.txt_result.exported] == ["alpha__20260525"]
    assert (service.paths.exports / "partial.pptx").is_file()
    assert (service.paths.exports / "partial.txt").read_text("utf-8").strip() == (
        "1|alpha|2026-05-25|08:30:00"
    )
    assert result.log_result is not None
    assert result.log_result.summary.skipped_count == 1
    assert result.log_result.log is not None
    skipped = result.log_result.log.skipped[0]
    assert skipped.composition_id == "alpha__20260526"
    assert "Khong co layer visible" in skipped.reason
    issue_ids = {issue.issue_id for issue in result.log_result.log.issues}
    assert "render.raster.no_overlap" in issue_ids
    assert "export.output_row_missing" not in issue_ids


def _write_template(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    presentation = Presentation()
    presentation.slide_width = Inches(10)
    presentation.slide_height = Inches(5.625)
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    map_shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.5),
        Inches(0.75),
        Inches(4),
        Inches(3),
    )
    presentation.save(path)
    return int(map_shape.shape_id)


def _target(template_path: Path, map_id: int) -> TargetConfig:
    placeholder = TemplatePlaceholder(
        field="map",
        element_id=map_id,
        kind=PlaceholderType.MAP_IMAGE,
        required=True,
    )
    return TargetConfig(
        id="alpha",
        name="Alpha Target",
        geojson_file="targets/alpha.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export={
            "template_pptx_file": str(template_path),
            "txt_line_template": "{slide_number}|{target_id}|{capture_date}|{time_label}",
            "placeholders": [placeholder.model_dump(mode="json")],
        },
        metadata={
            "template_metadata": TemplateMetadata(
                template_pptx=str(template_path),
                slide_index=0,
                map_frame=MapFrame(x=36, y=54, width=288, height=216),
                placeholders=[placeholder],
            ).model_dump(mode="json")
        },
    )


def _composition(
    *,
    composition_id: str = "alpha__20260525",
    capture_date: date = date(2026, 5, 25),
    review_order: int = 1,
) -> Composition:
    return Composition(
        composition_id=composition_id,
        target_id="alpha",
        capture_date=capture_date,
        view=ViewState(center=[106.7, 10.8], scale=50000),
        reviewed=True,
        ready=True,
        include=True,
        needs_revalidation=False,
        review_order=review_order,
        layers=[
            ImageLayer(
                layer_id=f"{composition_id}-layer",
                source_path="alpha.tif",
                order=0,
                visible=True,
                capture_date=capture_date,
                capture_time=time(8, 30),
                metadata_status=MetadataStatus.VALID,
            )
        ],
    )


def _success_render(spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
    return RasterRenderResult(
        canvas=np.full((spec.output_height, spec.output_width, 3), 128, dtype=np.uint8),
        painted_layer_ids=tuple(layer.layer_id for layer in spec.visible_layers),
    )


def _render_with_no_overlap_failure(
    spec: RenderSpec,
    is_cancelled=None,  # noqa: ANN001
) -> RasterRenderResult:
    if spec.composition_id == "alpha__20260526":
        raise RenderError(
            [
                Issue(
                    issue_id="render.raster.no_overlap",
                    severity=IssueSeverity.ERROR,
                    scope=IssueScope.RENDER,
                    target_id=spec.target_id,
                    composition_id=spec.composition_id,
                    message="Khong co layer visible nao phu vung ban do can render.",
                    remediation="Kiem tra lai tam ban do, scale hoac du lieu raster.",
                )
            ]
        )
    return _success_render(spec, is_cancelled=is_cancelled)
