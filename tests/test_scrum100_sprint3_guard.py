"""SCRUM-100: guard that Sprint 3 (MDC-008–010) engine surfaces stay importable and coherent."""

from __future__ import annotations

import zipfile
from pathlib import Path

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_revision_emit import build_paragraph_track_change_elements
from engine.document_package import parse_docx_document_package
from engine.table_diff import diff_table_blocks


def test_sprint3_table_diff_and_track_change_builder_round_trip() -> None:
    table_orig = {
        "type": "table",
        "id": "t1",
        "rows": [
            [
                {
                    "paragraphs": [
                        {
                            "type": "paragraph",
                            "id": "p1",
                            "runs": [{"text": "x"}],
                        }
                    ]
                }
            ]
        ],
    }
    table_rev = {
        "type": "table",
        "id": "t1",
        "rows": [
            [
                {
                    "paragraphs": [
                        {
                            "type": "paragraph",
                            "id": "p1",
                            "runs": [{"text": "y"}],
                        }
                    ]
                }
            ]
        ],
    }
    ops = diff_table_blocks(
        table_orig,
        table_rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=0,
    )
    assert len(ops) == 1
    assert ops[0]["op"] == "replace"

    para_orig = {"type": "paragraph", "id": "a", "runs": [{"text": "a"}]}
    para_rev = {"type": "paragraph", "id": "b", "runs": [{"text": "ab"}]}
    els = build_paragraph_track_change_elements(
        para_orig,
        para_rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Guard",
        date_iso="2026-03-27T00:00:00Z",
    )
    assert any(e.tag.endswith("ins") for e in els)


def test_sprint3_parse_document_package_callable(tmp_path: Path) -> None:
    word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    doc = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{word_ns}"><w:body><w:p><w:r><w:t>z</w:t></w:r></w:p></w:body></w:document>
"""
    p = tmp_path / "pkg.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", doc)
    pkg = parse_docx_document_package(p)
    assert pkg["version"] == 1
    assert pkg["document"]["blocks"][0]["runs"][0]["text"] == "z"
    assert pkg["header_footer"] == {}
