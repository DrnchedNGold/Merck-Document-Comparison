"""Table block diff (MDC-008)

Deterministic diff for ``BodyTable`` blocks: same dimensions use per-cell inline
diff (via :func:`inline_diff_single_paragraph`); shape mismatches emit a single
replace at ``blocks/{block_index}/table``.
"""

from __future__ import annotations

from .contracts import BodyIR, BodyParagraph, BodyTable, BodyTableCell, CompareConfig, DiffOp
from .inline_run_diff import inline_diff_single_paragraph


def _cell_concat_paragraph(cell: BodyTableCell) -> BodyParagraph:
    """Merge cell paragraphs into one paragraph (newline between paragraphs)."""

    parts: list[str] = []
    for para in cell.get("paragraphs", []):
        text = "".join(str(r.get("text", "")) for r in para.get("runs", []))
        parts.append(text)
    merged = "\n".join(parts)
    return {"type": "paragraph", "id": "cell-merged", "runs": [{"text": merged}]}


def _table_shape(table: BodyTable) -> tuple[int, list[int]]:
    rows = table.get("rows", [])
    nrows = len(rows)
    widths = [len(row) for row in rows]
    return nrows, widths


def _serialize_table_texts(table: BodyTable) -> str:
    """Stable serialization for whole-table replace when shapes differ."""

    lines: list[str] = []
    for row in table.get("rows", []):
        cells: list[str] = []
        for cell in row:
            parts: list[str] = []
            for para in cell.get("paragraphs", []):
                parts.append("".join(str(r.get("text", "")) for r in para.get("runs", [])))
            cells.append("\n".join(parts))
        lines.append("|".join(cells))
    return "\n".join(lines)


def diff_table_blocks(
    original: BodyTable,
    revised: BodyTable,
    config: CompareConfig,
    *,
    block_index: int,
) -> list[DiffOp]:
    """
    Produce ordered diff ops for two aligned table blocks.

    - If row/column counts differ between tables, return one ``replace`` whose
      ``before``/``after`` are stable serialized cell texts.
    - Otherwise, diff each cell in row-major order using the same normalization
      as inline paragraph diff, with paths
      ``blocks/{block_index}/rows/{r}/cells/{c}/inline/{n}``.
    """

    o_shape = _table_shape(original)
    r_shape = _table_shape(revised)
    if o_shape != r_shape:
        return [
            {
                "op": "replace",
                "path": f"blocks/{block_index}/table",
                "before": _serialize_table_texts(original),
                "after": _serialize_table_texts(revised),
            }
        ]

    ops: list[DiffOp] = []
    for r, row_o in enumerate(original["rows"]):
        row_r = revised["rows"][r]
        for c, cell_o in enumerate(row_o):
            cell_r = row_r[c]
            prefix = f"blocks/{block_index}/rows/{r}/cells/{c}"
            orig_ir: BodyIR = {
                "version": 1,
                "blocks": [_cell_concat_paragraph(cell_o)],
            }
            rev_ir: BodyIR = {
                "version": 1,
                "blocks": [_cell_concat_paragraph(cell_r)],
            }
            ops.extend(
                inline_diff_single_paragraph(
                    orig_ir,
                    rev_ir,
                    config,
                    path_block_index=0,
                    path_prefix=prefix,
                )
            )
    return ops
