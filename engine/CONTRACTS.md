# Engine Data Contracts (MDC-002)

This document defines stable contract shapes for early engine integration.

## 1) Body IR (v1)

Top-level shape:

- `version` (int): currently `1`
- `blocks` (list): ordered body blocks

Current block types:

- `paragraph`
  - `type`: `"paragraph"`
  - `id`: stable block identifier
  - `runs`: list of runs

- `table`
  - `type`: `"table"`
  - `id`: stable block identifier
  - `rows`: list of rows; each row is a list of cells
  - `cell`: `{ "paragraphs": [ BodyParagraph, ... ] }` (common `w:tc` → `w:p` sequences)

Run shape:

- `text` (string, required)
- `bold` (bool, optional)
- `italic` (bool, optional)
- `underline` (bool, optional)

## 1b) Document package IR (SCRUM-49)

Top-level shape for body + header/footer parts:

- `version` (int): currently `1`
- `document` (`BodyIR`): content from `word/document.xml`
- `header_footer` (object): map from OOXML zip paths (`word/header1.xml`, `word/footer1.xml`, …) to `BodyIR` for that part’s structural content (`w:hdr` / `w:ftr` children, same block shapes as the body)

## 2) Diff Ops (v1)

Each diff op has:

- `op`: one of `insert`, `delete`, `replace`
- `path`: logical selector (for example `blocks/0/runs/1`)
- `before`: prior text value (string or `null`)
- `after`: new text value (string or `null`)
- `part` (string, optional): OOXML zip path for the target XML part (for example `word/document.xml`, `word/header1.xml`). Omitted on legacy body-only diffs; set when comparing a full document package so emitters can route revisions to the correct part.

Notes:

- `insert` typically uses `before = null`
- `delete` typically uses `after = null`
- `replace` usually has both values present
- Inline paragraph diffs (MDC-007) use paths like `blocks/{block_index}/inline/0`, `blocks/{block_index}/inline/1`, … in document order (`block_index` is 0 when using single-paragraph `BodyIR` defaults).
- Table cell diffs (MDC-008) use paths like `blocks/{block_index}/rows/{r}/cells/{c}/inline/{n}`. Whole-table shape mismatches may use `blocks/{block_index}/table`.

## 3) Compare Config (Word-like default stub)

Required booleans:

- `ignore_case`
- `ignore_whitespace`
- `ignore_formatting`
- `detect_moves`

Default `Word-like` profile in code:

- `ignore_case = false`
- `ignore_whitespace = false`
- `ignore_formatting = true`
- `detect_moves = false`

## Contract fixture

Fixture file: `tests/fixtures/engine_contract_fixture.json`

It includes:

- tiny original/revised body IR trees
- expected diff ops for the tiny example
- compare config profile used by the fixture
