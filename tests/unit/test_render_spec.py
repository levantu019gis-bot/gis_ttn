"""Tests for Story 5.1: shared render specification builder."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from pyproj import Geod

from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    TargetConfig,
    TargetExportConfig,
    TemplateMetadata,
    TemporalCompareOrientation,
    TemporalCompareState,
    ViewState,
)
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    RenderSpec,
    RenderSpecError,
    build_render_spec,
)
from thucthengay.render.spec import (
    INCH_TO_METER,
    MAX_RENDER_PIXELS,
    POINT_TO_INCH,
)


def _target(
    target_id: str = "tgt",
    *,
    grid: GridConfig | None = None,
    map_background_color: str = "#FFFFFF",
) -> TargetConfig:
    return TargetConfig(
        id=target_id,
        sort_order=1,
        name=f"{target_id} Target",
        geojson_file=f"{target_id}.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=grid or GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(
            template_metadata_file=f"{target_id}.template.json",
            map_background_color=map_background_color,
        ),
    )


def _template() -> TemplateMetadata:
    return TemplateMetadata(
        template_pptx="tgt.pptx",
        slide_index=0,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
    )


def _layer(layer_id: str, *, order: int = 0, visible: bool = True) -> ImageLayer:
    return ImageLayer(
        layer_id=layer_id,
        source_path=f"{layer_id}.tif",
        cache_path=f"cache/{layer_id}.tif",
        order=order,
        visible=visible,
    )


def _composition(
    target_id: str = "tgt",
    *,
    layers: list[ImageLayer] | None = None,
    grid_override: GridConfig | None = None,
    scale: int = 50000,
) -> Composition:
    return Composition(
        composition_id=f"{target_id}__20260525",
        target_id=target_id,
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=scale),
        layers=layers or [_layer("L1", order=0), _layer("L2", order=1)],
        grid_override=grid_override,
    )


class TestBuildRenderSpecHappyPath:
    def test_returns_render_spec_with_expected_fields(self) -> None:
        spec = build_render_spec(
            composition=_composition(),
            target=_target(),
            template=_template(),
            template_metadata_file="targets/tgt.template.json",
            output_width=1280,
            output_height=720,
        )

        assert isinstance(spec, RenderSpec)
        assert spec.composition_id == "tgt__20260525"
        assert spec.target_id == "tgt"
        assert spec.output_width == 1280
        assert spec.output_height == 720
        assert spec.view_center == [106.7, 10.8]
        assert spec.view_scale == 50000
        assert spec.template_metadata_file == "targets/tgt.template.json"
        assert spec.template_pptx == "tgt.pptx"
        assert spec.slide_index == 0
        assert spec.background.color == "#FFFFFF"

    def test_uses_target_export_map_background_color(self) -> None:
        spec = build_render_spec(
            composition=_composition(),
            target=_target(map_background_color="#112233"),
            template=_template(),
            template_metadata_file="targets/tgt.template.json",
            output_width=1280,
            output_height=720,
        )

        assert spec.background.color == "#112233"

    def test_map_frame_aspect_matches_template(self) -> None:
        spec = build_render_spec(
            composition=_composition(),
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )
        assert spec.map_frame_aspect == pytest.approx(640 / 360)

    def test_geo_window_math(self) -> None:
        spec = build_render_spec(
            composition=_composition(),
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )

        # Reproduce the documented geodesic span calculation
        paper_w_m = 640 * POINT_TO_INCH * INCH_TO_METER
        paper_h_m = 360 * POINT_TO_INCH * INCH_TO_METER
        ground_w_m = paper_w_m * 50000
        ground_h_m = paper_h_m * 50000
        geod = Geod(ellps="WGS84")
        west_lon, _, _ = geod.fwd(106.7, 10.8, 270.0, ground_w_m / 2.0)
        east_lon, _, _ = geod.fwd(106.7, 10.8, 90.0, ground_w_m / 2.0)
        _, south_lat, _ = geod.fwd(106.7, 10.8, 180.0, ground_h_m / 2.0)
        _, north_lat, _ = geod.fwd(106.7, 10.8, 0.0, ground_h_m / 2.0)

        assert spec.geo_window.min_lon == pytest.approx(min(west_lon, east_lon))
        assert spec.geo_window.max_lon == pytest.approx(max(west_lon, east_lon))
        assert spec.geo_window.min_lat == pytest.approx(south_lat)
        assert spec.geo_window.max_lat == pytest.approx(north_lat)
        assert isinstance(spec.geo_window, GeoWindow)


class TestLayerOrdering:
    def test_hidden_layers_excluded(self) -> None:
        comp = _composition(
            layers=[
                _layer("L1", order=0, visible=True),
                _layer("HIDDEN", order=1, visible=False),
                _layer("L2", order=2, visible=True),
            ]
        )
        spec = build_render_spec(
            composition=comp,
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )
        ids = [ref.layer_id for ref in spec.visible_layers]
        assert ids == ["L1", "L2"]

    def test_visible_layers_preserve_persisted_order(self) -> None:
        # Insert layers out of physical list order; sort by `order` field
        comp = _composition(
            layers=[
                _layer("C", order=2),
                _layer("A", order=0),
                _layer("B", order=1),
            ]
        )
        spec = build_render_spec(
            composition=comp,
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )
        assert [ref.layer_id for ref in spec.visible_layers] == ["A", "B", "C"]
        assert [ref.order for ref in spec.visible_layers] == [0, 1, 2]

    def test_empty_visible_layers_allowed(self) -> None:
        comp = _composition(
            layers=[_layer("HIDDEN", order=0, visible=False)],
        )
        spec = build_render_spec(
            composition=comp,
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )
        assert spec.visible_layers == []

    def test_disabled_temporal_compare_preserves_legacy_visible_layers(self) -> None:
        spec = build_render_spec(
            composition=_composition(layers=[_layer("A", order=0), _layer("B", order=1)]),
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )

        assert spec.temporal_compare.enabled is False
        assert [ref.layer_id for ref in spec.visible_layers] == ["A", "B"]

    def test_enabled_temporal_compare_builds_pane_refs_from_selected_layers(self) -> None:
        comp = _composition(layers=[_layer("current", order=0), _layer("history", order=1)])
        comp = comp.model_copy(
            update={
                "temporal_compare": TemporalCompareState(
                    enabled=True,
                    orientation=TemporalCompareOrientation.HORIZONTAL,
                    pane_a_layer_id="current",
                    pane_b_layer_id="history",
                )
            }
        )

        spec = build_render_spec(
            composition=comp,
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )

        assert spec.temporal_compare.enabled is True
        assert spec.temporal_compare.orientation == TemporalCompareOrientation.HORIZONTAL
        assert spec.temporal_compare.pane_a.layer_id == "current"
        assert spec.temporal_compare.pane_b.layer_id == "history"
        assert [ref.layer_id for ref in spec.visible_layers] == ["current", "history"]

    def test_enabled_temporal_compare_builds_panes_from_selected_compositions(self) -> None:
        pane_a = _composition(
            layers=[_layer("A1", order=0), _layer("A2", order=1)],
        )
        pane_b = _composition(
            layers=[_layer("B1", order=0), _layer("B2", order=1, visible=False)],
        ).model_copy(
            update={
                "composition_id": "tgt__20260526",
                "capture_date": date(2026, 5, 26),
                "view": ViewState(center=[106.9, 10.9], scale=25000),
            }
        )
        comp = pane_a.model_copy(
            update={
                "temporal_compare": TemporalCompareState(
                    enabled=True,
                    orientation=TemporalCompareOrientation.VERTICAL,
                    pane_a_composition_id="tgt__20260525",
                    pane_b_composition_id="tgt__20260526",
                )
            }
        )

        spec = build_render_spec(
            composition=comp,
            target=_target(),
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
            compare_compositions=[pane_a, pane_b],
        )

        assert spec.temporal_compare.enabled is True
        assert spec.temporal_compare.pane_a.composition_id == "tgt__20260525"
        assert spec.temporal_compare.pane_b.composition_id == "tgt__20260526"
        assert spec.temporal_compare.pane_a.view_center == [106.7, 10.8]
        assert spec.temporal_compare.pane_b.view_center == [106.9, 10.9]
        assert spec.temporal_compare.pane_a.view_scale == 50000
        assert spec.temporal_compare.pane_b.view_scale == 25000
        assert spec.temporal_compare.pane_a.geo_window is not None
        assert spec.temporal_compare.pane_b.geo_window is not None
        assert spec.temporal_compare.pane_a.geo_window != spec.temporal_compare.pane_b.geo_window
        assert [ref.layer_id for ref in spec.temporal_compare.pane_a.layers] == ["A1", "A2"]
        assert [ref.layer_id for ref in spec.temporal_compare.pane_b.layers] == ["B1"]
        assert [ref.layer_id for ref in spec.visible_layers] == ["A1", "A2", "B1"]


class TestGridOverride:
    def test_grid_override_used_when_present(self) -> None:
        override = GridConfig(interval=GridInterval(seconds=30), label_format="dms_short")
        target = _target()
        original_target_grid = target.grid
        spec = build_render_spec(
            composition=_composition(grid_override=override),
            target=target,
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )
        assert spec.grid == override
        # Target default unchanged
        assert target.grid == original_target_grid

    def test_target_grid_used_when_no_override(self) -> None:
        target = _target()
        spec = build_render_spec(
            composition=_composition(grid_override=None),
            target=target,
            template=_template(),
            template_metadata_file="t.json",
            output_width=1280,
            output_height=720,
        )
        assert spec.grid == target.grid


class TestInvalidInputs:
    def test_target_id_mismatch_raises_with_vietnamese_remediation(self) -> None:
        with pytest.raises(RenderSpecError) as exc:
            build_render_spec(
                composition=_composition(target_id="A"),
                target=_target(target_id="B"),
                template=_template(),
                template_metadata_file="t.json",
                output_width=1280,
                output_height=720,
            )
        assert len(exc.value.issues) >= 1
        issue = exc.value.issues[0]
        assert issue.issue_id == "render.spec.target_mismatch"
        assert issue.blocking is True
        assert "không khớp" in issue.message.lower() or "không trùng" in (issue.remediation or "")

    def test_output_width_zero_raises(self) -> None:
        with pytest.raises(RenderSpecError) as exc:
            build_render_spec(
                composition=_composition(),
                target=_target(),
                template=_template(),
                template_metadata_file="t.json",
                output_width=0,
                output_height=720,
            )
        ids = [issue.issue_id for issue in exc.value.issues]
        assert "render.spec.output_size_invalid" in ids

    def test_negative_output_height_raises(self) -> None:
        with pytest.raises(RenderSpecError):
            build_render_spec(
                composition=_composition(),
                target=_target(),
                template=_template(),
                template_metadata_file="t.json",
                output_width=1280,
                output_height=-1,
            )

    def test_multiple_issues_collected(self) -> None:
        with pytest.raises(RenderSpecError) as exc:
            build_render_spec(
                composition=_composition(target_id="A"),
                target=_target(target_id="B"),
                template=_template(),
                template_metadata_file="t.json",
                output_width=0,
                output_height=0,
            )
        ids = {issue.issue_id for issue in exc.value.issues}
        assert "render.spec.target_mismatch" in ids
        assert "render.spec.output_size_invalid" in ids

    def test_output_size_too_large_raises_structured_issue(self) -> None:
        with pytest.raises(RenderSpecError) as exc:
            build_render_spec(
                composition=_composition(),
                target=_target(),
                template=_template(),
                template_metadata_file="t.json",
                output_width=MAX_RENDER_PIXELS + 1,
                output_height=1,
            )
        assert exc.value.issues[0].issue_id == "render.spec.output_size_too_large"

    def test_geo_window_crossing_antimeridian_raises_structured_issue(self) -> None:
        comp = Composition(
            composition_id="tgt__20260525",
            target_id="tgt",
            capture_date=date(2026, 5, 25),
            view=ViewState(center=[179.99, 0.0], scale=50000),
            layers=[_layer("L1", order=0)],
        )
        wide_template = TemplateMetadata(
            template_pptx="tgt.pptx",
            slide_index=0,
            map_frame=MapFrame(x=0, y=0, width=2000, height=360),
        )

        with pytest.raises(RenderSpecError) as exc:
            build_render_spec(
                composition=comp,
                target=_target(),
                template=wide_template,
                template_metadata_file="t.json",
                output_width=1280,
                output_height=720,
            )

        assert exc.value.issues[0].issue_id == "render.spec.geo_window_invalid"


class TestImportBoundary:
    def test_render_module_does_not_import_pyside6(self) -> None:
        # Run in a clean subprocess so other tests' Qt imports don't taint sys.modules.
        code = (
            "import sys; import thucthengay.render; "
            "leaked = [n for n in sys.modules if n.startswith('PySide6')]; "
            "assert not leaked, f'render leaked PySide6 imports: {leaked}'"
        )
        src_path = Path(__file__).resolve().parents[2] / "src"
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{src_path}{os.pathsep}{existing}" if existing else str(src_path)
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert result.returncode == 0, result.stderr
