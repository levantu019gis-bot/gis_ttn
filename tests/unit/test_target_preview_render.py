from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    TargetConfig,
    TargetExportConfig,
    ViewState,
)
from thucthengay.render import RenderSpecError, build_target_preview_spec


def _write_raster(
    path: Path,
    bounds: tuple[float, float, float, float],
    fill: int,
    *,
    width: int = 16,
    height: int = 16,
    tiled: bool = False,
    overviews: bool = False,
) -> None:
    data = np.full((3, height, width), fill, dtype=np.uint8)
    kwargs = {}
    if tiled:
        kwargs = {
            "tiled": True,
            "blockxsize": 16,
            "blockysize": 16,
        }
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=3,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_bounds(*bounds, width=width, height=height),
        **kwargs,
    ) as dataset:
        dataset.write(data)
        if overviews:
            dataset.build_overviews([2, 4], rasterio.enums.Resampling.nearest)


def _target() -> TargetConfig:
    return TargetConfig(
        id="alpha",
        sort_order=1,
        name="Alpha",
        geojson_file="alpha.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(template_metadata_file="alpha.template.json"),
        metadata={"target_preview_background": "#112233"},
    )


def _target_with_export_background() -> TargetConfig:
    return TargetConfig(
        id="alpha",
        sort_order=1,
        name="Alpha",
        geojson_file="alpha.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(
            template_metadata_file="alpha.template.json",
            map_background_color="#445566",
        ),
    )


def _composition(layers: list[ImageLayer]) -> Composition:
    return Composition(
        composition_id="alpha__20260525",
        target_id="alpha",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
        layers=layers,
    )


def test_target_preview_spec_covers_union_of_visible_layers_only(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.tif"
    second = tmp_path / "second.tif"
    _write_raster(first, (106.0, 10.0, 106.5, 10.5), fill=30)
    _write_raster(second, (106.4, 10.4, 107.0, 11.0), fill=200)
    composition = _composition(
        [
            ImageLayer(layer_id="first", source_path=str(first), visible=False, order=1),
            ImageLayer(layer_id="second", source_path=str(second), visible=True, order=0),
        ]
    )

    spec = build_target_preview_spec(
        composition=composition,
        target=_target(),
        output_width=320,
        output_height=180,
    )

    assert [layer.layer_id for layer in spec.visible_layers] == ["second"]
    assert spec.geo_window.min_lon <= 106.4
    assert spec.geo_window.min_lat <= 10.4
    assert spec.geo_window.min_lon > 106.0
    assert spec.geo_window.min_lat > 10.0
    assert spec.geo_window.max_lon >= 107.0
    assert spec.geo_window.max_lat >= 11.0
    assert spec.output_width <= 320
    assert spec.output_height <= 180
    assert spec.background.color == "#112233"


def test_target_preview_spec_uses_export_map_background_when_metadata_missing(
    tmp_path: Path,
) -> None:
    raster = tmp_path / "first.tif"
    _write_raster(raster, (106.0, 10.0, 106.5, 10.5), fill=30)
    composition = _composition(
        [ImageLayer(layer_id="first", source_path=str(raster), visible=True, order=0)]
    )

    spec = build_target_preview_spec(
        composition=composition,
        target=_target_with_export_background(),
        output_width=320,
        output_height=180,
    )

    assert spec.background.color == "#445566"


def test_target_preview_spec_requires_at_least_one_layer() -> None:
    with pytest.raises(RenderSpecError) as exc_info:
        build_target_preview_spec(
            composition=_composition([]),
            target=_target(),
            output_width=320,
            output_height=180,
        )

    assert exc_info.value.issues[0].issue_id == "target_preview.no_layers"


def test_target_preview_spec_requires_at_least_one_visible_layer() -> None:
    with pytest.raises(RenderSpecError) as exc_info:
        build_target_preview_spec(
            composition=_composition(
                [ImageLayer(layer_id="hidden", source_path="hidden.tif", visible=False, order=0)]
            ),
            target=_target(),
            output_width=320,
            output_height=180,
        )

    assert exc_info.value.issues[0].issue_id == "target_preview.no_visible_layers"


def test_target_preview_blocks_large_unoptimized_raster(tmp_path: Path) -> None:
    raster = tmp_path / "large-unoptimized.tif"
    _write_raster(
        raster,
        (106.0, 10.0, 106.5, 10.5),
        fill=30,
        width=64,
        height=64,
        tiled=True,
        overviews=False,
    )
    composition = _composition(
        [ImageLayer(layer_id="large", source_path=str(raster), visible=True, order=0)]
    )

    with pytest.raises(RenderSpecError) as exc_info:
        build_target_preview_spec(
            composition=composition,
            target=_target(),
            output_width=320,
            output_height=180,
            expensive_dimension_threshold=32,
        )

    assert exc_info.value.issues[0].issue_id == "target_preview.raster_not_optimized"


def test_target_preview_allows_optimized_cache_path_for_large_raster(tmp_path: Path) -> None:
    source = tmp_path / "source-unoptimized.tif"
    cache = tmp_path / "cache-ready.tif"
    _write_raster(
        source,
        (106.0, 10.0, 106.5, 10.5),
        fill=30,
        width=64,
        height=64,
        tiled=True,
        overviews=False,
    )
    _write_raster(
        cache,
        (106.0, 10.0, 106.5, 10.5),
        fill=30,
        width=64,
        height=64,
        tiled=True,
        overviews=True,
    )
    composition = _composition(
        [
            ImageLayer(
                layer_id="large",
                source_path=str(source),
                cache_path=str(cache),
                visible=True,
                order=0,
            )
        ]
    )

    spec = build_target_preview_spec(
        composition=composition,
        target=_target(),
        output_width=320,
        output_height=180,
        expensive_dimension_threshold=32,
    )

    assert spec.visible_layers[0].cache_path == str(cache)
