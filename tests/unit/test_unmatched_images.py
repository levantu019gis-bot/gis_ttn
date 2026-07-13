from __future__ import annotations

from datetime import date

from thucthengay.models import (
    Composition,
    ImageLayer,
    ProjectConfig,
    ViewState,
)
from thucthengay.unmatched import (
    target_for_unmatched_composition,
    targets_with_unmatched,
    unmatched_target_allows_include,
)


def test_unmatched_images_config_builds_transient_target() -> None:
    config = ProjectConfig.model_validate(
        {
            "defaults": {
                "grid": {"label_format": "dms_full"},
                "export": {
                    "date_format": "dd.MM.yy",
                    "time_format": "HH.mm/dd.MM.yy",
                    "final_render_dpi": 200,
                    "map_background_color": "#3a3756",
                },
            },
            "unmatched_images": {
                "enabled": True,
                "allow_include": True,
                "allow_export": True,
                "grid": {"interval": {"minutes": 5}},
                "export": {
                    "template_pptx_file": "data/templates/unmatched.pptx",
                    "template_txt_value": "xx",
                    "placeholders": [{"field": "map_image", "kind": "map_image"}],
                },
                "metadata": {
                    "template_metadata": {
                        "template_pptx": "data/templates/unmatched.pptx",
                        "slide_index": 0,
                        "map_frame": {"x": 0, "y": 0, "width": 640, "height": 360},
                    }
                },
            },
            "targets": [_target_dict()],
        }
    )
    composition = _unmatched_composition()

    target = target_for_unmatched_composition(composition, config.unmatched_images)

    assert target is not None
    assert target.id == "__unmatched__abc123"
    assert target.grid.interval.minutes == 5
    assert target.export.template_pptx_file == "data/templates/unmatched.pptx"
    assert target.export.date_format == "dd.MM.yy"
    assert "template_metadata" in target.metadata
    assert unmatched_target_allows_include(target) is True


def test_targets_with_unmatched_appends_only_workspace_unmatched_targets() -> None:
    config = ProjectConfig.model_validate(
        {
            "unmatched_images": {
                "enabled": True,
                "allow_include": True,
                "allow_export": True,
                "grid": {"interval": {"minutes": 5}},
                "export": {
                    "template_pptx_file": "data/templates/unmatched.pptx",
                    "placeholders": [{"field": "map_image", "kind": "map_image"}],
                },
            },
            "targets": [_target_dict()],
        }
    )

    targets = targets_with_unmatched(
        config.targets,
        [_unmatched_composition()],
        config.unmatched_images,
    )

    assert [target.id for target in targets] == ["target_001", "__unmatched__abc123"]


def _target_dict() -> dict[str, object]:
    return {
        "id": "target_001",
        "name": "Target 001",
        "coordinate": [106.7, 10.8],
        "scale": 50000,
        "grid": {"interval": {"minutes": 1}},
        "export": {"template_pptx_file": "templates/target_001.pptx"},
    }


def _unmatched_composition() -> Composition:
    return Composition(
        composition_id="__unmatched__abc123__20260712",
        target_id="__unmatched__abc123",
        capture_date=date(2026, 7, 12),
        layers=[ImageLayer(layer_id="outside", source_path="outside.tif", order=0)],
        view=ViewState(center=[116.0, 23.0], scale=50000),
        needs_revalidation=False,
    )
