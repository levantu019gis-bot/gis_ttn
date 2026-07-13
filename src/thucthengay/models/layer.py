"""Image layer models."""

from __future__ import annotations

from datetime import date, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class LayerRenderBands(BaseModel):
    """Manual raster band selection used when drawing a layer as RGB."""

    model_config = ConfigDict(extra="forbid")

    red: int = Field(ge=1)
    green: int = Field(ge=1)
    blue: int = Field(ge=1)
    alpha: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def alpha_must_not_duplicate_rgb(self) -> LayerRenderBands:
        if self.alpha is not None and self.alpha in {self.red, self.green, self.blue}:
            msg = "alpha band must be different from red/green/blue bands"
            raise ValueError(msg)
        return self

    def signature(self) -> tuple[int, int, int, int | None]:
        return (self.red, self.green, self.blue, self.alpha)


class LayerSymbology(BaseModel):
    """Display stretch/gamma settings used when drawing raster pixels."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    stretch_mode: Literal["none", "dtype", "min_max", "percent_clip", "stddev", "manual"] = (
        "percent_clip"
    )
    lower_percentile: float = Field(default=2.0, ge=0.0, le=100.0)
    upper_percentile: float = Field(default=98.0, ge=0.0, le=100.0)
    stddev_factor: float = Field(default=2.0, gt=0.0)
    manual_min: list[float] | None = None
    manual_max: list[float] | None = None
    gamma: float = Field(default=1.0, gt=0.0)
    brightness: float = Field(default=0.0, ge=-255.0, le=255.0)
    contrast: float = Field(default=1.0, ge=0.0, le=10.0)
    per_channel: bool = True
    nodata_transparent: bool = True

    @field_validator("manual_min", "manual_max")
    @classmethod
    def manual_values_must_be_short_numeric_lists(
        cls, value: list[float] | None
    ) -> list[float] | None:
        if value is None:
            return value
        if not 1 <= len(value) <= 3:
            msg = "manual stretch values must contain 1 to 3 numbers"
            raise ValueError(msg)
        return [float(item) for item in value]

    @model_validator(mode="after")
    def validate_ranges(self) -> LayerSymbology:
        if self.lower_percentile >= self.upper_percentile:
            msg = "lower_percentile must be smaller than upper_percentile"
            raise ValueError(msg)
        if self.stretch_mode == "manual":
            if self.manual_min is None or self.manual_max is None:
                msg = "manual stretch requires manual_min and manual_max"
                raise ValueError(msg)
            if len(self.manual_min) not in {1, len(self.manual_max)} and len(self.manual_max) != 1:
                msg = "manual_min/manual_max must have matching lengths or a single shared value"
                raise ValueError(msg)
            for low, high in zip(
                _expand_manual_values(self.manual_min, 3),
                _expand_manual_values(self.manual_max, 3),
                strict=True,
            ):
                if low >= high:
                    msg = "manual_min values must be smaller than manual_max values"
                    raise ValueError(msg)
        return self

    def signature(self) -> tuple[object, ...]:
        return (
            self.enabled,
            self.stretch_mode,
            self.lower_percentile,
            self.upper_percentile,
            self.stddev_factor,
            tuple(self.manual_min or ()),
            tuple(self.manual_max or ()),
            self.gamma,
            self.brightness,
            self.contrast,
            self.per_channel,
            self.nodata_transparent,
        )


def _expand_manual_values(values: list[float], count: int) -> list[float]:
    if len(values) == 1:
        return [values[0]] * count
    if len(values) >= count:
        return values[:count]
    return [*values, *([values[-1]] * (count - len(values)))]


class ImageLayer(BaseModel):
    """GeoTIFF layer included in a target-date composition."""

    model_config = ConfigDict(extra="forbid")

    layer_id: str
    source_path: str
    cache_path: str | None = None
    prepared_path: str | None = None
    visible: bool = True
    order: int = Field(ge=0)
    capture_date: date | None = None
    capture_time: time | None = None
    cloud_percent: float | None = Field(default=None, ge=0, le=100)
    metadata_status: MetadataStatus = MetadataStatus.UNKNOWN
    metadata_source: MetadataSource = MetadataSource.UNKNOWN
    source_kind: ImageLayerSourceKind = ImageLayerSourceKind.CURRENT
    image_asset_id: int | None = Field(default=None, ge=1)
    render_bands: LayerRenderBands | None = None
    symbology: LayerSymbology | None = None
    footprint_center: list[float] | None = None

    @field_validator("footprint_center")
    @classmethod
    def footprint_center_must_be_lon_lat(
        cls,
        value: list[float] | None,
    ) -> list[float] | None:
        if value is None:
            return value
        if len(value) != 2:
            msg = "footprint_center must contain exactly [lon, lat]"
            raise ValueError(msg)
        lon, lat = value
        if not -180 <= lon <= 180:
            msg = "footprint_center longitude must be between -180 and 180"
            raise ValueError(msg)
        if not -90 <= lat <= 90:
            msg = "footprint_center latitude must be between -90 and 90"
            raise ValueError(msg)
        return value
