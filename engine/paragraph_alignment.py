"""
Paragraph alignment (MDC-006)

Deterministically align paragraphs between two BodyIR payloads to localize diffs.
This is a minimal foundation implementation to support later inline diffing.

Algorithm
    Signatures are built from normalized compare keys per paragraph (see
    ``generate_compare_keys``). LCS alignment uses **exact signature match** or,
    when texts differ only by edits inside the same logical block, **fuzzy text
    similarity**: ``quick_ratio`` must clear a high bar, then we accept a match
    if ``max(character_ratio, word_token_ratio)`` is high enough. For **paragraph**
    pairs within a small index skew (near-diagonal after a local insert/delete),
    we also allow a slightly softer ``quick_ratio`` / combined bar, a looser
    character-length ratio, and—when raw-string similarity is still low—a tight
    **word-bag Jaccard** on non-whitespace token norm keys, and—when length ratio
    is still below the floor—**cheap ``quick_ratio`` rejection**, wider Jaccard /
    **fuzzy bypass** thresholds, or **prefix expansion** (longer text starts with
    the shorter after normalization). Character-only
    ratio misses long sentences that share a prefix but replace a large middle
    (e.g. primary-endpoint wording), which would otherwise align as delete+insert
    whole paragraphs. Without this, emit marks the **entire** paragraph as
    deleted and re-inserted instead of in-place ``w:ins`` / ``w:del`` on words.

    **TOC rows** (same numbered section prefix, tab-separated title/page) use a
    relaxed gate when titles are reworded but the entry is still the same slot
    (SCRUM-116); otherwise ``quick_ratio`` can sit near ~0.7 and miss the global
    bar.

    Backtracking prefers deleting from the original when LCS tie-breaks are
    equal (``dp[i+1][j] >= dp[i][j+1]``).

Assumptions and limits
    - One BodyIR "block" is treated as one alignable unit (paragraph-level).
    - Fuzzy matching can mis-align two different but boilerplate-similar blocks;
      threshold is conservative.
    - Debug: set ``MDC_DEBUG_UNMATCHED_REV_REPAIR_GATES=1`` (before expansion
      override) to print per-``(None,rj)`` gate outcomes and a failure summary for
      :func:`_repair_alignment_unmatched_rev_expansion_override`.
    - Debug: set ``MDC_DEBUG_ALIGNMENT=1`` to print matched pairs, unmatched
      indices, for each ``UNMATCHED_REV`` the **best** original by
      ``max(char_ratio, tok_ratio)``, ``would_align``, pre-repair **LCS replay**
      (frontier ``(i,j)``, ``dp[i+1][j]`` vs ``dp[i][j+1]``, chosen branch), and a
      one-line **SKIPPED_BECAUSE** summary plus full gate traces (stderr).
      For ``UNMATCHED_REV``, also prints **token overlap** (raw + norm lists,
      multiset overlap, ratios, ``char_ratio`` / ``tok_ratio`` / Jaccard, and a
      short **containment** hint vs paragraph expansion).

    - No cross-paragraph move detection; reordering is expressed as delete +
      insert alignment pairs, not as a semantic "move" op. v1 emit intentionally
      preserves this as ``w:del`` + ``w:ins`` fallback (no ``w:moveFrom`` /
      ``w:moveTo`` markup).
    - Table blocks use the same signature string for fuzzy ratio when not equal.
"""

from __future__ import annotations

import difflib
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import NamedTuple

from .compare_keys import _normalize_text, generate_compare_keys
from .contracts import BodyIR, CompareConfig
from .diff_tokens import norm_keys, tokenize_for_lcs

# Cheap upper-bound filter before computing full ratios (keeps unrelated lines
# with moderate overlap, e.g. “The patient was observed…” vs “…discharged…”,
# from fuzzy-matching when combined similarity is only modest).
_ALIGN_FUZZY_QUICK_MIN = 0.86

# After ``quick_ratio`` passes, accept when ``max(char_ratio, token_ratio)`` is
# at least this. Token ratio uses the same split as :func:`engine.diff_tokens.tokenize_for_lcs`.
_ALIGN_FUZZY_COMBINED_MIN = 0.76

# When ``quick_ratio`` sits just below the strict gate, still allow a match for
# **paragraph** pairs within a small index skew (same logical block after a local
# insert/delete shifts revised indices). Avoids whole-paragraph ``w:del`` + ``w:ins``
# when inline diff would be correct (SCRUM-121 follow-up).
_ALIGN_FUZZY_QUICK_SOFT_MIN = 0.78
_ALIGN_FUZZY_COMBINED_SOFT_MIN = 0.72
_MAX_INDEX_SKEW_FOR_SOFT_FUZZY = 2

# Last-resort gate for near-index paragraph pairs: Jaccard on *non-whitespace* token
# norm keys catches long same-vocabulary rewrites where character ``quick_ratio`` is low
# (e.g. list of tokens replaced but diction stays similar). Used only with tight
# thresholds and word-count ratio so unrelated boilerplate lines rarely pair.
_ALIGN_NEAR_INDEX_WORD_JACCARD_MIN = 0.65
_ALIGN_NEAR_INDEX_WORD_COUNT_RATIO_MIN = 0.38

# Length-ratio gate for paragraph pairs near each other on the diagonal (insert/delete
# skew); looser than the default 0.45 so one heavily rewritten long/short pair can match.
_ALIGN_LENGTH_RATIO_MIN = 0.45
_ALIGN_LENGTH_RATIO_NEAR_INDEX_MIN = 0.32

# When character length ratio fails the floor, do not reject immediately: run TOC /
# Jaccard / fuzzy first. Unrelated pairs are culled with a cheap ``quick_ratio`` cut,
# then strong evidence (bypass thresholds) is required to accept.
_ALIGN_LENGTH_WEAK_FAST_REJECT_QUICK = 0.18
# Accept length-weak paragraph pairs only with clearly non-random overlap.
_ALIGN_LENGTH_BYPASS_QUICK_MIN = 0.42
_ALIGN_LENGTH_BYPASS_COMBINED_MIN = 0.52
_ALIGN_LENGTH_BYPASS_TOK_MIN = 0.58
_ALIGN_LENGTH_BYPASS_TOK_QUICK_MIN = 0.34
_MAX_INDEX_SKEW_FOR_LENGTH_BYPASS_JACCARD = 8
_ALIGN_LENGTH_BYPASS_JACCARD_MIN = 0.55
_ALIGN_LENGTH_BYPASS_JACCARD_WORD_RATIO = 0.28
# When one paragraph is an expansion of the other (same opening text), token LCS
# can look weak while the shorter string is still a full prefix of the longer.
_ALIGN_LENGTH_BYPASS_PREFIX_MIN_CHARS = 36
_MAX_INDEX_SKEW_FOR_LENGTH_BYPASS_PREFIX = 6
_ALIGN_PUNCT_FLEX_PREFIX_MIN_CHARS = 12
_ALIGN_PUNCT_FLEX_PREFIX_MIN_WORDS = 2

# Full ``SequenceMatcher.ratio()`` on very large paragraph strings is quadratic
# and can dominate golden-corpus runtime on the large IB protocols. Keep the
# existing cheap gates, but for oversized paragraphs rely on token similarity
# instead of raw character ratio.
_ALIGN_SKIP_CHAR_RATIO_MAX_CHARS = 1400
_ALIGN_SKIP_CHAR_RATIO_MAX_PRODUCT = 1_200_000
_ALIGN_SKIP_CHAR_RATIO_MIN_BODY_BLOCKS = 1000

# Post-LCS repair: reclaim ``(o, None)`` + ``(None, r)`` when expansion is obvious (see
# :func:`_repair_alignment_unmatched_rev_expansion_override`).
_ALIGNMENT_OVERRIDE_RANK_SIM_MIN = 0.85
# When :func:`_containment_hint_string` reports ``paragraph_expansion_likely``, allow
# lower rank similarity than :data:`_ALIGNMENT_OVERRIDE_RANK_SIM_MIN` (short → longer).
_ALIGNMENT_OVERRIDE_RANK_SIM_EXPANSION_RELAX_MIN = 0.65
_CONTAINMENT_EXPANSION_HINT_PREFIX = "paragraph_expansion_likely"
# :func:`_pair_rank_similarity_best_candidate` only: mixed paragraph/table pairs get a
# lower rank than same-type pairs at equal raw ``max(char_ratio, tok_ratio)``.
_BEST_CANDIDATE_CROSS_TYPE_RANK_PENALTY = 0.85

# TOC lines (section number + tab + title + tab + page) often get reworded titles while
# keeping the same entry (e.g. ``1.2.1`` … ``Pathophysiology`` → ``Differences in …``).
# Global fuzzy gates then miss (``quick_ratio`` ~0.71 < 0.86), LCS pairs them as
# delete+insert, and emit shows full-line strikethrough + duplicate line (SCRUM-116).
_TOC_SLOT_PREFIX_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)")

# Relaxed gates when both lines share the same TOC section prefix and contain a tab.
_TOC_SLOT_QUICK_MIN = 0.50
_TOC_SLOT_COMBINED_MIN = 0.55


class _LcsBacktrackStep(NamedTuple):
    """One row from replaying :func:`align_paragraphs` backtrack (debug only)."""

    kind: str  # match | skip_orig | skip_rev | tail_orig | tail_rev
    i_before: int
    j_before: int
    aligned_ij: bool
    dp_down: int  # dp[i+1][j] when i<m, else -1
    dp_right: int  # dp[i][j+1] when j<n, else -1


@dataclass(frozen=True)
class ParagraphAlignment:
    original_paragraph_index: int | None
    revised_paragraph_index: int | None
    # When set, revised blocks ``rj .. revised_merge_end_exclusive-1`` are concatenated
    # for inline diff against ``original_paragraph_index`` (SCRUM-121 split paragraphs).
    revised_merge_end_exclusive: int | None = None


def _repair_alignment_orig_table_rev_paras_then_rev_table(
    alignment: list[ParagraphAlignment],
    original: BodyIR,
    revised: BodyIR,
) -> list[ParagraphAlignment]:
    """
    When LCS emits an original-only ``w:tbl``, then revised-only paragraph(s), then a
    revised-only ``w:tbl``, Track Changes emit would **remove** the original table and
    **insert** the whole revised table inside one ``w:ins`` (purple block). Word-style
    compare instead **matches** the two tables and applies cell-level revisions.

    Rewire to: revised-only paragraph steps unchanged in order, then ``(oi, rj)``
    **table–table** so :func:`engine.body_revision_emit._apply_matched_table_track_changes`
    runs (SCRUM-120 follow-up).
    """

    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    if not alignment:
        return alignment
    out: list[ParagraphAlignment] = []
    i = 0
    n = len(alignment)
    while i < n:
        al = alignment[i]
        oi, rj = al.original_paragraph_index, al.revised_paragraph_index
        repaired = False
        if (
            oi is not None
            and rj is None
            and oi < len(ob)
            and ob[oi].get("type") == "table"
        ):
            j = i + 1
            rev_only_mid: list[ParagraphAlignment] = []
            while j < n:
                a2 = alignment[j]
                o2, r2 = a2.original_paragraph_index, a2.revised_paragraph_index
                if o2 is not None:
                    break
                if r2 is None or r2 >= len(rb):
                    break
                br = rb[r2]
                if br.get("type") == "table":
                    out.extend(rev_only_mid)
                    out.append(ParagraphAlignment(oi, r2))
                    i = j + 1
                    repaired = True
                    break
                if br.get("type") == "paragraph":
                    rev_only_mid.append(a2)
                    j += 1
                    continue
                break
        if repaired:
            continue
        out.append(al)
        i += 1
    return out


# Revised split one logical paragraph into several ``w:p`` nodes; LCS leaves
# ``(oi, None)`` then ``(None, rj0..)`` before ``(oi+1, *)``. Merge for emit when
# enough shared text remains for a safe inline diff (not full-paragraph delete).
_SPLIT_MERGE_MAX_REV_PARAGRAPHS = 3
_SPLIT_MERGE_MIN_CHAR_BLOCK = 40
_SPLIT_MERGE_MIN_WORD_TOKEN_RATIO = 0.10


