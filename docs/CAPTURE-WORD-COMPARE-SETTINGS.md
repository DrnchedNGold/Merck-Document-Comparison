# Word compare baseline — status and follow-ups

The **initial capture is done**: screenshots and a written summary live under `sample-docs/email1docs/word-settings-screenshots/`. Use this file for **what is left to transcribe** (if anything) and **how to re-capture** on another Word build or OS.

## Where the baseline lives

| Artifact | Location |
|----------|----------|
| Screenshots | `sample-docs/email1docs/word-settings-screenshots/*.png` |
| Written summary | `sample-docs/email1docs/word-settings-screenshots/settings-summary.md` |
| Client procedure PDF | `sample-docs/email1docs/Merck_Create_Compare_Document_extracted_from_RPP-400-ER01.pdf` |

## Done (for this project)

- Blank-doc Review defaults recorded in `settings-summary.md` (Show Markup, Balloons baseline, Specific People).
- Merck procedure: balloons adjusted so **only** **Show All Revisions Inline** is checked (per client PDF flow).
- Correct UI path for advanced options documented: **`Markup` → `Track Changes Options` → `Advanced Options`** (client PDF may say `Review` → `Tracking` depending on Word version).
- Screenshots: Track Changes / Advanced Track Changes modals, and Compare **More >>** dialog.

## Remaining (optional but useful for engineering parity)

Complete these in `settings-summary.md` when you have a minute — they make automated “match Word” tests easier:

1. **Word version** and **Windows version** (exact build from Word About + OS).
2. **Final balloon checklist** — confirm the post–Merck-procedure row matches Word (check boxes in `settings-summary.md`).
3. **Compare dialog transcription** — from `Compare-Documents-More.png`, list every checked option under **Comparisons** and values for **Show changes** / **Show changes in** / **Label changes with**.

## Re-capture later (new teammate or new Word version)

1. Follow `sample-docs/email1docs/Merck_Create_Compare_Document_extracted_from_RPP-400-ER01.pdf` on the target Word install.
2. Save new PNGs alongside existing ones (use dated names if you keep both, e.g. `Compare-More-2026-06.png`).
3. Update `settings-summary.md` with Word/OS version and any checkbox differences.
