"""Project configuration models."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from thucthengay.models.template import TemplatePlaceholder


class GridInterval(BaseModel):
    """DMS-compatible grid interval."""

    model_config = ConfigDict(extra="forbid")

    degrees: int = Field(default=0, ge=0)
    minutes: int = Field(default=0, ge=0, lt=60)
    seconds: float = Field(default=0, ge=0, lt=60)

    @model_validator(mode="after")
    def interval_must_be_positive(self) -> GridInterval:
        if self.degrees == 0 and self.minutes == 0 and self.seconds == 0:
            msg = "grid interval must be greater than zero"
            raise ValueError(msg)
        return self


class GridConfig(BaseModel):
    """Target-level grid settings."""

    model_config = ConfigDict(extra="forbid")

    interval: GridInterval
    label_format: str = "dms_full"
    style: dict[str, Any] = Field(default_factory=dict)


class FilenamePatternConfig(BaseModel):
    """Configurable filename pattern for metadata extraction.

    Tokens separated by ``separator`` (default ``_``):
    - ``yyyyMMdd``      → capture date
    - ``HHmmss``        → capture time
    - ``cloud-percent`` → cloud cover percentage
    - ``*``             → wildcard (skip one segment)
    - anything else     → literal match
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    pattern: str
    separator: str = "_"

    @field_validator("pattern")
    @classmethod
    def pattern_must_have_extractable_token(cls, value: str) -> str:
        extractable = {"yyyyMMdd", "HHmmss", "cloud-percent"}
        tokens = value.split("_")
        if not any(token in extractable for token in tokens):
            msg = (
                "pattern must contain at least one extractable token"
                " (yyyyMMdd, HHmmss, cloud-percent)"
            )
            raise ValueError(msg)
        return value


class TargetExportConfig(BaseModel):
    """Target-specific export references."""

    model_config = ConfigDict(extra="forbid")

    template_pptx_file: str = Field(
        validation_alias=AliasChoices("template_pptx_file", "template_metadata_file")
    )
    placeholders: list[TemplatePlaceholder] = Field(default_factory=list)
    txt_line_template: str | None = Field(
        default=None,
        validation_alias=AliasChoices("txt_line_template", "template_txt_value"),
        serialization_alias="template_txt_value",
    )
    date_format: str = "yyyy-MM-dd"
    time_format: str = "HH:mm:ss"
    map_background_color: str = Field(
        default="#FFFFFF",
        validation_alias=AliasChoices(
            "map_background_color",
            "background_color",
            "map_background",
        ),
    )

    @field_validator("map_background_color", mode="before")
    @classmethod
    def map_background_color_from_string_or_object(cls, value: object) -> object:
        if isinstance(value, dict):
            return value.get("color") or value.get("background") or value.get("fill")
        return value

    @field_validator("map_background_color")
    @classmethod
    def map_background_color_must_be_hex_rgb(cls, value: str) -> str:
        text = value.strip().lstrip("#")
        if len(text) != 6:
            msg = "map_background_color must use #RRGGBB"
            raise ValueError(msg)
        try:
            int(text, 16)
        except ValueError as exc:
            msg = "map_background_color must use #RRGGBB"
            raise ValueError(msg) from exc
        return f"#{text.upper()}"

    @property
    def template_metadata_file(self) -> str:
        """Backward-compatible access during the Epic 6 migration."""
        return self.template_pptx_file

    @property
    def template_txt_value(self) -> str | None:
        """Config-contract alias for TXT export content."""
        return self.txt_line_template


class TargetConfig(BaseModel):
    """Configured reporting target."""

    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: bool = True
    sort_order: int = 0
    name: str
    alias: str | None = None
    title: str | None = None
    geojson_file: str
    coordinate: list[float]
    scale: int = Field(gt=0)
    grid: GridConfig
    export: TargetExportConfig
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("coordinate")
    @classmethod
    def coordinate_must_be_lon_lat(cls, value: list[float]) -> list[float]:
        if len(value) != 2:
            msg = "coordinate must contain exactly [lon, lat]"
            raise ValueError(msg)
        lon, lat = value
        if not -180 <= lon <= 180:
            msg = "longitude must be between -180 and 180"
            raise ValueError(msg)
        if not -90 <= lat <= 90:
            msg = "latitude must be between -90 and 90"
            raise ValueError(msg)
        return value


class ProjectConfig(BaseModel):
    """Root project configuration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    filename_patterns: list[FilenamePatternConfig] = Field(default_factory=list)
    targets: list[TargetConfig]
