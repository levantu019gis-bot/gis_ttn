"""Satellite image download tab."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from thucthengay.download import (
    DownloadFilenameFormatRule,
    DownloadRunStatus,
    SatelliteDownloadConfigError,
    SatelliteDownloadRequest,
    SatelliteDownloadResult,
    resolve_download_request,
)
from thucthengay.editor.widgets.multi_path_list import MultiPathListWidget
from thucthengay.editor.widgets.path_picker import PathKind, PathPickerRow
from thucthengay.jobs import ProgressEvent


class DownloadMode(QWidget):
    """Configure an in-app satellite image download request."""

    downloadRequested = Signal(object)
    cancelRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("downloadMode")
        self.geojson_files = MultiPathListWidget(
            "GeoJSON dau vao",
            PathKind.GEOJSON_FILE,
            add_button_text="Them file",
            empty_message="Chua chon file GeoJSON dau vao.",
            dialog_caption="Chon file GeoJSON",
            file_filter="GeoJSON files (*.geojson *.json);;All files (*)",
        )
        self.geojson_files.setObjectName("downloadGeojsonFiles")
        self.image_folders = MultiPathListWidget(
            "Thu muc anh nguon",
            PathKind.INPUT_FOLDER,
            add_button_text="Them folder",
            empty_message="Chua chon folder anh dau vao.",
            dialog_caption="Chon folder anh nguon",
        )
        self.image_folders.setObjectName("downloadImageFolders")
        self.output_row = PathPickerRow(
            "Output",
            PathKind.OUTPUT_FOLDER,
            dialog_caption="Chon folder output",
        )
        self.output_row.setObjectName("downloadOutputFolder")
        self.output_hint = QLabel(
            "Anh copy ve se nam trong output/ten_geojson/ten_folder_anh/..."
        )
        self.output_hint.setObjectName("downloadOutputStructureHint")
        self.output_hint.setWordWrap(True)

        self.overwrite_checkbox = QCheckBox("Ghi de file da ton tai")
        self.overwrite_checkbox.setObjectName("downloadOverwrite")
        self.dry_run_checkbox = QCheckBox("Chi kiem tra, khong copy file")
        self.dry_run_checkbox.setObjectName("downloadDryRun")
        self.include_boundary_checkbox = QCheckBox("Tinh ca anh cham bien GeoJSON")
        self.include_boundary_checkbox.setObjectName("downloadIncludeBoundaryTouch")
        self.include_boundary_checkbox.setChecked(True)
        self.preserve_tree_checkbox = QCheckBox("Giu cau truc thu muc con cua folder nguon")
        self.preserve_tree_checkbox.setObjectName("downloadPreserveSourceTree")
        self.preserve_tree_checkbox.setChecked(True)
        self.write_manifest_checkbox = QCheckBox("Ghi manifest CSV")
        self.write_manifest_checkbox.setObjectName("downloadWriteManifest")
        self.write_manifest_checkbox.setChecked(True)
        self.cloud_filter_checkbox = QCheckBox("Loc cloud theo ten file")
        self.cloud_filter_checkbox.setObjectName("downloadCloudFilterEnabled")
        self.cloud_filter_spin = QDoubleSpinBox()
        self.cloud_filter_spin.setObjectName("downloadMaxCloudPercent")
        self.cloud_filter_spin.setRange(0.0, 100.0)
        self.cloud_filter_spin.setDecimals(1)
        self.cloud_filter_spin.setSingleStep(5.0)
        self.cloud_filter_spin.setValue(90.0)
        self.cloud_filter_spin.setSuffix(" %")
        self.cloud_filter_spin.setMinimumHeight(28)
        self.cloud_filter_spin.setEnabled(False)
        self.cloud_filter_spin.setToolTip(
            "Ap dung cho filename co token cloud-percent/cloud_percent theo format mac dinh."
        )
        self.scan_workers_spin = QSpinBox()
        self.scan_workers_spin.setObjectName("downloadScanWorkers")
        self.scan_workers_spin.setRange(1, 16)
        self.scan_workers_spin.setValue(4)
        self.scan_workers_spin.setMinimumHeight(28)
        self.scan_workers_spin.setToolTip("So worker doc metadata raster song song.")

        self.download_button = QPushButton("Download")
        self.download_button.setObjectName("downloadRunButton")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("downloadCancelButton")
        self.cancel_button.setVisible(False)
        self.status_label = QLabel()
        self.status_label.setObjectName("downloadStatus")
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("downloadProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_detail_label = QLabel("Chua chay download.")
        self.progress_detail_label.setObjectName("downloadProgressDetail")
        self.progress_detail_label.setWordWrap(True)
        self.summary_label = QLabel("Chua co ket qua download.")
        self.summary_label.setObjectName("downloadSummary")
        self.summary_label.setWordWrap(True)
        self._download_running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        layout.addWidget(self._path_group())
        layout.addWidget(self._options_group())
        layout.addWidget(self._progress_group())
        layout.addWidget(self._summary_group())
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.download_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.status_label, 1)
        layout.addLayout(actions)

        self.geojson_files.pathsChanged.connect(self._update_action_state)
        self.image_folders.pathsChanged.connect(self._update_action_state)
        self.output_row.validationChanged.connect(self._update_action_state)
        self.overwrite_checkbox.toggled.connect(self._update_action_state)
        self.dry_run_checkbox.toggled.connect(self._update_action_state)
        self.include_boundary_checkbox.toggled.connect(self._update_action_state)
        self.preserve_tree_checkbox.toggled.connect(self._update_action_state)
        self.write_manifest_checkbox.toggled.connect(self._update_action_state)
        self.cloud_filter_checkbox.toggled.connect(self.cloud_filter_spin.setEnabled)
        self.cloud_filter_checkbox.toggled.connect(self._update_action_state)
        self.cloud_filter_spin.valueChanged.connect(self._update_action_state)
        self.scan_workers_spin.valueChanged.connect(self._update_action_state)
        self.download_button.clicked.connect(self._emit_download_requested)
        self.cancel_button.clicked.connect(self.cancelRequested.emit)
        self._update_action_state()

    def selected_request(self) -> SatelliteDownloadRequest | None:
        """Return a validated request for the current form state."""
        request = self._build_request()
        if request is None:
            return None
        try:
            resolve_download_request(request)
        except SatelliteDownloadConfigError:
            return None
        return request

    def _path_group(self) -> QGroupBox:
        group = QGroupBox("Duong dan")
        group.setObjectName("downloadPathGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.geojson_files)
        layout.addWidget(self.image_folders)
        layout.addWidget(self.output_row)
        layout.addWidget(self.output_hint)
        return group

    def _options_group(self) -> QGroupBox:
        group = QGroupBox("Tuy chon")
        group.setObjectName("downloadOptionsGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self.overwrite_checkbox)
        layout.addWidget(self.dry_run_checkbox)
        layout.addWidget(self.include_boundary_checkbox)
        layout.addWidget(self.preserve_tree_checkbox)
        layout.addWidget(self.write_manifest_checkbox)
        cloud_row = QHBoxLayout()
        cloud_row.setContentsMargins(0, 0, 0, 0)
        cloud_row.setSpacing(8)
        cloud_row.addWidget(self.cloud_filter_checkbox)
        cloud_row.addWidget(QLabel("Max cloud"))
        cloud_row.addWidget(self.cloud_filter_spin)
        cloud_row.addStretch(1)
        layout.addLayout(cloud_row)
        workers_row = QHBoxLayout()
        workers_row.setContentsMargins(0, 0, 0, 0)
        workers_row.setSpacing(8)
        workers_row.addWidget(QLabel("Workers scan"))
        workers_row.addWidget(self.scan_workers_spin)
        workers_row.addStretch(1)
        layout.addLayout(workers_row)
        return group

    def _progress_group(self) -> QGroupBox:
        group = QGroupBox("Tien trinh")
        group.setObjectName("downloadProgressGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_detail_label)
        return group

    def _summary_group(self) -> QGroupBox:
        group = QGroupBox("Ket qua")
        group.setObjectName("downloadSummaryGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self.summary_label)
        return group

    def start_download_progress(self) -> None:
        """Lock the form and show live download progress."""
        self._download_running = True
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("Dang chay")
        self.progress_detail_label.setText("Dang khoi dong download va dem anh trong folder nguon.")
        self.summary_label.setText("Dang chay download.")
        self.status_label.setText("Dang tai anh ve tinh...")
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setToolTip("Dung tac vu sau don vi xu ly an toan hien tai.")
        self._set_form_enabled(False)
        self._update_action_state()

    def mark_download_stopping(self) -> None:
        """Reflect that cancellation has been requested."""
        if not self._download_running:
            return
        self.cancel_button.setEnabled(False)
        self.cancel_button.setToolTip("Da yeu cau dung, dang cho tac vu ket thuc an toan.")
        self.status_label.setText("Dang dung download...")

    def show_download_progress(self, event: ProgressEvent) -> None:
        """Show one live download progress event."""
        percent = event.percent
        if percent is not None:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.setValue(percent)
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("Dang chay")
        self.status_label.setText(event.message)
        self.progress_detail_label.setText(_progress_detail(event))

    def show_download_summary(self, result: SatelliteDownloadResult) -> None:
        """Render terminal download result details."""
        self._download_running = False
        if result.status in {DownloadRunStatus.SUCCESS, DownloadRunStatus.WARNING}:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.setValue(100)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setFormat("%p%")
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(False)
        self._set_form_enabled(True)
        self._update_action_state()
        self.summary_label.setText(_summary_text(result))

    def _build_request(self) -> SatelliteDownloadRequest | None:
        output_path = self.output_row.selected_path
        if output_path is None:
            return None
        return SatelliteDownloadRequest(
            geojson_files=self.geojson_files.selected_paths(),
            image_folders=self.image_folders.selected_paths(),
            output_dir=output_path,
            overwrite=self.overwrite_checkbox.isChecked(),
            dry_run=self.dry_run_checkbox.isChecked(),
            include_boundary_touch=self.include_boundary_checkbox.isChecked(),
            preserve_source_tree=self.preserve_tree_checkbox.isChecked(),
            write_manifest=self.write_manifest_checkbox.isChecked(),
            filename_formats=_cloud_filename_formats(
                self.cloud_filter_spin.value()
            )
            if self.cloud_filter_checkbox.isChecked()
            else [],
            scan_workers=self.scan_workers_spin.value(),
        )

    def _blockers(self) -> list[str]:
        blockers: list[str] = []
        blockers.extend(self.geojson_files.blockers())
        blockers.extend(self.image_folders.blockers())
        if not self.output_row.validation.ok:
            blockers.append(self.output_row.validation.message)
        request = self._build_request()
        if request is not None:
            try:
                resolve_download_request(request)
            except SatelliteDownloadConfigError as error:
                blockers.append(str(error))
        return blockers

    def _update_action_state(self, *_args: object) -> None:
        if self._download_running:
            self.download_button.setEnabled(False)
            self.download_button.setToolTip("Dang chay download.")
            return

        blockers = self._blockers()
        ready = not blockers
        self.download_button.setEnabled(ready)
        if ready:
            self.download_button.setToolTip("San sang download anh ve tinh.")
            self.status_label.setText(
                "San sang. Ket qua se nam trong output/ten_geojson/ten_folder_anh/..."
            )
            self.status_label.setProperty("state", "valid")
            return

        reason = blockers[0]
        self.download_button.setToolTip(reason)
        self.status_label.setText(reason)
        self.status_label.setProperty("state", "invalid")

    def _emit_download_requested(self) -> None:
        request = self.selected_request()
        if request is None:
            self._update_action_state()
            return
        self.downloadRequested.emit(request)

    def _set_form_enabled(self, enabled: bool) -> None:
        self.geojson_files.setEnabled(enabled)
        self.image_folders.setEnabled(enabled)
        self.output_row.setEnabled(enabled)
        self.overwrite_checkbox.setEnabled(enabled)
        self.dry_run_checkbox.setEnabled(enabled)
        self.include_boundary_checkbox.setEnabled(enabled)
        self.preserve_tree_checkbox.setEnabled(enabled)
        self.write_manifest_checkbox.setEnabled(enabled)
        self.cloud_filter_checkbox.setEnabled(enabled)
        self.cloud_filter_spin.setEnabled(enabled and self.cloud_filter_checkbox.isChecked())
        self.scan_workers_spin.setEnabled(enabled)


def _cloud_filename_formats(max_cloud_percent: float) -> list[DownloadFilenameFormatRule]:
    """Return the default filename rules used by the in-app download UI."""

    return [
        DownloadFilenameFormatRule(
            raw_format="PSScene_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tif",
            name="planet_psscene_cloud_tif",
            max_cloud_percent=max_cloud_percent,
        ),
        DownloadFilenameFormatRule(
            raw_format="PSScene_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tiff",
            name="planet_psscene_cloud_tiff",
            max_cloud_percent=max_cloud_percent,
        ),
        DownloadFilenameFormatRule(
            raw_format="*_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tif",
            name="generic_cloud_tif",
            max_cloud_percent=max_cloud_percent,
        ),
        DownloadFilenameFormatRule(
            raw_format="*_yyyyMMdd_hhMMss_*_*_cloud_cloud-percent.tiff",
            name="generic_cloud_tiff",
            max_cloud_percent=max_cloud_percent,
        ),
    ]


def _progress_detail(event: ProgressEvent) -> str:
    scanned = _scanned_text(event.scanned_image_count, event.total_image_count)
    parts = [
        f"stage={event.stage}",
        f"files={event.scanned_file_count}",
        f"images_found={event.total_image_count}",
        f"scanned={scanned}",
        f"matched={event.matched_image_count}",
        f"copied={event.downloaded_image_count}",
        f"skipped_existing={event.skipped_existing_count}",
        f"skipped_cloud={event.skipped_cloud_count}",
        f"failed={event.failed_image_count}",
        f"cache_hits={event.metadata_cache_hit_count}",
        f"cache_misses={event.metadata_cache_miss_count}",
    ]
    if event.current_source_folder:
        parts.append(f"source={event.current_source_folder}")
    if event.current_geojson:
        parts.append(f"geojson={event.current_geojson}")
    if event.current_match_context:
        parts.append(f"context={event.current_match_context}")
    return "; ".join(parts)


def _summary_text(result: SatelliteDownloadResult) -> str:
    stats = result.stats
    status_text = _status_text(result.status)
    parts = [
        status_text,
        f"scanned={_scanned_text(stats.scanned_images, stats.total_images)}",
        f"matched={stats.matched_images}",
        f"copied={stats.downloaded_images}",
        f"skipped_existing={stats.skipped_existing}",
        f"skipped_cloud={stats.skipped_cloud}",
        f"failed={stats.failed_images}",
        f"cache_hits={stats.metadata_cache_hits}",
        f"cache_misses={stats.metadata_cache_misses}",
        f"output={result.output_dir or 'khong co'}",
        f"manifest={result.manifest_path or 'khong co'}",
    ]
    if result.issues:
        issue_text = " | ".join(_issue_text(issue) for issue in result.issues[:3])
        parts.append(f"issue={issue_text}")
    if result.status in {
        DownloadRunStatus.WARNING,
        DownloadRunStatus.ERROR,
        DownloadRunStatus.CANCELLED,
    }:
        parts.append(
            "Kiem tra manifest, duong dan khong doc duoc, quyen truy cap, CRS, "
            "filename rule va dung luong dia."
        )
    parts.append(
        "Co the chon output branch nay lam thu muc anh dau vao trong tab Setup."
    )
    return " ".join(parts)


def _status_text(status: DownloadRunStatus) -> str:
    if status == DownloadRunStatus.SUCCESS:
        return "Hoan tat."
    if status == DownloadRunStatus.WARNING:
        return "Canh bao."
    if status == DownloadRunStatus.CANCELLED:
        return "Da dung; output co the chi la mot phan."
    if status == DownloadRunStatus.ERROR:
        return "Loi."
    return "Dang chay."


def _scanned_text(scanned: int, total: int) -> str:
    if total:
        return f"{scanned}/{total}"
    return str(scanned)


def _issue_text(issue: object) -> str:
    message = getattr(issue, "message", str(issue))
    remediation = getattr(issue, "remediation", None)
    if remediation:
        return f"{message} Cach xu ly: {remediation}"
    return message
