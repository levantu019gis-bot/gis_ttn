"""Workspace manifest models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceReviewSessionState(BaseModel):
    """Last Review/Edit UI position that is safe to restore after reopening."""

    model_config = ConfigDict(extra="forbid")

    selected_composition_id: str | None = None
    selected_layer_id: str | None = None
    active_queue_filter: str = "all"


class WorkspaceSessionState(BaseModel):
    """Workspace-local UI session state kept separate from business data."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    review: WorkspaceReviewSessionState = Field(default_factory=WorkspaceReviewSessionState)
    updated_at: datetime | None = None


class WorkspaceManifest(BaseModel):
    """Top-level workspace manifest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    config_path: str
    imagery_input_path: str | None = None
    composition_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
