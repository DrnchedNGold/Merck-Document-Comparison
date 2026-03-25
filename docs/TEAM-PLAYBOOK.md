# Team Playbook — AI + Human Workflow

Teammates use this with Cursor Pro and BMad. **Do not commit or push** until the user asks to ship. Phrases like **“Push and open a PR”**, **“Create the pull request”**, or **“Ship this”** count as **full permission** to push the **feature branch** and open the PR — **not** to push directly to `main` (see **“Requests to push to `main`”** below).

## One-time onboarding (same as `TEAM-WORKFLOW.md`)

Use the **standard onboarding prompt** in [`AI-PROMPTS-INDEX.md → One-time onboarding`](AI-PROMPTS-INDEX.md#prompt-onboarding) after clone. One run per person per machine is enough; after that, **pull `main`** and the repo files remain the authority—the AI should re-read relevant docs when starting a new task, without repeating the full onboarding essay unless the user asks.

## Jira task format

Tickets should be easy to turn into a branch name.

- **Summary line:** `{KEY}-{number} {Short title}` — match **`docs/V1-ACCEPTANCE-CATALOG.md`** for backlog work (e.g. **`MDC-001 Monorepo scaffold and README`**) or your ad-hoc Jira title.

**Git branch name** — `{KEY}-{number}-{kebab-title}`: hyphens, no spaces; **key and number as in Jira**. Title segment casing is **your choice**.

| Jira summary (example) | Branch (examples) |
|------------------------|-------------------|
| `MDC-001 Monorepo scaffold and README` | `MDC-001-monorepo-scaffold-and-readme` |
| `MDC-007 Inline diff for runs` | `MDC-007-inline-diff-for-runs` |
| `MDC-24 Add a dark mode toggle` | `MDC-24-add-a-dark-mode-toggle` |

Paste into chat when you start work:

- Issue key (e.g. `MDC-24`)
- Summary/title (full line above)
- Description, acceptance criteria, attachments, links
- Any files/components the ticket names

## Start work on a task (copy-paste)

Replace the block with what Jira shows.

Copy the **“Start work on a Jira task”** prompt from [`AI-PROMPTS-INDEX.md → Start task`](AI-PROMPTS-INDEX.md#prompt-start-task).

## Context beyond task scope (AI / BMad — background check)

Before committing, use the **“Context beyond scope”** prompt from [`AI-PROMPTS-INDEX.md → Context beyond scope`](AI-PROMPTS-INDEX.md#prompt-context).

## Requests to push to `main`

Use [`AI-PROMPTS-INDEX.md → Requests to push to main`](AI-PROMPTS-INDEX.md#prompt-push-main).

## Ship: what the human says (default)

Copy the ship prompt from [`AI-PROMPTS-INDEX.md → Ship`](AI-PROMPTS-INDEX.md#prompt-ship).

## If push or PR creation fails

Use [`AI-PROMPTS-INDEX.md → If push or PR creation fails`](AI-PROMPTS-INDEX.md#prompt-push-fail).

## If the agent drifts
Use [`AI-PROMPTS-INDEX.md → If the agent drifts (scope recovery)`](AI-PROMPTS-INDEX.md#prompt-drift).

## Reviewer note

Product direction and approval of context-changing PRs are handled by a **reviewer** (see `docs/CONTEXT-CHANGE-POLICY.md`). This playbook does not define reviewer duties—only how implementers and AI escalate.

## BMad

Use BMad skills when your team’s process calls for them. **Guardrails** in `docs/PRODUCT-DECISIONS.md` and **scope** on the Jira issue still win over ad-hoc agent suggestions.
