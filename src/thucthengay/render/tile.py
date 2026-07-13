"""Fixed map-space tile index and byte-budgeted tile cache contracts."""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Hashable
from dataclasses import dataclass, field
from threading import Lock

import numpy as np

from thucthengay.render.overview import RasterFileSignature, raster_file_signature
from thucthengay.render.spec import GeoWindow, RenderLayerRef, RenderSpec

WORLD_GEO_WINDOW = GeoWindow(min_lon=-180.0, min_lat=-90.0, max_lon=180.0, max_lat=90.0)
DEFAULT_TILE_SIZE_DEGREES = 0.05


@dataclass(frozen=True)
class TileGrid:
    """Fixed map-space grid used to derive stable tile coordinates."""

    extent: GeoWindow = field(default_factory=lambda: WORLD_GEO_WINDOW.model_copy())
    tile_width: float = DEFAULT_TILE_SIZE_DEGREES
    tile_height: float = DEFAULT_TILE_SIZE_DEGREES
    grid_id: str = "fixed"

    def __post_init__(self) -> None:
        if self.tile_width <= 0 or self.tile_height <= 0:
            msg = "Tile dimensions must be positive map-space values."
            raise ValueError(msg)


@dataclass(frozen=True)
class TileKey:
    """Stable identity for a decoded raster tile."""

    layer_id: str
    source_signature: RasterFileSignature
    lod: int
    x: int
    y: int
    grid_id: str = "fixed"


@dataclass(frozen=True)
class TileCoverage:
    """One visible tile and its fixed map-space bounds."""

    key: TileKey
    bounds: GeoWindow


@dataclass(frozen=True)
class TileCacheEntry:
    """Cached decoded tile pixels."""

    pixels: np.ndarray
    bounds: GeoWindow
    nbytes: int
    valid_mask: np.ndarray | None = None


class TileIndex:
    """Resolve viewport coverage against a fixed map-space tile grid."""

    def __init__(self, grid: TileGrid | None = None) -> None:
        self.grid = grid or TileGrid()

    def visible_tiles(
        self,
        viewport: GeoWindow,
        *,
        map_scale: float,
        layer_id: str,
        source_signature: RasterFileSignature,
    ) -> tuple[TileCoverage, ...]:
        """Return deterministic visible tile keys sorted by row and column."""

        clipped = _clip_window(viewport, self.grid.extent)
        if clipped is None:
            return ()
        lod = scale_to_lod(map_scale)
        min_x = self._tile_x(clipped.min_lon)
        max_x = self._tile_x(_exclusive_upper(clipped.max_lon, self.grid.extent.max_lon))
        min_y = self._tile_y(clipped.min_lat)
        max_y = self._tile_y(_exclusive_upper(clipped.max_lat, self.grid.extent.max_lat))
        tiles: list[TileCoverage] = []
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                bounds = self.tile_bounds(x, y)
                tiles.append(
                    TileCoverage(
                        key=TileKey(
                            layer_id=layer_id,
                            source_signature=source_signature,
                            lod=lod,
                            x=x,
                            y=y,
                            grid_id=self.grid.grid_id,
                        ),
                        bounds=bounds,
                    )
                )
        return tuple(tiles)

    def visible_tiles_for_layer(
        self,
        viewport: GeoWindow,
        *,
        map_scale: float,
        layer: RenderLayerRef,
    ) -> tuple[TileCoverage, ...]:
        path = layer.cache_path or layer.source_path
        source_signature = raster_file_signature(path)
        if layer.render_bands is not None:
            band_sig = "-".join(str(value) for value in layer.render_bands.signature())
            source_signature = RasterFileSignature(
                path=f"{source_signature.path}#bands:{band_sig}",
                size_bytes=source_signature.size_bytes,
                mtime_ns=source_signature.mtime_ns,
            )
        if layer.symbology is not None:
            symbology_sig = "-".join(str(value) for value in layer.symbology.signature())
            source_signature = RasterFileSignature(
                path=f"{source_signature.path}#symbology:{symbology_sig}",
                size_bytes=source_signature.size_bytes,
                mtime_ns=source_signature.mtime_ns,
            )
        return self.visible_tiles(
            viewport,
            map_scale=map_scale,
            layer_id=layer.layer_id,
            source_signature=source_signature,
        )

    def visible_tiles_for_spec(self, spec: RenderSpec) -> tuple[TileCoverage, ...]:
        """Resolve coverage for the normal visible layers of a render spec."""

        coverages: list[TileCoverage] = []
        for layer in sorted(spec.visible_layers, key=lambda item: (item.order, item.layer_id)):
            coverages.extend(
                self.visible_tiles_for_layer(
                    spec.geo_window,
                    map_scale=spec.view_scale,
                    layer=layer,
                )
            )
        return tuple(coverages)

    def tile_bounds(self, x: int, y: int) -> GeoWindow:
        min_lon = self.grid.extent.min_lon + x * self.grid.tile_width
        min_lat = self.grid.extent.min_lat + y * self.grid.tile_height
        return GeoWindow(
            min_lon=max(self.grid.extent.min_lon, min_lon),
            min_lat=max(self.grid.extent.min_lat, min_lat),
            max_lon=min(self.grid.extent.max_lon, min_lon + self.grid.tile_width),
            max_lat=min(self.grid.extent.max_lat, min_lat + self.grid.tile_height),
        )

    def _tile_x(self, lon: float) -> int:
        return math.floor((lon - self.grid.extent.min_lon) / self.grid.tile_width)

    def _tile_y(self, lat: float) -> int:
        return math.floor((lat - self.grid.extent.min_lat) / self.grid.tile_height)


