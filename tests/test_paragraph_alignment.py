from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.paragraph_alignment import ParagraphAlignment, align_paragraphs


def _p(text: str) -> dict:
    return {"type": "paragraph", "id": "x", "runs": [{"text": text}]}


def test_alignment_is_deterministic_across_runs() -> None:
    original = {"version": 1, "blocks": [_p("A"), _p("B"), _p("C")]}
    revised = {"version": 1, "blocks": [_p("A"), _p("B"), _p("C")]}

    a1 = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    a2 = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    assert a1 == a2
    assert [(x.original_paragraph_index, x.revised_paragraph_index) for x in a1] == [
        (0, 0),
        (1, 1),
        (2, 2),
    ]


def test_alignment_handles_insert() -> None:
    original = {"version": 1, "blocks": [_p("A"), _p("B"), _p("C")]}
    revised = {"version": 1, "blocks": [_p("A"), _p("B"), _p("X"), _p("C")]}

    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]

    assert pairs == [(0, 0), (1, 1), (None, 2), (2, 3)]


def test_alignment_handles_delete() -> None:
    original = {"version": 1, "blocks": [_p("A"), _p("B"), _p("C")]}
    revised = {"version": 1, "blocks": [_p("A"), _p("C")]}

    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]

    assert pairs == [(0, 0), (1, None), (2, 1)]


def test_alignment_handles_small_reorder() -> None:
    original = {"version": 1, "blocks": [_p("A"), _p("B"), _p("C")]}
    revised = {"version": 1, "blocks": [_p("A"), _p("C"), _p("B")]}

    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]

    # LCS should match A and then deterministically choose the next best match.
    # This produces one delete and one insert around the reordered paragraph.
    assert pairs in (
        [(0, 0), (1, None), (2, 1), (None, 2)],
        [(0, 0), (1, 2), (2, None), (None, 1)],
    )


def test_alignment_empty_both_sides() -> None:
    original = {"version": 1, "blocks": []}
    revised = {"version": 1, "blocks": []}
    assert align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG) == []


def test_alignment_insert_all_paragraphs_when_original_empty() -> None:
    original = {"version": 1, "blocks": []}
    revised = {"version": 1, "blocks": [_p("A"), _p("B")]}
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert pairs == [(None, 0), (None, 1)]


def test_alignment_matches_identical_table_blocks() -> None:
    table = {
        "type": "table",
        "id": "t1",
        "rows": [
            [
                {
                    "paragraphs": [
                        {"type": "paragraph", "id": "p1", "runs": [{"text": "x"}]},
                    ]
                }
            ]
        ],
    }
    original = {"version": 1, "blocks": [table]}
    revised = {"version": 1, "blocks": [table]}
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert alignment == [ParagraphAlignment(0, 0)]


def test_alignment_delete_all_paragraphs_when_revised_empty() -> None:
    original = {"version": 1, "blocks": [_p("A"), _p("B")]}
    revised = {"version": 1, "blocks": []}
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert pairs == [(0, None), (1, None)]

