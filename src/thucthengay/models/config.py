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


class GridDefaultsConfig(BaseModel):
    """Project-level defaults shared by target grid settings."""

    model_config = ConfigDict(extra="forbid")

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
        return _normalize_hex_rgb(value, field_name="map_background_color")

    @property
    def template_metadata_file(self) -> str:
        """Backward-compatible access during the Epic 6 migration."""
        return self.template_pptx_file

    @property
    def template_txt_value(self) -> str | None:
        """Config-contract alias for TXT export content."""
        return self.txt_line_template


class ExportDefaultsConfig(BaseModel):
    """Project-level defaults shared by target export settings."""

    model_config = ConfigDict(extra="forbid")

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
        return _normalize_hex_rgb(value, field_name="map_background_color")


class ProjectDefaultsConfig(BaseModel):
    """Project-level target defaults."""

    model_config = ConfigDict(extra="forbid")

    grid: GridDefaultsConfig = Field(default_factory=GridDefaultsConfig)
    export: ExportDefaultsConfig = Field(default_factory=ExportDefaultsConfig)


class TargetGroupConfig(BaseModel):
    """Business grouping metadata for a reporting target."""

    model_config = ConfigDict(extra="forbid")

    key: str | int | float
    title: str


class TargetConfig(BaseModel):
    """Configured reporting target."""

    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: bool = True
    group: TargetGroupConfig | None = None
    sort_order: int = 0
    name: str
    alias: str | None = None
    title: str | None = None
    geojson_file: str | None = None
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


def target_group_order_key(target: TargetConfig) -> tuple[int, tuple[int, ...], str]:
    """Return the primary ordering key for a target group."""
    group = target.group
    if group is None:
        return (1, (10_000,), "")

    group_key = str(group.key)
    if group_key in {"0", "0.0"}:
        return (1, (10_000,), group_key)
    return (0, _dotted_numeric_key(group_key), group_key)


def target_order_key(target: TargetConfig) -> tuple[int, tuple[int, ...], str, int, str]:
    """Return target ordering by group first, then order within that group."""
    group_bucket, group_key, group_text = target_group_order_key(target)
    return (group_bucket, group_key, group_text, target.sort_order, target.id)


def _dotted_numeric_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in value.split("."):
        if not part.isdigit():
            return (9_999, *[ord(char) for char in value])
        parts.append(int(part))
    return tuple(parts)


class ProjectConfig(BaseModel):
    """Root project configuration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    defaults: ProjectDefaultsConfig = Field(default_factory=ProjectDefaultsConfig)
    filename_patterns: list[FilenamePatternConfig] = Field(default_factory=list)
    targets: list[TargetConfig]

    @model_validator(mode="before")
    @classmethod
    def apply_project_defaults_to_targets(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        defaults = data.get("defaults")
        targets = data.get("targets")
        if not isinstance(defaults, dict) or not isinstance(targets, list):
            return data

        grid_defaults = defaults.get("grid")
        export_defaults = defaults.get("export")
        if not isinstance(grid_defaults, dict) and not isinstance(export_defaults, dict):
            return data

        normalized = dict(data)
        normalized["targets"] = [
            _target_with_project_defaults(
                target,
                grid_defaults=grid_defaults if isinstance(grid_defaults, dict) else {},
                export_defaults=export_defaults if isinstance(export_defaults, dict) else {},
            )
            for target in targets
        ]
        return normalized


def _target_with_project_defaults(
    target: object,
    *,
    grid_defaults: dict[str, Any],
    export_defaults: dict[str, Any],
) -> object:
    if not isinstance(target, dict):
        return target

    normalized = dict(target)
    grid = normalized.get("grid")
    if isinstance(grid, dict) and grid_defaults:
        normalized["grid"] = _grid_with_project_defaults(grid, grid_defaults)

    export = normalized.get("export")
    if isinstance(export, dict) and export_defaults:
        normalized["export"] = _export_with_project_defaults(export, export_defaults)

    return normalized


def _grid_with_project_defaults(
    grid: dict[str, Any],
    grid_defaults: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(grid)
    if "label_format" not in normalized and "label_format" in grid_defaults:
        normalized["label_format"] = grid_defaults["label_format"]

    default_style = grid_defaults.get("style")
    target_style = normalized.get("style")
    if isinstance(default_style, dict):
        merged_style = dict(default_style)
        if isinstance(target_style, dict):
            merged_style.update(target_style)
        normalized["style"] = merged_style

    return normalized


def _export_with_project_defaults(
    export: dict[str, Any],
    export_defaults: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(export)
    for field_name in ("date_format", "time_format", "map_background_color"):
        if field_name not in normalized and field_name in export_defaults:
            normalized[field_name] = export_defaults[field_name]
    return normalized


def _normalize_hex_rgb(value: str, *, field_name: str) -> str:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        msg = f"{field_name} must use #RRGGBB"
        raise ValueError(msg)
    try:
        int(text, 16)
    except ValueError as exc:
        msg = f"{field_name} must use #RRGGBB"
        raise ValueError(msg) from exc
    return f"#{text.upper()}"
