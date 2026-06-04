"""Filesystem path text helpers shared by config, workspace, and export code."""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath

WINDOWS_INVALID_FILENAME_CHARS = frozenset('<>:"/\\|?*')
WINDOWS_RESERVED_FILENAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)

_UNSAFE_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE_RE = re.compile(r"\s+")


def is_absolute_path_text(value: str | Path) -> bool:
    """Return true for native absolute paths and Windows drive/UNC paths."""
    text = str(value)
    return Path(text).expanduser().is_absolute() or PureWindowsPath(text).is_absolute()


def normalize_relative_path_text(value: str | Path) -> str:
    """Normalize config/workspace relative path text to portable POSIX separators."""
    return str(value).strip().replace("\\", "/")


def validate_windows_safe_filename_component(value: str, *, field_name: str) -> str:
    """Validate one filename/path component against Windows portability rules."""
    if value != value.strip() or not value.strip():
        msg = f"{field_name} must not be empty or have leading/trailing spaces"
        raise ValueError(msg)
    if value in {".", ".."}:
        msg = f"{field_name} must not be . or .."
        raise ValueError(msg)
    if any(char in WINDOWS_INVALID_FILENAME_CHARS for char in value):
        invalid = "".join(sorted(set(value) & WINDOWS_INVALID_FILENAME_CHARS))
        msg = f"{field_name} contains Windows-invalid filename character(s): {invalid}"
        raise ValueError(msg)
    if value[-1] in {" ", "."}:
        msg = f"{field_name} must not end with a space or dot"
        raise ValueError(msg)
    if value.split(".", 1)[0].upper() in WINDOWS_RESERVED_FILENAMES:
        msg = f"{field_name} uses a reserved Windows filename: {value}"
        raise ValueError(msg)
    return value


def safe_filename_component(value: str | Path, *, fallback: str = "file") -> str:
    """Return a Windows-safe filename component while preserving readable text."""
    text = str(value).strip()
    text = _UNSAFE_FILENAME_CHARS_RE.sub("_", text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" .")
    if not text:
        text = fallback
    if text.split(".", 1)[0].upper() in WINDOWS_RESERVED_FILENAMES:
        text = f"{text}_"
    return text
