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
