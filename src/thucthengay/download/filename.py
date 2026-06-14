"""Filename metadata parsing and cloud filtering for satellite downloads."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from re import Pattern

from thucthengay.download.models import (
    DownloadFilenameFilterResult,
    DownloadFilenameFormatRule,
    DownloadFilenameMetadata,
    DownloadMatchResult,
    DownloadStats,
    PreparedDownloadImage,
    SkippedCloudDownloadCandidate,
    SkippedCloudDownloadImage,
)
from thucthengay.download.service import SatelliteDownloadConfigError

DownloadFilenameProgress = Callable[[DownloadStats, str], None]
Checkpoint = Callable[[], None]

_FORMAT_TOKENS = (
    ("cloud-percent", r"(?P<cloud_percent>\d+(?:\.\d+)?)"),
    ("cloud_percent", r"(?P<cloud_percent>\d+(?:\.\d+)?)"),
    ("yyyyMMdd", r"(?P<date>\d{8})"),
    ("hhMMss", r"(?P<time>\d{6})"),
    ("HHmmss", r"(?P<time>\d{6})"),
    ("*", ".*"),
)

_SAMPLE_TOKENS = (
    ("cloud-percent", "10"),
    ("cloud_percent", "10"),
    ("yyyyMMdd", "20260102"),
    ("hhMMss", "030405"),
    ("HHmmss", "030405"),
    ("*", "X"),
)


def filter_matches_by_filename_metadata(
    match_result: DownloadMatchResult,
    filename_formats: tuple[DownloadFilenameFormatRule, ...],
    *,
    on_progress: DownloadFilenameProgress | None = None,
    checkpoint: Checkpoint | None = None,
) -> DownloadFilenameFilterResult:
    """Attach filename metadata to matched images and split out cloud-filtered rows."""

    accepted: list[PreparedDownloadImage] = []
    skipped_cloud: list[SkippedCloudDownloadImage | SkippedCloudDownloadCandidate] = [
        *match_result.skipped_cloud_images
    ]

    for match in match_result.matches:
        if checkpoint is not None:
            checkpoint()
        metadata = parse_filename_metadata(match.path, filename_formats)
        if should_skip_for_cloud(metadata):
            cloud_text = (
                f"{metadata.cloud_percent:g}"
                if metadata.cloud_percent is not None
                else "unknown"
            )
            max_text = (
                f"{metadata.max_cloud_percent:g}"
                if metadata.max_cloud_percent is not None
                else "unknown"
            )
            skipped_cloud.append(
                SkippedCloudDownloadImage(
                    match=match,
                    metadata=metadata,
                    reason=(
                        "Cloud percent "
                        f"{cloud_text} vuot nguong cho phep {max_text} "
                        f"cua rule {metadata.matched_format_name}."
                    ),
                )
            )
            if on_progress is not None:
                on_progress(
                    _progress_stats(
                        match_result.stats,
                        len(accepted),
                        len(skipped_cloud) - len(match_result.skipped_cloud_images),
                    ),
                    "skipped_cloud",
                )
            continue
        accepted.append(PreparedDownloadImage(match=match, metadata=metadata))
        if on_progress is not None:
            on_progress(
                _progress_stats(
                    match_result.stats,
                    len(accepted),
                    len(skipped_cloud) - len(match_result.skipped_cloud_images),
                ),
                "accepted",
            )

    return DownloadFilenameFilterResult(
        accepted_matches=tuple(accepted),
        skipped_cloud_images=tuple(skipped_cloud),
        skipped_existing_images=match_result.skipped_existing_images,
        failed_images=match_result.failed_images,
        warnings=filename_format_warnings(filename_formats),
        stats=_progress_stats(
            match_result.stats,
            len(accepted),
            len(skipped_cloud) - len(match_result.skipped_cloud_images),
        ),
    )


def parse_filename_metadata(
    path: Path,
    filename_formats: tuple[DownloadFilenameFormatRule, ...],
) -> DownloadFilenameMetadata:
    """Parse filename metadata using the first matching rule."""

    for rule in filename_formats:
        pattern = compile_filename_format(rule.raw_format)
        match = pattern.match(path.name)
        if match is not None:
            return _metadata_from_match(match, rule)
    return DownloadFilenameMetadata(matched_format=False)


def should_skip_for_cloud(metadata: DownloadFilenameMetadata) -> bool:
    """Return true when parsed cloud percent exceeds the configured rule threshold."""

    if (
        not metadata.matched_format
        or metadata.cloud_percent is None
        or metadata.max_cloud_percent is None
    ):
        return False
    return metadata.cloud_percent > metadata.max_cloud_percent


def filename_format_warnings(
    filename_formats: tuple[DownloadFilenameFormatRule, ...],
) -> tuple[str, ...]:
    """Return non-blocking warnings for rules that may hide later rules."""

    compiled = [
        (rule, compile_filename_format(rule.raw_format))
        for rule in filename_formats
    ]
    warnings: list[str] = []
    for earlier_index, (earlier, earlier_pattern) in enumerate(compiled):
        for later, later_pattern in compiled[earlier_index + 1 :]:
            sample = sample_filename_from_format(later.raw_format)
            if earlier_pattern.match(sample) and later_pattern.match(sample):
                warnings.append(
                    f"Rule `{earlier.name}` co the match truoc va che rule `{later.name}`. "
                    "Neu rule sau can nguong may rieng, hay dat rule sau len truoc."
                )
    return tuple(warnings)


def compile_filename_format(raw_format: str) -> Pattern[str]:
    """Compile a tokenized filename format into a full filename regex."""

    parts: list[str] = []
    index = 0
    while index < len(raw_format):
        for token, replacement in _FORMAT_TOKENS:
            if raw_format.startswith(token, index):
                parts.append(replacement)
                index += len(token)
                break
        else:
            parts.append(re.escape(raw_format[index]))
            index += 1

    try:
        return re.compile(f"^{''.join(parts)}$")
    except re.error as error:
        raise SatelliteDownloadConfigError(
            f"Filename format khong the chuyen thanh regex hop le: {error}",
            field_name="filename_formats",
        ) from error


def sample_filename_from_format(raw_format: str) -> str:
    """Create a representative filename for overlap checks."""

    parts: list[str] = []
    index = 0
    while index < len(raw_format):
        for token, replacement in _SAMPLE_TOKENS:
            if raw_format.startswith(token, index):
                parts.append(replacement)
                index += len(token)
                break
        else:
            parts.append(raw_format[index])
            index += 1
    return "".join(parts)


def _metadata_from_match(
    match: re.Match[str],
    rule: DownloadFilenameFormatRule,
) -> DownloadFilenameMetadata:
    groups = match.groupdict()
    cloud_percent = _parse_cloud_percent(groups.get("cloud_percent"))
    return DownloadFilenameMetadata(
        matched_format=True,
        matched_format_name=rule.name,
        capture_datetime=_parse_capture_datetime(groups.get("date"), groups.get("time")),
        cloud_percent=cloud_percent,
        max_cloud_percent=rule.max_cloud_percent,
    )


def _parse_cloud_percent(value: str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_capture_datetime(date_text: str | None, time_text: str | None) -> datetime | None:
    if not date_text or not time_text:
        return None
    try:
        return datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _progress_stats(
    current: DownloadStats,
    accepted_count: int,
    skipped_cloud_count: int,
) -> DownloadStats:
    return DownloadStats(
        total_images=current.total_images,
        scanned_images=current.scanned_images,
        matched_images=accepted_count,
        downloaded_images=current.downloaded_images,
        skipped_existing=current.skipped_existing,
        skipped_cloud=current.skipped_cloud + skipped_cloud_count,
        failed_images=current.failed_images,
        metadata_cache_hits=current.metadata_cache_hits,
        metadata_cache_misses=current.metadata_cache_misses,
    )
