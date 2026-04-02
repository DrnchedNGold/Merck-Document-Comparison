"""
Emit Word Track Changes markup (w:ins / w:del) for body paragraphs (SCRUM-59).

Top-level blocks are aligned with
:func:`engine.paragraph_alignment.alignment_for_track_changes_emit` (index ``(i,i)``
when counts and types match; otherwise LCS via :func:`~engine.paragraph_alignment.align_paragraphs`)
so **new blocks only in the revised document** become
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

Ingest maps ``w:tab`` inside ``w:r`` to ``\\t`` in run text; emit splits on ``\\t`` and
outputs ``w:tab`` elements again so TOC lines keep tab stops (dot leaders from ``w:pPr``).
Matched ``w:p`` with ``TOC*`` styles use :func:`_build_toc_matched_line_track_change_elements`
(tab-preserving concat when *ignore_whitespace* is True, SCRUM-112). The public
:func:`build_paragraph_track_change_elements` path is unchanged for non-TOC content.
"""

from __future__ import annotations

import copy
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
from .paragraph_alignment import alignment_for_track_changes_emit
from .docx_body_ingest import WORD_NAMESPACE
from .docx_output_package import write_docx_copy_with_part_replacements
from .docx_package_parts import (
    DOCUMENT_PART_PATH,
    discover_header_footer_part_paths,
    discover_header_footer_part_paths_from_namelist,
)
from .ooxml_namespace import serialize_ooxml_part
from .table_diff import _cell_concat_paragraph, _table_shape

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


def _token_level_text_differs(o: str, r: str) -> bool:
    if o == r:
        return False
    ot, rt = _word_level_tokens(o), _word_level_tokens(r)
    for tag, *_ in difflib.SequenceMatcher(None, ot, rt, autojunk=False).get_opcodes():
        if tag != "equal":
            return True
    return False


def _structural_block_elements(container: ET.Element) -> list[ET.Element]:
    """Direct ``w:p`` / ``w:tbl`` children (``w:body``, ``w:hdr``, or ``w:ftr``)."""

    out: list[ET.Element] = []
    for child in container:
        ln = _local_name(child.tag)
        if ln in ("p", "tbl"):
            out.append(child)
    return out


def _structural_block_elements_for_part_root(root: ET.Element, part_path: str) -> list[ET.Element]:
    """Top-level ``w:p`` / ``w:tbl`` for ``word/document.xml`` or a header/footer root."""

    if part_path == DOCUMENT_PART_PATH:
        body = root.find("w:body", NS)
        if body is None:
            return []
        return _structural_block_elements(body)
    ln = _local_name(root.tag)
    if ln in ("hdr", "ftr"):
        return _structural_block_elements(root)
    return []


def load_structural_block_elements_from_docx_part(zf: zipfile.ZipFile, part_path: str) -> list[ET.Element]:
    """Parse one package part and return structural block elements in document order."""

    raw = zf.read(part_path)
    root = ET.fromstring(raw)
    return _structural_block_elements_for_part_root(root, part_path)


def _paragraph_style_is_toc(p_el: ET.Element) -> bool:
    """
    True when the paragraph uses a Word TOC line style (``TOC1`` … ``TOC9``, etc.).

    Standalone TOC insert/delete emit must preserve ``w:tab`` / tab leaders and run
    layout; body IR text alone drops tabs and collapses TOC lines.
    """

    ppr = p_el.find("w:pPr", NS)
    if ppr is None:
        return False
    ps = ppr.find("w:pStyle", NS)
    if ps is None:
        return False
    val = ps.get(f"{{{WORD_NAMESPACE}}}val")
    if not val:
        return False
    u = val.strip().upper()
    return u.startswith("TOC")


def _runs_convert_w_t_to_del_text(root: ET.Element) -> None:
    """In-place: each ``w:t`` directly under ``w:r`` becomes ``w:delText`` (Track Changes delete)."""

    for r_el in root.iter():
        if _local_name(r_el.tag) != "r":
            continue
        for idx, ch in enumerate(list(r_el)):
            if _local_name(ch.tag) != "t":
                continue
            r_el.remove(ch)
            dt = ET.Element(f"{{{WORD_NAMESPACE}}}delText")
            for k, v in ch.attrib.items():
                dt.set(k, v)
            dt.text = ch.text
            dt.tail = ch.tail
            r_el.insert(idx, dt)


