"""Tests for desktop shell behavior.

Validation and file-dialog wiring are tested without Tk via :mod:`desktop.desktop_state`.
One optional test creates a Tk root when a display is available; otherwise it skips.
"""

from __future__ import annotations

import pytest

from desktop.desktop_state import (
    ValidationState,
    compute_validation_state,
    normalize_dialog_path,
    pick_path_via_dialog,
    pick_save_path_via_dialog,
    tk_display_environment_ready,
)


def test_validation_empty_paths() -> None:
    state = compute_validation_state("", "")
    assert isinstance(state, ValidationState)
    assert not state.compare_enabled
    assert state.status_is_error
    assert "original" in state.message.lower() and "revised" in state.message.lower()


def test_validation_ready_when_both_files_exist(tmp_path) -> None:
    orig = tmp_path / "a.docx"
    rev = tmp_path / "b.docx"
    orig.write_bytes(b"PK\x00")
    rev.write_bytes(b"PK\x00")
    state = compute_validation_state(str(orig), str(rev))
    assert state.compare_enabled
    assert not state.status_is_error
    assert "ready" in state.message.lower()


def test_validation_missing_file_on_disk(tmp_path) -> None:
    orig = tmp_path / "gone.docx"
    rev = tmp_path / "b.docx"
    rev.write_bytes(b"PK\x00")
    state = compute_validation_state(str(orig), str(rev))
    assert not state.compare_enabled
    assert "original" in state.message.lower()


def test_normalize_dialog_path() -> None:
    assert normalize_dialog_path("") == ""
    assert normalize_dialog_path(None) == ""
    assert normalize_dialog_path("/a/b.docx") == "/a/b.docx"
    assert normalize_dialog_path(("/x",)) == "/x"
    assert normalize_dialog_path(()) == ""


def test_pick_path_via_dialog_invokes_backend() -> None:
    calls: list[tuple[str, str]] = []

    def fake_dialog(**kwargs) -> str:
        calls.append((kwargs.get("title", ""), "ok"))
        return "/tmp/chosen.docx"

    path = pick_path_via_dialog(
        fake_dialog,
        title="Select Original document",
        filetypes=[("Word documents", "*.docx")],
    )
    assert path == "/tmp/chosen.docx"
    assert calls and "Select Original" in calls[0][0]


def test_pick_path_via_dialog_cancel_returns_empty() -> None:
    def cancel(**_kwargs) -> str:
        return ""

    assert pick_path_via_dialog(cancel, title="t", filetypes=[]) == ""


def test_pick_save_path_via_dialog() -> None:
    def fake_save(**kwargs) -> str:
        assert kwargs.get("defaultextension") == ".docx"
        return "/tmp/out.docx"

    assert (
        pick_save_path_via_dialog(
            fake_save,
            title="Save",
            filetypes=[("Word documents", "*.docx")],
        )
        == "/tmp/out.docx"
    )


def test_desktop_window_instantiates() -> None:
    """Creates a real Tk root only when a display exists; skips cleanly in headless CI."""
    tk = pytest.importorskip("tkinter")
    from desktop.main_window import MerckDesktopApp

    if not tk_display_environment_ready():
        pytest.skip("No display available (headless environment)")

    try:
        app = MerckDesktopApp()
        app.withdraw()
        app.update_idletasks()
        assert app.winfo_exists()
        app.destroy()
    except tk.TclError as err:
        err_l = str(err).lower()
        if "display" in err_l or "no $display" in err_l:
            pytest.skip(f"Tk display not available: {err}")
        raise
