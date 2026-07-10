"""Tile decode scheduling and cooperative cancellation contracts."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

from thucthengay.gis.crs import GEOGRAPHIC_CRS, normalize_crs_key
from thucthengay.render.spec import GeoWindow, RenderLayerRef
from thucthengay.render.tile import TileCache, TileCoverage, TileKey

DEFAULT_DECODE_TILE_PIXELS = 256

CancelCallback = Callable[[], bool]
DatasetOpener = Callable[[str], Any]


class TileDecodeState(StrEnum):
    """Terminal state for one tile decode job."""

    SUCCESS = "success"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class TileDecodeJob:
    """One scheduled tile decode request."""

    request_id: str
    revision: int
    coverage: TileCoverage
    source_path: str
    output_width: int = DEFAULT_DECODE_TILE_PIXELS
    output_height: int = DEFAULT_DECODE_TILE_PIXELS
    priority: float = 0.0


@dataclass(frozen=True)
class TileDecodeResult:
    """Decoded tile result that can be conditionally applied to cache."""

    request_id: str
    revision: int
    key: TileKey
    bounds: GeoWindow
    state: TileDecodeState
    pixels: np.ndarray | None = None
    valid_mask: np.ndarray | None = None
    message: str = ""


class TileScheduler:
    """Headless tile scheduler with stale-result filtering."""

    def __init__(self, *, cache: TileCache) -> None:
        self.cache = cache
        self._revision = 0
        self._active_request_id: str | None = None

    @property
    def revision(self) -> int:
        return self._revision

    def begin_request(self, request_id: str) -> int:
        self._revision += 1
        self._active_request_id = request_id
        return self._revision

    def queue_missing(
        self,
        *,
        request_id: str,
        viewport: GeoWindow,
        layers: tuple[RenderLayerRef, ...] | list[RenderLayerRef],
        coverages: tuple[TileCoverage, ...] | list[TileCoverage],
        tile_pixels: int = DEFAULT_DECODE_TILE_PIXELS,
    ) -> tuple[TileDecodeJob, ...]:
        """Return center-prioritized jobs for tiles not already in cache."""

        revision = self._revision
        layer_paths = {layer.layer_id: layer.cache_path or layer.source_path for layer in layers}
        center_lon = (viewport.min_lon + viewport.max_lon) / 2.0
        center_lat = (viewport.min_lat + viewport.max_lat) / 2.0
        jobs: list[TileDecodeJob] = []
        for coverage in coverages:
            if self.cache.get(coverage.key) is not None:
                continue
            source_path = layer_paths.get(coverage.key.layer_id)
            if not source_path:
                continue
            priority = _distance_to_center(coverage.bounds, center_lon, center_lat)
            jobs.append(
                TileDecodeJob(
                    request_id=request_id,
                    revision=revision,
                    coverage=coverage,
                    source_path=source_path,
                    output_width=max(1, int(tile_pixels)),
                    output_height=max(1, int(tile_pixels)),
                    priority=priority,
                )
            )
        return tuple(
            sorted(
                jobs,
                key=lambda job: (job.priority, job.coverage.key.y, job.coverage.key.x),
            )
        )

    def is_stale(self, result_or_job: TileDecodeJob | TileDecodeResult) -> bool:
        return (
            result_or_job.revision != self._revision
            or result_or_job.request_id != self._active_request_id
        )

    def apply_result(self, result: TileDecodeResult) -> bool:
        """Cache successful results only when they belong to the latest request."""

        if self.is_stale(result):
            return False
        if result.state != TileDecodeState.SUCCESS or result.pixels is None:
            return False
        self.cache.put(result.key, result.pixels, result.bounds, valid_mask=result.valid_mask)
        return True


def decode_tile_job(
    job: TileDecodeJob,
    *,
    opener: DatasetOpener = rasterio.open,
    is_cancelled: CancelCallback | None = None,
) -> TileDecodeResult:
    """Decode one tile by reading only the tile's raster window into tile output size."""

    if _is_cancelled(is_cancelled):
        return _tile_result(job, TileDecodeState.CANCELLED, message="Tile decode cancelled.")
    try:
        with opener(job.source_path) as dataset:
            if _is_cancelled(is_cancelled):
                return _tile_result(
                    job,
                    TileDecodeState.CANCELLED,
                    message="Tile decode cancelled.",
                )
            tile = _read_dataset_tile(dataset, job, is_cancelled=is_cancelled)
            if _is_cancelled(is_cancelled):
                return _tile_result(
                    job,
                    TileDecodeState.CANCELLED,
                    message="Tile decode cancelled.",
                )
            if tile is None:
                return _tile_result(
                    job,
                    TileDecodeState.SKIPPED,
                    message="Tile outside raster bounds.",
                )
            pixels, valid_mask = tile
            return _tile_result(
                job,
                TileDecodeState.SUCCESS,
                pixels=pixels,
                valid_mask=valid_mask,
            )
    except Exception as exc:  # noqa: BLE001 - one bad tile should not crash the scheduler.
        return _tile_result(job, TileDecodeState.ERROR, message=str(exc))


