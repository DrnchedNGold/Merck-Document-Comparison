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

---

## Sprint 3 — Structured content + minimal Track Changes

### Epic: Structured content — Tables & headers/footers

#### Task: Tables in IR and table diff
- Sprint: Structured content + minimal Track Changes
- Epic name: Structured content — Tables & headers/footers
- Description:
  - Objective: Extend IR and compare logic to support common DOCX table structures.
  - Scope:
    - Parallel with: Headers and footers (separate XML parts)
    - Depends on: Inline diff for runs
  - Acceptance criteria:
    - IR supports table structures from common `document.xml` table shapes
    - Table diff behavior is deterministic on fixture input
  - Validation/tests:
    - Unit tests with at least one small table fixture
- Suggested sub tasks:
  - Extend Body IR/contracts for table nodes
  - Parse table XML (`w:tbl`, rows/cells) into IR
  - Add deterministic table diff baseline test fixture(s)

#### Task: Headers and footers
- Sprint: Structured content + minimal Track Changes
- Epic name: Structured content — Tables & headers/footers
- Description:
  - Objective: Load and compare header/footer parts in addition to body content.
  - Scope:
    - Parallel with: Table IR work
    - Depends on: DOCX part loading helpers and compare flow integration
  - Acceptance criteria:
    - Header/footer parts are loaded into IR (or equivalent parallel structures)
    - Revisions can target the correct `word/header*.xml` / `word/footer*.xml` parts
  - Validation/tests:
    - Tests/golden checks for correct part targeting
- Suggested sub tasks:
  - Add package-part discovery for header/footer XML files
  - Wire header/footer content into compare pipeline
  - Add tests asserting revisions are emitted to correct XML part names

### Epic: Track Changes — Minimal body output

#### Task: Track Changes body `w:ins` / `w:del`
- Sprint: Structured content + minimal Track Changes
- Epic name: Track Changes — Minimal body output
- Description:
  - Objective: Emit a new DOCX where body diffs are represented as valid Word Track Changes markup.
  - Scope:
    - Parallel with: None (depends on stable body diff ops)
    - Depends on: Inline diff + package write pipeline
  - Acceptance criteria:
    - Output DOCX opens successfully in Word for a trivial body-only case
    - Output XML contains expected `w:ins` / `w:del` markers for fixture diffs
  - Validation/tests:
    - Unit/integration tests assert expected markers in generated XML
- Suggested sub tasks:
  - Implement body revision emitter for insert/delete run groups
  - Add output packaging helper for writing updated DOCX parts
  - Add fixture tests that assert `w:ins` / `w:del` presence and shape

---

## Sprint 4 — Output metadata + verification

### Epic: Track Changes — metadata and part emission

#### Task: Revision metadata and header/footer emit
- Sprint: Output metadata + verification
- Epic name: Track Changes — metadata and part emission
- Description:
  - Objective: Emit valid revision metadata and apply revisions to all relevant parts.
  - Scope:
    - Parallel with: Golden corpus harness prep
    - Depends on: Body track-change emission and header/footer compare support
  - Acceptance criteria:
    - Valid OOXML revision attributes (for example `w:id`, `w:author`, `w:date`) are present
    - Header/footer parts receive revisions where diffs exist
  - Validation/tests:
    - Tests validate metadata attributes and part-level revision placement
- Suggested sub tasks:
  - Add metadata generation strategy (IDs/author/date source + deterministic test mode)
  - Apply metadata to inserted/deleted revision elements
  - Add tests for body + header/footer metadata emission correctness

### Epic: Verification — regression and CI

#### Task: Golden corpus harness
- Sprint: Output metadata + verification
- Epic name: Verification — regression and CI
- Description:
  - Objective: Create a repeatable regression harness using sponsor sample-doc corpora.
  - Scope:
    - Parallel with: CI pipeline updates
    - Depends on: Stable output generation path
  - Acceptance criteria:
    - Script/pytest module runs engine against configurable `sample-docs` pairs
    - Coverage includes `email1docs`, `email2docs`, and `email3docs`
    - Reports revision counts/locations by part (document vs headers)
    - README notes staged rollout from one stable pair to full corpus
  - Validation/tests:
    - Harness tests run in CI (full or documented subset)
- Suggested sub tasks:
  - Build corpus-pair config loader and runner
  - Add part-level revision count/report output
  - Document incremental corpus rollout strategy in README

