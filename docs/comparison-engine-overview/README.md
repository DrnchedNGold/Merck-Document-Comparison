# Comparison engine — stakeholder overview

This folder is a **self-contained pack** for demos, onboarding, and reviews: **what the comparison engine does**, **how it fits next to the desktop app**, and **where to go deeper in code**.

## Audience

| Who | Start here |
|-----|------------|
| **Sponsors / leadership** | Open [`diagrams/stakeholder-seven-step.svg`](diagrams/stakeholder-seven-step.svg) in a browser (or embed in slides). |
| **Course staff / reviewers** | Same SVG, plus the short narrative below. |
| **Future developers** | [`diagrams/technical-pipeline-explained.svg`](diagrams/technical-pipeline-explained.svg) for **what each step does**; [`technical-pipeline`](diagrams/technical-pipeline.mmd) for **function/module names** that match the code. Plus the [Engine pipeline narrative](#engine-pipeline-narrative-one-page) below. |

## Files in this folder

| File | Purpose |
|------|---------|
| [`diagrams/stakeholder-seven-step.svg`](diagrams/stakeholder-seven-step.svg) | **Primary showpiece:** plain-language pipeline (inputs → seven stages → redlined output). Hand-crafted vector; prints and scales cleanly. |
| [`diagrams/stakeholder-high-level.svg`](diagrams/stakeholder-high-level.svg) | Minimal flowchart (two `.docx` in → engine → redlined out). **Generated** from `.mmd` via Mermaid CLI. |
| [`diagrams/stakeholder-high-level.mmd`](diagrams/stakeholder-high-level.mmd) | Source for the high-level diagram (Confluence/GitHub Mermaid, or regenerate SVG). |
| [`diagrams/system-context.svg`](diagrams/system-context.svg) | Desktop + CLI + engine context. **Generated** from `.mmd`. |
| [`diagrams/system-context.mmd`](diagrams/system-context.mmd) | Source for system-context diagram. |
| [`diagrams/technical-pipeline.svg`](diagrams/technical-pipeline.svg) | Full pipeline with **function and file names** (maps directly to code). **Generated** from `.mmd`. |
| [`diagrams/technical-pipeline.mmd`](diagrams/technical-pipeline.mmd) | Source for the code-aligned diagram. |
| [`diagrams/technical-pipeline-explained.svg`](diagrams/technical-pipeline-explained.svg) | Same topology as `technical-pipeline`, but labels describe **behavior** (why suffix/zip, what is scanned, how diff and emit work). **Generated** from `.mmd`. |
| [`diagrams/technical-pipeline-explained.mmd`](diagrams/technical-pipeline-explained.mmd) | Source for the behavior-oriented technical diagram. |

### Regenerate SVG from Mermaid (Docker)

From the repo root:

```bash
for f in stakeholder-high-level system-context technical-pipeline technical-pipeline-explained; do
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" minlag/mermaid-cli:11.12.0 \
    -i "/data/docs/comparison-engine-overview/diagrams/${f}.mmd" \
    -o "/data/docs/comparison-engine-overview/diagrams/${f}.svg" \
    -b white
done
```

Or paste any `.mmd` file into [Mermaid Live Editor](https://mermaid.live) and export SVG or PNG.

---

## One-sentence value proposition

The engine takes **two Word `.docx` files** (baseline and revised), validates them, builds structured representations of body plus headers and footers, **aligns and diffs** at paragraph/table scale then **finer token scale**, and writes a **new `.docx`** that opens in Microsoft Word with **Track Changes** (`w:ins` / `w:del`) so reviewers see a familiar redline.

## Engine pipeline narrative (one page)

1. **Entry (`engine/compare_cli.py`)** — Parses paths, optional JSON compare profile, author, and date. Invalid config stops early with a clear exit code; no partial output file.

2. **Preflight (`engine/preflight_validation.py`)** — Ensures each input is a valid `.docx` package and enforces v1 policy (for example: no pre-existing Track Changes or comments in scoped parts). Failures map to a dedicated exit code so UIs can explain “why” without running diff logic.

3. **Ingest** — The zip is read; `word/document.xml` and header/footer parts become an internal **IR** (ordered blocks: paragraphs and tables; run text preserves layout signals such as tabs where the product needs them).

4. **Coarse alignment (`engine/paragraph_alignment.py`)** — Paragraph/table sequences are matched between original and revised so **structural** inserts and deletes are correct, not accidental merges of unrelated blocks.

5. **Fine diff** — Matched paragraphs use token-oriented comparison; **TOC-style** lines and **tables** use specialized paths so Word-specific layout is not destroyed by a naive character diff.

6. **Emit Track Changes (`engine/body_revision_emit.py`)** — Diffs become OOXML revision nodes with a **single ascending revision id stream** across body and header/footer parts, plus author and timestamp metadata.

7. **Package write (`engine/docx_output_package.py`)** — The **original** `.docx` is copied as the shell; only the XML parts that were revised are replaced, so styles, media, and unrelated content stay stable.

**Exit codes (CLI):** `0` success; `2` usage/config; `10` preflight; `11` structure/XML; `12` compare/emit or I/O.

## Desktop + engine

The **desktop** shell (`desktop/`) runs the same compare as a **subprocess** (`python -m engine.compare_cli` with `PYTHONPATH` set to the repo root), then can open the output file. The diagram [`diagrams/system-context.mmd`](diagrams/system-context.mmd) shows that relationship.

## Deeper technical write-up (repository)

For a longer module-by-module explanation aligned with the technical Mermaid diagram, see [`../ENGINE-PIPELINE-DIAGRAM.md`](../ENGINE-PIPELINE-DIAGRAM.md) if it exists on your branch (same content intent as the narrative above, with more file-level detail).
