"""Draft-oriented config editing service for the Config tab."""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from string import Formatter
from typing import Any

from pydantic import ValidationError

from thucthengay.config.loader import load_json_file
from thucthengay.config.path_resolver import resolve_relative_to_file
from thucthengay.export.txt_values import SUPPORTED_TEXT_FIELDS, SUPPORTED_TXT_FIELDS
from thucthengay.ingestion.metadata_parser import parse_business_metadata
from thucthengay.models import Issue, IssueScope, IssueSeverity, ProjectConfig, target_order_key


class ConfigEditorError(RuntimeError):
    """Raised when a config editor operation cannot be completed."""


@dataclass(frozen=True)
class ConfigSummary:
    """Small aggregate displayed by the Config tab."""

    target_count: int = 0
    enabled_count: int = 0
    group_count: int = 0
    template_count: int = 0
    geometry_count: int = 0
    warning_count: int = 0
    error_count: int = 0


@dataclass(frozen=True)
class ConfigGroupSummary:
    """One group row for navigation."""

    key: str
    title: str
    target_count: int


@dataclass
class ConfigEditorState:
    """Current config editor state."""

    source_path: Path | None = None
    draft: dict[str, Any] = field(default_factory=dict)
    persisted: dict[str, Any] | None = None
    issues: list[Issue] = field(default_factory=list)
    summary: ConfigSummary = field(default_factory=ConfigSummary)

    @property
    def dirty(self) -> bool:
        return self.persisted is None or self.draft != self.persisted

    @property
    def ok(self) -> bool:
        return not any(issue.blocking for issue in self.issues)


@dataclass(frozen=True)
class FilenamePatternTestResult:
    """Parsed sample filename result for the pattern test UI."""

    capture_date: str = ""
    capture_time: str = ""
    cloud_percent: str = ""
    source_identifier: str = ""


