"""Headless job progress contracts and stale-update filtering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from queue import Empty, SimpleQueue

from pydantic import BaseModel, ConfigDict, Field

from thucthengay.models import Issue


class JobState(StrEnum):
    """Progress states shared by long-running app jobs."""

    IDLE = "idle"
    RUNNING = "running"
    CANCELLED = "cancelled"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ProgressEvent(BaseModel):
    """Typed progress update safe to pass from workers to a UI adapter."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    stage: str
    state: JobState = JobState.RUNNING
    current: int | None = None
    total: int | None = None
    message: str
    issues: list[Issue] = Field(default_factory=list)
    scanned_image_count: int = 0
    scanned_file_count: int = 0
    total_image_count: int = 0
    matched_image_count: int = 0
    downloaded_image_count: int = 0
    skipped_existing_count: int = 0
    skipped_cloud_count: int = 0
    failed_image_count: int = 0
    metadata_cache_hit_count: int = 0
    metadata_cache_miss_count: int = 0
    targets_with_images_count: int = 0
    processed_target_count: int = 0
    total_target_count: int = 0
    warning_count: int = 0
    current_target_id: str | None = None
    current_target_name: str | None = None
    current_target_matched_count: int = 0
    current_source_folder: str | None = None
    current_geojson: str | None = None
    current_match_context: str | None = None
    created_composition_count: int = 0
    prepared_raster_count: int = 0
    total_prepare_raster_count: int = 0

    @property
    def percent(self) -> int | None:
        """Return rounded percent when current/total are known."""
        if self.current is None or self.total in (None, 0):
            return None
        return max(0, min(100, round((self.current / self.total) * 100)))

    @property
    def terminal(self) -> bool:
        """Return true when the job has stopped emitting active progress."""
        return self.state in {
            JobState.CANCELLED,
            JobState.SUCCESS,
            JobState.WARNING,
            JobState.ERROR,
        }


class QueuedProgressDispatcher:
    """Thread-safe progress handoff that a Qt adapter can drain on the main thread."""

    def __init__(self) -> None:
        self._queue: SimpleQueue[ProgressEvent] = SimpleQueue()

    def publish(self, event: ProgressEvent) -> None:
        """Queue an event from any worker context without touching UI objects."""
        self._queue.put(event)

    def drain(self) -> list[ProgressEvent]:
        """Return all queued events for main-thread UI processing."""
        events: list[ProgressEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                return events


@dataclass
class ActiveJobProgressModel:
    """Main-thread state holder that ignores stale job updates."""

    active_job_id: str | None = None
    completed_job_id: str | None = None
    latest: ProgressEvent | None = None
    history: list[ProgressEvent] = field(default_factory=list)

    def start(self, job_id: str) -> None:
        """Mark a new job as active and clear completion from any previous job."""
        self.active_job_id = job_id
        self.completed_job_id = None

    def apply(self, event: ProgressEvent) -> bool:
        """Apply an event only if it belongs to the active job."""
        if event.job_id != self.active_job_id:
            return False

        self.latest = event
        self.history.append(event)
        if event.state in {JobState.SUCCESS, JobState.WARNING}:
            self.completed_job_id = event.job_id
            self.active_job_id = None
        elif event.state in {JobState.CANCELLED, JobState.ERROR}:
            self.completed_job_id = None
            self.active_job_id = None
        return True

    @property
    def complete(self) -> bool:
        """Return true only after the active job finished successfully or with warnings."""
        return self.completed_job_id is not None and self.active_job_id is None
