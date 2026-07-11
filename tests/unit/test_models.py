from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from thucthengay.models import (
    Composition,
    ExportLog,
    FilenamePatternConfig,
    FinalRenderLog,
    FinalRenderLogEntry,
    FinalRenderResult,
    FinalRenderStatus,
    GridConfig,
    GridInterval,
    HistoricalImageSelectionConfig,
    HistoricalLoadingConfig,
    HistoricalLoadingTargetScope,
    HistoricalRegistryConfig,
    HistoricalSelectionMode,
    ImageLayer,
    ImageLayerSourceKind,
    Issue,
    IssueScope,
    IssueSeverity,
    MapFrame,
    PersistedValidationState,
    ProjectConfig,
    RenderResult,
    TargetConfig,
    TemplateMetadata,
    TemplatePlaceholder,
    TemplatePlaceholderSelector,
    TemporalCompareOrientation,
    TemporalCompareState,
    ValidationSummary,
    ViewState,
    WorkspaceManifest,
)


def valid_grid() -> GridConfig:
    return GridConfig(interval=GridInterval(minutes=1))


def valid_target_dict() -> dict[str, object]:
    return {
        "id": "target_001",
        "enabled": True,
        "sort_order": 1,
        "name": "Target 001",
        "alias": "T001",
        "title": "Target 001 Title",
        "geojson_file": "targets/target_001.geojson",
        "coordinate": [106.7, 10.8],
        "scale": 50000,
        "grid": {"interval": {"minutes": 1}},
        "export": {
            "template_pptx_file": "templates/target_001.pptx",
            "placeholders": [
                {"field": "map_image", "kind": "map_image", "element_id": 2}
            ],
        },
    }


def test_project_config_supports_target_specific_template_pptx() -> None:
    config = ProjectConfig.model_validate({"targets": [valid_target_dict()]})

    target = config.targets[0]

    assert config.historical_registry == HistoricalRegistryConfig()
    assert config.historical_loading == HistoricalLoadingConfig()
    assert target.export.template_pptx_file == "templates/target_001.pptx"
    assert target.export.placeholders[0].element_id == 2
    assert target.geojson_file == "targets/target_001.geojson"
    assert target.coordinate == [106.7, 10.8]
    assert target.scale == 50000
    assert target.grid.interval.minutes == 1


def test_project_config_supports_compare_template_pptx() -> None:
    config = ProjectConfig.model_validate(
        {
            "targets": [
                {
                    "id": "target_001",
                    "name": "Target 001",
                    "coordinate": [106.7, 10.8],
                    "scale": 50000,
                    "grid": {"interval": {"minutes": 1}},
                    "export": {
                        "template_pptx_file": "templates/target_001.pptx",
                        "compare_template_pptx_file": "templates/target_001.compare.pptx",
                        "placeholders": [
                            {"field": "map_image", "kind": "map_image", "element_id": 2}
                        ],
                        "compare_placeholders": [
                            {"field": "map_image", "kind": "map_image", "element_id": 2},
                            {
                                "field": "time_label_pane_A",
                                "kind": "text",
                                "element_id": 3,
                            },
                        ],
                    },
                }
            ]
        }
    )

    target = config.targets[0]
    assert target.export.compare_template_pptx_file == "templates/target_001.compare.pptx"
    assert target.export.compare_placeholders is not None
    assert target.export.compare_placeholders[1].field == "time_label_pane_A"


def test_project_config_accepts_inline_geojson_geometry_and_group() -> None:
    data = valid_target_dict()
    data.pop("geojson_file")
    data.pop("title")
    data["group"] = {"key": "2.2.1", "title": "Có người Trường Sa TQ"}
    data["metadata"] = {
        "geojson_geometry": {
            "type": "Polygon",
            "coordinates": [[
                [106.0, 10.0],
                [106.1, 10.0],
                [106.1, 10.1],
                [106.0, 10.1],
                [106.0, 10.0],
            ]],
        }
    }

    config = ProjectConfig.model_validate({"targets": [data]})

    target = config.targets[0]
    assert target.group is not None
    assert target.group.key == "2.2.1"
    assert target.group.title == "Có người Trường Sa TQ"
    assert target.geojson_file is None
    assert target.title is None
    assert target.metadata["geojson_geometry"]["type"] == "Polygon"


