from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def target_config() -> dict[str, object]:
    return {
        "id": "target_a",
        "enabled": True,
        "group": {"key": "1.1", "title": "Không người Hoàng Sa"},
        "sort_order": 1,
        "name": "Target A",
        "alias": "A",
        "title": "Target A Title",
        "geojson_file": "geojson/target_a.geojson",
        "coordinate": [106.7, 10.8],
        "scale": 50000,
        "grid": {"interval": {"minutes": 1}},
        "export": {
            "template_pptx_file": "templates/target_a.pptx",
            "template_txt_value": "Bao cao {target_name} luc {time_label}",
            "date_format": "dd.MM.yy",
            "time_format": "HH.mm/dd.MM.yy",
            "map_background_color": "#3a3756",
            "placeholders": [
                {
                    "field": "map_image",
                    "kind": "map_image",
                    "element_id": 12,
                    "value": "",
                },
                {
                    "field": "title",
                    "kind": "text",
                    "element_id": 13,
                    "selector": {"name": "Title Shape"},
                    "diagnostic_name": "Title placeholder",
                    "required": False,
                    "value": "{target_name}",
                },
            ],
        },
        "metadata": {"geojson_geometry": {"type": "Point", "coordinates": [106.7, 10.8]}},
    }


def config_defaults() -> dict[str, object]:
    return {
        "grid": {
            "label_format": "dms_short",
            "style": {
                "supported_label_formats": ["dms_full", "dms_short"],
                "reference_width": 3306,
                "reference_height": 2340,
                "reference_outer_frame": [244, 144, 3272, 2286],
                "reference_frame_gap": 42,
                "max_frame_ticks_per_axis": 2000,
                "epsilon": 1e-10,
                "default_label_font": "fonts/arial-bold/Arial Bold.ttf",
                "frame_color": "#000000",
                "label_color": "#000000",
                "label_font_size": 24,
                "tick_length_px": 8,
                "temporal_compare_pane_gap_px": 8,
                "temporal_compare_gap_color": "#FFFFFF",
                "reference_label_font_size": 72,
                "surround_tick_length": 14,
                "surround_outer_stroke_width": 6,
                "surround_inner_stroke_width": 4,
                "surround_tick_stroke_width": 4,
                "max_frame_ticks": "",
            },
        },
        "export": {
            "date_format": "dd.MM.yy",
            "time_format": "HH.mm/dd.MM.yy",
            "map_background_color": "#000000",
        },
    }


