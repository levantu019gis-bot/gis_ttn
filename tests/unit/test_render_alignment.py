"""Story 5.6 fixture-based preview/final render alignment tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_bounds

from thucthengay.gis.crs import GEOGRAPHIC_CRS
from thucthengay.ingestion.cache_builder import CachePopulationResult
from thucthengay.ingestion.composition_builder import create_target_date_compositions
from thucthengay.jobs import (
    PreviewRenderController,
    PreviewRenderQuality,
    run_preview_render_job,
)
from thucthengay.models import (
    Composition,
    FinalRenderStatus,
    GridConfig,
    GridInterval,
    ImageLayer,
    MetadataStatus,
    ProjectConfig,
    TargetConfig,
    TargetExportConfig,
    TemplateMetadata,
    ViewState,
)
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    RenderBackground,
    RenderSpec,
    build_render_spec,
    render_final_png,
    render_map,
)
from thucthengay.workspace import WorkspaceService


@dataclass(frozen=True)
class AlignmentFixture:
    root: Path
    composition: Composition
    target_id: str
    template: TemplateMetadata
    template_metadata_file: str
    spec: RenderSpec


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_geotiff(
    path: Path,
    *,
    bounds: tuple[float, float, float, float],
    rgb: tuple[int, int, int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros((3, 24, 24), dtype=np.uint8)
    data[0, :, :] = rgb[0]
    data[1, :, :] = rgb[1]
    data[2, :, :] = rgb[2]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=24,
        height=24,
        count=3,
        dtype="uint8",
        crs=GEOGRAPHIC_CRS,
        transform=from_bounds(*bounds, 24, 24),
    ) as ds:
        ds.write(data)


def _sample(canvas: np.ndarray, x_frac: float, y_frac: float) -> tuple[int, int, int]:
    row = min(canvas.shape[0] - 1, max(0, int(round(y_frac * (canvas.shape[0] - 1)))))
    col = min(canvas.shape[1] - 1, max(0, int(round(x_frac * (canvas.shape[1] - 1)))))
    return tuple(int(value) for value in canvas[row, col])


def _close_rgb(
    actual: tuple[int, int, int],
    expected: tuple[int, int, int],
    *,
    tolerance: int = 2,
) -> bool:
    return all(abs(channel - reference) <= tolerance for channel, reference in zip(actual, expected))


@pytest.fixture
def alignment_fixture(tmp_path: Path) -> AlignmentFixture:
    root = tmp_path / "fixture"
    geojson_path = root / "targets" / "target_001.geojson"
    template_metadata_path = root / "templates" / "target_001.template.json"
    composition_path = root / "workspace" / "compositions" / "target_001__20260525.json"

    _write_json(
        geojson_path,
        {
            "type": "Feature",
            "properties": {"id": 1, "name": "target_001", "alias": "Target 001"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [106.0, 10.0],
                        [107.0, 10.0],
                        [107.0, 11.0],
                        [106.0, 11.0],
                        [106.0, 10.0],
                    ]
                ],
            },
        },
    )
    template = TemplateMetadata(
        template_pptx="templates/target_001.template.pptx",
        slide_index=0,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
    )
    template_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    template_metadata_path.write_text(template.model_dump_json(indent=2), encoding="utf-8")

    config = ProjectConfig(
        targets=[
            {
                "id": "target_001",
                "sort_order": 1,
                "name": "Target 001",
                "geojson_file": str(geojson_path),
                "coordinate": [106.5, 10.5],
                "scale": 50000,
                "grid": GridConfig(
                    interval=GridInterval(minutes=20),
                    label_format="dms_full",
                    style={"frame_color": "#000000", "label_font_size": 10},
                ),
                "export": TargetExportConfig(
                    template_metadata_file=str(template_metadata_path)
                ),
            }
        ]
    )
    _write_json(root / "config.json", config.model_dump(mode="json"))

    pre_raster_composition = Composition(
        composition_id="target_001__20260525",
        target_id="target_001",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.5, 10.5], scale=50000),
        layers=[],
        grid_override=None,
    )
    target = ProjectConfig.model_validate_json(
        (root / "config.json").read_text(encoding="utf-8")
    ).targets[0]
    spec_for_bounds = build_render_spec(
        composition=pre_raster_composition,
        target=target,
        template=TemplateMetadata.model_validate_json(
            template_metadata_path.read_text(encoding="utf-8")
        ),
        template_metadata_file=str(template_metadata_path),
        output_width=80,
        output_height=45,
    )
    window = spec_for_bounds.geo_window
    mid_lon = (window.min_lon + window.max_lon) / 2
    west_bounds = (window.min_lon, window.min_lat, mid_lon, window.max_lat)
    full_bounds = (window.min_lon, window.min_lat, window.max_lon, window.max_lat)

    old_path = root / "rasters" / "old.tif"
    new_path = root / "rasters" / "new.tif"
    hidden_path = root / "rasters" / "hidden.tif"
    _write_geotiff(old_path, bounds=west_bounds, rgb=(180, 20, 20))
    _write_geotiff(new_path, bounds=west_bounds, rgb=(20, 30, 220))
    _write_geotiff(hidden_path, bounds=full_bounds, rgb=(0, 220, 0))

    composition = pre_raster_composition.model_copy(
        update={
            "layers": [
                ImageLayer(layer_id="old", source_path=str(old_path), order=0, visible=True),
                ImageLayer(layer_id="hidden", source_path=str(hidden_path), order=1, visible=False),
                ImageLayer(layer_id="new", source_path=str(new_path), order=2, visible=True),
            ]
        }
    )
    composition_path.parent.mkdir(parents=True, exist_ok=True)
    composition_path.write_text(composition.model_dump_json(indent=2), encoding="utf-8")
    loaded_composition = Composition.model_validate_json(
        composition_path.read_text(encoding="utf-8")
    )
    spec = build_render_spec(
        composition=loaded_composition,
        target=target,
        template=template,
        template_metadata_file=str(template_metadata_path),
        output_width=80,
        output_height=45,
    ).model_copy(update={"background": RenderBackground(color="#112233")})

    return AlignmentFixture(
        root=root,
        composition=loaded_composition,
        target_id=target.id,
        template=template,
        template_metadata_file=str(template_metadata_path),
        spec=spec,
    )


def test_preview_and_final_outputs_align_on_fixture_data(
    alignment_fixture: AlignmentFixture,
) -> None:
    spec = alignment_fixture.spec
    controller = PreviewRenderController(
        debounce_ms=0,
        interactive_max_width=40,
        settled_max_width=80,
    )
    plan = controller.request_preview(spec)

    preview_result = run_preview_render_job(plan.interactive)
    final_result = render_final_png(spec, workspace_root=alignment_fixture.root)

    assert preview_result.quality == PreviewRenderQuality.INTERACTIVE_LOW_RES
    assert preview_result.canvas is not None
    assert preview_result.output_width == 40
    assert preview_result.output_height == 22
    assert final_result.status == FinalRenderStatus.SUCCESS
    assert final_result.output_path is not None

    with Image.open(alignment_fixture.root / final_result.output_path) as image:
        final_canvas = np.asarray(image)

    # Normalized samples make the expected preview/final resolution difference explicit.
    assert _close_rgb(
        _sample(final_canvas, 0.25, 0.50),
        _sample(preview_result.canvas, 0.25, 0.50),
    )
    assert _close_rgb(_sample(final_canvas, 0.25, 0.50), (20, 30, 220))
    assert _close_rgb(
        _sample(final_canvas, 0.75, 0.50),
        _sample(preview_result.canvas, 0.75, 0.50),
    )
    assert _close_rgb(_sample(final_canvas, 0.75, 0.50), (17, 34, 51))

    top_mid_preview = _sample(preview_result.canvas, 0.50, 0.0)
    top_mid_final = _sample(final_canvas, 0.50, 0.0)
    assert _close_rgb(top_mid_final, top_mid_preview)
    assert top_mid_final != (17, 34, 51)


def test_fixture_layer_visibility_and_order_affect_render_output(
    alignment_fixture: AlignmentFixture,
) -> None:
    spec = alignment_fixture.spec

    assert [layer.layer_id for layer in spec.visible_layers] == ["old", "new"]
    result = render_map(spec)

    assert result.painted_layer_ids == ("old", "new")
    assert _sample(result.canvas, 0.25, 0.50) == (20, 30, 220)
    assert not np.any(np.all(result.canvas == np.array([0, 220, 0], dtype=np.uint8), axis=2))

    reversed_spec = spec.model_copy(
        update={"visible_layers": list(reversed(spec.visible_layers))}
    )
    reversed_result = render_map(reversed_spec)
    assert reversed_result.painted_layer_ids == ("new", "old")
    assert _sample(reversed_result.canvas, 0.25, 0.50) == (180, 20, 20)


def test_ingestion_default_orders_newest_valid_layer_first(tmp_path: Path) -> None:
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")
    target = TargetConfig(
        id="target_001",
        sort_order=1,
        name="Target 001",
        geojson_file="target_001.geojson",
        coordinate=[106.5, 10.5],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=20)),
        export=TargetExportConfig(template_metadata_file="target_001.template.json"),
    )
    day = date(2026, 5, 25)
    result = CachePopulationResult(
        layers_by_target_date={
            ("target_001", "20260525"): [
                ImageLayer(
                    layer_id="old",
                    source_path="old.tif",
                    order=99,
                    capture_date=day,
                    capture_time=time(8, 0),
                ),
                ImageLayer(
                    layer_id="missing_time",
                    source_path="missing_time.tif",
                    order=99,
                    capture_date=day,
                    capture_time=None,
                ),
                ImageLayer(
                    layer_id="new",
                    source_path="new.tif",
                    order=99,
                    capture_date=day,
                    capture_time=time(14, 0),
                ),
            ]
        },
        issues=[],
    )

    create_target_date_compositions(result, {"target_001": target}, workspace)
    composition = workspace.read_composition("target_001__20260525")

    assert [layer.layer_id for layer in composition.layers] == ["new", "old", "missing_time"]
    assert [layer.order for layer in composition.layers] == [0, 1, 2]
    assert composition.layers[-1].metadata_status == MetadataStatus.NEEDS_MANUAL_CORRECTION


def test_invalid_fixture_final_render_returns_issue_without_partial_image(
    alignment_fixture: AlignmentFixture,
) -> None:
    missing_layer_spec = alignment_fixture.spec.model_copy(
        update={
            "visible_layers": [
                alignment_fixture.spec.visible_layers[0].model_copy(
                    update={"source_path": "missing.tif", "cache_path": "missing.tif"}
                )
            ]
        }
    )

    result = render_final_png(missing_layer_spec, workspace_root=alignment_fixture.root)

    assert result.status == FinalRenderStatus.FAILURE
    assert result.output_path is None
    assert [issue.issue_id for issue in result.issues] == ["render.raster.unreadable"]
    assert list((alignment_fixture.root / "renders").glob("*.jpg")) == []
