"""Preserve Word-friendly namespace prefixes when serializing OOXML with ElementTree.

ElementTree's default serializer maps URIs to ``ns0``, ``ns1``, … on the root. Word's
``mc:Ignorable`` lists conventional prefixes (``w14``, ``w15``, …); if those prefixes
are not declared on the root, Word reports unreadable content and offers repair.

We re-register every ``xmlns:`` binding from the **original** part's root open tag before
``tostring`` so output keeps the same prefixes as the source document.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

_XML_DECL_RE = re.compile(r"^<\?xml[^>]*\?>\s*", re.DOTALL)
_XMLNS_RE = re.compile(r'\sxmlns:([A-Za-z0-9._-]+)="([^"]*)"')
# First-line root for main document / header / footer parts.
_ROOT_OPEN_RE = re.compile(r"(<w:(?:document|hdr|ftr)\b[^>]*>)")


def strip_xml_declaration(xml_text: str) -> str:
    return _XML_DECL_RE.sub("", xml_text, count=1)


def register_prefixes_from_root_open_tag(xml_text: str) -> None:
    """Read the first element's opening tag and call ``ET.register_namespace`` for each xmlns."""
    s = strip_xml_declaration(xml_text)
    mo = _ROOT_OPEN_RE.match(s)
    if not mo:
        gt = s.find(">")
        open_chunk = s[: gt + 1] if gt >= 0 else s
    else:
        open_chunk = mo.group(1)
    for mm in _XMLNS_RE.finditer(open_chunk):
        ET.register_namespace(mm.group(1), mm.group(2))


def serialize_ooxml_part(root: ET.Element, original_raw_xml: bytes) -> bytes:
    """
    Serialize ``root`` with UTF-8 and a Word-style XML declaration.

    Reuses the **original** root opening tag (all ``xmlns:*`` and ``mc:Ignorable``)
    so Word's prefix tokens stay valid, while body markup uses registered prefixes
    from that tag for ``ET.tostring``.
    """
    text = original_raw_xml.decode("utf-8")
    register_prefixes_from_root_open_tag(text)
    stripped = strip_xml_declaration(text)
    m_orig = _ROOT_OPEN_RE.match(stripped)

    ser = ET.tostring(root, encoding="utf-8", xml_declaration=False).decode("utf-8")
    ser = strip_xml_declaration(ser)
    m_ser = _ROOT_OPEN_RE.match(ser)
    if not m_ser:
        raise ValueError(f"Expected w:document / w:hdr / w:ftr root, got: {ser[:120]!r}")
    inner = ser[m_ser.end() :]

    decl = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    if m_orig:
        return decl + m_orig.group(1).encode("utf-8") + inner.encode("utf-8")
    return decl + ser.encode("utf-8")