def test_config_mode_widget_smoke_runs_in_isolated_qt_process(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "templates" / "target_a.pptx"
    template_path.parent.mkdir()
    template_path.write_bytes(b"pptx")
    source_font = tmp_path / "incoming" / "custom-label.ttf"
    source_font.parent.mkdir()
    source_font.write_bytes(b"font")
    geojson_path = tmp_path / "incoming" / "target.geojson"
    write_json(
        geojson_path,
        {
            "type": "Feature",
            "properties": {"name": "Imported"},
            "geometry": {"type": "Point", "coordinates": [112.0, 9.0]},
        },
    )
    copied_template_path = tmp_path / "data" / "templates" / "target_a.pptx"
    copied_font_path = tmp_path / "fonts" / "custom-label.ttf"
    write_json(
        config_path,
        {
            "defaults": config_defaults(),
            "historical_registry": {
                "enabled": True,
                "database_path": "history/target-history.sqlite",
            },
            "historical_loading": {
                "enabled": True,
                "target_scope": "targets_with_current_matches",
                "image_selection": {"mode": "latest_date"},
            },
            "targets": [target_config()],
        },
    )
    code = f"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QTableWidgetItem
from thucthengay.editor.modes.config_mode import ConfigMode, _PLACEHOLDER_COLUMNS
app = QApplication.instance() or QApplication([])
mode = ConfigMode()
mode.load_config(r"{config_path}")
assert mode.stat_labels["targets"].text() == "1"
assert mode.group_list.count() == 2
assert mode.target_model.rowCount() == 1
assert "id" not in mode.target_fields
assert "coordinate.0" not in mode.target_fields
assert "coordinate.1" not in mode.target_fields
assert "title" not in mode.target_fields
assert "geojson_file" not in mode.target_fields
assert "grid.label_format" not in mode.target_fields
assert "export.date_format" not in mode.target_fields
assert "export.time_format" not in mode.target_fields
assert "export.map_background_color" not in mode.target_fields
assert mode.template_browse_button.text() == "Browse"
assert mode.target_fields["export.template_pptx_file"].isReadOnly()
assert mode.target_fields["export.template_pptx_file"].text() == "templates/target_a.pptx"
assert not Path(r"{copied_template_path}").exists()
QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: (r"{template_path}", ""))
mode.template_browse_button.click()
assert mode.target_fields["export.template_pptx_file"].text() == "data/templates/target_a.pptx"
assert Path(r"{copied_template_path}").is_file()
enabled_index = mode.target_model.index(0, 0)
mode.target_model.setData(
    enabled_index,
    Qt.CheckState.Unchecked,
    int(Qt.ItemDataRole.CheckStateRole),
)
assert mode._service.target("target_a")["enabled"] is False
mode.target_model.setData(
    enabled_index,
    Qt.CheckState.Checked,
    int(Qt.ItemDataRole.CheckStateRole),
)
assert mode._service.target("target_a")["enabled"] is True
assert mode.geometry_text.isReadOnly()
assert '"target_id": "target_a"' in mode.geometry_text.toPlainText()
assert '"coordinates": [' in mode.geometry_text.toPlainText()
assert mode.defaults_combo_fields["grid.label_format"].currentText() == "dms_short"
assert mode.defaults_fields["grid.style.supported_label_formats"].text() == "dms_full, dms_short"
assert mode.defaults_fields["grid.style.reference_width"].text() == "3306"
assert mode.defaults_fields["grid.style.reference_height"].text() == "2340"
assert mode.defaults_fields["grid.style.reference_outer_frame"].text() == "244, 144, 3272, 2286"
assert mode.defaults_fields["grid.style.max_frame_ticks_per_axis"].text() == "2000"
assert mode.defaults_fields["grid.style.temporal_compare_pane_gap_px"].text() == "8"
assert mode.defaults_fields["grid.style.temporal_compare_gap_color"].text() == "#FFFFFF"
assert mode.defaults_fields["grid.style.max_frame_ticks"].text() == ""
assert mode.defaults_fields["grid.style.surround_outer_stroke_width"].text() == "6"
assert mode.defaults_fields["grid.style.default_label_font"].isReadOnly()
assert mode.defaults_combo_fields["export.date_format"].currentText() == "dd.MM.yy"
assert mode.defaults_combo_fields["export.time_format"].currentText() == "HH.mm/dd.MM.yy"
assert mode.defaults_fields["export.map_background_color"].isReadOnly()
mode.defaults_combo_fields["grid.label_format"].setCurrentText("dms_full")
mode.defaults_fields["grid.style.reference_outer_frame"].setText("10, 20, 90, 80")
mode.defaults_fields["grid.style.epsilon"].setText("0.0001")
mode._apply_defaults()
assert mode._service.state.draft["defaults"]["grid"]["label_format"] == "dms_full"
assert (
    mode._service.state.draft["defaults"]["grid"]["style"]["reference_outer_frame"]
    == [10, 20, 90, 80]
)
assert mode._service.state.draft["defaults"]["grid"]["style"]["epsilon"] == 0.0001
target_after_defaults = mode._service.target("target_a")
assert target_after_defaults["grid"] == {{"interval": {{"minutes": 1}}}}
assert mode.historical_registry_enabled_check.isChecked()
assert mode.historical_loading_enabled_check.isChecked()
assert mode.historical_fields["historical_registry.database_path"].text() == (
    "history/target-history.sqlite"
)
assert mode.historical_selection_mode_combo.currentData() == "latest_date"
mode.historical_selection_mode_combo.setCurrentIndex(
    mode.historical_selection_mode_combo.findData("latest_images")
)
mode.historical_fields["historical_loading.image_selection.limit_per_target"].setText("3")
mode._apply_historical()
assert mode._service.state.draft["historical_loading"]["image_selection"] == {{
    "mode": "latest_images",
    "lookback_anchor": "current_session_latest_date",
    "limit_per_target": 3,
}}
QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: (r"{source_font}", ""))
mode.default_label_font_browse_button.click()
assert Path(r"{copied_font_path}").read_bytes() == b"font"
assert mode.defaults_fields["grid.style.default_label_font"].text() == "fonts/custom-label.ttf"
assert (
    mode._service.state.draft["defaults"]["grid"]["style"]["default_label_font"]
    == "fonts/custom-label.ttf"
)
minimum_placeholder_height = (
    mode.placeholder_table.horizontalHeader().sizeHint().height()
    + mode.placeholder_table.verticalHeader().defaultSectionSize() * 5
)
assert mode.placeholder_table.minimumHeight() >= minimum_placeholder_height
mode.placeholder_table.setItem(
    1,
    _PLACEHOLDER_COLUMNS["value"],
    QTableWidgetItem("Doi {{target_name}}"),
)
mode.apply_button.click()
target = mode._service.target("target_a")
assert "value" not in target["export"]["placeholders"][0]
assert target["export"]["placeholders"][1]["value"] == "Doi {{target_name}}"
assert target["export"]["placeholders"][1]["element_id"] == 13
assert "date_format" not in target["export"]
assert "time_format" not in target["export"]
assert "map_background_color" not in target["export"]
assert "label_format" not in target["grid"]
assert target["export"]["placeholders"][1]["selector"] == {{"name": "Title Shape"}}
assert target["export"]["placeholders"][1]["diagnostic_name"] == "Title placeholder"
assert target["export"]["placeholders"][1]["required"] is False
mode.add_placeholder_button.click()
new_placeholder_row = mode.placeholder_table.rowCount() - 1
mode.placeholder_table.setItem(
    new_placeholder_row,
    _PLACEHOLDER_COLUMNS["field"],
    QTableWidgetItem("custom_comment"),
)
mode.placeholder_table.setItem(
    new_placeholder_row,
    _PLACEHOLDER_COLUMNS["value"],
    QTableWidgetItem("Ghi chu rieng"),
)
mode.apply_button.click()
target = mode._service.target("target_a")
assert any(
    placeholder["field"] == "custom_comment" and placeholder["value"] == "Ghi chu rieng"
    for placeholder in target["export"]["placeholders"]
)
for row in range(mode.placeholder_table.rowCount()):
    if mode.placeholder_table.item(row, _PLACEHOLDER_COLUMNS["field"]).text() == "custom_comment":
        mode.placeholder_table.selectRow(row)
        break