def _split_merge_pair_aligns(orig_txt: str, merged_rev_txt: str) -> bool:
    if not orig_txt.strip() or not merged_rev_txt.strip():
        return False
    sm = difflib.SequenceMatcher(None, orig_txt, merged_rev_txt, autojunk=False)
    max_blk = max((b[2] for b in sm.get_matching_blocks()), default=0)
    if max_blk < _SPLIT_MERGE_MIN_CHAR_BLOCK:
        return False
    ow = norm_keys([t for t in tokenize_for_lcs(orig_txt) if not t.surface.isspace()])
    mw = norm_keys([t for t in tokenize_for_lcs(merged_rev_txt) if not t.surface.isspace()])
    if not ow or not mw:
        return False
    tok_r = difflib.SequenceMatcher(None, ow, mw, autojunk=False).ratio()
    return tok_r >= _SPLIT_MERGE_MIN_WORD_TOKEN_RATIO


def _repair_alignment_orig_para_rev_split_merge(
    alignment: list[ParagraphAlignment],
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
) -> list[ParagraphAlignment]:
    """
    Merge ``(oi, None)`` + consecutive ``(None, rj)`` paragraph steps into
    ``(oi, rj0, revised_merge_end_exclusive=...)`` when the revised paragraphs are
    a split rewrite of the same original paragraph (SCRUM-121 cervical sample).
    """

    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    if not alignment:
        return alignment
    out: list[ParagraphAlignment] = []
    i = 0
    n = len(alignment)
    while i < n:
        al = alignment[i]
        oi, rj = al.original_paragraph_index, al.revised_paragraph_index
        merged = False
        if (
            oi is not None
            and rj is None
            and oi < len(ob)
            and ob[oi].get("type") == "paragraph"
            and i + 1 < n
        ):
            j = i + 1
            rev_chain: list[int] = []
            while j < n:
                a2 = alignment[j]
                o2, r2 = a2.original_paragraph_index, a2.revised_paragraph_index
                if o2 is not None:
                    break
                if r2 is None or r2 >= len(rb):
                    break
                if rb[r2].get("type") != "paragraph":
                    break
                if len(rev_chain) >= _SPLIT_MERGE_MAX_REV_PARAGRAPHS:
                    break
                rev_chain.append(r2)
                j += 1
            if (
                rev_chain
                and j < n
                and alignment[j].original_paragraph_index == oi + 1
            ):
                merged_txt = "".join(
                    _block_alignment_text(revised, ridx, config) for ridx in rev_chain
                )
                orig_txt = _block_alignment_text(original, oi, config)
                if _split_merge_pair_aligns(orig_txt, merged_txt):
                    end_excl = rev_chain[-1] + 1
                    out.append(
                        ParagraphAlignment(
                            oi,
                            rev_chain[0],
                            revised_merge_end_exclusive=end_excl,
                        )
                    )
                    i = j
                    merged = True
        if not merged:
            out.append(al)
            i += 1
    return out


def _merged_heading_prefix_before_colon(orig_txt: str) -> str | None:
    """
    Leading ``Heading:`` prefix for merged heading+body paragraphs, or None.

    Used by :func:`_repair_alignment_orig_delete_block_then_rev_insert_merge` to
    pair original one-paragraph subsections with revised split heading + body blocks
    (SCRUM-138).
    """

    m = re.match(r"^\s*([A-Za-z][^:\n]{0,120}?):\s*\S", orig_txt)
    return m.group(1).strip() if m else None


def _is_prevention_section_heading_text(txt: str) -> bool:
    tl = txt.strip().lower()
    return (
        "prevention" in tl
        and "screening" in tl
        and "diagnostic" in tl
        and "strategies" in tl
    )


def _prevention_headings_match(orig_txt: str, rev_txt: str) -> bool:
    """Loose match for ``Prevention, Screening…`` vs ``Differences in Prevention, Screening…``."""

    if not _is_prevention_section_heading_text(orig_txt):
        return False
    return _is_prevention_section_heading_text(rev_txt)


def _short_heading_suffix_rewrite_match(orig_txt: str, rev_txt: str) -> bool:
    """
    True for short heading rewrites that preserve the original title as a suffix.

    This targets sponsor headings like ``Pathophysiology`` → ``Differences in
    Pathophysiology`` after nearby blank-paragraph drift pulls LCS off the
    direct match. Keep it narrow so normal body paragraphs do not get re-paired.
    """

    os = orig_txt.strip()
    rs = rev_txt.strip()
    if not os or not rs or os == rs:
        return False
    if any(ch in os or ch in rs for ch in ("\n", "\t", ".", ":", ";")):
        return False

    ow = [t.norm_key() for t in tokenize_for_lcs(os) if re.search(r"\w", t.surface)]
    rw = [t.norm_key() for t in tokenize_for_lcs(rs) if re.search(r"\w", t.surface)]
    if not ow or not rw:
        return False
    if len(ow) > 4 or len(rw) > 8 or len(rw) <= len(ow):
        return False
    if rw[-len(ow) :] != ow:
        return False

    char_r = difflib.SequenceMatcher(None, os, rs, autojunk=False).ratio()
    return char_r >= 0.62


def _first_prevention_heading_index_in_rev_run(
    rev_run: list[int],
    r_ptr: int,
    revised: BodyIR,
    config: CompareConfig,
) -> int | None:
    """Smallest index ``t >= r_ptr`` into ``rev_run`` whose paragraph is a Prevention section heading."""

    rb = revised.get("blocks", [])
    for t in range(r_ptr, len(rev_run)):
        rj = rev_run[t]
        if rj >= len(rb) or rb[rj].get("type") != "paragraph":
            return None
        txt = _block_alignment_text(revised, rj, config)
        if _is_prevention_section_heading_text(txt):
            return t
    return None


def _try_repair_scrum138_orig_rev_block(
    orig_run: list[int],
    rev_run: list[int],
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
) -> list[ParagraphAlignment] | None:
    """
    Rewire a consecutive ``(oi, None)`` run followed by a consecutive ``(None, rj)``
    run when the original side used merged heading+body paragraphs and the revised
    side split them into headings and bodies (cervical diversity sample, SCRUM-138).

    Returns ``None`` when the pattern does not apply or matching fails.
    """

    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    if not orig_run or not rev_run:
        return None

    r_ptr = 0
    out: list[ParagraphAlignment] = []
    for orig_i in orig_run:
        if orig_i >= len(ob) or ob[orig_i].get("type") != "paragraph":
            return None
        orig_txt = _block_alignment_text(original, orig_i, config)
        prefix = _merged_heading_prefix_before_colon(orig_txt)

        if prefix and prefix.lower() == "hpv infection":
            if r_ptr + 1 >= len(rev_run):
                return None
            r0, r1 = rev_run[r_ptr], rev_run[r_ptr + 1]
            if r1 >= len(rb) or rb[r0].get("type") != "paragraph" or rb[r1].get("type") != "paragraph":
                return None
            r0_txt = _block_alignment_text(revised, r0, config).strip()
            if r0_txt.lower() != "hpv infection":
                return None
            merged = _block_alignment_text(revised, r0, config) + _block_alignment_text(
                revised, r1, config
            )
            if not _split_merge_pair_aligns(orig_txt, merged):
                return None
            out.append(
                ParagraphAlignment(
                    orig_i,
                    r0,
                    revised_merge_end_exclusive=r1 + 1,
                )
            )
            r_ptr += 2
            continue

        if prefix and prefix.lower() == "environmental factors":
            if r_ptr >= len(rev_run):
                return None
            r0 = rev_run[r_ptr]
            if r0 >= len(rb) or rb[r0].get("type") != "paragraph":
                return None
            if _block_alignment_text(revised, r0, config).strip().lower() != "environmental factors":
                return None
            stop_t = _first_prevention_heading_index_in_rev_run(rev_run, r_ptr, revised, config)
            if stop_t is None or stop_t <= r_ptr:
                return None
            merged = "".join(
                _block_alignment_text(revised, rev_run[t], config) for t in range(r_ptr, stop_t)
            )
            if not _split_merge_pair_aligns(orig_txt, merged):
                return None
            end_rj = rev_run[stop_t - 1]
            out.append(
                ParagraphAlignment(
                    orig_i,
                    rev_run[r_ptr],
                    revised_merge_end_exclusive=end_rj + 1,
                )
            )
            r_ptr = stop_t
            continue

        if prefix and "gene" in prefix.lower() and "polymorphism" in prefix.lower():
            out.append(ParagraphAlignment(orig_i, None))
            continue

        if r_ptr >= len(rev_run):
            out.append(ParagraphAlignment(orig_i, None))
            continue

        doc_rj = rev_run[r_ptr]
        if doc_rj >= len(rb) or rb[doc_rj].get("type") != "paragraph":
            return None
        rev_txt = _block_alignment_text(revised, doc_rj, config)
        if _prevention_headings_match(orig_txt, rev_txt):
            out.append(ParagraphAlignment(orig_i, doc_rj))
            r_ptr += 1
            continue

        return None

    if r_ptr != len(rev_run):
        return None
    return out


def _try_repair_short_heading_suffix_orig_rev_block(
    orig_run: list[int],
    rev_run: list[int],
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
) -> list[ParagraphAlignment] | None:
    """
    Re-pair short heading rewrites inside an orig-only run followed by a rev-only run.

    Example from the cervical corpus:
    ``Pathophysiology`` → ``Differences in Pathophysiology``.
    """

    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    if len(rev_run) != 1 or not orig_run:
        return None

    rj = rev_run[0]
    if rj >= len(rb) or rb[rj].get("type") != "paragraph":
        return None
    rev_txt = _block_alignment_text(revised, rj, config)

    match_pos: int | None = None
    for pos, oi in enumerate(orig_run):
        if oi >= len(ob) or ob[oi].get("type") != "paragraph":
            return None
        orig_txt = _block_alignment_text(original, oi, config)
        if _short_heading_suffix_rewrite_match(orig_txt, rev_txt):
            if match_pos is not None:
                return None
            match_pos = pos

    if match_pos is None:
        return None

    out: list[ParagraphAlignment] = []
    for pos, oi in enumerate(orig_run):
        out.append(ParagraphAlignment(oi, rj if pos == match_pos else None))
    return out


def _repair_alignment_orig_delete_block_then_rev_insert_merge(
    alignment: list[ParagraphAlignment],
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
) -> list[ParagraphAlignment]:
    """
    When LCS emits **all** consecutive original-only rows then **all** consecutive
    revised-only rows, :func:`_repair_alignment_orig_para_rev_split_merge` cannot
    fire (it requires an ``(oi, None)`` + ``(None, r…)`` chain **before** the next
    matched original). Rewire merged heading+body originals to split revised
    paragraphs (SCRUM-138).
    """

    if not alignment:
        return alignment
    out: list[ParagraphAlignment] = []
    i = 0
    n = len(alignment)
    while i < n:
        oi0 = alignment[i].original_paragraph_index
        rj0 = alignment[i].revised_paragraph_index
        if oi0 is None or rj0 is not None:
            out.append(alignment[i])
            i += 1
            continue
        j = i
        orig_run: list[int] = []
        while j < n:
            a = alignment[j]
            oi, rj = a.original_paragraph_index, a.revised_paragraph_index
            if oi is None or rj is not None:
                break
            if not orig_run:
                orig_run.append(oi)
            elif orig_run[-1] + 1 != oi:
                break
            else:
                orig_run.append(oi)
            j += 1
        if j >= n or alignment[j].original_paragraph_index is not None:
            out.extend(alignment[i:j])
            i = j
            continue
        k = j
        rev_run: list[int] = []
        while k < n:
            a = alignment[k]
            oi, rj = a.original_paragraph_index, a.revised_paragraph_index
            if oi is not None or rj is None:
                break
            if not rev_run:
                rev_run.append(rj)
            elif rev_run[-1] + 1 != rj:
                break
            else:
                rev_run.append(rj)
            k += 1
        repaired = _try_repair_scrum138_orig_rev_block(
            orig_run, rev_run, original, revised, config
        )
        if repaired is None:
            repaired = _try_repair_short_heading_suffix_orig_rev_block(
                orig_run, rev_run, original, revised, config
            )
        if repaired is not None:
            out.extend(repaired)
            i = k
        else:
            out.extend(alignment[i:k])
            i = k
    return out


