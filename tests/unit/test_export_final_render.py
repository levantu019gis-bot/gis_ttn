from __future__ import annotations

from datetime import date, time
from pathlib import Path

import numpy as np

from thucthengay.export import (
    ExportFinalRenderStatus,
    build_export_preflight_plan,
    ensure_final_renders_for_export,
    final_render_output_size,
)
from thucthengay.models import (
    Composition,
    CompositionArtifacts,
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


def _target(target_id: str = "alpha") -> TargetConfig:
    template = TemplateMetadata(
        template_pptx=f"templates/{target_id}.pptx",
        slide_index=0,
        map_frame=MapFrame(x=0, y=0, width=144, height=72),
        placeholders=[
            TemplatePlaceholder(
                field="map",
                element_id=10,
                kind=PlaceholderType.MAP_IMAGE,
                required=True,
            )
        ],
    )
    return TargetConfig(
        id=target_id,
        name=f"{target_id.title()} Target",
        alias=target_id.upper(),
        geojson_file=f"targets/{target_id}.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export={
            "template_pptx_file": f"templates/{target_id}.pptx",
            "txt_line_template": "{slide_number}|{target_id}|{capture_date}|{time_label}",
            "placeholders": [
                {
                    "field": "map",
                    "element_id": 10,
                    "kind": PlaceholderType.MAP_IMAGE,
                    "required": True,
                }
            ],
        },
        metadata={"template_metadata": template.model_dump(mode="json")},
    )


def _composition(
    composition_id: str = "alpha__20260525",
    *,
    artifacts: CompositionArtifacts | None = None,
    scale: int = 50000,
) -> Composition:
    return Composition(
        composition_id=composition_id,
        target_id="alpha",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=scale),
        reviewed=True,
        ready=True,
        include=True,
        needs_revalidation=False,
        review_order=1,
        artifacts=artifacts or CompositionArtifacts(),
        layers=[
            ImageLayer(
                layer_id="L1",
                source_path="L1.tif",
                cache_path="cache/L1.tif",
                order=0,
                visible=True,
                capture_date=date(2026, 5, 25),
                capture_time=time(8, 30),
                metadata_status=MetadataStatus.VALID,
            )
        ],
    )


def _workspace(tmp_path: Path, composition: Composition) -> WorkspaceService:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(composition)
    return service


