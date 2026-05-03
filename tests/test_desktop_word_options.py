from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from desktop.word_options import (
    SETTINGS_PART_PATH,
    apply_portable_track_changes_options_to_docx,
    apply_word_track_changes_options,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _docx(tmp_path: Path, *, include_settings: bool) -> Path:
    path = tmp_path / "sample.docx"
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>x</w:t></w:r></w:p></w:body></w:document>
"""
    settings_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{W_NS}">
  <w:doNotTrackMoves w:val="true"/>
  <w:doNotTrackFormatting w:val="true"/>
</w:settings>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels)
        if include_settings:
            zf.writestr("word/settings.xml", settings_xml)
    return path


def test_apply_portable_track_changes_options_creates_settings_part(tmp_path: Path) -> None:
    path = _docx(tmp_path, include_settings=False)
    ok, err = apply_portable_track_changes_options_to_docx(
        path,
        track_changes_options={"TrackMoves": 0, "TrackFormatting": 0},
    )
    assert ok is True
    assert err is None

    with zipfile.ZipFile(path, "r") as zf:
        settings_root = ET.fromstring(zf.read(SETTINGS_PART_PATH))
        rels_root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
        content_root = ET.fromstring(zf.read("[Content_Types].xml"))

    assert settings_root.find(f"{{{W_NS}}}doNotTrackMoves") is not None
    assert settings_root.find(f"{{{W_NS}}}doNotTrackFormatting") is not None
    assert any(
        rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
        and rel.get("Target") == "settings.xml"
        for rel in rels_root.findall(f"{{{RELS_NS}}}Relationship")
    )
    assert any(
        override.get("PartName") == "/word/settings.xml"
        for override in content_root.findall(f"{{{CT_NS}}}Override")
    )


def test_apply_portable_track_changes_options_removes_do_not_track_flags_when_enabled(
    tmp_path: Path,
) -> None:
    path = _docx(tmp_path, include_settings=True)
    ok, err = apply_portable_track_changes_options_to_docx(
        path,
        track_changes_options={"TrackMoves": 1, "TrackFormatting": 1},
    )
    assert ok is True
    assert err is None

    with zipfile.ZipFile(path, "r") as zf:
        settings_root = ET.fromstring(zf.read(SETTINGS_PART_PATH))
    assert settings_root.find(f"{{{W_NS}}}doNotTrackMoves") is None
    assert settings_root.find(f"{{{W_NS}}}doNotTrackFormatting") is None


def test_apply_portable_track_changes_options_preserves_settings_root_prefixes(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>
"""
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>x</w:t></w:r></w:p></w:body></w:document>
"""
    settings_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:w="{W_NS}"
 xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
 mc:Ignorable="w14">
  <w:doNotTrackMoves w:val="true"/>
  <w14:docId w14:val="24062061"/>
</w:settings>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels)
        zf.writestr("word/settings.xml", settings_xml)

    ok, err = apply_portable_track_changes_options_to_docx(
        path,
        track_changes_options={"TrackMoves": 1, "TrackFormatting": 0},
    )
    assert ok is True
    assert err is None

    with zipfile.ZipFile(path, "r") as zf:
        settings_raw = zf.read("word/settings.xml").decode("utf-8")
    assert 'mc:Ignorable="w14"' in settings_raw
    assert 'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"' in settings_raw
    assert "<w14:docId " in settings_raw


def test_apply_word_track_changes_options_non_windows_returns_portable_message() -> None:
    with patch.object(sys, "platform", "linux"):
        ok, err = apply_word_track_changes_options(track_changes_options={"TrackMoves": 0})
    assert ok is True
    assert err is not None
    assert "portable" in err.lower()


@patch("desktop.word_options.subprocess.run", return_value=MagicMock(returncode=0))
def test_apply_word_track_changes_options_macos_uses_osascript(mock_run: MagicMock) -> None:
    with patch.object(sys, "platform", "darwin"):
        ok, err = apply_word_track_changes_options(
            track_changes_options={
                "InsertedTextColor": 6,
                "DeletedTextMark": 1,
                "TrackFormatting": 0,
            }
        )
    assert ok is True
    assert err is None
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "osascript"
    rendered = " ".join(cmd)
    assert 'application id "com.microsoft.Word"' in rendered
    assert "set inserted text color of wordSettings to 6" in rendered
    assert "set deleted text mark of wordSettings to 1" in rendered
    assert "set keep track of formatting of wordSettings to false" in rendered


@patch("desktop.word_options.subprocess.run", return_value=MagicMock(returncode=0))
def test_apply_word_track_changes_options_windows_uses_powershell(mock_run: MagicMock) -> None:
    with patch.object(sys, "platform", "win32"):
        ok, err = apply_word_track_changes_options(track_changes_options={"InsertedTextColor": 6})
    assert ok is True
    assert err is None
    assert mock_run.call_args[0][0][0] == "powershell"
