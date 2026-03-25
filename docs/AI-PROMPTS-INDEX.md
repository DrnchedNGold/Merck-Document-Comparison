# AI Prompts Index (Team Copy/Paste)

This file centralizes the copy/paste prompts used by the team in Cursor Pro + BMad.
Keep the text here as the “source of truth” to avoid drift and redundancy in other docs.

<a id="prompt-onboarding"></a>
## 1) One-time onboarding prompt (after clone)

```text
This is my first session on this repository. Load full project context before we do any tasks.

Read in order (use the repo files, don’t guess):
1. README.md
2. docs/PRODUCT-DECISIONS.md
3. docs/TEAM-WORKFLOW.md
4. docs/CONTEXT-CHANGE-POLICY.md
5. docs/TEAM-PLAYBOOK.md
6. docs/PROJECT-PLAN-V1.md (phases and milestones)
7. docs/V1-ACCEPTANCE-CATALOG.md (skim structure; acceptance criteria reference catalog)
8. sample-docs/ — note what client reference materials exist

Then give a short summary: goal, v1 scope, guardrails, and where tasks live (Jira vs docs/V1-ACCEPTANCE-CATALOG.md). Do not write code yet.
```

[Back to TEAM-WORKFLOW](TEAM-WORKFLOW.md)

<a id="prompt-start-task"></a>
## 2) Start work on a Jira task (copy-paste)

Replace the block with what Jira shows (key + title + description + acceptance criteria + attachments).

```text
I’m implementing this Jira task only. Do not push to main.

Jira: (paste task id) Ex. MDC-007
Summary: (past task summary) Ex. MDC-007 Inline diff for runs
Description:
(paste)

Acceptance criteria:
(paste)

Attachments / links:
(paste)

Before coding:
1. Read docs/PRODUCT-DECISIONS.md and confirm this task fits v1 scope.
2. If docs/V1-ACCEPTANCE-CATALOG.md has a matching section, read only that section for acceptance criteria if Jira is thin.
3. Summarize scope in 3–5 bullets and list files you expect to touch.

Then implement, add/update tests as appropriate, and run checks you can.
```

[Back to TEAM-PLAYBOOK](TEAM-PLAYBOOK.md)

<a id="prompt-context"></a>
## 3) Context beyond scope (AI background check)

Use this behavior before committing.

```text
Before committing, check:
1) Does this edit any file listed in docs/CONTEXT-CHANGE-POLICY.md under “What Counts As Project Context”?
2) Does it change product scope or defaults (platforms/filetypes/Track Changes semantics/Word parity) beyond what the Jira task says?

If yes:
- Stop. Tell the user clearly what would exceed the ticket.
- Do not silently commit context changes.
- In the PR description, add “Reviewer attention — possible out-of-scope context change” and tag the reviewer.
- If the user wants to proceed anyway, they must confirm explicitly in chat.

If no:
- Proceed normally and note “No project-context docs changed” in the PR (or satisfy the PR template checkboxes).
```

[Back to TEAM-PLAYBOOK](TEAM-PLAYBOOK.md)

<a id="prompt-ship"></a>
## 4) Ship (branch + push + open PR)

The human already provided Jira key + summary + description at task start.
The human should only say one of the following:

- “Push and open a PR”
- “Create the pull request”
- “Ship this”

Agent behavior:

```text
Push and open a PR. Jira and summary are already above in this thread.

Do:
1. Create a new branch from latest main using the Jira key + issue number + kebab-case title.
2. Commit with a message including the Jira key.
3. Push that branch only (never push directly to main).
4. Open a PR into main and fill .github/pull_request_template.md completely from:
   - Jira details from chat
   - git diff / files touched
5. If any step fails, use the troubleshooting section in TEAM-PLAYBOOK.md.
```

[Back to TEAM-WORKFLOW](TEAM-WORKFLOW.md)

<a id="prompt-push-main"></a>
## 5) Requests to push to `main` (AI must warn and confirm)

If a team member asks for `git push origin main` or “push to main”, the AI must:

```text
Warn: feature work must go on a feature branch + PR. Pushing directly to main bypasses review.

Do not run the push until the user types an unambiguous confirmation:
"Confirm: push directly to main"
```

[Back to TEAM-PLAYBOOK](TEAM-PLAYBOOK.md)

<a id="prompt-push-fail"></a>
## 6) If push or PR creation fails (troubleshooting)

```text
If the agent cannot push or create the PR, it must not invent success.
Try this fallback order:
1) Verify you have git push rights (SSH key or HTTPS credential/PAT).
2) Verify GitHub CLI exists and is logged in: gh auth login
3) If network is blocked, perform git push and PR creation manually in terminal/browser.
4) If you cloned a fork, push to your fork then open PR fork → upstream.
5) If branch name is rejected, shorten the slug.

Fallback (human):
- Push branch themselves and use GitHub “Compare & pull request”
- Paste the AI-generated PR body into the description.
```

[Back to TEAM-PLAYBOOK](TEAM-PLAYBOOK.md)

<a id="prompt-drift"></a>
## 7) If the agent drifts (scope recovery)

```text
Stop. Scope check: only what this Jira issue describes. List anything you added that is not on the ticket and remove or split to another issue.
```

[Back to TEAM-PLAYBOOK](TEAM-PLAYBOOK.md)

