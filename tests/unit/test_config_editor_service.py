from __future__ import annotations

import json
from pathlib import Path

import pytest

from thucthengay.config import ConfigEditorError, ConfigEditorService


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def target_config(
    target_id: str,
    sort_order: int = 1,
    *,
    group_key: str = "1.1",
    group_title: str = "Không người Hoàng Sa",
) -> dict[str, object]:
    return {
        "id": target_id,
        "enabled": True,
        "group": {"key": group_key, "title": group_title},
        "sort_order": sort_order,
        "name": target_id,
        "alias": target_id,
        "coordinate": [106.7, 10.8],
        "scale": 50000,
        "grid": {"interval": {"minutes": 1}},
        "export": {
            "template_pptx_file": "templates/target.pptx",
            "template_txt_value": "Bao cao {target_name} luc {time_label}",
            "placeholders": [
                {"field": "map_image", "kind": "map_image", "value": ""},
                {"field": "title", "kind": "text", "value": "{target_name}"},
            ],
        },
        "metadata": {
            "geojson_geometry": {
                "type": "Point",
                "coordinates": [106.7, 10.8],
            }
        },
    }


def test_config_editor_loads_draft_and_reports_summary(tmp_path: Path) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "target.pptx").write_bytes(b"placeholder")
    write_json(tmp_path / "config.json", {"targets": [target_config("target_a")]})
    service = ConfigEditorService()

    state = service.load(tmp_path / "config.json")

    assert state.source_path == (tmp_path / "config.json").resolve()
    assert state.dirty is False
    assert state.summary.target_count == 1
    assert state.summary.enabled_count == 1
    assert state.summary.group_count == 1
    assert state.summary.geometry_count == 1


def test_config_editor_create_save_and_backup(tmp_path: Path) -> None:
    service = ConfigEditorService()
    state = service.create_new(tmp_path / "config.json")

    assert state.dirty is True
    assert state.summary.target_count == 0
    assert state.draft["defaults"]["grid"]["style"]["reference_width"] == 3306
    assert state.draft["defaults"]["grid"]["style"]["reference_outer_frame"] == [
        244,
        144,
        3272,
        2286,
    ]
    assert (
        state.draft["defaults"]["grid"]["style"]["default_label_font"]
        == "fonts/arial-bold/Arial Bold/Arial Bold.ttf"
    )
    assert state.draft["defaults"]["export"]["date_format"] == "dd.MM.yy"
    assert state.draft["defaults"]["export"]["time_format"] == "HH.mm/dd.MM.yy"
    assert state.draft["filename_patterns"] == [
        {
            "name": "PlanetScope PSScene",
            "pattern": "*_yyyyMMdd_HHmmss_*_*_cloud_cloud-percent",
        },
        {
            "name": "PlanetScope simple",
            "pattern": "yyyyMMdd_HHmmss_*",
        },
    ]

    service.add_target(group_key="2.2.4", group_title="Có người Trường Sa ĐL")
    service.update_target(
        "target_001",
        {
            "id": "da_lac",
            "name": "Đá Lạc",
            "alias": "ĐL",
            "export.template_pptx_file": "templates/da_lac.pptx",
            "metadata.geojson_geometry": {"type": "Point", "coordinates": [112.0, 9.0]},
        },
    )
    backup_path = service.backup(tmp_path / "manual.backup.json")
    saved = service.save()

    assert backup_path.is_file()
    assert (tmp_path / "config.json").is_file()
    assert saved.dirty is False
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert raw["targets"][0]["id"] == "da_lac"


def test_config_editor_new_config_defaults_are_isolated_between_drafts() -> None:
    first = ConfigEditorService()
    first.state.draft["defaults"]["grid"]["style"]["reference_outer_frame"][0] = 999
    first.state.draft["filename_patterns"].append({"name": "custom", "pattern": "yyyyMMdd_*"})

    second = ConfigEditorService()

    assert second.state.draft["defaults"]["grid"]["style"]["reference_outer_frame"] == [
        244,
        144,
        3272,
        2286,
    ]
    assert len(second.state.draft["filename_patterns"]) == 2


