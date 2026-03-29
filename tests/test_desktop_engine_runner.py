"""SCRUM-83 / SCRUM-86: desktop subprocess path to ``engine.compare_cli``."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from desktop.engine_runner import (
    build_compare_command,
    default_repo_root,
    open_path_with_default_app,
    run_compare_subprocess,
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


def test_default_repo_root_contains_engine_and_desktop() -> None:
    root = default_repo_root()
    assert (root / "engine").is_dir()
    assert (root / "desktop").is_dir()


def test_build_compare_command_sets_pythonpath(tmp_path: Path) -> None:
    cmd, env, root = build_compare_command("/a/o.docx", "/b/r.docx", "/c/out.docx", repo_root=tmp_path)
    assert "PYTHONPATH" in env
    assert env["PYTHONPATH"] == str(tmp_path)
    assert "-m" in cmd and "engine.compare_cli" in cmd


def test_build_compare_command_includes_config_when_provided(tmp_path: Path) -> None:
    cmd, env, _root = build_compare_command(
        "/a/o.docx",
        "/b/r.docx",
        "/c/out.docx",
        config_path="/settings/profile.json",
        repo_root=tmp_path,
    )
    assert "--config" in cmd
    ix = cmd.index("--config")
    assert cmd[ix + 1] == "/settings/profile.json"


def test_run_compare_subprocess_success(tmp_path: Path) -> None:
    root = default_repo_root()
    orig = tmp_path / "o.docx"
    rev = tmp_path / "r.docx"
    out = tmp_path / "out.docx"
    _minimal_docx(orig, "<w:p><w:r><w:t>One</w:t></w:r></w:p>")
    _minimal_docx(rev, "<w:p><w:r><w:t>Two</w:t></w:r></w:p>")
    proc = run_compare_subprocess(
        str(orig),
        str(rev),
        str(out),
        repo_root=root,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()


@patch("desktop.engine_runner.subprocess.run", return_value=MagicMock(returncode=0))
def test_open_path_with_default_app_linux_uses_xdg_open(mock_run: MagicMock, tmp_path: Path) -> None:
    target = tmp_path / "out.docx"
    target.write_bytes(b"x")
    with patch.object(sys, "platform", "linux"):
        err = open_path_with_default_app(target)
    assert err is None
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][0] == "xdg-open"


@patch("desktop.engine_runner.subprocess.run", return_value=MagicMock(returncode=0))
def test_open_path_with_default_app_macos_uses_open(mock_run: MagicMock, tmp_path: Path) -> None:
    target = tmp_path / "out.docx"
    target.write_bytes(b"x")
    with patch.object(sys, "platform", "darwin"):
        err = open_path_with_default_app(target)
    assert err is None
    assert mock_run.call_args[0][0][0] == "open"


@patch("desktop.engine_runner.os.startfile", create=True)
def test_open_path_with_default_app_windows_uses_startfile(mock_startfile: MagicMock, tmp_path: Path) -> None:
    target = tmp_path / "out.docx"
    target.write_bytes(b"x")
    with patch.object(sys, "platform", "win32"):
        err = open_path_with_default_app(target)
    assert err is None
    mock_startfile.assert_called_once()
