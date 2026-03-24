# Team Playbook — AI + Human Workflow

Teammates use this with Cursor Pro and BMad. **Do not commit or push** until the user asks to ship. Phrases like **“Push and open a PR”**, **“Create the pull request”**, or **“Ship this”** count as **full permission** to push the **feature branch** and open the PR — **not** to push directly to `main` (see **“Requests to push to `main`”** below).

## One-time onboarding (same as `TEAM-WORKFLOW.md`)

Use the **standard onboarding prompt** in `docs/TEAM-WORKFLOW.md` after clone. One run per person per machine is enough; after that, **pull `main`** and the repo files remain the authority—the AI should re-read relevant docs when starting a new task, without repeating the full onboarding essay unless the user asks.

## Jira task format

Tickets should be easy to turn into a branch name.

- **Summary line:** `{KEY}-{number} {Short title}`  
  Example: `MDC-24 Add a dark mode toggle`

**Git branch name** — `{KEY}-{number}-{kebab-title}`: hyphens, no spaces; **key and number as in Jira**. Title segment casing is **your choice** (all lowercase, title case, etc.).

| Jira summary (example) | Branch (examples) |
|------------------------|-------------------|
| `MDC-24 Add a dark mode toggle` | `MDC-24-add-a-dark-mode-toggle` or `MDC-24-Add-A-Dark-Mode-Toggle` |
| `MDC-152 Remove scrollbar` | `MDC-152-remove-scrollbar` or `MDC-152-Remove-Scrollbar` |
| `MDC-73 Update team docs` | `MDC-73-update-team-docs` or `MDC-73-Update-Team-Docs` |

Paste into chat when you start work:

- Issue key (e.g. `MDC-24`)
- Summary/title (full line above)
- Description, acceptance criteria, attachments, links
- Any files/components the ticket names

## Start work on a task (copy-paste)

Replace the block with what Jira shows.

```text
I’m implementing this Jira task only. Do not push to main.

Jira: MDC-24
Summary: MDC-24 Add a dark mode toggle
Description:
(paste)

Acceptance criteria:
(paste)

Attachments / links:
(paste)

Before coding:
1. Read docs/PRODUCT-DECISIONS.md and confirm this task fits v1 scope.
2. If docs/TASKS-V1.md has a matching section, read only that section for extra acceptance language.
3. Summarize scope in 3–5 bullets and list files you expect to touch.

Then implement, add/update tests as appropriate, and run checks you can.
```

## Context beyond task scope (AI / BMad — background check)

**Before committing**, the agent should check:

- Does this work **edit any file** listed in `docs/CONTEXT-CHANGE-POLICY.md` under “What Counts As Project Context”?
- Does it **change product scope or defaults** (platforms, file types, Track Changes semantics, Word parity) beyond what the Jira task says?

If **yes**:

1. **Stop** and tell the user clearly: what file or behavior would exceed the ticket.
2. **Do not** silently commit context changes.
3. In the eventual PR description, add a prominent **“Reviewer attention — possible out-of-scope context change”** section and **@DrnchedNGold** (or the reviewer your team uses).
4. If the user wants to proceed anyway, they must confirm in chat; still tag the reviewer on the PR.

If **no**: proceed and note in the PR body **“No project-context docs changed”** (or use the PR template checkboxes).

## Requests to push to `main` (AI must warn and confirm)

If the user (or a suggested command) would **push commits directly to `main`** — e.g. `git push origin main`, “push to main”, “merge my branch into main locally and push”, or being checked out on `main` with unpushed commits intended for `origin/main`:

1. **Do not run the push** immediately.
2. **Warn** clearly: normal task work must use a **named feature branch** and a **PR**; pushing straight to `main` bypasses review and breaks team workflow (`docs/TEAM-WORKFLOW.md`).
3. **Offer the default path:** create/use the Jira-based branch, push that branch, open a PR into `main`.
4. **Ask for explicit confirmation** to proceed with a direct `main` push anyway, e.g. require the user to type something unambiguous like **“Confirm: push directly to main”** or **“I accept pushing to main; proceed.”** Vague “ok” or “yes” alone is not enough — repeat what you are about to run and ask again.
5. If they **do not** give that explicit confirmation, **only** execute the branch + PR flow (or stop).