class ConfigEditorService:
    """Create, load, mutate, validate, and save project config drafts."""

    def __init__(self) -> None:
        self._state = ConfigEditorState(draft=_new_config_draft())
        self.validate()

    @property
    def state(self) -> ConfigEditorState:
        return self._state

    def load(self, path: str | Path) -> ConfigEditorState:
        """Load an existing config into persisted and draft state."""
        source_path = Path(path).expanduser().resolve()
        try:
            raw_config = load_json_file(source_path)
        except FileNotFoundError as error:
            raise ConfigEditorError(f"Không tìm thấy file config: {source_path}") from error
        except JSONDecodeError as error:
            msg = f"File config không phải JSON hợp lệ tại dòng {error.lineno}, cột {error.colno}."
            raise ConfigEditorError(msg) from error
        except (OSError, ValueError) as error:
            raise ConfigEditorError(f"Không đọc được config `{source_path}`: {error}") from error

        self._state = ConfigEditorState(
            source_path=source_path,
            draft=copy.deepcopy(raw_config),
            persisted=copy.deepcopy(raw_config),
        )
        return self.validate()

    def create_new(self, path: str | Path | None = None) -> ConfigEditorState:
        """Start a new draft config."""
        source_path = Path(path).expanduser().resolve() if path is not None else None
        self._state = ConfigEditorState(source_path=source_path, draft=_new_config_draft())
        return self.validate()

    def reload(self) -> ConfigEditorState:
        """Reload the current source path from disk."""
        if self._state.source_path is None:
            raise ConfigEditorError("Chưa có đường dẫn config để tải lại.")
        return self.load(self._state.source_path)

    def save(self, path: str | Path | None = None) -> ConfigEditorState:
        """Persist the current draft atomically."""
        destination = (
            Path(path).expanduser().resolve()
            if path is not None
            else self._state.source_path
        )
        if destination is None:
            raise ConfigEditorError("Chưa có đường dẫn để lưu config.")
        self.validate()
        _atomic_write_json(destination, self._state.draft)
        self._state.source_path = destination
        self._state.persisted = copy.deepcopy(self._state.draft)
        return self.validate()

    def backup(self, destination: str | Path | None = None) -> Path:
        """Write a timestamped backup of the current draft and return its path."""
        if destination is None:
            if self._state.source_path is None:
                raise ConfigEditorError("Chưa có đường dẫn config để tạo backup.")
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            destination_path = self._state.source_path.with_name(
                f"{self._state.source_path.stem}.backup.{timestamp}"
                f"{self._state.source_path.suffix or '.json'}"
            )
        else:
            destination_path = Path(destination).expanduser().resolve()
        _atomic_write_json(destination_path, self._state.draft)
        return destination_path

    def validate(self) -> ConfigEditorState:
        """Validate the draft and refresh issue/summary state."""
        issues: list[Issue] = []
        try:
            config = ProjectConfig.model_validate(self._state.draft)
        except ValidationError as error:
            issues.extend(_validation_issues(error))
            config = None

        if config is not None:
            issues.extend(_semantic_issues(self._state.draft, source_path=self._state.source_path))

        self._state.issues = issues
        self._state.summary = _summary_for_draft(self._state.draft, issues)
        return self._state

    def raw_json(self) -> str:
        """Return the current draft as formatted JSON."""
        return json.dumps(self._state.draft, ensure_ascii=False, indent=2)

    def groups(self) -> list[ConfigGroupSummary]:
        """Return group summaries sorted by business group key."""
        counts: dict[str, tuple[str, int]] = {}
        for target in _raw_targets(self._state.draft):
            key, title = _target_group(target)
            current_title, count = counts.get(key, (title, 0))
            counts[key] = (current_title or title, count + 1)
        return [
            ConfigGroupSummary(key=key, title=title, target_count=count)
            for key, (title, count) in sorted(
                counts.items(),
                key=lambda item: _group_sort_key(item[0]),
            )
        ]

    def targets_for_group(self, group_key: str | None = None) -> list[dict[str, Any]]:
        """Return target drafts sorted by group and local sort order."""
        targets = [copy.deepcopy(target) for target in _raw_targets(self._state.draft)]
        if group_key not in (None, ""):
            targets = [target for target in targets if _target_group(target)[0] == group_key]
        return sorted(targets, key=_raw_target_order_key)

    def target(self, target_id: str) -> dict[str, Any] | None:
        """Return a mutable target draft by id."""
        for target in _raw_targets(self._state.draft):
            if target.get("id") == target_id:
                return target
        return None

    def add_target(self, group_key: str = "0", group_title: str = "Chưa phân nhóm") -> str:
        """Append a minimal target draft and return its id."""
        targets = _ensure_targets(self._state.draft)
        target_id = _next_target_id(targets)
        sort_order = _next_sort_order(targets, group_key)
        targets.append(
            {
                "id": target_id,
                "enabled": True,
                "group": {"key": group_key, "title": group_title},
                "sort_order": sort_order,
                "name": target_id,
                "alias": target_id,
                "coordinate": [0.0, 0.0],
                "scale": 50000,
                "grid": {"interval": {"minutes": 1}},
                "export": {
                    "template_pptx_file": "",
                    "template_txt_value": "",
                    "placeholders": [
                        {"field": "map_image", "kind": "map_image", "value": ""},
                        {"field": "title", "kind": "text", "value": ""},
                        {"field": "time", "kind": "text", "value": "auto"},
                        {"field": "comment", "kind": "text", "value": ""},
                    ],
                },
                "metadata": {},
            }
        )
        self.validate()
        return target_id

    def delete_target(self, target_id: str) -> None:
        """Remove one target from the draft."""
        targets = _ensure_targets(self._state.draft)
        before = len(targets)
        targets[:] = [target for target in targets if target.get("id") != target_id]
        if len(targets) == before:
            raise ConfigEditorError(f"Không tìm thấy target `{target_id}` để xóa.")
        self.validate()

    def update_target(self, target_id: str, updates: dict[str, Any]) -> str:
        """Update a target draft and return its possibly changed id."""
        target = self.target(target_id)
        if target is None:
            raise ConfigEditorError(f"Không tìm thấy target `{target_id}`.")
        targets = _ensure_targets(self._state.draft)
        old_group_key, _old_group_title = _target_group(target)
        affects_order = "sort_order" in updates
        for dotted_key, value in updates.items():
            _set_dotted(target, dotted_key, value)
        new_id = str(target.get("id") or target_id)
        new_group_key, _new_group_title = _target_group(target)
        if old_group_key != new_group_key:
            _normalize_group_sort_orders(targets, old_group_key)
            _normalize_group_sort_orders(
                targets,
                new_group_key,
                moved_target=target,
                requested_sort_order=_sort_order_value(target),
            )
        elif affects_order:
            _normalize_group_sort_orders(
                targets,
                new_group_key,
                moved_target=target,
                requested_sort_order=_sort_order_value(target),
            )
        self.validate()
        return new_id

    def update_defaults(self, updates: dict[str, Any]) -> None:
        """Update dotted fields under `defaults`."""
        defaults = self._state.draft.setdefault("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
            self._state.draft["defaults"] = defaults
        for dotted_key, value in updates.items():
            _set_dotted(defaults, dotted_key, value)
        self.validate()

    def update_filename_patterns(self, patterns: list[dict[str, Any]]) -> None:
        """Replace filename patterns in the draft."""
        self._state.draft["filename_patterns"] = copy.deepcopy(patterns)
        self.validate()

    def import_geojson(self, target_id: str, path: str | Path) -> None:
        """Import one GeoJSON geometry into a target's metadata."""
        target = self.target(target_id)
        if target is None:
            raise ConfigEditorError(f"Không tìm thấy target `{target_id}`.")
        geometry = _read_geojson_geometry(Path(path))
        metadata = target.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            target["metadata"] = metadata
        metadata["geojson_geometry"] = geometry
        self.validate()

    def export_geojson(self, target_id: str, path: str | Path) -> None:
        """Export one target geometry as a GeoJSON Feature."""
        target = self.target(target_id)
        if target is None:
            raise ConfigEditorError(f"Không tìm thấy target `{target_id}`.")
        geometry = _target_geometry(target)
        if geometry is None:
            raise ConfigEditorError(f"Target `{target_id}` chưa có metadata.geojson_geometry.")
        feature = {
            "type": "Feature",
            "properties": {
                "target_id": target.get("id", target_id),
                "name": target.get("name", ""),
            },
            "geometry": geometry,
        }
        _atomic_write_json(Path(path).expanduser().resolve(), feature)

    def import_template_pptx(self, target_id: str, path: str | Path) -> str:
        """Copy a selected PPTX template into data/templates and update the target draft."""
        target = self.target(target_id)
        if target is None:
            raise ConfigEditorError(f"Không tìm thấy target `{target_id}`.")
        source_path = Path(path).expanduser().resolve()
        if source_path.suffix.lower() != ".pptx":
            raise ConfigEditorError("Template phải là file .pptx.")
        if not source_path.is_file():
            raise ConfigEditorError(f"Không tìm thấy template PPTX: {source_path}")

        relative_template_path = self._copy_template_to_project_data(source_path)
        export = target.setdefault("export", {})
        if not isinstance(export, dict):
            export = {}
            target["export"] = export
        export["template_pptx_file"] = relative_template_path
        self.validate()
        return relative_template_path

    def import_default_label_font(self, path: str | Path) -> str:
        """Copy a selected label font into fonts and update defaults."""
        source_path = Path(path).expanduser().resolve()
        if source_path.suffix.lower() not in {".otf", ".ttc", ".ttf"}:
            raise ConfigEditorError("Font label phải là file .ttf, .otf, hoặc .ttc.")
        if not source_path.is_file():
            raise ConfigEditorError(f"Không tìm thấy font label: {source_path}")

        relative_font_path = self._copy_font_to_project_fonts(source_path)
        self.update_defaults({"grid.style.default_label_font": relative_font_path})
        return relative_font_path

    def ensure_target_template_local(self, target_id: str) -> str | None:
        """Copy an existing configured target template into data/templates when needed."""
        target = self.target(target_id)
        if target is None:
            raise ConfigEditorError(f"Không tìm thấy target `{target_id}`.")
        export = target.get("export")
        template_value = (
            export.get("template_pptx_file")
            if isinstance(export, dict)
            else None
        )
        if not template_value:
            raise ConfigEditorError(
                f"Target `{target_id}` chưa khai báo template PPTX. Hãy chọn file bằng Browse."
            )

        source_path = self._resolve_project_path(str(template_value))
        if not source_path.is_file():
            raise ConfigEditorError(
                f"Không tìm thấy template PPTX của target `{target_id}`: {source_path}. "
                "Hãy chọn lại file bằng Browse."
            )

        if _is_inside_project_templates(source_path, self._project_templates_dir()):
            return str(template_value)

        return self.import_template_pptx(target_id, source_path)

    def test_filename(self, filename: str) -> FilenamePatternTestResult:
        """Parse a sample filename with the current draft patterns."""
        patterns = []
        try:
            config = ProjectConfig.model_validate(self._state.draft)
            patterns = config.filename_patterns
        except ValidationError:
            patterns = []
        parsed = parse_business_metadata(Path(filename), filename_patterns=patterns)
        return FilenamePatternTestResult(
            capture_date=parsed.capture_date.isoformat() if parsed.capture_date else "",
            capture_time=parsed.capture_time.strftime("%H:%M:%S") if parsed.capture_time else "",
            cloud_percent="" if parsed.cloud_percent is None else f"{parsed.cloud_percent:g}",
            source_identifier=parsed.source_identifier or "",
        )

    def _copy_template_to_project_data(self, source_path: Path) -> str:
        templates_dir = self._project_templates_dir()
        templates_dir.mkdir(parents=True, exist_ok=True)
        destination = templates_dir / source_path.name
        if source_path.resolve() != destination.resolve():
            shutil.copy2(source_path, destination)
        return destination.relative_to(self._project_root()).as_posix()

    def _copy_font_to_project_fonts(self, source_path: Path) -> str:
        fonts_dir = self._project_fonts_dir()
        if _is_inside_project_dir(source_path, fonts_dir):
            return source_path.resolve().relative_to(self._project_root()).as_posix()
        fonts_dir.mkdir(parents=True, exist_ok=True)
        destination = fonts_dir / source_path.name
        if source_path.resolve() != destination.resolve():
            shutil.copy2(source_path, destination)
        return destination.relative_to(self._project_root()).as_posix()

    def _resolve_project_path(self, value: str) -> Path:
        if self._state.source_path is None:
            path = Path(value).expanduser()
            return path.resolve()
        return resolve_relative_to_file(self._state.source_path, value)

    def _project_root(self) -> Path:
        if self._state.source_path is None:
            raise ConfigEditorError("Cần mở hoặc lưu config trước khi quản lý asset dự án.")
        return self._state.source_path.parent

    def _project_templates_dir(self) -> Path:
        return self._project_root() / "data" / "templates"

    def _project_fonts_dir(self) -> Path:
        return self._project_root() / "fonts"


def _new_config_draft() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "defaults": {
            "grid": {"label_format": "dms_full", "style": {}},
            "export": {
                "date_format": "yyyy-MM-dd",
                "time_format": "HH:mm:ss",
                "map_background_color": "#FFFFFF",
            },
        },
        "filename_patterns": [
            {
                "name": "PlanetScope prefix",
                "pattern": "yyyyMMdd_HHmmss_*",
                "separator": "_",
            }
        ],
        "targets": [],
    }


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
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    except Exception:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
        raise