def test_project_config_applies_shared_target_defaults() -> None:
    data = valid_target_dict()
    data["grid"] = {
        "interval": {"minutes": 1},
        "style": {"label_color": "#445566"},
    }
    data["export"] = {
        "template_pptx_file": "templates/target_001.pptx",
        "placeholders": [{"field": "map_image", "kind": "map_image", "element_id": 2}],
        "time_format": "HH:mm",
    }

    config = ProjectConfig.model_validate(
        {
            "defaults": {
                "grid": {
                    "label_format": "dms_short",
                    "style": {
                        "frame_color": "#112233",
                        "label_color": "#000000",
                        "label_font_size": 18,
                        "tick_length_px": 10,
                    },
                },
                "export": {
                    "date_format": "dd.MM.yy",
                    "time_format": "HH.mm/dd.MM.yy",
                    "map_background_color": "#AABBCC",
                    "managed_source_root": "managed/sources",
                },
            },
            "targets": [data],
        }
    )

    target = config.targets[0]
    assert target.grid.label_format == "dms_short"
    assert target.grid.style == {
        "frame_color": "#112233",
        "label_color": "#445566",
        "label_font_size": 18,
        "tick_length_px": 10,
    }
    assert target.export.date_format == "dd.MM.yy"
    assert target.export.time_format == "HH:mm"
    assert target.export.map_background_color == "#AABBCC"
    assert target.export.managed_source_root == "managed/sources"


def test_historical_registry_config_requires_database_path_when_enabled() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProjectConfig.model_validate(
            {
                "historical_registry": {"enabled": True},
                "targets": [valid_target_dict()],
            }
        )

    assert ("historical_registry",) in {
        tuple(error["loc"]) for error in exc_info.value.errors()
    }


def test_historical_registry_config_accepts_enabled_database_path() -> None:
    config = ProjectConfig.model_validate(
        {
            "historical_registry": {
                "enabled": True,
                "database_path": "history/target-history.sqlite",
            },
            "targets": [valid_target_dict()],
        }
    )

    assert config.historical_registry.enabled is True
    assert config.historical_registry.database_path == "history/target-history.sqlite"


def test_historical_loading_config_accepts_explicit_scope_and_latest_images() -> None:
    config = ProjectConfig.model_validate(
        {
            "historical_registry": {
                "enabled": True,
                "database_path": "history/target-history.sqlite",
            },
            "historical_loading": {
                "enabled": True,
                "target_scope": "all_enabled_targets",
                "image_selection": {
                    "mode": "latest_images",
                    "limit_per_target": 3,
                },
            },
            "targets": [valid_target_dict()],
        }
    )

    assert config.historical_loading.enabled is True
    assert (
        config.historical_loading.target_scope
        == HistoricalLoadingTargetScope.ALL_ENABLED_TARGETS
    )
    assert config.historical_loading.image_selection.mode == HistoricalSelectionMode.LATEST_IMAGES
    assert config.historical_loading.image_selection.limit_per_target == 3


def test_historical_loading_latest_images_requires_positive_limit() -> None:
    with pytest.raises(ValidationError) as exc_info:
        HistoricalImageSelectionConfig.model_validate({"mode": "latest_images"})

    assert "limit_per_target is required" in exc_info.value.errors()[0]["msg"]


def test_historical_loading_date_range_requires_ordered_dates() -> None:
    with pytest.raises(ValidationError) as exc_info:
        HistoricalImageSelectionConfig.model_validate(
            {
                "mode": "date_range",
                "start_date": "2026-06-10",
                "end_date": "2026-06-09",
            }
        )

    assert "start_date must be before or equal to end_date" in exc_info.value.errors()[0]["msg"]


def test_historical_loading_lookback_days_requires_positive_window() -> None:
    with pytest.raises(ValidationError) as exc_info:
        HistoricalImageSelectionConfig.model_validate({"mode": "lookback_days"})

    assert "lookback_days is required" in exc_info.value.errors()[0]["msg"]


def test_project_config_validation_error_locations_are_specific() -> None:
    data = valid_target_dict()
    data["coordinate"] = [200, 10]

    with pytest.raises(ValidationError) as exc_info:
        ProjectConfig.model_validate({"targets": [data]})

    error_locations = {tuple(error["loc"]) for error in exc_info.value.errors()}

    assert ("targets", 0, "coordinate") in error_locations


def test_non_positive_scale_fails_on_target_field() -> None:
    data = valid_target_dict()
    data["scale"] = 0

    with pytest.raises(ValidationError) as exc_info:
        TargetConfig.model_validate(data)

    assert ("scale",) in {tuple(error["loc"]) for error in exc_info.value.errors()}


def test_target_id_rejects_windows_unsafe_filename_characters() -> None:
    data = valid_target_dict()
    data["id"] = "alpha:beta"

    with pytest.raises(ValidationError) as exc_info:
        TargetConfig.model_validate(data)

    assert ("id",) in {tuple(error["loc"]) for error in exc_info.value.errors()}


def test_filename_pattern_validator_uses_configured_separator() -> None:
    pattern = FilenamePatternConfig(
        name="dash separated",
        pattern="yyyyMMdd-HHmmss-*",
        separator="-",
    )

    assert pattern.separator == "-"


