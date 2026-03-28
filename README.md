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

### Golden corpus regression harness (MDC-012)

The repo includes a **config-driven harness** that runs the engine emit path on sponsor pairs under `sample-docs/` and prints **`w:ins` / `w:del` counts** per OOXML part, summarized as **document vs headers vs footers**.

- **Pair list:** `tests/fixtures/golden_corpus_pairs.json` (paths relative to `sample-docs/`). It includes at least one pair from **`email1docs`**, **`email2docs`**, and **`email3docs`** (see `sample-docs/CORPUS-INVENTORY.md`).
- **Staged rollout:** Start with a single stable pair (edit the JSON to one entry, or pass a smaller JSON via `--config`), confirm reports locally, then restore the full list for complete corpus coverage.
- **CLI** (from repo root, with sponsor `.docx` files present):

```bash
python scripts/run_golden_corpus.py --output-dir golden-corpus-output
```

- **CI:** `pytest` runs harness **unit tests** on every PR. Tests marked `golden_corpus` **skip** automatically when the large `.docx` binaries are not in the workspace; synthetic tests still validate counting and emit wiring.

Host-local option (if you prefer a local venv):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest
```

### CI (GitHub Actions)

On every push and pull request, `.github/workflows/tests.yml` runs:

- **pytest-matrix** — suite **excluding** `@pytest.mark.golden_corpus` on Python 3.12 and 3.13, with coverage artifacts.
- **golden-regression** — only `golden_corpus`-marked tests (committed `sample-docs` baselines + optional harness smoke).
- **docker-make-test** — full `pytest` inside Docker (`make test`), same as a full local run.

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

- [`docs/CAPTURE-WORD-COMPARE-SETTINGS.md`](docs/CAPTURE-WORD-COMPARE-SETTINGS.md) — Word baseline status + follow-ups  
- [`docs/PRE-PUSH-CHECKLIST.md`](docs/PRE-PUSH-CHECKLIST.md) — repo / GitHub hygiene  
- [`docs/AI-PROMPTS-INDEX.md`](docs/AI-PROMPTS-INDEX.md) — all copy/paste AI prompts
- [`docs/ADD-JIRA-TASKS-PROMPT.md`](docs/ADD-JIRA-TASKS-PROMPT.md) — generate Jira-ready task suggestions from the repo state
- [`sample-docs/`](sample-docs/) — email1/email2/email3 corpora, client process artifacts, and compare reference outputs  

**BMad epics mirror (sprint tooling):** `_bmad-output/planning-artifacts/epics-v1.md`
