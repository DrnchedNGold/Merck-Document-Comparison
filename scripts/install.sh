#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEV=0
for arg in "$@"; do
  case "$arg" in
    --dev) DEV=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./scripts/install.sh [--dev]

Creates .venv, installs the repo (pip install -e .).
--dev also installs requirements-dev.txt (pytest, etc.).
EOF
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

os_name() { uname -s 2>/dev/null || echo "unknown"; }

prompt_yes_no() {
  local prompt="$1"
  local ans
  read -r -p "${prompt} [y/N] " ans || true
  case "${ans:-}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

have_sudo() { have sudo && sudo -n true >/dev/null 2>&1 || have sudo; }

linux_pkg_mgr() {
  if have pacman; then echo pacman; return 0; fi
  if have apt-get; then echo apt-get; return 0; fi
  if have dnf; then echo dnf; return 0; fi
  echo none
}

linux_install_cmd_for() {
  # Prints a single-line install command for a logical dep group.
  # Args: group
  local group="${1:-}"
  local mgr; mgr="$(linux_pkg_mgr)"

  case "$mgr:$group" in
    pacman:python) echo "sudo pacman -S --needed python" ;;
    pacman:venv) echo "sudo pacman -S --needed python" ;; # venv ships with python on Arch
    pacman:tk) echo "sudo pacman -S --needed tk tcl" ;;
    pacman:git) echo "sudo pacman -S --needed git" ;;
    pacman:make) echo "sudo pacman -S --needed make" ;;
    pacman:docker) echo "sudo pacman -S --needed docker" ;;

    apt-get:python) echo "sudo apt-get update && sudo apt-get install -y python3" ;;
    apt-get:venv) echo "sudo apt-get update && sudo apt-get install -y python3-venv" ;;
    apt-get:tk) echo "sudo apt-get update && sudo apt-get install -y python3-tk" ;;
    apt-get:git) echo "sudo apt-get update && sudo apt-get install -y git" ;;
    apt-get:make) echo "sudo apt-get update && sudo apt-get install -y make" ;;
    apt-get:docker) echo "sudo apt-get update && sudo apt-get install -y docker.io" ;;

    dnf:python) echo "sudo dnf install -y python3" ;;
    dnf:venv) echo "sudo dnf install -y python3" ;; # venv usually in python3 package
    dnf:tk) echo "sudo dnf install -y python3-tkinter" ;;
    dnf:git) echo "sudo dnf install -y git" ;;
    dnf:make) echo "sudo dnf install -y make" ;;
    dnf:docker) echo "sudo dnf install -y docker" ;;
    *)
      echo ""
      return 1
      ;;
  esac
}

print_linux_tk_instructions() {
  if have pacman; then
    echo "  - Arch/CachyOS: sudo pacman -S tk tcl" >&2
    return 0
  fi
  if have apt-get; then
    echo "  - Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y python3-tk" >&2
    return 0
  fi
  if have dnf; then
    echo "  - Fedora/RHEL: sudo dnf install -y python3-tkinter" >&2
    return 0
  fi
  echo "  - Linux: install your distro's Tk package (e.g. python3-tk / python3-tkinter / tk + tcl)" >&2
}

pick_python() {
  if have python3.13; then echo python3.13; return; fi
  if have python3.12; then echo python3.12; return; fi
  if have python3; then echo python3; return; fi
  if have python; then echo python; return; fi
  return 1
}

PY="$(pick_python || true)"
if [[ -z "${PY}" ]]; then
  echo "ERROR: Python not found." >&2
  if [[ "$(os_name)" == "Linux" ]]; then
    local cmd
    cmd="$(linux_install_cmd_for python || true)"
    if [[ -n "$cmd" ]]; then
      echo "Missing dependency: python (3.12+ required)." >&2
      echo "Install command: $cmd" >&2
      if prompt_yes_no "Run install command now?"; then
        bash -lc "$cmd"
      fi
    else
      echo "Install Python 3.12+ using your distro package manager, then re-run." >&2
    fi
  elif [[ "$(os_name)" == "Darwin" ]]; then
    echo "Install Python 3.12+ then re-run (Homebrew: brew install python@3.13)." >&2
  else
    echo "Install Python 3.12+ then re-run." >&2
  fi
  exit 1
fi

PY_VER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)'; then
  echo "ERROR: Detected $PY ($PY_VER) but need Python >= 3.12." >&2
  exit 1
fi

# Optional but commonly needed tools (we inform; we don't require to run the app).
missing_optional=()
have git || missing_optional+=("git")
have make || missing_optional+=("make")
have docker || missing_optional+=("docker")
if [[ "${#missing_optional[@]}" -gt 0 ]]; then
  echo "Note: Optional tools missing (not required to run CLI/desktop): ${missing_optional[*]}" >&2
  if [[ "$(os_name)" == "Linux" ]]; then
    for tool in "${missing_optional[@]}"; do
      cmd="$(linux_install_cmd_for "$tool" || true)"
      if [[ -n "$cmd" ]]; then
        echo "  Install $tool: $cmd" >&2
      fi
    done
  fi
fi

# Ensure venv support exists (Debian/Ubuntu commonly needs python3-venv).
if ! "$PY" -c 'import venv' >/dev/null 2>&1; then
  echo "Missing dependency: Python venv support." >&2
  if [[ "$(os_name)" == "Linux" ]]; then
    cmd="$(linux_install_cmd_for venv || true)"
    if [[ -n "$cmd" ]]; then
      echo "Install command: $cmd" >&2
      if prompt_yes_no "Install venv support now?"; then
        bash -lc "$cmd"
      fi
    else
      echo "Install your distro's venv package (e.g. python3-venv), then re-run." >&2
    fi
  else
    echo "Install Python with venv support, then re-run." >&2
  fi
fi

if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
fi

VENV_PY=".venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: .venv created but $VENV_PY missing/unexecutable." >&2
  exit 1
fi

"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -e .

if [[ "$DEV" == "1" ]]; then
  "$VENV_PY" -m pip install -r requirements-dev.txt
fi

TK_OK="$("$VENV_PY" -c 'import tkinter; print("ok")' 2>/dev/null || true)"
if [[ "$TK_OK" != "ok" ]]; then
  cat <<'EOF' >&2
NOTE: tkinter is not available in this Python build.

Desktop GUI requires Tk/tkinter:
  - macOS (Homebrew): brew install python-tk@3.13
CLI will still work.
EOF
  if [[ "$(uname -s)" == "Linux" ]]; then
    cmd="$(linux_install_cmd_for tk || true)"
    if [[ -n "$cmd" ]]; then
      echo "Missing dependency: Tk/Tcl (desktop GUI only)." >&2
      echo "Install command: $cmd" >&2
      if prompt_yes_no "Install Tk/Tcl now?"; then
        bash -lc "$cmd"
      fi
    else
      print_linux_tk_instructions
    fi
  fi
fi

cat <<EOF

Install complete.

Activate venv:
  source .venv/bin/activate

Run CLI (installed entrypoint):
  merck-compare --original a.docx --revised b.docx --output out.docx

Run CLI (module form; from repo root):
  $VENV_PY -m engine.compare_cli --original a.docx --revised b.docx --output out.docx

Run Desktop GUI (Tk):
  $VENV_PY -m desktop
  # or (macOS Homebrew Tk helper): ./scripts/run_desktop.sh

Docs:
  docs/INSTALL.md
  docs/CLI-MERCK-COMPARE.md
EOF

