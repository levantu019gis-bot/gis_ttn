from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from thucthengay.download import (
    DownloadRunStatus,
    DownloadStats,
    SatelliteDownloadRequest,
    SatelliteDownloadResult,
)
from thucthengay.editor.app_shell import AppShell
from thucthengay.editor.modes.download_mode import DownloadMode
from thucthengay.editor.preferences import PreferencesService
from thucthengay.jobs import JobState, ProgressEvent
from thucthengay.models import Issue, IssueScope, IssueSeverity


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_app_shell_adds_download_tab_next_to_config(tmp_path: Path) -> None:
    qapp()

    shell = AppShell(preferences_service=PreferencesService(tmp_path / "preferences.json"))

    assert shell.mode_tabs.count() == 5
    assert shell.mode_tabs.tabText(0) == "Setup"
    assert shell.mode_tabs.tabText(1) == "Review/Edit"
    assert shell.mode_tabs.tabText(2) == "Export"
    assert shell.mode_tabs.tabText(3) == "Download"
    assert shell.mode_tabs.tabText(4) == "Config"
    assert shell.mode_tabs.widget(3) is shell.download_mode


def test_download_mode_disables_action_until_required_inputs_are_valid(tmp_path: Path) -> None:
    qapp()
    mode = DownloadMode()

    assert not mode.download_button.isEnabled()
    assert mode.selected_request() is None
    assert "Chua chon file GeoJSON" in mode.status_label.text()

    output = tmp_path / "output"
    output.mkdir()
    mode.output_row.set_path(output)

    assert not mode.download_button.isEnabled()
    assert "Chua chon file GeoJSON" in mode.status_label.text()


def test_download_mode_builds_request_from_multiple_geojsons_and_folders(
    tmp_path: Path,
) -> None:
    qapp()
    geojson_a = tmp_path / "a.geojson"
    geojson_b = tmp_path / "b.json"
    geojson_a.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    geojson_b.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    output = tmp_path / "output"
    source_a.mkdir()
    source_b.mkdir()
    output.mkdir()

    mode = DownloadMode()
    mode.geojson_files.add_path(geojson_a)
    mode.geojson_files.add_path(geojson_b)
    mode.image_folders.add_path(source_a)
    mode.image_folders.add_path(source_b)
    mode.output_row.set_path(output)

    request = mode.selected_request()

    assert mode.download_button.isEnabled()
    assert isinstance(request, SatelliteDownloadRequest)
    assert request.geojson_files == [geojson_a.resolve(), geojson_b.resolve()]
    assert request.image_folders == [source_a.resolve(), source_b.resolve()]
    assert request.output_dir == output.resolve()
    assert request.include_boundary_touch is True
    assert request.preserve_source_tree is True
    assert request.write_manifest is True
    assert request.scan_workers == 4


def test_download_mode_builds_cloud_filter_and_workers_from_options(
    tmp_path: Path,
) -> None:
    qapp()
    geojson = tmp_path / "a.geojson"
    source = tmp_path / "source"
    output = tmp_path / "output"
    geojson.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    source.mkdir()
    output.mkdir()

    mode = DownloadMode()
    mode.geojson_files.add_path(geojson)
    mode.image_folders.add_path(source)
    mode.output_row.set_path(output)
    mode.cloud_filter_checkbox.setChecked(True)
    mode.cloud_filter_spin.setValue(65.5)
    mode.scan_workers_spin.setValue(8)

    request = mode.selected_request()

    assert isinstance(request, SatelliteDownloadRequest)
    assert mode.cloud_filter_spin.isEnabled()
    assert request.scan_workers == 8
    assert [rule.max_cloud_percent for rule in request.filename_formats] == [
        65.5,
        65.5,
        65.5,
        65.5,
    ]
    assert [rule.raw_format for rule in request.filename_formats] == [
        "PSScene_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tif",
        "PSScene_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tiff",
        "*_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tif",
        "*_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tiff",
    ]


def test_download_mode_keeps_invalid_rows_visible_with_text_status(tmp_path: Path) -> None:
    qapp()
    invalid_geojson = tmp_path / "bad.txt"
    invalid_geojson.write_text("not geojson", encoding="utf-8")

    mode = DownloadMode()
    mode.geojson_files.add_path(invalid_geojson)
    row = mode.geojson_files.row_widgets()[0]

    assert not mode.download_button.isEnabled()
    assert row.status_label.text() == "Loi"
    assert ".geojson" in row.status_label.toolTip()
    assert row.path_field.toolTip() == str(invalid_geojson)


