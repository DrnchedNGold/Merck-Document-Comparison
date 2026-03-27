# SCRUM-48 — Sprint 2 (Phase 1 body compare) verification

**Purpose:** Confirm Sprint 2 in `docs/V1-ACCEPTANCE-CATALOG.md` (MDC-005, MDC-006, MDC-007) is implemented and map suggested subtasks from `docs/AI-JIRA-TASKS-SUGGESTIONS.md`. Record optional follow-ups.

**v1 scope:** `docs/PRODUCT-DECISIONS.md` — body-level compare for `.docx` is in v1; this audit is documentation and verification only (no product direction change).

---

## Summary

| Task | Catalog ID | Verdict |
|------|------------|---------|
| Normalization + compare keys | MDC-005 | **Done** — `engine/compare_keys.py`, `DEFAULT_WORD_LIKE_COMPARE_CONFIG` in `engine/contracts.py`, tests in `tests/test_compare_keys.py`. |
| Paragraph alignment | MDC-006 | **Done** — `engine/paragraph_alignment.py` (LCS + algorithm/limits in module docstring), tests in `tests/test_paragraph_alignment.py`. |
| Inline diff for runs | MDC-007 | **Done** — `engine/inline_run_diff.py` (`inline_diff_single_paragraph`), paths per `engine/CONTRACTS.md`, tests in `tests/test_inline_run_diff.py`. |

**Suggested subtasks (Sprint 2 section of AI-JIRA-TASKS-SUGGESTIONS):** All listed items have matching implementation or tests. No mandatory Jira follow-ups for Sprint 2 closure.

---

## Optional follow-ups (not required to close Sprint 2)

These are **engineering hardening** or **later orchestration**, not acceptance gaps for MDC-005–007.

1. **Full-body orchestration:** Implemented as optional API in `engine/body_compare.py` (`matched_paragraph_inline_diffs`, `single_paragraph_body`). See `docs/AI-JIRA-TASKS-SUGGESTIONS.md` — Sprint 2 optional task **Full-body compare orchestration** for Jira wording.
2. **Alignment vs run-split:** Still **open optional** work — paragraph signatures depend on per-run compare keys; same concatenated text with different run splits may not LCS-align. Tracked as optional task **Paragraph alignment signature refinement** in `docs/AI-JIRA-TASKS-SUGGESTIONS.md`.

---

## Team decision (manual)

**Decision for SCRUM-48:** Treat Sprint 2 as **complete** for v1 catalog purposes. Track optional follow-ups as separate Jira items if the team prioritizes orchestration or alignment refinements.
