"""Desktop main window: Original / Revised pickers, engine CLI compare, open output (SCRUM-83)."""

from __future__ import annotations

import subprocess
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from desktop.desktop_state import (
    FileDialogFn,
    compute_validation_state,
    pick_path_via_dialog,
    pick_save_path_via_dialog,
)
from desktop.engine_runner import open_path_with_default_app, run_compare_subprocess

CompareRunner = Callable[..., subprocess.CompletedProcess[str]]


class MerckDesktopApp(tk.Tk):
    """Primary application window with two source document pickers."""

    def __init__(
        self,
        *,
        file_dialog: FileDialogFn | None = None,
        save_dialog: FileDialogFn | None = None,
        compare_runner: CompareRunner | None = None,
        title: str = "Merck Document Comparison",
    ) -> None:
        super().__init__()
        self.title(title)
        self.minsize(560, 220)
        self._file_dialog = file_dialog or filedialog.askopenfilename
        self._save_dialog = save_dialog or filedialog.asksaveasfilename
        self._compare_runner: CompareRunner = compare_runner or run_compare_subprocess

        self._original_path = tk.StringVar()
        self._revised_path = tk.StringVar()
        self._validation_message = tk.StringVar(
            value="Select both Original and Revised .docx files.",
        )

        self._build_ui()

        for v in (self._original_path, self._revised_path):
            v.trace_add("write", lambda *_: self._sync_validation())

    @property
    def original_path_var(self) -> tk.StringVar:
        return self._original_path

    @property
    def revised_path_var(self) -> tk.StringVar:
        return self._revised_path

    @property
    def validation_message_text(self) -> str:
        return self._validation_message.get()

    def compare_button_is_enabled(self) -> bool:
        return str(self._compare_btn.cget("state")) == str(tk.NORMAL)

    def set_file_dialog(self, fn: FileDialogFn | None) -> None:
        """Replace the file picker (used by tests to inject a fake dialog). Pass None to restore default."""
        self._file_dialog = fn or filedialog.askopenfilename

    def set_save_dialog(self, fn: FileDialogFn | None) -> None:
        """Replace the save-as picker (tests). Pass None for default ``asksaveasfilename``."""
        self._save_dialog = fn or filedialog.asksaveasfilename

    def set_compare_runner(self, fn: CompareRunner | None) -> None:
        """Replace the compare subprocess runner (tests). Pass None for default engine CLI."""
        self._compare_runner = fn or run_compare_subprocess

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        main = ttk.Frame(self, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="Compare two Word documents (.docx).", font=("", 11, "bold")).pack(
            anchor=tk.W,
            **pad,
        )

        self._add_file_row(main, "Original", self._original_path, self.browse_original)
        self._add_file_row(main, "Revised", self._revised_path, self.browse_revised)

        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, **pad)
        self._status_label = ttk.Label(
            status_frame,
            textvariable=self._validation_message,
            wraplength=480,
        )
        self._status_label.pack(anchor=tk.W)

        self._compare_btn = ttk.Button(
            main,
            text="Compare",
            command=self._on_compare,
            state=tk.DISABLED,
        )
        self._compare_btn.pack(anchor=tk.E, **pad)

    def _add_file_row(
        self,
        parent: ttk.Frame,
        label: str,
        path_var: tk.StringVar,
        browse_cmd: Callable[[], None],
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, **{"padx": 12, "pady": 4})
        ttk.Label(row, text=f"{label}:", width=10, anchor=tk.W).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=path_var, width=52)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse…", command=browse_cmd).pack(side=tk.RIGHT)

    def browse_original(self) -> None:
        self._pick_file(self._original_path, "Select Original document")

    def browse_revised(self) -> None:
        self._pick_file(self._revised_path, "Select Revised document")

    def _pick_file(self, dest: tk.StringVar, title: str) -> None:
        path = pick_path_via_dialog(
            self._file_dialog,
            title=title,
            filetypes=[
                ("Word documents", "*.docx"),
                ("All files", "*.*"),
            ],
        )
        if path:
            dest.set(path)

    def _sync_validation(self) -> None:
        state = compute_validation_state(self._original_path.get(), self._revised_path.get())
        self._validation_message.set(state.message)
        self._compare_btn.configure(state=tk.NORMAL if state.compare_enabled else tk.DISABLED)
        self._status_label.configure(foreground="#a50a0a" if state.status_is_error else "")

    def _on_compare(self) -> None:
        orig = self._original_path.get().strip()
        rev = self._revised_path.get().strip()
        out_path = pick_save_path_via_dialog(
            self._save_dialog,
            title="Save comparison output as…",
            filetypes=[
                ("Word documents", "*.docx"),
                ("All files", "*.*"),
            ],
            defaultextension=".docx",
        )
        if not out_path:
            return
        try:
            proc = self._compare_runner(orig, rev, out_path)
        except subprocess.TimeoutExpired:
            messagebox.showerror(
                self.title(),
                "Compare timed out. Try smaller documents or contact support.",
            )
            return
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip() or (proc.stdout or "").strip()
            msg = detail or f"Compare failed (exit code {proc.returncode})."
            messagebox.showerror(self.title(), msg)
            return
        if messagebox.askyesno(
            self.title(),
            "Comparison finished successfully.\n\nOpen the output document?",
        ):
            warn = open_path_with_default_app(Path(out_path))
            if warn:
                messagebox.showwarning(self.title(), warn)
