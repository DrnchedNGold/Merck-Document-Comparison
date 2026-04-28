"""SCRUM-61: assert w:ins / w:del shape in generated document XML (SCRUM-58)."""

from __future__ import annotations

import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

import engine.body_revision_emit as body_revision_emit
from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_revision_emit import (
    _build_toc_matched_line_track_change_elements,
    _track_change_elements_for_concat_texts,
    _word_token_similarity_ratio,
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


def _table_cell(text: str) -> dict:
    return {
        "paragraphs": [
            {"type": "paragraph", "id": "cell-p", "runs": [{"text": text}]},
        ]
    }


def _w_tbl_with_row(cell_texts: list[str]) -> ET.Element:
    tbl = ET.Element(f"{{{WORD_NS}}}tbl")
    tr = ET.SubElement(tbl, f"{{{WORD_NS}}}tr")
    for text in cell_texts:
        tc = ET.SubElement(tr, f"{{{WORD_NS}}}tc")
        p = ET.SubElement(tc, f"{{{WORD_NS}}}p")
        r = ET.SubElement(p, f"{{{WORD_NS}}}r")
        t = ET.SubElement(r, f"{{{WORD_NS}}}t")
        t.text = text
    return tbl


def _w_p_with_numpr(text: str, *, num_id: str, ilvl: str = "0") -> ET.Element:
    p = ET.Element(f"{{{WORD_NS}}}p")
    ppr = ET.SubElement(p, f"{{{WORD_NS}}}pPr")
    numpr = ET.SubElement(ppr, f"{{{WORD_NS}}}numPr")
    ilvl_el = ET.SubElement(numpr, f"{{{WORD_NS}}}ilvl")
    ilvl_el.set(f"{{{WORD_NS}}}val", ilvl)
    numid_el = ET.SubElement(numpr, f"{{{WORD_NS}}}numId")
    numid_el.set(f"{{{WORD_NS}}}val", num_id)
    r = ET.SubElement(p, f"{{{WORD_NS}}}r")
    t = ET.SubElement(r, f"{{{WORD_NS}}}t")
    t.text = text
    return p


def _w_r_with_vert_align(text: str, *, val: str) -> ET.Element:
    r = ET.Element(f"{{{WORD_NS}}}r")
    rpr = ET.SubElement(r, f"{{{WORD_NS}}}rPr")
    va = ET.SubElement(rpr, f"{{{WORD_NS}}}vertAlign")
    va.set(f"{{{WORD_NS}}}val", val)
    t = ET.SubElement(r, f"{{{WORD_NS}}}t")
    t.text = text
    return r


def _body_block_sequence(body: ET.Element) -> list[tuple[str, str]]:
    seq: list[tuple[str, str]] = []
    for ch in list(body):
        ln = _local_name(ch.tag)
        if ln == "p":
            seq.append(("p", (_collect_t_text(ch) + _collect_del_text(ch)).strip()))
        elif ln == "tbl":
            seq.append(("tbl", ""))
        elif ln == "ins" and ch.find("w:tbl", NS) is not None:
            seq.append(("tbl", ""))
    return seq


def test_table_cell_insert_with_sparse_revised_index_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SCRUM-143: a cloned revised cell may be the direct target when original cells are sparse."""

    monkeypatch.setattr(body_revision_emit, "_align_table_rows", lambda *_: [(0, 0)])
    monkeypatch.setattr(body_revision_emit, "_align_row_cells", lambda *_: [(None, 2)])

    body = ET.Element(f"{{{WORD_NS}}}body")
    orig_tbl_el = _w_tbl_with_row([])
    revised_tbl_el = _w_tbl_with_row(["A", "B", "C"])

    body_revision_emit._apply_matched_table_track_changes(
        body,
        orig_tbl_el,
        {"type": "table", "id": "orig", "rows": [[]]},
        {
            "type": "table",
            "id": "rev",
            "rows": [[_table_cell("A"), _table_cell("B"), _table_cell("C")]],
        },
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        [0],
        "Test",
        "2026-03-28T00:00:00Z",
        revised_tbl_el=revised_tbl_el,
    )

    assert len(orig_tbl_el.findall(".//w:tc", NS)) == 1
    assert _collect_t_text(orig_tbl_el.findall(".//w:ins", NS)[0]) == "C"


def test_table_cell_bullet_paragraphs_preserve_numpr_and_do_not_collapse_to_single_para() -> None:
    """Bullet list rows inside one table cell keep paragraph-level numbering metadata."""

    tc = ET.Element(f"{{{WORD_NS}}}tc")
    tc.append(_w_p_with_numpr("Updated total number of participants.", num_id="9"))
    tc.append(_w_p_with_numpr("Updated list of participating countries.", num_id="9"))

    revised_tc = ET.Element(f"{{{WORD_NS}}}tc")
    revised_tc.append(_w_p_with_numpr("Updated total number of participants.", num_id="9"))
    revised_tc.append(_w_p_with_numpr("Updated list of participating trial countries.", num_id="9"))

    orig_cell = {
        "paragraphs": [
            {"type": "paragraph", "id": "c0p0", "runs": [{"text": "Updated total number of participants."}]},
            {"type": "paragraph", "id": "c0p1", "runs": [{"text": "Updated list of participating countries."}]},
        ]
    }
    rev_cell = {
        "paragraphs": [
            {"type": "paragraph", "id": "c0p0", "runs": [{"text": "Updated total number of participants."}]},
            {"type": "paragraph", "id": "c0p1", "runs": [{"text": "Updated list of participating trial countries."}]},
        ]
    }

    body_revision_emit._apply_table_cell_track_changes(
        tc,
        orig_cell,
        rev_cell,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        [0],
        "Test",
        "2026-04-23T00:00:00Z",
        revised_tc_el=revised_tc,
    )

    paras = [c for c in tc if _local_name(c.tag) == "p"]
    assert len(paras) == 2
    for p in paras:
        num_id = p.find("w:pPr/w:numPr/w:numId", NS)
        assert num_id is not None
        assert num_id.get(f"{{{WORD_NS}}}val") == "9"


def test_table_cell_numbered_paragraphs_keep_numbered_numpr() -> None:
    """Control: true numbered list metadata should remain unchanged in table cells."""

    tc = ET.Element(f"{{{WORD_NS}}}tc")
    tc.append(_w_p_with_numpr("1) Numbered item one", num_id="42"))
    tc.append(_w_p_with_numpr("2) Numbered item two", num_id="42"))

    revised_tc = ET.Element(f"{{{WORD_NS}}}tc")
    revised_tc.append(_w_p_with_numpr("1) Numbered item one", num_id="42"))
    revised_tc.append(_w_p_with_numpr("2) Numbered list item two", num_id="42"))

    orig_cell = {
        "paragraphs": [
            {"type": "paragraph", "id": "n0", "runs": [{"text": "1) Numbered item one"}]},
            {"type": "paragraph", "id": "n1", "runs": [{"text": "2) Numbered item two"}]},
        ]
    }
    rev_cell = {
        "paragraphs": [
            {"type": "paragraph", "id": "n0", "runs": [{"text": "1) Numbered item one"}]},
            {"type": "paragraph", "id": "n1", "runs": [{"text": "2) Numbered list item two"}]},
        ]
    }

    body_revision_emit._apply_table_cell_track_changes(
        tc,
        orig_cell,
        rev_cell,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        [0],
        "Test",
        "2026-04-23T00:00:00Z",
        revised_tc_el=revised_tc,
    )

    paras = [c for c in tc if _local_name(c.tag) == "p"]
    assert len(paras) == 2
    for p in paras:
        num_id = p.find("w:pPr/w:numPr/w:numId", NS)
        assert num_id is not None
        assert num_id.get(f"{{{WORD_NS}}}val") == "42"


def test_table_cell_non_list_multi_para_keeps_legacy_merged_emit() -> None:
    """Non-list table cells should keep merged paragraph emit behavior."""

    tc = ET.Element(f"{{{WORD_NS}}}tc")
    for txt in ("Alpha line", "Bravo line"):
        p = ET.SubElement(tc, f"{{{WORD_NS}}}p")
        r = ET.SubElement(p, f"{{{WORD_NS}}}r")
        t = ET.SubElement(r, f"{{{WORD_NS}}}t")
        t.text = txt

    revised_tc = ET.Element(f"{{{WORD_NS}}}tc")
    for txt in ("Alpha line", "Bravo changed line"):
        p = ET.SubElement(revised_tc, f"{{{WORD_NS}}}p")
        r = ET.SubElement(p, f"{{{WORD_NS}}}r")
        t = ET.SubElement(r, f"{{{WORD_NS}}}t")
        t.text = txt

    orig_cell = {
        "paragraphs": [
            {"type": "paragraph", "id": "m0", "runs": [{"text": "Alpha line"}]},
            {"type": "paragraph", "id": "m1", "runs": [{"text": "Bravo line"}]},
        ]
    }
    rev_cell = {
        "paragraphs": [
            {"type": "paragraph", "id": "m0", "runs": [{"text": "Alpha line"}]},
            {"type": "paragraph", "id": "m1", "runs": [{"text": "Bravo changed line"}]},
        ]
    }

    body_revision_emit._apply_table_cell_track_changes(
        tc,
        orig_cell,
        rev_cell,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        [0],
        "Test",
        "2026-04-23T00:00:00Z",
        revised_tc_el=revised_tc,
    )

    paras = [c for c in tc if _local_name(c.tag) == "p"]
    assert len(paras) == 1


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


def test_concat_track_change_does_not_move_header_tab_into_inserted_drug_name() -> None:
    """SCRUM-152: keep the single header tab stop outside inserted drug-name text."""
    orig = "MK-2870\tPAGE 10"
    rev = "MK-2870 (SACITUZUMAB TIRUMOTECAN)\tPAGE 10"
    els = _track_change_elements_for_concat_texts(
        orig,
        rev,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-28T00:00:00Z",
    )
    p_xml = ET.Element(f"{{{WORD_NS}}}p")
    for el in els:
        p_xml.append(el)
    assert len(p_xml.findall(".//w:tab", NS)) == 1
    ins = [e for e in els if _local_name(e.tag) == "ins"]
    assert len(ins) == 1
    assert len(ins[0].findall(".//w:tab", NS)) == 0
    assert "SACITUZUMAB TIRUMOTECAN" in _collect_t_text(ins[0])


def test_preserving_path_does_not_move_header_tab_into_inserted_drug_name() -> None:
    """SCRUM-152: preserving emit must not duplicate/shift header tab stops."""
    orig_para = {
        "type": "paragraph",
        "id": "p1",
        "runs": [{"text": "MK-2870"}, {"text": "\t"}, {"text": "PAGE 10"}],
    }
    rev_para = {
        "type": "paragraph",
        "id": "p1",
        "runs": [
            {"text": "MK-2870 "},
            {"text": "(SACITUZUMAB TIRUMOTECAN)"},
            {"text": "\t"},
            {"text": "PAGE 10"},
        ],
    }
    src_p = ET.Element(f"{{{WORD_NS}}}p")
    src_r1 = ET.SubElement(src_p, f"{{{WORD_NS}}}r")
    src_t1 = ET.SubElement(src_r1, f"{{{WORD_NS}}}t")
    src_t1.text = "MK-2870"
    src_r2 = ET.SubElement(src_p, f"{{{WORD_NS}}}r")
    ET.SubElement(src_r2, f"{{{WORD_NS}}}tab")
    src_r3 = ET.SubElement(src_p, f"{{{WORD_NS}}}r")
    src_t3 = ET.SubElement(src_r3, f"{{{WORD_NS}}}t")
    src_t3.text = "PAGE 10"

    rev_p = ET.Element(f"{{{WORD_NS}}}p")
    rev_r1 = ET.SubElement(rev_p, f"{{{WORD_NS}}}r")
    rev_t1 = ET.SubElement(rev_r1, f"{{{WORD_NS}}}t")
    rev_t1.text = "MK-2870 "
    rev_r2 = ET.SubElement(rev_p, f"{{{WORD_NS}}}r")
    rev_t2 = ET.SubElement(rev_r2, f"{{{WORD_NS}}}t")
    rev_t2.text = "(SACITUZUMAB TIRUMOTECAN)"
    rev_r3 = ET.SubElement(rev_p, f"{{{WORD_NS}}}r")
    ET.SubElement(rev_r3, f"{{{WORD_NS}}}tab")
    rev_r4 = ET.SubElement(rev_p, f"{{{WORD_NS}}}r")
    rev_t4 = ET.SubElement(rev_r4, f"{{{WORD_NS}}}t")
    rev_t4.text = "PAGE 10"

    els = build_paragraph_track_change_elements(
        orig_para,
        rev_para,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-28T00:00:00Z",
        source_p_el=src_p,
        revised_p_el=rev_p,
    )
    p_xml = ET.Element(f"{{{WORD_NS}}}p")
    for el in els:
        p_xml.append(el)
    assert len(p_xml.findall(".//w:tab", NS)) == 1
    ins = [e for e in els if _local_name(e.tag) == "ins"]
    assert len(ins) == 1
    assert len(ins[0].findall(".//w:tab", NS)) == 0
    assert "SACITUZUMAB TIRUMOTECAN" in _collect_t_text(ins[0])


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


def test_toc_matched_line_track_change_keeps_shared_title_prefix_before_product_and_page() -> None:
    """TOC line with same section/title prefix should not degrade to whole-line del/ins."""
    orig = {
        "type": "paragraph",
        "id": "p1",
        "runs": [{"text": "2\tSCOPE OF MEDICAL PRODUCT DEVELOPMENT PROGRAM: MK-2870\t11"}],
    }
    rev = {
        "type": "paragraph",
        "id": "p1",
        "runs": [{"text": "2\tSCOPE OF MEDICAL PRODUCT DEVELOPMENT PROGRAM: sacituzumab tirumotecan\t18"}],
    }

    els = _build_toc_matched_line_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-17T00:00:00Z",
    )

    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    dels = [e for e in els if _local_name(e.tag) == "del"]
    inses = [e for e in els if _local_name(e.tag) == "ins"]

    p_xml = ET.Element(f"{{{WORD_NS}}}p")
    for el in els:
        p_xml.append(el)
    assert len(p_xml.findall(".//w:tab", NS)) >= 2
    assert plain.startswith("2SCOPE OF MEDICAL PRODUCT DEVELOPMENT PROGRAM: ")
    assert len(dels) == 1 and len(inses) == 1
    assert "MK-2870" in _collect_del_text(dels[0])
    assert "sacituzumab tirumotecan" in _collect_t_text(inses[0])


def test_heading2_title_diff_coalesce_preserves_long_shared_tail() -> None:
    """Body ``Heading2`` lines (no ``1.1`` prefix in runs): suffix coalesce must not swallow a long shared clause."""

    orig = _paragraph_block(
        "Incidence, Mortality, and Prevalence in the Overall Population and "
        "Underrepresented Racial and Ethnic Populations"
    )
    rev = _paragraph_block(
        "Disease Epidemiology in the Overall Population and Underrepresented Racial and Ethnic Populations"
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
    )
    del_all = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    ins_all = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "ins")
    shared = "in the Overall Population and Underrepresented Racial and"
    assert shared not in del_all and shared not in ins_all
    assert "Incidence" in del_all
    assert "Disease Epidemiology" in ins_all


def test_concat_tc_emitted_text_counts_w_tab_to_avoid_false_numeric_corruption() -> None:
    """
    Tab leaders between a product token and a page number must not flatten into one
    digit run (e.g. 2870 + tab + 11 misread as 287011), which previously triggered
    NUMERIC_CORRUPTION_FALLBACK and replaced a fine-grained diff with full-line del/ins.
    """

    mid_o = "SCOPE OF MEDICAL PRODUCT DEVELOPMENT PROGRAM: MK-2870\t11"
    mid_r = "SCOPE OF MEDICAL PRODUCT DEVELOPMENT PROGRAM: sacituzumab tirumotecan\t18"
    els = _track_change_elements_for_concat_texts(
        mid_o,
        mid_r,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
    )
    kinds = [_local_name(e.tag) for e in els]
    assert "r" in kinds, "expected preserved plain runs before del/ins, not full-paragraph rewrite"
    dels = [e for e in els if _local_name(e.tag) == "del"]
    assert dels and all("SCOPE" not in _collect_del_text(d) for d in dels)


def _paragraph_track_visible_text(p: ET.Element) -> str:
    """Plain ``w:t``, ``w:delText``, and ``w:t`` inside ``w:ins`` (reading order is approximate)."""

    parts: list[str] = []
    parts.append(_collect_t_text(p))
    parts.append(_collect_del_text(p))
    for ins in p.findall(".//w:ins", NS):
        for t in ins.findall(".//w:t", NS):
            if t.text:
                parts.append(t.text)
    return "".join(parts)


def test_toc_line_cervical_section_11_inline_title_diff_single_paragraph(tmp_path: Path) -> None:
    """TOC-style section 1.1 line: title + page change stay in one w:p with inline del/ins."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "toc_11_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    title_tail = "in the Overall Population and Underrepresented Racial and Ethnic Populations"
    target_p = next(
        (
            p
            for p in body.findall("w:p", NS)
            if "1.1" in _paragraph_track_visible_text(p)
            and title_tail in _paragraph_track_visible_text(p)
            and ("Incidence" in _collect_del_text(p) or "Disease" in _paragraph_track_visible_text(p))
        ),
        None,
    )
    assert target_p is not None
    vis = _paragraph_track_visible_text(target_p)
    assert "Incidence" in _collect_del_text(target_p)
    assert "Disease Epidemiology" in vis
    assert title_tail in vis
    shared_mid = "in the Overall Population and Underrepresented Racial and"
    ins_text = "".join(t.text or "" for t in target_p.findall(".//w:ins//w:t", NS))
    assert shared_mid not in _collect_del_text(target_p), (
        "shared title tail must stay plain text, not inside w:del (over-wide replace)"
    )
    assert shared_mid not in ins_text, (
        "shared title tail must stay plain text, not inside w:ins (over-wide replace)"
    )
    n_del = len(target_p.findall(".//w:del", NS))
    n_ins = len(target_p.findall(".//w:ins", NS))
    assert n_del >= 1 and n_ins >= 1 and n_del <= 6 and n_ins <= 6, (
        f"expected inline TOC revisions, not a single full-line pair; del={n_del} ins={n_ins}"
    )


def test_scrum156_cervical_heading3_rewrite_keeps_numbered_paragraph_inline(
    tmp_path: Path,
) -> None:
    """SCRUM-156: Heading3 rewrite should stay in one numbered paragraph with inline text revisions."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum156_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None

    matches = []
    for p in body.findall("w:p", NS):
        pstyle = p.find("w:pPr/w:pStyle", NS)
        if pstyle is None or pstyle.get(f"{{{WORD_NS}}}val") != "Heading3":
            continue
        combined = _collect_t_text(p) + _collect_del_text(p)
        if "Pathophysiology" in combined:
            matches.append(p)

    assert len(matches) == 1
    target = matches[0]
    num_id = target.find("w:pPr/w:numPr/w:numId", NS)
    assert num_id is not None
    assert num_id.get(f"{{{WORD_NS}}}val") == "4"
    assert _collect_t_text(target) == "Differences in Pathophysiology"
    assert len(target.findall(".//w:ins", NS)) == 1
    assert "".join(t.text or "" for t in target.findall(".//w:ins//w:t", NS)) == "Differences in "


def test_scrum157_cervical_prevalence_age_cells_do_not_emit_leading_space_inserts(
    tmp_path: Path,
) -> None:
    """SCRUM-157: avoid underscore-like leading-space inserts in prevalence age cells."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum157_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None

    age_labels = {"<50y", "50-64y", "≥65y"}
    seen = 0
    for tc in body.findall(".//w:tbl//w:tr//w:tc[1]", NS):
        plain = _collect_t_text(tc)
        label = plain.strip()
        if label not in age_labels:
            continue
        seen += 1
        # No leading inserted spaces before the age label.
        assert plain == label
        ins_chunks = [
            (t.text or "")
            for t in tc.findall(".//w:ins//w:t", NS)
            if (t.text or "").strip() == ""
        ]
        assert not ins_chunks
    assert seen >= 3


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
    # Hyphens are separate punctuation tokens; date month/day appear in del/ins.
    assert "09" in del_text and "APR" in del_text
    assert "30" in ins_text and "MAY" in ins_text


def test_build_paragraph_track_change_alphabetic_word_replace_no_character_peel() -> None:
    """Alphabetic single-token replace must not split inside the word (avoids garbled order)."""
    orig = _paragraph_block("Say the cat")
    rev = _paragraph_block("Say hte cat")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-10T00:00:00Z",
    )
    kinds = [_local_name(e.tag) for e in els]
    assert kinds == ["r", "del", "ins", "r"]
    assert _collect_t_text(els[0]).endswith("Say ")
    assert _collect_del_text(els[1]) == "the "
    assert _collect_t_text(els[2]) == "hte "
    assert _collect_t_text(els[3]) == "cat"
    flat = "".join(
        _collect_t_text(e) if _local_name(e.tag) != "del" else _collect_del_text(e)
        for e in els
    )
    assert flat == "Say the hte cat"


