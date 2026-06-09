"""Ingestion summary models for post-run UI and review handoff."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from thucthengay.jobs.ingestion_job import IngestionJobResult
from thucthengay.jobs.progress import JobState
from thucthengay.models import Issue, IssueScope

NO_MATCH_EMPTY_STATE_MESSAGE = (
    "Không có ảnh nào khớp với target đang bật. Hãy kiểm tra thư mục ảnh đầu vào, "
    "target có đang bị tắt không, footprint GeoTIFF có hợp lệ không, và ảnh có giao "
    "với boundary target hay không."
)
NO_HISTORICAL_EMPTY_STATE_MESSAGE = (
    "Đã bật tải ảnh lịch sử nhưng không có ảnh lịch sử nào khớp với target scope "
    "và image selection hiện tại."
)


class IngestionWarningItem(BaseModel):
    """Display-ready warning or error row derived from an ingestion issue."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    severity: str
    scope: IssueScope
    affected_object: str | None = None
    target_id: str | None = None
    composition_id: str | None = None
    layer_id: str | None = None
    message: str
    remediation: str | None = None
    review_surfaceable: bool = False

    @classmethod
    def from_issue(cls, issue: Issue) -> IngestionWarningItem:
        """Create a UI warning row while preserving issue identity."""
        return cls(
            issue_id=issue.issue_id,
            severity=str(issue.severity),
            scope=issue.scope,
            affected_object=_affected_object(issue),
            target_id=issue.target_id,
            composition_id=issue.composition_id,
            layer_id=issue.layer_id,
            message=issue.message,
            remediation=issue.remediation,
            review_surfaceable=bool(issue.composition_id or issue.layer_id),
        )


class IngestionSummary(BaseModel):
    """Stable summary shown after an ingestion job finishes."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    state: JobState
    scanned_image_count: int = 0
    matched_image_count: int = 0
    targets_with_images_count: int = 0
    created_composition_count: int = 0
    warning_count: int = 0
    historical_loading_enabled: bool = False
    historical_loaded_image_count: int = 0
    historical_skipped_image_count: int = 0
    historical_path_issue_count: int = 0
    workspace_path: str
    composition_ids: list[str] = Field(default_factory=list)
    warnings: list[IngestionWarningItem] = Field(default_factory=list)
    empty_state_message: str | None = None
    historical_empty_message: str | None = None

    @classmethod
    def from_job_result(
        cls,
        result: IngestionJobResult,
        *,
        workspace_path: str | Path,
    ) -> IngestionSummary:
        """Build a summary model from a completed ingestion job."""
        warnings = [IngestionWarningItem.from_issue(issue) for issue in result.issues]
        empty_state_message = (
            NO_MATCH_EMPTY_STATE_MESSAGE
            if result.state in {JobState.SUCCESS, JobState.WARNING}
            and result.matched_image_count == 0
            else None
        )
        historical_path_issue_count = sum(
            1 for issue in result.issues if issue.issue_id.startswith("historical.")
        )
        historical_empty_message = (
            NO_HISTORICAL_EMPTY_STATE_MESSAGE
            if result.state in {JobState.SUCCESS, JobState.WARNING}
            and result.historical_loading_enabled
            and result.historical_loaded_image_count == 0
            and result.historical_skipped_image_count == 0
            else None
        )
        return cls(
            job_id=result.job_id,
            state=result.state,
            scanned_image_count=result.scanned_image_count,
            matched_image_count=result.matched_image_count,
            targets_with_images_count=result.targets_with_images_count,
            created_composition_count=len(result.composition_ids),
            warning_count=len(warnings),
            historical_loading_enabled=result.historical_loading_enabled,
            historical_loaded_image_count=result.historical_loaded_image_count,
            historical_skipped_image_count=result.historical_skipped_image_count,
            historical_path_issue_count=historical_path_issue_count,
            workspace_path=str(Path(workspace_path).expanduser().resolve()),
            composition_ids=list(result.composition_ids),
            warnings=warnings,
            empty_state_message=empty_state_message,
            historical_empty_message=historical_empty_message,
        )

    @property
    def hard_failure(self) -> bool:
        """Return true for jobs that failed before producing usable workspace output."""
        return self.state in {JobState.CANCELLED, JobState.ERROR}

    @property
    def success_with_warnings(self) -> bool:
        """Return true when ingestion completed but needs operator attention."""
        return self.state == JobState.WARNING

    @property
    def empty(self) -> bool:
        """Return true when no imagery matched any enabled target."""
        return self.empty_state_message is not None


def _affected_object(issue: Issue) -> str | None:
    if issue.composition_id:
        return issue.composition_id
    if issue.layer_id:
        return issue.layer_id
    if issue.target_id:
        return issue.target_id
    if issue.scope:
        return str(issue.scope)
    return None