def test_zero_grid_interval_fails_on_interval_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        GridConfig.model_validate({"interval": {"degrees": 0, "minutes": 0, "seconds": 0}})

    assert ("interval",) in {tuple(error["loc"]) for error in exc_info.value.errors()}


def test_template_metadata_requires_template_path_and_map_frame() -> None:
    metadata = TemplateMetadata(
        template_pptx="templates/target_001.pptx",
        slide_index=0,
        map_frame=MapFrame(x=10, y=20, width=640, height=360),
        placeholders=[
            TemplatePlaceholder(field="map_image", element_id=2, kind="map_image"),
            TemplatePlaceholder(field="title", element_id=3, kind="text", required=False),
        ],
        metadata={
            "selected_slide": {
                "shapes": [
                    {
                        "id": "7",
                        "name": "TextBox 6",
                        "text": {"text": "NAME, TIME"},
                    }
                ]
            }
        },
    )

    dumped = metadata.model_dump(mode="json")

    assert dumped["template_pptx"] == "templates/target_001.pptx"
    assert dumped["placeholders"][0]["kind"] == "map_image"
    assert dumped["placeholders"][0]["element_id"] == 2
    assert dumped["metadata"]["selected_slide"]["shapes"][0]["text"]["text"] == "NAME, TIME"


def test_template_placeholder_supports_selector_only_mapping() -> None:
    placeholder = TemplatePlaceholder.model_validate(
        {
            "field": "map_image",
            "kind": "map_image",
            "selector": {"name": "ttn:map_image"},
        }
    )

    dumped = placeholder.model_dump(mode="json")

    assert placeholder.element_id is None
    assert placeholder.selector == TemplatePlaceholderSelector(name="ttn:map_image")
    assert dumped["selector"]["name"] == "ttn:map_image"


def test_template_placeholder_selector_requires_matching_signal() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TemplatePlaceholderSelector.model_validate({})

    assert () in {tuple(error["loc"]) for error in exc_info.value.errors()}


def test_template_metadata_missing_required_field_has_field_location() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TemplateMetadata.model_validate(
            {
                "slide_index": 0,
                "map_frame": {"x": 0, "y": 0, "width": 100, "height": 100},
            }
        )

    assert ("template_pptx",) in {tuple(error["loc"]) for error in exc_info.value.errors()}


def test_composition_defaults_and_round_trip_are_json_friendly() -> None:
    composition = Composition(
        composition_id="target_001__20260525",
        target_id="target_001",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
        layers=[
            ImageLayer(
                layer_id="layer_001",
                source_path="imagery/raw.tif",
                cache_path="cache/target_001/20260525/raw.tif",
                order=0,
                capture_date=date(2026, 5, 25),
                cloud_percent=12.5,
                metadata_status="valid",
                metadata_source="filename",
            )
        ],
    )

    dumped = composition.model_dump(mode="json")
    restored = Composition.model_validate(dumped)

    assert dumped["reviewed"] is False
    assert dumped["ready"] is False
    assert dumped["include"] is False
    assert dumped["needs_revalidation"] is True
    assert restored.layers[0].order == 0
    assert restored.layers[0].source_kind == ImageLayerSourceKind.CURRENT


def test_image_layer_source_kind_round_trips_for_historical_layers() -> None:
    layer = ImageLayer(
        layer_id="history_001",
        source_path="history/raw.tif",
        order=0,
        source_kind=ImageLayerSourceKind.HISTORICAL,
        image_asset_id=42,
    )

    dumped = layer.model_dump(mode="json")
    restored = ImageLayer.model_validate(dumped)

    assert dumped["source_kind"] == "historical"
    assert dumped["image_asset_id"] == 42
    assert restored.source_kind == ImageLayerSourceKind.HISTORICAL
    assert restored.image_asset_id == 42


def test_composition_temporal_compare_defaults_and_round_trip() -> None:
    composition = Composition(
        composition_id="target_001__20260525",
        target_id="target_001",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
        layers=[],
    )

    assert composition.temporal_compare == TemporalCompareState()
    assert composition.temporal_compare.enabled is False

    updated = composition.model_copy(
        update={
            "temporal_compare": TemporalCompareState(
                enabled=True,
                orientation=TemporalCompareOrientation.HORIZONTAL,
                pane_a_composition_id="target_001__20260525",
                pane_b_composition_id="target_001__20260526",
                pane_a_center=[106.7, 10.8],
                pane_b_center=[106.9, 10.9],
            )
        }
    )
    dumped = updated.model_dump(mode="json")
    restored = Composition.model_validate(dumped)

    assert dumped["temporal_compare"]["orientation"] == "horizontal"
    assert restored.temporal_compare.enabled is True
    assert restored.temporal_compare.pane_a_composition_id == "target_001__20260525"
    assert restored.temporal_compare.pane_b_center == [106.9, 10.9]


