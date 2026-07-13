"""Project configuration models."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from thucthengay.models.template import TemplatePlaceholder
from thucthengay.utils.path_safety import validate_windows_safe_filename_component


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
    split: list[str] = Field(default_factory=lambda: ["_"])
    separator: str | None = Field(default=None, exclude=True)

    @field_validator("split")
    @classmethod
    def split_chars_must_be_single_characters(cls, value: list[str]) -> list[str]:
        if not value:
            msg = "split must contain at least one separator character"
            raise ValueError(msg)
        normalized: list[str] = []
        for item in value:
            if len(item) != 1:
                msg = "each split entry must be exactly one character"
                raise ValueError(msg)
            if item not in normalized:
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def pattern_must_have_extractable_token(self) -> FilenamePatternConfig:
        if self.separator is not None and self.split == ["_"]:
            self.split = [self.separator]
        extractable = {"yyyyMMdd", "HHmmss", "cloud-percent"}
        if not any(marker in self.pattern for marker in extractable):
            msg = (
                "pattern must contain at least one extractable token"
                " (yyyyMMdd, HHmmss, cloud-percent)"
            )
            raise ValueError(msg)
        return self


class TargetExportConfig(BaseModel):
    """Target-specific export references."""

    model_config = ConfigDict(extra="forbid")

    template_pptx_file: str = Field(
        validation_alias=AliasChoices("template_pptx_file", "template_metadata_file")
    )
    compare_template_pptx_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "compare_template_pptx_file",
            "template_pptx_file_compare",
            "temporal_compare_template_pptx_file",
        ),
    )
    placeholders: list[TemplatePlaceholder] = Field(default_factory=list)
    compare_placeholders: list[TemplatePlaceholder] | None = None
    txt_line_template: str | None = Field(
        default=None,
        validation_alias=AliasChoices("txt_line_template", "template_txt_value"),
        serialization_alias="template_txt_value",
    )
    date_format: str = "yyyy-MM-dd"
    time_format: str = "HH:mm:ss"
    final_render_dpi: int = Field(default=200, ge=1, le=1200)
    map_background_color: str = Field(
        default="#FFFFFF",
        validation_alias=AliasChoices(
            "map_background_color",
            "background_color",
            "map_background",
        ),
    )
    managed_source_root: str | None = None

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
    def compare_template_metadata_file(self) -> str | None:
        """Backward-compatible-style access for temporal compare PPTX templates."""
        return self.compare_template_pptx_file

    @property
    def template_txt_value(self) -> str | None:
        """Config-contract alias for TXT export content."""
        return self.txt_line_template


class ExportDefaultsConfig(BaseModel):
    """Project-level defaults shared by target export settings."""

    model_config = ConfigDict(extra="forbid")

    date_format: str = "yyyy-MM-dd"
    time_format: str = "HH:mm:ss"
    final_render_dpi: int = Field(default=200, ge=1, le=1200)
    map_background_color: str = Field(
        default="#FFFFFF",
        validation_alias=AliasChoices(
            "map_background_color",
            "background_color",
            "map_background",
        ),
    )
    managed_source_root: str | None = None

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


class TilePreviewConfig(BaseModel):
    """Project-level controls for the Review/Edit tile preview pipeline."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_cache_bytes: int = Field(default=512 * 1024 * 1024, ge=0)
    max_decode_workers: int | Literal["auto"] = Field(default=1)
    tile_grid_mode: Literal["fixed_geo", "adaptive_screen"] = "fixed_geo"
    tile_pixels: int = Field(default=256, ge=1, le=2048)
    adaptive_tile_screen_pixels: int | None = Field(default=None, ge=64, le=4096)
    tile_width_degrees: float = Field(default=0.05, gt=0)
    tile_height_degrees: float = Field(default=0.05, gt=0)
    partial_repaint_threshold_px: int = Field(default=96, ge=0)
    progress_frame_interval_ms: int = Field(default=66, ge=0)
    progress_tile_batch_size: int = Field(default=4, ge=1)
    interaction_render_debounce_ms: int = Field(default=250, ge=0)
    live_preview_max_fps: int = Field(default=30, ge=1, le=120)
    cancel_on_interaction: bool = True
    tile_decode_timeout_ms: int = Field(default=0, ge=0)
    fallback_to_full_render: bool = True

    @field_validator("max_decode_workers")
    @classmethod
    def max_decode_workers_must_be_auto_or_positive(
        cls,
        value: int | str,
    ) -> int | Literal["auto"]:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "auto":
                return "auto"
            msg = "max_decode_workers must be a positive integer or 'auto'"
            raise ValueError(msg)
        if value < 1:
            msg = "max_decode_workers must be greater than or equal to 1"
            raise ValueError(msg)
        return min(int(value), 16)


class RenderPreviewConfig(BaseModel):
    """Project-level Review/Edit preview rendering settings."""

    model_config = ConfigDict(extra="forbid")

    tile_preview: TilePreviewConfig = Field(default_factory=TilePreviewConfig)
    diagnostics_enabled: bool = False
    prepared_raster_root: str | None = None
    auto_prefer_prepared_rasters: bool = True
    auto_prepare_min_size_mb: float | None = Field(default=None, gt=0)


class ProjectDefaultsConfig(BaseModel):
    """Project-level target defaults."""

    model_config = ConfigDict(extra="forbid")

    grid: GridDefaultsConfig = Field(default_factory=GridDefaultsConfig)
    export: ExportDefaultsConfig = Field(default_factory=ExportDefaultsConfig)
    render_preview: RenderPreviewConfig = Field(default_factory=RenderPreviewConfig)


