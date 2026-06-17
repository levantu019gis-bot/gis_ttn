from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from thucthengay.download import (
    DownloadFilenameFilterResult,
    DownloadFilenameMetadata,
    DownloadImageFolder,
    DownloadImageMatch,
    DownloadMatchedGeometry,
    DownloadOutputStructure,
    DownloadRasterMetadata,
    DownloadStats,
    FailedDownloadImage,
    PreparedDownloadImage,
    ResolvedSatelliteDownloadRequest,
    SkippedCloudDownloadImage,
    write_download_outputs,
)


def test_output_tree_uses_geojson_source_branch_and_preserves_relative_path(tmp_path: Path) -> None:
    source = tmp_path / "input" / "20260613"
    raster = source / "nested" / "scene.tif"
    raster.parent.mkdir(parents=True)
    raster.write_bytes(b"scene")
    request = make_request(tmp_path, source, preserve_source_tree=True)
    match = make_match(raster, source, ("all_processed",), (tmp_path / "all_processed.geojson",))

    result = write_download_outputs(
        request,
        DownloadFilenameFilterResult(
            accepted_matches=(PreparedDownloadImage(match=match, metadata=metadata()),),
            skipped_cloud_images=(),
            failed_images=(),
            warnings=(),
            stats=DownloadStats(total_images=1, scanned_images=1, matched_images=1),
        ),
    )

    expected = tmp_path / "out" / "all_processed" / "20260613" / "nested" / "scene.tif"
    assert expected.read_bytes() == b"scene"
    assert result.rows[0].status == "copied"
    assert result.rows[0].destination_path == expected
    assert result.stats.downloaded_images == 1


def test_duplicate_safe_names_use_suffixes_and_manifest_remains_traceable(tmp_path: Path) -> None:
    source_a = tmp_path / "source" / "20260613"
    source_b = tmp_path / "other" / "20260613"
    raster_a = source_a / "a.tif"
    raster_b = source_b / "b.tif"
    raster_a.parent.mkdir(parents=True)
    raster_b.parent.mkdir(parents=True)
    raster_a.write_bytes(b"a")
    raster_b.write_bytes(b"b")
    geojson_a = tmp_path / "geo" / "all processed.geojson"
    geojson_b = tmp_path / "geo" / "all#processed.geojson"
    geojson_a.parent.mkdir()
    request = make_request(
        tmp_path,
        source_a,
        image_folders=(
            DownloadImageFolder(name="20260613", path=source_a),
            DownloadImageFolder(name="20260613_2", path=source_b),
        ),
        geojson_files=(geojson_a, geojson_b),
        preserve_source_tree=False,
    )
    match_a = make_match(raster_a, source_a, ("all_processed",), (geojson_a,))
    match_b = make_match(raster_b, source_b, ("all_processed_2",), (geojson_b,))

    result = write_download_outputs(
        request,
        DownloadFilenameFilterResult(
            accepted_matches=(
                PreparedDownloadImage(match=match_a, metadata=metadata()),
                PreparedDownloadImage(match=match_b, metadata=metadata()),
            ),
            skipped_cloud_images=(),
            failed_images=(),
            warnings=(),
            stats=DownloadStats(total_images=2, scanned_images=2, matched_images=2),
        ),
    )

    branch_parts = [
        row.destination_path.relative_to(request.output_dir).parts[:2]
        for row in result.rows
        if row.destination_path is not None
    ]
    assert branch_parts == [
        ("all_processed", "20260613"),
        ("all_processed_2", "20260613_2"),
    ]
    manifest_rows = read_manifest(result.manifest_path)
    assert manifest_rows[0]["source_path"] == str(raster_a)
    assert manifest_rows[0]["matched_geojson"] == "all_processed"
    assert manifest_rows[1]["source_path"] == str(raster_b)
    assert manifest_rows[1]["matched_geojson"] == "all_processed_2"


