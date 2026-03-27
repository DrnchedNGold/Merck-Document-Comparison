"""Optional full-body orchestration: align paragraphs, then inline-diff matched pairs.

This is convenience wiring for CLI/desktop (not required for MDC-005–007 acceptance).
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import BodyIR, CompareConfig, DiffOp
from .inline_run_diff import inline_diff_single_paragraph
from .paragraph_alignment import align_paragraphs


@dataclass(frozen=True)
class MatchedParagraphDiff:
    """Inline diff result for one alignment row with both paragraph indices set."""

    original_paragraph_index: int
    revised_paragraph_index: int
    diff_ops: list[DiffOp]


def single_paragraph_body(body_ir: BodyIR, paragraph_index: int) -> BodyIR:
    """Return a BodyIR containing one block copied from the given index."""

    blocks = body_ir.get("blocks", [])
    if paragraph_index < 0 or paragraph_index >= len(blocks):
        raise IndexError(f"paragraph_index {paragraph_index} out of range.")
    block = blocks[paragraph_index]
    if block.get("type") != "paragraph":
        raise ValueError("Only paragraph blocks are supported.")
    return {"version": body_ir["version"], "blocks": [dict(block)]}


def matched_paragraph_inline_diffs(
    original: BodyIR, revised: BodyIR, config: CompareConfig
) -> list[MatchedParagraphDiff]:
    """
    Align bodies, then compute inline diffs for every row where both sides have a paragraph.

    Diff op paths use the **original** paragraph index (``blocks/{i}/inline/...``).
    """

    out: list[MatchedParagraphDiff] = []
    for row in align_paragraphs(original, revised, config):
        oi, ri = row.original_paragraph_index, row.revised_paragraph_index
        if oi is None or ri is None:
            continue
        ops = inline_diff_single_paragraph(
            single_paragraph_body(original, oi),
            single_paragraph_body(revised, ri),
            config,
            path_block_index=oi,
        )
        out.append(MatchedParagraphDiff(oi, ri, ops))
    return out
