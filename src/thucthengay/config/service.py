"""Project configuration loading and reference validation service."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from thucthengay.config.loader import load_json_file
from thucthengay.config.path_resolver import resolve_config_asset_path
from thucthengay.export import (
    LoadedTemplate,
    TemplateLoadError,
    load_target_template,
    template_compatibility_issues,
)
from thucthengay.models import (
    Issue,
    IssueScope,
    IssueSeverity,
    ProjectConfig,
    TargetConfig,
    TemplateMetadata,
    target_order_key,
)
from thucthengay.models.config import GridInterval


class ConfigUpdateError(RuntimeError):
    """Raised when an expected project config update cannot be persisted."""


@dataclass(frozen=True)
class ResolvedTargetPaths:
    """Filesystem paths resolved from one enabled target config."""

    target_id: str
    geojson_file: Path | None = None
    template_pptx_file: Path | None = None
    template_metadata_file: Path | None = None
    template_pptx: Path | None = None

    def __post_init__(self) -> None:
        if self.template_pptx_file is None:
            object.__setattr__(
                self,
                "template_pptx_file",
                self.template_pptx or self.template_metadata_file,
            )


@dataclass
class ConfigLoadResult:
    """Structured result for expected config loading outcomes."""

    config_path: Path
    config: ProjectConfig | None = None
    enabled_targets: list[TargetConfig] = field(default_factory=list)
    target_paths: dict[str, ResolvedTargetPaths] = field(default_factory=dict)
    template_metadata: dict[str, TemplateMetadata] = field(default_factory=dict)
    loaded_templates: dict[str, LoadedTemplate] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.blocking for issue in self.issues)


def load_project_config(config_path: str | Path) -> ConfigLoadResult:
    """Load config JSON, enabled target references, and PPTX template metadata."""
    config_file = Path(config_path).resolve()
    result = ConfigLoadResult(config_path=config_file)

    try:
        raw_config = load_json_file(config_file)
        result.config = ProjectConfig.model_validate(_enabled_targets_only(raw_config))
    except FileNotFoundError:
        result.issues.append(
            _config_issue(
                "config.file_missing",
                f"Không tìm thấy file config: {config_file}",
                "Chọn lại file config.json hợp lệ.",
            )
        )
        return result
    except PermissionError:
        result.issues.append(
            _config_issue(
                "config.file_unreadable",
                f"Không thể đọc file config: {config_file}",
                "Kiểm tra quyền truy cập file hoặc chọn file khác.",
            )
        )
        return result
    except OSError as error:
        result.issues.append(
            _config_issue(
                "config.file_unreadable",
                f"Không thể đọc file config: {config_file}",
                f"Kiểm tra lại đường dẫn và quyền truy cập. Chi tiết kỹ thuật: {error}",
            )
        )
        return result
    except JSONDecodeError as error:
        result.issues.append(
            _config_issue(
                "config.invalid_json",
                f"File config không phải JSON hợp lệ tại dòng {error.lineno}, cột {error.colno}.",
                "Sửa cú pháp JSON rồi tải lại config.",
            )
        )
        return result
    except (ValueError, ValidationError) as error:
        result.issues.extend(_validation_issues(error))
        return result

    result.enabled_targets = sorted(
        (target for target in result.config.targets if target.enabled),
        key=target_order_key,
    )

    for target in result.enabled_targets:
        _resolve_runtime_target_assets(config_file, target)
        _validate_target_references(config_file, target, result)

    result.issues.extend(template_compatibility_issues(result.loaded_templates.values()))
    return result


def update_target_alignment_defaults(
    config_path: str | Path,
    *,
    target_id: str,
    interval: GridInterval,
    scale: int,
) -> TargetConfig:
    """Persist the reviewed interval/scale back to one target in config.json."""
    config_file = Path(config_path).expanduser()
    if not config_file.is_absolute():
        config_file = config_file.resolve()

    try:
        raw_config = load_json_file(config_file)
    except (OSError, JSONDecodeError, ValueError) as error:
        msg = f"Không đọc được config để cập nhật target `{target_id}`: {error}"
        raise ConfigUpdateError(msg) from error

    targets = raw_config.get("targets")
    if not isinstance(targets, list):
        msg = "Config không có danh sách `targets` hợp lệ."
        raise ConfigUpdateError(msg)

    raw_target: dict[str, Any] | None = None
    for target in targets:
        if isinstance(target, dict) and target.get("id") == target_id:
            raw_target = target
            break

    if raw_target is None:
        msg = f"Không tìm thấy target `{target_id}` trong config."
        raise ConfigUpdateError(msg)

    raw_target["scale"] = scale
    raw_grid = raw_target.get("grid")
    if not isinstance(raw_grid, dict):
        raw_grid = {}
        raw_target["grid"] = raw_grid
    raw_grid["interval"] = _grid_interval_to_config(interval)

    try:
        validated_config = ProjectConfig.model_validate(_enabled_targets_only(raw_config))
    except ValidationError as error:
        msg = f"Config sau cập nhật target `{target_id}` không hợp lệ: {error}"
        raise ConfigUpdateError(msg) from error

    try:
        _write_json_file(config_file, raw_config)
    except OSError as error:
        msg = f"Không ghi được config `{config_file}`: {error}"
        raise ConfigUpdateError(msg) from error

    for target in validated_config.targets:
        if target.id == target_id:
            return target

    msg = f"Target `{target_id}` không còn hợp lệ sau khi cập nhật config."
    raise ConfigUpdateError(msg)


def _enabled_targets_only(raw_config: dict[str, Any]) -> dict[str, Any]:
    raw_targets = raw_config.get("targets")
    if not isinstance(raw_targets, list):
        return raw_config

    filtered_config = dict(raw_config)
    filtered_config["targets"] = [
        target
        for target in raw_targets
        if not isinstance(target, dict) or target.get("enabled", True)
    ]
    return filtered_config


def _grid_interval_to_config(interval: GridInterval) -> dict[str, int | float]:
    data: dict[str, int | float] = {}
    if interval.degrees:
        data["degrees"] = interval.degrees
    if interval.minutes:
        data["minutes"] = interval.minutes
    if interval.seconds:
        seconds = interval.seconds
        data["seconds"] = int(seconds) if seconds.is_integer() else seconds
    return data


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
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


def _validate_target_references(
    config_file: Path,
    target: TargetConfig,
    result: ConfigLoadResult,
) -> None:
    geojson_file = (
        resolve_config_asset_path(config_file, target.geojson_file)
        if target.geojson_file is not None
        else None
    )
    template_pptx_file = resolve_config_asset_path(
        config_file,
        target.export.template_pptx_file,
    )
    target_paths = ResolvedTargetPaths(
        target_id=target.id,
        geojson_file=geojson_file,
        template_pptx_file=template_pptx_file,
    )

    if geojson_file is None:
        if "geojson_geometry" not in target.metadata:
            result.issues.append(
                _target_issue(
                    "target.geojson_missing",
                    target.id,
                    f"Target `{target.id}` không có `geojson_file` hoặc metadata geometry.",
                    "Thêm `metadata.geojson_geometry` hoặc khôi phục `geojson_file` trong config.",
                )
            )
    elif not geojson_file.is_file():
        result.issues.append(
            _target_issue(
                "target.geojson_missing",
                target.id,
                f"Không tìm thấy GeoJSON của target `{target.id}`: {geojson_file}",
                "Kiểm tra lại `geojson_file` trong config; đường dẫn được tính từ config.json.",
            )
        )

    try:
        loaded_template = load_target_template(target, template_pptx_file)
    except TemplateLoadError as error:
        result.issues.append(_template_load_issue(target.id, error))
        result.target_paths[target.id] = target_paths
        return

    result.template_metadata[target.id] = loaded_template.metadata
    result.loaded_templates[target.id] = loaded_template
    target.metadata["template_metadata"] = loaded_template.metadata.model_dump(mode="json")
    result.target_paths[target.id] = target_paths


def _resolve_runtime_target_assets(config_file: Path, target: TargetConfig) -> None:
    font_value = target.grid.style.get("default_label_font")
    if not isinstance(font_value, str) or not font_value.strip():
        return
    resolved_font = resolve_config_asset_path(config_file, font_value)
    if resolved_font.is_file():
        target.grid.style["default_label_font"] = str(resolved_font)


def _config_issue(issue_id: str, message: str, remediation: str) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=IssueScope.CONFIG,
        message=message,
        remediation=remediation,
    )


def _target_issue(issue_id: str, target_id: str, message: str, remediation: str) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=IssueScope.TARGET,
        target_id=target_id,
        message=message,
        remediation=remediation,
    )


def _validation_issues(error: ValueError | ValidationError) -> list[Issue]:
    if not isinstance(error, ValidationError):
        return [
            _config_issue(
                "config.invalid",
                f"Config không hợp lệ: {error}",
                "Kiểm tra cấu trúc config JSON và các trường bắt buộc.",
            )
        ]

    issues: list[Issue] = []
    for item in error.errors():
        field_path = ".".join(str(part) for part in item["loc"])
        issues.append(
            _config_issue(
                "config.field_invalid",
                f"Trường config `{field_path}` không hợp lệ: {item['msg']}",
                _remediation_for_field_path(field_path),
            )
        )
    return issues


def _remediation_for_field_path(field_path: str) -> str:
    if "coordinate" in field_path:
        return "Khai báo `coordinate` dạng `[lon, lat]`, ví dụ `[106.7, 10.8]`."
    if "scale" in field_path:
        return "`scale` phải là mẫu số tỷ lệ bản đồ dương, ví dụ `50000`."
    if "grid.interval" in field_path:
        return "`grid.interval` phải là cấu hình DMS hợp lệ và lớn hơn 0."
    if "template_pptx_file" in field_path:
        return "Khai báo `export.template_pptx_file` trỏ tới PPTX template một slide của target."
    if "placeholders" in field_path:
        return (
            "Khai báo `export.placeholders` với `element_id` hoặc `selector`; "
            "ưu tiên đặt tên shape PPTX dạng `ttn:<field>`."
        )
    return "Kiểm tra giá trị và kiểu dữ liệu của trường này trong config JSON."


def _template_load_issue(target_id: str, error: TemplateLoadError) -> Issue:
    return _target_issue(
        error.issue_id,
        target_id,
        error.message,
        error.remediation,
    )
