"""
Paragraph alignment (MDC-006)

Deterministically align paragraphs between two BodyIR payloads to localize diffs.
This is a minimal foundation implementation to support later inline diffing.

Algorithm
    Signatures are built from normalized compare keys per paragraph (see
    ``generate_compare_keys``). LCS alignment uses **exact signature match** or,
    when texts differ only by edits inside the same logical block, **fuzzy text
    similarity**: ``quick_ratio`` must clear a high bar, then we accept a match
    if ``max(character_ratio, word_token_ratio)`` is high enough. Character-only
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
    - No cross-paragraph move detection; reordering is expressed as delete +
      insert alignment pairs, not as a semantic "move" op. v1 emit intentionally
      preserves this as ``w:del`` + ``w:ins`` fallback (no ``w:moveFrom`` /
      ``w:moveTo`` markup).
    - Table blocks use the same signature string for fuzzy ratio when not equal.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .compare_keys import _normalize_text, generate_compare_keys
from .contracts import BodyIR, CompareConfig

# Cheap upper-bound filter before computing full ratios (keeps unrelated lines
# with moderate overlap, e.g. “The patient was observed…” vs “…discharged…”,
# from fuzzy-matching when combined similarity is only modest).
_ALIGN_FUZZY_QUICK_MIN = 0.86

# After ``quick_ratio`` passes, accept when ``max(char_ratio, token_ratio)`` is
# at least this. Token ratio matches :func:`engine.body_revision_emit._word_level_tokens`.
_ALIGN_FUZZY_COMBINED_MIN = 0.76

# TOC lines (section number + tab + title + tab + page) often get reworded titles while
# keeping the same entry (e.g. ``1.2.1`` … ``Pathophysiology`` → ``Differences in …``).
# Global fuzzy gates then miss (``quick_ratio`` ~0.71 < 0.86), LCS pairs them as
# delete+insert, and emit shows full-line strikethrough + duplicate line (SCRUM-116).
_TOC_SLOT_PREFIX_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)")

# Relaxed gates when both lines share the same TOC section prefix and contain a tab.
_TOC_SLOT_QUICK_MIN = 0.50
_TOC_SLOT_COMBINED_MIN = 0.55


@dataclass(frozen=True)
class ParagraphAlignment:
    original_paragraph_index: int | None
    revised_paragraph_index: int | None


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
    return longer.startswith(shorter)


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
    ot = re.findall(r"\S+|\s+", o_txt)
    rt = re.findall(r"\S+|\s+", r_txt)
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


def _block_alignment_text(body_ir: BodyIR, block_index: int, config: CompareConfig) -> str:
    """Plain normalized text (paragraph) or signature string (table) for fuzzy comparison."""

    blocks = body_ir.get("blocks", [])
    block = blocks[block_index]
    if block.get("type") == "paragraph":
        return "".join(
            _normalize_text(str(run.get("text", "")), config) for run in block.get("runs", [])
        )
    return _block_signature(body_ir, block_index, config)


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
    if (
        not skip_length_ratio
        and lo
        and lr
        and min(lo, lr) / max(lo, lr) < 0.45
    ):
        cache[key] = False
        return False
    if _toc_slot_pair_relaxed_align(o_txt, r_txt):
        cache[key] = True
        return True
    sm = difflib.SequenceMatcher(None, o_txt, r_txt, autojunk=False)
    if sm.quick_ratio() < _ALIGN_FUZZY_QUICK_MIN:
        cache[key] = False
        return False
    char_r = sm.ratio()
    ot = re.findall(r"\S+|\s+", o_txt)
    rt = re.findall(r"\S+|\s+", r_txt)
    tok_r = difflib.SequenceMatcher(None, ot, rt, autojunk=False).ratio()
    ok = max(char_r, tok_r) >= _ALIGN_FUZZY_COMBINED_MIN
    cache[key] = ok
    return ok


def alignment_for_track_changes_emit(
    original: BodyIR, revised: BodyIR, config: CompareConfig
) -> list[ParagraphAlignment]:
    """
    Block alignment for :mod:`engine.body_revision_emit` Track Changes output.

    When both bodies have the same number of blocks and the block **types** match
    at every index (``paragraph`` with ``paragraph``, ``table`` with ``table``),
    pair ``(i, i)``. That matches the emit path used before SCRUM-115 table work
    and keeps paragraph diff localization stable for large protocols (golden
    ins/del counts).

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
        return _repair_alignment_orig_table_rev_paras_then_rev_table(al, original, revised)
    if not orig_blocks:
        return []
    if all(
        orig_blocks[i].get("type") == rev_blocks[i].get("type")
        for i in range(len(orig_blocks))
    ):
        return [ParagraphAlignment(i, i) for i in range(len(orig_blocks))]
    al = align_paragraphs(original, revised, config)
    return _repair_alignment_orig_table_rev_paras_then_rev_table(al, original, revised)


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

    # Backtrack to produce alignment with inserts/deletes.
    alignment: list[ParagraphAlignment] = []
    i = j = 0
    while i < m and j < n:
        if aligned(i, j):
            alignment.append(ParagraphAlignment(i, j))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            alignment.append(ParagraphAlignment(i, None))
            i += 1
        else:
            alignment.append(ParagraphAlignment(None, j))
            j += 1

    while i < m:
        alignment.append(ParagraphAlignment(i, None))
        i += 1
    while j < n:
        alignment.append(ParagraphAlignment(None, j))
        j += 1

    return alignment

