"""Preserve Word-friendly namespace prefixes when serializing OOXML with ElementTree.

ElementTree's default serializer maps URIs to ``ns0``, ``ns1``, … on the root. Word's
``mc:Ignorable`` lists conventional prefixes (``w14``, ``w15``, …); if those prefixes
are not declared on the root, Word reports unreadable content and offers repair.

We register every ``xmlns:`` binding found **anywhere** in the original part before
``tostring`` so ElementTree reuses conventional prefixes (``a``, ``wp``, …) instead of
``ns0``. After ``tostring``, inner markup may still use a prefix that was only declared
on a descendant in the source; we then add missing ``xmlns:*`` bindings onto the
spliced root open tag so the part stays namespace-well-formed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

_XML_DECL_RE = re.compile(r"^<\?xml[^>]*\?>\s*", re.DOTALL)
_XMLNS_RE = re.compile(r'\sxmlns:([A-Za-z0-9._-]+)="([^"]*)"')
# First-line root for main document / header / footer / settings parts.
_ROOT_OPEN_RE = re.compile(r"(<w:(?:document|hdr|ftr|settings)\b[^>]*>)")


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


def register_all_xmlns_prefixes_from_part(xml_text: str) -> None:
    """Call ``ET.register_namespace`` for every ``xmlns:prefix`` in the part (root and descendants)."""
    s = strip_xml_declaration(xml_text)
    for mm in _XMLNS_RE.finditer(s):
        ET.register_namespace(mm.group(1), mm.group(2))


def _prefix_to_uri_map_from_part(xml_text: str) -> dict[str, str]:
    """Last ``xmlns:prefix`` wins (same as typical Word serialization)."""
    s = strip_xml_declaration(xml_text)
    m: dict[str, str] = {}
    for mm in _XMLNS_RE.finditer(s):
        m[mm.group(1)] = mm.group(2)
    return m


def _prefixes_declared_on_open_tag(open_tag: str) -> set[str]:
    return {mm.group(1) for mm in _XMLNS_RE.finditer(open_tag)}


def _prefixes_used_in_inner_xml(inner: str) -> set[str]:
    """Collect namespace prefixes used on elements/attributes (not ``xmlns:…`` declarations)."""
    used: set[str] = set()
    for mm in re.finditer(r"</?([A-Za-z_][\w.-]*):", inner):
        used.add(mm.group(1))
    for mm in re.finditer(r'[\s\'"]([A-Za-z_][\w.-]*):[A-Za-z_][\w.-]*\s*=', inner):
        p = mm.group(1)
        if p != "xmlns":
            used.add(p)
    return used


def _augment_root_open_tag_for_inner_prefixes(
    root_open_tag: str,
    inner: str,
    prefix_to_uri: dict[str, str],
) -> str:
    """Append ``xmlns:`` for any prefix that appears in ``inner`` but is missing from the root."""
    declared = _prefixes_declared_on_open_tag(root_open_tag)
    need = _prefixes_used_in_inner_xml(inner) - declared
    if not need:
        return root_open_tag
    extras: list[str] = []
    for p in sorted(need):
        uri = prefix_to_uri.get(p)
        if uri is not None:
            extras.append(f' xmlns:{p}="{uri}"')
    if not extras:
        return root_open_tag
    if not root_open_tag.endswith(">"):
        return root_open_tag
    return root_open_tag[:-1] + "".join(extras) + ">"


def _merge_missing_xmlns_declarations(root_open_tag: str, donor_open_tag: str) -> str:
    """Copy any missing ``xmlns:*`` bindings from *donor_open_tag* onto *root_open_tag*."""

    declared = _prefixes_declared_on_open_tag(root_open_tag)
    extras: list[str] = []
    for mm in _XMLNS_RE.finditer(donor_open_tag):
        prefix = mm.group(1)
        if prefix not in declared:
            extras.append(f' xmlns:{prefix}="{mm.group(2)}"')
            declared.add(prefix)
    if not extras or not root_open_tag.endswith(">"):
        return root_open_tag
    return root_open_tag[:-1] + "".join(extras) + ">"


def serialize_ooxml_part(root: ET.Element, original_raw_xml: bytes) -> bytes:
    """
    Serialize ``root`` with UTF-8 and a Word-style XML declaration.

    Reuses the **original** root opening tag (all ``xmlns:*`` and ``mc:Ignorable``)
    so Word's prefix tokens stay valid, while body markup uses registered prefixes
    from that tag for ``ET.tostring``.
    """
    text = original_raw_xml.decode("utf-8")
    register_all_xmlns_prefixes_from_part(text)
    prefix_to_uri = _prefix_to_uri_map_from_part(text)
    stripped = strip_xml_declaration(text)
    m_orig = _ROOT_OPEN_RE.match(stripped)

    ser = ET.tostring(root, encoding="utf-8", xml_declaration=False).decode("utf-8")
    ser = strip_xml_declaration(ser)
    m_ser = _ROOT_OPEN_RE.match(ser)
    if not m_ser:
        raise ValueError(f"Expected w:document / w:hdr / w:ftr / w:settings root, got: {ser[:120]!r}")
    inner = ser[m_ser.end() :]

    decl = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    if m_orig:
        root_open = m_orig.group(1)
        if m_ser:
            root_open = _merge_missing_xmlns_declarations(root_open, m_ser.group(1))
        root_open = _augment_root_open_tag_for_inner_prefixes(root_open, inner, prefix_to_uri)
        return decl + root_open.encode("utf-8") + inner.encode("utf-8")
    return decl + ser.encode("utf-8")
