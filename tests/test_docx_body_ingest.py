import zipfile
from pathlib import Path

import pytest

from engine.docx_body_ingest import (
    DocumentXmlMissingError,
    load_word_document_xml_root,
    parse_docx_body_ir,
)


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx_with_document_xml(tmp_path: Path, document_xml: str) -> Path:
    docx_path = tmp_path / "fixture.docx"
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return docx_path


def test_parse_docx_body_ir_happy_path(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:r><w:t>The quick brown fox.</w:t></w:r>
      <w:r><w:t>Second run.</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Paragraph two.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""

    docx_path = _make_docx_with_document_xml(tmp_path, document_xml)
    body_ir = parse_docx_body_ir(docx_path)

    assert body_ir == {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [
                    {"text": "The quick brown fox."},
                    {"text": "Second run."},
                ],
            },
            {
                "type": "paragraph",
                "id": "p2",
                "runs": [{"text": "Paragraph two."}],
            },
        ],
    }


def test_parse_docx_body_ir_missing_document_xml(tmp_path: Path) -> None:
    docx_path = tmp_path / "missing.docx"
    with zipfile.ZipFile(docx_path, "w") as zf:
        # Intentionally omit word/document.xml
        zf.writestr("word/_rels/document.xml.rels", "<rels/>")

    with pytest.raises(DocumentXmlMissingError) as exc:
        parse_docx_body_ir(docx_path)

    assert "word/document.xml" in str(exc.value)


def test_parse_docx_body_ir_skips_runs_with_no_text_nodes(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:r></w:r>
      <w:r><w:t>Visible text only.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""

    docx_path = _make_docx_with_document_xml(tmp_path, document_xml)
    body_ir = parse_docx_body_ir(docx_path)
    assert body_ir["blocks"][0]["runs"] == [{"text": "Visible text only."}]


def test_load_word_document_xml_root_parses_document(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body><w:p><w:r><w:t>x</w:t></w:r></w:p></w:body>
</w:document>
"""
    docx_path = _make_docx_with_document_xml(tmp_path, document_xml)
    root = load_word_document_xml_root(docx_path)
    assert root.tag.endswith("document")

