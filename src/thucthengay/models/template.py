"""PowerPoint template metadata models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class PlaceholderType(StrEnum):
    """Supported template placeholder roles."""

    MAP_IMAGE = "map_image"
    TEXT = "text"
    IMAGE = "image"


class MapFrame(BaseModel):
    """Map image rectangle in template coordinate units."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class TemplatePlaceholderSelector(BaseModel):
    """Stable PPTX shape selector used to repair volatile element ids."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    title: str | None = None
    descr: str | None = None
    alt_text: str | None = Field(
        default=None,
        validation_alias=AliasChoices("alt_text", "description"),
    )
    text: str | None = None

    @model_validator(mode="after")
    def selector_must_have_signal(self) -> TemplatePlaceholderSelector:
        if any((self.name, self.title, self.descr, self.alt_text, self.text)):
            return self
        msg = "selector must contain at least one matching signal"
        raise ValueError(msg)


class TemplatePlaceholder(BaseModel):
    """Placeholder mapping in a target-specific PPTX template."""

    model_config = ConfigDict(extra="forbid")

    field: str
    element_id: int | None = Field(default=None, gt=0)
    kind: PlaceholderType
    value: str | None = None
    selector: TemplatePlaceholderSelector | None = None
    diagnostic_name: str | None = None
    required: bool = True

    @model_validator(mode="before")
    @classmethod
    def default_kind_from_field(cls, data: object) -> object:
        if not isinstance(data, dict) or data.get("kind"):
            return data
        updated = dict(data)
        updated["kind"] = (
            PlaceholderType.MAP_IMAGE
            if updated.get("field") == "map_image"
            else PlaceholderType.TEXT
        )
        return updated


class TemplateMetadata(BaseModel):
    """Metadata file consumed by export and validation services."""

    model_config = ConfigDict(extra="forbid")

    template_pptx: str
    slide_index: int = Field(ge=0)
    map_frame: MapFrame
    placeholders: list[TemplatePlaceholder] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
