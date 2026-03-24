# Team Workflow

This document is for **everyone implementing work** after clone, BMad, and Cursor Pro are set up.

## One-time: load project context into the AI

After you clone the repo, run **once** in Cursor chat (or your usual AI panel). You do not need to repeat this for every task; later sessions stay aligned by reading files in the repo when you work.

**Standard onboarding prompt (copy-paste):**

```text
This is my first session on this repository. Load full project context before we do any tasks.

Read in order (use the repo files, don’t guess):
1. README.md
2. docs/PRODUCT-DECISIONS.md
3. docs/TEAM-WORKFLOW.md (this file)
4. docs/CONTEXT-CHANGE-POLICY.md
5. docs/TEAM-PLAYBOOK.md
6. docs/TASKS-V1.md (skim structure; you’ll deep-read per task later)
7. sample-docs/ — note what client reference materials exist

Then give a short summary: goal, v1 scope, guardrails, and where tasks live (Jira vs docs/TASKS-V1.md). Do not write code yet.
```

The AI (and BMad, when you invoke it) should use **what is committed in the repo** as source of truth. Pull `main` when it moves so your workspace matches the latest context.

## Every task: start from Jira

1. Pull the latest `main`.
2. In **Jira**, open the issue you are taking.
3. Paste into chat **everything the issue gives you** (and anything your lead added): **issue key**, **summary/title**, **description**, **acceptance criteria**, links, attachments, and any named files or areas to touch.

You should not have to hunt for scope in chat if it is already on the ticket.

## While you work

- Stay within the Jira task. If the AI suggests changes that **clearly go beyond** that scope—especially edits to project context files listed in `docs/CONTEXT-CHANGE-POLICY.md`—it should **stop**, explain the gap, and **flag the reviewer** (see playbook: context escalation). You keep working only after scope is clarified or the reviewer approves.
- Follow product guardrails in `docs/PRODUCT-DECISIONS.md` (Word-compatible defaults, Track Changes output, v1 `.docx` only, etc.).

## When you are done: one short message to the AI (not `main`)

You already pasted the **Jira key, summary/title, and task body** at the start of the task. You should **not** need to paste them again or fill out the PR by hand.

Do **not** push task work directly to `main`. If you ask the AI to push to `main` anyway, it should **warn you**, restate this policy, and **ask for explicit confirmation** before running any push to `main` (see `docs/TEAM-PLAYBOOK.md`).

Tell the AI something short, for example:

- **“Push and open a PR”** (this alone is enough for the full ship: branch, push, and PR — no extra approval step)
- **“Create the pull request”**  
- **“Ship this”**

The AI should then, using **this chat thread + the repo** (Jira details you already provided):

1. Create a **new branch** using the **branch naming rule** below (Jira key + issue number + kebab-case words from the title; **no spaces**).
2. **Commit** the work with a message that references the Jira key.
3. **Push that branch only** (never `main`).
4. **Open a Pull Request** into `main` and **fill** `.github/pull_request_template.md` completely: Jira link, branch name, scope, tests, context-impact checkboxes, and reviewer tags when required by `docs/CONTEXT-CHANGE-POLICY.md`.

### Branch naming rule (examples)

Pattern: **`{KEY}-{number}-{short-description-in-kebab-case}`** — hyphens between words, **no spaces**. Use the **key and number exactly as in Jira**. For the title segment, **letter case is not prescribed** (e.g. all lowercase or title-style caps are both fine; stay consistent with your Jira summary if you prefer).

| Jira summary (example) | Branch name (examples) |
|------------------------|------------------------|
| `MDC-24 Add a dark mode toggle` | `MDC-24-add-a-dark-mode-toggle` or `MDC-24-Add-A-Dark-Mode-Toggle` |
| `MDC-152 Remove scrollbar` | `MDC-152-remove-scrollbar` or `MDC-152-Remove-Scrollbar` |
| `MDC-73 Update team docs` | `MDC-73-update-team-docs` or `MDC-73-Update-Team-Docs` |

Drop filler words only if needed to keep the slug readable.

A **reviewer** will review and merge. You do not merge your own PR unless your team policy says otherwise.

If the AI says it **cannot** push or create the PR, see **`docs/TEAM-PLAYBOOK.md` → “If push or PR creation fails”**.

## Where extra detail lives

- **Jira** — what you are doing *now* (key, title, description, acceptance criteria).
- **`docs/TASKS-V1.md`** — backlog shape and technical acceptance language for v1; use it when the ticket points there or when you need the full task write-up.
- **`docs/TEAM-PLAYBOOK.md`** — copy-paste prompts for tasks, shipping, and scope recovery.

## Guardrails (quick reference)

- **Pushing to `main`:** Task work belongs on a **feature branch + PR**. If someone asks to push to `main`, the AI must **warn**, explain why `main` is protected by team policy, and **require explicit confirmation** before any `git push` targeting `main` (full behavior in `docs/TEAM-PLAYBOOK.md`).
- Do not change product direction files on your own if the task does not explicitly include that work; if unsure, see context escalation in `docs/TEAM-PLAYBOOK.md`.
- Do not alter default Word-compatible behavior unless the task says so.
- Pre-existing tracked changes/comments in source docs: **visible error and stop** (v1); do not “fix” that in a random task without a ticket.
