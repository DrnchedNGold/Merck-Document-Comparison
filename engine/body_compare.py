"""Optional full-body orchestration: align paragraphs, then inline-diff matched pairs.

This is convenience wiring for CLI/desktop (not required for MDC-005–007 acceptance).
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import BodyIR, CompareConfig, DiffOp
from .document_package import DocumentPackageIR
from .docx_package_parts import DOCUMENT_PART_PATH
from .inline_run_diff import inline_diff_single_paragraph
from .paragraph_alignment import align_paragraphs


@dataclass(frozen=True)
class MatchedParagraphDiff:
    """Inline diff result for one alignment row with both paragraph indices set."""

    original_paragraph_index: int
    revised_paragraph_index: int
    diff_ops: list[DiffOp]
    part: str | None = None


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
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
    *,
    part: str | None = None,
) -> list[MatchedParagraphDiff]:
    """
    Align bodies, then compute inline diffs for every row where both sides have a paragraph.

    Diff op paths use the **original** paragraph index (``blocks/{i}/inline/...``).
    When ``part`` is an OOXML zip path, each emitted ``DiffOp`` includes ``part``,
    and :attr:`MatchedParagraphDiff.part` is set for downstream emitters.
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
            diff_part=part,
        )
        out.append(MatchedParagraphDiff(oi, ri, ops, part=part))
    return out


def matched_document_package_inline_diffs(
    original: DocumentPackageIR,
    revised: DocumentPackageIR,
    config: CompareConfig,
) -> list[MatchedParagraphDiff]:
    """
    Run :func:`matched_paragraph_inline_diffs` on the main document and on each
    header/footer part in the union of both packages, stamping ``DiffOp["part"]``
    and :attr:`MatchedParagraphDiff.part` with the target OOXML path.
    """

    merged: list[MatchedParagraphDiff] = []
    merged.extend(
        matched_paragraph_inline_diffs(
            original["document"],
            revised["document"],
            config,
            part=DOCUMENT_PART_PATH,
        )
    )
    all_hf = sorted(
        set(original["header_footer"].keys()) | set(revised["header_footer"].keys())
    )
    empty: BodyIR = {"version": 1, "blocks": []}
    for hf_part in all_hf:
        o_ir = original["header_footer"].get(hf_part, empty)
        r_ir = revised["header_footer"].get(hf_part, empty)
        merged.extend(
            matched_paragraph_inline_diffs(o_ir, r_ir, config, part=hf_part)
        )
    return merged
