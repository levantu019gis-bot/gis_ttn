"""Progress-reporting ingestion job orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path

from thucthengay.config.path_resolver import resolve_config_asset_path
from thucthengay.config.service import ConfigLoadResult
from thucthengay.history import (
    HistoricalImageRecord,
    HistoricalLoadingPlan,
    HistoricalLoadingResult,
    HistoryService,
)
from thucthengay.ingestion import (
    CacheImageInput,
    CompositionCreationResult,
    TargetMatchingResult,
    create_target_date_compositions,
    match_imagery_to_targets,
    populate_workspace_cache,
    scan_imagery_folder,
)
from thucthengay.jobs.control import JobCancelled, JobControl
from thucthengay.jobs.progress import JobState, ProgressEvent
from thucthengay.models import (
    HistoricalLoadingTargetScope,
    ImageLayer,
    ImageLayerSourceKind,
    Issue,
    IssueScope,
    IssueSeverity,
    MetadataSource,
    MetadataStatus,
    TargetConfig,
)
from thucthengay.workspace import WorkspaceError, WorkspaceService

ProgressPublisher = Callable[[ProgressEvent], None]
HistoricalLoader = Callable[[HistoricalLoadingPlan], HistoricalLoadingResult]


@dataclass(frozen=True)
class IngestionJobResult:
    """Final result returned by an ingestion job run."""

    job_id: str
    state: JobState
    issues: list[Issue]
    scanned_image_count: int
    matched_image_count: int
    targets_with_images_count: int
    composition_ids: list[str]
    historical_loading_enabled: bool = False
    historical_loaded_image_count: int = 0
    historical_skipped_image_count: int = 0


def run_ingestion_job(
    *,
    job_id: str,
    config_result: ConfigLoadResult,
    imagery_folder: str | Path,
    workspace_service: WorkspaceService,
    clear_existing: bool = False,
    clear_confirmed: bool = False,
    control: JobControl | None = None,
    publish: ProgressPublisher | None = None,
    historical_loader: HistoricalLoader | None = None,
) -> IngestionJobResult:
    """Run the ingestion pipeline and emit progress after every major phase."""
    progress = _ProgressBuilder(job_id=job_id, publish=publish)
    progress.emit(stage="setup", message="Đang chuẩn bị lấy dữ liệu.")
    checkpoint = control.checkpoint if control is not None else None

    fatal_issues = _fatal_setup_issues(config_result.issues)
    historical_setup_issue = _historical_loading_setup_issue(config_result)
    if historical_setup_issue is not None:
        fatal_issues.append(historical_setup_issue)
    if fatal_issues:
        return _finish_with_error(
            progress,
            job_id=job_id,
            issues=fatal_issues,
            message="Không thể bắt đầu lấy dữ liệu vì cấu hình chưa hợp lệ.",
        )
    if not _historical_loading_enabled(config_result):
        progress.emit(
            stage="history",
            message=(
                "Chế độ ảnh lịch sử: Không tải ảnh lịch sử; "
                "chỉ xử lý ảnh của phiên hiện tại."
            ),
        )

    try:
        if checkpoint is not None:
            checkpoint()
        workspace_service.initialize(
            config_path=config_result.config_path,
            imagery_input_path=imagery_folder,
        )
        filename_patterns = (
            config_result.config.filename_patterns if config_result.config else None
        )
        scan_result = scan_imagery_folder(
            imagery_folder,
            on_progress=lambda scanned_file_count, total_image_count, valid_image_count: (
                _emit_scan_progress(
                    progress,
                    scanned_file_count=scanned_file_count,
                    total_image_count=total_image_count,
                    valid_image_count=valid_image_count,
                )
            ),
            checkpoint=checkpoint,
            filename_patterns=filename_patterns or None,
        )
    except JobCancelled:
        return _finish_with_cancelled(progress, job_id=job_id)
    except (NotADirectoryError, OSError, WorkspaceError) as error:
        return _finish_with_error(
            progress,
            job_id=job_id,
            issues=[_setup_error_issue(error)],
            message="Không thể bắt đầu lấy dữ liệu vì lỗi đường dẫn hoặc workspace.",
        )

    issues: list[Issue] = list(scan_result.warnings)
    progress.update(scanned_image_count=len(scan_result.rasters), issues=issues)
    progress.emit(
        stage="scan",
        current=progress.scanned_file_count,
        total=progress.total_image_count,
        message=(
            f"Đã scan {progress.scanned_file_count}/{progress.total_image_count} ảnh; "
            f"{len(scan_result.rasters)} ảnh GeoTIFF hợp lệ."
        ),
    )

    try:
        if checkpoint is not None:
            checkpoint()
        matching_result = match_imagery_to_targets(
            scan_result.rasters,
            config_result,
            on_target_progress=lambda processed_target_count,
            total_target_count,
            target,
            target_match_count: _emit_live_target_match_progress(
                progress,
                processed_target_count=processed_target_count,
                total_target_count=total_target_count,
                target=target,
                target_match_count=target_match_count,
            ),
            checkpoint=checkpoint,
        )
    except JobCancelled:
        return _finish_with_cancelled(progress, job_id=job_id)
    issues.extend(matching_result.issues)
    _emit_target_match_progress(progress, config_result.enabled_targets, matching_result, issues)
    historical_cache_inputs: list[CacheImageInput] = []
    historical_plan = _build_historical_loading_plan(config_result, matching_result)
    historical_loaded_image_count = 0
    historical_skipped_image_count = 0
    if historical_plan.enabled:
        progress.emit(stage="history", message=_historical_loading_message(historical_plan))
        loader = historical_loader or _default_historical_loader(historical_plan)
        if loader is not None:
            historical_result = loader(historical_plan)
            issues.extend(historical_result.issues)
            historical_loaded_image_count = historical_result.loaded_image_count
            historical_skipped_image_count = historical_result.skipped_image_count
            historical_cache_inputs = _historical_cache_inputs(historical_result.records)
            progress.update(issues=issues)

    try:
        if checkpoint is not None:
            checkpoint()
        cache_result = populate_workspace_cache(
            matching_result,
            workspace_service,
            additional_images=historical_cache_inputs,
            clear_existing=clear_existing,
            clear_confirmed=clear_confirmed,
            checkpoint=checkpoint,
        )
        issues.extend(cache_result.issues)
        progress.update(issues=issues)
        progress.emit(stage="cache", message="Đã copy ảnh phù hợp vào workspace cache.")

        composition_result = create_target_date_compositions(
            cache_result,
            _targets_by_id(config_result.enabled_targets),
            workspace_service,
            checkpoint=checkpoint,
        )
    except JobCancelled:
        return _finish_with_cancelled(progress, job_id=job_id)
    except (OSError, WorkspaceError) as error:
        issues.append(_workspace_error_issue(error))
        return _finish_with_error(
            progress,
            job_id=job_id,
            issues=issues,
            message="Không thể hoàn tất lấy dữ liệu vì lỗi workspace.",
        )

    issues.extend(composition_result.issues)
    progress.update(
        issues=issues,
        created_composition_count=len(composition_result.composition_ids),
    )

    state = JobState.WARNING if issues else JobState.SUCCESS
    progress.emit(
        stage="complete",
        state=state,
        message=_completion_message(state, composition_result),
    )
    return IngestionJobResult(
        job_id=job_id,
        state=state,
        issues=issues,
        scanned_image_count=progress.scanned_image_count,
        matched_image_count=progress.matched_image_count,
        targets_with_images_count=progress.targets_with_images_count,
        composition_ids=composition_result.composition_ids,
        historical_loading_enabled=historical_plan.enabled,
        historical_loaded_image_count=historical_loaded_image_count,
        historical_skipped_image_count=historical_skipped_image_count,
    )


@dataclass
class _ProgressBuilder:
    job_id: str
    publish: ProgressPublisher | None = None
    scanned_image_count: int = 0
    matched_image_count: int = 0
    targets_with_images_count: int = 0
    scanned_file_count: int = 0
    total_image_count: int = 0
    processed_target_count: int = 0
    total_target_count: int = 0
    warning_count: int = 0
    issues: list[Issue] | None = None
    created_composition_count: int = 0

    def update(
        self,
        *,
        scanned_image_count: int | None = None,
        scanned_file_count: int | None = None,
        total_image_count: int | None = None,
        matched_image_count: int | None = None,
        targets_with_images_count: int | None = None,
        processed_target_count: int | None = None,
        total_target_count: int | None = None,
        issues: list[Issue] | None = None,
        created_composition_count: int | None = None,
    ) -> None:
        if scanned_image_count is not None:
            self.scanned_image_count = scanned_image_count
        if scanned_file_count is not None:
            self.scanned_file_count = scanned_file_count
        if total_image_count is not None:
            self.total_image_count = total_image_count
        if matched_image_count is not None:
            self.matched_image_count = matched_image_count
        if targets_with_images_count is not None:
            self.targets_with_images_count = targets_with_images_count
        if processed_target_count is not None:
            self.processed_target_count = processed_target_count
        if total_target_count is not None:
            self.total_target_count = total_target_count
        if issues is not None:
            self.issues = list(issues)
            self.warning_count = len(issues)
        if created_composition_count is not None:
            self.created_composition_count = created_composition_count

    def emit(
        self,
        *,
        stage: str,
        message: str,
        state: JobState = JobState.RUNNING,
        current: int | None = None,
        total: int | None = None,
        current_target: TargetConfig | None = None,
        current_target_matched_count: int = 0,
    ) -> ProgressEvent:
        event = ProgressEvent(
            job_id=self.job_id,
            stage=stage,
            state=state,
            current=current,
            total=total,
            message=message,
            issues=list(self.issues or []),
            scanned_image_count=self.scanned_image_count,
            scanned_file_count=self.scanned_file_count,
            total_image_count=self.total_image_count,
            matched_image_count=self.matched_image_count,
            targets_with_images_count=self.targets_with_images_count,
            processed_target_count=self.processed_target_count,
            total_target_count=self.total_target_count,
            warning_count=self.warning_count,
            current_target_id=current_target.id if current_target else None,
            current_target_name=current_target.name if current_target else None,
            current_target_matched_count=current_target_matched_count,
            created_composition_count=self.created_composition_count,
        )
        if self.publish is not None:
            self.publish(event)
        return event


def _emit_target_match_progress(
    progress: _ProgressBuilder,
    targets: list[TargetConfig],
    matching_result: TargetMatchingResult,
    issues: list[Issue],
) -> None:
    matched_image_count = sum(len(matches) for matches in matching_result.matches.values())
    targets_with_images_count = sum(
        1 for matches in matching_result.matches.values() if matches
    )
    total = len(targets)
    progress.update(
        matched_image_count=matched_image_count,
        targets_with_images_count=targets_with_images_count,
        processed_target_count=total if targets else 0,
        total_target_count=total,
        issues=issues,
    )
    if not targets:
        progress.emit(stage="match", current=0, total=0, message="Không có target bật.")
        return

    for index, target in enumerate(targets, start=1):
        current_matches = len(matching_result.matches.get(target.id, []))
        progress.emit(
            stage="match",
            current=index,
            total=total,
            message=f"Target `{target.name}` có {current_matches} ảnh phù hợp.",
            current_target=target,
            current_target_matched_count=current_matches,
        )

    progress.emit(
        stage="match",
        current=total,
        total=total,
        message=(
            f"Đã scan {total}/{total} target; "
            f"{matched_image_count} ảnh phù hợp trên {targets_with_images_count} target."
        ),
    )


def _emit_scan_progress(
    progress: _ProgressBuilder,
    *,
    scanned_file_count: int,
    total_image_count: int,
    valid_image_count: int,
) -> None:
    progress.update(
        scanned_file_count=scanned_file_count,
        total_image_count=total_image_count,
        scanned_image_count=valid_image_count,
    )
    progress.emit(
        stage="scan",
        current=scanned_file_count,
        total=total_image_count,
        message=(
            f"Đang scan ảnh {scanned_file_count}/{total_image_count}; "
            f"đã nhận {valid_image_count} ảnh GeoTIFF hợp lệ."
        ),
    )


def _emit_live_target_match_progress(
    progress: _ProgressBuilder,
    *,
    processed_target_count: int,
    total_target_count: int,
    target: TargetConfig,
    target_match_count: int,
) -> None:
    progress.update(
        processed_target_count=processed_target_count,
        total_target_count=total_target_count,
    )
    progress.emit(
        stage="match",
        current=processed_target_count,
        total=total_target_count,
        message=f"Đang scan target `{target.name}`; đã lấy {target_match_count} ảnh.",
        current_target=target,
        current_target_matched_count=target_match_count,
    )


def _finish_with_cancelled(
    progress: _ProgressBuilder,
    *,
    job_id: str,
) -> IngestionJobResult:
    progress.emit(
        stage="cancelled",
        state=JobState.CANCELLED,
        message="Đã dừng lấy dữ liệu.",
    )
    return IngestionJobResult(
        job_id=job_id,
        state=JobState.CANCELLED,
        issues=list(progress.issues or []),
        scanned_image_count=progress.scanned_image_count,
        matched_image_count=progress.matched_image_count,
        targets_with_images_count=progress.targets_with_images_count,
        composition_ids=[],
        historical_loading_enabled=False,
    )


def _finish_with_error(
    progress: _ProgressBuilder,
    *,
    job_id: str,
    issues: list[Issue],
    message: str,
) -> IngestionJobResult:
    progress.update(issues=issues)
    progress.emit(stage="error", state=JobState.ERROR, message=message)
    return IngestionJobResult(
        job_id=job_id,
        state=JobState.ERROR,
        issues=issues,
        scanned_image_count=progress.scanned_image_count,
        matched_image_count=progress.matched_image_count,
        targets_with_images_count=progress.targets_with_images_count,
        composition_ids=[],
        historical_loading_enabled=False,
    )


def _historical_loading_enabled(config_result: ConfigLoadResult) -> bool:
    return bool(
        config_result.config is not None
        and config_result.config.historical_loading.enabled
    )


def _default_historical_loader(
    plan: HistoricalLoadingPlan,
) -> HistoricalLoader | None:
    if plan.database_path is None:
        return None
    return HistoryService(plan.database_path).load_historical_images


def _historical_cache_inputs(
    records: list[HistoricalImageRecord],
) -> list[CacheImageInput]:
    return [
        CacheImageInput(
            target_id=record.target_id,
            source_path=record.source_path,
            layer=ImageLayer(
                layer_id=_historical_layer_id(record),
                source_path=str(record.source_path),
                cache_path=record.cache_path,
                order=0,
                capture_date=record.capture_date,
                capture_time=record.capture_time,
                cloud_percent=record.cloud_percent,
                metadata_status=(
                    MetadataStatus.VALID
                    if record.capture_date is not None and record.capture_time is not None
                    else MetadataStatus.NEEDS_MANUAL_CORRECTION
                ),
                metadata_source=MetadataSource.UNKNOWN,
                source_kind=ImageLayerSourceKind.HISTORICAL,
            ),
        )
        for record in records
    ]


def _historical_layer_id(record: HistoricalImageRecord) -> str:
    identity = "|".join(
        (
            record.target_id,
            str(record.source_path),
            record.capture_date.isoformat() if record.capture_date else "",
            record.capture_time.isoformat() if record.capture_time else "",
        )
    )
    identity_hash = sha1(identity.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"history__{identity_hash}"


def _historical_loading_setup_issue(config_result: ConfigLoadResult) -> Issue | None:
    if not _historical_loading_enabled(config_result):
        return None
    if any(
        issue.issue_id == "historical_loading.database_path_missing"
        for issue in config_result.issues
    ):
        return None

    config = config_result.config
    if config is None:
        return None
    if config.historical_registry.enabled and _historical_database_path(config_result):
        return None
    return _historical_database_path_missing_issue()


def _build_historical_loading_plan(
    config_result: ConfigLoadResult,
    matching_result: TargetMatchingResult,
) -> HistoricalLoadingPlan:
    if not _historical_loading_enabled(config_result) or config_result.config is None:
        return HistoricalLoadingPlan.disabled()

    loading = config_result.config.historical_loading
    database_path = _historical_database_path(config_result)
    target_ids = _historical_target_ids(config_result, matching_result)
    return HistoricalLoadingPlan(
        enabled=True,
        database_path=database_path,
        target_ids=target_ids,
        target_scope=loading.target_scope,
        image_selection=loading.image_selection,
        current_session_latest_capture_date=_current_session_latest_capture_date(
            matching_result
        ),
    )


def _historical_database_path(config_result: ConfigLoadResult) -> Path | None:
    if config_result.historical_database_path is not None:
        return config_result.historical_database_path
    if config_result.config is None:
        return None
    database_path = config_result.config.historical_registry.database_path
    if not database_path:
        return None
    return resolve_config_asset_path(config_result.config_path, database_path)


def _historical_target_ids(
    config_result: ConfigLoadResult,
    matching_result: TargetMatchingResult,
) -> tuple[str, ...]:
    if config_result.config is None:
        return ()
    scope = config_result.config.historical_loading.target_scope
    if scope == HistoricalLoadingTargetScope.ALL_ENABLED_TARGETS:
        return tuple(target.id for target in config_result.enabled_targets)
    return tuple(
        target.id
        for target in config_result.enabled_targets
        if matching_result.matches.get(target.id)
    )


def _current_session_latest_capture_date(
    matching_result: TargetMatchingResult,
):
    capture_dates = [
        match.image.layer.capture_date
        for matches in matching_result.matches.values()
        for match in matches
        if match.image.layer.capture_date is not None
    ]
    if not capture_dates:
        return None
    return max(capture_dates)


def _historical_loading_message(plan: HistoricalLoadingPlan) -> str:
    target_scope = (
        plan.target_scope.value
        if isinstance(plan.target_scope, HistoricalLoadingTargetScope)
        else plan.target_scope
    )
    return (
        "Chế độ ảnh lịch sử: Tải ảnh lịch sử; "
        f"scope={target_scope}, selection={plan.image_selection.mode.value}, "
        f"targets={len(plan.target_ids)}."
    )


def _historical_database_path_missing_issue() -> Issue:
    return Issue(
        issue_id="historical_loading.database_path_missing",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.CONFIG,
        message=(
            "Đã bật tải ảnh lịch sử nhưng chưa cấu hình "
            "`historical_registry.enabled=true` và `historical_registry.database_path`."
        ),
        remediation=(
            "Tắt `historical_loading.enabled` để giữ workflow hiện tại, hoặc cấu hình "
            "`historical_registry.database_path` trỏ tới SQLite registry trước khi ingest."
        ),
    )


def _fatal_setup_issues(issues: list[Issue]) -> list[Issue]:
    fatal_scopes = {IssueScope.CONFIG, IssueScope.PROJECT, IssueScope.WORKSPACE}
    return [issue for issue in issues if issue.scope in fatal_scopes]


def _targets_by_id(targets: list[TargetConfig]) -> dict[str, TargetConfig]:
    return {target.id: target for target in targets}


def _completion_message(
    state: JobState,
    composition_result: CompositionCreationResult,
) -> str:
    created_count = len(composition_result.composition_ids)
    if state == JobState.WARNING:
        return f"Lấy dữ liệu hoàn tất với cảnh báo; đã tạo {created_count} composition."
    return f"Lấy dữ liệu hoàn tất; đã tạo {created_count} composition."


def _setup_error_issue(error: Exception) -> Issue:
    return Issue(
        issue_id="ingestion.setup_failed",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.PROJECT,
        message=f"Không thể chuẩn bị dữ liệu đầu vào: {error}",
        remediation="Kiểm tra lại config, thư mục ảnh và workspace rồi chạy lại.",
    )


def _workspace_error_issue(error: Exception) -> Issue:
    return Issue(
        issue_id="ingestion.workspace_failed",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.WORKSPACE,
        message=f"Không thể ghi workspace trong quá trình lấy dữ liệu: {error}",
        remediation="Kiểm tra quyền ghi workspace và xác nhận xóa dữ liệu cũ nếu cần.",
    )
