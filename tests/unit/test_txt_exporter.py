from __future__ import annotations

from datetime import date, time
from pathlib import Path

from thucthengay.export import export_txt_report
from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    MetadataStatus,
    TargetConfig,
    ViewState,
)
from thucthengay.workspace import WorkspaceService


def _target(
    target_id: str = "alpha",
    *,
    txt_template: str = "{slide_number}|{target_id}|{capture_date}|{time_label}",
    alias: str | None = "ALPHA",
) -> TargetConfig:
    return TargetConfig(
        id=target_id,
        name=f"{target_id.title()} Name",
        alias=alias,
        title=f"{target_id.title()} Title",
        geojson_file=f"targets/{target_id}.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export={
            "template_pptx_file": f"templates/{target_id}.pptx",
            "txt_line_template": txt_template,
            "placeholders": [
                {
                    "field": "map",
                    "element_id": 10,
                    "kind": "map_image",
                    "required": True,
                }
            ],
        },
    )


def _composition(
    composition_id: str,
    *,
    target_id: str = "alpha",
    capture_date: date = date(2026, 5, 25),
    review_order: int = 1,
    layers: list[ImageLayer] | None = None,
) -> Composition:
    return Composition(
        composition_id=composition_id,
        target_id=target_id,
        capture_date=capture_date,
        view=ViewState(center=[106.7, 10.8], scale=50000),
        reviewed=True,
        ready=True,
        include=True,
        needs_revalidation=False,
        review_order=review_order,
        layers=layers if layers is not None else [_layer("valid", capture_time=time(8, 30))],
    )


def _layer(
    layer_id: str,
    *,
    visible: bool = True,
    status: MetadataStatus = MetadataStatus.VALID,
    capture_time: time | None = time(8, 30),
) -> ImageLayer:
    return ImageLayer(
        layer_id=layer_id,
        source_path=f"{layer_id}.tif",
        cache_path=f"cache/{layer_id}.tif",
        order=0,
        visible=visible,
        capture_date=date(2026, 5, 25),
        capture_time=capture_time,
        metadata_status=status,
    )


def _workspace(tmp_path: Path, *compositions: Composition) -> WorkspaceService:
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    for composition in compositions:
        service.write_composition(composition)
    return service


def test_export_txt_report_writes_lines_sorted_by_review_order(tmp_path: Path) -> None:
    service = _workspace(
        tmp_path,
        _composition("alpha__20260526", capture_date=date(2026, 5, 26), review_order=2),
        _composition("alpha__20260525", capture_date=date(2026, 5, 25), review_order=1),
    )
    output_path = service.paths.exports / "report.txt"

    result = export_txt_report(service, [_target()], output_path=output_path)

    assert result.ok is True
    assert result.txt_path == "exports/report.txt"
    assert [row.composition_id for row in result.exported] == [
        "alpha__20260525",
        "alpha__20260526",
    ]
    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "1|alpha|2026-05-25|08:30:00",
        "2|alpha|2026-05-26|08:30:00",
    ]


def test_export_txt_report_uses_template_txt_value_and_config_formats(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path, _composition("alpha__20260525"))
    output_path = service.paths.exports / "contract.txt"
    target = TargetConfig(
        id="alpha",
        name="Alpha Name",
        title="Alpha Title",
        geojson_file="targets/alpha.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export={
            "template_pptx_file": "templates/alpha.pptx",
            "template_txt_value": "Tai {target_title} luc {time_label} ngay {capture_date}",
            "date_format": "dd.MM.yy",
            "time_format": "HH.mm/dd.MM.yy",
            "placeholders": [{"field": "map_image", "element_id": "10"}],
        },
    )

    result = export_txt_report(service, [target], output_path=output_path)

    assert result.ok is True
    assert output_path.read_text(encoding="utf-8").strip() == (
        "Tai Alpha Title luc 08.30/25.05.26 ngay 25.05.26"
    )


def test_export_txt_report_blocks_required_unknown_placeholder(tmp_path: Path) -> None:
    service = _workspace(tmp_path, _composition("alpha__20260525"))
    output_path = service.paths.exports / "blocked.txt"

    result = export_txt_report(
        service,
        [_target(txt_template="{slide_number}|{unknown_required}")],
        output_path=output_path,
    )

    assert result.ok is False
    assert "export.txt_placeholder_unknown" in {issue.issue_id for issue in result.issues}
    assert not output_path.exists()


def test_export_txt_report_optional_placeholder_renders_empty_only_when_marked(
    tmp_path: Path,
) -> None:
    service = _workspace(tmp_path, _composition("alpha__20260525"))
    output_path = service.paths.exports / "optional.txt"

    result = export_txt_report(
        service,
        [_target(txt_template="{slide_number}|{target_alias?}", alias=None)],
        output_path=output_path,
    )

    assert result.ok is True
    assert output_path.read_text(encoding="utf-8") == "1|\n"

    required_result = export_txt_report(
        service,
        [_target(txt_template="{slide_number}|{target_alias}", alias=None)],
        output_path=service.paths.exports / "required.txt",
    )
    assert required_result.ok is False
    assert "export.txt_placeholder_unresolved" in {
        issue.issue_id for issue in required_result.issues
    }

    unknown_optional_result = export_txt_report(
        service,
        [_target(txt_template="{slide_number}|{unknown_optional?}")],
        output_path=service.paths.exports / "unknown-optional.txt",
    )
    assert unknown_optional_result.ok is False
    assert "export.txt_placeholder_unknown" in {
        issue.issue_id for issue in unknown_optional_result.issues
    }


def test_export_txt_report_time_label_requires_visible_valid_layer_time(
    tmp_path: Path,
) -> None:
    service = _workspace(
        tmp_path,
        _composition(
            "alpha__20260525",
            layers=[
                _layer("hidden", visible=False, capture_time=time(7, 0)),
                _layer(
                    "invalid",
                    status=MetadataStatus.NEEDS_MANUAL_CORRECTION,
                    capture_time=time(7, 30),
                ),
                _layer("valid", capture_time=time(8, 45)),
            ],
        ),
    )
    output_path = service.paths.exports / "time.txt"

    result = export_txt_report(service, [_target()], output_path=output_path)

    assert result.ok is True
    assert output_path.read_text(encoding="utf-8").strip().endswith("|08:45:00")

    blocked_service = _workspace(
        tmp_path / "blocked",
        _composition(
            "alpha__20260525",
            layers=[
                _layer("hidden", visible=False, capture_time=time(7, 0)),
                _layer("invalid", status=MetadataStatus.NEEDS_CORRECTION, capture_time=time(7, 30)),
            ],
        ),
    )
    blocked_result = export_txt_report(
        blocked_service,
        [_target()],
        output_path=blocked_service.paths.exports / "time.txt",
    )
    assert blocked_result.ok is False
    assert "export.txt_time_label_unresolved" in {
        issue.issue_id for issue in blocked_result.issues
    }


def test_export_txt_report_rejects_out_of_workspace_output_path(tmp_path: Path) -> None:
    service = _workspace(tmp_path, _composition("alpha__20260525"))
    output_path = tmp_path / "outside.txt"

    result = export_txt_report(service, [_target()], output_path=output_path)

    assert result.ok is False
    assert "export.txt_write_failed" in {issue.issue_id for issue in result.issues}
    assert not output_path.exists()
