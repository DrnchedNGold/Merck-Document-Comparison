"""Preflight validation before engine diffing (MDC-004).

Rules implemented here:
- Reject non-`.docx` inputs.
- Detect pre-existing tracked changes (w:ins / w:del) in `word/document.xml`.
- Detect pre-existing comments (comment markers in `word/document.xml` and/or
  `word/comments.xml` presence).

This module intentionally does not implement DOCX parsing beyond loading the
Word document XML root using the existing body ingest helper.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Union
import xml.etree.ElementTree as ET

from .docx_body_ingest import DocumentXmlMissingError, WORD_NAMESPACE, load_word_document_xml_root

NS = {"w": WORD_NAMESPACE}


class PreflightValidationError(Exception):
    """Base error for all preflight validation failures."""


class InvalidDocxFileTypeError(PreflightValidationError):
    """Raised when input is not a `.docx` file."""

    def __init__(self, docx_path: Path, actual_suffix: str):
        super().__init__(
            f"Invalid file type for '{docx_path}': expected '.docx' but got '{actual_suffix}'."
        )


class InvalidDocxZipFileError(PreflightValidationError):
    """Raised when a `.docx` path does not contain a valid zip archive."""

    def __init__(self, docx_path: Path):
        super().__init__(f"Invalid DOCX zip file for '{docx_path}': file is not a valid zip.")


class TrackedChangesDetectedError(PreflightValidationError):
    """Raised when pre-existing tracked changes are found."""

    def __init__(self, docx_path: Path, ins_count: int, del_count: int):
        super().__init__(
            f"Tracked changes detected in '{docx_path}': w:ins={ins_count}, w:del={del_count}."
        )


class CommentsDetectedError(PreflightValidationError):
    """Raised when pre-existing comments are found."""

    def __init__(
        self,
        docx_path: Path,
        comment_range_start_count: int,
        comment_range_end_count: int,
        comment_reference_count: int,
        comments_xml_present: bool,
    ):
        comments_xml_str = "present" if comments_xml_present else "missing"
        super().__init__(
            "Comments detected in "
            f"'{docx_path}': "
            f"w:commentRangeStart={comment_range_start_count}, "
            f"w:commentRangeEnd={comment_range_end_count}, "
            f"w:commentReference={comment_reference_count}, "
            f"word/comments.xml={comments_xml_str}."
        )


def _docx_contains_zip_entry(docx_path: Path, entry_name: str) -> bool:
    with zipfile.ZipFile(docx_path, "r") as zf:
        # `namelist()` is deterministic; no iteration order surprises.
        return entry_name in set(zf.namelist())


def _count_xml_elements(root: ET.Element, xpath: str) -> int:
    # ElementTree returns an empty list if the XPath matches nothing.
    return len(root.findall(xpath, NS))


def validate_docx_for_preflight(docx_path: Union[str, Path]) -> None:
    """Validate a single `.docx` for preflight engine readiness."""

    path = Path(docx_path)
    actual_suffix = path.suffix.lower()

    if actual_suffix != ".docx":
        raise InvalidDocxFileTypeError(path, actual_suffix)

    if not zipfile.is_zipfile(path):
        raise InvalidDocxZipFileError(path)

    # Reuse the existing body ingest XML loading behavior so we get a consistent
    # `word/document.xml missing` error and parsing mechanics.
    root = load_word_document_xml_root(path)

    ins_count = _count_xml_elements(root, ".//w:ins")
    del_count = _count_xml_elements(root, ".//w:del")
    if ins_count > 0 or del_count > 0:
        raise TrackedChangesDetectedError(path, ins_count=ins_count, del_count=del_count)

    # Comments can be represented either by markers in document.xml and/or a
    # standalone comments part (`word/comments.xml`).
    comment_range_start_count = _count_xml_elements(root, ".//w:commentRangeStart")
    comment_range_end_count = _count_xml_elements(root, ".//w:commentRangeEnd")
    comment_reference_count = _count_xml_elements(root, ".//w:commentReference")

    comments_xml_present = _docx_contains_zip_entry(path, "word/comments.xml")
    if (
        comment_range_start_count > 0
        or comment_range_end_count > 0
        or comment_reference_count > 0
        or comments_xml_present
    ):
        raise CommentsDetectedError(
            path,
            comment_range_start_count=comment_range_start_count,
            comment_range_end_count=comment_range_end_count,
            comment_reference_count=comment_reference_count,
            comments_xml_present=comments_xml_present,
        )

