# Merck-Document-Comparison

**Goal:** Compare two Word `.docx` files and produce a new document with **Track Changes** markup, with better behavior on tables/headers and formatting noise than a naive compare.

---

## Repo baseline scaffold

Top-level layout used for the monorepo baseline:

- `engine/` - backend/core comparison logic
- `desktop/` - desktop application shell
- `tests/` - repository-level tests

## Project setup dependencies and tools

- Python 3.12 or newer
- Docker (recommended test execution path via `make test`)
- GNU Make
- Git
- GitHub CLI (`gh`) for PR creation from terminal/agent workflows

## Install deps and run tests

Recommended (fully automated, no host Python setup required):

```bash
make test
```

This runs tests in Docker with Python 3.12+.

### Engine compare CLI (SCRUM-83)

Compare two `.docx` files and write a new document with package-wide Track Changes (`python -m engine.compare_cli` or `merck-compare` after `pip install -e .`):

```bash
python -m engine.compare_cli --original path/to/original.docx --revised path/to/revised.docx --output path/to/out.docx
```

**Full documentation:** [`docs/CLI-MERCK-COMPARE.md`](docs/CLI-MERCK-COMPARE.md) (options, exit codes, JSON config, examples). **Man page (troff):** [`man/man1/merck-compare.1`](man/man1/merck-compare.1) — e.g. `man ./man/man1/merck-compare.1` from the repo root.

Optional `--config` points to a JSON `CompareConfig` (same keys as `engine.DEFAULT_WORD_LIKE_COMPARE_CONFIG`). Exit codes: `0` success; `2` usage/config; `10` preflight; `11` document structure; `12` compare/emit or I/O. See `--help` for `--author` and `--date-iso`.

The **desktop** app runs this CLI via subprocess (with `PYTHONPATH` set to the repo root) and can open the output file when the run succeeds.

### Desktop GUI (Tk)

From the repo root:

```bash
make desktop
# or: ./scripts/run_desktop.sh
```

**macOS (Homebrew):** Plain `python3` from `brew install python@3.13` often has no `_tkinter`. Install Tk support, then use the launcher above (it prepends `$(brew --prefix python-tk@3.13)/libexec` to `PYTHONPATH` and runs `python3.13`):

```bash
brew install python-tk@3.13
```

### Troubleshooting (CLI + Desktop)

The desktop app runs the engine CLI and shows a user-friendly headline plus **Details** text on failure.
If you need to debug or file an issue, include the **exit code** and the **Details** section.

Common failures:

- **“Input documents are not eligible for compare” (exit code 10)**  
  The engine rejected one of the inputs during preflight. Typical causes:
  - file is not a valid `.docx` (or is corrupted)
  - source document already contains **Track Changes** or **comments** (v1 stops and shows an error)

- **“Invalid settings or usage” (exit code 2)**  
  The compare profile JSON was unreadable/invalid (or failed validation). Try the default profile or re-save the JSON.

- **“Document structure problem” (exit code 11)**  
  The `.docx` package is missing required parts (like `word/document.xml`) or contains malformed XML. Try re-saving the document as `.docx` in Word.

- **“Comparison failed” (exit code 12)**  
  A runtime/I/O error occurred while generating output. Retry; if it repeats, include the Details text.

### Golden corpus regression harness (MDC-012)

The repo includes a **config-driven harness** that runs the engine emit path on sponsor pairs under `sample-docs/` and prints **`w:ins` / `w:del` counts** per OOXML part, summarized as **document vs headers vs footers**.

- **Pair list:** `tests/fixtures/golden_corpus_pairs.json` (paths relative to `sample-docs/`). It includes at least one pair from **`email1docs`**, **`email2docs`**, and **`email3docs`** (see `sample-docs/CORPUS-INVENTORY.md`).
- **Snapshot baseline (ins/del counts):** `tests/fixtures/golden_corpus_expected.json` stores per-pair `summary` and `by_part` counts from `revision_counts_by_part` after emit. **`tests/test_golden_corpus_snapshot.py`** fails if the engine output drifts. **Refresh the baseline** after an intentional emit/report change:

```bash
python scripts/refresh_golden_corpus_baseline.py
```

