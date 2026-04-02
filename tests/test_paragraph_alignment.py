from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.paragraph_alignment import (
    ParagraphAlignment,
    align_paragraphs,
    alignment_for_track_changes_emit,
)


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


def test_alignment_for_track_changes_emit_pairs_by_index_when_types_match() -> None:
    """Emit uses (i,i) when block counts and types align index-for-index."""
    original = {"version": 1, "blocks": [_p("A"), _p("B")]}
    revised = {"version": 1, "blocks": [_p("A"), _p("C")]}
    a = alignment_for_track_changes_emit(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert [(x.original_paragraph_index, x.revised_paragraph_index) for x in a] == [
        (0, 0),
        (1, 1),
    ]


def test_alignment_for_track_changes_emit_uses_lcs_when_type_mismatches_at_index() -> None:
    """SCRUM-115: paragraph vs table at the same index must not use blind (i,i)."""
    table = {
        "type": "table",
        "id": "t1",
        "rows": [
            [
                {
                    "paragraphs": [
                        {"type": "paragraph", "id": "c1", "runs": [{"text": "X"}]}
                    ]
                }
            ]
        ],
    }
    original = {"version": 1, "blocks": [_p("Header"), _p("Filler"), _p("Tail")]}
    revised = {"version": 1, "blocks": [_p("Header"), table, _p("Tail")]}
    a = alignment_for_track_changes_emit(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in a]
    assert (1, 1) not in pairs


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


def test_alignment_toc_slot_reworded_title_pairs_same_paragraph() -> None:
    """SCRUM-116: same TOC section number + tab leaders should not become delete+insert."""
    original = {
        "version": 1,
        "blocks": [
            _p("Front matter."),
            _p("1.2.1\tPathophysiology\t9"),
            _p("1.2.2\tPrevention, Screening or Diagnostic Strategies\t10"),
            _p("Tail."),
        ],
    }
    revised = {
        "version": 1,
        "blocks": [
            _p("Front matter."),
            _p("1.2.1\tDifferences in Pathophysiology\t12"),
            _p("1.2.2\tDifferences in Prevention, Screening, or Diagnostic Strategies\t13"),
            _p("Tail."),
        ],
    }
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert pairs == [(0, 0), (1, 1), (2, 2), (3, 3)]


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


def test_alignment_pairs_primary_endpoint_paragraph_when_extra_paragraph_at_end() -> None:
    """Heavy edit + shared prefix must still match when B has an extra trailing block."""
    old_ep = "The primary endpoint is overall response rate at week 12."
    new_ep = "The primary endpoint is progression-free survival at week 24."
    original = {
        "version": 1,
        "blocks": [
            _p("The study will enroll 100 participants at three sites."),
            _p("Inclusion criteria: adults aged 65 to 75 with confirmed diagnosis."),
            _p(old_ep),
            _p("Contact: Dr. Smith (lead investigator)."),
        ],
    }
    revised = {
        "version": 1,
        "blocks": [
            _p("The study will enroll 120 participants at four sites."),
            _p("Inclusion criteria: adults aged 65 to 75 with confirmed diagnosis."),
            _p(new_ep),
            _p("Contact: Dr. Jones (lead investigator)."),
            _p("Data monitoring will occur monthly."),
        ],
    }
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert (2, 2) in pairs, pairs


def test_alignment_fuzzy_pairs_edited_paragraph_when_signatures_differ() -> None:
    """Edited same sentence must align (not delete+insert whole block) when counts differ."""
    s1 = "The study will enroll 100 participants at three sites."
    s2 = "The study will enroll 120 participants at four sites."
    original = {"version": 1, "blocks": [_p(s1), _p("Next section.")]}
    revised = {
        "version": 1,
        "blocks": [_p("New opening line."), _p(s2), _p("Next section.")],
    }
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert (0, 1) in pairs, pairs
    assert (1, 2) in pairs, pairs


def test_alignment_delete_all_paragraphs_when_revised_empty() -> None:
    original = {"version": 1, "blocks": [_p("A"), _p("B")]}
    revised = {"version": 1, "blocks": []}
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert pairs == [(0, None), (1, None)]


def _tbl_one_cell(text: str) -> dict:
    return {
        "type": "table",
        "id": "t",
        "rows": [
            [
                {
                    "paragraphs": [
                        {"type": "paragraph", "id": "c", "runs": [{"text": text}]},
                    ]
                }
            ]
        ],
    }


def test_alignment_emit_pairs_tables_after_revised_only_paragraph_scrum120() -> None:
    """SCRUM-120: LCS (orig-only tbl, rev-only p, rev-only tbl) → match tbl for cell diff."""
    original = {
        "version": 1,
        "blocks": [_p("H"), _p("intro"), _tbl_one_cell("oldcell")],
    }
    revised = {
        "version": 1,
        "blocks": [
            _p("H"),
            _p("intro"),
            _p("Long new paragraph before table."),
            _tbl_one_cell("newcell"),
        ],
    }
    raw = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert [(x.original_paragraph_index, x.revised_paragraph_index) for x in raw] == [
        (0, 0),
        (1, 1),
        (2, None),
        (None, 2),
        (None, 3),
    ]
    emit = alignment_for_track_changes_emit(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert [(x.original_paragraph_index, x.revised_paragraph_index) for x in emit] == [
        (0, 0),
        (1, 1),
        (None, 2),
        (2, 3),
    ]

