from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds

from thucthengay.download import (
    DownloadFilenameFormatRule,
    DownloadRunStatus,
    SatelliteDownloadRequest,
)
from thucthengay.jobs import JobState, ProgressEvent, run_satellite_download_job


def test_download_job_regression_copies_multi_geojson_and_records_cloud_manifest_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images" / "20260610"
    nested = source / "nested"
    nested.mkdir(parents=True)
    clear = nested / "20260610_120000_clear_cloud12.tif"
    cloudy = nested / "20260610_130000_cloudy_cloud95.tif"
    outside = nested / "20260610_140000_outside_cloud10.tif"
    write_geotiff(clear)
    write_geotiff(cloudy)
    write_geotiff(outside, left=107.0, bottom=12.0, right=107.2, top=12.2)
    area_a = tmp_path / "area_a.geojson"
    area_b = tmp_path / "area_b.geojson"
    write_geojson(area_a, square(106.02, 10.82, 106.08, 10.88))
    write_geojson(area_b, square(106.05, 10.85, 106.12, 10.92))
    events: list[ProgressEvent] = []

    result = run_satellite_download_job(
        job_id="download-regression",
        request=SatelliteDownloadRequest(
            geojson_files=[area_a, area_b],
            image_folders=[source],
            output_dir=tmp_path / "out",
            filename_formats=[
                DownloadFilenameFormatRule(
                    name="cloud_rule",
                    raw_format="yyyyMMdd_hhMMss_*_cloudcloud-percent.tif",
                    max_cloud_percent=50,
                )
            ],
        ),
        publish=events.append,
    )

    assert result.status == DownloadRunStatus.SUCCESS
    assert result.stats.total_images == 3
    assert result.stats.scanned_images == 2
    assert result.stats.matched_images == 1
    assert result.stats.downloaded_images == 2
    assert result.stats.skipped_cloud == 1
    assert result.stats.failed_images == 0
    assert (tmp_path / "out" / "area_a" / "20260610" / "nested" / clear.name).is_file()
    assert (tmp_path / "out" / "area_b" / "20260610" / "nested" / clear.name).is_file()
    assert not (tmp_path / "out" / "area_a" / "20260610" / "nested" / cloudy.name).exists()
    assert not (tmp_path / "out" / "area_b" / "20260610" / "nested" / cloudy.name).exists()

    rows = read_manifest(result.manifest_path)
    assert [(row["status"], row["matched_geojson"]) for row in rows] == [
        ("copied", "area_a"),
        ("copied", "area_b"),
        ("skipped_cloud", ""),
    ]
    assert rows[0]["source_folder"] == "20260610"
    assert rows[0]["filename_format_matched"] == "yes"
    assert rows[0]["filename_format_rule"] == "cloud_rule"
    assert rows[0]["cloud_percent"] == "12"
    assert rows[2]["cloud_percent"] == "95"
    assert "vuot nguong" in rows[2]["error"]

    assert [event.stage for event in events] == [
        "setup",
        "discover",
        "discover",
        "discover",
        "scan",
        "scan",
        "filter",
        "output",
        "output",
        "manifest",
        "complete",
    ]
    discover_events = [event for event in events if event.stage == "discover"]
    assert discover_events[-1].scanned_file_count == 3
    assert discover_events[-1].total_image_count == 3
    assert "images=3" in discover_events[-1].message
    assert events[-1].state == JobState.SUCCESS
    assert events[-1].downloaded_image_count == 2
    assert events[-1].skipped_cloud_count == 1


def test_download_job_regression_transforms_crs_and_uses_unique_source_branches(
    tmp_path: Path,
) -> None:
    source_a = tmp_path / "source-a" / "20260610"
    source_b = tmp_path / "source-b" / "20260610"
    raster_a = source_a / "nested" / "wgs84.tif"
    raster_b = source_b / "nested" / "web_mercator.tif"
    raster_a.parent.mkdir(parents=True)
    raster_b.parent.mkdir(parents=True)
    write_geotiff(raster_a)
    write_web_mercator_geotiff(raster_b)
    area = tmp_path / "area.geojson"
    write_geojson(area, square(106.02, 10.82, 106.08, 10.88))
    events: list[ProgressEvent] = []

    result = run_satellite_download_job(
        job_id="download-crs-branches",
        request=SatelliteDownloadRequest(
            geojson_files=[area],
            image_folders=[source_a, source_b],
            output_dir=tmp_path / "out",
            preserve_source_tree=True,
        ),
        publish=events.append,
    )

    assert result.status == DownloadRunStatus.SUCCESS
    assert result.stats.total_images == 2
    assert result.stats.scanned_images == 2
    assert result.stats.matched_images == 2
    assert result.stats.downloaded_images == 2
    assert (tmp_path / "out" / "area" / "20260610" / "nested" / raster_a.name).is_file()
    assert (tmp_path / "out" / "area" / "20260610_2" / "nested" / raster_b.name).is_file()

    rows = read_manifest(result.manifest_path)
    assert [row["source_folder"] for row in rows] == ["20260610", "20260610_2"]
    destination_parts = [
        Path(row["destination_path"]).relative_to(tmp_path / "out").parts for row in rows
    ]
    assert destination_parts == [
        ("area", "20260610", "nested", "wgs84.tif"),
        ("area", "20260610_2", "nested", "web_mercator.tif"),
    ]

    scan_events = [event for event in events if event.stage == "scan"]
    assert [event.percent for event in scan_events] == [50, 100]
    assert {event.current_source_folder for event in scan_events} == {"20260610", "20260610_2"}
    assert all(event.current_geojson == "area" for event in scan_events)
    assert any("web_mercator.tif -> area" == event.current_match_context for event in scan_events)
    complete = events[-1]
    assert complete.stage == "complete"
    assert complete.scanned_image_count == 2
    assert complete.matched_image_count == 2
    assert complete.downloaded_image_count == 2


def write_geojson(path: Path, coordinates: list[list[float]]) -> None:
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
                ],
            }
        ),
        encoding="utf-8",
    )


def square(left: float, bottom: float, right: float, top: float) -> list[list[float]]:
    return [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]


def write_geotiff(
    path: Path,
    *,
    left: float = 106.0,
    bottom: float = 10.8,
    right: float = 106.2,
    top: float = 11.0,
    crs: str = "EPSG:4326",
) -> None:
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
        transform=from_bounds(left, bottom, right, top, 2, 2),
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))


def write_web_mercator_geotiff(path: Path) -> None:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    minx, miny = transformer.transform(106.0, 10.8)
    maxx, maxy = transformer.transform(106.2, 11.0)
    write_geotiff(path, left=minx, bottom=miny, right=maxx, top=maxy, crs="EPSG:3857")


def read_manifest(path: Path | None) -> list[dict[str, str]]:
    assert path is not None
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))
