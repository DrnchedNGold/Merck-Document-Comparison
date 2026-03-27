import zipfile
from pathlib import Path

import pytest

from engine.docx_body_ingest import DocumentXmlMissingError
from engine.preflight_validation import (
    CommentsDetectedError,
    InvalidDocxFileTypeError,
    InvalidDocxZipFileError,
    TrackedChangesDetectedError,
    validate_docx_for_preflight,
)

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx_with_entries(tmp_path: Path, *, entries: dict[str, str]) -> Path:
    docx_path = tmp_path / "fixture.docx"
    with zipfile.ZipFile(docx_path, "w") as zf:
        for entry_name, entry_xml in entries.items():
            zf.writestr(entry_name, entry_xml)
    return docx_path


def test_preflight_rejects_non_docx_extension(tmp_path: Path) -> None:
    non_docx = tmp_path / "fixture.txt"
    non_docx.write_text("not a docx", encoding="utf-8")

    with pytest.raises(InvalidDocxFileTypeError) as exc:
        validate_docx_for_preflight(non_docx)

    assert (
        str(exc.value)
        == f"Invalid file type for '{non_docx}': expected '.docx' but got '.txt'."
    )


def test_preflight_rejects_docx_that_is_not_a_zip(tmp_path: Path) -> None:
    not_zip = tmp_path / "fixture.docx"
    not_zip.write_text("this is not a zip", encoding="utf-8")

    with pytest.raises(InvalidDocxZipFileError) as exc:
        validate_docx_for_preflight(not_zip)

    assert str(exc.value) == f"Invalid DOCX zip file for '{not_zip}': file is not a valid zip."


def test_preflight_rejects_tracked_changes_w_ins(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:r><w:t>before</w:t></w:r>
      <w:ins w:id="1"><w:r><w:t>after</w:t></w:r></w:ins>
    </w:p>
  </w:body>
</w:document>
"""

    docx_path = _make_docx_with_entries(tmp_path, entries={"word/document.xml": document_xml})

    with pytest.raises(TrackedChangesDetectedError) as exc:
        validate_docx_for_preflight(docx_path)

    assert str(exc.value) == f"Tracked changes detected in '{docx_path}': w:ins=1, w:del=0."


def test_preflight_rejects_tracked_changes_w_del(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:r><w:t>before</w:t></w:r>
      <w:del w:id="1"><w:r><w:t>removed</w:t></w:r></w:del>
    </w:p>
  </w:body>
</w:document>
"""

    docx_path = _make_docx_with_entries(tmp_path, entries={"word/document.xml": document_xml})

    with pytest.raises(TrackedChangesDetectedError) as exc:
        validate_docx_for_preflight(docx_path)

    assert str(exc.value) == f"Tracked changes detected in '{docx_path}': w:ins=0, w:del=1."


def test_preflight_rejects_comments_by_markers_in_document_xml(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:commentRangeStart w:id="0"/>
      <w:r><w:t>commented</w:t></w:r>
      <w:commentRangeEnd w:id="0"/>
      <w:r><w:commentReference w:id="0"/></w:r>
    </w:p>
  </w:body>
</w:document>
"""

    docx_path = _make_docx_with_entries(tmp_path, entries={"word/document.xml": document_xml})

    with pytest.raises(CommentsDetectedError) as exc:
        validate_docx_for_preflight(docx_path)

    assert (
        str(exc.value)
        == (
            f"Comments detected in '{docx_path}': "
            f"w:commentRangeStart=1, w:commentRangeEnd=1, w:commentReference=1, "
            f"word/comments.xml=missing."
        )
    )


def test_preflight_rejects_comments_by_comments_xml_entry(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:r><w:t>no markers in document.xml</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""

    docx_path = _make_docx_with_entries(
        tmp_path,
        entries={
            "word/document.xml": document_xml,
            "word/comments.xml": "<comments/>",
        },
    )

    with pytest.raises(CommentsDetectedError) as exc:
        validate_docx_for_preflight(docx_path)

    assert (
        str(exc.value)
        == (
            f"Comments detected in '{docx_path}': "
            f"w:commentRangeStart=0, w:commentRangeEnd=0, w:commentReference=0, "
            f"word/comments.xml=present."
        )
    )


def test_preflight_propagates_document_xml_missing_error(tmp_path: Path) -> None:
    docx_path = tmp_path / "missing.docx"
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/_rels/document.xml.rels", "<rels/>")

    with pytest.raises(DocumentXmlMissingError) as exc:
        validate_docx_for_preflight(docx_path)

    assert "word/document.xml" in str(exc.value)