def _new_w_p_toc_insert_from_revised_source(
    p_rev_source: ET.Element,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> ET.Element:
    """
    Build a ``w:p`` for a revised-only TOC line: ``w:pPr`` unchanged, body wrapped in one ``w:ins``.

    Deep-copies runs so ``w:tab``, paragraph styles, and run formatting are preserved.
    """

    p_out = ET.Element(f"{{{WORD_NAMESPACE}}}p")
    ins_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}ins",
        {
            f"{{{WORD_NAMESPACE}}}id": _next_id(id_counter),
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    for ch in p_rev_source:
        ln = _local_name(ch.tag)
        if ln == "pPr":
            p_out.append(copy.deepcopy(ch))
        else:
            ins_el.append(copy.deepcopy(ch))
    p_out.append(ins_el)
    return p_out


def _replace_toc_paragraph_with_del_preserving_layout(
    p_el: ET.Element,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> None:
    """
    Full-paragraph delete for a TOC-style line: wrap a deep copy of content in ``w:del``.

    Replaces non-``pPr`` children; ``w:t`` in runs becomes ``w:delText`` inside ``w:del``.
    """

    del_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}del",
        {
            f"{{{WORD_NAMESPACE}}}id": _next_id(id_counter),
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    for ch in list(p_el):
        if _local_name(ch.tag) == "pPr":
            continue
        clone = copy.deepcopy(ch)
        _runs_convert_w_t_to_del_text(clone)
        del_el.append(clone)
        p_el.remove(ch)
    insert_at = 0
    for i, ch in enumerate(p_el):
        if _local_name(ch.tag) == "pPr":
            insert_at = i + 1
            break
    p_el.insert(insert_at, del_el)


def _paragraph_needs_revision(orig: BodyParagraph, rev: BodyParagraph, config: CompareConfig) -> bool:
    o = _concat_paragraph_text(orig, config)
    r = _concat_paragraph_text(rev, config)
    return _token_level_text_differs(o, r)


def _next_id(counter: list[int]) -> str:
    counter[0] += 1
    return str(counter[0])


def _text_needs_xml_space_preserve(text: str) -> bool:
    if not text:
        return False
    return text[:1].isspace() or text[-1:].isspace()


def _w_tab_run() -> ET.Element:
    r_el = ET.Element(f"{{{WORD_NAMESPACE}}}r")
    ET.SubElement(r_el, f"{{{WORD_NAMESPACE}}}tab")
    return r_el


def _w_run_single_t(text: str) -> ET.Element:
    """One ``w:r`` with ``w:t`` only (no ``\\t`` in *text* — use :func:`_w_runs_for_plain_text`)."""

    assert "\t" not in text
    r_el = ET.Element(f"{{{WORD_NAMESPACE}}}r")
    t_el = ET.SubElement(r_el, f"{{{WORD_NAMESPACE}}}t")
    if _text_needs_xml_space_preserve(text):
        t_el.set(f"{{{XML_NAMESPACE}}}space", "preserve")
    t_el.text = text
    return r_el


def _w_runs_for_plain_text(text: str) -> list[ET.Element]:
    """``w:r`` sequence: ``w:t`` segments separated by ``w:tab`` for each ``\\t``."""

    if not text:
        return []
    if "\t" not in text:
        return [_w_run_single_t(text)]
    out: list[ET.Element] = []
    for i, part in enumerate(text.split("\t")):
        if i > 0:
            out.append(_w_tab_run())
        if part:
            out.append(_w_run_single_t(part))
    return out


def _w_del_segment(text: str, del_id: str, author: str, date_iso: str) -> ET.Element:
    del_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}del",
        {
            f"{{{WORD_NAMESPACE}}}id": del_id,
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    for i, part in enumerate(text.split("\t")):
        if i > 0:
            del_el.append(_w_tab_run())
        if not part:
            continue
        r_el = ET.SubElement(del_el, f"{{{WORD_NAMESPACE}}}r")
        dt = ET.SubElement(r_el, f"{{{WORD_NAMESPACE}}}delText")
        if _text_needs_xml_space_preserve(part):
            dt.set(f"{{{XML_NAMESPACE}}}space", "preserve")
        dt.text = part
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
    for run in _w_runs_for_plain_text(text):
        ins_el.append(run)
    return ins_el


def _emit_single_token_replace_fragment(
    before: str,
    after: str,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """
    Emit a fine-grained replacement for single-token spans.

    Preserves shared prefix/suffix as plain runs so only true differences are
    wrapped in w:del / w:ins (for example, ``1.0`` -> ``2.0`` keeps ``.0``).
    """

    if before == after:
        return [_w_run_single_t(before)] if before else []

    if not before:
        return [_w_ins_segment(after, _next_id(id_counter), author, date_iso)] if after else []
    if not after:
        return [_w_del_segment(before, _next_id(id_counter), author, date_iso)]

    min_len = min(len(before), len(after))
    prefix_len = 0
    while prefix_len < min_len and before[prefix_len] == after[prefix_len]:
        prefix_len += 1

    max_suffix = min_len - prefix_len
    suffix_len = 0
    while suffix_len < max_suffix and before[-(suffix_len + 1)] == after[-(suffix_len + 1)]:
        suffix_len += 1

    prefix = before[:prefix_len]
    before_mid_end = len(before) - suffix_len if suffix_len else len(before)
    after_mid_end = len(after) - suffix_len if suffix_len else len(after)
    before_mid = before[prefix_len:before_mid_end]
    after_mid = after[prefix_len:after_mid_end]
    suffix = before[-suffix_len:] if suffix_len else ""

    out: list[ET.Element] = []
    if prefix:
        out.append(_w_run_single_t(prefix))
    if before_mid:
        out.append(_w_del_segment(before_mid, _next_id(id_counter), author, date_iso))
    if after_mid:
        out.append(_w_ins_segment(after_mid, _next_id(id_counter), author, date_iso))
    if suffix:
        out.append(_w_run_single_t(suffix))
    return out


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
        out.extend(_w_runs_for_plain_text(lead_b.group(0)))
    trail_b = re.search(r"\s+$", before)
    trail_b_s = trail_b.group(0) if trail_b else ""

    wb = re.findall(r"\S+", before)
    wa = re.findall(r"\S+", after)
    if not wb and not wa:
        if trail_b_s:
            out.extend(_w_runs_for_plain_text(trail_b_s))
        return out

    sm = difflib.SequenceMatcher(None, wb, wa, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            if i1 < i2:
                out.extend(_w_runs_for_plain_text(" ".join(wb[i1:i2])))
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
        out.extend(_w_runs_for_plain_text(trail_b_s))
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
                out.extend(_w_runs_for_plain_text(chunk))
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
                out.extend(
                    _emit_single_token_replace_fragment(
                        b,
                        a,
                        id_counter=id_counter,
                        author=author,
                        date_iso=date_iso,
                    )
                )
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


def _track_change_elements_for_concat_texts(
    orig_text: str,
    rev_text: str,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """Word/whitespace token diff → ``w:r`` / ``w:ins`` / ``w:del`` (shared by paragraph + TOC paths)."""

    orig_tokens = _word_level_tokens(orig_text)
    rev_tokens = _word_level_tokens(rev_text)
    matcher = difflib.SequenceMatcher(None, orig_tokens, rev_tokens, autojunk=False)
    out: list[ET.Element] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            chunk = "".join(orig_tokens[i1:i2])
            if chunk:
                out.extend(_w_runs_for_plain_text(chunk))
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
                out.extend(
                    _emit_single_token_replace_fragment(
                        before,
                        after,
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
    return _track_change_elements_for_concat_texts(
        orig_text,
        rev_text,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )


def _concat_paragraph_text_toc_track_layout(
    paragraph: BodyParagraph, config: CompareConfig
) -> str:
    """
    TOC ``w:pStyle`` lines: keep ``\\t`` from runs while still honoring *ignore_case*.

    Global *ignore_whitespace* collapses tabs to a space and breaks TOC layout (SCRUM-112).
    Used only by :func:`_build_toc_matched_line_track_change_elements`.
    """

    cfg = dict(config)
    cfg["ignore_whitespace"] = False
    return "".join(
        _normalize_text(str(run.get("text", "")), cfg) for run in paragraph.get("runs", [])
    )


def _toc_matched_line_needs_revision(
    orig: BodyParagraph, rev: BodyParagraph, config: CompareConfig
) -> bool:
    """Whether a matched TOC line pair needs track markup (tab-preserving concat)."""

    o = _concat_paragraph_text_toc_track_layout(orig, config)
    r = _concat_paragraph_text_toc_track_layout(rev, config)
    return _token_level_text_differs(o, r)


def _build_toc_matched_line_track_change_elements(
    original: BodyParagraph,
    revised: BodyParagraph,
    config: CompareConfig,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """Track Changes for two aligned TOC paragraphs (``TOC*`` style), preserving tab leaders."""

    orig_text = _concat_paragraph_text_toc_track_layout(original, config)
    rev_text = _concat_paragraph_text_toc_track_layout(revised, config)
    return _track_change_elements_for_concat_texts(
        orig_text,
        rev_text,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )


def _tc_direct_paragraph_elements(tc: ET.Element) -> list[ET.Element]:
    return [c for c in tc if _local_name(c.tag) == "p"]


def _tbl_tr_elements(tbl: ET.Element) -> list[ET.Element]:
    return [c for c in tbl if _local_name(c.tag) == "tr"]


def _replace_body_child_element(container: ET.Element, old: ET.Element, new: ET.Element) -> None:
    idx = list(container).index(old)
    container.remove(old)
    container.insert(idx, new)


def _w_ins_wrap_block_content(
    inner: ET.Element,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> ET.Element:
    """Block-level insert wrapper (e.g. a ``w:tbl`` only in the revised document)."""

    ins_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}ins",
        {
            f"{{{WORD_NAMESPACE}}}id": _next_id(id_counter),
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    ins_el.append(inner)
    return ins_el


def _apply_matched_table_track_changes(
    container: ET.Element,
    tbl_el: ET.Element,
    orig_table: dict,
    rev_table: dict,
    config: CompareConfig,
    id_counter: list[int],
    author: str,
    date_iso: str,
    *,
    revised_tbl_el: ET.Element | None,
) -> None:
    """
    Preserve table grid while applying per-cell Track Changes, matching
    :func:`table_diff.diff_table_blocks` cell merge semantics. On row/column
    shape mismatch, replace the original ``w:tbl`` with a copy of the revised
    table when OOXML is available.
    """

    if _table_shape(orig_table) != _table_shape(rev_table):
        if revised_tbl_el is not None:
            _replace_body_child_element(
                container, tbl_el, copy.deepcopy(revised_tbl_el)
            )
        return

    tr_els = _tbl_tr_elements(tbl_el)
    rows_o = orig_table.get("rows", [])
    rows_r = rev_table.get("rows", [])
    for r, row_o in enumerate(rows_o):
        if r >= len(tr_els) or r >= len(rows_r):
            break
        row_r = rows_r[r]
        tcs = [c for c in tr_els[r] if _local_name(c.tag) == "tc"]
        for c, cell_o in enumerate(row_o):
            if c >= len(tcs) or c >= len(row_r):
                break
            cell_r = row_r[c]
            tc_el = tcs[c]
            paras = _tc_direct_paragraph_elements(tc_el)
            if not paras:
                continue
            orig_para = _cell_concat_paragraph(cell_o)
            rev_para = _cell_concat_paragraph(cell_r)
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
            _replace_p_content_preserving_p_pr(paras[0], new_kids)
            for extra in paras[1:]:
                tc_el.remove(extra)


def _apply_track_changes_to_structural_container(
    container: ET.Element,
    original_ir: BodyIR,
    revised_ir: BodyIR,
    config: CompareConfig,
    author: str,
    date_iso: str,
    id_counter: list[int],
    *,
    revised_block_elements: list[ET.Element] | None = None,
) -> None:
    """Mutate ``container`` in place using LCS paragraph alignment (inserts, deletes, in-place edits)."""

    block_els = _structural_block_elements(container)
    ob = original_ir.get("blocks", [])
    rb = revised_ir.get("blocks", [])

    # Use :func:`alignment_for_track_changes_emit`: index ``(i,i)`` when counts and
    # per-index types match (stable golden counts); full LCS when types diverge
    # (paragraph vs table at the same slot, SCRUM-115).
    alignment = alignment_for_track_changes_emit(original_ir, revised_ir, config)
    empty_rev = _empty_body_paragraph()

    for step_i, al in enumerate(alignment):
        oi = al.original_paragraph_index
        rj = al.revised_paragraph_index

        if oi is not None and rj is not None:
            if oi >= len(block_els):
                continue
            oblock, rblock = ob[oi], rb[rj]
            el = block_els[oi]
            if oblock.get("type") == "table" and rblock.get("type") == "table":
                if _local_name(el.tag) != "tbl":
                    continue
                rev_tbl: ET.Element | None = None
                if (
                    revised_block_elements is not None
                    and rj < len(revised_block_elements)
                    and _local_name(revised_block_elements[rj].tag) == "tbl"
                ):
                    rev_tbl = revised_block_elements[rj]
                _apply_matched_table_track_changes(
                    container,
                    el,
                    oblock,
                    rblock,
                    config,
                    id_counter,
                    author,
                    date_iso,
                    revised_tbl_el=rev_tbl,
                )
                continue
            if oblock.get("type") != "paragraph" or rblock.get("type") != "paragraph":
                continue
            if _local_name(el.tag) != "p":
                continue
            orig_para: BodyParagraph = oblock  # type: ignore[assignment]
            rev_para: BodyParagraph = rblock  # type: ignore[assignment]
            if _paragraph_style_is_toc(el):
                if not _toc_matched_line_needs_revision(orig_para, rev_para, config):
                    continue
                new_kids = _build_toc_matched_line_track_change_elements(
                    orig_para,
                    rev_para,
                    config,
                    id_counter=id_counter,
                    author=author,
                    date_iso=date_iso,
                )
            else:
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
            if oblock.get("type") == "table":
                if _local_name(el.tag) == "tbl":
                    container.remove(el)
                continue
            if oblock.get("type") != "paragraph":
                continue
            if _local_name(el.tag) != "p":
                continue
            orig_para = oblock  # type: ignore[assignment]
            if not _paragraph_needs_revision(orig_para, empty_rev, config):
                continue
            if _paragraph_style_is_toc(el):
                _replace_toc_paragraph_with_del_preserving_layout(
                    el,
                    id_counter=id_counter,
                    author=author,
                    date_iso=date_iso,
                )
            else:
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
            idx = _body_insert_index_before_next_orig_block(
                container, alignment, step_i, block_els
            )
            if rblock.get("type") == "table":
                rev_tbl_el: ET.Element | None = None
                if (
                    revised_block_elements is not None
                    and rj < len(revised_block_elements)
                    and _local_name(revised_block_elements[rj].tag) == "tbl"
                ):
                    rev_tbl_el = revised_block_elements[rj]
                if rev_tbl_el is not None:
                    wrapped = _w_ins_wrap_block_content(
                        copy.deepcopy(rev_tbl_el),
                        id_counter=id_counter,
                        author=author,
                        date_iso=date_iso,
                    )
                    container.insert(idx, wrapped)
                continue
            if rblock.get("type") != "paragraph":
                continue
            rev_para = rblock  # type: ignore[assignment]
            if not _paragraph_needs_revision(empty_rev, rev_para, config):
                continue
            rev_el: ET.Element | None = None
            if (
                revised_block_elements is not None
                and rj < len(revised_block_elements)
                and _local_name(revised_block_elements[rj].tag) == "p"
            ):
                rev_el = revised_block_elements[rj]
            if rev_el is not None and _paragraph_style_is_toc(rev_el):
                new_p = _new_w_p_toc_insert_from_revised_source(
                    rev_el,
                    id_counter=id_counter,
                    author=author,
                    date_iso=date_iso,
                )
            else:
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
    revised_block_elements: list[ET.Element] | None = None,
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
        revised_block_elements=revised_block_elements,
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
    revised_block_elements: list[ET.Element] | None = None,
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
        revised_block_elements=revised_block_elements,
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
    with zipfile.ZipFile(rev_path, "r") as zrev:
        rev_doc_blocks = load_structural_block_elements_from_docx_part(zrev, DOCUMENT_PART_PATH)
        rev_hf_blocks: dict[str, list[ET.Element]] = {}
        for _part in discover_header_footer_part_paths_from_namelist(zrev.namelist()):
            rev_hf_blocks[_part] = load_structural_block_elements_from_docx_part(zrev, _part)

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
        revised_block_elements=rev_doc_blocks,
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
            rev_hf_el = rev_hf_blocks.get(part)
            apply_track_changes_to_hdr_ftr_root(
                hf_root,
                o_ir,
                r_ir,
                config,
                author=author,
                date_iso=date_iso,
                id_counter=id_counter,
                revised_block_elements=rev_hf_el,
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
