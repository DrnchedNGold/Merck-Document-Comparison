"""SCRUM-61: assert w:ins / w:del shape in generated document XML (SCRUM-58)."""

from __future__ import annotations

import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_revision_emit import (
    _build_toc_matched_line_track_change_elements,
    build_paragraph_track_change_elements,
    emit_docx_with_body_track_changes,
    emit_docx_with_package_track_changes,
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


def test_build_paragraph_track_change_preserves_tab_between_label_and_value() -> None:
    """SCRUM-105: metadata lines use tabs; only changing the value must keep the gap."""
    orig = _paragraph_block("Version Number:\t1.0")
    rev = _paragraph_block("Version Number:\t2.0")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-29T00:00:00Z",
    )
    plain_r_text = "".join(
        _collect_t_text(e) for e in els if _local_name(e.tag) == "r"
    )
    p_xml = ET.Element(f"{{{WORD_NS}}}p")
    for el in els:
        p_xml.append(el)
    assert len(p_xml.findall(".//w:tab", NS)) >= 1
    assert "Version Number:" in plain_r_text
    assert "Version Number:2" not in plain_r_text


def test_build_paragraph_track_change_split_tab_run_with_ignore_whitespace() -> None:
    """SCRUM-105: tab-only runs must not disappear when ignore_whitespace=True."""
    cfg = dict(DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    cfg["ignore_whitespace"] = True

    orig = {
        "type": "paragraph",
        "id": "p1",
        "runs": [
            {"text": "Version Number:"},
            {"text": "\t"},
            {"text": "1.0"},
        ],
    }
    rev = {
        "type": "paragraph",
        "id": "p1",
        "runs": [
            {"text": "Version Number:"},
            {"text": "\t"},
            {"text": "2.0"},
        ],
    }

    els = build_paragraph_track_change_elements(
        orig,
        rev,
        cfg,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-30T00:00:00Z",
    )

    plain_r_text = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    del_text = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    ins_text = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "ins")

    assert "Version Number: " in plain_r_text
    assert "Version Number:2" not in plain_r_text
    assert ".0" in plain_r_text
    assert del_text == "1"
    assert ins_text == "2"


def test_toc_matched_line_track_change_preserves_w_tab_with_ignore_whitespace() -> None:
    """SCRUM-112: TOC-only builder keeps ``\\t`` in emit when ignore_whitespace=True."""
    cfg = dict(DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    cfg["ignore_whitespace"] = True

    orig = {
        "type": "paragraph",
        "id": "p1",
        "runs": [
            {"text": "1"},
            {"text": "\t"},
            {"text": "OVERVIEW"},
        ],
    }
    rev = {
        "type": "paragraph",
        "id": "p1",
        "runs": [
            {"text": "1"},
            {"text": "\t"},
            {"text": "SCOPE"},
        ],
    }

    els = _build_toc_matched_line_track_change_elements(
        orig,
        rev,
        cfg,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-30T00:00:00Z",
    )

    p_xml = ET.Element(f"{{{WORD_NS}}}p")
    for el in els:
        p_xml.append(el)
    assert len(p_xml.findall(".//w:tab", NS)) >= 1
    dels = [e for e in els if _local_name(e.tag) == "del"]
    inses = [e for e in els if _local_name(e.tag) == "ins"]
    assert any("OVERVIEW" in _collect_del_text(d) for d in dels)
    assert any("SCOPE" in _collect_t_text(i) for i in inses)


def test_build_paragraph_track_change_preserves_unchanged_date_year_suffix() -> None:
    """SCRUM-105: only changed date core should be revised; -2025 remains unchanged."""
    orig = _paragraph_block("Release Date:\t09-APR-2025")
    rev = _paragraph_block("Release Date:\t30-MAY-2025")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-30T00:00:00Z",
    )

    plain_r_text = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    del_text = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    ins_text = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "ins")

    p_xml = ET.Element(f"{{{WORD_NS}}}p")
    for el in els:
        p_xml.append(el)
    assert len(p_xml.findall(".//w:tab", NS)) >= 1
    assert "Release Date:" in plain_r_text
    assert "-2025" in plain_r_text
    assert del_text == "09-APR"
    assert ins_text == "30-MAY"


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


def test_build_paragraph_track_change_unrelated_phrase_not_single_del() -> None:
    """Long unrelated edits must not collapse to one ``w:del`` for the whole tail."""
    orig = _paragraph_block(
        "The primary endpoint is overall response rate at week 12."
    )
    rev = _paragraph_block(
        "The primary endpoint is progression-free survival at week 24."
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-28T00:00:00Z",
    )
    dels = [e for e in els if _local_name(e.tag) == "del"]
    del_chunks = [_collect_del_text(d) for d in dels]
    assert len(dels) >= 4
    assert "overall" in del_chunks
    assert "response" in del_chunks
    assert "rate" in del_chunks
    assert not any(
        "overall response rate" in chunk and len(chunk) > 20 for chunk in del_chunks
    )


