"""
Inline diff for runs (MDC-007 / SCRUM-36)

Computes ordered `DiffOp` values for a single aligned paragraph by diffing the
concatenated normalized run text. Callers align paragraphs first, then pass the
matching original/revised paragraph blocks.
"""

from __future__ import annotations

import difflib

from .compare_keys import _normalize_text
from .contracts import BodyIR, BodyParagraph, CompareConfig, DiffOp


def _concat_paragraph_text(paragraph: BodyParagraph, config: CompareConfig) -> str:
    return "".join(
        _normalize_text(str(run.get("text", "")), config) for run in paragraph.get("runs", [])
    )


def _single_paragraph(body_ir: BodyIR) -> BodyParagraph:
    blocks = body_ir.get("blocks", [])
    if len(blocks) != 1:
        raise ValueError("Expected exactly one paragraph block in BodyIR.")
    block = blocks[0]
    if block.get("type") != "paragraph":
        raise ValueError("Expected block type 'paragraph'.")
    return block


def _with_part(op: DiffOp, diff_part: str | None) -> DiffOp:
    if diff_part is None:
        return op
    return {**op, "part": diff_part}


def inline_diff_single_paragraph(
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
    *,
    path_block_index: int = 0,
    path_prefix: str | None = None,
    diff_part: str | None = None,
) -> list[DiffOp]:
    """
    Produce deterministic, ordered diff ops for one aligned paragraph pair.

    Text is the concatenation of per-run text after the same normalization used
    for compare keys.     Paths are stable render targets: ``blocks/{path_block_index}/inline/{n}``,
    or ``{path_prefix}/inline/{n}`` when ``path_prefix`` is set (table cells).
    """

    orig_para = _single_paragraph(original)
    rev_para = _single_paragraph(revised)

    orig_text = _concat_paragraph_text(orig_para, config)
    rev_text = _concat_paragraph_text(rev_para, config)

    matcher = difflib.SequenceMatcher(None, orig_text, rev_text)
    ops: list[DiffOp] = []
    op_index = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if path_prefix is not None:
            path = f"{path_prefix}/inline/{op_index}"
        else:
            path = f"blocks/{path_block_index}/inline/{op_index}"
        op_index += 1

        if tag == "delete":
            segment = orig_text[i1:i2]
            ops.append(
                _with_part(
                    {"op": "delete", "path": path, "before": segment, "after": None},
                    diff_part,
                )
            )
        elif tag == "insert":
            segment = rev_text[j1:j2]
            ops.append(
                _with_part(
                    {"op": "insert", "path": path, "before": None, "after": segment},
                    diff_part,
                )
            )
        elif tag == "replace":
            ops.append(
                _with_part(
                    {
                        "op": "replace",
                        "path": path,
                        "before": orig_text[i1:i2],
                        "after": rev_text[j1:j2],
                    },
                    diff_part,
                )
            )

    return ops
