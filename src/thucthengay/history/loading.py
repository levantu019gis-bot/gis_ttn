"""Historical imagery loading plan models for ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

from thucthengay.models import HistoricalImageSelectionConfig, Issue


@dataclass(frozen=True)
class HistoricalImageRecord:
    """One image selected from the registry for ingestion into a workspace."""

    image_asset_id: int
    target_id: str
    source_path: Path
    capture_date: date | None
    capture_time: time | None
    cloud_percent: float | None = None
    cache_path: str | None = None


@dataclass(frozen=True)
class HistoricalLoadingPlan:
    """Resolved ingestion-time instructions for future historical image queries."""

    enabled: bool
    database_path: Path | None = None
    target_ids: tuple[str, ...] = ()
    target_scope: str = "targets_with_current_matches"
    image_selection: HistoricalImageSelectionConfig = field(
        default_factory=HistoricalImageSelectionConfig
    )
    current_session_latest_capture_date: date | None = None

    @classmethod
    def disabled(cls) -> HistoricalLoadingPlan:
        """Return a no-query plan matching the current workspace-only workflow."""
        return cls(enabled=False)


@dataclass(frozen=True)
class HistoricalLoadingResult:
    """Result placeholder for historical loading integration in later stories."""

    loaded_image_count: int = 0
    skipped_image_count: int = 0
    records: list[HistoricalImageRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
