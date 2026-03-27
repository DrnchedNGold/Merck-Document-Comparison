"""SCRUM-48: guard that Sprint 2 (MDC-005–007) engine surface stays wired."""

from __future__ import annotations

from engine import (
    DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    align_paragraphs,
    generate_compare_keys,
    inline_diff_single_paragraph,
)


def test_sprint2_core_functions_are_callable_and_deterministic() -> None:
    body = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "x"}],
            }
        ],
    }
    cfg = DEFAULT_WORD_LIKE_COMPARE_CONFIG
    assert generate_compare_keys(body, cfg) == generate_compare_keys(body, cfg)
    a1 = align_paragraphs(body, body, cfg)
    a2 = align_paragraphs(body, body, cfg)
    assert a1 == a2
    assert inline_diff_single_paragraph(body, body, cfg) == []
