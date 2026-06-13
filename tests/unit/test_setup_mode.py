from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path
from types import MethodType

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from thucthengay.config import ConfigLoadResult
from thucthengay.editor.app_shell import AppShell, _manifest_config_path
from thucthengay.editor.modes.setup_mode import SetupMode
from thucthengay.editor.preferences import PreferencesService, RecentProjectEntry
from thucthengay.editor.widgets.path_picker import (
    PathKind,
    PathPickerRow,
    PathStatus,
    validate_selected_path,
)
from thucthengay.editor.widgets.workspace_confirmation import ExistingWorkspaceAction
from thucthengay.jobs import IngestionJobResult, JobState, ProgressEvent
from thucthengay.models import (
    GridConfig,
    GridInterval,
    HistoricalSelectionMode,
    ProjectConfig,
    TargetConfig,
)
from thucthengay.workspace import WorkspaceService


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def preferences_service(tmp_path: Path) -> PreferencesService:
    return PreferencesService(tmp_path / "preferences.json")


def test_validate_selected_config_path_requires_json_file(tmp_path: Path) -> None:
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    folder = tmp_path / "folder"
    folder.mkdir()

    assert validate_selected_path(str(config_file), PathKind.CONFIG_FILE).ok

    folder_validation = validate_selected_path(str(folder), PathKind.CONFIG_FILE)
    assert folder_validation.status == PathStatus.INVALID
    assert "file JSON" in folder_validation.message

    txt_file = tmp_path / "project.txt"
    txt_file.write_text("{}", encoding="utf-8")
    txt_validation = validate_selected_path(str(txt_file), PathKind.CONFIG_FILE)
    assert txt_validation.status == PathStatus.INVALID
    assert ".json" in txt_validation.message


def test_path_picker_row_keeps_full_path_tooltip_and_elides_display(tmp_path: Path) -> None:
    qapp()
    long_dir = tmp_path / "very" / "long" / "local" / "or" / "lan" / "workspace" / "path"
    long_dir.mkdir(parents=True)

    row = PathPickerRow("Workspace", PathKind.WORKSPACE_FOLDER)
    row.resize(260, row.sizeHint().height())
    row.set_path(long_dir)
    row.path_field.resize(90, row.path_field.height())
    row.path_field.set_full_text(str(long_dir))

    assert row.validation.ok
    assert row.status_label.text() == "Hợp lệ"
    assert row.path_field.toolTip() == str(long_dir)
    assert row.path_field.text() != str(long_dir)


def test_setup_mode_disables_ingest_until_all_required_paths_are_valid(tmp_path: Path) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()

    setup = SetupMode()
    assert not setup.ingest_button.isEnabled()
    assert not setup.open_workspace_button.isEnabled()
    assert setup.selected_paths() is None

    setup.config_row.set_path(config_file)
    setup.imagery_row.set_path(imagery_folder)
    assert not setup.ingest_button.isEnabled()

    setup.workspace_row.set_path(workspace_folder)
    assert setup.ingest_button.isEnabled()
    assert setup.open_workspace_button.isEnabled()

    selected_paths = setup.selected_paths()
    assert selected_paths is not None
    assert selected_paths.config_file == config_file.resolve()
    assert selected_paths.imagery_input_folder == imagery_folder.resolve()
    assert selected_paths.workspace_folder == workspace_folder.resolve()
    assert selected_paths.historical_loading_enabled is False


def test_setup_mode_exposes_historical_loading_choice_from_config(tmp_path: Path) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text(
        '{"historical_loading": {"enabled": true}, "targets": []}',
        encoding="utf-8",
    )
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()

    setup = SetupMode()
    assert setup.historical_loading_checkbox.text() == "Load historical images"
    assert setup.historical_loading_checkbox.objectName() == "setupHistoricalLoadingEnabled"

    setup.config_row.set_path(config_file)
    setup.imagery_row.set_path(imagery_folder)
    setup.workspace_row.set_path(workspace_folder)

    selected_paths = setup.selected_paths()
    assert selected_paths is not None
    assert setup.historical_loading_checkbox.isChecked()
    assert selected_paths.historical_loading_enabled is True
    assert selected_paths.historical_image_selection is not None
    assert setup.historical_mode_combo.currentData() == "latest_date"
    assert selected_paths.historical_image_selection.mode == HistoricalSelectionMode.LATEST_DATE
    assert selected_paths.historical_image_selection.limit_per_target is None