def test_build_paragraph_track_change_suffix_coalesce_stable_tail_after_phrase_edit() -> None:
    """SCRUM-121: shared token before a stable tail stays in one replace; tail stays plain ``w:r``."""
    orig = _paragraph_block("A recently published study")
    rev = _paragraph_block("The 10 most recently published study")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-11T00:00:00Z",
    )
    assert [_local_name(e.tag) for e in els] == ["del", "ins", "r"]
    assert _collect_del_text(els[0]) == "A recently "
    assert _collect_t_text(els[1]) == "The 10 most recently "
    assert _collect_t_text(els[2]) == "published study"


def test_build_paragraph_track_change_merges_fragmented_rewrite_between_plain_anchors() -> None:
    """Expanded rewrite between strong equal anchors should not fragment into many tiny del/ins pairs."""
    orig = _paragraph_block(
        "A recently published study women in the US had the highest incidence rates of "
        "cervical SCC [Ref. 5.4: OLD]. "
    )
    rev = _paragraph_block(
        "The 10 most common oncogenic HPV types among women in the US are 16, 18, 31, and 59. "
        "Approximately 3.9% of women in the general population are infected with cervical HPV "
        "types 16 or 18 [Ref. 5.4: NEW]. "
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-16T00:00:00Z",
    )
    kinds = [_local_name(e.tag) for e in els]
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    dels = [e for e in els if _local_name(e.tag) == "del"]
    inses = [e for e in els if _local_name(e.tag) == "ins"]
    assert "women in the US" in plain
    assert "[Ref. 5.4:" in plain
    assert len(dels) <= 5 and len(inses) <= 5, kinds
    assert "highest incidence rates" in "".join(_collect_del_text(e) for e in dels)
    assert "general population are infected" in "".join(_collect_t_text(e) for e in inses)


