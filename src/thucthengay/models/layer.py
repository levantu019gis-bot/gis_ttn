"""Image layer models."""

from __future__ import annotations

from datetime import date, time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MetadataStatus(StrEnum):
    """Current trust state for layer business metadata."""

    UNKNOWN = "unknown"
    VALID = "valid"
    NEEDS_CORRECTION = "needs_correction"
    NEEDS_MANUAL_CORRECTION = "needs_manual_correction"


class MetadataSource(StrEnum):
    """Where layer metadata came from."""

    UNKNOWN = "unknown"
    FILENAME = "filename"
    SIDECAR = "sidecar"
    EMBEDDED = "embedded"
    MANUAL = "manual"


class ImageLayerSourceKind(StrEnum):
    """Whether a layer comes from the current ingestion run or historical registry."""

    CURRENT = "current"
    HISTORICAL = "historical"


class ImageLayer(BaseModel):
    """GeoTIFF layer included in a target-date composition."""

    model_config = ConfigDict(extra="forbid")

    layer_id: str
    source_path: str
    cache_path: str | None = None
    visible: bool = True
    order: int = Field(ge=0)
    capture_date: date | None = None
    capture_time: time | None = None
    cloud_percent: float | None = Field(default=None, ge=0, le=100)
    metadata_status: MetadataStatus = MetadataStatus.UNKNOWN
    metadata_source: MetadataSource = MetadataSource.UNKNOWN
    source_kind: ImageLayerSourceKind = ImageLayerSourceKind.CURRENT
    image_asset_id: int | None = Field(default=None, ge=1)
