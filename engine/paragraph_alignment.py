"""
Paragraph alignment (MDC-006)

Deterministically align paragraphs between two BodyIR payloads to localize diffs.
This is a minimal foundation implementation to support later inline diffing.

Algorithm (v1 foundation)
    Signatures are built from normalized compare keys per paragraph (see
    ``generate_compare_keys``). Alignment is the longest common subsequence (LCS)
    of signature strings. Backtracking prefers deleting from the original when
    LCS tie-breaks are equal (``dp[i+1][j] >= dp[i][j+1]``), which keeps
    behavior stable and repeatable for the same inputs.

Assumptions and limits
    - One BodyIR "block" is treated as one alignable unit (paragraph-level).
    - Matching is by full-paragraph signature equality; two different paragraphs
      with the same normalized content+format key can align ambiguously (same
      as any hash/LCS over equality).
    - No cross-paragraph move detection; reordering is expressed as delete +
      insert alignment pairs, not as a semantic "move" op.
    - Tables, headers/footers, and non-body parts are out of scope until wired
      into BodyIR the same way as body paragraphs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .compare_keys import generate_compare_keys
from .contracts import BodyIR, CompareConfig


@dataclass(frozen=True)
class ParagraphAlignment:
    original_paragraph_index: int | None
    revised_paragraph_index: int | None


def _paragraph_signature(body_ir: BodyIR, paragraph_index: int, config: CompareConfig) -> str:
    """
    Compute a deterministic signature for a paragraph, based on normalized run keys.
    """

    blocks = body_ir.get("blocks", [])
    paragraph = blocks[paragraph_index]
    paragraph_ir: BodyIR = {"version": body_ir["version"], "blocks": [paragraph]}
    keys = generate_compare_keys(paragraph_ir, config)
    # Drop the paragraph/run indices part by keeping only normalized text+format component.
    return "|".join(k["key"].split(":", 1)[1] for k in keys)


def align_paragraphs(original: BodyIR, revised: BodyIR, config: CompareConfig) -> list[ParagraphAlignment]:
    """
    Align paragraphs using a stable, deterministic strategy.

    Strategy:
    - Compute paragraph signatures (normalized, optionally format-ignored).
    - Use dynamic programming LCS over signatures to match unchanged paragraphs.
    - Emit a full alignment list including inserts/deletes as (None, idx) / (idx, None).
    """

    orig_blocks = original.get("blocks", [])
    rev_blocks = revised.get("blocks", [])

    orig_sigs = [_paragraph_signature(original, i, config) for i in range(len(orig_blocks))]
    rev_sigs = [_paragraph_signature(revised, i, config) for i in range(len(rev_blocks))]

    # LCS DP table.
    m, n = len(orig_sigs), len(rev_sigs)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            if orig_sigs[i] == rev_sigs[j]:
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = dp[i + 1][j] if dp[i + 1][j] >= dp[i][j + 1] else dp[i][j + 1]

    # Backtrack to produce alignment with inserts/deletes.
    alignment: list[ParagraphAlignment] = []
    i = j = 0
    while i < m and j < n:
        if orig_sigs[i] == rev_sigs[j]:
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

