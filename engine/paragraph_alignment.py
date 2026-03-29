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

    Backtracking prefers deleting from the original when LCS tie-breaks are
    equal (``dp[i+1][j] >= dp[i][j+1]``).

Assumptions and limits
    - One BodyIR "block" is treated as one alignable unit (paragraph-level).
    - Fuzzy matching can mis-align two different but boilerplate-similar blocks;
      threshold is conservative.
    - No cross-paragraph move detection; reordering is expressed as delete +
      insert alignment pairs, not as a semantic "move" op.
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


@dataclass(frozen=True)
class ParagraphAlignment:
    original_paragraph_index: int | None
    revised_paragraph_index: int | None


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
    if lo and lr and min(lo, lr) / max(lo, lr) < 0.45:
        cache[key] = False
        return False
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


def align_paragraphs(original: BodyIR, revised: BodyIR, config: CompareConfig) -> list[ParagraphAlignment]:
    """
    Align paragraphs using a stable, deterministic strategy.

    Strategy:
    - Compute paragraph signatures and normalized block text for fuzzy matching.
    - LCS dynamic programming: match when signatures are equal **or** fuzzy
      similarity is high enough (``quick_ratio`` plus combined character/token
      ratio; edited same paragraph across unequal-length bodies).
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

