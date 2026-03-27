"""Guardrail: Jira task suggestions doc must include Sprint 3–5 MDC tasks (SCRUM-45)."""

from __future__ import annotations

from pathlib import Path


def _suggestions_text() -> str:
    root = Path(__file__).resolve().parents[1]
    path = root / "docs" / "AI-JIRA-TASKS-SUGGESTIONS.md"
    return path.read_text(encoding="utf-8")


def test_sprint_3_5_sections_and_mdc_tasks_present() -> None:
    text = _suggestions_text()
    assert "## Sprint 3 — Structured content + minimal Track Changes" in text
    assert "## Sprint 4 — Output metadata + verification" in text
    assert "## Sprint 5 — Desktop MVP + hardening" in text

    # Task titles aligned with docs/V1-ACCEPTANCE-CATALOG.md MDC-008 … MDC-018
    for needle in (
        "#### Task: Tables in IR and table diff",
        "#### Task: Headers and footers",
        "#### Task: Track Changes body `w:ins` / `w:del`",
        "#### Task: Revision metadata and header/footer emit",
        "#### Task: Golden corpus harness",
        "#### Task: CI pipeline",
        "#### Task: Desktop shell and file pickers",
        "#### Task: Engine CLI and open output",
        "#### Task: Settings profiles UI",
        "#### Task: Error UX and logging",
        "#### Task: Move detection (stretch)",
    ):
        assert needle in text, f"missing task section: {needle}"
