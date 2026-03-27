from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.contracts import validate_diff_ops
from engine.inline_run_diff import inline_diff_single_paragraph


def _p(runs: list[dict]) -> dict:
    return {"version": 1, "blocks": [{"type": "paragraph", "id": "p1", "runs": runs}]}


def test_inline_diff_insert_within_one_paragraph() -> None:
    original = _p([{"text": "Hello"}])
    revised = _p([{"text": "Hello world"}])
    ops = inline_diff_single_paragraph(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert ops == [
        {"op": "insert", "path": "blocks/0/inline/0", "before": None, "after": " world"},
    ]
    assert validate_diff_ops(ops) == []


def test_inline_diff_delete_within_one_paragraph() -> None:
    original = _p([{"text": "Hello world"}])
    revised = _p([{"text": "Hello"}])
    ops = inline_diff_single_paragraph(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert ops == [
        {"op": "delete", "path": "blocks/0/inline/0", "before": " world", "after": None},
    ]
    assert validate_diff_ops(ops) == []


def test_inline_diff_replace_within_one_paragraph() -> None:
    # No shared substring between "foo" and "bar" so SequenceMatcher emits one replace.
    original = _p([{"text": "foo"}])
    revised = _p([{"text": "bar"}])
    ops = inline_diff_single_paragraph(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert ops == [
        {"op": "replace", "path": "blocks/0/inline/0", "before": "foo", "after": "bar"},
    ]
    assert validate_diff_ops(ops) == []


def test_inline_diff_is_deterministic_on_repeated_calls() -> None:
    original = _p([{"text": "a"}, {"text": "b"}])
    revised = _p([{"text": "a"}, {"text": "c"}])
    cfg = DEFAULT_WORD_LIKE_COMPARE_CONFIG
    first = inline_diff_single_paragraph(original, revised, cfg)
    second = inline_diff_single_paragraph(original, revised, cfg)
    assert first == second
    assert first == [{"op": "replace", "path": "blocks/0/inline/0", "before": "b", "after": "c"}]


def test_inline_diff_multiple_runs_concatenates_like_word_runs() -> None:
    original = _p([{"text": "The "}, {"text": "quick"}])
    revised = _p([{"text": "The slow"}])
    ops = inline_diff_single_paragraph(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert ops == [{"op": "replace", "path": "blocks/0/inline/0", "before": "quick", "after": "slow"}]


def test_inline_diff_no_ops_when_identical() -> None:
    body = _p([{"text": "Same"}])
    assert inline_diff_single_paragraph(body, body, DEFAULT_WORD_LIKE_COMPARE_CONFIG) == []
