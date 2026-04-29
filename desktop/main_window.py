"""Desktop main window: Original / Revised pickers, engine CLI compare, open output (SCRUM-83)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import threading
import time
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from desktop.desktop_state import (
    FileDialogFn,
    cached_output_path,
    compare_signature,
    compute_validation_state,
    pick_path_via_dialog,
    pick_save_path_via_dialog,
)
from desktop.engine_runner import open_path_with_default_app, run_compare_subprocess
from desktop.error_ux import describe_compare_failure
from desktop.profiles import (
    DEFAULT_WORD_COMPAT_PROFILE_NAME,
    ProfileFormatError,
    default_word_compatible_config,
    default_word_track_changes_options,
    load_profile_bundle,
    load_profile_json,
    save_profile_json,
)
from desktop.user_prefs import load_prefs, save_prefs
from desktop.word_options import (
    apply_word_track_changes_options,
    open_in_word_with_temp_track_changes_options,
    poll_word_saved_path_for_compare_signature,
)

CompareRunner = Callable[..., subprocess.CompletedProcess[str]]

_PREF_COMPARE_SAVED_PATHS = "compare_saved_paths_by_signature"

_WORD_COLOR_CHOICES: list[tuple[str, int]] = [
    ("By author", -1),
    ("Auto", 0),
    ("Black", 1),
    ("Blue", 2),
    ("Turquoise", 3),
    ("Bright Green", 4),
    ("Pink", 5),
    ("Red", 6),
    ("Yellow", 7),
    ("White", 8),
    ("Dark Blue", 9),
    ("Teal", 10),
    ("Green", 11),
    ("Violet", 12),
    ("Dark Red", 13),
    ("Dark Yellow", 14),
    ("Gray-50%", 15),
    ("Gray-25%", 16),
    ("Classic Red", 6),
    ("Classic Blue", 2),
]

_INSERTED_MARK_CHOICES: list[tuple[str, int]] = [
    ("(none)", 0),
    ("Color only", 5),
    ("Bold", 1),
    ("Italic", 2),
    ("Underline", 3),
    ("Double underline", 4),
    ("Strikethrough", 6),
]

_DELETED_MARK_CHOICES: list[tuple[str, int]] = [
    ("(none)", 4),
    ("Color only", 9),
    ("Bold", 5),
    ("Italic", 6),
    ("Underline", 7),
    ("Double underline", 8),
    ("Strikethrough", 1),
    ("Hidden", 0),
    ("^", 2),  # caret
    ("#", 3),  # pound
    ("Double strikethrough", 10),
]

_REVISED_LINES_MARK_CHOICES: list[tuple[str, int]] = [
    ("Outside border", 3),
    ("Left border", 1),
    ("Right border", 2),
    ("None", 0),
]

_MOVE_FROM_MARK_CHOICES: list[tuple[str, int]] = [
    ("(none)", 5),
    ("Color only", 10),
    ("Bold", 6),
    ("Italic", 7),
    ("Underline", 8),
    ("Double underline", 9),
    ("Strikethrough", 2),
    ("Hidden", 0),
    ("^", 3),
    ("#", 4),
    ("Double strikethrough", 1),
]

_MOVE_TO_MARK_CHOICES: list[tuple[str, int]] = [
    ("(none)", 0),
    ("Color only", 5),
    ("Bold", 1),
    ("Italic", 2),
    ("Underline", 3),
    ("Double underline", 4),
    ("Strikethrough", 6),
]

_FORMATTING_MARK_CHOICES: list[tuple[str, int]] = [
    ("(none)", 0),
    ("Color only", 5),
    ("Bold", 1),
    ("Italic", 2),
    ("Underline", 3),
    ("Double underline", 4),
    ("Strikethrough", 6),
    ("Double strikethrough", 7),
]

_CELL_COLOR_CHOICES: list[tuple[str, int]] = [
    ("By author", -1),
    ("(none)", 0),
    ("Pink", 1),
    ("Light Blue", 2),
    ("Light Yellow", 3),
    ("Light Purple", 4),
    ("Light Orange", 5),
    ("Light Green", 6),
    ("Gray", 7),
]


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
        default_cfg = default_word_compatible_config()
        self._ignore_case = tk.BooleanVar(value=default_cfg["ignore_case"])
        self._ignore_whitespace = tk.BooleanVar(value=default_cfg["ignore_whitespace"])
        self._ignore_formatting = tk.BooleanVar(value=default_cfg["ignore_formatting"])
        self._detect_moves = tk.BooleanVar(value=default_cfg["detect_moves"])
        self._word_track_changes_options: dict[str, int] = default_word_track_changes_options()
        self._word_track_changes_profile_name = tk.StringVar(value="Merck Word defaults")
        self._prefs = load_prefs()
        self._profile_label = tk.StringVar(value=DEFAULT_WORD_COMPAT_PROFILE_NAME)
        self._validation_message = tk.StringVar(
            value="Select both Original and Revised .docx files.",
        )
        self._cached_sig: str | None = None
        self._cached_generation: int = 0
        self._cached_output: Path | None = None
        self._cached_saved_copy: Path | None = None
        # Reuse on-disk outputs only if we wrote them in *this* process. Otherwise a stale file
        # under tempfile (merck-document-comparison-cache) could skip regeneration after restart.
        self._session_materialized_outputs: set[str] = set()
        self._word_poll_sig: str | None = None
        self._word_poll_attempts: int = 0

        self._build_ui()

        for v in (self._original_path, self._revised_path):
            v.trace_add("write", lambda *_: self._invalidate_cached_output())
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
        return str(self._compare_save_btn.cget("state")) == str(tk.NORMAL)

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
        self._add_profile_section(main)

        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, **pad)
        self._status_label = ttk.Label(
            status_frame,
            textvariable=self._validation_message,
            wraplength=480,
        )
        self._status_label.pack(anchor=tk.W)

        compare_row = ttk.Frame(main)
        compare_row.pack(fill=tk.X, **pad)

        self._recompare_btn = ttk.Button(
            compare_row,
            text="Recompare",
            command=self._on_recompare,
            state=tk.DISABLED,
        )
        self._recompare_btn.pack(side=tk.LEFT)

        self._compare_btn = ttk.Button(
            compare_row,
            text="Save Only",
            command=self._on_compare_save,
            state=tk.DISABLED,
        )
        self._compare_save_open_btn = ttk.Button(
            compare_row,
            text="Save & Open",
            command=self._on_compare_save_open,
            state=tk.DISABLED,
        )
        self._compare_word_btn = ttk.Button(
            compare_row,
            text="Open",
            command=self._on_compare_open,
            state=tk.DISABLED,
        )
        # Right-aligned, matching Browse buttons: Open (rightmost), then Save & Open, then Save Only.
        self._compare_word_btn.pack(side=tk.RIGHT)
        self._compare_save_open_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self._compare_btn.pack(side=tk.RIGHT, padx=(0, 8))

        # Backwards-compatible attribute names (older tests/scripts referenced these).
        self._compare_save_btn = self._compare_btn
        self._compare_open_btn = self._compare_word_btn

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

    def _add_profile_section(self, parent: ttk.Frame) -> None:
        section = ttk.LabelFrame(parent, text="Compare settings profile", padding=10)
        section.pack(fill=tk.X, padx=12, pady=6)

        ttk.Label(section, textvariable=self._profile_label).pack(anchor=tk.W, pady=(0, 6))

        future = ttk.Label(
            section,
            text='Future options to implement: "Ignore case", "Ignore whitespace", "Ignore formatting", and "Detect moves"',
            font=("", 9, "italic"),
            wraplength=600,
            justify=tk.LEFT,
        )
        future.pack(anchor=tk.W, pady=(0, 6))

        actions = ttk.Frame(section)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions, text="Load profile…", command=self._on_load_profile).pack(
            side=tk.LEFT
        )
        ttk.Button(actions, text="Save profile…", command=self._on_save_profile).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(actions, text="Edit Word options…", command=self._on_edit_word_options).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(actions, text="Apply Word Track Changes options", command=self._on_apply_word_options).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )

        ttk.Label(section, textvariable=self._word_track_changes_profile_name, font=("", 9, "bold")).pack(
            anchor=tk.W, pady=(8, 0)
        )

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
        enabled = tk.NORMAL if state.compare_enabled else tk.DISABLED
        self._compare_save_btn.configure(state=enabled)
        self._compare_save_open_btn.configure(state=enabled)
        self._compare_open_btn.configure(state=enabled)
        self._recompare_btn.configure(state=enabled)
        self._status_label.configure(foreground="#a50a0a" if state.status_is_error else "")

    def _invalidate_cached_output(self) -> None:
        self._cached_sig = None
        self._cached_generation = 0
        self._cached_output = None
        self._cached_saved_copy = None
        self._word_poll_sig = None

    def _persist_compare_saved_path(self, sig: str, p: Path) -> None:
        m = self._prefs.get(_PREF_COMPARE_SAVED_PATHS)
        if not isinstance(m, dict):
            m = {}
        m = dict(m)
        m[sig] = str(p)
        self._prefs[_PREF_COMPARE_SAVED_PATHS] = m
        save_prefs(self._prefs)

    def _clear_compare_saved_path_pref_for_sig(self, sig: str) -> None:
        m = self._prefs.get(_PREF_COMPARE_SAVED_PATHS)
        if not isinstance(m, dict) or sig not in m:
            return
        m = dict(m)
        m.pop(sig, None)
        self._prefs[_PREF_COMPARE_SAVED_PATHS] = m
        save_prefs(self._prefs)

    def _restore_compare_saved_path_from_prefs(self) -> None:
        if self._cached_saved_copy and self._cached_saved_copy.exists():
            return
        sig = self._current_sig()
        m = self._prefs.get(_PREF_COMPARE_SAVED_PATHS)
        if not isinstance(m, dict):
            return
        raw = m.get(sig)
        if not isinstance(raw, str) or not raw.strip():
            return
        p = Path(raw.strip())
        if p.is_file():
            self._cached_saved_copy = p
            self._mark_session_materialized(p)
            return
        m = dict(m)
        m.pop(sig, None)
        self._prefs[_PREF_COMPARE_SAVED_PATHS] = m
        save_prefs(self._prefs)

    def _schedule_word_save_poll(self, signature: str) -> None:
        if sys.platform != "win32":
            return
        self._word_poll_sig = signature
        self._word_poll_attempts = 0
        self.after(400, self._poll_word_save_tick)

    def _poll_word_save_tick(self) -> None:
        if sys.platform != "win32" or not self._word_poll_sig:
            return
        if self._word_poll_sig != self._current_sig():
            self._word_poll_sig = None
            return
        found = poll_word_saved_path_for_compare_signature(self._word_poll_sig)
        if found:
            p = Path(found)
            if p.is_file():
                self._cached_saved_copy = p
                self._mark_session_materialized(p)
                self._persist_compare_saved_path(self._word_poll_sig, p)
            self._word_poll_sig = None
            return
        self._word_poll_attempts += 1
        if self._word_poll_attempts > 600:
            self._word_poll_sig = None
            return
        self.after(1000, self._poll_word_save_tick)

    def _materialized_key(self, p: Path) -> str:
        try:
            return str(p.resolve())
        except OSError:
            return str(p)

    def _mark_session_materialized(self, p: Path) -> None:
        self._session_materialized_outputs.add(self._materialized_key(p))

    def _is_reusable_output(self, p: Path) -> bool:
        return p.exists() and self._materialized_key(p) in self._session_materialized_outputs

    def _current_compare_config(self) -> dict[str, bool]:
        return {
            "ignore_case": bool(self._ignore_case.get()),
            "ignore_whitespace": bool(self._ignore_whitespace.get()),
            "ignore_formatting": bool(self._ignore_formatting.get()),
            "detect_moves": bool(self._detect_moves.get()),
        }

    def _apply_compare_config(self, config: dict[str, bool]) -> None:
        self._ignore_case.set(bool(config["ignore_case"]))
        self._ignore_whitespace.set(bool(config["ignore_whitespace"]))
        self._ignore_formatting.set(bool(config["ignore_formatting"]))
        self._detect_moves.set(bool(config["detect_moves"]))
        self._invalidate_cached_output()

    def _on_load_profile(self) -> None:
        selected = pick_path_via_dialog(
            self._file_dialog,
            title="Load compare profile JSON",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        try:
            cfg, word_opts, prof_name = load_profile_bundle(Path(selected))
        except ProfileFormatError as exc:
            messagebox.showerror(self.title(), str(exc))
            return
        self._apply_compare_config(cfg)
        self._word_track_changes_options = dict(word_opts)
        self._profile_label.set(f"Loaded profile: {prof_name}")
        self._word_track_changes_profile_name.set(f"Word options: {prof_name}")

    def _on_save_profile(self) -> None:
        dest = pick_save_path_via_dialog(
            self._save_dialog,
            title="Save compare profile as…",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
            defaultextension=".json",
        )
        if not dest:
            return
        try:
            cfg = {
                "ignore_case": bool(self._ignore_case.get()),
                "ignore_whitespace": bool(self._ignore_whitespace.get()),
                "ignore_formatting": bool(self._ignore_formatting.get()),
                "detect_moves": bool(self._detect_moves.get()),
            }
            save_profile_json(
                Path(dest),
                cfg,
                word_track_changes_options=dict(self._word_track_changes_options),
            )  # do not persist per-run override
        except (ProfileFormatError, OSError, UnicodeError) as exc:
            messagebox.showerror(self.title(), f"Could not save profile: {exc}")
            return
        self._profile_label.set(f"Loaded profile: {Path(dest).name}")
        self._word_track_changes_profile_name.set(f"Word options: {Path(dest).name}")

    def _on_apply_word_options(self) -> None:
        if sys.platform != "win32":
            messagebox.showwarning(self.title(), "Word automation is only supported on Windows.")
            return
        if not bool(self._prefs.get("skip_word_global_confirm", False)):
            dlg = tk.Toplevel(self)
            dlg.title("Apply Word settings?")
            dlg.resizable(False, False)
            dlg.transient(self)
            dlg.grab_set()
            ttk.Label(
                dlg,
                text=(
                    "This will change Word's Track Changes settings for your Windows user.\n"
                    "It affects all documents you open in Word."
                ),
                padding=12,
                wraplength=420,
            ).pack(anchor=tk.W)
            dont_ask = tk.BooleanVar(value=False)
            ttk.Checkbutton(dlg, text="Don't show this again", variable=dont_ask).pack(
                anchor=tk.W, padx=12, pady=(0, 8)
            )
            btns = ttk.Frame(dlg, padding=(12, 0, 12, 12))
            btns.pack(fill=tk.X)
            proceed = {"ok": False}

            def do_ok() -> None:
                proceed["ok"] = True
                if dont_ask.get():
                    self._prefs["skip_word_global_confirm"] = True
                    save_prefs(self._prefs)
                dlg.destroy()

            ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
            ttk.Button(btns, text="Apply", command=do_ok).pack(side=tk.RIGHT, padx=(8, 0))
            dlg.wait_window(dlg)
            if not proceed["ok"]:
                return

        ok, err = apply_word_track_changes_options(
            track_changes_options=dict(self._word_track_changes_options),
        )
        if not ok:
            messagebox.showerror(
                self.title(),
                f"Could not apply Word Track Changes options.\n\n{err or ''}".strip(),
            )
            return
        messagebox.showinfo(self.title(), "Applied Track Changes options to Word for this PC/user.")

    def _on_edit_word_options(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Word Track Changes options")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        def mk_choice_var(key: str, choices: list[tuple[str, int]]) -> tk.StringVar:
            current = int(self._word_track_changes_options.get(key, choices[0][1]))
            label = next((n for n, v in choices if v == current), choices[0][0])
            return tk.StringVar(value=label)

        def read_choice(var: tk.StringVar, choices: list[tuple[str, int]]) -> int:
            label = var.get()
            for n, val in choices:
                if n == label:
                    return val
            return choices[0][1]

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Markup", font=("", 10, "bold")).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 6)
        )

        ins_mark = mk_choice_var("InsertedTextMark", _INSERTED_MARK_CHOICES)
        ins_color = mk_choice_var("InsertedTextColor", _WORD_COLOR_CHOICES)
        del_mark = mk_choice_var("DeletedTextMark", _DELETED_MARK_CHOICES)
        del_color = mk_choice_var("DeletedTextColor", _WORD_COLOR_CHOICES)
        lines_mark = mk_choice_var("RevisedLinesMark", _REVISED_LINES_MARK_CHOICES)

        ttk.Label(frame, text="Insertions:").grid(row=1, column=0, sticky=tk.W)
        ttk.Combobox(
            frame,
            textvariable=ins_mark,
            values=[n for n, _ in _INSERTED_MARK_CHOICES],
            width=18,
            state="readonly",
        ).grid(row=1, column=1, padx=(6, 6))
        ttk.Label(frame, text="Color:").grid(row=1, column=2, sticky=tk.E)
        ttk.Combobox(
            frame,
            textvariable=ins_color,
            values=[n for n, _ in _WORD_COLOR_CHOICES],
            width=14,
            state="readonly",
        ).grid(row=1, column=3, padx=(6, 0))

        ttk.Label(frame, text="Deletions:").grid(row=2, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Combobox(
            frame,
            textvariable=del_mark,
            values=[n for n, _ in _DELETED_MARK_CHOICES],
            width=18,
            state="readonly",
        ).grid(row=2, column=1, padx=(6, 6), pady=(4, 0))
        ttk.Label(frame, text="Color:").grid(row=2, column=2, sticky=tk.E, pady=(4, 0))
        ttk.Combobox(
            frame,
            textvariable=del_color,
            values=[n for n, _ in _WORD_COLOR_CHOICES],
            width=14,
            state="readonly",
        ).grid(row=2, column=3, padx=(6, 0), pady=(4, 0))

        ttk.Label(frame, text="Changed lines:").grid(row=3, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Combobox(
            frame,
            textvariable=lines_mark,
            values=[n for n, _ in _REVISED_LINES_MARK_CHOICES],
            width=18,
            state="readonly",
        ).grid(row=3, column=1, padx=(6, 6), pady=(4, 0))

        ttk.Separator(frame, orient="horizontal").grid(
            row=4, column=0, columnspan=5, sticky="ew", pady=10
        )
        ttk.Label(frame, text="Moves", font=("", 10, "bold")).grid(
            row=5, column=0, sticky=tk.W, pady=(0, 6)
        )

        track_moves = tk.BooleanVar(
            value=bool(int(self._word_track_changes_options.get("TrackMoves", 1)))
        )
        move_from_mark = mk_choice_var("MoveFromTextMark", _MOVE_FROM_MARK_CHOICES)
        move_from_color = mk_choice_var("MoveFromTextColor", _WORD_COLOR_CHOICES)
        move_to_mark = mk_choice_var("MoveToTextMark", _MOVE_TO_MARK_CHOICES)
        move_to_color = mk_choice_var("MoveToTextColor", _WORD_COLOR_CHOICES)

        ttk.Checkbutton(frame, text="Track moves", variable=track_moves).grid(
            row=6, column=0, sticky=tk.W
        )
        ttk.Label(frame, text="Moved from:").grid(row=7, column=0, sticky=tk.W, pady=(4, 0))
        move_from_mark_cb = ttk.Combobox(
            frame,
            textvariable=move_from_mark,
            values=[n for n, _ in _MOVE_FROM_MARK_CHOICES],
            width=18,
            state="readonly",
        )
        move_from_mark_cb.grid(row=7, column=1, padx=(6, 6), pady=(4, 0))
        ttk.Label(frame, text="Color:").grid(row=7, column=2, sticky=tk.E, pady=(4, 0))
        move_from_color_cb = ttk.Combobox(
            frame,
            textvariable=move_from_color,
            values=[n for n, _ in _WORD_COLOR_CHOICES],
            width=14,
            state="readonly",
        )
        move_from_color_cb.grid(row=7, column=3, padx=(6, 0), pady=(4, 0))

        ttk.Label(frame, text="Moved to:").grid(row=8, column=0, sticky=tk.W, pady=(4, 0))
        move_to_mark_cb = ttk.Combobox(
            frame,
            textvariable=move_to_mark,
            values=[n for n, _ in _MOVE_TO_MARK_CHOICES],
            width=18,
            state="readonly",
        )
        move_to_mark_cb.grid(row=8, column=1, padx=(6, 6), pady=(4, 0))
        ttk.Label(frame, text="Color:").grid(row=8, column=2, sticky=tk.E, pady=(4, 0))
        move_to_color_cb = ttk.Combobox(
            frame,
            textvariable=move_to_color,
            values=[n for n, _ in _WORD_COLOR_CHOICES],
            width=14,
            state="readonly",
        )
        move_to_color_cb.grid(row=8, column=3, padx=(6, 0), pady=(4, 0))

        def sync_moves_enabled(*_args: object) -> None:
            state = "readonly" if track_moves.get() else "disabled"
            for w in (move_from_mark_cb, move_from_color_cb, move_to_mark_cb, move_to_color_cb):
                w.configure(state=state)

        track_moves.trace_add("write", sync_moves_enabled)
        sync_moves_enabled()

        ttk.Separator(frame, orient="horizontal").grid(
            row=9, column=0, columnspan=5, sticky="ew", pady=10
        )
        ttk.Label(frame, text="Table cell highlighting", font=("", 10, "bold")).grid(
            row=10, column=0, sticky=tk.W, pady=(0, 6)
        )

        ins_cell = mk_choice_var("InsertedCellColor", _CELL_COLOR_CHOICES)
        del_cell = mk_choice_var("DeletedCellColor", _CELL_COLOR_CHOICES)
        merged_cell = mk_choice_var("MergedCellColor", _CELL_COLOR_CHOICES)
        split_cell = mk_choice_var("SplitCellColor", _CELL_COLOR_CHOICES)

        ttk.Label(frame, text="Inserted cells:").grid(row=11, column=0, sticky=tk.W)
        ttk.Combobox(
            frame,
            textvariable=ins_cell,
            values=[n for n, _ in _CELL_COLOR_CHOICES],
            width=18,
            state="readonly",
        ).grid(row=11, column=1, padx=(6, 0))
        ttk.Label(frame, text="Deleted cells:").grid(row=12, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Combobox(
            frame,
            textvariable=del_cell,
            values=[n for n, _ in _CELL_COLOR_CHOICES],
            width=18,
            state="readonly",
        ).grid(row=12, column=1, padx=(6, 0), pady=(4, 0))
        ttk.Label(frame, text="Merged cells:").grid(row=11, column=2, sticky=tk.E)
        ttk.Combobox(
            frame,
            textvariable=merged_cell,
            values=[n for n, _ in _CELL_COLOR_CHOICES],
            width=14,
            state="readonly",
        ).grid(row=11, column=3, padx=(6, 0))
        ttk.Label(frame, text="Split cells:").grid(row=12, column=2, sticky=tk.E, pady=(4, 0))
        ttk.Combobox(
            frame,
            textvariable=split_cell,
            values=[n for n, _ in _CELL_COLOR_CHOICES],
            width=14,
            state="readonly",
        ).grid(row=12, column=3, padx=(6, 0), pady=(4, 0))

        ttk.Separator(frame, orient="horizontal").grid(
            row=13, column=0, columnspan=5, sticky="ew", pady=10
        )
        ttk.Label(frame, text="Formatting / Balloons", font=("", 10, "bold")).grid(
            row=14, column=0, sticky=tk.W, pady=(0, 6)
        )

        track_fmt = tk.BooleanVar(
            value=bool(int(self._word_track_changes_options.get("TrackFormatting", 1)))
        )
        ttk.Checkbutton(frame, text="Track formatting", variable=track_fmt).grid(
            row=15, column=0, sticky=tk.W
        )

        fmt_mark = mk_choice_var("RevisedPropertiesMark", _FORMATTING_MARK_CHOICES)
        fmt_color = mk_choice_var("RevisedPropertiesColor", _WORD_COLOR_CHOICES)
        ttk.Label(frame, text="Formatting:").grid(row=15, column=1, sticky=tk.W)
        ttk.Combobox(
            frame,
            textvariable=fmt_mark,
            values=[n for n, _ in _FORMATTING_MARK_CHOICES],
            width=18,
            state="readonly",
        ).grid(row=15, column=2, padx=(6, 6))
        ttk.Label(frame, text="Color:").grid(row=15, column=3, sticky=tk.W)
        ttk.Combobox(
            frame,
            textvariable=fmt_color,
            values=[n for n, _ in _WORD_COLOR_CHOICES],
            width=14,
            state="readonly",
        ).grid(row=15, column=4, padx=(6, 0))

        width_in = tk.StringVar(
            value=str(self._word_track_changes_options.get("BalloonsPreferredWidthInches", 3.7))
        )
        show_lines = tk.BooleanVar(
            value=bool(int(self._word_track_changes_options.get("BalloonsShowConnectingLines", 0)))
        )
        ttk.Label(frame, text="Balloons width (in):").grid(row=16, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(frame, textvariable=width_in, width=10).grid(
            row=16, column=1, sticky=tk.W, padx=(6, 0), pady=(4, 0)
        )
        ttk.Checkbutton(frame, text="Show connecting lines", variable=show_lines).grid(
            row=16, column=2, columnspan=2, sticky=tk.W, pady=(4, 0)
        )

        btns = ttk.Frame(dialog, padding=(12, 8, 12, 12))
        btns.pack(fill=tk.X)

        def reset_to_defaults() -> None:
            defaults = default_word_track_changes_options()
            self._word_track_changes_options = dict(defaults)
            # Re-sync all UI vars to defaults.
            ins_mark.set(next(n for n, v in _INSERTED_MARK_CHOICES if v == defaults["InsertedTextMark"]))
            ins_color.set(next(n for n, v in _WORD_COLOR_CHOICES if v == defaults["InsertedTextColor"]))
            del_mark.set(next(n for n, v in _DELETED_MARK_CHOICES if v == defaults["DeletedTextMark"]))
            del_color.set(next(n for n, v in _WORD_COLOR_CHOICES if v == defaults["DeletedTextColor"]))
            lines_mark.set(next(n for n, v in _REVISED_LINES_MARK_CHOICES if v == defaults["RevisedLinesMark"]))
            track_moves.set(bool(int(defaults.get("TrackMoves", 1))))
            move_from_mark.set(next(n for n, v in _MOVE_FROM_MARK_CHOICES if v == defaults["MoveFromTextMark"]))
            move_from_color.set(next(n for n, v in _WORD_COLOR_CHOICES if v == defaults["MoveFromTextColor"]))
            move_to_mark.set(next(n for n, v in _MOVE_TO_MARK_CHOICES if v == defaults["MoveToTextMark"]))
            move_to_color.set(next(n for n, v in _WORD_COLOR_CHOICES if v == defaults["MoveToTextColor"]))
            ins_cell.set(next(n for n, v in _CELL_COLOR_CHOICES if v == defaults["InsertedCellColor"]))
            del_cell.set(next(n for n, v in _CELL_COLOR_CHOICES if v == defaults["DeletedCellColor"]))
            merged_cell.set(next(n for n, v in _CELL_COLOR_CHOICES if v == defaults["MergedCellColor"]))
            split_cell.set(next(n for n, v in _CELL_COLOR_CHOICES if v == defaults["SplitCellColor"]))
            track_fmt.set(bool(int(defaults.get("TrackFormatting", 1))))
            fmt_mark.set(next(n for n, v in _FORMATTING_MARK_CHOICES if v == defaults["RevisedPropertiesMark"]))
            fmt_color.set(next(n for n, v in _WORD_COLOR_CHOICES if v == defaults["RevisedPropertiesColor"]))
            width_in.set(str(defaults.get("BalloonsPreferredWidthInches", 3.7)))
            show_lines.set(bool(int(defaults.get("BalloonsShowConnectingLines", 0))))

        def save_and_close() -> None:
            try:
                width = float(width_in.get().strip())
            except ValueError:
                messagebox.showerror(self.title(), "Balloons width must be a number.", parent=dialog)
                return
            self._word_track_changes_options.update(
                {
                    "InsertedTextMark": read_choice(ins_mark, _INSERTED_MARK_CHOICES),
                    "InsertedTextColor": read_choice(ins_color, _WORD_COLOR_CHOICES),
                    "DeletedTextMark": read_choice(del_mark, _DELETED_MARK_CHOICES),
                    "DeletedTextColor": read_choice(del_color, _WORD_COLOR_CHOICES),
                    "RevisedLinesMark": read_choice(lines_mark, _REVISED_LINES_MARK_CHOICES),
                    "TrackMoves": 1 if track_moves.get() else 0,
                    "MoveFromTextMark": read_choice(move_from_mark, _MOVE_FROM_MARK_CHOICES),
                    "MoveFromTextColor": read_choice(move_from_color, _WORD_COLOR_CHOICES),
                    "MoveToTextMark": read_choice(move_to_mark, _MOVE_TO_MARK_CHOICES),
                    "MoveToTextColor": read_choice(move_to_color, _WORD_COLOR_CHOICES),
                    "InsertedCellColor": read_choice(ins_cell, _CELL_COLOR_CHOICES),
                    "DeletedCellColor": read_choice(del_cell, _CELL_COLOR_CHOICES),
                    "MergedCellColor": read_choice(merged_cell, _CELL_COLOR_CHOICES),
                    "SplitCellColor": read_choice(split_cell, _CELL_COLOR_CHOICES),
                    "TrackFormatting": 1 if track_fmt.get() else 0,
                    "RevisedPropertiesMark": read_choice(fmt_mark, _FORMATTING_MARK_CHOICES),
                    "RevisedPropertiesColor": read_choice(fmt_color, _WORD_COLOR_CHOICES),
                    "BalloonsPreferredWidthInches": width,
                    "BalloonsShowConnectingLines": 1 if show_lines.get() else 0,
                }
            )
            dialog.destroy()

        ttk.Button(btns, text="Reset to defaults", command=reset_to_defaults).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Save", command=save_and_close).pack(side=tk.RIGHT, padx=(8, 0))

        dialog.wait_window(dialog)

    def _run_compare_to_path(
        self,
        *,
        out_path: str,
        on_success: str,
        post_success: Callable[[Path], None] | None = None,
    ) -> None:
        """Run compare and perform a post-success action.

        `on_success`:
          - "saved": show info dialog only
          - "open": open the output document (no Save-As prompt)
        """
        orig = self._original_path.get().strip()
        rev = self._revised_path.get().strip()

        # Disable actions while generating (prevents duplicate subprocess runs).
        self._compare_save_btn.configure(state=tk.DISABLED)
        self._compare_save_open_btn.configure(state=tk.DISABLED)
        self._compare_open_btn.configure(state=tk.DISABLED)
        self._recompare_btn.configure(state=tk.DISABLED)

        progress = self._show_progress_dialog("Generating comparison document…")

        result: dict[str, object] = {"done": False}

        def worker() -> None:
            temp_config_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".json",
                    encoding="utf-8",
                    delete=False,
                ) as temp_cfg:
                    json.dump(self._current_compare_config(), temp_cfg)
                    temp_config_path = temp_cfg.name
                proc = self._compare_runner(orig, rev, out_path, config_path=temp_config_path)
                result["proc"] = proc
            except Exception as exc:  # noqa: BLE001 - surface to UI thread
                result["exc"] = exc
            finally:
                if temp_config_path:
                    Path(temp_config_path).unlink(missing_ok=True)
                result["done"] = True

        threading.Thread(target=worker, name="compare-runner", daemon=True).start()

        def finish() -> None:
            if not bool(result.get("done", False)):
                self.after(100, finish)
                return

            progress["close"]()
            self._sync_validation()

            exc = result.get("exc")
            if exc is not None:
                if isinstance(exc, subprocess.TimeoutExpired):
                    messagebox.showerror(
                        self.title(),
                        "Compare timed out. Try smaller documents or contact support.",
                    )
                    return
                if isinstance(exc, OSError):
                    messagebox.showerror(self.title(), f"Could not prepare compare settings: {exc}")
                    return
                messagebox.showerror(self.title(), f"Unexpected error during compare: {exc}")
                return

            proc = result.get("proc")
            if not isinstance(proc, subprocess.CompletedProcess):
                messagebox.showerror(self.title(), "Internal error: compare did not return a process result.")
                return

            if proc.returncode != 0:
                ux = describe_compare_failure(
                    returncode=int(proc.returncode),
                    stderr=proc.stderr,
                    stdout=proc.stdout,
                )
                messagebox.showerror(
                    self.title(),
                    f"{ux.headline}\n\n{ux.message}\n\nDetails:\n{ux.details}",
                )
                return

            output_path = Path(out_path)
            self._mark_session_materialized(output_path)
            # If a caller provided a custom post-success action, run it and stop.
            if post_success is not None:
                post_success(output_path)
                return

            if on_success == "saved":
                messagebox.showinfo(
                    self.title(),
                    f"Comparison finished successfully.\n\nSaved to:\n{output_path}",
                )
                return

            if on_success not in ("none", "open", "open_saved"):
                messagebox.showerror(self.title(), f"Internal error: unknown on_success='{on_success}'")
                return
            if on_success == "none":
                return

            if sys.platform == "win32":
                ok, err = open_in_word_with_temp_track_changes_options(
                    output_path,
                    track_changes_options=dict(self._word_track_changes_options),
                    as_new_unsaved_document=(on_success == "open"),
                    keep_source_file=(on_success != "open"),
                )
                if not ok:
                    messagebox.showwarning(
                        self.title(),
                        (
                            "Could not open in Word with Track Changes options.\n\n"
                            + (err or "").strip()
                            + "\n\nCommon fixes:\n- Close all Word windows and retry\n- Ensure Word is installed and activated\n- Retry without elevated/admin mode"
                        ).strip(),
                    )
                    warn = open_path_with_default_app(output_path)
                    if warn:
                        messagebox.showwarning(self.title(), warn)
                if on_success == "open":
                    messagebox.showinfo(
                        self.title(),
                        "Opened a temporary comparison document.\n\n"
                        "Closing it will discard it.\n\n"
                        "To keep a copy, use Save As… in Word (not Save).",
                    )
                else:
                    # Saved file should persist and can be saved normally.
                    messagebox.showinfo(self.title(), f"Opened:\n{output_path}")
                return

            warn = open_path_with_default_app(output_path)
            if warn:
                messagebox.showwarning(self.title(), warn)
            if on_success == "open":
                messagebox.showinfo(
                    self.title(),
                    "Opened a temporary comparison document.\n\n"
                    "Closing it will delete it.\n\n"
                    "To keep a copy, use Save As… in your editor (not Save).",
                )
                self._delete_when_closed(output_path)

        self.after(50, finish)

    def _current_sig(self) -> str:
        return compare_signature(
            original_path=self._original_path.get().strip(),
            revised_path=self._revised_path.get().strip(),
            compare_config=self._current_compare_config(),
        )

    def _get_or_prepare_cached_output(self, *, force_regenerate: bool) -> Path:
        sig = self._current_sig()
        if self._cached_sig != sig:
            self._cached_sig = sig
            self._cached_generation = 0
            self._cached_saved_copy = None
            self._cached_output = cached_output_path(signature=sig, generation=self._cached_generation)
        if force_regenerate:
            self._cached_generation += 1
            self._cached_saved_copy = None
            self._cached_output = cached_output_path(signature=sig, generation=self._cached_generation)
        assert self._cached_output is not None
        return self._cached_output

    def _ensure_generated_then(self, *, force_regenerate: bool, after: Callable[[Path], None]) -> None:
        out = self._get_or_prepare_cached_output(force_regenerate=force_regenerate)
        # If already generated and we are not forcing regeneration, reuse it.
        if self._is_reusable_output(out) and not force_regenerate:
            after(out)
            return
        self._run_compare_to_path(out_path=str(out), on_success="none", post_success=after)

    def _prompt_move_or_copy_if_already_saved(self) -> str:
        """Return 'move', 'copy', or 'cancel' for a re-save flow."""
        if not (self._cached_saved_copy and self._cached_saved_copy.exists()):
            return "copy"
        # askyesnocancel => True/False/None
        choice = messagebox.askyesnocancel(
            self.title(),
            f"Output was previously saved to:\n{self._cached_saved_copy}\n\n"
            "Do you want to move it to a new location?\n\n"
            "Yes = Move (old path will no longer exist)\n"
            "No = Create a copy (keep old path too)\n"
            "Cancel = Do nothing",
        )
        if choice is None:
            return "cancel"
        return "move" if choice else "copy"

    def _on_compare_save(self) -> None:
        def after(gen_path: Path) -> None:
            mode = self._prompt_move_or_copy_if_already_saved()
            if mode == "cancel":
                return
            dest = pick_save_path_via_dialog(
                self._save_dialog,
                title="Save comparison output as…",
                filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
                defaultextension=".docx",
            )
            if not dest:
                return
            try:
                if mode == "move" and self._cached_saved_copy and self._cached_saved_copy.exists():
                    try:
                        self._cached_saved_copy.replace(dest)
                    except OSError:
                        # Cross-device move fallback.
                        shutil.copyfile(self._cached_saved_copy, dest)
                        self._cached_saved_copy.unlink(missing_ok=True)
                else:
                    shutil.copyfile(gen_path, dest)
            except OSError as exc:
                messagebox.showerror(self.title(), f"Could not save output: {exc}")
                return
            self._cached_saved_copy = Path(dest)
            self._mark_session_materialized(self._cached_saved_copy)
            self._persist_compare_saved_path(self._current_sig(), self._cached_saved_copy)
            messagebox.showinfo(self.title(), f"Saved to:\n{dest}")

        self._ensure_generated_then(force_regenerate=False, after=after)

    def _on_compare_open(self) -> None:
        self._restore_compare_saved_path_from_prefs()
        if self._cached_saved_copy and self._cached_saved_copy.exists():
            p = self._cached_saved_copy
            if sys.platform == "win32":
                ok, err = open_in_word_with_temp_track_changes_options(
                    p,
                    track_changes_options=dict(self._word_track_changes_options),
                    as_new_unsaved_document=False,
                )
                if not ok:
                    messagebox.showwarning(self.title(), (err or "Could not open in Word.").strip())
                    warn = open_path_with_default_app(p)
                    if warn:
                        messagebox.showwarning(self.title(), warn)
            else:
                warn = open_path_with_default_app(p)
                if warn:
                    messagebox.showwarning(self.title(), warn)
            return

        def after(gen_path: Path) -> None:
            self._restore_compare_saved_path_from_prefs()
            if self._cached_saved_copy and self._cached_saved_copy.exists():
                p = self._cached_saved_copy
                if sys.platform == "win32":
                    ok, err = open_in_word_with_temp_track_changes_options(
                        p,
                        track_changes_options=dict(self._word_track_changes_options),
                        as_new_unsaved_document=False,
                    )
                    if not ok:
                        messagebox.showwarning(self.title(), (err or "Could not open in Word.").strip())
                        warn = open_path_with_default_app(p)
                        if warn:
                            messagebox.showwarning(self.title(), warn)
                else:
                    warn = open_path_with_default_app(p)
                    if warn:
                        messagebox.showwarning(self.title(), warn)
                return

            sig = self._current_sig()
            if sys.platform == "win32":
                ok, err = open_in_word_with_temp_track_changes_options(
                    gen_path,
                    track_changes_options=dict(self._word_track_changes_options),
                    as_new_unsaved_document=True,
                    keep_source_file=True,
                    compare_signature_for_unsaved=sig,
                )
                if not ok:
                    messagebox.showwarning(self.title(), (err or "Could not open in Word.").strip())
                    warn = open_path_with_default_app(gen_path)
                    if warn:
                        messagebox.showwarning(self.title(), warn)
                else:
                    self._schedule_word_save_poll(sig)
            else:
                warn = open_path_with_default_app(gen_path)
                if warn:
                    messagebox.showwarning(self.title(), warn)

            messagebox.showinfo(
                self.title(),
                "Opened a temporary comparison document.\n\n"
                "Closing it will discard it.\n\n"
                "To keep a copy, use Save As… in your editor (not Save).",
            )

        self._ensure_generated_then(force_regenerate=False, after=after)

    def _on_compare_save_open(self) -> None:
        # Requirement: ask for save location BEFORE generating.
        mode = self._prompt_move_or_copy_if_already_saved()
        if mode == "cancel":
            return
        dest = pick_save_path_via_dialog(
            self._save_dialog,
            title="Save comparison output as…",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
            defaultextension=".docx",
        )
        if not dest:
            return

        # If we already have a generated output for this signature, reuse it (no regeneration).
        gen_path = self._get_or_prepare_cached_output(force_regenerate=False)
        if self._is_reusable_output(gen_path):
            try:
                if mode == "move" and self._cached_saved_copy and self._cached_saved_copy.exists():
                    try:
                        self._cached_saved_copy.replace(dest)
                    except OSError:
                        shutil.copyfile(self._cached_saved_copy, dest)
                        self._cached_saved_copy.unlink(missing_ok=True)
                else:
                    shutil.copyfile(gen_path, dest)
            except OSError as exc:
                messagebox.showerror(self.title(), f"Could not save output: {exc}")
                return
            self._cached_saved_copy = Path(dest)
            self._mark_session_materialized(self._cached_saved_copy)
            self._persist_compare_saved_path(self._current_sig(), self._cached_saved_copy)
            # Open saved file (file-backed).
            if sys.platform == "win32":
                ok, err = open_in_word_with_temp_track_changes_options(
                    self._cached_saved_copy,
                    track_changes_options=dict(self._word_track_changes_options),
                    as_new_unsaved_document=False,
                )
                if not ok:
                    messagebox.showwarning(self.title(), (err or "Could not open in Word.").strip())
                    warn = open_path_with_default_app(self._cached_saved_copy)
                    if warn:
                        messagebox.showwarning(self.title(), warn)
            else:
                warn = open_path_with_default_app(self._cached_saved_copy)
                if warn:
                    messagebox.showwarning(self.title(), warn)
            return

        def after_generate(_generated_path: Path) -> None:
            # Generated directly to dest.
            self._cached_saved_copy = Path(dest)
            self._persist_compare_saved_path(self._current_sig(), self._cached_saved_copy)
            if sys.platform == "win32":
                ok, err = open_in_word_with_temp_track_changes_options(
                    self._cached_saved_copy,
                    track_changes_options=dict(self._word_track_changes_options),
                    as_new_unsaved_document=False,
                )
                if not ok:
                    messagebox.showwarning(self.title(), (err or "Could not open in Word.").strip())
                    warn = open_path_with_default_app(self._cached_saved_copy)
                    if warn:
                        messagebox.showwarning(self.title(), warn)
            else:
                warn = open_path_with_default_app(self._cached_saved_copy)
                if warn:
                    messagebox.showwarning(self.title(), warn)

        # Generate to the user-selected destination path.
        # Also treat it as the cached output for this signature so later "Open" uses it.
        self._cached_output = Path(dest)
        self._run_compare_to_path(out_path=dest, on_success="none", post_success=after_generate)

    def _on_recompare(self) -> None:
        # Force a new generation (doc4) and make subsequent actions operate on it.
        self._clear_compare_saved_path_pref_for_sig(self._current_sig())
        self._ensure_generated_then(force_regenerate=True, after=lambda _p: None)

    def _show_progress_dialog(self, headline: str) -> dict[str, Callable[[], None]]:
        """Show a modal progress dialog with an indeterminate bar.

        This avoids freezing the UI and does not claim percent completion.
        """
        dlg = tk.Toplevel(self)
        dlg.title(self.title())
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=headline, font=("", 10, "bold"), wraplength=420).pack(anchor=tk.W)
        detail_var = tk.StringVar(value="This can take a while for large documents.")
        ttk.Label(frame, textvariable=detail_var, wraplength=420).pack(anchor=tk.W, pady=(6, 0))
        bar = ttk.Progressbar(frame, mode="indeterminate", length=420)
        bar.pack(fill=tk.X, pady=(10, 0))
        bar.start(12)

        started = time.time()

        def tick() -> None:
            elapsed = int(time.time() - started)
            detail_var.set(f"Working… {elapsed}s elapsed")
            if dlg.winfo_exists():
                dlg.after(1000, tick)

        dlg.after(1000, tick)

        def close() -> None:
            if not dlg.winfo_exists():
                return
            try:
                bar.stop()
            except tk.TclError:
                pass
            try:
                dlg.grab_release()
            except tk.TclError:
                pass
            dlg.destroy()

        dlg.update_idletasks()
        return {"close": close}

    def _delete_when_closed(self, path: Path) -> None:
        """Best-effort: delete a temp output once the user closes the viewer app."""

        def worker() -> None:
            deadline = time.time() + 24 * 60 * 60
            while time.time() < deadline:
                if not path.exists():
                    return
                try:
                    path.unlink()
                    return
                except OSError:
                    time.sleep(2.0)

        threading.Thread(target=worker, name="temp-docx-cleaner", daemon=True).start()
