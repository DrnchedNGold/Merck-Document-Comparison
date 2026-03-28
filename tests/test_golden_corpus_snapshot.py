"""Committed golden corpus snapshot: ins/del counts must match tests/fixtures/golden_corpus_expected.json."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.corpus_harness import (
    iter_snapshot_mismatches,
    load_golden_expected_baseline,
    load_golden_pairs,
    resolve_under_sample_docs,
    run_configured_pairs,
)

# Must match scripts/refresh_golden_corpus_baseline.py --date-iso default.
_SNAPSHOT_DATE_ISO = "2026-03-27T12:00:00Z"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_golden_baseline_pair_ids_match_pairs_fixture() -> None:
    root = _repo_root()
    pairs = load_golden_pairs(root / "tests/fixtures/golden_corpus_pairs.json")
    baseline = load_golden_expected_baseline(
        root / "tests/fixtures/golden_corpus_expected.json"
    )
    assert baseline.get("version") == 1
    assert set(baseline["pairs"].keys()) == {p.id for p in pairs}


def _sample_docs_available_for_all_pairs() -> bool:
    root = _repo_root()
    pairs = load_golden_pairs(root / "tests/fixtures/golden_corpus_pairs.json")
    for p in pairs:
        o = resolve_under_sample_docs(root, p.original_relative)
        r = resolve_under_sample_docs(root, p.revised_relative)
        if not o.is_file() or not r.is_file():
            return False
    return True


@pytest.mark.golden_corpus
def test_golden_harness_emit_counts_match_committed_baseline(tmp_path: Path) -> None:
    root = _repo_root()
    if not _sample_docs_available_for_all_pairs():
        pytest.skip("Full sample-docs corpus not present; snapshot regression runs in CI with committed binaries.")

    pairs = load_golden_pairs(root / "tests/fixtures/golden_corpus_pairs.json")
    baseline = load_golden_expected_baseline(
        root / "tests/fixtures/golden_corpus_expected.json"
    )

    batch = run_configured_pairs(
        root,
        pairs,
        tmp_path / "golden-snapshot-out",
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author="GoldenCorpusBaselineRefresh",
        date_iso=_SNAPSHOT_DATE_ISO,
    )
    assert batch.all_ok(), [r.error for r in batch.results if not r.ok]

    for r in batch.results:
        assert r.report is not None
        expected = baseline["pairs"][r.pair_id]
        mismatches = list(iter_snapshot_mismatches(r.report, expected))
        assert not mismatches, f"{r.pair_id}:\n" + "\n".join(mismatches)
