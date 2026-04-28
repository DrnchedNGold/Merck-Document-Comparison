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


CustomPalette = dict[str, Any]


def default_word_compatible_config() -> CompareConfig:
    """Return a mutable copy of the default compare profile."""
    return DEFAULT_WORD_LIKE_COMPARE_CONFIG.copy()


def _validate_custom_palettes(raw: Any) -> list[tuple[str, list[str]]]:
    # Palette support removed.
    return []


def profile_payload_from_config(
    config: CompareConfig,
    *,
    profile_name: str = DEFAULT_WORD_COMPAT_PROFILE_NAME,
    word_track_changes_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable profile JSON payload from a validated compare config."""
    errs = validate_compare_config(config)
    if errs:
        raise ProfileFormatError("Invalid compare config:\n" + "\n".join(errs))
    word_track_changes_options = word_track_changes_options or default_word_track_changes_options()
    return {
        "profile_name": profile_name,
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "compare_config": dict(config),
        "word_track_changes_options": dict(word_track_changes_options),
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


def default_word_track_changes_options() -> dict[str, int]:
    # Matches user screenshots (Advanced Track Changes Options) and keeps all knobs editable via profile.
    return {
        # MARKUP
        "InsertedTextMark": 3,
        "InsertedTextColor": 6,  # wdRed
        "DeletedTextMark": 1,
        "DeletedTextColor": 6,  # wdRed
        "RevisedLinesMark": 3,  # wdRevisedLinesMarkOutsideBorder
        "RevisedLinesColor": 6,  # wdRed
        "RevisedPropertiesMark": 0,
        "RevisedPropertiesColor": -1,  # wdByAuthor
        "CommentsColor": -1,  # wdByAuthor

        # MOVES
        "TrackMoves": 1,  # bool-ish (1/0) for storage simplicity
        "MoveFromTextMark": 7,  # italic (per user default)
        "MoveFromTextColor": 6,  # wdRed
        "MoveToTextMark": 4,  # double underline
        "MoveToTextColor": 6,  # wdRed

        # TABLE CELL HIGHLIGHTING
        "InsertedCellColor": 2,  # wdCellColorLightBlue
        "DeletedCellColor": 1,  # wdCellColorPink
        "MergedCellColor": -1,  # wdCellColorByAuthor
        "SplitCellColor": -1,  # wdCellColorByAuthor

        # FORMATTING
        "TrackFormatting": 1,  # doc setting, stored here

        # BALLOONS
        "BalloonsPreferredWidthInches": 3.7,
        "BalloonsShowConnectingLines": 0,  # disabled in screenshot
        "BalloonsPrintOrientation": 1,  # wdBalloonPrintOrientationPreserve
    }


def _validate_word_track_changes_options(raw: Any) -> dict[str, int]:
    if raw is None:
        return default_word_track_changes_options()
    if not isinstance(raw, dict):
        raise ProfileFormatError("word_track_changes_options must be an object when present.")
    defaults = default_word_track_changes_options()
    out: dict[str, Any] = dict(defaults)
    for k in defaults.keys():
        if k not in raw:
            continue
        v = raw[k]
        # A few fields are numeric but not integer (width inches).
        if k == "BalloonsPreferredWidthInches":
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                raise ProfileFormatError(
                    "word_track_changes_options.BalloonsPreferredWidthInches must be a number."
                ) from None
            continue
        # Bool-ish fields stored as 0/1.
        if k in ("TrackMoves", "TrackFormatting", "BalloonsShowConnectingLines"):
            if isinstance(v, bool):
                out[k] = 1 if v else 0
            else:
                try:
                    out[k] = 1 if int(v) != 0 else 0
                except (TypeError, ValueError):
                    raise ProfileFormatError(f"word_track_changes_options.{k} must be 0/1.") from None
            continue
        try:
            out[k] = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ProfileFormatError(f"word_track_changes_options.{k} must be an integer.") from None
    # Type is loose on purpose (mixed int/float).
    return out  # type: ignore[return-value]


def load_profile_bundle(
    path: Path,
) -> tuple[CompareConfig, dict[str, int], str]:
    """Load a profile JSON file into (CompareConfig, word options, profile name)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ProfileFormatError(f"Could not read profile JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileFormatError(f"Invalid profile JSON: {exc}") from exc

    cfg = config_from_profile_payload(payload)
    if isinstance(payload, dict) and "compare_config" in payload:
        word_opts = _validate_word_track_changes_options(payload.get("word_track_changes_options"))
        prof_name = payload.get("profile_name", path.name)
        if not isinstance(prof_name, str) or not prof_name.strip():
            prof_name = path.name
        return cfg, word_opts, prof_name.strip()
    # Legacy bare config: no wrapper fields.
    return cfg, default_word_track_changes_options(), path.name


def load_profile_json(path: Path) -> CompareConfig:
    """Load a profile JSON file into CompareConfig."""
    cfg, _, _ = load_profile_bundle(path)
    return cfg


def save_profile_json(
    path: Path,
    config: CompareConfig,
    *,
    profile_name: str = DEFAULT_WORD_COMPAT_PROFILE_NAME,
    word_track_changes_options: dict[str, Any] | None = None,
) -> None:
    """Write profile JSON payload to disk."""
    payload = profile_payload_from_config(
        config,
        profile_name=profile_name,
        word_track_changes_options=word_track_changes_options,
    )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
