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
from typing import Any

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