def test_build_paragraph_track_change_keeps_multiple_meaningful_equal_anchors() -> None:
    """Do not collapse anchored multi-clause paragraph rewrites into one giant replace."""
    orig = _paragraph_block(
        "Based on SEER data between 2000 and 2018, the percentage of non-Hispanic Black "
        "patients increased steadily from those who were diagnosed at localized stage to "
        "those diagnosed at distant stage. However, the percentage of non-Hispanic White "
        "and Hispanic patients diagnosed for cervical cancer remained consistent across the "
        "stages [Ref. 5.4: 08BZMY]. In addition, it was observed that in White women, "
        "incidence rates of SCC and adenocarcinoma peaked between the ages of 35-44 years "
        "and remained stable thereafter, whereas the incidence rates continued to increase "
        "with age among Black women, peaking between the ages of 65-74 years for both subtypes."
    )
    rev = _paragraph_block(
        "Based on SEER data between 2000 and 2018, the percentage of non-Hispanic Black "
        "females diagnosed with cervical cancer increased steadily from those who were "
        "diagnosed at localized stage to those diagnosed at distant stage. However, the "
        "percentage of non-Hispanic White and Hispanic patients diagnosed for cervical cancer "
        "remained consistent across the stages. In addition, incidence rates of SCC and "
        "adenocarcinoma in White women peaked between the ages of 35 to 44 years and remained "
        "stable thereafter, whereas the incidence rates continued to increase with age among "
        "Black women, peaking between the ages of 65 to 74 years for both subtypes."
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-16T00:00:00Z",
    )
    kinds = [_local_name(e.tag) for e in els]
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    dels = [e for e in els if _local_name(e.tag) == "del"]
    inses = [e for e in els if _local_name(e.tag) == "ins"]
    assert kinds != ["del", "ins", "r"], kinds
    assert len(dels) >= 4 and len(inses) >= 4, kinds
    assert "Based on SEER data between 2000 and 2018, the percentage of non-Hispanic Black " in plain
    assert "However, the percentage of non-Hispanic White and Hispanic patients diagnosed for cervical cancer remained consistent across the stages" in plain
    assert "incidence rates of SCC and adenocarcinoma" in plain
    assert any("patients " == _collect_del_text(e) for e in dels)
    assert any(
        "females diagnosed with cervical cancer " == _collect_t_text(e) for e in inses
    )


def test_build_paragraph_track_change_splits_asymmetric_replace_on_internal_phrase() -> None:
    """A coarse replace can still preserve an internal reused phrase like ``In addition``."""
    orig = _paragraph_block(
        "Based on SEER data between 2000 and 2018, patients increased steadily. "
        "[Ref. 5.4: 08BZMY]. In addition, it was observed that in White women, incidence rates rose."
    )
    rev = _paragraph_block(
        "Based on SEER data between 2000 and 2018, females diagnosed with cervical cancer increased steadily. "
        ". In addition, incidence rates rose."
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-16T00:00:00Z",
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    dels = [_collect_del_text(e) for e in els if _local_name(e.tag) == "del"]
    assert "In addition" in plain
    assert sum(1 for e in els if _local_name(e.tag) == "del") >= 2
    assert any("it was observed that in White women" in chunk for chunk in dels)


def test_build_paragraph_track_change_splits_replace_on_multiple_short_nonweak_anchors() -> None:
    """Multiple short non-weak anchors inside a large replace should still split the span."""
    orig = _paragraph_block(
        "had the highest incidence rates of cervical SCC compared with other racial and ethnic groups"
    )
    rev = _paragraph_block(
        "are 16, 18, and 59. Approximately 3.9% of women are infected with cervical HPV types compared with non-Hispanic groups"
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-17T00:00:00Z",
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    assert "cervical " in plain
    assert "compared with " in plain
    assert "groups" in plain


def test_build_paragraph_track_change_keeps_cervical_disparities_reference_boundary_stable() -> None:
    """SCRUM-151: keep the reference/sentence boundary plain in the disparities rewrite."""

    orig = _paragraph_block(
        "Racial and ethnic differences in cervical cancer incidence and mortality in the US "
        "may be partly attributed to differences in access to healthcare/screening and follow-up "
        "after abnormal results [Ref. 5.4: 08BZMY, 08D67R]. Cervical screening that employs "
        "cytology is less effective in detecting adenocarcinoma compared with SCC, which may "
        "partly explain the relative lower incidence of cervical adenocarcinoma among Black women "
        "[Ref. 5.4: 03Q0K8, 08D67W]. It is also possible that the differences in the prevalence "
        "of HPV16 contribute to subtype-specific differences in cervical cancer incidence, "
        "particularly because of its reduced prevalence among Black women compared with White "
        "women in the US, and because this type is more likely to cause adenocarcinoma relative "
        "to other HPV types [Ref. 5.4: 08D67M, 08D67G, 08D67L]. "
    )
    rev = _paragraph_block(
        "Disparities in cervical cancer incidence and mortality exist by geographic area and "
        "income level, which may reflect differences in access to health care/screening and "
        "follow-up after abnormal results [Ref. 5.4: 08BZMY, 08D67R, 08RS8Q, 08RS8S]. Women "
        "living in nonmetropolitan or rural areas had higher incidence of cervical cancer and "
        "higher mortality from cervical cancer compared with those living in urban or metropolitan "
        "areas, in part due to lower vaccination and screening rates [Ref. 5.4: 08RS8S]. Deaths "
        "from cervical cancer were 48.8% higher in counties with persistent poverty compared with "
        "nonpersistent poverty counties [Ref. 5.4: 08RS8N]. Mortality rates were highest for "
        "Black residents of counties that were both rural and lowincome/persistent poverty "
        "[Ref. 5.4: 08RS8N, 08RS8Q]."
    )

    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-24T00:00:00Z",
    )

    plain_chunks = [_collect_t_text(e) for e in els if _local_name(e.tag) == "r"]
    del_chunks = [_collect_del_text(e) for e in els if _local_name(e.tag) == "del"]

    assert "]. " in plain_chunks
    assert "adenocarcinoma among Black women " in del_chunks
    assert not any(
        "Cervical screening" in chunk and "03Q0K8" in chunk for chunk in del_chunks
    ), del_chunks


def test_build_paragraph_track_change_prefers_earlier_repeated_internal_anchor() -> None:
    """Repeated equal text inside a coarse replace should anchor to the earlier semantic match."""
    orig = _paragraph_block(
        "had the highest incidence rates of cervical SCC compared with other racial and ethnic groups, "
        "while the incidence of cervical adenocarcinoma was highest among White and Hispanic women."
    )
    rev = _paragraph_block(
        "are 16, 18, 31, 39, 45, 51, 52, 56, 58, and 59. Approximately 3.9% of women in the general "
        "population are infected with cervical HPV types 16 or 18 at any given time, and these 2 types "
        "account for 71.2% of invasive cervical cancers [Ref. 5.4: 08S7BQ]. An evaluation of 26,302 US "
        "gynecologic cytology specimens reported a higher prevalence of non-16/18 highrisk HPV among Black "
        "women (15%) compared with White women (9%) [Ref. 5.4: 08D7B6]. A recent study of 60 patients with "
        "cervical carcinoma where 90% self-identified as Black or African American, found non16/18 HPV "
        "genotypes to be more prevalent than 16/18 HPV genotypes. Notably, the study identified HPV 35 as "
        "the most frequently isolated high-risk genotype in the Black patient population [Ref. 5.4: 08D7B3]. "
        "A large proportion of cases of cervical intraepithelial neoplasia Grade 3 have also been attributed "
        "to HPV 35 in non-Hispanic Black women compared with non-Hispanic Asian or Pacific Islander, "
        "non-Hispanic White, and Hispanic women [Ref. 5.4: 08FCRY]."
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-17T00:00:00Z",
    )
    chunks = []
    for el in els:
        tag = _local_name(el.tag)
        if tag == "r":
            chunks.append((tag, _collect_t_text(el)))
        elif tag == "del":
            chunks.append((tag, _collect_del_text(el)))
        elif tag == "ins":
            chunks.append((tag, _collect_t_text(el)))
    scc_idx = next(i for i, (tag, text) in enumerate(chunks) if tag == "del" and text == "SCC ")
    next_tag, next_text = chunks[scc_idx + 1]
    assert next_tag == "ins"
    assert "HPV types 16 or 18" in next_text
    assert next_text.startswith("HPV types 16 or 18")


def test_build_paragraph_track_change_rotates_shared_punctuation_around_deleted_clause() -> None:
    """Comma/space around a deleted clause should stay plain when shared by both sides."""
    orig = _paragraph_block("Alpha. In addition, it was observed that in White women, incidence rates rose.")
    rev = _paragraph_block("Alpha. In addition, incidence rates rose.")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-17T00:00:00Z",
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    dels = [_collect_del_text(e) for e in els if _local_name(e.tag) == "del"]
    assert "In addition, " in plain
    assert any(chunk.startswith("it was observed") for chunk in dels)
    assert any(chunk.endswith(", ") for chunk in dels)


def test_numeric_grouping_comma_removal_is_inline_delete_not_full_replace() -> None:
    """SCRUM-141: comma-only numeric formatting edits should delete just the comma."""
    els = _track_change_elements_for_concat_texts(
        "5,003",
        "5003",
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
    )
    dels = [e for e in els if _local_name(e.tag) == "del"]
    inses = [e for e in els if _local_name(e.tag) == "ins"]
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    assert len(dels) == 1
    assert len(inses) == 0
    assert _collect_del_text(dels[0]) == ","
    assert plain.replace(" ", "") == "5003"


def test_preserving_path_numeric_grouping_comma_only_inline_delete() -> None:
    """SCRUM-141: table cells use preserving emit; comma-only edits must not full-replace the cell."""
    p = ET.Element(f"{{{WORD_NS}}}p")
    r_el = ET.Element(f"{{{WORD_NS}}}r")
    t = ET.SubElement(r_el, f"{{{WORD_NS}}}t")
    t.text = "5,003"
    p.append(r_el)
    orig = {"type": "paragraph", "id": "p1", "runs": [{"text": "5,003"}]}
    rev = {"type": "paragraph", "id": "p1", "runs": [{"text": "5003"}]}
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
        source_p_el=p,
    )
    dels = [e for e in els if _local_name(e.tag) == "del"]
    inses = [e for e in els if _local_name(e.tag) == "ins"]
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    assert len(dels) == 1
    assert len(inses) == 0
    assert _collect_del_text(dels[0]) == ","
    assert plain.replace(" ", "") == "5003"


