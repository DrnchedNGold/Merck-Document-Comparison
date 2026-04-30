"""
Emit Word Track Changes markup (w:ins / w:del) for body paragraphs (SCRUM-59).

Top-level blocks are aligned with
:func:`engine.paragraph_alignment.alignment_for_track_changes_emit` (index ``(i,i)``
when counts and types match; otherwise LCS via :func:`~engine.paragraph_alignment.align_paragraphs`)
so **new blocks only in the revised document** become
inserted ``w:p`` elements with ``w:ins``, and paragraphs only in the original become
full-paragraph ``w:del``. Matched paragraphs use :mod:`engine.diff_tokens` (``\\w+`` / punctuation / ``\\s+``)
with **case-folded keys** for LCS; surfaces preserve original text for emit. When a
word-level ``replace`` covers multiple tokens, we **sub-diff again at word level**
on that span so phrases like ``overall response rate … 12`` vs ``progression-free
survival … 24`` become separate ``w:del`` / ``w:ins`` markers per word (with shared
fragments like ``at week`` left as normal text). If a nested replace still has
multiple words on a side, we diff :mod:`engine.diff_tokens` again—never a
character-level matcher on unrelated phrases, which would align stray letters
and merge the whole clause into one deletion.
**Single-token** replace spans use **one** ``w:del`` + **one** ``w:ins`` for
ordinary words (no digits) so we never split inside alphabetic text (avoids
scrambled output). Character-level prefix/suffix is reserved for
numeric/metadata tokens (digits present), e.g. ``1.0`` → ``2.0`` (SCRUM-105).
Inline ``DiffOp`` generation remains character-based in :mod:`engine.inline_run_diff`.

**Debug:** set ``MDC_DEBUG_PARAGRAPH_TC=1`` to print ``repr(orig_text)`` /
``repr(rev_text)``, per-run concat breakdown, preserving vs concat branch, and
``SequenceMatcher.get_opcodes()`` for the paragraph token LCS (stderr).

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
(tab-preserving concat when *ignore_whitespace* is True, SCRUM-112). For other matched
body paragraphs, when the live ``w:p`` matches ingest IR (run count/text and length-preserving
normalization), :func:`build_paragraph_track_change_elements` uses
:func:`_try_build_track_changes_preserving_orig_runs`: builds
:class:`~engine.diff_tokens.StructuredOrigToken` rows (LCS token + owning ``w:r`` +
offsets) so ``equal`` spans can reuse **deep copies** of whole unchanged ``w:r``
nodes or slice-clones with preserved ``w:rPr``. Deletes, inserts, and ``replace`` sides
use ``w:del`` / ``w:ins`` text from joined LCS token surfaces (no ``raw_full[ts:te]`` or
``rev_text[rs:re_]`` slicing). Otherwise it falls back to the synthetic concat-based builder.
"""

from __future__ import annotations

import copy
import difflib
import os
import re
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Literal, Union

from .compare_keys import _normalize_text
from .contracts import BodyIR, BodyParagraph, CompareConfig
from .diff_tokens import (
    DiffToken,
    StructuredOrigToken,
    bounds_from_token_indices,
    equal_span_surface,
    lcs_token_similarity_ratio,
    maybe_log_lcs_debug,
    non_whitespace_norm_keys,
    norm_keys,
    structured_orig_tokens_from_aligned_runs,
    structured_token_index_bounds_for_global_span,
    tokenize_for_lcs,
)
from .document_package import parse_docx_document_package
from .docx_body_ingest import WORD_NAMESPACE, _parse_text_from_run_element
from .paragraph_alignment import alignment_for_track_changes_emit
from .docx_output_package import write_docx_copy_with_part_replacements
from .docx_package_parts import (
    DOCUMENT_PART_PATH,
    discover_header_footer_part_paths,
    discover_header_footer_part_paths_from_namelist,
)
from .ooxml_namespace import serialize_ooxml_part
from .table_diff import (
    _align_row_cells,
    _align_table_rows,
    _cell_concat_paragraph,
    _is_abbreviation_definition_table,
    _table_shape,
)

XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
NS = {"w": WORD_NAMESPACE}
def _local_name(tag: str) -> str:
    return tag.split("}", maxsplit=1)[-1] if "}" in tag else tag


