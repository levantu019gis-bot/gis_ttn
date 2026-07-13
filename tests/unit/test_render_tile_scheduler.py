"""Tests for Story 11.4 tile scheduler and decode cancellation contracts."""

from __future__ import annotations

import numpy as np
from rasterio.enums import ColorInterp
from rasterio.transform import from_bounds

from thucthengay.gis.crs import GEOGRAPHIC_CRS
from thucthengay.models import LayerRenderBands, LayerSymbology
from thucthengay.render import (
    GeoWindow,
    RasterFileSignature,
    RenderLayerRef,
    TileCache,
    TileDecodeState,
    TileGrid,
    TileIndex,
    TileScheduler,
    decode_tile_job,
)


def _signature() -> RasterFileSignature:
    return RasterFileSignature(path="source.tif", size_bytes=100, mtime_ns=200)


def _coverages():
    index = TileIndex(
        TileGrid(
            extent=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=4.0, max_lat=4.0),
            tile_width=1.0,
            tile_height=1.0,
        )
    )
    return index.visible_tiles(
        GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=3.0, max_lat=3.0),
        map_scale=10000,
        layer_id="L1",
        source_signature=_signature(),
    )


def test_tile_scheduler_queues_missing_tiles_center_first() -> None:
    cache = TileCache(max_bytes=1024)
    scheduler = TileScheduler(cache=cache)
    revision = scheduler.begin_request("req-1")
    coverages = _coverages()

    jobs = scheduler.queue_missing(
        request_id="req-1",
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=3.0, max_lat=3.0),
        layers=[RenderLayerRef(layer_id="L1", source_path="source.tif", order=0)],
        coverages=coverages,
        tile_pixels=32,
    )

    assert len(jobs) == 9
    assert all(job.revision == revision for job in jobs)
    assert jobs[0].coverage.key.x == 1
    assert jobs[0].coverage.key.y == 1
    assert jobs == tuple(
        sorted(
            jobs,
            key=lambda job: (job.priority, job.coverage.key.y, job.coverage.key.x),
        )
    )


def test_tile_scheduler_rejects_stale_results_and_does_not_overwrite_cache() -> None:
    cache = TileCache(max_bytes=1024)
    scheduler = TileScheduler(cache=cache)
    scheduler.begin_request("req-1")
    job = scheduler.queue_missing(
        request_id="req-1",
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=3.0, max_lat=3.0),
        layers=[RenderLayerRef(layer_id="L1", source_path="source.tif", order=0)],
        coverages=_coverages(),
        tile_pixels=2,
    )[0]
    scheduler.begin_request("req-2")
    result = decode_tile_job(job, opener=lambda _path: _FakeDataset())

    assert result.state == TileDecodeState.SUCCESS
    assert scheduler.apply_result(result) is False
    assert cache.entry_count == 0


def test_tile_scheduler_applies_current_successful_result_to_cache() -> None:
    cache = TileCache(max_bytes=1024)
    scheduler = TileScheduler(cache=cache)
    scheduler.begin_request("req-1")
    job = scheduler.queue_missing(
        request_id="req-1",
        viewport=GeoWindow(min_lon=0.0, min_lat=0.0, max_lon=3.0, max_lat=3.0),
        layers=[RenderLayerRef(layer_id="L1", source_path="source.tif", order=0)],
        coverages=_coverages(),
        tile_pixels=2,
    )[0]
    result = decode_tile_job(job, opener=lambda _path: _FakeDataset())

    assert result.state == TileDecodeState.SUCCESS
    assert scheduler.apply_result(result) is True
    cached = cache.get(result.key)
    assert cached is not None
    assert cached.pixels.shape == (2, 2, 3)


def test_decode_tile_job_uses_window_and_target_out_shape() -> None:
    dataset = _FakeDataset(width=100, height=100)
    job = _job(output_size=16)

    result = decode_tile_job(job, opener=lambda _path: dataset)

    assert result.state == TileDecodeState.SUCCESS
    assert result.pixels is not None
    assert result.pixels.shape == (16, 16, 3)
    assert dataset.read_calls
    indexes, window, out_shape = dataset.read_calls[0]
    assert indexes == (1, 2, 3)
    assert window is not None
    assert out_shape == (3, 16, 16)
    assert (window.width, window.height) != (dataset.width, dataset.height)


def test_decode_tile_job_uses_manual_render_bands() -> None:
    dataset = _FakeDataset(band_count=4)
    job = scheduler_job(
        request_id="req-1",
        revision=1,
        coverage=_coverages()[0],
        output_size=16,
        render_bands=LayerRenderBands(red=3, green=2, blue=1, alpha=4),
    )

    result = decode_tile_job(job, opener=lambda _path: dataset)

    assert result.state == TileDecodeState.SUCCESS
    assert dataset.read_calls[0][0] == (3, 2, 1)
    assert dataset.read_calls[1][0] == 4


