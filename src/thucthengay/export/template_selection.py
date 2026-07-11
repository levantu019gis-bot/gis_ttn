"""Select normal or temporal-compare PPTX template metadata."""

from __future__ import annotations

from pydantic import ValidationError

from thucthengay.models import Composition, TargetConfig, TemplateMetadata

TEMPLATE_METADATA_KEY = "template_metadata"
COMPARE_TEMPLATE_METADATA_KEY = "compare_template_metadata"


def template_metadata_for_composition(
    target: TargetConfig,
    composition: Composition,
) -> TemplateMetadata:
    """Return template metadata matching the composition export mode."""
    key = template_metadata_key_for_composition(target, composition)
    try:
        return TemplateMetadata.model_validate(target.metadata[key])
    except (KeyError, ValidationError) as error:
        msg = f"target is missing derived {key}"
        raise ValueError(msg) from error


def template_metadata_key_for_composition(
    target: TargetConfig,
    composition: Composition,
) -> str:
    """Return the metadata key used for a composition's PPTX template."""
    if (
        composition.temporal_compare.enabled
        and target.export.compare_template_pptx_file
        and COMPARE_TEMPLATE_METADATA_KEY in target.metadata
    ):
        return COMPARE_TEMPLATE_METADATA_KEY
    return TEMPLATE_METADATA_KEY


def template_pptx_file_for_composition(
    target: TargetConfig,
    composition: Composition,
) -> str:
    """Return the configured PPTX path for a composition's export mode."""
    if composition.temporal_compare.enabled and target.export.compare_template_pptx_file:
        return target.export.compare_template_pptx_file
    return target.export.template_pptx_file
