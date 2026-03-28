"""
Normalization + compare keys (MDC-005)

Generates deterministic compare keys over BodyIR so later alignment/diff steps
can match content while optionally ignoring formatting noise.
"""

from __future__ import annotations

from typing import Iterable, TypedDict

from .contracts import BodyIR, CompareConfig


class CompareKey(TypedDict):
    paragraph_index: int
    run_index: int
    key: str


def _normalize_whitespace(text: str) -> str:
    # Collapse all whitespace sequences to single spaces.
    return " ".join(text.split())


def _normalize_text(text: str, config: CompareConfig) -> str:
    if config.get("ignore_case"):
        text = text.lower()
    if config.get("ignore_whitespace"):
        text = _normalize_whitespace(text)
    return text


def _format_signature(run: dict, config: CompareConfig) -> str:
    """
    Return a stable formatting signature for a run.

    When ignore_formatting=True, this must return an empty string so compare keys
    are unaffected by formatting-only edits.
    """

    if config.get("ignore_formatting"):
        return ""

    # Missing fields default to False/None in our synthetic IR.
    bold = bool(run.get("bold", False))
    italic = bool(run.get("italic", False))
    underline = bool(run.get("underline", False))
    return f"b{int(bold)}i{int(italic)}u{int(underline)}"


def _iter_runs(body_ir: BodyIR) -> Iterable[tuple[int, int, dict]]:
    """Yield ``(paragraph_index, run_index, run)`` with paragraph_index global in reading order."""

    paragraph_index = 0
    for block in body_ir.get("blocks", []):
        btype = block.get("type")
        if btype == "paragraph":
            for run_index, run in enumerate(block.get("runs", [])):
                yield paragraph_index, run_index, run
            paragraph_index += 1
        elif btype == "table":
            for row in block.get("rows", []):
                for cell in row:
                    for para in cell.get("paragraphs", []):
                        for run_index, run in enumerate(para.get("runs", [])):
                            yield paragraph_index, run_index, run
                        paragraph_index += 1


def generate_compare_keys(body_ir: BodyIR, config: CompareConfig) -> list[CompareKey]:
    """
    Generate deterministic compare keys for every run in BodyIR.

    Key includes stable indices so alignment is deterministic even when identical
    text appears multiple times within a paragraph.
    """

    keys: list[CompareKey] = []
    for paragraph_index, run_index, run in _iter_runs(body_ir):
        text = str(run.get("text", ""))
        normalized_text = _normalize_text(text, config)
        fmt_sig = _format_signature(run, config)
        key = f"p{paragraph_index}/r{run_index}:{normalized_text}:{fmt_sig}"
        keys.append(
            {
                "paragraph_index": paragraph_index,
                "run_index": run_index,
                "key": key,
            }
        )
    return keys


def align_runs_by_compare_keys(
    original: BodyIR, revised: BodyIR, config: CompareConfig
) -> list[tuple[int, int]]:
    """
    Align runs by compare keys.

    For now, we assume stable run order (determinism requirement). Alignment
    pairs each original run index with the corresponding revised run index
    when compare keys match exactly.
    """

    original_keys = generate_compare_keys(original, config)
    revised_keys = generate_compare_keys(revised, config)

    if len(original_keys) != len(revised_keys):
        # Keep behavior explicit; callers can raise richer errors later.
        return []

    alignment: list[tuple[int, int]] = []
    for orig_i, orig in enumerate(original_keys):
        rev = revised_keys[orig_i]
        if orig["key"] != rev["key"]:
            return []
        alignment.append((orig["run_index"], rev["run_index"]))
    return alignment

