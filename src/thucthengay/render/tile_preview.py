"""Tile-backed Review/Edit preview renderer."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import nullcontext
from dataclasses import dataclass, field
from time import perf_counter

import numpy as np

from thucthengay.render.core import (
    MapRenderCache,
    TemporalComparePaneRenderPlan,
    inner_render_spec_and_layout,
    render_map_with_raster_base,
    temporal_compare_render_plan,
)
from thucthengay.render.diagnostics import RenderDiagnostics
from thucthengay.render.raster import CancelCallback, RasterRenderResult
from thucthengay.render.spec import RenderSpec
from thucthengay.render.tile import TileCache, TileCoverage, TileGrid, TileIndex, TileKey
from thucthengay.render.tile_compositor import (
    TileComposedFrame,
    TileCompositorConfig,
    TileFrameState,
    compose_cached_tiles,
)
from thucthengay.render.tile_scheduler import (
    TileDecodeJob,
    TileDecodeResult,
    TileScheduler,
    decode_tile_job,
)


@dataclass(frozen=True)
class TilePreviewSettings:
    """Runtime settings for the Review/Edit tile preview path."""

    tile_pixels: int = 256
    max_decode_workers: int = 1
    tile_width_degrees: float = 0.05
    tile_height_degrees: float = 0.05
    partial_repaint_threshold_px: int = 96
    progress_frame_interval_ms: int = 66
    progress_tile_batch_size: int = 4
    tile_decode_timeout_ms: int = 0


@dataclass(frozen=True)
class TilePreviewState:
    """Reusable tile-composed frames retained between preview requests."""

    normal_frame: TileFrameState | None = None
    pane_frames: dict[str, TileFrameState] = field(default_factory=dict)


@dataclass(frozen=True)
class TilePreviewProgressFrame:
    """One progressive tile preview frame ready for UI display."""

    result: RasterRenderResult
    state: TilePreviewState
    decoded_tiles: int
    total_missing_tiles: int
    done: bool
    message: str


@dataclass(frozen=True)
class _PaneContext:
    pane_key: str
    plan: TemporalComparePaneRenderPlan
    coverages: tuple[TileCoverage, ...]
    previous_frame: TileFrameState | None


@dataclass(frozen=True)
class _PaneJob:
    pane_key: str
    job: TileDecodeJob


@dataclass(frozen=True)
class _TimedTileDecodeResult:
    result: TileDecodeResult
    elapsed_ms: float


@dataclass
class _ProgressComposeGate:
    """Coalesce tile decode completions before rebuilding a preview frame."""

    settings: TilePreviewSettings
    last_compose_at: float = field(default_factory=perf_counter)
    last_compose_decoded: int = 0

    def should_compose(self, *, decoded: int, done: bool) -> bool:
        if done:
            return True
        elapsed_ms = (perf_counter() - self.last_compose_at) * 1000.0
        interval_reached = (
            self.settings.progress_frame_interval_ms <= 0
            or elapsed_ms >= self.settings.progress_frame_interval_ms
        )
        batch_reached = (
            decoded - self.last_compose_decoded
        ) >= self.settings.progress_tile_batch_size
        # OR semantics: compose when either time or decoded-tile batch reaches its threshold.
        return interval_reached or batch_reached

    def mark_composed(self, *, decoded: int) -> None:
        self.last_compose_at = perf_counter()
        self.last_compose_decoded = decoded


def render_tile_preview_map(
    spec: RenderSpec,
    *,
    tile_cache: TileCache,
    tile_scheduler: TileScheduler,
    render_cache: MapRenderCache | None = None,
    previous_frame: TileFrameState | None = None,
    previous_state: TilePreviewState | None = None,
    settings: TilePreviewSettings | None = None,
    is_cancelled: CancelCallback | None = None,
    diagnostics: RenderDiagnostics | None = None,
) -> tuple[RasterRenderResult, TilePreviewState]:
    """Render a full map-surround preview by decoding only missing map-space tiles."""

    initial_state = previous_state or TilePreviewState(normal_frame=previous_frame)
    last: TilePreviewProgressFrame | None = None
    for frame in iter_tile_preview_frames(
        spec,
        tile_cache=tile_cache,
        tile_scheduler=tile_scheduler,
        render_cache=render_cache,
        previous_state=initial_state,
        settings=settings,
        is_cancelled=is_cancelled,
        diagnostics=diagnostics,
    ):
        last = frame
    if last is None:
        raise RuntimeError("Tile preview did not produce a frame.")
    return last.result, last.state


def iter_tile_preview_frames(
    spec: RenderSpec,
    *,
    tile_cache: TileCache,
    tile_scheduler: TileScheduler,
    render_cache: MapRenderCache | None = None,
    previous_state: TilePreviewState | None = None,
    settings: TilePreviewSettings | None = None,
    is_cancelled: CancelCallback | None = None,
    diagnostics: RenderDiagnostics | None = None,
) -> Iterator[TilePreviewProgressFrame]:
    """Yield full map-surround frames as cached/missing tiles become available."""

    if diagnostics is not None:
        diagnostics.record_render_spec(spec)
    if spec.temporal_compare.enabled:
        yield from _iter_compare_tile_preview_frames(
            spec,
            tile_cache=tile_cache,
            tile_scheduler=tile_scheduler,
            render_cache=render_cache,
            previous_state=previous_state or TilePreviewState(),
            settings=settings or TilePreviewSettings(),
            is_cancelled=is_cancelled,
            diagnostics=diagnostics,
        )
        return
    yield from _iter_normal_tile_preview_frames(
        spec,
        tile_cache=tile_cache,
        tile_scheduler=tile_scheduler,
        render_cache=render_cache,
        previous_state=previous_state or TilePreviewState(),
        settings=settings or TilePreviewSettings(),
        is_cancelled=is_cancelled,
        diagnostics=diagnostics,
    )


def _iter_normal_tile_preview_frames(
    spec: RenderSpec,
    *,
    tile_cache: TileCache,
    tile_scheduler: TileScheduler,
    render_cache: MapRenderCache | None,
    previous_state: TilePreviewState,
    settings: TilePreviewSettings,
    is_cancelled: CancelCallback | None,
    diagnostics: RenderDiagnostics | None,
) -> Iterator[TilePreviewProgressFrame]:
    with diagnostics.time("tile_preview.layout") if diagnostics is not None else nullcontext():
        render_spec, layout = inner_render_spec_and_layout(spec)
    inner = layout.inner_map
    tile_index = _tile_index(settings)
    request_id = _tile_request_id(render_spec)
    revision = tile_scheduler.begin_request(request_id)
    with diagnostics.time("tile_preview.coverage") if diagnostics is not None else nullcontext():
        coverages = tile_index.visible_tiles_for_spec(render_spec)
    jobs = _queue_jobs(
        tile_scheduler,
        request_id=request_id,
        viewport=render_spec.geo_window,
        layers=render_spec.visible_layers,
        coverages=coverages,
        tile_pixels=settings.tile_pixels,
        diagnostics=diagnostics,
    )
    total = len(jobs)
    decoded = 0
    compose_gate = _ProgressComposeGate(settings)
    has_initial_content = (
        total == 0
        or previous_state.normal_frame is not None
        or total < len(coverages)
    )
    if has_initial_content:
        yield _normal_progress_frame(
            spec,
            render_spec=render_spec,
            coverages=coverages,
            tile_cache=tile_cache,
            render_cache=render_cache,
            previous_frame=previous_state.normal_frame,
            width=inner.width,
            height=inner.height,
            settings=settings,
            diagnostics=diagnostics,
            decoded=decoded,
            total=total,
            done=total == 0,
        )
        compose_gate.mark_composed(decoded=decoded)
    for result in _iter_decode_results(
        jobs,
        max_workers=settings.max_decode_workers,
        timeout_ms=settings.tile_decode_timeout_ms,
        is_cancelled=is_cancelled,
        diagnostics=diagnostics,
    ):
        tile_scheduler.apply_result(result)
        decoded += 1
        done = decoded >= total or revision != tile_scheduler.revision
        if not compose_gate.should_compose(decoded=decoded, done=done):
            continue
        yield _normal_progress_frame(
            spec,
            render_spec=render_spec,
            coverages=coverages,
            tile_cache=tile_cache,
            render_cache=render_cache,
            previous_frame=None,
            width=inner.width,
            height=inner.height,
            settings=settings,
            diagnostics=diagnostics,
            decoded=decoded,
            total=total,
            done=done,
        )
        compose_gate.mark_composed(decoded=decoded)


def _iter_compare_tile_preview_frames(
    spec: RenderSpec,
    *,
    tile_cache: TileCache,
    tile_scheduler: TileScheduler,
    render_cache: MapRenderCache | None,
    previous_state: TilePreviewState,
    settings: TilePreviewSettings,
    is_cancelled: CancelCallback | None,
    diagnostics: RenderDiagnostics | None,
) -> Iterator[TilePreviewProgressFrame]:
    with diagnostics.time("tile_preview.layout") if diagnostics is not None else nullcontext():
        plan = temporal_compare_render_plan(spec)
    tile_index = _tile_index(settings)
    request_id = _tile_request_id(plan.spec)
    revision = tile_scheduler.begin_request(request_id)
    contexts = tuple(
        _pane_context(
            item,
            tile_index=tile_index,
            previous_state=previous_state,
            diagnostics=diagnostics,
        )
        for item in (plan.pane_a, plan.pane_b)
    )
    pane_jobs: list[_PaneJob] = []
    for context in contexts:
        jobs = _queue_jobs(
            tile_scheduler,
            request_id=request_id,
            viewport=context.plan.spec.geo_window,
            layers=context.plan.spec.visible_layers,
            coverages=context.coverages,
            tile_pixels=settings.tile_pixels,
            diagnostics=diagnostics,
        )
        pane_jobs.extend(_PaneJob(context.pane_key, job) for job in jobs)
    total = len(pane_jobs)
    decoded = 0
    compose_gate = _ProgressComposeGate(settings)
    coverage_total = sum(len(context.coverages) for context in contexts)
    has_initial_content = (
        total == 0
        or any(context.previous_frame is not None for context in contexts)
        or total < coverage_total
    )
    if has_initial_content:
        yield _compare_progress_frame(
            spec,
            plan=plan,
            contexts=contexts,
            tile_cache=tile_cache,
            render_cache=render_cache,
            settings=settings,
            diagnostics=diagnostics,
            decoded=decoded,
            total=total,
            done=total == 0,
        )
        compose_gate.mark_composed(decoded=decoded)
    for result in _iter_decode_results(
        tuple(pane_job.job for pane_job in pane_jobs),
        max_workers=settings.max_decode_workers,
        timeout_ms=settings.tile_decode_timeout_ms,
        is_cancelled=is_cancelled,
        diagnostics=diagnostics,
    ):
        tile_scheduler.apply_result(result)
        decoded += 1
        done = decoded >= total or revision != tile_scheduler.revision
        if not compose_gate.should_compose(decoded=decoded, done=done):
            continue
        yield _compare_progress_frame(
            spec,
            plan=plan,
            contexts=contexts,
            tile_cache=tile_cache,
            render_cache=render_cache,
            settings=settings,
            diagnostics=diagnostics,
            decoded=decoded,
            total=total,
            done=done,
        )
        compose_gate.mark_composed(decoded=decoded)


def _normal_progress_frame(
    spec: RenderSpec,
    *,
    render_spec: RenderSpec,
    coverages: tuple[TileCoverage, ...],
    tile_cache: TileCache,
    render_cache: MapRenderCache | None,
    previous_frame: TileFrameState | None,
    width: int,
    height: int,
    settings: TilePreviewSettings,
    diagnostics: RenderDiagnostics | None,
    decoded: int,
    total: int,
    done: bool,
) -> TilePreviewProgressFrame:
    composed = _compose_tiles(
        viewport=render_spec.geo_window,
        map_scale=render_spec.view_scale,
        coverages=coverages,
        tile_cache=tile_cache,
        previous_frame=previous_frame,
        width=width,
        height=height,
        background_rgb=_parse_hex_rgb(render_spec.background.color),
        settings=settings,
        diagnostics=diagnostics,
    )
    raster = RasterRenderResult(
        canvas=composed.canvas,
        painted_layer_ids=tuple(dict.fromkeys(key.layer_id for key in composed.used_keys)),
    )
    state = TilePreviewState(
        normal_frame=TileFrameState(
            viewport=render_spec.geo_window,
            map_scale=render_spec.view_scale,
            canvas=composed.canvas,
        )
    )
    return TilePreviewProgressFrame(
        result=_frame_safe_result(
            spec,
            raster,
            render_cache=render_cache,
            diagnostics=diagnostics,
        ),
        state=state,
        decoded_tiles=decoded,
        total_missing_tiles=total,
        done=done,
        message=_progress_message(decoded, total, done=done),
    )


def _compare_progress_frame(
    spec: RenderSpec,
    *,
    plan,
    contexts: tuple[_PaneContext, ...],
    tile_cache: TileCache,
    render_cache: MapRenderCache | None,
    settings: TilePreviewSettings,
    diagnostics: RenderDiagnostics | None,
    decoded: int,
    total: int,
    done: bool,
) -> TilePreviewProgressFrame:
    inner = plan.inner_rect
    canvas = np.empty((inner.height, inner.width, 3), dtype=np.uint8)
    canvas[:, :] = np.array(plan.gap_rgb, dtype=np.uint8)
    pane_frames: dict[str, TileFrameState] = {}
    used_keys: list[TileKey] = []
    for context in contexts:
        pane = context.plan
        pane_canvas = _compose_tiles(
            viewport=pane.spec.geo_window,
            map_scale=pane.spec.view_scale,
            coverages=context.coverages,
            tile_cache=tile_cache,
            previous_frame=context.previous_frame if decoded == 0 else None,
            width=pane.rect.width,
            height=pane.rect.height,
            background_rgb=_parse_hex_rgb(pane.spec.background.color),
            settings=settings,
            diagnostics=diagnostics,
        )
        pane_frames[context.pane_key] = TileFrameState(
            viewport=pane.spec.geo_window,
            map_scale=pane.spec.view_scale,
            canvas=pane_canvas.canvas,
        )
        used_keys.extend(pane_canvas.used_keys)
        top = pane.rect.top - inner.top
        bottom = pane.rect.bottom - inner.top
        left = pane.rect.left - inner.left
        right = pane.rect.right - inner.left
        canvas[top:bottom, left:right, :] = pane_canvas.canvas

    raster = RasterRenderResult(
        canvas=canvas,
        painted_layer_ids=tuple(dict.fromkeys(key.layer_id for key in used_keys)),
    )
    return TilePreviewProgressFrame(
        result=_frame_safe_result(
            spec,
            raster,
            render_cache=render_cache,
            diagnostics=diagnostics,
        ),
        state=TilePreviewState(pane_frames=pane_frames),
        decoded_tiles=decoded,
        total_missing_tiles=total,
        done=done,
        message=_progress_message(decoded, total, done=done, compare=True),
    )


def _pane_context(
    plan: TemporalComparePaneRenderPlan,
    *,
    tile_index: TileIndex,
    previous_state: TilePreviewState,
    diagnostics: RenderDiagnostics | None,
) -> _PaneContext:
    with diagnostics.time("tile_preview.coverage") if diagnostics is not None else nullcontext():
        coverages = tile_index.visible_tiles_for_spec(plan.spec)
    if diagnostics is not None:
        diagnostics.increment("tile_preview.coverage.tiles", len(coverages))
        diagnostics.increment(f"tile_preview.coverage.pane_{plan.pane_key}", len(coverages))
    return _PaneContext(
        pane_key=plan.pane_key,
        plan=plan,
        coverages=coverages,
        previous_frame=previous_state.pane_frames.get(plan.pane_key),
    )


def _queue_jobs(
    tile_scheduler: TileScheduler,
    *,
    request_id: str,
    viewport,
    layers,
    coverages: tuple[TileCoverage, ...],
    tile_pixels: int,
    diagnostics: RenderDiagnostics | None,
) -> tuple[TileDecodeJob, ...]:
    with diagnostics.time("tile_preview.queue") if diagnostics is not None else nullcontext():
        jobs = tile_scheduler.queue_missing(
            request_id=request_id,
            viewport=viewport,
            layers=layers,
            coverages=coverages,
            tile_pixels=tile_pixels,
        )
    if diagnostics is not None:
        diagnostics.increment("tile_preview.decode.jobs", len(jobs))
        for _coverage in range(max(0, len(coverages) - len(jobs))):
            diagnostics.record_cache_hit("tile_preview")
        for _job in jobs:
            diagnostics.record_cache_miss("tile_preview")
    return jobs


def _iter_decode_results(
    jobs: tuple[TileDecodeJob, ...],
    *,
    max_workers: int,
    timeout_ms: int,
    is_cancelled: CancelCallback | None,
    diagnostics: RenderDiagnostics | None,
) -> Iterator[TileDecodeResult]:
    if not jobs:
        return
    workers = max(1, min(int(max_workers), len(jobs)))
    if diagnostics is not None:
        diagnostics.increment("tile_preview.decode.workers", workers)
    if workers <= 1:
        for job in jobs:
            if _is_cancelled(is_cancelled):
                break
            timed = _decode_tile_job_timed(job, is_cancelled=is_cancelled)
            _record_decode_timing(timed, diagnostics=diagnostics)
            yield timed.result
        return

    executor = ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="tile-preview-decode",
    )
    futures = [
        executor.submit(_decode_tile_job_timed, job, is_cancelled=is_cancelled)
        for job in jobs
    ]
    pending = set(futures)
    timeout_seconds = timeout_ms / 1000.0 if timeout_ms > 0 else None
    poll_seconds = 0.05
    last_progress_at = perf_counter()
    aborted = False
    try:
        while pending:
            if _is_cancelled(is_cancelled):
                aborted = True
                break
            wait_timeout = poll_seconds
            if timeout_seconds is not None:
                elapsed = perf_counter() - last_progress_at
                remaining = max(0.0, timeout_seconds - elapsed)
                wait_timeout = min(poll_seconds, remaining)
            done, pending = wait(
                pending,
                timeout=wait_timeout,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                if timeout_seconds is not None and (
                    perf_counter() - last_progress_at
                ) >= timeout_seconds:
                    if diagnostics is not None:
                        diagnostics.increment("tile_preview.decode.timeouts", len(pending))
                    aborted = True
                    break
                continue
            last_progress_at = perf_counter()
            for future in done:
                timed = future.result()
                _record_decode_timing(timed, diagnostics=diagnostics)
                yield timed.result
    finally:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=not aborted, cancel_futures=True)


def _decode_tile_job_timed(
    job: TileDecodeJob,
    *,
    is_cancelled: CancelCallback | None,
) -> _TimedTileDecodeResult:
    started = perf_counter()
    result = decode_tile_job(job, is_cancelled=is_cancelled)
    return _TimedTileDecodeResult(
        result=result,
        elapsed_ms=(perf_counter() - started) * 1000.0,
    )


def _record_decode_timing(
    timed: _TimedTileDecodeResult,
    *,
    diagnostics: RenderDiagnostics | None,
) -> None:
    if diagnostics is not None:
        diagnostics.add_timing_ms("tile_preview.decode", timed.elapsed_ms)


def _compose_tiles(
    *,
    viewport,
    map_scale: float,
    coverages: tuple[TileCoverage, ...],
    tile_cache: TileCache,
    previous_frame: TileFrameState | None,
    width: int,
    height: int,
    background_rgb: tuple[int, int, int],
    settings: TilePreviewSettings,
    diagnostics: RenderDiagnostics | None,
) -> TileComposedFrame:
    with diagnostics.time("tile_preview.compose") if diagnostics is not None else nullcontext():
        composed = compose_cached_tiles(
            viewport=viewport,
            map_scale=map_scale,
            coverages=coverages,
            cache=tile_cache,
            config=TileCompositorConfig(
                width=width,
                height=height,
                background_rgb=background_rgb,
                partial_repaint_threshold_px=settings.partial_repaint_threshold_px,
            ),
            previous=previous_frame,
        )
    if diagnostics is not None:
        diagnostics.increment("tile_preview.compose.used_tiles", len(composed.used_keys))
        diagnostics.increment("tile_preview.compose.missing_tiles", len(composed.missing))
        diagnostics.increment(
            "tile_preview.compose.partial_repaint",
            1 if composed.partial_repaint_used else 0,
        )
        diagnostics.increment(
            "tile_preview.compose.full_recompose",
            1 if composed.full_recompose_used else 0,
        )
    return composed


def _frame_safe_result(
    spec: RenderSpec,
    raster: RasterRenderResult,
    *,
    render_cache: MapRenderCache | None,
    diagnostics: RenderDiagnostics | None,
) -> RasterRenderResult:
    return render_map_with_raster_base(
        spec,
        raster,
        frame_cache=render_cache.frame_overlays if render_cache is not None else None,
        diagnostics=diagnostics,
    )


def _tile_index(settings: TilePreviewSettings) -> TileIndex:
    return TileIndex(
        TileGrid(
            tile_width=settings.tile_width_degrees,
            tile_height=settings.tile_height_degrees,
        )
    )


def _tile_request_id(spec: RenderSpec) -> str:
    window = spec.geo_window
    compare = "compare" if spec.temporal_compare.enabled else "single"
    return (
        f"{compare}:{spec.composition_id}:{spec.output_width}x{spec.output_height}:"
        f"{window.min_lon:.10f},{window.min_lat:.10f},"
        f"{window.max_lon:.10f},{window.max_lat:.10f}:{spec.view_scale}"
    )


def _progress_message(
    decoded: int,
    total: int,
    *,
    done: bool,
    compare: bool = False,
) -> str:
    if total <= 0:
        return "Tile preview da cap nhat tu cache."
    if done:
        return f"Tile preview da tai xong {decoded}/{total} tile."
    prefix = "Tile compare" if compare else "Tile preview"
    return f"{prefix} dang tai {decoded}/{total} tile..."


def _parse_hex_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _is_cancelled(is_cancelled: CancelCallback | None) -> bool:
    return is_cancelled is not None and is_cancelled()
