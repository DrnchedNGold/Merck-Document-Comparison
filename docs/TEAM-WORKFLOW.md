# Team Workflow (Master-Controller Model)

This project uses a "master-controller + implementers" workflow.

## Roles
- **Master controller (you):**
  - Owns product direction and architecture decisions.
  - Defines/approves backlog tasks.
  - Accepts/rejects output quality.
- **Team implementers:**
  - Pick assigned tasks.
  - Execute implementation and tests.
  - Open PRs for review.

## Shared Context Files
All team members should read these first:
- `docs/PRODUCT-DECISIONS.md`
- `docs/TASKS-V1.md`
- `docs/CAPTURE-WORD-COMPARE-SETTINGS.md`
- `docs/CONTEXT-CHANGE-POLICY.md`

## Cursor + BMad Working Pattern
1. Pull latest `main`.
2. Open task in `docs/TASKS-V1.md`.
3. Start a focused branch for one task only.
4. In Cursor, state:
   - the task id,
   - acceptance criteria,
   - files expected to change.
5. Implement + test.
6. Open PR with task id in title/body.
7. Await master-controller review/approval.

## Guardrails
- Do not change product decisions without explicit approval.
- Do not alter default Word-compatible behavior unless task explicitly says so.
- If handling pre-existing tracked changes/comments appears, preserve current behavior: visible error and stop.
- Prefer small PRs tied to one task id.
- Any significant context/direction changes must tag `@DrnchedNGold` in PR and wait for approval.

## Suggested Branch Naming
- `task/T001-repo-scaffold`
- `task/T004-docx-parser`
- `task/T009-preexisting-revisions-validation`

## Suggested PR Template Fields
- Task ID
- Scope implemented
- Test evidence
- Known limitations
- Follow-up tasks created