def test_decode_tile_job_applies_layer_symbology() -> None:
    dataset = _FakeDataset(pixel_value=100, dtype=np.uint16)
    job = scheduler_job(
        request_id="req-1",
        revision=1,
        coverage=_coverages()[0],
        output_size=4,
        symbology=LayerSymbology(
            stretch_mode="manual",
            manual_min=[0],
            manual_max=[200],
        ),
    )

    result = decode_tile_job(job, opener=lambda _path: dataset)

    assert result.state == TileDecodeState.SUCCESS
    assert result.pixels is not None
    assert tuple(result.pixels[2, 2].tolist()) == (127, 127, 127)


def test_decode_tile_job_returns_valid_mask_for_nodata_pixels() -> None:
    result = decode_tile_job(
        _job(output_size=4),
        opener=lambda _path: _FakeDataset(mask_left_half=True),
    )

    assert result.state == TileDecodeState.SUCCESS
    assert result.pixels is not None
    assert result.valid_mask is not None
    assert result.valid_mask.shape == (4, 4)
    assert not result.valid_mask[:, :2].any()
    assert result.valid_mask[:, 2:].all()
    assert np.all(result.pixels[:, :2] == 0)


def test_decode_tile_job_places_partial_raster_overlap_at_correct_tile_position() -> None:
    dataset = _FakeDataset(bounds=(0.5, 0.0, 1.0, 1.0))

    result = decode_tile_job(
        _job(output_size=8),
        opener=lambda _path: dataset,
    )

    assert result.state == TileDecodeState.SUCCESS
    assert result.pixels is not None
    assert result.valid_mask is not None
    assert result.pixels.shape == (8, 8, 3)
    assert not result.valid_mask[:, :4].any()
    assert result.valid_mask[:, 4:].all()
    assert np.all(result.pixels[:, :4] == 0)
    assert np.all(result.pixels[:, 4:] == 120)
    _indexes, _window, out_shape = dataset.read_calls[0]
    assert out_shape == (3, 8, 4)


def test_decode_tile_job_cancellation_exits_without_cache_mutation() -> None:
    cache = TileCache(max_bytes=1024)
    scheduler = TileScheduler(cache=cache)
    scheduler.begin_request("req-1")
    job = _job(request_id="req-1")

    result = decode_tile_job(job, opener=lambda _path: _FakeDataset(), is_cancelled=lambda: True)

    assert result.state == TileDecodeState.CANCELLED
    assert scheduler.apply_result(result) is False
    assert cache.entry_count == 0


def test_decode_tile_job_cancellation_after_read_is_cancelled_not_cached() -> None:
    cache = TileCache(max_bytes=1024)
    scheduler = TileScheduler(cache=cache)
    scheduler.begin_request("req-1")
    calls = {"count": 0}

    def cancel_after_first_checkpoint() -> bool:
        calls["count"] += 1
        return calls["count"] >= 3

    result = decode_tile_job(
        _job(request_id="req-1"),
        opener=lambda _path: _FakeDataset(),
        is_cancelled=cancel_after_first_checkpoint,
    )

    assert result.state == TileDecodeState.CANCELLED
    assert scheduler.apply_result(result) is False
    assert cache.entry_count == 0


def _job(request_id: str = "req-1", output_size: int = 8):
    coverage = _coverages()[0]
    return scheduler_job(
        request_id=request_id,
        revision=1,
        coverage=coverage,
        output_size=output_size,
    )


def scheduler_job(  # noqa: ANN001
    request_id,
    revision,
    coverage,
    output_size,
    render_bands=None,
    symbology=None,
):
    from thucthengay.render import TileDecodeJob

    return TileDecodeJob(
        request_id=request_id,
        revision=revision,
        coverage=coverage,
        source_path="source.tif",
        render_bands=render_bands,
        symbology=symbology,
        output_width=output_size,
        output_height=output_size,
    )


class _FakeDataset:
    def __init__(
        self,
        *,
        width: int = 100,
        height: int = 100,
        bounds: tuple[float, float, float, float] = (0.0, 0.0, 4.0, 4.0),
        mask_left_half: bool = False,
        band_count: int = 3,
        pixel_value: int = 120,
        dtype=np.uint8,
    ) -> None:
        self.width = width
        self.height = height
        self._bounds = bounds
        self.mask_left_half = mask_left_half
        self.count = band_count
        self.pixel_value = pixel_value
        self.dtype = dtype
        self.crs = GEOGRAPHIC_CRS
        self.bounds = bounds
        self.transform = from_bounds(*bounds, width, height)
        self.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue)
        self.read_calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self) -> None:
        self.closed = True

    def read(self, indexes, *, window, out_shape, resampling, masked):  # noqa: ANN001, ARG002
        self.read_calls.append((indexes, window, out_shape))
        shape = (
            out_shape
            if isinstance(out_shape, tuple) and len(out_shape) == 3
            else (out_shape[0], out_shape[1])
        )
        mask_array = False
        if self.mask_left_half and isinstance(indexes, tuple):
            mask_array = np.zeros(shape, dtype=bool)
            mask_array[..., : shape[-1] // 2] = True
        if isinstance(indexes, tuple):
            return np.ma.array(np.full(shape, self.pixel_value, dtype=self.dtype), mask=mask_array)
        return np.ma.array(np.full(shape, 255, dtype=self.dtype), mask=False)
