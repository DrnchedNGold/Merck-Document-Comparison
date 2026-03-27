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


def test_inline_diff_path_uses_path_block_index() -> None:
    a = {"version": 1, "blocks": [_block([{"text": "aa"}], "z")]}
    b = {"version": 1, "blocks": [_block([{"text": "bb"}], "z")]}
    ops = inline_diff_single_paragraph(
        a, b, DEFAULT_WORD_LIKE_COMPARE_CONFIG, path_block_index=3
    )
    assert ops[0]["path"] == "blocks/3/inline/0"
