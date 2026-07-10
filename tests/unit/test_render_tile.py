"""Tests for Story 11.3 fixed tile index and tile cache contracts."""

from __future__ import annotations

import numpy as np

from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    RasterFileSignature,
    RenderBackground,
    RenderLayerRef,
    RenderSpec,
    TileCache,
    TileGrid,
    TileIndex,
    TileKey,
    raster_file_signature,
    scale_to_lod,
    tile_key_parts,
)


def _signature(path: str = "source.tif", size: int = 100, mtime: int = 200) -> RasterFileSignature:
    return RasterFileSignature(path=path, size_bytes=size, mtime_ns=mtime)


def _spec(path: str) -> RenderSpec:
    return RenderSpec(
        composition_id="tgt__20260710",
        target_id="tgt",
        output_width=256,
        output_height=144,
        view_center=[106.5, 10.5],
        view_scale=50000,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=640 / 360,
        geo_window=GeoWindow(min_lon=106.0, min_lat=10.0, max_lon=107.0, max_lat=11.0),
        visible_layers=[
            RenderLayerRef(layer_id="L1", source_path=path, cache_path=path, order=0)
        ],
        grid=GridConfig(interval=GridInterval(minutes=30), label_format="dms_full"),
        background=RenderBackground(color="#112233"),
        template_metadata_file="t.json",
        template_pptx="t.pptx",
        slide_index=0,
    )


def test_tile_index_returns_deterministic_keys_independent_from_widget_frame() -> None:
    index = TileIndex(
        TileGrid(
            extent=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=10.0, max_lat=10.0),
            tile_width=1.0,
            tile_height=1.0,
        )
    )
    viewport = GeoWindow(min_lon=2.1, min_lat=3.2, max_lon=4.9, max_lat=5.8)
    signature = _signature()

    first = index.visible_tiles(
        viewport,
        map_scale=50000,
        layer_id="L1",
        source_signature=signature,
    )
    second = index.visible_tiles(
        viewport,
        map_scale=50000,
        layer_id="L1",
        source_signature=signature,
    )

    assert [tile.key for tile in first] == [tile.key for tile in second]
    assert [(tile.key.x, tile.key.y) for tile in first] == [
        (2, 3),
        (3, 3),
        (4, 3),
        (2, 4),
        (3, 4),
        (4, 4),
        (2, 5),
        (3, 5),
        (4, 5),
    ]
    assert all(tile.key.lod == scale_to_lod(50000) for tile in first)
    assert first[0].bounds == GeoWindow(min_lon=2.0, min_lat=3.0, max_lon=3.0, max_lat=4.0)


def test_nearby_pan_positions_reuse_overlapping_map_space_tile_keys() -> None:
    index = TileIndex(
        TileGrid(
            extent=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=10.0, max_lat=10.0),
            tile_width=1.0,
            tile_height=1.0,
        )
    )
    signature = _signature()
    original = index.visible_tiles(
        GeoWindow(min_lon=2.1, min_lat=2.1, max_lon=4.9, max_lat=4.9),
        map_scale=25000,
        layer_id="L1",
        source_signature=signature,
    )
    panned = index.visible_tiles(
        GeoWindow(min_lon=2.9, min_lat=2.1, max_lon=5.7, max_lat=4.9),
        map_scale=25000,
        layer_id="L1",
        source_signature=signature,
    )

    original_keys = {tile.key for tile in original}
    panned_keys = {tile.key for tile in panned}

    assert original_keys & panned_keys == {
        TileKey("L1", signature, scale_to_lod(25000), x, y)
        for x in (2, 3, 4)
        for y in (2, 3, 4)
    }
    assert panned_keys - original_keys == {
        TileKey("L1", signature, scale_to_lod(25000), 5, y) for y in (2, 3, 4)
    }


def test_tile_cache_evicts_least_recently_used_entries_by_byte_budget() -> None:
    cache = TileCache(max_bytes=12)
    bounds = GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0)
    signature = _signature()
    keys = [TileKey("L1", signature, 1, x, 0) for x in range(4)]

    cache.put(keys[0], np.full((2, 2), 1, dtype=np.uint8), bounds)
    cache.put(keys[1], np.full((2, 2), 2, dtype=np.uint8), bounds)
    cache.put(keys[2], np.full((2, 2), 3, dtype=np.uint8), bounds)
    assert cache.used_bytes == 12

    assert cache.get(keys[0]) is not None
    cache.put(keys[3], np.full((2, 2), 4, dtype=np.uint8), bounds)

    assert cache.get(keys[1]) is None
    assert cache.get(keys[0]) is not None
    assert cache.get(keys[2]) is not None
    assert cache.get(keys[3]) is not None
    assert cache.entry_count == 3
    assert cache.used_bytes == 12


def test_tile_cache_copies_arrays_on_put_and_get() -> None:
    cache = TileCache(max_bytes=100)
    bounds = GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0)
    key = TileKey("L1", _signature(), 1, 0, 0)
    pixels = np.full((2, 2), 7, dtype=np.uint8)

    cache.put(key, pixels, bounds)
    pixels[:, :] = 1
    first = cache.get(key)
    assert first is not None
    assert np.all(first.pixels == 7)

    first.pixels[:, :] = 2
    second = cache.get(key)
    assert second is not None
    assert np.all(second.pixels == 7)


def test_file_signature_changes_make_tile_keys_different(tmp_path) -> None:
    raster_path = tmp_path / "source.tif"
    raster_path.write_bytes(b"first")
    first_signature = raster_file_signature(raster_path)
    raster_path.write_bytes(b"second-version")
    second_signature = raster_file_signature(raster_path)

    index = TileIndex(
        TileGrid(
            extent=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=2.0, max_lat=2.0),
            tile_width=1.0,
            tile_height=1.0,
        )
    )
    viewport = GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0)
    first_key = index.visible_tiles(
        viewport,
        map_scale=10000,
        layer_id="L1",
        source_signature=first_signature,
    )[0].key
    second_key = index.visible_tiles(
        viewport,
        map_scale=10000,
        layer_id="L1",
        source_signature=second_signature,
    )[0].key

    assert first_signature != second_signature
    assert first_key != second_key
    assert tile_key_parts(first_key)[:4] != tile_key_parts(second_key)[:4]


def test_tile_index_for_render_spec_uses_existing_geo_window_without_layout_changes(
    tmp_path,
) -> None:
    raster_path = tmp_path / "source.tif"
    raster_path.write_bytes(b"raster")
    spec = _spec(str(raster_path))
    index = TileIndex(
        TileGrid(
            extent=GeoWindow(min_lon=100.0, min_lat=5.0, max_lon=110.0, max_lat=15.0),
            tile_width=0.5,
            tile_height=0.5,
        )
    )

    tiles = index.visible_tiles_for_spec(spec)

    assert tiles
    assert spec.map_frame == MapFrame(x=0, y=0, width=640, height=360)
    assert spec.output_width == 256
    assert spec.output_height == 144
    assert all(tile.key.layer_id == "L1" for tile in tiles)
    assert all(100.0 <= tile.bounds.min_lon <= tile.bounds.max_lon <= 110.0 for tile in tiles)
