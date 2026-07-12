"""Tests for Story 5.2: render_raster_layers compositing."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from thucthengay.gis.crs import GEOGRAPHIC_CRS, get_transformer
from thucthengay.models import LayerRenderBands
from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    RenderBackground,
    RenderError,
    RenderLayerRef,
    RenderSpec,
    render_raster_layers,
)


class _CountingDataset:
    def __init__(
        self,
        dataset: rasterio.DatasetReader,
        path: str,
        read_counts: dict[str, int],
    ) -> None:
        self._dataset = dataset
        self._path = path
        self._read_counts = read_counts

    def __getattr__(self, name: str):
        return getattr(self._dataset, name)

    def read(self, *args, **kwargs):
        self._read_counts[self._path] = self._read_counts.get(self._path, 0) + 1
        return self._dataset.read(*args, **kwargs)

    def close(self) -> None:
        self._dataset.close()


def _spec(
    *,
    layers: list[RenderLayerRef],
    geo: tuple[float, float, float, float] = (106.0, 10.0, 107.0, 11.0),
    width: int = 32,
    height: int = 32,
    bg_color: str = "#FFFFFF",
) -> RenderSpec:
    return RenderSpec(
        composition_id="tgt__20260525",
        target_id="tgt",
        output_width=width,
        output_height=height,
        view_center=[(geo[0] + geo[2]) / 2, (geo[1] + geo[3]) / 2],
        view_scale=50000,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=640 / 360,
        geo_window=GeoWindow(
            min_lon=geo[0], min_lat=geo[1], max_lon=geo[2], max_lat=geo[3]
        ),
        visible_layers=layers,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        background=RenderBackground(color=bg_color),
        template_metadata_file="t.json",
        template_pptx="t.pptx",
        slide_index=0,
    )


def _make_memfile(
    *,
    bounds: tuple[float, float, float, float],
    crs: str,
    rgb: tuple[int, int, int],
    width: int = 32,
    height: int = 32,
    dtype: str = "uint8",
    nodata: int | float | None = None,
    alpha: np.ndarray | None = None,
    extra_bands: tuple[int, ...] = (),
    transform: Affine | None = None,
    nodata_right_half: bool = False,
) -> MemoryFile:
    """Return an open MemoryFile holding a tiny GeoTIFF; caller closes it."""
    left, bottom, right, top = bounds
    transform = transform or from_bounds(left, bottom, right, top, width, height)
    band_count = 4 if alpha is not None else 3 + len(extra_bands)
    data = np.zeros((band_count, height, width), dtype=np.dtype(dtype))
    data[0, :, :] = rgb[0]
    data[1, :, :] = rgb[1]
    data[2, :, :] = rgb[2]
    if alpha is not None:
        data[3, :, :] = alpha.astype(data.dtype)
    else:
        for offset, value in enumerate(extra_bands, start=3):
            data[offset, :, :] = value
    if nodata is not None and nodata_right_half:
        data[:, :, width // 2 :] = nodata
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": band_count,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    memfile = MemoryFile()
    with memfile.open(**profile) as ds:
        ds.write(data)
        if alpha is not None:
            ds.colorinterp = (
                rasterio.enums.ColorInterp.red,
                rasterio.enums.ColorInterp.green,
                rasterio.enums.ColorInterp.blue,
                rasterio.enums.ColorInterp.alpha,
            )
    return memfile


@contextmanager
def _opener_for(
    mapping: dict[str, MemoryFile],
    *,
    unreadable_paths: set[str] | None = None,
) -> Iterator[callable]:
    """Yield a ``dataset_opener`` callable backed by an in-memory registry."""
    unreadable_paths = unreadable_paths or set()
    handles: list = []

    def opener(path: str) -> rasterio.DatasetReader:
        if path in unreadable_paths:
            raise rasterio.RasterioIOError(f"Synthetic open failure for {path!r}")
        memfile = mapping.get(path)
        if memfile is None:
            raise rasterio.RasterioIOError(f"Unknown synthetic path {path!r}")
        ds = memfile.open()
        handles.append(ds)
        return ds

    try:
        yield opener
    finally:
        for ds in handles:
            ds.close()
        for memfile in mapping.values():
            memfile.close()


@contextmanager
def _counting_opener_for(
    mapping: dict[str, MemoryFile],
    read_counts: dict[str, int],
) -> Iterator[callable]:
    handles: list = []

    def opener(path: str) -> rasterio.DatasetReader:
        memfile = mapping.get(path)
        if memfile is None:
            raise rasterio.RasterioIOError(f"Unknown synthetic path {path!r}")
        ds = _CountingDataset(memfile.open(), path, read_counts)
        handles.append(ds)
        return ds

    try:
        yield opener
    finally:
        for ds in handles:
            ds.close()
        for memfile in mapping.values():
            memfile.close()


class TestSingleLayerHappyPath:
    def test_layer_pixels_overwrite_background(self) -> None:
        memfile = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0),
            crs=GEOGRAPHIC_CRS,
            rgb=(10, 20, 30),
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=16, height=16, bg_color="#FFFFFF")

        with _opener_for({"L1.tif": memfile}) as opener:
            result = render_raster_layers(spec, dataset_opener=opener)
        canvas = result.canvas

        assert canvas.shape == (16, 16, 3)
        assert canvas.dtype == np.uint8
        assert result.issues == ()
        assert result.painted_layer_ids == ("L1",)
        # Center pixel should be from the layer, not the background
        cy, cx = 8, 8
        assert tuple(canvas[cy, cx].tolist()) == (10, 20, 30)

    def test_manual_render_bands_override_default_band_order(self) -> None:
        memfile = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0),
            crs=GEOGRAPHIC_CRS,
            rgb=(10, 20, 30),
            extra_bands=(40,),
        )
        layer = RenderLayerRef(
            layer_id="L1",
            source_path="L1.tif",
            cache_path="L1.tif",
            order=0,
            render_bands=LayerRenderBands(red=4, green=3, blue=2),
        )
        spec = _spec(layers=[layer], width=16, height=16, bg_color="#FFFFFF")

        with _opener_for({"L1.tif": memfile}) as opener:
            result = render_raster_layers(spec, dataset_opener=opener)

        assert tuple(result.canvas[8, 8].tolist()) == (40, 30, 20)


class TestCrsMismatch:
    def test_projected_crs_reads_through_warped_vrt(self) -> None:
        forward = get_transformer(GEOGRAPHIC_CRS, "EPSG:3857")
        x0, y0 = forward.transform(106.0, 10.0)
        x1, y1 = forward.transform(107.0, 11.0)
        memfile = _make_memfile(
            bounds=(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
            crs="EPSG:3857",
            rgb=(50, 60, 70),
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=16, height=16)

        with _opener_for({"L1.tif": memfile}) as opener:
            canvas = render_raster_layers(spec, dataset_opener=opener).canvas

        # Layer fills the whole geo_window — center pixel must not be background
        assert tuple(canvas[8, 8].tolist()) == (50, 60, 70)


class TestCompositingOrder:
    def test_higher_order_overwrites_lower(self) -> None:
        bottom = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0), crs=GEOGRAPHIC_CRS, rgb=(10, 10, 10)
        )
        top = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0), crs=GEOGRAPHIC_CRS, rgb=(200, 200, 200)
        )
        layers = [
            RenderLayerRef(layer_id="BOT", source_path="b.tif", cache_path="b.tif", order=0),
            RenderLayerRef(layer_id="TOP", source_path="t.tif", cache_path="t.tif", order=1),
        ]
        spec = _spec(layers=layers, width=16, height=16)

        with _opener_for({"b.tif": bottom, "t.tif": top}) as opener:
            canvas = render_raster_layers(spec, dataset_opener=opener).canvas

        assert tuple(canvas[8, 8].tolist()) == (200, 200, 200)

    def test_fully_occluded_lower_layer_is_not_read(self) -> None:
        bottom = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0), crs=GEOGRAPHIC_CRS, rgb=(10, 10, 10)
        )
        top = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0), crs=GEOGRAPHIC_CRS, rgb=(200, 200, 200)
        )
        layers = [
            RenderLayerRef(layer_id="BOT", source_path="b.tif", cache_path="b.tif", order=0),
            RenderLayerRef(layer_id="TOP", source_path="t.tif", cache_path="t.tif", order=1),
        ]
        spec = _spec(layers=layers, width=16, height=16)
        read_counts: dict[str, int] = {}

        with _counting_opener_for({"b.tif": bottom, "t.tif": top}, read_counts) as opener:
            result = render_raster_layers(spec, dataset_opener=opener)

        assert tuple(result.canvas[8, 8].tolist()) == (200, 200, 200)
        assert result.painted_layer_ids == ("BOT", "TOP")
        assert read_counts["t.tif"] > 0
        assert read_counts.get("b.tif", 0) == 0

    def test_transparent_top_layer_keeps_reading_uncovered_lower_pixels(self) -> None:
        bottom = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0), crs=GEOGRAPHIC_CRS, rgb=(10, 20, 30)
        )
        alpha = np.full((8, 8), 255, dtype=np.uint8)
        alpha[:, 4:] = 0
        top = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0),
            crs=GEOGRAPHIC_CRS,
            rgb=(200, 210, 220),
            width=8,
            height=8,
            alpha=alpha,
        )
        layers = [
            RenderLayerRef(layer_id="BOT", source_path="b.tif", cache_path="b.tif", order=0),
            RenderLayerRef(layer_id="TOP", source_path="t.tif", cache_path="t.tif", order=1),
        ]
        spec = _spec(layers=layers, width=8, height=8)
        read_counts: dict[str, int] = {}

        with _counting_opener_for({"b.tif": bottom, "t.tif": top}, read_counts) as opener:
            result = render_raster_layers(spec, dataset_opener=opener)

        assert tuple(result.canvas[4, 2].tolist()) == (200, 210, 220)
        assert tuple(result.canvas[4, 6].tolist()) == (10, 20, 30)
        assert result.painted_layer_ids == ("BOT", "TOP")
        assert read_counts["t.tif"] > 0
        assert read_counts["b.tif"] > 0


class TestPartialOverlap:
    def test_uncovered_area_keeps_background(self) -> None:
        # Layer covers only the western half of the geo_window
        memfile = _make_memfile(
            bounds=(106.0, 10.0, 106.5, 11.0), crs=GEOGRAPHIC_CRS, rgb=(100, 100, 100)
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=32, height=16, bg_color="#FF0000")

        with _opener_for({"L1.tif": memfile}) as opener:
            canvas = render_raster_layers(spec, dataset_opener=opener).canvas

        # West (col=4) covered by layer; east (col=28) still red background
        assert tuple(canvas[8, 4].tolist()) == (100, 100, 100)
        assert tuple(canvas[8, 28].tolist()) == (255, 0, 0)


class TestErrorHandling:
    def test_unreadable_layer_collects_issue_but_others_render(self) -> None:
        good = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0), crs=GEOGRAPHIC_CRS, rgb=(40, 40, 40)
        )
        layers = [
            RenderLayerRef(layer_id="BAD", source_path="bad.tif", cache_path="bad.tif", order=0),
            RenderLayerRef(layer_id="OK", source_path="ok.tif", cache_path="ok.tif", order=1),
        ]
        spec = _spec(layers=layers, width=16, height=16)

        with _opener_for(
            {"ok.tif": good}, unreadable_paths={"bad.tif"}
        ) as opener:
            result = render_raster_layers(spec, dataset_opener=opener)

        assert tuple(result.canvas[8, 8].tolist()) == (40, 40, 40)
        assert [issue.issue_id for issue in result.issues] == ["render.raster.unreadable"]
        assert result.issues[0].layer_id == "BAD"

    def test_all_layers_fail_raises_render_error(self) -> None:
        layers = [
            RenderLayerRef(layer_id="X", source_path="x.tif", cache_path="x.tif", order=0)
        ]
        spec = _spec(layers=layers, width=16, height=16)

        with _opener_for({}, unreadable_paths={"x.tif"}) as opener:
            with pytest.raises(RenderError) as exc:
                render_raster_layers(spec, dataset_opener=opener)

        ids = [i.issue_id for i in exc.value.issues]
        assert "render.raster.unreadable" in ids
        assert exc.value.issues[0].layer_id == "X"


class TestCanvasShape:
    def test_empty_visible_layers_returns_background_canvas(self) -> None:
        spec = _spec(layers=[], width=24, height=12, bg_color="#0000FF")
        canvas = render_raster_layers(spec).canvas
        assert canvas.shape == (12, 24, 3)
        assert canvas.dtype == np.uint8
        # All pixels should be background blue
        assert (canvas[..., 2] == 255).all()
        assert (canvas[..., 0] == 0).all()
        assert (canvas[..., 1] == 0).all()

    def test_huge_output_raises_structured_issue_before_allocation(self) -> None:
        spec = _spec(layers=[], width=100_000, height=100_000)

        with pytest.raises(RenderError) as exc:
            render_raster_layers(spec)

        assert exc.value.issues[0].issue_id == "render.output.too_large"


class TestRasterDataSafety:
    def test_nodata_pixels_do_not_overwrite_background(self) -> None:
        memfile = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0),
            crs=GEOGRAPHIC_CRS,
            rgb=(10, 80, 160),
            nodata=0,
            nodata_right_half=True,
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=16, height=16, bg_color="#112233")

        with _opener_for({"L1.tif": memfile}) as opener:
            canvas = render_raster_layers(spec, dataset_opener=opener).canvas

        assert tuple(canvas[8, 4].tolist()) == (10, 80, 160)
        assert tuple(canvas[8, 12].tolist()) == (17, 34, 51)

    def test_alpha_zero_pixels_do_not_overwrite_background(self) -> None:
        alpha = np.full((8, 8), 255, dtype=np.uint8)
        alpha[:, 4:] = 0
        memfile = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0),
            crs=GEOGRAPHIC_CRS,
            rgb=(10, 20, 30),
            width=8,
            height=8,
            alpha=alpha,
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=8, height=8, bg_color="#FF0000")

        with _opener_for({"L1.tif": memfile}) as opener:
            canvas = render_raster_layers(spec, dataset_opener=opener).canvas

        assert tuple(canvas[4, 2].tolist()) == (10, 20, 30)
        assert tuple(canvas[4, 6].tolist()) == (255, 0, 0)

    def test_uint16_raster_scales_instead_of_saturating(self) -> None:
        memfile = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0),
            crs=GEOGRAPHIC_CRS,
            rgb=(32768, 32768, 32768),
            dtype="uint16",
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=8, height=8)

        with _opener_for({"L1.tif": memfile}) as opener:
            canvas = render_raster_layers(spec, dataset_opener=opener).canvas

        assert tuple(canvas[4, 4].tolist()) == pytest.approx((128, 128, 128), abs=1)

    def test_no_overlap_visible_layers_raise_structured_issue(self) -> None:
        memfile = _make_memfile(
            bounds=(110.0, 20.0, 111.0, 21.0), crs=GEOGRAPHIC_CRS, rgb=(10, 20, 30)
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=8, height=8)

        with _opener_for({"L1.tif": memfile}) as opener:
            with pytest.raises(RenderError) as exc:
                render_raster_layers(spec, dataset_opener=opener)

        assert exc.value.issues[0].issue_id == "render.raster.no_overlap"

    def test_rotated_transform_reports_layer_issue(self) -> None:
        rotated = Affine(0.01, 0.001, 106.0, 0.001, -0.01, 11.0)
        memfile = _make_memfile(
            bounds=(106.0, 10.0, 107.0, 11.0),
            crs=GEOGRAPHIC_CRS,
            rgb=(10, 20, 30),
            transform=rotated,
        )
        layer = RenderLayerRef(
            layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0
        )
        spec = _spec(layers=[layer], width=8, height=8)

        with _opener_for({"L1.tif": memfile}) as opener:
            with pytest.raises(RenderError) as exc:
                render_raster_layers(spec, dataset_opener=opener)

        assert exc.value.issues[0].issue_id == "render.raster.unreadable"
