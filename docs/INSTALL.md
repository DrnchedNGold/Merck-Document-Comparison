# Install (Windows / macOS / Linux)

This repo is a **Python** project:

- **Required**: Python **3.12+**
- **CLI**: `merck-compare` (after install) or `python -m engine.compare_cli` (from repo root)
- **Desktop GUI**: `python -m desktop` (requires **Tk / tkinter**)

---

## Quickstart (recommended)

From the repo root:

- **Linux / macOS (bash)**:

```bash
./scripts/install.sh
```

- **Windows (PowerShell)**:

```powershell
.\scripts\install.ps1
```

These scripts:

- create `.venv/`
- install the repo in editable mode (`pip install -e .`) so `merck-compare` is available
- print the exact commands to run the CLI and the desktop app

To also install test/dev tools (`pytest`), pass `--dev`:

- **Linux / macOS**:

```bash
./scripts/install.sh --dev
```

- **Windows**:

```powershell
.\scripts\install.ps1 -Dev
```

---

## Running

After install:

- **CLI (installed entrypoint)**:

```bash
merck-compare --original path/to/original.docx --revised path/to/revised.docx --output path/to/out.docx
```

- **CLI (module form, no install required; run from repo root)**:

```bash
python -m engine.compare_cli --original path/to/original.docx --revised path/to/revised.docx --output path/to/out.docx
```

- **Desktop GUI (Tk)**:

```bash
python -m desktop
```

macOS note: if `tkinter` is missing in your Python build, see the **Tk / tkinter** section below.

---

## Tk / tkinter (desktop GUI prerequisites)

The desktop app requires that your Python has `tkinter`.

- **Windows**: the official python.org installer and `winget` Python typically include Tk.
- **macOS (Homebrew)**: Homebrew `python@3.13` often lacks `_tkinter`; the repo already documents the fix:
  - `brew install python-tk@3.13`
  - then run `make desktop` or `./scripts/run_desktop.sh`
- **Linux**: you usually need an OS package such as:
  - Debian/Ubuntu: `sudo apt-get update && sudo apt-get install -y python3-tk`
  - Fedora/RHEL: `sudo dnf install -y python3-tkinter`
  - Arch/CachyOS: `sudo pacman -S tk tcl`

The install scripts try to detect and guide you if `tkinter` isn’t available.

---

## Troubleshooting

- **Wrong Python version**
  - Ensure `python --version` reports **3.12+**.
- **CLI works, desktop fails**
  - If you see `ImportError: libtk8.6.so: cannot open shared object file`, install Tk:
    - Arch/CachyOS: `sudo pacman -S tk tcl`
  - Otherwise, your Python likely lacks `tkinter` or you’re in a headless environment (no display).
- **Need full docs**
  - CLI options: `docs/CLI-MERCK-COMPARE.md`

