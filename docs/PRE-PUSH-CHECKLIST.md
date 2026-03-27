# Repo and GitHub checklist

Use this for **ongoing** hygiene and for anyone bringing the repo to a “team-ready” state.

## Project context (keep current)

- [ ] `docs/PRODUCT-DECISIONS.md` matches agreed v1 scope.
- [ ] `docs/V1-ACCEPTANCE-CATALOG.md` matches Jira: same **`MDC-### Title`** summaries (or your project key) for active work.
- [ ] `docs/TEAM-WORKFLOW.md` and `docs/TEAM-PLAYBOOK.md` still describe how you work.
- [ ] `docs/CONTEXT-CHANGE-POLICY.md` changelog updated when governance changes.

## Word baseline (optional refinements)

- [ ] `sample-docs/email1docs/word-settings-screenshots/settings-summary.md` has **Word + OS version** filled in.
- [ ] Compare dialog options transcribed from `Compare-Documents-More.png` into `settings-summary.md`.

See `docs/CAPTURE-WORD-COMPARE-SETTINGS.md` for what is already captured vs optional follow-ups.

## GitHub

- [ ] `.github/CODEOWNERS` lists the correct GitHub user for reviews (`@DrnchedNGold`).
- [ ] `.github/workflows/tests.yml` still matches current test strategy (matrix versions, Docker path, and required checks).
- [ ] Branch protection on `main` (recommended): require PR, require review from code owners where applicable.
- [ ] Teammates have access (write or fork + PR, per your policy).
- [ ] No secrets in the repo.

## First-time teammate

- [ ] Point them at `README.md` then `docs/TEAM-PLAYBOOK.md` before their first task.