def test_setup_mode_exposes_historical_date_range_from_config(tmp_path: Path) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text(
        (
            '{"historical_loading": {"enabled": true, "image_selection": {'
            '"mode": "date_range", "start_date": "2026-05-01", '
            '"end_date": "2026-05-31"}}, "targets": []}'
        ),
        encoding="utf-8",
    )
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()

    setup = SetupMode()
    setup.config_row.set_path(config_file)
    setup.imagery_row.set_path(imagery_folder)
    setup.workspace_row.set_path(workspace_folder)

    selected_paths = setup.selected_paths()
    assert selected_paths is not None
    assert setup.historical_mode_combo.currentData() == "date_range"
    assert setup.historical_start_date_edit.isEnabled()
    assert setup.historical_end_date_edit.isEnabled()
    assert selected_paths.historical_image_selection is not None
    assert selected_paths.historical_image_selection.mode == HistoricalSelectionMode.DATE_RANGE
    assert selected_paths.historical_image_selection.start_date == date(2026, 5, 1)
    assert selected_paths.historical_image_selection.end_date == date(2026, 5, 31)


def test_setup_mode_can_request_opening_existing_workspace_with_workspace_only(
    tmp_path: Path,
) -> None:
    qapp()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()
    setup = SetupMode()
    emitted: list[Path] = []
    setup.openWorkspaceRequested.connect(emitted.append)

    setup.workspace_row.set_path(workspace_folder)
    setup.open_workspace_button.click()

    assert emitted == [workspace_folder.resolve()]


def test_setup_mode_applies_recent_project_paths(tmp_path: Path) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()
    setup = SetupMode()
    recent = RecentProjectEntry(
        label="workspace",
        config_path=str(config_file),
        imagery_folder=str(imagery_folder),
        workspace_folder=str(workspace_folder),
        last_opened_at="2026-06-03T00:00:00+00:00",
    )

    setup.set_recent_projects([recent])
    setup.apply_recent_button.click()

    assert setup.selected_paths() is not None
    assert setup.selected_paths().config_file == config_file.resolve()
    assert setup.selected_paths().imagery_input_folder == imagery_folder.resolve()
    assert setup.selected_paths().workspace_folder == workspace_folder.resolve()


def test_app_shell_restores_recent_setup_parameters(tmp_path: Path) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()
    preferences = preferences_service(tmp_path)
    preferences.update_setup_parameters(
        config_path=config_file,
        imagery_folder=imagery_folder,
        workspace_folder=workspace_folder,
    )

    shell = AppShell(preferences_service=PreferencesService(tmp_path / "preferences.json"))

    selected_paths = shell.setup_mode.selected_paths()
    assert selected_paths is not None
    assert selected_paths.config_file == config_file.resolve()
    assert selected_paths.imagery_input_folder == imagery_folder.resolve()
    assert selected_paths.workspace_folder == workspace_folder.resolve()


def test_app_shell_persists_recent_setup_parameter_changes(tmp_path: Path) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()
    preferences = preferences_service(tmp_path)
    shell = AppShell(preferences_service=preferences)

    shell.setup_mode.config_row.set_path(config_file)
    shell.setup_mode.imagery_row.set_path(imagery_folder)
    shell.setup_mode.workspace_row.set_path(workspace_folder)

    reloaded = PreferencesService(tmp_path / "preferences.json")
    assert reloaded.preferences.setup.last_config_path == str(config_file.resolve())
    assert reloaded.preferences.setup.last_imagery_folder == str(imagery_folder.resolve())
    assert reloaded.preferences.setup.last_workspace_folder == str(workspace_folder.resolve())


def test_setup_mode_reports_first_blocker_in_ingest_tooltip(tmp_path: Path) -> None:
    qapp()
    setup = SetupMode()

    missing_config = tmp_path / "missing.json"
    setup.config_row.set_path(missing_config)

    assert not setup.ingest_button.isEnabled()
    assert "Không tìm thấy" in setup.ingest_button.toolTip()


def test_setup_mode_requires_confirmation_before_ingest_with_existing_workspace_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    (workspace_folder / "cache").mkdir(parents=True)
    (workspace_folder / "cache" / "old.tif").write_text("old", encoding="utf-8")

    confirmed_plans = []

    def cancel_existing_workspace(_parent, plan):
        confirmed_plans.append(plan)
        return ExistingWorkspaceAction.CANCEL

    monkeypatch.setattr(
        "thucthengay.editor.modes.setup_mode.choose_existing_workspace_action",
        cancel_existing_workspace,
    )

    setup = SetupMode()
    emitted = []
    setup.ingestRequested.connect(emitted.append)
    setup.config_row.set_path(config_file)
    setup.imagery_row.set_path(imagery_folder)
    setup.workspace_row.set_path(workspace_folder)

    setup.ingest_button.click()

    assert confirmed_plans
    assert emitted == []


