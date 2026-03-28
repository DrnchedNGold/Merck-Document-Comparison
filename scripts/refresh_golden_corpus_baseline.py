#!/usr/bin/env python3
"""Rewrite tests/fixtures/golden_corpus_expected.json from the current engine emit + report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
    from engine.corpus_harness import (
        build_expected_baseline_dict,
        load_golden_pairs,
        run_configured_pairs,
    )

    default_pairs = repo_root / "tests" / "fixtures" / "golden_corpus_pairs.json"
    default_out = repo_root / "tests" / "fixtures" / "golden_corpus_expected.json"

    parser = argparse.ArgumentParser(
        description=(
            "Run the golden corpus harness and overwrite the committed snapshot baseline. "
            "Requires sample-docs pairs referenced by --config."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_pairs,
        help="Pair list JSON (default: tests/fixtures/golden_corpus_pairs.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_out,
        help="Baseline JSON to write (default: tests/fixtures/golden_corpus_expected.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "golden-corpus-output",
        help="Temp directory for emitted .docx while refreshing",
    )
    parser.add_argument(
        "--author",
        default="GoldenCorpusBaselineRefresh",
        help="w:author for emitted revisions (does not affect ins/del counts)",
    )
    parser.add_argument(
        "--date-iso",
        default="2026-03-27T12:00:00Z",
        metavar="UTC_DATETIME",
        help="Fixed w:date for reproducibility (default matches snapshot tests)",
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
    if not batch.all_ok():
        for r in batch.results:
            if not r.ok:
                print(f"{r.pair_id}: {r.error}", file=sys.stderr)
        return 1

    want = {p.id for p in pairs}
    payload = build_expected_baseline_dict(batch)
    got = set(payload["pairs"].keys())
    if got != want:
        print(
            f"Baseline pair ids {got!r} != config ids {want!r}",
            file=sys.stderr,
        )
        return 1

    out_obj = {
        "version": payload["version"],
        "note": (
            "Per-pair w:ins/w:del counts from engine.corpus_harness.revision_counts_by_part "
            "after emit. Refresh with: python scripts/refresh_golden_corpus_baseline.py"
        ),
        "pairs": dict(sorted(payload["pairs"].items())),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(out_obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
