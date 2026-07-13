from __future__ import annotations

from datetime import date, time

from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    MapFrame,
    MetadataStatus,
    TargetConfig,
    TemplateMetadata,
    ViewState,
)
from thucthengay.validation import (
    ValidationContext,
    validate_composition_readiness,
    validate_export_preflight,
)

_DEFAULT = object()


def target_config() -> TargetConfig:
    return TargetConfig(
        id="alpha",
        name="Alpha",
        geojson_file="targets/alpha.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export={"template_pptx_file": "templates/alpha.pptx"},
    )


def template_metadata() -> TemplateMetadata:
    return TemplateMetadata(
        template_pptx="templates/alpha.pptx",
        slide_index=0,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
    )


def layer(**overrides: object) -> ImageLayer:
    data = {
        "layer_id": "l1",
        "source_path": "imagery/l1.tif",
        "cache_path": "cache/alpha/l1.tif",
        "order": 0,
        "visible": True,
        "capture_date": date(2026, 5, 25),
        "capture_time": time(9, 30),
        "metadata_status": MetadataStatus.VALID,
    }
    data.update(overrides)
    return ImageLayer(**data)


def composition(**overrides: object) -> Composition:
    data = {
        "composition_id": "alpha__20260525",
        "target_id": "alpha",
        "capture_date": date(2026, 5, 25),
        "layers": [layer()],
        "view": ViewState(center=[106.7, 10.8], scale=50000),
        "needs_revalidation": False,
    }
    data.update(overrides)
    return Composition(**data)


def context(
    composition_value: Composition | None = None,
    target_value: TargetConfig | None = None,
    template_value: TemplateMetadata | None | object = _DEFAULT,
    template_error: str | None = None,
    require_current_validation: bool = False,
) -> ValidationContext:
    selected_template = template_metadata() if template_value is _DEFAULT else template_value
    return ValidationContext(
        composition=composition_value if composition_value is not None else composition(),
        target=target_value if target_value is not None else target_config(),
        template_metadata=selected_template,
        template_metadata_error=template_error,
        require_current_validation=require_current_validation,
    )


def issue_ids(result) -> set[str]:  # noqa: ANN001
    return {issue.issue_id for issue in result.issues}


def test_readiness_passes_for_valid_current_composition() -> None:
    result = validate_composition_readiness(context())

    assert result.passed is True
    assert result.summary.error_count == 0
    assert result.issues == ()


def test_no_visible_layers_blocks_readiness_with_composition_issue() -> None:
    result = validate_composition_readiness(
        context(composition(layers=[layer(visible=False)]))
    )

    assert "composition.no_visible_layer" in issue_ids(result)
    issue = result.issues[0]
    assert issue.blocking is True
    assert issue.scope.value == "composition"
    assert "Bật ít nhất" in issue.remediation


def test_visible_layer_missing_capture_time_blocks_with_metadata_remediation() -> None:
    result = validate_composition_readiness(
        context(composition(layers=[layer(capture_time=None)]))
    )

    issue = result.issues[0]
    assert issue.issue_id == "layer.capture_timestamp_invalid"
    assert issue.layer_id == "l1"
    assert "metadata editor" in issue.remediation


def test_visible_layer_unconfirmed_metadata_blocks_readiness() -> None:
    result = validate_composition_readiness(
        context(composition(layers=[layer(metadata_status=MetadataStatus.NEEDS_CORRECTION)]))
    )

    assert "layer.metadata_needs_correction" in issue_ids(result)
    assert result.blocking is True


def test_invalid_view_and_grid_override_block_readiness_defensively() -> None:
    bad_view = ViewState.model_construct(center=[999, 10.8], scale=0, rotation=0)
    bad_grid = GridConfig.model_construct(
        interval=GridInterval.model_construct(degrees=0, minutes=0, seconds=0),
        label_format="dms_full",
        style={},
    )

    result = validate_composition_readiness(
        context(composition(view=bad_view, grid_override=bad_grid))
    )

    assert {"composition.view_invalid", "composition.grid_override_invalid"} <= issue_ids(result)


def test_missing_template_metadata_blocks_with_target_remediation() -> None:
    result = validate_composition_readiness(context(template_value=None))

    issue = result.issues[0]
    assert issue.issue_id == "template.metadata_missing"
    assert issue.target_id == "alpha"
    assert "PPTX template" in issue.remediation


def test_missing_target_still_blocks_regular_composition() -> None:
    result = validate_composition_readiness(
        ValidationContext(
            composition=composition(),
            target=None,
            template_metadata=None,
        )
    )

    assert "target.missing" in issue_ids(result)
    assert result.blocking is True


def test_unmatched_geometry_composition_does_not_require_target_config() -> None:
    unmatched = composition(
        composition_id="__unmatched__abc123__20260525",
        target_id="__unmatched__abc123",
    )

    result = validate_composition_readiness(
        ValidationContext(
            composition=unmatched,
            target=None,
            template_metadata=None,
        )
    )

    assert "target.missing" not in issue_ids(result)
    assert result.passed is True


def test_invalid_template_metadata_error_blocks_readiness() -> None:
    result = validate_composition_readiness(context(template_error="bad json"))

    assert "template.metadata_invalid" in issue_ids(result)
    assert result.summary.error_count == 1


def test_invalid_map_frame_blocks_readiness() -> None:
    bad_template = TemplateMetadata.model_construct(
        template_pptx="templates/alpha.pptx",
        slide_index=0,
        map_frame=MapFrame.model_construct(x=0, y=0, width=0, height=360),
        placeholders=[],
    )

    result = validate_composition_readiness(context(template_value=bad_template))

    assert "template.map_frame_invalid" in issue_ids(result)


def test_recomputed_readiness_can_pass_for_stale_composition_before_summary_is_saved() -> None:
    result = validate_composition_readiness(context(composition(needs_revalidation=True)))

    assert "composition.needs_revalidation" not in issue_ids(result)
    assert result.passed is True


def test_persisted_readiness_evaluation_blocks_stale_composition() -> None:
    result = validate_composition_readiness(
        context(
            composition(needs_revalidation=True),
            require_current_validation=True,
        )
    )

    issue = result.issues[0]
    assert issue.issue_id == "composition.needs_revalidation"
    assert "Revalidate" in issue.remediation
    assert result.blocking is True


def test_export_preflight_recomputes_included_composition_issues() -> None:
    clean = context(composition(include=True, ready=True))
    blocked = context(composition(layers=[layer(visible=False)], include=True, ready=True))

    result = validate_export_preflight([clean, blocked])

    assert "composition.no_visible_layer" in issue_ids(result)
    assert result.summary.error_count == 1
    assert result.blocking is True


def test_export_preflight_surfaces_template_compatibility_issues() -> None:
    warning = Issue(
        issue_id="target.template_compatibility_unknown",
        severity=IssueSeverity.WARNING,
        scope=IssueScope.TEMPLATE,
        message="Nhieu PPTX template chua xac minh tuong thich.",
        remediation="Kiem tra base/theme/master truoc khi export.",
    )

    result = validate_export_preflight([context()], template_issues=[warning])

    assert "target.template_compatibility_unknown" in issue_ids(result)
    assert result.summary.warning_count == 1
    assert result.blocking is False
