"""Workspace path layout helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thucthengay.utils.path_safety import validate_windows_safe_filename_component

APP_OWNED_DIRS = ("cache", "compositions", "renders", "exports")
MANIFEST_FILENAME = "manifest.json"
SESSION_STATE_FILENAME = "session_state.json"


@dataclass(frozen=True)
class WorkspacePaths:
    """Canonical filesystem paths inside one workspace root."""

    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / MANIFEST_FILENAME

    @property
    def session_state(self) -> Path:
        return self.root / SESSION_STATE_FILENAME

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def compositions(self) -> Path:
        return self.root / "compositions"

    @property
    def renders(self) -> Path:
        return self.root / "renders"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def app_owned_dirs(self) -> tuple[Path, ...]:
        return (self.cache, self.compositions, self.renders, self.exports)

    def composition_file(self, composition_id: str) -> Path:
        try:
            validate_windows_safe_filename_component(composition_id, field_name="composition id")
        except ValueError as error:
            msg = f"Invalid composition id for workspace path: {composition_id!r}"
            raise ValueError(msg) from error
        return self.compositions / f"{composition_id}.json"
