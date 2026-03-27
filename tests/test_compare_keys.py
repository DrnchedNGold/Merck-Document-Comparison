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

