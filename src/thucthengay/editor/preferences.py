"""User-level editor preferences stored outside project config/workspace."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

APP_CONFIG_DIR_NAME = "3.ThucTheNgay"
PREFERENCES_FILE_NAME = "preferences.json"
MAX_RECENT_PROJECTS = 10


class RecentProjectEntry(BaseModel):
    """Recently used project paths for Setup mode quick restore."""

    model_config = ConfigDict(extra="forbid")

    label: str
    config_path: str
    workspace_folder: str
    imagery_folder: str | None = None
    last_opened_at: str
    last_successful: bool = True


class SetupPreferences(BaseModel):
    """Last Setup mode parameters remembered between application launches."""

    model_config = ConfigDict(extra="forbid")

    last_config_path: str | None = None
    last_imagery_folder: str | None = None
    last_workspace_folder: str | None = None


class UiPreferences(BaseModel):
    """Window and widget layout preferences."""

    model_config = ConfigDict(extra="forbid")

    window_size: list[int] | None = None
    review_main_splitter_sizes: list[int] | None = None


class PreviewPreferences(BaseModel):
    """Preview rendering preferences kept ready for GIS preview optimization."""

    model_config = ConfigDict(extra="forbid")

    gis_preview_quality: Literal["balanced", "high"] = "balanced"
    target_preview_quality: Literal["balanced", "high"] = "balanced"


class ExportPreferences(BaseModel):
    """Export option defaults remembered between application launches."""

    model_config = ConfigDict(extra="forbid")

    output_stem: str = "report"
    open_folder_after_export: bool = False
    overwrite_policy: Literal["overwrite", "timestamp_suffix"] = "overwrite"


class UserPreferences(BaseModel):
    """Versioned user preferences persisted in the OS app-data folder."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    recent_projects: list[RecentProjectEntry] = Field(default_factory=list)
    setup: SetupPreferences = Field(default_factory=SetupPreferences)
    ui: UiPreferences = Field(default_factory=UiPreferences)
    preview: PreviewPreferences = Field(default_factory=PreviewPreferences)
    export: ExportPreferences = Field(default_factory=ExportPreferences)


