"""Write a new `.docx` by copying an existing package and replacing selected parts (SCRUM-60)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Union


def _norm_zip_name(name: str) -> str:
    return name.replace("\\", "/")


def write_docx_copy_with_part_replacements(
    source_docx: Union[str, Path],
    dest_docx: Union[str, Path],
    replacements: dict[str, bytes],
) -> None:
    """
    Copy every entry from ``source_docx`` into ``dest_docx``, overwriting bytes for
    keys in ``replacements`` (OOXML zip paths, forward slashes, e.g.
    ``word/document.xml``).
    """

    src = Path(source_docx)
    dst = Path(dest_docx)
    keys = {_norm_zip_name(k): v for k, v in replacements.items()}

    # Performance: writing output can be a major cost on Windows (large corpora).
    # Track Changes correctness is in the XML payloads, not the zip compression.
    # Use ZIP_STORED to avoid per-entry recompression CPU while preserving package layout.
    with (
        zipfile.ZipFile(src, "r") as zin,
        zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_STORED) as zout,
    ):
        for info in zin.infolist():
            name = _norm_zip_name(info.filename)
            payload = keys.get(name, zin.read(info.filename))
            # Fresh ZipInfo so CRC/size match replaced payloads (avoids Word repair).
            zi = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = info.external_attr
            zout.writestr(zi, payload)