def test_setup_mode_emits_clear_flags_after_workspace_clear_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    (workspace_folder / "cache").mkdir(parents=True)
    (workspace_folder / "cache" / "old.tif").write_text("old", encoding="utf-8")

    confirmed_plans = []

    def choose_clear(_parent, plan):
        confirmed_plans.append(plan)
        return ExistingWorkspaceAction.CLEAR

    monkeypatch.setattr(
        "thucthengay.editor.modes.setup_mode.choose_existing_workspace_action",
        choose_clear,
    )

    setup = SetupMode()
    emitted = []
    setup.ingestRequested.connect(emitted.append)
    setup.config_row.set_path(config_file)
    setup.imagery_row.set_path(imagery_folder)
    setup.workspace_row.set_path(workspace_folder)

    setup.ingest_button.click()

    assert confirmed_plans
    assert len(emitted) == 1
    selected_paths = emitted[0]
    assert selected_paths.clear_existing_workspace is True
    assert selected_paths.clear_workspace_confirmed is True
    assert selected_paths.override_existing_workspace is False


def test_setup_mode_emits_override_flag_for_existing_workspace_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    (workspace_folder / "cache").mkdir(parents=True)
    (workspace_folder / "cache" / "old.tif").write_text("old", encoding="utf-8")

    selected_actions = []

    def choose_override(_parent, plan):
        selected_actions.append(plan)
        return ExistingWorkspaceAction.OVERRIDE

    monkeypatch.setattr(
        "thucthengay.editor.modes.setup_mode.choose_existing_workspace_action",
        choose_override,
    )

    setup = SetupMode()
    emitted = []
    setup.ingestRequested.connect(emitted.append)
    setup.config_row.set_path(config_file)
    setup.imagery_row.set_path(imagery_folder)
    setup.workspace_row.set_path(workspace_folder)

    setup.ingest_button.click()

    assert selected_actions
    assert len(emitted) == 1
    selected_paths = emitted[0]
    assert selected_paths.clear_existing_workspace is False
    assert selected_paths.clear_workspace_confirmed is False
    assert selected_paths.override_existing_workspace is True


def test_setup_mode_shows_live_ingestion_progress_and_locks_action(tmp_path: Path) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    workspace_folder.mkdir()

    setup = SetupMode()
    setup.config_row.set_path(config_file)
    setup.imagery_row.set_path(imagery_folder)
    setup.workspace_row.set_path(workspace_folder)
    assert setup.ingest_button.isEnabled()

    setup.start_ingestion_progress()
    assert not setup.progress_widget.isHidden()
    assert setup.progress_widget.progress_body.isHidden()
    assert not setup.ingest_button.isEnabled()
    assert not setup.pause_button.isHidden()
    assert not setup.stop_button.isHidden()
    assert setup.pause_button.text() == "Tạm dừng"

    setup.show_ingestion_progress(
        ProgressEvent(
            job_id="job",
            stage="scan",
            current=2,
            total=5,
            message="Đang scan ảnh.",
            scanned_file_count=2,
            total_image_count=5,
            scanned_image_count=1,
        )
    )
    assert not setup.progress_widget.progress_body.isHidden()
    assert setup.progress_widget.image_progress.value() == 2
    assert setup.progress_widget.image_progress.maximum() == 5
    assert setup.progress_widget.image_count_label.text() == "Ảnh đã scan: 2/5 (hợp lệ: 1)"

    setup.show_ingestion_progress(
        ProgressEvent(
            job_id="job",
            stage="match",
            current=1,
            total=3,
            message="Đang scan target Alpha.",
            processed_target_count=1,
            total_target_count=3,
            current_target_id="alpha",
            current_target_name="Alpha",
            current_target_matched_count=4,
        )
    )
    assert setup.progress_widget.target_progress.value() == 1
    assert setup.progress_widget.target_progress.maximum() == 3
    assert setup.progress_widget.target_count_label.text() == "Target đã scan: 1/3"
    assert setup.progress_widget.current_target_label.text() == (
        "Target hiện tại: Alpha - đã lấy 4 ảnh"
    )

    setup.show_ingestion_progress(
        ProgressEvent(job_id="job", stage="complete", state=JobState.SUCCESS, message="Xong.")
    )
    assert setup.ingest_button.isEnabled()
    assert setup.pause_button.isHidden()
    assert setup.stop_button.isHidden()


