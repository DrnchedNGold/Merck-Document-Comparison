"""End-to-end checks: synthetic .docx → preflight → ingest → keys → alignment."""

from __future__ import annotations

import zipfile
from pathlib import Path

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.compare_keys import generate_compare_keys
from engine.docx_body_ingest import parse_docx_body_ir
from engine.paragraph_alignment import align_paragraphs
from engine.preflight_validation import validate_docx_for_preflight

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_clean_docx(tmp_path: Path, document_xml: str) -> Path:
    docx_path = tmp_path / "pipeline.docx"
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return docx_path


def test_preflight_ingest_keys_and_alignment_are_consistent_on_fixture(tmp_path: Path) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p>
      <w:r><w:t>First.</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Second line.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""

    docx_path = _make_clean_docx(tmp_path, document_xml)
    validate_docx_for_preflight(docx_path)

    body_ir = parse_docx_body_ir(docx_path)
    keys = generate_compare_keys(body_ir, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert len(keys) == 2

    alignment = align_paragraphs(body_ir, body_ir, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert [(a.original_paragraph_index, a.revised_paragraph_index) for a in alignment] == [
        (0, 0),
        (1, 1),
    ]
