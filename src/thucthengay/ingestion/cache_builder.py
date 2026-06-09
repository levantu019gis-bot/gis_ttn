"""Populate workspace cache from matched imagery."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path

from thucthengay.ingestion.intersection import TargetMatchingResult
from thucthengay.models import ImageLayer, Issue, IssueScope, IssueSeverity
from thucthengay.utils.path_safety import safe_filename_component
from thucthengay.workspace import WorkspaceService

UNKNOWN_DATE_KEY = "unknown_date"
CheckpointCallback = Callable[[], None]


@dataclass(frozen=True)
class CachePopulationResult:
    """Result of copying matched imagery into workspace cache."""

    layers_by_target_date: dict[tuple[str, str], list[ImageLayer]]
    issues: list[Issue]
    cache_recreated: bool = False


@dataclass(frozen=True)
class CacheImageInput:
    """One image already associated with a target and ready for workspace cache copy."""

    target_id: str
    source_path: Path
    layer: ImageLayer


def populate_workspace_cache(
    matching_result: TargetMatchingResult,
    workspace_service: WorkspaceService,
    *,
    additional_images: Sequence[CacheImageInput] = (),
    clear_existing: bool = False,
    clear_confirmed: bool = False,
    checkpoint: CheckpointCallback | None = None,
) -> CachePopulationResult:
    """Copy matched imagery into deterministic target/date cache folders."""
    cache_recreated = False
    if clear_existing and workspace_service.has_app_owned_data():
        workspace_service.clear_app_owned_data(confirmed=clear_confirmed)
        cache_recreated = True
    else:
        workspace_service.paths.cache.mkdir(parents=True, exist_ok=True)

    layers_by_target_date: dict[tuple[str, str], list[ImageLayer]] = {}
    issues: list[Issue] = []
    seen_identities: set[tuple[str, str, str]] = set()

    for target_id, matches in matching_result.matches.items():
        if checkpoint is not None:
            checkpoint()
        for match in matches:
            if checkpoint is not None:
                checkpoint()
            _add_cache_input(
                CacheImageInput(
                    target_id=target_id,
                    source_path=match.image.path,
                    layer=match.image.layer,
                ),
                workspace_service,
                layers_by_target_date=layers_by_target_date,
                issues=issues,
                seen_identities=seen_identities,
            )

    for image in additional_images:
        if checkpoint is not None:
            checkpoint()
        _add_cache_input(
            image,
            workspace_service,
            layers_by_target_date=layers_by_target_date,
            issues=issues,
            seen_identities=seen_identities,
        )
        if checkpoint is not None:
            checkpoint()

    return CachePopulationResult(
        layers_by_target_date=layers_by_target_date,
        issues=issues,
        cache_recreated=cache_recreated,
    )


def _add_cache_input(
    image: CacheImageInput,
    workspace_service: WorkspaceService,
    *,
    layers_by_target_date: dict[tuple[str, str], list[ImageLayer]],
    issues: list[Issue],
    seen_identities: set[tuple[str, str, str]],
) -> None:
    source_path = image.source_path.expanduser().resolve()
    date_key = _date_key(image.layer)
    group_key = (image.target_id, date_key)
    layers_by_target_date.setdefault(group_key, [])

    identity = (image.target_id, date_key, str(source_path))
    if identity in seen_identities:
        return
    seen_identities.add(identity)

    cache_path = _cache_path_for_source(
        workspace_service,
        image.target_id,
        date_key,
        source_path,
    )
    try:
        _copy_source_to_cache(source_path, cache_path)
    except OSError as error:
        issues.append(_copy_failed_issue(source_path, error))
        return

    layers_by_target_date[group_key].append(
        _cached_layer(
            image.layer,
            source_path,
            workspace_service.paths.root,
            cache_path,
        )
    )


def _date_key(layer: ImageLayer) -> str:
    if layer.capture_date is None:
        return UNKNOWN_DATE_KEY
    return layer.capture_date.strftime("%Y%m%d")


def _cache_path_for_source(
    workspace_service: WorkspaceService,
    target_id: str,
    date_key: str,
    source_path: Path,
) -> Path:
    source_hash = sha1(str(source_path).encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    target_dir = safe_filename_component(target_id, fallback="target")
    source_stem = safe_filename_component(source_path.stem, fallback="image")
    filename = f"{source_stem}__{source_hash}{source_path.suffix.lower()}"
    return workspace_service.paths.cache / target_dir / date_key / filename


def _copy_source_to_cache(source_path: Path, cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        return
    shutil.copy2(source_path, cache_path)


def _cached_layer(
    layer: ImageLayer,
    source_path: Path,
    workspace_root: Path,
    cache_path: Path,
) -> ImageLayer:
    return layer.model_copy(
        update={
            "source_path": str(source_path),
            "cache_path": cache_path.relative_to(workspace_root).as_posix(),
        }
    )


def _copy_failed_issue(source_path: Path, error: OSError) -> Issue:
    return Issue(
        issue_id="cache.copy_failed",
        severity=IssueSeverity.WARNING,
        scope=IssueScope.LAYER,
        layer_id=str(source_path),
        message=f"Không thể copy ảnh vào workspace cache: {source_path}",
        remediation=f"Kiểm tra file nguồn, quyền truy cập hoặc dung lượng ổ đĩa. Chi tiết: {error}",
    )
