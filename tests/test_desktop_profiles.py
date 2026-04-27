"""Desktop compare settings profile JSON tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from desktop.profiles import (
    DEFAULT_WORD_COMPAT_PROFILE_NAME,
    ProfileFormatError,
    config_from_profile_payload,
    default_word_compatible_config,
    load_profile_json,
    profile_payload_from_config,
    save_profile_json,
)
from engine.contracts import DEFAULT_WORD_LIKE_COMPARE_CONFIG


def test_default_word_compatible_profile_matches_engine_default() -> None:
    assert default_word_compatible_config() == DEFAULT_WORD_LIKE_COMPARE_CONFIG


def test_profile_payload_round_trip(tmp_path: Path) -> None:
    cfg = {
        "ignore_case": True,
        "ignore_whitespace": False,
        "ignore_formatting": True,
        "detect_moves": False,
    }
    profile_path = tmp_path / "profile.json"
    save_profile_json(profile_path, cfg, profile_name="My profile")
    loaded = load_profile_json(profile_path)
    assert loaded == cfg


def test_profile_payload_contains_word_compatible_default_name() -> None:
    payload = profile_payload_from_config(default_word_compatible_config())
    assert payload["profile_name"] == DEFAULT_WORD_COMPAT_PROFILE_NAME
    assert "compare_config" in payload


def test_load_profile_supports_legacy_bare_compare_config(tmp_path: Path) -> None:
    cfg = default_word_compatible_config()
    profile_path = tmp_path / "legacy.json"
    profile_path.write_text(json.dumps(cfg), encoding="utf-8")
    assert load_profile_json(profile_path) == cfg


def test_invalid_profile_payload_raises() -> None:
    with pytest.raises(ProfileFormatError):
        config_from_profile_payload({"compare_config": {"ignore_case": "yes"}})
