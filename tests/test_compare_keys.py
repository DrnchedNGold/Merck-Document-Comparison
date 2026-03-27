from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.compare_keys import align_runs_by_compare_keys, generate_compare_keys


def test_generate_compare_keys_is_deterministic() -> None:
    body_ir = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [
                    {"text": "Hello", "bold": True},
                    {"text": " world", "italic": True},
                ],
            }
        ],
    }

    keys1 = generate_compare_keys(body_ir, DEFAULT_WORD_LIKE_COMPARE_CONFIG)
    keys2 = generate_compare_keys(body_ir, DEFAULT_WORD_LIKE_COMPARE_CONFIG)

    assert keys1 == keys2


def test_formatting_only_changes_do_not_break_alignment_when_ignored() -> None:
    original = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [
                    {"text": "Hello", "bold": True},
                    {"text": " world", "italic": True},
                ],
            }
        ],
    }

    # Same text, different formatting flags.
    revised = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [
                    {"text": "Hello", "bold": False, "underline": True},
                    {"text": " world", "italic": False},
                ],
            }
        ],
    }

    config = {**DEFAULT_WORD_LIKE_COMPARE_CONFIG, "ignore_formatting": True}
    alignment = align_runs_by_compare_keys(original, revised, config)

    assert alignment == [(0, 0), (1, 1)]


def test_compare_keys_change_when_formatting_is_not_ignored() -> None:
    original = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "Hello", "bold": True}],
            }
        ],
    }
    revised = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "Hello", "bold": False}],
            }
        ],
    }

    config = {**DEFAULT_WORD_LIKE_COMPARE_CONFIG, "ignore_formatting": False}

    keys_original = generate_compare_keys(original, config)
    keys_revised = generate_compare_keys(revised, config)

    assert keys_original[0]["key"] != keys_revised[0]["key"]
    assert align_runs_by_compare_keys(original, revised, config) == []


def test_ignore_case_normalizes_keys() -> None:
    body_ir = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "Hello"}],
            }
        ],
    }
    lower = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "hello"}],
            }
        ],
    }
    config = {**DEFAULT_WORD_LIKE_COMPARE_CONFIG, "ignore_case": True}
    k1 = generate_compare_keys(body_ir, config)[0]["key"]
    k2 = generate_compare_keys(lower, config)[0]["key"]
    assert k1 == k2
    assert align_runs_by_compare_keys(body_ir, lower, config) == [(0, 0)]


def test_ignore_whitespace_collapses_internal_space() -> None:
    spaced = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "a   b\t\tc"}],
            }
        ],
    }
    tight = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "a b c"}],
            }
        ],
    }
    config = {**DEFAULT_WORD_LIKE_COMPARE_CONFIG, "ignore_whitespace": True}
    assert generate_compare_keys(spaced, config) == generate_compare_keys(tight, config)


def test_generate_compare_keys_empty_body_ir() -> None:
    body_ir = {"version": 1, "blocks": []}
    assert generate_compare_keys(body_ir, DEFAULT_WORD_LIKE_COMPARE_CONFIG) == []


def test_align_runs_returns_empty_when_run_counts_differ() -> None:
    one = {
        "version": 1,
        "blocks": [{"type": "paragraph", "id": "p1", "runs": [{"text": "a"}]}],
    }
    two = {
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "id": "p1",
                "runs": [{"text": "a"}, {"text": "b"}],
            }
        ],
    }
    assert align_runs_by_compare_keys(one, two, DEFAULT_WORD_LIKE_COMPARE_CONFIG) == []

