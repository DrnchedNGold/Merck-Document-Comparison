"""OOXML package helpers: discover and parse header/footer parts (SCRUM-49)."""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

from .contracts import BodyIR
from .docx_body_ingest import _local_name, parse_structural_blocks_from_element

DOCUMENT_PART_PATH = "word/document.xml"

_HEADER_RE = re.compile(r"^word/header[0-9]+\.xml$", re.IGNORECASE)
_FOOTER_RE = re.compile(r"^word/footer[0-9]+\.xml$", re.IGNORECASE)


def _normalize_zip_name(name: str) -> str:
    return name.replace("\\", "/")


def discover_header_footer_part_paths_from_namelist(namelist: list[str]) -> list[str]:
    """Return sorted `word/header*.xml` and `word/footer*.xml` paths in the package."""

    found: list[str] = []
    for raw in namelist:
        n = _normalize_zip_name(raw)
        if _HEADER_RE.match(n) or _FOOTER_RE.match(n):
            found.append(n)
    return sorted(found)


def discover_header_footer_part_paths(docx_path: Union[str, Path]) -> list[str]:
    """List header/footer XML part paths for a `.docx` (zip) file."""

    path = Path(docx_path)
    with zipfile.ZipFile(path, "r") as zf:
        return discover_header_footer_part_paths_from_namelist(zf.namelist())


def parse_header_footer_zip_part(zf: zipfile.ZipFile, part_path: str) -> BodyIR:
    """
    Parse one `word/header*.xml` or `word/footer*.xml` entry into `BodyIR`.

    Root element must be `w:hdr` or `w:ftr` (OOXML). Structural children match
    body semantics (`w:p`, `w:tbl`, …).
    """

    raw = zf.read(part_path)
    root = ET.fromstring(raw)
    ln = _local_name(root.tag)
    if ln not in ("hdr", "ftr"):
        raise ValueError(
            f"Expected w:hdr or w:ftr root in '{part_path}', got local name {ln!r}."
        )
    return parse_structural_blocks_from_element(root)
