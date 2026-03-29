# V1 Project Plan — Document Comparison Tool

This is the phased plan for the first shippable product.
Stable narrative lives here; detailed acceptance criteria live in `docs/V1-ACCEPTANCE-CATALOG.md`.

## What ships in v1

From two Word `.docx` files (original + revised), generate a third `.docx` that uses **Word Track Changes markup** (`w:ins` / `w:del`, etc.) and produces fewer formatting-driven false positives than naive comparisons.

## Phases (durable technical breakdown)

Phases map to acceptance/scope slices:

| Phase | Topic |
|------:|-------|
| 0 | Foundation: repo scaffolding, IR contracts, DOCX body ingest, preflight validation |
| 1 | Body compare: normalization, paragraph alignment, inline diff |
| 2 | Structured content: tables, headers/footers |
| 3 | Track Changes output: body revisions, revision metadata + emit in correct parts |
| 4 | Verification: golden corpus harness, CI quality gates |
| 5 | Desktop MVP: UI shell, engine CLI wiring, settings, error UX |
| 6 | Hardening / delivery notes (+ stretch items as late optional work) |

## Sprint plan (Scrum grouping: 5 sprints)

Sprints below group the same phases into ~5 time windows so the team can plan and execute.

| Sprint | Focus | Task IDs |
|--------:|--------|----------|
| Sprint 1 | Phase 0 foundation | MDC-001, MDC-002, MDC-003, MDC-004 |
| Sprint 2 | Phase 1 body compare | MDC-005, MDC-006, MDC-007 |
| Sprint 3 | Phase 2 + minimal Phase 3 output | MDC-008, MDC-009, MDC-010 |
| Sprint 4 | Phase 3.2 + Phase 4 verification | MDC-011, MDC-012, MDC-013 |
| Sprint 5 | Desktop MVP (Phase 5) + stretch | MDC-014, MDC-015, MDC-016, MDC-017, MDC-018 |

## Sprint 2 — implementation map (Phase 1 / body compare)

Verification note: `docs/SCRUM-48-SPRINT2-AUDIT.md` (SCRUM-48) confirms catalog acceptance for MDC-005–007 against the repo.

| Catalog | Engine module(s) | Tests |
|--------|-------------------|--------|
| MDC-005 | `engine/compare_keys.py`, compare profile in `engine/contracts.py` | `tests/test_compare_keys.py` |
| MDC-006 | `engine/paragraph_alignment.py` | `tests/test_paragraph_alignment.py` |
| MDC-007 | `engine/inline_run_diff.py` | `tests/test_inline_run_diff.py` |

Optional orchestration (post-SCRUM-48): `engine/body_compare.py` (`matched_paragraph_inline_diffs`), tests in `tests/test_body_compare.py`.

## Sprint 3 — implementation map (Phase 2 + minimal Phase 3.1)

Verification note: `docs/SCRUM-100-SPRINT3-AUDIT.md` (SCRUM-100) confirms catalog acceptance for MDC-008–010 against the repo.

| Catalog | Engine module(s) | Tests |
|--------|-------------------|--------|
| MDC-008 | `engine/contracts.py` (`BodyTable`, …), `engine/docx_body_ingest.py` (`w:tbl` → IR), `engine/table_diff.py` | `tests/test_docx_body_ingest.py` (table fixture), `tests/test_table_diff.py` |
| MDC-009 | `engine/docx_package_parts.py`, `engine/document_package.py` | `tests/test_docx_header_footer_package.py` |
| MDC-010 | `engine/body_revision_emit.py`, `engine/docx_output_package.py` | `tests/test_body_track_changes_output.py` |

**Orchestration:** `engine/body_compare.py` — `matched_paragraph_inline_diffs` aligns top-level blocks (paragraphs and tables) and emits inline diffs for paragraph pairs and `diff_table_blocks` for aligned table pairs; `matched_document_package_inline_diffs` runs the same over `word/document.xml` and each header/footer part. Tests: `tests/test_body_compare.py`, `tests/test_docx_header_footer_package.py`.