def _read_dataset_tile(
    dataset: Any,
    job: TileDecodeJob,
    *,
    is_cancelled: CancelCallback | None,
) -> tuple[np.ndarray, np.ndarray] | None:
    src = _geographic_dataset(dataset)
    close_src = src is not dataset
    try:
        bounds = job.coverage.bounds
        raster_bounds = getattr(src, "bounds", None)
        read_bounds = bounds
        dst_row0 = 0
        dst_row1 = job.output_height
        dst_col0 = 0
        dst_col1 = job.output_width
        if raster_bounds is not None:
            overlap = _intersection(bounds, _bounds_to_window(raster_bounds))
            if overlap is None:
                return None
            read_bounds = overlap
            dst_row0, dst_row1, dst_col0, dst_col1 = _geo_to_pixel_rect(
                bounds,
                overlap,
                job.output_width,
                job.output_height,
            )
            if dst_row0 >= dst_row1 or dst_col0 >= dst_col1:
                return None
        read_window = from_bounds(
            read_bounds.min_lon,
            read_bounds.min_lat,
            read_bounds.max_lon,
            read_bounds.max_lat,
            transform=src.transform,
        )
        band_indexes, alpha_index = _resolve_band_indexes(src)
        if _is_cancelled(is_cancelled):
            return None
        read_height = dst_row1 - dst_row0
        read_width = dst_col1 - dst_col0
        data = src.read(
            indexes=band_indexes,
            window=read_window,
            out_shape=(len(band_indexes), read_height, read_width),
            resampling=Resampling.bilinear,
            masked=True,
        )
        if _is_cancelled(is_cancelled):
            return None
        masked_data = np.ma.asarray(data)
        mask = np.ma.getmaskarray(masked_data).any(axis=0)
        if alpha_index is not None:
            alpha = src.read(
                alpha_index,
                window=read_window,
                out_shape=(read_height, read_width),
                resampling=Resampling.nearest,
                masked=True,
            )
            mask = np.logical_or(mask, np.ma.asarray(alpha).filled(0) <= 0)
        if len(band_indexes) == 1:
            rgb = np.repeat(_scale_to_uint8(masked_data), 3, axis=0)
        else:
            rgb = _scale_to_uint8(masked_data)
        pixels = np.zeros((job.output_height, job.output_width, 3), dtype=np.uint8)
        valid_mask = np.zeros((job.output_height, job.output_width), dtype=bool)
        read_pixels = np.transpose(rgb, (1, 2, 0))
        read_valid = ~mask
        read_pixels[mask, :] = 0
        pixels[dst_row0:dst_row1, dst_col0:dst_col1, :] = read_pixels
        valid_mask[dst_row0:dst_row1, dst_col0:dst_col1] = read_valid
        return pixels, valid_mask
    finally:
        if close_src:
            src.close()


def _geographic_dataset(dataset: Any) -> Any:
    raster_crs = normalize_crs_key(getattr(dataset, "crs", None))
    if raster_crs == GEOGRAPHIC_CRS:
        return dataset
    return WarpedVRT(dataset, crs=GEOGRAPHIC_CRS, resampling=Resampling.bilinear, warp_mem_limit=64)


def _resolve_band_indexes(src: Any) -> tuple[tuple[int, ...], int | None]:
    colorinterp = tuple(getattr(src, "colorinterp", ()) or ())
    alpha_index = None
    for index, interp in enumerate(colorinterp, start=1):
        if interp == ColorInterp.alpha:
            alpha_index = index
            break
    rgb_indexes: list[int] = []
    for desired in (ColorInterp.red, ColorInterp.green, ColorInterp.blue):
        if desired in colorinterp:
            rgb_indexes.append(colorinterp.index(desired) + 1)
    if len(rgb_indexes) == 3:
        return tuple(rgb_indexes), alpha_index
    if ColorInterp.gray in colorinterp:
        return (colorinterp.index(ColorInterp.gray) + 1,), alpha_index
    count = int(getattr(src, "count", 0) or 0)
    if count >= 3:
        return (1, 2, 3), alpha_index
    return (1,), alpha_index


