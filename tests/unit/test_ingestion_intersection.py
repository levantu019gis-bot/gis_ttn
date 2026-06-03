from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds, from_origin

from thucthengay.config.service import ConfigLoadResult, ResolvedTargetPaths
from thucthengay.ingestion import match_imagery_to_targets, scan_imagery_folder
from thucthengay.models import GridConfig, GridInterval, TargetConfig, TargetExportConfig


def target_config(target_id: str, *, enabled: bool = True) -> TargetConfig:
    return TargetConfig(
        id=target_id,
        enabled=enabled,
        sort_order=1,
        name=target_id,
        geojson_file=f"{target_id}.geojson",
        coordinate=[106.0, 11.0],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(template_metadata_file=f"{target_id}.template.json"),
    )


def config_result_for(
    targets: list[TargetConfig],
    paths: dict[str, Path],
) -> ConfigLoadResult:
    enabled_targets = [target for target in targets if target.enabled]
    return ConfigLoadResult(
        config_path=Path("config.json"),
        config=None,
        enabled_targets=enabled_targets,
        target_paths={
            target.id: ResolvedTargetPaths(
                target_id=target.id,
                geojson_file=paths[target.id],
                template_metadata_file=Path(f"{target.id}.template.json"),
            )
            for target in enabled_targets
        },
    )


def write_geojson(path: Path, coordinates: list[list[float]], crs_name: str | None = None) -> None:
    data: dict[str, object] = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
            }
        ],
    }
    if crs_name:
        data["crs"] = {"type": "name", "properties": {"name": crs_name}}
    path.write_text(json.dumps(data), encoding="utf-8")


def write_geotiff(path: Path, *, crs: str = "EPSG:4326") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def square(left: float, bottom: float, right: float, top: float) -> list[list[float]]:
    return [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]


def test_matching_records_intersections_for_enabled_targets(tmp_path: Path) -> None:
    geotiff = tmp_path / "20260525_101112_scene.tif"
    write_geotiff(geotiff)
    inside = tmp_path / "inside.geojson"
    outside = tmp_path / "outside.geojson"
    write_geojson(inside, square(106.05, 10.85, 106.08, 10.88))
    write_geojson(outside, square(107.0, 12.0, 107.1, 12.1))

    scan_result = scan_imagery_folder(tmp_path)
    config_result = config_result_for(
        [target_config("inside"), target_config("outside")],
        {"inside": inside, "outside": outside},
    )

    result = match_imagery_to_targets(scan_result.rasters, config_result)

    assert result.issues == []
    paths_by_target = {
        target_id: [match.image.path for match in matches]
        for target_id, matches in result.matches.items()
    }
    assert paths_by_target == {
        "inside": [geotiff],
        "outside": [],
    }


def test_matching_uses_inline_target_geometry_when_geojson_file_is_absent(
    tmp_path: Path,
) -> None:
    geotiff = tmp_path / "20260525_101112_scene.tif"
    write_geotiff(geotiff)
    target = target_config("inline").model_copy(
        update={
            "geojson_file": None,
            "metadata": {
                "geojson_geometry": {
                    "type": "Polygon",
                    "coordinates": [square(106.05, 10.85, 106.08, 10.88)],
                }
            },
        }
    )
    config_result = ConfigLoadResult(
        config_path=Path("config.json"),
        config=None,
        enabled_targets=[target],
        target_paths={
            "inline": ResolvedTargetPaths(
                target_id="inline",
                template_metadata_file=Path("inline.template.json"),
            )
        },
    )

    scan_result = scan_imagery_folder(tmp_path)
    result = match_imagery_to_targets(scan_result.rasters, config_result)

    assert result.issues == []
    assert [match.image.path for match in result.matches["inline"]] == [geotiff]


def test_matching_transforms_target_geometry_to_raster_crs(tmp_path: Path) -> None:
    geotiff = tmp_path / "20260525_101112_scene.tif"
    write_web_mercator_geotiff(geotiff)
    boundary = tmp_path / "target.geojson"
    write_geojson(boundary, square(106.05, 10.85, 106.08, 10.88))

    scan_result = scan_imagery_folder(tmp_path)
    config_result = config_result_for([target_config("target")], {"target": boundary})

    result = match_imagery_to_targets(scan_result.rasters, config_result)

    assert result.issues == []
    assert [match.image.path for match in result.matches["target"]] == [geotiff]


def test_disabled_targets_are_not_matched(tmp_path: Path) -> None:
    geotiff = tmp_path / "20260525_101112_scene.tif"
    write_geotiff(geotiff)
    disabled_boundary = tmp_path / "disabled.geojson"
    write_geojson(disabled_boundary, square(106.05, 10.85, 106.08, 10.88))

    scan_result = scan_imagery_folder(tmp_path)
    config_result = config_result_for(
        [target_config("disabled", enabled=False)],
        {"disabled": disabled_boundary},
    )

    result = match_imagery_to_targets(scan_result.rasters, config_result)

    assert result.matches == {}
    assert result.issues == []


def test_missing_or_invalid_boundaries_report_target_issues_and_continue(tmp_path: Path) -> None:
    geotiff = tmp_path / "20260525_101112_scene.tif"
    write_geotiff(geotiff)
    valid_boundary = tmp_path / "valid.geojson"
    invalid_boundary = tmp_path / "invalid.geojson"
    missing_boundary = tmp_path / "missing.geojson"
    write_geojson(valid_boundary, square(106.05, 10.85, 106.08, 10.88))
    invalid_boundary.write_text("not json", encoding="utf-8")

    scan_result = scan_imagery_folder(tmp_path)
    config_result = config_result_for(
        [
            target_config("invalid"),
            target_config("missing"),
            target_config("valid"),
        ],
        {
            "invalid": invalid_boundary,
            "missing": missing_boundary,
            "valid": valid_boundary,
        },
    )

    result = match_imagery_to_targets(scan_result.rasters, config_result)

    assert {issue.issue_id for issue in result.issues} == {
        "target.geojson_invalid",
        "target.geojson_missing",
    }
    assert [match.image.path for match in result.matches["valid"]] == [geotiff]
    assert result.matches["invalid"] == []
    assert result.matches["missing"] == []
    assert all(issue.blocking for issue in result.issues)


def test_non_object_geojson_reports_target_issue_instead_of_crashing(tmp_path: Path) -> None:
    geotiff = tmp_path / "20260525_101112_scene.tif"
    write_geotiff(geotiff)
    bad_boundary = tmp_path / "bad.geojson"
    bad_boundary.write_text("[]", encoding="utf-8")

    scan_result = scan_imagery_folder(tmp_path)
    config_result = config_result_for([target_config("bad")], {"bad": bad_boundary})

    result = match_imagery_to_targets(scan_result.rasters, config_result)

    assert result.matches["bad"] == []
    assert [issue.issue_id for issue in result.issues] == ["target.geojson_invalid"]
