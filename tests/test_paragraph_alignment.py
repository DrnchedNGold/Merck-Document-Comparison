import pytest

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
import engine.paragraph_alignment as paragraph_alignment
from engine.paragraph_alignment import (
    ParagraphAlignment,
    align_paragraphs,
    alignment_for_track_changes_emit,
    _repair_alignment_orig_para_rev_split_merge,
    _repair_alignment_unmatched_rev_expansion_override,
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


def test_alignment_token_similarity_keeps_large_similar_paragraph_in_place() -> None:
    """Large same-paragraph rewrites should align instead of reflowing into delete+insert blocks."""

    original = {
        "version": 1,
        "blocks": [
            _p("Intro paragraph."),
            _p(
                "The sponsor will continue to build upon diversity efforts expected by the FDA "
                "and will embed participant diversity and inclusion into product development "
                "across clinical planning, study recruitment, site activation, and monitoring."
            ),
            _p("Tail paragraph."),
        ],
    }
    revised = {
        "version": 1,
        "blocks": [
            _p("Intro paragraph."),
            _p("Intervening inserted paragraph."),
            _p(
                "The sponsor will continue to build upon diversity efforts expected by the FDA "
                "and will embed participant diversity and inclusion into product development "
                "across clinical planning, study recruitment, country selection, site activation, "
                "enrollment monitoring, and patient retention."
            ),
            _p("Tail paragraph."),
        ],
    }

    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert (1, 2) in pairs, pairs


def test_alignment_near_index_word_jaccard_pairs_after_insert() -> None:
    """Near-diagonal paragraph with heavy char churn but same vocabulary still matches.

    Without a word-bag signal, ``quick_ratio`` on raw strings can be low while the
    revised block is still the edited same paragraph (one ``w:p`` inserted above).
    """

    long_shared = ("token " * 60).strip()
    short_shared = ("token " * 24).strip()
    original = {"version": 1, "blocks": [_p("A"), _p(long_shared), _p("Z")]}
    revised = {
        "version": 1,
        "blocks": [
            _p("A"),
            _p("Inserted paragraph between anchors."),
            _p(short_shared),
            _p("Z"),
        ],
    }
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert (1, 2) in pairs, pairs


def test_raw_max_char_tok_ratio_skips_expensive_char_ratio_for_large_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSequenceMatcher:
        def __init__(self, _junk, a, b, autojunk=False):
            self.a = a
            self.b = b

        def quick_ratio(self) -> float:
            return 1.0

        def ratio(self) -> float:
            if isinstance(self.a, str) and isinstance(self.b, str):
                raise AssertionError("raw string ratio() should be skipped for huge inputs")
            return 1.0

    monkeypatch.setattr(paragraph_alignment.difflib, "SequenceMatcher", FakeSequenceMatcher)
    monkeypatch.setattr(paragraph_alignment, "_ALIGN_SKIP_CHAR_RATIO_MAX_CHARS", 10)
    monkeypatch.setattr(paragraph_alignment, "_ALIGN_SKIP_CHAR_RATIO_MAX_PRODUCT", 100)

    text = ("token " * 40).strip()
    assert paragraph_alignment._raw_max_char_tok_ratio(text, text) == 1.0


def test_alignment_large_paragraphs_uses_token_ratio_when_char_ratio_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSequenceMatcher:
        def __init__(self, _junk, a, b, autojunk=False):
            self.a = a
            self.b = b

        def quick_ratio(self) -> float:
            return 0.95

        def ratio(self) -> float:
            if isinstance(self.a, str) and isinstance(self.b, str):
                raise AssertionError("raw string ratio() should be skipped for huge inputs")
            return 1.0

    monkeypatch.setattr(paragraph_alignment.difflib, "SequenceMatcher", FakeSequenceMatcher)
    monkeypatch.setattr(paragraph_alignment, "_ALIGN_SKIP_CHAR_RATIO_MAX_CHARS", 10)
    monkeypatch.setattr(paragraph_alignment, "_ALIGN_SKIP_CHAR_RATIO_MAX_PRODUCT", 100)

    original = {"version": 1, "blocks": [_p(("token " * 400).strip() + " old")]}
    revised = {"version": 1, "blocks": [_p(("token " * 400).strip() + " new")]}

    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    assert alignment == [ParagraphAlignment(0, 0)]


def test_raw_max_char_tok_ratio_keeps_char_ratio_for_small_body_even_if_text_is_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSequenceMatcher:
        def __init__(self, _junk, a, b, autojunk=False):
            self.a = a
            self.b = b

        def quick_ratio(self) -> float:
            return 1.0

        def ratio(self) -> float:
            if isinstance(self.a, str) and isinstance(self.b, str):
                return 0.6
            return 1.0

    monkeypatch.setattr(paragraph_alignment.difflib, "SequenceMatcher", FakeSequenceMatcher)
    monkeypatch.setattr(paragraph_alignment, "_ALIGN_SKIP_CHAR_RATIO_MAX_CHARS", 10)
    monkeypatch.setattr(paragraph_alignment, "_ALIGN_SKIP_CHAR_RATIO_MAX_PRODUCT", 100)
    monkeypatch.setattr(paragraph_alignment, "_ALIGN_SKIP_CHAR_RATIO_MIN_BODY_BLOCKS", 1000)

    text = ("token " * 40).strip()
    assert paragraph_alignment._raw_max_char_tok_ratio(text, text, body_block_count=200) == 1.0


def test_repair_unmatched_rev_expansion_override_merges_false_delete_insert() -> None:
    """Post-LCS repair pairs (o,None)+(None,r) when rank, gates, and containment allow."""

    short = "Section one establishes inclusion criteria for adult patients enrolled."
    # Mild suffix keeps _pair_rank_similarity above the override floor (heavy
    # appended text drives char/tok ratio down and the repair correctly skips).
    long_rev = short + " Extra."
    original = {"version": 1, "blocks": [_p("x"), _p(short), _p("z")]}
    revised = {
        "version": 1,
        "blocks": [
            _p("x"),
            _p("noise paragraph inserted between anchors."),
            _p(long_rev),
            _p("z"),
        ],
    }
    cfg = DEFAULT_WORD_LIKE_COMPARE_CONFIG
    raw = [
        ParagraphAlignment(0, 0),
        ParagraphAlignment(1, None),
        ParagraphAlignment(None, 1),
        ParagraphAlignment(None, 2),
        ParagraphAlignment(2, 3),
    ]
    repaired = _repair_alignment_unmatched_rev_expansion_override(
        raw, original, revised, cfg
    )
    pairs = [(a.original_paragraph_index, a.revised_paragraph_index) for a in repaired]
    assert (1, 2) in pairs, pairs
    assert (1, None) not in pairs and (None, 2) not in pairs


def test_alignment_length_weak_prefix_expansion_pairs_with_insert_above() -> None:
    """Short original paragraph expanded to many chars still matches after an insert."""

    short = "Section one establishes inclusion criteria for adult patients enrolled."
    long_rev = short + (" more detail." * 40)
    original = {"version": 1, "blocks": [_p("x"), _p(short), _p("z")]}
    revised = {
        "version": 1,
        "blocks": [_p("x"), _p("Inserted paragraph."), _p(long_rev), _p("z")],
    }
    alignment = align_paragraphs(original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    pairs = [(x.original_paragraph_index, x.revised_paragraph_index) for x in alignment]
    assert (1, 2) in pairs, pairs


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


def test_repair_scrum121_merges_orig_only_then_rev_split_paragraphs() -> None:
    """SCRUM-121: (oi, None) + (None, r0) + (None, r1) + (oi+1, *) → merged revised span."""

    shared = " ".join(["SHAREDWORD"] * 15)
    original = {
        "version": 1,
        "blocks": [
            _p("x"),
            _p("alpha beta gamma delta epsilon " + shared),
            _p("z"),
        ],
    }
    revised = {
        "version": 1,
        "blocks": [
            _p("x"),
            _p("completely new opening sentence here "),
            _p(shared),
            _p("z"),
        ],
    }
    raw_lcs = [
        ParagraphAlignment(0, 0),
        ParagraphAlignment(1, None),
        ParagraphAlignment(None, 1),
        ParagraphAlignment(None, 2),
        ParagraphAlignment(2, 3),
    ]
    repaired = _repair_alignment_orig_para_rev_split_merge(
        raw_lcs, original, revised, DEFAULT_WORD_LIKE_COMPARE_CONFIG
    )
    assert repaired == [
        ParagraphAlignment(0, 0),
        ParagraphAlignment(1, 1, revised_merge_end_exclusive=3),
        ParagraphAlignment(2, 3),
    ]
