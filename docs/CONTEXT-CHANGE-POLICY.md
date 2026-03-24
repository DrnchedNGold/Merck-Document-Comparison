# Context Change Policy

Use this policy to keep team members aligned and ensure master-controller approval for significant context changes.

## What Counts As "Project Context"
- `docs/PRODUCT-DECISIONS.md`
- `docs/TEAM-WORKFLOW.md`
- `docs/TASKS-V1.md`
- `docs/CAPTURE-WORD-COMPARE-SETTINGS.md`
- `docs/TEAM-PLAYBOOK.md` (team process and AI prompts)
- `README.md` (context links and project framing)

## Rules
1. Any PR that changes project context must tag `@DrnchedNGold`.
2. Context-changing PRs must explain:
   - what changed,
   - why it changed,
   - impact on implementation tasks.
3. No teammate should treat context changes as final until master-controller approval.
4. Significant direction changes should be split into a dedicated PR.

## Significant Change Triggers
Treat these as significant and require explicit verification:
- Changes to scope (supported file types, platforms, or v1/v2 boundaries).
- Changes to output behavior (Track Changes semantics, Word parity defaults).
- Changes to team workflow or authority model.
- Changes that invalidate existing task acceptance criteria.

## Changelog (Context Decisions)
Keep a short history of significant context updates.

- 2026-03-24: Initial policy created. Master-controller model and Word-parity v1 scope in effect.
- 2026-03-24: Added `docs/TEAM-PLAYBOOK.md` for shared AI/human prompts; listed under project context files.
