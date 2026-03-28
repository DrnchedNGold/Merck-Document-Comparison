import pytest

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.contracts import validate_diff_ops
from engine.inline_run_diff import inline_diff_single_paragraph
from engine.paragraph_alignment import align_paragraphs


def _p(runs: list[dict]) -> dict:
    return {"version": 1, "blocks": [{"type": "paragraph", "id": "p1", "runs": runs}]}


def test_inline_diff_stamps_part_when_diff_part_set() -> None:
    original = _p([{"text": "foo"}])
    revised = _p([{"text": "bar"}])
    ops = inline_diff_single_paragraph(
        original,
        revised,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        diff_part="word/header1.xml",
    )
    assert ops == [
        {
            "op": "replace",
            "path": "blocks/0/inline/0",
            "before": "foo",
            "after": "bar",
            "part": "word/header1.xml",
        },
    ]
    assert validate_diff_ops(ops) == []


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


def test_inline_diff_rejects_non_single_block_body_ir() -> None:
    two_blocks = {
        "version": 1,
        "blocks": [
            {"type": "paragraph", "id": "a", "runs": [{"text": "x"}]},
            {"type": "paragraph", "id": "b", "runs": [{"text": "y"}]},
        ],
    }
    with pytest.raises(ValueError, match="exactly one paragraph"):
        inline_diff_single_paragraph(two_blocks, _p([{"text": "x"}]), DEFAULT_WORD_LIKE_COMPARE_CONFIG)


def test_inline_diff_rejects_non_paragraph_block() -> None:
    bad = {"version": 1, "blocks": [{"type": "paragraph", "id": "p1", "runs": [{"text": "a"}]}]}
    bad["blocks"][0]["type"] = "table"  # type: ignore[index, assignment]
    with pytest.raises(ValueError, match="paragraph"):
        inline_diff_single_paragraph(bad, _p([{"text": "a"}]), DEFAULT_WORD_LIKE_COMPARE_CONFIG)


def test_after_paragraph_alignment_when_signatures_match_inline_diff_is_empty() -> None:
    """Same paragraph text yields LCS match (0,0) and no inline ops."""
    body = _p([{"text": "Hello"}])
    alignment = align_paragraphs(body, body, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert [(a.original_paragraph_index, a.revised_paragraph_index) for a in alignment] == [(0, 0)]
    assert inline_diff_single_paragraph(body, body, DEFAULT_WORD_LIKE_COMPARE_CONFIG) == []


def test_inline_diff_paths_are_sequential() -> None:
    """Every emitted op uses path blocks/0/inline/0, /1, ... in order."""
    original = _p([{"text": "aa"}])
    revised = _p([{"text": "bb"}])
    ops = inline_diff_single_paragraph(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert [o["path"] for o in ops] == [f"blocks/0/inline/{i}" for i in range(len(ops))]
    assert validate_diff_ops(ops) == []
