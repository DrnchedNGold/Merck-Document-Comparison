"""Table block diff (MDC-008)

Deterministic diff for ``BodyTable`` blocks using row/cell granularity.
For each row/column index present on either side, cell text is compared via
:func:`inline_diff_single_paragraph` so row/cell additions and removals become
cell-level insert/delete ops instead of whole-table replacement.
"""

from __future__ import annotations

import difflib
import re

from .compare_keys import _normalize_text
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


def _empty_cell() -> BodyTableCell:
    """Synthetic empty cell used for row/column additions/removals."""

    return {"paragraphs": []}


def _cell_text(cell: BodyTableCell) -> str:
    parts: list[str] = []
    for para in cell.get("paragraphs", []):
        parts.append("".join(str(r.get("text", "")) for r in para.get("runs", [])))
    return "\n".join(parts)


def _row_signature(row: list[BodyTableCell], config: CompareConfig) -> str:
    return "||".join(_normalize_text(_cell_text(cell), config) for cell in row)


def _alignment_from_signatures(
    left_sigs: list[str], right_sigs: list[str]
) -> list[tuple[int | None, int | None]]:
    """
    LCS-style alignment between two signature lists.

    Emits pairs ``(li, ri)`` for matched elements, plus ``(li, None)`` deletes and
    ``(None, ri)`` inserts.
    """

    sm = difflib.SequenceMatcher(None, left_sigs, right_sigs, autojunk=False)
    out: list[tuple[int | None, int | None]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out.append((i1 + k, j1 + k))
        elif tag == "replace":
            shared = min(i2 - i1, j2 - j1)
            for k in range(shared):
                out.append((i1 + k, j1 + k))
            for k in range(shared, i2 - i1):
                out.append((i1 + k, None))
            for k in range(shared, j2 - j1):
                out.append((None, j1 + k))
        elif tag == "delete":
            for i in range(i1, i2):
                out.append((i, None))
        elif tag == "insert":
            for j in range(j1, j2):
                out.append((None, j))
    return out


def _row_primary_key(row: list[BodyTableCell], config: CompareConfig) -> str:
    """Normalized first-cell text as a lightweight row identity key."""

    if not row:
        return ""
    return _normalize_text(_cell_text(row[0]).strip(), config)


def _is_abbrev_like_key(key: str) -> bool:
    """
    Heuristic for glossary-style row identifiers (e.g. ``HLA``, ``ASCO-ACCC``).

    Used to avoid pairing different abbreviation rows as in-place replacements.
    """

    if not key or len(key) > 24 or " " in key:
        return False
    if key != key.upper():
        return False
    return bool(re.search(r"[A-Z]", key))


def _align_table_rows(
    rows_o: list[list[BodyTableCell]],
    rows_r: list[list[BodyTableCell]],
    config: CompareConfig,
) -> list[tuple[int | None, int | None]]:
    sig_o = [_row_signature(row, config) for row in rows_o]
    sig_r = [_row_signature(row, config) for row in rows_r]
    key_o = [_row_primary_key(row, config) for row in rows_o]
    key_r = [_row_primary_key(row, config) for row in rows_r]

    sm = difflib.SequenceMatcher(None, sig_o, sig_r, autojunk=False)
    out: list[tuple[int | None, int | None]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out.append((i1 + k, j1 + k))
        elif tag == "replace":
            unmatched_r = set(range(j1, j2))
            unmatched_o: list[int] = []
            # Prefer pairing rows with the same primary key (first cell text).
            for oi in range(i1, i2):
                ko = key_o[oi]
                if not ko:
                    unmatched_o.append(oi)
                    continue
                match_ri = next(
                    (ri for ri in range(j1, j2) if ri in unmatched_r and key_r[ri] == ko),
                    None,
                )
                if match_ri is not None:
                    out.append((oi, match_ri))
                    unmatched_r.remove(match_ri)
                else:
                    unmatched_o.append(oi)

            # Pair remaining rows by position unless both keys look like glossary
            # IDs and differ (that case should be delete+insert, not replace).
            rem_o = sorted(unmatched_o)
            rem_r = sorted(unmatched_r)
            shared = min(len(rem_o), len(rem_r))
            for k in range(shared):
                oi = rem_o[k]
                ri = rem_r[k]
                ko = key_o[oi]
                kr = key_r[ri]
                if _is_abbrev_like_key(ko) and _is_abbrev_like_key(kr) and ko != kr:
                    out.append((oi, None))
                else:
                    out.append((oi, ri))
                    unmatched_r.remove(ri)

            # Unpaired original rows are deletes.
            for oi in rem_o[shared:]:
                out.append((oi, None))

            # Any remaining revised rows are inserts.
            for ri in range(j1, j2):
                if ri in unmatched_r:
                    out.append((None, ri))
        elif tag == "delete":
            for i in range(i1, i2):
                out.append((i, None))
        elif tag == "insert":
            for j in range(j1, j2):
                out.append((None, j))
    return out


def _align_row_cells(
    row_o: list[BodyTableCell],
    row_r: list[BodyTableCell],
    config: CompareConfig,
) -> list[tuple[int | None, int | None]]:
    sig_o = [_normalize_text(_cell_text(cell), config) for cell in row_o]
    sig_r = [_normalize_text(_cell_text(cell), config) for cell in row_r]
    return _alignment_from_signatures(sig_o, sig_r)


def diff_table_blocks(
    original: BodyTable,
    revised: BodyTable,
    config: CompareConfig,
    *,
    block_index: int,
) -> list[DiffOp]:
    """
    Produce ordered diff ops for two aligned table blocks.

    Diff each logical cell in row-major order using the same normalization as
    inline paragraph diff. For shape mismatches (row/column add/remove), cells
    missing on one side are treated as empty so ops stay at
    ``blocks/{block_index}/rows/{r}/cells/{c}/inline/{n}`` granularity.
    """

    ops: list[DiffOp] = []
    rows_o = original.get("rows", [])
    rows_r = revised.get("rows", [])
    for oi, ri in _align_table_rows(rows_o, rows_r, config):
        row_o = rows_o[oi] if oi is not None else []
        row_r = rows_r[ri] if ri is not None else []
        row_idx = ri if ri is not None else (oi if oi is not None else 0)
        for oc, rc in _align_row_cells(row_o, row_r, config):
            cell_o = row_o[oc] if oc is not None else _empty_cell()
            cell_r = row_r[rc] if rc is not None else _empty_cell()
            cell_idx = rc if rc is not None else (oc if oc is not None else 0)
            prefix = f"blocks/{block_index}/rows/{row_idx}/cells/{cell_idx}"
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