def test_download_mode_add_remove_clear_paths_refreshes_state(tmp_path: Path) -> None:
    qapp()
    geojson_a = tmp_path / "a.geojson"
    geojson_b = tmp_path / "b.geojson"
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    output = tmp_path / "output"
    geojson_a.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    geojson_b.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    source_a.mkdir()
    source_b.mkdir()
    output.mkdir()
    mode = DownloadMode()

    mode.geojson_files.add_paths((str(geojson_a), str(geojson_b)))
    mode.image_folders.add_paths((str(source_a), str(source_b)))
    mode.output_row.set_path(output)

    assert mode.download_button.isEnabled()
    assert [row.selected_path for row in mode.geojson_files.row_widgets()] == [
        geojson_a.resolve(),
        geojson_b.resolve(),
    ]
    assert [row.selected_path for row in mode.image_folders.row_widgets()] == [
        source_a.resolve(),
        source_b.resolve(),
    ]

    mode.geojson_files.row_widgets()[0].remove_button.click()
    qapp().processEvents()

    assert mode.download_button.isEnabled()
    assert mode.geojson_files.selected_paths() == [geojson_b.resolve()]

    mode.geojson_files.clear_paths()
    qapp().processEvents()

    assert not mode.download_button.isEnabled()
    assert "Chua chon file GeoJSON" in mode.status_label.text()
    assert not mode.geojson_files.empty_label.isHidden()

    mode.geojson_files.add_path(geojson_a)
    mode.image_folders.clear_paths()
    qapp().processEvents()

    assert not mode.download_button.isEnabled()
    assert "Chua chon folder anh" in mode.status_label.text()
    assert not mode.image_folders.empty_label.isHidden()


def test_download_mode_shows_success_summary_with_required_counters(tmp_path: Path) -> None:
    qapp()
    output = tmp_path / "out"
    manifest = output / "download-manifest.csv"
    result = SatelliteDownloadResult(
        status=DownloadRunStatus.SUCCESS,
        stats=DownloadStats(
            total_images=12,
            scanned_images=10,
            matched_images=8,
            downloaded_images=7,
            skipped_existing=1,
            skipped_cloud=2,
            failed_images=0,
            metadata_cache_hits=3,
            metadata_cache_misses=9,
        ),
        output_dir=output,
        manifest_path=manifest,
        message="done",
    )
    mode = DownloadMode()

    mode.show_download_summary(result)

    text = mode.summary_label.text()
    assert "Hoan tat" in text
    assert "scanned=10/12" in text
    assert "matched=8" in text
    assert "copied=7" in text
    assert "skipped_existing=1" in text
    assert "skipped_cloud=2" in text
    assert "failed=0" in text
    assert "cache_hits=3" in text
    assert "cache_misses=9" in text
    assert str(output) in text
    assert str(manifest) in text
    assert "Setup" in text


def test_download_mode_warning_summary_includes_failure_remediation(tmp_path: Path) -> None:
    qapp()
    issue = Issue(
        issue_id="satellite_download.nonfatal_failures",
        severity=IssueSeverity.WARNING,
        scope=IssueScope.PROJECT,
        message="Co 2 anh bi loi.",
        remediation="Mo manifest de xem loi.",
    )
    result = SatelliteDownloadResult(
        status=DownloadRunStatus.WARNING,
        stats=DownloadStats(scanned_images=5, matched_images=4, failed_images=2),
        output_dir=tmp_path / "out",
        manifest_path=tmp_path / "out" / "manifest.csv",
        issues=(issue,),
    )
    mode = DownloadMode()

    mode.show_download_summary(result)

    text = mode.summary_label.text()
    assert "Canh bao" in text
    assert "failed=2" in text
    assert "Kiem tra manifest" in text
    assert "duong dan khong doc duoc" in text
    assert "quyen truy cap" in text
    assert "CRS" in text
    assert "filename rule" in text
    assert "dung luong dia" in text


def test_download_mode_cancelled_summary_reports_partial_output(tmp_path: Path) -> None:
    qapp()
    result = SatelliteDownloadResult(
        status=DownloadRunStatus.CANCELLED,
        stats=DownloadStats(scanned_images=3, matched_images=2, downloaded_images=1),
        output_dir=tmp_path / "out",
        manifest_path=tmp_path / "out" / "partial.csv",
    )
    mode = DownloadMode()

    mode.show_download_summary(result)

    text = mode.summary_label.text()
    assert "Da dung" in text
    assert "co the chi la mot phan" in text
    assert "scanned=3" in text
    assert "matched=2" in text
    assert "copied=1" in text
    assert "partial.csv" in text


