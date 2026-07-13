from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from thucthengay.config.service import ConfigLoadResult, ResolvedTargetPaths
from thucthengay.history import HistoricalLoadingPlan, HistoricalLoadingResult, HistoryService
from thucthengay.jobs import (
    ActiveJobProgressModel,
    JobControl,
    JobState,
    ProgressEvent,
    QueuedProgressDispatcher,
    run_ingestion_job,
)
from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    MetadataSource,
    MetadataStatus,
    ProjectConfig,
    TargetConfig,
    TargetExportConfig,
    ViewState,
)
from thucthengay.workspace import WorkspaceService


def target_config(target_id: str = "target_001") -> TargetConfig:
    return TargetConfig(
        id=target_id,
        enabled=True,
        sort_order=1,
        name="Target 001",
        geojson_file=f"{target_id}.geojson",
        coordinate=[106.0, 11.0],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(template_metadata_file=f"{target_id}.template.json"),
    )


def config_result_for(target: TargetConfig, geojson_path: Path) -> ConfigLoadResult:
    return ConfigLoadResult(
        config_path=geojson_path.parent / "config.json",
        config=ProjectConfig(targets=[target]),
        enabled_targets=[target],
        target_paths={
            target.id: ResolvedTargetPaths(
                target_id=target.id,
                geojson_file=geojson_path,
                template_metadata_file=geojson_path.parent / f"{target.id}.template.json",
            )
        },
    )


def write_geotiff(path: Path, *, origin_x: float = 106.0, origin_y: float = 11.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(origin_x, origin_y, 0.1, 0.1),
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))


