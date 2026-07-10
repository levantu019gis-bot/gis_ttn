"""Tests for Story 11.1 render diagnostics instrumentation."""

from __future__ import annotations

import numpy as np
import rasterio
from PySide6.QtWidgets import QApplication
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

from thucthengay.editor.widgets.gis_canvas import _image_to_pixmap, _numpy_to_image
from thucthengay.gis.crs import GEOGRAPHIC_CRS
from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    MapRenderCache,
    RenderBackground,
    RenderDiagnostics,
    RenderLayerRef,
    RenderSpec,
    render_map,
    render_map_with_cache,
)


def _spec(path: str) -> RenderSpec:
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
            RenderLayerRef(layer_id="L1", source_path=path, cache_path=path, order=0)
        ],
        grid=GridConfig(interval=GridInterval(minutes=30), label_format="dms_full"),
        background=RenderBackground(color="#112233"),
        template_metadata_file="t.json",
        template_pptx="t.pptx",
        slide_index=0,
    )


def _write_geotiff(path: str, *, overviews: bool = True) -> None:
    data = np.zeros((3, 64, 64), dtype=np.uint8)
    data[0, :, :] = 80
    data[1, :, :] = 120
    data[2, :, :] = 160
    profile = {
        "driver": "GTiff",
        "width": 64,
        "height": 64,
        "count": 3,
        "dtype": "uint8",
        "crs": GEOGRAPHIC_CRS,
        "transform": from_bounds(106.0, 10.0, 107.0, 11.0, 64, 64),
        "tiled": True,
        "blockxsize": 16,
        "blockysize": 16,
    }
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(data)
        if overviews:
            dataset.build_overviews([2, 4], Resampling.nearest)


def test_render_diagnostics_collects_timings_cache_counts_and_overview_metadata(
    tmp_path,
) -> None:
    tif_path = tmp_path / "overviewed.tif"
    _write_geotiff(str(tif_path), overviews=True)
    spec = _spec(str(tif_path))
    cache = MapRenderCache()

    first_diagnostics = RenderDiagnostics()
    render_map_with_cache(spec, render_cache=cache, diagnostics=first_diagnostics)
    first = first_diagnostics.summary()

    assert first.output_width == spec.output_width
    assert first.output_height == spec.output_height
    assert first.timings_ms["render.total"] > 0
    assert first.timings_ms["raster.window_read"] > 0
    assert first.timings_ms["raster.scale_to_uint8"] >= 0
    assert first.counters["rasterio.read.calls"] >= 1
    assert first.cache_misses["full_map"] == 1
    assert first.cache_misses["raster_base"] == 1
    assert first.cache_misses["frame_overlay"] == 1
    assert len(first.raster_sources) == 1
    source = first.raster_sources[0]
    assert source.path == str(tif_path)
    assert source.layer_id == "L1"
    assert source.width == 64
    assert source.height == 64
    assert source.file_size_bytes is not None
    assert source.file_mtime_ns is not None
    assert source.has_usable_overviews

    cached_diagnostics = RenderDiagnostics()
    render_map_with_cache(spec, render_cache=cache, diagnostics=cached_diagnostics)
    cached = cached_diagnostics.summary()

    assert cached.cache_hits["full_map"] == 1
    assert cached.counters.get("rasterio.read.calls", 0) == 0


def test_render_diagnostics_do_not_change_rendered_canvas_pixels(tmp_path) -> None:
    tif_path = tmp_path / "plain.tif"
    _write_geotiff(str(tif_path), overviews=False)
    spec = _spec(str(tif_path))

    plain = render_map(spec).canvas
    diagnostics = RenderDiagnostics()
    measured = render_map(spec, diagnostics=diagnostics).canvas
    disabled = render_map(spec, diagnostics=RenderDiagnostics(enabled=False)).canvas

    assert measured.shape == plain.shape == disabled.shape
    assert np.array_equal(measured, plain)
    assert np.array_equal(disabled, plain)
    assert diagnostics.summary().output_width == spec.output_width


def test_qt_conversion_diagnostics_are_opt_in() -> None:
    QApplication.instance() or QApplication([])
    canvas = np.zeros((24, 32, 3), dtype=np.uint8)
    canvas[:, :] = (10, 20, 30)
    diagnostics = RenderDiagnostics()

    image = _numpy_to_image(canvas, diagnostics=diagnostics)
    pixmap = _image_to_pixmap(image, max_width=16, diagnostics=diagnostics)
    summary = diagnostics.summary()

    assert image.width() == 32
    assert image.height() == 24
    assert pixmap.width() == 16
    assert summary.timings_ms["qt.qimage_conversion"] > 0
    assert summary.timings_ms["qt.qpixmap_conversion"] > 0