def test_numeric_cell_partial_change_keeps_unchanged_prefix_and_parentheses() -> None:
    """
    SCRUM-141: small internal edits inside a numeric table cell should not delete
    large unchanged spans.
    """
    els = _track_change_elements_for_concat_texts(
        "6566 (47.3%)",
        "6,376 (47.8%)",
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    del_all = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    ins_all = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "ins")
    # Must keep shared structure plain.
    assert "(" in plain and "%)" in plain
    # Must not delete the shared " (" prefix into a giant replace span.
    assert " (" not in del_all
    # Should at least revise some digits.
    assert any(ch.isdigit() for ch in del_all)
    assert any(ch.isdigit() for ch in ins_all)


def test_preserving_path_numeric_cell_partial_change_keeps_structure() -> None:
    """
    SCRUM-141: table cells use ``source_p_el`` preserving emit; partial numeric edits
    must not monolithically strike the whole cell.

    Assertions are behavioral (plain vs revision regions), not opcode counts or exact
    chunk boundaries, so refactors can still change internal TC shape.
    """
    orig_s = "6566 (47.3%)"
    rev_s = "6,376 (47.8%)"
    p = ET.Element(f"{{{WORD_NS}}}p")
    r_el = ET.Element(f"{{{WORD_NS}}}r")
    t = ET.SubElement(r_el, f"{{{WORD_NS}}}t")
    t.text = orig_s
    p.append(r_el)
    orig = {"type": "paragraph", "id": "p1", "runs": [{"text": orig_s}]}
    rev = {"type": "paragraph", "id": "p1", "runs": [{"text": rev_s}]}
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
        source_p_el=p,
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    del_all = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    ins_all = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "ins")
    assert "(" in plain and "%)" in plain
    assert " (" not in del_all
    assert any(ch.isdigit() for ch in del_all)
    assert any(ch.isdigit() for ch in ins_all)
    # Coarse regression: entire original cell must not be one undifferentiated deletion.
    assert del_all.replace(" ", "") != orig_s.replace(" ", "")


def test_table_header_cell_does_not_delete_unchanged_estimated_number_prefix() -> None:
    """SCRUM-141: table header edits should not strike through unchanged leading phrase."""
    prefix = "Estimated Number of New Cases in "
    orig = prefix + "2023b, c, d, n (%)"
    rev = prefix + "2025b,c,d, n (%)"
    els = _track_change_elements_for_concat_texts(
        orig,
        rev,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    del_all = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    assert prefix in plain
    assert prefix not in del_all


def test_preserving_path_table_header_keeps_long_prefix_plain() -> None:
    """SCRUM-141: preserving emit for table cells must apply char-level replace like concat path."""
    prefix = "Estimated Number of New Cases in "
    orig_s = prefix + "2023b, c, d, n (%)"
    rev_s = prefix + "2025b,c,d, n (%)"
    p = ET.Element(f"{{{WORD_NS}}}p")
    r_el = ET.Element(f"{{{WORD_NS}}}r")
    t = ET.SubElement(r_el, f"{{{WORD_NS}}}t")
    t.text = orig_s
    p.append(r_el)
    orig = {"type": "paragraph", "id": "p1", "runs": [{"text": orig_s}]}
    rev = {"type": "paragraph", "id": "p1", "runs": [{"text": rev_s}]}
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
        source_p_el=p,
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    del_all = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    assert prefix in plain
    assert prefix not in del_all


def test_table_header_cell_preserves_superscript_footnote_runs_during_year_change() -> None:
    tc = ET.Element(f"{{{WORD_NS}}}tc")
    p = ET.SubElement(tc, f"{{{WORD_NS}}}p")
    r1 = ET.SubElement(p, f"{{{WORD_NS}}}r")
    t1 = ET.SubElement(r1, f"{{{WORD_NS}}}t")
    t1.text = "Estimated Number of New Cases in 2023"
    p.append(_w_r_with_vert_align("b, c, d", val="superscript"))
    r3 = ET.SubElement(p, f"{{{WORD_NS}}}r")
    t3 = ET.SubElement(r3, f"{{{WORD_NS}}}t")
    t3.text = ", n (%)"

    revised_tc = ET.Element(f"{{{WORD_NS}}}tc")
    revised_p = ET.SubElement(revised_tc, f"{{{WORD_NS}}}p")
    rr1 = ET.SubElement(revised_p, f"{{{WORD_NS}}}r")
    rt1 = ET.SubElement(rr1, f"{{{WORD_NS}}}t")
    rt1.text = "Estimated Number of New Cases in 2025"
    revised_p.append(_w_r_with_vert_align("b,c,d", val="superscript"))
    rr3 = ET.SubElement(revised_p, f"{{{WORD_NS}}}r")
    rt3 = ET.SubElement(rr3, f"{{{WORD_NS}}}t")
    rt3.text = ", n (%)"

    orig_cell = {
        "paragraphs": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [
                    {"text": "Estimated Number of New Cases in 2023"},
                    {"text": "b, c, d"},
                    {"text": ", n (%)"},
                ],
            }
        ]
    }
    rev_cell = {
        "paragraphs": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [
                    {"text": "Estimated Number of New Cases in 2025"},
                    {"text": "b,c,d"},
                    {"text": ", n (%)"},
                ],
            }
        ]
    }

    body_revision_emit._apply_table_cell_track_changes(
        tc,
        orig_cell,
        rev_cell,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        [0],
        "Test",
        "2026-04-25T00:00:00Z",
        revised_tc_el=revised_tc,
    )

    superscript_runs = [
        r
        for r in tc.findall(".//w:r", NS)
        if r.find("w:rPr/w:vertAlign[@w:val='superscript']", NS) is not None
    ]
    superscript_texts = [_collect_t_text(r) for r in superscript_runs]
    assert any(any(ch in text for ch in ("b", "c", "d")) for text in superscript_texts)
    del_all = "".join(_collect_del_text(e) for e in tc.findall(".//w:del", NS))
    ins_all = "".join(_collect_t_text(e) for e in tc.findall(".//w:ins", NS))
    deleted_superscript_runs = [
        r
        for r in tc.findall(".//w:del//w:r", NS)
        if r.find("w:rPr/w:vertAlign[@w:val='superscript']", NS) is not None
    ]
    assert any("b" in _collect_del_text(r) for r in deleted_superscript_runs)
    assert "2023" in del_all
    assert "2025" in ins_all
    assert "Estimated Number of New Cases in " not in del_all


