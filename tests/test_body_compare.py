from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.body_compare import matched_paragraph_inline_diffs, single_paragraph_body
from engine.contracts import validate_diff_ops
from engine.inline_run_diff import inline_diff_single_paragraph


def _block(runs: list[dict], pid: str = "p") -> dict:
    return {"type": "paragraph", "id": pid, "runs": runs}


def test_single_paragraph_body_extracts_block() -> None:
    body = {
        "version": 1,
        "blocks": [_block([{"text": "a"}], "0"), _block([{"text": "b"}], "1")],
    }
    one = single_paragraph_body(body, 1)
    assert one == {"version": 1, "blocks": [_block([{"text": "b"}], "1")]}


def test_matched_paragraph_inline_diffs_sets_part_when_requested() -> None:
    cfg = DEFAULT_WORD_LIKE_COMPARE_CONFIG
    original = {"version": 1, "blocks": [_block([{"text": "x"}]), _block([{"text": "y"}])]}
    revised = {"version": 1, "blocks": [_block([{"text": "x"}]), _block([{"text": "y"}])]}
    rows = matched_paragraph_inline_diffs(
        original, revised, cfg, part="word/footer1.xml"
    )
    assert len(rows) == 2
    assert all(r.part == "word/footer1.xml" for r in rows)
    assert rows[0].diff_ops == []


def test_matched_paragraph_inline_diffs_empty_when_all_signatures_match() -> None:
    cfg = DEFAULT_WORD_LIKE_COMPARE_CONFIG
    original = {"version": 1, "blocks": [_block([{"text": "x"}]), _block([{"text": "y"}])]}
    revised = {"version": 1, "blocks": [_block([{"text": "x"}]), _block([{"text": "y"}])]}
    rows = matched_paragraph_inline_diffs(original, revised, cfg)
    assert len(rows) == 2
    assert rows[0].original_paragraph_index == 0
    assert rows[0].diff_ops == []
    assert rows[1].diff_ops == []
    for r in rows:
        assert validate_diff_ops(r.diff_ops) == []


def _table_cell(text: str) -> dict:
    return {
        "paragraphs": [
            {"type": "paragraph", "id": "c", "runs": [{"text": text}]},
        ]
    }


def _one_by_one_table(cell_text: str, tid: str = "t1") -> dict:
    return {
        "type": "table",
        "id": tid,
        "rows": [[_table_cell(cell_text)]],
    }


def test_matched_paragraph_inline_diffs_aligned_tables_emit_ops() -> None:
    cfg = DEFAULT_WORD_LIKE_COMPARE_CONFIG
    original = {"version": 1, "blocks": [_one_by_one_table("old")]}
    revised = {"version": 1, "blocks": [_one_by_one_table("new")]}
    rows = matched_paragraph_inline_diffs(original, revised, cfg)
    assert len(rows) == 1
    r = rows[0]
    assert r.original_paragraph_index == 0
    assert r.revised_paragraph_index == 0
    assert r.diff_ops == [
        {
            "op": "replace",
            "path": "blocks/0/rows/0/cells/0/inline/0",
            "before": "old",
            "after": "new",
        }
    ]
    assert validate_diff_ops(r.diff_ops) == []


def test_matched_paragraph_inline_diffs_table_ops_include_part() -> None:
    cfg = DEFAULT_WORD_LIKE_COMPARE_CONFIG
    original = {"version": 1, "blocks": [_one_by_one_table("old")]}
    revised = {"version": 1, "blocks": [_one_by_one_table("new")]}
    rows = matched_paragraph_inline_diffs(
        original, revised, cfg, part="word/document.xml"
    )
    assert len(rows) == 1
    assert len(rows[0].diff_ops) == 1
    assert all(op.get("part") == "word/document.xml" for op in rows[0].diff_ops)
    assert validate_diff_ops(rows[0].diff_ops) == []


def test_inline_diff_path_uses_path_block_index() -> None:
    a = {"version": 1, "blocks": [_block([{"text": "aa"}], "z")]}
    b = {"version": 1, "blocks": [_block([{"text": "bb"}], "z")]}
    ops = inline_diff_single_paragraph(
        a, b, DEFAULT_WORD_LIKE_COMPARE_CONFIG, path_block_index=3
    )
    assert ops[0]["path"] == "blocks/3/inline/0"
