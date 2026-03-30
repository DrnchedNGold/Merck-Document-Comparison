"""Regression: standalone TOC-style insert/delete preserves ``w:tab`` and run layout."""

from __future__ import annotations

import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_revision_emit import emit_docx_with_body_track_changes
from engine.docx_body_ingest import load_word_document_xml_root

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


def _minimal_docx(tmp_path: Path, body_inner: str, filename: str) -> Path:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    {body_inner}
  </w:body>
</w:document>
"""
    p = tmp_path / filename
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", document_xml.encode("utf-8"))
    return p


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


TOC_ENTRY_XML = """
<w:p>
  <w:pPr><w:pStyle w:val="TOC1"/></w:pPr>
  <w:r><w:t>SECTION TITLE</w:t></w:r>
  <w:r><w:tab/><w:t>12</w:t></w:r>
</w:p>
"""


def test_emit_toc_style_insert_preserves_w_tab_and_page_run(tmp_path: Path) -> None:
    """Revised-only TOC line must keep ``w:tab`` (dot leaders) and separate page run inside ``w:ins``."""

    orig = _minimal_docx(
        tmp_path,
        '<w:p><w:r><w:t>Before</w:t></w:r></w:p>',
        "toc_ins_orig.docx",
    )
    rev = _minimal_docx(
        tmp_path,
        '<w:p><w:r><w:t>Before</w:t></w:r></w:p>' + TOC_ENTRY_XML,
        "toc_ins_rev.docx",
    )
    out = tmp_path / "toc_ins_out.docx"
    emit_docx_with_body_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        date_iso="2026-03-30T12:00:00Z",
    )
    root = load_word_document_xml_root(out)
    ps = root.findall("./w:body/w:p", NS)
    assert len(ps) == 2
    ins = ps[1].find("w:ins", NS)
    assert ins is not None
    assert ins.find(".//w:tab", NS) is not None
    assert _collect_t_text(ins) == "SECTION TITLE12"
    assert ins.find("w:pPr", NS) is None
    ppr = ps[1].find("w:pPr", NS)
    assert ppr is not None
    style = ppr.find("w:pStyle", NS)
    assert style is not None
    assert style.get(f"{{{WORD_NS}}}val") == "TOC1"


def test_emit_toc_style_delete_preserves_tab_inside_w_del(tmp_path: Path) -> None:
    """Original-only TOC line: ``w:del`` subtree should retain ``w:tab`` and ``w:delText`` for page."""

    orig = _minimal_docx(
        tmp_path,
        '<w:p><w:r><w:t>Before</w:t></w:r></w:p>' + TOC_ENTRY_XML,
        "toc_del_orig.docx",
    )
    rev = _minimal_docx(
        tmp_path,
        '<w:p><w:r><w:t>Before</w:t></w:r></w:p>',
        "toc_del_rev.docx",
    )
    out = tmp_path / "toc_del_out.docx"
    emit_docx_with_body_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        date_iso="2026-03-30T12:00:00Z",
    )
    root = load_word_document_xml_root(out)
    ps = root.findall("./w:body/w:p", NS)
    assert len(ps) == 2
    del_el = ps[1].find("w:del", NS)
    assert del_el is not None
    assert del_el.find(".//w:tab", NS) is not None
    assert _collect_del_text(del_el) == "SECTION TITLE12"


def test_reported_diversity_fixture_toc_revisions_line_preserves_tab(tmp_path: Path) -> None:
    """Reported case: ``TABLE OF REVISIONS`` TOC entry must not collapse to ``TABLE OF REVISIONS6`` layout."""

    base = Path(__file__).resolve().parent.parent / "sample-docs" / "email1docs"
    v1 = base / "diversity-plan-bladder-cancer-version1.docx"
    v2 = base / "diversity-plan-bladder-cancer-version2.docx"
    if not v1.is_file() or not v2.is_file():
        pytest.skip("sample diversity fixtures not present")

    out = tmp_path / "diversity_toc_out.docx"
    emit_docx_with_body_track_changes(
        v1,
        v2,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        date_iso="2026-03-30T12:00:00Z",
    )
    root = load_word_document_xml_root(out)
    toc_p = None
    for p in root.findall(".//w:body/w:p", NS):
        ppr = p.find("w:pPr", NS)
        if ppr is None:
            continue
        ps = ppr.find("w:pStyle", NS)
        val = (ps.get(f"{{{WORD_NS}}}val") if ps is not None else "") or ""
        if not val.upper().startswith("TOC"):
            continue
        texts = []
        for t in p.findall(".//w:t", NS):
            if t.text:
                texts.append(t.text)
        flat = "".join(texts)
        if flat.startswith("TABLE OF REVISIONS") and flat.endswith("6"):
            toc_p = p
            break
    assert toc_p is not None, "expected TOC1 line for TABLE OF REVISIONS with page 6"
    ins = toc_p.find("w:ins", NS)
    assert ins is not None, "revised-only TOC entry should be wrapped in w:ins"
    assert ins.find(".//w:tab", NS) is not None
    assert _collect_t_text(ins).startswith("TABLE OF REVISIONS")


TOC2_ENTRY_XML = """
<w:p>
  <w:pPr><w:pStyle w:val="TOC2"/></w:pPr>
  <w:r><w:t>1.1 Subsection</w:t></w:r>
  <w:r><w:tab/><w:t>3</w:t></w:r>
</w:p>
"""


def test_emit_toc2_style_insert_preserves_w_tab(tmp_path: Path) -> None:
    """Second synthetic: ``TOC2`` standalone insert also uses the layout-preserving path."""

    orig = _minimal_docx(
        tmp_path,
        '<w:p><w:r><w:t>Doc start</w:t></w:r></w:p>',
        "toc2_ins_orig.docx",
    )
    rev = _minimal_docx(
        tmp_path,
        '<w:p><w:r><w:t>Doc start</w:t></w:r></w:p>' + TOC2_ENTRY_XML,
        "toc2_ins_rev.docx",
    )
    out = tmp_path / "toc2_ins_out.docx"
    emit_docx_with_body_track_changes(
        orig,
        rev,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        date_iso="2026-03-30T12:00:00Z",
    )
    root = load_word_document_xml_root(out)
    ps = root.findall("./w:body/w:p", NS)
    assert len(ps) == 2
    ins = ps[1].find("w:ins", NS)
    assert ins is not None
    assert ins.find(".//w:tab", NS) is not None
    assert _collect_t_text(ins) == "1.1 Subsection3"