def _validation_issues(error: ValidationError) -> list[Issue]:
    issues: list[Issue] = []
    for item in error.errors():
        field_path = ".".join(str(part) for part in item["loc"])
        issues.append(
            Issue(
                issue_id="config.field_invalid",
                severity=IssueSeverity.ERROR,
                scope=IssueScope.CONFIG,
                message=f"Trường config `{field_path}` không hợp lệ: {item['msg']}",
                remediation=_remediation_for_field_path(field_path),
            )
        )
    return issues


def _semantic_issues(raw_config: dict[str, Any], *, source_path: Path | None) -> list[Issue]:
    issues: list[Issue] = []
    targets = _raw_targets(raw_config)
    seen_ids: dict[str, int] = {}
    seen_sort_orders: dict[str, dict[int, str]] = {}

    for index, target in enumerate(targets):
        target_id = str(target.get("id") or f"targets.{index}")
        seen_ids[target_id] = seen_ids.get(target_id, 0) + 1
        group_key, _group_title = _target_group(target)
        sort_order = target.get("sort_order")
        if isinstance(sort_order, int):
            group_orders = seen_sort_orders.setdefault(group_key, {})
            existing_target_id = group_orders.get(sort_order)
            if existing_target_id is not None:
                issues.append(
                    _target_issue(
                        "target.sort_order_duplicate",
                        target_id,
                        (
                            f"Target `{target_id}` trùng sort_order `{sort_order}` "
                            f"trong group `{group_key}`."
                        ),
                        "Đổi `sort_order` để mỗi target trong cùng group có thứ tự riêng.",
                    )
                )
            else:
                group_orders[sort_order] = target_id

        if _target_geometry(target) is None and not target.get("geojson_file"):
            issues.append(
                _target_issue(
                    "target.geojson_geometry_missing",
                    target_id,
                    f"Target `{target_id}` chưa có geometry.",
                    "Import GeoJSON hoặc bổ sung `metadata.geojson_geometry`.",
                )
            )

        export = target.get("export")
        template_path = export.get("template_pptx_file") if isinstance(export, dict) else None
        if not template_path:
            issues.append(
                _target_issue(
                    "target.template_missing",
                    target_id,
                    f"Target `{target_id}` chưa khai báo template PPTX.",
                    "Chọn file trong `export.template_pptx_file`.",
                )
            )
        elif source_path is not None:
            resolved = resolve_relative_to_file(source_path, str(template_path))
            if not resolved.is_file():
                issues.append(
                    _target_issue(
                        "target.template_file_missing",
                        target_id,
                        f"Không tìm thấy template PPTX của target `{target_id}`: {resolved}",
                        "Kiểm tra đường dẫn template, tính tương đối từ file config.",
                    )
                )

        if isinstance(export, dict):
            txt_template = export.get("template_txt_value") or export.get("txt_line_template")
            if isinstance(txt_template, str):
                for field in _unknown_template_fields(txt_template, SUPPORTED_TXT_FIELDS):
                    issues.append(
                        _target_issue(
                            "target.txt_placeholder_unknown",
                            target_id,
                            (
                                f"TXT template của target `{target_id}` có placeholder "
                                f"`{field}` chưa hỗ trợ."
                            ),
                            (
                                "Dùng placeholder thuộc tập hỗ trợ như `{time_label}`, "
                                "`{target_name}`, `{target_alias}`."
                            ),
                        )
                    )
            for placeholder in export.get("placeholders", []):
                if not isinstance(placeholder, dict):
                    continue
                value = placeholder.get("value")
                if isinstance(value, str):
                    for field in _unknown_template_fields(value, SUPPORTED_TEXT_FIELDS):
                        issues.append(
                            _target_issue(
                                "target.placeholder_value_unknown",
                                target_id,
                                (
                                    f"Placeholder `{placeholder.get('field', '')}` "
                                    f"dùng `{field}` chưa hỗ trợ."
                                ),
                                "Kiểm tra lại value của placeholder trong Target Inspector.",
                            )
                        )

    for target_id, count in seen_ids.items():
        if count > 1:
            issues.append(
                _target_issue(
                    "target.id_duplicate",
                    target_id,
                    f"Target id `{target_id}` bị trùng.",
                    "Đổi id để mỗi target có định danh duy nhất.",
                )
            )

    return issues