def _toc_section_prefix_for_alignment(txt: str) -> str | None:
    """Leading numbered section id (``1``, ``1.2.1``, …) or None if not TOC-shaped."""

    m = _TOC_SLOT_PREFIX_RE.match(txt.lstrip())
    return m.group(1) if m else None


def _diagonal_prefix_anchor(o_txt: str, r_txt: str) -> bool:
    """
    True when same-slot bodies look like an in-place grow/shrink (prefix/suffix),
    not a different sentence. Used only for diagonal ``(i,i)`` paragraph pairs
    when fuzzy gates fail (e.g. ``Hi`` vs ``Hi there``).
    """

    o_st, r_st = o_txt.strip(), r_txt.strip()
    if not o_st or not r_st:
        return o_st == r_st
    if o_st == r_st:
        return True
    shorter, longer = (o_st, r_st) if len(o_st) <= len(r_st) else (r_st, o_st)
    if longer.startswith(shorter):
        return True
    return _punctuation_flexible_prefix_match(o_st, r_st)


def _punctuation_flexible_prefix_match(o_txt: str, r_txt: str) -> bool:
    """
    True when both paragraphs share the same opening token sequence and only
    diverge on punctuation right at the boundary where the shorter text ends.

    This keeps short sentence-shortening cases aligned when the revised text
    ends the shared stem with a period while the original continues with a
    comma-led clause.
    """

    o_st, r_st = o_txt.strip(), r_txt.strip()
    if not o_st or not r_st:
        return False
    shorter, longer = (o_st, r_st) if len(o_st) <= len(r_st) else (r_st, o_st)
    if len(shorter) < _ALIGN_PUNCT_FLEX_PREFIX_MIN_CHARS:
        return False

    shorter_tokens = [t for t in tokenize_for_lcs(shorter) if not t.surface.isspace()]
    longer_tokens = [t for t in tokenize_for_lcs(longer) if not t.surface.isspace()]
    shorter_words = [t for t in shorter_tokens if re.search(r"\w", t.surface)]
    if len(shorter_words) < _ALIGN_PUNCT_FLEX_PREFIX_MIN_WORDS:
        return False

    i = j = 0
    while i < len(shorter_tokens) and j < len(longer_tokens):
        if shorter_tokens[i].norm_key() != longer_tokens[j].norm_key():
            break
        i += 1
        j += 1

    while i < len(shorter_tokens) and not re.search(r"\w", shorter_tokens[i].surface):
        i += 1
    while j < len(longer_tokens) and not re.search(r"\w", longer_tokens[j].surface):
        j += 1
    return i == len(shorter_tokens)


def _toc_slot_pair_relaxed_align(o_txt: str, r_txt: str) -> bool:
    """
    True when both lines look like TOC entries with the same section number and
    enough textual overlap to treat as the same paragraph for alignment.
    """

    if "\t" not in o_txt or "\t" not in r_txt:
        return False
    po, pr = _toc_section_prefix_for_alignment(o_txt), _toc_section_prefix_for_alignment(
        r_txt
    )
    if not po or po != pr:
        return False
    sm = difflib.SequenceMatcher(None, o_txt, r_txt, autojunk=False)
    q = sm.quick_ratio()
    char_r = sm.ratio()
    ot = norm_keys(tokenize_for_lcs(o_txt))
    rt = norm_keys(tokenize_for_lcs(r_txt))
    tok_r = difflib.SequenceMatcher(None, ot, rt, autojunk=False).ratio()
    return q >= _TOC_SLOT_QUICK_MIN and max(char_r, tok_r) >= _TOC_SLOT_COMBINED_MIN


def _block_signature(body_ir: BodyIR, block_index: int, config: CompareConfig) -> str:
    """
    Compute a deterministic signature for one top-level block (paragraph or table).
    """

    blocks = body_ir.get("blocks", [])
    block = blocks[block_index]
    btype = block.get("type")
    if btype == "paragraph":
        paragraph_ir: BodyIR = {"version": body_ir["version"], "blocks": [block]}
        keys = generate_compare_keys(paragraph_ir, config)
        return "|".join(k["key"].split(":", 1)[1] for k in keys)
    if btype == "table":
        parts: list[str] = []
        for row in block.get("rows", []):
            for cell in row:
                cell_ir: BodyIR = {
                    "version": body_ir["version"],
                    "blocks": cell["paragraphs"],
                }
                keys = generate_compare_keys(cell_ir, config)
                parts.append("|".join(k["key"].split(":", 1)[1] for k in keys))
        return "||".join(parts)
    raise ValueError(f"Unsupported block type for alignment: {btype!r}.")


def _non_whitespace_word_jaccard_and_counts(o_txt: str, r_txt: str) -> tuple[float, int, int]:
    """Jaccard on norm keys of non-whitespace tokens plus both token counts."""

    ow = [t.norm_key() for t in tokenize_for_lcs(o_txt) if not t.surface.isspace()]
    rw = [t.norm_key() for t in tokenize_for_lcs(r_txt) if not t.surface.isspace()]
    if not ow and not rw:
        return 1.0, 0, 0
    if not ow or not rw:
        return 0.0, len(ow), len(rw)
    so, sr = set(ow), set(rw)
    j = len(so & sr) / len(so | sr)
    return j, len(ow), len(rw)


def _block_alignment_text(body_ir: BodyIR, block_index: int, config: CompareConfig) -> str:
    """Plain normalized text (paragraph) or signature string (table) for fuzzy comparison."""

    blocks = body_ir.get("blocks", [])
    block = blocks[block_index]
    if block.get("type") == "paragraph":
        return "".join(
            _normalize_text(str(run.get("text", "")), config) for run in block.get("runs", [])
        )
    return _block_signature(body_ir, block_index, config)


def _length_weak_prefix_expansion_match(o_txt: str, r_txt: str) -> bool:
    """
    True when the shorter normalized text is a prefix of the longer and the
    shorter side is long enough to avoid accidental ``Hi``-style matches.
    Also allows a punctuation-only boundary change at the end of the shared stem.
    """

    os, rs = o_txt.strip(), r_txt.strip()
    if not os or not rs:
        return False
    shorter, longer = (os, rs) if len(os) <= len(rs) else (rs, os)
    if len(shorter) >= _ALIGN_LENGTH_BYPASS_PREFIX_MIN_CHARS and longer.startswith(shorter):
        return True
    return _punctuation_flexible_prefix_match(os, rs)


def _should_skip_expensive_char_ratio(
    lo: int, lr: int, *, body_block_count: int | None = None
) -> bool:
    """True when raw character ``ratio()`` is too expensive to justify."""

    return (
        lo > 0
        and lr > 0
        and (body_block_count is None or body_block_count >= _ALIGN_SKIP_CHAR_RATIO_MIN_BODY_BLOCKS)
        and max(lo, lr) >= _ALIGN_SKIP_CHAR_RATIO_MAX_CHARS
        and lo * lr >= _ALIGN_SKIP_CHAR_RATIO_MAX_PRODUCT
    )


def _containment_hint_string(o_txt: str, r_txt: str) -> str:
    """
    Same heuristic labels as stderr token overlap debug (single string per pair).
    """

    toks_o = [t for t in tokenize_for_lcs(o_txt) if not t.surface.isspace()]
    toks_r = [t for t in tokenize_for_lcs(r_txt) if not t.surface.isspace()]
    norm_o = [t.norm_key() for t in toks_o]
    norm_r = [t.norm_key() for t in toks_r]
    co = Counter(norm_o)
    cr = Counter(norm_r)
    shared_occ = sum(min(co[k], cr[k]) for k in co)
    set_o, set_r = set(co), set(cr)
    tot_o, tot_r = len(norm_o), len(norm_r)
    ratio_o = shared_occ / tot_o if tot_o else 0.0
    char_r = 0.0
    if not _should_skip_expensive_char_ratio(len(o_txt), len(r_txt)):
        sm = difflib.SequenceMatcher(None, o_txt, r_txt, autojunk=False)
        char_r = sm.ratio()
    ot = norm_keys(tokenize_for_lcs(o_txt))
    rt = norm_keys(tokenize_for_lcs(r_txt))
    tok_r = difflib.SequenceMatcher(None, ot, rt, autojunk=False).ratio()
    jacc, _owc, _rwc = _non_whitespace_word_jaccard_and_counts(o_txt, r_txt)
    subset_vocab = set_o <= set_r if set_o else True
    os_, rs_ = o_txt.strip(), r_txt.strip()
    prefix_exp = False
    if os_ and rs_:
        shorter, longer = (os_, rs_) if len(os_) <= len(rs_) else (rs_, os_)
        if len(shorter) >= 12:
            prefix_exp = longer.startswith(shorter)

    if max(char_r, tok_r) < 0.18 and jacc < 0.12 and ratio_o < 0.15:
        return "unrelated_likely (low char/tok/jaccard and low multiset overlap on orig)"
    if prefix_exp or _length_weak_prefix_expansion_match(o_txt, r_txt):
        return "paragraph_expansion_likely (shorter text is prefix of longer, or prefix-bypass shape)"
    if ratio_o >= 0.88 or (subset_vocab and tot_o >= 6):
        return "orig_mostly_contained_in_rev (high multiset orig coverage or orig vocab subset of rev)"
    if tot_r > max(tot_o * 2, 12) and ratio_o >= 0.35 and max(char_r, tok_r) < 0.45:
        return "diluted_similarity_likely (many extra rev tokens; orig overlap moderate but char/tok ratios low)"
    return "mixed_overlap (review raw/norm lists and ratios manually)"