def test_scrum154_cervical_table_header_superscripts_remain_superscripted(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum154_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    target_tc = next(
        (
            tc
            for tc in root.findall(".//w:tc", NS)
            if "Estimated Number" in _collect_t_text(tc)
            and "of New Cases in" in _collect_t_text(tc)
            and "n (%)" in _collect_t_text(tc)
            and any(
                any(ch in _collect_t_text(r) for ch in ("b", "c", "d"))
                for r in tc.findall(".//w:r", NS)
                if r.find("w:rPr/w:vertAlign[@w:val='superscript']", NS) is not None
            )
        ),
        None,
    )
    assert target_tc is not None
    superscript_runs = [
        r
        for r in target_tc.findall(".//w:r", NS)
        if r.find("w:rPr/w:vertAlign[@w:val='superscript']", NS) is not None
    ]
    superscript_texts = [_collect_t_text(r) for r in superscript_runs]
    assert any(any(ch in text for ch in ("b", "c", "d")) for text in superscript_texts)
    del_all = "".join(_collect_del_text(e) for e in target_tc.findall(".//w:del", NS))
    ins_all = "".join(_collect_t_text(e) for e in target_tc.findall(".//w:ins", NS))
    deleted_superscript_runs = [
        r
        for r in target_tc.findall(".//w:del//w:r", NS)
        if r.find("w:rPr/w:vertAlign[@w:val='superscript']", NS) is not None
    ]
    assert any("b" in _collect_del_text(r) for r in deleted_superscript_runs)
    assert "2023" in del_all
    assert "2025" in ins_all
    assert "Estimated Number of New Cases in " not in del_all


def test_build_paragraph_track_change_dedupes_reinserted_plain_anchor() -> None:
    """A repeated anchor should not survive as both plain text and a duplicate insert."""
    orig = _paragraph_block(
        "However, the percentage remained consistent [Ref. 5.4: 08BZMY]. In addition, "
        "it was observed that in White women, incidence rates of SCC and adenocarcinoma peaked "
        "between the ages of 35-44 years."
    )
    rev = _paragraph_block(
        "However, the percentage remained consistent. In addition, incidence rates of SCC and "
        "adenocarcinoma in White women peaked between the ages of 35 to 44 years."
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-17T00:00:00Z",
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    inses = [_collect_t_text(e) for e in els if _local_name(e.tag) == "ins"]
    dels = [_collect_del_text(e) for e in els if _local_name(e.tag) == "del"]
    assert "In addition, " in plain
    assert not any(chunk == "In addition" for chunk in inses)
    assert any("it was observed that in White women" in chunk for chunk in dels)


def test_build_paragraph_track_change_absorbs_weak_short_equal_anchor() -> None:
    """Short weak anchors like ``may`` should merge into surrounding changes."""
    orig = _paragraph_block(
        "Disparities in cervical cancer incidence and mortality in the US may be partly attributed to differences in access to healthcare."
    )
    rev = _paragraph_block(
        "Disparities in cervical cancer incidence and mortality exist by geographic area, which may reflect differences in access to health care."
    )
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-16T00:00:00Z",
    )
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    assert "may " not in plain


def test_build_paragraph_track_change_preserving_source_p_el_clones_run_properties() -> None:
    """When *source_p_el* matches IR runs, unchanged spans emit cloned ``w:r`` with same ``w:rPr``."""

    def r_with_pr(text: str, *, bold: bool = False, italic: bool = False) -> ET.Element:
        r = ET.Element(f"{{{WORD_NS}}}r")
        if bold or italic:
            rpr = ET.SubElement(r, f"{{{WORD_NS}}}rPr")
            if bold:
                ET.SubElement(rpr, f"{{{WORD_NS}}}b")
            if italic:
                ET.SubElement(rpr, f"{{{WORD_NS}}}i")
        t = ET.SubElement(r, f"{{{WORD_NS}}}t")
        t.text = text
        return r

    p = ET.Element(f"{{{WORD_NS}}}p")
    p.append(r_with_pr("Say ", bold=True))
    p.append(r_with_pr("the cat", italic=True))

    orig = {
        "type": "paragraph",
        "id": "p1",
        "runs": [{"text": "Say "}, {"text": "the cat"}],
    }
    rev = {
        "type": "paragraph",
        "id": "p1",
        "runs": [{"text": "Say hte cat"}],
    }

    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-11T00:00:00Z",
        source_p_el=p,
    )

    assert [_local_name(e.tag) for e in els] == ["r", "del", "ins", "r"]
    assert els[0].find("w:rPr/w:b", NS) is not None
    assert _collect_t_text(els[0]) == "Say "
    assert _collect_del_text(els[1]) == "the "
    assert _collect_t_text(els[2]) == "hte "
    assert els[3].find("w:rPr/w:i", NS) is not None
    assert _collect_t_text(els[3]) == "cat"


def test_build_paragraph_preserving_refines_multi_token_replace_span() -> None:
    """Run-preserving path: equal spans stay plain ``w:r``; replace is one ``w:del`` + one ``w:ins``."""
    full_o = "LEFT KEEP MID1 MID2 RIGHT KEEP"
    full_r = "LEFT KEEP NEW1 NEW2 RIGHT KEEP"
    p = ET.Element(f"{{{WORD_NS}}}p")
    r_el = ET.Element(f"{{{WORD_NS}}}r")
    t = ET.SubElement(r_el, f"{{{WORD_NS}}}t")
    t.text = full_o
    p.append(r_el)
    orig = {"type": "paragraph", "id": "p1", "runs": [{"text": full_o}]}
    rev = {"type": "paragraph", "id": "p1", "runs": [{"text": full_r}]}
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-11T12:00:00Z",
        source_p_el=p,
    )
    del_text = "".join(_collect_del_text(e) for e in els if _local_name(e.tag) == "del")
    ins_text = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "ins")
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    assert "LEFT KEEP" in plain and "RIGHT KEEP" in plain
    assert "LEFT" not in del_text and "RIGHT" not in del_text
    assert "MID1" in del_text and "MID2" in del_text
    assert "NEW1" in ins_text and "NEW2" in ins_text


def test_word_token_similarity_ratio_unrelated_is_below_coalesce_threshold() -> None:
    """Unrelated token lists score low on non-whitespace norm-key similarity."""
    assert _word_token_similarity_ratio("a b c d e", "v w x y z") < 0.20


def test_word_token_similarity_ratio_shared_structure_scores_higher() -> None:
    """Shared vocabulary yields higher similarity than unrelated text."""
    assert _word_token_similarity_ratio("foo bar hello world", "foo bar goodbye world") >= 0.20


def test_word_token_similarity_ratio_large_similar_paragraph_clears_inline_threshold() -> None:
    """Large same-paragraph edits should stay above the inline-diff threshold."""

    orig = (
        "The sponsor will continue to build upon diversity efforts expected by the FDA "
        "and will embed participant diversity and inclusion into product development "
        "across clinical planning, study recruitment, site activation, and monitoring."
    )
    rev = (
        "The sponsor will continue to build upon diversity efforts expected by the FDA "
        "and will embed participant diversity and inclusion into product development "
        "across clinical planning, study recruitment, country selection, site activation, "
        "enrollment monitoring, and patient retention."
    )
    assert _word_token_similarity_ratio(orig, rev) >= 0.70


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


def test_build_paragraph_track_change_partial_token_edit_stays_inline_not_full_replace() -> None:
    """Small token edits must not collapse the paragraph into one full delete/insert."""

    orig = _paragraph_block("Marker status was L in the baseline sample.")
    rev = _paragraph_block("Marker status was (L) in the baseline sample.")
    els = build_paragraph_track_change_elements(
        orig,
        rev,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        id_counter=[0],
        author="Test",
        date_iso="2026-04-19T00:00:00Z",
    )
    assert [_local_name(e.tag) for e in els] != ["del", "ins"]
    plain = "".join(_collect_t_text(e) for e in els if _local_name(e.tag) == "r")
    assert "Marker status was " in plain
    assert "in the baseline sample." in plain


def test_build_paragraph_track_change_unrelated_phrase_block_del_ins() -> None:
    """Large rewrites use one ``w:del`` + ``w:ins`` per multi-token replace opcode (no nested word LCS)."""
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
    inses = [e for e in els if _local_name(e.tag) == "ins"]
    del_chunks = [_collect_del_text(d) for d in dels]
    ins_chunks = [_collect_t_text(i) for i in inses]
    joined_del = "".join(del_chunks)
    joined_ins = "".join(ins_chunks)
    assert "overall" in joined_del and "response" in joined_del and "rate" in joined_del
    assert "progression" in joined_ins and "survival" in joined_ins
    assert "12" in joined_del and "24" in joined_ins
    assert len(dels) >= 1 and len(inses) >= 1


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
    """SCRUM-120: revised-only paragraph then table — insert order keeps paragraph above table."""
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


def test_scrum131_cervical_abbreviations_table_diffs_in_place_not_whole_table_insert(
    tmp_path: Path,
) -> None:
    """SCRUM-131: abbreviation table should stay in place with row/cell-level revisions."""
    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum131_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    children = list(body)

    terms_i = next(
        (
            i
            for i, ch in enumerate(children)
            if _local_name(ch.tag) == "p"
            and "Terms describing racial and ethnic categories" in _collect_t_text(ch)
        ),
        None,
    )
    assert terms_i is not None

    first_table_idx = next(
        (
            i
            for i, ch in enumerate(children)
            if i > terms_i
            and (
                _local_name(ch.tag) == "tbl"
                or (_local_name(ch.tag) == "ins" and ch.find("w:tbl", NS) is not None)
            )
        ),
        None,
    )
    assert first_table_idx is not None
    first_table_container = children[first_table_idx]
    assert _local_name(first_table_container.tag) == "tbl"
    assert first_table_container.find(".//w:ins", NS) is not None


