#!/usr/bin/env python3
"""
Scripted smoke check: import desktop UI, exercise pickers without blocking on mainloop.

Run from repo root:
  python scripts/verify_desktop.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root_dir))

    from desktop.desktop_state import tk_display_environment_ready

    if not tk_display_environment_ready():
        print("SKIP: no display (headless); cannot create Tk root", file=sys.stderr)
        return 0

    try:
        import tkinter  # noqa: F401 — ensure GUI toolkit is present before loading the shell
    except ImportError:
        print("SKIP: tkinter not available in this Python build", file=sys.stderr)
        return 0

    from desktop.main_window import MerckDesktopApp

    picked: list[str] = []

    def fake_dialog(**_kwargs) -> str:
        picked.append("dialog")
        return ""

    app = MerckDesktopApp(file_dialog=fake_dialog)
    app.withdraw()
    app.browse_revised()
    app.update_idletasks()

    if picked != ["dialog"]:
        print("FAIL: expected file dialog to be invoked once", file=sys.stderr)
        return 1

    app.destroy()
    print("verify_desktop: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
