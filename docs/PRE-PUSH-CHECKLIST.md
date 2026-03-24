# Pre-Push Checklist (First Team-Ready Push)

Use this before pushing so teammates can clone and start tasks immediately.

## Repo content

- [ ] `docs/PRODUCT-DECISIONS.md` reflects current v1 scope and constraints.
- [ ] `docs/TASKS-V1.md` is up to date (or matches what you copied into Jira).
- [ ] `docs/TEAM-WORKFLOW.md` and `docs/CONTEXT-CHANGE-POLICY.md` are committed.
- [ ] `docs/CAPTURE-WORD-COMPARE-SETTINGS.md` includes corrected navigation (Markup path) if different from client PDF.
- [ ] `sample-docs/` contains client materials (PDF, diversity plan pairs, expected compare outputs).
- [ ] **Word baseline:** Screenshots live under `sample-docs/word-settings-screenshots/` (see naming in capture doc).
- [ ] **Word baseline:** `sample-docs/word-settings-screenshots/settings-summary.md` lists Word version, Windows build, and every checkbox value you care to mirror in software.

## GitHub

- [ ] `.github/CODEOWNERS` uses your real GitHub username (update if not `DrnchedNGold`).
- [ ] Branch protection on `main` (recommended): require PR, require review from code owners for protected paths, optional status checks once CI exists.
- [ ] Teammates invited with **write** access (or fork + PR workflow documented).
- [ ] No secrets in repo (no API keys, tokens, or client confidential paths you should not share).

## Optional before push

- [ ] `README.md` points at all context docs (already should).
- [ ] One commit message that makes clear: “Initial context + samples for team execution.”

## After first push (you said next)

- [ ] Add `docs/TEAM-PLAYBOOK.md` (copy/paste prompts for you vs teammates).
- [ ] Post in team channel: clone URL, “read docs in README order,” and Jira board link.
