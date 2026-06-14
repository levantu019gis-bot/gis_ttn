from __future__ import annotations

import csv
import json
import threading
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import thucthengay.download.matching as matching_module
from thucthengay.download import (
    DownloadFilenameFormatRule,
    DownloadRunStatus,
    SatelliteDownloadRequest,
)
from thucthengay.jobs import JobControl, JobState, ProgressEvent, run_satellite_download_job


def test_satellite_download_job_emits_progress_and_success_result(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    raster = source / "20260610_120000_scene_cloud12.tif"
    note = source / "readme.txt"
    geojson = tmp_path / "area.geojson"
    write_geotiff(raster)
    note.write_text("not an image", encoding="utf-8")
    write_geojson(geojson)
    events: list[ProgressEvent] = []

    result = run_satellite_download_job(
        job_id="download-success",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=tmp_path / "out",
            filename_formats=[
                DownloadFilenameFormatRule(
                    raw_format="yyyyMMdd_hhMMss_*_cloudcloud-percent.tif",
                    name="default",
                    max_cloud_percent=50,
                )
            ],
        ),
        publish=events.append,
    )

    assert result.status == DownloadRunStatus.SUCCESS
    assert result.stats.total_images == 1
    assert result.stats.scanned_images == 1
    assert result.stats.matched_images == 1
    assert result.stats.downloaded_images == 1
    assert result.manifest_path is not None
    assert result.manifest_path.is_file()
    assert [event.stage for event in events] == [
        "setup",
        "discover",
        "discover",
        "scan",
        "filter",
        "output",
        "manifest",
        "complete",
    ]
    discover_events = [event for event in events if event.stage == "discover"]
    assert discover_events[-1].scanned_file_count == 2
    assert discover_events[-1].total_image_count == 1
    assert discover_events[-1].current_source_folder == "images"
    assert any(event.current_match_context == raster.name for event in discover_events)
    assert "images=1" in discover_events[-1].message
    scan_event = next(event for event in events if event.stage == "scan")
    assert scan_event.percent == 100
    assert scan_event.total_image_count == 1
    assert scan_event.scanned_image_count == 1
    assert scan_event.matched_image_count == 1
    assert scan_event.current_source_folder == "images"
    assert scan_event.current_geojson == "area"
    complete = events[-1]
    assert complete.state == JobState.SUCCESS
    assert complete.downloaded_image_count == 1
    assert complete.skipped_existing_count == 0
    assert complete.skipped_cloud_count == 0
    assert complete.failed_image_count == 0
    assert complete.metadata_cache_hit_count == 0
    assert complete.metadata_cache_miss_count == 1


def test_satellite_download_job_reuses_cached_raster_metadata(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    raster = source / "scene.tif"
    geojson = tmp_path / "area.geojson"
    output_dir = tmp_path / "out"
    write_geotiff(raster)
    write_geojson(geojson)
    request = SatelliteDownloadRequest(
        geojson_files=[geojson],
        image_folders=[source],
        output_dir=output_dir,
        overwrite=True,
    )

    first_events: list[ProgressEvent] = []
    first = run_satellite_download_job(
        job_id="download-cache-first",
        request=request,
        publish=first_events.append,
    )
    second_events: list[ProgressEvent] = []
    second = run_satellite_download_job(
        job_id="download-cache-second",
        request=request,
        publish=second_events.append,
    )

    assert first.status == DownloadRunStatus.SUCCESS
    assert first.stats.metadata_cache_hits == 0
    assert first.stats.metadata_cache_misses == 1
    assert (output_dir / ".satellite_input_metadata_cache.sqlite3").is_file()
    assert second.status == DownloadRunStatus.SUCCESS
    assert second.stats.metadata_cache_hits == 1
    assert second.stats.metadata_cache_misses == 0
    scan_events = [event for event in second_events if event.stage == "scan"]
    assert scan_events[-1].metadata_cache_hit_count == 1
    assert "cache_hits=1" in scan_events[-1].message


def test_satellite_download_job_errors_when_no_source_images_found(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    (source / "readme.txt").write_text("not an image", encoding="utf-8")
    geojson = tmp_path / "area.geojson"
    write_geojson(geojson)
    events: list[ProgressEvent] = []

    result = run_satellite_download_job(
        job_id="download-no-images",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=tmp_path / "out",
        ),
        publish=events.append,
    )

    assert result.status == DownloadRunStatus.ERROR
    assert result.issues[0].issue_id == "satellite_download.config_invalid"
    assert "Khong tim thay anh" in result.issues[0].message
    assert events[-1].state == JobState.ERROR


def test_satellite_download_job_skips_cloudy_source_before_raster_open(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    cloudy = source / "20260610_120000_scene_cloud95.tif"
    cloudy.write_text("not a geotiff", encoding="utf-8")
    geojson = tmp_path / "area.geojson"
    write_geojson(geojson)

    result = run_satellite_download_job(
        job_id="download-cloud-prefilter",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=tmp_path / "out",
            filename_formats=[
                DownloadFilenameFormatRule(
                    raw_format="yyyyMMdd_hhMMss_*_cloudcloud-percent.tif",
                    name="cloud_rule",
                    max_cloud_percent=50,
                )
            ],
        ),
    )

    assert result.status == DownloadRunStatus.SUCCESS
    assert result.stats.total_images == 1
    assert result.stats.scanned_images == 0
    assert result.stats.failed_images == 0
    assert result.stats.skipped_cloud == 1
    rows = read_manifest(result.manifest_path)
    assert [(row["status"], row["matched_geojson"]) for row in rows] == [("skipped_cloud", "")]
    assert rows[0]["cloud_percent"] == "95"


def test_satellite_download_job_skips_existing_output_before_raster_open(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    raster = source / "scene.tif"
    raster.write_text("not a geotiff", encoding="utf-8")
    output_dir = tmp_path / "out"
    existing = output_dir / "area" / "images" / raster.name
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")
    geojson = tmp_path / "area.geojson"
    write_geojson(geojson)

    result = run_satellite_download_job(
        job_id="download-existing-prefilter",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=output_dir,
            overwrite=False,
        ),
    )

    assert result.status == DownloadRunStatus.SUCCESS
    assert result.stats.scanned_images == 0
    assert result.stats.failed_images == 0
    assert result.stats.skipped_existing == 1
    rows = read_manifest(result.manifest_path)
    assert [(row["status"], row["destination_path"], row["matched_geojson"]) for row in rows] == [
        ("skipped_existing_name", str(existing), "")
    ]


def test_satellite_download_job_reads_uncached_metadata_in_parallel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    first = source / "first.tif"
    second = source / "second.tif"
    geojson = tmp_path / "area.geojson"
    write_geotiff(first)
    write_geotiff(second)
    write_geojson(geojson)
    original_read = matching_module.read_raster_metadata
    started: list[Path] = []
    lock = threading.Lock()
    both_started = threading.Event()

    def spy_read(path: Path) -> object:
        with lock:
            started.append(path)
            if len(started) == 2:
                both_started.set()
        assert both_started.wait(timeout=2)
        return original_read(path)

    monkeypatch.setattr(matching_module, "read_raster_metadata", spy_read)

    result = run_satellite_download_job(
        job_id="download-parallel-scan",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=tmp_path / "out",
            scan_workers=2,
        ),
    )

    assert result.status == DownloadRunStatus.SUCCESS
    assert result.stats.scanned_images == 2
    assert set(started) == {first.resolve(), second.resolve()}


