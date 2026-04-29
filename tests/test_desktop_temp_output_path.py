from __future__ import annotations

from desktop.desktop_state import make_temp_output_docx_path


def test_make_temp_output_docx_path_creates_real_docx_file() -> None:
    p = make_temp_output_docx_path(prefix="merck-test-")
    try:
        assert p.suffix == ".docx"
        assert p.is_file()
        assert p.name.startswith("merck-test-")
    finally:
        p.unlink(missing_ok=True)

