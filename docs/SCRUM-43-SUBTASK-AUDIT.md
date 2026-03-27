# SCRUM-43 — Sprint 1 subtasks through MDC-006 (Paragraph alignment)

**Purpose:** Map every suggested subtask in `docs/AI-JIRA-TASKS-SUGGESTIONS.md` (through **Paragraph alignment** only; **Inline diff / MDC-007** is out of scope for this audit) to current repo state and record implement vs defer vs skip.

**v1 scope check:** `docs/PRODUCT-DECISIONS.md` — foundation + body IR, preflight, compare keys, and paragraph alignment are in v1; this audit does not add batch mode, non-docx formats, or handling of pre-existing track changes beyond preflight.

---

## Summary

| Area | Verdict |
|------|---------|
| **MDC-001 Monorepo** | All suggested subtasks **done** (layout, pytest wiring, README). |
| **MDC-002 Contracts** | All **done** (`engine/CONTRACTS.md`, fixture + tests, default compare config stub). |
| **MDC-003 DOCX ingest** | All **done** (ingest, tests happy + missing `document.xml`, clear errors). |
| **MDC-004 Preflight** | All **done** (non-docx, tracked changes/comments, deterministic errors, tests per mode). |
| **MDC-005 Compare keys** | All **done** (keys, formatting-ignore tests, default Word-like profile in contracts). |
| **MDC-006 Paragraph alignment** | Code + tests **done**; **brief algorithm/limits note** added in `engine/paragraph_alignment.py` module docstring (see below). |
| **MDC-007 Inline diff** | **Out of scope** for this ticket — not audited in detail. |

**Recommendation:** No additional code subtasks are **required** for Sprint 1 through MDC-006. Optional **later** work (not blocking v1 acceptance for these items): corpus-level regression harness expansion, CLI/desktop surfacing of preflight errors, and MDC-007+ features per `docs/V1-ACCEPTANCE-CATALOG.md`.

---

## Per–suggested-subtask checklist

### MDC-001 Monorepo scaffold

| Suggested subtask | Status | Notes |
|-------------------|--------|--------|
| Add/confirm `engine/`, `desktop/`, `tests/` | **Done** | Present; documented in root `README.md`. |
| Minimal test runner (placeholder pytest OK) | **Done** | `pytest` + `tests/`; `make test` for Docker path. |
| README dev/test instructions match layout | **Done** | README lists dirs and install/test commands. |

### MDC-002 Engine data contracts

| Suggested subtask | Status | Notes |
|-------------------|--------|--------|
| Document body IR and diff op list | **Done** | `engine/CONTRACTS.md` + `engine/contracts.py`. |
| Tiny fixture + expected diff ops | **Done** | `tests/test_engine_contracts.py` + fixtures in contracts module. |
| Default Word-like compare config shape | **Done** | `DEFAULT_WORD_LIKE_COMPARE_CONFIG` in `engine/contracts.py`. |

### MDC-003 DOCX body ingest

| Suggested subtask | Status | Notes |
|-------------------|--------|--------|
| DOCX open + `document.xml` extraction | **Done** | `engine/docx_body_ingest.py`. |
| Body XML → body IR + unit tests | **Done** | `tests/test_docx_body_ingest.py`. |
| Clear error for missing/invalid `word/document.xml` | **Done** | Dedicated exceptions + tests. |

### MDC-004 Preflight validation

| Suggested subtask | Status | Notes |
|-------------------|--------|--------|
| Detect tracked changes/comments; clear error | **Done** | `engine/preflight_validation.py`. |
| Unit tests for each failure mode | **Done** | `tests/test_docx_preflight_validation.py`. |
| Deterministic errors for CLI/desktop | **Done** | Structured result / stable messages where tested. |

### MDC-005 Normalization + compare keys

| Suggested subtask | Status | Notes |
|-------------------|--------|--------|
| Compare-key generation | **Done** | `engine/compare_keys.py`. |
| Tests: formatting-only edits don’t break alignment | **Done** | `tests/test_compare_keys.py`. |
| Default ignore toggles (stub OK) | **Done** | Wired via `CompareConfig` + defaults. |

### MDC-006 Paragraph alignment

| Suggested subtask | Status | Notes |
|-------------------|--------|--------|
| Paragraph alignment algorithm | **Done** | LCS over paragraph signatures in `engine/paragraph_alignment.py`. |
| Deterministic fixtures (insert/delete/reorder) | **Done** | `tests/test_paragraph_alignment.py`. |
| Brief note on assumptions/limits | **Done** | Module docstring in `engine/paragraph_alignment.py` (this SCRUM-43 change). |

---

## Team decision (manual)

**Decision recorded for SCRUM-43:** Treat all Sprint-1-through-MDC-006 suggested subtasks as **implemented or satisfied** in repo; **skip** further feature work on this ticket. **Defer** MDC-007 and beyond to their own issues.
