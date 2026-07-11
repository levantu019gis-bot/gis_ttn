from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from thucthengay.models import GridConfig, GridInterval, TemporalCompareOrientation
from thucthengay.models.template import MapFrame
from thucthengay.render import RenderDiagnostics
from thucthengay.render.core import MapRenderCache
from thucthengay.render.raster import RasterRenderResult
from thucthengay.render.spec import (
    GeoWindow,
    RenderBackground,
    RenderComparisonPane,
    RenderComparisonSpec,
    RenderLayerRef,
    RenderSpec,
)
from thucthengay.render.tile import TileCache
from thucthengay.render.tile_preview import (
    TilePreviewSettings,
    iter_tile_preview_frames,
    render_tile_preview_map,
)
from thucthengay.render.tile_scheduler import TileScheduler


def test_render_tile_preview_decodes_tiles_and_reuses_cache(tmp_path: Path) -> None:
    raster_path = tmp_path / "source.tif"
    _write_geotiff(raster_path)
    spec = _tile_preview_spec(raster_path)
    tile_cache = TileCache(max_bytes=32 * 1024 * 1024)
    scheduler = TileScheduler(cache=tile_cache)
    render_cache = MapRenderCache()
    settings = TilePreviewSettings(
        tile_pixels=64,
        max_decode_workers=2,
        tile_width_degrees=0.2,
        tile_height_degrees=0.2,
        partial_repaint_threshold_px=64,
    )

    first_diagnostics = RenderDiagnostics()
    first, previous_state = render_tile_preview_map(
        spec,
        tile_cache=tile_cache,
        tile_scheduler=scheduler,
        render_cache=render_cache,
        settings=settings,
        diagnostics=first_diagnostics,
    )

    assert isinstance(first, RasterRenderResult)
    assert first.canvas.shape == (360, 640, 3)
    assert first.painted_layer_ids == ("L1",)
    assert tile_cache.entry_count > 0
    first_summary = first_diagnostics.summary()
    assert first_summary.counters["tile_preview.decode.jobs"] > 0
    assert first_summary.counters["tile_preview.decode.workers"] == 2
    assert first_summary.cache_misses["tile_preview"] > 0

    second_diagnostics = RenderDiagnostics()
    second, _previous = render_tile_preview_map(
        spec,
        tile_cache=tile_cache,
        tile_scheduler=scheduler,
        render_cache=render_cache,
        previous_state=previous_state,
        settings=settings,
        diagnostics=second_diagnostics,
    )

    assert second.canvas.shape == first.canvas.shape
    second_summary = second_diagnostics.summary()
    assert second_summary.counters["tile_preview.decode.jobs"] == 0
    assert second_summary.cache_hits["tile_preview"] >= first_summary.cache_misses[
        "tile_preview"
    ]
    assert second_summary.counters["tile_preview.compose.partial_repaint"] == 1


def test_iter_tile_preview_frames_renders_temporal_compare_panes(
    tmp_path: Path,
) -> None:
    pane_a_path = tmp_path / "pane-a.tif"
    pane_b_path = tmp_path / "pane-b.tif"
    _write_geotiff(pane_a_path, offset=20)
    _write_geotiff(pane_b_path, offset=120)
    spec = _tile_preview_spec(pane_a_path).model_copy(
        update={
            "temporal_compare": RenderComparisonSpec(
                enabled=True,
                orientation=TemporalCompareOrientation.VERTICAL,
                pane_a=RenderComparisonPane(
                    composition_id="alpha__20260525",
                    geo_window=GeoWindow(
                        min_lon=106.45,
                        min_lat=10.55,
                        max_lon=106.95,
                        max_lat=11.05,
                    ),
                    layers=[
                        RenderLayerRef(
                            layer_id="A",
                            source_path=str(pane_a_path),
                            order=0,
                        )
                    ],
                ),
                pane_b=RenderComparisonPane(
                    composition_id="alpha__20260526",
                    geo_window=GeoWindow(
                        min_lon=106.45,
                        min_lat=10.55,
                        max_lon=106.95,
                        max_lat=11.05,
                    ),
                    layers=[
                        RenderLayerRef(
                            layer_id="B",
                            source_path=str(pane_b_path),
                            order=0,
                        )
                    ],
                ),
            )
        }
    )
    tile_cache = TileCache(max_bytes=32 * 1024 * 1024)
    scheduler = TileScheduler(cache=tile_cache)

    frames = list(
        iter_tile_preview_frames(
            spec,
            tile_cache=tile_cache,
            tile_scheduler=scheduler,
            render_cache=MapRenderCache(),
            settings=TilePreviewSettings(
                tile_pixels=64,
                tile_width_degrees=0.2,
                tile_height_degrees=0.2,
            ),
            diagnostics=RenderDiagnostics(),
        )
    )

    assert len(frames) > 1
    final = frames[-1]
    assert final.done is True
    assert final.result.canvas.shape == (360, 640, 3)
    assert set(final.result.painted_layer_ids) == {"A", "B"}
    assert set(final.state.pane_frames) == {"A", "B"}


def test_iter_tile_preview_frames_batches_compose_work(
    tmp_path: Path,
) -> None:
    raster_path = tmp_path / "source.tif"
    _write_geotiff(raster_path)
    spec = _tile_preview_spec(raster_path)
    diagnostics = RenderDiagnostics()
    tile_cache = TileCache(max_bytes=32 * 1024 * 1024)

    frames = list(
        iter_tile_preview_frames(
            spec,
            tile_cache=tile_cache,
            tile_scheduler=TileScheduler(cache=tile_cache),
            render_cache=MapRenderCache(),
            settings=TilePreviewSettings(
                tile_pixels=64,
                max_decode_workers=1,
                tile_width_degrees=0.2,
                tile_height_degrees=0.2,
                progress_frame_interval_ms=10**9,
                progress_tile_batch_size=4,
            ),
            diagnostics=diagnostics,
        )
    )

    total = frames[-1].total_missing_tiles
    expected_decoded = list(range(4, total, 4))
    if not expected_decoded or expected_decoded[-1] != total:
        expected_decoded.append(total)

    assert [frame.decoded_tiles for frame in frames] == expected_decoded
    assert frames[0].decoded_tiles > 0
    assert frames[-1].done is True
    summary = diagnostics.summary()
    assert summary.counters["tile_preview.decode.jobs"] == total
    assert summary.counters["tile_preview.compose.full_recompose"] == len(frames)
    assert len(frames) < total + 1


def _write_geotiff(path: Path, *, offset: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.arange(300 * 300, dtype=np.uint16).reshape(300, 300) + offset) % 255
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=300,
        width=300,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(106.0, 11.4, 0.005, 0.005),
    ) as dataset:
        dataset.write(data.astype("uint8"), 1)


def _tile_preview_spec(raster_path: Path) -> RenderSpec:
    return RenderSpec(
        composition_id="alpha__20260525",
        target_id="alpha",
        output_width=640,
        output_height=360,
        view_center=[106.7, 10.8],
        view_scale=50_000,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=16 / 9,
        geo_window=GeoWindow(min_lon=106.45, min_lat=10.55, max_lon=106.95, max_lat=11.05),
        visible_layers=[
            RenderLayerRef(layer_id="L1", source_path=str(raster_path), order=0)
        ],
        grid=GridConfig(
            interval=GridInterval(minutes=30),
            style={"max_frame_ticks_per_axis": 8},
        ),
        background=RenderBackground(color="#FFFFFF"),
        template_metadata_file="alpha.template.json",
        template_pptx="alpha.pptx",
        slide_index=0,
    )