def test_build_paragraph_track_change_toc_line_preserves_w_tab_around_page_change() -> None:
    """SCRUM-111: TOC-style ``heading`` + tab + page number keeps ``w:tab`` when only the number changes."""
    orig = _paragraph_block("Topic\t6")
    rev = _paragraph_block("Topic\t7")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-03-28T00:00:00Z",
    )
    p_xml = ET.Element(f"{{{WORD_NS}}}p")
    for el in els:
        p_xml.append(el)
    tabs = p_xml.findall(".//w:tab", NS)
    assert len(tabs) >= 1
    dels = [e for e in els if _local_name(e.tag) == "del"]
    inses = [e for e in els if _local_name(e.tag) == "ins"]
    assert len(dels) == 1 and len(inses) == 1
    assert _collect_del_text(dels[0]) == "6"
    assert _collect_t_text(inses[0]) == "7"


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


def test_emit_preserves_table_equal_block_count_paragraph_vs_table_slot(
    tmp_path: Path,
) -> None:
    """SCRUM-115: same-length bodies must not drop a revised table at a filler paragraph index."""
    orig_inner = """
<w:p><w:r><w:t>HeaderA</w:t></w:r></w:p>
<w:p><w:r><w:t>FillerPara</w:t></w:r></w:p>
<w:p><w:r><w:t>FooterB</w:t></w:r></w:p>
"""
    rev_inner = """
<w:p><w:r><w:t>HeaderA</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>CellOne</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p><w:r><w:t>FooterB</w:t></w:r></w:p>
"""
    orig = _minimal_docx(tmp_path, orig_inner, "orig_scrum115.docx")
    rev = _minimal_docx(tmp_path, rev_inner, "rev_scrum115.docx")
    out = tmp_path / "out_scrum115.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    assert len(root.findall(".//w:tbl", NS)) >= 1
    assert "CellOne" in _collect_t_text(root)


def test_scrum120_cervical_abbreviations_paragraph_before_inserted_table(
    tmp_path: Path,
) -> None:
    """SCRUM-120: revised-only paragraph then table must not reverse (tbl before p)."""
    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")
    out = tmp_path / "scrum120_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    needle = "Terms describing racial"
    children = list(body)
    terms_i: int | None = None
    for i, ch in enumerate(children):
        if _local_name(ch.tag) == "p" and needle in _collect_t_text(ch):
            terms_i = i
            break
    assert terms_i is not None
    first_tbl_i: int | None = None
    for j in range(terms_i + 1, len(children)):
        ch = children[j]
        ln = _local_name(ch.tag)
        if ln == "tbl":
            first_tbl_i = j
            break
        if ln == "ins" and ch.find(f"{{{WORD_NS}}}tbl") is not None:
            first_tbl_i = j
            break
    assert first_tbl_i is not None
    rev_heading_i = next(
        (
            i
            for i, ch in enumerate(children)
            if i > terms_i
            and _local_name(ch.tag) == "p"
            and "TABLE OF REVISIONS" in _collect_t_text(ch)
        ),
        None,
    )
    assert rev_heading_i is not None
    assert terms_i < first_tbl_i < rev_heading_i


def test_emit_full_paragraph_delete_strips_numpr_no_empty_bullets(tmp_path: Path) -> None:
    """Deleted list lines must not keep w:numPr (avoids empty bullet glyphs vs Word)."""
    list_p = """
<w:p>
  <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
  <w:r><w:t>Removed line</w:t></w:r>
</w:p>"""
    orig_inner = "<w:p><w:r><w:t>Intro</w:t></w:r></w:p>" + list_p
    rev_inner = "<w:p><w:r><w:t>Intro</w:t></w:r></w:p>"
    orig = _minimal_docx(tmp_path, orig_inner, "orig_bullet.docx")
    rev = _minimal_docx(tmp_path, rev_inner, "rev_bullet.docx")
    out = tmp_path / "out_bullet.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    ps = [c for c in body if _local_name(c.tag) == "p"]
    assert len(ps) >= 2
    deleted_p = ps[1]
    assert deleted_p.find("w:pPr/w:numPr", NS) is None
    assert "Removed line" in _collect_del_text(deleted_p)


