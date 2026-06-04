"""Packaging entrypoint regression tests."""

from pathlib import Path


def test_pyinstaller_spec_uses_package_entrypoint() -> None:
    spec_text = Path("scripts/pyinstaller/thucthengay_windows.spec").read_text(encoding="utf-8")

    assert 'SRC / "thucthengay" / "__main__.py"' in spec_text