class PreferencesService:
    """Load and save editor preferences with tolerant reads and atomic writes."""

    def __init__(self, preferences_file: str | Path | None = None) -> None:
        self.preferences_file = (
            Path(preferences_file) if preferences_file else default_preferences_file()
        )
        self._preferences = self.load()

    @property
    def preferences(self) -> UserPreferences:
        return self._preferences

    def load(self) -> UserPreferences:
        if not self.preferences_file.is_file():
            return UserPreferences()
        try:
            raw = json.loads(self.preferences_file.read_text(encoding="utf-8"))
            return UserPreferences.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError):
            return UserPreferences()

    def save(self, preferences: UserPreferences | None = None) -> bool:
        if preferences is not None:
            self._preferences = preferences
        try:
            _atomic_write_json(
                self.preferences_file,
                self._preferences.model_dump(mode="json"),
            )
        except OSError:
            return False
        return True

    def update(self, updater: Callable[[UserPreferences], UserPreferences]) -> bool:
        self._preferences = updater(self._preferences)
        return self.save()

    def record_recent_project(
        self,
        *,
        config_path: str | Path,
        workspace_folder: str | Path,
        imagery_folder: str | Path | None = None,
        label: str | None = None,
        successful: bool = True,
    ) -> bool:
        config_text = _normalized_path_text(config_path)
        workspace_text = _normalized_path_text(workspace_folder)
        imagery_text = _normalized_path_text(imagery_folder) if imagery_folder is not None else None
        existing = self._find_recent_by_workspace(workspace_text)
        if imagery_text is None and existing is not None:
            imagery_text = existing.imagery_folder

        entry = RecentProjectEntry(
            label=label or _recent_project_label(config_text, workspace_text),
            config_path=config_text,
            imagery_folder=imagery_text,
            workspace_folder=workspace_text,
            last_opened_at=datetime.now(UTC).isoformat(),
            last_successful=successful,
        )
        recent = [
            item
            for item in self._preferences.recent_projects
            if _path_key(item.workspace_folder) != _path_key(workspace_text)
        ]
        recent.insert(0, entry)
        recent = recent[:MAX_RECENT_PROJECTS]
        self._preferences = self._preferences.model_copy(update={"recent_projects": recent})
        return self.save()

    def update_setup_parameters(
        self,
        *,
        config_path: str | Path | None = None,
        imagery_folder: str | Path | None = None,
        workspace_folder: str | Path | None = None,
    ) -> bool:
        setup = self._preferences.setup.model_copy(
            update={
                "last_config_path": _optional_normalized_path_text(config_path),
                "last_imagery_folder": _optional_normalized_path_text(imagery_folder),
                "last_workspace_folder": _optional_normalized_path_text(workspace_folder),
            }
        )
        self._preferences = self._preferences.model_copy(update={"setup": setup})
        return self.save()

    def remove_recent_project(self, workspace_folder: str | Path) -> bool:
        workspace_key = _path_key(_normalized_path_text(workspace_folder))
        recent = [
            item
            for item in self._preferences.recent_projects
            if _path_key(item.workspace_folder) != workspace_key
        ]
        self._preferences = self._preferences.model_copy(update={"recent_projects": recent})
        return self.save()

    def update_window_size(self, width: int, height: int) -> bool:
        size = [max(1, int(width)), max(1, int(height))]
        ui = self._preferences.ui.model_copy(update={"window_size": size})
        self._preferences = self._preferences.model_copy(update={"ui": ui})
        return self.save()

    def update_review_splitter_sizes(self, sizes: list[int]) -> bool:
        normalized = [max(0, int(size)) for size in sizes if int(size) >= 0]
        if not normalized:
            return False
        ui = self._preferences.ui.model_copy(update={"review_main_splitter_sizes": normalized})
        self._preferences = self._preferences.model_copy(update={"ui": ui})
        return self.save()

    def update_export_output_stem(self, output_stem: str) -> bool:
        stem = output_stem.strip() or "report"
        export = self._preferences.export.model_copy(update={"output_stem": stem})
        self._preferences = self._preferences.model_copy(update={"export": export})
        return self.save()

    def _find_recent_by_workspace(self, workspace_folder: str) -> RecentProjectEntry | None:
        workspace_key = _path_key(workspace_folder)
        for item in self._preferences.recent_projects:
            if _path_key(item.workspace_folder) == workspace_key:
                return item
        return None


def default_preferences_file() -> Path:
    override = os.environ.get("THUCTHENGAY_PREFERENCES_FILE")
    if override:
        return Path(override).expanduser()
    return _default_app_config_dir() / PREFERENCES_FILE_NAME


def _default_app_config_dir(
    *,
    os_name: str | None = None,
    platform_name: str | None = None,
) -> Path:
    current_os_name = os_name or os.name
    current_platform = platform_name or sys.platform

    if current_os_name == "nt":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_CONFIG_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_CONFIG_DIR_NAME

    if current_platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_CONFIG_DIR_NAME

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / APP_CONFIG_DIR_NAME
    return Path.home() / ".config" / APP_CONFIG_DIR_NAME


def _normalized_path_text(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _optional_normalized_path_text(path: str | Path | None) -> str | None:
    if path is None:
        return None
    path_text = str(path).strip()
    if not path_text:
        return None
    return _normalized_path_text(path_text)


def _path_key(path_text: str) -> str:
    normalized = os.path.normcase(os.path.normpath(path_text))
    if os.name == "nt":
        return normalized.casefold()
    return normalized


def _recent_project_label(config_path: str, workspace_folder: str) -> str:
    workspace_name = Path(workspace_folder).name
    if workspace_name:
        return workspace_name
    config_name = Path(config_path).stem
    return config_name or "Project"


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
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
            json.dump(payload, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
