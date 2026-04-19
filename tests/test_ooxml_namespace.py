"""Word OOXML: preserve xmlns prefixes so mc:Ignorable prefix tokens resolve (SCRUM-83 follow-up)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from engine.ooxml_namespace import register_prefixes_from_root_open_tag, serialize_ooxml_part

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def test_serialize_preserves_w14_prefix_not_ns0() -> None:
    original = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{WORD_NS}" xmlns:w14="{W14_NS}" xmlns:mc="{MC_NS}" mc:Ignorable="w14">
  <w:body><w:p w14:paraId="11111111" w14:textId="77777777"><w:r><w:t>Hi</w:t></w:r></w:p></w:body>
</w:document>
"""
    root = ET.fromstring(original.encode("utf-8"))
    out = serialize_ooxml_part(root, original.encode("utf-8")).decode("utf-8")
    assert "xmlns:w14=" in out
    assert "w14:paraId=" in out
    assert "xmlns:ns" not in out.split("<w:body", 1)[0]
    assert "mc:Ignorable=" in out or "Ignorable=" in out


def test_serialize_keeps_extra_serialized_xmlns_bindings_when_reusing_original_root() -> None:
    original = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{WORD_NS}" xmlns:mc="{MC_NS}" mc:Ignorable="w14">
  <w:p><w:r><w:t>Foot</w:t></w:r></w:p>
</w:ftr>
"""
    root = ET.fromstring(original.encode("utf-8"))
    drawing_uri = "http://example.com/drawing"
    pic_uri = "http://example.com/picture"
    p = root.find(f".//{{{WORD_NS}}}p")
    assert p is not None
    p.set("{http://schemas.microsoft.com/office/word/2010/wordml}paraId", "12345678")
    r = ET.SubElement(p, f"{{{WORD_NS}}}r")
    drawing = ET.SubElement(r, f"{{{drawing_uri}}}graphic")
    ET.SubElement(drawing, f"{{{pic_uri}}}pic")

    out = serialize_ooxml_part(root, original.encode("utf-8")).decode("utf-8")
    assert "xmlns:w14=" in out
    assert "w14:paraId=" in out
    assert "xmlns:ns" in out.split("\n", 1)[1].split(">", 1)[0]
    ET.fromstring(out.encode("utf-8"))