def write_geojson(path: Path) -> None:
    data = {
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
    path.write_text(json.dumps(data), encoding="utf-8")


def _included_history_composition(source_path: Path) -> Composition:
    layer = ImageLayer(
        layer_id=source_path.stem,
        source_path=str(source_path),
        cache_path=f"cache/target_001/20260525/{source_path.name}",
        order=0,
        capture_date=date(2026, 5, 25),
        capture_time=time(10, 11, 12),
        cloud_percent=12,
        metadata_status=MetadataStatus.VALID,
        metadata_source=MetadataSource.FILENAME,
    )
    return Composition(
        composition_id="target_001__20260525",
        target_id="target_001",
        capture_date=date(2026, 5, 25),
        layers=[layer],
        view=ViewState(center=[106.0, 11.0], scale=50000),
        reviewed=True,
        ready=True,
        include=True,
        needs_revalidation=False,
        review_order=1,
    )


def test_progress_model_ignores_stale_job_updates_and_marks_active_completion() -> None:
    progress_model = ActiveJobProgressModel()
    progress_model.start("active")

    stale_event = ProgressEvent(
        job_id="old",
        stage="complete",
        state=JobState.SUCCESS,
        message="old done",
    )
    active_event = ProgressEvent(
        job_id="active",
        stage="complete",
        state=JobState.SUCCESS,
        message="active done",
    )

    assert progress_model.apply(stale_event) is False
    assert progress_model.complete is False
    assert progress_model.latest is None

    assert progress_model.apply(active_event) is True
    assert progress_model.complete is True
    assert progress_model.completed_job_id == "active"


def test_queued_dispatcher_hands_off_events_for_main_thread_drain() -> None:
    dispatcher = QueuedProgressDispatcher()
    first = ProgressEvent(job_id="job", stage="scan", message="scanning")
    second = ProgressEvent(job_id="job", stage="complete", message="done")

    dispatcher.publish(first)
    dispatcher.publish(second)

    assert dispatcher.drain() == [first, second]
    assert dispatcher.drain() == []


def test_ingestion_job_emits_progress_counters_and_success_state(tmp_path: Path) -> None:
    imagery = tmp_path / "imagery"
    geotiff = imagery / "20260525_101112_scene_cloud12.tif"
    boundary = tmp_path / "target_001.geojson"
    write_geotiff(geotiff)
    write_geojson(boundary)
    workspace = WorkspaceService(tmp_path / "workspace")
    events: list[ProgressEvent] = []

    result = run_ingestion_job(
        job_id="job-1",
        config_result=config_result_for(target_config(), boundary),
        imagery_folder=imagery,
        workspace_service=workspace,
        publish=events.append,
    )

    assert result.state == JobState.SUCCESS
    assert result.issues == []
    assert result.scanned_image_count == 1
    assert result.matched_image_count == 1
    assert result.targets_with_images_count == 1
    assert result.composition_ids == ["target_001__20260525"]
    assert workspace.load_manifest().composition_ids == ["target_001__20260525"]
    assert events[0].stage == "setup"
    assert events[-1].stage == "complete"
    scan_events = [event for event in events if event.stage == "scan"]
    assert scan_events[0].scanned_file_count == 0
    assert scan_events[0].total_image_count == 1
    assert scan_events[-1].scanned_file_count == 1
    assert scan_events[-1].total_image_count == 1
    assert scan_events[-1].scanned_image_count == 1
    match_events = [event for event in events if event.stage == "match"]
    match_event = match_events[0]
    assert match_event.processed_target_count == 1
    assert match_event.total_target_count == 1
    assert match_event.current_target_id == "target_001"
    assert match_event.current_target_matched_count == 1
    assert match_events[-1].matched_image_count == 1
    assert events[-1].state == JobState.SUCCESS
    assert events[-1].warning_count == 0


def test_ingestion_job_can_keep_images_outside_all_target_geometry(
    tmp_path: Path,
) -> None:
    imagery = tmp_path / "imagery"
    geotiff = imagery / "20260525_101112_scene_cloud12.tif"
    boundary = tmp_path / "target_001.geojson"
    write_geotiff(geotiff, origin_x=120.0, origin_y=20.0)
    write_geojson(boundary)
    workspace = WorkspaceService(tmp_path / "workspace")

    result = run_ingestion_job(
        job_id="job-unmatched",
        config_result=config_result_for(target_config(), boundary),
        imagery_folder=imagery,
        workspace_service=workspace,
        include_unmatched_images=True,
    )

    assert result.state == JobState.SUCCESS
    assert result.matched_image_count == 0
    assert len(result.composition_ids) == 1
    composition_id = result.composition_ids[0]
    assert composition_id.startswith("__unmatched__")
    composition = workspace.read_composition(composition_id)
    assert composition.target_id.startswith("__unmatched__")
    assert composition.layers[0].source_path == str(geotiff.resolve())
    assert composition.view.center == [120.1, 19.9]


def test_ingestion_job_preserves_nonfatal_warnings_for_summary(tmp_path: Path) -> None:
    imagery = tmp_path / "imagery"
    geotiff = imagery / "20260525_101112_scene.tif"
    boundary = tmp_path / "target_001.geojson"
    write_geotiff(geotiff)
    write_geojson(boundary)
    events: list[ProgressEvent] = []

    result = run_ingestion_job(
        job_id="job-warning",
        config_result=config_result_for(target_config(), boundary),
        imagery_folder=imagery,
        workspace_service=WorkspaceService(tmp_path / "workspace"),
        publish=events.append,
    )

    assert result.state == JobState.WARNING
    assert result.composition_ids == ["target_001__20260525"]
    assert [issue.issue_id for issue in result.issues] == ["imagery.metadata_missing"]
    assert events[-1].state == JobState.WARNING
    assert events[-1].warning_count == 1
    assert events[-1].issues == result.issues


def test_ingestion_job_does_not_call_historical_loader_when_loading_disabled(
    tmp_path: Path,
) -> None:
    imagery = tmp_path / "imagery"
    geotiff = imagery / "20260525_101112_scene_cloud12.tif"
    boundary = tmp_path / "target_001.geojson"
    write_geotiff(geotiff)
    write_geojson(boundary)
    calls: list[HistoricalLoadingPlan] = []

    def historical_loader(plan: HistoricalLoadingPlan) -> HistoricalLoadingResult:
        calls.append(plan)
        return HistoricalLoadingResult()

    result = run_ingestion_job(
        job_id="job-history-disabled",
        config_result=config_result_for(target_config(), boundary),
        imagery_folder=imagery,
        workspace_service=WorkspaceService(tmp_path / "workspace"),
        historical_loader=historical_loader,
    )

    assert result.state == JobState.SUCCESS
    assert calls == []


def test_ingestion_job_passes_enabled_historical_loading_plan_before_cache(
    tmp_path: Path,
) -> None:
    imagery = tmp_path / "imagery"
    geotiff = imagery / "20260525_101112_scene_cloud12.tif"
    boundary = tmp_path / "target_001.geojson"
    database_path = tmp_path / "history" / "target-history.sqlite"
    write_geotiff(geotiff)
    write_geojson(boundary)
    target = target_config()
    config_result = ConfigLoadResult(
        config_path=tmp_path / "config.json",
        config=ProjectConfig.model_validate(
            {
                "historical_registry": {
                    "enabled": True,
                    "database_path": "history/target-history.sqlite",
                },
                "historical_loading": {
                    "enabled": True,
                    "target_scope": "targets_with_current_matches",
                    "image_selection": {
                        "mode": "latest_images",
                        "limit_per_target": 2,
                    },
                },
                "targets": [target.model_dump(mode="json")],
            }
        ),
        enabled_targets=[target],
        target_paths={
            target.id: ResolvedTargetPaths(
                target_id=target.id,
                geojson_file=boundary,
                template_metadata_file=tmp_path / f"{target.id}.template.json",
            )
        },
        historical_database_path=database_path,
    )
    calls: list[HistoricalLoadingPlan] = []
    events: list[ProgressEvent] = []

    def historical_loader(plan: HistoricalLoadingPlan) -> HistoricalLoadingResult:
        calls.append(plan)
        return HistoricalLoadingResult()

    result = run_ingestion_job(
        job_id="job-history-enabled",
        config_result=config_result,
        imagery_folder=imagery,
        workspace_service=WorkspaceService(tmp_path / "workspace"),
        publish=events.append,
        historical_loader=historical_loader,
    )

    assert result.state == JobState.SUCCESS
    assert len(calls) == 1
    plan = calls[0]
    assert plan.enabled is True
    assert plan.database_path == database_path
    assert plan.target_ids == ("target_001",)
    assert plan.image_selection.mode == "latest_images"
    assert plan.image_selection.limit_per_target == 2
    assert plan.current_session_latest_capture_date == date(2026, 5, 25)
    event_stages = [event.stage for event in events]
    assert event_stages.index("history") < event_stages.index("cache")
    assert "Tải ảnh lịch sử" in events[event_stages.index("history")].message


def test_ingestion_job_loads_historical_imagery_into_workspace_cache(
    tmp_path: Path,
) -> None:
    imagery = tmp_path / "imagery"
    imagery.mkdir()
    boundary = tmp_path / "target_001.geojson"
    history_source = tmp_path / "history-source" / "20260525_101112_scene_cloud12.tif"
    database_path = tmp_path / "history" / "target-history.sqlite"
    write_geojson(boundary)
    write_geotiff(history_source)
    target = target_config()
    HistoryService(database_path).record_included_composition(
        _included_history_composition(history_source),
        target=target,
        workspace_path=tmp_path / "old-workspace",
    )
    config_result = ConfigLoadResult(
        config_path=tmp_path / "config.json",
        config=ProjectConfig.model_validate(
            {
                "historical_registry": {
                    "enabled": True,
                    "database_path": str(database_path),
                },
                "historical_loading": {
                    "enabled": True,
                    "target_scope": "all_enabled_targets",
                    "image_selection": {"mode": "latest_date"},
                },
                "targets": [target.model_dump(mode="json")],
            }
        ),
        enabled_targets=[target],
        target_paths={
            target.id: ResolvedTargetPaths(
                target_id=target.id,
                geojson_file=boundary,
                template_metadata_file=tmp_path / f"{target.id}.template.json",
            )
        },
        historical_database_path=database_path,
    )
    workspace = WorkspaceService(tmp_path / "workspace")

    result = run_ingestion_job(
        job_id="job-history-e2e",
        config_result=config_result,
        imagery_folder=imagery,
        workspace_service=workspace,
    )

    composition = workspace.read_composition("target_001__20260525")
    assert result.state == JobState.SUCCESS
    assert result.composition_ids == ["target_001__20260525"]
    assert len(composition.layers) == 1
    assert composition.layers[0].source_path == str(history_source)
    assert composition.layers[0].source_kind == "historical"
    assert composition.layers[0].image_asset_id is not None
    assert composition.layers[0].cache_path is not None
    assert (workspace.paths.root / composition.layers[0].cache_path).is_file()


def test_ingestion_job_skips_invalid_historical_paths_and_reports_issue(
    tmp_path: Path,
) -> None:
    imagery = tmp_path / "imagery"
    imagery.mkdir()
    boundary = tmp_path / "target_001.geojson"
    missing_history_source = tmp_path / "missing-history" / "missing.tif"
    database_path = tmp_path / "history" / "target-history.sqlite"
    write_geojson(boundary)
    target = target_config()
    HistoryService(database_path).record_included_composition(
        _included_history_composition(missing_history_source),
        target=target,
        workspace_path=tmp_path / "old-workspace",
    )
    config_result = ConfigLoadResult(
        config_path=tmp_path / "config.json",
        config=ProjectConfig.model_validate(
            {
                "historical_registry": {
                    "enabled": True,
                    "database_path": str(database_path),
                },
                "historical_loading": {
                    "enabled": True,
                    "target_scope": "all_enabled_targets",
                    "image_selection": {"mode": "latest_date"},
                },
                "targets": [target.model_dump(mode="json")],
            }
        ),
        enabled_targets=[target],
        target_paths={
            target.id: ResolvedTargetPaths(
                target_id=target.id,
                geojson_file=boundary,
                template_metadata_file=tmp_path / f"{target.id}.template.json",
            )
        },
        historical_database_path=database_path,
    )

    result = run_ingestion_job(
        job_id="job-history-missing",
        config_result=config_result,
        imagery_folder=imagery,
        workspace_service=WorkspaceService(tmp_path / "workspace"),
    )

    assert result.state == JobState.WARNING
    assert result.composition_ids == []
    assert [issue.issue_id for issue in result.issues] == ["historical.path_missing"]
    assert result.issues[0].target_id == "target_001"


def test_ingestion_job_deduplicates_current_and_historical_source(
    tmp_path: Path,
) -> None:
    imagery = tmp_path / "imagery"
    current_source = imagery / "20260525_101112_scene_cloud12.tif"
    boundary = tmp_path / "target_001.geojson"
    database_path = tmp_path / "history" / "target-history.sqlite"
    write_geotiff(current_source)
    write_geojson(boundary)
    target = target_config()
    HistoryService(database_path).record_included_composition(
        _included_history_composition(current_source),
        target=target,
        workspace_path=tmp_path / "old-workspace",
    )
    config_result = config_result_for(target, boundary)
    config_result.config = ProjectConfig.model_validate(
        {
            "historical_registry": {
                "enabled": True,
                "database_path": str(database_path),
            },
            "historical_loading": {
                "enabled": True,
                "target_scope": "targets_with_current_matches",
                "image_selection": {"mode": "latest_date"},
            },
            "targets": [target.model_dump(mode="json")],
        }
    )
    config_result.historical_database_path = database_path
    workspace = WorkspaceService(tmp_path / "workspace")

    result = run_ingestion_job(
        job_id="job-history-dedupe",
        config_result=config_result,
        imagery_folder=imagery,
        workspace_service=workspace,
    )

    composition = workspace.read_composition("target_001__20260525")
    assert result.state == JobState.SUCCESS
    assert len(composition.layers) == 1


def test_ingestion_job_reports_fatal_setup_error_without_workspace_completion(
    tmp_path: Path,
) -> None:
    fatal_issue = Issue(
        issue_id="config.invalid",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.CONFIG,
        message="Config không hợp lệ.",
    )
    config_result = ConfigLoadResult(
        config_path=tmp_path / "config.json",
        issues=[fatal_issue],
    )
    workspace = WorkspaceService(tmp_path / "workspace")
    events: list[ProgressEvent] = []

    result = run_ingestion_job(
        job_id="job-error",
        config_result=config_result,
        imagery_folder=tmp_path / "missing-imagery",
        workspace_service=workspace,
        publish=events.append,
    )

    assert result.state == JobState.ERROR
    assert result.composition_ids == []
    assert result.issues == [fatal_issue]
    assert events[-1].state == JobState.ERROR
    assert events[-1].scanned_image_count == 0
    assert workspace.paths.manifest.exists() is False


def test_ingestion_job_can_be_cancelled_before_scan(tmp_path: Path) -> None:
    imagery = tmp_path / "imagery"
    imagery.mkdir()
    boundary = tmp_path / "target_001.geojson"
    write_geojson(boundary)
    events: list[ProgressEvent] = []
    control = JobControl()
    control.request_cancel()

    result = run_ingestion_job(
        job_id="job-cancelled",
        config_result=config_result_for(target_config(), boundary),
        imagery_folder=imagery,
        workspace_service=WorkspaceService(tmp_path / "workspace"),
        control=control,
        publish=events.append,
    )

    assert result.state == JobState.CANCELLED
    assert result.composition_ids == []
    assert events[-1].state == JobState.CANCELLED
    assert events[-1].stage == "cancelled"
