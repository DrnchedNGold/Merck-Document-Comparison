"""Load document body plus header/footer parts into a single package IR (SCRUM-49)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Literal, TypedDict, Union

from .contracts import BodyIR
from .docx_body_ingest import parse_docx_body_ir
from .docx_package_parts import (
    discover_header_footer_part_paths_from_namelist,
    parse_header_footer_zip_part,
)


class DocumentPackageIR(TypedDict):
    """Parallel structures for `word/document.xml` and header/footer parts."""

    version: Literal[1]
    document: BodyIR
    header_footer: dict[str, BodyIR]


def parse_docx_document_package(docx_path: Union[str, Path]) -> DocumentPackageIR:
    """
    Ingest `word/document.xml` and every `word/header*.xml` / `word/footer*.xml`
    part into Body-shaped IR payloads keyed by OOXML zip path.
    """

    path = Path(docx_path)
    document = parse_docx_body_ir(path)
    header_footer: dict[str, BodyIR] = {}
    with zipfile.ZipFile(path, "r") as zf:
        for part in discover_header_footer_part_paths_from_namelist(zf.namelist()):
            header_footer[part] = parse_header_footer_zip_part(zf, part)

    return {
        "version": 1,
        "document": document,
        "header_footer": header_footer,
    }
