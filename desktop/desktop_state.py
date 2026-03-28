"""Display-independent validation and file-picker helpers for the desktop shell."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

FileDialogFn = Callable[..., str | tuple[str, ...]]


def tk_display_environment_ready() -> bool:
    """True if creating a :class:`tkinter.Tk` root is expected to work (headless Linux is False)."""
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@dataclass(frozen=True)
class ValidationState:
    compare_enabled: bool
    message: str
    status_is_error: bool


def compute_validation_state(original_path: str, revised_path: str) -> ValidationState:
    """Derive Compare enablement and status text from the two path fields."""
    o = original_path.strip()
    r = revised_path.strip()
    reasons: list[str] = []
    if not o:
        reasons.append("Original is not selected.")
    elif not Path(o).is_file():
        reasons.append("Original path is not a valid file.")
    if not r:
        reasons.append("Revised is not selected.")
    elif not Path(r).is_file():
        reasons.append("Revised path is not a valid file.")

    if not reasons:
        return ValidationState(True, "Ready to compare.", False)
    return ValidationState(False, " ".join(reasons), True)


def normalize_dialog_path(result: str | tuple[str, ...] | None) -> str:
    """Normalize ``askopenfilename`` return value (str, tuple, or empty)."""
    if not result:
        return ""
    if isinstance(result, tuple):
        return result[0] if result else ""
    return str(result)


def pick_path_via_dialog(
    file_dialog: FileDialogFn,
    *,
    title: str,
    filetypes: list[tuple[str, str]],
) -> str:
    """Invoke a file dialog and return a normalized path, or empty string if cancelled."""
    raw = file_dialog(title=title, filetypes=filetypes)
    return normalize_dialog_path(raw)
