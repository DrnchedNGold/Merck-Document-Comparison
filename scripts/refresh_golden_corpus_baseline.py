#!/usr/bin/env python3
"""Rewrite tests/fixtures/golden_corpus_expected.json from the current engine emit + report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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

    def _write_baseline(out_path: Path, pairs_payload: dict[str, Any]) -> None:
        out_obj = {
            "version": 1,
            "note": (
                "Per-pair w:ins/w:del counts from engine.corpus_harness.revision_counts_by_part "
                "after emit. Refresh with: python scripts/refresh_golden_corpus_baseline.py"
            ),
            "pairs": dict(sorted(pairs_payload.items())),
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(out_obj, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
    parser.add_argument(
        "--only",
        default=None,
        metavar="ID,ID,...",
        help=(
            "Comma-separated pair ids to refresh. Merges into existing --output; "
            "other pairs' counts stay as in that file. Requires --output to already exist."
        ),
    )
    args = parser.parse_args()

    all_config_pairs = load_golden_pairs(args.config)
    if not all_config_pairs:
        print("No pairs in config.", file=sys.stderr)
        return 2

    only_ids: set[str] | None = None
    if args.only:
        only_ids = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = only_ids - {p.id for p in all_config_pairs}
        if unknown:
            print(f"Unknown pair id(s) for --only: {sorted(unknown)}", file=sys.stderr)
            return 2
        if not args.output.is_file():
            print("--only requires an existing --output file to merge into.", file=sys.stderr)
            return 2

    pairs = (
        [p for p in all_config_pairs if p.id in only_ids]
        if only_ids
        else all_config_pairs
    )

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
            f"Baseline pair ids {got!r} != run ids {want!r}",
            file=sys.stderr,
        )
        return 1

    if only_ids is not None:
        prior = json.loads(args.output.read_text(encoding="utf-8"))
        merged_pairs: dict[str, Any] = dict(prior.get("pairs", {}))
        merged_pairs.update(payload["pairs"])
        config_ids = {p.id for p in all_config_pairs}
        if set(merged_pairs.keys()) != config_ids:
            print(
                f"After merge, pair keys {set(merged_pairs.keys())!r} != config {config_ids!r}",
                file=sys.stderr,
            )
            return 1
        _write_baseline(args.output, merged_pairs)
    else:
        _write_baseline(args.output, dict(payload["pairs"]))

    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