else:
    raise AssertionError("custom_comment row not found")
mode.delete_placeholder_button.click()
mode.apply_button.click()
target = mode._service.target("target_a")
assert all(
    placeholder["field"] != "custom_comment"
    for placeholder in target["export"]["placeholders"]
)
mode.group_list.setCurrentRow(1)
mode.add_target_button.click()
assert len(mode._service.targets_for_group("1.1")) == 2
assert mode.import_geojson_button.isEnabled()
assert not mode.export_geojson_button.isEnabled()
mode.target_fields["name"].setText("New GeoJSON Target")
mode.target_fields["alias"].setText("NGT")
mode.target_fields["group.key"].setText("2.1")
mode.target_fields["group.title"].setText("Có người Hoàng Sa")
QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: (r"{geojson_path}", ""))
mode.import_geojson_button.click()
imported_target = mode._service.target("NewGeoJSONTarget")
assert imported_target is not None
assert imported_target["name"] == "New GeoJSON Target"
assert imported_target["alias"] == "NGT"
assert imported_target["group"] == {{"key": "2.1", "title": "Có người Hoàng Sa"}}
assert imported_target["metadata"]["geojson_geometry"] == {{
    "type": "Point",
    "coordinates": [112.0, 9.0],
}}
assert imported_target["coordinate"] == [112.0, 9.0]
assert mode._selected_target_id == "NewGeoJSONTarget"
assert '"target_id": "NewGeoJSONTarget"' in mode.geometry_text.toPlainText()
assert "112.0" in mode.geometry_text.toPlainText()
mode.target_fields["name"].setText("Renamed Before Group Change")
mode.group_list.setCurrentRow(0)
assert mode._service.target("RenamedBeforeGroupChange")["name"] == "Renamed Before Group Change"
mode.close()
print("config-mode-ok")
"""
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "config-mode-ok" in result.stdout