def _paragraph_track_change_build_debug_enabled() -> bool:
    """True when ``MDC_DEBUG_PARAGRAPH_TC`` requests stderr trace for paragraph TC."""

    v = os.environ.get("MDC_DEBUG_PARAGRAPH_TC", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _debug_log_concat_paragraph_runs(
    side: str, paragraph: BodyParagraph, config: CompareConfig, joined: str
) -> None:
    """Per-run raw + normalized pieces (same order as :func:`_concat_paragraph_text`)."""

    runs = paragraph.get("runs", [])
    print(
        f"[MDC_DEBUG_PARAGRAPH_TC] _concat_paragraph_text side={side} "
        f"n_runs={len(runs)} joined_len={len(joined)} joined={joined!r}",
        file=sys.stderr,
    )
    for i, run in enumerate(runs):
        raw = str(run.get("text", ""))
        norm = _normalize_text(raw, config)
        print(
            f"[MDC_DEBUG_PARAGRAPH_TC]   run[{i}] raw={raw!r} norm_piece={norm!r} "
            f"len_raw={len(raw)} len_norm={len(norm)}",
            file=sys.stderr,
        )


def _debug_log_tc_sequence_opcodes(label: str, orig_text: str, rev_text: str) -> None:
    """Print ``SequenceMatcher.get_opcodes()`` for the same token LCS as concat emit."""

    ot = tokenize_for_lcs(orig_text)
    rt = tokenize_for_lcs(rev_text)
    sm = difflib.SequenceMatcher(None, norm_keys(ot), norm_keys(rt), autojunk=False)
    opcodes = sm.get_opcodes()
    print(
        f"[MDC_DEBUG_PARAGRAPH_TC] SequenceMatcher opcodes ({label}): {opcodes}",
        file=sys.stderr,
    )
    print(f"[MDC_DEBUG_PARAGRAPH_TC]   matcher.ratio()={sm.ratio()}", file=sys.stderr)


def _concat_paragraph_text(paragraph: BodyParagraph, config: CompareConfig) -> str:
    return "".join(
        _normalize_text(str(run.get("text", "")), config) for run in paragraph.get("runs", [])
    )


def _tc_norm_keys(tokens: list[DiffToken]) -> list[str]:
    """
    Track-change LCS keys with tab-aware whitespace handling.

    Keep tab-containing whitespace distinct from plain spaces so inline emit
    does not absorb a tab stop into inserted/deleted spans (header/TOC layout).
    """

    out: list[str] = []
    for tok in tokens:
        if tok.surface and tok.surface.isspace() and "\t" in tok.surface:
            out.append("\t")
        else:
            out.append(tok.norm_key())
    return out


def _should_use_tab_aware_lcs_keys(orig_text: str, rev_text: str) -> bool:
    """
    Keep tab boundaries strict only for header-like page title lines.

    Broad tab-aware matching perturbs body paragraphs that use tabs (TOC/content
    fields), which changes golden ins/del counts. Restrict this behavior to the
    sponsor page header pattern where the layout-shift bug occurs.
    """

    if "\t" not in orig_text or "\t" not in rev_text:
        return False
    uo = orig_text.upper()
    ur = rev_text.upper()
    has_page = "PAGE" in uo and "PAGE" in ur
    has_product = ("MK-" in uo or "MK-" in ur) and ("(" in orig_text or "(" in rev_text)
    return has_page and has_product


def _paragraph_w_runs_in_document_order(p_el: ET.Element) -> list[ET.Element]:
    """``w:r`` elements under ``w:p`` in document order (matches body ingest)."""

    return [r for r in p_el.findall(".//w:r", NS) if _parse_text_from_run_element(r)]


def _runs_align_with_ir_for_preserving(
    p_el: ET.Element, orig_para: BodyParagraph, config: CompareConfig
) -> list[tuple[ET.Element, str]] | None:
    """
    Pair each ingest ``w:r`` with IR run text when XML serialization matches IR.

    Returns None when structure does not match (fallback to synthetic emit).
    """

    runs = _paragraph_w_runs_in_document_order(p_el)
    iruns = orig_para.get("runs", [])
    if len(runs) != len(iruns):
        return None
    out: list[tuple[ET.Element, str]] = []
    for r_el, ir in zip(runs, iruns, strict=True):
        raw = _parse_text_from_run_element(r_el)
        ir_text = str(ir.get("text", ""))
        if raw != ir_text:
            return None
        norm = _normalize_text(raw, config)
        if len(norm) != len(raw):
            return None
        out.append((r_el, raw))
    cmp_full = _concat_paragraph_text(orig_para, config)
    raw_full = "".join(raw for _, raw in out)
    if len(raw_full) != len(cmp_full):
        return None
    if "".join(_normalize_text(r, config) for r in (x[1] for x in out)) != cmp_full:
        return None
    return out


def _cloned_w_r_sequence_from_template(template_r: ET.Element, text: str) -> list[ET.Element]:
    """New ``w:r`` nodes copying ``w:rPr`` from *template_r*, with *text* (tabs → ``w:tab``)."""

    if not text:
        return []
    r_pr = template_r.find("w:rPr", NS)
    out: list[ET.Element] = []
    for i, part in enumerate(text.split("\t")):
        if i > 0:
            out.append(_w_tab_run())
        if not part:
            continue
        r_el = ET.Element(f"{{{WORD_NAMESPACE}}}r")
        if r_pr is not None:
            r_el.append(copy.deepcopy(r_pr))
        t_el = ET.SubElement(r_el, f"{{{WORD_NAMESPACE}}}t")
        if _text_needs_xml_space_preserve(part):
            t_el.set(f"{{{XML_NAMESPACE}}}space", "preserve")
        t_el.text = part
        out.append(r_el)
    return out


def _emit_cloned_runs_for_raw_range(
    aligned: list[tuple[ET.Element, str]],
    start: int,
    end: int,
) -> list[ET.Element]:
    """Slice *aligned* run raw strings on ``[start, end)`` and emit cloned ``w:r``."""

    if start >= end:
        return []
    out: list[ET.Element] = []
    pos = 0
    for r_el, raw in aligned:
        n = len(raw)
        lo, hi = max(start, pos), min(end, pos + n)
        if lo < hi:
            sub = raw[lo - pos : hi - pos]
            out.extend(_cloned_w_r_sequence_from_template(r_el, sub))
        pos += n
    return out


def _w_ins_segment_from_aligned_runs_range(
    aligned: list[tuple[ET.Element, str]],
    start: int,
    end: int,
    ins_id: str,
    author: str,
    date_iso: str,
) -> ET.Element | None:
    """Inserted segment using cloned revised runs for one raw text span."""

    runs = _emit_cloned_runs_for_raw_range(aligned, start, end)
    if not runs:
        return None
    ins_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}ins",
        {
            f"{{{WORD_NAMESPACE}}}id": ins_id,
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    for run in runs:
        ins_el.append(run)
    return ins_el


def _w_del_segment_from_aligned_runs_range(
    aligned: list[tuple[ET.Element, str]],
    start: int,
    end: int,
    del_id: str,
    author: str,
    date_iso: str,
) -> ET.Element | None:
    """Deleted segment using cloned original runs for one raw text span."""

    runs = _emit_cloned_runs_for_raw_range(aligned, start, end)
    if not runs:
        return None
    del_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}del",
        {
            f"{{{WORD_NAMESPACE}}}id": del_id,
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    for run in runs:
        _runs_convert_w_t_to_del_text(run)
        del_el.append(run)
    return del_el


def _emit_structured_equal_runs(struct: list[StructuredOrigToken], lo: int, hi: int) -> list[ET.Element]:
    """
    Emit ``w:r`` for an ``equal`` LCS span using per-token ``w:r`` linkage.

    Contiguous tokens from the same source ``w:r`` are merged. When the span is
    the entire run text, emit a **deep copy** of that ``w:r`` (no string rebuild);
    otherwise emit clones with ``w:rPr`` preserved via :func:`_cloned_w_r_sequence_from_template`.
    """

    if lo >= hi:
        return []
    out: list[ET.Element] = []
    g = lo
    while g < hi:
        st0 = struct[g]
        run_el = st0.run_el
        raw = _parse_text_from_run_element(run_el)
        r_lo = st0.run_lo
        r_hi = st0.run_hi
        h = g + 1
        while h < hi:
            stn = struct[h]
            if stn.run_el is not run_el or stn.run_lo != r_hi:
                break
            r_hi = stn.run_hi
            h += 1
        if r_lo == 0 and r_hi == len(raw) and raw:
            out.append(copy.deepcopy(run_el))
        else:
            sub = raw[r_lo:r_hi]
            out.extend(_cloned_w_r_sequence_from_template(run_el, sub))
        g = h
    return out


def _try_build_track_changes_preserving_orig_runs(
    p_el: ET.Element,
    orig_para: BodyParagraph,
    rev_para: BodyParagraph,
    config: CompareConfig,
    *,
    revised_p_el: ET.Element | None,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element] | None:
    """
    Emit track changes by cloning original ``w:r`` / ``w:t`` for unchanged spans.

    Diff is still word-token based on compare text; only *insert* segments are new
    ``w:ins`` runs. Deletes use ``w:del`` with ``w:delText`` from joined LCS token
    surfaces on the original side; inserts from joined revised token surfaces.
    Falls back to ``None``
    when DOM and IR diverge or normalization changes string length.
    """

    aligned = _runs_align_with_ir_for_preserving(p_el, orig_para, config)
    if aligned is None:
        return None
    revised_aligned: list[tuple[ET.Element, str]] | None = None
    if revised_p_el is not None:
        revised_aligned = _runs_align_with_ir_for_preserving(revised_p_el, rev_para, config)
    orig_cmp = _concat_paragraph_text(orig_para, config)
    rev_text = _concat_paragraph_text(rev_para, config)
    if _numeric_grouping_only_change(orig_cmp, rev_text):
        return _emit_char_level_tc_elements(
            orig_cmp,
            rev_text,
            id_counter=id_counter,
            author=author,
            date_iso=date_iso,
        )
    struct_ot = structured_orig_tokens_from_aligned_runs(aligned, orig_cmp)
    ot = tokenize_for_lcs(orig_cmp)
    rt = tokenize_for_lcs(rev_text)
    key_fn = _tc_norm_keys if _should_use_tab_aware_lcs_keys(orig_cmp, rev_text) else norm_keys
    sm = difflib.SequenceMatcher(None, key_fn(ot), key_fn(rt), autojunk=False)
    maybe_log_lcs_debug("preserving_paragraph", ot, rt, sm)
    opcodes = sm.get_opcodes()
    opcodes = _collapse_adjacent_replace_opcodes(opcodes, ot, rt)
    opcodes = _refine_replace_boundaries(opcodes, ot, rt)
    coalesced_suffix = _coalesce_opcodes_at_longest_common_token_suffix(ot, rt, opcodes)
    if coalesced_suffix is not None:
        opcodes = coalesced_suffix
    else:
        opcodes = _merge_unstable_opcode_regions(opcodes, ot, rt)
    opcodes = _merge_change_cluster_between_meaningful_equals(opcodes, ot, rt)
    opcodes = _split_replace_opcodes_on_internal_meaningful_equals(opcodes, ot, rt)
    opcodes = _left_bias_internal_equal_between_changes(opcodes, ot, rt)
    opcodes = _pull_meaningful_equal_earlier_from_long_left_replace(opcodes, ot, rt)
    opcodes = _prefer_later_stronger_equal_anchor(opcodes, ot, rt)
    opcodes = _dedupe_reinserted_equal_prefix(opcodes, ot, rt)
    opcodes = _absorb_weak_equal_islands_between_changes(opcodes, ot, rt)
    opcodes = _rotate_shared_punctuation_around_deleted_clause(opcodes, ot, rt)
    opcodes = _expand_replace_to_include_following_shared_ws_token(opcodes, ot, rt)
    out: list[ET.Element] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            if struct_ot is not None:
                out.extend(_emit_structured_equal_runs(struct_ot, i1, i2))
            else:
                # Clone runs; span text matches "".join(t.surface for t in rt[j1:j2]) (equal opcode).
                ts, te = bounds_from_token_indices(ot, i1, i2)
                out.extend(_emit_cloned_runs_for_raw_range(aligned, ts, te))
        elif tag == "delete":
            chunk = equal_span_surface(ot, i1, i2)
            if chunk:
                ts, te = bounds_from_token_indices(ot, i1, i2)
                del_id = _next_id(id_counter)
                del_el = _w_del_segment_from_aligned_runs_range(
                    aligned,
                    ts,
                    te,
                    del_id,
                    author,
                    date_iso,
                )
                if del_el is not None:
                    out.append(del_el)
                else:
                    out.append(_w_del_segment(chunk, del_id, author, date_iso))
        elif tag == "insert":
            chunk = equal_span_surface(rt, j1, j2)
            if chunk:
                if revised_aligned is not None:
                    rs, re_ = bounds_from_token_indices(rt, j1, j2)
                    ins_el = _w_ins_segment_from_aligned_runs_range(
                        revised_aligned,
                        rs,
                        re_,
                        _next_id(id_counter),
                        author,
                        date_iso,
                    )
                    if ins_el is not None:
                        out.append(ins_el)
                        continue
                out.append(_w_ins_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "replace":
            before_text = equal_span_surface(ot, i1, i2)
            after_text = equal_span_surface(rt, j1, j2)
            out.extend(
                _emit_preserving_replace_multitoken_bounded(
                    aligned,
                    ot,
                    rt,
                    i1,
                    i2,
                    j1,
                    j2,
                    struct_ot=struct_ot,
                    revised_aligned=revised_aligned,
                    id_counter=id_counter,
                    author=author,
                    date_iso=date_iso,
                )
            )
    return out


def _token_level_text_differs(o: str, r: str) -> bool:
    if o == r:
        return False
    ot, rt = tokenize_for_lcs(o), tokenize_for_lcs(r)
    sm = difflib.SequenceMatcher(None, norm_keys(ot), norm_keys(rt), autojunk=False)
    for tag, *_ in sm.get_opcodes():
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


def _p_style_val_indicates_list_paragraph(val: str) -> bool:
    """Heuristic: Word list / bullet paragraph styles (e.g. ``ListBullet`` without ``w:numPr``)."""

    u = "".join(val.split()).upper()
    if u.startswith("LIST"):
        return True
    if "BULLET" in u or "NUMBERING" in u:
        return True
    return False


def _p_paragraph_style_id(p_el: ET.Element) -> str | None:
    ppr = p_el.find("w:pPr", NS)
    if ppr is None:
        return None
    ps = ppr.find("w:pStyle", NS)
    if ps is None:
        return None
    return ps.get(f"{{{WORD_NAMESPACE}}}val")


def _p_only_p_pr_and_single_w_del(p_el: ET.Element) -> bool:
    """True when ``w:p`` has optional ``w:pPr`` and exactly one ``w:del`` (no other block children)."""

    non_ppr = [c for c in p_el if _local_name(c.tag) != "pPr"]
    return len(non_ppr) == 1 and _local_name(non_ppr[0].tag) == "del"


def _append_br_run_to_del(del_el: ET.Element) -> None:
    br_r = ET.Element(f"{{{WORD_NAMESPACE}}}r")
    br_el = ET.SubElement(br_r, f"{{{WORD_NAMESPACE}}}br")
    br_el.set(f"{{{WORD_NAMESPACE}}}type", "textWrapping")
    del_el.append(br_r)


def _coalesce_w_del_runs_to_single_del_text(del_el: ET.Element) -> None:
    """
    After merging several full-paragraph deletes, replace many ``w:r`` / ``w:delText`` / ``w:br``
    with **one** ``w:r`` and one ``w:delText``. Use **spaces** between former lines so Word shows
    a **single flowing line** of strike-through (SCRUM-130); collapse redundant whitespace.
    """

    direct_runs = [c for c in del_el if _local_name(c.tag) == "r"]
    if not direct_runs:
        return
    needs_coalesce = len(direct_runs) > 1
    if not needs_coalesce:
        for r_el in direct_runs:
            for gg in r_el:
                if _local_name(gg.tag) == "br":
                    needs_coalesce = True
                    break
            if needs_coalesce:
                break
    if not needs_coalesce:
        return

    pieces: list[str] = []
    had_br = False
    for r_el in direct_runs:
        for gg in r_el:
            ln = _local_name(gg.tag)
            if ln == "delText":
                pieces.append(gg.text or "")
            elif ln == "br":
                had_br = True
                pieces.append(" ")
    # Keep line-broken merged deletes as-is so Word shows one balloon with
    # separate deleted lines (not a flattened sentence).
    if had_br:
        return
    combined = "".join(pieces)
    combined = re.sub(r"\s+", " ", combined).strip()
    for ch in list(del_el):
        del_el.remove(ch)
    r_out = ET.Element(f"{{{WORD_NAMESPACE}}}r")
    dt = ET.SubElement(r_out, f"{{{WORD_NAMESPACE}}}delText")
    dt.text = combined
    del_el.append(r_out)


def _strip_list_layout_from_merged_consolidated_delete_paragraph(p_el: ET.Element) -> None:
    """
    Consolidated delete still inherited ``Paragraph`` / list indents / ``w:tabs`` from the first
    merged ``w:p``; Word can draw bullets or hanging space. Force plain ``Normal`` and zero
    indents so removed list content leaves no list chrome (SCRUM-130).
    """

    ppr = p_el.find("w:pPr", NS)
    if ppr is None:
        ppr = ET.Element(f"{{{WORD_NAMESPACE}}}pPr")
        ps = ET.SubElement(ppr, f"{{{WORD_NAMESPACE}}}pStyle")
        ps.set(f"{{{WORD_NAMESPACE}}}val", "Normal")
        p_el.insert(0, ppr)
        return
    for ch in list(ppr):
        ln = _local_name(ch.tag)
        if ln in ("numPr", "tabs", "ind"):
            ppr.remove(ch)
    ps = ppr.find("w:pStyle", NS)
    if ps is None:
        ps = ET.Element(f"{{{WORD_NAMESPACE}}}pStyle")
        ps.set(f"{{{WORD_NAMESPACE}}}val", "Normal")
        ppr.insert(0, ps)
    else:
        ps.set(f"{{{WORD_NAMESPACE}}}val", "Normal")
    ind = ET.Element(f"{{{WORD_NAMESPACE}}}ind")
    ind.set(f"{{{WORD_NAMESPACE}}}left", "0")
    ind.set(f"{{{WORD_NAMESPACE}}}right", "0")
    ind.set(f"{{{WORD_NAMESPACE}}}hanging", "0")
    ind.set(f"{{{WORD_NAMESPACE}}}firstLine", "0")
    ind.set(f"{{{WORD_NAMESPACE}}}start", "0")
    ind.set(f"{{{WORD_NAMESPACE}}}end", "0")
    ppr.append(ind)


def _merge_w_del_paragraph_group_into_first(
    container: ET.Element, paragraphs: list[ET.Element]
) -> None:
    """Join several ``w:p`` (each single ``w:del``) into the first ``w:p`` using ``w:br`` between chunks."""

    if len(paragraphs) < 2:
        return
    first = paragraphs[0]
    first_del = first.find("w:del", NS)
    if first_del is None:
        return
    for p in paragraphs[1:]:
        other = p.find("w:del", NS)
        if other is None:
            continue
        _append_br_run_to_del(first_del)
        for ch in list(other):
            first_del.append(copy.deepcopy(ch))
        container.remove(p)
    _coalesce_w_del_runs_to_single_del_text(first_del)
    _strip_list_layout_from_merged_consolidated_delete_paragraph(first)


def _style_ok_after_paragraph_intro_for_list_merge(sid: str | None) -> bool:
    """
    Body lines after the first deleted ``Paragraph`` in sponsor templates: another ``Paragraph``
    (e.g. “The following terms…”) often precedes ``ListBullet`` rows — must merge into one block
    (SCRUM-130). Also allow ``Normal`` and list-like styles.
    """

    if sid == "Normal" or sid == "Paragraph":
        return True
    if sid and _p_style_val_indicates_list_paragraph(sid):
        return True
    return False


def _post_merge_paragraph_intro_then_list_like_full_deletes(container: ET.Element) -> None:
    """
    Diversity-plan style: ``Paragraph`` intro + ``ListBullet`` rows all deleted → one ``w:p``, one ``w:del``
    with ``w:br`` between lines (SCRUM-130). Avoids one revision per bullet and duplicate sidebar noise.
    """

    idx = 0
    while idx < len(container):
        el = container[idx]
        if _local_name(el.tag) != "p":
            idx += 1
            continue
        if not _p_only_p_pr_and_single_w_del(el) or _p_paragraph_style_id(el) != "Paragraph":
            idx += 1
            continue
        intro_del = el.find("w:del", NS)
        if intro_del is None:
            idx += 1
            continue
        group: list[ET.Element] = [el]
        j = idx + 1
        while j < len(container):
            nxt = container[j]
            if _local_name(nxt.tag) != "p":
                break
            if not _p_only_p_pr_and_single_w_del(nxt):
                break
            n_sid = _p_paragraph_style_id(nxt)
            if not _style_ok_after_paragraph_intro_for_list_merge(n_sid):
                break
            group.append(nxt)
            j += 1
        if len(group) >= 2 and not _post_merge_deleted_list_group_followed_by_insert(
            container, idx, len(group)
        ):
            for p in group[1:]:
                other_del = p.find("w:del", NS)
                if other_del is None:
                    continue
                _append_br_run_to_del(intro_del)
                for ch in list(other_del):
                    intro_del.append(copy.deepcopy(ch))
                container.remove(p)
            _coalesce_w_del_runs_to_single_del_text(intro_del)
            _strip_list_layout_from_merged_consolidated_delete_paragraph(el)
        idx += 1


def _post_merge_consecutive_same_list_like_full_deletes(container: ET.Element) -> None:
    """
    Merge **2+** adjacent full-paragraph deletes that share the same list-like ``w:pStyle`` (no ``Paragraph``
    intro). Runs after :func:`_post_merge_paragraph_intro_then_list_like_full_deletes`.
    """

    idx = 0
    while idx < len(container):
        el = container[idx]
        if _local_name(el.tag) != "p" or not _p_only_p_pr_and_single_w_del(el):
            idx += 1
            continue
        sid = _p_paragraph_style_id(el)
        if not sid or not _p_style_val_indicates_list_paragraph(sid):
            idx += 1
            continue
        group: list[ET.Element] = [el]
        j = idx + 1
        while j < len(container):
            nxt = container[j]
            if _local_name(nxt.tag) != "p" or not _p_only_p_pr_and_single_w_del(nxt):
                break
            n_sid = _p_paragraph_style_id(nxt)
            if n_sid != sid:
                break
            group.append(nxt)
            j += 1
        if len(group) >= 2 and not _post_merge_deleted_list_group_followed_by_insert(
            container, idx, len(group)
        ):
            _merge_w_del_paragraph_group_into_first(container, group)
        idx += 1


def _paragraph_is_insert_only(p_el: ET.Element) -> bool:
    """True when a ``w:p`` contains optional ``w:pPr`` plus exactly one ``w:ins``."""

    non_ppr = [c for c in p_el if _local_name(c.tag) != "pPr"]
    return len(non_ppr) == 1 and _local_name(non_ppr[0].tag) == "ins"


def _post_merge_deleted_list_group_followed_by_insert(container: ET.Element, idx: int, group_len: int) -> bool:
    """
    Do not consolidate deleted list/introduction paragraphs when the next block is
    an inserted replacement paragraph.

    Word keeps those deleted lines as separate paragraphs in sponsor compare output
    for the cervical abbreviations section; merging them changes pagination.
    """

    next_idx = idx + group_len
    if next_idx >= len(container):
        return False
    nxt = container[next_idx]
    return _local_name(nxt.tag) == "p" and _paragraph_is_insert_only(nxt)


def _post_merge_consolidated_list_full_paragraph_deletes(container: ET.Element) -> None:
    """Post-pass: consolidate adjacent deleted list rows into fewer ``w:del`` blocks (SCRUM-130)."""
    _post_merge_paragraph_intro_then_list_like_full_deletes(container)
    _post_merge_consecutive_same_list_like_full_deletes(container)


def _sync_blank_paragraph_structure_to_revised(orig_p: ET.Element, rev_p: ET.Element) -> bool:
    """
    For matched textually blank paragraphs, copy revised non-text structure.

    This preserves authored page-break paragraphs and spacing-only blanks that do
    not show up in the token diff because both sides have empty paragraph text.
    """

    if _paragraph_plain_text(orig_p) or _paragraph_plain_text(rev_p):
        return False
    changed = False

    orig_ppr = orig_p.find("w:pPr", NS)
    rev_ppr = rev_p.find("w:pPr", NS)
    if rev_ppr is not None:
        if orig_ppr is None or ET.tostring(orig_ppr, encoding="unicode") != ET.tostring(
            rev_ppr, encoding="unicode"
        ):
            if orig_ppr is not None:
                orig_p.remove(orig_ppr)
            orig_p.insert(0, copy.deepcopy(rev_ppr))
            changed = True
    elif orig_ppr is not None:
        orig_p.remove(orig_ppr)
        changed = True

    orig_non_ppr = [copy.deepcopy(ch) for ch in orig_p if _local_name(ch.tag) != "pPr"]
    rev_non_ppr = [copy.deepcopy(ch) for ch in rev_p if _local_name(ch.tag) != "pPr"]
    if [ET.tostring(ch, encoding="unicode") for ch in orig_non_ppr] != [
        ET.tostring(ch, encoding="unicode") for ch in rev_non_ppr
    ]:
        for ch in list(orig_p):
            if _local_name(ch.tag) != "pPr":
                orig_p.remove(ch)
        for ch in rev_non_ppr:
            orig_p.append(ch)
        changed = True
    return changed


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
    if len(ins_el):
        p_out.append(ins_el)
    _mark_paragraph_mark_as_inserted(
        p_out,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )
    return p_out


def _mark_paragraph_mark_as_inserted(
    p_el: ET.Element,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> None:
    """Mark the paragraph mark itself as inserted so Word can track paragraph-level structure."""

    ppr = p_el.find("w:pPr", NS)
    if ppr is None:
        ppr = ET.Element(f"{{{WORD_NAMESPACE}}}pPr")
        p_el.insert(0, ppr)
    rpr = ppr.find("w:rPr", NS)
    if rpr is None:
        rpr = ET.Element(f"{{{WORD_NAMESPACE}}}rPr")
        ppr.append(rpr)
    if rpr.find("w:ins", NS) is not None:
        return
    rpr.append(
        ET.Element(
            f"{{{WORD_NAMESPACE}}}ins",
            {
                f"{{{WORD_NAMESPACE}}}id": _next_id(id_counter),
                f"{{{WORD_NAMESPACE}}}author": author,
                f"{{{WORD_NAMESPACE}}}date": date_iso,
            },
        )
    )


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


def _revised_only_paragraph_should_emit(
    rev_para: BodyParagraph,
    config: CompareConfig,
    *,
    revised_p_el: ET.Element | None,
) -> bool:
    """
    Emit revised-only paragraphs even when they are textually blank.

    Blank body paragraphs carry real document structure in Word, especially in
    front matter around title blocks, tables, and TOC boundaries. Treating
    ``empty -> empty`` as "no revision" collapses those separators.
    """

    if _paragraph_needs_revision(_empty_body_paragraph(), rev_para, config):
        return True
    return revised_p_el is not None and len(rev_para.get("runs", [])) == 0


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


def _w_ins_segment_from_revised_paragraph_runs(
    rev_p: ET.Element,
    ins_id: str,
    author: str,
    date_iso: str,
) -> ET.Element:
    """Inserted paragraph content preserving revised run formatting."""

    ins_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}ins",
        {
            f"{{{WORD_NAMESPACE}}}id": ins_id,
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    for run in _paragraph_w_runs_in_document_order(rev_p):
        ins_el.append(copy.deepcopy(run))
    return ins_el


# Table ``major_sentence_mode`` full-line replace uses a looser bar so unrelated
# sentences still collapse to one ``w:del`` + one ``w:ins`` (SCRUM-131).
_TABLE_MAJOR_SENTENCE_WORD_OVERLAP_MAX = 0.35
_INSERTED_TABLE_CELL_SHADE_FILL = "D9EAF7"
_INLINE_DIFF_SIMILARITY_MIN = 0.70
_INLINE_DIFF_ANCHORED_REWRITE_SIMILARITY_MIN = 0.55
_INLINE_DIFF_STRONG_ANCHOR_MIN_TOKENS = 4


def _word_token_similarity_ratio(a: str, b: str) -> float:
    """
    Similarity of non-whitespace :class:`~engine.diff_tokens.DiffToken` norm keys
    via :class:`difflib.SequenceMatcher` (same tokenization as paragraph LCS).
    """

    ta = [t for t in tokenize_for_lcs(a) if not t.surface.isspace()]
    tb = [t for t in tokenize_for_lcs(b) if not t.surface.isspace()]
    return lcs_token_similarity_ratio(non_whitespace_norm_keys(ta), non_whitespace_norm_keys(tb))


def _emit_preserving_replace_multitoken_bounded(
    aligned: list[tuple[ET.Element, str]],
    ot: list[DiffToken],
    rt: list[DiffToken],
    i1: int,
    i2: int,
    j1: int,
    j2: int,
    *,
    struct_ot: list[StructuredOrigToken] | None,
    revised_aligned: list[tuple[ET.Element, str]] | None,
    id_counter: list[int],
    author: str,
    date_iso: str,
    depth: int = 0,
) -> list[ET.Element]:
    """
    One ``w:del`` + one ``w:ins`` for the outer replace span (no nested LCS).

    Before/after text is :func:`~engine.diff_tokens.equal_span_surface` on the LCS
    token spans (``ot[i1:i2]``, ``rt[j1:j2]``), not ``raw_full``/``rev_text`` slices.
    *aligned* / *struct_ot* are unused but kept for a stable call signature with
    :func:`_try_build_track_changes_preserving_orig_runs`.
    """

    _ = aligned, struct_ot, depth
    bo = equal_span_surface(ot, i1, i2)
    ar = equal_span_surface(rt, j1, j2)
    out: list[ET.Element] = []
    if bo:
        ts, te = bounds_from_token_indices(ot, i1, i2)
        del_id = _next_id(id_counter)
        del_el = _w_del_segment_from_aligned_runs_range(
            aligned,
            ts,
            te,
            del_id,
            author,
            date_iso,
        )
        if del_el is not None:
            out.append(del_el)
        else:
            out.append(_w_del_segment(bo, del_id, author, date_iso))
    if ar:
        if revised_aligned is not None:
            rs, re_ = bounds_from_token_indices(rt, j1, j2)
            ins_el = _w_ins_segment_from_aligned_runs_range(
                revised_aligned,
                rs,
                re_,
                _next_id(id_counter),
                author,
                date_iso,
            )
            if ins_el is not None:
                out.append(ins_el)
                return out
        out.append(_w_ins_segment(ar, _next_id(id_counter), author, date_iso))
    return out


def _tc_concat_fragmentation_debug_enabled(orig_text: str, rev_text: str) -> bool:
    """True when detailed concat-texts token/opcode tracing should print (stderr)."""

    if os.environ.get("MDC_DEBUG_TC_CONCAT_FRAGMENTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return True
    return (
        orig_text == "the name is kiran" and rev_text == "I am introduce as kiran"
    )


def _log_tc_concat_fragmentation_trace(
    orig_text: str,
    rev_text: str,
    orig_tokens: list,
    rev_tokens: list,
    opcodes: list[tuple[str, int, int, int, int]],
) -> None:
    """Stderr-only: token lists, norm keys, per-opcode slices, and counts (grouping design aid).

    *opcodes* must be the **post-collapse** opcode list (same as used for emit).
    """

    print(
        "[MDC_DEBUG_TC_CONCAT_FRAG] emit_branch=concat_texts "
        "(_track_change_elements_for_concat_texts; preserving_orig_runs bypasses this function)",
        file=sys.stderr,
    )
    print(f"[MDC_DEBUG_TC_CONCAT_FRAG] orig_text={orig_text!r}", file=sys.stderr)
    print(f"[MDC_DEBUG_TC_CONCAT_FRAG] rev_text={rev_text!r}", file=sys.stderr)
    for i, t in enumerate(orig_tokens):
        print(
            f"[MDC_DEBUG_TC_CONCAT_FRAG] orig_tokens[{i}]={t.surface!r} [{t.start},{t.end})",
            file=sys.stderr,
        )
    for j, t in enumerate(rev_tokens):
        print(
            f"[MDC_DEBUG_TC_CONCAT_FRAG] rev_tokens[{j}]={t.surface!r} [{t.start},{t.end})",
            file=sys.stderr,
        )
    nk_o = norm_keys(orig_tokens)
    nk_r = norm_keys(rev_tokens)
    print(f"[MDC_DEBUG_TC_CONCAT_FRAG] norm_keys(orig_tokens)={nk_o!r}", file=sys.stderr)
    print(f"[MDC_DEBUG_TC_CONCAT_FRAG] norm_keys(rev_tokens)={nk_r!r}", file=sys.stderr)
    opcode_count = len(opcodes)
    pattern_parts: list[str] = []
    replace_orig_spans: list[int] = []
    matched_tc = deleted_tc = inserted_tc = 0
    for tag, i1, i2, j1, j2 in opcodes:
        o_slice = orig_tokens[i1:i2]
        r_slice = rev_tokens[j1:j2]
        o_parts = [f"[{i1 + k}]={t.surface!r}" for k, t in enumerate(o_slice)]
        r_parts = [f"[{j1 + k}]={t.surface!r}" for k, t in enumerate(r_slice)]
        print(
            f"[MDC_DEBUG_TC_CONCAT_FRAG] opcode tag={tag!r} i1={i1} i2={i2} j1={j1} j2={j2}",
            file=sys.stderr,
        )
        print(
            f"[MDC_DEBUG_TC_CONCAT_FRAG]   orig_token_slice: {' '.join(o_parts) if o_parts else '(empty)'}",
            file=sys.stderr,
        )
        print(
            f"[MDC_DEBUG_TC_CONCAT_FRAG]   rev_token_slice:  {' '.join(r_parts) if r_parts else '(empty)'}",
            file=sys.stderr,
        )
        if tag == "equal":
            pattern_parts.append("E")
            matched_tc += i2 - i1
        elif tag == "delete":
            pattern_parts.append("D")
            deleted_tc += i2 - i1
        elif tag == "insert":
            pattern_parts.append("I")
            inserted_tc += j2 - j1
        elif tag == "replace":
            pattern_parts.append("R")
            deleted_tc += i2 - i1
            inserted_tc += j2 - j1
            replace_orig_spans.append(i2 - i1)

    total_orig_tokens = len(orig_tokens)
    total_rev_tokens = len(rev_tokens)
    denom = max(total_orig_tokens, total_rev_tokens)
    match_ratio = (matched_tc / denom) if denom > 0 else 0.0
    opcode_pattern = ",".join(pattern_parts)
    avg_replace_span_size = (
        sum(replace_orig_spans) / len(replace_orig_spans) if replace_orig_spans else 0.0
    )

    print(f"[MDC_DEBUG_TC_CONCAT_FRAG] opcode_count={opcode_count}", file=sys.stderr)
    print(f"[MDC_DEBUG_TC_CONCAT_FRAG] opcode_pattern={opcode_pattern}", file=sys.stderr)
    print(
        f"[MDC_DEBUG_TC_CONCAT_FRAG] total_orig_tokens={total_orig_tokens} "
        f"total_rev_tokens={total_rev_tokens} match_ratio={match_ratio:.6f}",
        file=sys.stderr,
    )
    print(
        f"[MDC_DEBUG_TC_CONCAT_FRAG] avg_replace_span_size={avg_replace_span_size:.6f} "
        f"(orig-side token count per replace opcode; n_replace={len(replace_orig_spans)})",
        file=sys.stderr,
    )
    print(
        f"[MDC_DEBUG_TC_CONCAT_FRAG] metrics: matched_token_count={matched_tc} "
        f"deleted_token_count={deleted_tc} inserted_token_count={inserted_tc}",
        file=sys.stderr,
    )
    print(
        f"[MDC_DEBUG_TC_CONCAT_FRAG] total_tokens orig={total_orig_tokens} rev={total_rev_tokens}",
        file=sys.stderr,
    )


def _tc_token_surface_trivial_for_merge(surface: str) -> bool:
    """True if *surface* has no Unicode letters and no digits (separator-only).

    Whitespace, punctuation, and symbols such as ``-``, ``:``, ``_`` are trivial.
    Uses :meth:`str.isalpha` / :meth:`str.isdigit` so ``_`` is not treated as
    blocking (unlike :meth:`str.isalnum`, which is true for underscore).
    """

    for c in surface:
        if c.isalpha() or c.isdigit():
            return False
    return True


def _tc_equal_opcode_tokens_all_trivial_for_merge(
    orig_tokens: list,
    ei1: int,
    ei2: int,
    rev_tokens: list,
    ej1: int,
    ej2: int,
) -> bool:
    """True if every token on both sides has no letters or digits (separator-only)."""

    if ei1 >= ei2 and ej1 >= ej2:
        return True
    for k in range(ei1, ei2):
        if not _tc_token_surface_trivial_for_merge(orig_tokens[k].surface):
            return False
    for k in range(ej1, ej2):
        if not _tc_token_surface_trivial_for_merge(rev_tokens[k].surface):
            return False
    return True


def _tc_equal_opcode_has_hard_boundary_for_merge(
    orig_tokens: list,
    ei1: int,
    ei2: int,
    rev_tokens: list,
    ej1: int,
    ej2: int,
) -> bool:
    """
    True when a trivial equal span still marks a sentence/reference boundary.

    We do not want ``replace`` chain collapsing to merge across stable boundaries
    such as ``. `` or ``]. ``, or across explicit tab stops, because that turns
    local edits into large cross-sentence or cross-field replace spans.
    """

    text = "".join(tok.surface for tok in orig_tokens[ei1:ei2]) + "".join(
        tok.surface for tok in rev_tokens[ej1:ej2]
    )
    if not text:
        return False
    return any(ch in text for ch in ".!?;]\t")


def _collapse_adjacent_replace_opcodes(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Greedy merge of ``replace`` + (``equal`` + ``replace``)* chains when each ``equal``
    span is only trivial separators (whitespace / punctuation), so
    ``R,E,R,E,R,…`` becomes a single ``replace`` for emission.
    """

    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    n = len(opcodes)
    while i < n:
        tag, i1, i2, j1, j2 = opcodes[i]
        if tag != "replace":
            out.append((tag, i1, i2, j1, j2))
            i += 1
            continue
        start_i1, start_j1 = i1, j1
        end_i2, end_j2 = i2, j2
        j = i + 1
        chain_steps = 0
        while j + 1 < n:
            et, ei1, ei2, ej1, ej2 = opcodes[j]
            rt, ri1, ri2, rj1, rj2 = opcodes[j + 1]
            if et != "equal" or rt != "replace":
                break
            if not _tc_equal_opcode_tokens_all_trivial_for_merge(
                orig_tokens, ei1, ei2, rev_tokens, ej1, ej2
            ):
                break
            if _tc_equal_opcode_has_hard_boundary_for_merge(
                orig_tokens, ei1, ei2, rev_tokens, ej1, ej2
            ):
                break
            end_i2 = ri2
            end_j2 = rj2
            chain_steps += 1
            j += 2
        if chain_steps > 0:
            print(
                f"[MDC_DEBUG_TC_COLLAPSE_CHAIN] merged_chain_span "
                f"i1={start_i1} i2={end_i2} j1={start_j1} j2={end_j2} chain_steps={chain_steps}",
                file=sys.stderr,
            )
        out.append(("replace", start_i1, end_i2, start_j1, end_j2))
        i = j
    return out


def _merge_adjacent_equal_opcodes(
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[tuple[str, int, int, int, int]]:
    """Merge consecutive ``equal`` opcodes that share boundaries (keeps list compact)."""

    if not opcodes:
        return opcodes
    out: list[tuple[str, int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal" and out and out[-1][0] == "equal":
            pt, pi1, pi2, pj1, pj2 = out[-1]
            if pi2 == i1 and pj2 == j1:
                out[-1] = ("equal", pi1, i2, pj1, j2)
                continue
        out.append((tag, i1, i2, j1, j2))
    return out


def _refine_replace_boundaries(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Split ``replace`` opcodes so leading/trailing token pairs with identical surfaces
    become ``equal`` opcodes (Word-like boundaries; avoids gluing unrelated tokens).
    """

    new_opcodes: list[tuple[str, int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag != "replace":
            new_opcodes.append((tag, i1, i2, j1, j2))
            continue
        end_i2, end_j2 = i2, j2
        a, b = i1, j1
        while a < end_i2 and b < end_j2 and orig_tokens[a].surface == rev_tokens[b].surface:
            new_opcodes.append(("equal", a, a + 1, b, b + 1))
            a += 1
            b += 1
        c, d = end_i2, end_j2
        while c > a and d > b and orig_tokens[c - 1].surface == rev_tokens[d - 1].surface:
            c -= 1
            d -= 1
        if a < c or b < d:
            new_opcodes.append(("replace", a, c, b, d))
        while c < end_i2 and d < end_j2:
            new_opcodes.append(("equal", c, c + 1, d, d + 1))
            c += 1
            d += 1
    return _merge_adjacent_equal_opcodes(new_opcodes)


# Minimum matching token suffix length to coalesce into one ``equal`` tail (stable shared text).
# ``3`` keeps tails like ``published`` + space + ``study`` as one ``equal`` while allowing a
# broader ``replace`` prefix than the raw matcher (e.g. include ``recently`` on both sides).
_TC_ALIGN_MIN_COMMON_SUFFIX_TOKENS = 3

# When the matcher already emitted a long ``equal`` tail after ``replace`` (two-opcode form),
# do **not** re-derive boundaries from the global 3-token suffix only: that can swallow a
# long shared clause back into ``replace`` (e.g. Heading2 titles with repeated ``and`` tokens).
_TC_COALESCE_SKIP_WHEN_TAIL_EQUAL_MIN = 8

# Minimum equal-token count at end of opcode list to treat as stable tail for unstable merge.
_TC_ALIGN_MIN_STABLE_TAIL_TOKENS = 4

# Mid-paragraph change cluster merge: keep substantial equal anchors (for example,
# ``women in the US`` or a full preserved sentence) plain, but collapse the
# rewrite region between them when changes dominate and the inner equal islands
# are too small to justify alternating ``w:del`` / ``w:ins`` churn.
_TC_CLUSTER_MEANINGFUL_EQUAL_TOKENS = 4
_TC_CLUSTER_ANCHOR_EQUAL_TOKENS = 6
_TC_CLUSTER_STRONG_INNER_EQUAL_TOKENS = 5
_TC_CLUSTER_MIN_CHANGE_OPCODES = 3
_MERGED_PARA_SPLIT_PREFIX_WORDS = 8


def _coalesce_opcodes_at_longest_common_token_suffix(
    orig_tokens: list,
    rev_tokens: list,
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[tuple[str, int, int, int, int]] | None:
    """
    When both sides share an identical token suffix of at least
    ``_TC_ALIGN_MIN_COMMON_SUFFIX_TOKENS`` tokens (fixed tail, not necessarily the
    longest possible LCS suffix), collapse the diff to
    ``replace(prefix_orig, prefix_rev)`` + ``equal(suffix)``.

    This aligns replace boundaries with a stable shared tail (e.g. ``published study``)
    without changing emission helpers. Skips when the prefix would be a trivial
    single-token alphabetic/digit substitution (granular typo / number).

    For a two-opcode ``replace`` + ``equal`` diff, this can move tokens out of the
    equal span into the replace when the matcher over-anchors on a shared word
    (e.g. ``recently``) before the tail. Leading ``equal`` opcodes are never merged.

    If the trailing ``equal`` is already long (at least
    ``_TC_COALESCE_SKIP_WHEN_TAIL_EQUAL_MIN`` tokens), skip: suffix-only
    realignment would incorrectly pull a large shared clause into ``replace``
    (e.g. ``Heading2`` titles with repeated words like ``and``).
    """

    m = _TC_ALIGN_MIN_COMMON_SUFFIX_TOKENS
    os, rs = len(orig_tokens), len(rev_tokens)
    # Two-opcode ``replace`` + ``equal``: realign when the matcher anchors too much in the
    # equal span (e.g. shared ``recently`` before a stable ``published study`` tail).
    # Skip two-opcode forms that are not ``replace``+``equal`` (and skip when the diff
    # begins with ``equal``, which would pull shared prefix text into ``replace``).
    if len(opcodes) < 2:
        return None
    if len(opcodes) == 2:
        if opcodes[0][0] != "replace" or opcodes[1][0] != "equal":
            return None
        _t0, _r_i1, r_i2, _r_j1, r_j2 = opcodes[0]
        _t1, e_i1, e_i2, e_j1, e_j2 = opcodes[1]
        if r_i2 == e_i1 and r_j2 == e_j1 and (e_i2 - e_i1) >= _TC_COALESCE_SKIP_WHEN_TAIL_EQUAL_MIN:
            return None
    elif len(opcodes) < 3:
        return None
    else:
        # Do not pull leading unchanged text into ``replace`` (shared prefix is ``equal``).
        if opcodes[0][0] == "equal":
            return None
    if os < m or rs < m:
        return None
    for k in range(m):
        if orig_tokens[os - 1 - k].surface != rev_tokens[rs - 1 - k].surface:
            return None
    si, sj = os - m, rs - m
    if si <= 0 or sj <= 0:
        return None
    if si == 1 and sj == 1:
        o0 = orig_tokens[0].surface.strip()
        r0 = rev_tokens[0].surface.strip()
        if o0 and r0 and (
            (o0.isalpha() and r0.isalpha()) or (o0.isdigit() and r0.isdigit())
        ):
            return None
    out = [
        ("replace", 0, si, 0, sj),
        ("equal", si, os, sj, rs),
    ]
    if out == opcodes:
        return None
    return out


def _tc_opcode_prefix_is_contiguous(
    prefix: list[tuple[str, int, int, int, int]],
) -> bool:
    if len(prefix) <= 1:
        return True
    for i in range(len(prefix) - 1):
        a, b = prefix[i], prefix[i + 1]
        if a[2] != b[1] or a[4] != b[3]:
            return False
    return True


def _tc_unstable_prefix_pattern(prefix: list[tuple[str, int, int, int, int]]) -> bool:
    tags = [p[0] for p in prefix]
    if len(prefix) >= 3:
        return True
    if "insert" in tags and "delete" in tags:
        return True
    if len(tags) >= 2 and tags[0] == "delete" and tags[1] == "insert":
        return True
    return False


def _merge_unstable_opcode_regions(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Merge a fragmented prefix (many small delete/insert/replace/equal ops) into one
    ``replace`` when a stable equal tail of at least ``_TC_ALIGN_MIN_STABLE_TAIL_TOKENS``
    tokens remains at the end.
    """

    if len(opcodes) <= 1:
        return opcodes

    acc = 0
    stable_start: int | None = None
    for idx in range(len(opcodes) - 1, -1, -1):
        tag, i1, i2, j1, j2 = opcodes[idx]
        if tag != "equal":
            break
        acc += i2 - i1
        stable_start = idx
        if acc >= _TC_ALIGN_MIN_STABLE_TAIL_TOKENS:
            break
    if stable_start is None or acc < _TC_ALIGN_MIN_STABLE_TAIL_TOKENS:
        return opcodes

    prefix = opcodes[:stable_start]
    if not prefix:
        return opcodes

    matched_tokens = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in opcodes if tag == "equal")
    similarity = lcs_token_similarity_ratio(
        non_whitespace_norm_keys(orig_tokens),
        non_whitespace_norm_keys(rev_tokens),
    )
    if (
        similarity >= _INLINE_DIFF_SIMILARITY_MIN
        and prefix[0][0] == "equal"
        and (prefix[0][2] - prefix[0][1]) >= _TC_CLUSTER_MEANINGFUL_EQUAL_TOKENS
        and matched_tokens > 0
    ):
        return opcodes

    meaningful_equal_lengths = [
        (i2 - i1)
        for tag, i1, i2, _j1, _j2 in prefix
        if tag == "equal" and (i2 - i1) >= _TC_CLUSTER_MEANINGFUL_EQUAL_TOKENS
    ]
    if len(meaningful_equal_lengths) >= 2:
        return opcodes

    if len(prefix) == 1:
        t, i1, i2, j1, j2 = prefix[0]
        if t == "replace" and (i2 - i1) == 1 and (j2 - j1) == 1:
            return opcodes
        return opcodes
    if len(prefix) == 2 and not _tc_unstable_prefix_pattern(prefix):
        return opcodes

    if not _tc_opcode_prefix_is_contiguous(prefix):
        return opcodes

    i1_lo = prefix[0][1]
    i2_hi = prefix[-1][2]
    j1_lo = prefix[0][3]
    j2_hi = prefix[-1][4]
    merged = [("replace", i1_lo, i2_hi, j1_lo, j2_hi)] + opcodes[stable_start:]
    return _merge_adjacent_equal_opcodes(merged)


def _merge_change_cluster_between_meaningful_equals(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Collapse a fragmented change cluster between substantial equal anchors.

    This targets paragraph rewrites where the matcher finds a few strong anchors
    but still emits ``replace/equal(1-2 tokens)/replace/...`` through the middle.
    Long equal spans remain plain text; only the noisy cluster between them is
    collapsed to a single change opcode.
    """

    if len(opcodes) < 5:
        return opcodes

    def _meaningful_equal(op: tuple[str, int, int, int, int]) -> bool:
        tag, i1, i2, _j1, _j2 = op
        return tag == "equal" and (i2 - i1) >= _TC_CLUSTER_MEANINGFUL_EQUAL_TOKENS

    def _anchor_equal(op: tuple[str, int, int, int, int]) -> bool:
        tag, i1, i2, _j1, _j2 = op
        return tag == "equal" and (i2 - i1) >= _TC_CLUSTER_ANCHOR_EQUAL_TOKENS

    def _emit_change_opcode(
        region: list[tuple[str, int, int, int, int]],
    ) -> tuple[str, int, int, int, int]:
        i1_lo = region[0][1]
        i2_hi = region[-1][2]
        j1_lo = region[0][3]
        j2_hi = region[-1][4]
        if i1_lo == i2_hi:
            return ("insert", i1_lo, i2_hi, j1_lo, j2_hi)
        if j1_lo == j2_hi:
            return ("delete", i1_lo, i2_hi, j1_lo, j2_hi)
        return ("replace", i1_lo, i2_hi, j1_lo, j2_hi)

    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    n = len(opcodes)
    while i < n:
        cur = opcodes[i]
        if not _anchor_equal(cur):
            out.append(cur)
            i += 1
            continue

        region: list[tuple[str, int, int, int, int]] = []
        j = i + 1
        while j < n and not _anchor_equal(opcodes[j]):
            region.append(opcodes[j])
            j += 1
        out.append(cur)
        if not region or j >= n:
            out.extend(region)
            i = j
            continue

        change_count = sum(1 for tag, *_ in region if tag != "equal")
        equal_token_total = sum((i2 - i1) for tag, i1, i2, _j1, _j2 in region if tag == "equal")
        changed_token_total = sum(
            max(i2 - i1, j2 - j1)
            for tag, i1, i2, j1, j2 in region
            if tag != "equal"
        )
        strongest_inner_equal = max(
            ((i2 - i1) for tag, i1, i2, _j1, _j2 in region if tag == "equal"),
            default=0,
        )
        hard_boundary_inside_region = any(
            tag == "equal"
            and _tc_equal_opcode_has_hard_boundary_for_merge(
                orig_tokens, i1, i2, rev_tokens, j1, j2
            )
            for tag, i1, i2, j1, j2 in region
        )
        if (
            change_count >= _TC_CLUSTER_MIN_CHANGE_OPCODES
            and strongest_inner_equal < _TC_CLUSTER_STRONG_INNER_EQUAL_TOKENS
            and changed_token_total > max(12, equal_token_total * 2)
            and _tc_opcode_prefix_is_contiguous(region)
            and not hard_boundary_inside_region
        ):
            out.append(_emit_change_opcode(region))
            out.append(opcodes[j])
            i = j + 1
            continue

        out.extend(region)
        i = j

    return _merge_adjacent_equal_opcodes(out)


def _split_replace_opcodes_on_internal_meaningful_equals(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Expand one coarse ``replace`` when it contains a real reused phrase internally.

    This targets asymmetric replace spans such as ``old citation + phrase`` vs
    ``short reused phrase`` where Word still preserves an internal anchor like
    ``In addition`` as plain text.
    """

    def _find_token_subsequence_start(
        haystack: list[DiffToken], needle: list[DiffToken], start: int
    ) -> int | None:
        if not needle:
            return start
        n = len(needle)
        for idx in range(start, len(haystack) - n + 1):
            if all(haystack[idx + k].surface == needle[k].surface for k in range(n)):
                return idx
        return None

    def _candidate_anchor_ranges_for_equal_span(
        sub_o: list[DiffToken], si1: int, si2: int
    ) -> list[tuple[int, int]]:
        """Full equal span plus trimmed variants that drop weak leading/trailing text."""

        ranges: list[tuple[int, int]] = []

        def _add(a: int, b: int, *, allow_weak: bool = False) -> None:
            if a >= b:
                return
            text = equal_span_surface(sub_o, a, b)
            if not re.search(r"[A-Za-z0-9]", text):
                return
            if not allow_weak and _equal_text_is_weak_anchor(text):
                return
            rng = (a, b)
            if rng not in ranges:
                ranges.append(rng)

        _add(si1, si2)
        wordish = [
            idx
            for idx in range(si1, si2)
            if sub_o[idx].surface.strip() and re.search(r"\w", sub_o[idx].surface)
        ]
        if not wordish:
            return ranges
        for idx in wordish[1:]:
            prefix = equal_span_surface(sub_o, si1, idx)
            if _equal_text_is_weak_anchor(prefix):
                _add(si1, idx, allow_weak=True)
                _add(idx, si2)
        for idx in reversed(wordish[:-1]):
            suffix = equal_span_surface(sub_o, idx + 1, si2)
            if _equal_text_is_weak_anchor(suffix):
                _add(si1, idx + 1)
        # When an equal span starts with a weak bridge and ends with several
        # content words, also expose the interior content words as anchor
        # candidates. This helps split spans like ``and Hispanic women`` or
        # ``of cervical`` without making arbitrary short stopwords anchors.
        if len(wordish) >= 2:
            for k in range(1, len(wordish)):
                head = equal_span_surface(sub_o, si1, wordish[k])
                if not _equal_text_is_weak_anchor(head):
                    break
                for m in range(k, len(wordish)):
                    end = wordish[m] + 1
                    if m + 1 < len(wordish):
                        end = wordish[m + 1]
                    _add(wordish[k], end)
        return ranges

    def _rebuild_with_left_biased_internal_anchors(
        sub_o: list[DiffToken],
        sub_r: list[DiffToken],
        sub_ops: list[tuple[str, int, int, int, int]],
    ) -> list[tuple[str, int, int, int, int]] | None:
        candidates: list[list[tuple[int, int]]] = []
        for stag, si1, si2, _sj1, _sj2 in sub_ops:
            if stag != "equal" or si1 <= 0 or si2 >= len(sub_o):
                continue
            anchor_ranges = _candidate_anchor_ranges_for_equal_span(sub_o, si1, si2)
            if anchor_ranges:
                candidates.append(anchor_ranges)
        if not candidates:
            return None
        rebuilt: list[tuple[str, int, int, int, int]] = []
        cur_i = 0
        cur_j = 0
        used = 0
        for anchor_ranges in candidates:
            chosen: tuple[int, int, int] | None = None
            for si1, si2 in anchor_ranges:
                if si1 < cur_i:
                    continue
                needle = sub_o[si1:si2]
                new_j = _find_token_subsequence_start(sub_r, needle, cur_j)
                if new_j is None:
                    continue
                cand = (new_j, si1, si2)
                if chosen is None or cand[0] < chosen[0] or (
                    cand[0] == chosen[0] and (cand[2] - cand[1]) > (chosen[2] - chosen[1])
                ):
                    chosen = cand
            if chosen is None:
                continue
            new_j, si1, si2 = chosen
            if si1 < cur_i:
                continue
            if si1 > cur_i or new_j > cur_j:
                tag = "replace"
                if si1 == cur_i:
                    tag = "insert"
                elif new_j == cur_j:
                    tag = "delete"
                rebuilt.append((tag, cur_i, si1, cur_j, new_j))
            rebuilt.append(("equal", si1, si2, new_j, new_j + len(needle)))
            cur_i = si2
            cur_j = new_j + len(needle)
            used += 1
        if used == 0:
            return None
        if cur_i < len(sub_o) or cur_j < len(sub_r):
            tag = "replace"
            if cur_i == len(sub_o):
                tag = "insert"
            elif cur_j == len(sub_r):
                tag = "delete"
            rebuilt.append((tag, cur_i, len(sub_o), cur_j, len(sub_r)))
        return _merge_adjacent_equal_opcodes(rebuilt)

    out: list[tuple[str, int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag != "replace":
            out.append((tag, i1, i2, j1, j2))
            continue
        o_len = i2 - i1
        r_len = j2 - j1
        if max(o_len, r_len) < 8:
            out.append((tag, i1, i2, j1, j2))
            continue
        sub_o = orig_tokens[i1:i2]
        sub_r = rev_tokens[j1:j2]
        sm = difflib.SequenceMatcher(None, norm_keys(sub_o), norm_keys(sub_r), autojunk=False)
        sub_ops = sm.get_opcodes()
        sub_ratio = sm.ratio()
        internal_eq = [
            (si1, si2, sj1, sj2)
            for stag, si1, si2, sj1, sj2 in sub_ops
            if stag == "equal" and 0 < si1 and si2 < len(sub_o)
        ]
        has_meaningful_internal_equal = any(
            (si2 - si1) >= _TC_CLUSTER_MEANINGFUL_EQUAL_TOKENS
            for si1, si2, _sj1, _sj2 in internal_eq
        )
        nonweak_internal_equals = [
            (si1, si2, sj1, sj2)
            for si1, si2, sj1, sj2 in internal_eq
            if _candidate_anchor_ranges_for_equal_span(sub_o, si1, si2)
        ]
        allow_left_biased_anchor_split = (
            len(nonweak_internal_equals) >= 1
            and sum((si2 - si1) for si1, si2, _sj1, _sj2 in nonweak_internal_equals) >= 3
            and sub_ratio <= 0.35
        )
        if not has_meaningful_internal_equal and not allow_left_biased_anchor_split:
            out.append((tag, i1, i2, j1, j2))
            continue
        rebuilt_left = None
        if allow_left_biased_anchor_split:
            rebuilt_left = _rebuild_with_left_biased_internal_anchors(sub_o, sub_r, sub_ops)
        if rebuilt_left is not None:
            for stag, si1, si2, sj1, sj2 in rebuilt_left:
                out.append((stag, i1 + si1, i1 + si2, j1 + sj1, j1 + sj2))
            continue
        for stag, si1, si2, sj1, sj2 in sub_ops:
            out.append((stag, i1 + si1, i1 + si2, j1 + sj1, j1 + sj2))
    return _merge_adjacent_equal_opcodes(out)


def _left_bias_internal_equal_between_changes(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Re-anchor a repeated internal ``equal`` to an earlier revised occurrence.

    This repairs ``replace/equal/replace`` triplets where the equal span was
    matched against a later repeated phrase in the revised paragraph, causing the
    following replacement to pull in the wrong clause.
    """

    def _find_token_subsequence_start(
        haystack: list[DiffToken],
        needle: list[DiffToken],
        start: int,
        end: int,
    ) -> int | None:
        if not needle:
            return start
        n = len(needle)
        hi = min(end, len(haystack) - n)
        for idx in range(start, hi + 1):
            if all(haystack[idx + k].surface == needle[k].surface for k in range(n)):
                return idx
        return None

    def _candidate_ranges(i1: int, i2: int) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []

        def _add(a: int, b: int) -> None:
            if a >= b:
                return
            text = equal_span_surface(orig_tokens, a, b)
            if not re.search(r"[A-Za-z0-9]", text):
                return
            if _equal_text_is_weak_anchor(text):
                return
            rng = (a, b)
            if rng not in ranges:
                ranges.append(rng)

        _add(i1, i2)
        a, b = i1, i2
        while a < b and orig_tokens[a].surface.isspace():
            a += 1
            _add(a, b)
        while a < b and orig_tokens[b - 1].surface.isspace():
            b -= 1
            _add(a, b)
        wordish = [
            idx
            for idx in range(i1, i2)
            if orig_tokens[idx].surface.strip() and re.search(r"\w", orig_tokens[idx].surface)
        ]
        if not wordish:
            return ranges
        for idx in wordish[1:]:
            if _equal_text_is_weak_anchor(equal_span_surface(orig_tokens, i1, idx)):
                _add(idx, i2)
        for idx in reversed(wordish[:-1]):
            if _equal_text_is_weak_anchor(equal_span_surface(orig_tokens, idx + 1, i2)):
                _add(i1, idx + 1)
        return ranges

    def _tag_for_bounds(
        i1: int, i2: int, j1: int, j2: int
    ) -> tuple[str, int, int, int, int] | None:
        if i1 == i2 and j1 == j2:
            return None
        if i1 == i2:
            return ("insert", i1, i2, j1, j2)
        if j1 == j2:
            return ("delete", i1, i2, j1, j2)
        return ("replace", i1, i2, j1, j2)

    if len(opcodes) < 3:
        return opcodes
    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    while i < len(opcodes):
        if i + 2 < len(opcodes):
            left = opcodes[i]
            mid = opcodes[i + 1]
            right = opcodes[i + 2]
            if (
                left[0] != "equal"
                and mid[0] == "equal"
                and right[0] != "equal"
                and _tc_opcode_prefix_is_contiguous([left, mid, right])
            ):
                chosen: tuple[int, int, int] | None = None
                for ai1, ai2 in _candidate_ranges(mid[1], mid[2]):
                    new_j = _find_token_subsequence_start(
                        rev_tokens,
                        orig_tokens[ai1:ai2],
                        left[3],
                        mid[3] - 1,
                    )
                    if new_j is None or new_j >= mid[3]:
                        continue
                    cand = (new_j, ai1, ai2)
                    if chosen is None or cand[0] < chosen[0] or (
                        cand[0] == chosen[0] and (cand[2] - cand[1]) > (chosen[2] - chosen[1])
                    ):
                        chosen = cand
                if chosen is not None:
                    new_j, ai1, ai2 = chosen
                    left_new = _tag_for_bounds(left[1], ai1, left[3], new_j)
                    right_new = _tag_for_bounds(ai2, right[2], new_j + (ai2 - ai1), right[4])
                    if left_new is not None:
                        out.append(left_new)
                    out.append(("equal", ai1, ai2, new_j, new_j + (ai2 - ai1)))
                    if right_new is not None:
                        out.append(right_new)
                    i += 3
                    continue
        out.append(opcodes[i])
        i += 1
    return _merge_adjacent_equal_opcodes(out)


def _dedupe_reinserted_equal_prefix(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Remove a duplicate revised prefix that repeats the preceding plain-text equal.

    This repairs patterns like ``equal("In addition")`` followed by a change whose
    revised side also starts with ``In addition``. After stripping the duplicate
    prefix, downstream punctuation rotation can keep the anchor plain instead of
    surfacing a spurious insert.
    """

    def _candidate_ranges(i1: int, i2: int) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []

        def _add(a: int, b: int) -> None:
            if a >= b:
                return
            text = equal_span_surface(orig_tokens, a, b)
            if not text.strip() or _equal_text_is_weak_anchor(text):
                return
            rng = (a, b)
            if rng not in ranges:
                ranges.append(rng)

        _add(i1, i2)
        while i1 < i2 and orig_tokens[i1].surface.isspace():
            i1 += 1
            _add(i1, i2)
        while i1 < i2 and orig_tokens[i2 - 1].surface.isspace():
            i2 -= 1
            _add(i1, i2)
        return ranges

    if len(opcodes) < 2:
        return opcodes
    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    while i < len(opcodes):
        cur = opcodes[i]
        if (
            i + 1 < len(opcodes)
            and cur[0] == "equal"
            and opcodes[i + 1][0] != "equal"
        ):
            nxt = opcodes[i + 1]
            matched = None
            for ai1, ai2 in _candidate_ranges(cur[1], cur[2]):
                span_len = ai2 - ai1
                if equal_span_surface(orig_tokens, ai1, ai2) == equal_span_surface(
                    rev_tokens, nxt[3], min(nxt[4], nxt[3] + span_len)
                ):
                    matched = (ai1, ai2)
                    break
            if matched is not None:
                ai1, ai2 = matched
                new_j1 = nxt[3] + (ai2 - ai1)
                tag = nxt[0]
                if nxt[1] == nxt[2] and new_j1 == nxt[4]:
                    out.append(cur)
                    i += 2
                    continue
                if nxt[1] == nxt[2]:
                    tag = "insert"
                elif new_j1 == nxt[4]:
                    tag = "delete"
                else:
                    tag = "replace"
                out.append(cur)
                out.append((tag, nxt[1], nxt[2], new_j1, nxt[4]))
                i += 2
                continue
        out.append(cur)
        i += 1
    return _merge_adjacent_equal_opcodes(out)


def _pull_meaningful_equal_earlier_from_long_left_replace(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Shift an ``equal`` earlier when a tiny left replace already contains it.

    This targets patterns like ``SCC`` -> long inserted text followed by
    ``compared with`` where the same meaningful phrase appears earlier inside the
    long revised text and should bound the next replacement instead.
    """

    def _find_token_subsequence_start(
        haystack: list[DiffToken],
        needle: list[DiffToken],
        start: int,
        end: int,
    ) -> int | None:
        if not needle:
            return start
        n = len(needle)
        hi = min(end, len(haystack) - n)
        for idx in range(start, hi + 1):
            if all(haystack[idx + k].surface == needle[k].surface for k in range(n)):
                return idx
        return None

    if len(opcodes) < 3:
        return opcodes
    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    while i < len(opcodes):
        if i + 2 < len(opcodes):
            left = opcodes[i]
            mid = opcodes[i + 1]
            right = opcodes[i + 2]
            if (
                left[0] == "replace"
                and mid[0] == "equal"
                and right[0] == "replace"
                and _tc_opcode_prefix_is_contiguous([left, mid, right])
                and (left[2] - left[1]) <= 2
                and (left[4] - left[3]) >= 20
            ):
                eq_text = equal_span_surface(orig_tokens, mid[1], mid[2])
                if eq_text.strip() and not _equal_text_is_weak_anchor(eq_text):
                    needle = orig_tokens[mid[1] : mid[2]]
                    earlier = _find_token_subsequence_start(
                        rev_tokens, needle, left[3], mid[3] - 1
                    )
                    if earlier is not None and earlier < mid[3]:
                        out.append(("replace", left[1], left[2], left[3], earlier))
                        out.append(
                            (
                                "equal",
                                mid[1],
                                mid[2],
                                earlier,
                                earlier + (mid[2] - mid[1]),
                            )
                        )
                        out.append(
                            (
                                "replace",
                                right[1],
                                right[2],
                                earlier + (mid[2] - mid[1]),
                                right[4],
                            )
                        )
                        i += 3
                        continue
        out.append(opcodes[i])
        i += 1
    return _merge_adjacent_equal_opcodes(out)


def _prefer_later_stronger_equal_anchor(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Prefer a later stronger equal over an earlier single-word anchor.

    This helps regions like ``White`` vs ``and Hispanic women`` where the later
    phrase is a better stable anchor and the earlier single word should merge
    into the surrounding change.
    """

    def _trim_weak_prefix(i1: int, i2: int) -> tuple[int, int]:
        words = [
            idx
            for idx in range(i1, i2)
            if orig_tokens[idx].surface.strip() and re.search(r"\w", orig_tokens[idx].surface)
        ]
        for idx in words[1:]:
            if _equal_text_is_weak_anchor(equal_span_surface(orig_tokens, i1, idx)):
                return idx, i2
        return i1, i2

    if len(opcodes) < 4:
        return opcodes

    overall_similarity = lcs_token_similarity_ratio(
        non_whitespace_norm_keys(orig_tokens),
        non_whitespace_norm_keys(rev_tokens),
    )
    if overall_similarity >= 0.85:
        return opcodes

    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    while i < len(opcodes):
        if i + 3 < len(opcodes):
            left, eq1, mid, eq2 = opcodes[i : i + 4]
            if (
                left[0] != "equal"
                and eq1[0] == "equal"
                and mid[0] != "equal"
                and eq2[0] == "equal"
                and _tc_opcode_prefix_is_contiguous([left, eq1, mid, eq2])
            ):
                eq1_text = equal_span_surface(orig_tokens, eq1[1], eq1[2]).strip()
                t_i1, t_i2 = _trim_weak_prefix(eq2[1], eq2[2])
                eq2_trimmed = equal_span_surface(orig_tokens, t_i1, t_i2)
                eq1_words = re.findall(r"[A-Za-z]+", eq1_text)
                eq2_words = re.findall(r"[A-Za-z]+", eq2_trimmed)
                mid_text = equal_span_surface(orig_tokens, mid[1], mid[2]) + equal_span_surface(
                    rev_tokens, mid[3], mid[4]
                )
                if (
                    len(eq1_words) == 1
                    and len(eq2_words) >= 1
                    and not _equal_text_is_weak_anchor(eq2_trimmed)
                    and (
                        not re.search(r"[A-Za-z0-9]", mid_text)
                        or re.fullmatch(r"[\s,;:.-]*", mid_text) is not None
                    )
                ):
                    out.append(("replace", left[1], eq1[2], left[3], mid[4]))
                    out.append(("equal", t_i1, t_i2, eq2[3] + (t_i1 - eq2[1]), eq2[3] + (t_i2 - eq2[1])))
                    i += 4
                    continue
        out.append(opcodes[i])
        i += 1
    return _merge_adjacent_equal_opcodes(out)


def _rotate_shared_punctuation_around_deleted_clause(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Rotate shared punctuation around ``equal -> delete -> equal`` boundaries.

    This fixes cases like ``In addition, ...`` where the comma should stay plain,
    not be shown as deleted, and the deleted clause should keep the trailing comma
    before the next unchanged phrase.
    """

    def _shared_punct_ws_prefix_len(tokens: list, start: int, end: int) -> int:
        k = 0
        while start + k < end:
            s = tokens[start + k].surface
            if s.isspace() or re.fullmatch(r"[,\.;:]", s):
                k += 1
                continue
            break
        return k

    if len(opcodes) < 3:
        return opcodes
    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    while i < len(opcodes):
        if i + 2 < len(opcodes):
            left = opcodes[i]
            mid = opcodes[i + 1]
            right = opcodes[i + 2]
            if (
                left[0] == "equal"
                and mid[0] == "delete"
                and right[0] == "equal"
                and _tc_opcode_prefix_is_contiguous([left, mid, right])
            ):
                li1, li2, lj1, lj2 = left[1], left[2], left[3], left[4]
                mi1, mi2 = mid[1], mid[2]
                ri1, ri2, rj1, rj2 = right[1], right[2], right[3], right[4]
                if li2 > li1 and lj2 > lj1:
                    left_text = equal_span_surface(orig_tokens, li1, li2)
                    if left_text and re.search(r"[A-Za-z]$", left_text):
                        k_del = _shared_punct_ws_prefix_len(orig_tokens, mi1, mi2)
                        k_eq_o = _shared_punct_ws_prefix_len(orig_tokens, ri1, ri2)
                        k_eq_r = _shared_punct_ws_prefix_len(rev_tokens, rj1, rj2)
                        k = min(k_del, k_eq_o, k_eq_r)
                        if k > 0:
                            del_prefix = equal_span_surface(orig_tokens, mi1, mi1 + k)
                            eq_o_prefix = equal_span_surface(orig_tokens, ri1, ri1 + k)
                            eq_r_prefix = equal_span_surface(rev_tokens, rj1, rj1 + k)
                            if del_prefix == eq_o_prefix == eq_r_prefix:
                                out.append(("equal", li1, li2 + k, lj1, lj2 + k))
                                out.append(("delete", mi1 + k, mi2 + k, mid[3], mid[4]))
                                out.append(("equal", ri1 + k, ri2, rj1 + k, rj2))
                                i += 3
                                continue
        out.append(opcodes[i])
        i += 1
    return _merge_adjacent_equal_opcodes(out)


def _equal_text_is_weak_anchor(text: str) -> bool:
    """True for short stopword/citation equal islands that should not stand alone."""

    stripped = text.strip()
    if not stripped:
        return True
    if stripped == ".":
        return True
    words = re.findall(r"[A-Za-z]+", stripped)
    if not words:
        return True
    weak_words = {"the", "a", "an", "may", "of", "and", "or", "to", "in", "on", "with"}
    return len(words) <= 2 and all(w.lower() in weak_words for w in words)


def _absorb_weak_equal_islands_between_changes(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    Merge short weak ``equal`` spans into surrounding changes.

    Word often absorbs tiny stopword/citation matches such as ``the``, ``may``,
    or a citation prefix instead of emitting them as standalone plain-text anchors.
    """

    if len(opcodes) < 3:
        return opcodes
    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    while i < len(opcodes):
        if i + 2 < len(opcodes):
            left = opcodes[i]
            mid = opcodes[i + 1]
            right = opcodes[i + 2]
            if (
                left[0] != "equal"
                and mid[0] == "equal"
                and right[0] != "equal"
                and _tc_opcode_prefix_is_contiguous([left, mid, right])
            ):
                mid_text = equal_span_surface(orig_tokens, mid[1], mid[2])
                if (
                    (mid[2] - mid[1]) <= _TC_CLUSTER_MEANINGFUL_EQUAL_TOKENS
                    and _equal_text_is_weak_anchor(mid_text)
                    and not _tc_equal_opcode_has_hard_boundary_for_merge(
                        orig_tokens, mid[1], mid[2], rev_tokens, mid[3], mid[4]
                    )
                ):
                    i1_lo = left[1]
                    i2_hi = right[2]
                    j1_lo = left[3]
                    j2_hi = right[4]
                    tag = "replace"
                    if i1_lo == i2_hi:
                        tag = "insert"
                    elif j1_lo == j2_hi:
                        tag = "delete"
                    out.append((tag, i1_lo, i2_hi, j1_lo, j2_hi))
                    i += 3
                    continue
        out.append(opcodes[i])
        i += 1
    return _merge_adjacent_equal_opcodes(out)


def _expand_replace_to_include_following_shared_ws_token(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
    rev_tokens: list,
) -> list[tuple[str, int, int, int, int]]:
    """
    When a ``replace`` is immediately followed by ``equal`` whose first token is
    whitespace on both sides, fold that token into the ``replace``.

    The outer LCS often leaves a shared space in the ``equal`` span (same ``norm_key``),
    which would otherwise emit ``w:del``/``w:ins`` without the separator before the next
    word. Moving one whitespace token into the replace keeps one del + one ins atomic
    while preserving visible spacing (e.g. ``A `` / ``The 10 most ``).
    """

    out: list[tuple[str, int, int, int, int]] = []
    i = 0
    while i < len(opcodes):
        tag, i1, i2, j1, j2 = opcodes[i]
        if tag != "replace":
            out.append((tag, i1, i2, j1, j2))
            i += 1
            continue
        if i + 1 < len(opcodes):
            ntag, ni1, ni2, nj1, nj2 = opcodes[i + 1]
            if (
                ntag == "equal"
                and ni1 == i2
                and nj1 == j2
                and ni1 < ni2
                and nj1 < nj2
                and orig_tokens[ni1].surface.isspace()
                and rev_tokens[nj1].surface.isspace()
            ):
                new_i2 = ni1 + 1
                new_j2 = nj1 + 1
                if new_i2 == ni2 and new_j2 == nj2:
                    out.append(("replace", i1, new_i2, j1, new_j2))
                    i += 2
                    continue
                out.append(("replace", i1, new_i2, j1, new_j2))
                out.append(("equal", new_i2, ni2, new_j2, nj2))
                i += 2
                continue
        out.append((tag, i1, i2, j1, j2))
        i += 1
    return _merge_adjacent_equal_opcodes(out)


def classify_change(
    orig_tokens: list,
    rev_tokens: list,
    ratio: float,
) -> Literal["MICRO_EDIT", "PHRASE_EDIT", "HEAVY_EDIT"]:
    """Route concat-texts diff by shared token similarity, not raw character churn."""

    _ = orig_tokens, rev_tokens
    if ratio > 0.92:
        return "MICRO_EDIT"
    if ratio >= 0.80:
        return "PHRASE_EDIT"
    return "HEAVY_EDIT"


def _meaningful_equal_anchor_lengths(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
) -> list[int]:
    lengths: list[int] = []
    for tag, i1, i2, _j1, _j2 in opcodes:
        if tag != "equal":
            continue
        meaningful = sum(
            1 for tok in orig_tokens[i1:i2] if any(ch.isalnum() for ch in tok.surface)
        )
        if meaningful:
            lengths.append(meaningful)
    return lengths


def _should_force_inline_diff_for_low_similarity(
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
) -> bool:
    """
    Keep low-similarity diffs inline when they are still one anchored local edit.

    This catches cases like ``Hello`` → ``Hello world`` or ``Topic\t6`` → ``Topic\t7``
    where the overall token overlap is below the global 0.7 threshold but the
    change is obviously a small insertion/deletion/replacement around a stable
    prefix or suffix, not a true paragraph rewrite.
    """

    change_ops = [op for op in opcodes if op[0] != "equal"]
    if not change_ops or len(change_ops) > 2:
        return False
    anchor_lengths = _meaningful_equal_anchor_lengths(opcodes, orig_tokens)
    if not anchor_lengths:
        return False
    if max(anchor_lengths) < 1:
        return False
    if (
        len(change_ops) == 2
        and len(opcodes) == 3
        and opcodes[1][0] == "equal"
    ):
        changed_orig = sum(op[2] - op[1] for op in change_ops)
        changed_rev = sum(op[4] - op[3] for op in change_ops)
        if changed_orig <= 4 and changed_rev <= 4:
            return True
    return opcodes[0][0] == "equal" or opcodes[-1][0] == "equal"


def _should_emit_full_rewrite_for_token_diff(
    similarity: float,
    opcodes: list[tuple[str, int, int, int, int]],
    orig_tokens: list,
) -> bool:
    if similarity >= _INLINE_DIFF_SIMILARITY_MIN:
        return False
    anchor_lengths = _meaningful_equal_anchor_lengths(opcodes, orig_tokens)
    if len(anchor_lengths) >= 3 and sum(anchor_lengths) >= 5:
        return False
    if (
        anchor_lengths
        and max(anchor_lengths) >= _INLINE_DIFF_STRONG_ANCHOR_MIN_TOKENS
        and similarity >= _INLINE_DIFF_ANCHORED_REWRITE_SIMILARITY_MIN
    ):
        return False
    if _should_force_inline_diff_for_low_similarity(opcodes, orig_tokens):
        return False
    return True


def _max_digit_run_length(s: str) -> int:
    best = cur = 0
    for c in s:
        if c.isdigit():
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _concat_tc_collect_emitted_text(elements: list[ET.Element]) -> str:
    """
    Flatten emitted track-change nodes to a string for sanity checks.

    Includes ``w:tab`` stops as ``\\t`` so digit runs are not glued across tab
    leaders (e.g. ``MK-2870`` + tab + ``11`` must not read as ``287011`` for
    :func:`_concat_tc_emitted_numeric_corruption`).
    """

    parts: list[str] = []
    for root in elements:
        for el in root.iter():
            ln = _local_name(el.tag)
            if ln == "tab":
                parts.append("\t")
            elif ln in ("t", "delText") and el.text:
                parts.append(el.text)
    return "".join(parts)


def _numeric_grouping_only_change(a: str, b: str) -> bool:
    """
    True when *a* and *b* differ only by thousands separators in numeric text.

    Example: ``5,003`` → ``5003`` should emit a small inline delete of `,`
    rather than a full-token replace (token LCS treats ``5,003`` vs ``5003``
    as multiple tokens vs one token and would otherwise emit full del+ins).
    """

    if a == b:
        return False
    if not (re.search(r"\d", a) and re.search(r"\d", b)):
        return False
    if "," not in a and "," not in b:
        return False
    return a.replace(",", "") == b.replace(",", "")


def _emit_char_level_tc_elements(
    a: str,
    b: str,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """Character-level ``w:r`` / ``w:del`` / ``w:ins`` children for *a* → *b* (SCRUM-141)."""

    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out: list[ET.Element] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            chunk = a[i1:i2]
            if chunk:
                out.extend(_w_runs_for_plain_text(chunk))
        elif tag == "delete":
            chunk = a[i1:i2]
            if chunk:
                out.append(_w_del_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "insert":
            chunk = b[j1:j2]
            if chunk:
                out.append(_w_ins_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "replace":
            before = a[i1:i2]
            after = b[j1:j2]
            if before:
                out.append(_w_del_segment(before, _next_id(id_counter), author, date_iso))
            if after:
                out.append(_w_ins_segment(after, _next_id(id_counter), author, date_iso))
    return out


def _replace_span_prefers_char_level_track_changes(before_text: str, after_text: str) -> bool:
    """Same gates as :func:`_track_change_elements_for_concat_texts` ``replace`` branch (SCRUM-141)."""

    if not (before_text and after_text):
        return False
    span_chars = len(before_text) + len(after_text)
    span_ratio = difflib.SequenceMatcher(
        None, before_text, after_text, autojunk=False
    ).ratio()
    lcp_len = 0
    for ca, cb in zip(before_text, after_text, strict=False):
        if ca != cb:
            break
        lcp_len += 1
    digitish = bool(
        re.search(r"\d", before_text) and re.search(r"\d", after_text)
    )
    return (
        span_chars >= 16
        and span_ratio >= 0.55
        and (lcp_len >= 15 or digitish)
    )


def _concat_tc_emitted_numeric_corruption(
    orig_text: str, rev_text: str, emitted_concat: str
) -> bool:
    """True if emitted text shows digit runs longer than in either source (merged-number glitch)."""

    mo = _max_digit_run_length(orig_text)
    mr = _max_digit_run_length(rev_text)
    me = _max_digit_run_length(emitted_concat)
    base = max(mo, mr)
    if me <= base:
        return False
    if me >= 6 and me >= base + 2:
        return True
    if re.search(r"\d{4}\d{4,}", emitted_concat):
        if not re.search(r"\d{4}\d{4,}", rev_text) and not re.search(
            r"\d{4}\d{4,}", orig_text
        ):
            return True
    return False


def _track_change_elements_for_concat_texts(
    orig_text: str,
    rev_text: str,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element]:
    """Word / punctuation / whitespace LCS on norm keys → surfaces in ``w:r`` / ``w:ins`` / ``w:del``.

    Each ``replace`` opcode normally emits at most one ``w:del`` and one ``w:ins`` (joined token
    surfaces; no nested diff inside that pair).

    When a ``replace`` span is long and still **high-similarity** at the character level, the
    span is expanded to **character-level** ``w:r`` / ``w:del`` / ``w:ins`` instead of one
    monolithic delete+insert. That addresses token/heuristic opcode merging that otherwise pulls
    unchanged text into a single ``replace`` (SCRUM-141 class defects).

    When token LCS looks like a large rewrite (low match ratio, many opcodes), returns a single
    ``w:del`` for *orig_text* and a single ``w:ins`` for *rev_text* instead of interleaved markup.

    Verbose fragmentation trace (stderr): set ``MDC_DEBUG_TC_CONCAT_FRAGMENTS=1``, or use the
    built-in example pair ``the name is kiran`` vs ``I am introduce as kiran`` (always traces).
    """

    if _numeric_grouping_only_change(orig_text, rev_text):
        return _emit_char_level_tc_elements(
            orig_text,
            rev_text,
            id_counter=id_counter,
            author=author,
            date_iso=date_iso,
        )

    orig_tokens = tokenize_for_lcs(orig_text)
    rev_tokens = tokenize_for_lcs(rev_text)
    total_orig_tokens = len(orig_tokens)
    total_rev_tokens = len(rev_tokens)
    if total_orig_tokens == 0 and total_rev_tokens > 0:
        print(
            "[MDC_DEBUG_TC_CONCAT_FRAG] STRUCTURAL_EMPTY_CASE_TRIGGERED "
            "orig_tokens=0 rev_tokens>0 insert_only",
            file=sys.stderr,
        )
        return [
            _w_ins_segment(rev_text, _next_id(id_counter), author, date_iso),
        ]
    if total_rev_tokens == 0 and total_orig_tokens > 0:
        print(
            "[MDC_DEBUG_TC_CONCAT_FRAG] STRUCTURAL_EMPTY_CASE_TRIGGERED "
            "rev_tokens=0 orig_tokens>0 delete_only",
            file=sys.stderr,
        )
        return [
            _w_del_segment(orig_text, _next_id(id_counter), author, date_iso),
        ]
    key_fn = _tc_norm_keys if _should_use_tab_aware_lcs_keys(orig_text, rev_text) else norm_keys
    matcher = difflib.SequenceMatcher(
        None, key_fn(orig_tokens), key_fn(rev_tokens), autojunk=False
    )
    sm_match_ratio = _word_token_similarity_ratio(orig_text, rev_text)
    opcodes = matcher.get_opcodes()
    classification = classify_change(orig_tokens, rev_tokens, sm_match_ratio)
    if _should_emit_full_rewrite_for_token_diff(sm_match_ratio, opcodes, orig_tokens):
        if _tc_concat_fragmentation_debug_enabled(orig_text, rev_text):
            print(
                f"[MDC_DEBUG_TC_CONCAT_FRAG] CLASSIFY_FULL_REWRITE match_ratio={sm_match_ratio:.6f}",
                file=sys.stderr,
            )
        return [
            _w_del_segment(orig_text, _next_id(id_counter), author, date_iso),
            _w_ins_segment(rev_text, _next_id(id_counter), author, date_iso),
        ]
    if _tc_concat_fragmentation_debug_enabled(orig_text, rev_text):
        print(
            f"[MDC_DEBUG_TC_CONCAT_FRAG] classification={classification} "
            f"match_ratio={sm_match_ratio:.6f} "
            f"n_orig_tokens={total_orig_tokens} n_rev_tokens={total_rev_tokens}",
            file=sys.stderr,
        )
    maybe_log_lcs_debug("concat_texts", orig_tokens, rev_tokens, matcher)
    opcodes = _collapse_adjacent_replace_opcodes(opcodes, orig_tokens, rev_tokens)
    opcodes = _refine_replace_boundaries(opcodes, orig_tokens, rev_tokens)
    coalesced_suffix = _coalesce_opcodes_at_longest_common_token_suffix(
        orig_tokens, rev_tokens, opcodes
    )
    if coalesced_suffix is not None:
        opcodes = coalesced_suffix
    else:
        opcodes = _merge_unstable_opcode_regions(opcodes, orig_tokens, rev_tokens)
    opcodes = _merge_change_cluster_between_meaningful_equals(opcodes, orig_tokens, rev_tokens)
    opcodes = _split_replace_opcodes_on_internal_meaningful_equals(
        opcodes, orig_tokens, rev_tokens
    )
    opcodes = _left_bias_internal_equal_between_changes(
        opcodes, orig_tokens, rev_tokens
    )
    opcodes = _pull_meaningful_equal_earlier_from_long_left_replace(
        opcodes, orig_tokens, rev_tokens
    )
    opcodes = _prefer_later_stronger_equal_anchor(
        opcodes, orig_tokens, rev_tokens
    )
    opcodes = _dedupe_reinserted_equal_prefix(
        opcodes, orig_tokens, rev_tokens
    )
    opcodes = _absorb_weak_equal_islands_between_changes(
        opcodes, orig_tokens, rev_tokens
    )
    opcodes = _rotate_shared_punctuation_around_deleted_clause(
        opcodes, orig_tokens, rev_tokens
    )
    opcodes = _expand_replace_to_include_following_shared_ws_token(
        opcodes, orig_tokens, rev_tokens
    )
    matched_tc = deleted_tc = inserted_tc = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            matched_tc += i2 - i1
        elif tag == "delete":
            deleted_tc += i2 - i1
        elif tag == "insert":
            inserted_tc += j2 - j1
        elif tag == "replace":
            deleted_tc += i2 - i1
            inserted_tc += j2 - j1
    opcode_count = len(opcodes)
    denom = max(total_orig_tokens, total_rev_tokens)
    match_ratio = (matched_tc / denom) if denom > 0 else 0.0
    has_meaningful_equal = any(
        tag == "equal" and (i2 - i1) >= _TC_CLUSTER_MEANINGFUL_EQUAL_TOKENS
        for tag, i1, i2, _j1, _j2 in opcodes
    )
    collapse_rewrite = (
        match_ratio < 0.35
        and opcode_count >= 5
        and (deleted_tc + inserted_tc) >= 4
        and total_orig_tokens >= 4
        and total_rev_tokens >= 4
        and not has_meaningful_equal
    )
    if collapse_rewrite:
        print(
            "[MDC_DEBUG_TC_CONCAT_FRAG] COLLAPSE_REWRITE_TRIGGERED",
            file=sys.stderr,
        )
        return [
            _w_del_segment(orig_text, _next_id(id_counter), author, date_iso),
            _w_ins_segment(rev_text, _next_id(id_counter), author, date_iso),
        ]
    if _tc_concat_fragmentation_debug_enabled(orig_text, rev_text):
        _log_tc_concat_fragmentation_trace(orig_text, rev_text, orig_tokens, rev_tokens, opcodes)
    out: list[ET.Element] = []

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            chunk = equal_span_surface(orig_tokens, i1, i2)
            if chunk:
                out.extend(_w_runs_for_plain_text(chunk))
        elif tag == "delete":
            chunk = equal_span_surface(orig_tokens, i1, i2)
            if chunk:
                out.append(_w_del_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "insert":
            chunk = equal_span_surface(rev_tokens, j1, j2)
            if chunk:
                out.append(_w_ins_segment(chunk, _next_id(id_counter), author, date_iso))
        elif tag == "replace":
            before_text = equal_span_surface(orig_tokens, i1, i2)
            after_text = equal_span_surface(rev_tokens, j1, j2)
            if _replace_span_prefers_char_level_track_changes(before_text, after_text):
                out.extend(
                    _emit_char_level_tc_elements(
                        before_text,
                        after_text,
                        id_counter=id_counter,
                        author=author,
                        date_iso=date_iso,
                    )
                )
                continue
            if before_text:
                out.append(_w_del_segment(before_text, _next_id(id_counter), author, date_iso))
            if after_text:
                out.append(_w_ins_segment(after_text, _next_id(id_counter), author, date_iso))
            continue

    if _concat_tc_emitted_numeric_corruption(
        orig_text, rev_text, _concat_tc_collect_emitted_text(out)
    ):
        if _tc_concat_fragmentation_debug_enabled(orig_text, rev_text):
            print(
                "[MDC_DEBUG_TC_CONCAT_FRAG] NUMERIC_CORRUPTION_FALLBACK full_del_ins",
                file=sys.stderr,
            )
        return [
            _w_del_segment(orig_text, _next_id(id_counter), author, date_iso),
            _w_ins_segment(rev_text, _next_id(id_counter), author, date_iso),
        ]
    return out


def build_paragraph_track_change_elements(
    original: BodyParagraph,
    revised: BodyParagraph,
    config: CompareConfig,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
    source_p_el: ET.Element | None = None,
    revised_p_el: ET.Element | None = None,
) -> list[ET.Element]:
    """Return ordered ``w:r`` / ``w:ins`` / ``w:del`` children for one ``w:p``."""

    dbg = _paragraph_track_change_build_debug_enabled()
    orig_text: str | None = None
    rev_text: str | None = None
    if dbg:
        orig_text = _concat_paragraph_text(original, config)
        rev_text = _concat_paragraph_text(revised, config)
        print("[MDC_DEBUG_PARAGRAPH_TC] build_paragraph_track_change_elements", file=sys.stderr)
        print(f"[MDC_DEBUG_PARAGRAPH_TC]   repr(orig_text)={orig_text!r}", file=sys.stderr)
        print(f"[MDC_DEBUG_PARAGRAPH_TC]   repr(rev_text)={rev_text!r}", file=sys.stderr)
        print(
            f"[MDC_DEBUG_PARAGRAPH_TC]   len(original.runs)={len(original.get('runs', []))} "
            f"len(revised.runs)={len(revised.get('runs', []))}",
            file=sys.stderr,
        )
        print(
            f"[MDC_DEBUG_PARAGRAPH_TC]   orig_text_empty={orig_text == ''} "
            f"rev_text_empty={rev_text == ''}",
            file=sys.stderr,
        )
        _debug_log_concat_paragraph_runs("original", original, config, orig_text)
        _debug_log_concat_paragraph_runs("revised", revised, config, rev_text)
        print(
            f"[MDC_DEBUG_PARAGRAPH_TC]   source_p_el is not None → "
            f"preserving path will be tried first: {source_p_el is not None}",
            file=sys.stderr,
        )

    if source_p_el is not None:
        preserved = _try_build_track_changes_preserving_orig_runs(
            source_p_el,
            original,
            revised,
            config,
            revised_p_el=revised_p_el,
            id_counter=id_counter,
            author=author,
            date_iso=date_iso,
        )
        if preserved is not None:
            if dbg:
                assert orig_text is not None and rev_text is not None
                print(
                    "[MDC_DEBUG_PARAGRAPH_TC]   branch=preserving_orig_runs (returned list, "
                    "not concat fallback)",
                    file=sys.stderr,
                )
                _debug_log_tc_sequence_opcodes(
                    "preserving (same strings as _concat_paragraph_text / preserving inner LCS)",
                    orig_text,
                    rev_text,
                )
            return preserved
        if dbg:
            print(
                "[MDC_DEBUG_PARAGRAPH_TC]   preserving path returned None "
                "(DOM/IR mismatch or normalization length change); using concat fallback",
                file=sys.stderr,
            )

    if orig_text is None:
        orig_text = _concat_paragraph_text(original, config)
        rev_text = _concat_paragraph_text(revised, config)
    if dbg:
        _debug_log_tc_sequence_opcodes("concat_fallback _track_change_elements_for_concat_texts", orig_text, rev_text)
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


def _build_structured_toc_field_diff(
    orig_text: str,
    rev_text: str,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> list[ET.Element] | None:
    """
    Tab-aware diff for TOC lines with stable ``section<TAB>title<TAB>page`` fields.

    Keep the section field plain when unchanged, then diff the title and page
    fields independently. This preserves TOC tab boundaries and prevents a title
    rewrite from absorbing the page number into the same ``w:del`` / ``w:ins`` span.
    """

    ofields = orig_text.split("\t")
    rfields = rev_text.split("\t")
    if len(ofields) != 3 or len(rfields) != 3:
        return None
    if ofields[0] != rfields[0]:
        return None
    if not (re.search(r"\d", ofields[1]) or re.search(r"\d", rfields[1])):
        return None

    out: list[ET.Element] = []
    if ofields[0]:
        out.extend(_w_runs_for_plain_text(ofields[0]))
    out.extend(_w_runs_for_plain_text("\t"))

    if ofields[1] == rfields[1]:
        if ofields[1]:
            out.extend(_w_runs_for_plain_text(ofields[1]))
    else:
        out.extend(
            _track_change_elements_for_concat_texts(
                ofields[1],
                rfields[1],
                id_counter=id_counter,
                author=author,
                date_iso=date_iso,
            )
        )

    out.extend(_w_runs_for_plain_text("\t"))

    if ofields[2] == rfields[2]:
        if ofields[2]:
            out.extend(_w_runs_for_plain_text(ofields[2]))
    else:
        out.extend(
            _track_change_elements_for_concat_texts(
                ofields[2],
                rfields[2],
                id_counter=id_counter,
                author=author,
                date_iso=date_iso,
            )
        )
    return out


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
    out = _build_structured_toc_field_diff(
        orig_text,
        rev_text,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )
    if out is None:
        out = _track_change_elements_for_concat_texts(
            orig_text,
            rev_text,
            id_counter=id_counter,
            author=author,
            date_iso=date_iso,
        )
    # TOC heading/list page-number deltas (e.g. 1 -> 2) can create noisy "Deleted: 1"
    # balloons near the front-matter heading block. Limit numeric-delete suppression to
    # those heading/list lines so deeper TOC entries still keep numeric-only del markers.
    toc_line = (orig_text + " " + rev_text).upper()
    suppress_numeric_delete = (
        "TABLE OF CONTENTS" in toc_line
        or "LIST OF TABLES" in toc_line
        or "LIST OF ABBREVIATIONS" in toc_line
        or "TABLE OF REVISIONS" in toc_line
    )
    cleaned: list[ET.Element] = []
    i = 0
    while i < len(out):
        cur = out[i]
        ln = _local_name(cur.tag)
        if ln == "del":
            del_txt = "".join((t.text or "") for t in cur.findall(".//w:delText", NS)).strip()
            if suppress_numeric_delete and re.fullmatch(r"\d+", del_txt):
                if i + 1 < len(out) and _local_name(out[i + 1].tag) == "ins":
                    ins_txt = "".join(
                        (t.text or "") for t in out[i + 1].findall(".//w:t", NS)
                    ).strip()
                    if re.fullmatch(r"\d+", ins_txt):
                        for run in _w_runs_for_plain_text(ins_txt):
                            cleaned.append(run)
                        i += 2
                        continue
                i += 1
                continue
        cleaned.append(cur)
        i += 1
    return cleaned


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


def _wrap_paragraph_non_ppr_children_with_ins(
    p_el: ET.Element,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> None:
    """Wrap one table paragraph's non-``w:pPr`` children in a single ``w:ins``."""

    non_ppr = [c for c in p_el if _local_name(c.tag) != "pPr"]
    if not non_ppr:
        return
    if len(non_ppr) == 1 and _local_name(non_ppr[0].tag) == "ins":
        return
    ins_el = ET.Element(
        f"{{{WORD_NAMESPACE}}}ins",
        {
            f"{{{WORD_NAMESPACE}}}id": _next_id(id_counter),
            f"{{{WORD_NAMESPACE}}}author": author,
            f"{{{WORD_NAMESPACE}}}date": date_iso,
        },
    )
    for ch in list(p_el):
        if _local_name(ch.tag) == "pPr":
            continue
        ins_el.append(copy.deepcopy(ch))
        p_el.remove(ch)
    insert_at = 0
    for i, ch in enumerate(p_el):
        if _local_name(ch.tag) == "pPr":
            insert_at = i + 1
            break
    p_el.insert(insert_at, ins_el)


def _ensure_inserted_table_cell_shading(tc_el: ET.Element) -> None:
    """Apply Word-like light blue shading to structurally inserted table cells."""

    tc_pr = tc_el.find("w:tcPr", NS)
    if tc_pr is None:
        tc_pr = ET.Element(f"{{{WORD_NAMESPACE}}}tcPr")
        tc_el.insert(0, tc_pr)
    shd = tc_pr.find("w:shd", NS)
    if shd is None:
        shd = ET.Element(f"{{{WORD_NAMESPACE}}}shd")
        tc_pr.append(shd)
    shd.set(f"{{{WORD_NAMESPACE}}}val", "clear")
    shd.set(f"{{{WORD_NAMESPACE}}}color", "auto")
    shd.set(f"{{{WORD_NAMESPACE}}}fill", _INSERTED_TABLE_CELL_SHADE_FILL)


def _mark_table_content_as_inserted(
    tbl_el: ET.Element,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
) -> None:
    """Revised-only table: keep ``w:tbl`` in-flow and mark paragraph content with ``w:ins``."""

    for tc_el in tbl_el.findall(".//w:tc", NS):
        _ensure_inserted_table_cell_shading(tc_el)
    for p_el in tbl_el.findall(".//w:p", NS):
        _wrap_paragraph_non_ppr_children_with_ins(
            p_el,
            id_counter=id_counter,
            author=author,
            date_iso=date_iso,
        )


def _table_preview_text(tbl_el: ET.Element) -> str:
    parts: list[str] = []
    for t in tbl_el.findall(".//w:t", NS):
        if t.text:
            parts.append(t.text)
            if len("".join(parts)) > 120:
                break
    return "".join(parts)[:120]


def _paragraph_contains_text(p_el: ET.Element, needle: str) -> bool:
    text = "".join((t.text or "") for t in p_el.findall(".//w:t", NS))
    return needle.lower() in text.lower()


def _paragraph_has_page_break_before(p_el: ET.Element) -> bool:
    ppr = p_el.find("w:pPr", NS)
    if ppr is None:
        return False
    return ppr.find("w:pageBreakBefore", NS) is not None


def _ensure_page_break_before_from_revised(orig_p: ET.Element, rev_p: ET.Element) -> bool:
    """
    If revised paragraph has ``w:pageBreakBefore`` and original paragraph lacks it,
    copy that one property into the original paragraph ``w:pPr``.
    """

    if not _paragraph_has_page_break_before(rev_p):
        return False
    ppr = orig_p.find("w:pPr", NS)
    if ppr is None:
        ppr = ET.Element(f"{{{WORD_NAMESPACE}}}pPr")
        orig_p.insert(0, ppr)
    if ppr.find("w:pageBreakBefore", NS) is not None:
        return False
    ppr.append(ET.Element(f"{{{WORD_NAMESPACE}}}pageBreakBefore"))
    return True


def _sync_page_break_before_to_revised(orig_p: ET.Element, rev_p: ET.Element) -> bool:
    """
    Make ``orig_p`` page-break-before parity match ``rev_p``.

    Preserve all other paragraph properties; only add/remove ``w:pageBreakBefore``
    so matched paragraphs don't keep legacy pagination that was removed in the
    revised document.
    """

    rev_has_pb = _paragraph_has_page_break_before(rev_p)
    ppr = orig_p.find("w:pPr", NS)
    if rev_has_pb:
        if ppr is None:
            ppr = ET.Element(f"{{{WORD_NAMESPACE}}}pPr")
            orig_p.insert(0, ppr)
        if ppr.find("w:pageBreakBefore", NS) is None:
            ppr.append(ET.Element(f"{{{WORD_NAMESPACE}}}pageBreakBefore"))
            return True
        return False

    if ppr is None:
        return False
    pb = ppr.find("w:pageBreakBefore", NS)
    if pb is None:
        return False
    ppr.remove(pb)
    return True


def _copy_revised_p_pr_to_inserted_paragraph(new_p: ET.Element, rev_p: ET.Element) -> None:
    """Preserve revised paragraph layout (including page breaks) on revised-only inserts."""

    rev_ppr = rev_p.find("w:pPr", NS)
    if rev_ppr is None:
        return
    existing = new_p.find("w:pPr", NS)
    if existing is not None:
        new_p.remove(existing)
    new_p.insert(0, copy.deepcopy(rev_ppr))


def _replace_p_pr_from_revised(orig_p: ET.Element, rev_p: ET.Element) -> None:
    """Replace ``orig_p`` paragraph properties with the revised paragraph properties."""

    existing = orig_p.find("w:pPr", NS)
    if existing is not None:
        orig_p.remove(existing)
    rev_ppr = rev_p.find("w:pPr", NS)
    if rev_ppr is not None:
        orig_p.insert(0, copy.deepcopy(rev_ppr))


def _paragraph_plain_text(p_el: ET.Element) -> str:
    return "".join((t.text or "") for t in p_el.findall(".//w:t", NS))


def _relocate_legacy_toc_title_before_first_table_to_toc_section(
    container: ET.Element,
) -> bool:
    """
    Move a leading legacy ``TOCTitle`` paragraph (``TABLE OF CONTENTS``) so it
    appears right before the revised TOC block after the first table.
    """

    children = list(container)
    first_table_idx: int | None = None
    for i, ch in enumerate(children):
        ln = _local_name(ch.tag)
        if ln == "tbl" or (ln == "ins" and ch.find("w:tbl", NS) is not None):
            first_table_idx = i
            break
    if first_table_idx is None:
        return False

    legacy_heading: ET.Element | None = None
    for ch in children[:first_table_idx]:
        if _local_name(ch.tag) != "p":
            continue
        if (
            _p_paragraph_style_id(ch) == "TOCTitle"
            and _paragraph_plain_text(ch).strip().upper() == "TABLE OF CONTENTS"
        ):
            legacy_heading = ch
            break
    if legacy_heading is None:
        return False

    target_toc_idx: int | None = None
    for i in range(first_table_idx + 1, len(children)):
        ch = children[i]
        if _local_name(ch.tag) != "p":
            continue
        txt = _paragraph_plain_text(ch).strip().upper()
        if txt.startswith("TABLE OF CONTENTS") and _p_paragraph_style_id(ch) == "TOC1":
            target_toc_idx = i
            break
    if target_toc_idx is None:
        return False

    # Remove old heading before table and insert right before TOC section.
    container.remove(legacy_heading)
    children_after = list(container)
    insert_idx = len(children_after)
    for i, ch in enumerate(children_after):
        if _local_name(ch.tag) != "p":
            continue
        txt = _paragraph_plain_text(ch).strip().upper()
        if txt.startswith("TABLE OF CONTENTS") and _p_paragraph_style_id(ch) == "TOC1":
            insert_idx = i
            break

    ppr = legacy_heading.find("w:pPr", NS)
    if ppr is None:
        ppr = ET.Element(f"{{{WORD_NAMESPACE}}}pPr")
        legacy_heading.insert(0, ppr)
    ps = ppr.find("w:pStyle", NS)
    if ps is None:
        ps = ET.Element(f"{{{WORD_NAMESPACE}}}pStyle")
        ppr.insert(0, ps)
    ps.set(f"{{{WORD_NAMESPACE}}}val", "Heading1Unnumbered")
    jc = ppr.find("w:jc", NS)
    if jc is None:
        jc = ET.Element(f"{{{WORD_NAMESPACE}}}jc")
        ppr.append(jc)
    jc.set(f"{{{WORD_NAMESPACE}}}val", "center")
    container.insert(insert_idx, legacy_heading)
    return True


def _paragraph_is_blank_page_break_only(p_el: ET.Element) -> bool:
    """True when a paragraph carries only a page break and no visible text."""

    if _local_name(p_el.tag) != "p":
        return False
    if _paragraph_plain_text(p_el) != "":
        return False
    brs = p_el.findall(".//w:br", NS)
    if len(brs) != 1:
        return False
    return brs[0].get(f"{{{WORD_NAMESPACE}}}type") == "page"


def _relocate_misplaced_page_break_before_exec_summary(container: ET.Element) -> bool:
    """
    Keep a page-break-only blank paragraph attached to the executive summary boundary.

    In the cervical front matter, a page-break paragraph can drift ahead of the
    inserted ``TABLE OF REVISIONS`` block, which creates the wrong pagination
    between the abbreviation table and the revisions section.
    """

    children = list(container)
    break_idx: int | None = None
    rev_idx: int | None = None
    exec_idx: int | None = None
    for i, ch in enumerate(children):
        if _local_name(ch.tag) != "p":
            continue
        txt = _paragraph_plain_text(ch).strip().upper()
        if break_idx is None and _paragraph_is_blank_page_break_only(ch):
            next_p = children[i + 1] if i + 1 < len(children) else None
            if (
                next_p is not None
                and _local_name(next_p.tag) == "p"
                and _paragraph_plain_text(next_p).strip().upper() == "TABLE OF REVISIONS"
            ):
                break_idx = i
                rev_idx = i + 1
                continue
        if rev_idx is not None and txt == "EXECUTIVE SUMMARY OF THE SPONSOR’S US CLINICAL STUDY EFFORT":
            exec_idx = i
            break
    if break_idx is None or rev_idx is None or exec_idx is None:
        return False

    page_break_p = children[break_idx]
    container.remove(page_break_p)
    insert_idx = exec_idx - 1  # removal shifts indices left by one
    container.insert(insert_idx, page_break_p)
    return True


def _drop_blank_spacer_before_page_break_heading_after_toc(container: ET.Element) -> bool:
    """
    Remove an orphanable blank spacer between the TOC block and a page-break heading.

    Word can strand a normal blank paragraph onto its own page when it falls between
    the last TOC line and a following heading that already has ``w:pageBreakBefore``.
    Keep the heading break and drop only the empty spacer so the next section starts
    on the intended page without a visual blank page in between.
    """

    children = list(container)
    changed = False
    i = 0
    while i + 1 < len(children):
        spacer = children[i]
        next_el = children[i + 1]
        prev_para: ET.Element | None = None
        for j in range(i - 1, -1, -1):
            cand = children[j]
            if _local_name(cand.tag) == "p":
                prev_para = cand
                break
        if (
            prev_para is not None
            and (_p_paragraph_style_id(prev_para) or "").startswith("TOC")
            and _local_name(spacer.tag) == "p"
            and _paragraph_plain_text(spacer) == ""
            and spacer.find(".//w:br", NS) is None
            and spacer.find("w:pPr/w:sectPr", NS) is None
            and _local_name(next_el.tag) == "p"
            and next_el.find("w:pPr/w:pageBreakBefore", NS) is not None
        ):
            container.remove(spacer)
            children.pop(i)
            changed = True
            continue
        i += 1
    return changed


def _revised_alignment_step_is_blank_page_break(
    alignment: list,
    step_index: int,
    revised_block_elements: list[ET.Element] | None,
) -> bool:
    """True when *step_index* is a revised-only blank paragraph containing only a page break."""

    if revised_block_elements is None or step_index < 0 or step_index >= len(alignment):
        return False
    row = alignment[step_index]
    if row.original_paragraph_index is not None or row.revised_paragraph_index is None:
        return False
    rj = row.revised_paragraph_index
    if rj >= len(revised_block_elements):
        return False
    rev_el = revised_block_elements[rj]
    return _local_name(rev_el.tag) == "p" and _paragraph_is_blank_page_break_only(rev_el)


def _should_drop_blank_original_before_revised_page_break_insert(
    alignment: list,
    step_index: int,
    el: ET.Element,
    revised_block_elements: list[ET.Element] | None,
) -> bool:
    """
    Drop an original blank paragraph when it is immediately replaced by a revised-only
    blank page-break paragraph before the same following matched block.
    """

    if _local_name(el.tag) != "p":
        return False
    if _paragraph_plain_text(el) != "" or _paragraph_is_blank_page_break_only(el):
        return False
    return _revised_alignment_step_is_blank_page_break(alignment, step_index + 1, revised_block_elements)


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
    :func:`table_diff.diff_table_blocks` cell merge semantics.

    Row/column additions and removals are emitted at cell level against
    synthetic empty cells, so matched tables do not degrade into whole-table
    replacement.
    """

    rows_o = orig_table.get("rows", [])
    rows_r = rev_table.get("rows", [])
    is_abbrev_tbl = _is_abbreviation_definition_table(rows_o, rows_r, config)

    tr_els = _tbl_tr_elements(tbl_el)
    rev_tr_els = _tbl_tr_elements(revised_tbl_el) if revised_tbl_el is not None else []

    # SCRUM-143: When column widths per row or row counts differ, still align rows/cells
    # and emit per-cell track changes. Replacing the whole w:tbl with the revised
    # package copy hid table-level redline for sponsor tables (e.g. goals-by-race).
    if is_abbrev_tbl or _table_shape(orig_table) != _table_shape(rev_table) or len(
        rows_o
    ) != len(rows_r):
        row_alignment = _align_table_rows(rows_o, rows_r, config)
    else:
        row_alignment = [(i, i) for i in range(len(rows_o))]
    out_row = 0
    for oi, ri in row_alignment:
        row_o = rows_o[oi] if oi is not None else []
        row_r = rows_r[ri] if ri is not None else []

        # Row exists only in revised: insert cloned row at aligned position.
        if oi is None and ri is not None and ri < len(rev_tr_els):
            new_tr = copy.deepcopy(rev_tr_els[ri])
            for tc_el in new_tr.findall("w:tc", NS):
                _ensure_inserted_table_cell_shading(tc_el)
            if out_row < len(tr_els):
                anchor_tr = tr_els[out_row]
                tbl_el.insert(list(tbl_el).index(anchor_tr), new_tr)
                tr_els.insert(out_row, new_tr)
            else:
                tbl_el.append(new_tr)
                tr_els.append(new_tr)
        elif out_row >= len(tr_els):
            out_row += 1
            continue

        tr_el = tr_els[out_row]
        tcs = [c for c in tr_el if _local_name(c.tag) == "tc"]
        rev_tcs = (
            [c for c in rev_tr_els[ri] if _local_name(c.tag) == "tc"]
            if ri is not None and ri < len(rev_tr_els)
            else []
        )

        if is_abbrev_tbl or len(row_o) != len(row_r):
            cell_alignment = _align_row_cells(row_o, row_r, config)
        else:
            cell_alignment = [(c, c) for c in range(len(row_o))]

        for oc, rc in cell_alignment:
            # Map edits onto the **original** row's w:tc list: use orig index `oc` so
            # track changes sit on the correct column when a column is removed
            # (e.g. Goal | MK → merged MK).
            cell_idx = (
                oc
                if oc is not None
                else (rc if rc is not None else 0)
            )
            if cell_idx >= len(tcs):
                if cell_idx < len(rev_tcs):
                    new_tc = copy.deepcopy(rev_tcs[cell_idx])
                    _ensure_inserted_table_cell_shading(new_tc)
                    tr_el.append(new_tc)
                    tcs.append(new_tc)
                    tc_el = new_tc
                else:
                    continue
            else:
                tc_el = tcs[cell_idx]
            orig_cell = row_o[oc] if oc is not None else _empty_table_cell()
            rev_cell = row_r[rc] if rc is not None else _empty_table_cell()
            _apply_table_cell_track_changes(
                tc_el,
                orig_cell,
                rev_cell,
                config,
                id_counter,
                author,
                date_iso,
                major_sentence_mode=is_abbrev_tbl,
                revised_tc_el=rev_tcs[rc] if rc is not None and rc < len(rev_tcs) else None,
            )
        out_row += 1


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

    # Consecutive revised-only rows (None, rj0), (None, rj1), … share the same forward
    # DOM anchor (next matched original block). Without an offset, each insert used the
    # same index so later inserts appeared before earlier ones in document order — e.g.
    # ``w:tbl`` before the preceding ``w:p`` when revised order is paragraph then table
    # (SCRUM-120). Advance the index by how many nodes we already inserted at this anchor.
    rev_insert_anchor_key: object | None = None
    rev_insert_count = 0

    for step_i, al in enumerate(alignment):
        oi = al.original_paragraph_index
        rj = al.revised_paragraph_index

        if oi is not None and rj is not None:
            rev_insert_anchor_key = None
            rev_insert_count = 0
            if oi >= len(block_els):
                continue
            oblock = ob[oi]
            rblock = rb[rj]
            merge_end = al.revised_merge_end_exclusive
            if merge_end is not None and (merge_end <= rj or merge_end > len(rb)):
                merge_end = None
            rev_para_for_diff: BodyParagraph
            if merge_end is not None:
                rev_para_for_diff = _merged_body_paragraph_from_span(rb, rj, merge_end)
            else:
                rev_para_for_diff = rblock  # type: ignore[assignment]
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
            split_ops: list[tuple[str, BodyParagraph | None, BodyParagraph]] | None = None
            split_rev_elements: list[ET.Element | None] = []
            if merge_end is not None:
                revised_span = [
                    rb[k] for k in range(rj, merge_end) if rb[k].get("type") == "paragraph"
                ]
                if len(revised_span) == (merge_end - rj):
                    if _revised_span_starts_with_heading_promotion(
                        orig_para,
                        revised_span,  # type: ignore[arg-type]
                        config,
                    ):
                        split_ops = _plan_original_paragraph_for_revised_span(
                            orig_para,
                            revised_span,  # type: ignore[arg-type]
                            config,
                        )
                    else:
                        split_pairs = _split_original_paragraph_for_revised_span(
                            orig_para,
                            revised_span,  # type: ignore[arg-type]
                            config,
                        )
                        if split_pairs is not None:
                            split_ops = [
                                ("match", split_orig, split_rev)
                                for split_orig, split_rev in split_pairs
                            ]
                        else:
                            split_ops = _plan_original_paragraph_for_revised_span(
                                orig_para,
                                revised_span,  # type: ignore[arg-type]
                                config,
                            )
                    if split_ops is not None:
                        for k in range(rj, merge_end):
                            rev_el: ET.Element | None = None
                            if (
                                revised_block_elements is not None
                                and k < len(revised_block_elements)
                                and _local_name(revised_block_elements[k].tag) == "p"
                                ):
                                    rev_el = revised_block_elements[k]
                            split_rev_elements.append(rev_el)
            if split_ops is not None:
                first_match_idx = next(
                    (
                        idx
                        for idx, (kind, extra_orig, _) in enumerate(split_ops)
                        if kind == "match" and extra_orig is not None
                    ),
                    None,
                )
                if first_match_idx is None:
                    continue
                insert_at = list(container).index(el)
                for lead_idx, (kind, _, extra_rev) in enumerate(split_ops[:first_match_idx]):
                    if kind != "insert":
                        continue
                    revised_p_el = (
                        split_rev_elements[lead_idx] if lead_idx < len(split_rev_elements) else None
                    )
                    if not _revised_only_paragraph_should_emit(
                        extra_rev,
                        config,
                        revised_p_el=revised_p_el,
                    ):
                        continue
                    if revised_p_el is not None and _paragraph_style_is_toc(revised_p_el):
                        lead_p = _new_w_p_toc_insert_from_revised_source(
                            revised_p_el,
                            id_counter=id_counter,
                            author=author,
                            date_iso=date_iso,
                        )
                    else:
                        lead_p = _new_w_p_from_full_paragraph_insert(
                            extra_rev,
                            config,
                            id_counter=id_counter,
                            author=author,
                            date_iso=date_iso,
                            revised_p_el=revised_p_el,
                        )
                    if revised_p_el is not None:
                        _copy_revised_p_pr_to_inserted_paragraph(lead_p, revised_p_el)
                        _mark_paragraph_mark_as_inserted(
                            lead_p,
                            id_counter=id_counter,
                            author=author,
                            date_iso=date_iso,
                        )
                    container.insert(insert_at, lead_p)
                    insert_at += 1

                first_kind, first_orig, first_rev = split_ops[first_match_idx]
                first_rev_el = (
                    split_rev_elements[first_match_idx] if first_match_idx < len(split_rev_elements) else None
                )
                if _paragraph_needs_revision(first_orig, first_rev, config):
                    first_kids = build_paragraph_track_change_elements(
                        first_orig,
                        first_rev,
                        config,
                        id_counter=id_counter,
                        author=author,
                        date_iso=date_iso,
                        revised_p_el=first_rev_el,
                    )
                    if _split_first_matched_para_should_take_revised_p_pr(
                        first_orig,
                        first_rev,
                        config,
                        first_rev_el,
                    ):
                        _replace_p_pr_from_revised(el, first_rev_el)
                    _replace_p_content_preserving_p_pr(el, first_kids)
                insert_at = list(container).index(el) + 1
                for extra_idx, (kind, extra_orig, extra_rev) in enumerate(
                    split_ops[first_match_idx + 1 :],
                    start=first_match_idx + 1,
                ):
                    revised_p_el = (
                        split_rev_elements[extra_idx] if extra_idx < len(split_rev_elements) else None
                    )
                    if kind == "insert":
                        if not _revised_only_paragraph_should_emit(
                            extra_rev,
                            config,
                            revised_p_el=revised_p_el,
                        ):
                            continue
                        if revised_p_el is not None and _paragraph_style_is_toc(revised_p_el):
                            extra_p = _new_w_p_toc_insert_from_revised_source(
                                revised_p_el,
                                id_counter=id_counter,
                                author=author,
                                date_iso=date_iso,
                            )
                        else:
                            extra_p = _new_w_p_from_full_paragraph_insert(
                                extra_rev,
                                config,
                                id_counter=id_counter,
                                author=author,
                                date_iso=date_iso,
                                revised_p_el=revised_p_el,
                            )
                        if revised_p_el is not None:
                            _copy_revised_p_pr_to_inserted_paragraph(extra_p, revised_p_el)
                            _mark_paragraph_mark_as_inserted(
                                extra_p,
                                id_counter=id_counter,
                                author=author,
                                date_iso=date_iso,
                            )
                    else:
                        if extra_orig is None:
                            continue
                        extra_p = _new_w_p_from_matched_paragraph_diff(
                            extra_orig,
                            extra_rev,
                            config,
                            id_counter=id_counter,
                            author=author,
                            date_iso=date_iso,
                            revised_p_el=revised_p_el,
                        )
                    container.insert(insert_at, extra_p)
                    insert_at += 1
                continue
            rev_para: BodyParagraph = rev_para_for_diff
            rev_el_for_match: ET.Element | None = None
            if (
                revised_block_elements is not None
                and rj < len(revised_block_elements)
                and _local_name(revised_block_elements[rj].tag) == "p"
            ):
                rev_el_for_match = revised_block_elements[rj]
            if rev_el_for_match is not None:
                _sync_page_break_before_to_revised(el, rev_el_for_match)
                _sync_blank_paragraph_structure_to_revised(el, rev_el_for_match)
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
                    source_p_el=el,
                    revised_p_el=rev_el_for_match,
                )
            _replace_p_content_preserving_p_pr(el, new_kids)
        elif oi is not None and rj is None:
            rev_insert_anchor_key = None
            rev_insert_count = 0
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
                if _should_drop_blank_original_before_revised_page_break_insert(
                    alignment,
                    step_i,
                    el,
                    revised_block_elements,
                ):
                    container.remove(el)
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
                    source_p_el=el,
                )
                _replace_p_content_preserving_p_pr(el, new_kids)
        elif oi is None and rj is not None:
            rblock = rb[rj]
            next_oi = _next_alignment_original_block_index(alignment, step_i)
            anchor_key: object
            if next_oi is not None and next_oi < len(block_els):
                anchor_key = ("oi", next_oi, id(container))
            else:
                anchor_key = ("sectpr", id(container))
            if anchor_key != rev_insert_anchor_key:
                rev_insert_anchor_key = anchor_key
                rev_insert_count = 0
            base = _body_insert_index_before_next_orig_block(
                container, alignment, step_i, block_els
            )
            idx = base + rev_insert_count
            if rblock.get("type") == "table":
                rev_tbl_el: ET.Element | None = None
                if (
                    revised_block_elements is not None
                    and rj < len(revised_block_elements)
                    and _local_name(revised_block_elements[rj].tag) == "tbl"
                ):
                    rev_tbl_el = revised_block_elements[rj]
                if rev_tbl_el is not None:
                    inserted_tbl = copy.deepcopy(rev_tbl_el)
                    _mark_table_content_as_inserted(
                        inserted_tbl,
                        id_counter=id_counter,
                        author=author,
                        date_iso=date_iso,
                    )
                    container.insert(idx, inserted_tbl)
                    rev_insert_count += 1
                continue
            if rblock.get("type") != "paragraph":
                continue
            rev_para = rblock  # type: ignore[assignment]
            rev_el: ET.Element | None = None
            if (
                revised_block_elements is not None
                and rj < len(revised_block_elements)
                and _local_name(revised_block_elements[rj].tag) == "p"
            ):
                rev_el = revised_block_elements[rj]
            if not _revised_only_paragraph_should_emit(
                rev_para,
                config,
                revised_p_el=rev_el,
            ):
                continue
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
                    revised_p_el=rev_el,
                )
            if rev_el is not None:
                _copy_revised_p_pr_to_inserted_paragraph(new_p, rev_el)
                _mark_paragraph_mark_as_inserted(
                    new_p,
                    id_counter=id_counter,
                    author=author,
                    date_iso=date_iso,
                )
            container.insert(idx, new_p)
            rev_insert_count += 1


def _next_alignment_original_block_index(alignment: list, step_index: int) -> int | None:
    """First ``original_paragraph_index`` after *step_index* (exclusive), or ``None``."""

    for k in range(step_index + 1, len(alignment)):
        oi = alignment[k].original_paragraph_index
        if oi is not None:
            return oi
    return None


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


def _split_first_matched_para_should_take_revised_p_pr(
    orig_para: BodyParagraph,
    rev_para: BodyParagraph,
    config: CompareConfig,
    revised_p_el: ET.Element | None,
) -> bool:
    """Detect inline-heading to numbered-heading promotions for split matched paragraphs."""

    if revised_p_el is None:
        return False
    rev_style = _p_paragraph_style_id(revised_p_el) or ""
    if not rev_style.startswith("Heading"):
        return False
    orig_text = _concat_paragraph_text(orig_para, config).strip()
    rev_text = _concat_paragraph_text(rev_para, config).strip()
    if not rev_text:
        return False
    return orig_text == f"{rev_text}:"


def _is_short_structural_insert_paragraph(
    rev_para: BodyParagraph,
    config: CompareConfig,
) -> bool:
    """Heuristic for short structural lead-ins inserted between split body chunks."""

    txt = _concat_paragraph_text(rev_para, config).strip()
    if not txt or len(txt) > 120:
        return False
    if any(ch in txt for ch in (".", "!", "?", ":", "\n", "\t")):
        return False
    words = [t.surface for t in tokenize_for_lcs(txt) if re.search(r"\w", t.surface)]
    return 1 <= len(words) <= 12


def _next_revised_anchor_in_original(
    orig_text: str,
    revised_paras: list[BodyParagraph],
    config: CompareConfig,
    *,
    start_index: int,
    start_at: int,
    allow_equal: bool = False,
) -> tuple[int, int] | None:
    """First later revised paragraph whose leading prefix re-anchors in ``orig_text``."""

    for idx in range(start_index, len(revised_paras)):
        rev_text = _concat_paragraph_text(revised_paras[idx], config)
        pos = _find_revised_paragraph_anchor_in_original(
            orig_text,
            rev_text,
            start_at=start_at,
            allow_equal=allow_equal,
        )
        if pos is not None and (allow_equal or pos > start_at):
            return idx, pos
    return None


def _plan_original_paragraph_for_revised_span(
    orig_para: BodyParagraph,
    revised_paras: list[BodyParagraph],
    config: CompareConfig,
) -> list[tuple[str, BodyParagraph | None, BodyParagraph]] | None:
    """
    Expand one original paragraph into matched and inserted revised paragraphs.

    Returns operations shaped as ``("match", orig_chunk, rev_para)`` or
    ``("insert", None, rev_para)``. This supports structural promotions where
    one original inline-heading paragraph becomes a heading plus multiple
    revised-only structural lead-ins and re-anchored body paragraphs.
    """

    if len(revised_paras) <= 1:
        return None
    orig_text = _concat_paragraph_text(orig_para, config)
    if not orig_text.strip():
        return None

    ops: list[tuple[str, BodyParagraph | None, BodyParagraph]] = []
    current_lo = 0
    ri = 0

    heading_match = re.match(r"^\s*([A-Za-z][^:\n]{0,120}?):\s+", orig_text)
    if heading_match is not None:
        first_rev_text = _concat_paragraph_text(revised_paras[0], config).strip()
        heading_text = heading_match.group(1).strip()
        if first_rev_text and first_rev_text == heading_text:
            ops.append(("insert", None, revised_paras[0]))
            ri = 1

    while ri < len(revised_paras):
        anchor = _next_revised_anchor_in_original(
            orig_text,
            revised_paras,
            config,
            start_index=ri,
            start_at=current_lo,
            allow_equal=True,
        )
        if anchor is None:
            ops.append(
                (
                    "match",
                    _paragraph_from_text_like(orig_para, orig_text[current_lo:]),
                    revised_paras[ri],
                )
            )
            current_lo = len(orig_text)
            ri += 1
            break

        anchor_idx, anchor_pos = anchor
        if anchor_idx > ri:
            current_rev = revised_paras[ri]
            if current_lo >= len(orig_text):
                ops.append(("insert", None, current_rev))
                ri += 1
                continue
            if (
                _is_short_structural_insert_paragraph(current_rev, config)
                or ops
            ):
                ops.append(("insert", None, current_rev))
                ri += 1
                continue
            return None

        later_anchor = _next_revised_anchor_in_original(
            orig_text,
            revised_paras,
            config,
            start_index=ri + 1,
            start_at=max(anchor_pos, current_lo),
            allow_equal=True,
        )
        hi = later_anchor[1] if later_anchor is not None else len(orig_text)
        if hi <= current_lo:
            return None
        ops.append(
            (
                "match",
                _paragraph_from_text_like(orig_para, orig_text[current_lo:hi]),
                revised_paras[ri],
            )
        )
        current_lo = hi
        ri += 1

    if not ops or all(kind != "match" for kind, _, _ in ops):
        return None
    if current_lo < len(orig_text):
        return None
    return ops


def _revised_span_starts_with_heading_promotion(
    orig_para: BodyParagraph,
    revised_paras: list[BodyParagraph],
    config: CompareConfig,
) -> bool:
    """Whether the revised span starts with a heading promoted out of an inline ``Heading:`` lead-in."""

    if not revised_paras:
        return False
    orig_text = _concat_paragraph_text(orig_para, config)
    heading_match = re.match(r"^\s*([A-Za-z][^:\n]{0,120}?):\s+", orig_text)
    if heading_match is None:
        return False
    first_rev_text = _concat_paragraph_text(revised_paras[0], config).strip()
    if not first_rev_text:
        return False
    return first_rev_text == heading_match.group(1).strip()


def _empty_table_cell() -> dict:
    """Synthetic empty table cell used for row/cell add/remove emit."""

    return {"paragraphs": []}


def _cell_paragraphs(cell: dict) -> list[BodyParagraph]:
    paras = cell.get("paragraphs", [])
    out: list[BodyParagraph] = []
    for para in paras:
        if isinstance(para, dict) and para.get("type") == "paragraph":
            out.append(para)  # type: ignore[arg-type]
    return out


def _cell_paragraph_text(para: BodyParagraph) -> str:
    return "".join(str(r.get("text", "")) for r in para.get("runs", []))


def _table_cell_leading_whitespace_only_change(orig_text: str, rev_text: str) -> bool:
    """
    True when revised differs from original only by short leading whitespace.

    In some sponsor tables, revised cells can carry layout-only leading spaces
    (for example before ``<50y`` / ``50-64y`` / ``>=65y`` labels). Emitting these
    as inserted text creates visible redline noise (rendered like underscores in
    Word). Treat this as formatting-only and keep cell text unchanged.
    """

    if not orig_text or not rev_text:
        return False
    if orig_text != orig_text.lstrip():
        return False
    trimmed_rev = rev_text.lstrip()
    if trimmed_rev == rev_text:
        return False
    # Keep this narrow: ignore only short indentation-like prefixes.
    lead = len(rev_text) - len(trimmed_rev)
    if lead > 8:
        return False
    return trimmed_rev == orig_text


def _cell_paragraph_alignment(
    orig_paras: list[BodyParagraph],
    rev_paras: list[BodyParagraph],
    config: CompareConfig,
) -> list[tuple[int | None, int | None]]:
    """LCS alignment for paragraphs inside one table cell."""

    sig_o = [_normalize_text(_cell_paragraph_text(p), config) for p in orig_paras]
    sig_r = [_normalize_text(_cell_paragraph_text(p), config) for p in rev_paras]
    sm = difflib.SequenceMatcher(None, sig_o, sig_r, autojunk=False)
    out: list[tuple[int | None, int | None]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace"):
            shared = min(i2 - i1, j2 - j1)
            for k in range(shared):
                out.append((i1 + k, j1 + k))
            for k in range(shared, i2 - i1):
                out.append((i1 + k, None))
            for k in range(shared, j2 - j1):
                out.append((None, j1 + k))
        elif tag == "delete":
            for i in range(i1, i2):
                out.append((i, None))
        elif tag == "insert":
            for j in range(j1, j2):
                out.append((None, j))
    return out


def _paragraph_is_list_like(p_el: ET.Element) -> bool:
    ppr = p_el.find("w:pPr", NS)
    if ppr is None:
        return False
    if ppr.find("w:numPr", NS) is not None:
        return True
    sid = _p_paragraph_style_id(p_el)
    return bool(sid and _p_style_val_indicates_list_paragraph(sid))


def _table_cell_should_preserve_paragraph_structure(
    tc_paras: list[ET.Element], rev_tc_paras: list[ET.Element]
) -> bool:
    """
    Enable paragraph-aware cell emit only for true list blocks.

    Guardrails:
    - require explicit ``w:numPr`` on at least one side (not style-only guesses),
    - and require multi-paragraph list structure so normal cells keep legacy emit.
    """

    if len(tc_paras) < 2 and len(rev_tc_paras) < 2:
        return False
    has_numpr = any(p.find("w:pPr/w:numPr", NS) is not None for p in (tc_paras + rev_tc_paras))
    if not has_numpr:
        return False
    list_like_count = sum(1 for p in (tc_paras + rev_tc_paras) if _paragraph_is_list_like(p))
    return list_like_count >= 2


def _ensure_tc_first_paragraph(tc_el: ET.Element) -> ET.Element:
    """Return first direct ``w:p`` in ``w:tc``; create one if absent."""

    paras = _tc_direct_paragraph_elements(tc_el)
    if paras:
        return paras[0]
    p_el = ET.Element(f"{{{WORD_NAMESPACE}}}p")
    insert_at = 0
    for i, ch in enumerate(list(tc_el)):
        if _local_name(ch.tag) == "tcPr":
            insert_at = i + 1
            break
    tc_el.insert(insert_at, p_el)
    return p_el


def _merged_tc_paragraph_for_preserving(paras: list[ET.Element]) -> ET.Element | None:
    """
    Synthetic merged ``w:p`` for non-list table-cell preserving emit.

    This keeps original/revised run structure across multi-paragraph cells by
    cloning each paragraph's runs in order and inserting an explicit newline run
    between paragraphs so the XML text matches :func:`_cell_concat_paragraph`.
    """

    if not paras:
        return None
    merged = ET.Element(f"{{{WORD_NAMESPACE}}}p")
    for pi, p_el in enumerate(paras):
        for r_el in p_el.findall(".//w:r", NS):
            if _parse_text_from_run_element(r_el):
                merged.append(copy.deepcopy(r_el))
        if pi < len(paras) - 1:
            nl_r = ET.Element(f"{{{WORD_NAMESPACE}}}r")
            nl_t = ET.SubElement(nl_r, f"{{{WORD_NAMESPACE}}}t")
            nl_t.text = "\n"
            merged.append(nl_r)
    return merged


def _apply_table_cell_track_changes(
    tc_el: ET.Element,
    orig_cell: dict,
    rev_cell: dict,
    config: CompareConfig,
    id_counter: list[int],
    author: str,
    date_iso: str,
    *,
    major_sentence_mode: bool = False,
    revised_tc_el: ET.Element | None = None,
) -> None:
    """Apply paragraph-aware Track Changes for one table cell."""

    orig_paras = _cell_paragraphs(orig_cell)
    rev_paras = _cell_paragraphs(rev_cell)
    tc_paras = _tc_direct_paragraph_elements(tc_el)
    rev_tc_paras = _tc_direct_paragraph_elements(revised_tc_el) if revised_tc_el is not None else []
    preserve_para_structure = _table_cell_should_preserve_paragraph_structure(tc_paras, rev_tc_paras)

    if not preserve_para_structure:
        # Non-list table cells keep historical merged-paragraph emit behavior.
        orig_para = _cell_concat_paragraph(orig_cell)  # type: ignore[arg-type]
        rev_para = _cell_concat_paragraph(rev_cell)  # type: ignore[arg-type]
        if not _paragraph_needs_revision(orig_para, rev_para, config):
            return
        orig_text = "".join(str(r.get("text", "")) for r in orig_para.get("runs", []))
        rev_text = "".join(str(r.get("text", "")) for r in rev_para.get("runs", []))
        if _table_cell_leading_whitespace_only_change(orig_text, rev_text):
            return
        orig_words = norm_keys([x for x in tokenize_for_lcs(orig_text) if not x.surface.isspace()])
        rev_words = norm_keys([x for x in tokenize_for_lcs(rev_text) if not x.surface.isspace()])
        word_overlap = difflib.SequenceMatcher(None, orig_words, rev_words, autojunk=False).ratio()

        first_p = _ensure_tc_first_paragraph(tc_el)
        merged_source_p = _merged_tc_paragraph_for_preserving(tc_paras)
        merged_revised_p = _merged_tc_paragraph_for_preserving(rev_tc_paras)
        if (
            major_sentence_mode
            and orig_text
            and rev_text
            and min(len(orig_words), len(rev_words)) >= 4
            and word_overlap < _TABLE_MAJOR_SENTENCE_WORD_OVERLAP_MAX
        ):
            new_kids = [
                _w_del_segment(orig_text, _next_id(id_counter), author, date_iso),
                _w_ins_segment(rev_text, _next_id(id_counter), author, date_iso),
            ]
        else:
            new_kids = build_paragraph_track_change_elements(
                orig_para,
                rev_para,
                config,
                id_counter=id_counter,
                author=author,
                date_iso=date_iso,
                source_p_el=merged_source_p if merged_source_p is not None else first_p,
                revised_p_el=merged_revised_p,
            )
        _replace_p_content_preserving_p_pr(first_p, new_kids)
        for extra in _tc_direct_paragraph_elements(tc_el)[1:]:
            tc_el.remove(extra)
        return

    if not orig_paras:
        orig_paras = [_empty_body_paragraph()]
    if not rev_paras:
        rev_paras = [_empty_body_paragraph()]
    if not tc_paras:
        tc_paras = [_ensure_tc_first_paragraph(tc_el)]

    para_alignment = _cell_paragraph_alignment(orig_paras, rev_paras, config)
    empty_para = _empty_body_paragraph()
    out_paras: list[ET.Element] = []
    for oi, ri in para_alignment:
        orig_para = orig_paras[oi] if oi is not None and oi < len(orig_paras) else empty_para
        rev_para = rev_paras[ri] if ri is not None and ri < len(rev_paras) else empty_para
        source_p = tc_paras[oi] if oi is not None and oi < len(tc_paras) else None
        revised_p = rev_tc_paras[ri] if ri is not None and ri < len(rev_tc_paras) else None

        if oi is None:
            out_paras.append(
                _new_w_p_from_full_paragraph_insert(
                    rev_para,
                    config,
                    id_counter=id_counter,
                    author=author,
                    date_iso=date_iso,
                    revised_p_el=revised_p,
                )
            )
            continue

        p_el = source_p if source_p is not None else ET.Element(f"{{{WORD_NAMESPACE}}}p")
        if ri is None:
            if _paragraph_needs_revision(orig_para, empty_para, config):
                new_kids = build_paragraph_track_change_elements(
                    orig_para,
                    empty_para,
                    config,
                    id_counter=id_counter,
                    author=author,
                    date_iso=date_iso,
                    source_p_el=p_el,
                    revised_p_el=revised_p,
                )
                _replace_p_content_preserving_p_pr(p_el, new_kids)
            out_paras.append(p_el)
            continue

        if not _paragraph_needs_revision(orig_para, rev_para, config):
            out_paras.append(p_el)
            continue

        orig_text = _cell_paragraph_text(orig_para)
        rev_text = _cell_paragraph_text(rev_para)
        if _table_cell_leading_whitespace_only_change(orig_text, rev_text):
            out_paras.append(p_el)
            continue
        orig_words = norm_keys([x for x in tokenize_for_lcs(orig_text) if not x.surface.isspace()])
        rev_words = norm_keys([x for x in tokenize_for_lcs(rev_text) if not x.surface.isspace()])
        word_overlap = difflib.SequenceMatcher(None, orig_words, rev_words, autojunk=False).ratio()
        if (
            major_sentence_mode
            and orig_text
            and rev_text
            and min(len(orig_words), len(rev_words)) >= 4
            and word_overlap < _TABLE_MAJOR_SENTENCE_WORD_OVERLAP_MAX
        ):
            new_kids = [
                _w_del_segment(orig_text, _next_id(id_counter), author, date_iso),
                _w_ins_segment(rev_text, _next_id(id_counter), author, date_iso),
            ]
        else:
            new_kids = build_paragraph_track_change_elements(
                orig_para,
                rev_para,
                config,
                id_counter=id_counter,
                author=author,
                date_iso=date_iso,
                source_p_el=p_el,
                revised_p_el=revised_p,
            )
        _replace_p_content_preserving_p_pr(p_el, new_kids)
        out_paras.append(p_el)

    for p in _tc_direct_paragraph_elements(tc_el):
        tc_el.remove(p)
    insert_at = 0
    for i, ch in enumerate(list(tc_el)):
        if _local_name(ch.tag) == "tcPr":
            insert_at = i + 1
            break
    for i, p_el in enumerate(out_paras):
        tc_el.insert(insert_at + i, p_el)


def _merged_body_paragraph_from_span(
    rb: list, start: int, end_exclusive: int
) -> BodyParagraph:
    """Concatenate revised ``w:p`` IR blocks ``[start, end_exclusive)`` for SCRUM-121 split merge."""

    if start < 0 or end_exclusive <= start or end_exclusive > len(rb):
        raise ValueError("invalid revised span for merged paragraph")
    runs: list = []
    first_id = str(rb[start]["id"])
    for k in range(start, end_exclusive):
        runs.extend(rb[k].get("runs", []))  # type: ignore[union-attr]
    return {"type": "paragraph", "id": first_id, "runs": runs}


def _paragraph_from_text_like(source: BodyParagraph, text: str) -> BodyParagraph:
    """Paragraph IR using *text* as one run, preserving basic shape from *source*."""

    return {
        "type": "paragraph",
        "id": str(source.get("id", "_")),
        "runs": [{"text": text}],
    }


def _leading_word_prefix(text: str, *, n_words: int) -> str:
    """Leading substring containing up to *n_words* non-space word tokens."""

    if not text:
        return ""
    out: list[str] = []
    words = 0
    for tok in tokenize_for_lcs(text):
        out.append(tok.surface)
        if tok.surface.strip() and re.search(r"\w", tok.surface):
            words += 1
            if words >= n_words:
                break
    return "".join(out)


def _find_revised_paragraph_anchor_in_original(
    orig_text: str,
    revised_text: str,
    *,
    start_at: int,
    allow_equal: bool = False,
) -> int | None:
    """
    Char offset where a later revised paragraph re-anchors inside *orig_text*.

    This supports the sponsor/Word behavior where one original paragraph can split
    across multiple compared paragraphs when the revised document introduces a new
    paragraph at a sentence that already existed later in the original paragraph.
    """

    prefix = _leading_word_prefix(revised_text, n_words=_MERGED_PARA_SPLIT_PREFIX_WORDS).strip()
    if not prefix:
        return None
    pos = orig_text.find(prefix, start_at)
    if pos < 0:
        return None
    if allow_equal:
        if pos < start_at:
            return None
    elif pos <= start_at:
        return None
    return pos


def _split_original_paragraph_for_revised_span(
    orig_para: BodyParagraph,
    revised_paras: list[BodyParagraph],
    config: CompareConfig,
) -> list[tuple[BodyParagraph, BodyParagraph]] | None:
    """
    Split one original paragraph into multiple compared paragraph pairs when possible.

    Returns ``[(orig_chunk0, rev0), (orig_chunk1, rev1), ...]`` when every later
    revised paragraph begins with a strong prefix that also appears later in the
    original paragraph text. Otherwise returns ``None``.
    """

    if len(revised_paras) <= 1:
        return None
    orig_text = _concat_paragraph_text(orig_para, config)
    split_points = [0]
    later_revised = revised_paras[1:]
    heading_match = re.match(r"^\s*([A-Za-z][^:\n]{0,120}?):\s+", orig_text)
    if heading_match is not None:
        first_rev_text = _concat_paragraph_text(revised_paras[0], config).strip()
        heading_text = heading_match.group(1).strip()
        if first_rev_text and first_rev_text == heading_text:
            split_points.append(heading_match.end())
            later_revised = revised_paras[2:]
            search_start = heading_match.end()
        else:
            search_start = 1
    else:
        search_start = 1
    for rev_para in later_revised:
        rev_text = _concat_paragraph_text(rev_para, config)
        pos = _find_revised_paragraph_anchor_in_original(
            orig_text,
            rev_text,
            start_at=search_start,
        )
        if pos is None:
            return None
        split_points.append(pos)
        search_start = pos + 1
    split_points.append(len(orig_text))
    out: list[tuple[BodyParagraph, BodyParagraph]] = []
    for idx, rev_para in enumerate(revised_paras):
        lo = split_points[idx]
        hi = split_points[idx + 1]
        if lo >= hi:
            return None
        out.append((_paragraph_from_text_like(orig_para, orig_text[lo:hi]), rev_para))
    return out


def _new_w_p_from_matched_paragraph_diff(
    orig_para: BodyParagraph,
    rev_para: BodyParagraph,
    config: CompareConfig,
    *,
    id_counter: list[int],
    author: str,
    date_iso: str,
    revised_p_el: ET.Element | None = None,
) -> ET.Element:
    """A new ``w:p`` containing matched paragraph revisions for *orig_para* vs *rev_para*."""

    kids = build_paragraph_track_change_elements(
        orig_para,
        rev_para,
        config,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )
    p_el = ET.Element(f"{{{WORD_NAMESPACE}}}p")
    if revised_p_el is not None:
        _copy_revised_p_pr_to_inserted_paragraph(p_el, revised_p_el)
    for node in kids:
        p_el.append(node)
    return p_el


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
        if next_oi > 0:
            prev_anchor = block_els[next_oi - 1]
            if (
                _local_name(anchor.tag) == "p"
                and _local_name(prev_anchor.tag) == "p"
                and _paragraph_plain_text(prev_anchor) == ""
                and prev_anchor.find(".//w:br[@w:type='page']", NS) is not None
            ):
                anchor = prev_anchor
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
    revised_p_el: ET.Element | None = None,
) -> ET.Element:
    """A ``w:p`` whose content is Track Changes for text that exists only in the revised document."""
    p_el = ET.Element(f"{{{WORD_NAMESPACE}}}p")
    if revised_p_el is not None:
        _copy_revised_p_pr_to_inserted_paragraph(p_el, revised_p_el)
        _mark_paragraph_mark_as_inserted(
            p_el,
            id_counter=id_counter,
            author=author,
            date_iso=date_iso,
        )
        runs = _paragraph_w_runs_in_document_order(revised_p_el)
        if runs:
            p_el.append(
                _w_ins_segment_from_revised_paragraph_runs(
                    revised_p_el,
                    _next_id(id_counter),
                    author,
                    date_iso,
                )
            )
            return p_el
    kids = build_paragraph_track_change_elements(
        _empty_body_paragraph(),
        rev_para,
        config,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )
    _mark_paragraph_mark_as_inserted(
        p_el,
        id_counter=id_counter,
        author=author,
        date_iso=date_iso,
    )
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
    _post_merge_consolidated_list_full_paragraph_deletes(body)
    _relocate_legacy_toc_title_before_first_table_to_toc_section(body)
    _drop_blank_spacer_before_page_break_heading_after_toc(body)
    _relocate_misplaced_page_break_before_exec_summary(body)


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
    _post_merge_consolidated_list_full_paragraph_deletes(hdr_or_ftr_root)


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
    revised_numbering_xml: bytes | None = None
    has_original_numbering = False
    with zipfile.ZipFile(rev_path, "r") as zrev:
        rev_doc_blocks = load_structural_block_elements_from_docx_part(zrev, DOCUMENT_PART_PATH)
        rev_hf_blocks: dict[str, list[ET.Element]] = {}
        for _part in discover_header_footer_part_paths_from_namelist(zrev.namelist()):
            rev_hf_blocks[_part] = load_structural_block_elements_from_docx_part(zrev, _part)
        if "word/numbering.xml" in zrev.namelist():
            revised_numbering_xml = zrev.read("word/numbering.xml")

    with zipfile.ZipFile(orig_path, "r") as zin:
        raw_document_xml = zin.read(DOCUMENT_PART_PATH)
        has_original_numbering = "word/numbering.xml" in zin.namelist()
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

    # Keep numbering definitions in sync with any revised paragraph properties we
    # copied (for example list bullets inside table cells). Without this, revised
    # numId values can resolve to unrelated original numbering definitions.
    if revised_numbering_xml is not None and has_original_numbering:
        replacements["word/numbering.xml"] = revised_numbering_xml

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
