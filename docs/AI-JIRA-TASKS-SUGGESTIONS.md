## Sprint 1 — Foundation Setup

### Epic: Foundation — Repo & Contracts

#### Task: Monorepo scaffold
- Sprint: Foundation Setup
- Epic name: Foundation — Repo & Contracts
- Description:
  - Objective: Set up the repo baseline so the team can run tests and build on the code.
  - Scope:
    - Parallel with: Engine data contracts
    - Depends on: None
  - Acceptance criteria:
    - Expected top-level dirs exist (`engine/`, `desktop/`, `tests/` or documented layout)
    - `README.md` includes how to install deps and run tests
  - Validation/tests:
    - `pytest` passes (even with placeholder tests)
- Suggested sub tasks:
  - Add/confirm `engine/`, `desktop/`, `tests/` (or document chosen layout)
  - Add minimal test runner wiring (placeholder `pytest` OK)
  - Ensure README dev/test instructions match the real folder layout

#### Task: Engine data contracts
- Sprint: Foundation Setup
- Epic name: Foundation — Repo & Contracts
- Description:
  - Objective: Define stable engine interfaces so later DOCX parsing/diff logic doesn’t churn.
  - Scope:
    - Parallel with: DOCX body ingest (using mocks/stubs)
    - Depends on: Monorepo scaffold (repo baseline)
  - Acceptance criteria:
    - Body IR + diff-op + compare-config contracts are documented (types/schema) and testable
    - At least one small fixture validates contract boundaries
  - Validation/tests:
    - Unit tests cover the contract fixture
- Suggested sub tasks:
  - Document body IR and diff op list (types/schema)
  - Add a tiny fixture + expected diff ops for contract validation
  - Define the default “Word-like” compare config shape (stub OK)

### Epic: Foundation — DOCX ingest & Preflight

#### Task: DOCX body ingest
- Sprint: Foundation Setup
- Epic name: Foundation — DOCX ingest & Preflight
- Description:
  - Objective: Convert DOCX body XML (`word/document.xml`) into the body IR.
  - Scope:
    - Parallel with: Preflight validation (can start once OpenXML helpers exist)
    - Depends on: Engine data contracts
  - Acceptance criteria:
    - Parses a valid `.docx` and produces deterministic body IR
    - Missing `document.xml` is handled with a clear, testable failure
  - Validation/tests:
    - Unit tests cover happy path + `document.xml missing`
- Suggested sub tasks:
  - Implement DOCX open + `document.xml` extraction
  - Convert body XML -> body IR + add unit tests (happy + missing `document.xml`)
  - Add clear error for missing/invalid `word/document.xml`

#### Task: Preflight validation
- Sprint: Foundation Setup
- Epic name: Foundation — DOCX ingest & Preflight
- Description:
  - Objective: Enforce v1 governance before diffing.
  - Scope:
    - Parallel with: None (must run before comparison)
    - Depends on: DOCX body ingest parsing helpers
  - Acceptance criteria:
    - Rejects non-`.docx` with a clear error
    - Detects pre-existing tracked changes/comments and fails visibly (v1 policy)
    - Errors are deterministic and easy to surface
  - Validation/tests:
    - Unit tests cover all failure modes
- Suggested sub tasks:
  - Detect tracked changes/comments and return a clear error
  - Add unit tests for each failure mode
  - Keep error messages deterministic for later CLI/desktop wiring

---

## Sprint 2 — Body Comparison Core

### Epic: Body compare — Normalization & Alignment

#### Task: Normalization + compare keys
- Sprint: Body Comparison Core
- Epic name: Body compare — Normalization & Alignment
- Description:
  - Objective: Generate stable compare keys and apply normalization to ignore formatting noise.
  - Scope:
    - Parallel with: Paragraph alignment tests (using synthetic IR)
    - Depends on: Engine data contracts
  - Acceptance criteria:
    - Compare keys are deterministic
    - Formatting-only changes don’t break alignment (when ignore toggles are on)
  - Validation/tests:
    - Unit tests demonstrate alignment stability under formatting-only edits
- Suggested sub tasks:
  - Implement compare-key generation logic
  - Add tests showing formatting-only changes don’t break alignment
  - Implement default ignore toggles matching v1 “Word-like” behavior (stub OK)

#### Task: Paragraph alignment
- Sprint: Body Comparison Core
- Epic name: Body compare — Normalization & Alignment
- Description:
  - Objective: Align paragraphs deterministically to localize diffs.
  - Scope:
    - Parallel with: None (but can be driven by synthetic fixtures)
    - Depends on: Compare keys
  - Acceptance criteria:
    - Deterministic alignment for insert/delete/reorder scenarios
    - Alignment is stable across repeated runs with same inputs
  - Validation/tests:
    - Unit tests cover the required fixture scenarios
- Suggested sub tasks:
  - Implement paragraph alignment algorithm
  - Add deterministic fixtures/tests (insert/delete/reorder)
  - Add a brief note on alignment assumptions/limits

### Epic: Body compare — Inline run diffs

#### Task: Inline diff for runs
- Sprint: Body Comparison Core
- Epic name: Body compare — Inline run diffs
- Description:
  - Objective: Compute ordered inline diffs for runs inside an aligned paragraph.
  - Scope:
    - Parallel with: None (builds on alignment + keys)
    - Depends on: Paragraph alignment
  - Acceptance criteria:
    - Inline diff ops are deterministic and ordered
    - Tests cover insert/delete/replace within one paragraph
  - Validation/tests:
    - Unit tests assert expected inline diff operations
- Suggested sub tasks:
  - Implement inline diff op generation
  - Add tests: insert/delete/replace within one paragraph
  - Ensure diff ops are emitted in deterministic order for stable output

