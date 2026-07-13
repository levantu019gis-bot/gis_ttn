"""Application entrypoint."""

from __future__ import annotations

import os
import sys

from thucthengay.runtime import initialize_gis_runtime


def main(argv: list[str] | None = None) -> int:
    """Run the desktop app when possible, or a headless smoke check."""
    initialize_gis_runtime()
    args = sys.argv[1:] if argv is None else argv
    if "--smoke" in args or "--no-gui" in args or _is_headless_linux():
        print("3.ThucTheNgay app ready.")
        return 0

    from thucthengay.editor.app_shell import run_gui

    return run_gui([sys.argv[0], *args])


def _is_headless_linux() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    return not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")


if __name__ == "__main__":
    raise SystemExit(main())
