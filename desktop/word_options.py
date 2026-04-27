"""Windows-only helper: open a generated doc in Word with temporary Track Changes options.

This uses Word COM automation via PowerShell so we don't need extra Python deps.
We apply options, open the document, and then restore prior options in the same
Word instance. This is best-effort and affects only that Word instance/session.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def apply_word_track_changes_options(
    *,
    track_changes_options: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Apply Track Changes options to Word (current user/machine)."""
    opts = track_changes_options or {}

    def _get_int(key: str, default: int) -> int:
        v = opts.get(key, default)
        return int(v) if isinstance(v, (int, float, str)) and str(v).strip() else default

    def _get_bool01(key: str, default: int) -> int:
        v = opts.get(key, default)
        if isinstance(v, bool):
            return 1 if v else 0
        try:
            return 1 if int(v) != 0 else 0  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    ps = f"""
$ErrorActionPreference = "Stop"
$word = New-Object -ComObject Word.Application
try {{
  $opts = $word.Options
  $opts.InsertedTextMark = {_get_int("InsertedTextMark", 3)}
  $opts.InsertedTextColor = {_get_int("InsertedTextColor", 6)}
  $opts.DeletedTextMark = {_get_int("DeletedTextMark", 1)}
  $opts.DeletedTextColor = {_get_int("DeletedTextColor", 6)}
  $opts.RevisedPropertiesMark = {_get_int("RevisedPropertiesMark", 0)}
  $opts.RevisedPropertiesColor = {_get_int("RevisedPropertiesColor", -1)}
  $opts.RevisedLinesMark = {_get_int("RevisedLinesMark", 3)}
  $opts.RevisedLinesColor = {_get_int("RevisedLinesColor", 6)}
  $opts.CommentsColor = {_get_int("CommentsColor", -1)}

  # Moves + table cell highlighting (options-level)
  $opts.MoveFromTextMark = {_get_int("MoveFromTextMark", 7)}
  $opts.MoveFromTextColor = {_get_int("MoveFromTextColor", 6)}
  $opts.MoveToTextMark = {_get_int("MoveToTextMark", 4)}
  $opts.MoveToTextColor = {_get_int("MoveToTextColor", 6)}
  $opts.InsertedCellColor = {_get_int("InsertedCellColor", 2)}
  $opts.DeletedCellColor = {_get_int("DeletedCellColor", 1)}
  $opts.MergedCellColor = {_get_int("MergedCellColor", -1)}
  $opts.SplitCellColor = {_get_int("SplitCellColor", -1)}

  # Balloons print orientation
  $opts.RevisionsBalloonPrintOrientation = {_get_int("BalloonsPrintOrientation", 1)}
}} finally {{
  $word.Quit()
}}
"""
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        return False, details or "Failed to apply Word Track Changes options."
    except OSError as exc:
        return False, str(exc)
    return True, None


def open_in_word_with_temp_track_changes_options(
    doc_path: Path,
    *,
    track_changes_options: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    if not doc_path.exists():
        return False, f"File not found: {doc_path}"

    opts = track_changes_options or {}

    def _get_int(key: str, default: int) -> int:
        v = opts.get(key, default)
        return int(v) if isinstance(v, (int, float, str)) and str(v).strip() else default

    def _get_bool01(key: str, default: int) -> int:
        v = opts.get(key, default)
        if isinstance(v, bool):
            return 1 if v else 0
        try:
            return 1 if int(v) != 0 else 0  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def _get_float(key: str, default: float) -> float:
        v = opts.get(key, default)
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    # See: Word Options.* (InsertedTextColor, DeletedTextColor, etc.)
    # We set the same knobs the user changes in Advanced Track Changes Options.
    ps = f"""
$ErrorActionPreference = "Stop"
$p = "{str(doc_path.resolve()).replace('"', '""')}"
$word = New-Object -ComObject Word.Application
try {{
  $opts = $word.Options
  # Apply requested global options (persist for this user/machine).
  $opts.InsertedTextMark = {_get_int("InsertedTextMark", 3)}
  $opts.InsertedTextColor = {_get_int("InsertedTextColor", 6)}
  $opts.DeletedTextMark = {_get_int("DeletedTextMark", 1)}
  $opts.DeletedTextColor = {_get_int("DeletedTextColor", 6)}
  $opts.RevisedPropertiesMark = {_get_int("RevisedPropertiesMark", 0)}
  $opts.RevisedPropertiesColor = {_get_int("RevisedPropertiesColor", -1)}
  $opts.RevisedLinesMark = {_get_int("RevisedLinesMark", 3)}
  $opts.RevisedLinesColor = {_get_int("RevisedLinesColor", 6)}
  $opts.CommentsColor = {_get_int("CommentsColor", -1)}
  $opts.MoveFromTextMark = {_get_int("MoveFromTextMark", 7)}
  $opts.MoveFromTextColor = {_get_int("MoveFromTextColor", 6)}
  $opts.MoveToTextMark = {_get_int("MoveToTextMark", 4)}
  $opts.MoveToTextColor = {_get_int("MoveToTextColor", 6)}
  $opts.InsertedCellColor = {_get_int("InsertedCellColor", 2)}
  $opts.DeletedCellColor = {_get_int("DeletedCellColor", 1)}
  $opts.MergedCellColor = {_get_int("MergedCellColor", -1)}
  $opts.SplitCellColor = {_get_int("SplitCellColor", -1)}
  $opts.RevisionsBalloonPrintOrientation = {_get_int("BalloonsPrintOrientation", 1)}

  $word.Visible = $true
  $doc = $word.Documents.Open($p, $false, $false) # not read-only (document track-moves/formatting)
  $doc.Activate() | Out-Null

  # Document-scoped settings
  $doc.TrackMoves = ({_get_bool01("TrackMoves", 1)} -ne 0)
  $doc.TrackFormatting = ({_get_bool01("TrackFormatting", 1)} -ne 0)

  # Ensure markup is shown.
  $view = $word.ActiveWindow.View
  $view.ShowRevisionsAndComments = $true
  $view.RevisionsView = 0 # wdRevisionsViewFinal

  # Balloons (preferred width, connecting lines)
  $view.RevisionsBalloonWidthType = 1 # wdBalloonWidthPoints
  $view.RevisionsBalloonWidth = {(_get_float("BalloonsPreferredWidthInches", 3.7))} * 72.0
  $view.RevisionsBalloonShowConnectingLines = ({_get_bool01("BalloonsShowConnectingLines", 0)} -ne 0)

}} catch {{
  throw
}}
"""

    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        return False, details or "Failed to open Word with Track Changes options."
    except OSError as exc:
        return False, str(exc)
    return True, None

