# Engine Data Contracts (MDC-002)

This document defines stable contract shapes for early engine integration.

## 1) Body IR (v1)

Top-level shape:

- `version` (int): currently `1`
- `blocks` (list): ordered body blocks

Current block type:

- `paragraph`
  - `type`: `"paragraph"`
  - `id`: stable block identifier
  - `runs`: list of runs

Run shape:

- `text` (string, required)
- `bold` (bool, optional)
- `italic` (bool, optional)
- `underline` (bool, optional)

## 2) Diff Ops (v1)

Each diff op has:

- `op`: one of `insert`, `delete`, `replace`
- `path`: logical selector (for example `blocks/0/runs/1`)
- `before`: prior text value (string or `null`)
- `after`: new text value (string or `null`)

Notes:

- `insert` typically uses `before = null`
- `delete` typically uses `after = null`
- `replace` usually has both values present
- Inline paragraph diffs (MDC-007) use paths like `blocks/{paragraph_index}/inline/0`, `blocks/{paragraph_index}/inline/1`, … in document order (`paragraph_index` is 0 when using single-paragraph `BodyIR` defaults).

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
