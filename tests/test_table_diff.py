from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.contracts import validate_diff_ops
from engine.table_diff import diff_table_blocks


def _cell(text: str) -> dict:
    return {
        "paragraphs": [
            {"type": "paragraph", "id": "px", "runs": [{"text": text}]},
        ]
    }


def _table(rows: list[list[dict]]) -> dict:
    return {"type": "table", "id": "t1", "rows": rows}


def test_table_diff_same_shape_one_cell_replace_is_deterministic() -> None:
    original = _table([[_cell("old")]])
    revised = _table([[_cell("new")]])
    ops = diff_table_blocks(
        original,
        revised,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=0,
    )
    assert ops == [
        {
            "op": "replace",
            "path": "blocks/0/rows/0/cells/0/inline/0",
            "before": "old",
            "after": "new",
        }
    ]
    assert validate_diff_ops(ops) == []


def test_table_diff_shape_mismatch_emits_single_table_replace() -> None:
    original = _table([[_cell("a"), _cell("b")]])
    revised = _table([[_cell("a")]])
    ops = diff_table_blocks(
        original,
        revised,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=2,
    )
    assert ops == [
        {
            "op": "replace",
            "path": "blocks/2/table",
            "before": "a|b",
            "after": "a",
        }
    ]
    assert validate_diff_ops(ops) == []


def test_table_diff_two_by_two_row_major_cell_diffs() -> None:
    original = _table(
        [
            [_cell("a1"), _cell("b1")],
            [_cell("a2"), _cell("b2")],
        ]
    )
    revised = _table(
        [
            [_cell("a1"), _cell("b1")],
            [_cell("z2"), _cell("b2")],
        ]
    )
    ops = diff_table_blocks(
        original,
        revised,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=1,
    )
    # ``a2`` vs ``z2``: ``difflib`` emits a single replace for the first character.
    assert ops == [
        {
            "op": "replace",
            "path": "blocks/1/rows/1/cells/0/inline/0",
            "before": "a",
            "after": "z",
        }
    ]
    assert validate_diff_ops(ops) == []
