# Using BMad in This Repo

BMad lives in `_bmad/` (workflows + agents). **Use it whenever it saves time** on planning, stories, reviews, and tests—not only for coding.

## When to use which workflow

| Your goal | BMad skill / workflow (Cursor) | Notes |
|-----------|-------------------------------|--------|
| **Backlog & execution order** | You already have `docs/PROJECT-PLAN-V1.md` + `docs/V1-ACCEPTANCE-CATALOG.md`. Optional: `bmad-sprint-planning` after epics exist. | Sprint planning reads `*_bmad-output/planning-artifacts/*epic*.md`. |
| **Epics / stories from PRD** | `bmad-create-epics-and-stories`, `bmad-create-story` | Use if you formalize a PRD; sync outputs with `docs/V1-ACCEPTANCE-CATALOG.md` and Jira. |
| **Architecture decisions** | `bmad-create-architecture` | Before major engine/API choices. |
| **Implementation** | `bmad-dev-story`, `bmad-quick-dev-new-preview` | Per Jira issue; still follow `docs/TEAM-PLAYBOOK.md`. |
| **Code review** | `bmad-code-review`, `bmad-review-edge-case-hunter` | On PRs or before merge. |
| **Tests / CI** | `bmad-testarch-*` (TEA module) | After you have code + CI skeleton. |
| **Unsure what to run** | `bmad-help` | Routes to next workflow. |

## Planning artifacts (BMad + this project)

- **Human-readable plan:** `docs/PROJECT-PLAN-V1.md`
- **Jira-ready tasks:** `docs/V1-ACCEPTANCE-CATALOG.md` (summaries = **`MDC-### Title`**)
- **BMad epic mirror (for sprint tooling):** `_bmad-output/planning-artifacts/epics-v1.md`

Keep **one source of truth** for acceptance criteria: `docs/V1-ACCEPTANCE-CATALOG.md`. If BMad generates new stories, **merge or link** them there and in Jira.

## Config

BMad BMM config: `_bmad/bmm/config.yaml` — `planning_artifacts` and `implementation_artifacts` point at `_bmad-output/`. `project_knowledge` includes `docs/`.
