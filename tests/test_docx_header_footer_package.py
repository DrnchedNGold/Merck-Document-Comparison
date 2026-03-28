"""SCRUM-49: header/footer discovery, package IR, compare wiring, part targeting."""

from __future__ import annotations

import zipfile
from pathlib import Path

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_compare import matched_document_package_inline_diffs
from engine.docx_package_parts import (
    DOCUMENT_PART_PATH,
    discover_header_footer_part_paths,
    discover_header_footer_part_paths_from_namelist,
)
from engine.document_package import parse_docx_document_package

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(
    tmp_path: Path,
    *,
    document_xml: str,
    extra_entries: dict[str, str] | None = None,
    filename: str = "hf.docx",
) -> Path:
    docx_path = tmp_path / filename
    entries = {"word/document.xml": document_xml}
    if extra_entries:
        entries.update(extra_entries)
    with zipfile.ZipFile(docx_path, "w") as zf:
        for name, xml in entries.items():
            zf.writestr(name, xml)
    return docx_path


def test_discover_header_footer_sorts_and_filters(tmp_path: Path) -> None:
    doc = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}"><w:body><w:p><w:r><w:t>x</w:t></w:r></w:p></w:body></w:document>
"""
    hdr2 = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{WORD_NS}"><w:p><w:r><w:t>H2</w:t></w:r></w:p></w:hdr>
"""
    hdr1 = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{WORD_NS}"><w:p><w:r><w:t>H1</w:t></w:r></w:p></w:hdr>
"""
    ftr = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{WORD_NS}"><w:p><w:r><w:t>F1</w:t></w:r></w:p></w:ftr>
"""
    noise = "<r/>"
    path = _docx(
        tmp_path,
        document_xml=doc,
        extra_entries={
            "word/header2.xml": hdr2,
            "word/header1.xml": hdr1,
            "word/footer1.xml": ftr,
            "word/settings.xml": noise,
            "word/_rels/document.xml.rels": noise,
        },
    )
    assert discover_header_footer_part_paths(path) == [
        "word/footer1.xml",
        "word/header1.xml",
        "word/header2.xml",
    ]


def test_discover_from_namelist_case_insensitive() -> None:
    names = ["Word/HEADER1.xml", "word/footer2.XML"]
    assert discover_header_footer_part_paths_from_namelist(names) == [
        "Word/HEADER1.xml",
        "word/footer2.XML",
    ]


def test_parse_document_package_loads_header_body_ir(tmp_path: Path) -> None:
    doc = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}"><w:body><w:p><w:r><w:t>Body</w:t></w:r></w:p></w:body></w:document>
"""
    hdr = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{WORD_NS}"><w:p><w:r><w:t>Hdr</w:t></w:r></w:p></w:hdr>
"""
    p = _docx(tmp_path, document_xml=doc, extra_entries={"word/header1.xml": hdr})
    pkg = parse_docx_document_package(p)
    assert pkg["version"] == 1
    assert pkg["document"]["blocks"][0]["runs"][0]["text"] == "Body"
    assert "word/header1.xml" in pkg["header_footer"]
    assert pkg["header_footer"]["word/header1.xml"]["blocks"][0]["runs"][0]["text"] == "Hdr"


def test_package_compare_sets_part_on_rows_for_document_and_header(tmp_path: Path) -> None:
    doc_same = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}"><w:body><w:p><w:r><w:t>Body</w:t></w:r></w:p></w:body></w:document>
"""
    hdr_same = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{WORD_NS}"><w:p><w:r><w:t>Hdr</w:t></w:r></w:p></w:hdr>
"""
    left = _docx(tmp_path, document_xml=doc_same, extra_entries={"word/header1.xml": hdr_same})
    right = _docx(
        tmp_path,
        document_xml=doc_same,
        extra_entries={"word/header1.xml": hdr_same},
        filename="right.docx",
    )
    rows = matched_document_package_inline_diffs(
        parse_docx_document_package(left),
        parse_docx_document_package(right),
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )

    doc_rows = [r for r in rows if r.part == DOCUMENT_PART_PATH]
    hdr_rows = [r for r in rows if r.part == "word/header1.xml"]

    assert len(doc_rows) >= 1
    assert len(hdr_rows) >= 1
    assert all(r.part == DOCUMENT_PART_PATH for r in doc_rows)
    assert all(r.part == "word/header1.xml" for r in hdr_rows)
    assert all(len(r.diff_ops) == 0 for r in rows)


def test_package_compare_sets_part_on_rows_for_document_and_footer(tmp_path: Path) -> None:
    doc_same = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}"><w:body><w:p><w:r><w:t>Body</w:t></w:r></w:p></w:body></w:document>
"""
    ftr_same = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{WORD_NS}"><w:p><w:r><w:t>Ftr</w:t></w:r></w:p></w:ftr>
"""
    left = _docx(tmp_path, document_xml=doc_same, extra_entries={"word/footer1.xml": ftr_same})
    right = _docx(
        tmp_path,
        document_xml=doc_same,
        extra_entries={"word/footer1.xml": ftr_same},
        filename="right_ftr.docx",
    )
    rows = matched_document_package_inline_diffs(
        parse_docx_document_package(left),
        parse_docx_document_package(right),
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    )

    doc_rows = [r for r in rows if r.part == DOCUMENT_PART_PATH]
    ftr_rows = [r for r in rows if r.part == "word/footer1.xml"]

    assert len(doc_rows) >= 1
    assert len(ftr_rows) >= 1
    assert all(r.part == DOCUMENT_PART_PATH for r in doc_rows)
    assert all(r.part == "word/footer1.xml" for r in ftr_rows)
    assert all(len(r.diff_ops) == 0 for r in rows)


def test_parse_document_package_loads_footer_body_ir(tmp_path: Path) -> None:
    doc = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}"><w:body><w:p><w:r><w:t>Body</w:t></w:r></w:p></w:body></w:document>
"""
    ftr = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{WORD_NS}"><w:p><w:r><w:t>Foot</w:t></w:r></w:p></w:ftr>
"""
    p = _docx(tmp_path, document_xml=doc, extra_entries={"word/footer1.xml": ftr})
    pkg = parse_docx_document_package(p)
    assert "word/footer1.xml" in pkg["header_footer"]
    assert pkg["header_footer"]["word/footer1.xml"]["blocks"][0]["runs"][0]["text"] == "Foot"
