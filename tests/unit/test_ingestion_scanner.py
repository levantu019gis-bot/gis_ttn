from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from thucthengay.ingestion import scan_imagery_folder
from thucthengay.ingestion.metadata_parser import _try_pattern_match
from thucthengay.models import FilenamePatternConfig, IssueSeverity, MetadataSource, MetadataStatus


def write_geotiff(
    path: Path,
    *,
    tags: dict[str, str] | None = None,
    crs: str | None = "EPSG:4326",
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
        transform=from_origin(106.0, 11.0, 0.01, 0.01),
        nodata=0,
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))
        if tags:
            dataset.update_tags(**tags)


def write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_scan_recursively_discovers_geotiffs_and_ignores_unsupported_files(tmp_path: Path) -> None:
    geotiff = tmp_path / "nested" / "20260525_101112_psscene_cloud12.tif"
    write_geotiff(geotiff)
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    (tmp_path / "nested" / "20260525_101112_psscene_cloud12.tif.json").write_text(
        "{}",
        encoding="utf-8",
    )

    result = scan_imagery_folder(tmp_path)

    assert [item.path for item in result.rasters] == [geotiff]
    assert result.rasters[0].layer.capture_date.isoformat() == "2026-05-25"
    assert result.rasters[0].layer.capture_time.isoformat() == "17:11:12"
    assert result.rasters[0].layer.cloud_percent == 12
    assert result.warnings == []


def test_scan_converts_filename_utc_timestamp_to_local_date_and_time(
    tmp_path: Path,
) -> None:
    geotiff = tmp_path / "20260525_230000_psscene.tif"
    write_geotiff(geotiff)

    result = scan_imagery_folder(tmp_path)

    assert len(result.rasters) == 1
    layer = result.rasters[0].layer
    assert layer.capture_date is not None
    assert layer.capture_date.isoformat() == "2026-05-26"
    assert layer.capture_time is not None
    assert layer.capture_time.isoformat() == "06:00:00"


def test_scan_uses_unique_layer_ids_for_duplicate_filenames_in_subfolders(tmp_path: Path) -> None:
    first = tmp_path / "a" / "20260525_101112_psscene.tif"
    second = tmp_path / "b" / "20260525_101112_psscene.tif"
    write_geotiff(first)
    write_geotiff(second)

    result = scan_imagery_folder(tmp_path)

    layer_ids = [item.layer.layer_id for item in result.rasters]
    assert len(layer_ids) == len(set(layer_ids))
    assert all(layer_id.startswith("20260525_101112_psscene__") for layer_id in layer_ids)


def test_sidecar_metadata_takes_precedence_and_records_field_sources(tmp_path: Path) -> None:
    geotiff = tmp_path / "20260525_101112_psscene_cloud12.tif"
    write_geotiff(geotiff)
    write_json(
        tmp_path / "20260525_101112_psscene_cloud12.tif.json",
        {
            "properties": {
                "acquired": "2026-05-26T03:04:05Z",
                "cloud_cover": 8.5,
                "item_id": "sidecar-item",
            }
        },
    )

    result = scan_imagery_folder(tmp_path)
    scanned = result.rasters[0]

    assert scanned.layer.capture_date.isoformat() == "2026-05-26"
    assert scanned.layer.capture_time.isoformat() == "03:04:05"
    assert scanned.layer.cloud_percent == 8.5
    assert scanned.source_identifier == "sidecar-item"
    assert scanned.layer.metadata_source == MetadataSource.SIDECAR
    assert scanned.metadata_field_sources == {
        "capture_date": MetadataSource.SIDECAR,
        "capture_time": MetadataSource.SIDECAR,
        "cloud_percent": MetadataSource.SIDECAR,
        "source_identifier": MetadataSource.SIDECAR,
    }


def test_embedded_tags_are_used_when_filename_and_sidecar_are_unusable(tmp_path: Path) -> None:
    geotiff = tmp_path / "raw_image.tif"
    write_geotiff(
        geotiff,
        tags={
            "acquired": "2026-05-25T01:02:03Z",
            "cloud_percent": "23",
            "source_id": "embedded-item",
        },
    )

    result = scan_imagery_folder(tmp_path)
    scanned = result.rasters[0]

    assert scanned.layer.capture_date.isoformat() == "2026-05-25"
    assert scanned.layer.capture_time.isoformat() == "01:02:03"
    assert scanned.layer.cloud_percent == 23
    assert scanned.source_identifier == "embedded-item"
    assert scanned.layer.metadata_source == MetadataSource.EMBEDDED
    assert scanned.raster.crs == "EPSG:4326"
    assert scanned.raster.width == 2
    assert scanned.raster.height == 2
    assert scanned.raster.band_count == 1
    assert scanned.raster.nodata == 0
    assert scanned.raster.bounds.left == 106.0


def test_missing_business_metadata_warns_but_keeps_valid_footprint(tmp_path: Path) -> None:
    geotiff = tmp_path / "raw_image.tif"
    write_geotiff(geotiff)

    result = scan_imagery_folder(tmp_path)

    assert [item.path for item in result.rasters] == [geotiff]
    assert result.rasters[0].layer.metadata_status == MetadataStatus.NEEDS_MANUAL_CORRECTION
    assert {warning.issue_id for warning in result.warnings} == {"imagery.metadata_missing"}
    assert result.warnings[0].severity == IssueSeverity.WARNING
    assert str(geotiff) in result.warnings[0].message


