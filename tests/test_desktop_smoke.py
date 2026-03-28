"""Smoke tests for the desktop shell (requires tkinter).

Only one :class:`tkinter.Tk` root is created per module: creating multiple roots in
one process is unreliable after the first window is destroyed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tkinter")

from desktop.main_window import MerckDesktopApp


@pytest.fixture(scope="module")
def desktop_app() -> MerckDesktopApp:
    app = MerckDesktopApp()
    app.withdraw()
    yield app
    app.destroy()


def test_desktop_window_instantiates(desktop_app: MerckDesktopApp) -> None:
    desktop_app.update_idletasks()
    assert desktop_app.winfo_exists()


def test_compare_starts_disabled_without_files(desktop_app: MerckDesktopApp) -> None:
    desktop_app.original_path_var.set("")
    desktop_app.revised_path_var.set("")
    desktop_app.set_file_dialog(None)
    desktop_app.update_idletasks()
    assert not desktop_app.compare_button_is_enabled()
    msg = desktop_app.validation_message_text.lower()
    assert "original" in msg and "revised" in msg


def test_compare_enables_when_both_paths_are_existing_files(
    desktop_app: MerckDesktopApp,
    tmp_path,
) -> None:
    orig = tmp_path / "a.docx"
    rev = tmp_path / "b.docx"
    orig.write_bytes(b"PK\x00")
    rev.write_bytes(b"PK\x00")

    desktop_app.original_path_var.set(str(orig))
    desktop_app.revised_path_var.set(str(rev))
    desktop_app.update_idletasks()
    assert desktop_app.compare_button_is_enabled()
    assert "ready" in desktop_app.validation_message_text.lower()


def test_browse_uses_injected_file_dialog(desktop_app: MerckDesktopApp) -> None:
    calls: list[str] = []

    def fake_dialog(**_kwargs) -> str:
        calls.append("open")
        return ""

    desktop_app.set_file_dialog(fake_dialog)
    desktop_app.original_path_var.set("")
    desktop_app.revised_path_var.set("")
    desktop_app.browse_original()
    desktop_app.update_idletasks()
    assert calls == ["open"]
    desktop_app.set_file_dialog(None)