def test_satellite_download_job_cancellation_during_scan_returns_partial_counters(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    first = source / "first.tif"
    second = source / "second.tif"
    geojson = tmp_path / "area.geojson"
    write_geotiff(first)
    write_geotiff(second)
    write_geojson(geojson)
    control = JobControl()
    events: list[ProgressEvent] = []

    def publish(event: ProgressEvent) -> None:
        events.append(event)
        if event.stage == "scan" and event.scanned_image_count == 1:
            control.request_cancel()

    result = run_satellite_download_job(
        job_id="download-cancel-scan",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=tmp_path / "out",
        ),
        control=control,
        publish=publish,
    )

    assert result.status == DownloadRunStatus.CANCELLED
    assert result.stats.total_images == 2
    assert result.stats.scanned_images == 1
    assert result.output_rows == ()
    assert result.manifest_path is None
    assert events[-1].state == JobState.CANCELLED
    assert events[-1].failed_image_count == 0


def test_satellite_download_job_cancellation_during_output_writes_partial_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    first = source / "first.tif"
    second = source / "second.tif"
    geojson = tmp_path / "area.geojson"
    write_geotiff(first)
    write_geotiff(second)
    write_geojson(geojson)
    control = JobControl()
    events: list[ProgressEvent] = []

    def publish(event: ProgressEvent) -> None:
        events.append(event)
        if event.stage == "output" and event.downloaded_image_count == 1:
            control.request_cancel()

    result = run_satellite_download_job(
        job_id="download-cancel-output",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=tmp_path / "out",
        ),
        control=control,
        publish=publish,
    )

    assert result.status == DownloadRunStatus.CANCELLED
    assert result.stats.downloaded_images == 1
    assert len(result.output_rows) == 1
    assert result.manifest_path is not None
    rows = read_manifest(result.manifest_path)
    assert [row["status"] for row in rows] == ["copied"]
    assert events[-1].state == JobState.CANCELLED
    assert events[-1].downloaded_image_count == 1


def test_satellite_download_job_keeps_nonfatal_raster_failures_in_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    bad = source / "bad.tif"
    good = source / "good.tif"
    geojson = tmp_path / "area.geojson"
    bad.write_text("not a geotiff", encoding="utf-8")
    write_geotiff(good)
    write_geojson(geojson)
    events: list[ProgressEvent] = []

    result = run_satellite_download_job(
        job_id="download-warning",
        request=SatelliteDownloadRequest(
            geojson_files=[geojson],
            image_folders=[source],
            output_dir=tmp_path / "out",
        ),
        publish=events.append,
    )

    assert result.status == DownloadRunStatus.WARNING
    assert result.stats.scanned_images == 2
    assert result.stats.failed_images == 1
    assert result.stats.downloaded_images == 1
    assert result.issues[0].issue_id == "satellite_download.nonfatal_failures"
    rows = read_manifest(result.manifest_path)
    assert [row["status"] for row in rows] == ["copied", "failed"]
    assert "bad.tif" in rows[1]["source_path"]
    assert events[-1].state == JobState.WARNING
    assert events[-1].failed_image_count == 1


def write_geojson(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [106.05, 10.85],
                                    [106.08, 10.85],
                                    [106.08, 10.88],
                                    [106.05, 10.88],
                                    [106.05, 10.85],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def write_geotiff(path: Path) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(106.0, 11.0, 0.1, 0.1),
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))


def read_manifest(path: Path | None) -> list[dict[str, str]]:
    assert path is not None
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))