def test_scrum140_bladder_abbreviation_row_keeps_partial_inline_change(
    tmp_path: Path,
) -> None:
    """SCRUM-140: punctuation-only abbreviation edits should stay on one row inline."""
    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("bladder diversity sample docs not present")

    out = tmp_path / "scrum140_bladder_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    rows = root.findall(".//w:tr", NS)

    def _row_cells(tr: ET.Element) -> list[str]:
        return [
            "".join(t.text or "" for t in tc.findall(".//w:t", NS))
            for tc in tr.findall("w:tc", NS)
        ]

    anchor_rows: dict[str, int] = {}
    for idx, tr in enumerate(rows):
        cells = _row_cells(tr)
        joined = " | ".join(cells)
        if joined == "PAO | patient advocacy organization":
            anchor_rows["pao"] = idx
        elif joined == "PD-(L)1 | programmed death-ligand 1":
            anchor_rows["pd"] = idx
        elif joined == "PK | pharmacokinetics":
            anchor_rows["pk"] = idx

    assert anchor_rows == {
        "pao": anchor_rows["pao"],
        "pd": anchor_rows["pao"] + 1,
        "pk": anchor_rows["pao"] + 2,
    }

    pd_row = rows[anchor_rows["pd"]]
    ins_texts = [
        "".join(t.text or "" for t in ins.findall(".//w:t", NS))
        for ins in pd_row.findall(".//w:ins", NS)
    ]
    assert any("(L)" in text for text in ins_texts)
    assert "programmed death-ligand 1" not in ins_texts


def test_scrum140b_bladder_body_disparities_paragraph_partial_inline_not_full_replace(
    tmp_path: Path,
) -> None:
    """SCRUM-140B: body paragraph with long shared opening — not one giant w:del/w:ins pair."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("bladder diversity sample docs not present")

    shared_opening = (
        "Despite the fact that bladder cancer incidence is higher among White individuals, "
        "Black individuals in the US die of bladder cancer at higher rates than any other "
        "racial or ethnic group."
    )

    out = tmp_path / "scrum140b_bladder_body_disparities_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    anchor = "Despite the fact that bladder cancer incidence is higher among White individuals"
    target_p = next(
        (
            p
            for p in body.findall("w:p", NS)
            if anchor in _paragraph_track_visible_text(p)
        ),
        None,
    )
    assert target_p is not None

    del_concat = _collect_del_text(target_p)
    ins_concat = "".join(
        t.text or "" for t in target_p.findall(".//w:ins//w:t", NS)
    )
    assert shared_opening not in del_concat, (
        "stable opening must not appear inside w:del (full-paragraph-style replace)"
    )
    assert shared_opening not in ins_concat, (
        "stable opening must not appear only as inserted text (full-paragraph-style replace)"
    )
    n_del = len(target_p.findall(".//w:del", NS))
    n_ins = len(target_p.findall(".//w:ins", NS))
    assert n_del >= 1 and n_ins >= 1, "expected some inline revisions"
    assert n_del <= 24 and n_ins <= 24, (
        f"expected localized edits, not one block replace; del={n_del} ins={n_ins}"
    )
    max_del_run = 0
    for d in target_p.findall(".//w:del", NS):
        chunk = _collect_del_text(d)
        max_del_run = max(max_del_run, len(chunk))
    assert max_del_run <= 120, (
        f"single w:del span should not cover a huge clause; max_del_run={max_del_run}"
    )
    assert len(del_concat) <= 400, (
        f"total deleted chars should be modest vs paragraph length; got {len(del_concat)}"
    )


def test_scrum144_bladder_enrollment_goals_shortening_stays_inline(
    tmp_path: Path,
) -> None:
    """SCRUM-144: preserve the shared sentence stem inline instead of delete+insert blocks."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("bladder diversity sample docs not present")

    out = tmp_path / "scrum144_bladder_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    paras = body.findall("w:p", NS)

    heading_idx = next(
        i
        for i, p in enumerate(paras)
        if _collect_t_text(p).strip() == "STATUS OF MEETING ENROLLMENT GOALS"
    )
    target_p = paras[heading_idx + 1]

    plain = _collect_t_text(target_p)
    deleted = _collect_del_text(target_p)
    ins_chunks = [_collect_t_text(ins) for ins in target_p.findall(".//w:ins", NS)]

    assert plain.strip() == "Not applicable."
    assert "Not applicable" not in deleted
    assert "as this is the initial Diversity Plan for la/mUC" in deleted
    assert not ins_chunks

    next_plain = _collect_t_text(paras[heading_idx + 2]).strip()
    assert next_plain != "Not applicable."


def test_scrum143_bladder_table2_shape_mismatch_has_cell_level_track_changes(
    tmp_path: Path,
) -> None:
    """SCRUM-143: goals-by-race table with differing w:tbl shape must not be a silent v2 replace."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-bladder-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("bladder diversity sample docs not present")

    out = tmp_path / "scrum143_bladder_table2_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    goals_tbl = next(
        (
            tbl
            for tbl in root.findall(".//w:tbl", NS)
            if "Distribution of New" in _collect_t_text(tbl)
        ),
        None,
    )
    assert goals_tbl is not None, "expected US distribution / goals table in output"
    n_ins = len(goals_tbl.findall(".//w:ins", NS))
    n_del = len(goals_tbl.findall(".//w:del", NS))
    assert n_ins >= 1 and n_del >= 1, (
        f"Table 2 must show cell-level track changes, not a bare v2 w:tbl; ins={n_ins} del={n_del}"
    )
    assert n_ins + n_del >= 8, (
        f"expected substantial per-cell redline; ins={n_ins} del={n_del}"
    )


def test_scrum130_merges_two_paragraph_intros_then_list_bullets(
    tmp_path: Path,
) -> None:
    """SCRUM-130: sponsor abbreviations — two ``Paragraph`` lines then bullets → one line, one ``w:del``."""
    orig_inner = """
<w:p><w:r><w:t>Keep</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Paragraph"/></w:pPr><w:r><w:t>This list serves as the first appearance.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Paragraph"/></w:pPr><w:r><w:t>The following terms may be used interchangeably:</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r><w:t>RowA</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r><w:t>RowB</w:t></w:r></w:p>
"""
    rev_inner = "<w:p><w:r><w:t>Keep</w:t></w:r></w:p>"
    orig = _minimal_docx(tmp_path, orig_inner, "orig_scrum130_two_para.docx")
    rev = _minimal_docx(tmp_path, rev_inner, "rev_scrum130_two_para.docx")
    out = tmp_path / "out_scrum130_two_para.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    dels = body.findall(".//w:del", NS)
    assert len(dels) == 1
    dt = _collect_del_text(dels[0])
    assert "This list serves" in dt
    assert "following terms" in dt
    assert "RowA" in dt and "RowB" in dt
    assert "\n" not in dt
    assert len(dels[0].findall("w:r", NS)) >= 1
    assert len(dels[0].findall(".//w:br", NS)) >= 1
    merged_p = next(p for p in body.findall("w:p", NS) if p.find("w:del", NS) is not None)
    ppr = merged_p.find("w:pPr", NS)
    assert ppr is not None
    ps = ppr.find("w:pStyle", NS)
    assert ps is not None and ps.get(f"{{{WORD_NS}}}val") == "Normal"
    assert ppr.find("w:numPr", NS) is None


def test_scrum130_merges_paragraph_intro_and_list_bullet_full_deletes(
    tmp_path: Path,
) -> None:
    """SCRUM-130: ``Paragraph`` intro + list rows removed → one ``w:del`` on the intro ``w:p``."""
    orig_inner = """
<w:p><w:r><w:t>Keep</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Paragraph"/></w:pPr><w:r><w:t>Intro line removed</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r><w:t>RowA</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r><w:t>RowB</w:t></w:r></w:p>
"""
    rev_inner = "<w:p><w:r><w:t>Keep</w:t></w:r></w:p>"
    orig = _minimal_docx(tmp_path, orig_inner, "orig_scrum130_intro_list.docx")
    rev = _minimal_docx(tmp_path, rev_inner, "rev_scrum130_intro_list.docx")
    out = tmp_path / "out_scrum130_intro_list.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    dels = body.findall(".//w:del", NS)
    assert len(dels) == 1
    merged = dels[0]
    assert "Intro line removed" in _collect_del_text(merged)
    assert "RowA" in _collect_del_text(merged)
    assert "RowB" in _collect_del_text(merged)
    assert len(merged.findall("w:r", NS)) >= 1
    assert len(merged.findall(".//w:br", NS)) >= 1
    mp = next(p for p in body.findall("w:p", NS) if p.find("w:del", NS) is merged)
    assert mp.find("w:pPr/w:pStyle", NS).get(f"{{{WORD_NS}}}val") == "Normal"


def test_scrum130_merges_consecutive_list_bullet_full_deletes_without_intro(
    tmp_path: Path,
) -> None:
    """SCRUM-130: consecutive ``ListBullet`` full deletes (no ``Paragraph`` intro) → one ``w:del``."""
    orig_inner = """
