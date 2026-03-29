"""Profile JSON load/save helpers for desktop compare settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.contracts import (
    DEFAULT_WORD_LIKE_COMPARE_CONFIG,
    CompareConfig,
    validate_compare_config,
)

DEFAULT_WORD_COMPAT_PROFILE_NAME = "Word-compatible default"
PROFILE_SCHEMA_VERSION = 1


class ProfileFormatError(ValueError):
    """Raised when a profile JSON payload is invalid."""


def default_word_compatible_config() -> CompareConfig:
    """Return a mutable copy of the default compare profile."""
    return DEFAULT_WORD_LIKE_COMPARE_CONFIG.copy()


def profile_payload_from_config(
    config: CompareConfig,
    *,
    profile_name: str = DEFAULT_WORD_COMPAT_PROFILE_NAME,
) -> dict[str, Any]:
    """Build a stable profile JSON payload from a validated compare config."""
    errs = validate_compare_config(config)
    if errs:
        raise ProfileFormatError("Invalid compare config:\n" + "\n".join(errs))
    return {
        "profile_name": profile_name,
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "compare_config": dict(config),
    }


def config_from_profile_payload(payload: Any) -> CompareConfig:
    """Parse either wrapped profile JSON or bare CompareConfig JSON."""
    if not isinstance(payload, dict):
        raise ProfileFormatError("Profile JSON must be an object.")

    raw_config: Any = payload.get("compare_config", payload)
    if not isinstance(raw_config, dict):
        raise ProfileFormatError("compare_config must be a JSON object when present.")

    errs = validate_compare_config(raw_config)  # type: ignore[arg-type]
    if errs:
        raise ProfileFormatError("Invalid compare config:\n" + "\n".join(errs))
    return dict(raw_config)  # type: ignore[return-value]


def load_profile_json(path: Path) -> CompareConfig:
    """Load a profile JSON file into CompareConfig."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ProfileFormatError(f"Could not read profile JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileFormatError(f"Invalid profile JSON: {exc}") from exc
    return config_from_profile_payload(payload)


def save_profile_json(
    path: Path,
    config: CompareConfig,
    *,
    profile_name: str = DEFAULT_WORD_COMPAT_PROFILE_NAME,
) -> None:
    """Write profile JSON payload to disk."""
    payload = profile_payload_from_config(config, profile_name=profile_name)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
