# How to report comparison issues (bugs vs Word parity)

This guide is for **anyone** testing the tool—no need to understand the golden harness or CI. It helps turn “a lot of errors” into **reproducible** reports so the team can open the right Jira tasks.

---

## One problem = one short write-up

For **each** issue, include the following (Jira ticket, email, or chat is fine).

### 1. Which two files you compared

Use paths **relative to the repo root** when possible, e.g.:

- Original: `sample-docs/email2docs/ind-general-investigation-plan-V940-v1.docx`
- Revised: `sample-docs/email2docs/ind-general-investigation-plan-V940-v4.docx`

If files are outside the repo, attach them or describe their full path.

### 2. What you ran (desktop or CLI)

- **Desktop:** Say whether you used **defaults** after launch, or list which toggles you changed. Best: use **Save profile…** and attach the saved **JSON** file.
- **CLI:** Paste the **full command**, including `--config` if you used it.

### 3. Where it went wrong

Avoid only “the whole document is wrong.” Pick **one concrete location**, for example:

- “Page 3, first table, second row”
- “Section titled …”
- Copy **one sentence** that was wrongly deleted, wrongly added, or over-changed

### 4. What you expected

One line, e.g.:

- “That sentence should stay unchanged.”
- “That text does not appear in the revised file.”
- “Only this word should be marked as changed.”

### 5. The output your tool produced

Attach the generated **`.docx`**, or put it in a known path and name it in the report.

That bundle is enough to **reproduce** the issue and split work into tasks (alignment, table diff, emit, preflight, desktop UX, etc.).

---

## Mapping common complaints to how we triage them

| What you observe                       | How we use it                                                                                                                        |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Deletes text it should not             | Likely **content / alignment / emit** — needs concrete location + repro pair + profile.                                              |
| “Corrects” more than necessary         | Often **compare settings** (e.g. ignore formatting) or **alignment** — same: one example + profile JSON.                             |
| Deletes parts of tables                | **Table-specific** — we need **which table** (e.g. first table on page X, row/cell if possible).                                     |
| Adds text that is not there            | **High priority** — exact snippet + clarify whether it appears in original, revised, or neither.                                     |
| Settings are confusing / not like Word | **Separate UX / product task** — list what Word offers that you need (e.g. moves, tables, whitespace) and what is unclear in our UI. |

You do **not** have to run **Word’s compare** between our output and the sample reference document unless you want extra context. It is **optional**; the five items above are enough.

---

## What you do not need to do

- Prove every issue with Word compare on every bug.
- Understand **golden corpus** harnesses or snapshot baselines—that is for implementers after a repro exists.
- Worry that **settings change output**—just always say **“defaults”** or attach **one profile JSON** so everyone sees the same behavior.

---

## Optional extra context (when helpful)

- **Reference compare in `sample-docs/`:** If a sponsor/Word reference output exists for that pair, note its path. Product docs treat some references as **guidance**, not the only definition of “correct,” but they still help **spot checks**.
- **Screenshot:** Useful for UI confusion or layout; still add at least one **text anchor** (section title or quoted phrase).

---

## Smallest useful first step

Pick the **single worst** or **clearest** wrong case, fill the five sections above, and send that one report first. From one good repro the team can open follow-up tasks; many vague reports without a fixed location are hard to fix.

---

## Related docs

- [`README.md`](../README.md) — run desktop, CLI, troubleshooting (exit codes)
- [`CLI-MERCK-COMPARE.md`](CLI-MERCK-COMPARE.md) — CLI options and `CompareConfig` JSON keys
- [`PRODUCT-DECISIONS.md`](PRODUCT-DECISIONS.md) — v1 scope (e.g. `.docx` only, no docs with existing Track Changes/comments)
- [`sample-docs/CORPUS-INVENTORY.md`](../sample-docs/CORPUS-INVENTORY.md) — what lives under each email corpus folder
