# MDC-018 Move Detection (v1 Decision)

## Decision

For v1 demo readiness, the engine intentionally uses a deterministic fallback for reordered content:

- Paragraph/table moves are represented as `w:del` + `w:ins`
- `w:moveFrom` / `w:moveTo` are not emitted in v1

## Why this choice is correct for v1

- The current pipeline aligns top-level blocks with LCS/fuzzy matching tuned for stable inline edits.
- Reliable semantic move detection requires additional matching logic across delete/insert candidates and move range bookkeeping.
- Adding partial move emission now would increase correctness risk on sponsor docs and could destabilize existing `w:ins`/`w:del` behavior.

This keeps output deterministic, reviewable, and low-risk for the first demo.

## Current validation

- Test coverage explicitly guards this fallback:
  - `tests/test_body_track_changes_output.py`
  - `test_emit_reordered_paragraph_uses_delete_insert_fallback_not_move_markup`
- The test verifies:
  - no `w:moveFrom` / `w:moveTo` in emitted XML
  - reordered text appears as both a deletion and insertion marker

## Deferred scope (post-v1)

If move markup becomes a requirement after v1, implementation should include:

- deterministic move candidate pairing criteria
- stable move IDs/ranges across document parts
- fixtures proving valid Word behavior for both simple and edge-case moves
