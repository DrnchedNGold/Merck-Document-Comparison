# V1 Acceptance Criteria Catalog (Reference)

This file defines what **each v1-scope task must achieve** (acceptance criteria) so the team implements consistently.
It is a **reference catalog**, not the live Jira backlog.

## Story Points (quick explanation)

**Story points** are a *relative* measure of complexity/effort for a user story (not calendar time).
Teams typically estimate points based on how hard the work is compared to other work.

In this repo we also use `S|M|L` estimates as a simple size proxy:

- `S` = small (~0.5–1 day)
- `M` = medium (~1–2 days)
- `L` = large (>2 days)

If your Jira uses story points, map them however your team does; the acceptance criteria still define correctness.

## How sprints map to phases

Phases come from `docs/PROJECT-PLAN-V1.md`. Sprints below group tasks into ~5 Scrum sprint windows.

## Sprint 1 — Foundation (Phase 0)

### MDC-001 Monorepo scaffold and README

Acceptance criteria

- Top-level dirs: `engine/`, `desktop/`, `tests/` (or document your chosen layout)
- `README.md`: Python version, how to install engine deps, how to run tests (placeholder `pytest` OK)
- No secrets committed
Estimate: `S`

### MDC-002 Engine data contracts

Acceptance criteria

- Documented models or JSON Schema for: body IR, diff op list, compare config
- One example fixture (tiny paragraph trees + expected diff ops)
Estimate: `M`

### MDC-003 DOCX body ingest

Acceptance criteria

- Open valid `.docx`, parse `word/document.xml` → body IR
- Unit test on a minimal docx fixture
- Graceful handling when `document.xml` is missing
Estimate: `M`

### MDC-004 Preflight validation

Acceptance criteria

- Reject non-`.docx` with a clear error message
- Detect pre-existing tracked changes/comments and stop with visible error (v1 policy)
- Unit tests for happy path + each failure mode
Estimate: `S`

## Sprint 2 — Body compare (Phase 1)

### MDC-005 Normalization and compare keys

Acceptance criteria

- Config object wired from a default “Word-like” profile (JSON stub OK)
- Unit tests: formatting-only changes don’t break alignment when configured to ignore formatting noise
Estimate: `M`

### MDC-006 Paragraph alignment

Acceptance criteria

- Deterministic alignment on fixtures (insert / delete / small reorder)
- Short note on algorithm choice (engine README or docstring)
Estimate: `M`

### MDC-007 Inline diff for runs

Acceptance criteria

- Output ordered diff ops consumable by a renderer (stub renderer OK)
- Deterministic outputs on repeated runs
- Tests for insert, delete, replace within one paragraph
Estimate: `M`

## Sprint 3 — Structured content + minimal Track Changes (Phase 2 + 3.1)

### MDC-008 Tables in IR and table diff

Acceptance criteria

- IR extension for tables; parse common `document.xml` table shapes
- Tests with a small table fixture
Estimate: `M`

### MDC-009 Headers and footers

Acceptance criteria

- Load header/footer parts into IR or parallel structures
- Test/golden check that revisions can target the correct `word/header*.xml` / `word/footer*.xml` parts
Estimate: `M`

### MDC-010 Track Changes: body `w:ins` / `w:del`

Acceptance criteria

- New `.docx` output opens in Word (trivial body-only case)
- Test: output XML contains expected `w:ins` / `w:del` markers for fixture diffs
Estimate: `L`

## Sprint 4 — Output metadata + verification (Phase 3.2 + 4)

### MDC-011 Revision metadata and header/footer emit

Acceptance criteria

- Valid OOXML revision attributes present (e.g. `w:id`, `w:author`, `w:date`) per v1 rule/config
- Header/footer parts receive revisions where the diffs exist
Estimate: `M`

### MDC-012 Golden corpus harness

Acceptance criteria

- Script/pytest module runs engine against `sample-docs` pairs (paths configurable)
- Coverage includes `sample-docs/email1docs/`, `sample-docs/email2docs/`, and `sample-docs/email3docs/` sources
- Report revision counts/locations by part (document vs headers)
- README note: start with one stable pair, then expand to all corpora
Estimate: `M`

### MDC-013 CI pipeline

Acceptance criteria

- CI runs `pytest` on PR/push
- Golden regression job is included (full or smoke subset documented)
Estimate: `S`

## Sprint 5 — Desktop MVP + hardening (Phase 5 + 6 stretch)

### MDC-014 Desktop shell and file pickers

Acceptance criteria

- App launches and shows UI with Original + Revised pickers
- Compare can be stubbed (engine integration comes next)
Estimate: `S`

### MDC-015 Engine CLI and open output

Acceptance criteria

- Engine exposed as CLI (args: original, revised, output, optional config; stable exit codes)
- Desktop invokes CLI, surfaces errors (preflight + runtime) and “Open output” works
Estimate: `M`

### MDC-016 Settings profiles UI

Acceptance criteria

- Profile JSON load/save; UI edits drive CLI/config
- Default Word-compatible profile exists and is documented
Estimate: `M`

### MDC-017 Error UX and logging

Acceptance criteria

- Map engine stderr/exit codes to human-readable messages
- Troubleshooting section in README
Estimate: `S`

### MDC-018 Move detection (stretch)

Acceptance criteria

- Either produce one move-markup fixture (`w:moveFrom`/`w:moveTo`) OR document fallback to del+ins
- Optional: can be deferred beyond first v1 demo; note in Jira/PR if skipped
Estimate: `L` (or `M` if just documented fallback)

## Notes

- Phase definitions + overall narrative: `docs/PROJECT-PLAN-V1.md`
- Product rules/guardrails: `docs/PRODUCT-DECISIONS.md`

