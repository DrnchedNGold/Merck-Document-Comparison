"""
Word / punctuation / whitespace tokens for paragraph LCS diff (Track Changes emit).

Tokenization splits mixed product-code identifiers (e.g. ``MK-2870``), plain
``\\w+`` spans (Unicode word characters, including digits), each non-word
non-space cluster (e.g. commas), and each ``\\s+`` run into separate tokens so
``16,18,31`` becomes ``16``, ``,``, ``18``, ``,``, ``31``.

**Matching:** :meth:`DiffToken.norm_key` uses Unicode case-folding and maps any
whitespace-only surface to a single space key so LCS aligns on normalized
identity while **surfaces** preserve original casing and spacing for output.

:class:`StructuredOrigToken` links each token to the source ``w:r`` for run-aware emit.

Enable stderr debug: ``MDC_DEBUG_LCS=1`` (prints token lists, equal-span counts, and ``matcher.ratio()``).
"""

from __future__ import annotations

import difflib
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# Sponsor-style identifiers like ``MK-2870`` should stay intact, but generic
# word+number labels such as ``TroFuse-020`` should still split so stable
# numeric suffixes can align independently. Dates such as ``09-APR-2025`` also
# continue to fall back to smaller pieces.
_MIXED_ALNUM_HYPHEN_TOKEN = r"(?:[A-Z]{1,10}-\d+|\d+-[A-Z]{1,10})(?!-\d)"

# Mixed identifiers, word chars, punctuation (non-word, non-space), or whitespace runs.
_DIFF_TOKEN_PATTERN = re.compile(
    rf"{_MIXED_ALNUM_HYPHEN_TOKEN}|\w+|[^\w\s]+|\s+",
    re.UNICODE,
)


@dataclass(frozen=True)
class DiffToken:
    """One contiguous slice of the source string (``surface``) with span ``[start, end)``."""

    surface: str
    start: int
    end: int

    def norm_key(self) -> str:
        """Lowercase / case-folded key for LCS; whitespace runs collapse to one space."""
        if not self.surface:
            return ""
        if self.surface.isspace():
            return " "
        return self.surface.casefold()


def tokenize_for_lcs(text: str) -> list[DiffToken]:
    """Split *text* into word, punctuation, and whitespace tokens (full coverage)."""

    if not text:
        return []
    return [DiffToken(m.group(0), m.start(), m.end()) for m in _DIFF_TOKEN_PATTERN.finditer(text)]


def norm_keys(tokens: list[DiffToken]) -> list[str]:
    return [t.norm_key() for t in tokens]


def non_whitespace_norm_keys(tokens: list[DiffToken]) -> list[str]:
    """Normalized keys for non-whitespace tokens only."""

    return [t.norm_key() for t in tokens if not t.surface.isspace()]


def lcs_matched_token_count(left_keys: list[str], right_keys: list[str]) -> int:
    """LCS-equal token count for two normalized token-key sequences."""

    if not left_keys or not right_keys:
        return 0
    matcher = difflib.SequenceMatcher(None, left_keys, right_keys, autojunk=False)
    return sum(i2 - i1 for tag, i1, i2, _j1, _j2 in matcher.get_opcodes() if tag == "equal")


def lcs_token_similarity_ratio(left_keys: list[str], right_keys: list[str]) -> float:
    """
    Symmetric token similarity based on LCS overlap.

    Uses ``2 * matched / (len(left) + len(right))`` so heavily shared paragraph
    rewrites still score as "same" when most tokens are preserved, while still
    rejecting unrelated text that only shares a few anchors.
    """

    if not left_keys and not right_keys:
        return 1.0
    if not left_keys or not right_keys:
        return 0.0
    matched = lcs_matched_token_count(left_keys, right_keys)
    return (2.0 * matched) / (len(left_keys) + len(right_keys))


def bounds_from_token_indices(tokens: list[DiffToken], i1: int, i2: int) -> tuple[int, int]:
    """Character ``[start, end)`` in the source string covering ``tokens[i1:i2]``."""

    if i1 >= i2 or not tokens:
        return 0, 0
    return tokens[i1].start, tokens[i2 - 1].end