def _summary_for_draft(raw_config: dict[str, Any], issues: list[Issue]) -> ConfigSummary:
    targets = _raw_targets(raw_config)
    group_keys = {_target_group(target)[0] for target in targets}
    templates = {
        str(export.get("template_pptx_file"))
        for target in targets
        if isinstance((export := target.get("export")), dict) and export.get("template_pptx_file")
    }
    geometry_count = sum(1 for target in targets if _target_geometry(target) is not None)
    return ConfigSummary(
        target_count=len(targets),
        enabled_count=sum(1 for target in targets if target.get("enabled", True)),
        group_count=len(group_keys),
        template_count=len(templates),
        geometry_count=geometry_count,
        warning_count=sum(1 for issue in issues if issue.severity == IssueSeverity.WARNING),
        error_count=sum(1 for issue in issues if issue.severity == IssueSeverity.ERROR),
    )


def _target_issue(
    issue_id: str,
    target_id: str,
    message: str,
    remediation: str,
    *,
    severity: IssueSeverity = IssueSeverity.ERROR,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=severity,
        scope=IssueScope.TARGET,
        target_id=target_id,
        message=message,
        remediation=remediation,
    )


def _remediation_for_field_path(field_path: str) -> str:
    if "coordinate" in field_path:
        return "Khai báo `coordinate` dạng `[lon, lat]`, ví dụ `[106.7, 10.8]`."
    if "scale" in field_path:
        return "`scale` phải là mẫu số tỷ lệ bản đồ dương, ví dụ `50000`."
    if "grid.interval" in field_path:
        return "`grid.interval` phải là cấu hình DMS hợp lệ và lớn hơn 0."
    if "filename_patterns" in field_path:
        return "Pattern cần có token trích xuất như `yyyyMMdd`, `HHmmss`, hoặc `cloud-percent`."
    return "Kiểm tra giá trị và kiểu dữ liệu của trường này trong config JSON."


