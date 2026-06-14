from __future__ import annotations

from datetime import datetime
from pathlib import Path

from thucthengay.download import (
    DownloadFilenameFormatRule,
    DownloadImageFolder,
    DownloadImageMatch,
    DownloadMatchResult,
    DownloadRasterMetadata,
    DownloadStats,
    filename_format_warnings,
    filter_matches_by_filename_metadata,
)


def test_first_matching_rule_extracts_datetime_cloud_and_rule_name(tmp_path: Path) -> None:
    match = make_match(tmp_path / "PSScene_20260610_123456_cloud_12.5.tif")
    result = filter_matches_by_filename_metadata(
        DownloadMatchResult(
            matches=(match,),
            failed_images=(),
            stats=DownloadStats(matched_images=1),
        ),
        (
            DownloadFilenameFormatRule(
                name="planet_specific",
                raw_format="PSScene_yyyyMMdd_hhMMss_cloud_cloud-percent.tif",
                max_cloud_percent=80,
            ),
            DownloadFilenameFormatRule(
                name="planet_fallback",
                raw_format="PSScene_*_cloud_cloud-percent.tif",
                max_cloud_percent=10,
            ),
        ),
    )

    assert len(result.accepted_matches) == 1
    metadata = result.accepted_matches[0].metadata
    assert metadata.matched_format is True
    assert metadata.matched_format_name == "planet_specific"
    assert metadata.capture_datetime == datetime(2026, 6, 10, 12, 34, 56)
    assert metadata.cloud_percent == 12.5
    assert metadata.max_cloud_percent == 80
    assert result.skipped_cloud_images == ()
    assert result.stats.matched_images == 1
    assert result.stats.skipped_cloud == 0


def test_over_threshold_cloud_is_skipped(tmp_path: Path) -> None:
    match = make_match(tmp_path / "scene_20260610_123456_cloud_91.tif")
    result = filter_matches_by_filename_metadata(
        DownloadMatchResult(
            matches=(match,),
            failed_images=(),
            stats=DownloadStats(matched_images=1),
        ),
        (
            DownloadFilenameFormatRule(
                name="cloud_filter",
                raw_format="scene_yyyyMMdd_HHmmss_cloud_cloud_percent.tif",
                max_cloud_percent=90,
            ),
        ),
    )

    assert result.accepted_matches == ()
    assert len(result.skipped_cloud_images) == 1
    skipped = result.skipped_cloud_images[0]
    assert skipped.match == match
    assert skipped.metadata.cloud_percent == 91
    assert skipped.status == "skipped_cloud"
    assert "91" in skipped.reason
    assert result.stats.matched_images == 0
    assert result.stats.skipped_cloud == 1


def test_unmatched_filename_stays_accepted_with_unmatched_metadata(tmp_path: Path) -> None:
    match = make_match(tmp_path / "freeform.tif")
    result = filter_matches_by_filename_metadata(
        DownloadMatchResult(
            matches=(match,),
            failed_images=(),
            stats=DownloadStats(matched_images=1),
        ),
        (
            DownloadFilenameFormatRule(
                name="known",
                raw_format="scene_yyyyMMdd_hhMMss_cloud_cloud-percent.tif",
                max_cloud_percent=10,
            ),
        ),
    )

    assert len(result.accepted_matches) == 1
    metadata = result.accepted_matches[0].metadata
    assert metadata.matched_format is False
    assert metadata.matched_format_name is None
    assert metadata.capture_datetime is None
    assert metadata.cloud_percent is None
    assert result.skipped_cloud_images == ()


def test_overlapping_rules_produce_vietnamese_warning() -> None:
    warnings = filename_format_warnings(
        (
            DownloadFilenameFormatRule(name="broad", raw_format="PSScene_*"),
            DownloadFilenameFormatRule(
                name="specific",
                raw_format="PSScene_yyyyMMdd_hhMMss_cloud_cloud-percent.tif",
                max_cloud_percent=20,
            ),
        )
    )

    assert len(warnings) == 1
    assert "broad" in warnings[0]
    assert "specific" in warnings[0]
    assert "match truoc" in warnings[0]
    assert "dat rule sau len truoc" in warnings[0]


def make_match(path: Path) -> DownloadImageMatch:
    return DownloadImageMatch(
        source_folder=DownloadImageFolder(name="source", path=path.parent),
        path=path,
        raster=DownloadRasterMetadata(crs="EPSG:4326", bounds=(0.0, 0.0, 1.0, 1.0)),
        matched_geojson_names=("area",),
        matched_geojson_paths=(path.parent / "area.geojson",),
    )
