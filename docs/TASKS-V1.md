# V1 Task Backlog (Executable by Team)

Use these tasks as implementation units. Each task is intentionally scoped for one PR.

**How you work:** Jira is the driver for day-to-day tasks (key + summary like `MDC-24 Add a …`). This file is the technical backlog reference. See `docs/TEAM-WORKFLOW.md` and `docs/TEAM-PLAYBOOK.md` for onboarding, branch naming (slug from Jira), and PR flow.

## T001 - Scaffold Monorepo Structure
**Goal:** Create initial folders for engine, desktop app, test corpus, and scripts.  
**Acceptance Criteria:**
- Repository contains clear top-level structure for `engine`, `desktop`, `tests`, and `sample-docs`.
- README updated with local setup instructions.

## T002 - Define Engine Data Contracts
**Goal:** Add versioned schemas/interfaces for normalized document model and diff result model.  
**Acceptance Criteria:**
- Schemas committed and documented.
- Example JSON fixtures provided for one simple paragraph diff.

## T003 - Build DOCX Package Reader
**Goal:** Read `.docx` package and extract relevant OpenXML parts.  
**Acceptance Criteria:**
- Can parse `word/document.xml`, headers, and footers.
- Unit tests for missing/invalid parts.

## T004 - Implement Preflight Validation
**Goal:** Validate inputs before compare run.  
**Acceptance Criteria:**
- Reject non-`.docx` inputs with visible error.
- Detect pre-existing tracked changes/comments and stop with visible error message.
- Tests cover both valid and invalid inputs.

## T005 - Build Normalization Pipeline (v1)
**Goal:** Canonicalize text/structure for stable diffing while preserving render context.  
**Acceptance Criteria:**
- Paragraph and run-level normalized representation implemented.
- Config toggles for formatting-sensitive vs formatting-insensitive comparison behavior.

## T006 - Paragraph/Run Diff Engine (v1)
**Goal:** Produce deterministic insert/delete diffs for body content.  
**Acceptance Criteria:**
- Works for simple paragraphs and mixed inline formatting.
- Deterministic outputs on repeated runs.

## T007 - Table-Aware Diffing
**Goal:** Handle tables without collapsing into noisy full-block replacements.  
**Acceptance Criteria:**
- Row/cell-aware matching implemented for common cases.
- Reduced false positives on provided sample docs with tables.

## T008 - Header/Footer Diffing
**Goal:** Include header/footer changes in compare output.  
**Acceptance Criteria:**
- Revisions can be generated in header/footer parts.
- Tests verify changes in `word/header*.xml` and/or `word/footer*.xml`.

## T009 - Track Changes Renderer
**Goal:** Emit Word-compatible revision markup in output `.docx`.  
**Acceptance Criteria:**
- Emits `w:ins` and `w:del` correctly in v1.
- Preserves non-changed formatting context.
- Output opens cleanly in Word.

## T010 - Move Detection (Phase 1)
**Goal:** Add basic move detection for structural blocks.  
**Acceptance Criteria:**
- Emits `w:moveFrom`/`w:moveTo` for straightforward moved blocks.
- Falls back safely to del+ins when confidence is low.

## T011 - Golden Corpus Regression Harness
**Goal:** Compare generated output against expected client compare docs.  
**Acceptance Criteria:**
- Harness can run all current sample pairs.
- Reports structural mismatch summary by XML part and revision type.

## T012 - Desktop App Skeleton (Cross-Platform)
**Goal:** Build initial app flow: select files, run compare, save/open output.  
**Acceptance Criteria:**
- UI supports Original + Revised picker.
- Compare command invokes engine and reports success/errors.
- "Open output" action works on all supported OS targets.

## T013 - Settings Editor (Word-Compatible Default)
**Goal:** Add settings UI with default Word-compatible profile.  
**Acceptance Criteria:**
- Default profile is locked as baseline.
- User can save/load custom profiles.
- Compare run logs active profile.

## T014 - Error UX + Logging
**Goal:** Ensure user-facing errors are clear and actionable.  
**Acceptance Criteria:**
- Preflight failures show human-readable messages.
- Errors include remediation hints where possible.

## T015 - CI + Quality Gates
**Goal:** Add automated tests and minimum gates for merges.  
**Acceptance Criteria:**
- Test suite runs in CI on PRs.
- Golden regression job is included.

---

## Priority Order (Suggested)
T001 -> T002 -> T003 -> T004 -> T005 -> T006 -> T007 -> T008 -> T009 -> T011 -> T012 -> T013 -> T014 -> T015 -> T010

Move detection (`T010`) is intentionally later because high-confidence insert/delete parity is more important first.
