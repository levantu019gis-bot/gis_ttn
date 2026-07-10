"""Progressive LOD selection and GPU decision helpers for tile preview rendering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from thucthengay.render.diagnostics import RenderDiagnosticSummary
from thucthengay.render.spec import GeoWindow
from thucthengay.render.tile import TileCache, TileCoverage, TileKey
from thucthengay.render.tile_compositor import (
    TileComposedFrame,
    TileCompositorConfig,
    TileFrameState,
    compose_cached_tiles,
)


class ProgressiveQuality(StrEnum):
    """Visible raster quality for progressive tile composition."""

    COMPLETE = "complete"
    PROGRESSIVE = "progressive"
    LOADING = "loading"


class GpuDecision(StrEnum):
    """Recommendation for a possible future GPU path."""

    KEEP_QPAINTER = "keep_qpainter"
    CREATE_GPU_EPIC = "create_gpu_epic"


@dataclass(frozen=True)
class ProgressiveTileMatch:
    """Mapping from a requested tile to the key currently displayed."""

    requested: TileCoverage
    selected_key: TileKey
    exact: bool


@dataclass(frozen=True)
class ProgressiveTilePlan:
    """Progressive tile selection with status suitable for UI surfacing."""

    display_coverages: tuple[TileCoverage, ...]
    missing: tuple[TileCoverage, ...]
    matches: tuple[ProgressiveTileMatch, ...]
    quality: ProgressiveQuality
    status_message: str
    review_actions_blocked: bool = False


@dataclass(frozen=True)
class ProgressiveComposedFrame:
    """Composed frame plus progressive quality metadata."""

    frame: TileComposedFrame
    plan: ProgressiveTilePlan


@dataclass(frozen=True)
class GpuPathDecisionRecord:
    """Evidence-based GPU/QPainter decision record."""

    decision: GpuDecision
    rationale: str
    evidence: tuple[str, ...]


def build_progressive_tile_plan(
    coverages: tuple[TileCoverage, ...] | list[TileCoverage],
    *,
    cache: TileCache,
    min_lod: int = 0,
) -> ProgressiveTilePlan:
    """Select exact cached tiles or lower-LOD temporary replacements."""

    display: list[TileCoverage] = []
    missing: list[TileCoverage] = []
    matches: list[ProgressiveTileMatch] = []
    used_fallback = False
    for coverage in coverages:
        if cache.get(coverage.key) is not None:
            display.append(coverage)
            matches.append(
                ProgressiveTileMatch(
                    requested=coverage,
                    selected_key=coverage.key,
                    exact=True,
                )
            )
            continue
        fallback_key = _fallback_key(coverage.key, cache=cache, min_lod=min_lod)
        missing.append(coverage)
        if fallback_key is not None:
            used_fallback = True
            fallback_coverage = TileCoverage(key=fallback_key, bounds=coverage.bounds)
            display.append(fallback_coverage)
            matches.append(
                ProgressiveTileMatch(
                    requested=coverage,
                    selected_key=fallback_key,
                    exact=False,
                )
            )
    if used_fallback:
        quality = ProgressiveQuality.PROGRESSIVE
        message = "Dang hien thi anh tam thoi do phan giai thap; anh sac net van dang tai."
    elif missing:
        quality = ProgressiveQuality.LOADING
        message = "Dang tai anh hien thi; co the tiep tuc thao tac trong khi render."
    else:
        quality = ProgressiveQuality.COMPLETE
        message = "Anh hien thi da cap nhat day du."
    return ProgressiveTilePlan(
        display_coverages=tuple(display),
        missing=tuple(missing),
        matches=tuple(matches),
        quality=quality,
        status_message=message,
        review_actions_blocked=False,
    )


def compose_progressive_tiles(
    *,
    viewport: GeoWindow,
    map_scale: float,
    coverages: tuple[TileCoverage, ...] | list[TileCoverage],
    cache: TileCache,
    config: TileCompositorConfig,
    previous: TileFrameState | None = None,
    min_lod: int = 0,
) -> ProgressiveComposedFrame:
    """Compose exact tiles or lower-LOD fallbacks into the requested canvas."""

    plan = build_progressive_tile_plan(coverages, cache=cache, min_lod=min_lod)
    frame = compose_cached_tiles(
        viewport=viewport,
        map_scale=map_scale,
        coverages=plan.display_coverages,
        cache=cache,
        config=config,
        previous=previous,
    )
    return ProgressiveComposedFrame(frame=frame, plan=plan)


def assess_gpu_path(
    optimized: RenderDiagnosticSummary,
    *,
    baseline: RenderDiagnosticSummary | None = None,
) -> GpuPathDecisionRecord:
    """Create an evidence-based decision record; GPU remains opt-in for a later epic."""

    raster_ms = _timing(optimized, "raster.window_read") + _timing(
        optimized, "raster.scale_to_uint8"
    )
    qt_ms = _timing(optimized, "qt.qimage_conversion") + _timing(
        optimized, "qt.qpixmap_conversion"
    )
    composite_ms = _timing(optimized, "render.composite") + _timing(
        optimized,
        "qt.paint_composite",
    )
    total_ms = _timing(optimized, "render.total")
    read_calls = optimized.counters.get("rasterio.read.calls", 0)
    full_hits = optimized.cache_hits.get("full_map", 0)
    full_misses = optimized.cache_misses.get("full_map", 0)
    cache_hit_rate = _rate(full_hits, full_hits + full_misses)
    evidence = [
        f"optimized total_ms={total_ms:.2f}",
        f"raster_decode_ms={raster_ms:.2f}",
        f"qt_composite_ms={(qt_ms + composite_ms):.2f}",
        f"raster_read_calls={read_calls}",
        f"full_map_cache_hit_rate={cache_hit_rate:.2f}",
    ]
    if baseline is not None:
        baseline_total = _timing(baseline, "render.total")
        evidence.append(f"baseline total_ms={baseline_total:.2f}")
        if baseline_total > 0:
            evidence.append(f"total_improvement_ratio={total_ms / baseline_total:.2f}")
    gpu_candidate = (qt_ms + composite_ms) > max(raster_ms * 1.5, 8.0) and cache_hit_rate >= 0.5
    if gpu_candidate:
        return GpuPathDecisionRecord(
            decision=GpuDecision.CREATE_GPU_EPIC,
            rationale=(
                "Remaining measured cost is dominated by Qt/composite work after raster decode "
                "and cache behavior are acceptable; create a separate GPU-specific epic before "
                "changing the renderer."
            ),
            evidence=tuple(evidence),
        )
    return GpuPathDecisionRecord(
        decision=GpuDecision.KEEP_QPAINTER,
        rationale=(
            "Keep the QPainter/QImage path for now; diagnostics do not yet justify a GPU path "
            "outside a dedicated future epic."
        ),
        evidence=tuple(evidence),
    )


def _fallback_key(key: TileKey, *, cache: TileCache, min_lod: int) -> TileKey | None:
    for lod in range(key.lod - 1, min_lod - 1, -1):
        candidate = TileKey(
            layer_id=key.layer_id,
            source_signature=key.source_signature,
            lod=lod,
            x=key.x,
            y=key.y,
        )
        if cache.get(candidate) is not None:
            return candidate
    return None


def _timing(summary: RenderDiagnosticSummary, bucket: str) -> float:
    return float(summary.timings_ms.get(bucket, 0.0))


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return count / total
