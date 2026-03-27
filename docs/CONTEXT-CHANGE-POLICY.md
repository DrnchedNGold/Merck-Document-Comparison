# Context Change Policy

Use this policy so **project context** stays controlled and **reviewers** can approve meaningful changes.

## What Counts As "Project Context"
- `docs/PROJECT-PLAN-V1.md`
- `docs/PRODUCT-DECISIONS.md`
- `docs/TEAM-WORKFLOW.md`
- `docs/V1-ACCEPTANCE-CATALOG.md`
- `docs/CAPTURE-WORD-COMPARE-SETTINGS.md`
- `docs/TEAM-PLAYBOOK.md` (team process and AI prompts)
- `docs/BMAD-USAGE.md` (BMad workflow pointers)
- `README.md` (context links and project framing)

## Rules
1. Any PR that changes project context must tag **`@DrnchedNGold`** (or the designated reviewer).
2. Context-changing PRs must explain:
   - what changed,
   - why it changed,
   - impact on implementation tasks.
3. No one should treat context changes as final until **reviewer approval**.
4. Significant direction changes should be split into a dedicated PR.

## Significant Change Triggers
Treat these as significant and require explicit verification:
- Changes to scope (supported file types, platforms, or v1/v2 boundaries).
- Changes to output behavior (Track Changes semantics, Word parity defaults).
- Changes to team workflow or review model.
- Changes that invalidate existing task acceptance criteria.

## Changelog (Context Decisions)
Keep a short history of significant context updates.

- 2026-03-24: Initial policy created. Reviewer-gated context and Word-parity v1 scope in effect.
- 2026-03-24: Added `docs/TEAM-PLAYBOOK.md` for shared AI/human prompts; listed under project context files.
- 2026-03-24: Team workflow updated: Jira-first tasks, feature branches + PRs (not direct `main`), reviewer wording; AI escalation for out-of-scope context edits.
- 2026-03-24: Added `docs/PROJECT-PLAN-V1.md` and expanded `docs/V1-ACCEPTANCE-CATALOG.md` with sprint/phase mapping; internal planning IDs use **MDC-###**.
- 2026-03-26: SCRUM-40 corpus update: recognized combined `email1docs/` + `email2docs/` samples, added `sample-docs/CORPUS-INVENTORY.md`, and aligned sample-doc path references in docs.
- 2026-03-26: SCRUM-40 expanded with `email3docs/` (Protocol + IB corpus); updated planning/context docs and corpus expectations to include all three email sample sets.
- 2026-03-27: SCRUM-48 added Sprint 2 implementation map to `docs/PROJECT-PLAN-V1.md` and `docs/SCRUM-48-SPRINT2-AUDIT.md` for MDC-005–007 verification traceability.