## Sprint 4 — golden harness (Phase 4 slice, SCRUM-68)

| Catalog | Location | Tests / runner |
|--------|----------|----------------|
| MDC-012 | `engine/corpus_harness.py`, `tests/fixtures/golden_corpus_pairs.json`, `scripts/run_golden_corpus.py` | `tests/test_golden_corpus_harness.py` (synthetic + optional `golden_corpus` marker when `sample-docs` binaries exist); `README.md` rollout notes |

Other Sprint 4 catalog items (MDC-011 revision metadata / MDC-013 CI) are implemented elsewhere in the repo; see `docs/V1-ACCEPTANCE-CATALOG.md` and `docs/CONTEXT-CHANGE-POLICY.md` changelog.

## Sprint 5 — Desktop MVP + wiring (Phase 5)

Verification note: **MDC-014** (desktop shell) and **MDC-015** (engine CLI + desktop invoke + open output) are implemented and covered by tests below. **MDC-016–018** remain per catalog (settings UI, richer error UX, stretch move detection) unless listed as done in a future audit.

| Catalog | Location | Tests |
|--------|----------|--------|
| MDC-014 | `desktop/main_window.py`, `desktop/desktop_state.py`, `desktop/__main__.py` | `tests/test_desktop_smoke.py` (validation + optional Tk smoke); `desktop/` pickers wired without stub-only compare |
| MDC-015 | `engine/compare_cli.py` (also `merck-compare` in `pyproject.toml`), `desktop/engine_runner.py` (`python -m engine.compare_cli`, optional `--config`), `desktop/main_window.py` (subprocess compare, stderr on failure, **Open output** via OS default app); user docs `docs/CLI-MERCK-COMPARE.md`, man page `man/man1/merck-compare.1` | `tests/test_compare_cli.py`, `tests/test_desktop_engine_runner.py` |
| MDC-016 | *Backlog:* profile JSON in UI driving `--config` — not yet a full settings screen | — |
| MDC-017 | *Partial:* desktop shows CLI **stderr** on failure; dedicated exit-code → message table in README is catalog follow-up | — |
| MDC-018 | *Stretch / backlog* | — |

**MDC-015 suggested subtasks (all implemented):** CLI entry + argparse schema (`engine/compare_cli.py`); stable exit codes + stderr messages (`classify_engine_failure`, `main`); desktop subprocess + `PYTHONPATH` (`desktop/engine_runner.py`); compare button + error dialog + optional open output (`desktop/main_window.py`, `open_path_with_default_app`).

## Dependency sketch (simplified)

```text
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4
                               ↘
Phase 5 (desktop can start after Phase 0 + CLI stub; full integration after Phase 3)
Phase 6 last
```

## Out of scope for v1

Per `docs/PRODUCT-DECISIONS.md`:
- Batch multi-file compare
- Non-docx formats (Excel/PowerPoint, etc.)
- Accepting source docs that already have tracked changes/comments without explicit workflow changes

## Where each type of detail lives

- `docs/PRODUCT-DECISIONS.md` — product guardrails and scope rules
- `docs/V1-ACCEPTANCE-CATALOG.md` — acceptance criteria by MDC task under 5 sprints
- `docs/TEAM-WORKFLOW.md` / `docs/TEAM-PLAYBOOK.md` — team process and AI prompts
- `sample-docs/` — client procedure + expected compare outputs
- `sample-docs/CORPUS-INVENTORY.md` — combined email1/email2/email3 corpus details

## SCRUM-40 corpus direction

With `email2docs/` and `email3docs/` included, planning and implementation should:

- Use all email corpora for acceptance and regression expectations.
- Keep engine design document-agnostic across templates and sponsor formats.
- Treat generated compare documents as reference outcomes (not source-input happy paths).
- Prioritize robustness for large structured docs (tables, headers/footers) seen in Protocol/IB samples.
- Treat all `email#docs` folders as one unified real-world corpus; complexity tiers expand test scope but do not replace earlier-tier behavior requirements.
- Maintain non-regression expectations across simpler, mid-complexity, and high-complexity samples when evolving comparison logic.
