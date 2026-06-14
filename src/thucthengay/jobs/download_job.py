"""Progress-reporting satellite download job orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from thucthengay.download import (
    DownloadFilenameFilterResult,
    DownloadManifestRow,
    DownloadOutputResult,
    DownloadRunStatus,
    DownloadStats,
    SatelliteDownloadConfigError,
    SatelliteDownloadRequest,
    SatelliteDownloadResult,
    filter_matches_by_filename_metadata,
    match_source_images,
    resolve_download_request,
    write_download_outputs,
)
from thucthengay.download.models import DownloadImageFolder, DownloadRasterCandidate
from thucthengay.jobs.control import JobCancelled, JobControl
from thucthengay.jobs.progress import JobState, ProgressEvent
from thucthengay.models import Issue, IssueScope, IssueSeverity

ProgressPublisher = Callable[[ProgressEvent], None]


def run_satellite_download_job(
    *,
    job_id: str,
    request: SatelliteDownloadRequest,
    control: JobControl | None = None,
    publish: ProgressPublisher | None = None,
) -> SatelliteDownloadResult:
    """Run the satellite download pipeline and emit job progress events."""

    progress = _DownloadProgressBuilder(job_id=job_id, publish=publish)
    progress.emit(stage="setup", message="Dang chuan bi tac vu tai anh ve tinh.")
    checkpoint = control.checkpoint if control is not None else None

    try:
        if checkpoint is not None:
            checkpoint()
        resolved = resolve_download_request(request)
    except JobCancelled:
        return _finish_cancelled(progress)
    except SatelliteDownloadConfigError as error:
        issue = _config_error_issue(error)
        return _finish_error(
            progress,
            issues=[issue],
            message="Khong the bat dau tai anh vi cau hinh dau vao chua hop le.",
        )
    except OSError as error:
        issue = _runtime_error_issue(error)
        return _finish_error(
            progress,
            issues=[issue],
            message="Khong the bat dau tai anh vi loi duong dan hoac quyen truy cap.",
        )

    try:
        match_result = match_source_images(
            resolved,
            checkpoint=checkpoint,
            on_discovery_progress=(
                lambda scanned_files, image_count, source_folder, path: _emit_discovery_progress(
                    progress,
                    scanned_file_count=scanned_files,
                    image_count=image_count,
                    source_folder=source_folder,
                    path=path,
                )
            ),
            on_progress=lambda stats, candidate, geojson_names: _emit_scan_progress(
                progress,
                stats=stats,
                candidate=candidate,
                geojson_names=geojson_names,
            ),
        )
    except JobCancelled:
        return _finish_cancelled(progress)
    except SatelliteDownloadConfigError as error:
        issue = _config_error_issue(error)
        return _finish_error(
            progress,
            issues=[issue],
            message="Khong the scan anh dau vao vi cau hinh hoac metadata cache chua hop le.",
        )

    try:
        filter_result = filter_matches_by_filename_metadata(
            match_result,
            resolved.filename_formats,
            checkpoint=checkpoint,
            on_progress=lambda stats, status: _emit_filter_progress(
                progress,
                stats=stats,
                status=status,
            ),
        )
    except JobCancelled:
        return _finish_cancelled(progress)
    except SatelliteDownloadConfigError as error:
        issue = _config_error_issue(error)
        return _finish_error(
            progress,
            issues=[issue],
            message="Khong the xu ly metadata ten file vi cau hinh format chua hop le.",
        )

    issues = _warning_issues(filter_result)
    progress.update(stats=filter_result.stats, issues=issues)

    output_result = write_download_outputs(
        resolved,
        filter_result,
        should_cancel=(lambda: control.cancel_requested) if control is not None else None,
        on_progress=lambda partial: _emit_output_progress(progress, partial),
    )
    progress.update(
        stats=output_result.stats,
        output_rows=output_result.rows,
        manifest_path=output_result.manifest_path,
    )

    if output_result.cancelled:
        return _finish_cancelled(progress)

    issues = _warning_issues(filter_result, output_result)
    progress.update(issues=issues)
    if output_result.manifest_path is not None:
        progress.emit(
            stage="manifest",
            current=len(output_result.rows),
            total=len(output_result.rows),
            message=f"Da ghi manifest: {output_result.manifest_path}",
        )

    state = JobState.WARNING if issues else JobState.SUCCESS
    status = DownloadRunStatus.WARNING if issues else DownloadRunStatus.SUCCESS
    message = _completion_message(status, output_result.stats)
    progress.emit(stage="complete", state=state, message=message)
    return SatelliteDownloadResult(
        status=status,
        stats=output_result.stats,
        output_dir=output_result.output_dir,
        manifest_path=output_result.manifest_path,
        output_rows=output_result.rows,
        issues=tuple(issues),
        message=message,
    )


@dataclass
class _DownloadProgressBuilder:
    job_id: str
    publish: ProgressPublisher | None = None
    stats: DownloadStats = field(default_factory=DownloadStats)
    issues: list[Issue] = field(default_factory=list)
    output_rows: tuple[DownloadManifestRow, ...] = ()
    manifest_path: object | None = None
    current_source_folder: str | None = None
    current_geojson: str | None = None
    current_match_context: str | None = None
    scanned_file_count: int = 0

    def update(
        self,
        *,
        stats: DownloadStats | None = None,
        issues: list[Issue] | None = None,
        output_rows: tuple[DownloadManifestRow, ...] | None = None,
        manifest_path: object | None = None,
        current_source_folder: str | None = None,
        current_geojson: str | None = None,
        current_match_context: str | None = None,
        scanned_file_count: int | None = None,
    ) -> None:
        if stats is not None:
            self.stats = stats
        if issues is not None:
            self.issues = list(issues)
        if output_rows is not None:
            self.output_rows = output_rows
        if manifest_path is not None:
            self.manifest_path = manifest_path
        if current_source_folder is not None:
            self.current_source_folder = current_source_folder
        if current_geojson is not None:
            self.current_geojson = current_geojson
        if current_match_context is not None:
            self.current_match_context = current_match_context
        if scanned_file_count is not None:
            self.scanned_file_count = scanned_file_count

    def emit(
        self,
        *,
        stage: str,
        message: str,
        state: JobState = JobState.RUNNING,
        current: int | None = None,
        total: int | None = None,
    ) -> ProgressEvent:
        event = ProgressEvent(
            job_id=self.job_id,
            stage=stage,
            state=state,
            current=current,
            total=total,
            message=message,
            issues=list(self.issues),
            scanned_image_count=self.stats.scanned_images,
            scanned_file_count=self.scanned_file_count,
            total_image_count=self.stats.total_images,
            matched_image_count=self.stats.matched_images,
            downloaded_image_count=self.stats.downloaded_images,
            skipped_existing_count=self.stats.skipped_existing,
            skipped_cloud_count=self.stats.skipped_cloud,
            failed_image_count=self.stats.failed_images,
            metadata_cache_hit_count=self.stats.metadata_cache_hits,
            metadata_cache_miss_count=self.stats.metadata_cache_misses,
            warning_count=len(self.issues),
            current_source_folder=self.current_source_folder,
            current_geojson=self.current_geojson,
            current_match_context=self.current_match_context,
        )
        if self.publish is not None:
            self.publish(event)
        return event


def _emit_discovery_progress(
    progress: _DownloadProgressBuilder,
    *,
    scanned_file_count: int,
    image_count: int,
    source_folder: DownloadImageFolder,
    path: object,
) -> None:
    progress.update(
        stats=DownloadStats(total_images=image_count),
        scanned_file_count=scanned_file_count,
        current_source_folder=source_folder.name,
        current_geojson=None,
        current_match_context=getattr(path, "name", str(path)),
    )
    progress.emit(
        stage="discover",
        message=(
            f"Dang dem anh trong folder nguon: files={scanned_file_count}, "
            f"images={image_count}."
        ),
    )


def _emit_scan_progress(
    progress: _DownloadProgressBuilder,
    *,
    stats: DownloadStats,
    candidate: DownloadRasterCandidate,
    geojson_names: tuple[str, ...],
) -> None:
    current_geojson = ", ".join(geojson_names) if geojson_names else None
    match_context = (
        f"{candidate.path.name} -> {current_geojson}"
        if current_geojson
        else candidate.path.name
    )
    progress.update(
        stats=stats,
        current_source_folder=candidate.source_folder.name,
        current_geojson=current_geojson,
        current_match_context=match_context,
    )
    progress.emit(
        stage="scan",
        current=stats.scanned_images,
        total=stats.total_images,
        message=(
            f"Dang scan anh {stats.scanned_images}/{stats.total_images}; "
            f"matched={stats.matched_images}, failed={stats.failed_images}, "
            f"cache_hits={stats.metadata_cache_hits}, cache_misses={stats.metadata_cache_misses}."
        ),
    )


def _emit_filter_progress(
    progress: _DownloadProgressBuilder,
    *,
    stats: DownloadStats,
    status: str,
) -> None:
    progress.update(stats=stats, current_match_context=status)
    processed = stats.matched_images + stats.skipped_cloud
    progress.emit(
        stage="filter",
        current=processed,
        total=stats.scanned_images,
        message=(
            f"Dang loc metadata/cloud: accepted={stats.matched_images}, "
            f"skipped_cloud={stats.skipped_cloud}."
        ),
    )


def _emit_output_progress(
    progress: _DownloadProgressBuilder,
    output_result: DownloadOutputResult,
) -> None:
    progress.update(
        stats=output_result.stats,
        output_rows=output_result.rows,
        manifest_path=output_result.manifest_path,
    )
    progress.emit(
        stage="output",
        current=len(output_result.rows),
        total=_output_total(output_result),
        message=(
            f"Dang copy anh: copied={output_result.stats.downloaded_images}, "
            f"skipped_existing={output_result.stats.skipped_existing}, "
            f"failed={output_result.stats.failed_images}."
        ),
    )


def _output_total(output_result: DownloadOutputResult) -> int:
    total = (
        output_result.stats.matched_images
        + output_result.stats.skipped_cloud
        + output_result.stats.failed_images
    )
    return max(total, len(output_result.rows))


def _finish_cancelled(progress: _DownloadProgressBuilder) -> SatelliteDownloadResult:
    message = "Da dung tac vu tai anh ve tinh."
    progress.emit(stage="cancelled", state=JobState.CANCELLED, message=message)
    return SatelliteDownloadResult(
        status=DownloadRunStatus.CANCELLED,
        stats=progress.stats,
        manifest_path=progress.manifest_path,  # type: ignore[arg-type]
        output_rows=progress.output_rows,
        issues=tuple(progress.issues),
        message=message,
    )


def _finish_error(
    progress: _DownloadProgressBuilder,
    *,
    issues: list[Issue],
    message: str,
) -> SatelliteDownloadResult:
    progress.update(issues=issues)
    progress.emit(stage="error", state=JobState.ERROR, message=message)
    return SatelliteDownloadResult(
        status=DownloadRunStatus.ERROR,
        stats=progress.stats,
        issues=tuple(issues),
        message=message,
    )


def _warning_issues(
    filter_result: DownloadFilenameFilterResult,
    output_result: DownloadOutputResult | None = None,
) -> list[Issue]:
    issues = [_filename_warning_issue(warning) for warning in filter_result.warnings]
    stats = output_result.stats if output_result is not None else filter_result.stats
    if stats.failed_images:
        issues.append(_nonfatal_failure_issue(stats.failed_images))
    return issues


def _filename_warning_issue(warning: str) -> Issue:
    return Issue(
        issue_id="satellite_download.filename_format_warning",
        severity=IssueSeverity.WARNING,
        scope=IssueScope.PROJECT,
        message=warning,
        remediation="Kiem tra thu tu filename format rule neu ket qua loc cloud khong dung.",
    )


def _nonfatal_failure_issue(failed_count: int) -> Issue:
    return Issue(
        issue_id="satellite_download.nonfatal_failures",
        severity=IssueSeverity.WARNING,
        scope=IssueScope.PROJECT,
        message=f"Co {failed_count} anh bi loi nhung tac vu van tiep tuc.",
        remediation="Mo manifest hoac chi tiet trang thai de xem source_path va loi cu the.",
    )


def _config_error_issue(error: SatelliteDownloadConfigError) -> Issue:
    field_text = f" Truong loi: {error.field_name}." if error.field_name else ""
    return Issue(
        issue_id="satellite_download.config_invalid",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.CONFIG,
        message=f"Cau hinh tai anh khong hop le: {error}.{field_text}",
        remediation="Kiem tra lai danh sach GeoJSON, folder anh, output va filename format.",
    )


def _runtime_error_issue(error: OSError) -> Issue:
    return Issue(
        issue_id="satellite_download.runtime_error",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.PROJECT,
        message=f"Khong the thuc hien tac vu tai anh: {error}",
        remediation="Kiem tra quyen doc/ghi, ket noi LAN va duong dan input/output.",
    )


def _completion_message(status: DownloadRunStatus, stats: DownloadStats) -> str:
    if status == DownloadRunStatus.WARNING:
        return (
            "Tai anh ve tinh hoan tat voi canh bao; "
            f"copied={stats.downloaded_images}, failed={stats.failed_images}."
        )
    return f"Tai anh ve tinh hoan tat; copied={stats.downloaded_images}."
