"""Stable data contracts for engine IR, diff ops, and compare config.

This module intentionally defines only shape/contracts for MDC-002.
It does not implement DOCX parsing or diff generation.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

BodyBlockType = Literal["paragraph", "table"]
DiffOpKind = Literal["insert", "delete", "replace"]
BodyIRVersion = Literal[1]


class BodyRun(TypedDict, total=False):
    """A single text run inside a paragraph."""

    text: str
    bold: bool
    italic: bool
    underline: bool


class BodyParagraph(TypedDict):
    """Paragraph block in body IR."""

    type: Literal["paragraph"]
    id: str
    runs: list[BodyRun]


class BodyTableCell(TypedDict):
    """One table cell: ordered paragraphs (common Word `w:tc` → `w:p` sequences)."""

    paragraphs: list[BodyParagraph]


class BodyTable(TypedDict):
    """Table block: rows of cells (common `w:tbl` → `w:tr` → `w:tc`)."""

    type: Literal["table"]
    id: str
    rows: list[list[BodyTableCell]]


class BodyIR(TypedDict):
    """Top-level body IR container."""

    version: BodyIRVersion
    blocks: list[BodyParagraph | BodyTable]


class DiffOp(TypedDict):
    """Minimal diff operation shape consumed by later renderer/output steps."""

    op: DiffOpKind
    path: str
    before: str | None
    after: str | None
    part: NotRequired[str]


class CompareConfig(TypedDict):
    """Word-like compare settings profile (stub for now)."""

    ignore_case: bool
    ignore_whitespace: bool
    ignore_formatting: bool
    detect_moves: bool


DEFAULT_WORD_LIKE_COMPARE_CONFIG: CompareConfig = {
    "ignore_case": False,
    "ignore_whitespace": False,
    "ignore_formatting": True,
    "detect_moves": False,
}

ALLOWED_DIFF_OPS: tuple[DiffOpKind, ...] = ("insert", "delete", "replace")


def _validate_paragraph_block(block_index: str, block: dict) -> list[str]:
    errors: list[str] = []
    if block.get("type") != "paragraph":
        errors.append(f"{block_index} must have type='paragraph'.")
    if not isinstance(block.get("id"), str) or not block["id"]:
        errors.append(f"{block_index} must have a non-empty string id.")
    runs = block.get("runs")
    if not isinstance(runs, list):
        return errors + [f"{block_index} runs must be a list."]
    for run_index, run in enumerate(runs):
        if not isinstance(run.get("text"), str):
            errors.append(
                f"{block_index} run {run_index} must include string text."
            )
    return errors


def _validate_table_block(block_index: int, block: dict) -> list[str]:
    errors: list[str] = []
    if block.get("type") != "table":
        errors.append(f"Block {block_index} must have type='table'.")
        return errors
    if not isinstance(block.get("id"), str) or not block["id"]:
        errors.append(f"Block {block_index} must have a non-empty string id.")
    rows = block.get("rows")
    if not isinstance(rows, list):
        return errors + [f"Block {block_index} rows must be a list."]
    for r, row in enumerate(rows):
        if not isinstance(row, list):
            errors.append(f"Block {block_index} row {r} must be a list.")
            continue
        for c, cell in enumerate(row):
            if not isinstance(cell, dict):
                errors.append(
                    f"Block {block_index} row {r} cell {c} must be an object."
                )
                continue
            paras = cell.get("paragraphs")
            if not isinstance(paras, list):
                errors.append(
                    f"Block {block_index} row {r} cell {c} paragraphs must be a list."
                )
                continue
            for pi, para in enumerate(paras):
                if not isinstance(para, dict):
                    errors.append(
                        f"Block {block_index} row {r} cell {c} paragraph {pi} must be an object."
                    )
                    continue
                errors.extend(
                    _validate_paragraph_block(
                        f"Block {block_index} row {r} cell {c} paragraph {pi}",
                        para,
                    )
                )
    return errors


def validate_body_ir(body_ir: BodyIR) -> list[str]:
    """Return contract violations for a body IR payload."""
    errors: list[str] = []
    if body_ir.get("version") != 1:
        errors.append("Body IR version must be 1.")

    blocks = body_ir.get("blocks")
    if not isinstance(blocks, list):
        return errors + ["Body IR blocks must be a list."]

    for block_index, block in enumerate(blocks):
        if not isinstance(block, dict):
            errors.append(f"Block {block_index} must be an object.")
            continue
        btype = block.get("type")
        if btype == "paragraph":
            errors.extend(_validate_paragraph_block(f"Block {block_index}", block))
        elif btype == "table":
            errors.extend(_validate_table_block(block_index, block))
        else:
            errors.append(
                f"Block {block_index} must have type 'paragraph' or 'table'."
            )
    return errors


def validate_diff_ops(diff_ops: list[DiffOp]) -> list[str]:
    """Return contract violations for a diff-op list."""
    errors: list[str] = []
    for index, op in enumerate(diff_ops):
        if op.get("op") not in ALLOWED_DIFF_OPS:
            errors.append(f"Diff op {index} has unsupported op '{op.get('op')}'.")
        if not isinstance(op.get("path"), str) or not op["path"]:
            errors.append(f"Diff op {index} path must be a non-empty string.")
        if not isinstance(op.get("before"), (str, type(None))):
            errors.append(f"Diff op {index} before must be string or null.")
        if not isinstance(op.get("after"), (str, type(None))):
            errors.append(f"Diff op {index} after must be string or null.")
        if "part" in op and not isinstance(op["part"], str):
            errors.append(f"Diff op {index} part must be a string when present.")
    return errors


def validate_compare_config(config: CompareConfig) -> list[str]:
    """Return contract violations for compare config."""
    errors: list[str] = []
    required = (
        "ignore_case",
        "ignore_whitespace",
        "ignore_formatting",
        "detect_moves",
    )
    for field in required:
        if field not in config:
            errors.append(f"Compare config missing required field '{field}'.")
            continue
        if not isinstance(config[field], bool):
            errors.append(f"Compare config field '{field}' must be bool.")
    return errors
