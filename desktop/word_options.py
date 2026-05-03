"""Desktop helpers for Track Changes option handling.

Windows can apply the full Word application-level options via COM. On every
platform we can also write the portable document-level revision settings into a
generated ``.docx`` package so the output carries those defaults with it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from desktop.profiles import validate_word_track_changes_options
from engine.ooxml_namespace import serialize_ooxml_part

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SETTINGS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
SETTINGS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"
SETTINGS_PART_PATH = "word/settings.xml"
DOCUMENT_RELS_PATH = "word/_rels/document.xml.rels"
CONTENT_TYPES_PATH = "[Content_Types].xml"

ET.register_namespace("w", W_NS)


def _get_bool01(opts: dict[str, Any], key: str, default: int) -> int:
    v = opts.get(key, default)
    if isinstance(v, bool):
        return 1 if v else 0
    try:
        return 1 if int(v) != 0 else 0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _run_osascript(lines: list[str]) -> tuple[bool, str | None]:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        return False, details or "AppleScript automation failed."
    except OSError as exc:
        return False, str(exc)
    return True, None


def _serialize_xml(root: ET.Element, *, default_ns: str | None = None) -> bytes:
    if default_ns is not None:
        ET.register_namespace("", default_ns)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _max_rid(rels_root: ET.Element) -> int:
    max_num = 0
    for rel in rels_root.findall(f"{{{RELS_NS}}}Relationship"):
        rid = rel.get("Id", "")
        if rid.startswith("rId"):
            try:
                max_num = max(max_num, int(rid[3:]))
            except ValueError:
                continue
    return max_num


def _upsert_onoff_setting(settings_root: ET.Element, local_name: str, enabled: bool) -> None:
    tag = f"{{{W_NS}}}{local_name}"
    existing = settings_root.find(tag)
    if enabled:
        if existing is not None:
            settings_root.remove(existing)
        return
    if existing is None:
        existing = ET.Element(tag)
        settings_root.append(existing)
    existing.set(f"{{{W_NS}}}val", "true")


def apply_portable_track_changes_options_to_docx(
    doc_path: Path,
    *,
    track_changes_options: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Write portable document-level Track Changes defaults into ``word/settings.xml``."""
    if not doc_path.exists():
        return False, f"File not found: {doc_path}"

    opts = validate_word_track_changes_options(track_changes_options)

    try:
        with zipfile.ZipFile(doc_path, "r") as zin:
            members = {info.filename: zin.read(info.filename) for info in zin.infolist()}
    except (OSError, zipfile.BadZipFile) as exc:
        return False, str(exc)

    if CONTENT_TYPES_PATH not in members or DOCUMENT_RELS_PATH not in members:
        return False, "Document package is missing required OOXML parts."

    settings_raw = members.get(SETTINGS_PART_PATH)
    if settings_raw is None:
        settings_root = ET.Element(f"{{{W_NS}}}settings")
    else:
        settings_root = ET.fromstring(settings_raw)
    _upsert_onoff_setting(
        settings_root,
        "doNotTrackMoves",
        enabled=bool(_get_bool01(opts, "TrackMoves", 1)),
    )
    _upsert_onoff_setting(
        settings_root,
        "doNotTrackFormatting",
        enabled=bool(_get_bool01(opts, "TrackFormatting", 1)),
    )
    if settings_raw is None:
        members[SETTINGS_PART_PATH] = _serialize_xml(settings_root)
    else:
        members[SETTINGS_PART_PATH] = serialize_ooxml_part(settings_root, settings_raw)

    rels_root = ET.fromstring(members[DOCUMENT_RELS_PATH])
    rel = None
    for candidate in rels_root.findall(f"{{{RELS_NS}}}Relationship"):
        if candidate.get("Type") == SETTINGS_REL_TYPE:
            rel = candidate
            break
    if rel is None:
        rel = ET.SubElement(rels_root, f"{{{RELS_NS}}}Relationship")
        rel.set("Id", f"rId{_max_rid(rels_root) + 1}")
        rel.set("Type", SETTINGS_REL_TYPE)
    rel.set("Target", "settings.xml")
    members[DOCUMENT_RELS_PATH] = _serialize_xml(rels_root, default_ns=RELS_NS)

    content_types_root = ET.fromstring(members[CONTENT_TYPES_PATH])
    found_override = None
    for override in content_types_root.findall(f"{{{CT_NS}}}Override"):
        if override.get("PartName") == f"/{SETTINGS_PART_PATH}":
            found_override = override
            break
    if found_override is None:
        found_override = ET.SubElement(content_types_root, f"{{{CT_NS}}}Override")
        found_override.set("PartName", f"/{SETTINGS_PART_PATH}")
    found_override.set("ContentType", SETTINGS_CONTENT_TYPE)
    members[CONTENT_TYPES_PATH] = _serialize_xml(content_types_root, default_ns=CT_NS)

    tmp_dir = doc_path.parent
    fd, tmp_name = tempfile.mkstemp(prefix=f"{doc_path.stem}-wordopts-", suffix=".docx", dir=tmp_dir)
    os.close(fd)
    try:
        Path(tmp_name).unlink(missing_ok=True)
        with zipfile.ZipFile(doc_path, "r") as zin, zipfile.ZipFile(
            tmp_name,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as zout:
            seen: set[str] = set()
            for info in zin.infolist():
                payload = members.get(info.filename)
                if payload is None:
                    continue
                zi = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
                zi.compress_type = zipfile.ZIP_STORED
                zi.external_attr = info.external_attr
                zout.writestr(zi, payload)
                seen.add(info.filename)
            for name, payload in members.items():
                if name in seen:
                    continue
                zi = zipfile.ZipInfo(filename=name)
                zi.compress_type = zipfile.ZIP_STORED
                zout.writestr(zi, payload)
        Path(tmp_name).replace(doc_path)
    except (OSError, zipfile.BadZipFile) as exc:
        Path(tmp_name).unlink(missing_ok=True)
        return False, str(exc)
    finally:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
    return True, None


def apply_word_track_changes_options(
    *,
    track_changes_options: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Apply Track Changes options to Word (current user/machine)."""
    opts = validate_word_track_changes_options(track_changes_options)
    if sys.platform == "darwin":
        lines = [
            'tell application id "com.microsoft.Word"',
            "activate",
            "set wordSettings to settings",
            f'set inserted text mark of wordSettings to {int(opts.get("InsertedTextMark", 3))}',
            f'set inserted text color of wordSettings to {int(opts.get("InsertedTextColor", 6))}',
            f'set deleted text mark of wordSettings to {int(opts.get("DeletedTextMark", 1))}',
            f'set deleted text color of wordSettings to {int(opts.get("DeletedTextColor", 6))}',
            f'set revised properties mark of wordSettings to {int(opts.get("RevisedPropertiesMark", 0))}',
            f'set revised properties color of wordSettings to {int(opts.get("RevisedPropertiesColor", -1))}',
            f'set revised lines mark of wordSettings to {int(opts.get("RevisedLinesMark", 3))}',
            f'set revised lines color of wordSettings to {int(opts.get("RevisedLinesColor", 6))}',
            f'set comments color of wordSettings to {int(opts.get("CommentsColor", -1))}',
            f'set move from text mark of wordSettings to {int(opts.get("MoveFromTextMark", 7))}',
            f'set move from text color of wordSettings to {int(opts.get("MoveFromTextColor", 6))}',
            f'set move to text mark of wordSettings to {int(opts.get("MoveToTextMark", 4))}',
            f'set move to text color of wordSettings to {int(opts.get("MoveToTextColor", 6))}',
            f'set inserted cell color of wordSettings to {int(opts.get("InsertedCellColor", 2))}',
            f'set deleted cell color of wordSettings to {int(opts.get("DeletedCellColor", 1))}',
            f'set merged cell color of wordSettings to {int(opts.get("MergedCellColor", -1))}',
            f'set split cell color of wordSettings to {int(opts.get("SplitCellColor", -1))}',
            f'set keep track of formatting of wordSettings to {"true" if _get_bool01(opts, "TrackFormatting", 1) else "false"}',
            "end tell",
        ]
        return _run_osascript(lines)
    if sys.platform != "win32":
        return (
            True,
            "Saved portable Track Changes defaults. Word application-level colors and marks "
            "can only be automated on Windows.",
        )

    def _get_int(key: str, default: int) -> int:
        v = opts.get(key, default)
        return int(v) if isinstance(v, (int, float, str)) and str(v).strip() else default

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
  $doc.TrackMoves = ({_get_bool01(opts, "TrackMoves", 1)} -ne 0)
  $doc.TrackFormatting = ({_get_bool01(opts, "TrackFormatting", 1)} -ne 0)

  # Ensure markup is shown.
  $view = $word.ActiveWindow.View
  $view.ShowRevisionsAndComments = $true
  $view.RevisionsView = 0 # wdRevisionsViewFinal

  # Balloons (preferred width, connecting lines)
  $view.RevisionsBalloonWidthType = 1 # wdBalloonWidthPoints
  $view.RevisionsBalloonWidth = {(_get_float("BalloonsPreferredWidthInches", 3.7))} * 72.0
  $view.RevisionsBalloonShowConnectingLines = ({_get_bool01(opts, "BalloonsShowConnectingLines", 0)} -ne 0)

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