def test_setup_mode_emits_pause_resume_and_stop_controls(tmp_path: Path) -> None:
    qapp()
    setup = SetupMode()
    pauses: list[bool] = []
    resumes: list[bool] = []
    stops: list[bool] = []
    setup.pauseRequested.connect(lambda: pauses.append(True))
    setup.resumeRequested.connect(lambda: resumes.append(True))
    setup.stopRequested.connect(lambda: stops.append(True))

    setup.start_ingestion_progress()
    setup.pause_button.click()
    assert pauses == [True]

    setup.mark_ingestion_paused()
    assert setup.pause_button.text() == "Tiếp tục"
    setup.pause_button.click()
    assert resumes == [True]

    setup.mark_ingestion_resumed()
    setup.stop_button.click()
    assert stops == [True]
    setup.mark_ingestion_stopping()
    assert not setup.pause_button.isEnabled()
    assert not setup.stop_button.isEnabled()


def test_app_shell_runs_ingestion_when_setup_requests_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    imagery_folder = tmp_path / "imagery"
    imagery_folder.mkdir()
    workspace_folder = tmp_path / "workspace"
    (workspace_folder / "cache").mkdir(parents=True)
    (workspace_folder / "cache" / "old.tif").write_text("old", encoding="utf-8")
    target = TargetConfig(
        id="alpha",
        name="Alpha",
        geojson_file="alpha.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export={"template_pptx_file": "alpha.pptx"},
    )
    config_result = ConfigLoadResult(
        config_path=config_file.resolve(),
        config=ProjectConfig(targets=[target]),
        enabled_targets=[target],
    )
    calls: dict[str, object] = {}

    def fake_load_project_config(path: Path) -> ConfigLoadResult:
        calls["config_path"] = path
        return config_result

    def fake_run_ingestion_job(**kwargs) -> IngestionJobResult:
        calls["job_kwargs"] = kwargs
        kwargs["publish"](
            ProgressEvent(
                job_id=kwargs["job_id"],
                stage="scan",
                current=1,
                total=2,
                message="Đang scan ảnh.",
                scanned_file_count=1,
                total_image_count=2,
                scanned_image_count=1,
            )
        )
        kwargs["publish"](
            ProgressEvent(
                job_id=kwargs["job_id"],
                stage="match",
                current=1,
                total=1,
                message="Đang scan target Alpha.",
                scanned_file_count=1,
                total_image_count=2,
                scanned_image_count=1,
                processed_target_count=1,
                total_target_count=1,
                current_target_id="alpha",
                current_target_name="Alpha",
                current_target_matched_count=1,
            )
        )
        return IngestionJobResult(
            job_id=kwargs["job_id"],
            state=JobState.SUCCESS,
            issues=[],
            scanned_image_count=1,
            matched_image_count=1,
            targets_with_images_count=1,
            composition_ids=["alpha__20260525"],
        )

    monkeypatch.setattr(
        "thucthengay.editor.ingestion_worker.load_project_config",
        fake_load_project_config,
    )
    monkeypatch.setattr(
        "thucthengay.editor.ingestion_worker.run_ingestion_job",
        fake_run_ingestion_job,
    )
    confirmed_plans = []

    def choose_override(_parent, plan):
        confirmed_plans.append(plan)
        return ExistingWorkspaceAction.OVERRIDE

    monkeypatch.setattr(
        "thucthengay.editor.modes.setup_mode.choose_existing_workspace_action",
        choose_override,
    )

    shell = AppShell(preferences_service=preferences_service(tmp_path))
    loaded_modes: list[tuple[str, WorkspaceService, list[TargetConfig] | None]] = []

    def capture_review_load(self, service, *, targets=None) -> None:
        loaded_modes.append(("review", service, targets))

    def capture_export_load(
        self,
        service,
        *,
        targets=None,
        template_issues=None,
        history_service=None,
    ) -> None:
        del template_issues, history_service
        loaded_modes.append(("export", service, targets))

    shell.review_edit_mode.load_workspace = MethodType(
        capture_review_load,
        shell.review_edit_mode,
    )
    shell.export_mode.load_workspace = MethodType(
        capture_export_load,
        shell.export_mode,
    )
    shell.setup_mode.config_row.set_path(config_file)
    shell.setup_mode.imagery_row.set_path(imagery_folder)
    shell.setup_mode.workspace_row.set_path(workspace_folder)
    shell.setup_mode.historical_loading_checkbox.setChecked(True)
    shell.setup_mode.historical_mode_combo.setCurrentIndex(
        shell.setup_mode.historical_mode_combo.findData("date_range")
    )
    shell.setup_mode.historical_start_date_edit.setDate(QDate(2026, 5, 1))
    shell.setup_mode.historical_end_date_edit.setDate(QDate(2026, 5, 31))

    shell.setup_mode.ingest_button.click()
    deadline = time.monotonic() + 3
    while shell._ingestion_thread is not None and time.monotonic() < deadline:
        qapp().processEvents()
        time.sleep(0.01)

    assert calls["config_path"] == config_file.resolve()
    assert confirmed_plans
    job_kwargs = calls["job_kwargs"]
    assert job_kwargs["config_result"] is config_result
    assert job_kwargs["config_result"].config.historical_loading.enabled is True
    selection = job_kwargs["config_result"].config.historical_loading.image_selection
    assert selection.mode == HistoricalSelectionMode.DATE_RANGE
    assert selection.start_date == date(2026, 5, 1)
    assert selection.end_date == date(2026, 5, 31)
    assert job_kwargs["imagery_folder"] == imagery_folder.resolve()
    assert job_kwargs["workspace_service"].paths.root == workspace_folder.resolve()
    assert job_kwargs["clear_existing"] is False
    assert job_kwargs["clear_confirmed"] is False
    assert job_kwargs["merge_existing"] is True
    assert callable(job_kwargs["publish"])
    assert shell.setup_mode.progress_widget.image_count_label.text() == (
        "Ảnh đã scan: 1/2 (hợp lệ: 1)"
    )
    assert shell.setup_mode.progress_widget.target_count_label.text() == "Target đã scan: 1/1"
    assert shell.setup_mode.summary_widget.scanned_label.text() == "1"
    assert loaded_modes == [
        ("review", job_kwargs["workspace_service"], [target]),
        ("export", job_kwargs["workspace_service"], [target]),
    ]
    assert shell.mode_tabs.currentWidget() is shell.review_edit_mode
    assert shell.preferences_service.preferences.recent_projects[0].workspace_folder == str(
        workspace_folder.resolve()
    )


