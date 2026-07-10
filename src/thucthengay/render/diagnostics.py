"""Optional render diagnostics for measuring the current preview pipeline."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter_ns
from typing import Any


@dataclass(frozen=True)
class RasterSourceDiagnostics:
    """Read-only metadata used to compare raster readiness between render runs."""

    layer_id: str
    path: str
    width: int
    height: int
    band_count: int
    crs: str | None
    block_shapes: tuple[tuple[int, int], ...]
    overviews_by_band: tuple[tuple[int, ...], ...]
    file_size_bytes: int | None = None
    file_mtime_ns: int | None = None

    @property
    def has_usable_overviews(self) -> bool:
        return any(level > 1 for band_levels in self.overviews_by_band for level in band_levels)


@dataclass(frozen=True)
class RenderDiagnosticSummary:
    """Immutable snapshot of collected render measurements."""

    composition_id: str | None
    target_id: str | None
    output_width: int | None
    output_height: int | None
    timings_ms: dict[str, float]
    counters: dict[str, int]
    cache_hits: dict[str, int]
    cache_misses: dict[str, int]
    raster_sources: tuple[RasterSourceDiagnostics, ...]


@dataclass
class RenderDiagnostics:
    """Small opt-in collector shared by render services and Review/Edit widgets."""

    enabled: bool = True
    composition_id: str | None = None
    target_id: str | None = None
    output_width: int | None = None
    output_height: int | None = None
    _timings_ms: defaultdict[str, float] = field(default_factory=lambda: defaultdict(float))
    _counters: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    _cache_hits: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    _cache_misses: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    _raster_sources: OrderedDict[tuple[str, str], RasterSourceDiagnostics] = field(
        default_factory=OrderedDict
    )

    def record_render_spec(self, spec: Any) -> None:
        if not self.enabled:
            return
        self.composition_id = self.composition_id or getattr(spec, "composition_id", None)
        self.target_id = self.target_id or getattr(spec, "target_id", None)
        self.output_width = self.output_width or getattr(spec, "output_width", None)
        self.output_height = self.output_height or getattr(spec, "output_height", None)

    @contextmanager
    def time(self, bucket: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        start = perf_counter_ns()
        try:
            yield
        finally:
            self._timings_ms[bucket] += (perf_counter_ns() - start) / 1_000_000

    def increment(self, counter: str, amount: int = 1) -> None:
        if self.enabled:
            self._counters[counter] += amount

    def add_timing_ms(self, bucket: str, value: float) -> None:
        if self.enabled:
            self._timings_ms[bucket] += value

    def record_cache_hit(self, cache_name: str) -> None:
        if self.enabled:
            self._cache_hits[cache_name] += 1

    def record_cache_miss(self, cache_name: str) -> None:
        if self.enabled:
            self._cache_misses[cache_name] += 1

    def record_raster_source(self, *, layer_id: str, path: str, dataset: Any) -> None:
        if not self.enabled:
            return
        key = (layer_id, path)
        if key in self._raster_sources:
            return
        block_shapes = tuple(
            (int(shape[0]), int(shape[1]))
            for shape in tuple(getattr(dataset, "block_shapes", ()) or ())
            if len(shape) >= 2
        )
        band_count = int(getattr(dataset, "count", 0) or 0)
        overviews_by_band: list[tuple[int, ...]] = []
        for band_index in range(1, band_count + 1):
            try:
                overviews_by_band.append(
                    tuple(int(level) for level in dataset.overviews(band_index))
                )
            except Exception:  # noqa: BLE001 - diagnostics must not break rendering.
                overviews_by_band.append(())

        stat = _path_signature(path)
        self._raster_sources[key] = RasterSourceDiagnostics(
            layer_id=layer_id,
            path=path,
            width=int(getattr(dataset, "width", 0) or 0),
            height=int(getattr(dataset, "height", 0) or 0),
            band_count=band_count,
            crs=str(getattr(dataset, "crs", None)) if getattr(dataset, "crs", None) else None,
            block_shapes=block_shapes,
            overviews_by_band=tuple(overviews_by_band),
            file_size_bytes=stat[0],
            file_mtime_ns=stat[1],
        )

    def summary(self) -> RenderDiagnosticSummary:
        return RenderDiagnosticSummary(
            composition_id=self.composition_id,
            target_id=self.target_id,
            output_width=self.output_width,
            output_height=self.output_height,
            timings_ms=dict(self._timings_ms),
            counters=dict(self._counters),
            cache_hits=dict(self._cache_hits),
            cache_misses=dict(self._cache_misses),
            raster_sources=tuple(self._raster_sources.values()),
        )


def _path_signature(path: str) -> tuple[int | None, int | None]:
    try:
        stat = Path(path).stat()
    except OSError:
        return None, None
    return stat.st_size, stat.st_mtime_ns