def test_emit_full_paragraph_delete_strips_listbullet_pstyle(tmp_path: Path) -> None:
    """Cervical-style list rows use ``ListBullet`` without ``w:numPr``."""
    list_p = """
<w:p>
  <w:pPr><w:pStyle w:val="ListBullet"/></w:pPr>
  <w:r><w:t>Study and trial</w:t></w:r>
</w:p>"""
    orig_inner = "<w:p><w:r><w:t>Intro</w:t></w:r></w:p>" + list_p
    rev_inner = "<w:p><w:r><w:t>Intro</w:t></w:r></w:p>"
    orig = _minimal_docx(tmp_path, orig_inner, "orig_listbullet.docx")
    rev = _minimal_docx(tmp_path, rev_inner, "rev_listbullet.docx")
    out = tmp_path / "out_listbullet.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    ps = [c for c in body if _local_name(c.tag) == "p"]
    deleted_p = ps[1]
    ppr = deleted_p.find("w:pPr", NS)
    if ppr is not None:
        ps_el = ppr.find("w:pStyle", NS)
        assert ps_el is None or ps_el.get(f"{{{WORD_NS}}}val") != "ListBullet"
    assert "Study and trial" in _collect_del_text(deleted_p)


def test_emit_table_cell_text_change_has_revision_markers(tmp_path: Path) -> None:
    """Matched tables get per-cell w:ins / w:del like paragraph inline diff."""
    tbl = (
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    orig = _minimal_docx(tmp_path, tbl.format(text="oldcell"), "orig_cell.docx")
    rev = _minimal_docx(tmp_path, tbl.format(text="newcell"), "rev_cell.docx")
    out = tmp_path / "out_cell.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    assert len(root.findall(".//w:tbl", NS)) == 1
    assert root.findall(".//w:ins", NS)
    assert root.findall(".//w:del", NS)


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


def test_emit_zip_output_primary_endpoint_not_one_whole_paragraph_del(tmp_path: Path) -> None:
    """Regression: extra paragraph in B must still align endpoint line for word-level XML."""
    old_ep = "The primary endpoint is overall response rate at week 12."
    new_ep = "The primary endpoint is progression-free survival at week 24."
    paras_o = [
        "The study will enroll 100 participants at three sites.",
        "Inclusion criteria: adults aged 65 to 75 with confirmed diagnosis.",
        old_ep,
        "Contact: Dr. Smith (lead investigator).",
    ]
    paras_r = [
        "The study will enroll 120 participants at four sites.",
        "Inclusion criteria: adults aged 65 to 75 with confirmed diagnosis.",
        new_ep,
        "Contact: Dr. Jones (lead investigator).",
        "Data monitoring will occur monthly.",
    ]
    body_o = "".join(
        f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paras_o
    )
    body_r = "".join(
        f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paras_r
    )
    orig = _minimal_docx(tmp_path, body_o, "demo_orig.docx")
    rev = _minimal_docx(tmp_path, body_r, "demo_rev.docx")
    out = tmp_path / "demo_out.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    ps = root.findall(".//w:body/w:p", NS)
    assert len(ps) >= 3
    p3 = ps[2]
    dels = p3.findall(".//w:del", NS)
    del_chunks = [_collect_del_text(d) for d in dels]
    assert old_ep not in del_chunks
    assert "overall" in del_chunks


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


def test_emit_reordered_paragraph_uses_delete_insert_fallback_not_move_markup(
    tmp_path: Path,
) -> None:
    """v1 fallback: reorders are emitted as del+ins, never w:moveFrom/w:moveTo."""
    orig = _minimal_docx(
        tmp_path,
        "<w:p><w:r><w:t>A</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>B moved paragraph</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>C</w:t></w:r></w:p>",
        "move_orig.docx",
    )
    rev = _minimal_docx(
        tmp_path,
        "<w:p><w:r><w:t>A</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>C</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>B moved paragraph</w:t></w:r></w:p>",
        "move_rev.docx",
    )
    out = tmp_path / "move_out.docx"
    emit_docx_with_body_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author="Fixture",
        date_iso="2026-03-29T12:00:00Z",
    )
    root = load_word_document_xml_root(out)

    # Explicit guard: current v1 does not emit move markup.
    assert len(root.findall(".//w:moveFrom", NS)) == 0
    assert len(root.findall(".//w:moveTo", NS)) == 0

    # Reorder is represented as deletion at old position + insertion at new position.
    del_chunks = [_collect_del_text(d) for d in root.findall(".//w:del", NS)]
    ins_chunks = [_collect_t_text(i) for i in root.findall(".//w:ins", NS)]
    del_flat = " ".join(del_chunks)
    ins_flat = " ".join(ins_chunks)
    assert "B" in del_flat and "moved" in del_flat and "paragraph" in del_flat
    assert "B" in ins_flat and "moved" in ins_flat and "paragraph" in ins_flat
