"""Output tree and manifest writing for satellite downloads."""

from __future__ import annotations

import csv
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from thucthengay.download.models import (
    DownloadFilenameFilterResult,
    DownloadFilenameMetadata,
    DownloadImageFolder,
    DownloadManifestRow,
    DownloadOutputResult,
    DownloadStats,
    PreparedDownloadImage,
    ResolvedSatelliteDownloadRequest,
    SkippedCloudDownloadCandidate,
    SkippedCloudDownloadImage,
    SkippedExistingDownloadImage,
)
from thucthengay.download.service import safe_name, unique_name

DownloadOutputProgress = Callable[[DownloadOutputResult], None]
CancelCheck = Callable[[], bool]

MANIFEST_FIELDNAMES = (
    "status",
    "source_folder",
    "source_path",
    "destination_path",
    "matched_geojson",
    "filename_format_matched",
    "filename_format_rule",
    "capture_datetime",
    "cloud_percent",
    "max_cloud_percent",
    "error",
)


def write_download_outputs(
    request: ResolvedSatelliteDownloadRequest,
    filter_result: DownloadFilenameFilterResult,
    *,
    on_progress: DownloadOutputProgress | None = None,
    should_cancel: CancelCheck | None = None,
) -> DownloadOutputResult:
    """Copy accepted download rows and write a CSV manifest when requested."""

    source_folders = _source_folders_by_path(request.image_folders)
    geojson_names = _geojson_names_by_path(request.geojson_files)
    rows: list[DownloadManifestRow] = []
    copied_count = 0
    skipped_existing_count = 0
    failed_count = len(filter_result.failed_images)

    for prepared in filter_result.accepted_matches:
        for geojson_name, geojson_path in zip(
            prepared.match.matched_geojson_names,
            prepared.match.matched_geojson_paths,
            strict=True,
        ):
            if should_cancel is not None and should_cancel():
                return _result(
                    request,
                    filter_result,
                    rows,
                    copied_count=copied_count,
                    skipped_existing_count=skipped_existing_count,
                    failed_count=failed_count,
                    cancelled=True,
                )
            source_folder = _resolved_source_folder(prepared, source_folders)
            branch_name = _resolved_geojson_name(geojson_name, geojson_path, geojson_names)
            destination = destination_for(
                request,
                prepared,
                source_folder=source_folder,
                geojson_name=branch_name,
            )
            try:
                status = _copy_file(
                    prepared.match.path,
                    destination,
                    overwrite=request.overwrite,
                    dry_run=request.dry_run,
                )
            except OSError as error:
                failed_count += 1
                rows.append(
                    _accepted_row(
                        prepared,
                        status="failed",
                        source_folder=source_folder,
                        destination_path=destination,
                        matched_geojson=branch_name,
                        error=str(error),
                    )
                )
                _emit_progress(
                    on_progress,
                    request,
                    filter_result,
                    rows,
                    copied_count=copied_count,
                    skipped_existing_count=skipped_existing_count,
                    failed_count=failed_count,
                )
                continue

            if status == "copied":
                copied_count += 1
            elif status == "skipped_existing":
                skipped_existing_count += 1

            rows.append(
                _accepted_row(
                    prepared,
                    status=status,
                    source_folder=source_folder,
                    destination_path=destination,
                    matched_geojson=branch_name,
                    error="",
                )
            )
            _emit_progress(
                on_progress,
                request,
                filter_result,
                rows,
                copied_count=copied_count,
                skipped_existing_count=skipped_existing_count,
                failed_count=failed_count,
            )

    rows.extend(
        _skipped_cloud_rows(filter_result.skipped_cloud_images, source_folders, geojson_names)
    )
    rows.extend(_skipped_existing_rows(filter_result.skipped_existing_images, source_folders))
    rows.extend(_failed_rows(filter_result.failed_images, source_folders))

    return _result(
        request,
        filter_result,
        rows,
        copied_count=copied_count,
        skipped_existing_count=skipped_existing_count,
        failed_count=failed_count,
    )


