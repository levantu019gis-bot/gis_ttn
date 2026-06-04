from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    MetadataStatus,
    PersistedValidationState,
    ValidationSummary,
    ViewState,
)
from thucthengay.workspace.atomic_write import atomic_write_json
from thucthengay.workspace.service import WorkspaceClearNotConfirmedError, WorkspaceService


def valid_composition(composition_id: str = "target_001__20260525") -> Composition:
    return Composition(
        composition_id=composition_id,
        target_id="target_001",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
    )


def layer(layer_id: str, *, order: int, visible: bool = True) -> ImageLayer:
    return ImageLayer(
        layer_id=layer_id,
        source_path=f"/imagery/{layer_id}.tif",
        visible=visible,
        order=order,
        metadata_status=MetadataStatus.VALID,
    )


def test_initialize_creates_manifest_and_known_subfolders(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")

    manifest = service.initialize(config_path="config.json", imagery_input_path="imagery")

    assert service.paths.manifest.is_file()
    assert service.paths.cache.is_dir()
    assert service.paths.compositions.is_dir()
    assert service.paths.renders.is_dir()
    assert service.paths.exports.is_dir()
    assert manifest.config_path == "config.json"
    assert manifest.imagery_input_path == "imagery"


def test_reopen_recreates_missing_known_folders_without_changing_compositions(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())
    service.paths.renders.rmdir()

    reopened = WorkspaceService(tmp_path / "workspace")
    manifest = reopened.load_manifest()

    assert reopened.paths.renders.is_dir()
    assert manifest.composition_ids == ["target_001__20260525"]
    assert reopened.read_composition("target_001__20260525").target_id == "target_001"


def test_write_composition_is_atomic_and_registers_manifest_id(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")

    composition_path = service.write_composition(valid_composition())

    manifest = service.load_manifest()
    assert composition_path == service.paths.composition_file("target_001__20260525")
    assert manifest.composition_ids == ["target_001__20260525"]
    assert service.read_composition("target_001__20260525").capture_date == date(2026, 5, 25)


def test_resolve_composition_layer_paths_keeps_json_relative_but_returns_absolute(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    composition = valid_composition().model_copy(
        update={
            "layers": [
                ImageLayer(
                    layer_id="L1",
                    source_path="imagery/L1.tif",
                    cache_path="cache/target/L1.tif",
                    order=0,
                    metadata_status=MetadataStatus.VALID,
                )
            ]
        }
    )

    resolved = service.resolve_composition_layer_paths(composition)

    assert composition.layers[0].cache_path == "cache/target/L1.tif"
    assert resolved.layers[0].source_path == str((service.paths.root / "imagery/L1.tif").resolve())
    assert resolved.layers[0].cache_path == str(
        (service.paths.root / "cache/target/L1.tif").resolve()
    )


def test_atomic_write_failure_keeps_existing_final_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final_path = tmp_path / "manifest.json"
    final_path.write_text('{"stable": true}\n', encoding="utf-8")

    def fail_replace(_source: str, _destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("thucthengay.workspace.atomic_write.os.replace", fail_replace)

    with pytest.raises(OSError):
        atomic_write_json(final_path, {"stable": False})

    assert final_path.read_text(encoding="utf-8") == '{"stable": true}\n'
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))


def test_clear_app_owned_data_requires_confirmation_and_resets_manifest(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())
    (service.paths.cache / "image.tif").write_text("cache", encoding="utf-8")
    (service.paths.renders / "preview.png").write_text("render", encoding="utf-8")

    assert service.has_app_owned_data()
    with pytest.raises(WorkspaceClearNotConfirmedError):
        service.clear_app_owned_data()

    assert service.read_composition("target_001__20260525").target_id == "target_001"

    service.clear_app_owned_data(confirmed=True)

    assert service.load_manifest().composition_ids == []
    assert service.paths.cache.is_dir()
    assert service.paths.compositions.is_dir()
    assert not any(service.paths.cache.iterdir())
    assert not any(service.paths.compositions.iterdir())


def test_composition_id_cannot_escape_workspace(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")

    with pytest.raises(ValueError):
        service.write_composition(valid_composition("../escape"))


def test_composition_id_rejects_windows_invalid_filename_characters(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")

    with pytest.raises(ValueError):
        service.write_composition(valid_composition("target:001__20260525"))


def test_update_review_state_persists_status_and_notes_after_reload(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())

    service.update_review_state(
        "target_001__20260525",
        reviewed=True,
        ready=True,
        include=True,
        review_order=7,
        notes="Đã kiểm tra.",
    )

    reloaded = WorkspaceService(tmp_path / "workspace").read_composition("target_001__20260525")
    assert reloaded.reviewed is True
    assert reloaded.ready is True
    assert reloaded.include is True
    assert reloaded.review_order == 7
    assert reloaded.notes == "Đã kiểm tra."


def test_update_review_state_validates_review_order(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())

    with pytest.raises(ValidationError):
        service.update_review_state("target_001__20260525", review_order=0)


def test_include_transition_requires_passing_validation_gate(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())

    with pytest.raises(Exception, match="passing validation"):
        service.apply_include_transition("target_001__20260525", validation_passed=False)

    unchanged = service.read_composition("target_001__20260525")
    assert unchanged.reviewed is False
    assert unchanged.ready is False
    assert unchanged.include is False
    assert unchanged.review_order is None


def test_include_transition_marks_ready_include_and_assigns_review_order(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition("target_001__20260525"))
    service.write_composition(valid_composition("target_002__20260526"))

    first = service.apply_include_transition("target_001__20260525", validation_passed=True)
    second = service.apply_include_transition("target_002__20260526", validation_passed=True)

    assert first.reviewed is True
    assert first.ready is True
    assert first.include is True
    assert first.review_order == 1
    assert second.review_order == 2


def test_skip_transition_marks_reviewed_not_included_and_clears_review_order(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())
    service.apply_include_transition("target_001__20260525", validation_passed=True)

    skipped = service.apply_skip_transition("target_001__20260525")

    assert skipped.reviewed is True
    assert skipped.ready is False
    assert skipped.include is False
    assert skipped.review_order is None


def test_previous_and_next_navigation_do_not_mutate_current_composition(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition("target_001__20260525"))
    service.write_composition(valid_composition("target_002__20260526"))

    before = service.read_composition("target_002__20260526").model_dump()

    assert service.previous_composition_id("target_002__20260526") == "target_001__20260525"
    assert service.next_composition_id("target_001__20260525") == "target_002__20260526"
    assert service.previous_composition_id("target_001__20260525") is None
    assert service.read_composition("target_002__20260526").model_dump() == before


def test_save_validation_summary_persists_only_compact_summary(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())

    summary = ValidationSummary(
        last_validated_at=datetime(2026, 5, 25, 8, 30, tzinfo=UTC),
        info_count=2,
        warning_count=1,
        error_count=0,
    )
    service.save_validation_summary("target_001__20260525", summary)

    raw = json.loads(
        service.paths.composition_file("target_001__20260525").read_text(encoding="utf-8")
    )
    assert raw["validation_summary"]["warning_count"] == 1
    assert raw["needs_revalidation"] is False
    assert "issues" not in raw
    assert "detailed_issues" not in raw


def test_mark_needs_revalidation_makes_prior_summary_stale_and_unincludes(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())
    service.save_validation_summary(
        "target_001__20260525",
        ValidationSummary(warning_count=1),
    )
    service.apply_include_transition("target_001__20260525", validation_passed=True)

    stale = service.mark_needs_revalidation("target_001__20260525")

    assert stale.needs_revalidation is True
    assert stale.ready is False
    assert stale.include is False
    assert stale.review_order is None
    assert stale.validation_summary.warning_count == 1
    assert stale.persisted_validation_state == PersistedValidationState.STALE


def test_set_layer_visibility_persists_and_marks_composition_stale(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        valid_composition().model_copy(
            update={
                "layers": [layer("old", order=0), layer("new", order=1)],
                "reviewed": True,
                "ready": True,
                "include": True,
                "needs_revalidation": False,
                "review_order": 3,
            }
        )
    )

    updated = service.set_layer_visibility("target_001__20260525", "old", visible=False)

    assert updated.layers[0].visible is False
    assert updated.layers[1].visible is True
    assert updated.needs_revalidation is True
    assert updated.ready is False
    assert updated.include is False
    assert updated.review_order is None

    reloaded = WorkspaceService(tmp_path / "workspace").read_composition("target_001__20260525")
    assert reloaded.layers[0].visible is False


def test_set_layer_visibility_unknown_layer_does_not_write(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        valid_composition().model_copy(update={"layers": [layer("old", order=0)]})
    )

    with pytest.raises(Exception, match="Layer not found"):
        service.set_layer_visibility("target_001__20260525", "missing", visible=False)

    assert service.read_composition("target_001__20260525").layers[0].visible is True


def test_reorder_layers_persists_normalized_order_and_marks_stale(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        valid_composition().model_copy(
            update={
                "layers": [layer("old", order=0), layer("new", order=1), layer("third", order=2)],
                "ready": True,
                "include": True,
                "needs_revalidation": False,
                "review_order": 4,
            }
        )
    )

    updated = service.reorder_layers(
        "target_001__20260525",
        ["third", "old", "new"],
    )

    assert [layer.layer_id for layer in updated.layers] == ["third", "old", "new"]
    assert [layer.order for layer in updated.layers] == [0, 1, 2]
    assert updated.needs_revalidation is True
    assert updated.ready is False
    assert updated.include is False
    assert updated.review_order is None


def test_reorder_layers_requires_all_layers_exactly_once(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        valid_composition().model_copy(
            update={"layers": [layer("old", order=0), layer("new", order=1)]}
        )
    )

    with pytest.raises(Exception, match="exactly once"):
        service.reorder_layers("target_001__20260525", ["new"])

    layer_ids = [
        layer.layer_id
        for layer in service.read_composition("target_001__20260525").layers
    ]
    assert layer_ids == [
        "old",
        "new",
    ]


def test_update_view_state_persists_and_marks_composition_stale(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        valid_composition().model_copy(
            update={
                "layers": [layer("old", order=0)],
                "ready": True,
                "include": True,
                "needs_revalidation": False,
                "review_order": 5,
                "validation_summary": ValidationSummary(warning_count=1),
            }
        )
    )

    updated = service.update_view_state(
        "target_001__20260525",
        center=[106.75, 10.85],
        scale=25000,
    )

    assert updated.view.center == [106.75, 10.85]
    assert updated.view.scale == 25000
    assert updated.view.rotation == 0
    assert updated.needs_revalidation is True
    assert updated.ready is False
    assert updated.include is False
    assert updated.review_order is None
    assert updated.validation_summary.warning_count == 1
    assert updated.layers[0].layer_id == "old"

    reloaded = service.read_composition("target_001__20260525")
    assert reloaded.view.center == [106.75, 10.85]
    assert reloaded.view.scale == 25000


def test_update_view_state_invalid_values_do_not_write(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())

    with pytest.raises(ValidationError):
        service.update_view_state(
            "target_001__20260525",
            center=[999, 10.85],
            scale=25000,
        )

    reloaded = service.read_composition("target_001__20260525")
    assert reloaded.view.center == [106.7, 10.8]
    assert reloaded.view.scale == 50000


def test_update_grid_override_persists_only_composition_and_marks_stale(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        valid_composition().model_copy(
            update={
                "layers": [layer("old", order=0)],
                "ready": True,
                "include": True,
                "needs_revalidation": False,
                "review_order": 5,
                "validation_summary": ValidationSummary(warning_count=1),
            }
        )
    )
    target_default = GridConfig(interval=GridInterval(minutes=1))

    updated = service.update_grid_override(
        "target_001__20260525",
        degrees=0,
        minutes=2,
        seconds=30,
        label_format="dms_short",
        style={"color": "white"},
    )

    assert updated.grid_override is not None
    assert updated.grid_override.interval.minutes == 2
    assert updated.grid_override.interval.seconds == 30
    assert updated.grid_override.label_format == "dms_short"
    assert updated.grid_override.style == {"color": "white"}
    assert updated.needs_revalidation is True
    assert updated.ready is False
    assert updated.include is False
    assert updated.review_order is None
    assert updated.validation_summary.warning_count == 1
    assert updated.layers[0].layer_id == "old"
    assert target_default.interval.minutes == 1

    raw = json.loads(
        service.paths.composition_file("target_001__20260525").read_text(encoding="utf-8")
    )
    assert raw["grid_override"]["interval"]["minutes"] == 2
    assert raw["grid_override"]["label_format"] == "dms_short"


def test_update_grid_override_invalid_values_do_not_write(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        valid_composition().model_copy(
            update={
                "grid_override": GridConfig(
                    interval=GridInterval(minutes=1),
                    label_format="dms_full",
                ),
                "ready": True,
                "include": True,
                "needs_revalidation": False,
                "review_order": 2,
            }
        )
    )

    with pytest.raises(ValidationError):
        service.update_grid_override(
            "target_001__20260525",
            degrees=0,
            minutes=0,
            seconds=0,
            label_format="dms_full",
        )

    reloaded = service.read_composition("target_001__20260525")
    assert reloaded.grid_override is not None
    assert reloaded.grid_override.interval.minutes == 1
    assert reloaded.ready is True
    assert reloaded.include is True
    assert reloaded.needs_revalidation is False
    assert reloaded.review_order == 2


def test_reloaded_validation_summary_provides_aggregate_counts_and_state(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())
    service.save_validation_summary(
        "target_001__20260525",
        ValidationSummary(info_count=1, warning_count=2, error_count=0),
    )

    reloaded = WorkspaceService(tmp_path / "workspace").read_composition("target_001__20260525")

    assert reloaded.validation_summary.info_count == 1
    assert reloaded.validation_summary.warning_count == 2
    assert reloaded.validation_summary.error_count == 0
    assert reloaded.persisted_validation_state == PersistedValidationState.WARNING


def test_included_export_candidates_refuse_stale_or_errored_persisted_state(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition("clean"))
    service.write_composition(valid_composition("stale"))
    service.write_composition(valid_composition("errored"))

    service.save_validation_summary("clean", ValidationSummary())
    service.apply_include_transition("clean", validation_passed=True)

    service.save_validation_summary("stale", ValidationSummary())
    service.apply_include_transition("stale", validation_passed=True)
    service.mark_needs_revalidation("stale")

    service.save_validation_summary("errored", ValidationSummary(error_count=1))
    service.update_review_state("errored", reviewed=True, ready=True, include=True, review_order=3)

    assert [composition.composition_id for composition in service.included_export_candidates()] == [
        "clean"
    ]


def test_record_final_render_artifacts_and_edit_invalidation(tmp_path: Path) -> None:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(valid_composition())

    rendered = service.record_final_render_artifacts(
        "target_001__20260525",
        final_render_path="renders/target_001__20260525.abcd1234.png",
        render_log_path="renders/target_001__20260525.render-log.json",
    )

    assert rendered.artifacts.final_render_path == "renders/target_001__20260525.abcd1234.png"
    assert rendered.artifacts.render_log_path == "renders/target_001__20260525.render-log.json"

    stale = service.update_view_state(
        "target_001__20260525",
        center=[106.8, 10.9],
        scale=25000,
    )

    assert stale.needs_revalidation is True
    assert stale.artifacts.final_render_path is None
    assert stale.artifacts.render_log_path is None
