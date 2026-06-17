from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds, from_origin

import thucthengay.download.matching as matching_module
from thucthengay.download import (
    SatelliteDownloadConfigError,
    SatelliteDownloadRequest,
    match_source_images,
    resolve_download_request,
)


def test_match_source_images_loads_explicit_geojson_file_shapes(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    raster = source / "scene.tif"
    write_geotiff(raster)
    feature_collection = tmp_path / "feature_collection.geojson"
    feature = tmp_path / "feature.geojson"
    geometry = tmp_path / "geometry.geojson"
    write_feature_collection(feature_collection, [square(106.05, 10.85, 106.08, 10.88)])
    write_feature(feature, square(106.06, 10.86, 106.09, 10.89))
    write_geometry(geometry, square(106.07, 10.87, 106.10, 10.90))

    result = match_source_images(
        resolve_download_request(
            SatelliteDownloadRequest(
                geojson_files=[feature_collection, feature, geometry],
                image_folders=[source],
                output_dir=tmp_path / "out",
            )
        )
    )

    assert result.failed_images == ()
    assert len(result.matches) == 1
    assert result.matches[0].path == raster.resolve()
    assert result.matches[0].matched_geojson_names == (
        "feature_collection",
        "feature",
        "geometry",
    )


def test_match_source_images_transforms_geojson_to_raster_crs(tmp_path: Path) -> None:
    source = tmp_path / "images"
    nested = source / "nested"
    nested.mkdir(parents=True)
    raster = nested / "scene.tif"
    write_web_mercator_geotiff(raster)
    area = tmp_path / "area.geojson"
    write_feature_collection(area, [square(106.05, 10.85, 106.08, 10.88)])

    result = match_source_images(
        resolve_download_request(
            SatelliteDownloadRequest(
                geojson_files=[area],
                image_folders=[source],
                output_dir=tmp_path / "out",
            )
        )
    )

    assert result.stats.total_images == 1
    assert result.stats.scanned_images == 1
    assert result.matches[0].path == raster.resolve()
    assert result.matches[0].source_folder.name == "images"


def test_match_source_images_reuses_transformed_geometry_for_same_raster_crs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    first = source / "first.tif"
    second = source / "second.tif"
    write_web_mercator_geotiff(first)
    write_web_mercator_geotiff(second)
    area = tmp_path / "area.geojson"
    write_feature_collection(area, [square(106.05, 10.85, 106.08, 10.88)])
    original_transform = matching_module._transform_geometry
    transform_calls: list[tuple[str, str]] = []

    def spy_transform(*args: object, **kwargs: object) -> object:
        transform_calls.append((str(kwargs["source_crs"]), str(kwargs["target_crs"])))
        return original_transform(*args, **kwargs)

    monkeypatch.setattr(matching_module, "_transform_geometry", spy_transform)

    result = match_source_images(
        resolve_download_request(
            SatelliteDownloadRequest(
                geojson_files=[area],
                image_folders=[source],
                output_dir=tmp_path / "out",
            )
        )
    )

    assert result.stats.scanned_images == 2
    assert result.stats.matched_images == 2
    assert len(transform_calls) == 2


def test_match_source_images_records_one_image_for_multiple_geojsons(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    raster = source / "scene.tif"
    write_geotiff(raster)
    area_a = tmp_path / "area_a.geojson"
    area_b = tmp_path / "area_b.geojson"
    outside = tmp_path / "outside.geojson"
    write_feature_collection(area_a, [square(106.05, 10.85, 106.08, 10.88)])
    write_feature_collection(area_b, [square(106.07, 10.87, 106.09, 10.89)])
    write_feature_collection(outside, [square(107.0, 12.0, 107.1, 12.1)])

    result = match_source_images(
        resolve_download_request(
            SatelliteDownloadRequest(
                geojson_files=[area_a, area_b, outside],
                image_folders=[source],
                output_dir=tmp_path / "out",
            )
        )
    )

    assert len(result.matches) == 1
    assert result.matches[0].matched_geojson_names == ("area_a", "area_b")
    assert result.matches[0].matched_geojson_paths == (area_a.resolve(), area_b.resolve())


def test_match_source_images_records_geometry_names_for_output_branches(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    raster = source / "scene.tif"
    write_geotiff(raster)
    area = tmp_path / "all_processed.geojson"
    area.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Target A"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [square(106.05, 10.85, 106.08, 10.88)],
                        },
                    },
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [square(106.07, 10.87, 106.09, 10.89)],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = match_source_images(
        resolve_download_request(
            SatelliteDownloadRequest(
                geojson_files=[area],
                image_folders=[source],
                output_dir=tmp_path / "out",
            )
        )
    )

    assert len(result.matches) == 1
    assert result.matches[0].matched_geojson_names == ("all_processed",)
    assert [item.geometry_name for item in result.matches[0].matched_geometries] == [
        "Target_A",
        "geometry_002",
    ]


def test_match_source_images_uses_yaml_sidecar_footprint_without_opening_raster(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    raster = source / "scene.tif"
    raster.write_text("not a geotiff", encoding="utf-8")
    (source / "scene.yaml").write_text(
        "\n".join(
            [
                "cloud_percent: 12",
                "the_geom: POLYGON ((0 0, 1 0, 0 1, 0 0))",
            ]
        ),
        encoding="utf-8",
    )
    inside = tmp_path / "inside.geojson"
    bbox_only = tmp_path / "bbox_only.geojson"
    write_feature_collection(inside, [square(0.10, 0.10, 0.20, 0.20)])
    write_feature_collection(bbox_only, [square(0.80, 0.80, 0.90, 0.90)])

    result = match_source_images(
        resolve_download_request(
            SatelliteDownloadRequest(
                geojson_files=[inside, bbox_only],
                image_folders=[source],
                output_dir=tmp_path / "out",
            )
        )
    )

    assert result.failed_images == ()
    assert len(result.matches) == 1
    assert result.matches[0].path == raster.resolve()
    assert result.matches[0].raster.crs == "EPSG:4326"
    assert result.matches[0].raster.footprint is not None
    assert result.matches[0].matched_geojson_names == ("inside",)


def test_match_source_images_records_failed_raster_and_continues(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    bad = source / "bad.tif"
    good = source / "good.tif"
    bad.write_text("not a geotiff", encoding="utf-8")
    write_geotiff(good)
    area = tmp_path / "area.geojson"
    write_feature_collection(area, [square(106.05, 10.85, 106.08, 10.88)])

    result = match_source_images(
        resolve_download_request(
            SatelliteDownloadRequest(
                geojson_files=[area],
                image_folders=[source],
                output_dir=tmp_path / "out",
            )
        )
    )

    assert [match.path for match in result.matches] == [good.resolve()]
    assert len(result.failed_images) == 1
    assert result.failed_images[0].path == bad.resolve()
    assert result.failed_images[0].source_folder.name == "images"
    assert "bad.tif" in result.failed_images[0].error


def test_match_source_images_rejects_invalid_geojson_with_file_context(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    invalid = tmp_path / "invalid.geojson"
    invalid.write_text("[]", encoding="utf-8")

    resolved = resolve_download_request(
        SatelliteDownloadRequest(
            geojson_files=[invalid],
            image_folders=[source],
            output_dir=tmp_path / "out",
        )
    )

    with pytest.raises(SatelliteDownloadConfigError) as exc_info:
        match_source_images(resolved)

    assert exc_info.value.field_name == "geojson_files[1]"
    assert "GeoJSON không hợp lệ" in str(exc_info.value)
    assert str(invalid.resolve()) in str(exc_info.value)


def write_feature_collection(path: Path, polygons: list[list[list[float]]]) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
                    }
                    for coordinates in polygons
                ],
            }
        ),
        encoding="utf-8",
    )


def write_feature(path: Path, coordinates: list[list[float]]) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
            }
        ),
        encoding="utf-8",
    )


def write_geometry(path: Path, coordinates: list[list[float]]) -> None:
    path.write_text(
        json.dumps({"type": "Polygon", "coordinates": [coordinates]}),
        encoding="utf-8",
    )


def square(left: float, bottom: float, right: float, top: float) -> list[list[float]]:
    return [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]


def write_geotiff(path: Path, *, crs: str = "EPSG:4326") -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs=crs,
        transform=from_origin(106.0, 11.0, 0.1, 0.1),
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))


def write_web_mercator_geotiff(path: Path) -> None:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    minx, miny = transformer.transform(106.0, 10.8)
    maxx, maxy = transformer.transform(106.2, 11.0)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:3857",
        transform=from_bounds(minx, miny, maxx, maxy, 2, 2),
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))
