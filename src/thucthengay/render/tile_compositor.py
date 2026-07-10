"""Compose cached raster tiles into a frame-agnostic GIS canvas."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from thucthengay.render.spec import GeoWindow
from thucthengay.render.tile import TileCache, TileCoverage, TileKey

DEFAULT_PARTIAL_REPAINT_THRESHOLD_PX = 96


@dataclass(frozen=True)
class TileFrameState:
    """Previous composed tile frame that may be reused during small pans."""

    viewport: GeoWindow
    map_scale: float
    canvas: np.ndarray


@dataclass(frozen=True)
class TileCompositorConfig:
    """Settings for cached tile composition."""

    width: int
    height: int
    background_rgb: tuple[int, int, int] = (255, 255, 255)
    partial_repaint_threshold_px: int = DEFAULT_PARTIAL_REPAINT_THRESHOLD_PX


@dataclass(frozen=True)
class TileComposedFrame:
    """Result of composing cached tiles for a viewport."""

    canvas: np.ndarray
    used_keys: tuple[TileKey, ...]
    missing: tuple[TileCoverage, ...]
    partial_repaint_used: bool = False
    full_recompose_used: bool = True


def compose_cached_tiles(
    *,
    viewport: GeoWindow,
    map_scale: float,
    coverages: tuple[TileCoverage, ...] | list[TileCoverage],
    cache: TileCache,
    config: TileCompositorConfig,
    previous: TileFrameState | None = None,
) -> TileComposedFrame:
    """Compose cached tile pixels into the requested canvas dimensions."""

    canvas, partial = _initial_canvas(
        viewport=viewport,
        map_scale=map_scale,
        config=config,
        previous=previous,
    )
    used: list[TileKey] = []
    missing: list[TileCoverage] = []
    for coverage in coverages:
        cached = cache.get(coverage.key)
        if cached is None:
            missing.append(coverage)
            continue
        if _draw_tile(canvas, viewport, coverage.bounds, cached.pixels, cached.valid_mask):
            used.append(coverage.key)
    return TileComposedFrame(
        canvas=canvas,
        used_keys=tuple(used),
        missing=tuple(missing),
        partial_repaint_used=partial,
        full_recompose_used=not partial,
    )


def pan_delta_pixels(
    *,
    previous_viewport: GeoWindow,
    current_viewport: GeoWindow,
    width: int,
    height: int,
) -> tuple[int, int]:
    """Return approximate pixel shift from previous viewport to current viewport."""

    lon_per_px = (previous_viewport.max_lon - previous_viewport.min_lon) / width
    lat_per_px = (previous_viewport.max_lat - previous_viewport.min_lat) / height
    delta_lon = current_viewport.min_lon - previous_viewport.min_lon
    delta_lat = current_viewport.min_lat - previous_viewport.min_lat
    return int(round(-delta_lon / lon_per_px)), int(round(delta_lat / lat_per_px))


def _initial_canvas(
    *,
    viewport: GeoWindow,
    map_scale: float,
    config: TileCompositorConfig,
    previous: TileFrameState | None,
) -> tuple[np.ndarray, bool]:
    if previous is not None and _can_partial_repaint(
        previous=previous,
        viewport=viewport,
        map_scale=map_scale,
        config=config,
    ):
        dx, dy = pan_delta_pixels(
            previous_viewport=previous.viewport,
            current_viewport=viewport,
            width=config.width,
            height=config.height,
        )
        return _shift_canvas(
            previous.canvas,
            dx=dx,
            dy=dy,
            background_rgb=config.background_rgb,
        ), True
    return _blank_canvas(config), False


def _can_partial_repaint(
    *,
    previous: TileFrameState,
    viewport: GeoWindow,
    map_scale: float,
    config: TileCompositorConfig,
) -> bool:
    if previous.canvas.shape[:2] != (config.height, config.width):
        return False
    if previous.map_scale != map_scale:
        return False
    dx, dy = pan_delta_pixels(
        previous_viewport=previous.viewport,
        current_viewport=viewport,
        width=config.width,
        height=config.height,
    )
    return max(abs(dx), abs(dy)) <= config.partial_repaint_threshold_px


def _blank_canvas(config: TileCompositorConfig) -> np.ndarray:
    canvas = np.zeros((config.height, config.width, 3), dtype=np.uint8)
    canvas[:, :] = np.array(config.background_rgb, dtype=np.uint8)
    return canvas


def _shift_canvas(
    canvas: np.ndarray,
    *,
    dx: int,
    dy: int,
    background_rgb: tuple[int, int, int],
) -> np.ndarray:
    shifted = np.zeros_like(canvas)
    shifted[:, :] = np.array(background_rgb, dtype=np.uint8)
    height, width = canvas.shape[:2]
    src_x0 = max(0, -dx)
    src_x1 = min(width, width - dx)
    dst_x0 = max(0, dx)
    dst_x1 = min(width, width + dx)
    src_y0 = max(0, -dy)
    src_y1 = min(height, height - dy)
    dst_y0 = max(0, dy)
    dst_y1 = min(height, height + dy)
    if src_x0 < src_x1 and src_y0 < src_y1 and dst_x0 < dst_x1 and dst_y0 < dst_y1:
        shifted[dst_y0:dst_y1, dst_x0:dst_x1] = canvas[src_y0:src_y1, src_x0:src_x1]
    return shifted


def _draw_tile(
    canvas: np.ndarray,
    viewport: GeoWindow,
    tile_bounds: GeoWindow,
    pixels: np.ndarray,
    valid_mask: np.ndarray | None,
) -> bool:
    overlap = _intersection(viewport, tile_bounds)
    if overlap is None:
        return False
    dst = _geo_to_pixel_rect(viewport, overlap, canvas.shape[1], canvas.shape[0])
    src = _geo_to_pixel_rect(tile_bounds, overlap, pixels.shape[1], pixels.shape[0])
    dst_row0, dst_row1, dst_col0, dst_col1 = dst
    src_row0, src_row1, src_col0, src_col1 = src
    if dst_row0 >= dst_row1 or dst_col0 >= dst_col1:
        return False
    tile_slice = pixels[src_row0:src_row1, src_col0:src_col1]
    if tile_slice.size == 0:
        return False
    resized_tile = _resize_nearest(
        tile_slice,
        height=dst_row1 - dst_row0,
        width=dst_col1 - dst_col0,
    )
    target = canvas[dst_row0:dst_row1, dst_col0:dst_col1]
    if valid_mask is None:
        target[:] = resized_tile
        return True

    mask_slice = valid_mask[src_row0:src_row1, src_col0:src_col1]
    resized_mask = _resize_nearest_mask(
        mask_slice,
        height=dst_row1 - dst_row0,
        width=dst_col1 - dst_col0,
    )
    if not resized_mask.any():
        return False
    target[resized_mask] = resized_tile[resized_mask]
    return True


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
    col0 = int(np.floor((bounds.min_lon - reference.min_lon) / lon_span * width))
    col1 = int(np.ceil((bounds.max_lon - reference.min_lon) / lon_span * width))
    row0 = int(np.floor((reference.max_lat - bounds.max_lat) / lat_span * height))
    row1 = int(np.ceil((reference.max_lat - bounds.min_lat) / lat_span * height))
    return (
        max(0, min(height, row0)),
        max(0, min(height, row1)),
        max(0, min(width, col0)),
        max(0, min(width, col1)),
    )


def _resize_nearest(pixels: np.ndarray, *, height: int, width: int) -> np.ndarray:
    if pixels.shape[0] == height and pixels.shape[1] == width:
        return pixels
    row_idx = np.linspace(0, pixels.shape[0] - 1, height).round().astype(int)
    col_idx = np.linspace(0, pixels.shape[1] - 1, width).round().astype(int)
    return pixels[row_idx][:, col_idx]


def _resize_nearest_mask(mask: np.ndarray, *, height: int, width: int) -> np.ndarray:
    if mask.shape[0] == height and mask.shape[1] == width:
        return mask.astype(bool, copy=False)
    row_idx = np.linspace(0, mask.shape[0] - 1, height).round().astype(int)
    col_idx = np.linspace(0, mask.shape[1] - 1, width).round().astype(int)
    return mask[row_idx][:, col_idx].astype(bool, copy=False)