def equal_span_surface(tokens: list[DiffToken], i1: int, i2: int) -> str:
    """Concatenate original surfaces for ``tokens[i1:i2]`` (unchanged emit text)."""

    return "".join(t.surface for t in tokens[i1:i2])


def lcs_equal_token_count(opcodes: list[tuple[str, int, int, int, int]]) -> int:
    """Number of tokens covered by ``equal`` opcodes (for diagnostics)."""

    n = 0
    for op in opcodes:
        if op[0] == "equal":
            n += op[2] - op[1]
    return n


def maybe_log_lcs_debug(
    label: str,
    orig_tokens: list[DiffToken],
    rev_tokens: list[DiffToken],
    matcher: difflib.SequenceMatcher,
) -> None:
    if os.environ.get("MDC_DEBUG_LCS") != "1":
        return
    opcodes = matcher.get_opcodes()
    eq = lcs_equal_token_count(opcodes)
    orig_surfaces = [t.surface for t in orig_tokens]
    rev_surfaces = [t.surface for t in rev_tokens]
    ratio = matcher.ratio()
    print(f"[MDC_DEBUG_LCS] {label}", file=sys.stderr)
    print(f"  orig: n={len(orig_tokens)} surfaces={orig_surfaces!r}", file=sys.stderr)
    print(f"  orig: norm_keys={norm_keys(orig_tokens)!r}", file=sys.stderr)
    print(f"  rev:  n={len(rev_tokens)} surfaces={rev_surfaces!r}", file=sys.stderr)
    print(f"  rev:  norm_keys={norm_keys(rev_tokens)!r}", file=sys.stderr)
    print(
        f"  LCS equal_token_count={eq} opcodes={len(opcodes)} matcher.ratio()={ratio:.4f}",
        file=sys.stderr,
    )


@dataclass(frozen=True)
class StructuredOrigToken:
    """
    One LCS token on the original side with a concrete ``w:r`` source and offsets
    inside that run's raw text (from :func:`~engine.docx_body_ingest._parse_text_from_run_element`).
    """

    token: DiffToken
    run_el: ET.Element
    run_lo: int
    run_hi: int


def structured_orig_tokens_from_aligned_runs(
    aligned: list[tuple[ET.Element, str]],
    orig_cmp: str,
) -> list[StructuredOrigToken] | None:
    """
    Tokenize each original ``w:r`` raw string, then verify the concatenation matches
    :func:`tokenize_for_lcs` on *orig_cmp* (same token boundaries and surfaces).

    Returns ``None`` when per-run tokenization does not match whole-paragraph tokens
    (caller should fall back to flat raw-range emit).
    """

    flat: list[StructuredOrigToken] = []
    pos = 0
    for run_el, raw in aligned:
        for dt in tokenize_for_lcs(raw):
            g0 = pos + dt.start
            g1 = pos + dt.end
            flat.append(
                StructuredOrigToken(
                    token=DiffToken(dt.surface, g0, g1),
                    run_el=run_el,
                    run_lo=dt.start,
                    run_hi=dt.end,
                )
            )
        pos += len(raw)
    ref = tokenize_for_lcs(orig_cmp)
    if len(ref) != len(flat):
        return None
    for a, b in zip(ref, flat, strict=True):
        if a.surface != b.token.surface or a.start != b.token.start or a.end != b.token.end:
            return None
    return flat


def structured_token_index_bounds_for_global_span(
    struct: list[StructuredOrigToken], ts: int, te: int
) -> tuple[int, int]:
    """Return ``[lo, hi)`` indices into *struct* covering ``orig_cmp[ts:te)``."""

    if ts >= te or not struct:
        return 0, 0
    lo = 0
    while lo < len(struct) and struct[lo].token.end <= ts:
        lo += 1
    hi = lo
    while hi < len(struct) and struct[hi].token.start < te:
        hi += 1
    return lo, hi
