from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from thucthengay.ingestion import (
    ImageryTargetMatch,
    RasterBounds,
    RasterMetadata,
    ScannedGeoTiff,
    TargetMatchingResult,
    populate_workspace_cache,
)
from thucthengay.models import ImageLayer, IssueSeverity, MetadataSource, MetadataStatus
from thucthengay.workspace import WorkspaceClearNotConfirmedError, WorkspaceService


def scanned_image(path: Path, *, layer_id: str = "layer-1") -> ScannedGeoTiff:
    return ScannedGeoTiff(
        path=path,
        raster=RasterMetadata(
            crs="EPSG:4326",
            bounds=RasterBounds(left=106.0, bottom=10.8, right=106.2, top=11.0),
            transform=(1, 0, 0, 0, -1, 0, 0, 0, 1),
            width=2,
            height=2,
            band_count=1,
            nodata=None,
            tags={},
        ),
        layer=ImageLayer(
            layer_id=layer_id,
            source_path=str(path),
            order=0,
            capture_date=date(2026, 5, 25),
            capture_time=time(10, 11, 12),
            cloud_percent=12.5,
            metadata_status=MetadataStatus.VALID,
            metadata_source=MetadataSource.FILENAME,
        ),
        source_identifier="source-1",
        metadata_field_sources={
            "capture_date": MetadataSource.FILENAME,
            "capture_time": MetadataSource.FILENAME,
            "cloud_percent": MetadataSource.FILENAME,
        },
    )


def matching_result(target_id: str, *images: ScannedGeoTiff) -> TargetMatchingResult:
    return TargetMatchingResult(
        matches={
            target_id: [
                ImageryTargetMatch(target_id=target_id, image=image)
                for image in images
            ]
        },
        issues=[],
    )


def test_populate_workspace_cache_copies_files_and_preserves_layer_metadata(
    tmp_path: Path,
) -> None:
    source = tmp_path / "imagery" / "20260525_101112_scene.tif"
    source.parent.mkdir()
    source.write_bytes(b"raster")
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")

    result = populate_workspace_cache(
        matching_result("target_001", scanned_image(source)),
        workspace,
    )

    assert result.issues == []
    assert result.cache_recreated is False
    cached_layer = result.layers_by_target_date[("target_001", "20260525")][0]
    cache_path = workspace.paths.root / cached_layer.cache_path
    assert cached_layer.source_path == str(source.resolve())
    assert cached_layer.cache_path.startswith("cache/target_001/20260525/")
    assert cache_path.read_bytes() == b"raster"
    assert cached_layer.capture_date == date(2026, 5, 25)
    assert cached_layer.capture_time == time(10, 11, 12)
    assert cached_layer.cloud_percent == 12.5
    assert cached_layer.metadata_source == MetadataSource.FILENAME


def test_populate_workspace_cache_deduplicates_same_source_for_same_target_date(
    tmp_path: Path,
) -> None:
    source = tmp_path / "imagery" / "same.tif"
    source.parent.mkdir()
    source.write_bytes(b"raster")
    image = scanned_image(source)
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")

    first = populate_workspace_cache(matching_result("target_001", image, image), workspace)
    second = populate_workspace_cache(matching_result("target_001", image, image), workspace)

    assert len(first.layers_by_target_date[("target_001", "20260525")]) == 1
    assert len(second.layers_by_target_date[("target_001", "20260525")]) == 1
    assert len(list((workspace.paths.cache / "target_001" / "20260525").iterdir())) == 1
    assert first.layers_by_target_date == second.layers_by_target_date


def test_populate_workspace_cache_can_overwrite_existing_cached_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "imagery" / "same.tif"
    source.parent.mkdir()
    source.write_bytes(b"first")
    image = scanned_image(source)
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")

    first = populate_workspace_cache(matching_result("target_001", image), workspace)
    cached_path = workspace.paths.root / first.layers_by_target_date[
        ("target_001", "20260525")
    ][0].cache_path
    source.write_bytes(b"second")

    populate_workspace_cache(
        matching_result("target_001", image),
        workspace,
        overwrite_existing=True,
    )

    assert cached_path.read_bytes() == b"second"


def test_populate_workspace_cache_sanitizes_source_filename_for_windows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "imagery" / "scene:bad?.tif"
    source.parent.mkdir()
    source.write_bytes(b"raster")
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")

    result = populate_workspace_cache(
        matching_result("target_001", scanned_image(source)),
        workspace,
    )

    cached_layer = result.layers_by_target_date[("target_001", "20260525")][0]
    assert Path(cached_layer.cache_path).name.startswith("scene_bad_")
    assert ":" not in cached_layer.cache_path
    assert "?" not in cached_layer.cache_path


def test_populate_workspace_cache_warns_and_excludes_missing_source(tmp_path: Path) -> None:
    missing_source = tmp_path / "imagery" / "missing.tif"
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")

    result = populate_workspace_cache(
        matching_result("target_001", scanned_image(missing_source)),
        workspace,
    )

    assert result.layers_by_target_date == {("target_001", "20260525"): []}
    assert len(result.issues) == 1
    assert result.issues[0].issue_id == "cache.copy_failed"
    assert result.issues[0].severity == IssueSeverity.WARNING
    assert str(missing_source.resolve()) in result.issues[0].message


def test_populate_workspace_cache_requires_confirmation_before_clear(
    tmp_path: Path,
) -> None:
    source = tmp_path / "imagery" / "scene.tif"
    source.parent.mkdir()
    source.write_bytes(b"raster")
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")
    stale_file = workspace.paths.cache / "old" / "stale.tif"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_bytes(b"old")

    with pytest.raises(WorkspaceClearNotConfirmedError):
        populate_workspace_cache(
            matching_result("target_001", scanned_image(source)),
            workspace,
            clear_existing=True,
        )

    result = populate_workspace_cache(
        matching_result("target_001", scanned_image(source)),
        workspace,
        clear_existing=True,
        clear_confirmed=True,
    )

    assert result.cache_recreated is True
    assert not stale_file.exists()
    assert result.layers_by_target_date[("target_001", "20260525")]
