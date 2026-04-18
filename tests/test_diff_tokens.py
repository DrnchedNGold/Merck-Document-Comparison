"""Unit tests for :mod:`engine.diff_tokens` (LCS tokenization for Track Changes)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.compare_keys import _normalize_text
from engine.diff_tokens import (
    DiffToken,
    bounds_from_token_indices,
    equal_span_surface,
    norm_keys,
    structured_orig_tokens_from_aligned_runs,
    tokenize_for_lcs,
)


def test_tokenize_splits_commas_between_numbers() -> None:
    s = "16,18,31"
    toks = tokenize_for_lcs(s)
    assert [t.surface for t in toks] == ["16", ",", "18", ",", "31"]
    assert "".join(t.surface for t in toks) == s


def test_tokenize_preserves_whitespace_surface() -> None:
    toks = tokenize_for_lcs("Hi  \tthere")
    assert any(t.surface == "  \t" for t in toks)
    assert norm_keys([t for t in toks if t.surface.isspace()]) == [" "]


def test_norm_key_casefolds_words_not_whitespace_count() -> None:
    toks = tokenize_for_lcs("The CAT")
    keys = norm_keys(toks)
    assert keys[0] == "the"
    assert keys[2] == "cat"


def test_bounds_and_equal_surface_concat() -> None:
    toks = tokenize_for_lcs("a, b")
    n = len(toks)
    assert equal_span_surface(toks, 0, n) == "a, b"
    assert bounds_from_token_indices(toks, 0, n) == (0, len("a, b"))
    assert equal_span_surface(toks, 0, 1) == "a"


def test_diff_token_dataclass_fields() -> None:
    t = DiffToken("x", 0, 1)
    assert t.start == 0 and t.end == 1


def test_structured_orig_tokens_aligns_per_run_tokenization_with_paragraph() -> None:
    """Per-``w:r`` token streams must match :func:`tokenize_for_lcs` on concatenated compare text."""
    word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    r1 = ET.Element(f"{{{word_ns}}}r")
    ET.SubElement(r1, f"{{{word_ns}}}t").text = "Hi,"
    r2 = ET.Element(f"{{{word_ns}}}r")
    ET.SubElement(r2, f"{{{word_ns}}}t").text = " there"
    aligned = [(r1, "Hi,"), (r2, " there")]
    orig_cmp = "".join(_normalize_text(raw, DEFAULT_WORD_LIKE_COMPARE_CONFIG) for _, raw in aligned)
    assert orig_cmp == "Hi, there"
    struct = structured_orig_tokens_from_aligned_runs(aligned, orig_cmp)
    assert struct is not None
    assert len(struct) == len(tokenize_for_lcs(orig_cmp))
    assert struct[0].run_el is r1 and struct[2].run_el is r2
