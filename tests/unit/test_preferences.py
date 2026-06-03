from __future__ import annotations

from pathlib import Path

from thucthengay.editor.preferences import (
    PreferencesService,
    _default_app_config_dir,
    default_preferences_file,
)


def test_preferences_service_records_recent_projects_and_round_trips(tmp_path: Path) -> None:
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()
    service = PreferencesService(tmp_path / "preferences.json")

    assert service.record_recent_project(
        config_path=config_file,
        imagery_folder=imagery_folder,
        workspace_folder=workspace_folder,
    )
    assert service.record_recent_project(
        config_path=config_file,
        workspace_folder=workspace_folder,
    )

    reloaded = PreferencesService(tmp_path / "preferences.json")
    assert len(reloaded.preferences.recent_projects) == 1
    recent = reloaded.preferences.recent_projects[0]
    assert recent.config_path == str(config_file.resolve())
    assert recent.imagery_folder == str(imagery_folder.resolve())
    assert recent.workspace_folder == str(workspace_folder.resolve())


def test_preferences_service_persists_layout_and_export_options(tmp_path: Path) -> None:
    service = PreferencesService(tmp_path / "preferences.json")

    assert service.update_window_size(1440, 900)
    assert service.update_review_splitter_sizes([420, 960])
    assert service.update_export_output_stem("daily_report")

    reloaded = PreferencesService(tmp_path / "preferences.json")
    assert reloaded.preferences.ui.window_size == [1440, 900]
    assert reloaded.preferences.ui.review_main_splitter_sizes == [420, 960]
    assert reloaded.preferences.export.output_stem == "daily_report"
    assert reloaded.preferences.preview.gis_preview_quality == "balanced"


def test_preferences_service_persists_setup_parameters(tmp_path: Path) -> None:
    config_file = tmp_path / "project.json"
    imagery_folder = tmp_path / "imagery"
    workspace_folder = tmp_path / "workspace"
    service = PreferencesService(tmp_path / "preferences.json")

    assert service.update_setup_parameters(
        config_path=config_file,
        imagery_folder=imagery_folder,
        workspace_folder=workspace_folder,
    )

    reloaded = PreferencesService(tmp_path / "preferences.json")
    assert reloaded.preferences.setup.last_config_path == str(config_file.resolve())
    assert reloaded.preferences.setup.last_imagery_folder == str(imagery_folder.resolve())
    assert reloaded.preferences.setup.last_workspace_folder == str(workspace_folder.resolve())


def test_default_preferences_file_uses_appdata_on_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("THUCTHENGAY_PREFERENCES_FILE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    assert _default_app_config_dir(os_name="nt") == tmp_path / "Roaming" / "3.ThucTheNgay"


def test_default_preferences_file_can_be_overridden(tmp_path: Path, monkeypatch) -> None:
    override = tmp_path / "custom-preferences.json"
    monkeypatch.setenv("THUCTHENGAY_PREFERENCES_FILE", str(override))

    assert default_preferences_file() == override
