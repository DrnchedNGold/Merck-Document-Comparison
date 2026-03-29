"""SCRUM-61: assert w:ins / w:del shape in generated document XML (SCRUM-58)."""

from __future__ import annotations

import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_revision_emit import (
    build_paragraph_track_change_elements,
    emit_docx_with_body_track_changes,
)
from engine.docx_body_ingest import load_word_document_xml_root
from engine.docx_output_package import write_docx_copy_with_part_replacements

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


def _local_name(tag: str) -> str:
    return tag.split("}", maxsplit=1)[-1] if "}" in tag else tag


def _paragraph_block(text: str) -> dict:
    return {"type": "paragraph", "id": "p1", "runs": [{"text": text}]}


def _collect_t_text(container: ET.Element) -> str:
    parts: list[str] = []
    for t in container.findall(".//w:t", NS):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def _collect_del_text(container: ET.Element) -> str:
    parts: list[str] = []
    for t in container.findall(".//w:delText", NS):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def test_build_paragraph_track_change_insert_has_ins_with_t() -> None:
    orig = _paragraph_block("Hello")
    rev = _paragraph_block("Hello world")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-28T00:00:00Z",
    )
    assert any(_local_name(e.tag) == "r" for e in els)
    ins = [e for e in els if _local_name(e.tag) == "ins"]
    assert len(ins) == 1
    assert ins[0].get(f"{{{WORD_NS}}}author") == "Test"
    assert _collect_t_text(ins[0]) == " world"


def test_build_paragraph_track_change_delete_has_del_with_del_text() -> None:
    orig = _paragraph_block("Hello world")
    rev = _paragraph_block("Hello")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-28T00:00:00Z",
    )
    dels = [e for e in els if _local_name(e.tag) == "del"]
    assert len(dels) == 1
    assert _collect_del_text(dels[0]) == " world"


def test_build_paragraph_track_change_replace_has_del_then_ins() -> None:
    # Avoid shared trailing characters so SequenceMatcher emits one clean replace.
    orig = _paragraph_block("aaa bbb")
    rev = _paragraph_block("aaa ccc")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-28T00:00:00Z",
    )
    kinds = [_local_name(e.tag) for e in els]
    assert "del" in kinds
    assert "ins" in kinds
    di, ii = kinds.index("del"), kinds.index("ins")
    assert di < ii
    del_el = els[di]
    ins_el = els[ii]
    assert _collect_del_text(del_el) == "bbb"
    assert _collect_t_text(ins_el) == "ccc"


def _minimal_docx(tmp_path: Path, body_inner: str, filename: str = "in.docx") -> Path:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    {body_inner}
  </w:body>