def test_app_shell_opens_existing_workspace_from_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    qapp()
    config_file = tmp_path / "project.json"
    config_file.write_text("{}", encoding="utf-8")
    workspace_folder = tmp_path / "workspace"
    service = WorkspaceService(workspace_folder)
    service.initialize(config_path=config_file.resolve())
    target = TargetConfig(
        id="alpha",
        name="Alpha",
        geojson_file="alpha.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export={"template_pptx_file": "alpha.pptx"},
    )
    config_result = ConfigLoadResult(
        config_path=config_file.resolve(),
        enabled_targets=[target],
    )
    calls: dict[str, object] = {}

    def fake_load_project_config(path: Path) -> ConfigLoadResult:
        calls["config_path"] = path
        return config_result

    monkeypatch.setattr(
        "thucthengay.editor.app_shell.load_project_config",
        fake_load_project_config,
    )

    shell = AppShell(preferences_service=preferences_service(tmp_path))
    loaded_modes: list[tuple[str, WorkspaceService, list[TargetConfig] | None]] = []

    def capture_review_load(self, loaded_service, *, targets=None) -> None:
        loaded_modes.append(("review", loaded_service, targets))

    def capture_export_load(
        self,
        loaded_service,
        *,
        targets=None,
        template_issues=None,
        history_service=None,
    ) -> None:
        del template_issues, history_service
        loaded_modes.append(("export", loaded_service, targets))

    shell.review_edit_mode.load_workspace = MethodType(
        capture_review_load,
        shell.review_edit_mode,
    )
    shell.export_mode.load_workspace = MethodType(
        capture_export_load,
        shell.export_mode,
    )
    shell.setup_mode.workspace_row.set_path(workspace_folder)

    shell.setup_mode.open_workspace_button.click()

    assert calls["config_path"] == config_file.resolve()
    assert loaded_modes == [
        ("review", loaded_modes[0][1], [target]),
        ("export", loaded_modes[0][1], [target]),
    ]
    assert loaded_modes[0][1].paths.root == workspace_folder.resolve()
    assert "Đã mở workspace" in shell.setup_mode.workspace_status_label.text()
    assert shell.mode_tabs.currentWidget() is shell.review_edit_mode
    assert shell.preferences_service.preferences.recent_projects[0].config_path == str(
        config_file.resolve()
    )


def test_manifest_config_path_falls_back_when_absolute_path_was_moved(tmp_path: Path) -> None:
    project_config = tmp_path / "config.json"
    project_config.write_text("{}", encoding="utf-8")
    workspace = tmp_path / "examples" / "w1"
    workspace.mkdir(parents=True)

    resolved = _manifest_config_path(r"C:\old\project\config.json", workspace)

    assert resolved == project_config.resolve()
