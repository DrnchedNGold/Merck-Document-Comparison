"""SCRUM-83 / SCRUM-84 / SCRUM-85: compare CLI argument handling and exit codes."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from engine.compare_cli import (
    EXIT_COMPARE_RUN,
    EXIT_DOCUMENT_STRUCTURE,
    EXIT_PREFLIGHT,
    EXIT_SUCCESS,
    EXIT_USAGE,
    build_arg_parser,
    classify_engine_failure,
    main,
)

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _minimal_docx(path: Path, body_inner: str) -> None:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}">
  <w:body>
    {body_inner}
  </w:body>
</w:document>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)


def test_build_arg_parser_requires_original_revised_output() -> None:
    p = build_arg_parser()
    with pytest.raises(SystemExit):
        p.parse_args([])


def test_main_missing_required_args_exits_usage() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_main_invalid_config_json_exits_usage(tmp_path: Path) -> None:
    bad = tmp_path / "cfg.json"
    bad.write_text("{not json", encoding="utf-8")
    orig = tmp_path / "o.docx"
    rev = tmp_path / "r.docx"
    out = tmp_path / "out.docx"
    _minimal_docx(orig, "<w:p><w:r><w:t>A</w:t></w:r></w:p>")
    _minimal_docx(rev, "<w:p><w:r><w:t>B</w:t></w:r></w:p>")
    assert main(["--original", str(orig), "--revised", str(rev), "--output", str(out), "--config", str(bad)]) == EXIT_USAGE


def test_main_invalid_config_shape_exits_usage(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps([]), encoding="utf-8")
    orig = tmp_path / "o.docx"
    rev = tmp_path / "r.docx"
    out = tmp_path / "out.docx"
    _minimal_docx(orig, "<w:p><w:r><w:t>A</w:t></w:r></w:p>")
    _minimal_docx(rev, "<w:p><w:r><w:t>B</w:t></w:r></w:p>")
    assert main(["--original", str(orig), "--revised", str(rev), "--output", str(out), "--config", str(cfg)]) == EXIT_USAGE


def test_main_non_docx_original_exits_preflight(tmp_path: Path) -> None:
    orig = tmp_path / "o.txt"
    orig.write_text("x", encoding="utf-8")
    rev = tmp_path / "r.docx"
    out = tmp_path / "out.docx"
    _minimal_docx(rev, "<w:p><w:r><w:t>B</w:t></w:r></w:p>")
    assert main(["--original", str(orig), "--revised", str(rev), "--output", str(out)]) == EXIT_PREFLIGHT


def test_main_verbose_prints_emit_stats(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    orig = tmp_path / "o.docx"
    rev = tmp_path / "r.docx"
    out = tmp_path / "out.docx"
    _minimal_docx(orig, "<w:p><w:r><w:t>Hi</w:t></w:r></w:p>")
    _minimal_docx(rev, "<w:p><w:r><w:t>Hi there</w:t></w:r></w:p>")
    code = main(
        [
            "--original",
            str(orig),
            "--revised",
            str(rev),
            "--output",
            str(out),
            "--date-iso",
            "2026-03-28T12:00:00Z",
            "-v",
        ]
    )
    assert code == EXIT_SUCCESS
    err = capsys.readouterr().err
    assert "emit-stats:" in err
    assert "w:del total" in err


def test_main_success_writes_output(tmp_path: Path) -> None:
    orig = tmp_path / "o.docx"
    rev = tmp_path / "r.docx"
    out = tmp_path / "out.docx"
    _minimal_docx(orig, "<w:p><w:r><w:t>Hi</w:t></w:r></w:p>")
    _minimal_docx(rev, "<w:p><w:r><w:t>Hi there</w:t></w:r></w:p>")
    code = main(
        [
            "--original",
            str(orig),
            "--revised",
            str(rev),
            "--output",
            str(out),
            "--date-iso",
            "2026-03-28T12:00:00Z",
        ]
    )
    assert code == EXIT_SUCCESS
    assert out.is_file()
    with zipfile.ZipFile(out, "r") as zf:
        assert "word/document.xml" in zf.namelist()


def test_main_valid_config_file(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        json.dumps(
            {
                "ignore_case": False,
                "ignore_whitespace": False,
                "ignore_formatting": True,
                "detect_moves": False,
            }
        ),
        encoding="utf-8",
    )
    orig = tmp_path / "o.docx"
    rev = tmp_path / "r.docx"
    out = tmp_path / "out.docx"
    _minimal_docx(orig, "<w:p><w:r><w:t>X</w:t></w:r></w:p>")
    _minimal_docx(rev, "<w:p><w:r><w:t>Y</w:t></w:r></w:p>")
    assert (
        main(
            [
                "--original",
                str(orig),
                "--revised",
                str(rev),
                "--output",
                str(out),
                "--config",
                str(cfg),
                "--date-iso",
                "2026-03-28T12:00:00Z",
            ]
        )
        == EXIT_SUCCESS
    )


def test_main_missing_document_xml_exits_structure(tmp_path: Path) -> None:
    orig = tmp_path / "o.docx"
    with zipfile.ZipFile(orig, "w") as zf:
        zf.writestr("readme.txt", b"x")
    rev = tmp_path / "r.docx"
    _minimal_docx(rev, "<w:p><w:r><w:t>A</w:t></w:r></w:p>")
    out = tmp_path / "out.docx"
    assert main(["--original", str(orig), "--revised", str(rev), "--output", str(out)]) == EXIT_DOCUMENT_STRUCTURE


def test_main_output_dir_missing_parent_ok(tmp_path: Path) -> None:
    orig = tmp_path / "o.docx"
    rev = tmp_path / "r.docx"
    out = tmp_path / "nested" / "out.docx"
    _minimal_docx(orig, "<w:p><w:r><w:t>A</w:t></w:r></w:p>")
    _minimal_docx(rev, "<w:p><w:r><w:t>B</w:t></w:r></w:p>")
    assert (
        main(
            [
                "--original",
                str(orig),
                "--revised",
                str(rev),
                "--output",
                str(out),
                "--date-iso",
                "2026-03-28T12:00:00Z",
            ]
        )
        == EXIT_SUCCESS
    )
    assert out.is_file()


def test_classify_maps_unknown_to_compare_run() -> None:
    code, _msg = classify_engine_failure(RuntimeError("boom"))
    assert code == EXIT_COMPARE_RUN