class HistoricalRegistryConfig(BaseModel):
    """Optional SQLite registry used by Epic 9 historical imagery features."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    database_path: str | None = None

    @model_validator(mode="after")
    def enabled_registry_requires_database_path(self) -> HistoricalRegistryConfig:
        if self.enabled and not self.database_path:
            msg = "historical registry database_path is required when enabled"
            raise ValueError(msg)
        return self


class HistoricalLoadingTargetScope(StrEnum):
    """Targets considered when seeding a workspace from historical imagery."""

    TARGETS_WITH_CURRENT_MATCHES = "targets_with_current_matches"
    ALL_ENABLED_TARGETS = "all_enabled_targets"


class HistoricalSelectionMode(StrEnum):
    """Historical image selection strategy used during ingestion."""

    LATEST_DATE = "latest_date"
    LATEST_IMAGES = "latest_images"
    DATE_RANGE = "date_range"
    LOOKBACK_DAYS = "lookback_days"


class HistoricalLookbackAnchor(StrEnum):
    """Anchor date used for historical lookback windows."""

    TODAY = "today"
    CURRENT_SESSION_LATEST_DATE = "current_session_latest_date"


class HistoricalImageSelectionConfig(BaseModel):
    """Configurable historical image selector for future registry queries."""

    model_config = ConfigDict(extra="forbid")

    mode: HistoricalSelectionMode = HistoricalSelectionMode.LATEST_DATE
    limit_per_target: int | None = Field(default=None, ge=1)
    start_date: date | None = None
    end_date: date | None = None
    lookback_days: int | None = Field(default=None, ge=1)
    lookback_anchor: HistoricalLookbackAnchor = (
        HistoricalLookbackAnchor.CURRENT_SESSION_LATEST_DATE
    )

    @model_validator(mode="after")
    def mode_specific_settings_must_be_complete(
        self,
    ) -> HistoricalImageSelectionConfig:
        if self.mode == HistoricalSelectionMode.LATEST_IMAGES:
            if self.limit_per_target is None:
                msg = "limit_per_target is required when mode is latest_images"
                raise ValueError(msg)
        if self.mode == HistoricalSelectionMode.DATE_RANGE:
            if self.start_date is None or self.end_date is None:
                msg = "start_date and end_date are required when mode is date_range"
                raise ValueError(msg)
            if self.start_date > self.end_date:
                msg = "start_date must be before or equal to end_date"
                raise ValueError(msg)
        if (
            self.mode == HistoricalSelectionMode.LOOKBACK_DAYS
            and self.lookback_days is None
        ):
            msg = "lookback_days is required when mode is lookback_days"
            raise ValueError(msg)
        return self


class HistoricalLoadingConfig(BaseModel):
    """Explicit ingestion-time historical imagery loading mode."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    target_scope: HistoricalLoadingTargetScope = (
        HistoricalLoadingTargetScope.TARGETS_WITH_CURRENT_MATCHES
    )
    image_selection: HistoricalImageSelectionConfig = Field(
        default_factory=HistoricalImageSelectionConfig
    )


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

    @field_validator("id")
    @classmethod
    def id_must_be_portable_filename_component(cls, value: str) -> str:
        return validate_windows_safe_filename_component(value, field_name="target id")


class UnmatchedImagesViewConfig(BaseModel):
    """Default view settings for images outside configured target geometry."""

    model_config = ConfigDict(extra="forbid")

    center_mode: Literal["raster_center"] = "raster_center"
    scale: int = Field(default=50000, gt=0)


class UnmatchedImagesConfig(BaseModel):
    """Review/export defaults for images that do not intersect any configured target."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    review_group: TargetGroupConfig = Field(
        default_factory=lambda: TargetGroupConfig(key="999", title="Anh ngoai geometry")
    )
    target_id_prefix: Literal["__unmatched__"] = "__unmatched__"
    target_name: str = "Anh ngoai geometry"
    allow_include: bool = False
    allow_export: bool = False
    view: UnmatchedImagesViewConfig = Field(default_factory=UnmatchedImagesViewConfig)
    grid: GridConfig | None = None
    export: TargetExportConfig | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def export_requires_export_config(self) -> UnmatchedImagesConfig:
        if (self.allow_include or self.allow_export) and self.export is None:
            msg = "unmatched_images.export is required when allow_include or allow_export is true"
            raise ValueError(msg)
        return self


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
    historical_registry: HistoricalRegistryConfig = Field(
        default_factory=HistoricalRegistryConfig
    )
    historical_loading: HistoricalLoadingConfig = Field(
        default_factory=HistoricalLoadingConfig
    )
    unmatched_images: UnmatchedImagesConfig = Field(default_factory=UnmatchedImagesConfig)
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
        unmatched = normalized.get("unmatched_images")
        if isinstance(unmatched, dict):
            normalized["unmatched_images"] = _unmatched_with_project_defaults(
                unmatched,
                grid_defaults=grid_defaults if isinstance(grid_defaults, dict) else {},
                export_defaults=export_defaults if isinstance(export_defaults, dict) else {},
            )
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


def _unmatched_with_project_defaults(
    unmatched: dict[str, Any],
    *,
    grid_defaults: dict[str, Any],
    export_defaults: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(unmatched)
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
    for field_name in (
        "date_format",
        "time_format",
        "final_render_dpi",
        "map_background_color",
        "managed_source_root",
    ):
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
