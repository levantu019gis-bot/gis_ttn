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
        "coordinate": [106.7, 10.8],
        "scale": 50000,
        "grid": {"interval": {"minutes": 1}},
        "export": {
            "template_pptx_file": "templates/target_a.pptx",
            "template_txt_value": "Bao cao {target_name} luc {time_label}",
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
                    "value": "{target_name}",
                },
            ],
        },
        "metadata": {"geojson_geometry": {"type": "Point", "coordinates": [106.7, 10.8]}},
    }


def test_config_mode_widget_smoke_runs_in_isolated_qt_process(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "templates" / "target_a.pptx"
    template_path.parent.mkdir()
    template_path.write_bytes(b"pptx")
    copied_template_path = tmp_path / "data" / "templates" / "target_a.pptx"
    write_json(config_path, {"targets": [target_config()]})
    code = f"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PySide6.QtWidgets import QApplication, QTableWidgetItem
from thucthengay.editor.modes.config_mode import ConfigMode
app = QApplication.instance() or QApplication([])
mode = ConfigMode()
mode.load_config(r"{config_path}")
assert mode.stat_labels["targets"].text() == "1"
assert mode.group_list.count() == 2
assert mode.target_model.rowCount() == 1
assert "export.date_format" not in mode.target_fields
assert "export.time_format" not in mode.target_fields
assert mode.template_browse_button.text() == "Browse"
assert mode.target_fields["export.template_pptx_file"].isReadOnly()
assert mode.target_fields["export.template_pptx_file"].text() == "data/templates/target_a.pptx"
assert Path(r"{copied_template_path}").is_file()
mode.placeholder_table.setItem(1, 1, QTableWidgetItem("Doi {{target_name}}"))
mode.apply_button.click()
target = mode._service.target("target_a")
assert target["export"]["placeholders"][1]["value"] == "Doi {{target_name}}"
assert target["export"]["placeholders"][1]["element_id"] == 13
mode.group_list.setCurrentRow(1)
mode.add_target_button.click()
assert len(mode._service.targets_for_group("1.1")) == 2
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
