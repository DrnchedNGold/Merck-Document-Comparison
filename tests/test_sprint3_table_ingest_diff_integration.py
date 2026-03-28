"""SCRUM-100: minimal .docx table ingest → BodyTable → diff_table_blocks (MDC-008)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_compare import matched_document_package_inline_diffs
from engine.contracts import validate_body_ir
from engine.docx_body_ingest import parse_docx_body_ir
from engine.document_package import parse_docx_document_package
from engine.docx_package_parts import DOCUMENT_PART_PATH
from engine.table_diff import diff_table_blocks

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx_with_table(tmp_path: Path, cell_text: str, name: str) -> Path:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:tbl>
      <w:tr>
        <w:tc>
          <w:p><w:r><w:t>{cell_text}</w:t></w:r></w:p>
        </w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return p


def test_ingested_one_by_one_table_diffs_cell_text(tmp_path: Path) -> None:
    # Use disjoint strings so difflib emits one clean ``replace`` (same as ``test_table_diff``).
    orig_path = _docx_with_table(tmp_path, "old", "t_orig.docx")
    rev_path = _docx_with_table(tmp_path, "new", "t_rev.docx")

    orig_ir = parse_docx_body_ir(orig_path)
    rev_ir = parse_docx_body_ir(rev_path)

    assert validate_body_ir(orig_ir) == []
    assert validate_body_ir(rev_ir) == []

    assert len(orig_ir["blocks"]) == 1
    assert orig_ir["blocks"][0]["type"] == "table"
    assert rev_ir["blocks"][0]["type"] == "table"

    ops = diff_table_blocks(
        orig_ir["blocks"][0],  # type: ignore[arg-type]
        rev_ir["blocks"][0],  # type: ignore[arg-type]
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=0,
    )
    assert ops == [
        {
            "op": "replace",
            "path": "blocks/0/rows/0/cells/0/inline/0",
            "before": "old",
            "after": "new",
        }
    ]


def test_package_compare_table_only_bodies_emit_document_part_ops(tmp_path: Path) -> None:
    orig_path = _docx_with_table(tmp_path, "old", "pkg_orig.docx")
    rev_path = _docx_with_table(tmp_path, "new", "pkg_rev.docx")
    rows = matched_document_package_inline_diffs(
        parse_docx_document_package(orig_path),
        parse_docx_document_package(rev_path),
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    doc_rows = [r for r in rows if r.part == DOCUMENT_PART_PATH]
    assert len(doc_rows) == 1
    assert doc_rows[0].diff_ops == [
        {
            "op": "replace",
            "path": "blocks/0/rows/0/cells/0/inline/0",
            "before": "old",
            "after": "new",
            "part": DOCUMENT_PART_PATH,
        }
    ]
