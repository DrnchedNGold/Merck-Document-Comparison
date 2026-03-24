# How To Capture Word Compare Settings (For Baseline Parity)

Use this checklist to capture the exact Word settings your client uses, so engineering can replicate behavior.

## Goal
Provide screenshots and values for all relevant Word comparison settings.

## Prerequisites
- Microsoft Word installed.
- Any two sample `.docx` documents.
- Save screenshots to `sample-docs/word-settings-screenshots/`.

## Correct path to Advanced Options

The client PDF (`RPP-400-ER01`) may describe **Review > Tracking > Track Changes Options**. On current Word builds the **Advanced Track Changes Options** dialog is typically under:

**`Markup` > `Track Changes Options` > `Advanced Options`**

(Use whatever your Word UI shows; capture screenshots either way.)

## Step-by-Step

1. Open Microsoft Word with a blank document.
2. Go to `Review` tab (or your Word equivalent for markup/tracking).
3. Set display mode to `All Markup`.
4. Open `Show Markup` and record checked items. Example baseline on blank doc:
   - **Insertions and Deletions**: checked  
   - **Formatting**: checked  
5. Open `Balloons` submenu and record checked items. Example baseline on blank doc:
   - **Show Only Formatting in Balloons**: checked  
   Under **Specific People**, record e.g. **All Reviewers** if selected.
6. When following `Merck_Create_Compare_Document_extracted_from_RPP-400-ER01.pdf`, align balloon behavior with their process: after changes, **only** `Show All Revisions Inline` should be checked under Balloons (per client instructions — record your final state in `settings-summary.md`).
7. Open **`Markup` > `Track Changes Options` > `Advanced Options`** (or equivalent).
   - Screenshot both **Track Changes Options** and **Advanced Track Changes Options** if they are separate modals.
   - Write down key values in `settings-summary.md`.
8. Go to `Review` > `Compare` > `Compare...`.
   - Click `More >>`.
   - Take a full screenshot of this expanded dialog (sample files may be placeholders; any two `.docx` files are fine).
   - Record all checked/unchecked comparison options.
9. In the same Compare dialog, record:
   - Which document is set as Original and Revised.
   - "Label changes with" value (if blank or populated).
   - "Show changes" and "Show changes in" settings.
10. Save screenshots with clear names, for example:
   - `01-tracking-all-markup.png`
   - `02-track-changes-advanced-options.png`
   - `03-compare-dialog-expanded.png`

## Optional But Useful
- Repeat for Word on both Windows and macOS if available.
- Add Word version number (e.g., Word 365 build/version) in a note file.

## Deliverables To Commit
- Screenshot files under `sample-docs/word-settings-screenshots/`
- A summary file `sample-docs/word-settings-screenshots/settings-summary.md` containing:
  - Word version
  - OS
  - Exact checked options
  - Any ambiguous or unclear settings
