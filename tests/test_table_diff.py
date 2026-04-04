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


def test_table_diff_shape_mismatch_emits_cell_level_delete() -> None:
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
            "op": "delete",
            "path": "blocks/2/rows/0/cells/1/inline/0",
            "before": "b",
            "after": None,
        }
    ]
    assert validate_diff_ops(ops) == []


def test_table_diff_row_addition_emits_cell_level_insert() -> None:
    original = _table([[_cell("abbr"), _cell("definition")]])
    revised = _table(
        [
            [_cell("abbr"), _cell("definition")],
            [_cell("NEW"), _cell("new meaning")],
        ]
    )
    ops = diff_table_blocks(
        original,
        revised,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=0,
    )
    assert any(op["op"] == "insert" for op in ops)
    assert any(op["path"].startswith("blocks/0/rows/1/cells/0/inline/") for op in ops)
    assert any(op["path"].startswith("blocks/0/rows/1/cells/1/inline/") for op in ops)
    assert validate_diff_ops(ops) == []


def test_table_diff_middle_row_insert_keeps_following_row_unchanged() -> None:
    original = _table(
        [
            [_cell("A"), _cell("Alpha")],
            [_cell("C"), _cell("Charlie")],
        ]
    )
    revised = _table(
        [
            [_cell("A"), _cell("Alpha")],
            [_cell("B"), _cell("Bravo")],
            [_cell("C"), _cell("Charlie")],
        ]
    )
    ops = diff_table_blocks(
        original,
        revised,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=0,
    )
    # New middle row is inserted; trailing row "C/Charlie" should not be replaced.
    assert any(op["op"] == "insert" and "/rows/1/" in op["path"] for op in ops)
    assert not any(
        op["op"] == "replace"
        and (op.get("before") == "C" or op.get("before") == "Charlie")
        for op in ops
    )
    assert validate_diff_ops(ops) == []


def test_table_diff_row_key_change_prefers_delete_insert_over_replace() -> None:
    original = _table([[_cell("HLA"), _cell("human leukocyte antigen")]])
    revised = _table([[_cell("HTA"), _cell("human technology assessment")]])
    ops = diff_table_blocks(
        original,
        revised,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        block_index=0,
    )
    assert any(op["op"] == "delete" for op in ops)
    assert any(op["op"] == "insert" for op in ops)
    # Row identity changed: avoid pretending this is one in-place replacement row.
    assert not any(op["op"] == "replace" and op.get("before") == "HLA" for op in ops)
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
