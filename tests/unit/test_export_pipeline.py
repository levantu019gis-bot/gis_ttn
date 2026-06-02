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
    MapFrame,
    MetadataStatus,
    PlaceholderType,
    TargetConfig,
    TemplateMetadata,
    TemplatePlaceholder,
    ViewState,
)
from thucthengay.render import RasterRenderResult, RenderSpec
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


def _composition() -> Composition:
    return Composition(
        composition_id="alpha__20260525",
        target_id="alpha",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
        reviewed=True,
        ready=True,
        include=True,
        needs_revalidation=False,
        review_order=1,
        layers=[
            ImageLayer(
                layer_id="alpha-layer",
                source_path="alpha.tif",
                order=0,
                visible=True,
                capture_date=date(2026, 5, 25),
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
