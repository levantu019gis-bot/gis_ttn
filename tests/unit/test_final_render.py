from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from thucthengay.models import FinalRenderStatus, Issue, IssueScope, IssueSeverity
from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    FinalRenderCurrentness,
    GeoWindow,
    RasterRenderResult,
    RenderBackground,
    RenderError,
    RenderLayerRef,
    RenderSpec,
    is_final_render_current,
    render_final_png,
    render_spec_hash,
)
from thucthengay.render.final import FINAL_RENDER_DPI


def _spec(*, width: int = 96, height: int = 54, scale: int = 50000) -> RenderSpec:
    return RenderSpec(
        composition_id="target_001__20260525",
        target_id="target_001",
        output_width=width,
        output_height=height,
        view_center=[106.7, 10.8],
        view_scale=scale,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=640 / 360,
        geo_window=GeoWindow(min_lon=106.0, min_lat=10.0, max_lon=107.0, max_lat=11.0),
        visible_layers=[
            RenderLayerRef(layer_id="L1", source_path="L1.tif", cache_path="cache/L1.tif", order=0),
            RenderLayerRef(layer_id="L2", source_path="L2.tif", cache_path="cache/L2.tif", order=1),
        ],
        grid=GridConfig(interval=GridInterval(minutes=30), label_format="dms_full"),
        background=RenderBackground(color="#112233"),
        template_metadata_file="templates/target_001.template.json",
        template_pptx="templates/target_001.pptx",
        slide_index=0,
    )


def _success_render(spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
    canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
    canvas[..., 0] = 12
    canvas[..., 1] = 34
    canvas[..., 2] = 56
    return RasterRenderResult(canvas=canvas, painted_layer_ids=("L1", "L2"))


def test_final_render_writes_jpeg_and_success_log(tmp_path: Path) -> None:
    timestamp = datetime(2026, 5, 26, 8, 30, tzinfo=UTC)
    spec = _spec(width=120, height=68)

    result = render_final_png(
        spec,
        workspace_root=tmp_path,
        render=_success_render,
        timestamp=timestamp,
    )

    assert result.status == FinalRenderStatus.SUCCESS
    assert result.output_path is not None
    assert result.log_path == "renders/target_001__20260525.render-log.json"
    assert result.width == 120
    assert result.height == 68
    assert result.render_spec_hash == render_spec_hash(spec)

    assert result.output_path.endswith(".jpg")
    jpeg_path = tmp_path / result.output_path
    with Image.open(jpeg_path) as image:
        assert image.format == "JPEG"
        assert image.size == (120, 68)
        assert image.mode == "RGB"
        dpi = image.info["dpi"]
        assert round(dpi[0]) == FINAL_RENDER_DPI
        assert round(dpi[1]) == FINAL_RENDER_DPI

    log = json.loads((tmp_path / result.log_path).read_text(encoding="utf-8"))
    entry = log["entries"][-1]
    assert entry["status"] == "success"
    assert entry["composition_id"] == "target_001__20260525"
    assert entry["output_path"] == result.output_path
    assert entry["width"] == 120
    assert entry["height"] == 68
    assert entry["render_spec_hash"] == render_spec_hash(spec)
    assert entry["visible_layer_refs"] == ["L1", "L2"]
    assert entry["timestamp"] == "2026-05-26T08:30:00Z"


def test_final_render_failure_writes_failure_log_without_success_output(
    tmp_path: Path,
) -> None:
    issue = Issue(
        issue_id="render.synthetic_failure",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        composition_id="target_001__20260525",
        message="Khong tao duoc anh final.",
        remediation="Kiem tra layer va thu render lai.",
    )

    def fail_render(_spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
        raise RenderError([issue])

    result = render_final_png(_spec(), workspace_root=tmp_path, render=fail_render)

    assert result.status == FinalRenderStatus.FAILURE
    assert result.output_path is None
    assert result.failure_reason == "Khong tao duoc anh final."
    assert list((tmp_path / "renders").glob("*.jpg")) == []

    log = json.loads((tmp_path / result.log_path).read_text(encoding="utf-8"))
    entry = log["entries"][-1]
    assert entry["status"] == "failure"
    assert entry["composition_id"] == "target_001__20260525"
    assert entry["failure_reason"] == "Khong tao duoc anh final."
    assert entry["output_path"] is None


def test_final_render_rejects_canvas_size_mismatch(tmp_path: Path) -> None:
    def wrong_size_render(_spec: RenderSpec, is_cancelled=None) -> RasterRenderResult:
        return RasterRenderResult(canvas=np.zeros((4, 5, 3), dtype=np.uint8))

    result = render_final_png(
        _spec(width=12, height=8),
        workspace_root=tmp_path,
        render=wrong_size_render,
    )

    assert result.status == FinalRenderStatus.FAILURE
    assert result.output_path is None
    assert list((tmp_path / "renders").glob("*.jpg")) == []
    assert result.issues[0].issue_id == "render.final_image.failed"
    assert "dimensions" in result.issues[0].remediation


def test_final_render_currentness_rejects_missing_path_failed_log_and_spec_mismatch(
    tmp_path: Path,
) -> None:
    spec = _spec()
    result = render_final_png(spec, workspace_root=tmp_path, render=_success_render)

    assert is_final_render_current(
        workspace_root=tmp_path,
        output_path=result.output_path,
        log_path=result.log_path,
        spec=spec,
    ) == FinalRenderCurrentness(current=True, reason=None)

    assert is_final_render_current(
        workspace_root=tmp_path,
        output_path="renders/missing.png",
        log_path=result.log_path,
        spec=spec,
    ).reason == "output_missing"

    stale_spec = _spec(scale=25000)
    assert is_final_render_current(
        workspace_root=tmp_path,
        output_path=result.output_path,
        log_path=result.log_path,
        spec=stale_spec,
    ).reason == "spec_hash_mismatch"

    assert result.output_path is not None
    Image.new("RGB", (spec.output_width, spec.output_height), (1, 2, 3)).save(
        tmp_path / result.output_path
    )
    assert is_final_render_current(
        workspace_root=tmp_path,
        output_path=result.output_path,
        log_path=result.log_path,
        spec=spec,
    ).reason == "output_dpi_mismatch"

    failed = render_final_png(
        spec,
        workspace_root=tmp_path,
        render=lambda _spec, is_cancelled=None: (_ for _ in ()).throw(
            RenderError(
                [
                    Issue(
                        issue_id="render.failed",
                        severity=IssueSeverity.ERROR,
                        scope=IssueScope.RENDER,
                        composition_id=spec.composition_id,
                        message="Render hong.",
                    )
                ]
            )
        ),
    )
    assert is_final_render_current(
        workspace_root=tmp_path,
        output_path=result.output_path,
        log_path=failed.log_path,
        spec=spec,
    ).reason == "latest_log_not_success"


def test_final_render_currentness_rejects_paths_outside_renders(tmp_path: Path) -> None:
    spec = _spec()
    result = render_final_png(spec, workspace_root=tmp_path, render=_success_render)

    assert is_final_render_current(
        workspace_root=tmp_path,
        output_path="../outside.png",
        log_path=result.log_path,
        spec=spec,
    ).reason == "artifact_path_invalid"
    assert is_final_render_current(
        workspace_root=tmp_path,
        output_path=result.output_path,
        log_path=str((tmp_path / "renders" / "log.json").resolve()),
        spec=spec,
    ).reason == "artifact_path_invalid"
