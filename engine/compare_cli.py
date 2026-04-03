"""SCRUM-83 / SCRUM-84 / SCRUM-85: CLI entrypoint for package track-changes compare.

Exit codes (stable; document in ``--help``):
  0  Success
  2  Invalid CLI usage, bad ``--config`` JSON, or compare-config validation failure
 10  Preflight rejection (file type, zip, existing track changes, comments, …)
 11  Document / package structure problem (missing ``word/document.xml``, …)
 12  Compare/emit or I/O failure during generation
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from .body_revision_emit import emit_docx_with_package_track_changes
from .contracts import DEFAULT_WORD_LIKE_COMPARE_CONFIG, CompareConfig, validate_compare_config
from .docx_body_ingest import DocumentXmlMissingError
from .preflight_validation import PreflightValidationError, validate_docx_for_preflight

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_PREFLIGHT = 10
EXIT_DOCUMENT_STRUCTURE = 11
EXIT_COMPARE_RUN = 12

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_NS = {"w": WORD_NS}


def _verbose_emit_revision_stats(output_docx: Path) -> None:
    """
    SCRUM-130 sanity: after emit, print how the abbreviations-style delete block looks in XML.

    If consolidation ran, expect **one** ``w:p`` containing ``following terms`` in ``w:delText``,
    **one** ``w:del``, and **one** ``w:r`` inside it (no per-bullet paragraphs). Use this to
    confirm Word is opening the file this CLI just wrote — not an older build or Merck reference output.
    """

    import zipfile

    with zipfile.ZipFile(output_docx, "r") as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find("w:body", _W_NS)
    total_del = len(root.findall(".//w:del", _W_NS))
    print(f"emit-stats: word/document.xml w:del total = {total_del}", file=sys.stderr)
    if body is None:
        return
    hits = 0
    for p in body.findall("w:p", _W_NS):
        blob = "".join(t.text or "" for t in p.findall(".//w:delText", _W_NS))
        if "following terms" not in blob.lower():
            continue
        hits += 1
        n_del = len(p.findall("w:del", _W_NS))
        runs = sum(len(d.findall("w:r", _W_NS)) for d in p.findall("w:del", _W_NS))
        ps = ""
        ppr = p.find("w:pPr", _W_NS)
        if ppr is not None:
            ps_el = ppr.find("w:pStyle", _W_NS)
            if ps_el is not None:
                ps = ps_el.get(f"{{{WORD_NS}}}val") or ""
        has_num = (
            ppr.find("w:numPr", _W_NS) is not None if ppr is not None else False
        )
        print(
            f"emit-stats: abbreviations delete block — w:pStyle={ps!r} numPr={has_num} "
            f"w:del in paragraph={n_del} w:r inside those dels={runs} preview={blob[:90]!r}",
            file=sys.stderr,
        )
    if hits == 0:
        print(
            "emit-stats: no paragraph with 'following terms' in w:delText (pair may differ)",
            file=sys.stderr,
        )


def _load_compare_config(path: Path | None) -> tuple[int, str | None, CompareConfig | None]:
    if path is None:
        return EXIT_SUCCESS, None, DEFAULT_WORD_LIKE_COMPARE_CONFIG.copy()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as e:
        return EXIT_USAGE, f"Could not read config file: {e}", None
    except json.JSONDecodeError as e:
        return EXIT_USAGE, f"Invalid JSON in --config: {e}", None
    if not isinstance(raw, dict):
        return EXIT_USAGE, "--config must be a JSON object.", None
    errs = validate_compare_config(raw)  # type: ignore[arg-type]
    if errs:
        return EXIT_USAGE, "Compare config invalid:\n" + "\n".join(errs), None
    return EXIT_SUCCESS, None, raw  # type: ignore[return-value]


def classify_engine_failure(exc: BaseException) -> tuple[int, str]:
    if isinstance(exc, PreflightValidationError):
        return EXIT_PREFLIGHT, str(exc)
    if isinstance(exc, DocumentXmlMissingError):
        return EXIT_DOCUMENT_STRUCTURE, str(exc)
    if isinstance(exc, ET.ParseError):
        return EXIT_DOCUMENT_STRUCTURE, f"XML parse error: {exc}"
    return EXIT_COMPARE_RUN, str(exc)


def run_compare(
    original: Path,
    revised: Path,
    output: Path,
    config: CompareConfig,
    *,
    author: str,
    date_iso: str | None,
) -> None:
    validate_docx_for_preflight(original)
    validate_docx_for_preflight(revised)
    output.parent.mkdir(parents=True, exist_ok=True)
    emit_docx_with_package_track_changes(
        original,
        revised,
        output,
        config,
        author=author,
        date_iso=date_iso,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="merck-compare",
        description="Compare two .docx files and write a new document with Track Changes markup.",
        epilog=(
            "Exit codes: 0 success; 2 usage/config; 10 preflight; "
            "11 document/package structure; 12 compare/emit or I/O."
        ),
    )
    p.add_argument("--original", required=True, type=Path, help="Path to the original .docx")
    p.add_argument("--revised", required=True, type=Path, help="Path to the revised .docx")
    p.add_argument("--output", required=True, type=Path, help="Path for the generated .docx")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON file for CompareConfig (ignore_case, ignore_whitespace, …).",
    )
    p.add_argument(
        "--author",
        default="MerckDocCompare",
        help="w:author value on revision elements (default: %(default)s).",
    )
    p.add_argument(
        "--date-iso",
        default=None,
        help="Optional fixed w:date (ISO-8601 UTC, e.g. 2026-03-28T12:00:00Z) for reproducible runs.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="After success, print w:del stats (SCRUM-130: confirm consolidated abbreviations block in output).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    code, err, cfg = _load_compare_config(args.config)
    if err:
        print(err, file=sys.stderr)
        return code
    assert cfg is not None
    try:
        run_compare(
            args.original,
            args.revised,
            args.output,
            cfg,
            author=str(args.author),
            date_iso=args.date_iso,
        )
    except (PreflightValidationError, DocumentXmlMissingError, ET.ParseError) as e:
        exit_code, msg = classify_engine_failure(e)
        print(msg, file=sys.stderr)
        return exit_code
    except OSError as e:
        print(str(e), file=sys.stderr)
        return EXIT_COMPARE_RUN
    except Exception as e:  # noqa: BLE001 — last-resort mapping for stable exit bucket
        print(str(e), file=sys.stderr)
        return EXIT_COMPARE_RUN
    if args.verbose:
        _verbose_emit_revision_stats(args.output)
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
