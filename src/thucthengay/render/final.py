"""Final image rendering and render-log persistence."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pydantic import ValidationError

from thucthengay.models.issue import Issue, IssueScope, IssueSeverity
from thucthengay.models.render import (
    FinalRenderCurrentness,
    FinalRenderLog,
    FinalRenderLogEntry,
    FinalRenderResult,
    FinalRenderStatus,
)
from thucthengay.render.core import render_map
from thucthengay.render.raster import CancelCallback, RasterRenderResult, RenderError
from thucthengay.render.spec import RenderSpec

FinalRenderFunction = Callable[..., RasterRenderResult]
FINAL_RENDER_DPI = 200
FINAL_RENDER_JPEG_QUALITY = 90


def render_spec_hash(spec: RenderSpec) -> str:
    """Return a stable hash for the canonical final render spec."""
    payload = json.dumps(
        spec.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def render_final_png(
    spec: RenderSpec,
    *,
    workspace_root: str | Path,
    render: FinalRenderFunction = render_map,
    is_cancelled: CancelCallback | None = None,
    dpi: int = FINAL_RENDER_DPI,
    timestamp: datetime | None = None,
) -> FinalRenderResult:
    """Render a final JPEG under ``workspace_root/renders`` and append its log."""
    root = Path(workspace_root).expanduser().resolve()
    dpi = max(1, int(dpi))
    spec_hash = render_spec_hash(spec)
    log_rel_path = _render_log_rel_path(spec.composition_id)
    log_path = root / log_rel_path
    timestamp = _normalize_timestamp(timestamp or datetime.now(UTC))

    try:
        render_result = render(spec, is_cancelled=is_cancelled)
        _validate_canvas_matches_spec(render_result.canvas, spec)
        output_rel_path = _final_image_rel_path(spec.composition_id, spec_hash)
        output_path = root / output_rel_path
        _atomic_write_jpeg(output_path, render_result.canvas, dpi=dpi)
        entry = _entry(
            spec=spec,
            status=FinalRenderStatus.SUCCESS,
            output_path=output_rel_path,
            width=spec.output_width,
            height=spec.output_height,
            spec_hash=spec_hash,
            timestamp=timestamp,
            issues=list(render_result.issues),
        )
        _append_log_entry(log_path, entry)
        return FinalRenderResult(
            composition_id=spec.composition_id,
            target_id=spec.target_id,
            status=FinalRenderStatus.SUCCESS,
            output_path=output_rel_path,
            log_path=log_rel_path,
            width=spec.output_width,
            height=spec.output_height,
            render_spec_hash=spec_hash,
            issues=list(render_result.issues),
        )
    except RenderError as exc:
        return _record_failure(
            spec=spec,
            log_path=log_path,
            log_rel_path=log_rel_path,
            spec_hash=spec_hash,
            timestamp=timestamp,
            issues=list(exc.issues),
            failure_reason=_failure_reason(exc.issues, str(exc)),
        )
    except (OSError, ValueError) as exc:
        issue = _failure_issue(spec, str(exc))
        return _record_failure(
            spec=spec,
            log_path=log_path,
            log_rel_path=log_rel_path,
            spec_hash=spec_hash,
            timestamp=timestamp,
            issues=[issue],
            failure_reason=issue.message,
        )


def is_final_render_current(
    *,
    workspace_root: str | Path,
    output_path: str | None,
    log_path: str | None,
    spec: RenderSpec,
    dpi: int = FINAL_RENDER_DPI,
) -> FinalRenderCurrentness:
    """Check whether a persisted final render artifact still matches ``spec``."""
    if not output_path or not log_path:
        return FinalRenderCurrentness(current=False, reason="artifact_reference_missing")

    root = Path(workspace_root).expanduser().resolve()
    invalid_artifact_path = (
        not _is_workspace_render_artifact_path(output_path)
        or not _is_workspace_render_artifact_path(log_path)
    )
    if invalid_artifact_path:
        return FinalRenderCurrentness(current=False, reason="artifact_path_invalid")

    resolved_output = root / output_path
    resolved_log = root / log_path
    if not resolved_output.is_file():
        return FinalRenderCurrentness(current=False, reason="output_missing")
    if not resolved_log.is_file():
        return FinalRenderCurrentness(current=False, reason="log_missing")

    try:
        log = _load_log(resolved_log)
    except (OSError, json.JSONDecodeError, ValidationError):
        return FinalRenderCurrentness(current=False, reason="log_unreadable")

    if not log.entries:
        return FinalRenderCurrentness(current=False, reason="log_empty")

    latest = log.entries[-1]
    if latest.status != FinalRenderStatus.SUCCESS:
        return FinalRenderCurrentness(current=False, reason="latest_log_not_success")
    if latest.output_path != output_path:
        return FinalRenderCurrentness(current=False, reason="output_path_mismatch")
    if latest.render_spec_hash != render_spec_hash(spec):
        return FinalRenderCurrentness(current=False, reason="spec_hash_mismatch")
    if latest.width != spec.output_width or latest.height != spec.output_height:
        return FinalRenderCurrentness(current=False, reason="output_size_mismatch")
    if not _image_has_expected_dpi(resolved_output, expected_dpi=max(1, int(dpi))):
        return FinalRenderCurrentness(current=False, reason="output_dpi_mismatch")

    return FinalRenderCurrentness(current=True, reason=None)


def _final_image_rel_path(composition_id: str, spec_hash: str) -> str:
    return f"renders/{composition_id}.{spec_hash[:12]}.jpg"


def _render_log_rel_path(composition_id: str) -> str:
    return f"renders/{composition_id}.render-log.json"


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _entry(
    *,
    spec: RenderSpec,
    status: FinalRenderStatus,
    output_path: str | None,
    width: int | None,
    height: int | None,
    spec_hash: str,
    timestamp: datetime,
    failure_reason: str | None = None,
    issues: list[Issue] | None = None,
) -> FinalRenderLogEntry:
    return FinalRenderLogEntry(
        composition_id=spec.composition_id,
        target_id=spec.target_id,
        status=status,
        output_path=output_path,
        width=width,
        height=height,
        render_spec_hash=spec_hash,
        visible_layer_refs=[layer.layer_id for layer in spec.visible_layers],
        timestamp=timestamp,
        failure_reason=failure_reason,
        issues=issues or [],
    )


def _record_failure(
    *,
    spec: RenderSpec,
    log_path: Path,
    log_rel_path: str,
    spec_hash: str,
    timestamp: datetime,
    issues: list[Issue],
    failure_reason: str,
) -> FinalRenderResult:
    entry = _entry(
        spec=spec,
        status=FinalRenderStatus.FAILURE,
        output_path=None,
        width=None,
        height=None,
        spec_hash=spec_hash,
        timestamp=timestamp,
        failure_reason=failure_reason,
        issues=issues,
    )
    _append_log_entry(log_path, entry)
    return FinalRenderResult(
        composition_id=spec.composition_id,
        target_id=spec.target_id,
        status=FinalRenderStatus.FAILURE,
        output_path=None,
        log_path=log_rel_path,
        render_spec_hash=spec_hash,
        failure_reason=failure_reason,
        issues=issues,
    )


def _failure_reason(issues: list[Issue], fallback: str) -> str:
    if issues:
        return issues[0].message
    return fallback or "Khong tao duoc anh final."


def _failure_issue(spec: RenderSpec, detail: str) -> Issue:
    return Issue(
        issue_id="render.final_image.failed",
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=spec.target_id,
        composition_id=spec.composition_id,
        message="Khong tao duoc anh final.",
        remediation=f"Kiem tra workspace render va thu lai. Chi tiet: {detail}",
    )


def _atomic_write_jpeg(path: Path, canvas: np.ndarray, *, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        Image.fromarray(_as_rgb_uint8(canvas)).save(
            temp_path,
            format="JPEG",
            dpi=(dpi, dpi),
            optimize=True,
            quality=FINAL_RENDER_JPEG_QUALITY,
            subsampling=0,
        )
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _validate_canvas_matches_spec(canvas: np.ndarray, spec: RenderSpec) -> None:
    wrong_shape = (
        canvas.ndim < 2
        or canvas.shape[0] != spec.output_height
        or canvas.shape[1] != spec.output_width
    )
    if wrong_shape:
        msg = (
            "final render canvas dimensions must match RenderSpec "
            f"({spec.output_width}x{spec.output_height})"
        )
        raise ValueError(msg)


def _as_rgb_uint8(canvas: np.ndarray) -> np.ndarray:
    if canvas.dtype != np.uint8:
        msg = "final render canvas must use uint8 pixels"
        raise ValueError(msg)
    if canvas.ndim != 3 or canvas.shape[2] != 3:
        msg = "final render canvas must be RGB with shape (height, width, 3)"
        raise ValueError(msg)
    return canvas


def _image_has_expected_dpi(path: Path, *, expected_dpi: int) -> bool:
    try:
        with Image.open(path) as image:
            image_dpi = image.info.get("dpi")
    except OSError:
        return False
    if not isinstance(image_dpi, tuple) or len(image_dpi) < 2:
        return False
    return (
        round(float(image_dpi[0])) == expected_dpi
        and round(float(image_dpi[1])) == expected_dpi
    )


def _is_workspace_render_artifact_path(value: str) -> bool:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    return path.as_posix().startswith("renders/")


def _append_log_entry(path: Path, entry: FinalRenderLogEntry) -> None:
    try:
        log = _load_log(path)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError):
        log = FinalRenderLog()
    log.entries.append(entry)
    _atomic_write_json(path, log.model_dump(mode="json"))


def _load_log(path: Path) -> FinalRenderLog:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return FinalRenderLog.model_validate(raw)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            json.dump(data, temp_file, ensure_ascii=False, indent=2, sort_keys=True)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except Exception:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
        raise
