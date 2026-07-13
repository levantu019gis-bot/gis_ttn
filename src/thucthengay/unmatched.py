"""Helpers for images outside configured target geometry."""

from __future__ import annotations

from collections.abc import Iterable

from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    TargetConfig,
    UnmatchedImagesConfig,
)

UNMATCHED_TARGET_ID_PREFIX = "__unmatched__"
UNMATCHED_METADATA_KIND = "unmatched_geometry"


def is_unmatched_target_id(target_id: str) -> bool:
    """Return true for generated target ids used by outside-geometry images."""
    return target_id.startswith(UNMATCHED_TARGET_ID_PREFIX)


def target_for_unmatched_composition(
    composition: Composition,
    config: UnmatchedImagesConfig,
) -> TargetConfig | None:
    """Build a transient target config for one outside-geometry composition."""
    if not config.enabled or not is_unmatched_target_id(composition.target_id):
        return None

    grid = config.grid or GridConfig(
        interval=GridInterval(minutes=1),
        label_format="dms_full",
    )
    export = config.export
    if export is None:
        export = {
            "template_pptx_file": "",
            "final_render_dpi": 200,
            "map_background_color": "#FFFFFF",
        }
    else:
        export = export.model_dump(mode="python", by_alias=True)

    metadata = dict(config.metadata)
    metadata.update(
        {
            "fallback_kind": UNMATCHED_METADATA_KIND,
            "allow_include": config.allow_include,
            "allow_export": config.allow_export,
            "history_disabled": True,
        }
    )

    return TargetConfig.model_validate(
        {
            "id": composition.target_id,
            "enabled": False,
            "group": config.review_group.model_dump(mode="python"),
            "sort_order": 10_000,
            "name": config.target_name,
            "alias": config.target_name,
            "coordinate": list(composition.view.center),
            "scale": config.view.scale,
            "grid": grid.model_dump(mode="python"),
            "export": export,
            "metadata": metadata,
        }
    )


def targets_with_unmatched(
    targets: Iterable[TargetConfig],
    compositions: Iterable[Composition],
    config: UnmatchedImagesConfig,
) -> list[TargetConfig]:
    """Append transient unmatched targets for workspace compositions when configured."""
    result = list(targets)
    existing_ids = {target.id for target in result}
    if not config.enabled:
        return result

    for composition in compositions:
        if composition.target_id in existing_ids:
            continue
        target = target_for_unmatched_composition(composition, config)
        if target is None:
            continue
        result.append(target)
        existing_ids.add(target.id)
    return result


def unmatched_target_allows_include(target: TargetConfig | None) -> bool:
    """Return true when a transient unmatched target may be included/exported."""
    if target is None or not is_unmatched_target_id(target.id):
        return False
    return bool(target.metadata.get("allow_include") and target.metadata.get("allow_export"))