def _emit_progress(
    on_progress: DownloadOutputProgress | None,
    request: ResolvedSatelliteDownloadRequest,
    filter_result: DownloadFilenameFilterResult,
    rows: list[DownloadManifestRow],
    *,
    copied_count: int,
    skipped_existing_count: int,
    failed_count: int,
) -> None:
    if on_progress is None:
        return
    on_progress(
        _result(
            request,
            filter_result,
            rows,
            copied_count=copied_count,
            skipped_existing_count=skipped_existing_count,
            failed_count=failed_count,
            write_manifest=False,
        )
    )


def _result(
    request: ResolvedSatelliteDownloadRequest,
    filter_result: DownloadFilenameFilterResult,
    rows: list[DownloadManifestRow],
    *,
    copied_count: int,
    skipped_existing_count: int,
    failed_count: int,
    cancelled: bool = False,
    write_manifest: bool = True,
) -> DownloadOutputResult:
    manifest_path = (
        _write_manifest(request.output_dir, rows)
        if write_manifest and request.write_manifest and rows
        else None
    )
    return DownloadOutputResult(
        rows=tuple(rows),
        stats=DownloadStats(
            total_images=filter_result.stats.total_images,
            scanned_images=filter_result.stats.scanned_images,
            matched_images=filter_result.stats.matched_images,
            downloaded_images=copied_count,
            skipped_existing=filter_result.stats.skipped_existing + skipped_existing_count,
            skipped_cloud=filter_result.stats.skipped_cloud,
            failed_images=failed_count,
            metadata_cache_hits=filter_result.stats.metadata_cache_hits,
            metadata_cache_misses=filter_result.stats.metadata_cache_misses,
        ),
        output_dir=request.output_dir,
        manifest_path=manifest_path,
        cancelled=cancelled,
    )


def destination_for(
    request: ResolvedSatelliteDownloadRequest,
    prepared: PreparedDownloadImage,
    *,
    source_folder: DownloadImageFolder,
    geojson_name: str,
) -> Path:
    """Return the output path for one accepted image and matched GeoJSON branch."""

    source_path = prepared.match.path
    if request.preserve_source_tree:
        try:
            leaf = source_path.relative_to(source_folder.path)
        except ValueError:
            leaf = Path(source_path.name)
    else:
        leaf = Path(source_path.name)
    return request.output_dir / geojson_name / source_folder.name / leaf


def _copy_file(source_path: Path, destination_path: Path, *, overwrite: bool, dry_run: bool) -> str:
    if dry_run:
        return "dry_run"
    if destination_path.exists() and not overwrite:
        return "skipped_existing"
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return "copied"