def _success_render(spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
    return RasterRenderResult(
        canvas=np.full((spec.output_height, spec.output_width, 3), 21, dtype=np.uint8),
        painted_layer_ids=("L1",),
    )


def test_export_final_render_generates_missing_and_persists_workspace_artifacts(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path, _composition())

    result = ensure_final_renders_for_export(service, [_target()], render=_success_render)

    assert result.summary.ready_count == 1
    assert result.summary.rendered_count == 1
    assert result.summary.error_count == 0
    row = result.rows[0]
    assert row.status == ExportFinalRenderStatus.RENDERED
    assert row.final_render_path is not None
    assert row.render_log_path is not None
    assert (service.paths.root / row.final_render_path).is_file()

    persisted = service.read_composition("alpha__20260525")
    assert persisted.artifacts.final_render_path == row.final_render_path
    assert persisted.artifacts.render_log_path == row.render_log_path


def test_final_render_output_size_prefers_map_placeholder_image_dimensions() -> None:
    template = TemplateMetadata(
        template_pptx="templates/alpha.pptx",
        slide_index=0,
        map_frame=MapFrame(x=0, y=0, width=16.5223, height=11.6946),
        placeholders=[
            TemplatePlaceholder(
                field="map",
                element_id=1026,
                kind=PlaceholderType.MAP_IMAGE,
                required=True,
            )
        ],
        metadata={
            "selected_slide": {
                "shapes": [
                    {
                        "id": "1026",
                        "picture": {
                            "media": {
                                "image": {
                                    "width_px": 3306,
                                    "height_px": 2340,
                                }
                            }
                        },
                    }
                ]
            }
        },
    )

    assert final_render_output_size(template) == (3306, 2340)


def test_export_final_render_resolves_workspace_relative_layer_paths(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path, _composition())
    captured_cache_paths: list[str | None] = []

    def capture_render(spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
        captured_cache_paths.extend(layer.cache_path for layer in spec.visible_layers)
        return _success_render(spec, is_cancelled=is_cancelled)

    result = ensure_final_renders_for_export(service, [_target()], render=capture_render)

    assert result.summary.rendered_count == 1
    assert captured_cache_paths == [str((service.paths.root / "cache/L1.tif").resolve())]


def test_export_final_render_skips_current_render_without_calling_renderer(
    tmp_path: Path,
) -> None:
    target = _target()
    service = _workspace(tmp_path, _composition())
    first = ensure_final_renders_for_export(service, [target], render=_success_render)
    persisted = service.read_composition("alpha__20260525")
    assert first.rows[0].status == ExportFinalRenderStatus.RENDERED

    def unexpected_render(spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
        raise AssertionError("renderer should not be called for a current final PNG")

    second = ensure_final_renders_for_export(service, [target], render=unexpected_render)

    assert second.summary.current_count == 1
    assert second.rows[0].status == ExportFinalRenderStatus.CURRENT
    assert second.rows[0].final_render_path == persisted.artifacts.final_render_path


def test_export_final_render_regenerates_stale_render_and_preflight_blocks_it_beforehand(
    tmp_path: Path,
) -> None:
    target = _target()
    service = _workspace(tmp_path, _composition())
    ensure_final_renders_for_export(service, [target], render=_success_render)
    stale = service.read_composition("alpha__20260525").model_copy(
        update={"view": ViewState(center=[106.7, 10.8], scale=25000)}
    )
    service.write_composition(stale)

    plan = build_export_preflight_plan(service, [target])
    assert "export.final_render_stale" in {issue.issue_id for issue in plan.issues}

    regenerated = ensure_final_renders_for_export(service, [target], render=_success_render)

    assert regenerated.summary.rendered_count == 1
    assert regenerated.rows[0].status == ExportFinalRenderStatus.RENDERED
    assert regenerated.rows[0].final_render_path != stale.artifacts.final_render_path


def test_export_final_render_failure_returns_issue_without_success_artifact(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path, _composition())
    issue = Issue(
        issue_id="render.synthetic_failure",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        composition_id="alpha__20260525",
        message="Khong tao duoc PNG final.",
        remediation="Kiem tra du lieu raster roi render lai.",
    )

    def fail_render(spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
        raise RenderError([issue])

    result = ensure_final_renders_for_export(service, [_target()], render=fail_render)

    assert result.summary.error_count == 1
    assert result.rows[0].status == ExportFinalRenderStatus.FAILED
    assert result.rows[0].final_render_path is None
    assert "render.synthetic_failure" in {item.issue_id for item in result.issues}
    assert service.read_composition("alpha__20260525").artifacts.final_render_path is None


def test_export_preflight_accepts_current_final_render(tmp_path: Path) -> None:
    target = _target()
    service = _workspace(tmp_path, _composition())
    result = ensure_final_renders_for_export(service, [target], render=_success_render)
    assert result.summary.ready_count == 1

    plan = build_export_preflight_plan(service, [target])

    assert plan.summary.error_count == 0
    assert plan.rows[0].final_render_path == result.rows[0].final_render_path


def test_export_preflight_rejects_unreadable_final_render_log(tmp_path: Path) -> None:
    target = _target()
    service = _workspace(tmp_path, _composition())
    result = ensure_final_renders_for_export(service, [target], render=_success_render)
    (service.paths.root / result.rows[0].render_log_path).write_text("{bad json", encoding="utf-8")

    plan = build_export_preflight_plan(service, [target])

    assert "export.final_render_stale" in {issue.issue_id for issue in plan.issues}
