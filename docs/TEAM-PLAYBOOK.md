# Team Playbook — AI + Human Workflow

Use this so everyone starts from the same context and agents don’t need you to re-explain the project.

## 30-second orientation

1. Pull latest `main`.
2. Read in order: `README.md` → `docs/PRODUCT-DECISIONS.md` → your task in `docs/TASKS-V1.md` (and matching Jira issue if you use one).
3. One branch = **one task id** (e.g. `task/T003-docx-reader`).
4. Open a PR; fill `.github/pull_request_template.md` honestly (especially **Context Impact**).

## Jira ↔ repo

- **Jira** = assignment and sprint tracking.
- **`docs/TASKS-V1.md`** = authoritative acceptance criteria and technical scope for v1.
- Put the **task id** (e.g. `T007`) in the Jira title or description so implementers can jump straight to the right section.

---

## Implementer: first message to Cursor / AI (copy-paste)

Customize `T00X` and the Jira key.

```text
You are implementing ONE task only.

Grounding (read before changing code):
- README.md
- docs/PRODUCT-DECISIONS.md
- docs/TEAM-WORKFLOW.md
- docs/CONTEXT-CHANGE-POLICY.md
- docs/TASKS-V1.md — section for task T00X only

Constraints:
- Do not change docs/PRODUCT-DECISIONS.md or broaden v1 scope unless I explicitly ask.
- Match default Word-compatible compare behavior as documented; no new product features outside this task.
- If you would add pre-existing tracked-changes handling beyond “visible error and stop”, don’t — that’s out of scope for v1.

Task: T00X (Jira: ABC-123 if applicable)

Do this:
1. Summarize acceptance criteria from TASKS-V1 for T00X in your own words (3–5 bullets).
2. Propose a minimal file/change list.
3. Implement and add or update tests as the task requires.
4. Run checks you can (format, tests, linters) and report results.

Do not ask me product questions answered in PRODUCT-DECISIONS or TASKS-V1; if something is truly ambiguous, state the gap and the smallest safe default.
```

## Implementer: follow-up if the agent drifts

```text
Stop. Scope check only T00X from docs/TASKS-V1.md. Revert or don’t add anything not in acceptance criteria. List what you’ll remove to get back to minimal scope.
```

## Master controller: direction / task update (copy-paste)

Use when you want the team or an agent to reflect a **decision**, not random code churn.

```text
Update project context as follows (then implementation can follow):

1. Edit docs/PRODUCT-DECISIONS.md with the new decision (one clear bullet).
2. If task scope shifts, edit docs/TASKS-V1.md for the affected T00X rows only.
3. Open a dedicated PR titled `docs: (short decision summary)` and tag @DrnchedNGold for review per CONTEXT-CHANGE-POLICY.

Do not implement application code in this same PR unless I say so.
```

## Master controller: small task tweak only

```text
Only update docs/TASKS-V1.md for task T00X: (what to add or clarify).
Keep PRODUCT-DECISIONS unchanged unless the v1 contract changes.
```

## PR title / description snippets

**Title:** `T00X: short description` (e.g. `T003: DOCX package reader`)

**Body opener:**

```text
Task: T00X
Jira: ABC-123 (if any)

## What changed
- ...

## Tests
- ...

## Context Impact
- [ ] No project-context docs changed
(or checklist from PR template if docs changed)
```

## BMad / skills

- Repo includes `_bmad/` for shared workflows. Use your normal BMad + Cursor setup; this playbook is the **minimal** path so any agent can work from markdown + code alone.
- For heavy BMad workflows (PRD, architecture, story generation), use the skills you already installed; product **defaults and v1 guardrails** still live in `docs/PRODUCT-DECISIONS.md`.

## When something is “missing”

1. If it’s **product scope** → master updates `PRODUCT-DECISIONS.md` + PR.
2. If it’s **task detail** → master updates `TASKS-V1.md` + PR (small is fine).
3. If it’s **implementation detail** (e.g. library version) → implementer picks a reasonable default, notes it in PR; master only intervenes if it violates decisions.