def test_unreadable_geotiff_is_warned_and_excluded_from_valid_rasters(tmp_path: Path) -> None:
    bad_raster = tmp_path / "broken.tif"
    bad_raster.write_text("not a real geotiff", encoding="utf-8")

    result = scan_imagery_folder(tmp_path)

    assert result.rasters == []
    assert len(result.warnings) == 1
    assert result.warnings[0].issue_id == "imagery.geotiff_unreadable"
    assert result.warnings[0].severity == IssueSeverity.WARNING
    assert str(bad_raster) in result.warnings[0].message


def test_geotiff_without_valid_footprint_is_warned_and_excluded(tmp_path: Path) -> None:
    geotiff = tmp_path / "20260525_101112_psscene.tif"
    write_geotiff(geotiff, crs=None)

    result = scan_imagery_folder(tmp_path)

    assert result.rasters == []
    assert len(result.warnings) == 1
    assert result.warnings[0].issue_id == "imagery.invalid_footprint"
    assert str(geotiff) in result.warnings[0].message


# --- FilenamePattern matching tests ---


def _pattern(name: str, pattern: str, separator: str = "_") -> FilenamePatternConfig:
    return FilenamePatternConfig(name=name, pattern=pattern, separator=separator)


class TestTryPatternMatch:
    def test_psscene_full_pattern(self) -> None:
        pat = _pattern("ps", "*_yyyyMMdd_HHmmss_*_*_cloud_cloud-percent")
        result = _try_pattern_match("PSScene_20260526_024535_12_255b_cloud_10.0", pat)
        assert result.capture_date is not None
        assert result.capture_date.isoformat() == "2026-05-26"
        assert result.capture_time is not None
        assert result.capture_time.isoformat() == "09:45:35"
        assert result.cloud_percent == 10.0
        assert result.field_sources["capture_date"] == MetadataSource.FILENAME
        assert result.field_sources["capture_time"] == MetadataSource.FILENAME
        assert result.field_sources["cloud_percent"] == MetadataSource.FILENAME
        assert result.source_identifier is not None

    def test_simple_date_time_pattern(self) -> None:
        pat = _pattern("simple", "yyyyMMdd_HHmmss_*")
        result = _try_pattern_match("20260101_120000_scene", pat)
        assert result.capture_date is not None
        assert result.capture_date.isoformat() == "2026-01-01"
        assert result.capture_time is not None
        assert result.capture_time.isoformat() == "19:00:00"
        assert result.cloud_percent is None

    def test_pattern_date_time_rolls_over_to_next_local_day(self) -> None:
        pat = _pattern("simple", "yyyyMMdd_HHmmss_*")
        result = _try_pattern_match("20260101_230000_scene", pat)
        assert result.capture_date is not None
        assert result.capture_date.isoformat() == "2026-01-02"
        assert result.capture_time is not None
        assert result.capture_time.isoformat() == "06:00:00"

    def test_segment_count_mismatch_returns_empty(self) -> None:
        pat = _pattern("ps", "*_yyyyMMdd_HHmmss")
        result = _try_pattern_match("PSScene_20260526_024535_extra", pat)
        assert result.field_sources == {}

    def test_literal_mismatch_returns_empty(self) -> None:
        pat = _pattern("ps", "*_yyyyMMdd_HHmmss_cloud_cloud-percent")
        result = _try_pattern_match("PSScene_20260526_024535_rain_10.0", pat)
        assert result.field_sources == {}

    def test_invalid_date_returns_empty(self) -> None:
        pat = _pattern("ps", "yyyyMMdd_HHmmss_*")
        result = _try_pattern_match("99991301_120000_scene", pat)
        assert result.field_sources == {}

    def test_invalid_time_returns_empty(self) -> None:
        pat = _pattern("ps", "yyyyMMdd_HHmmss_*")
        result = _try_pattern_match("20260101_259999_scene", pat)
        assert result.field_sources == {}

    def test_cloud_percent_optional_in_pattern(self) -> None:
        pat = _pattern("ps", "*_yyyyMMdd_HHmmss_cloud-percent")
        result = _try_pattern_match("PSScene_20260526_024535_notanumber", pat)
        assert result.capture_date is not None
        assert result.cloud_percent is None

    def test_date_only_pattern(self) -> None:
        pat = _pattern("date", "*_yyyyMMdd")
        result = _try_pattern_match("mosaic_20260526", pat)
        assert result.capture_date is not None
        assert result.capture_date.isoformat() == "2026-05-26"
        assert result.capture_time is None


def test_scan_with_filename_patterns_extracts_metadata(tmp_path: Path) -> None:
    geotiff = tmp_path / "PSScene_20260526_024535_12_255b_cloud_10.0.tif"
    write_geotiff(geotiff)

    patterns = [_pattern("ps", "*_yyyyMMdd_HHmmss_*_*_cloud_cloud-percent")]
    result = scan_imagery_folder(tmp_path, filename_patterns=patterns)

    assert len(result.rasters) == 1
    layer = result.rasters[0].layer
    assert layer.capture_date is not None
    assert layer.capture_date.isoformat() == "2026-05-26"
    assert layer.capture_time is not None
    assert layer.capture_time.isoformat() == "09:45:35"
    assert layer.cloud_percent == 10.0
    assert layer.metadata_status == MetadataStatus.VALID
    assert layer.metadata_source == MetadataSource.FILENAME