def test_config_editor_detects_duplicate_id_and_sort_order(tmp_path: Path) -> None:
    write_json(
        tmp_path / "config.json",
        {"targets": [target_config("target_a", 1), target_config("target_a", 1)]},
    )
    service = ConfigEditorService()

    state = service.load(tmp_path / "config.json")
    issue_ids = {issue.issue_id for issue in state.issues}

    assert "target.id_duplicate" in issue_ids
    assert "target.sort_order_duplicate" in issue_ids
    assert state.ok is False


def test_config_editor_reorders_old_and_new_groups_when_target_moves(
    tmp_path: Path,
) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "target.pptx").write_bytes(b"placeholder")
    write_json(
        tmp_path / "config.json",
        {
            "targets": [
                target_config("alpha", 1),
                target_config("beta", 2),
                target_config("gamma", 3),
                target_config(
                    "delta",
                    1,
                    group_key="2.1",
                    group_title="Có người Hoàng Sa",
                ),
                target_config(
                    "epsilon",
                    2,
                    group_key="2.1",
                    group_title="Có người Hoàng Sa",
                ),
            ]
        },
    )
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    service.update_target(
        "beta",
        {
            "group.key": "2.1",
            "group.title": "Có người Hoàng Sa",
            "sort_order": 2,
        },
    )

    old_group = service.targets_for_group("1.1")
    new_group = service.targets_for_group("2.1")
    assert [(target["id"], target["sort_order"]) for target in old_group] == [
        ("alpha", 1),
        ("gamma", 2),
    ]
    assert [(target["id"], target["sort_order"]) for target in new_group] == [
        ("delta", 1),
        ("beta", 2),
        ("epsilon", 3),
    ]
    assert "target.sort_order_duplicate" not in {
        issue.issue_id for issue in service.state.issues
    }


def test_config_editor_delete_target_reorders_remaining_group(tmp_path: Path) -> None:
    write_json(
        tmp_path / "config.json",
        {
            "targets": [
                target_config("alpha", 1),
                target_config("beta", 2),
                target_config("gamma", 3),
                target_config(
                    "delta",
                    1,
                    group_key="2.1",
                    group_title="Có người Hoàng Sa",
                ),
            ]
        },
    )
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    service.delete_target("beta")

    default_group = service.targets_for_group("1.1")
    other_group = service.targets_for_group("2.1")
    assert [(target["id"], target["sort_order"]) for target in default_group] == [
        ("alpha", 1),
        ("gamma", 2),
    ]
    assert [(target["id"], target["sort_order"]) for target in other_group] == [
        ("delta", 1),
    ]
    assert "target.sort_order_duplicate" not in {
        issue.issue_id for issue in service.state.issues
    }


def test_config_editor_imports_and_exports_geojson(tmp_path: Path) -> None:
    write_json(tmp_path / "config.json", {"targets": [target_config("target_a")]})
    geojson_path = tmp_path / "source.geojson"
    write_json(
        geojson_path,
        {
            "type": "Feature",
            "properties": {"name": "Target"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[1, 2], [3, 2], [3, 4], [1, 2]]],
            },
        },
    )
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    service.import_geojson("target_a", geojson_path)
    export_path = tmp_path / "export.geojson"
    service.export_geojson("target_a", export_path)

    raw = json.loads(export_path.read_text(encoding="utf-8"))
    assert raw["type"] == "Feature"
    assert raw["geometry"]["type"] == "Polygon"


