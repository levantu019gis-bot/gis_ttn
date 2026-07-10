"""Tests for Story 11.5 cached tile composition and partial repaint contracts."""

from __future__ import annotations

import numpy as np

from thucthengay.render import (
    GeoWindow,
    RasterFileSignature,
    TileCache,
    TileCompositorConfig,
    TileCoverage,
    TileFrameState,
    TileKey,
    compose_cached_tiles,
)


def _signature() -> RasterFileSignature:
    return RasterFileSignature(path="source.tif", size_bytes=1, mtime_ns=2)


def _coverage(x: int, y: int) -> TileCoverage:
    return TileCoverage(
        key=TileKey("L1", _signature(), 1, x, y),
        bounds=GeoWindow(
            min_lon=float(x),
            min_lat=float(y),
            max_lon=float(x + 1),
            max_lat=float(y + 1),
        ),
    )


def _solid(value: int, size: int = 4) -> np.ndarray:
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    pixels[:, :] = value
    return pixels


def test_compositor_draws_cached_tiles_and_reports_only_missing_tiles() -> None:
    cache = TileCache(max_bytes=4096)
    coverages = (_coverage(0, 0), _coverage(1, 0), _coverage(0, 1), _coverage(1, 1))
    cache.put(coverages[0].key, _solid(20), coverages[0].bounds)
    cache.put(coverages[1].key, _solid(80), coverages[1].bounds)
    cache.put(coverages[2].key, _solid(140), coverages[2].bounds)

    frame = compose_cached_tiles(
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=2.0, max_lat=2.0),
        map_scale=10000,
        coverages=coverages,
        cache=cache,
        config=TileCompositorConfig(width=20, height=20, background_rgb=(0, 0, 0)),
    )

    assert frame.canvas.shape == (20, 20, 3)
    assert frame.full_recompose_used
    assert not frame.partial_repaint_used
    assert set(frame.used_keys) == {coverage.key for coverage in coverages[:3]}
    assert frame.missing == (coverages[3],)
    assert np.all(frame.canvas[15, 5] == 20)
    assert np.all(frame.canvas[15, 15] == 80)
    assert np.all(frame.canvas[5, 5] == 140)
    assert np.all(frame.canvas[5, 15] == 0)


def test_compositor_does_not_paint_invalid_tile_pixels_over_lower_layer() -> None:
    cache = TileCache(max_bytes=4096)
    lower = TileCoverage(
        key=TileKey("lower", _signature(), 1, 0, 0),
        bounds=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
    )
    upper = TileCoverage(
        key=TileKey("upper", _signature(), 1, 0, 0),
        bounds=lower.bounds,
    )
    upper_pixels = _solid(220)
    upper_pixels[:, :2] = 0
    upper_mask = np.ones((4, 4), dtype=bool)
    upper_mask[:, :2] = False
    cache.put(lower.key, _solid(50), lower.bounds)
    cache.put(upper.key, upper_pixels, upper.bounds, valid_mask=upper_mask)

    frame = compose_cached_tiles(
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        map_scale=10000,
        coverages=(lower, upper),
        cache=cache,
        config=TileCompositorConfig(width=20, height=20, background_rgb=(0, 0, 0)),
    )

    assert np.all(frame.canvas[10, 4] == 50)
    assert np.all(frame.canvas[10, 16] == 220)


def test_small_pan_reuses_previous_frame_buffer_and_repositions_cached_tiles() -> None:
    cache = TileCache(max_bytes=4096)
    old_viewport = GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=2.0, max_lat=2.0)
    new_viewport = GeoWindow(min_lon=0.2, min_lat=0.0, max_lon=2.2, max_lat=2.0)
    coverages = (_coverage(0, 0), _coverage(1, 0), _coverage(2, 0))
    cache.put(coverages[0].key, _solid(10), coverages[0].bounds)
    cache.put(coverages[1].key, _solid(120), coverages[1].bounds)
    previous_canvas = np.zeros((20, 20, 3), dtype=np.uint8)
    previous_canvas[:, :] = 33

    frame = compose_cached_tiles(
        viewport=new_viewport,
        map_scale=10000,
        coverages=coverages,
        cache=cache,
        config=TileCompositorConfig(
            width=20,
            height=20,
            background_rgb=(0, 0, 0),
            partial_repaint_threshold_px=5,
        ),
        previous=TileFrameState(
            viewport=old_viewport,
            map_scale=10000,
            canvas=previous_canvas,
        ),
    )

    assert frame.partial_repaint_used
    assert not frame.full_recompose_used
    assert frame.missing == (coverages[2],)
    assert np.all(frame.canvas[:, -1] == 0)
    assert np.any(frame.canvas == 120)


def test_zoom_change_or_large_pan_falls_back_to_full_recompose() -> None:
    cache = TileCache(max_bytes=4096)
    coverage = _coverage(0, 0)
    cache.put(coverage.key, _solid(200), coverage.bounds)
    previous = TileFrameState(
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        map_scale=10000,
        canvas=_solid(11, size=10),
    )

    zoom_frame = compose_cached_tiles(
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        map_scale=20000,
        coverages=(coverage,),
        cache=cache,
        config=TileCompositorConfig(width=10, height=10, background_rgb=(0, 0, 0)),
        previous=previous,
    )
    large_pan_frame = compose_cached_tiles(
        viewport=GeoWindow(min_lon=0.8, min_lat=0.0, max_lon=1.8, max_lat=1.0),
        map_scale=10000,
        coverages=(coverage,),
        cache=cache,
        config=TileCompositorConfig(
            width=10,
            height=10,
            background_rgb=(0, 0, 0),
            partial_repaint_threshold_px=2,
        ),
        previous=previous,
    )

    assert zoom_frame.full_recompose_used
    assert not zoom_frame.partial_repaint_used
    assert large_pan_frame.full_recompose_used
    assert not large_pan_frame.partial_repaint_used


def test_compositor_preserves_requested_canvas_dimensions_for_compare_like_coverage() -> None:
    cache = TileCache(max_bytes=4096)
    left = TileCoverage(
        key=TileKey("A", _signature(), 1, 0, 0),
        bounds=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
    )
    right = TileCoverage(
        key=TileKey("B", _signature(), 1, 1, 0),
        bounds=GeoWindow(min_lon=1.0, min_lat=0.0, max_lon=2.0, max_lat=1.0),
    )
    cache.put(left.key, _solid(60), left.bounds)
    cache.put(right.key, _solid(180), right.bounds)

    frame = compose_cached_tiles(
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=2.0, max_lat=1.0),
        map_scale=10000,
        coverages=(left, right),
        cache=cache,
        config=TileCompositorConfig(width=40, height=20, background_rgb=(0, 0, 0)),
    )

    assert frame.canvas.shape == (20, 40, 3)
    assert np.all(frame.canvas[10, 5] == 60)
    assert np.all(frame.canvas[10, 35] == 180)