#### Task: CI pipeline
- Sprint: Output metadata + verification
- Epic name: Verification — regression and CI
- Description:
  - Objective: Enforce regression checks in CI for all PRs/pushes.
  - Scope:
    - Parallel with: Golden harness implementation
    - Depends on: Existing pytest workflow and harness entrypoints
  - Acceptance criteria:
    - CI runs `pytest` on PR/push
    - Golden regression job is included (full or documented smoke subset)
  - Validation/tests:
    - CI run shows expected job matrix and passing statuses
- Suggested sub tasks:
  - Add/maintain dedicated CI job for golden regression harness
  - Ensure CI remains deterministic and reports artifact outputs where helpful
  - Document CI job purpose and smoke/full mode in workflow comments or docs

---

## Sprint 5 — Desktop MVP + hardening

### Epic: Desktop MVP — shell and engine wiring

#### Task: Desktop shell and file pickers
- Sprint: Desktop MVP + hardening
- Epic name: Desktop MVP — shell and engine wiring
- Description:
  - Objective: Deliver a launchable desktop shell with source file selection.
  - Scope:
    - Parallel with: Engine CLI hardening
    - Depends on: Desktop scaffold and runtime packaging baseline
  - Acceptance criteria:
    - App launches with Original + Revised pickers visible
    - Compare action can be stubbed pending full engine integration
  - Validation/tests:
    - Basic UI smoke checks for launch and picker interaction
- Suggested sub tasks:
  - Implement desktop main window shell
  - Add file picker controls + input validation state
  - Add smoke test or scripted launch verification

#### Task: Engine CLI and open output
- Sprint: Desktop MVP + hardening
- Epic name: Desktop MVP — shell and engine wiring
- Description:
  - Objective: Expose engine via CLI and wire desktop compare flow to it.
  - Scope:
    - Parallel with: Settings profile groundwork
    - Depends on: Engine output generation readiness
  - Acceptance criteria:
    - CLI supports args: original, revised, output, optional config and stable exit codes
    - Desktop invokes CLI, surfaces preflight/runtime errors, and supports opening output
  - Validation/tests:
    - CLI tests for arg parsing + exit codes; integration test for desktop invocation path
- Suggested sub tasks:
  - Add CLI entrypoint and argument schema
  - Map engine exceptions to stable exit codes and messages
  - Wire desktop compare action to CLI execution and output-open action

### Epic: Desktop MVP — settings and resilience

#### Task: Settings profiles UI
- Sprint: Desktop MVP + hardening
- Epic name: Desktop MVP — settings and resilience
- Description:
  - Objective: Allow editing and persistence of compare profile settings in desktop UI.
  - Scope:
    - Parallel with: Error UX/logging polish
    - Depends on: CLI config loading support
  - Acceptance criteria:
    - Profile JSON can be loaded/saved
    - UI edits update CLI/config payload
    - Default Word-compatible profile is available and documented
  - Validation/tests:
    - UI + config serialization tests for profile round-trip
- Suggested sub tasks:
  - Create settings model for profile JSON
  - Add settings UI controls mapped to compare config fields
  - Add tests for save/load + default profile behavior

#### Task: Error UX and logging
- Sprint: Desktop MVP + hardening
- Epic name: Desktop MVP — settings and resilience
- Description:
  - Objective: Make failures understandable for users and maintainers.
  - Scope:
    - Parallel with: Settings profile UI
    - Depends on: CLI exit code contract and desktop invocation wiring
  - Acceptance criteria:
    - Engine stderr/exit codes are mapped to user-readable messages
    - README includes troubleshooting guidance
  - Validation/tests:
    - Tests verify error mapping and representative failure scenarios
- Suggested sub tasks:
  - Define error mapping table for known engine failures
  - Surface actionable UI messages and optional logs path
  - Add README troubleshooting section with common failure patterns

### Epic: Stretch — move detection

#### Task: Move detection (stretch)
- Sprint: Desktop MVP + hardening
- Epic name: Stretch — move detection
- Description:
  - Objective: Decide and implement move-handling behavior for v1 demo readiness.
  - Scope:
    - Parallel with: None (stretch, optional)
    - Depends on: Stable core diff + output emission
  - Acceptance criteria:
    - Either one move-markup fixture (`w:moveFrom`/`w:moveTo`) is produced, or
    - Documented fallback to delete+insert behavior is provided and referenced in Jira/PR if deferred
  - Validation/tests:
    - Fixture test for move markup OR documentation test/check for fallback path
- Suggested sub tasks:
  - Spike move detection feasibility on a small synthetic fixture
  - Implement move markup emitter or codify delete+insert fallback
  - Document decision and constraints for reviewers
