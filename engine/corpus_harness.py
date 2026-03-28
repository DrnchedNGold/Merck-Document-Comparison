"""
Golden corpus harness (MDC-012 / SCRUM-68).

Run the engine compare+emit path over configured ``sample-docs`` pairs and report
``w:ins`` / ``w:del`` counts per OOXML part (document vs headers vs footers).
"""

from __future__ import annotations

import json
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .contracts import CompareConfig
from .docx_package_parts import (
    DOCUMENT_PART_PATH,
    discover_header_footer_part_paths_from_namelist,
)
from .body_revision_emit import emit_docx_with_package_track_changes
from .preflight_validation import validate_docx_for_preflight

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": WORD_NS}


def _count_ins_del_in_xml(xml_bytes: bytes) -> tuple[int, int]:
    root = ET.fromstring(xml_bytes)
    ins = len(root.findall(".//w:ins", _NS))
    dels = len(root.findall(".//w:del", _NS))
    return ins, dels


def revision_counts_by_part(docx_path: Path) -> dict[str, Any]:
    """
    Count revision markers in ``word/document.xml`` and each header/footer part.

    Returns ``by_part`` (zip path -> counts) and ``summary`` aggregating
    document / all headers / all footers.
    """

    by_part: dict[str, dict[str, int]] = {}
    with zipfile.ZipFile(docx_path, "r") as zf:
        namelist = zf.namelist()
        to_scan = [DOCUMENT_PART_PATH] + discover_header_footer_part_paths_from_namelist(
            namelist
        )
        seen: set[str] = set()
        for part in to_scan:
            if part in seen:
                continue
            seen.add(part)
            try:
                raw = zf.read(part)
            except KeyError:
                continue
            ins_c, del_c = _count_ins_del_in_xml(raw)
            by_part[part] = {"ins": ins_c, "del": del_c}

    doc = by_part.get(DOCUMENT_PART_PATH, {"ins": 0, "del": 0})
    hdr_ins = hdr_del = 0
    ftr_ins = ftr_del = 0
    for path, c in by_part.items():
        p = path.replace("\\", "/").lower()
        if p.startswith("word/header") and p.endswith(".xml"):
            hdr_ins += c["ins"]
            hdr_del += c["del"]
        elif p.startswith("word/footer") and p.endswith(".xml"):
            ftr_ins += c["ins"]
            ftr_del += c["del"]

    return {
        "by_part": by_part,
        "summary": {
            "document": {"ins": doc["ins"], "del": doc["del"]},
            "headers": {"ins": hdr_ins, "del": hdr_del},
            "footers": {"ins": ftr_ins, "del": ftr_del},
        },
    }


def normalize_report_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    """
    Stable JSON shape for golden baselines: sorted ``by_part`` keys, POSIX paths.

    ``summary`` is copied verbatim (``revision_counts_by_part`` already aggregates
    document / headers / footers).
    """

    raw_bp = report.get("by_part", {})
    by_part: dict[str, dict[str, int]] = {}
    for key in sorted(raw_bp.keys()):
        path = key.replace("\\", "/")
        c = raw_bp[key]
        by_part[path] = {"ins": int(c["ins"]), "del": int(c["del"])}
    summ = report["summary"]
    return {
        "summary": {
            "document": {
                "ins": int(summ["document"]["ins"]),
                "del": int(summ["document"]["del"]),
            },
            "headers": {
                "ins": int(summ["headers"]["ins"]),
                "del": int(summ["headers"]["del"]),
            },
            "footers": {
                "ins": int(summ["footers"]["ins"]),
                "del": int(summ["footers"]["del"]),
            },
        },
        "by_part": by_part,
    }