def test_output_tree_can_group_by_geojson_source_folder_and_geometry(tmp_path: Path) -> None:
    source = tmp_path / "input" / "20260613"
    raster = source / "nested" / "scene.tif"
    raster.parent.mkdir(parents=True)
    raster.write_bytes(b"scene")
    geojson = tmp_path / "all_processed.geojson"
    request = make_request(
        tmp_path,
        source,
        geojson_files=(geojson,),
        output_structure=DownloadOutputStructure.GEOJSON_SOURCE_GEOMETRY,
        preserve_source_tree=True,
    )
    match = make_match(
        raster,
        source,
        ("all_processed",),
        (geojson,),
        matched_geometries=(
            DownloadMatchedGeometry(
                geojson_name="all_processed",
                geojson_path=geojson,
                geometry_name="Target_A",
            ),
            DownloadMatchedGeometry(
                geojson_name="all_processed",
                geojson_path=geojson,
                geometry_name="geometry_002",
            ),
        ),
    )

    result = write_download_outputs(
        request,
        DownloadFilenameFilterResult(
            accepted_matches=(PreparedDownloadImage(match=match, metadata=metadata()),),
            skipped_cloud_images=(),
            failed_images=(),
            warnings=(),
            stats=DownloadStats(total_images=1, scanned_images=1, matched_images=1),
        ),
    )

    expected_a = (
        tmp_path
        / "out"
        / "all_processed"
        / "20260613"
        / "Target_A"
        / "nested"
        / "scene.tif"
    )
    expected_b = (
        tmp_path
        / "out"
        / "all_processed"
        / "20260613"
        / "geometry_002"
        / "nested"
        / "scene.tif"
    )
    assert expected_a.read_bytes() == b"scene"
    assert expected_b.read_bytes() == b"scene"
    assert [row.destination_path for row in result.rows] == [expected_a, expected_b]
    assert [row.matched_geojson for row in result.rows] == [
        "all_processed/Target_A",
        "all_processed/geometry_002",
    ]
    assert result.stats.downloaded_images == 2


def test_skipped_existing_and_dry_run_do_not_overwrite_or_create_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    raster = source / "scene.tif"
    source.mkdir()
    raster.write_bytes(b"new")
    request = make_request(tmp_path, source, overwrite=False, preserve_source_tree=False)
    existing = tmp_path / "out" / "area" / "images" / "scene.tif"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")
    match = make_match(raster, source, ("area",), (tmp_path / "area.geojson",))

    skipped = write_download_outputs(
        request,
        DownloadFilenameFilterResult(
            accepted_matches=(PreparedDownloadImage(match=match, metadata=metadata()),),
            skipped_cloud_images=(),
            failed_images=(),
            warnings=(),
            stats=DownloadStats(total_images=1, scanned_images=1, matched_images=1),
        ),
    )

    assert existing.read_bytes() == b"old"
    assert skipped.rows[0].status == "skipped_existing"
    assert skipped.stats.skipped_existing == 1

    dry_run_request = make_request(
        tmp_path,
        source,
        output_dir=tmp_path / "dry-run-out",
        dry_run=True,
        preserve_source_tree=False,
    )
    dry_run = write_download_outputs(
        dry_run_request,
        DownloadFilenameFilterResult(
            accepted_matches=(PreparedDownloadImage(match=match, metadata=metadata()),),
            skipped_cloud_images=(),
            failed_images=(),
            warnings=(),
            stats=DownloadStats(total_images=1, scanned_images=1, matched_images=1),
        ),
    )

    assert dry_run.rows[0].status == "dry_run"
    assert dry_run.rows[0].destination_path == (
        tmp_path / "dry-run-out" / "area" / "images" / "scene.tif"
    )
    assert not dry_run.rows[0].destination_path.exists()
    assert dry_run.stats.downloaded_images == 0


