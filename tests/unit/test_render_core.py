"""Tests for Story 5.3 composed map rendering."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

import thucthengay.render.core as render_core
from thucthengay.gis.crs import GEOGRAPHIC_CRS
from thucthengay.models import TemporalCompareOrientation
from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    RasterRenderResult,
    RenderBackground,
    RenderComparisonPane,
    RenderComparisonSpec,
    RenderError,
    RenderLayerRef,
    RenderSpec,
    build_map_surround_layout,
    draw_map_surround_frame,
    render_map,
    render_raster_layers_to_size,
)
from thucthengay.render.frame import PixelRect


def _spec(
    *,
    layers: list[RenderLayerRef],
    bg_color: str = "#112233",
    interval: GridInterval | None = None,
) -> RenderSpec:
    return RenderSpec(
        composition_id="tgt__20260525",
        target_id="tgt",
        output_width=64,
        output_height=48,
        view_center=[106.5, 10.5],
        view_scale=50000,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=640 / 360,
        geo_window=GeoWindow(min_lon=106.0, min_lat=10.0, max_lon=107.0, max_lat=11.0),
        visible_layers=layers,
        grid=GridConfig(interval=interval or GridInterval(minutes=30), label_format="dms_full"),
        background=RenderBackground(color=bg_color),
        template_metadata_file="t.json",
        template_pptx="t.pptx",
        slide_index=0,
    )


def test_temporal_compare_vertical_split_renders_selected_layers_per_pane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], int, int]] = []

    def fake_raster_base(
        render_spec: RenderSpec,
        *,
        output_width: int,
        output_height: int,
        **_kwargs,
    ):
        layer_ids = tuple(layer.layer_id for layer in render_spec.visible_layers)
        calls.append((layer_ids, output_width, output_height))
        color = (255, 0, 0) if layer_ids == ("A",) else (0, 0, 255)
        canvas = np.zeros((output_height, output_width, 3), dtype=np.uint8)
        canvas[:, :] = color
        return RasterRenderResult(canvas=canvas, painted_layer_ids=layer_ids)

    monkeypatch.setattr(render_core, "_render_raster_base", fake_raster_base)
    spec = _spec(layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)])
    spec = spec.model_copy(
        update={
            "temporal_compare": RenderComparisonSpec(
                enabled=True,
                orientation=TemporalCompareOrientation.VERTICAL,
                pane_a=RenderComparisonPane(
                    layer_id="A",
                    layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)],
                ),
                pane_b=RenderComparisonPane(
                    layer_id="B",
                    layers=[RenderLayerRef(layer_id="B", source_path="B.tif", order=0)],
                ),
            )
        }
    )

    result = render_core.render_map_with_cache(spec, render_cache=None)

    assert calls[0][0] == ("A",)
    assert calls[1][0] == ("B",)
    full_layout = build_map_surround_layout(spec.output_width, spec.output_height, spec.grid.style)
    pane_a, pane_b = render_core._split_compare_inner_map(
        full_layout.inner_map,
        TemporalCompareOrientation.VERTICAL,
    )
    assert calls[0][1:] == (pane_a.width, pane_a.height)
    assert calls[1][1:] == (pane_b.width, pane_b.height)
    pane_a_sample = (
        pane_a.center_y,
        pane_a.center_x,
    )
    pane_b_sample = (
        pane_b.center_y,
        pane_b.center_x,
    )
    assert result.canvas[pane_a_sample][0] > 200
    assert result.canvas[pane_b_sample][2] > 200
    assert set(result.painted_layer_ids) == {"A", "B"}


def test_temporal_compare_split_keeps_outer_inner_map_and_defaults_to_8px_gap() -> None:
    inner = PixelRect(left=10, top=20, right=110, bottom=80)

    vertical_a, vertical_b = render_core._split_compare_inner_map(
        inner,
        TemporalCompareOrientation.VERTICAL,
    )
    assert vertical_a == PixelRect(left=10, top=20, right=56, bottom=80)
    assert vertical_b == PixelRect(left=64, top=20, right=110, bottom=80)
    assert vertical_b.left - vertical_a.right == 8

    horizontal_a, horizontal_b = render_core._split_compare_inner_map(
        inner,
        TemporalCompareOrientation.HORIZONTAL,
    )
    assert horizontal_a == PixelRect(left=10, top=20, right=110, bottom=46)
    assert horizontal_b == PixelRect(left=10, top=54, right=110, bottom=80)
    assert horizontal_b.top - horizontal_a.bottom == 8


def test_temporal_compare_split_uses_configured_gap_from_grid_style() -> None:
    inner = PixelRect(left=10, top=20, right=110, bottom=80)

    vertical_a, vertical_b = render_core._split_compare_inner_map(
        inner,
        TemporalCompareOrientation.VERTICAL,
        gap_px=12,
    )

    assert vertical_a == PixelRect(left=10, top=20, right=54, bottom=80)
    assert vertical_b == PixelRect(left=66, top=20, right=110, bottom=80)
    assert vertical_b.left - vertical_a.right == 12


def test_temporal_compare_gap_remains_clear_between_independent_panes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_raster_base(
        render_spec: RenderSpec,
        *,
        output_width: int,
        output_height: int,
        **_kwargs,
    ) -> RasterRenderResult:
        layer_ids = tuple(layer.layer_id for layer in render_spec.visible_layers)
        color = tuple(
            int(render_spec.background.color.lstrip("#")[index : index + 2], 16)
            for index in (0, 2, 4)
        )
        canvas = np.zeros((output_height, output_width, 3), dtype=np.uint8)
        canvas[:, :] = color
        return RasterRenderResult(canvas=canvas, painted_layer_ids=layer_ids)

    monkeypatch.setattr(render_core, "_render_raster_base", fake_raster_base)
    monkeypatch.setattr(
        render_core,
        "draw_map_surround_pane_frame",
        lambda canvas, *_args, **_kwargs: canvas,
    )

    spec = _spec(layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)])
    spec = spec.model_copy(
        update={
            "temporal_compare": RenderComparisonSpec(
                enabled=True,
                orientation=TemporalCompareOrientation.VERTICAL,
                pane_a=RenderComparisonPane(
                    layer_id="A",
                    layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)],
                ),
                pane_b=RenderComparisonPane(
                    layer_id="B",
                    layers=[RenderLayerRef(layer_id="B", source_path="B.tif", order=0)],
                ),
            )
        }
    )

    result = render_core.render_map_with_cache(spec, render_cache=None)

    layout = build_map_surround_layout(spec.output_width, spec.output_height, spec.grid.style)
    pane_a, pane_b = render_core._split_compare_inner_map(
        layout.inner_map,
        TemporalCompareOrientation.VERTICAL,
    )
    gap_x = (pane_a.right + pane_b.left) // 2
    assert tuple(result.canvas[pane_a.center_y, pane_a.center_x]) == (17, 34, 51)
    assert tuple(result.canvas[pane_b.center_y, pane_b.center_x]) == (17, 34, 51)
    assert tuple(result.canvas[layout.inner_map.center_y, gap_x]) == (255, 255, 255)


def test_temporal_compare_gap_color_can_be_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_raster_base(
        render_spec: RenderSpec,
        *,
        output_width: int,
        output_height: int,
        **_kwargs,
    ) -> RasterRenderResult:
        layer_ids = tuple(layer.layer_id for layer in render_spec.visible_layers)
        canvas = np.zeros((output_height, output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 0, 0) if layer_ids == ("A",) else (0, 0, 255)
        return RasterRenderResult(canvas=canvas, painted_layer_ids=layer_ids)

    monkeypatch.setattr(render_core, "_render_raster_base", fake_raster_base)
    monkeypatch.setattr(
        render_core,
        "draw_map_surround_pane_frame",
        lambda canvas, *_args, **_kwargs: canvas,
    )

    spec = _spec(layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)])
    spec.grid.style["temporal_compare_gap_color"] = "#EDEDED"
    spec = spec.model_copy(
        update={
            "temporal_compare": RenderComparisonSpec(
                enabled=True,
                orientation=TemporalCompareOrientation.VERTICAL,
                pane_a=RenderComparisonPane(
                    layer_id="A",
                    layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)],
                ),
                pane_b=RenderComparisonPane(
                    layer_id="B",
                    layers=[RenderLayerRef(layer_id="B", source_path="B.tif", order=0)],
                ),
            )
        }
    )

    result = render_core.render_map_with_cache(spec, render_cache=None)

    layout = build_map_surround_layout(spec.output_width, spec.output_height, spec.grid.style)
    pane_a, pane_b = render_core._split_compare_inner_map(
        layout.inner_map,
        TemporalCompareOrientation.VERTICAL,
    )
    gap_x = (pane_a.right + pane_b.left) // 2
    assert tuple(result.canvas[layout.inner_map.center_y, gap_x]) == (237, 237, 237)


def test_temporal_compare_draws_independent_coordinate_overlay_per_pane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pane_frame_calls: list[tuple[tuple[str, ...], GeoWindow, PixelRect, PixelRect, int]] = []

    def fake_raster_base(
        render_spec: RenderSpec,
        *,
        output_width: int,
        output_height: int,
        **_kwargs,
    ) -> RasterRenderResult:
        layer_ids = tuple(layer.layer_id for layer in render_spec.visible_layers)
        canvas = np.zeros((output_height, output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 0, 0) if layer_ids == ("A",) else (0, 0, 255)
        return RasterRenderResult(canvas=canvas, painted_layer_ids=layer_ids)

    def fake_pane_frame(
        canvas: np.ndarray,
        render_spec: RenderSpec,
        layout,
        pane_rect: PixelRect,
        internal_gap_px: int,
        **_kwargs,
    ) -> np.ndarray:
        layer_ids = tuple(layer.layer_id for layer in render_spec.visible_layers)
        pane_frame_calls.append(
            (layer_ids, render_spec.geo_window, pane_rect, layout.inner_map, internal_gap_px)
        )
        return canvas

    monkeypatch.setattr(render_core, "_render_raster_base", fake_raster_base)
    monkeypatch.setattr(render_core, "draw_map_surround_pane_frame", fake_pane_frame)

    pane_a_window = GeoWindow(min_lon=106.0, min_lat=10.0, max_lon=107.0, max_lat=11.0)
    pane_b_window = GeoWindow(min_lon=108.0, min_lat=12.0, max_lon=109.0, max_lat=13.0)
    spec = _spec(layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)])
    spec.grid.style["temporal_compare_pane_gap_px"] = 12
    spec = spec.model_copy(
        update={
            "temporal_compare": RenderComparisonSpec(
                enabled=True,
                orientation=TemporalCompareOrientation.VERTICAL,
                pane_a=RenderComparisonPane(
                    layer_id="A",
                    view_center=[106.5, 10.5],
                    view_scale=50000,
                    geo_window=pane_a_window,
                    layers=[RenderLayerRef(layer_id="A", source_path="A.tif", order=0)],
                ),
                pane_b=RenderComparisonPane(
                    layer_id="B",
                    view_center=[108.5, 12.5],
                    view_scale=50000,
                    geo_window=pane_b_window,
                    layers=[RenderLayerRef(layer_id="B", source_path="B.tif", order=0)],
                ),
            )
        }
    )

    render_core.render_map_with_cache(spec, render_cache=None)

    assert [call[0] for call in pane_frame_calls] == [("A",), ("B",)]
    assert pane_frame_calls[0][1].min_lon < 107.0
    assert pane_frame_calls[1][1].min_lon > 107.0
    assert pane_frame_calls[0][2].left == pane_frame_calls[0][3].left
    assert pane_frame_calls[1][2].right == pane_frame_calls[1][3].right
    assert pane_frame_calls[1][2].left - pane_frame_calls[0][2].right == 12
    assert pane_frame_calls[0][4] == 12
    assert pane_frame_calls[1][4] == 12


def _make_memfile(
    *,
    bounds: tuple[float, float, float, float],
    rgb: tuple[int, int, int],
    width: int = 32,
    height: int = 32,
) -> MemoryFile:
    data = np.zeros((3, height, width), dtype=np.uint8)
    data[0, :, :] = rgb[0]
    data[1, :, :] = rgb[1]
    data[2, :, :] = rgb[2]
    memfile = MemoryFile()
    with memfile.open(
        driver="GTiff",
        width=width,
        height=height,
        count=3,
        dtype="uint8",
        crs=GEOGRAPHIC_CRS,
        transform=from_bounds(*bounds, width, height),
    ) as ds:
        ds.write(data)
    return memfile


@contextmanager
def _opener_for(
    mapping: dict[str, MemoryFile],
    *,
    unreadable_paths: set[str] | None = None,
) -> Iterator[callable]:
    unreadable_paths = unreadable_paths or set()
    handles: list = []

    def opener(path: str) -> rasterio.DatasetReader:
        if path in unreadable_paths:
            raise rasterio.RasterioIOError(f"Synthetic open failure for {path!r}")
        ds = mapping[path].open()
        handles.append(ds)
        return ds

    try:
        yield opener
    finally:
        for ds in handles:
            ds.close()
        for memfile in mapping.values():
            memfile.close()


class TestRenderMap:
    def test_background_survives_uncovered_raster_area_and_frame_is_drawn(self) -> None:
        memfile = _make_memfile(bounds=(106.0, 10.0, 106.5, 11.0), rgb=(80, 90, 100))
        layer = RenderLayerRef(layer_id="L1", source_path="L1.tif", cache_path="L1.tif", order=0)

        with _opener_for({"L1.tif": memfile}) as opener:
            spec = _spec(layers=[layer])
            result = render_map(spec, dataset_opener=opener)

        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        geo_map = layout.inner_map
        raster_col = geo_map.left + geo_map.width // 4
        background_col = geo_map.left + geo_map.width * 3 // 4
        row = geo_map.center_y
        assert tuple(result.canvas[row, raster_col].tolist()) == (80, 90, 100)
        assert tuple(result.canvas[row, background_col].tolist()) == (17, 34, 51)
        assert tuple(result.canvas[0, 0].tolist()) == (255, 255, 255)

    def test_raster_render_fills_entire_inner_map_without_bitmap_letterbox(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spec = _spec(layers=[])
        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        calls: dict[str, object] = {}

        def fake_render_raster_layers_to_size(
            render_spec: RenderSpec,
            *,
            output_width: int,
            output_height: int,
            dataset_opener,
            is_cancelled,
        ) -> RasterRenderResult:
            calls["spec"] = render_spec
            calls["output_width"] = output_width
            calls["output_height"] = output_height
            canvas = np.empty((output_height, output_width, 3), dtype=np.uint8)
            canvas[:, :] = (80, 90, 100)
            return RasterRenderResult(canvas=canvas)

        monkeypatch.setattr(
            render_core,
            "render_raster_layers_to_size",
            fake_render_raster_layers_to_size,
        )

        result = render_map(spec)

        assert calls["output_width"] == layout.inner_map.width
        assert calls["output_height"] == layout.inner_map.height
        assert tuple(
            result.canvas[layout.inner_map.center_y, layout.inner_map.left + 8].tolist()
        ) == (80, 90, 100)
        assert tuple(
            result.canvas[layout.inner_map.center_y, layout.inner_map.right - 9].tolist()
        ) == (80, 90, 100)
        rendered_spec = calls["spec"]
        assert isinstance(rendered_spec, RenderSpec)
        geo_aspect = (
            rendered_spec.geo_window.max_lon - rendered_spec.geo_window.min_lon
        ) / (rendered_spec.geo_window.max_lat - rendered_spec.geo_window.min_lat)
        assert geo_aspect == pytest.approx(layout.inner_map.width / layout.inner_map.height)
        assert rendered_spec.geo_window.min_lon <= spec.geo_window.min_lon
        assert rendered_spec.geo_window.max_lon >= spec.geo_window.max_lon
        assert rendered_spec.geo_window.min_lat <= spec.geo_window.min_lat
        assert rendered_spec.geo_window.max_lat >= spec.geo_window.max_lat

    def test_cached_render_reuses_raster_base_when_only_grid_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[int, int]] = []

        def fake_render_raster_layers_to_size(
            render_spec: RenderSpec,
            *,
            output_width: int,
            output_height: int,
            dataset_opener,
            is_cancelled,
        ) -> RasterRenderResult:
            calls.append((output_width, output_height))
            canvas = np.empty((output_height, output_width, 3), dtype=np.uint8)
            canvas[:, :] = (80, 90, 100)
            return RasterRenderResult(canvas=canvas, painted_layer_ids=("fake",))

        monkeypatch.setattr(
            render_core,
            "render_raster_layers_to_size",
            fake_render_raster_layers_to_size,
        )
        cache = render_core.RasterBaseCache()
        spec = _spec(layers=[], interval=GridInterval(minutes=30))

        first = render_core.render_map_with_cache(spec, raster_cache=cache)
        second = render_core.render_map_with_cache(
            spec.model_copy(
                update={
                    "grid": GridConfig(
                        interval=GridInterval(minutes=15),
                        label_format="dms_full",
                    )
                }
            ),
            raster_cache=cache,
        )

        assert len(calls) == 1
        assert cache.entry_count == 1
        assert first.canvas.shape == second.canvas.shape

    def test_cached_render_invalidates_raster_base_when_geo_window_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[GeoWindow] = []

        def fake_render_raster_layers_to_size(
            render_spec: RenderSpec,
            *,
            output_width: int,
            output_height: int,
            dataset_opener,
            is_cancelled,
        ) -> RasterRenderResult:
            calls.append(render_spec.geo_window)
            canvas = np.empty((output_height, output_width, 3), dtype=np.uint8)
            canvas[:, :] = (80, 90, 100)
            return RasterRenderResult(canvas=canvas, painted_layer_ids=("fake",))

        monkeypatch.setattr(
            render_core,
            "render_raster_layers_to_size",
            fake_render_raster_layers_to_size,
        )
        cache = render_core.RasterBaseCache()
        spec = _spec(layers=[], interval=GridInterval(minutes=30))

        render_core.render_map_with_cache(spec, raster_cache=cache)
        render_core.render_map_with_cache(
            spec.model_copy(
                update={
                    "geo_window": GeoWindow(
                        min_lon=106.1,
                        min_lat=10.0,
                        max_lon=107.1,
                        max_lat=11.0,
                    )
                }
            ),
            raster_cache=cache,
        )

        assert len(calls) == 2
        assert cache.entry_count == 2

    def test_cached_render_reuses_frame_overlay_when_only_layers_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raster_calls = 0
        frame_calls = 0

        def fake_render_raster_layers_to_size(
            render_spec: RenderSpec,
            *,
            output_width: int,
            output_height: int,
            dataset_opener,
            is_cancelled,
        ) -> RasterRenderResult:
            nonlocal raster_calls
            raster_calls += 1
            canvas = np.empty((output_height, output_width, 3), dtype=np.uint8)
            canvas[:, :] = (40 + raster_calls, 50, 60)
            return RasterRenderResult(canvas=canvas, painted_layer_ids=("fake",))

        original_draw = render_core.draw_map_surround_frame

        def counting_draw_map_surround_frame(*args, **kwargs):
            nonlocal frame_calls
            frame_calls += 1
            return original_draw(*args, **kwargs)

        monkeypatch.setattr(
            render_core,
            "render_raster_layers_to_size",
            fake_render_raster_layers_to_size,
        )
        monkeypatch.setattr(
            render_core,
            "draw_map_surround_frame",
            counting_draw_map_surround_frame,
        )
        cache = render_core.MapRenderCache()
        spec = _spec(
            layers=[RenderLayerRef(layer_id="A", source_path="a.tif", cache_path=None, order=0)]
        )
        changed_layers = spec.model_copy(
            update={
                "visible_layers": [
                    RenderLayerRef(
                        layer_id="B",
                        source_path="b.tif",
                        cache_path=None,
                        order=0,
                    )
                ]
            }
        )

        render_core.render_map_with_cache(spec, render_cache=cache)
        render_core.render_map_with_cache(changed_layers, render_cache=cache)

        assert raster_calls == 2
        assert frame_calls == 1
        assert cache.frame_overlays.entry_count == 1

    def test_cached_render_reuses_full_map_when_spec_is_identical(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raster_calls = 0
        frame_calls = 0

        def fake_render_raster_layers_to_size(
            render_spec: RenderSpec,
            *,
            output_width: int,
            output_height: int,
            dataset_opener,
            is_cancelled,
        ) -> RasterRenderResult:
            nonlocal raster_calls
            raster_calls += 1
            canvas = np.empty((output_height, output_width, 3), dtype=np.uint8)
            canvas[:, :] = (80, 90, 100)
            return RasterRenderResult(canvas=canvas, painted_layer_ids=("fake",))

        original_draw = render_core.draw_map_surround_frame

        def counting_draw_map_surround_frame(*args, **kwargs):
            nonlocal frame_calls
            frame_calls += 1
            return original_draw(*args, **kwargs)

        monkeypatch.setattr(
            render_core,
            "render_raster_layers_to_size",
            fake_render_raster_layers_to_size,
        )
        monkeypatch.setattr(
            render_core,
            "draw_map_surround_frame",
            counting_draw_map_surround_frame,
        )
        cache = render_core.MapRenderCache()
        spec = _spec(layers=[], interval=GridInterval(minutes=30))

        first = render_core.render_map_with_cache(spec, render_cache=cache)
        second = render_core.render_map_with_cache(spec, render_cache=cache)

        assert raster_calls == 1
        assert frame_calls == 1
        assert cache.full_maps.entry_count == 1
        assert np.array_equal(first.canvas, second.canvas)

    def test_cached_render_matches_uncached_pixels(self) -> None:
        spec = _spec(layers=[], bg_color="#112233", interval=GridInterval(degrees=1))
        uncached = render_map(spec)
        cached = render_core.render_map_with_cache(spec, render_cache=render_core.MapRenderCache())

        assert np.array_equal(cached.canvas, uncached.canvas)
        assert cached.issues == uncached.issues
        assert cached.painted_layer_ids == uncached.painted_layer_ids

    def test_preserves_non_fatal_raster_issues(self) -> None:
        good = _make_memfile(bounds=(106.0, 10.0, 107.0, 11.0), rgb=(40, 50, 60))
        layers = [
            RenderLayerRef(layer_id="BAD", source_path="bad.tif", cache_path="bad.tif", order=0),
            RenderLayerRef(layer_id="OK", source_path="ok.tif", cache_path="ok.tif", order=1),
        ]

        with _opener_for({"ok.tif": good}, unreadable_paths={"bad.tif"}) as opener:
            result = render_map(_spec(layers=layers), dataset_opener=opener)

        assert result.painted_layer_ids == ("OK",)
        assert [issue.issue_id for issue in result.issues] == ["render.raster.unreadable"]

    def test_mvp_does_not_draw_boundary_north_arrow_or_scale_bar(self) -> None:
        spec = _spec(layers=[], bg_color="#112233", interval=GridInterval(degrees=1))
        result = render_map(spec)
        layout = build_map_surround_layout(spec.output_width, spec.output_height)

        expected = np.zeros_like(result.canvas)
        expected[:, :] = (255, 255, 255)
        expected[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)
        layout = layout.__class__(
            outer_frame=layout.outer_frame,
            inner_map=layout.inner_map,
            geo_map=layout.inner_map,
        )
        draw_map_surround_frame(
            expected,
            render_core._spec_for_inner_map(spec, layout.inner_map),
            layout,
        )

        assert np.array_equal(result.canvas, expected)

    def test_frame_error_preserves_prior_raster_issues(self) -> None:
        good = _make_memfile(bounds=(106.0, 10.0, 107.0, 11.0), rgb=(40, 50, 60))
        layers = [
            RenderLayerRef(layer_id="BAD", source_path="bad.tif", cache_path="bad.tif", order=0),
            RenderLayerRef(layer_id="OK", source_path="ok.tif", cache_path="ok.tif", order=1),
        ]
        spec = _spec(layers=layers)
        spec.grid.label_format = "unsupported"

        with _opener_for({"ok.tif": good}, unreadable_paths={"bad.tif"}) as opener:
            with pytest.raises(RenderError) as exc:
                render_map(spec, dataset_opener=opener)

        assert [issue.issue_id for issue in exc.value.issues] == [
            "render.raster.unreadable",
            "render.frame.label_format_invalid",
        ]

    def test_cancellation_after_raster_before_frame_raises_structured_issue(self) -> None:
        with pytest.raises(RenderError) as exc:
            render_map(
                _spec(layers=[], bg_color="#112233", interval=GridInterval(degrees=1)),
                is_cancelled=lambda: True,
            )

        assert [issue.issue_id for issue in exc.value.issues] == ["render.cancelled"]

    def test_raster_to_size_rejects_invalid_dimensions(self) -> None:
        with pytest.raises(RenderError) as exc:
            render_raster_layers_to_size(
                _spec(layers=[]),
                output_width=0,
                output_height=12,
            )

        assert exc.value.issues[0].issue_id == "render.output.size_invalid"
