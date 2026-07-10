"""Tests for Story 11.2 COG/overview readiness tooling."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

from thucthengay.gis.crs import GEOGRAPHIC_CRS
from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    RasterOverviewReadinessCache,
    RasterReadinessStatus,
    RenderBackground,
    RenderComparisonPane,
    RenderComparisonSpec,
    RenderLayerRef,
    RenderSpec,
    build_raster_preparation_plan,
    inspect_raster_overview_readiness,
    inspect_render_spec_overview_readiness,
    prepare_raster_overview_output,
    raster_file_signature,
)


def _write_geotiff(path: str, *, tiled: bool = True, overviews: bool = False) -> None:
    data = np.zeros((3, 64, 64), dtype=np.uint8)
    data[0, :, :] = 50
    data[1, :, :] = 90
    data[2, :, :] = 130
    profile = {
        "driver": "GTiff",
        "width": 64,
        "height": 64,
        "count": 3,
        "dtype": "uint8",
        "crs": GEOGRAPHIC_CRS,
        "transform": from_bounds(106.0, 10.0, 107.0, 11.0, 64, 64),
    }
    if tiled:
        profile.update(tiled=True, blockxsize=16, blockysize=16)
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(data)
        if overviews:
            dataset.build_overviews([2, 4], Resampling.nearest)


def _spec(path_a: str, path_b: str) -> RenderSpec:
    return RenderSpec(
        composition_id="tgt__20260709",
        target_id="tgt",
        output_width=256,
        output_height=144,
        view_center=[106.5, 10.5],
        view_scale=50000,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=640 / 360,
        geo_window=GeoWindow(min_lon=106.0, min_lat=10.0, max_lon=107.0, max_lat=11.0),
        visible_layers=[
            RenderLayerRef(layer_id="A", source_path=path_a, cache_path=path_a, order=0)
        ],
        grid=GridConfig(interval=GridInterval(minutes=30), label_format="dms_full"),
        background=RenderBackground(color="#112233"),
        temporal_compare=RenderComparisonSpec(
            enabled=True,
            pane_a=RenderComparisonPane(
                layers=[RenderLayerRef(layer_id="A", source_path=path_a, order=0)]
            ),
            pane_b=RenderComparisonPane(
                layers=[RenderLayerRef(layer_id="B", source_path=path_b, order=0)]
            ),
        ),
        template_metadata_file="t.json",
        template_pptx="t.pptx",
        slide_index=0,
    )


def test_overview_readiness_reports_ready_tiled_geotiff_with_overviews(tmp_path) -> None:
    tif_path = tmp_path / "ready.tif"
    _write_geotiff(str(tif_path), tiled=True, overviews=True)

    readiness = inspect_raster_overview_readiness(str(tif_path))

    assert readiness.status == RasterReadinessStatus.READY
    assert readiness.width == 64
    assert readiness.height == 64
    assert readiness.band_count == 3
    assert readiness.crs == GEOGRAPHIC_CRS
    assert readiness.is_tiled
    assert readiness.block_shapes
    assert readiness.overview_levels == (2, 4)
    assert readiness.has_usable_overviews
    assert not readiness.likely_expensive_to_zoom_out


def test_overview_readiness_reports_missing_overviews_with_actionable_notes(tmp_path) -> None:
    tif_path = tmp_path / "missing-overviews.tif"
    _write_geotiff(str(tif_path), tiled=True, overviews=False)

    readiness = inspect_raster_overview_readiness(
        str(tif_path),
        expensive_dimension_threshold=32,
    )

    assert readiness.status == RasterReadinessStatus.NEEDS_OVERVIEWS
    assert readiness.overview_levels == ()
    assert readiness.likely_expensive_to_zoom_out
    assert any("overview" in note.lower() for note in readiness.notes)


def test_overview_readiness_reports_need_cog_for_untiled_geotiff(tmp_path) -> None:
    tif_path = tmp_path / "untiled.tif"
    _write_geotiff(str(tif_path), tiled=False, overviews=True)

    readiness = inspect_raster_overview_readiness(str(tif_path))

    assert readiness.status == RasterReadinessStatus.NEEDS_COG
    assert not readiness.is_tiled
    assert readiness.has_usable_overviews
    assert any("tiled geotiff" in note.lower() or "cog" in note.lower() for note in readiness.notes)


def test_overview_readiness_reports_unreadable_without_raising(tmp_path) -> None:
    bad_path = tmp_path / "not-raster.tif"
    bad_path.write_text("not a raster", encoding="utf-8")

    readiness = inspect_raster_overview_readiness(str(bad_path))

    assert readiness.status == RasterReadinessStatus.UNREADABLE
    assert readiness.width is None
    assert any("cannot be opened" in note.lower() for note in readiness.notes)


def test_overview_readiness_cache_reuses_unchanged_file_metadata(tmp_path, monkeypatch) -> None:
    tif_path = tmp_path / "cached.tif"
    _write_geotiff(str(tif_path), tiled=True, overviews=True)
    cache = RasterOverviewReadinessCache()

    first = inspect_raster_overview_readiness(str(tif_path), cache=cache)

    def fail_open(*_args, **_kwargs):
        raise AssertionError("cache should avoid reopening unchanged raster")

    monkeypatch.setattr(rasterio, "open", fail_open)
    second = inspect_raster_overview_readiness(str(tif_path), cache=cache)

    assert second is first


def test_inspect_render_spec_overview_readiness_deduplicates_visible_and_compare_paths(
    tmp_path,
) -> None:
    path_a = tmp_path / "a.tif"
    path_b = tmp_path / "b.tif"
    _write_geotiff(str(path_a), tiled=True, overviews=True)
    _write_geotiff(str(path_b), tiled=True, overviews=False)

    results = inspect_render_spec_overview_readiness(_spec(str(path_a), str(path_b)))

    assert [result.path for result in results] == [str(path_a), str(path_b)]
    assert results[0].status == RasterReadinessStatus.READY
    assert results[1].status == RasterReadinessStatus.NEEDS_OVERVIEWS


def test_prepare_plan_without_output_is_non_mutating_and_requires_explicit_destination(
    tmp_path,
) -> None:
    tif_path = tmp_path / "source.tif"
    _write_geotiff(str(tif_path), tiled=True, overviews=False)
    before = raster_file_signature(str(tif_path))

    plan = build_raster_preparation_plan(str(tif_path))

    assert plan.output_path is None
    assert not plan.will_mutate_source
    try:
        prepare_raster_overview_output(plan)
    except ValueError as exc:
        assert "output_path" in str(exc)
    else:  # pragma: no cover - defensive assertion shape.
        raise AssertionError("expected explicit output requirement")
    assert raster_file_signature(str(tif_path)) == before
    assert inspect_raster_overview_readiness(str(tif_path)).overview_levels == ()


def test_prepare_raster_overview_output_writes_prepared_copy_without_mutating_source(
    tmp_path,
) -> None:
    source_path = tmp_path / "source.tif"
    output_path = tmp_path / "prepared" / "source.tif"
    _write_geotiff(str(source_path), tiled=False, overviews=False)
    before = raster_file_signature(str(source_path))

    plan = build_raster_preparation_plan(str(source_path), output_path=str(output_path))
    prepared = prepare_raster_overview_output(plan)

    assert prepared.path == str(output_path)
    assert prepared.status == RasterReadinessStatus.READY
    assert prepared.is_tiled
    assert prepared.has_usable_overviews
    assert output_path.exists()
    assert raster_file_signature(str(source_path)) == before
    source_readiness = inspect_raster_overview_readiness(str(source_path))
    assert source_readiness.status == RasterReadinessStatus.NEEDS_COG
    assert source_readiness.overview_levels == ()
