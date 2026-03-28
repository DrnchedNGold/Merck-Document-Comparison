#!/usr/bin/env python3
"""Run golden corpus pairs (SCRUM-68). Invoke from repo root."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
    from engine.corpus_harness import (
        format_batch_report_json,
        format_batch_text_report,
        format_batch_text_report_verbose,
        load_golden_pairs,
        run_configured_pairs,
    )

    default_config = repo_root / "tests" / "fixtures" / "golden_corpus_pairs.json"
    parser = argparse.ArgumentParser(
        description="Run engine emit over configured sample-docs pairs and print revision counts.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help="JSON file listing pairs (default: tests/fixtures/golden_corpus_pairs.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "golden-corpus-output",
        help="Directory for emitted .docx files",
    )
    parser.add_argument(
        "--author",
        default="GoldenCorpusHarness",
        help="w:author for emitted revisions",
    )
    parser.add_argument(
        "--date-iso",
        default=None,
        metavar="UTC_DATETIME",
        help=(
            "Fixed w:date for all revisions (ISO 8601 UTC, e.g. 2026-03-27T12:00:00Z). "
            "Omit for wall-clock UTC time (non-reproducible across runs)."
        ),
    )
    parser.add_argument(
        "--verbose-parts",
        action="store_true",
        help="After the summary TSV, print per-pair summary and sorted by_part lines.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON (pair_id, ok, error, normalized report). Implies not TSV-only.",
    )
    args = parser.parse_args()

    pairs = load_golden_pairs(args.config)
    if not pairs:
        print("No pairs in config.", file=sys.stderr)
        return 2

    batch = run_configured_pairs(
        repo_root,
        pairs,
        args.output_dir,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        author=args.author,
        date_iso=args.date_iso,
    )
    if args.json:
        print(format_batch_report_json(batch), end="")
    elif args.verbose_parts:
        print(format_batch_text_report_verbose(batch), end="")
    else:
        print(format_batch_text_report(batch))
    return 0 if batch.all_ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
