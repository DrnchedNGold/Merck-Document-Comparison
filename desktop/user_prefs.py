"""Small per-user prefs store for the desktop app."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _prefs_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "MerckDocCompare" / "prefs.json"
    return Path.home() / ".config" / "merck-doc-compare" / "prefs.json"


def load_prefs() -> dict[str, Any]:
    path = _prefs_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_prefs(prefs: dict[str, Any]) -> None:
    path = _prefs_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prefs, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return