def test_manifest_contains_accepted_skipped_cloud_and_failed_rows_with_metadata(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    raster = source / "scene.tif"
    cloudy = source / "cloudy.tif"
    failed = source / "failed.tif"
    source.mkdir()
    raster.write_bytes(b"scene")
    cloudy.write_bytes(b"cloudy")
    request = make_request(tmp_path, source, preserve_source_tree=False)
    accepted_match = make_match(raster, source, ("area",), (tmp_path / "area.geojson",))
    cloudy_match = make_match(cloudy, source, ("area",), (tmp_path / "area.geojson",))

    result = write_download_outputs(
        request,
        DownloadFilenameFilterResult(
            accepted_matches=(
                PreparedDownloadImage(
                    match=accepted_match,
                    metadata=metadata(
                        matched_format=True,
                        matched_format_name="planet",
                        capture_datetime=datetime(2026, 6, 10, 12, 34, 56),
                        cloud_percent=12.5,
                        max_cloud_percent=90,
                    ),
                ),
            ),
            skipped_cloud_images=(
                SkippedCloudDownloadImage(
                    match=cloudy_match,
                    metadata=metadata(
                        matched_format=True,
                        matched_format_name="planet",
                        cloud_percent=95,
                        max_cloud_percent=90,
                    ),
                    reason="cloud too high",
                ),
            ),
            failed_images=(
                FailedDownloadImage(
                    source_folder=DownloadImageFolder("images", source),
                    path=failed,
                    error="bad raster",
                ),
            ),
            warnings=(),
            stats=DownloadStats(
                total_images=3,
                scanned_images=3,
                matched_images=1,
                skipped_cloud=1,
                failed_images=1,
            ),
        ),
    )

    rows = read_manifest(result.manifest_path)
    assert [row["status"] for row in rows] == ["copied", "skipped_cloud", "failed"]
    assert rows[0]["filename_format_matched"] == "yes"
    assert rows[0]["filename_format_rule"] == "planet"
    assert rows[0]["capture_datetime"] == "2026-06-10 12:34:56"
    assert rows[0]["cloud_percent"] == "12.5"
    assert rows[0]["max_cloud_percent"] == "90"
    assert rows[1]["error"] == "cloud too high"
    assert rows[2]["source_path"] == str(failed)
    assert rows[2]["error"] == "bad raster"


def make_request(
    tmp_path: Path,
    source: Path,
    *,
    output_dir: Path | None = None,
    image_folders: tuple[DownloadImageFolder, ...] | None = None,
    geojson_files: tuple[Path, ...] | None = None,
    dry_run: bool = False,
    preserve_source_tree: bool = True,
    overwrite: bool = False,
    output_structure: DownloadOutputStructure = DownloadOutputStructure.GEOJSON_SOURCE,
) -> ResolvedSatelliteDownloadRequest:
    return ResolvedSatelliteDownloadRequest(
        geojson_files=geojson_files or (tmp_path / "all_processed.geojson",),
        image_folders=image_folders or (DownloadImageFolder(name=source.name, path=source),),
        output_dir=output_dir or (tmp_path / "out"),
        extensions=frozenset({".tif"}),
        filename_formats=(),
        overwrite=overwrite,
        dry_run=dry_run,
        include_boundary_touch=True,
        preserve_source_tree=preserve_source_tree,
        write_manifest=True,
        output_structure=output_structure,
    )


def make_match(
    raster: Path,
    source: Path,
    geojson_names: tuple[str, ...],
    geojson_paths: tuple[Path, ...],
    matched_geometries: tuple[DownloadMatchedGeometry, ...] = (),
) -> DownloadImageMatch:
    return DownloadImageMatch(
        source_folder=DownloadImageFolder(name=source.name, path=source),
        path=raster,
        raster=DownloadRasterMetadata(crs="EPSG:4326", bounds=(0.0, 0.0, 1.0, 1.0)),
        matched_geojson_names=geojson_names,
        matched_geojson_paths=geojson_paths,
        matched_geometries=matched_geometries,
    )


def metadata(
    *,
    matched_format: bool = False,
    matched_format_name: str | None = None,
    capture_datetime: datetime | None = None,
    cloud_percent: float | None = None,
    max_cloud_percent: float | None = None,
) -> DownloadFilenameMetadata:
    return DownloadFilenameMetadata(
        matched_format=matched_format,
        matched_format_name=matched_format_name,
        capture_datetime=capture_datetime,
        cloud_percent=cloud_percent,
        max_cloud_percent=max_cloud_percent,
    )


def read_manifest(path: Path | None) -> list[dict[str, str]]:
    assert path is not None
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))
