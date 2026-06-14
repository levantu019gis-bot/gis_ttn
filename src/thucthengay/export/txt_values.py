"""Shared export text placeholder resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from string import Formatter
from typing import Any

from thucthengay.models import Composition, MetadataStatus, TargetConfig

SUPPORTED_TXT_FIELDS = {
    "capture_date",
    "capture_date_A",
    "capture_date_B",
    "capture_time",
    "composition_id",
    "slide_number",
    "target_alias",
    "target_id",
    "target_name",
    "target_title",
    "time",
    "time_label",
    "time_label_pane_A",
    "time_label_pane_B",
    "title",
}
SUPPORTED_TEXT_FIELDS = {
    "capture_date",
    "capture_date_A",
    "capture_date_B",
    "capture_time",
    "composition_id",
    "slide_number",
    "target_alias",
    "target_id",
    "target_name",
    "target_title",
    "time",
    "time_label",
    "time_label_pane_A",
    "time_label_pane_B",
    "title",
}


@dataclass(frozen=True)
class TxtPlaceholderProblem:
    """One unresolved TXT placeholder problem."""

    field: str
    issue_id: str
    optional: bool


@dataclass(frozen=True)
class TxtLineResolution:
    """Resolved TXT line or placeholder problems."""

    text: str
    problems: tuple[TxtPlaceholderProblem, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems


def resolve_txt_line(
    template: str,
    composition: Composition,
    target: TargetConfig,
    *,
    slide_number: int,
    pane_a_composition: Composition | None = None,
    pane_b_composition: Composition | None = None,
) -> TxtLineResolution:
    """Render one TXT line, supporting optional placeholders as ``{field?}``."""
    return resolve_export_text(
        template,
        composition,
        target,
        slide_number=slide_number,
        pane_a_composition=pane_a_composition,
        pane_b_composition=pane_b_composition,
        supported_fields=SUPPORTED_TXT_FIELDS,
        unknown_issue_id="export.txt_placeholder_unknown",
        unresolved_issue_id="export.txt_placeholder_unresolved",
    )


def resolve_export_text(
    template: str,
    composition: Composition,
    target: TargetConfig,
    *,
    slide_number: int,
    pane_a_composition: Composition | None = None,
    pane_b_composition: Composition | None = None,
    supported_fields: set[str] | None = None,
    unknown_issue_id: str = "export.text_placeholder_unknown",
    unresolved_issue_id: str = "export.text_placeholder_unresolved",
) -> TxtLineResolution:
    """Render one export text value from composition/target placeholders."""
    values = export_text_values(
        composition,
        target,
        slide_number,
        pane_a_composition=pane_a_composition,
        pane_b_composition=pane_b_composition,
    )
    allowed_fields = supported_fields or SUPPORTED_TEXT_FIELDS
    parts: list[str] = []
    problems: list[TxtPlaceholderProblem] = []
    for literal, field_name, format_spec, conversion in Formatter().parse(template):
        parts.append(literal)
        if not field_name:
            continue
        field, optional = _parse_field(field_name)
        value = values.get(field)
        if field not in allowed_fields:
            problems.append(
                TxtPlaceholderProblem(
                    field=field,
                    issue_id=unknown_issue_id,
                    optional=optional,
                )
            )
            continue
        if value in (None, ""):
            if optional:
                parts.append("")
                continue
            is_txt_time_problem = _is_time_label_field(
                field
            ) and unknown_issue_id.startswith("export.txt")
            problems.append(
                TxtPlaceholderProblem(
                    field=field,
                    issue_id=(
                        "export.txt_time_label_unresolved"
                        if is_txt_time_problem
                        else unresolved_issue_id
                    ),
                    optional=False,
                )
            )
            continue
        parts.append(_format_value(value, format_spec, conversion))
    return TxtLineResolution(text="".join(parts), problems=tuple(problems))


def txt_values(
    composition: Composition,
    target: TargetConfig,
    slide_number: int,
    *,
    pane_a_composition: Composition | None = None,
    pane_b_composition: Composition | None = None,
) -> dict[str, Any]:
    """Return supported TXT placeholder values for one export row."""
    return export_text_values(
        composition,
        target,
        slide_number,
        pane_a_composition=pane_a_composition,
        pane_b_composition=pane_b_composition,
    )


def export_text_values(
    composition: Composition,
    target: TargetConfig,
    slide_number: int,
    *,
    pane_a_composition: Composition | None = None,
    pane_b_composition: Composition | None = None,
) -> dict[str, Any]:
    """Return supported PPTX/TXT placeholder values for one export row."""
    capture_time = selected_capture_time(composition)
    return {
        "capture_date": format_capture_date(composition.capture_date, target.export.date_format),
        "capture_date_A": _pane_capture_date(pane_a_composition, target),
        "capture_date_B": _pane_capture_date(pane_b_composition, target),
        "capture_time": _format_time(capture_time) if capture_time is not None else "",
        "composition_id": composition.composition_id,
        "slide_number": slide_number,
        "target_alias": target.alias or "",
        "target_id": target.id,
        "target_name": target.name,
        "target_title": target.title or target.name,
        "time": time_label(composition, target=target),
        "time_label": time_label(composition, target=target),
        "time_label_pane_A": _pane_time_label(pane_a_composition, target),
        "time_label_pane_B": _pane_time_label(pane_b_composition, target),
        "title": target.title or target.name,
    }


def time_label(composition: Composition, *, target: TargetConfig | None = None) -> str:
    """Return the earliest visible valid layer capture time."""
    selected = selected_capture_time(composition)
    if selected is None:
        return ""
    if target is not None:
        return format_capture_datetime(
            composition.capture_date,
            selected,
            target.export.time_format,
        )
    return _format_time(selected)


def selected_capture_time(composition: Composition) -> time | None:
    """Return the earliest visible valid layer capture time."""
    visible_times = [
        layer.capture_time
        for layer in composition.layers
        if layer.visible
        and layer.metadata_status == MetadataStatus.VALID
        and layer.capture_time is not None
    ]
    if not visible_times:
        return None
    return min(visible_times)


def format_capture_date(value: date, date_format: str) -> str:
    """Format a capture date using config tokens such as ``dd.MM.yy``."""
    return value.strftime(_to_strftime_format(date_format))


def format_capture_datetime(capture_date: date, capture_time: time, time_format: str) -> str:
    """Format capture date/time using config tokens such as ``HH.mm/dd.MM.yy``."""
    combined = datetime.combine(capture_date, capture_time)
    return combined.strftime(_to_strftime_format(time_format))


def _pane_capture_date(composition: Composition | None, target: TargetConfig) -> str:
    if composition is None:
        return ""
    return format_capture_date(composition.capture_date, target.export.date_format)


def _pane_time_label(composition: Composition | None, target: TargetConfig) -> str:
    if composition is None:
        return ""
    return time_label(composition, target=target)


def _parse_field(field_name: str) -> tuple[str, bool]:
    normalized = field_name.split(".", 1)[0].split("[", 1)[0]
    if normalized.endswith("?"):
        return normalized[:-1], True
    return normalized, False


def _format_value(value: Any, format_spec: str, conversion: str | None) -> str:
    if conversion == "r":
        value = repr(value)
    elif conversion == "s":
        value = str(value)
    elif conversion == "a":
        value = ascii(value)
    if format_spec:
        return format(value, format_spec)
    return str(value)


def _format_time(value: time) -> str:
    return value.strftime("%H:%M:%S")


def _is_time_label_field(field: str) -> bool:
    return field in {"time", "time_label", "time_label_pane_A", "time_label_pane_B"}


def _to_strftime_format(value: str) -> str:
    replacements = (
        ("yyyy", "%Y"),
        ("yy", "%y"),
        ("dd", "%d"),
        ("MM", "%m"),
        ("HH", "%H"),
        ("mm", "%M"),
        ("ss", "%S"),
    )
    result = value
    for token, replacement in replacements:
        result = result.replace(token, replacement)
    return result