class TileCache:
    """Thread-safe LRU cache for decoded tile arrays."""

    def __init__(self, *, max_bytes: int) -> None:
        self.max_bytes = max(0, int(max_bytes))
        self._used_bytes = 0
        self._entries: OrderedDict[TileKey, TileCacheEntry] = OrderedDict()
        self._lock = Lock()

    @property
    def used_bytes(self) -> int:
        with self._lock:
            return self._used_bytes

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def keys(self) -> tuple[TileKey, ...]:
        with self._lock:
            return tuple(self._entries.keys())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._used_bytes = 0

    def get(self, key: TileKey) -> TileCacheEntry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return TileCacheEntry(
                pixels=entry.pixels.copy(),
                bounds=entry.bounds,
                nbytes=entry.nbytes,
                valid_mask=entry.valid_mask.copy() if entry.valid_mask is not None else None,
            )

    def put(
        self,
        key: TileKey,
        pixels: np.ndarray,
        bounds: GeoWindow,
        *,
        valid_mask: np.ndarray | None = None,
    ) -> None:
        mask = None if valid_mask is None else valid_mask.astype(bool, copy=True)
        nbytes = int(pixels.nbytes + (0 if mask is None else mask.nbytes))
        if self.max_bytes <= 0 or nbytes > self.max_bytes:
            return
        entry = TileCacheEntry(
            pixels=pixels.copy(),
            bounds=bounds,
            nbytes=nbytes,
            valid_mask=mask,
        )
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._used_bytes -= old.nbytes
            self._entries[key] = entry
            self._used_bytes += nbytes
            self._evict_locked()

    def _evict_locked(self) -> None:
        while self._used_bytes > self.max_bytes and self._entries:
            _old_key, old = self._entries.popitem(last=False)
            self._used_bytes -= old.nbytes


def scale_to_lod(map_scale: float) -> int:
    """Convert map scale to a deterministic zoom bucket for tile identity."""

    if not math.isfinite(map_scale) or map_scale <= 0:
        msg = "map_scale must be a positive finite number."
        raise ValueError(msg)
    return max(0, int(math.floor(math.log2(map_scale))))


def tile_key_parts(key: TileKey) -> tuple[Hashable, ...]:
    """Return a tuple suitable for logging, serialization, or future cache bridges."""

    return (
        key.layer_id,
        key.source_signature.path,
        key.source_signature.size_bytes,
        key.source_signature.mtime_ns,
        key.lod,
        key.x,
        key.y,
        key.grid_id,
    )


def adaptive_tile_grid_for_viewport(
    viewport: GeoWindow,
    *,
    output_width: int,
    output_height: int,
    screen_tile_pixels: int,
    extent: GeoWindow | None = None,
) -> TileGrid:
    """Build a world-anchored grid sized from the current screen-space viewport.

    The grid remains anchored to the world extent so nearby pans at the same
    zoom reuse overlapping tile keys. The tile dimensions are derived from the
    current pane size to cap the number of visible jobs.
    """

    resolved_extent = extent or WORLD_GEO_WINDOW.model_copy()
    pixels = max(1, int(screen_tile_pixels))
    columns = max(1, math.ceil(max(1, int(output_width)) / pixels))
    rows = max(1, math.ceil(max(1, int(output_height)) / pixels))
    lon_span = max(viewport.max_lon - viewport.min_lon, 1e-12)
    lat_span = max(viewport.max_lat - viewport.min_lat, 1e-12)
    tile_width = lon_span / columns
    tile_height = lat_span / rows
    grid_id = (
        f"adaptive-screen:{columns}x{rows}:"
        f"{tile_width:.12g}:{tile_height:.12g}"
    )
    return TileGrid(
        extent=resolved_extent,
        tile_width=tile_width,
        tile_height=tile_height,
        grid_id=grid_id,
    )


def _clip_window(window: GeoWindow, extent: GeoWindow) -> GeoWindow | None:
    min_lon = max(window.min_lon, extent.min_lon)
    min_lat = max(window.min_lat, extent.min_lat)
    max_lon = min(window.max_lon, extent.max_lon)
    max_lat = min(window.max_lat, extent.max_lat)
    if min_lon >= max_lon or min_lat >= max_lat:
        return None
    return GeoWindow(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)


def _exclusive_upper(value: float, extent_max: float) -> float:
    if value >= extent_max:
        return math.nextafter(extent_max, -math.inf)
    return math.nextafter(value, -math.inf)