<w:p><w:r><w:t>Keep</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r><w:t>Alpha</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r><w:t>Bravo</w:t></w:r></w:p>
"""
    rev_inner = "<w:p><w:r><w:t>Keep</w:t></w:r></w:p>"
    orig = _minimal_docx(tmp_path, orig_inner, "orig_scrum130_list_only.docx")
    rev = _minimal_docx(tmp_path, rev_inner, "rev_scrum130_list_only.docx")
    out = tmp_path / "out_scrum130_list_only.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    dels = body.findall(".//w:del", NS)
    assert len(dels) == 1
    dt = _collect_del_text(dels[0])
    assert "Alpha" in dt and "Bravo" in dt
    assert len(dels[0].findall("w:r", NS)) >= 1
    assert len(dels[0].findall(".//w:br", NS)) >= 1
    mp = next(p for p in body.findall("w:p", NS) if p.find("w:del", NS) is dels[0])
    assert mp.find("w:pPr/w:pStyle", NS).get(f"{{{WORD_NS}}}val") == "Normal"


def test_scrum130_cervical_abbreviations_keep_separate_deleted_paragraphs_before_insert(
    tmp_path: Path,
) -> None:
    """Real cervical pair: keep deleted intro/bullets as separate paragraphs before inserted replacement."""
    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")
    out = tmp_path / "scrum130_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    children = [ch for ch in list(body) if _local_name(ch.tag) in ("p", "tbl")]
    terms_idx = next(
        i
        for i, ch in enumerate(children)
        if _local_name(ch.tag) == "p"
        and "Terms describing racial and ethnic categories" in _collect_t_text(ch)
    )

    deleted_group = children[terms_idx - 4 : terms_idx]
    assert [_local_name(ch.tag) for ch in deleted_group] == ["p", "p", "p", "p"]
    expected = [
        ("Paragraph", "The following terms may be used interchangeably in this report:"),
        ("ListBullet", "Study and trial"),
        ("ListBullet", "Black and African American"),
        ("ListBullet", "White and non-Hispanic White"),
    ]
    for p, (style, deleted_text) in zip(deleted_group, expected, strict=True):
        ppr = p.find("w:pPr", NS)
        assert ppr is not None
        ps = ppr.find("w:pStyle", NS)
        assert ps is not None and ps.get(f"{{{WORD_NS}}}val") == style
        dels = p.findall("w:del", NS)
        assert len(dels) == 1
        assert deleted_text in _collect_del_text(dels[0])

    merged_blob = " ".join(_collect_del_text(p) for p in deleted_group)
    assert "The following terms may be used interchangeably in this report:" in merged_blob
    assert "Study and trial" in merged_blob
    assert "Black and African American" in merged_blob
    assert "White and non-Hispanic White" in merged_blob
    assert not any(
        p.find("w:pPr/w:pStyle", NS) is not None
        and p.find("w:pPr/w:pStyle", NS).get(f"{{{WORD_NS}}}val") == "Normal"
        and "following terms" in _collect_del_text(p).lower()
        for p in deleted_group
    )


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


def test_emit_table_row_addition_keeps_table_and_marks_new_row_inserted(
    tmp_path: Path,
) -> None:
    """SCRUM-131: row additions in matched tables stay row-level, not whole-table replace."""
    orig_tbl = """
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Abbreviation</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Definition</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
"""
    rev_tbl = """
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Abbreviation</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Definition</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>NEW</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>New meaning</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
"""
    orig = _minimal_docx(tmp_path, orig_tbl, "orig_row_add.docx")
    rev = _minimal_docx(tmp_path, rev_tbl, "rev_row_add.docx")
    out = tmp_path / "out_row_add.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    root = load_word_document_xml_root(out)
    tbls = root.findall(".//w:tbl", NS)
    assert len(tbls) == 1
    rows = tbls[0].findall("w:tr", NS)
    assert len(rows) == 2
    assert len(rows[0].findall("w:tc", NS)) == 2
    assert len(rows[1].findall("w:tc", NS)) == 2
    assert rows[1].findall(".//w:ins", NS)
    assert all(tc.find("w:tcPr/w:shd", NS) is not None for tc in rows[1].findall("w:tc", NS))
    body = root.find(".//w:body", NS)
    assert body is not None
    assert not any(
        _local_name(ch.tag) == "ins" and ch.find("w:tbl", NS) is not None
        for ch in list(body)
    )


def test_emit_table_middle_row_insert_does_not_replace_following_row(
    tmp_path: Path,
) -> None:
    """SCRUM-131: inserting a middle row should not mark later rows as replaced."""
    orig_tbl = """
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Abbreviation</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Definition</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Alpha</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>C</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Charlie</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
"""
    rev_tbl = """
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Abbreviation</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Definition</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Alpha</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Bravo</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>C</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Charlie</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
"""
    orig = _minimal_docx(tmp_path, orig_tbl, "orig_row_mid.docx")
    rev = _minimal_docx(tmp_path, rev_tbl, "rev_row_mid.docx")
    out = tmp_path / "out_row_mid.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    root = load_word_document_xml_root(out)
    tbl = root.find(".//w:tbl", NS)
    assert tbl is not None
    rows = tbl.findall("w:tr", NS)
    assert len(rows) == 4
    assert all(len(r.findall("w:tc", NS)) == 2 for r in rows)
    assert "B" in _collect_t_text(rows[2]) and rows[2].find(".//w:ins", NS) is not None
    assert all(tc.find("w:tcPr/w:shd", NS) is not None for tc in rows[2].findall("w:tc", NS))
    # Following row should remain unchanged (no revisions inside "C/Charlie" row).
    assert "CCharlie" in _collect_t_text(rows[3]).replace(" ", "")
    assert rows[3].find(".//w:ins", NS) is None
    assert rows[3].find(".//w:del", NS) is None
    assert all(tc.find("w:tcPr/w:shd", NS) is None for tc in rows[3].findall("w:tc", NS))


def test_emit_table_text_edit_cell_does_not_get_shading(
    tmp_path: Path,
) -> None:
    """SCRUM-133: text-only edits in existing cells should not trigger tc shading."""

    orig_tbl = """
<w:tbl>
  <w:tr>
    <w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
    <w:tc><w:p><w:r><w:t>Alpha</w:t></w:r></w:p></w:tc>
  </w:tr>
</w:tbl>
"""
    rev_tbl = """
<w:tbl>
  <w:tr>
    <w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
    <w:tc><w:p><w:r><w:t>Alpha revised</w:t></w:r></w:p></w:tc>
  </w:tr>
</w:tbl>
"""
    orig = _minimal_docx(tmp_path, orig_tbl, "orig_cell_edit.docx")
    rev = _minimal_docx(tmp_path, rev_tbl, "rev_cell_edit.docx")
    out = tmp_path / "out_cell_edit.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    root = load_word_document_xml_root(out)
    row = root.find(".//w:tbl/w:tr", NS)
    assert row is not None
    cells = row.findall("w:tc", NS)
    assert len(cells) == 2
    assert cells[1].find(".//w:ins", NS) is not None
    assert cells[1].find("w:tcPr/w:shd", NS) is None


def test_emit_table_cell_major_sentence_replace_emits_full_del_and_full_ins(
    tmp_path: Path,
) -> None:
    """SCRUM-131: major sentence replacement should appear as full-line del/ins."""
    orig_tbl = """
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Abbreviation</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Definition</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>This sentence describes the original clinical endpoint clearly.</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
"""
    rev_tbl = """
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Abbreviation</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Definition</w:t></w:r></w:p></w:tc></w:tr>
  <w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>A completely different sentence explains another safety objective now.</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
"""
    orig = _minimal_docx(tmp_path, orig_tbl, "orig_major_replace.docx")
    rev = _minimal_docx(tmp_path, rev_tbl, "rev_major_replace.docx")
    out = tmp_path / "out_major_replace.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    root = load_word_document_xml_root(out)
    tbl = root.find(".//w:tbl", NS)
    assert tbl is not None
    # Second cell should carry one full deleted sentence and one full inserted sentence.
    row = tbl.findall("w:tr", NS)[1]
    tc = row.findall("w:tc", NS)[1]
    dels = tc.findall(".//w:del", NS)
    ins = tc.findall(".//w:ins", NS)
    assert len(dels) == 1
    assert len(ins) == 1
    assert "original clinical endpoint" in _collect_del_text(dels[0])
    assert "different sentence explains another safety objective" in _collect_t_text(ins[0])


def test_emit_table_diff_preserves_neighbor_paragraph_spacing(
    tmp_path: Path,
) -> None:
    """SCRUM-131: table diffs must not alter spacing before/after neighboring paragraphs."""
    orig_body = """
<w:p>
  <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
  <w:r><w:t>Before table</w:t></w:r>
</w:p>
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Key</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Old sentence for value</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
<w:p>
  <w:pPr><w:spacing w:before="60" w:after="300"/></w:pPr>
  <w:r><w:t>After table</w:t></w:r>
</w:p>
"""
    rev_body = """
<w:p>
  <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
  <w:r><w:t>Before table</w:t></w:r>
</w:p>
<w:tbl>
  <w:tr><w:tc><w:p><w:r><w:t>Key</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>New sentence for value that changed</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
<w:p>
  <w:pPr><w:spacing w:before="60" w:after="300"/></w:pPr>
  <w:r><w:t>After table</w:t></w:r>
</w:p>
"""
    orig = _minimal_docx(tmp_path, orig_body, "orig_spacing.docx")
    rev = _minimal_docx(tmp_path, rev_body, "rev_spacing.docx")
    out = tmp_path / "out_spacing.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    children = list(body)
    # Expect exactly: paragraph, table, paragraph (no extra spacing paragraphs).
    assert [_local_name(ch.tag) for ch in children[:3]] == ["p", "tbl", "p"]

    p_before = children[0]
    p_after = children[2]
    spacing_before = p_before.find("w:pPr/w:spacing", NS)
    spacing_after = p_after.find("w:pPr/w:spacing", NS)
    assert spacing_before is not None
    assert spacing_after is not None
    assert spacing_before.get(f"{{{WORD_NS}}}before") == "240"
    assert spacing_before.get(f"{{{WORD_NS}}}after") == "120"
    assert spacing_after.get(f"{{{WORD_NS}}}before") == "60"
    assert spacing_after.get(f"{{{WORD_NS}}}after") == "300"


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


def test_emit_package_replaces_numbering_part_with_revised_bytes(tmp_path: Path) -> None:
    """When both inputs carry numbering.xml, output should keep revised numbering defs."""

    body = "<w:p><w:r><w:t>Same</w:t></w:r></w:p>"
    orig = _minimal_docx(tmp_path, body, "orig_num.docx")
    rev = _minimal_docx(tmp_path, body, "rev_num.docx")

    orig_numbering = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>"""
    rev_numbering = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="9"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>
  <w:num w:numId="9"><w:abstractNumId w:val="9"/></w:num>
