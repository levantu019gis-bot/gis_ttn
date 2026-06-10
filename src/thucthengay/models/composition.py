"""Composition state models."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from thucthengay.models.config import GridConfig
from thucthengay.models.layer import ImageLayer


class ViewState(BaseModel):
    """Source-of-truth map view state for preview and final render."""

    model_config = ConfigDict(extra="forbid")

    center: list[float]
    scale: int = Field(gt=0)
    rotation: int = Field(default=0, ge=0, le=0)

    @field_validator("center")
    @classmethod
    def center_must_be_lon_lat(cls, value: list[float]) -> list[float]:
        if len(value) != 2:
            msg = "center must contain exactly [lon, lat]"
            raise ValueError(msg)
        lon, lat = value
        if not -180 <= lon <= 180:
            msg = "center longitude must be between -180 and 180"
            raise ValueError(msg)
        if not -90 <= lat <= 90:
            msg = "center latitude must be between -90 and 90"
            raise ValueError(msg)
        return value


class ValidationSummary(BaseModel):
    """Compact persisted validation state."""

    model_config = ConfigDict(extra="forbid")

    last_validated_at: datetime | None = None
    info_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)


class PersistedValidationState(StrEnum):
    """Status UI/export code can infer from persisted summary plus stale flag."""

    CLEAN = "clean"
    WARNING = "warning"
    ERROR = "error"
    STALE = "stale"


class TemporalCompareOrientation(StrEnum):
    """Split orientation for a two-time comparison map frame."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class TemporalCompareState(BaseModel):
    """Persisted temporal comparison selections for one composition."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    orientation: TemporalCompareOrientation = TemporalCompareOrientation.VERTICAL
    pane_a_composition_id: str | None = None
    pane_b_composition_id: str | None = None
    pane_a_layer_id: str | None = None
    pane_b_layer_id: str | None = None


class CompositionArtifacts(BaseModel):
    """Workspace-relative artifacts generated for a composition."""

    model_config = ConfigDict(extra="forbid")

    preview_render_path: str | None = None
    final_render_path: str | None = None
    render_log_path: str | None = None
    export_log_path: str | None = None


class Composition(BaseModel):
    """Review/edit state for one target-date slide candidate."""

    model_config = ConfigDict(extra="forbid")

    composition_id: str
    target_id: str
    capture_date: date
    layers: list[ImageLayer] = Field(default_factory=list)
    view: ViewState
    grid_override: GridConfig | None = None
    reviewed: bool = False
    ready: bool = False
    include: bool = False
    needs_revalidation: bool = True
    review_order: int | None = Field(default=None, ge=1)
    notes: str = ""
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    artifacts: CompositionArtifacts = Field(default_factory=CompositionArtifacts)
    temporal_compare: TemporalCompareState = Field(default_factory=TemporalCompareState)

    @property
    def persisted_validation_state(self) -> PersistedValidationState:
        """Return displayable validation state without recomputing detailed issues."""
        if self.needs_revalidation:
            return PersistedValidationState.STALE
        if self.validation_summary.error_count > 0:
            return PersistedValidationState.ERROR
        if self.validation_summary.warning_count > 0:
            return PersistedValidationState.WARNING
        return PersistedValidationState.CLEAN