def _raw_targets(raw_config: dict[str, Any]) -> list[dict[str, Any]]:
    targets = raw_config.get("targets", [])
    if not isinstance(targets, list):
        return []
    return [target for target in targets if isinstance(target, dict)]


def _ensure_targets(raw_config: dict[str, Any]) -> list[dict[str, Any]]:
    targets = raw_config.setdefault("targets", [])
    if not isinstance(targets, list):
        targets = []
        raw_config["targets"] = targets
    return targets


def _target_group(target: dict[str, Any]) -> tuple[str, str]:
    group = target.get("group")
    if isinstance(group, dict):
        key = str(group.get("key", "0"))
        title = str(group.get("title", "Chưa phân nhóm"))
        return key, title
    if group is not None:
        return str(group), "Chưa phân nhóm"
    return "0", "Chưa phân nhóm"


def _group_sort_key(group_key: str) -> tuple[int, tuple[int, ...], str]:
    if group_key in {"0", "0.0"}:
        return (1, (10_000,), group_key)
    parts: list[int] = []
    for part in group_key.split("."):
        if not part.isdigit():
            return (0, (9_999,), group_key)
        parts.append(int(part))
    return (0, tuple(parts), group_key)


def _raw_target_order_key(target: dict[str, Any]) -> tuple[int, tuple[int, ...], str, int, str]:
    try:
        parsed = ProjectConfig.model_validate({"targets": [target]}).targets[0]
        return target_order_key(parsed)
    except ValidationError:
        key, _title = _target_group(target)
        sort_order = target.get("sort_order")
        return (*_group_sort_key(key), sort_order if isinstance(sort_order, int) else 0, "")


