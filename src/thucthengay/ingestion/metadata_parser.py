"""Business metadata extraction for source GeoTIFF imagery."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from thucthengay.models import FilenamePatternConfig, MetadataSource

_PLANETSCOPE_PREFIX_RE = re.compile(
    r"^(?P<date>\d{8})[_-](?P<time>\d{6})(?:[_-](?P<rest>.+))?$"
)
_CLOUD_TOKEN_RE = re.compile(
    r"(?:cloud(?:[_-]?cover)?|cc)[_-]?(?P<value>\d+(?:\.\d+)?)p?",
    re.IGNORECASE,
)
_FILENAME_UTC_TO_LOCAL_OFFSET = timedelta(hours=7)


@dataclass(frozen=True)
class ParsedBusinessMetadata:
    """Business metadata parsed from filename, sidecar, or embedded tags."""

    capture_date: date | None = None
    capture_time: time | None = None
    cloud_percent: float | None = None
    source_identifier: str | None = None
    field_sources: dict[str, MetadataSource] = field(default_factory=dict)

    @property
    def primary_source(self) -> MetadataSource:
        for source in (MetadataSource.SIDECAR, MetadataSource.FILENAME, MetadataSource.EMBEDDED):
            if source in self.field_sources.values():
                return source
        return MetadataSource.UNKNOWN


def parse_business_metadata(
    geotiff_path: Path,
    *,
    embedded_tags: dict[str, Any] | None = None,
    filename_patterns: list[FilenamePatternConfig] | None = None,
) -> ParsedBusinessMetadata:
    """Parse layer business metadata with sidecar > filename > embedded precedence."""
    candidates = [
        _parse_sidecar_metadata(geotiff_path),
        _parse_filename_metadata(geotiff_path, filename_patterns=filename_patterns),
        _parse_mapping_metadata(embedded_tags or {}, MetadataSource.EMBEDDED),
    ]

    capture_date = _first_present(candidates, "capture_date")
    capture_time = _first_present(candidates, "capture_time")
    cloud_percent = _first_present(candidates, "cloud_percent")
    source_identifier = _first_present(candidates, "source_identifier")

    field_sources: dict[str, MetadataSource] = {}
    for field_name, value in (
        ("capture_date", capture_date),
        ("capture_time", capture_time),
        ("cloud_percent", cloud_percent),
        ("source_identifier", source_identifier),
    ):
        if value is None:
            continue
        source = _source_for_field(candidates, field_name)
        if source is not None:
            field_sources[field_name] = source

    return ParsedBusinessMetadata(
        capture_date=capture_date,
        capture_time=capture_time,
        cloud_percent=cloud_percent,
        source_identifier=source_identifier,
        field_sources=field_sources,
    )


def _parse_filename_metadata(
    path: Path,
    *,
    filename_patterns: list[FilenamePatternConfig] | None = None,
) -> ParsedBusinessMetadata:
    if filename_patterns:
        for pattern in filename_patterns:
            result = _try_pattern_match(path.stem, pattern)
            if result.field_sources:
                return result

    match = _PLANETSCOPE_PREFIX_RE.match(path.stem)
    capture_date: date | None = None
    capture_time: time | None = None
    field_sources: dict[str, MetadataSource] = {}

    if match:
        capture_date, capture_time = _filename_utc_to_local_capture(
            datetime.strptime(match.group("date"), "%Y%m%d").date(),
            datetime.strptime(match.group("time"), "%H%M%S").time(),
        )
        field_sources["capture_date"] = MetadataSource.FILENAME
        field_sources["capture_time"] = MetadataSource.FILENAME

    cloud_percent = _parse_cloud_from_text(path.stem)
    if cloud_percent is not None:
        field_sources["cloud_percent"] = MetadataSource.FILENAME

    source_identifier = path.stem if match else None
    if source_identifier:
        field_sources["source_identifier"] = MetadataSource.FILENAME

    return ParsedBusinessMetadata(
        capture_date=capture_date,
        capture_time=capture_time,
        cloud_percent=cloud_percent,
        source_identifier=source_identifier,
        field_sources=field_sources,
    )


def _try_pattern_match(
    stem: str, pattern: FilenamePatternConfig
) -> ParsedBusinessMetadata:
    parts = stem.split(pattern.separator)
    tokens = pattern.pattern.split(pattern.separator)
    if len(parts) != len(tokens):
        return ParsedBusinessMetadata()

    capture_date: date | None = None
    capture_time: time | None = None
    cloud_percent: float | None = None
    field_sources: dict[str, MetadataSource] = {}

    for part, token in zip(parts, tokens, strict=True):
        if token == "yyyyMMdd":
            try:
                capture_date = datetime.strptime(part, "%Y%m%d").date()
                field_sources["capture_date"] = MetadataSource.FILENAME
            except ValueError:
                return ParsedBusinessMetadata()
        elif token == "HHmmss":
            try:
                capture_time = datetime.strptime(part, "%H%M%S").time()
                field_sources["capture_time"] = MetadataSource.FILENAME
            except ValueError:
                return ParsedBusinessMetadata()
        elif token == "cloud-percent":
            parsed = _parse_cloud_value(part)
            if parsed is not None:
                cloud_percent = parsed
                field_sources["cloud_percent"] = MetadataSource.FILENAME
        elif token == "*":
            continue
        elif token != part:
            return ParsedBusinessMetadata()

    source_identifier = stem if field_sources else None
    if source_identifier:
        field_sources["source_identifier"] = MetadataSource.FILENAME
    if capture_date is not None and capture_time is not None:
        capture_date, capture_time = _filename_utc_to_local_capture(
            capture_date,
            capture_time,
        )

    return ParsedBusinessMetadata(
        capture_date=capture_date,
        capture_time=capture_time,
        cloud_percent=cloud_percent,
        source_identifier=source_identifier,
        field_sources=field_sources,
    )


def _parse_sidecar_metadata(path: Path) -> ParsedBusinessMetadata:
    for sidecar_path in _candidate_sidecars(path):
        if not sidecar_path.is_file():
            continue
        try:
            raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError):
            continue
        if isinstance(raw, dict):
            parsed = _parse_mapping_metadata(raw, MetadataSource.SIDECAR)
            if parsed.field_sources:
                return parsed
    return ParsedBusinessMetadata()


def _parse_mapping_metadata(raw: dict[str, Any], source: MetadataSource) -> ParsedBusinessMetadata:
    flattened = _flatten_metadata(raw)

    capture_dt = _parse_datetime_value(
        _first_key(
            flattened,
            "capture_datetime",
            "acquired",
            "published",
            "datetime",
            "timestamp",
        )
    )
    capture_date = capture_dt.date() if capture_dt else _parse_date_value(
        _first_key(flattened, "capture_date", "date")
    )
    capture_time = capture_dt.time().replace(tzinfo=None) if capture_dt else _parse_time_value(
        _first_key(flattened, "capture_time", "time")
    )
    cloud_percent = _parse_cloud_value(
        _first_key(
            flattened,
            "cloud_percent",
            "cloud_cover_percent",
            "cloud_cover",
            "cloud",
        )
    )
    source_identifier = _parse_text_value(
        _first_key(flattened, "source_id", "source_identifier", "item_id", "satellite_id")
    )

    field_sources: dict[str, MetadataSource] = {}
    if capture_date is not None:
        field_sources["capture_date"] = source
    if capture_time is not None:
        field_sources["capture_time"] = source
    if cloud_percent is not None:
        field_sources["cloud_percent"] = source
    if source_identifier:
        field_sources["source_identifier"] = source

    return ParsedBusinessMetadata(
        capture_date=capture_date,
        capture_time=capture_time,
        cloud_percent=cloud_percent,
        source_identifier=source_identifier,
        field_sources=field_sources,
    )


def _filename_utc_to_local_capture(capture_date: date, capture_time: time) -> tuple[date, time]:
    local_dt = datetime.combine(capture_date, capture_time) + _FILENAME_UTC_TO_LOCAL_OFFSET
    return local_dt.date(), local_dt.time()


def _candidate_sidecars(path: Path) -> tuple[Path, ...]:
    return (
        path.with_name(f"{path.name}.json"),
        path.with_suffix(".json"),
        path.with_name(f"{path.stem}.metadata.json"),
    )


def _flatten_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(raw)
    properties = raw.get("properties")
    if isinstance(properties, dict):
        flattened.update(properties)
    return {str(key).lower(): value for key, value in flattened.items()}


def _first_key(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in values and values[key] not in (None, ""):
            return values[key]
    return None


def _first_present(candidates: list[ParsedBusinessMetadata], field_name: str) -> Any:
    for candidate in candidates:
        value = getattr(candidate, field_name)
        if value is not None:
            return value
    return None


def _source_for_field(
    candidates: list[ParsedBusinessMetadata],
    field_name: str,
) -> MetadataSource | None:
    for candidate in candidates:
        if field_name in candidate.field_sources:
            return candidate.field_sources[field_name]
    return None


def _parse_datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _parse_date_value(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


def _parse_time_value(value: Any) -> time | None:
    if isinstance(value, time):
        return value
    if not isinstance(value, str):
        return None
    for time_format in ("%H:%M:%S", "%H%M%S"):
        try:
            return datetime.strptime(value.strip(), time_format).time()
        except ValueError:
            continue
    return None


def _parse_cloud_value(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().rstrip("%")
    try:
        cloud_percent = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= cloud_percent <= 1:
        cloud_percent *= 100
    if not 0 <= cloud_percent <= 100:
        return None
    return cloud_percent


def _parse_cloud_from_text(value: str) -> float | None:
    match = _CLOUD_TOKEN_RE.search(value)
    if not match:
        return None
    return _parse_cloud_value(match.group("value"))


def _parse_text_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