def _write_manifest(output_dir: Path, rows: list[DownloadManifestRow]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = output_dir / f"satellite_download_manifest_{timestamp}.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(_manifest_dict(row) for row in rows)
    return manifest_path


def _manifest_dict(row: DownloadManifestRow) -> dict[str, str]:
    metadata = row.metadata
    return {
        "status": row.status,
        "source_folder": row.source_folder,
        "source_path": str(row.source_path),
        "destination_path": "" if row.destination_path is None else str(row.destination_path),
        "matched_geojson": row.matched_geojson,
        "filename_format_matched": "yes" if metadata.matched_format else "no",
        "filename_format_rule": metadata.matched_format_name or "",
        "capture_datetime": (
            metadata.capture_datetime.isoformat(sep=" ") if metadata.capture_datetime else ""
        ),
        "cloud_percent": "" if metadata.cloud_percent is None else f"{metadata.cloud_percent:g}",
        "max_cloud_percent": (
            "" if metadata.max_cloud_percent is None else f"{metadata.max_cloud_percent:g}"
        ),
        "error": row.error,
    }


def _accepted_row(
    prepared: PreparedDownloadImage,
    *,
    status: str,
    source_folder: DownloadImageFolder,
    destination_path: Path,
    matched_geojson: str,
    error: str,
) -> DownloadManifestRow:
    return DownloadManifestRow(
        status=status,
        source_folder=source_folder.name,
        source_path=prepared.match.path,
        destination_path=destination_path,
        matched_geojson=matched_geojson,
        metadata=prepared.metadata,
        error=error,
    )


def _skipped_cloud_rows(
    skipped_images: tuple[SkippedCloudDownloadImage | SkippedCloudDownloadCandidate, ...],
    source_folders: dict[Path, DownloadImageFolder],
    geojson_names: dict[Path, str],
) -> list[DownloadManifestRow]:
    rows: list[DownloadManifestRow] = []
    for skipped in skipped_images:
        if isinstance(skipped, SkippedCloudDownloadCandidate):
            source_folder = _source_folder_for_path(skipped.source_folder, source_folders)
            rows.append(
                DownloadManifestRow(
                    status=skipped.status,
                    source_folder=source_folder.name,
                    source_path=skipped.path,
                    destination_path=None,
                    matched_geojson="",
                    metadata=skipped.metadata,
                    error=skipped.reason,
                )
            )
            continue
        source_folder = _source_folder_for_path(skipped.match.source_folder, source_folders)
        for geojson_name, geojson_path in zip(
            skipped.match.matched_geojson_names,
            skipped.match.matched_geojson_paths,
            strict=True,
        ):
            rows.append(
                DownloadManifestRow(
                    status=skipped.status,
                    source_folder=source_folder.name,
                    source_path=skipped.match.path,
                    destination_path=None,
                    matched_geojson=_resolved_geojson_name(
                        geojson_name,
                        geojson_path,
                        geojson_names,
                    ),
                    metadata=skipped.metadata,
                    error=skipped.reason,
                )
            )
    return rows


def _skipped_existing_rows(
    skipped_images: tuple[SkippedExistingDownloadImage, ...],
    source_folders: dict[Path, DownloadImageFolder],
) -> list[DownloadManifestRow]:
    rows: list[DownloadManifestRow] = []
    for skipped in skipped_images:
        source_folder = _source_folder_for_path(skipped.source_folder, source_folders)
        rows.append(
            DownloadManifestRow(
                status=skipped.status,
                source_folder=source_folder.name,
                source_path=skipped.path,
                destination_path=skipped.existing_path,
                matched_geojson="",
                metadata=skipped.metadata,
                error=skipped.reason,
            )
        )
    return rows


def _failed_rows(
    failed_images: tuple,
    source_folders: dict[Path, DownloadImageFolder],
) -> list[DownloadManifestRow]:
    rows: list[DownloadManifestRow] = []
    for failed in failed_images:
        source_folder = _source_folder_for_path(failed.source_folder, source_folders)
        rows.append(
            DownloadManifestRow(
                status="failed",
                source_folder=source_folder.name,
                source_path=failed.path,
                destination_path=None,
                matched_geojson="",
                metadata=DownloadFilenameMetadata(matched_format=False),
                error=failed.error,
            )
        )
    return rows


def _source_folders_by_path(
    image_folders: tuple[DownloadImageFolder, ...],
) -> dict[Path, DownloadImageFolder]:
    return {folder.path.resolve(): folder for folder in image_folders}


def _geojson_names_by_path(geojson_files: tuple[Path, ...]) -> dict[Path, str]:
    used_names: set[str] = set()
    names: dict[Path, str] = {}
    for path in geojson_files:
        names[path.resolve()] = unique_name(safe_name(path.stem), used_names)
    return names


def _resolved_source_folder(
    prepared: PreparedDownloadImage,
    source_folders: dict[Path, DownloadImageFolder],
) -> DownloadImageFolder:
    return _source_folder_for_path(prepared.match.source_folder, source_folders)


def _source_folder_for_path(
    source_folder: DownloadImageFolder,
    source_folders: dict[Path, DownloadImageFolder],
) -> DownloadImageFolder:
    return source_folders.get(source_folder.path.resolve(), source_folder)


def _resolved_geojson_name(
    matched_name: str,
    matched_path: Path,
    geojson_names: dict[Path, str],
) -> str:
    return geojson_names.get(matched_path.resolve(), safe_name(matched_name))
