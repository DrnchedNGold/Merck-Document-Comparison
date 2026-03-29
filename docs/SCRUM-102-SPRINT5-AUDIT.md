# SCRUM-102 — Sprint 5 (Phase 5 desktop MVP + hardening) verification

**Purpose:** Confirm Sprint 5 in `docs/V1-ACCEPTANCE-CATALOG.md` (MDC-014, MDC-015, MDC-016, MDC-017, MDC-018) is implemented, map code and tests, and record any remaining follow-ups as separate Jira tasks.

**v1 scope:** `docs/PRODUCT-DECISIONS.md` — desktop UX that generates output and opens it is v1, with `.docx`-only inputs and a visible error/stop on pre-existing Track Changes/comments. This audit is verification and documentation only.

---

## Summary

| Task | Catalog ID | Verdict |
|------|------------|---------|
| Desktop shell and file pickers | MDC-014 | **Done** — `desktop/main_window.py` launches UI with Original/Revised pickers and validation in `desktop/desktop_state.py`; entrypoint `desktop/__main__.py`. Tests: `tests/test_desktop_smoke.py` (validation + optional Tk instantiate). |
| Engine CLI and open output | MDC-015 | **Done** — CLI entrypoint `engine/compare_cli.py` with stable exit codes and args; desktop invokes via subprocess `desktop/engine_runner.py` (`python -m engine.compare_cli`, optional `--config`) and can open output (`open_path_with_default_app`). Tests: `tests/test_compare_cli.py`, `tests/test_desktop_engine_runner.py`. |
| Settings profiles UI | MDC-016 | **Done** — profile JSON load/save helpers in `desktop/profiles.py`; desktop UI toggles + Load/Save profile in `desktop/main_window.py` (writes config JSON and passes as `--config`). Tests: `tests/test_desktop_profiles.py`. |
| Error UX and logging | MDC-017 | **Done** — desktop maps engine exit codes/stderr to friendly messages via `desktop/error_ux.py` and shows a Details block in the UI (`desktop/main_window.py`); compare runner logs start/success/failure in `desktop/engine_runner.py`. README includes troubleshooting guidance. Tests: `tests/test_desktop_error_ux.py`, plus logging assertion in `tests/test_desktop_engine_runner.py`. |
| Move detection (stretch) | MDC-018 | **Done (documented fallback)** — v1 decision is to treat moves as delete+insert (no `w:moveFrom`/`w:moveTo`). Documented in `docs/MDC-018-MOVE-DETECTION-V1.md` and referenced in engine notes (e.g. `engine/paragraph_alignment.py`). |

---

## Notes / follow-ups (optional)

1. **Golden regression runtime:** Golden corpus snapshot regression is intentionally expensive; the workflow can be sharded/cached to reduce wall-clock time without reducing coverage (tracked as CI hardening when needed).
2. **Desktop “Details” UX:** Current UI includes Details text in the error dialog; a future enhancement could add a copy-to-clipboard button or expandable panel, but it is not required for MDC-017 acceptance.

---

## Team decision (manual)

**Decision for SCRUM-102:** Treat Sprint 5 as **complete** for v1 catalog MDC-014–018. Any UX polish beyond the current acceptance criteria should be tracked as new Jira tasks.

