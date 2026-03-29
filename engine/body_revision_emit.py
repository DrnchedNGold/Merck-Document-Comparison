"""
Emit Word Track Changes markup (w:ins / w:del) for body paragraphs (SCRUM-59).

Paragraphs are aligned with :func:`engine.paragraph_alignment.align_paragraphs` (LCS
on block signatures) so **new paragraphs only in the revised document** become
inserted ``w:p`` elements with ``w:ins``, and paragraphs only in the original become
full-paragraph ``w:del``. Matched paragraphs use **word/whitespace** tokens (``\\S+`` / ``\\s+``). When a
word-level ``replace`` covers multiple tokens, we **sub-diff again at word level**
on that span so phrases like ``overall response rate … 12`` vs ``progression-free
survival … 24`` become separate ``w:del`` / ``w:ins`` markers per word (with shared
fragments like ``at week`` left as normal text). If a nested replace still has
multiple words on a side, we diff **word tokens** (``\\S+``) only—never a
character-level matcher on unrelated phrases, which would align stray letters
and merge the whole clause into one deletion.
Inline ``DiffOp`` generation remains character-based in :mod:`engine.inline_run_diff`.

Package-wide emit (SCRUM-64 / MDC-011): ``word/document.xml`` plus each
``word/header*.xml`` / ``word/footer*.xml`` present in the original package,
with one shared ``w:id`` counter across all revised parts.

**OOXML scope:** Inserts/deletes are emitted with ``w:id``, ``w:author``, and ``w:date``
(ECMA-376 Track Changes). The product catalog (MDC-010) does not currently require
additional Word-specific attributes (for example ``w:rsid*`` on runs or paragraphs).
If Word rejects or rewrites output on real sponsor documents, capture a failing case
and extend markup in a dedicated parity task rather than guessing attributes here.
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Union

from .compare_keys import _normalize_text
from .contracts import BodyIR, BodyParagraph, CompareConfig
from .document_package import parse_docx_document_package
from .paragraph_alignment import ParagraphAlignment, align_paragraphs
from .docx_body_ingest import WORD_NAMESPACE
from .docx_output_package import write_docx_copy_with_part_replacements
from .docx_package_parts import (
    DOCUMENT_PART_PATH,
    discover_header_footer_part_paths,
    discover_header_footer_part_paths_from_namelist,
)
from .ooxml_namespace import serialize_ooxml_part

XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
NS = {"w": WORD_NAMESPACE}


def _local_name(tag: str) -> str:
    return tag.split("}", maxsplit=1)[-1] if "}" in tag else tag


def _concat_paragraph_text(paragraph: BodyParagraph, config: CompareConfig) -> str:
    return "".join(
        _normalize_text(str(run.get("text", "")), config) for run in paragraph.get("runs", [])
    )


def _word_level_tokens(text: str) -> list[str]:
    """Split into runs of non-whitespace (words, numbers, punctuation clumps) and whitespace."""
    return re.findall(r"\S+|\s+", text)


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
    if o == r:
        return False
    ot, rt = _word_level_tokens(o), _word_level_tokens(r)
    for tag, *_ in difflib.SequenceMatcher(None, ot, rt, autojunk=False).get_opcodes():
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


def _replace_span_is_multi_token(before: str, after: str) -> bool:
    """True when the replaced text spans more than one word token or includes spaces."""
    if not before and not after:
        return False
    for s in (before, after):
        if re.search(r"\s", s):
            return True
        if len(re.findall(r"\S+", s)) > 1:
            return True
    return False


def _emit_word_only_track_change_fragment(
    before: str,
    after: str,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """
    Diff on ``\\S+`` tokens only (no whitespace runs).

    Used when a word-token replace span still has multiple words on a side but
    no reliable character alignment (unrelated phrases). ``equal`` runs join
    words with a single ASCII space (acceptable for clinical prose).
    """

    out: list[ET.Element] = []
    lead_b = re.match(r"^\s+", before)
    if lead_b:
        out.append(_w_run_with_t(lead_b.group(0)))
    trail_b = re.search(r"\s+$", before)
    trail_b_s = trail_b.group(0) if trail_b else ""

    wb = re.findall(r"\S+", before)
    wa = re.findall(r"\S+", after)
    if not wb and not wa:
        if trail_b_s:
            out.append(_w_run_with_t(trail_b_s))
        return out

    sm = difflib.SequenceMatcher(None, wb, wa, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            if i1 < i2:
                out.append(_w_run_with_t(" ".join(wb[i1:i2])))
        elif tag == "delete":
            for w in wb[i1:i2]:
                out.append(_w_del_segment(w, _next_id(id_counter), author, date_iso))
        elif tag == "insert":
            for w in wa[j1:j2]:
                out.append(_w_ins_segment(w, _next_id(id_counter), author, date_iso))
        elif tag == "replace":
            slice_b, slice_a = wb[i1:i2], wa[j1:j2]
            nb, na = len(slice_b), len(slice_a)
            for k in range(min(nb, na)):
                out.append(
                    _w_del_segment(slice_b[k], _next_id(id_counter), author, date_iso)
                )
                out.append(
                    _w_ins_segment(slice_a[k], _next_id(id_counter), author, date_iso)
                )
            for k in range(min(nb, na), nb):
                out.append(
                    _w_del_segment(slice_b[k], _next_id(id_counter), author, date_iso)
                )
            for k in range(min(nb, na), na):
                out.append(
                    _w_ins_segment(slice_a[k], _next_id(id_counter), author, date_iso)
                )
    if trail_b_s:
        out.append(_w_run_with_t(trail_b_s))
    return out


def _emit_word_token_track_change_fragment(
    before: str,
    after: str,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """
    Word-token diff on a substring (typically the ``before``/``after`` of a
    multi-token outer ``replace``).

    Character-level diff on long unrelated phrases often yields a single huge
    ``replace`` opcode → one ``w:del`` for the whole clause. Re-running LCS on
    tokens pulls out shared pieces (e.g. `` at week ``) and splits outgoing words
    into separate revision markers.
    """

    out: list[ET.Element] = []
    if not before and not after:
        return out
    if not before:
        if after:
            out.append(_w_ins_segment(after, _next_id(id_counter), author, date_iso))
        return out
    if not after:
        out.append(_w_del_segment(before, _next_id(id_counter), author, date_iso))
        return out

    ot, rt = _word_level_tokens(before), _word_level_tokens(after)
    sm = difflib.SequenceMatcher(None, ot, rt, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            chunk = "".join(ot[i1:i2])
            if chunk:
                out.append(_w_run_with_t(chunk))
        elif tag == "delete":
            chunk = "".join(ot[i1:i2])
            if chunk:
                out.append(_w_del_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "insert":
            chunk = "".join(rt[j1:j2])
            if chunk:
                out.append(_w_ins_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "replace":
            b = "".join(ot[i1:i2])
            a = "".join(rt[j1:j2])
            if not _replace_span_is_multi_token(b, a):
                if b:
                    out.append(_w_del_segment(b, _next_id(id_counter), author, date_iso))
                if a:
                    out.append(_w_ins_segment(a, _next_id(id_counter), author, date_iso))
            else:
                out.extend(
                    _emit_word_only_track_change_fragment(
                        b,
                        a,
                        id_counter=id_counter,
                        author=author,
                        date_iso=date_iso,
                    )
                )
    return out


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
    orig_tokens = _word_level_tokens(orig_text)
    rev_tokens = _word_level_tokens(rev_text)
    matcher = difflib.SequenceMatcher(None, orig_tokens, rev_tokens, autojunk=False)
    out: list[ET.Element] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            chunk = "".join(orig_tokens[i1:i2])
            if chunk:
                out.append(_w_run_with_t(chunk))
        elif tag == "delete":
            chunk = "".join(orig_tokens[i1:i2])
            if chunk:
                out.append(_w_del_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "insert":
            chunk = "".join(rev_tokens[j1:j2])
            if chunk:
                out.append(_w_ins_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "replace":
            before = "".join(orig_tokens[i1:i2])
            after = "".join(rev_tokens[j1:j2])
            if _replace_span_is_multi_token(before, after):
                out.extend(
                    _emit_word_token_track_change_fragment(
                        before,
                        after,
                        id_counter=id_counter,
                        author=author,
                        date_iso=date_iso,
                    )
                )
            else:
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
    """Mutate ``container`` in place using LCS paragraph alignment (inserts, deletes, in-place edits)."""

    block_els = _structural_block_elements(container)
    ob = original_ir.get("blocks", [])
    rb = revised_ir.get("blocks", [])

    # Always run LCS alignment when A/B block counts differ. A legacy branch used to
    # return early with index-only pairing when ``len(block_els) != len(ob)``, which
    # skipped :func:`align_paragraphs` entirely—so real docs (extra paragraph in B,
    # slightly different OOXML shape) never got fuzzy-matched paragraphs and showed
    # whole-paragraph delete/insert instead of in-place word revisions.

    # Same block count: pair by index so in-place text edits (e.g. ``Hi`` → ``Hi there``)
    # stay one paragraph with word-level ins/del. When counts differ, LCS finds inserted /
    # deleted paragraphs (lines only in A or only in B).
    if len(ob) == len(rb):
        alignment = [ParagraphAlignment(i, i) for i in range(len(ob))]
    else:
        alignment = align_paragraphs(original_ir, revised_ir, config)
    empty_rev = _empty_body_paragraph()

    for step_i, al in enumerate(alignment):
        oi = al.original_paragraph_index
        rj = al.revised_paragraph_index

        if oi is not None and rj is not None:
            if oi >= len(block_els):
                continue
            oblock, rblock = ob[oi], rb[rj]
            el = block_els[oi]
            if oblock.get("type") != "paragraph" or rblock.get("type") != "paragraph":
                continue
            if _local_name(el.tag) != "p":
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
            _replace_p_content_preserving_p_pr(el, new_kids)
        elif oi is not None and rj is None:
            if oi >= len(block_els):
                continue
            oblock = ob[oi]
            el = block_els[oi]
            if oblock.get("type") != "paragraph":
                continue
            if _local_name(el.tag) != "p":
                continue
            orig_para = oblock  # type: ignore[assignment]
            if not _paragraph_needs_revision(orig_para, empty_rev, config):
                continue
            new_kids = build_paragraph_track_change_elements(
                orig_para,
                empty_rev,
                config,
                id_counter=id_counter,
                author=author,
                date_iso=date_iso,
            )
            _replace_p_content_preserving_p_pr(el, new_kids)
        elif oi is None and rj is not None:
            rblock = rb[rj]
            if rblock.get("type") != "paragraph":
                continue
            rev_para = rblock  # type: ignore[assignment]
            if not _paragraph_needs_revision(empty_rev, rev_para, config):
                continue
            idx = _body_insert_index_before_next_orig_block(
                container, alignment, step_i, block_els
            )
            new_p = _new_w_p_from_full_paragraph_insert(
                rev_para,
                config,
                id_counter=id_counter,
                author=author,
                date_iso=date_iso,
            )
            container.insert(idx, new_p)


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


def _empty_body_paragraph() -> BodyParagraph:
    return {"type": "paragraph", "id": "_", "runs": []}


def _body_insert_index_before_next_orig_block(
    container: ET.Element,
    alignment: list,
    step_index: int,
    block_els: list[ET.Element],
) -> int:
    """DOM index in ``container`` to insert a new block before the next original block (or before ``sectPr``)."""

    children = list(container)
    next_oi: int | None = None
    for k in range(step_index + 1, len(alignment)):
        oi = alignment[k].original_paragraph_index
        if oi is not None:
            next_oi = oi
            break
    if next_oi is not None and next_oi < len(block_els):
        anchor = block_els[next_oi]
        return children.index(anchor)
    sect = container.find("w:sectPr", NS)
    if sect is not None:
        return children.index(sect)
    return len(children)


def _new_w_p_from_full_paragraph_insert(
    rev_para: BodyParagraph,
    config: CompareConfig,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> ET.Element:
    """A ``w:p`` whose content is Track Changes for text that exists only in the revised document."""
    kids = build_paragraph_track_change_elements(
        _empty_body_paragraph(),
        rev_para,
        config,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )
    p_el = ET.Element(f"{{{WORD_NAMESPACE}}}p")
    for node in kids:
        p_el.append(node)
    return p_el


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
    Mutate ``document_root`` (``w:document``): align body blocks to the revised IR,
    then apply Track Changes (including inserted ``w:p`` / full-paragraph deletes).

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
    Mutate a ``w:hdr`` or ``w:ftr`` root in place using the same LCS block alignment
    as the main document body.
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
    with zipfile.ZipFile(orig_path, "r") as zin:
        raw_document_xml = zin.read(DOCUMENT_PART_PATH)
    root = ET.fromstring(raw_document_xml)
    apply_body_track_changes_to_document_root(
        root,
        orig_pkg["document"],
        rev_pkg["document"],
        config,
        author=author,
        date_iso=date_iso,
        id_counter=id_counter,
    )

    replacements: dict[str, bytes] = {
        DOCUMENT_PART_PATH: serialize_ooxml_part(root, raw_document_xml),
    }

    empty_ir: BodyIR = {"version": 1, "blocks": []}
    with zipfile.ZipFile(orig_path, "r") as zin:
        for part in discover_header_footer_part_paths_from_namelist(zin.namelist()):
            raw_hf = zin.read(part)
            hf_root = ET.fromstring(raw_hf)
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
            replacements[part] = serialize_ooxml_part(hf_root, raw_hf)

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
