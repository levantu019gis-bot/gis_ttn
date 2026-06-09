#!/usr/bin/env python3
"""Download/copy satellite GeoTIFFs that intersect GeoJSON areas of interest.

The script is intentionally config-driven so it can run from a local machine or
another LAN workstation without installing anything on the imagery server.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import rasterio
from rasterio.crs import CRS
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_geom
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


DEFAULT_EXTENSIONS = {".tif", ".tiff"}


class ConfigError(ValueError):
    """Raised when the run configuration is missing or invalid."""


@dataclass(frozen=True)
class ImageFolder:
    name: str
    path: Path


@dataclass(frozen=True)
class GeoJsonArea:
    name: str
    path: Path
    geometry: BaseGeometry


@dataclass(frozen=True)
class RasterCandidate:
    source: ImageFolder
    path: Path


@dataclass(frozen=True)
class FilenameFormatRule:
    name: str
    raw_format: str
    pattern: re.Pattern[str]
    max_cloud_percent: float | None


@dataclass(frozen=True)
class FilenameMetadata:
    matched_format: bool
    matched_format_name: str | None = None
    cloud_percent: float | None = None
    capture_datetime: datetime | None = None
    max_cloud_percent: float | None = None


@dataclass(frozen=True)
class RunConfig:
    geojson_dir: Path | None
    geojson_files: list[Path]
    image_folders: list[ImageFolder]
    output_dir: Path
    geojson_crs: str | None
    extensions: set[str]
    preserve_source_tree: bool
    overwrite: bool
    dry_run: bool
    include_boundary_touch: bool
    write_manifest: bool
    filename_formats: list[FilenameFormatRule]


@dataclass
class RunStats:
    total_images: int = 0
    scanned_images: int = 0
    matched_images: int = 0
    downloaded_images: int = 0
    skipped_existing: int = 0
    skipped_cloud: int = 0
    failed_images: int = 0
    geojson_count: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy satellite GeoTIFF files from LAN folders when their raster bounds "
            "intersect configured GeoJSON AOIs."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("scripts/satellite_download_config.json"),
        help="Path to the JSON config file.",
    )
    return parser.parse_args()


def load_json_config(config_path: Path) -> dict[str, Any]:
    if not config_path:
        raise ConfigError("Chưa cung cấp file config. Dùng: --config <duong_dan_config.json>")
    if not config_path.is_file():
        raise ConfigError(f"Không tìm thấy file config: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"File config không phải JSON hợp lệ: {config_path} "
            f"(dòng {exc.lineno}, cột {exc.colno}: {exc.msg})"
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Không đọc được file config {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Config phải là một JSON object ở cấp gốc.")
    return data


def resolve_config_path(config_path: Path, raw_path: str | None, field_name: str) -> Path | None:
    if raw_path is None or raw_path == "":
        return None
    if not isinstance(raw_path, str):
        raise ConfigError(f"`{field_name}` phải là chuỗi đường dẫn.")

    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()


def bool_field(data: dict[str, Any], name: str, default: bool) -> bool:
    value = data.get(name, default)
    if not isinstance(value, bool):
        raise ConfigError(f"`{name}` phải là true hoặc false.")
    return value


def string_list_field(data: dict[str, Any], name: str) -> list[str]:
    value = data.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigError(f"`{name}` phải là danh sách chuỗi.")
    return value


def optional_float_field(data: dict[str, Any], name: str) -> float | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"`{name}` phải là số hoặc null.")
    return float(value)


def load_run_config(config_path: Path) -> RunConfig:
    data = load_json_config(config_path)

    geojson_dir = resolve_config_path(config_path, data.get("geojson_dir"), "geojson_dir")
    geojson_files = [
        path
        for item in string_list_field(data, "geojson_files")
        if (path := resolve_config_path(config_path, item, "geojson_files")) is not None
    ]

    raw_image_folders = data.get("image_folders")
    if not isinstance(raw_image_folders, list) or not raw_image_folders:
        raise ConfigError("Chưa cung cấp `image_folders`. Cần ít nhất 1 folder ảnh đầu vào.")

    image_folders: list[ImageFolder] = []
    used_names: set[str] = set()
    for index, item in enumerate(raw_image_folders, start=1):
        if not isinstance(item, str):
            raise ConfigError(
                f"`image_folders[{index}]` phải là chuỗi đường dẫn, ví dụ "
                '`"//192.168.100.234/data/satellite_image"`.'
            )

        folder_path = resolve_config_path(config_path, item, f"image_folders[{index}]")
        if folder_path is None:
            raise ConfigError(f"Thiếu đường dẫn `image_folders[{index}]`.")

        name = unique_name(safe_name(folder_path.name or f"source_{index}"), used_names)
        image_folders.append(ImageFolder(name=name, path=folder_path))

    output_dir = resolve_config_path(config_path, data.get("output_dir"), "output_dir")
    if output_dir is None:
        raise ConfigError("Chưa cung cấp `output_dir` trong config.")

    explicit_crs = data.get("geojson_crs")
    if explicit_crs is not None and not isinstance(explicit_crs, str):
        raise ConfigError("`geojson_crs` phải là chuỗi, ví dụ `EPSG:4326`, hoặc null.")
    if explicit_crs:
        try:
            CRS.from_user_input(explicit_crs)
        except Exception as exc:
            raise ConfigError(f"`geojson_crs` không hợp lệ: {explicit_crs}") from exc

    extensions = {item.lower() for item in string_list_field(data, "extensions")}
    if not extensions:
        extensions = set(DEFAULT_EXTENSIONS)
    invalid_extensions = [item for item in extensions if not item.startswith(".")]
    if invalid_extensions:
        raise ConfigError(
            "`extensions` phải gồm các phần mở rộng bắt đầu bằng dấu chấm, ví dụ `.tif`."
        )

    filename_formats = load_filename_format_rules(data)

    return RunConfig(
        geojson_dir=geojson_dir,
        geojson_files=geojson_files,
        image_folders=image_folders,
        output_dir=output_dir,
        geojson_crs=explicit_crs,
        extensions=extensions,
        preserve_source_tree=bool_field(data, "preserve_source_tree", True),
        overwrite=bool_field(data, "overwrite", False),
        dry_run=bool_field(data, "dry_run", False),
        include_boundary_touch=bool_field(data, "include_boundary_touch", True),
        write_manifest=bool_field(data, "write_manifest", True),
        filename_formats=filename_formats,
    )


def load_filename_format_rules(data: dict[str, Any]) -> list[FilenameFormatRule]:
    raw_rules = data.get("filename_formats")
    if raw_rules is None:
        legacy_rule = load_legacy_filename_format_rule(data)
        return [legacy_rule] if legacy_rule is not None else []

    if not isinstance(raw_rules, list):
        raise ConfigError("`filename_formats` phải là danh sách.")
    if data.get("filename_format") not in (None, "") or data.get("max_cloud_percent") is not None:
        raise ConfigError(
            "Không dùng đồng thời `filename_formats` với `filename_format`/`max_cloud_percent`."
        )

    rules: list[FilenameFormatRule] = []
    used_names: set[str] = set()
    for index, item in enumerate(raw_rules, start=1):
        if isinstance(item, str):
            raw_format = item
            max_cloud_percent = None
            raw_name = f"format_{index}"
        elif isinstance(item, dict):
            raw_format = item.get("format")
            raw_name = item.get("name") or f"format_{index}"
            max_cloud_percent = optional_float_field(item, "max_cloud_percent")
        else:
            raise ConfigError(
                f"`filename_formats[{index}]` phải là chuỗi format hoặc object có `format`."
            )

        if not isinstance(raw_format, str) or not raw_format:
            raise ConfigError(f"`filename_formats[{index}].format` phải là chuỗi không rỗng.")
        if not isinstance(raw_name, str) or not raw_name:
            raise ConfigError(f"`filename_formats[{index}].name` phải là chuỗi không rỗng.")

        rules.append(
            build_filename_format_rule(
                raw_format=raw_format,
                max_cloud_percent=max_cloud_percent,
                name=unique_name(safe_name(raw_name), used_names),
                field_name=f"filename_formats[{index}]",
            )
        )

    return rules


def load_legacy_filename_format_rule(data: dict[str, Any]) -> FilenameFormatRule | None:
    raw_format = data.get("filename_format")
    max_cloud_percent = optional_float_field(data, "max_cloud_percent")

    if raw_format is None or raw_format == "":
        if max_cloud_percent is not None:
            raise ConfigError("`max_cloud_percent` chỉ dùng được khi có `filename_format`.")
        return None
    if not isinstance(raw_format, str):
        raise ConfigError("`filename_format` phải là chuỗi hoặc null.")

    return build_filename_format_rule(
        raw_format=raw_format,
        max_cloud_percent=max_cloud_percent,
        name="legacy_format",
        field_name="filename_format",
    )


def build_filename_format_rule(
    *,
    raw_format: str,
    max_cloud_percent: float | None,
    name: str,
    field_name: str,
) -> FilenameFormatRule:
    if "cloud-percent" not in raw_format and "cloud_percent" not in raw_format:
        raise ConfigError(
            f"`{field_name}` phải chứa token `cloud-percent` hoặc `cloud_percent` "
            "để trích xuất độ phủ mây."
        )
    if max_cloud_percent is not None and not 0 <= max_cloud_percent <= 100:
        raise ConfigError(f"`{field_name}.max_cloud_percent` phải nằm trong khoảng 0..100.")

    return FilenameFormatRule(
        name=name,
        raw_format=raw_format,
        pattern=compile_filename_format(raw_format),
        max_cloud_percent=max_cloud_percent,
    )


def compile_filename_format(raw_format: str) -> re.Pattern[str]:
    tokens = [
        ("cloud-percent", r"(?P<cloud_percent>\d+(?:\.\d+)?)"),
        ("cloud_percent", r"(?P<cloud_percent>\d+(?:\.\d+)?)"),
        ("yyyyMMdd", r"(?P<date>\d{8})"),
        ("hhMMss", r"(?P<time>\d{6})"),
        ("*", ".*"),
    ]
    parts: list[str] = []
    index = 0
    while index < len(raw_format):
        for token, replacement in tokens:
            if raw_format.startswith(token, index):
                parts.append(replacement)
                index += len(token)
                break
        else:
            parts.append(re.escape(raw_format[index]))
            index += 1

    regex = "".join(parts)
    try:
        return re.compile(f"^{regex}$")
    except re.error as exc:
        raise ConfigError(f"Filename format không thể chuyển thành regex hợp lệ: {exc}") from exc


def filename_format_warnings(rules: list[FilenameFormatRule]) -> list[str]:
    warnings: list[str] = []
    for earlier_index, earlier in enumerate(rules):
        for later in rules[earlier_index + 1 :]:
            sample = sample_filename_from_format(later.raw_format)
            if earlier.pattern.match(sample) and later.pattern.match(sample):
                warnings.append(
                    f"Rule `{earlier.name}` có thể match trước và che rule `{later.name}`. "
                    "Nếu rule sau cần ngưỡng mây riêng, hãy đặt rule sau lên trước."
                )
    return warnings


def sample_filename_from_format(raw_format: str) -> str:
    tokens = [
        ("cloud-percent", "10"),
        ("cloud_percent", "10"),
        ("yyyyMMdd", "20260102"),
        ("hhMMss", "030405"),
        ("*", "X"),
    ]
    parts: list[str] = []
    index = 0
    while index < len(raw_format):
        for token, replacement in tokens:
            if raw_format.startswith(token, index):
                parts.append(replacement)
                index += len(token)
                break
        else:
            parts.append(raw_format[index])
            index += 1
    return "".join(parts)


def safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in value.strip())
    return cleaned.strip("._") or "source"


def unique_name(name: str, used_names: set[str]) -> str:
    candidate = name
    suffix = 2
    while candidate in used_names:
        candidate = f"{name}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def validate_paths(config: RunConfig) -> None:
    if config.geojson_dir is None and not config.geojson_files:
        raise ConfigError("Chưa cung cấp `geojson_dir` hoặc `geojson_files` trong config.")

    if config.geojson_dir is not None and not config.geojson_dir.is_dir():
        raise ConfigError(f"Folder GeoJSON không tồn tại hoặc không phải thư mục: {config.geojson_dir}")

    for geojson_file in config.geojson_files:
        if not geojson_file.is_file():
            raise ConfigError(f"File GeoJSON không tồn tại: {geojson_file}")

    for image_folder in config.image_folders:
        if not image_folder.path.is_dir():
            raise ConfigError(
                f"Folder ảnh đầu vào không tồn tại hoặc không phải thư mục "
                f"({image_folder.name}): {image_folder.path}"
            )

    output_dir = config.output_dir.resolve()
    for image_folder in config.image_folders:
        source_dir = image_folder.path.resolve()
        if output_dir == source_dir or output_dir.is_relative_to(source_dir):
            raise ConfigError(
                "Không đặt `output_dir` trùng hoặc nằm bên trong folder ảnh đầu vào: "
                f"{config.output_dir}"
            )


def discover_geojson_files(config: RunConfig) -> list[Path]:
    files: list[Path] = []
    if config.geojson_dir is not None:
        files.extend(sorted(config.geojson_dir.glob("*.geojson")))
        files.extend(sorted(config.geojson_dir.glob("*.json")))
    files.extend(config.geojson_files)

    unique_files: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(path)

    if not unique_files:
        raise ConfigError("Không tìm thấy file GeoJSON nào trong cấu hình.")
    return unique_files


def read_geojson_crs(data: dict[str, Any], explicit_crs: str | None) -> CRS:
    if explicit_crs:
        return CRS.from_user_input(explicit_crs)

    crs_info = data.get("crs")
    if isinstance(crs_info, dict):
        properties = crs_info.get("properties") or {}
        name = properties.get("name")
        if name:
            return CRS.from_user_input(name)

    return CRS.from_epsg(4326)


def extract_geometries(data: dict[str, Any], geojson_path: Path) -> list[BaseGeometry]:
    data_type = data.get("type")

    if data_type == "FeatureCollection":
        raw_geometries = [
            feature.get("geometry")
            for feature in data.get("features", [])
            if isinstance(feature, dict) and feature.get("geometry")
        ]
    elif data_type == "Feature":
        raw_geometries = [data.get("geometry")]
    else:
        raw_geometries = [data]

    geometries: list[BaseGeometry] = []
    for index, raw_geometry in enumerate(raw_geometries, start=1):
        if not raw_geometry:
            continue
        try:
            geometry = shape(raw_geometry)
        except Exception as exc:
            raise ConfigError(f"Geometry lỗi trong {geojson_path} tại item #{index}: {exc}") from exc
        if geometry.is_empty:
            continue
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if not geometry.is_empty:
            geometries.append(geometry)

    return geometries


def load_geojson_areas(geojson_files: list[Path], explicit_crs: str | None) -> tuple[list[GeoJsonArea], CRS]:
    areas: list[GeoJsonArea] = []
    detected_crs: CRS | None = None

    for geojson_path in geojson_files:
        try:
            with geojson_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"File GeoJSON không phải JSON hợp lệ: {geojson_path} "
                f"(dòng {exc.lineno}, cột {exc.colno}: {exc.msg})"
            ) from exc
        except OSError as exc:
            raise ConfigError(f"Không đọc được GeoJSON {geojson_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"GeoJSON phải là JSON object: {geojson_path}")

        current_crs = read_geojson_crs(data, explicit_crs)
        if detected_crs is None:
            detected_crs = current_crs
        elif current_crs != detected_crs:
            raise ConfigError(
                "Các file GeoJSON đang dùng CRS khác nhau. Hãy đặt `geojson_crs` "
                "trong config để ép cùng một CRS."
            )

        geometries = extract_geometries(data, geojson_path)
        if not geometries:
            raise ConfigError(f"Không có geometry hợp lệ trong GeoJSON: {geojson_path}")

        areas.append(
            GeoJsonArea(
                name=safe_name(geojson_path.stem),
                path=geojson_path,
                geometry=unary_union(geometries),
            )
        )

    if detected_crs is None:
        raise ConfigError("Không xác định được CRS GeoJSON.")
    return areas, detected_crs


def discover_rasters(config: RunConfig) -> list[RasterCandidate]:
    candidates: list[RasterCandidate] = []
    for image_folder in config.image_folders:
        print(f"[DISCOVER] Đang đếm ảnh trong {image_folder.name}: {image_folder.path}")
        folder_count = 0
        try:
            for path in image_folder.path.rglob("*"):
                if path.is_file() and path.suffix.lower() in config.extensions:
                    candidates.append(RasterCandidate(source=image_folder, path=path))
                    folder_count += 1
        except OSError as exc:
            raise ConfigError(
                f"Không scan được folder ảnh ({image_folder.name}): {image_folder.path} | {exc}"
            ) from exc
        print(f"[DISCOVER] {image_folder.name}: {folder_count} ảnh")

    if not candidates:
        raise ConfigError("Không tìm thấy ảnh phù hợp với `extensions` trong các folder input.")
    return candidates


def parse_filename_metadata(
    path: Path,
    rules: list[FilenameFormatRule],
) -> FilenameMetadata:
    for rule in rules:
        match = rule.pattern.match(path.name)
        if match is not None:
            return metadata_from_match(match, rule)

    return FilenameMetadata(matched_format=False)


def metadata_from_match(match: re.Match[str], rule: FilenameFormatRule) -> FilenameMetadata:
    cloud_percent = float(match.group("cloud_percent"))
    capture_datetime = None
    date_text = match.groupdict().get("date")
    time_text = match.groupdict().get("time")
    if date_text and time_text:
        try:
            capture_datetime = datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M%S")
        except ValueError:
            capture_datetime = None

    return FilenameMetadata(
        matched_format=True,
        matched_format_name=rule.name,
        cloud_percent=cloud_percent,
        capture_datetime=capture_datetime,
        max_cloud_percent=rule.max_cloud_percent,
    )


def should_skip_for_cloud(metadata: FilenameMetadata) -> bool:
    if (
        not metadata.matched_format
        or metadata.cloud_percent is None
        or metadata.max_cloud_percent is None
    ):
        return False
    return metadata.cloud_percent > metadata.max_cloud_percent


def transform_geometry(
    geometry: BaseGeometry,
    source_crs: CRS,
    target_crs: CRS | None,
    cache: dict[str, BaseGeometry],
    cache_key_prefix: str,
) -> BaseGeometry:
    if target_crs is None or target_crs == source_crs:
        return geometry

    cache_key = f"{cache_key_prefix}:{target_crs.to_string()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    transformed = shape(transform_geom(source_crs, target_crs, geometry.__geo_interface__))
    if not transformed.is_valid:
        transformed = transformed.buffer(0)
    cache[cache_key] = transformed
    return transformed


def intersects_geometry(
    raster_bounds: BaseGeometry,
    geometry: BaseGeometry,
    include_boundary_touch: bool,
) -> bool:
    intersects = raster_bounds.intersects(geometry)
    if intersects and not include_boundary_touch:
        return raster_bounds.intersection(geometry).area > 0
    return intersects


def destination_for(candidate: RasterCandidate, config: RunConfig) -> Path:
    if config.preserve_source_tree:
        return config.output_dir / candidate.source.name / candidate.path.relative_to(candidate.source.path)
    return config.output_dir / candidate.source.name / candidate.path.name


def copy_file(source_path: Path, destination_path: Path, overwrite: bool, dry_run: bool) -> str:
    if dry_run:
        return "dry_run"

    if destination_path.exists() and not overwrite:
        return "skipped_existing"

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return "copied"


def write_manifest(output_dir: Path, rows: list[dict[str, str]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = output_dir / f"satellite_download_manifest_{timestamp}.csv"
    fieldnames = [
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
    ]
    try:
        with manifest_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        raise ConfigError(f"Không ghi được manifest {manifest_path}: {exc}") from exc
    return manifest_path


def run(config: RunConfig) -> RunStats:
    validate_paths(config)
    geojson_files = discover_geojson_files(config)
    areas, geojson_crs = load_geojson_areas(geojson_files, config.geojson_crs)
    candidates = discover_rasters(config)

    stats = RunStats(total_images=len(candidates), geojson_count=len(areas))
    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"Không tạo được output_dir {config.output_dir}: {exc}") from exc

    print("[CONFIG] GeoJSON folder/files OK")
    print(f"[CONFIG] Số GeoJSON: {stats.geojson_count}")
    print(f"[CONFIG] Số folder ảnh: {len(config.image_folders)}")
    print(f"[CONFIG] Output: {config.output_dir}")
    if config.filename_formats:
        print(f"[CONFIG] Số filename format: {len(config.filename_formats)}")
        for rule in config.filename_formats:
            if rule.max_cloud_percent is None:
                print(f"[CONFIG] - {rule.name}: {rule.raw_format} | không lọc mây")
            else:
                print(
                    f"[CONFIG] - {rule.name}: {rule.raw_format} "
                    f"| cloud_percent <= {rule.max_cloud_percent:g}"
                )
        for warning in filename_format_warnings(config.filename_formats):
            print(f"[WARN] {warning}", file=sys.stderr)
    print(f"[SCAN] Tổng số ảnh cần scan: {stats.total_images}")

    union_geometry = unary_union([area.geometry for area in areas])
    geometry_cache: dict[str, BaseGeometry] = {}
    manifest_rows: list[dict[str, str]] = []

    for candidate in candidates:
        stats.scanned_images += 1
        prefix = progress_prefix(stats)
        metadata = parse_filename_metadata(candidate.path, config.filename_formats)

        if should_skip_for_cloud(metadata):
            stats.skipped_cloud += 1
            print(
                f"{progress_prefix(stats)} | skipped_cloud=1 "
                f"| rule={metadata.matched_format_name} "
                f"| cloud={metadata.cloud_percent:g} > {metadata.max_cloud_percent:g} "
                f"| {candidate.path}"
            )
            manifest_rows.append(
                manifest_row(
                    status="skipped_cloud",
                    candidate=candidate,
                    destination_path=None,
                    matched_areas=[],
                    metadata=metadata,
                    error="",
                )
            )
            continue

        try:
            with rasterio.open(candidate.path) as dataset:
                if dataset.crs is None:
                    raise ValueError("Ảnh không có CRS; không thể so sánh với GeoJSON.")
                raster_bounds = box(*dataset.bounds)
                comparable_union = transform_geometry(
                    union_geometry,
                    geojson_crs,
                    dataset.crs,
                    geometry_cache,
                    "union",
                )
                if not intersects_geometry(
                    raster_bounds,
                    comparable_union,
                    config.include_boundary_touch,
                ):
                    print(f"{prefix} | match=0 | {candidate.path}")
                    continue

                matched_areas = []
                for area in areas:
                    comparable_area = transform_geometry(
                        area.geometry,
                        geojson_crs,
                        dataset.crs,
                        geometry_cache,
                        area.name,
                    )
                    if intersects_geometry(
                        raster_bounds,
                        comparable_area,
                        config.include_boundary_touch,
                    ):
                        matched_areas.append(area.name)
        except (RasterioIOError, ValueError, OSError) as exc:
            stats.failed_images += 1
            print(f"{progress_prefix(stats)} | ERROR đọc ảnh: {candidate.path} | {exc}", file=sys.stderr)
            manifest_rows.append(
                manifest_row(
                    status="failed",
                    candidate=candidate,
                    destination_path=None,
                    matched_areas=[],
                    metadata=metadata,
                    error=str(exc),
                )
            )
            continue

        stats.matched_images += 1
        destination_path = destination_for(candidate, config)

        try:
            status = copy_file(
                candidate.path,
                destination_path,
                overwrite=config.overwrite,
                dry_run=config.dry_run,
            )
        except OSError as exc:
            stats.failed_images += 1
            print(
                f"{progress_prefix(stats)} | ERROR tải ảnh: "
                f"{candidate.path} -> {destination_path} | {exc}"
            )
            manifest_rows.append(
                manifest_row(
                    status="failed",
                    candidate=candidate,
                    destination_path=destination_path,
                    matched_areas=matched_areas,
                    metadata=metadata,
                    error=str(exc),
                )
            )
            continue

        if status == "copied":
            stats.downloaded_images += 1
        elif status == "skipped_existing":
            stats.skipped_existing += 1

        print(
            f"{progress_prefix(stats)} | match=1 | status={status} | "
            f"{candidate.path} -> {destination_path}"
        )
        manifest_rows.append(
            manifest_row(
                status=status,
                candidate=candidate,
                destination_path=destination_path,
                matched_areas=matched_areas,
                metadata=metadata,
                error="",
            )
        )

    if config.write_manifest:
        manifest_path = write_manifest(config.output_dir, manifest_rows)
        print(f"[MANIFEST] Đã ghi manifest: {manifest_path}")

    return stats


def progress_prefix(stats: RunStats) -> str:
    return (
        f"[SCAN] {stats.scanned_images}/{stats.total_images} "
        f"| matched={stats.matched_images} "
        f"| downloaded={stats.downloaded_images} "
        f"| skipped={stats.skipped_existing} "
        f"| skipped_cloud={stats.skipped_cloud} "
        f"| failed={stats.failed_images}"
    )


def manifest_row(
    *,
    status: str,
    candidate: RasterCandidate,
    destination_path: Path | None,
    matched_areas: list[str],
    metadata: FilenameMetadata,
    error: str,
) -> dict[str, str]:
    return {
        "status": status,
        "source_folder": candidate.source.name,
        "source_path": str(candidate.path),
        "destination_path": str(destination_path or ""),
        "matched_geojson": ";".join(matched_areas),
        "filename_format_matched": "yes" if metadata.matched_format else "no",
        "filename_format_rule": metadata.matched_format_name or "",
        "capture_datetime": (
            metadata.capture_datetime.isoformat(sep=" ") if metadata.capture_datetime else ""
        ),
        "cloud_percent": "" if metadata.cloud_percent is None else f"{metadata.cloud_percent:g}",
        "max_cloud_percent": (
            "" if metadata.max_cloud_percent is None else f"{metadata.max_cloud_percent:g}"
        ),
        "error": error,
    }


def main() -> int:
    args = parse_args()
    try:
        config = load_run_config(args.config)
        stats = run(config)
    except ConfigError as exc:
        print(f"[ERROR] Lỗi cấu hình: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[ERROR] Người dùng đã dừng tiến trình.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[ERROR] Lỗi không mong muốn: {exc}", file=sys.stderr)
        return 1

    print(
        "[DONE] Hoàn tất | "
        f"total={stats.total_images} | "
        f"scanned={stats.scanned_images} | "
        f"matched={stats.matched_images} | "
        f"downloaded={stats.downloaded_images} | "
        f"skipped_existing={stats.skipped_existing} | "
        f"skipped_cloud={stats.skipped_cloud} | "
        f"failed={stats.failed_images}"
    )
    return 1 if stats.failed_images else 0


if __name__ == "__main__":
    raise SystemExit(main())
