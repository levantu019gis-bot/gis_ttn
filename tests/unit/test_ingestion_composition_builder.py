from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

from thucthengay.ingestion import CachePopulationResult, create_target_date_compositions
from thucthengay.models import (
    Composition,
    CompositionArtifacts,
    GridConfig,
    GridInterval,
    ImageLayer,
    MetadataSource,
    MetadataStatus,
    TargetConfig,
    TargetExportConfig,
    ValidationSummary,
    ViewState,
)
from thucthengay.workspace import WorkspaceService


def target(target_id: str = "target_001") -> TargetConfig:
    return TargetConfig(
        id=target_id,
        enabled=True,
        sort_order=1,
        name=target_id,
        geojson_file=f"{target_id}.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(template_metadata_file=f"{target_id}.template.json"),
    )


def cached_layer(
    layer_id: str,
    *,
    capture_date: date,
    capture_time: time | None,
) -> ImageLayer:
    return ImageLayer(
        layer_id=layer_id,
        source_path=f"/source/{layer_id}.tif",
        cache_path=f"cache/target_001/{capture_date:%Y%m%d}/{layer_id}.tif",
        order=99,
        capture_date=capture_date,
        capture_time=capture_time,
        cloud_percent=10,
        metadata_status=MetadataStatus.VALID,
        metadata_source=MetadataSource.FILENAME,
    )


def test_create_target_date_compositions_splits_multi_date_layers(tmp_path: Path) -> None:
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")
    result = CachePopulationResult(
        layers_by_target_date={
            ("target_001", "20260525"): [
                cached_layer("morning", capture_date=date(2026, 5, 25), capture_time=time(8, 0))
            ],
            ("target_001", "20260526"): [
                cached_layer("next", capture_date=date(2026, 5, 26), capture_time=time(9, 0))
            ],
        },
        issues=[],
    )

    created = create_target_date_compositions(result, {"target_001": target()}, workspace)

    assert created.issues == []
    assert created.composition_ids == ["target_001__20260525", "target_001__20260526"]
    assert workspace.load_manifest().composition_ids == [
        "target_001__20260525",
        "target_001__20260526",
    ]
    assert workspace.read_composition("target_001__20260525").capture_date == date(2026, 5, 25)
    assert workspace.read_composition("target_001__20260526").capture_date == date(2026, 5, 26)


def test_new_composition_defaults_view_and_workspace_relative_paths(tmp_path: Path) -> None:
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")
    result = CachePopulationResult(
        layers_by_target_date={
            ("target_001", "20260525"): [
                cached_layer("layer", capture_date=date(2026, 5, 25), capture_time=time(10, 0))
            ]
        },
        issues=[],
    )

    create_target_date_compositions(result, {"target_001": target()}, workspace)
    composition = workspace.read_composition("target_001__20260525")
    raw = json.loads(
        workspace.paths.composition_file("target_001__20260525").read_text(encoding="utf-8")
    )

    assert composition.reviewed is False
    assert composition.ready is False
    assert composition.include is False
    assert composition.needs_revalidation is True
    assert composition.review_order is None
    assert composition.view.center == [106.7, 10.8]
    assert composition.view.scale == 50000
    assert composition.grid_override is None
    assert raw["layers"][0]["cache_path"].startswith("cache/target_001/20260525/")


def test_layer_stack_sorts_newest_valid_time_first_and_keeps_missing_time(
    tmp_path: Path,
) -> None:
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")
    day = date(2026, 5, 25)
    result = CachePopulationResult(
        layers_by_target_date={
            ("target_001", "20260525"): [
                cached_layer("old", capture_date=day, capture_time=time(8, 0)),
                cached_layer("missing", capture_date=day, capture_time=None),
                cached_layer("new", capture_date=day, capture_time=time(14, 0)),
            ]
        },
        issues=[],
    )

    create_target_date_compositions(result, {"target_001": target()}, workspace)
    composition = workspace.read_composition("target_001__20260525")

    assert [layer.layer_id for layer in composition.layers] == ["new", "old", "missing"]
    assert [layer.order for layer in composition.layers] == [0, 1, 2]
    assert composition.layers[2].metadata_status == MetadataStatus.NEEDS_MANUAL_CORRECTION


def test_create_target_date_compositions_merges_existing_workspace_composition(
    tmp_path: Path,
) -> None:
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")
    day = date(2026, 5, 25)
    existing = Composition(
        composition_id="target_001__20260525",
        target_id="target_001",
        capture_date=day,
        layers=[
            cached_layer("old", capture_date=day, capture_time=time(8, 0)).model_copy(
                update={"visible": False, "order": 0, "cloud_percent": 77}
            )
        ],
        view=ViewState(center=[106.71, 10.81], scale=25000),
        grid_override=GridConfig(interval=GridInterval(seconds=30)),
        reviewed=True,
        ready=True,
        include=True,
        needs_revalidation=False,
        review_order=3,
        notes="keep me",
        validation_summary=ValidationSummary(last_validated_at=None, error_count=0),
        artifacts=CompositionArtifacts(
            final_render_path="renders/target_001__20260525.png",
            render_log_path="renders/target_001__20260525.render-log.json",
        ),
    )
    workspace.write_composition(existing)
    result = CachePopulationResult(
        layers_by_target_date={
            ("target_001", "20260525"): [
                cached_layer("old", capture_date=day, capture_time=time(8, 0)).model_copy(
                    update={"cloud_percent": 11}
                ),
                cached_layer("new", capture_date=day, capture_time=time(12, 0)),
            ]
        },
        issues=[],
    )

    created = create_target_date_compositions(
        result,
        {"target_001": target()},
        workspace,
        merge_existing=True,
    )

    assert created.composition_ids == ["target_001__20260525"]
    merged = workspace.read_composition("target_001__20260525")
    assert [layer.layer_id for layer in merged.layers] == ["old", "new"]
    assert [layer.order for layer in merged.layers] == [0, 1]
    assert merged.layers[0].visible is False
    assert merged.layers[0].cloud_percent == 11
    assert merged.view.center == [106.71, 10.81]
    assert merged.view.scale == 25000
    assert merged.grid_override == existing.grid_override
    assert merged.reviewed is True
    assert merged.ready is False
    assert merged.include is False
    assert merged.needs_revalidation is True
    assert merged.review_order is None
    assert merged.notes == "keep me"
    assert merged.artifacts.final_render_path is None
    assert merged.artifacts.render_log_path is None


def test_unknown_target_or_date_group_creates_issue_without_writing_composition(
    tmp_path: Path,
) -> None:
    workspace = WorkspaceService(tmp_path / "workspace")
    workspace.initialize(config_path="config.json")
    result = CachePopulationResult(
        layers_by_target_date={
            ("missing_target", "20260525"): [
                cached_layer("layer", capture_date=date(2026, 5, 25), capture_time=time(10, 0))
            ],
            ("target_001", "unknown_date"): [
                ImageLayer(layer_id="no-date", source_path="/source/no-date.tif", order=0)
            ],
        },
        issues=[],
    )

    created = create_target_date_compositions(result, {"target_001": target()}, workspace)

    assert created.composition_ids == []
    assert {issue.issue_id for issue in created.issues} == {
        "composition.target_missing",
        "composition.capture_date_missing",
    }
    assert workspace.load_manifest().composition_ids == []