def _scale_to_uint8(data: np.ma.MaskedArray | np.ndarray) -> np.ndarray:
    source = np.ma.asarray(data)
    if source.dtype == np.uint8:
        return source.filled(0).astype(np.uint8, copy=False)
    valid = source.compressed()
    if valid.size == 0:
        return np.zeros(source.shape, dtype=np.uint8)
    if np.issubdtype(source.dtype, np.integer):
        dtype_info = np.iinfo(source.dtype)
        scaled = source.astype(np.float32) / float(dtype_info.max) * 255.0
    else:
        finite = valid[np.isfinite(valid)]
        if finite.size == 0:
            return np.zeros(source.shape, dtype=np.uint8)
        min_value = float(finite.min())
        max_value = float(finite.max())
        if min_value >= 0.0 and max_value <= 1.0:
            scaled = source.astype(np.float32) * 255.0
        elif max_value > min_value:
            scaled = (source.astype(np.float32) - min_value) / (max_value - min_value) * 255.0
        else:
            scaled = np.ma.zeros(source.shape, dtype=np.float32)
    return np.ma.clip(scaled, 0, 255).filled(0).astype(np.uint8)


def _tile_result(
    job: TileDecodeJob,
    state: TileDecodeState,
    *,
    pixels: np.ndarray | None = None,
    valid_mask: np.ndarray | None = None,
    message: str = "",
) -> TileDecodeResult:
    return TileDecodeResult(
        request_id=job.request_id,
        revision=job.revision,
        key=job.coverage.key,
        bounds=job.coverage.bounds,
        state=state,
        pixels=pixels,
        valid_mask=valid_mask,
        message=message,
    )


def _distance_to_center(bounds: GeoWindow, center_lon: float, center_lat: float) -> float:
    tile_lon = (bounds.min_lon + bounds.max_lon) / 2.0
    tile_lat = (bounds.min_lat + bounds.max_lat) / 2.0
    return math.hypot(tile_lon - center_lon, tile_lat - center_lat)


def _intersects(bounds: GeoWindow, raster_bounds: Any) -> bool:
    left, bottom, right, top = _bounds_tuple(raster_bounds)
    return not (
        bounds.max_lon <= left
        or bounds.min_lon >= right
        or bounds.max_lat <= bottom
        or bounds.min_lat >= top
    )


def _intersection(a: GeoWindow, b: GeoWindow) -> GeoWindow | None:
    min_lon = max(a.min_lon, b.min_lon)
    min_lat = max(a.min_lat, b.min_lat)
    max_lon = min(a.max_lon, b.max_lon)
    max_lat = min(a.max_lat, b.max_lat)
    if min_lon >= max_lon or min_lat >= max_lat:
        return None
    return GeoWindow(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)


def _geo_to_pixel_rect(
    reference: GeoWindow,
    bounds: GeoWindow,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    lon_span = reference.max_lon - reference.min_lon
    lat_span = reference.max_lat - reference.min_lat
    col0 = int(math.floor((bounds.min_lon - reference.min_lon) / lon_span * width))
    col1 = int(math.ceil((bounds.max_lon - reference.min_lon) / lon_span * width))
    row0 = int(math.floor((reference.max_lat - bounds.max_lat) / lat_span * height))
    row1 = int(math.ceil((reference.max_lat - bounds.min_lat) / lat_span * height))
    return (
        max(0, min(height, row0)),
        max(0, min(height, row1)),
        max(0, min(width, col0)),
        max(0, min(width, col1)),
    )


def _bounds_to_window(raster_bounds: Any) -> GeoWindow:
    left, bottom, right, top = _bounds_tuple(raster_bounds)
    return GeoWindow(min_lon=left, min_lat=bottom, max_lon=right, max_lat=top)


def _bounds_tuple(raster_bounds: Any) -> tuple[float, float, float, float]:
    if all(hasattr(raster_bounds, name) for name in ("left", "bottom", "right", "top")):
        return (
            float(raster_bounds.left),
            float(raster_bounds.bottom),
            float(raster_bounds.right),
            float(raster_bounds.top),
        )
    return (
        float(raster_bounds[0]),
        float(raster_bounds[1]),
        float(raster_bounds[2]),
        float(raster_bounds[3]),
    )


def _is_cancelled(is_cancelled: CancelCallback | None) -> bool:
    return is_cancelled is not None and is_cancelled()
