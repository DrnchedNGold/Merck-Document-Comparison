"""
DOCX body ingest (MDC-003)

Converts `word/document.xml` from a `.docx` into the project Body IR shape.
This is intentionally minimal: it parses block-level `w:p` and `w:tbl` in
`w:body` order, with paragraph/run text deterministically and formatting
details ignored for now.

``w:tab`` inside ``w:r`` is preserved as a U+0009 tab in the concatenated run text
so Table of Contents lines (tab to right-aligned page number with dot leaders from
``w:pPr`` tab stops) survive ingest and can be re-emitted as ``w:tab`` in Track Changes.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union
import xml.etree.ElementTree as ET

from .contracts import BodyIR, BodyParagraph, BodyRun, BodyTable, BodyTableCell


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NAMESPACE}


@dataclass(frozen=True)
class DocumentXmlMissingError(Exception):
    """Raised when a `.docx` does not contain `word/document.xml`."""

    docx_path: Path
    missing_path: str = "word/document.xml"

    def __str__(self) -> str:
        return f"Missing {self.missing_path} in '{self.docx_path}'."


def _local_name(tag: str) -> str:
    return tag.split("}", maxsplit=1)[-1] if "}" in tag else tag


def load_word_document_xml_root(docx_path: Union[str, Path]) -> ET.Element:
    """Load and parse `word/document.xml` from a `.docx` into an XML root.

    This helper is shared by preflight validation and body ingest so their
    XML parsing behavior stays consistent.
    """

    path = Path(docx_path)
    with zipfile.ZipFile(path, "r") as zf:
        try:
            document_xml = zf.read("word/document.xml")
        except KeyError as e:
            raise DocumentXmlMissingError(path) from e

    return ET.fromstring(document_xml)


def _run_text_from_w_r(r: ET.Element) -> str:
    """Ordered text + tab markers from one ``w:r`` (direct children only)."""

    parts: list[str] = []
    for child in r:
        ln = _local_name(child.tag)
        if ln == "t" and child.text:
            parts.append(child.text)
        elif ln == "tab":
            parts.append("\t")
    return "".join(parts)


def _parse_runs_from_paragraph(p: ET.Element) -> list[BodyRun]:
    runs: list[BodyRun] = []
    for r in p.findall(".//w:r", NS):
        run_text = _run_text_from_w_r(r)
        if run_text:
            runs.append({"text": run_text})
    return runs


def _parse_paragraph_element(p: ET.Element, paragraph_counter: list[int]) -> BodyParagraph:
    paragraph_counter[0] += 1
    pid = f"p{paragraph_counter[0]}"
    return {"type": "paragraph", "id": pid, "runs": _parse_runs_from_paragraph(p)}


def _parse_table_cell(tc: ET.Element, paragraph_counter: list[int]) -> BodyTableCell:
    """Parse one `w:tc`: direct `w:p` children (nested `w:tbl` skipped for now)."""

    paragraphs: list[BodyParagraph] = []
    for child in tc:
        if _local_name(child.tag) == "p":
            paragraphs.append(_parse_paragraph_element(child, paragraph_counter))
    return {"paragraphs": paragraphs}


def _parse_table_element(
    tbl: ET.Element, table_counter: list[int], paragraph_counter: list[int]
) -> BodyTable:
    table_counter[0] += 1
    tid = f"t{table_counter[0]}"
    rows: list[list[BodyTableCell]] = []
    for child in tbl:
        if _local_name(child.tag) != "tr":
            continue
        row: list[BodyTableCell] = []
        for tc in child:
            if _local_name(tc.tag) == "tc":
                row.append(_parse_table_cell(tc, paragraph_counter))
        rows.append(row)
    return {"type": "table", "id": tid, "rows": rows}


def parse_structural_blocks_from_element(container: ET.Element) -> BodyIR:
    """
    Parse top-level `w:p` / `w:tbl` sequences from a container element.

    Used for `w:body` in `word/document.xml` and for `w:hdr` / `w:ftr` roots in
    header/footer parts (SCRUM-49).
    """

    paragraph_counter = [0]
    table_counter = [0]
    blocks: list[BodyParagraph | BodyTable] = []

    for child in container:
        tag = _local_name(child.tag)
        if tag == "p":
            blocks.append(_parse_paragraph_element(child, paragraph_counter))
        elif tag == "tbl":
            blocks.append(_parse_table_element(child, table_counter, paragraph_counter))

    return {"version": 1, "blocks": blocks}


def parse_docx_body_ir(docx_path: Union[str, Path]) -> BodyIR:
    """
    Parse `word/document.xml` from a `.docx` and convert it into `BodyIR`.

    Determinism notes:
    - Block order follows direct children of `w:body` (`w:p`, `w:tbl`, ...).
    - Paragraph `id` values are assigned in document reading order (including
      paragraphs inside table cells).
    - Each run's text is the concatenation of `w:t` text and ``\\t`` for each direct
      child ``w:tab`` under `w:r`, in document order.
    """

    root = load_word_document_xml_root(docx_path)
    body = root.find("w:body", NS)
    if body is None:
        return {"version": 1, "blocks": []}

    return parse_structural_blocks_from_element(body)
