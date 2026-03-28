"""Full-body orchestration: align top-level blocks, then diff matched pairs.

Paragraphs use :func:`inline_diff_single_paragraph`. Tables use
:func:`table_diff.diff_table_blocks`; when table signatures differ (edited cell
text) LCS may not pair same-index tables, so same-index table pairs are also
diffed when not already matched (see :func:`matched_paragraph_inline_diffs`).
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import BodyIR, CompareConfig, DiffOp
from .document_package import DocumentPackageIR
from .docx_package_parts import DOCUMENT_PART_PATH
from .inline_run_diff import inline_diff_single_paragraph
from .paragraph_alignment import align_paragraphs
from .table_diff import diff_table_blocks


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


def _stamp_part(ops: list[DiffOp], part: str | None) -> list[DiffOp]:
    if part is None:
        return ops
    return [{**op, "part": part} for op in ops]


def matched_paragraph_inline_diffs(
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
    *,
    part: str | None = None,
) -> list[MatchedParagraphDiff]:
    """
    Align top-level blocks, then compute diffs for each matched pair.

    - For aligned **paragraph** blocks: inline run diff; paths
      ``blocks/{original_index}/inline/...``.
    - For aligned **table** blocks: :func:`table_diff.diff_table_blocks` with
      ``block_index`` = original block index; paths include
      ``blocks/{i}/rows/...`` or ``blocks/{i}/table`` on shape mismatch.

    When ``part`` is an OOXML zip path, each ``DiffOp`` includes ``part``, and
    :attr:`MatchedParagraphDiff.part` is set for downstream emitters.
    """

    out: list[MatchedParagraphDiff] = []
    oblocks = original.get("blocks", [])
    rblocks = revised.get("blocks", [])
    matched_pairs: set[tuple[int, int]] = set()

    for row in align_paragraphs(original, revised, config):
        oi, ri = row.original_paragraph_index, row.revised_paragraph_index
        if oi is None or ri is None:
            continue
        matched_pairs.add((oi, ri))
        ob = oblocks[oi]
        rb = rblocks[ri]
        otype, rtype = ob.get("type"), rb.get("type")
        if otype == "paragraph" and rtype == "paragraph":
            ops = inline_diff_single_paragraph(
                single_paragraph_body(original, oi),
                single_paragraph_body(revised, ri),
                config,
                path_block_index=oi,
                diff_part=part,
            )
            out.append(MatchedParagraphDiff(oi, ri, ops, part=part))
        elif otype == "table" and rtype == "table":
            ops = _stamp_part(
                diff_table_blocks(
                    ob,  # type: ignore[arg-type]
                    rb,  # type: ignore[arg-type]
                    config,
                    block_index=oi,
                ),
                part,
            )
            out.append(MatchedParagraphDiff(oi, ri, ops, part=part))

    # When cell text (or other content) differs, table block signatures differ and
    # LCS may emit (i, None)/(None, j) instead of (i, j). Pair same-index tables
    # for cell-level diff when that index was not already matched both sides.
    n = min(len(oblocks), len(rblocks))
    for i in range(n):
        if (i, i) in matched_pairs:
            continue
        ob, rb = oblocks[i], rblocks[i]
        if ob.get("type") == "table" and rb.get("type") == "table":
            ops = _stamp_part(
                diff_table_blocks(
                    ob,  # type: ignore[arg-type]
                    rb,  # type: ignore[arg-type]
                    config,
                    block_index=i,
                ),
                part,
            )
            out.append(MatchedParagraphDiff(i, i, ops, part=part))

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
