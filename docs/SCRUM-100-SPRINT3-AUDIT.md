# SCRUM-100 — Sprint 3 (Phase 2 + minimal Phase 3.1) verification

**Purpose:** Confirm Sprint 3 in `docs/V1-ACCEPTANCE-CATALOG.md` (MDC-008, MDC-009, MDC-010) is implemented, map engine modules and tests, and record optional follow-ups for Jira if the team wants deeper integration.

**v1 scope:** `docs/PRODUCT-DECISIONS.md` — structured `.docx` content (tables, headers/footers) and Track Changes body output are in v1; this audit is documentation and verification (no product direction change).

---

## Summary

| Task | Catalog ID | Verdict |
|------|------------|---------|
| Tables in IR and table diff | MDC-008 | **Done** — `BodyTable` / `BodyTableCell` in `engine/contracts.py`; `word/document.xml` `w:tbl` parsing in `engine/docx_body_ingest.py` (`parse_structural_blocks_from_element`); deterministic cell-level diff in `engine/table_diff.py` (`diff_table_blocks`). Tests: `tests/test_docx_body_ingest.py` (minimal table fixture), `tests/test_table_diff.py`, plus SCRUM-100 integration test `tests/test_sprint3_table_ingest_diff_integration.py`. |
| Headers and footers | MDC-009 | **Done** — discovery and parse in `engine/docx_package_parts.py`; package IR in `engine/document_package.py` (`parse_docx_document_package`); compare rows carry `part` for `word/document.xml` and each `word/header*.xml` / `word/footer*.xml` via `engine/body_compare.py` (`matched_document_package_inline_diffs`). Tests: `tests/test_docx_header_footer_package.py` (includes footer part coverage from SCRUM-100). |
| Track Changes body `w:ins` / `w:del` | MDC-010 | **Done** — `engine/body_revision_emit.py` (`build_paragraph_track_change_elements`, `emit_docx_with_body_track_changes`) writes OOXML revision markup; `engine/docx_output_package.py` copies package with replaced `word/document.xml`. Tests: `tests/test_body_track_changes_output.py` (element builders + zip output XML assertions). “Opens in Word” for non-trivial docs remains a manual spot-check; trivial synthetic fixtures are covered by automated XML tests. |

**Suggested subtasks (Sprint 3 section of `docs/AI-JIRA-TASKS-SUGGESTIONS.md`):** Catalog-level acceptance for MDC-008–010 is satisfied in repo, including package orchestration for aligned table blocks via `matched_paragraph_inline_diffs` → `diff_table_blocks` (SCRUM-100 follow-up).

---

## Optional follow-ups (separate Jira items if prioritized)

1. **Track Changes for table cell bodies:** MDC-010 scope is body `w:p` / positional pairing in `emit_docx_with_body_track_changes`; emitting revisions inside `w:tc` is a later task (may overlap Sprint 4 metadata / part emission).
2. **Nested tables in `w:tc`:** Ingest skips nested `w:tbl` inside cells per `docx_body_ingest` docstring; document limitation or extend parser if sponsor docs require it.

**Orchestration detail:** `matched_paragraph_inline_diffs` pairs tables from LCS when signatures match, and applies a **same-index table fallback** when signatures differ (typical edited-cell case) so cell-level `diff_table_blocks` still runs for aligned document structure.

---

## Team decision (manual)

**Decision for SCRUM-100:** Treat Sprint 3 as **complete** for v1 catalog MDC-008–010. Track optional follow-ups as new Jira stories if the team prioritizes orchestration or table Track Changes emission.