def load_golden_expected_baseline(path: Path) -> dict[str, Any]:
    """Load ``tests/fixtures/golden_corpus_expected.json`` (or a path with the same shape)."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("pairs"), dict):
        raise ValueError("Expected baseline JSON to have a top-level 'pairs' object.")
    return data


def iter_snapshot_mismatches(
    actual: dict[str, Any], expected: dict[str, Any]
) -> Iterator[str]:
    """Yield human-readable diff lines when normalized reports differ."""

    a = normalize_report_snapshot(actual)
    e = normalize_report_snapshot(expected)
    if a["summary"] != e["summary"]:
        yield f"summary: {a['summary']!r} != {e['summary']!r}"
    a_parts, e_parts = a["by_part"], e["by_part"]
    if set(a_parts.keys()) != set(e_parts.keys()):
        yield (
            f"by_part keys differ: only_in_actual={set(a_parts.keys()) - set(e_parts.keys())} "
            f"only_in_expected={set(e_parts.keys()) - set(a_parts.keys())}"
        )
    for path in sorted(set(a_parts.keys()) | set(e_parts.keys())):
        if path not in e_parts or path not in a_parts:
            continue
        if a_parts[path] != e_parts[path]:
            yield f"by_part[{path!r}]: {a_parts[path]!r} != {e_parts[path]!r}"


@dataclass
class GoldenPair:
    """One original/revised pair under ``sample-docs/``."""

    id: str
    corpus_folder: str
    original_relative: str
    revised_relative: str


@dataclass
class PairRunResult:
    pair_id: str
    ok: bool
    error: str | None = None
    output_path: Path | None = None
    report: dict[str, Any] | None = None


def load_golden_pairs(config_path: Path) -> list[GoldenPair]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    out: list[GoldenPair] = []
    for row in data.get("pairs", []):
        out.append(
            GoldenPair(
                id=str(row["id"]),
                corpus_folder=str(row.get("corpus_folder", "")),
                original_relative=str(row["original"]),
                revised_relative=str(row["revised"]),
            )
        )
    return out


def resolve_under_sample_docs(repo_root: Path, relative: str) -> Path:
    return (repo_root / "sample-docs" / relative).resolve()


def run_pair_emit_and_report(
    repo_root: Path,
    pair: GoldenPair,
    output_docx: Path,
    compare_config: CompareConfig,
    *,
    author: str = "GoldenCorpusHarness",
    date_iso: str | None = None,
) -> PairRunResult:
    """Preflight, emit package track changes, then build revision report."""

    orig = resolve_under_sample_docs(repo_root, pair.original_relative)
    rev = resolve_under_sample_docs(repo_root, pair.revised_relative)
    try:
        validate_docx_for_preflight(orig)
        validate_docx_for_preflight(rev)
    except Exception as e:  # noqa: BLE001 — surface preflight failures in harness report
        return PairRunResult(pair.id, False, error=f"preflight: {e!s}")

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    try:
        emit_docx_with_package_track_changes(
            orig,
            rev,
            output_docx,
            compare_config,
            author=author,
            date_iso=date_iso,
        )
    except Exception as e:  # noqa: BLE001
        return PairRunResult(pair.id, False, error=f"emit: {e!s}")

    try:
        report = revision_counts_by_part(output_docx)
    except Exception as e:  # noqa: BLE001
        return PairRunResult(pair.id, False, error=f"report: {e!s}")

    return PairRunResult(
        pair.id, True, None, output_path=output_docx, report=report
    )


@dataclass
class HarnessBatchResult:
    results: list[PairRunResult] = field(default_factory=list)

    def all_ok(self) -> bool:
        return all(r.ok for r in self.results)


def run_configured_pairs(
    repo_root: Path,
    pairs: list[GoldenPair],
    output_dir: Path,
    compare_config: CompareConfig,
    *,
    author: str = "GoldenCorpusHarness",
    date_iso: str | None = None,
) -> HarnessBatchResult:
    batch = HarnessBatchResult()
    for pair in pairs:
        out_path = output_dir / f"{pair.id}.docx"
        batch.results.append(
            run_pair_emit_and_report(
                repo_root,
                pair,
                out_path,
                compare_config,
                author=author,
                date_iso=date_iso,
            )
        )
    return batch


def format_batch_text_report(batch: HarnessBatchResult) -> str:
    """Plain-text table for logs / CLI."""

    lines = [
        "pair_id\tok\tdoc_ins\tdoc_del\thdr_ins\thdr_del\tftr_ins\tftr_del\terror",
    ]
    for r in batch.results:
        if r.ok and r.report:
            s = r.report["summary"]
            d, h, f = s["document"], s["headers"], s["footers"]
            lines.append(
                f"{r.pair_id}\ttrue\t{d['ins']}\t{d['del']}\t{h['ins']}\t{h['del']}\t{f['ins']}\t{f['del']}\t"
            )
        else:
            lines.append(
                f"{r.pair_id}\tfalse\t\t\t\t\t\t\t{r.error or 'unknown'}"
            )
    return "\n".join(lines)


def format_batch_text_report_verbose(batch: HarnessBatchResult) -> str:
    """
    Default one-line TSV plus per-pair ``summary`` and sorted ``by_part`` lines for logs.
    """

    lines = [format_batch_text_report(batch), ""]
    for r in batch.results:
        lines.append(f"--- {r.pair_id} ---")
        if not r.ok:
            lines.append(f"error: {r.error or 'unknown'}")
            lines.append("")
            continue
        if not r.report:
            lines.append("report: (missing)")
            lines.append("")
            continue
        snap = normalize_report_snapshot(r.report)
        s = snap["summary"]
        lines.append(
            "summary\t"
            f"doc_ins={s['document']['ins']}\tdoc_del={s['document']['del']}\t"
            f"hdr_ins={s['headers']['ins']}\thdr_del={s['headers']['del']}\t"
            f"ftr_ins={s['footers']['ins']}\tftr_del={s['footers']['del']}"
        )
        lines.append("by_part")
        for path, c in snap["by_part"].items():
            lines.append(f"  {path}\tins={c['ins']}\tdel={c['del']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def harness_batch_to_json_dict(batch: HarnessBatchResult) -> dict[str, Any]:
    """Structured batch result for ``--json`` (normalized ``report`` when present)."""

    return {
        "results": [
            {
                "pair_id": r.pair_id,
                "ok": r.ok,
                "error": r.error,
                "report": normalize_report_snapshot(r.report)
                if r.ok and r.report
                else None,
            }
            for r in batch.results
        ]
    }


def format_batch_report_json(batch: HarnessBatchResult) -> str:
    return json.dumps(harness_batch_to_json_dict(batch), indent=2, sort_keys=True) + "\n"


def build_expected_baseline_dict(batch: HarnessBatchResult) -> dict[str, Any]:
    """
    Payload written by :file:`scripts/refresh_golden_corpus_baseline.py`.

    One entry per successful pair; failed pairs are omitted (refresh script should abort).
    """

    pairs: dict[str, Any] = {}
    for r in batch.results:
        if not r.ok or not r.report:
            continue
        pairs[r.pair_id] = normalize_report_snapshot(r.report)
    return {
        "version": 1,
        "pairs": pairs,
    }