</w:numbering>"""

    with zipfile.ZipFile(orig, "a") as zf:
        zf.writestr("word/numbering.xml", orig_numbering)
    with zipfile.ZipFile(rev, "a") as zf:
        zf.writestr("word/numbering.xml", rev_numbering)

    out = tmp_path / "out_num.docx"
    emit_docx_with_package_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    with zipfile.ZipFile(out, "r") as zf:
        assert zf.read("word/numbering.xml") == rev_numbering


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
    assert any("overall" in c for c in del_chunks)


def test_scrum121_cervical_disparities_inline_track_changes_not_full_paragraph_del(
    tmp_path: Path,
) -> None:
    """SCRUM-121: cervical sample should group inline diff and preserve sponsor-like paragraph split."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum121_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    anchor = "ArecentlypublishedstudybasedonSEERdata"
    target_p = next(
        (
            p
            for p in body.findall("w:p", NS)
            if anchor
            in (_collect_t_text(p) + _collect_del_text(p)).replace(" ", "")
        ),
        None,
    )
    assert target_p is not None
    n_del = len(target_p.findall(".//w:del", NS))
    n_ins = len(target_p.findall(".//w:ins", NS))
    plain = _collect_t_text(target_p).strip()
    assert "women in the US" in plain
    assert "[Ref." in plain
    assert "Black women were more likely to be diagnosed" not in plain
    assert n_del <= 8 and n_ins <= 10 and len(plain) > 60, (
        "expected grouped inline revision, "
        f"got del={n_del} ins={n_ins} plain_len={len(plain)}"
    )
    paras = body.findall("w:p", NS)
    idx = paras.index(target_p)
    assert idx + 1 < len(paras)
    next_plain = _collect_t_text(paras[idx + 1]).strip()
    assert next_plain.startswith("Black women were more likely to be diagnosed")


def test_scrum151_cervical_disparities_reference_boundary_not_swallowed_into_large_delete(
    tmp_path: Path,
) -> None:
    """SCRUM-151: keep the adenocarcinoma sentence and reference boundary split cleanly."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum151_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None
    target_p = next(
        (
            p
            for p in body.findall("w:p", NS)
            if "adenocarcinoma among Black women" in _collect_del_text(p)
        ),
        None,
    )
    assert target_p is not None

    plain_chunks = [
        _collect_t_text(e) for e in list(target_p) if _local_name(e.tag) == "r"
    ]
    del_chunks = [_collect_del_text(d) for d in target_p.findall(".//w:del", NS)]

    assert "]" in plain_chunks
    assert ". " in plain_chunks
    assert "adenocarcinoma among Black women " in del_chunks
    assert not any(
        "Cervical screening" in chunk and "03Q0K8" in chunk for chunk in del_chunks
    ), del_chunks


def test_scrum127_cervical_page1_front_matter_preserves_blank_block_structure(
    tmp_path: Path,
) -> None:
    """SCRUM-127: revised-only blank paragraphs on page 1 should not be dropped."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum127_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None

    seq = _body_block_sequence(body)
    assert seq[0] == ("p", "SPONSOR’S NAME:Merck Sharp & Dohme LLC")
    assert seq[1] == ("p", "Rahway, NJ, USA (MSD)")
    assert seq[2] == ("p", "")
    assert seq[3][0] == "p"
    assert seq[3][1].startswith("Product number and indication:MK-2870")
    assert "cervical cancer" in seq[3][1]
    assert seq[4] == ("p", "Studies included in this Diversity Plan:")
    assert seq[5] == ("tbl", "")
    assert seq[6] == ("p", "")
    assert seq[7] == ("p", "DIVERSITY PLAN")
    assert seq[8] == ("p", "")
    assert seq[9] == ("p", "Version Number:2")
    assert seq[10] == ("p", "Release Date:26-JUN-2025")
    assert seq[11] == ("p", "")
    assert seq[12] == ("p", "")


def test_scrum127_cervical_diversity_plan_insert_preserves_run_formatting(
    tmp_path: Path,
) -> None:
    """SCRUM-127: revised-only front-matter title keeps bold/size on inserted run."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum127_cervical_diversity_plan_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None

    target_p = next(
        (
            p
            for p in body.findall("w:p", NS)
            if _collect_t_text(p).strip() == "DIVERSITY PLAN"
        ),
        None,
    )
    assert target_p is not None
    ins = target_p.find("w:ins", NS)
    assert ins is not None
    run = ins.find("w:r", NS)
    assert run is not None
    rpr = run.find("w:rPr", NS)
    assert rpr is not None
    assert rpr.find("w:b", NS) is not None
    sz = rpr.find("w:sz", NS)
    assert sz is not None and sz.get(f"{{{WORD_NS}}}val") == "36"


def test_revised_only_full_paragraph_insert_preserves_run_rpr(tmp_path: Path) -> None:
    """Revised-only paragraph inserts should keep source run formatting inside ``w:ins``."""

    orig = _minimal_docx(tmp_path, "", "scrum127_orig_empty.docx")
    rev_inner = """
<w:p>
  <w:pPr><w:jc w:val="center"/></w:pPr>
  <w:r>
    <w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr>
    <w:t>DIVERSITY PLAN</w:t>
  </w:r>
</w:p>
"""
    rev = _minimal_docx(tmp_path, rev_inner, "scrum127_rev_formatted.docx")
    out = tmp_path / "scrum127_out_formatted.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    p = root.find(".//w:body/w:p", NS)
    assert p is not None
    ins = p.find("w:ins", NS)
    assert ins is not None
    run = ins.find("w:r", NS)
    assert run is not None
    rpr = run.find("w:rPr", NS)
    assert rpr is not None
    assert rpr.find("w:b", NS) is not None
    sz = rpr.find("w:sz", NS)
    assert sz is not None and sz.get(f"{{{WORD_NS}}}val") == "36"


def test_revised_only_blank_toc_paragraph_preserves_structure_without_empty_insert(
    tmp_path: Path,
) -> None:
    """Blank TOC/sectPr paragraphs should not add an empty ``w:ins`` node."""

    orig = _minimal_docx(tmp_path, "", "scrum127_orig_empty_toc.docx")
    rev_inner = """
<w:p>
  <w:pPr>
    <w:pStyle w:val="TOCTitle"/>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
    </w:sectPr>
  </w:pPr>
</w:p>
"""
    rev = _minimal_docx(tmp_path, rev_inner, "scrum127_rev_blank_toc.docx")
    out = tmp_path / "scrum127_out_blank_toc.docx"
    emit_docx_with_body_track_changes(orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    root = load_word_document_xml_root(out)
    p = root.find(".//w:body/w:p", NS)
    assert p is not None
    assert p.find("w:pPr/w:pStyle", NS) is not None
    assert p.find("w:pPr/w:sectPr", NS) is not None
    assert p.find("w:ins", NS) is None


def test_scrum134_cervical_does_not_add_extra_page_breaks_after_toc_and_tables(
    tmp_path: Path,
) -> None:
    """SCRUM-134: keep sponsor-style blank/page-break structure after TOC and revision tables."""

    repo = Path(__file__).resolve().parents[1]
    v1 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version1.docx"
    v2 = repo / "sample-docs/email1docs/diversity-plan-cervical-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("cervical diversity sample docs not present")

    out = tmp_path / "scrum134_cervical_compare.docx"
    emit_docx_with_package_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )
    root = load_word_document_xml_root(out)
    body = root.find("w:body", NS)
    assert body is not None

    by_text: dict[str, ET.Element] = {}
    for p in body.findall("w:p", NS):
        txt = _collect_t_text(p).strip()
        if txt:
            by_text[txt] = p

    def has_page_break_before(text: str) -> bool:
        p = by_text[text]
        ppr = p.find("w:pPr", NS)
        return ppr is not None and ppr.find("w:pageBreakBefore", NS) is not None

    assert not has_page_break_before("TABLE OF CONTENTS")
    assert has_page_break_before("LIST OF TABLES")
    assert not has_page_break_before("LIST OF ABBREVIATIONS AND DEFINITION OF TERMS")
    assert not has_page_break_before("Key partnership and patient advocacy measures include:")
    assert has_page_break_before("REFERENCES")

    children = [ch for ch in list(body) if _local_name(ch.tag) in ("p", "tbl")]
    abbrev_table_idx = next(
        i
        for i, ch in enumerate(children)
        if _local_name(ch.tag) == "tbl"
        and "Abbreviation" in _collect_t_text(ch)
        and "Definition" in _collect_t_text(ch)
    )
    rev_heading_idx = next(
        i
        for i, ch in enumerate(children)
        if i > abbrev_table_idx
        and _local_name(ch.tag) == "p"
        and "TABLE OF REVISIONS" in _collect_t_text(ch)
    )
    exec_idx = next(
        i
        for i, ch in enumerate(children)
        if i > rev_heading_idx
        and _local_name(ch.tag) == "p"
        and "EXECUTIVE SUMMARY OF THE SPONSOR" in _collect_t_text(ch)
    )
    between = children[rev_heading_idx + 1 : exec_idx]
    assert [_local_name(ch.tag) for ch in between] == ["tbl", "p", "p"]
    first_blank, second_blank = between[1], between[2]
    assert _collect_t_text(first_blank) == ""
    assert _collect_t_text(second_blank) == ""
    assert first_blank.find(".//w:br", NS) is None
    br = second_blank.find(".//w:br", NS)
    assert br is not None
    assert br.get(f"{{{WORD_NS}}}type") == "page"

    list_tables_idx = next(
        i
        for i, ch in enumerate(children)
        if _local_name(ch.tag) == "p" and _collect_t_text(ch).strip() == "LIST OF TABLES"
    )
    last_toc_idx = max(
        i
        for i, ch in enumerate(children[:list_tables_idx])
        if _local_name(ch.tag) == "p" and _collect_t_text(ch).strip() == "6REFERENCES31"
    )
    assert children[last_toc_idx + 1] is children[list_tables_idx]
    list_abbrev_idx = next(
        i
        for i, ch in enumerate(children)
        if i > list_tables_idx
        and _local_name(ch.tag) == "p"
        and _collect_t_text(ch).strip() == "LIST OF ABBREVIATIONS AND DEFINITION OF TERMS"
    )
    between_lot_and_abbrev = children[list_tables_idx + 1 : list_abbrev_idx]
    assert [_local_name(ch.tag) for ch in between_lot_and_abbrev] == ["p", "p", "p", "p"]
    assert all(_local_name(ch.tag) == "p" for ch in between_lot_and_abbrev)
    # Three table-of-figures lines, then one page-break-only blank paragraph.
    for p in between_lot_and_abbrev[:3]:
        assert p.find(".//w:br", NS) is None
    trailing_break = between_lot_and_abbrev[3]
    br = trailing_break.find(".//w:br", NS)
    assert br is not None
    assert br.get(f"{{{WORD_NS}}}type") == "page"


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