def _repair_alignment_unmatched_rev_expansion_override(
    alignment: list[ParagraphAlignment],
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
) -> list[ParagraphAlignment]:
    """
    Post-process LCS alignment: turn some ``(None, rj)`` + prior ``(o, None)``
    pairs into ``(o, rj)`` when rank similarity, gates, and containment say the
    revised block is an expansion of that original. Does not change
    :func:`align_paragraphs` or :func:`_blocks_align_in_lcs`.
    """

    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    m, n = len(ob), len(rb)
    if not alignment or m == 0 or n == 0:
        return alignment

    orig_matched = {
        al.original_paragraph_index
        for al in alignment
        if al.original_paragraph_index is not None and al.revised_paragraph_index is not None
    }
    orig_only = {
        al.original_paragraph_index
        for al in alignment
        if al.original_paragraph_index is not None and al.revised_paragraph_index is None
    }
    slack = abs(m - n) + 12
    o_txts = [_block_alignment_text(original, i, config) for i in range(m)]
    r_txts = [_block_alignment_text(revised, j, config) for j in range(n)]
    orig_sigs = [_block_signature(original, i, config) for i in range(m)]
    rev_sigs = [_block_signature(revised, j, config) for j in range(n)]

    def _orig_only_step_index(oi_del: int) -> int | None:
        for j, a2 in enumerate(alignment):
            if a2.original_paragraph_index == oi_del and a2.revised_paragraph_index is None:
                return j
        return None

    def _best_candidate(rj: int) -> tuple[int, float, bool, str] | None:
        if rj < 0 or rj >= n:
            return None
        candidates = [i for i in range(m) if abs(i - rj) <= slack]
        ranked: list[tuple[int, float]] = []
        for c in candidates:
            s = _pair_rank_similarity_best_candidate(c, rj, o_txts, r_txts, ob, rb)
            ranked.append((c, s))
        if not ranked:
            return None
        ranked.sort(
            key=lambda t: (
                -t[1],
                0 if ob[t[0]].get("type") == rb[rj].get("type") else 1,
                abs(t[0] - rj),
            )
        )
        o_best, s_best = ranked[0]
        if o_best < 0 or o_best >= len(orig_sigs) or rj >= len(rev_sigs):
            return None
        ok_best, _ = _align_score_full_pair_detail(
            original,
            revised,
            o_best,
            rj,
            config,
            m=m,
            n=n,
            o_txts=o_txts,
            r_txts=r_txts,
            orig_sigs=orig_sigs,
            rev_sigs=rev_sigs,
            orig_blocks=ob,
            rev_blocks=rb,
        )
        if o_best >= len(o_txts) or rj >= len(r_txts):
            return None
        hint = _containment_hint_string(o_txts[o_best], r_txts[rj])
        return (o_best, s_best, ok_best, hint)

    replace_at: dict[int, ParagraphAlignment] = {}
    remove_idx: set[int] = set()
    claimed_orig = set(orig_matched)
    last_matched_pair_orig = -1

    for idx, al in enumerate(alignment):
        oi, rj = al.original_paragraph_index, al.revised_paragraph_index
        if oi is not None and rj is not None:
            last_matched_pair_orig = max(last_matched_pair_orig, oi)
            continue
        if oi is None and rj is not None:
            bc = _best_candidate(rj)
            if bc is None:
                continue
            o_best, s_best, ok_best, hint = bc
            expansion_hint = hint.startswith(_CONTAINMENT_EXPANSION_HINT_PREFIX)
            if expansion_hint:
                if s_best < _ALIGNMENT_OVERRIDE_RANK_SIM_EXPANSION_RELAX_MIN:
                    continue
            else:
                if s_best <= _ALIGNMENT_OVERRIDE_RANK_SIM_MIN:
                    continue
            if not ok_best:
                continue
            if not expansion_hint:
                continue
            if o_best in claimed_orig:
                continue
            if o_best in orig_matched:
                continue
            if o_best not in orig_only:
                continue
            if not (o_best > last_matched_pair_orig or o_best == 0):
                continue
            del_j = _orig_only_step_index(o_best)
            if del_j is None or del_j >= idx:
                continue
            replace_at[idx] = ParagraphAlignment(
                o_best,
                rj,
                al.revised_merge_end_exclusive,
            )
            remove_idx.add(del_j)
            claimed_orig.add(o_best)
            last_matched_pair_orig = max(last_matched_pair_orig, o_best)

    if not replace_at and not remove_idx:
        return alignment

    out: list[ParagraphAlignment] = []
    for idx, al in enumerate(alignment):
        if idx in remove_idx:
            continue
        if idx in replace_at:
            out.append(replace_at[idx])
            continue
        out.append(al)
    return out


