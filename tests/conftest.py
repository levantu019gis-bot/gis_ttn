"""Test process environment defaults."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"


def pytest_configure() -> None:
    """Ensure subprocess smoke tests can import the local package."""

    existing = os.environ.get("PYTHONPATH", "")
    parts = existing.split(os.pathsep) if existing else []
    src_text = str(SRC_PATH)
    if src_text not in parts:
        os.environ["PYTHONPATH"] = (
            os.pathsep.join([src_text, *parts]) if parts else src_text
        )
