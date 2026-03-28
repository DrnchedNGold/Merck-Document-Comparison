"""SCRUM-68 / MDC-012: golden corpus harness unit + optional real corpus smoke."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from engine import DEFAULT_WORD_LIKE_COMPARE_CONFIG
from engine.corpus_harness import (
    GoldenPair,
    HarnessBatchResult,
    PairRunResult,
    format_batch_text_report,
    load_golden_pairs,
    revision_counts_by_part,
    run_configured_pairs,
    run_pair_emit_and_report,
    resolve_under_sample_docs,
)
from engine.body_revision_emit import emit_docx_with_package_track_changes

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fixture_pairs_path() -> Path:
    return _repo_root() / "tests" / "fixtures" / "golden_corpus_pairs.json"


def test_load_golden_pairs_reads_fixture_json() -> None:
    pairs = load_golden_pairs(_fixture_pairs_path())
    assert len(pairs) >= 7
    ids = {p.id for p in pairs}
    assert "email1-bladder" in ids
    assert "email2-v940" in ids
    assert "email3-protocol-1026" in ids


def test_revision_counts_by_part_on_synthetic_docx(tmp_path: Path) -> None:
    doc_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{WORD_NS}"><w:body>
  <w:p><w:r><w:t>x</w:t></w:r></w:p>
</w:body></w:document>"""
    hdr = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:hdr xmlns:w="{WORD_NS}">
  <w:p><w:del w:id="9" w:author="a" w:date="2020-01-01T00:00:00Z"><w:r><w:delText>gone</w:delText></w:r></w:del></w:p>
</w:hdr>"""
    p = tmp_path / "c.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", doc_body.encode())
        zf.writestr("word/header1.xml", hdr.encode())

    report = revision_counts_by_part(p)
    assert report["summary"]["document"]["ins"] == 0
    assert report["summary"]["document"]["del"] == 0
    assert report["summary"]["headers"]["del"] == 1
    assert report["summary"]["footers"]["ins"] == 0
    assert "word/document.xml" in report["by_part"]
    assert report["by_part"]["word/header1.xml"]["del"] == 1


def test_package_emit_produces_revision_counts_on_minimal_docx(tmp_path: Path) -> None:
    def _one_docx(name: str, text: str) -> Path:
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{WORD_NS}"><w:body>
  <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
</w:body></w:document>"""
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("word/document.xml", body.encode())
        return path

    orig = _one_docx("o.docx", "aa")
    rev = _one_docx("r.docx", "ab")
    out = tmp_path / "out.docx"
    emit_docx_with_package_track_changes(
        orig, rev, out, DEFAULT_WORD_LIKE_COMPARE_CONFIG, date_iso="2026-03-27T00:00:00Z"
    )
    report = revision_counts_by_part(out)
    assert report["summary"]["document"]["ins"] + report["summary"]["document"]["del"] >= 1


def test_format_batch_text_report() -> None:
    r_ok = PairRunResult(
        "p1",
        True,
        None,
        None,
        {
            "summary": {
                "document": {"ins": 1, "del": 0},
                "headers": {"ins": 0, "del": 2},
                "footers": {"ins": 0, "del": 0},
            }
        },
    )
    r_bad = PairRunResult("p2", False, error="boom")
    text = format_batch_text_report(HarnessBatchResult([r_ok, r_bad]))
    assert "p1" in text and "\ttrue\t" in text
    assert "\t1\t0\t0\t2\t0\t0\t" in text
    assert "p2" in text and "\tfalse\t" in text and "boom" in text


def test_golden_fixture_json_lists_all_three_corpora() -> None:
    raw = json.loads(_fixture_pairs_path().read_text(encoding="utf-8"))
    folders = {p["corpus_folder"] for p in raw["pairs"]}
    assert folders == {"email1docs", "email2docs", "email3docs"}


@pytest.mark.golden_corpus
@pytest.mark.parametrize(
    ("orig_rel", "rev_rel"),
    [
        (
            "email1docs/diversity-plan-bladder-cancer-version1.docx",
            "email1docs/diversity-plan-bladder-cancer-version2.docx",
        ),
        (
            "email2docs/ind-general-investigation-plan-V940-v1.docx",
            "email2docs/ind-general-investigation-plan-V940-v4.docx",
        ),
        (
            "email3docs/1026-010-02.docx",
            "email3docs/1026-010-04.docx",
        ),
    ],
)
def test_real_corpus_pair_runs_when_sample_docs_present(
    tmp_path: Path, orig_rel: str, rev_rel: str
) -> None:
    root = _repo_root()
    o = root / "sample-docs" / orig_rel
    r = root / "sample-docs" / rev_rel
    if not o.is_file() or not r.is_file():
        pytest.skip("Sponsor .docx files not in workspace; CI runs harness logic via synthetic tests.")

    pair = GoldenPair(
        id="smoke-" + orig_rel.split("/")[-1],
        corpus_folder=orig_rel.split("/")[0],
        original_relative=orig_rel,
        revised_relative=rev_rel,
    )
    out = tmp_path / "golden.docx"
    result = run_pair_emit_and_report(
        root,
        pair,
        out,
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        date_iso="2026-03-27T12:00:00Z",
    )
    assert result.ok, result.error
    assert result.report is not None
    s = result.report["summary"]
    assert "document" in s and "headers" in s and "footers" in s


@pytest.mark.golden_corpus
def test_configured_pairs_from_fixture_json_when_files_exist(tmp_path: Path) -> None:
    root = _repo_root()
    pairs = load_golden_pairs(_fixture_pairs_path())
    first = pairs[0]
    o = resolve_under_sample_docs(root, first.original_relative)
    if not o.is_file():
        pytest.skip("sample-docs corpus not present")

    batch = run_configured_pairs(
        root,
        [first],
        tmp_path / "golden-out",
        DEFAULT_WORD_LIKE_COMPARE_CONFIG,
        date_iso="2026-03-27T12:00:00Z",
    )
    assert batch.results[0].ok, batch.results[0].error