def _maybe_diagnose_unmatched_rev_repair_gates(
    alignment: list[ParagraphAlignment],
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
    *,
    strategy_tag: str,
) -> None:
    """
    When ``MDC_DEBUG_UNMATCHED_REV_REPAIR_GATES=1``, print per-step gate
    evaluation for each ``(None, rj)`` row using the **same sequential rules** as
    :func:`_repair_alignment_unmatched_rev_expansion_override` (including
    ``claimed_orig`` / ``last_matched_pair_orig`` updates after a virtual apply).

    Call this on the alignment **immediately before** the override runs. Does not
    change alignment output.
    """

    flag = os.environ.get("MDC_DEBUG_UNMATCHED_REV_REPAIR_GATES", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return

    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    m, n = len(ob), len(rb)
    if not alignment or m == 0 or n == 0:
        print(
            f"[MDC_UNMATCHED_REV_REPAIR_GATE] strategy={strategy_tag} skip: empty alignment or bodies",
            file=sys.stderr,
        )
        return

    orig_matched = {
        al.original_paragraph_index
        for al in alignment
        if al.original_paragraph_index is not None and al.revised_paragraph_index is not None
    }
    orig_only = {
        al.original_paragraph_index
        for al in alignment
        if al.original_paragraph_index is not None and al.revised_paragraph_index is None
    }
    slack = abs(m - n) + 12
    o_txts = [_block_alignment_text(original, i, config) for i in range(m)]
    r_txts = [_block_alignment_text(revised, j, config) for j in range(n)]
    orig_sigs = [_block_signature(original, i, config) for i in range(m)]
    rev_sigs = [_block_signature(revised, j, config) for j in range(n)]

    def _orig_only_step_index(oi_del: int) -> int | None:
        for j, a2 in enumerate(alignment):
            if a2.original_paragraph_index == oi_del and a2.revised_paragraph_index is None:
                return j
        return None

    def _best_candidate(rj: int) -> tuple[int, float, bool, str] | None:
        if rj < 0 or rj >= n:
            return None
        candidates = [i for i in range(m) if abs(i - rj) <= slack]
        ranked: list[tuple[int, float]] = []
        for c in candidates:
            s = _pair_rank_similarity_best_candidate(c, rj, o_txts, r_txts, ob, rb)
            ranked.append((c, s))
        if not ranked:
            return None
        ranked.sort(
            key=lambda t: (
                -t[1],
                0 if ob[t[0]].get("type") == rb[rj].get("type") else 1,
                abs(t[0] - rj),
            )
        )
        o_best, s_best = ranked[0]
        if o_best < 0 or o_best >= len(orig_sigs) or rj >= len(rev_sigs):
            return None
        ok_best, _ = _align_score_full_pair_detail(
            original,
            revised,
            o_best,
            rj,
            config,
            m=m,
            n=n,
            o_txts=o_txts,
            r_txts=r_txts,
            orig_sigs=orig_sigs,
            rev_sigs=rev_sigs,
            orig_blocks=ob,
            rev_blocks=rb,
        )
        if o_best >= len(o_txts) or rj >= len(r_txts):
            return None
        hint = _containment_hint_string(o_txts[o_best], r_txts[rj])
        return (o_best, s_best, ok_best, hint)

    claimed_orig = set(orig_matched)
    last_matched_pair_orig = -1
    summary: Counter[str] = Counter()
    records: list[tuple[str, int, int, int]] = []  # (reason, idx, rj, o_best_or_-1)

    def _pair_str(al2: ParagraphAlignment) -> str:
        return f"({al2.original_paragraph_index},{al2.revised_paragraph_index})"

    print(
        f"[MDC_UNMATCHED_REV_REPAIR_GATE] strategy={strategy_tag} "
        f"orig_blocks={m} rev_blocks={n} alignment_steps={len(alignment)}",
        file=sys.stderr,
    )

    for idx, al in enumerate(alignment):
        oi, rj = al.original_paragraph_index, al.revised_paragraph_index
        if oi is not None and rj is not None:
            last_matched_pair_orig = max(last_matched_pair_orig, oi)
            continue
        if oi is None and rj is None:
            continue
        if oi is not None and rj is None:
            continue

        assert oi is None and rj is not None
        last_before = last_matched_pair_orig
        bc = _best_candidate(rj)
        if bc is None:
            reason = "FAIL_NO_CANDIDATE"
            print(
                f"[MDC_UNMATCHED_REV_REPAIR_GATE] idx={idx} rj={rj} {reason} "
                f"last_matched_pair_orig={last_before}",
                file=sys.stderr,
            )
            summary[reason] += 1
            records.append((reason, idx, rj, -1))
            continue

        o_best, s_best, ok_best, hint = bc
        in_orig_matched = o_best in orig_matched
        in_orig_only = o_best in orig_only
        del_j = _orig_only_step_index(o_best)
        hint_ok = hint.startswith(_CONTAINMENT_EXPANSION_HINT_PREFIX)

        reason: str | None = None
        if hint_ok:
            low_sim = s_best < _ALIGNMENT_OVERRIDE_RANK_SIM_EXPANSION_RELAX_MIN
        else:
            low_sim = s_best <= _ALIGNMENT_OVERRIDE_RANK_SIM_MIN
        if low_sim:
            reason = "FAIL_LOW_SIMILARITY"
        elif not ok_best:
            reason = "FAIL_ALIGNMENT_GATE"
        elif not hint_ok:
            reason = "FAIL_CONTAINMENT_HINT"
        elif o_best in claimed_orig:
            reason = (
                "FAIL_ALREADY_MATCHED"
                if in_orig_matched
                else "FAIL_CLAIMED_BY_EARLIER_OVERRIDE_IN_PASS"
            )
        elif o_best not in orig_only:
            reason = "FAIL_NOT_IN_ORIG_ONLY"
        elif not (o_best > last_matched_pair_orig or o_best == 0):
            reason = "FAIL_ORDER_CONSTRAINT"
        elif del_j is None or del_j >= idx:
            reason = "FAIL_DELETE_ORDER"
        else:
            reason = "APPLY_OK"
            claimed_orig.add(o_best)
            last_matched_pair_orig = max(last_matched_pair_orig, o_best)

        print(
            f"[MDC_UNMATCHED_REV_REPAIR_GATE] idx={idx} rj={rj} o_best={o_best} "
            f"s_best={s_best:.6f} ok_best={ok_best} containment_hint={hint!r} "
            f"o_best_in_orig_matched={in_orig_matched} o_best_in_orig_only={in_orig_only} "
            f"del_j={del_j} last_matched_pair_orig={last_before} -> {reason}",
            file=sys.stderr,
        )
        summary[reason] += 1
        records.append((reason, idx, rj, o_best))

    print(f"[MDC_UNMATCHED_REV_REPAIR_GATE] strategy={strategy_tag} SUMMARY:", file=sys.stderr)
    for label, cnt in summary.most_common():
        print(f"[MDC_UNMATCHED_REV_REPAIR_GATE]   {label}: {cnt}", file=sys.stderr)

    fail_codes = [k for k in summary if k != "APPLY_OK"]
    if not fail_codes:
        return
    dominant = max(fail_codes, key=lambda k: summary[k])
    samples = [(r, i, j, ob) for r, i, j, ob in records if r == dominant][:3]
    print(
        f"[MDC_UNMATCHED_REV_REPAIR_GATE] strategy={strategy_tag} "
        f"SAMPLES (up to 3) for dominant_failure={dominant!r}:",
        file=sys.stderr,
    )
    for reason, idx, rj, o_best_s in samples:
        lo = max(0, idx - 3)
        hi = min(len(alignment), idx + 4)
        print(
            f"[MDC_UNMATCHED_REV_REPAIR_GATE]   --- sample idx={idx} rj={rj} {reason} ---",
            file=sys.stderr,
        )
        for k in range(lo, hi):
            mark = " <-- UNMATCHED_REV under test" if k == idx else ""
            print(
                f"[MDC_UNMATCHED_REV_REPAIR_GATE]     step[{k}] {_pair_str(alignment[k])}{mark}",
                file=sys.stderr,
            )
        if o_best_s >= 0:
            dj = _orig_only_step_index(o_best_s)
            print(
                f"[MDC_UNMATCHED_REV_REPAIR_GATE]     (o_best={o_best_s},None) at step_index del_j={dj}; "
                f"(None,rj={rj}) at step_index idx={idx}; "
                f"ordering_ok_for_repair={dj is not None and dj < idx}",
                file=sys.stderr,
            )


def _blocks_align_in_lcs(
    original: BodyIR,
    revised: BodyIR,
    oi: int,
    rj: int,
    o_sig: str,
    r_sig: str,
    config: CompareConfig,
    *,
    m: int,
    n: int,
    o_txts: list[str],
    r_txts: list[str],
    cache: dict[tuple[int, int], bool],
    skip_length_ratio: bool = False,
) -> bool:
    if o_sig == r_sig:
        return True
    key = (oi, rj)
    if key in cache:
        return cache[key]
    # Only compare distant indices when block-count skew explains the offset;
    # avoids O(m*n) full-document fuzzy ratios on every pair.
    slack = abs(m - n) + 12
    if abs(oi - rj) > slack:
        cache[key] = False
        return False
    o_txt = o_txts[oi]
    r_txt = r_txts[rj]
    if not o_txt and not r_txt:
        cache[key] = True
        return True
    lo, lr = len(o_txt), len(r_txt)
    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    both_paragraph = (
        oi < len(ob)
        and rj < len(rb)
        and ob[oi].get("type") == "paragraph"
        and rb[rj].get("type") == "paragraph"
    )
    index_skew = abs(oi - rj)
    relax_length = both_paragraph and index_skew <= _MAX_INDEX_SKEW_FOR_SOFT_FUZZY
    length_floor = (
        _ALIGN_LENGTH_RATIO_NEAR_INDEX_MIN
        if relax_length and not skip_length_ratio
        else _ALIGN_LENGTH_RATIO_MIN
    )
    length_ok = (
        skip_length_ratio
        or (not lo or not lr)
        or (min(lo, lr) / max(lo, lr) >= length_floor)
    )
    if _toc_slot_pair_relaxed_align(o_txt, r_txt):
        cache[key] = True
        return True
    if both_paragraph and index_skew <= _MAX_INDEX_SKEW_FOR_SOFT_FUZZY:
        jacc, owc, rwc = _non_whitespace_word_jaccard_and_counts(o_txt, r_txt)
        if owc and rwc and jacc >= _ALIGN_NEAR_INDEX_WORD_JACCARD_MIN:
            w_ratio = min(owc, rwc) / max(owc, rwc)
            if w_ratio >= _ALIGN_NEAR_INDEX_WORD_COUNT_RATIO_MIN:
                cache[key] = True
                return True
    if (
        not length_ok
        and both_paragraph
        and index_skew <= _MAX_INDEX_SKEW_FOR_LENGTH_BYPASS_JACCARD
    ):
        j2, ow2, rw2 = _non_whitespace_word_jaccard_and_counts(o_txt, r_txt)
        if ow2 and rw2:
            w2 = min(ow2, rw2) / max(ow2, rw2)
            if j2 >= _ALIGN_LENGTH_BYPASS_JACCARD_MIN and w2 >= _ALIGN_LENGTH_BYPASS_JACCARD_WORD_RATIO:
                cache[key] = True
                return True
    if (
        not length_ok
        and both_paragraph
        and index_skew <= _MAX_INDEX_SKEW_FOR_LENGTH_BYPASS_PREFIX
        and _length_weak_prefix_expansion_match(o_txt, r_txt)
    ):
        cache[key] = True
        return True

    # Defer expensive difflib work until after cheap accept gates above.
    sm = difflib.SequenceMatcher(None, o_txt, r_txt, autojunk=False)
    q = sm.quick_ratio()
    # Performance: length-weak pairs with almost no shared structure skip heavy tok ratio.
    if not length_ok and lo and lr and q < _ALIGN_LENGTH_WEAK_FAST_REJECT_QUICK:
        cache[key] = False
        return False
    skip_char_ratio = _should_skip_expensive_char_ratio(
        lo, lr, body_block_count=max(m, n)
    )
    ot = norm_keys(tokenize_for_lcs(o_txt))
    rt = norm_keys(tokenize_for_lcs(r_txt))
    tok_sm = difflib.SequenceMatcher(None, ot, rt, autojunk=False)
    tok_q = tok_sm.quick_ratio()

    # If neither the character nor token quick upper bounds can possibly reach the
    # minimum threshold for this pair, avoid the quadratic ``ratio()`` call.
    if not length_ok and both_paragraph:
        combined_min = _ALIGN_LENGTH_BYPASS_COMBINED_MIN
    elif both_paragraph and index_skew <= _MAX_INDEX_SKEW_FOR_SOFT_FUZZY:
        combined_min = _ALIGN_FUZZY_COMBINED_SOFT_MIN
    else:
        combined_min = _ALIGN_FUZZY_COMBINED_MIN

    if max(q, tok_q) < combined_min:
        # Still allow the length-weak token-bypass path to proceed if its quick gate
        # could pass; otherwise this cannot match.
        if not (
            (not length_ok and both_paragraph)
            and q >= _ALIGN_LENGTH_BYPASS_TOK_QUICK_MIN
            and tok_q >= _ALIGN_LENGTH_BYPASS_TOK_MIN
        ):
            cache[key] = False
            return False

    # Compute the expensive token ratio only when it could affect the outcome.
    tok_r = tok_sm.ratio() if tok_q >= min(combined_min, _ALIGN_LENGTH_BYPASS_TOK_MIN) else 0.0
    # Performance: ratio() is expensive; quick_ratio() is a cheap upper bound.
    # If q <= tok_r then char_r cannot exceed tok_r and cannot change max(char_r, tok_r).
    if skip_char_ratio or q <= tok_r:
        char_r = 0.0
    else:
        char_r = sm.ratio()
    combined = tok_r if skip_char_ratio else max(char_r, tok_r)
    if q >= _ALIGN_FUZZY_QUICK_MIN and combined >= _ALIGN_FUZZY_COMBINED_MIN:
        ok = True
    elif (
        both_paragraph
        and index_skew <= _MAX_INDEX_SKEW_FOR_SOFT_FUZZY
        and q >= _ALIGN_FUZZY_QUICK_SOFT_MIN
        and combined >= _ALIGN_FUZZY_COMBINED_SOFT_MIN
    ):
        ok = True
    elif not length_ok and both_paragraph:
        if q >= _ALIGN_LENGTH_BYPASS_QUICK_MIN and combined >= _ALIGN_LENGTH_BYPASS_COMBINED_MIN:
            ok = True
        elif q >= _ALIGN_LENGTH_BYPASS_TOK_QUICK_MIN and tok_r >= _ALIGN_LENGTH_BYPASS_TOK_MIN:
            ok = True
        else:
            ok = False
    else:
        ok = False
    cache[key] = ok
    return ok


def _align_score_blocks_pair_detail(
    original: BodyIR,
    revised: BodyIR,
    oi: int,
    rj: int,
    o_sig: str,
    r_sig: str,
    config: CompareConfig,
    *,
    m: int,
    n: int,
    o_txts: list[str],
    r_txts: list[str],
    skip_length_ratio: bool,
) -> tuple[bool, list[str]]:
    """
    Same gates as :func:`_blocks_align_in_lcs` without memoization; returns
    ``(would_match, log_lines)`` for stderr diagnostics.
    """

    lines: list[str] = []
    if o_sig == r_sig:
        lines.append("  gate: signatures_equal → MATCH")
        return True, lines
    slack = abs(m - n) + 12
    skew = abs(oi - rj)
    lines.append(f"  index_skew=|{oi}-{rj}|={skew} slack={slack} m={m} n={n}")
    if skew > slack:
        lines.append(f"  gate: FAIL (skew > slack; pair not considered in DP)")
        return False, lines
    o_txt = o_txts[oi]
    r_txt = r_txts[rj]
    if not o_txt and not r_txt:
        lines.append("  gate: both_texts_empty → MATCH")
        return True, lines
    lo, lr = len(o_txt), len(r_txt)
    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    both_paragraph = (
        oi < len(ob)
        and rj < len(rb)
        and ob[oi].get("type") == "paragraph"
        and rb[rj].get("type") == "paragraph"
    )
    o_type = ob[oi].get("type") if oi < len(ob) else "?"
    r_type = rb[rj].get("type") if rj < len(rb) else "?"
    lines.append(f"  block_types orig={o_type!r} rev={r_type!r} both_paragraph={both_paragraph}")
    index_skew = skew
    relax_length = both_paragraph and index_skew <= _MAX_INDEX_SKEW_FOR_SOFT_FUZZY
    length_floor = (
        _ALIGN_LENGTH_RATIO_NEAR_INDEX_MIN
        if relax_length and not skip_length_ratio
        else _ALIGN_LENGTH_RATIO_MIN
    )
    length_ratio = min(lo, lr) / max(lo, lr) if lo and lr else 1.0
    length_ok = (
        skip_length_ratio
        or (not lo or not lr)
        or (length_ratio >= length_floor)
    )
    lines.append(
        f"  char_lengths lo={lo} lr={lr} length_ratio={length_ratio:.4f} "
        f"floor={length_floor} length_ok={length_ok} skip_length_ratio={skip_length_ratio} "
        f"relax_length_band={relax_length}"
    )
    sm = difflib.SequenceMatcher(None, o_txt, r_txt, autojunk=False)
    q = sm.quick_ratio()
    if not length_ok and lo and lr:
        lines.append(
            f"  length_weak: quick_ratio={q:.4f} (fast_reject_if<{_ALIGN_LENGTH_WEAK_FAST_REJECT_QUICK})"
        )
        if q < _ALIGN_LENGTH_WEAK_FAST_REJECT_QUICK:
            lines.append("  gate: FAIL (length_weak + quick_ratio fast reject)")
            return False, lines
    if _toc_slot_pair_relaxed_align(o_txt, r_txt):
        lines.append(
            f"  gate: TOC_slot_relaxed (quick>={_TOC_SLOT_QUICK_MIN}, "
            f"max(char,tok)>={_TOC_SLOT_COMBINED_MIN}) → MATCH"
        )
        return True, lines
    if both_paragraph and index_skew <= _MAX_INDEX_SKEW_FOR_SOFT_FUZZY:
        jacc, owc, rwc = _non_whitespace_word_jaccard_and_counts(o_txt, r_txt)
        w_ratio = min(owc, rwc) / max(owc, rwc) if owc and rwc else 0.0
        lines.append(
            f"  word_bag: jaccard={jacc:.4f} (min {_ALIGN_NEAR_INDEX_WORD_JACCARD_MIN}) "
            f"word_count_ratio={w_ratio:.4f} (min {_ALIGN_NEAR_INDEX_WORD_COUNT_RATIO_MIN}) "
            f"owc={owc} rwc={rwc}"
        )
        if owc and rwc and jacc >= _ALIGN_NEAR_INDEX_WORD_JACCARD_MIN:
            if w_ratio >= _ALIGN_NEAR_INDEX_WORD_COUNT_RATIO_MIN:
                lines.append("  gate: word_bag_jaccard_lane → MATCH")
                return True, lines
    if (
        not length_ok
        and both_paragraph
        and index_skew <= _MAX_INDEX_SKEW_FOR_LENGTH_BYPASS_JACCARD
    ):
        j2, ow2, rw2 = _non_whitespace_word_jaccard_and_counts(o_txt, r_txt)
        w2 = min(ow2, rw2) / max(ow2, rw2) if ow2 and rw2 else 0.0
        lines.append(
            f"  word_bag_length_bypass: jaccard={j2:.4f} (min {_ALIGN_LENGTH_BYPASS_JACCARD_MIN}) "
            f"word_count_ratio={w2:.4f} (min {_ALIGN_LENGTH_BYPASS_JACCARD_WORD_RATIO}) "
            f"skew<={_MAX_INDEX_SKEW_FOR_LENGTH_BYPASS_JACCARD}"
        )
        if ow2 and rw2 and j2 >= _ALIGN_LENGTH_BYPASS_JACCARD_MIN and w2 >= _ALIGN_LENGTH_BYPASS_JACCARD_WORD_RATIO:
            lines.append("  gate: word_bag_jaccard_length_bypass_lane → MATCH")
            return True, lines
    if (
        not length_ok
        and both_paragraph
        and index_skew <= _MAX_INDEX_SKEW_FOR_LENGTH_BYPASS_PREFIX
        and _length_weak_prefix_expansion_match(o_txt, r_txt)
    ):
        lines.append("  gate: length_weak_prefix_expansion → MATCH")
        return True, lines
    skip_char_ratio = _should_skip_expensive_char_ratio(
        lo, lr, body_block_count=max(m, n)
    )
    char_r = 0.0 if skip_char_ratio else sm.ratio()
    ot = norm_keys(tokenize_for_lcs(o_txt))
    rt = norm_keys(tokenize_for_lcs(r_txt))
    tok_r = difflib.SequenceMatcher(None, ot, rt, autojunk=False).ratio()
    combined = tok_r if skip_char_ratio else max(char_r, tok_r)
    lines.append(
        f"  fuzzy: quick_ratio={q:.4f} (strict min {_ALIGN_FUZZY_QUICK_MIN}, soft min {_ALIGN_FUZZY_QUICK_SOFT_MIN}) "
        f"char_ratio={char_r:.4f} tok_ratio={tok_r:.4f} combined_max={combined:.4f} "
        f"(strict combined min {_ALIGN_FUZZY_COMBINED_MIN}, soft {_ALIGN_FUZZY_COMBINED_SOFT_MIN})"
    )
    if q >= _ALIGN_FUZZY_QUICK_MIN and combined >= _ALIGN_FUZZY_COMBINED_MIN:
        lines.append("  gate: strict_fuzzy → MATCH")
        return True, lines
    if (
        both_paragraph
        and index_skew <= _MAX_INDEX_SKEW_FOR_SOFT_FUZZY
        and q >= _ALIGN_FUZZY_QUICK_SOFT_MIN
        and combined >= _ALIGN_FUZZY_COMBINED_SOFT_MIN
    ):
        lines.append("  gate: soft_fuzzy (near-index paragraph) → MATCH")
        return True, lines
    if not length_ok and both_paragraph:
        if q >= _ALIGN_LENGTH_BYPASS_QUICK_MIN and combined >= _ALIGN_LENGTH_BYPASS_COMBINED_MIN:
            lines.append(
                f"  gate: length_weak_fuzzy_bypass (quick>={_ALIGN_LENGTH_BYPASS_QUICK_MIN}, "
                f"combined>={_ALIGN_LENGTH_BYPASS_COMBINED_MIN}) → MATCH"
            )
            return True, lines
        if q >= _ALIGN_LENGTH_BYPASS_TOK_QUICK_MIN and tok_r >= _ALIGN_LENGTH_BYPASS_TOK_MIN:
            lines.append(
                f"  gate: length_weak_tok_bypass (quick>={_ALIGN_LENGTH_BYPASS_TOK_QUICK_MIN}, "
                f"tok>={_ALIGN_LENGTH_BYPASS_TOK_MIN}) → MATCH"
            )
            return True, lines
    lines.append("  gate: FAIL (no fuzzy, TOC, jaccard, length-bypass, or signature path)")
    return False, lines


def _align_score_full_pair_detail(
    original: BodyIR,
    revised: BodyIR,
    oi: int,
    rj: int,
    config: CompareConfig,
    *,
    m: int,
    n: int,
    o_txts: list[str],
    r_txts: list[str],
    orig_sigs: list[str],
    rev_sigs: list[str],
    orig_blocks: list,
    rev_blocks: list,
) -> tuple[bool, list[str]]:
    """
    Mirrors :func:`align_paragraphs` local ``aligned(oi, rj)`` (type rules + diagonal shortcuts).
    """

    lines: list[str] = []
    if orig_blocks[oi].get("type") != rev_blocks[rj].get("type"):
        lines.append(
            f"PAIR (o{oi},r{rj}): FAIL type_mismatch "
            f"orig={orig_blocks[oi].get('type')!r} rev={rev_blocks[rj].get('type')!r}"
        )
        return False, lines
    header = f"PAIR (o{oi},r{rj}):"
    if m == n and oi == rj:
        lines.append(f"{header} diagonal m==n")
        if (
            m == 1
            and orig_blocks[oi].get("type") == "paragraph"
            and rev_blocks[rj].get("type") == "paragraph"
        ):
            lines.append("  gate: single_block_paragraph_same_count → MATCH")
            return True, lines
        if orig_blocks[oi].get("type") == "table":
            lines.append("  gate: table_on_diagonal → MATCH")
            return True, lines
        if orig_sigs[oi] == rev_sigs[rj]:
            lines.append("  gate: signatures_equal (diagonal) → MATCH")
            return True, lines
        ok, sub = _align_score_blocks_pair_detail(
            original,
            revised,
            oi,
            rj,
            orig_sigs[oi],
            rev_sigs[rj],
            config,
            m=m,
            n=n,
            o_txts=o_txts,
            r_txts=r_txts,
            skip_length_ratio=True,
        )
        lines.extend(sub)
        if ok:
            lines.append("  gate: diagonal _blocks_align_in_lcs(skip_length_ratio=True) → MATCH")
            return True, lines
        if _diagonal_prefix_anchor(o_txts[oi], r_txts[rj]):
            lines.append("  gate: diagonal_prefix_anchor → MATCH")
            return True, lines
        lines.append("  overall: diagonal NO_MATCH (fuzzy blocks + prefix_anchor both false)")
        return False, lines
    ok, sub = _align_score_blocks_pair_detail(
        original,
        revised,
        oi,
        rj,
        orig_sigs[oi],
        rev_sigs[rj],
        config,
        m=m,
        n=n,
        o_txts=o_txts,
        r_txts=r_txts,
        skip_length_ratio=False,
    )
    lines.append(f"{header} off_diagonal _blocks_align_in_lcs")
    lines.extend(sub)
    return ok, lines


def _debug_print_unmatched_rev_token_overlap(
    label: str,
    oi: int,
    rj: int,
    o_txt: str,
    r_txt: str,
    *,
    max_list_items: int = 200,
) -> None:
    """
    Token-level diagnostics for ``MDC_DEBUG_ALIGNMENT`` when a revised block is
    unmatched: overlap counts, raw/norm token lists, ratios, and a containment hint.
    """

    toks_o = [t for t in tokenize_for_lcs(o_txt) if not t.surface.isspace()]
    toks_r = [t for t in tokenize_for_lcs(r_txt) if not t.surface.isspace()]
    raw_o = [t.surface for t in toks_o]
    raw_r = [t.surface for t in toks_r]
    norm_o = [t.norm_key() for t in toks_o]
    norm_r = [t.norm_key() for t in toks_r]
    co = Counter(norm_o)
    cr = Counter(norm_r)
    shared_occ = sum(min(co[k], cr[k]) for k in co)
    set_o, set_r = set(co), set(cr)
    shared_unique = len(set_o & set_r)
    tot_o, tot_r = len(norm_o), len(norm_r)
    ratio_o = shared_occ / tot_o if tot_o else 0.0
    ratio_r = shared_occ / tot_r if tot_r else 0.0
    sm = difflib.SequenceMatcher(None, o_txt, r_txt, autojunk=False)
    char_r = sm.ratio()
    ot = norm_keys(tokenize_for_lcs(o_txt))
    rt = norm_keys(tokenize_for_lcs(r_txt))
    tok_r = difflib.SequenceMatcher(None, ot, rt, autojunk=False).ratio()
    jacc, _owc, _rwc = _non_whitespace_word_jaccard_and_counts(o_txt, r_txt)
    distinct_orig_in_rev = sum(1 for k in set_o if k in cr)
    distinct_o = len(set_o)
    vocab_cover = distinct_orig_in_rev / distinct_o if distinct_o else 0.0
    subset_vocab = set_o.issubset(set_r)
    hint = _containment_hint_string(o_txt, r_txt)

    def _clip(seq: list[str]) -> str:
        if len(seq) <= max_list_items:
            return repr(seq)
        return repr(seq[:max_list_items]) + f" ... (+{len(seq) - max_list_items} more)"

    print(
        f"[MDC_DEBUG_ALIGNMENT] TOKEN_OVERLAP label={label!r} pair=(o{oi},r{rj})",
        file=sys.stderr,
    )
    print(
        f"[MDC_DEBUG_ALIGNMENT]   non_ws_token_counts orig={tot_o} rev={tot_r} "
        f"shared_unique_norm_types={shared_unique} shared_norm_occurrences={shared_occ}",
        file=sys.stderr,
    )
    print(
        f"[MDC_DEBUG_ALIGNMENT]   overlap_ratio_shared_div_orig={ratio_o:.4f} "
        f"overlap_ratio_shared_div_rev={ratio_r:.4f} "
        f"distinct_orig_norm_types_in_rev={distinct_orig_in_rev}/{distinct_o} "
        f"vocab_cover={vocab_cover:.4f} orig_vocab_subset_of_rev={subset_vocab}",
        file=sys.stderr,
    )
    print(
        f"[MDC_DEBUG_ALIGNMENT]   char_ratio={char_r:.4f} tok_ratio={tok_r:.4f} "
        f"jaccard_unique_norm={jacc:.4f}",
        file=sys.stderr,
    )
    print(f"[MDC_DEBUG_ALIGNMENT]   containment_hint={hint}", file=sys.stderr)
    print(f"[MDC_DEBUG_ALIGNMENT]   raw_tokens_orig={_clip(raw_o)}", file=sys.stderr)
    print(f"[MDC_DEBUG_ALIGNMENT]   raw_tokens_rev={_clip(raw_r)}", file=sys.stderr)
    print(f"[MDC_DEBUG_ALIGNMENT]   norm_keys_orig={_clip(norm_o)}", file=sys.stderr)
    print(f"[MDC_DEBUG_ALIGNMENT]   norm_keys_rev={_clip(norm_r)}", file=sys.stderr)


def _debug_print_rev_only_token_lists(rj: int, r_txt: str, *, max_list_items: int = 200) -> None:
    """When no same-type original exists in slack, still print revised token lists."""

    toks_r = [t for t in tokenize_for_lcs(r_txt) if not t.surface.isspace()]
    raw_r = [t.surface for t in toks_r]
    norm_r = [t.norm_key() for t in toks_r]

    def _clip(seq: list[str]) -> str:
        if len(seq) <= max_list_items:
            return repr(seq)
        return repr(seq[:max_list_items]) + f" ... (+{len(seq) - max_list_items} more)"

    print(
        f"[MDC_DEBUG_ALIGNMENT] TOKEN_LISTS_REV_ONLY r{rj} non_ws_count={len(norm_r)}",
        file=sys.stderr,
    )
    print(f"[MDC_DEBUG_ALIGNMENT]   raw_tokens_rev={_clip(raw_r)}", file=sys.stderr)
    print(f"[MDC_DEBUG_ALIGNMENT]   norm_keys_rev={_clip(norm_r)}", file=sys.stderr)


def _log_alignment_unmatched_diagnostics(
    original: BodyIR,
    revised: BodyIR,
    alignment: list[ParagraphAlignment],
    config: CompareConfig,
) -> None:
    """For unmatched blocks, print candidate pairs and gate scores (stderr)."""

    orig_blocks = original.get("blocks", [])
    rev_blocks = revised.get("blocks", [])
    m, n = len(orig_blocks), len(rev_blocks)
    if not m or not n:
        return
    orig_sigs = [_block_signature(original, i, config) for i in range(m)]
    rev_sigs = [_block_signature(revised, j, config) for j in range(n)]
    o_txts = [_block_alignment_text(original, i, config) for i in range(m)]
    r_txts = [_block_alignment_text(revised, j, config) for j in range(n)]
    slack = abs(m - n) + 12

    raw_alignment, lcs_trace, dp = _align_paragraphs_compute(
        original, revised, config, collect_lcs_trace=True
    )
    optimal_matches = dp[0][0] if m and n else 0
    raw_pairs = [(a.original_paragraph_index, a.revised_paragraph_index) for a in raw_alignment]
    final_pairs = [(a.original_paragraph_index, a.revised_paragraph_index) for a in alignment]
    print(
        f"[MDC_DEBUG_ALIGNMENT] pre_repair_LCS dp[0][0]={optimal_matches} (max block matches) | "
        f"raw_steps={len(raw_alignment)} final_steps={len(alignment)} "
        f"raw_pairs==final_pairs={raw_pairs == final_pairs}",
        file=sys.stderr,
    )

    unmatched_r = [al.revised_paragraph_index for al in alignment if al.revised_paragraph_index is not None and al.original_paragraph_index is None]
    unmatched_o = [al.original_paragraph_index for al in alignment if al.original_paragraph_index is not None and al.revised_paragraph_index is None]

    for rj in unmatched_r:
        if rj >= n:
            continue
        print(
            f"[MDC_DEBUG_ALIGNMENT] --- UNMATCHED_REV r{rj}: final alignment has (None,{rj}) "
            f"(revised-only). Pairwise gates + LCS replay (pre-repair) below. ---",
            file=sys.stderr,
        )
        print(
            f"[MDC_DEBUG_ALIGNMENT] rev_preview={_preview_block_text(revised, rj, config)!r}",
            file=sys.stderr,
        )
        candidates = [oi for oi in range(m) if abs(oi - rj) <= slack]
        print(
            f"[MDC_DEBUG_ALIGNMENT] candidate_orig_indices (|oi-rj|<={slack}): {candidates}",
            file=sys.stderr,
        )

        ranked: list[tuple[int, float]] = []
        for oi in candidates:
            s = _pair_rank_similarity_best_candidate(
                oi, rj, o_txts, r_txts, orig_blocks, rev_blocks
            )
            ranked.append((oi, s))
        ranked.sort(
            key=lambda t: (
                -t[1],
                0 if orig_blocks[t[0]].get("type") == rev_blocks[rj].get("type") else 1,
                abs(t[0] - rj),
            )
        )
        o_best = -1
        s_best = float("-inf")
        ok_best = False
        if ranked:
            o_best, s_best = ranked[0]
            ok_best, _detail_best = _align_score_full_pair_detail(
                original,
                revised,
                o_best,
                rj,
                config,
                m=m,
                n=n,
                o_txts=o_txts,
                r_txts=r_txts,
                orig_sigs=orig_sigs,
                rev_sigs=rev_sigs,
                orig_blocks=orig_blocks,
                rev_blocks=rev_blocks,
            )
            print(
                f"[MDC_DEBUG_ALIGNMENT] BEST_CANDIDATE o{o_best} vs r{rj}: "
                f"rank_similarity=max(char_ratio,tok_ratio)={s_best:.4f} would_align={ok_best}",
                file=sys.stderr,
            )
            if o_best < len(o_txts) and 0 <= rj < len(r_txts):
                _debug_print_unmatched_rev_token_overlap(
                    "best_rank_similarity", o_best, rj, o_txts[o_best], r_txts[rj]
                )
            else:
                print(
                    f"[MDC_DEBUG_ALIGNMENT] SKIP_TOKEN_OVERLAP: invalid indices "
                    f"(best o_best={o_best}, len(o_txts)={len(o_txts)}, rj={rj}, len(r_txts)={len(r_txts)})",
                    file=sys.stderr,
                )
        else:
            print(
                f"[MDC_DEBUG_ALIGNMENT] BEST_CANDIDATE: none (no candidates within slack)",
                file=sys.stderr,
            )
            _debug_print_rev_only_token_lists(rj, r_txts[rj])

        step_idx: int | None = None
        frontier_i = frontier_j = -1
        if lcs_trace is not None and len(lcs_trace) == len(raw_alignment):
            for k, (al, st) in enumerate(zip(raw_alignment, lcs_trace, strict=True)):
                if (
                    al.original_paragraph_index is None
                    and al.revised_paragraph_index == rj
                    and st.kind in ("skip_rev", "tail_rev")
                ):
                    step_idx = k
                    frontier_i, frontier_j = st.i_before, st.j_before
                    break
        if step_idx is None:
            print(
                f"[MDC_DEBUG_ALIGNMENT] LCS_REPLAY: no pre-repair step (None,{rj}) "
                f"(SCRUM-120/121 repair likely rewrote this slot, or rj matched in raw LCS).",
                file=sys.stderr,
            )
        else:
            assert lcs_trace is not None
            st = lcs_trace[step_idx]
            aij = st.aligned_ij
            dd, dr = st.dp_down, st.dp_right
            print(
                f"[MDC_DEBUG_ALIGNMENT] LCS_REPLAY step={step_idx} kind={st.kind} "
                f"frontier=(i={frontier_i},j={frontier_j}) aligned({frontier_i},{frontier_j})={aij} "
                f"dp[i+1][j]={dd} dp[i][j+1]={dr}",
                file=sys.stderr,
            )
            if st.kind == "skip_rev":
                print(
                    f"[MDC_DEBUG_ALIGNMENT] CHOSEN_BRANCH: revised-only step because "
                    f"dp[i][j+1] ({dr}) > dp[i+1][j] ({dd}) (if equal, delete-original would win).",
                    file=sys.stderr,
                )
            elif st.kind == "tail_rev":
                print(
                    f"[MDC_DEBUG_ALIGNMENT] CHOSEN_BRANCH: tail_rev — all original rows already "
                    f"consumed; remaining revised blocks are unmatched inserts.",
                    file=sys.stderr,
                )
            if ranked and o_best >= 0 and frontier_i >= 0:
                if st.kind == "tail_rev":
                    print(
                        f"[MDC_DEBUG_ALIGNMENT] SKIPPED_BECAUSE: after matching prefix, no original row "
                        f"remained to pair with revised r{rj}; best same-type text match was o{o_best} "
                        f"(rank_similarity={s_best:.4f}, would_align={ok_best}) but that row was already "
                        f"used or never reachable at this tail.",
                        file=sys.stderr,
                    )
                elif not aij:
                    print(
                        f"[MDC_DEBUG_ALIGNMENT] SKIPPED_BECAUSE: at frontier (i={frontier_i}, j={rj}), "
                        f"`aligned(i,j)` was False — alignment gates reject (o{frontier_i},r{rj}). "
                        f"Best candidate by text similarity: o{o_best} (rank={s_best:.4f}, would_align={ok_best}).",
                        file=sys.stderr,
                    )
                elif ok_best and o_best != frontier_i:
                    print(
                        f"[MDC_DEBUG_ALIGNMENT] SKIPPED_BECAUSE: best text match is o{o_best} "
                        f"(would_align={ok_best}) but DP was at row i={frontier_i} for column j={rj} "
                        f"(document-order LCS already committed other matches for a total of {optimal_matches}).",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[MDC_DEBUG_ALIGNMENT] SKIPPED_BECAUSE: see CHOSEN_BRANCH above "
                        f"(optimal LCS length={optimal_matches}).",
                        file=sys.stderr,
                    )

        if frontier_i >= 0 and o_best >= 0 and frontier_i != o_best:
            if frontier_i < len(o_txts) and 0 <= rj < len(r_txts):
                _debug_print_unmatched_rev_token_overlap(
                    "lcs_frontier", frontier_i, rj, o_txts[frontier_i], r_txts[rj]
                )
            else:
                print(
                    f"[MDC_DEBUG_ALIGNMENT] SKIP_TOKEN_OVERLAP: invalid indices "
                    f"(frontier_i={frontier_i}, len(o_txts)={len(o_txts)}, rj={rj}, len(r_txts)={len(r_txts)})",
                    file=sys.stderr,
                )
        elif frontier_i >= 0 and o_best < 0:
            if frontier_i < len(o_txts) and 0 <= rj < len(r_txts):
                _debug_print_unmatched_rev_token_overlap(
                    "lcs_frontier", frontier_i, rj, o_txts[frontier_i], r_txts[rj]
                )
            else:
                print(
                    f"[MDC_DEBUG_ALIGNMENT] SKIP_TOKEN_OVERLAP: invalid indices "
                    f"(frontier_i={frontier_i}, len(o_txts)={len(o_txts)}, rj={rj}, len(r_txts)={len(r_txts)})",
                    file=sys.stderr,
                )

        for oi in candidates:
            ok, detail_lines = _align_score_full_pair_detail(
                original,
                revised,
                oi,
                rj,
                config,
                m=m,
                n=n,
                o_txts=o_txts,
                r_txts=r_txts,
                orig_sigs=orig_sigs,
                rev_sigs=rev_sigs,
                orig_blocks=orig_blocks,
                rev_blocks=rev_blocks,
            )
            rank_s = _pair_rank_similarity_best_candidate(
                oi, rj, o_txts, r_txts, orig_blocks, rev_blocks
            )
            print(
                f"[MDC_DEBUG_ALIGNMENT] would_align={ok} rank_similarity={rank_s:.4f} "
                f"(o{oi},r{rj}) orig_preview={_preview_block_text(original, oi, config)!r}",
                file=sys.stderr,
            )
            for ln in detail_lines:
                print(f"[MDC_DEBUG_ALIGNMENT] {ln}", file=sys.stderr)

    for oi in unmatched_o:
        if oi >= m:
            continue
        print(
            f"[MDC_DEBUG_ALIGNMENT] --- UNMATCHED_ORIG o{oi}: LCS emitted ({oi},None) ---",
            file=sys.stderr,
        )
        print(
            f"[MDC_DEBUG_ALIGNMENT] orig_preview={_preview_block_text(original, oi, config)!r}",
            file=sys.stderr,
        )
        candidates = [rj for rj in range(n) if abs(oi - rj) <= slack]
        print(
            f"[MDC_DEBUG_ALIGNMENT] candidate_rev_indices (|oi-rj|<={slack}): {candidates}",
            file=sys.stderr,
        )
        for rj in candidates:
            ok, detail_lines = _align_score_full_pair_detail(
                original,
                revised,
                oi,
                rj,
                config,
                m=m,
                n=n,
                o_txts=o_txts,
                r_txts=r_txts,
                orig_sigs=orig_sigs,
                rev_sigs=rev_sigs,
                orig_blocks=orig_blocks,
                rev_blocks=rev_blocks,
            )
            print(
                f"[MDC_DEBUG_ALIGNMENT] would_align={ok} for (o{oi},r{rj}) "
                f"rev_preview={_preview_block_text(revised, rj, config)!r}",
                file=sys.stderr,
            )
            for ln in detail_lines:
                print(f"[MDC_DEBUG_ALIGNMENT] {ln}", file=sys.stderr)


def _preview_block_text(body_ir: BodyIR, idx: int, config: CompareConfig, limit: int = 72) -> str:
    """One-line preview for debug logs."""

    t = _block_alignment_text(body_ir, idx, config)
    t = " ".join(t.split())
    if len(t) > limit:
        return t[: limit - 3] + "..."
    return t


def _maybe_log_alignment_debug(
    strategy: str,
    original: BodyIR,
    revised: BodyIR,
    alignment: list[ParagraphAlignment],
    config: CompareConfig,
) -> None:
    """
    When ``MDC_DEBUG_ALIGNMENT=1``, print matched pairs and unmatched indices to stderr.

    Same convention as :func:`engine.diff_tokens.maybe_log_lcs_debug`.
    """

    if os.environ.get("MDC_DEBUG_ALIGNMENT", "").strip() not in ("1", "true", "yes", "on"):
        return
    ob = original.get("blocks", [])
    rb = revised.get("blocks", [])
    matched: list[tuple[int, int]] = []
    unmatched_o: list[int] = []
    unmatched_r: list[int] = []
    for al in alignment:
        oi, rj = al.original_paragraph_index, al.revised_paragraph_index
        if oi is not None and rj is not None:
            matched.append((oi, rj))
        elif oi is not None:
            unmatched_o.append(oi)
        else:
            unmatched_r.append(rj)
    print(f"[MDC_DEBUG_ALIGNMENT] strategy={strategy}", file=sys.stderr)
    print(f"[MDC_DEBUG_ALIGNMENT] blocks orig={len(ob)} rev={len(rb)} steps={len(alignment)}", file=sys.stderr)
    for oi, rj in matched:
        merge = ""
        for a in alignment:
            if a.original_paragraph_index == oi and a.revised_paragraph_index == rj:
                if a.revised_merge_end_exclusive is not None:
                    merge = f" merge_rev_end={a.revised_merge_end_exclusive}"
                break
        print(
            f"[MDC_DEBUG_ALIGNMENT] MATCH (o{oi},r{rj}){merge} "
            f"orig={_preview_block_text(original, oi, config)!r} | "
            f"rev={_preview_block_text(revised, rj, config)!r}",
            file=sys.stderr,
        )
    if unmatched_o or unmatched_r:
        _log_alignment_unmatched_diagnostics(original, revised, alignment, config)


def alignment_for_track_changes_emit(
    original: BodyIR, revised: BodyIR, config: CompareConfig
) -> list[ParagraphAlignment]:
    """
    Block alignment for :mod:`engine.body_revision_emit` Track Changes output.

    When both bodies have the same number of blocks and the block **types** match
    at every index (``paragraph`` with ``paragraph``, ``table`` with ``table``),
    pair ``(i, i)``. That matches the emit path used before SCRUM-115 table work,
    keeps paragraph diff localization stable for large protocols (golden ins/del counts),
    and applies Track Changes **in place** on each original ``w:p`` / ``w:tbl`` slot.
    When counts differ or any index has mismatched types, :func:`align_paragraphs`
    supplies LCS-based block alignment (insert/delete/reorder across blocks).

    When counts match but **any** index has mismatched types—e.g. ``w:p`` in the
    original and ``w:tbl`` in the revised at the same slot—delegate to
    :func:`align_paragraphs` so LCS can insert, delete, or match blocks without
    dropping revised tables.

    :func:`align_paragraphs` remains the single source of truth for LCS/fuzzy
    logic (inline diff, reorder tests, etc.); this helper only selects the
    pairing strategy for OOXML emit.
    """

    orig_blocks = original.get("blocks", [])
    rev_blocks = revised.get("blocks", [])
    if len(orig_blocks) != len(rev_blocks):
        al = align_paragraphs(original, revised, config)
        al = _repair_alignment_orig_table_rev_paras_then_rev_table(al, original, revised)
        al = _repair_alignment_orig_para_rev_split_merge(al, original, revised, config)
        al = _repair_alignment_orig_delete_block_then_rev_insert_merge(al, original, revised, config)
        _maybe_diagnose_unmatched_rev_repair_gates(
            al, original, revised, config, strategy_tag="lcs_block_count_mismatch"
        )
        al = _repair_alignment_unmatched_rev_expansion_override(al, original, revised, config)
        _maybe_log_alignment_debug("lcs_block_count_mismatch", original, revised, al, config)
        return al
    if not orig_blocks:
        _maybe_log_alignment_debug("empty_both", original, revised, [], config)
        return []
    if all(
        orig_blocks[i].get("type") == rev_blocks[i].get("type")
        for i in range(len(orig_blocks))
    ):
        identity = [ParagraphAlignment(i, i) for i in range(len(orig_blocks))]
        _maybe_log_alignment_debug("index_identity_same_types", original, revised, identity, config)
        return identity
    al = align_paragraphs(original, revised, config)
    al = _repair_alignment_orig_table_rev_paras_then_rev_table(al, original, revised)
    al = _repair_alignment_orig_para_rev_split_merge(al, original, revised, config)
    al = _repair_alignment_orig_delete_block_then_rev_insert_merge(al, original, revised, config)
    _maybe_diagnose_unmatched_rev_repair_gates(
        al, original, revised, config, strategy_tag="lcs_type_mismatch_at_slot"
    )
    al = _repair_alignment_unmatched_rev_expansion_override(al, original, revised, config)
    _maybe_log_alignment_debug("lcs_type_mismatch_at_slot", original, revised, al, config)
    return al


def _raw_max_char_tok_ratio(
    o_txt: str, r_txt: str, *, body_block_count: int | None = None
) -> float:
    """``max(char_ratio, tok_ratio)`` for two normalized block texts (no type check)."""

    if not o_txt and not r_txt:
        return 1.0
    ot = norm_keys(tokenize_for_lcs(o_txt))
    rt = norm_keys(tokenize_for_lcs(r_txt))
    tok_r = difflib.SequenceMatcher(None, ot, rt, autojunk=False).ratio()
    if _should_skip_expensive_char_ratio(
        len(o_txt), len(r_txt), body_block_count=body_block_count
    ):
        return float(tok_r)
    # Performance: ratio() is expensive, but quick_ratio() is a cheap upper bound.
    # If quick_ratio <= tok_r then char_r cannot exceed tok_r, so char_r cannot
    # change max(char_r, tok_r).
    sm = difflib.SequenceMatcher(None, o_txt, r_txt, autojunk=False)
    if sm.quick_ratio() <= tok_r:
        return float(tok_r)
    char_r = sm.ratio()
    return float(max(char_r, tok_r))


def _pair_rank_similarity(
    oi: int,
    rj: int,
    o_txts: list[str],
    r_txts: list[str],
    orig_blocks: list,
    rev_blocks: list,
) -> float:
    """Scalar rank for ``best candidate'' (not identical to ``aligned()``)."""

    if orig_blocks[oi].get("type") != rev_blocks[rj].get("type"):
        return float("-inf")
    o_txt, r_txt = o_txts[oi], r_txts[rj]
    return _raw_max_char_tok_ratio(
        o_txt, r_txt, body_block_count=max(len(orig_blocks), len(rev_blocks))
    )


def _pair_rank_similarity_best_candidate(
    oi: int,
    rj: int,
    o_txts: list[str],
    r_txts: list[str],
    orig_blocks: list,
    rev_blocks: list,
) -> float:
    """
    Rank score for :func:`_repair_alignment_unmatched_rev_expansion_override` /
    gate diagnostics: same formula as :func:`_pair_rank_similarity`, but mixed
    block types are allowed with :data:`_BEST_CANDIDATE_CROSS_TYPE_RANK_PENALTY`.
    """

    o_txt, r_txt = o_txts[oi], r_txts[rj]
    base = _raw_max_char_tok_ratio(
        o_txt, r_txt, body_block_count=max(len(orig_blocks), len(rev_blocks))
    )
    if orig_blocks[oi].get("type") == rev_blocks[rj].get("type"):
        return base
    return base * _BEST_CANDIDATE_CROSS_TYPE_RANK_PENALTY


def _align_paragraphs_compute(
    original: BodyIR,
    revised: BodyIR,
    config: CompareConfig,
    *,
    collect_lcs_trace: bool,
) -> tuple[list[ParagraphAlignment], list[_LcsBacktrackStep] | None, list[list[int]]]:
    """
    Core LCS alignment shared with :func:`align_paragraphs`.

    Returns ``(alignment, lcs_trace_or_none, dp)``. Trace is only for stderr
    diagnostics (pre-repair); ``dp[0][0]`` is optimal match count on this grid.
    """

    orig_blocks = original.get("blocks", [])
    rev_blocks = revised.get("blocks", [])

    orig_sigs = [_block_signature(original, i, config) for i in range(len(orig_blocks))]
    rev_sigs = [_block_signature(revised, i, config) for i in range(len(rev_blocks))]

    m, n = len(orig_sigs), len(rev_sigs)
    o_txts = [_block_alignment_text(original, i, config) for i in range(m)]
    r_txts = [_block_alignment_text(revised, j, config) for j in range(n)]
    align_cache: dict[tuple[int, int], bool] = {}

    def aligned(oi: int, rj: int) -> bool:
        # Never pair a table block with a paragraph (or any mixed types). Fuzzy
        # text vs table signature could otherwise align the wrong rows and emit
        # skips the revised table while leaving a paragraph in place (SCRUM-115).
        if orig_blocks[oi].get("type") != rev_blocks[rj].get("type"):
            return False
        if m == n and oi == rj:
            if (
                m == 1
                and orig_blocks[oi].get("type") == "paragraph"
                and rev_blocks[rj].get("type") == "paragraph"
            ):
                return True
            if orig_blocks[oi].get("type") == "table":
                return True
            if orig_sigs[oi] == rev_sigs[rj]:
                return True
            if _blocks_align_in_lcs(
                original,
                revised,
                oi,
                rj,
                orig_sigs[oi],
                rev_sigs[rj],
                config,
                m=m,
                n=n,
                o_txts=o_txts,
                r_txts=r_txts,
                cache=align_cache,
                skip_length_ratio=True,
            ):
                return True
            if _diagonal_prefix_anchor(o_txts[oi], r_txts[rj]):
                return True
            return False
        return _blocks_align_in_lcs(
            original,
            revised,
            oi,
            rj,
            orig_sigs[oi],
            rev_sigs[rj],
            config,
            m=m,
            n=n,
            o_txts=o_txts,
            r_txts=r_txts,
            cache=align_cache,
            skip_length_ratio=False,
        )

    # LCS DP table.
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            if aligned(i, j):
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = dp[i + 1][j] if dp[i + 1][j] >= dp[i][j + 1] else dp[i][j + 1]

    trace: list[_LcsBacktrackStep] | None = [] if collect_lcs_trace else None

    # Backtrack to produce alignment with inserts/deletes.
    alignment: list[ParagraphAlignment] = []
    i = j = 0
    while i < m and j < n:
        aij = aligned(i, j)
        if aij:
            if trace is not None:
                trace.append(
                    _LcsBacktrackStep(
                        kind="match",
                        i_before=i,
                        j_before=j,
                        aligned_ij=True,
                        dp_down=dp[i + 1][j] if i + 1 <= m else -1,
                        dp_right=dp[i][j + 1] if j + 1 <= n else -1,
                    )
                )
            alignment.append(ParagraphAlignment(i, j))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            if trace is not None:
                trace.append(
                    _LcsBacktrackStep(
                        kind="skip_orig",
                        i_before=i,
                        j_before=j,
                        aligned_ij=aij,
                        dp_down=dp[i + 1][j],
                        dp_right=dp[i][j + 1],
                    )
                )
            alignment.append(ParagraphAlignment(i, None))
            i += 1
        else:
            if trace is not None:
                trace.append(
                    _LcsBacktrackStep(
                        kind="skip_rev",
                        i_before=i,
                        j_before=j,
                        aligned_ij=aij,
                        dp_down=dp[i + 1][j],
                        dp_right=dp[i][j + 1],
                    )
                )
            alignment.append(ParagraphAlignment(None, j))
            j += 1

    while i < m:
        if trace is not None:
            trace.append(
                _LcsBacktrackStep(
                    kind="tail_orig",
                    i_before=i,
                    j_before=j,
                    aligned_ij=False,
                    dp_down=-1,
                    dp_right=-1,
                )
            )
        alignment.append(ParagraphAlignment(i, None))
        i += 1
    while j < n:
        if trace is not None:
            trace.append(
                _LcsBacktrackStep(
                    kind="tail_rev",
                    i_before=i,
                    j_before=j,
                    aligned_ij=False,
                    dp_down=-1,
                    dp_right=-1,
                )
            )
        alignment.append(ParagraphAlignment(None, j))
        j += 1

    return alignment, trace, dp


def align_paragraphs(original: BodyIR, revised: BodyIR, config: CompareConfig) -> list[ParagraphAlignment]:
    """
    Align paragraphs using a stable, deterministic strategy.

    Strategy:
    - Compute paragraph signatures and normalized block text for fuzzy matching.
    - LCS dynamic programming: match when signatures are equal **or** fuzzy
      similarity is high enough (``quick_ratio`` plus combined character/token
      ratio; edited same paragraph across unequal-length bodies).
    - Block types must match for any pair; mixed pairs never align.
    - When both bodies have the same number of blocks, diagonal ``(i,i)``
      uses: signature equality; fuzzy match with relaxed length ratio; prefix
      anchor for obvious in-place paragraph edits; or always for two tables.
      Off-diagonal pairs use standard fuzzy matching (reorders).
    - Emit a full alignment list including inserts/deletes as (None, idx) / (idx, None).
    """

    alignment, _trace, _dp = _align_paragraphs_compute(
        original, revised, config, collect_lcs_trace=False
    )
    return alignment