def _target_geometry(target: dict[str, Any]) -> dict[str, Any] | None:
    metadata = target.get("metadata")
    if not isinstance(metadata, dict):
        return None
    geometry = metadata.get("geojson_geometry")
    return geometry if isinstance(geometry, dict) else None


def _next_target_id(targets: list[dict[str, Any]]) -> str:
    used = {str(target.get("id")) for target in targets}
    index = len(targets) + 1
    while True:
        target_id = f"target_{index:03d}"
        if target_id not in used:
            return target_id
        index += 1


def _next_sort_order(targets: list[dict[str, Any]], group_key: str) -> int:
    orders = [
        target.get("sort_order")
        for target in targets
        if _target_group(target)[0] == group_key and isinstance(target.get("sort_order"), int)
    ]
    return (max(orders) if orders else 0) + 1


def _normalize_group_sort_orders(
    targets: list[dict[str, Any]],
    group_key: str,
    *,
    moved_target: dict[str, Any] | None = None,
    requested_sort_order: int | None = None,
) -> None:
    group_targets = [
        target
        for target in targets
        if _target_group(target)[0] == group_key and target is not moved_target
    ]
    group_targets = sorted(group_targets, key=_raw_target_order_key)
    if moved_target is not None and _target_group(moved_target)[0] == group_key:
        insert_at = _sort_order_insert_index(requested_sort_order, len(group_targets))
        group_targets.insert(insert_at, moved_target)
    for sort_order, target in enumerate(group_targets, start=1):
        target["sort_order"] = sort_order


def _sort_order_insert_index(requested_sort_order: int | None, existing_count: int) -> int:
    if requested_sort_order is None or requested_sort_order < 1:
        return existing_count
    return min(requested_sort_order, existing_count + 1) - 1


def _sort_order_value(target: dict[str, Any]) -> int | None:
    sort_order = target.get("sort_order")
    return sort_order if isinstance(sort_order, int) else None


def _set_dotted(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    current: dict[str, Any] = target
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _read_geojson_geometry(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as error:
        raise ConfigEditorError(f"Không đọc được GeoJSON `{path}`: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigEditorError("GeoJSON root phải là object.")
    if raw.get("type") == "Feature":
        geometry = raw.get("geometry")
    elif raw.get("type") == "FeatureCollection":
        features = raw.get("features")
        if not isinstance(features, list) or len(features) != 1:
            raise ConfigEditorError("FeatureCollection phải có đúng 1 feature trong MVP.")
        feature = features[0]
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
    else:
        geometry = raw
    if not isinstance(geometry, dict) or not geometry.get("type"):
        raise ConfigEditorError("Không tìm thấy geometry hợp lệ trong GeoJSON.")
    return geometry


def _is_inside_project_templates(path: Path, templates_dir: Path) -> bool:
    return _is_inside_project_dir(path, templates_dir)


def _is_inside_project_dir(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _unknown_template_fields(template: str, allowed_fields: set[str]) -> list[str]:
    fields: list[str] = []
    for _literal, field_name, _format_spec, _conversion in Formatter().parse(template):
        if not field_name:
            continue
        normalized = field_name.split(".", 1)[0].split("[", 1)[0].rstrip("?")
        if normalized and normalized not in allowed_fields and normalized not in fields:
            fields.append(normalized)
    return fields