def test_config_editor_import_template_copies_to_project_data_templates(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "config.json", {"targets": [target_config("target_a")]})
    source_template = tmp_path / "incoming" / "custom.pptx"
    source_template.parent.mkdir()
    source_template.write_bytes(b"pptx")
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    relative_path = service.import_template_pptx("target_a", source_template)

    assert relative_path == "data/templates/custom.pptx"
    assert (tmp_path / relative_path).read_bytes() == b"pptx"
    target = service.target("target_a")
    assert target is not None
    assert target["export"]["template_pptx_file"] == relative_path


def test_config_editor_import_default_label_font_copies_to_project_fonts(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "config.json", {"targets": [target_config("target_a")]})
    source_font = tmp_path / "incoming" / "custom-label.ttf"
    source_font.parent.mkdir()
    source_font.write_bytes(b"font")
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    relative_path = service.import_default_label_font(source_font)

    assert relative_path == "fonts/custom-label.ttf"
    assert (tmp_path / relative_path).read_bytes() == b"font"
    assert (
        service.state.draft["defaults"]["grid"]["style"]["default_label_font"]
        == relative_path
    )


def test_config_editor_import_default_label_font_keeps_existing_fonts_path(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "config.json", {"targets": [target_config("target_a")]})
    source_font = tmp_path / "fonts" / "arial-bold" / "Arial Bold.ttf"
    source_font.parent.mkdir(parents=True)
    source_font.write_bytes(b"font")
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    relative_path = service.import_default_label_font(source_font)

    assert relative_path == "fonts/arial-bold/Arial Bold.ttf"
    assert not (tmp_path / "fonts" / "Arial Bold.ttf").exists()


def test_config_editor_update_defaults_keeps_target_grid_overrides(tmp_path: Path) -> None:
    target = target_config("target_a")
    target["grid"] = {
        "interval": {"minutes": 1},
        "style": {"label_color": "#445566"},
    }
    write_json(tmp_path / "config.json", {"targets": [target]})
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    service.update_defaults(
        {
            "grid.label_format": "dms_short",
            "grid.style.supported_label_formats": ["dms_full", "dms_short"],
            "grid.style.reference_width": 3306,
            "grid.style.reference_height": 2340,
            "grid.style.reference_outer_frame": [244, 144, 3272, 2286],
            "grid.style.max_frame_ticks_per_axis": 2000,
            "grid.style.epsilon": 1e-10,
        }
    )

    defaults = service.state.draft["defaults"]
    assert defaults["grid"]["label_format"] == "dms_short"
    assert defaults["grid"]["style"]["reference_outer_frame"] == [244, 144, 3272, 2286]
    assert defaults["grid"]["style"]["supported_label_formats"] == ["dms_full", "dms_short"]
    assert service.target("target_a")["grid"] == {
        "interval": {"minutes": 1},
        "style": {"label_color": "#445566"},
    }


def test_config_editor_ensure_target_template_local_copies_existing_config_path(
    tmp_path: Path,
) -> None:
    source_template = tmp_path / "templates" / "target.pptx"
    source_template.parent.mkdir()
    source_template.write_bytes(b"pptx")
    write_json(tmp_path / "config.json", {"targets": [target_config("target_a")]})
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    relative_path = service.ensure_target_template_local("target_a")

    assert relative_path == "data/templates/target.pptx"
    assert (tmp_path / relative_path).read_bytes() == b"pptx"
    target = service.target("target_a")
    assert target is not None
    assert target["export"]["template_pptx_file"] == relative_path


def test_config_editor_ensure_target_template_local_reports_missing_file(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "config.json", {"targets": [target_config("target_a")]})
    service = ConfigEditorService()
    service.load(tmp_path / "config.json")

    with pytest.raises(ConfigEditorError, match="Không tìm thấy template PPTX"):
        service.ensure_target_template_local("target_a")


def test_config_editor_filename_test_applies_filename_utc_plus_seven_hours() -> None:
    service = ConfigEditorService()

    result = service.test_filename("20260526_203927_anything_12.tif")

    assert result.capture_date == "2026-05-27"
    assert result.capture_time == "03:39:27"
