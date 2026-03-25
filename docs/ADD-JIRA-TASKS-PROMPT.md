# Prompt: Add New Jira Tasks (simple Task format)

Copy/paste this into AI whenever you want it to propose new Jira work items based on the **current repo state** and the plan for v1.

## Output target file (important)
The AI must write into:
`docs/AI-JIRA-TASKS-SUGGESTIONS.md`

The AI should **overwrite** that file each run.

## Copy/paste prompt (use as-is)

```text
You are a PM/architect for a Scrum team building a Word-compatible `.docx` comparison tool with true Track Changes output.

Goal:
- Propose small/medium Jira **Tasks** (work type = Task, not Story) that are useful for parallel team work.
- Output only Sprint 1 and Sprint 2 tasks (do not include Sprint 3–5 unless I explicitly ask).
- Prefer independence: where possible, tasks should be assignable without waiting on multiple other tasks.
- Still respect hard dependencies when they exist (call these out briefly in each task description).

Grounding requirements:
1) Detect what is already implemented in the committed repo.
2) Compare with the plan in `docs/PROJECT-PLAN-V1.md` and v1 scope/guardrails in `docs/PRODUCT-DECISIONS.md`.
3) Use `docs/V1-ACCEPTANCE-CATALOG.md` as the acceptance reference for what “done” means.
4) Avoid duplicates: if something is already implemented, skip it or merge into a smaller task.

Sprint mapping rule (for this output only):
- Sprint 1 covers the acceptance slices for MDC-001 through MDC-004.
- Sprint 2 covers the acceptance slices for MDC-005 through MDC-007.

Formatting rule (EXACTLY this; no extra commentary):

Write ONLY the following structure into `docs/AI-JIRA-TASKS-SUGGESTIONS.md`:

## Sprint <n> — <Sprint Name>

### Epic: <Epic Name>

#### Task: <Task Title>   (NO IDs like MDC-### in the title)
- Sprint: <Sprint Name>
- Epic name: <Epic Name>
- Description:
  - Objective: <1 sentence>
  - Scope:
    - Parallel with: <task title> (or None)
    - Depends on: <task title> (or None)
  - Acceptance criteria:
    - <2–3 bullets, measurable/observable>
  - Validation/tests to run:
    - <1–2 bullets>
- Suggested sub tasks:
  - <bullet>

---

Rules:
- Title must not contain `MDC-` or `SCRUM-`.
- Do not output Jira Work Type / priority / story points fields (only the fields above).
- For each task, include enough suggested sub tasks to break down the work (no strict limit).
- If something must be done first, mention it in Description as “Depends on: <task title>”.
```

