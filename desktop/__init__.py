"""Merck document comparison desktop shell.

``MerckDesktopApp`` is imported lazily so that ``import desktop.desktop_state`` (and
pytest collection) does not require Tk / ``libtk`` — needed for Docker/headless CI.
"""

from __future__ import annotations

__all__ = ["MerckDesktopApp"]


def __getattr__(name: str):
    if name == "MerckDesktopApp":
        from desktop.main_window import MerckDesktopApp

        return MerckDesktopApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
