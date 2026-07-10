"""Tests for Story 11.6 progressive LOD and GPU decision contracts."""

from __future__ import annotations

import numpy as np

from thucthengay.render import (
    GeoWindow,
    GpuDecision,
    ProgressiveQuality,
    RasterFileSignature,
    RenderDiagnosticSummary,
    TileCache,
    TileCompositorConfig,
    TileCoverage,
    TileKey,
    assess_gpu_path,
    build_progressive_tile_plan,
    compose_progressive_tiles,
)


def _signature() -> RasterFileSignature:
    return RasterFileSignature(path="source.tif", size_bytes=1, mtime_ns=2)


def _coverage(lod: int = 5) -> TileCoverage:
    return TileCoverage(
        key=TileKey("L1", _signature(), lod, 3, 4),
        bounds=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
    )


def _solid(value: int) -> np.ndarray:
    pixels = np.zeros((4, 4, 3), dtype=np.uint8)
    pixels[:, :] = value
    return pixels


def _summary(
    *,
    total: float,
    raster: float,
    qt: float,
    hits: int,
    misses: int,
    reads: int,
) -> RenderDiagnosticSummary:
    return RenderDiagnosticSummary(
        composition_id="c1",
        target_id="t1",
        output_width=100,
        output_height=100,
        timings_ms={
            "render.total": total,
            "raster.window_read": raster,
            "raster.scale_to_uint8": 0.0,
            "qt.qimage_conversion": qt / 2,
            "qt.qpixmap_conversion": qt / 2,
            "render.composite": 0.0,
            "qt.paint_composite": 0.0,
        },
        counters={"rasterio.read.calls": reads},
        cache_hits={"full_map": hits},
        cache_misses={"full_map": misses},
        raster_sources=(),
    )


def test_progressive_plan_uses_lower_lod_tile_while_exact_tile_is_missing() -> None:
    cache = TileCache(max_bytes=4096)
    requested = _coverage(lod=5)
    fallback_key = TileKey("L1", requested.key.source_signature, 3, 3, 4)
    cache.put(fallback_key, _solid(70), requested.bounds)

    plan = build_progressive_tile_plan((requested,), cache=cache)

    assert plan.quality == ProgressiveQuality.PROGRESSIVE
    assert plan.missing == (requested,)
    assert plan.display_coverages == (TileCoverage(key=fallback_key, bounds=requested.bounds),)
    assert plan.matches[0].selected_key == fallback_key
    assert not plan.matches[0].exact
    assert not plan.review_actions_blocked
    assert "tam thoi" in plan.status_message


def test_progressive_composition_replaces_fallback_when_exact_tile_arrives() -> None:
    cache = TileCache(max_bytes=4096)
    requested = _coverage(lod=5)
    fallback_key = TileKey("L1", requested.key.source_signature, 3, 3, 4)
    cache.put(fallback_key, _solid(70), requested.bounds)

    progressive = compose_progressive_tiles(
        viewport=requested.bounds,
        map_scale=10000,
        coverages=(requested,),
        cache=cache,
        config=TileCompositorConfig(width=10, height=10, background_rgb=(0, 0, 0)),
    )
    cache.put(requested.key, _solid(200), requested.bounds)
    complete = compose_progressive_tiles(
        viewport=requested.bounds,
        map_scale=10000,
        coverages=(requested,),
        cache=cache,
        config=TileCompositorConfig(width=10, height=10, background_rgb=(0, 0, 0)),
    )

    assert progressive.plan.quality == ProgressiveQuality.PROGRESSIVE
    assert np.all(progressive.frame.canvas[5, 5] == 70)
    assert complete.plan.quality == ProgressiveQuality.COMPLETE
    assert complete.plan.missing == ()
    assert np.all(complete.frame.canvas[5, 5] == 200)


def test_progressive_plan_reports_loading_when_no_exact_or_fallback_tile_exists() -> None:
    requested = _coverage(lod=5)

    plan = build_progressive_tile_plan((requested,), cache=TileCache(max_bytes=4096))

    assert plan.quality == ProgressiveQuality.LOADING
    assert plan.display_coverages == ()
    assert plan.missing == (requested,)
    assert not plan.review_actions_blocked
    assert "tiep tuc thao tac" in plan.status_message


def test_gpu_assessment_keeps_qpainter_when_raster_decode_still_dominates() -> None:
    decision = assess_gpu_path(
        _summary(total=120.0, raster=80.0, qt=10.0, hits=1, misses=3, reads=12)
    )

    assert decision.decision == GpuDecision.KEEP_QPAINTER
    assert any("raster_decode_ms=80.00" in item for item in decision.evidence)


def test_gpu_assessment_creates_future_gpu_epic_when_qt_cost_dominates_after_cache() -> None:
    decision = assess_gpu_path(
        _summary(total=45.0, raster=2.0, qt=30.0, hits=9, misses=1, reads=1),
        baseline=_summary(total=120.0, raster=90.0, qt=5.0, hits=0, misses=5, reads=20),
    )

    assert decision.decision == GpuDecision.CREATE_GPU_EPIC
    assert "separate GPU-specific epic" in decision.rationale
    assert any("baseline total_ms=120.00" in item for item in decision.evidence)
