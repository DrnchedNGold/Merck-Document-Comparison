"""
Emit Word Track Changes markup (w:ins / w:del) for matched body paragraphs (SCRUM-59).

Uses the same concatenated-run text and :mod:`difflib` segmentation as
:func:`engine.inline_run_diff.inline_diff_single_paragraph` so output aligns with
inline ``DiffOp`` semantics.

Package-wide emit (SCRUM-64 / MDC-011): ``word/document.xml`` plus each
``word/header*.xml`` / ``word/footer*.xml`` present in the original package,
with one shared ``w:id`` counter across all revised parts.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Union

from .compare_keys import _normalize_text
from .contracts import BodyIR, BodyParagraph, CompareConfig
from .document_package import parse_docx_document_package
from .docx_body_ingest import WORD_NAMESPACE, load_word_document_xml_root
from .docx_output_package import write_docx_copy_with_part_replacements
from .docx_package_parts import DOCUMENT_PART_PATH, discover_header_footer_part_paths

XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
NS = {"w": WORD_NAMESPACE}


def _local_name(tag: str) -> str:
    return tag.split("}", maxsplit=1)[-1] if "}" in tag else tag


def _concat_paragraph_text(paragraph: BodyParagraph, config: CompareConfig) -> str:
    return "".join(
        _normalize_text(str(run.get("text", "")), config) for run in paragraph.get("runs", [])
    )


def _structural_block_elements(container: ET.Element) -> list[ET.Element]:
    """Direct ``w:p`` / ``w:tbl`` children (``w:body``, ``w:hdr``, or ``w:ftr``)."""

    out: list[ET.Element] = []
    for child in container:
        ln = _local_name(child.tag)
        if ln in ("p", "tbl"):
            out.append(child)
    return out


def _paragraph_needs_revision(orig: BodyParagraph, rev: BodyParagraph, config: CompareConfig) -> bool:
    o = _concat_paragraph_text(orig, config)
    r = _concat_paragraph_text(rev, config)
    for tag, *_ in difflib.SequenceMatcher(None, o, r).get_opcodes():
        if tag != "equal":
            return True
    return False


def _next_id(counter: list[int]) -> str:
    counter[0] += 1
    return str(counter[0])


def _w_run_with_t(text: str) -> ET.Element:
    r_el = ET.Element(f"{{{WORD_NAMESPACE}}}r")
    t_el = ET.SubElement(r_el, f"{{{WORD_NAMESPACE}}}t")
    if text[:1].isspace() or text[-1:].isspace() or "\t" in text:
        t_el.set(f"{{{XML_NAMESPACE}}}space", "preserve")
    t_el.text = text
    return r_el


def _w_del_segment(text: str, del_id: str, author: str, date_iso: str) -> ET.Element:
    del_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}del",
        {
            f"{{{WORD_NAMESPACE}}}id": del_id,
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    r_el = ET.SubElement(del_el, f"{{{WORD_NAMESPACE}}}r")
    dt = ET.SubElement(r_el, f"{{{WORD_NAMESPACE}}}delText")
    if text[:1].isspace() or text[-1:].isspace() or "\t" in text:
        dt.set(f"{{{XML_NAMESPACE}}}space", "preserve")
    dt.text = text
    return del_el


def _w_ins_segment(text: str, ins_id: str, author: str, date_iso: str) -> ET.Element:
    ins_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}ins",
        {
            f"{{{WORD_NAMESPACE}}}id": ins_id,
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    ins_el.append(_w_run_with_t(text))
    return ins_el


def build_paragraph_track_change_elements(
    original: BodyParagraph,
    revised: BodyParagraph,
    config: CompareConfig,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """Return ordered ``w:r`` / ``w:ins`` / ``w:del`` children for one ``w:p``."""

    orig_text = _concat_paragraph_text(original, config)
    rev_text = _concat_paragraph_text(revised, config)
    matcher = difflib.SequenceMatcher(None, orig_text, rev_text)
    out: list[ET.Element] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            chunk = orig_text[i1:i2]
            if chunk:
                out.append(_w_run_with_t(chunk))
        elif tag == "delete":
            chunk = orig_text[i1:i2]
            if chunk:
                out.append(_w_del_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "insert":
            chunk = rev_text[j1:j2]
            if chunk:
                out.append(_w_ins_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "replace":
            before = orig_text[i1:i2]
            after = rev_text[j1:j2]
            if before:
                out.append(_w_del_segment(before, _next_id(id_counter), author, date_iso))
            if after:
                out.append(_w_ins_segment(after, _next_id(id_counter), author, date_iso))

    return out


def _apply_track_changes_to_structural_container(
    container: ET.Element,
    original_ir: BodyIR,
    revised_ir: BodyIR,
    config: CompareConfig,
    author: str,
    date_iso: str,
    id_counter: list[int],
) -> None:
    """Mutate ``container`` in place: revision markup on index-paired paragraphs."""

    block_els = _structural_block_elements(container)

    for oi, oblock, rblock in _positional_paragraph_pairs(original_ir, revised_ir):
        if oi < 0 or oi >= len(block_els):
            continue
        p_el = block_els[oi]
        if _local_name(p_el.tag) != "p":
            continue

        orig_para: BodyParagraph = oblock  # type: ignore[assignment]
        rev_para: BodyParagraph = rblock  # type: ignore[assignment]
        if not _paragraph_needs_revision(orig_para, rev_para, config):
            continue

        new_kids = build_paragraph_track_change_elements(
            orig_para,
            rev_para,
            config,
            id_counter=id_counter,
            author=author,
            date_iso=date_iso,
        )
        _replace_p_content_preserving_p_pr(p_el, new_kids)


def _replace_p_content_preserving_p_pr(p_el: ET.Element, new_children: list[ET.Element]) -> None:
    for ch in list(p_el):
        if _local_name(ch.tag) != "pPr":
            p_el.remove(ch)
    insert_at = 0
    for ch in list(p_el):
        if _local_name(ch.tag) == "pPr":
            insert_at = list(p_el).index(ch) + 1
            break
    for i, node in enumerate(new_children):
        p_el.insert(insert_at + i, node)


def _positional_paragraph_pairs(
    original_ir: BodyIR, revised_ir: BodyIR
) -> list[tuple[int, BodyParagraph, BodyParagraph]]:
    """
    Pair top-level paragraph blocks by **index** (0 with 0, 1 with 1, …) up to
    the shorter body length.

    Signature-based :func:`engine.paragraph_alignment.align_paragraphs` only links
    paragraphs whose compare-key signatures match, so edited text in the “same”
    paragraph slot would never pair. Positional pairing matches the trivial
    body-only compare case (same block order, text edits in place).
    """

    ob = original_ir.get("blocks", [])
    rb = revised_ir.get("blocks", [])
    n = min(len(ob), len(rb))
    out: list[tuple[int, BodyParagraph, BodyParagraph]] = []
    for i in range(n):
        o_blk, r_blk = ob[i], rb[i]
        if o_blk.get("type") == "paragraph" and r_blk.get("type") == "paragraph":
            out.append((i, o_blk, r_blk))  # type: ignore[arg-type]
    return out


def apply_body_track_changes_to_document_root(
    document_root: ET.Element,
    original_ir: BodyIR,
    revised_ir: BodyIR,
    config: CompareConfig,
    *,
    author: str = "MerckDocCompare",
    date_iso: str | None = None,
    id_counter: list[int] | None = None,
) -> None:
    """
    Mutate ``document_root`` (``w:document``): for each index-paired paragraph
    block that differs, replace non-``w:pPr`` content under the corresponding
    ``w:p`` with Track Changes children.

    When ``id_counter`` is omitted, a fresh counter is used for this part only.
    Pass a shared list for package-wide unique ``w:id`` values (MDC-011).
    """

    if date_iso is None:
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    body = document_root.find("w:body", NS)
    if body is None:
        return

    counter = id_counter if id_counter is not None else [0]
    _apply_track_changes_to_structural_container(
        body,
        original_ir,
        revised_ir,
        config,
        author,
        date_iso,
        counter,
    )


def apply_track_changes_to_hdr_ftr_root(
    hdr_or_ftr_root: ET.Element,
    original_ir: BodyIR,
    revised_ir: BodyIR,
    config: CompareConfig,
    *,
    author: str = "MerckDocCompare",
    date_iso: str | None = None,
    id_counter: list[int] | None = None,
) -> None:
    """
    Mutate a ``w:hdr`` or ``w:ftr`` root in place using the same positional
    paragraph pairing as the main document body.
    """

    ln = _local_name(hdr_or_ftr_root.tag)
    if ln not in ("hdr", "ftr"):
        raise ValueError(
            f"Expected w:hdr or w:ftr root element, got local name {ln!r}."
        )
    if date_iso is None:
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counter = id_counter if id_counter is not None else [0]
    _apply_track_changes_to_structural_container(
        hdr_or_ftr_root,
        original_ir,
        revised_ir,
        config,
        author,
        date_iso,
        counter,
    )


def emit_docx_with_package_track_changes(
    original_docx: Union[str, Path],
    revised_docx: Union[str, Path],
    output_docx: Union[str, Path],
    config: CompareConfig,
    *,
    author: str = "MerckDocCompare",
    date_iso: str | None = None,
) -> None:
    """
    Apply Track Changes to ``word/document.xml`` and every header/footer part
    present in the original package, using a single ``w:id`` sequence across
    all touched parts. Revised content comes from the corresponding IR in the
    revised ``.docx`` (missing parts use an empty body IR).
    """

    orig_path = Path(original_docx)
    rev_path = Path(revised_docx)
    out_path = Path(output_docx)

    orig_pkg = parse_docx_document_package(orig_path)
    rev_pkg = parse_docx_document_package(rev_path)

    if date_iso is None:
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    id_counter = [0]
    root = load_word_document_xml_root(orig_path)
    apply_body_track_changes_to_document_root(
        root,
        orig_pkg["document"],
        rev_pkg["document"],
        config,
        author=author,
        date_iso=date_iso,
        id_counter=id_counter,
    )

    ET.register_namespace("w", WORD_NAMESPACE)
    ET.register_namespace("xml", XML_NAMESPACE)

    replacements: dict[str, bytes] = {
        DOCUMENT_PART_PATH: ET.tostring(root, encoding="utf-8", xml_declaration=True),
    }

    empty_ir: BodyIR = {"version": 1, "blocks": []}
    with zipfile.ZipFile(orig_path, "r") as zin:
        for part in discover_header_footer_part_paths(orig_path):
            raw = zin.read(part)
            hf_root = ET.fromstring(raw)
            o_ir = orig_pkg["header_footer"].get(part, empty_ir)
            r_ir = rev_pkg["header_footer"].get(part, empty_ir)
            apply_track_changes_to_hdr_ftr_root(
                hf_root,
                o_ir,
                r_ir,
                config,
                author=author,
                date_iso=date_iso,
                id_counter=id_counter,
            )
            replacements[part] = ET.tostring(
                hf_root, encoding="utf-8", xml_declaration=True
            )

    write_docx_copy_with_part_replacements(orig_path, out_path, replacements)


def emit_docx_with_body_track_changes(
    original_docx: Union[str, Path],
    revised_docx: Union[str, Path],
    output_docx: Union[str, Path],
    config: CompareConfig,
    *,
    author: str = "MerckDocCompare",
    date_iso: str | None = None,
) -> None:
    """
    Read two ``.docx`` files and write ``output_docx`` with Track Changes on
    the main document and all header/footer parts (same as
    :func:`emit_docx_with_package_track_changes`).
    """

    emit_docx_with_package_track_changes(
        original_docx,
        revised_docx,
        output_docx,
        config,
        author=author,
        date_iso=date_iso,
    )
