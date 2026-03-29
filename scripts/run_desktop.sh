#!/usr/bin/env bash
# Launch the Tk desktop from the repo root. On macOS + Homebrew, Homebrew's
# python@3.13 has no _tkinter; python-tk@3.13 installs the extension under
# $(brew --prefix python-tk@3.13)/libexec — prepend that to PYTHONPATH.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT"

if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  PYTK_PREFIX="$(brew --prefix python-tk@3.13 2>/dev/null || true)"
  if [[ -n "${PYTK_PREFIX}" && -d "${PYTK_PREFIX}/libexec" ]]; then
    export PYTHONPATH="${PYTK_PREFIX}/libexec:${PYTHONPATH}"
  fi
fi

if command -v python3.13 >/dev/null 2>&1; then
  exec python3.13 -m desktop
fi

exec python3 -m desktop