def test_issue_contract_serializes_vietnamese_message_and_blocking_flag() -> None:
    issue = Issue(
        issue_id="layer.file_missing",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.LAYER,
        target_id="target_001",
        composition_id="target_001__20260525",
        layer_id="layer_001",
        message="Không tìm thấy file ảnh.",
        remediation="Kiểm tra lại cache hoặc chạy ingest lại.",
        blocking=True,
    )

    dumped = issue.model_dump(mode="json")

    assert dumped["severity"] == "error"
    assert dumped["message"].startswith("Không")
    assert dumped["blocking"] is True


def test_error_issue_is_always_blocking() -> None:
    issue = Issue(
        issue_id="composition.invalid",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.COMPOSITION,
        message="Composition không hợp lệ.",
    )

    assert issue.blocking is True


def test_invalid_issue_severity_reports_severity_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Issue.model_validate(
            {
                "issue_id": "bad",
                "severity": "fatal",
                "scope": "layer",
                "message": "Lỗi.",
            }
        )

    assert ("severity",) in {tuple(error["loc"]) for error in exc_info.value.errors()}


def test_render_result_center_validates_lon_lat_range() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RenderResult(
            composition_id="target_001__20260525",
            output_path="renders/target_001__20260525.png",
            width=1920,
            height=1080,
            center=[999, 10.8],
            scale=50000,
        )

    assert ("center",) in {tuple(error["loc"]) for error in exc_info.value.errors()}


def test_workspace_render_and_export_models_round_trip() -> None:
    manifest = WorkspaceManifest(
        config_path="config.json",
        imagery_input_path="imagery",
        composition_ids=["target_001__20260525"],
    )
    render_result = RenderResult(
        composition_id="target_001__20260525",
        output_path="renders/target_001__20260525.png",
        width=1920,
        height=1080,
        center=[106.7, 10.8],
        scale=50000,
        layer_ids=["layer_001"],
    )
    export_log = ExportLog(
        pptx_path="exports/report.pptx",
        txt_path="exports/report.txt",
        slide_count=1,
        target_count=1,
    )

    restored_manifest = WorkspaceManifest.model_validate(manifest.model_dump(mode="json"))

    assert restored_manifest.config_path == "config.json"
    assert RenderResult.model_validate(render_result.model_dump(mode="json")).width == 1920
    assert ExportLog.model_validate(export_log.model_dump(mode="json")).slide_count == 1


def test_final_render_log_and_result_models_round_trip() -> None:
    entry = FinalRenderLogEntry(
        composition_id="target_001__20260525",
        target_id="target_001",
        status=FinalRenderStatus.SUCCESS,
        output_path="renders/target_001__20260525.abcd1234.png",
        width=1920,
        height=1080,
        render_spec_hash="abcd1234",
        visible_layer_refs=["L1", "L2"],
        timestamp=datetime(2026, 5, 26, 8, 30, tzinfo=UTC),
    )
    log = FinalRenderLog(entries=[entry])
    result = FinalRenderResult(
        composition_id="target_001__20260525",
        target_id="target_001",
        status=FinalRenderStatus.SUCCESS,
        output_path="renders/target_001__20260525.abcd1234.png",
        log_path="renders/target_001__20260525.render-log.json",
        width=1920,
        height=1080,
        render_spec_hash="abcd1234",
    )

    restored_log = FinalRenderLog.model_validate(log.model_dump(mode="json"))
    restored_result = FinalRenderResult.model_validate(result.model_dump(mode="json"))

    assert restored_log.entries[0].status == FinalRenderStatus.SUCCESS
    assert restored_log.entries[0].visible_layer_refs == ["L1", "L2"]
    assert restored_result.output_path == "renders/target_001__20260525.abcd1234.png"


def test_persisted_validation_state_distinguishes_stale_clean_warning_error() -> None:
    stale = Composition(
        composition_id="target_001__20260525",
        target_id="target_001",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
    )
    clean = stale.model_copy(update={"needs_revalidation": False})
    warning = stale.model_copy(
        update={
            "needs_revalidation": False,
            "validation_summary": ValidationSummary(warning_count=1),
        }
    )
    error = stale.model_copy(
        update={
            "needs_revalidation": False,
            "validation_summary": ValidationSummary(error_count=1, warning_count=1),
        }
    )

    assert stale.persisted_validation_state == PersistedValidationState.STALE
    assert clean.persisted_validation_state == PersistedValidationState.CLEAN
    assert warning.persisted_validation_state == PersistedValidationState.WARNING
    assert error.persisted_validation_state == PersistedValidationState.ERROR
