from __future__ import annotations

import sys
from pathlib import Path

import pytest

from desktop.desktop_state import cached_output_path, compare_signature
from desktop.word_options import poll_word_saved_path_for_compare_signature


def test_compare_signature_changes_when_config_changes(tmp_path: Path) -> None:
    o = tmp_path / "o.docx"
    r = tmp_path / "r.docx"
    o.write_bytes(b"a")
    r.write_bytes(b"b")

    sig1 = compare_signature(original_path=str(o), revised_path=str(r), compare_config={"ignore_case": False})
    sig2 = compare_signature(original_path=str(o), revised_path=str(r), compare_config={"ignore_case": True})
    assert sig1 != sig2


def test_cached_output_path_includes_signature_and_generation() -> None:
    p = cached_output_path(signature="abc123", generation=7)
    assert p.name == "abc123-7.docx"


@pytest.mark.skipif(sys.platform == "win32", reason="Word may be installed; COM result varies")
def test_poll_word_saved_path_non_windows_returns_none() -> None:
    assert poll_word_saved_path_for_compare_signature("deadbeef") is None