- **Staged rollout:** Start with a single stable pair (edit the JSON to one entry, or pass a smaller JSON via `--config`), confirm reports locally, then restore the full list for complete corpus coverage.
- **CLI** (from repo root, with sponsor `.docx` files present). Default: one TSV line per pair. **`--verbose-parts`** adds per-pair `summary` and sorted `by_part` lines; **`--json`** prints structured JSON (same shape as `engine.corpus_harness.harness_batch_to_json_dict`).

```bash
python scripts/run_golden_corpus.py --output-dir golden-corpus-output
python scripts/run_golden_corpus.py --verbose-parts --output-dir golden-corpus-output
python scripts/run_golden_corpus.py --json --output-dir golden-corpus-output
```

- **CI:** The main **CI** workflow runs `pytest` excluding `golden_corpus` (fast matrix). The **Golden regression** workflow runs `pytest -m golden_corpus`. Harness logic is always covered by synthetic tests (no `sample-docs` needed). Parametrized **harness smoke** tests skip individual pairs when those paths are missing. **Corpus baseline** tests (`tests/test_sample_docs_corpus_baseline.py`) require the corresponding `sample-docs/**/*.docx` files to exist; they skip per file if a path is absent (e.g. partial clone).

Host-local option (if you prefer a local venv):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest
```

### CI (GitHub Actions)

On every push and pull request, two workflows run:

| Workflow | Purpose |
|----------|---------|
| `.github/workflows/tests.yml` (**CI**) | Guardrails, **pytest-matrix** (excludes `golden_corpus`) on Python 3.12 + 3.13 with coverage artifacts, **docker-make-test** (full `pytest` in Docker). |
| `.github/workflows/golden-regression.yml` | **Golden regression** only: `pytest -m golden_corpus` (harness smoke, corpus baselines, **snapshot count regression** vs `golden_corpus_expected.json` when `sample-docs` are present), log artifact. |

Run the golden subset locally: `python -m pytest -m golden_corpus`.

---

## Start here

| Role | Read first |
|------|------------|
| **Implementer** | [`docs/TEAM-WORKFLOW.md`](docs/TEAM-WORKFLOW.md) → [`docs/V1-ACCEPTANCE-CATALOG.md`](docs/V1-ACCEPTANCE-CATALOG.md) (pick a **`MDC-###`** issue in Jira) |
| **Reviewer / PM** | [`docs/PRODUCT-DECISIONS.md`](docs/PRODUCT-DECISIONS.md) → [`docs/CONTEXT-CHANGE-POLICY.md`](docs/CONTEXT-CHANGE-POLICY.md) |
| **Big picture** | [`docs/PROJECT-PLAN-V1.md`](docs/PROJECT-PLAN-V1.md) |

**AI + Cursor:** [`docs/TEAM-PLAYBOOK.md`](docs/TEAM-PLAYBOOK.md)  
**BMad (when to use which workflow):** [`docs/BMAD-USAGE.md`](docs/BMAD-USAGE.md)  
**Jira vs Markdown backlog:** [`docs/JIRA-AND-BACKLOG.md`](docs/JIRA-AND-BACKLOG.md)

---

## More docs

- [`docs/CLI-MERCK-COMPARE.md`](docs/CLI-MERCK-COMPARE.md) — `merck-compare` / `engine.compare_cli` user guide and exit codes  
- [`docs/CAPTURE-WORD-COMPARE-SETTINGS.md`](docs/CAPTURE-WORD-COMPARE-SETTINGS.md) — Word baseline status + follow-ups  
- [`docs/PRE-PUSH-CHECKLIST.md`](docs/PRE-PUSH-CHECKLIST.md) — repo / GitHub hygiene  
- [`docs/AI-PROMPTS-INDEX.md`](docs/AI-PROMPTS-INDEX.md) — all copy/paste AI prompts
- [`docs/ADD-JIRA-TASKS-PROMPT.md`](docs/ADD-JIRA-TASKS-PROMPT.md) — generate Jira-ready task suggestions from the repo state
- [`sample-docs/`](sample-docs/) — email1/email2/email3 corpora, client process artifacts, and compare reference outputs  

**BMad epics mirror (sprint tooling):** `_bmad-output/planning-artifacts/epics-v1.md`