def test_download_mode_progress_updates_percent_activity_and_counters() -> None:
    qapp()
    mode = DownloadMode()

    mode.start_download_progress()
    mode.show_download_progress(
        ProgressEvent(
            job_id="download-1",
            stage="scan",
            current=3,
            total=6,
            message="Dang scan anh 3/6",
            scanned_image_count=3,
            total_image_count=6,
            matched_image_count=2,
            downloaded_image_count=1,
            skipped_existing_count=1,
            skipped_cloud_count=0,
            failed_image_count=0,
            metadata_cache_hit_count=4,
            metadata_cache_miss_count=2,
            current_source_folder="images",
            current_geojson="area",
            current_match_context="scene.tif -> area",
        )
    )

    assert mode.progress_bar.value() == 50
    assert "Dang scan anh 3/6" in mode.status_label.text()
    assert "scanned=3/6" in mode.progress_detail_label.text()
    assert "matched=2" in mode.progress_detail_label.text()
    assert "copied=1" in mode.progress_detail_label.text()
    assert "source=images" in mode.progress_detail_label.text()
    assert "geojson=area" in mode.progress_detail_label.text()
    assert "scene.tif -> area" in mode.progress_detail_label.text()
    assert not mode.cancel_button.isHidden()


def test_download_mode_shows_indeterminate_progress_while_discovering() -> None:
    qapp()
    mode = DownloadMode()

    mode.start_download_progress()
    mode.show_download_progress(
        ProgressEvent(
            job_id="download-1",
            stage="discover",
            message="Dang dem anh trong folder nguon: files=20, images=7.",
            scanned_file_count=20,
            total_image_count=7,
            current_source_folder="20260610",
            current_match_context="scene.tif",
        )
    )

    assert mode.progress_bar.minimum() == 0
    assert mode.progress_bar.maximum() == 0
    assert "files=20" in mode.progress_detail_label.text()
    assert "images_found=7" in mode.progress_detail_label.text()
    assert "Dang dem anh" in mode.status_label.text()


def test_app_shell_runs_download_job_and_renders_summary(tmp_path: Path) -> None:
    app = qapp()
    geojson = tmp_path / "area.geojson"
    source = tmp_path / "images"
    output = tmp_path / "out"
    geojson.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    source.mkdir()
    output.mkdir()
    calls: list[str] = []

    def fake_runner(**kwargs):
        calls.append("run")
        kwargs["publish"](
            ProgressEvent(
                job_id=kwargs["job_id"],
                stage="complete",
                state=JobState.SUCCESS,
                current=1,
                total=1,
                message="Done",
                scanned_image_count=1,
                total_image_count=1,
                matched_image_count=1,
                downloaded_image_count=1,
            )
        )
        return SatelliteDownloadResult(
            status=DownloadRunStatus.SUCCESS,
            stats=DownloadStats(
                total_images=1,
                scanned_images=1,
                matched_images=1,
                downloaded_images=1,
            ),
            output_dir=output,
            manifest_path=output / "manifest.csv",
        )

    shell = AppShell(
        preferences_service=PreferencesService(tmp_path / "preferences.json"),
        download_runner=fake_runner,
    )
    request = SatelliteDownloadRequest(
        geojson_files=[geojson],
        image_folders=[source],
        output_dir=output,
    )

    shell._run_download(request)

    assert "Dang tai anh" in shell.download_mode.status_label.text()
    assert not shell.download_mode.cancel_button.isHidden()

    for _ in range(100):
        app.processEvents()
        if shell._download_thread is None:
            break

    assert calls == ["run"]
    assert shell._download_thread is None
    assert "Hoan tat" in shell.download_mode.summary_label.text()
    assert "copied=1" in shell.download_mode.summary_label.text()


def test_download_ui_and_worker_do_not_import_workspace_or_history_services() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    guarded_files = [
        repo_root / "src" / "thucthengay" / "editor" / "modes" / "download_mode.py",
        repo_root / "src" / "thucthengay" / "editor" / "download_worker.py",
    ]
    forbidden = (
        "WorkspaceService",
        "HistoryService",
        "run_ingestion_job",
        "run_full_export",
        "run_preview_render_job",
    )

    for path in guarded_files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text
