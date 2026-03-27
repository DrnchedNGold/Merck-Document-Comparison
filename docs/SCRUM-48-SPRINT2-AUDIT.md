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

1. **Full-body orchestration:** A single public API that runs `align_paragraphs` over two `BodyIR`s, then runs `inline_diff_single_paragraph` for each alignment row where both indices are non-null (with paragraph extraction helpers). Useful for CLI/desktop later; not specified in Sprint 2 acceptance text.
2. **Alignment vs run-split:** Paragraph signatures depend on per-run compare keys. Two paragraphs with the **same concatenated text** but **different run boundaries** can produce different signatures and may not align as the same paragraph under LCS. If that becomes a real-world issue, consider a catalog task to align on concatenated paragraph text, normalize run splits, or document the limitation.

---

## Team decision (manual)

**Decision for SCRUM-48:** Treat Sprint 2 as **complete** for v1 catalog purposes. Track optional follow-ups as separate Jira items if the team prioritizes orchestration or alignment refinements.
