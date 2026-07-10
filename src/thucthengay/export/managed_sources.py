"""Copy exported source rasters into a managed archive before history sync."""

from __future__ import annotations

import shutil
from hashlib import sha1
from pathlib import Path

from thucthengay.models import (
    Composition,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    TargetConfig,
)
from thucthengay.utils.path_safety import safe_filename_component
from thucthengay.workspace import WorkspaceService

UNKNOWN_DATE_KEY = "unknown_date"


def managed_source_composition(
    workspace_service: WorkspaceService,
    target: TargetConfig,
    composition: Composition,
) -> tuple[Composition, list[Issue]]:
    """Return a transient composition whose visible layer sources point to managed copies."""
    root_text = target.export.managed_source_root
    if not root_text:
        return composition, []

    managed_root = Path(root_text).expanduser().resolve()
    updated_layers: list[ImageLayer] = []
    issues: list[Issue] = []
    for layer in composition.layers:
        if not layer.visible:
            updated_layers.append(layer)
            continue
        source_path = _export_source_path(workspace_service, layer)
        if source_path is None:
            issues.append(
                _issue(
                    "export.managed_source_missing",
                    "Khong tim thay file anh nguon de dua vao thu muc quan ly.",
                    (
                        "Kiem tra layer source_path/cache_path trong workspace roi export lai. "
                        "Database history se khong ghi layer nay neu khong co file nguon hop le."
                    ),
                    target=target,
                    composition=composition,
                    layer=layer,
                )
            )
            updated_layers.append(layer)
            continue

        destination = _managed_source_path(
            managed_root,
            target=target,
            composition=composition,
            layer=layer,
            source_path=source_path,
        )
        try:
            _copy_source(source_path, destination)
        except OSError as error:
            issues.append(
                _issue(
                    "export.managed_source_copy_failed",
                    "Khong copy duoc anh nguon vao thu muc quan ly.",
                    (
                        "Kiem tra duong dan `export.managed_source_root`, quyen ghi va dung "
                        f"luong o dia roi export lai. Chi tiet: {error}"
                    ),
                    target=target,
                    composition=composition,
                    layer=layer,
                )
            )
            updated_layers.append(layer)
            continue

        updated_layers.append(
            layer.model_copy(
                update={
                    "source_path": str(destination),
                    "cache_path": None,
                }
            )
        )

    if issues:
        return composition, issues
    return composition.model_copy(update={"layers": updated_layers}), []


def _export_source_path(
    workspace_service: WorkspaceService,
    layer: ImageLayer,
) -> Path | None:
    for raw_path in (layer.source_path, layer.cache_path):
        if not raw_path:
            continue
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_service.paths.root / candidate
        candidate = candidate.resolve()
        if candidate.is_file():
            return candidate
    return None


def _managed_source_path(
    managed_root: Path,
    *,
    target: TargetConfig,
    composition: Composition,
    layer: ImageLayer,
    source_path: Path,
) -> Path:
    target_dir = safe_filename_component(target.id, fallback="target")
    date_value = layer.capture_date or composition.capture_date
    date_dir = (
        date_value.strftime("%Y%m%d")
        if date_value is not None
        else UNKNOWN_DATE_KEY
    )
    managed_date_dir = managed_root / target_dir / date_dir
    try:
        source_path.resolve().relative_to(managed_date_dir.resolve())
    except ValueError:
        pass
    else:
        return source_path

    source_hash = sha1(
        str(source_path).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]
    source_stem = safe_filename_component(source_path.stem, fallback="image")
    suffix = source_path.suffix.lower() or ".tif"
    filename = f"{source_stem}__{source_hash}{suffix}"
    return managed_date_dir / filename


def _copy_source(source_path: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    if source_path.resolve() == destination.resolve():
        return
    shutil.copy2(source_path, destination)


def _issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    target: TargetConfig,
    composition: Composition,
    layer: ImageLayer,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.WARNING,
        scope=IssueScope.EXPORT,
        target_id=target.id,
        composition_id=composition.composition_id,
        layer_id=layer.layer_id,
        message=message,
        remediation=remediation,
    )
