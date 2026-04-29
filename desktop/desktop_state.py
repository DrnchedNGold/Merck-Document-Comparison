"""Display-independent validation and file-picker helpers for the desktop shell."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

FileDialogFn = Callable[..., str | tuple[str, ...]]


def tk_display_environment_ready() -> bool:
    """Heuristic for whether :class:`tkinter.Tk` can be created (headless Linux CI is usually False)."""
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


def pick_save_path_via_dialog(
    save_dialog: FileDialogFn,
    *,
    title: str,
    filetypes: list[tuple[str, str]],
    defaultextension: str = ".docx",
) -> str:
    """Invoke a save dialog (e.g. ``asksaveasfilename``) and return a path, or empty if cancelled."""
    raw = save_dialog(
        title=title,
        filetypes=filetypes,
        defaultextension=defaultextension,
    )
    return normalize_dialog_path(raw)


def make_temp_output_docx_path(*, prefix: str = "merck-compare-", suffix: str = ".docx") -> Path:
    """Create a real temporary `.docx` file path for a compare output.

    The file is created on disk (empty) so downstream openers can rely on it existing.
    The caller owns lifecycle/cleanup; in "Compare & Open" flows we intentionally
    leave the file so Word/default apps can open it.
    """
    fd, raw = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    return Path(raw)


def default_output_cache_dir() -> Path:
    """Directory for cached compare outputs (safe to delete).

    Files here may survive app restarts; the desktop shell only *reuses* a path
    after it successfully wrote that path in the current process (see session
    materialization in ``main_window``).
    """
    d = Path(tempfile.gettempdir()) / "merck-document-comparison-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def compare_signature(
    *,
    original_path: str,
    revised_path: str,
    compare_config: dict[str, object],
) -> str:
    """Stable signature for whether output must be regenerated.

    Uses file path + (mtime_ns, size) for each input plus the compare config.
    """
    o = Path(original_path)
    r = Path(revised_path)
    o_stat = o.stat()
    r_stat = r.stat()
    payload = {
        "original": {"path": str(o), "mtime_ns": int(o_stat.st_mtime_ns), "size": int(o_stat.st_size)},
        "revised": {"path": str(r), "mtime_ns": int(r_stat.st_mtime_ns), "size": int(r_stat.st_size)},
        "config": compare_config,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cached_output_path(*, signature: str, generation: int) -> Path:
    """Cache path for a given signature + regeneration index."""
    # Include generation index so "Recompare" can produce a fresh doc even when signature is unchanged.
    return default_output_cache_dir() / f"{signature}-{generation}.docx"
