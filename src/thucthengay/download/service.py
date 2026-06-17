"""Request validation for the satellite image download workflow."""

from __future__ import annotations

from pathlib import Path

from thucthengay.download.models import (
    DEFAULT_DOWNLOAD_EXTENSIONS,
    DownloadImageFolder,
    DownloadOutputStructure,
    ResolvedSatelliteDownloadRequest,
    SatelliteDownloadRequest,
)


class SatelliteDownloadConfigError(ValueError):
    """Raised when a download request is invalid before scanning starts."""

    def __init__(self, message: str, *, field_name: str | None = None) -> None:
        super().__init__(message)
        self.field_name = field_name


def resolve_download_request(
    request: SatelliteDownloadRequest,
) -> ResolvedSatelliteDownloadRequest:
    """Resolve and validate a raw satellite download request."""

    base_dir = Path(request.base_dir).expanduser().resolve() if request.base_dir else None
    geojson_files = _resolve_geojson_files(request.geojson_files, base_dir)
    image_folders = _resolve_image_folders(request.image_folders, base_dir)
    output_dir = _resolve_path(request.output_dir, base_dir).resolve()
    extensions = _normalize_extensions(request.extensions)
    output_structure = _normalize_output_structure(request.output_structure)
    _validate_output_location(output_dir, image_folders)

    return ResolvedSatelliteDownloadRequest(
        geojson_files=tuple(geojson_files),
        image_folders=tuple(image_folders),
        output_dir=output_dir,
        extensions=extensions,
        filename_formats=tuple(request.filename_formats),
        overwrite=bool(request.overwrite),
        dry_run=bool(request.dry_run),
        include_boundary_touch=bool(request.include_boundary_touch),
        preserve_source_tree=bool(request.preserve_source_tree),
        write_manifest=bool(request.write_manifest),
        scan_workers=_normalize_scan_workers(request.scan_workers),
        output_structure=output_structure,
    )


def safe_name(value: str) -> str:
    """Return filesystem-safe branch name matching the standalone script behavior."""

    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in value.strip())
    return cleaned.strip("._") or "source"


def unique_name(name: str, used_names: set[str]) -> str:
    """Return a unique branch name by appending numeric suffixes when needed."""

    candidate = name
    suffix = 2
    while candidate in used_names:
        candidate = f"{name}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def _resolve_geojson_files(raw_files: list[str | Path], base_dir: Path | None) -> list[Path]:
    if not raw_files:
        raise SatelliteDownloadConfigError(
            "Chưa chọn file GeoJSON đầu vào.",
            field_name="geojson_files",
        )

    resolved: list[Path] = []
    for index, raw_path in enumerate(raw_files, start=1):
        path = _resolve_path(raw_path, base_dir).resolve()
        if not path.is_file():
            raise SatelliteDownloadConfigError(
                f"File GeoJSON không tồn tại: {path}",
                field_name=f"geojson_files[{index}]",
            )
        if path.suffix.lower() not in {".geojson", ".json"}:
            raise SatelliteDownloadConfigError(
                f"File GeoJSON phải có phần mở rộng .geojson hoặc .json: {path}",
                field_name=f"geojson_files[{index}]",
            )
        resolved.append(path)
    return resolved


def _resolve_image_folders(
    raw_folders: list[str | Path],
    base_dir: Path | None,
) -> list[DownloadImageFolder]:
    if not raw_folders:
        raise SatelliteDownloadConfigError(
            "Chưa chọn folder ảnh đầu vào.",
            field_name="image_folders",
        )

    image_folders: list[DownloadImageFolder] = []
    used_names: set[str] = set()
    for index, raw_path in enumerate(raw_folders, start=1):
        path = _resolve_path(raw_path, base_dir).resolve()
        if not path.is_dir():
            raise SatelliteDownloadConfigError(
                f"Folder ảnh đầu vào không tồn tại hoặc không phải thư mục: {path}",
                field_name=f"image_folders[{index}]",
            )
        name = unique_name(safe_name(path.name or f"source_{index}"), used_names)
        image_folders.append(DownloadImageFolder(name=name, path=path))
    return image_folders


def _normalize_extensions(raw_extensions: list[str]) -> frozenset[str]:
    if not raw_extensions:
        return DEFAULT_DOWNLOAD_EXTENSIONS

    extensions: set[str] = set()
    for index, extension in enumerate(raw_extensions, start=1):
        normalized = extension.lower()
        if not normalized.startswith("."):
            raise SatelliteDownloadConfigError(
                f"`extensions[{index}]` phải bắt đầu bằng dấu chấm, ví dụ `.tif`.",
                field_name=f"extensions[{index}]",
            )
        extensions.add(normalized)
    return frozenset(extensions)


def _validate_output_location(
    output_dir: Path,
    image_folders: list[DownloadImageFolder],
) -> None:
    for image_folder in image_folders:
        source_dir = image_folder.path.resolve()
        if output_dir == source_dir or output_dir.is_relative_to(source_dir):
            raise SatelliteDownloadConfigError(
                "Không đặt output trong folder ảnh đầu vào hoặc trùng với folder ảnh đầu vào: "
                f"{output_dir}",
                field_name="output_dir",
            )


def _normalize_scan_workers(raw_value: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise SatelliteDownloadConfigError(
            "`scan_workers` phai la so nguyen duong.",
            field_name="scan_workers",
        ) from error
    if value < 1:
        raise SatelliteDownloadConfigError(
            "`scan_workers` phai lon hon hoac bang 1.",
            field_name="scan_workers",
        )
    return min(value, 16)


def _normalize_output_structure(
    raw_value: DownloadOutputStructure | str,
) -> DownloadOutputStructure:
    try:
        return DownloadOutputStructure(raw_value)
    except ValueError as error:
        allowed = ", ".join(item.value for item in DownloadOutputStructure)
        raise SatelliteDownloadConfigError(
            f"`output_structure` khong hop le. Gia tri hop le: {allowed}.",
            field_name="output_structure",
        ) from error


def _resolve_path(raw_path: str | Path, base_dir: Path | None) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute() or base_dir is None:
        return path
    return base_dir / path
