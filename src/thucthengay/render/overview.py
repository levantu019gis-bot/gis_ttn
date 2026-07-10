"""COG/overview readiness helpers for raster render performance work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import rasterio
from rasterio.enums import Resampling

from thucthengay.render.spec import RenderSpec

DEFAULT_EXPENSIVE_DIMENSION_THRESHOLD = 4096
DEFAULT_EXPENSIVE_PIXEL_THRESHOLD = 16_000_000
DEFAULT_OVERVIEW_LEVELS = (2, 4, 8, 16)


class RasterReadinessStatus(StrEnum):
    """High-level overview/COG readiness state for a raster source."""

    READY = "ready"
    NEEDS_OVERVIEWS = "needs_overviews"
    NEEDS_COG = "needs_cog"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class RasterFileSignature:
    """Stable cache key for metadata that changes when the file changes."""

    path: str
    size_bytes: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class RasterOverviewReadiness:
    """Read-only raster metadata and readiness classification."""

    path: str
    signature: RasterFileSignature
    status: RasterReadinessStatus
    notes: tuple[str, ...] = ()
    width: int | None = None
    height: int | None = None
    band_count: int | None = None
    driver: str | None = None
    dtype: str | None = None
    crs: str | None = None
    block_shapes: tuple[tuple[int, int], ...] = ()
    overviews_by_band: tuple[tuple[int, ...], ...] = ()
    is_tiled: bool = False
    likely_expensive_to_zoom_out: bool = False

    @property
    def pixel_count(self) -> int | None:
        if self.width is None or self.height is None:
            return None
        return self.width * self.height

    @property
    def max_dimension(self) -> int | None:
        if self.width is None or self.height is None:
            return None
        return max(self.width, self.height)

    @property
    def has_usable_overviews(self) -> bool:
        return any(level > 1 for levels in self.overviews_by_band for level in levels)

    @property
    def overview_levels(self) -> tuple[int, ...]:
        levels = sorted({level for band_levels in self.overviews_by_band for level in band_levels})
        return tuple(int(level) for level in levels if level > 1)


@dataclass(frozen=True)
class RasterOverviewPreparationPlan:
    """Plan for creating prepared raster output without mutating sources by default."""

    source_path: str
    output_path: str | None
    mutate_source: bool = False
    create_cog: bool = False
    overview_levels: tuple[int, ...] = DEFAULT_OVERVIEW_LEVELS
    notes: tuple[str, ...] = ()

    @property
    def will_mutate_source(self) -> bool:
        return self.mutate_source and self.output_path == self.source_path


class RasterOverviewReadinessCache:
    """Small metadata cache keyed by path, size, and mtime."""

    def __init__(self) -> None:
        self._entries: dict[RasterFileSignature, RasterOverviewReadiness] = {}

    def inspect(
        self,
        path: str | Path,
        *,
        expensive_dimension_threshold: int = DEFAULT_EXPENSIVE_DIMENSION_THRESHOLD,
        expensive_pixel_threshold: int = DEFAULT_EXPENSIVE_PIXEL_THRESHOLD,
    ) -> RasterOverviewReadiness:
        signature = raster_file_signature(path)
        cached = self._entries.get(signature)
        if cached is not None:
            return cached
        result = _inspect_raster_overview_readiness(
            path,
            signature=signature,
            expensive_dimension_threshold=expensive_dimension_threshold,
            expensive_pixel_threshold=expensive_pixel_threshold,
        )
        self._entries[signature] = result
        return result

    def clear(self) -> None:
        self._entries.clear()


def raster_file_signature(path: str | Path) -> RasterFileSignature:
    raster_path = Path(path)
    try:
        stat = raster_path.stat()
    except OSError:
        return RasterFileSignature(path=str(raster_path), size_bytes=None, mtime_ns=None)
    return RasterFileSignature(
        path=str(raster_path),
        size_bytes=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
    )


def inspect_raster_overview_readiness(
    path: str | Path,
    *,
    cache: RasterOverviewReadinessCache | None = None,
    expensive_dimension_threshold: int = DEFAULT_EXPENSIVE_DIMENSION_THRESHOLD,
    expensive_pixel_threshold: int = DEFAULT_EXPENSIVE_PIXEL_THRESHOLD,
) -> RasterOverviewReadiness:
    """Inspect one raster path and classify overview/COG readiness."""

    if cache is not None:
        return cache.inspect(
            path,
            expensive_dimension_threshold=expensive_dimension_threshold,
            expensive_pixel_threshold=expensive_pixel_threshold,
        )
    signature = raster_file_signature(path)
    return _inspect_raster_overview_readiness(
        path,
        signature=signature,
        expensive_dimension_threshold=expensive_dimension_threshold,
        expensive_pixel_threshold=expensive_pixel_threshold,
    )


def inspect_render_spec_overview_readiness(
    spec: RenderSpec,
    *,
    cache: RasterOverviewReadinessCache | None = None,
) -> tuple[RasterOverviewReadiness, ...]:
    """Inspect the raster sources used by a render spec, including compare panes."""

    paths: list[str] = []
    seen: set[str] = set()
    for layer in list(spec.visible_layers) + list(spec.temporal_compare.pane_a.layers) + list(
        spec.temporal_compare.pane_b.layers
    ):
        path = layer.cache_path or layer.source_path
        if path and path not in seen:
            paths.append(path)
            seen.add(path)
    return tuple(inspect_raster_overview_readiness(path, cache=cache) for path in paths)


def build_raster_preparation_plan(
    source_path: str | Path,
    *,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    mutate_source: bool = False,
    create_cog: bool = False,
    overview_levels: tuple[int, ...] = DEFAULT_OVERVIEW_LEVELS,
) -> RasterOverviewPreparationPlan:
    """Build an explicit non-mutating plan for prepared raster output."""

    source = Path(source_path)
    notes: list[str] = []
    if mutate_source:
        destination: Path | None = source
        notes.append("Explicit source mutation requested.")
    elif output_path is not None:
        destination = Path(output_path)
        notes.append("Prepared output will be written to the explicit output path.")
    elif output_dir is not None:
        destination = Path(output_dir) / source.name
        notes.append("Prepared output will be written under the configured output directory.")
    else:
        destination = None
        notes.append("No output path selected; source imagery will not be modified.")
    if not create_cog:
        notes.append("Plan will create tiled GeoTIFF output with internal overviews.")
    else:
        notes.append("Plan will request COG output when supported by the rasterio/GDAL build.")
    return RasterOverviewPreparationPlan(
        source_path=str(source),
        output_path=str(destination) if destination is not None else None,
        mutate_source=mutate_source,
        create_cog=create_cog,
        overview_levels=tuple(int(level) for level in overview_levels if int(level) > 1),
        notes=tuple(notes),
    )


def prepare_raster_overview_output(
    plan: RasterOverviewPreparationPlan,
    *,
    resampling: Resampling = Resampling.nearest,
    fallback_to_tiled_geotiff: bool = True,
) -> RasterOverviewReadiness:
    """Create prepared raster output according to a plan and inspect the result."""

    if plan.output_path is None:
        msg = "Preparation requires output_path, output_dir, or explicit mutate_source=True."
        raise ValueError(msg)
    source = Path(plan.source_path)
    destination = Path(plan.output_path)
    if not plan.mutate_source and source.resolve() == destination.resolve():
        msg = "Refusing to overwrite the source without mutate_source=True."
        raise ValueError(msg)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if plan.create_cog:
        try:
            _copy_as_cog(source, destination, resampling=resampling)
            return inspect_raster_overview_readiness(destination)
        except Exception:  # noqa: BLE001 - fall back when GDAL lacks COG support.
            if not fallback_to_tiled_geotiff:
                raise

    _copy_as_tiled_geotiff_with_overviews(
        source,
        destination,
        overview_levels=plan.overview_levels,
        resampling=resampling,
    )
    return inspect_raster_overview_readiness(destination)


def _inspect_raster_overview_readiness(
    path: str | Path,
    *,
    signature: RasterFileSignature,
    expensive_dimension_threshold: int,
    expensive_pixel_threshold: int,
) -> RasterOverviewReadiness:
    raster_path = Path(path)
    try:
        with rasterio.open(raster_path) as dataset:
            overviews_by_band = tuple(
                tuple(int(level) for level in dataset.overviews(index))
                for index in range(1, int(dataset.count) + 1)
            )
            block_shapes = tuple(
                (int(shape[0]), int(shape[1]))
                for shape in tuple(getattr(dataset, "block_shapes", ()) or ())
                if len(shape) >= 2
            )
            is_tiled = bool(dataset.profile.get("tiled"))
            width = int(dataset.width)
            height = int(dataset.height)
            likely_expensive = (
                max(width, height) >= expensive_dimension_threshold
                or width * height >= expensive_pixel_threshold
            )
            has_overviews = any(level > 1 for levels in overviews_by_band for level in levels)
            status, notes = _classify_readiness(
                driver=str(dataset.driver or ""),
                is_tiled=is_tiled,
                has_overviews=has_overviews,
                likely_expensive=likely_expensive,
            )
            return RasterOverviewReadiness(
                path=str(raster_path),
                signature=signature,
                status=status,
                notes=tuple(notes),
                width=width,
                height=height,
                band_count=int(dataset.count),
                driver=str(dataset.driver or ""),
                dtype=str(dataset.dtypes[0]) if dataset.dtypes else None,
                crs=str(dataset.crs) if dataset.crs else None,
                block_shapes=block_shapes,
                overviews_by_band=overviews_by_band,
                is_tiled=is_tiled,
                likely_expensive_to_zoom_out=likely_expensive,
            )
    except Exception as exc:  # noqa: BLE001 - report unreadable instead of raising.
        return RasterOverviewReadiness(
            path=str(raster_path),
            signature=signature,
            status=RasterReadinessStatus.UNREADABLE,
            notes=(f"Raster cannot be opened: {exc}",),
        )


def _classify_readiness(
    *,
    driver: str,
    is_tiled: bool,
    has_overviews: bool,
    likely_expensive: bool,
) -> tuple[RasterReadinessStatus, list[str]]:
    notes: list[str] = []
    is_geotiff = driver.upper() in {"GTIFF", "COG"}
    if not is_geotiff or not is_tiled:
        notes.append("Create a separate tiled GeoTIFF/COG output before tile-based rendering.")
        if not has_overviews:
            notes.append("Prepared output should include overview levels such as 2, 4, 8, 16.")
        return RasterReadinessStatus.NEEDS_COG, notes
    if not has_overviews:
        notes.append("Create overview levels on a separate prepared output or external sidecar.")
        if likely_expensive:
            notes.append("Raster is likely expensive to zoom out without overview pyramids.")
        else:
            notes.append("Raster is small, but overview metadata is still absent.")
        return RasterReadinessStatus.NEEDS_OVERVIEWS, notes
    notes.append("Raster has tiled GeoTIFF layout and usable overview levels.")
    if likely_expensive:
        notes.append("Overview pyramid should help zoomed-out reads avoid full-resolution decode.")
    return RasterReadinessStatus.READY, notes


def _copy_as_cog(source: Path, destination: Path, *, resampling: Resampling) -> None:
    import rasterio.shutil

    rasterio.shutil.copy(
        str(source),
        str(destination),
        driver="COG",
        overview_resampling=resampling.name.upper(),
        compress="DEFLATE",
        blocksize=256,
    )


def _copy_as_tiled_geotiff_with_overviews(
    source: Path,
    destination: Path,
    *,
    overview_levels: tuple[int, ...],
    resampling: Resampling,
) -> None:
    with rasterio.open(source) as src:
        block_size = 256 if max(src.width, src.height) >= 256 else 16
        profile: dict[str, Any] = dict(src.profile)
        profile.update(
            driver="GTiff",
            tiled=True,
            blockxsize=block_size,
            blockysize=block_size,
            compress=profile.get("compress") or "DEFLATE",
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(destination, "w", **profile) as dst:
            for _, window in src.block_windows(1):
                dst.write(src.read(window=window), window=window)
            levels = tuple(level for level in overview_levels if level < min(src.width, src.height))
            if levels:
                dst.build_overviews(levels, resampling)
                dst.update_tags(ns="rio_overview", resampling=resampling.name.lower())
