"""Path resolution helpers for config and template metadata files."""

from __future__ import annotations

import os
from pathlib import Path

from thucthengay.utils.path_safety import is_absolute_path_text, normalize_relative_path_text


def resolve_relative_to_file(owner_file: str | Path, value: str) -> Path:
    """Resolve a string path relative to the file that declares it."""
    path = Path(value).expanduser()
    if is_absolute_path_text(value):
        return path
    relative_path = Path(normalize_relative_path_text(value))
    return (Path(owner_file).resolve().parent / relative_path).resolve()


def resolve_config_asset_path(config_file: str | Path, value: str) -> Path:
    """Resolve config path text with a project-root fallback for data/config.json layouts."""
    resolved = resolve_relative_to_file(config_file, value)
    if resolved.exists() or is_absolute_path_text(value):
        return resolved
    project_relative = (
        project_root_for_config_file(config_file) / normalize_relative_path_text(value)
    )
    if project_relative.exists():
        return project_relative.resolve()
    return resolved


def project_root_for_config_file(config_file: str | Path) -> Path:
    """Infer the project asset root for a config file path."""
    config_dir = Path(config_file).resolve().parent
    if config_dir.name.lower() == "data":
        return config_dir.parent
    return config_dir


def relative_to_file(owner_file: str | Path, path: str | Path) -> str:
    """Return a POSIX path from the owner file's directory to ``path``."""
    relative = os.path.relpath(Path(path).resolve(), Path(owner_file).resolve().parent)
    return relative.replace("\\", "/")
