"""SCRUM-64 / MDC-011: revision metadata on ins/del and header/footer part emit."""

from __future__ import annotations

import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_revision_emit import (
    build_paragraph_track_change_elements,
    emit_docx_with_package_track_changes,
)
from engine.docx_body_ingest import load_word_document_xml_root

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


def _local_name(tag: str) -> str:
    return tag.split("}", maxsplit=1)[-1] if "}" in tag else tag


def _paragraph_block(text: str) -> dict:
    return {"type": "paragraph", "id": "p1", "runs": [{"text": text}]}


def test_ins_del_include_w_id_author_date() -> None:
    # Single-token replace keeps common prefix "a" unchanged and inserts only "b".
    ins_els = build_paragraph_track_change_elements(
        _paragraph_block("a"),
        _paragraph_block("ab"),
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="MetaAuthor",
        date_iso="2026-03-27T15:00:00Z",
    )
    ins_nodes = [e for e in ins_els if _local_name(e.tag) == "ins"]
    del_nodes = [e for e in ins_els if _local_name(e.tag) == "del"]
    assert len(ins_nodes) == 1
    assert len(del_nodes) == 0
    ins = ins_nodes[0]
    assert ins.get(f"{{{WORD_NS}}}id") == "1"
    assert ins.get(f"{{{WORD_NS}}}author") == "MetaAuthor"
    assert ins.get(f"{{{WORD_NS}}}date") == "2026-03-27T15:00:00Z"

    del_els = build_paragraph_track_change_elements(
        _paragraph_block("xy"),
        _paragraph_block("x"),
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="DelAuthor",
        date_iso="2026-03-27T16:00:00Z",
    )
    del_nodes = [e for e in del_els if _local_name(e.tag) == "del"]
    ins2 = [e for e in del_els if _local_name(e.tag) == "ins"]
    assert len(del_nodes) == 1
    assert len(ins2) == 0
    d = del_nodes[0]
    assert d.get(f"{{{WORD_NS}}}id") == "1"
    assert d.get(f"{{{WORD_NS}}}author") == "DelAuthor"
    assert d.get(f"{{{WORD_NS}}}date") == "2026-03-27T16:00:00Z"


def _docx_with_body_and_header(
    tmp_path: Path,
    *,
    body_text: str,
    header_text: str,
    filename: str,
) -> Path:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p><w:r><w:t>{body_text}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    header_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{WORD_NS}">
  <w:p><w:r><w:t>{header_text}</w:t></w:r></w:p>
</w:hdr>
"""
    p = tmp_path / filename
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/header1.xml", header_xml)
    return p


def test_header_part_receives_ins_when_header_text_changes(tmp_path: Path) -> None:
    orig = _docx_with_body_and_header(
        tmp_path, body_text="Body", header_text="HdrOld", filename="oh_orig.docx"
    )
    rev = _docx_with_body_and_header(
        tmp_path, body_text="Body", header_text="HdrNew", filename="oh_rev.docx"
    )
    out = tmp_path / "oh_out.docx"
    emit_docx_with_package_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author="HFTest",
        date_iso="2026-03-27T18:00:00Z",
    )
    with zipfile.ZipFile(out, "r") as zf:
        hdr_root = ET.fromstring(zf.read("word/header1.xml"))
    ins_list = hdr_root.findall(".//w:ins", NS)
    dels = hdr_root.findall(".//w:del", NS)
    assert len(ins_list) == 1
    assert len(dels) == 1
    assert ins_list[0].get(f"{{{WORD_NS}}}author") == "HFTest"
    assert ins_list[0].get(f"{{{WORD_NS}}}date") == "2026-03-27T18:00:00Z"
    assert ins_list[0].get(f"{{{WORD_NS}}}id") is not None
    t_parts = [t.text or "" for t in ins_list[0].findall(".//w:t", NS)]
    # Shared prefix "Hdr" remains plain text; only changed core is inserted.
    assert "".join(t_parts) == "New"


def test_w_ids_unique_across_document_and_header(tmp_path: Path) -> None:
    orig = _docx_with_body_and_header(
        tmp_path, body_text="B", header_text="H", filename="id_orig.docx"
    )
    rev = _docx_with_body_and_header(
        tmp_path, body_text="BX", header_text="HY", filename="id_rev.docx"
    )
    out = tmp_path / "id_out.docx"
    emit_docx_with_package_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author="IdTest",
        date_iso="2026-03-27T19:00:00Z",
    )

    def collect_revision_ids(xml_bytes: bytes) -> list[str]:
        root = ET.fromstring(xml_bytes)
        ids: list[str] = []
        for el in root.iter():
            if _local_name(el.tag) not in ("ins", "del"):
                continue
            i = el.get(f"{{{WORD_NS}}}id")
            if i is not None:
                ids.append(i)
        return ids

    with zipfile.ZipFile(out, "r") as zf:
        doc_ids = collect_revision_ids(zf.read("word/document.xml"))
        hdr_ids = collect_revision_ids(zf.read("word/header1.xml"))

    assert sorted(doc_ids + hdr_ids) == ["1", "2"]

    doc_root = load_word_document_xml_root(out)
    doc_ins = doc_root.findall(".//w:ins", NS)
    assert len(doc_ins) == 1
    assert doc_ins[0].get(f"{{{WORD_NS}}}id") == "1"


def _docx_with_body_and_footer(
    tmp_path: Path,
    *,
    body_text: str,
    footer_text: str,
    filename: str,
) -> Path:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    <w:p><w:r><w:t>{body_text}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    footer_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{WORD_NS}">
  <w:p><w:r><w:t>{footer_text}</w:t></w:r></w:p>
</w:ftr>
"""
    p = tmp_path / filename
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/footer1.xml", footer_xml)
    return p


def test_footer_part_receives_del_when_footer_text_removed(tmp_path: Path) -> None:
    # Spaced words so word-level diff deletes " Long" (not one token "FootLong" vs "Foot").
    orig = _docx_with_body_and_footer(
        tmp_path, body_text="X", footer_text="Foot Long", filename="ftr_orig.docx"
    )
    rev = _docx_with_body_and_footer(
        tmp_path, body_text="X", footer_text="Foot", filename="ftr_rev.docx"
    )
    out = tmp_path / "ftr_out.docx"
    emit_docx_with_package_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author="FtrAuthor",
        date_iso="2026-03-27T20:00:00Z",
    )
    with zipfile.ZipFile(out, "r") as zf:
        ftr_root = ET.fromstring(zf.read("word/footer1.xml"))
    dels = ftr_root.findall(".//w:del", NS)
    assert len(dels) == 1
    assert dels[0].get(f"{{{WORD_NS}}}author") == "FtrAuthor"
    assert dels[0].get(f"{{{WORD_NS}}}date") == "2026-03-27T20:00:00Z"
    assert dels[0].get(f"{{{WORD_NS}}}id") == "1"
