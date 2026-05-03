# `merck-compare` — engine CLI user guide

Command-line entry point for **Merck Document Comparison**: compare two Word `.docx` files and write a **new** document with package **Track Changes**–style revision markup (`w:ins` / `w:del` / `w:delText`, etc.).

For product scope and acceptance IDs, see [`V1-ACCEPTANCE-CATALOG.md`](V1-ACCEPTANCE-CATALOG.md) (**MDC-015**).

---

## Installation and invocation

After a development install from the repo root:

```bash
python -m pip install -e .
```

You can run the tool as:

| Invocation | Notes |
|------------|--------|
| `merck-compare …` | Console script from `pyproject.toml` |
| `python -m engine.compare_cli …` | Module form (useful without install, from repo root) |

Implementation: [`engine/compare_cli.py`](../engine/compare_cli.py).

---

## Synopsis

```text
merck-compare --original PATH --revised PATH --output PATH
              [--config PATH] [--author NAME] [--date-iso ISO8601] [--profile]
```

All of `--original`, `--revised`, and `--output` are **required** unless you only run `--help`.

---

## Options

| Option | Description |
|--------|-------------|
| `--original` | Path to the **baseline** `.docx` (Word Open XML package). |
| `--revised` | Path to the **modified** `.docx`. |
| `--output` | Path where the generated `.docx` is written (parent directories are created if needed). |
| `--config` | Optional JSON file describing a `CompareConfig` (see below). If omitted, defaults match `engine.DEFAULT_WORD_LIKE_COMPARE_CONFIG`. |
| `--author` | String stored as revision author in emitted markup (default: `MerckDocCompare`). |
| `--date-iso` | Optional fixed `w:date` for reproducible runs, e.g. `2026-03-28T12:00:00Z`. |
| `--profile` | Print phase timings for document generation to **stderr** (diagnostics only; does not change output). |

Run **`merck-compare --help`** for the same summary and the exit-code epilog.

---

## Compare configuration (`--config`)

The file must be a **JSON object** with **exactly** these boolean keys (see [`engine/contracts.py`](../engine/contracts.py)):

| Key | Meaning |
|-----|---------|
| `ignore_case` | Case-insensitive text comparison when applicable. |
| `ignore_whitespace` | Collapse/normalize whitespace for comparison. |
| `ignore_formatting` | Ignore formatting-only differences where supported. |
| `detect_moves` | Enable move detection when implemented (v1 may treat as no-op). |

Invalid JSON, wrong shape, or failed validation exits with code **2** and prints a message on **stderr**.

**Example** (`compare-config.json`):

```json
{
  "ignore_case": false,
  "ignore_whitespace": false,
  "ignore_formatting": true,
  "detect_moves": false
}
```

This JSON is also the default **Word-compatible** settings profile used by the desktop UI when no custom profile is loaded.

```bash
merck-compare --original a.docx --revised b.docx --output c.docx --config compare-config.json
```

---

## Exit codes

Stable contract (also printed in `--help` epilog):

| Code | Meaning |
|------|---------|
| `0` | Success; output file written. |
| `2` | Invalid CLI usage, unreadable `--config`, invalid JSON, or compare-config validation failure. |
| `10` | **Preflight** rejection (wrong file type, zip issues, existing track changes, comments, …). |
| `11` | **Document / package structure** problem (e.g. missing `word/document.xml`, XML parse errors). |
| `12` | **Compare / emit** failure or other I/O/runtime error during generation. |

Errors are written to **stderr**; stdout is not used for structured machine-readable codes—parse exit codes or stderr text as needed.

---

## Examples

Minimal run (development tree, no editable install; use your own `.docx` paths):

```bash
python -m engine.compare_cli \
  --original path/to/original.docx \
  --revised path/to/revised.docx \
  --output /tmp/compared.docx
```

With author and fixed date:

```bash
merck-compare --original o.docx --revised r.docx --output out.docx \
  --author "CI Bot" --date-iso "2026-01-15T00:00:00Z"
```

---

## Desktop integration

The **desktop** app invokes the same CLI in a subprocess (with `PYTHONPATH` pointing at the repo when run from source) and can open the output path with the OS default application when the run succeeds. See [`desktop/engine_runner.py`](../desktop/engine_runner.py).

---

## Man page

A **troff** man page ships in the repository: [`man/man1/merck-compare.1`](../man/man1/merck-compare.1).

From the repo root on many Unix systems:

```bash
man ./man/man1/merck-compare.1
```

`pip install` does not register this page in the system manual path; packagers can install it under `man1` as needed.

---

## See also

- [`README.md`](../README.md) — install, tests, golden corpus harness (separate script)
- [`CAPTURE-WORD-COMPARE-SETTINGS.md`](CAPTURE-WORD-COMPARE-SETTINGS.md) — Word baseline / settings capture notes