**Exception:** Trivial docs-only hotfixes *might* be allowed by your team; still use the same warning + explicit confirmation unless `docs/PRODUCT-DECISIONS.md` or reviewer policy says otherwise.

## Ship: what the human says (default)

The human already provided **Jira key + summary + description** when the task started. They should only need to say one of:

- **“Push and open a PR”** / **“Create the pull request”** / **“Ship this”**

**Agent behavior:** Use the **Jira key and summary from this conversation** (re-read the thread if needed). Do **not** ask the human to re-paste the ticket unless something is genuinely missing (e.g. no key was ever given).

1. Base on latest `main` (pull/rebase as appropriate).
2. Create a **new branch** using the **Jira key + number + kebab-case title** rule (see table under “Jira task format”). Examples: `MDC-24-add-a-dark-mode-toggle`, `MDC-152-remove-scrollbar`, `MDC-73-update-team-docs` (or the same with title-style caps if the team prefers).
3. Commit with a message that includes the Jira key (e.g. `MDC-24: …`).
4. **Push this branch only** (never `main`). **“Push and open a PR”** (or equivalent) is enough permission — do not ask for a second push approval.
5. **Create the PR** to `main` and **fully populate** `.github/pull_request_template.md` from: Jira details in chat + `git diff` + files touched. Include Jira URL if the human pasted it; otherwise construct a clear **Jira: MDC-24** line and description.

### Ship (optional explicit prompt)

Use only if the human prefers to paste once more:

```text
Push and open a PR. Jira and summary are already above in this thread.
Branch: slug from MDC-24 + title (kebab-case). Fill the PR template completely.
```

## If push or PR creation fails

The AI **cannot** push or open a PR unless **your machine and accounts** allow it. Common causes and fixes:

| Issue | What to do |
|--------|------------|
| **No `git` push rights** | Confirm GitHub access to the repo; for HTTPS use a credential helper or PAT with `repo` scope; for SSH ensure `ssh -T git@github.com` works and your key is added to GitHub. |
| **`gh` not installed** | Install [GitHub CLI](https://cli.github.com/), run `gh auth login`, then the agent can use `gh pr create` with a filled body. |
| **`gh` not logged in** | Run `gh auth login` (same browser/account as the repo). |
| **Org SSO / token** | Some orgs require authorizing the PAT or SSH key for SSO (GitHub → Settings → SSH and GPG keys / Fine-grained tokens). |
| **Agent sandbox / no network** | Cursor (or the tool environment) may block network. Run `git push` and `gh pr create` **locally in your terminal**, or approve agent steps that request network permissions. |
| **Fork workflow** | If you cloned a **fork**, push to **your fork’s branch**, then open PR **fork → upstream**; tell the AI which remote is `origin`. |
| **Branch name rejected** | Extremely long names or reserved characters: shorten slug (keep `KEY-###-` prefix + short title). |

**Fallback (human, ~2 minutes):** Push the branch yourself (`git push -u origin <branch>`), then on GitHub use **“Compare & pull request”** and paste a PR body the AI generated into the description field.

If you want **one-command PRs** for the whole team, standardize on: **GitHub CLI installed + `gh auth login` + HTTPS or SSH push working** for this repository.

## If the agent drifts

```text
Stop. Scope check: only what Jira MDC-24 describes. List anything you added that is not on the ticket and remove or split to another issue.
```

## Reviewer note

Product direction and approval of context-changing PRs are handled by a **reviewer** (see `docs/CONTEXT-CHANGE-POLICY.md`). This playbook does not define reviewer duties—only how implementers and AI escalate.

## BMad

Use BMad skills when your team’s process calls for them. **Guardrails** in `docs/PRODUCT-DECISIONS.md` and **scope** on the Jira issue still win over ad-hoc agent suggestions.
