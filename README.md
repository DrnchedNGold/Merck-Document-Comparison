# Merck-Document-Comparison

**Goal:** Compare two Word `.docx` files and produce a new document with **Track Changes** markup, with better behavior on tables/headers and formatting noise than a naive compare.

---

## Repo baseline scaffold

Top-level layout used for the monorepo baseline:

- `engine/` - backend/core comparison logic
- `desktop/` - desktop application shell
- `tests/` - repository-level tests

## Install deps and run tests

Recommended (fully automated, no host Python setup required):

```bash
make test
```

This runs tests in Docker with Python 3.12+.

Host-local option (if you prefer a local venv):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest
```

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