</w:document>
"""
    p = tmp_path / filename
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return p


def test_emit_docx_fixture_insert_xml_markers(tmp_path: Path) -> None:
    orig = _minimal_docx(tmp_path, "<w:p><w:r><w:t>Hi</w:t></w:r></w:p>", "orig.docx")
    rev = _minimal_docx(
        tmp_path, "<w:p><w:r><w:t>Hi there</w:t></w:r></w:p>", "rev.docx"
    )
    out = tmp_path / "out.docx"
    emit_docx_with_body_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author="Fixture",
        date_iso="2026-03-28T12:00:00Z",
    )
    root = load_word_document_xml_root(out)
    ins_list = root.findall(".//w:ins", NS)
    assert len(ins_list) == 1
    assert ins_list[0].get(f"{{{WORD_NS}}}author") == "Fixture"
    assert _collect_t_text(ins_list[0]) == " there"
    assert len(root.findall(".//w:del", NS)) == 0


def test_emit_docx_fixture_delete_xml_markers(tmp_path: Path) -> None:
    orig = _minimal_docx(
        tmp_path, "<w:p><w:r><w:t>Hi there</w:t></w:r></w:p>", "orig_del.docx"
    )
    rev = _minimal_docx(tmp_path, "<w:p><w:r><w:t>Hi</w:t></w:r></w:p>", "rev_del.docx")
    out = tmp_path / "out.docx"
    emit_docx_with_body_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        date_iso="2026-03-28T12:00:00Z",
    )
    root = load_word_document_xml_root(out)
    dels = root.findall(".//w:del", NS)
    assert len(dels) == 1
    assert _collect_del_text(dels[0]) == " there"


def test_write_docx_copy_with_part_replacements_overrides(tmp_path: Path) -> None:
    src = tmp_path / "src.docx"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("word/document.xml", b"<old/>")
        zf.writestr("word/styles.xml", b"<keep/>")
    dst = tmp_path / "dst.docx"
    write_docx_copy_with_part_replacements(
        src,
        dst,
        {"word/document.xml": b"<?xml version='1.0'?><new/>"},
    )
    with zipfile.ZipFile(dst, "r") as zf:
        assert b"<new/>" in zf.read("word/document.xml")
        assert zf.read("word/styles.xml") == b"<keep/>"


def test_emit_inserts_new_paragraph_only_in_revised(tmp_path: Path) -> None:
    """Revised-only lines become new ``w:p`` with the full line inside ``w:ins``."""
    orig = _minimal_docx(
        tmp_path,
        "<w:p><w:r><w:t>First</w:t></w:r></w:p>",
        "ins_para_orig.docx",
    )
    rev = _minimal_docx(
        tmp_path,
        "<w:p><w:r><w:t>First</w:t></w:r></w:p>"
        '<w:p><w:r><w:t>Second line only in B</w:t></w:r></w:p>',
        "ins_para_rev.docx",
    )
    out = tmp_path / "ins_para_out.docx"
    emit_docx_with_body_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author="Fixture",
        date_iso="2026-03-28T12:00:00Z",
    )
    root = load_word_document_xml_root(out)
    ps = root.findall(".//w:body/w:p", NS)
    assert len(ps) == 2
    second = ps[1]
    ins = second.findall("w:ins", NS)
    assert len(ins) == 1
    assert _collect_t_text(ins[0]) == "Second line only in B"


def test_emit_inserts_paragraph_between_matching_blocks(tmp_path: Path) -> None:
    orig = _minimal_docx(
        tmp_path,
        "<w:p><w:r><w:t>A</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>C</w:t></w:r></w:p>",
        "mid_ins_orig.docx",
    )
    rev = _minimal_docx(
        tmp_path,
        "<w:p><w:r><w:t>A</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>B new</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>C</w:t></w:r></w:p>",
        "mid_ins_rev.docx",
    )
    out = tmp_path / "mid_ins_out.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    ps = root.findall(".//w:body/w:p", NS)
    assert len(ps) == 3
    assert _collect_t_text(ps[0]) == "A"
    mid_ins = ps[1].find("w:ins", NS)
    assert mid_ins is not None
    assert _collect_t_text(mid_ins) == "B new"
    assert _collect_t_text(ps[2]) == "C"


def test_emit_marks_deleted_paragraph_only_in_original(tmp_path: Path) -> None:
    orig = _minimal_docx(
        tmp_path,
        "<w:p><w:r><w:t>Keep</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Remove me</w:t></w:r></w:p>",
        "del_para_orig.docx",
    )
    rev = _minimal_docx(
        tmp_path, "<w:p><w:r><w:t>Keep</w:t></w:r></w:p>", "del_para_rev.docx"
    )
    out = tmp_path / "del_para_out.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    ps = root.findall(".//w:body/w:p", NS)
    assert len(ps) == 2
    dels = ps[1].findall(".//w:del", NS)
    assert len(dels) >= 1
    assert _collect_del_text(ps[1]) == "Remove me"


def test_emit_preserves_w_p_pr(tmp_path: Path) -> None:
    body = """<w:p>
      <w:pPr><w:pStyle w:val="Title"/></w:pPr>
      <w:r><w:t>Old</w:t></w:r>
    </w:p>"""
    orig = _minimal_docx(tmp_path, body, "pr_orig.docx")
    rev = _minimal_docx(
        tmp_path, "<w:p><w:r><w:t>New</w:t></w:r></w:p>", "pr_rev.docx"
    )
    out = tmp_path / "out.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    p = root.find(".//w:p", NS)
    assert p is not None
    assert p.find("w:pPr", NS) is not None
