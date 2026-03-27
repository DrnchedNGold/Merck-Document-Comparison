# Product Decisions (Source of Truth)

## Current Goal
Build a better `.docx` comparison tool that outputs a Word-compatible comparison document with Track Changes metadata and fewer formatting-driven false positives.

## Confirmed Decisions
- Target platforms: Windows, macOS, Linux.
- v1 file type: `.docx` only.
- Output type: true Track Changes metadata (not just visual styling).
- UX priority: Generate output and open it in Word/default app first.
- Batch compare (baseline vs many revised files): later phase.
- If source documents contain existing tracked changes/comments: show visible error and stop (for now).

## Comparison Fidelity Requirements
- Default comparison behavior should match Word compare defaults as closely as possible.
- Default redline display should match Word formatting conventions.
- Settings editor must allow custom formatting/rules while keeping a "Word-compatible default profile."

## Known Real-World Sample Inputs
Current samples live in `sample-docs/` and include:
- Email 1 corpus (`email1docs/`) with source pairs and expected compare outputs.
- Email 2 corpus (`email2docs/`) with GIP source pairs and expected compare outputs.
- Email 3 corpus (`email3docs/`) with Protocol + IB source pairs and expected compare outputs.
- Client PDF and Word compare settings artifacts.
- Corpus inventory: `sample-docs/CORPUS-INVENTORY.md`.

Corpus handling rule:
- All implementation work should validate against all sample corpora together.
- Do not specialize core logic to one sponsor template family (including GIP/Protocol/IB-only assumptions).

Unified corpus rule:
- All provided sample documents, regardless of folder name (`email1docs`, `email2docs`, `email3docs`) or complexity level, are one real-world Merck corpus and must be treated as a unified set of supported inputs.
- Comparison behavior must remain consistent across this unified corpus and must not regress on simpler or mid-complexity documents as support for higher-complexity structures is added.
- Newer datasets (email2/email3) expand structural coverage and requirements; they do not replace behavior expectations from earlier datasets.

## Non-Goals for v1
- `.doc`, `.rtf`, `.odt`, `.xlsx`, `.pptx` support.
- Handling source docs that already contain tracked changes/comments.
- Batch mode.
