"""
DOCX body ingest (MDC-003)

Converts `word/document.xml` from a `.docx` into the project Body IR shape.
This is intentionally minimal: it parses paragraph/runs text deterministically
and ignores formatting details for now.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union
import xml.etree.ElementTree as ET

from .contracts import BodyIR, BodyParagraph, BodyRun


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NAMESPACE}


@dataclass(frozen=True)
class DocumentXmlMissingError(Exception):
    """Raised when a `.docx` does not contain `word/document.xml`."""

    docx_path: Path
    missing_path: str = "word/document.xml"

    def __str__(self) -> str:
        return f"Missing {self.missing_path} in '{self.docx_path}'."


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


def parse_docx_body_ir(docx_path: Union[str, Path]) -> BodyIR:
    """
    Parse `word/document.xml` from a `.docx` and convert it into `BodyIR`.

    Determinism notes:
    - Paragraph order is the document XML order.
    - Run order is the run XML order.
    - Each run's text is the concatenation of all `w:t` text nodes under `w:r`.
    """

    root = load_word_document_xml_root(docx_path)

    paragraphs = root.findall(".//w:p", NS)
    blocks: list[BodyParagraph] = []

    for paragraph_index, p in enumerate(paragraphs, start=1):
        runs: list[BodyRun] = []

        for r in p.findall(".//w:r", NS):
            text_parts: list[str] = []
            for t in r.findall(".//w:t", NS):
                if t.text:
                    text_parts.append(t.text)
            run_text = "".join(text_parts)

            # Keep the IR minimal: include runs only when they have extractable text.
            if run_text:
                runs.append({"text": run_text})

        blocks.append(
            {
                "type": "paragraph",
                "id": f"p{paragraph_index}",
                "runs": runs,
            }
        )

    return {"version": 1, "blocks": blocks}

