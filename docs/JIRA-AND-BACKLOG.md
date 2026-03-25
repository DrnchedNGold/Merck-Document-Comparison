# Jira + repo: how we track work

## The “MDC” and numbers note (with examples)

**`MDC`** is your **Jira project key** (like a ticket prefix). Replace it if your project uses something else (e.g. `PROJ`).

**The number** is Jira’s **issue number** for that project. Jira assigns it when you create the issue — you usually **cannot** pick `001`, `002`, … in order.

### Example A — numbers match the doc (lucky / seeded)

You create the first issue; Jira assigns **MDC-1**. You use summary: **“Monorepo scaffold and README”**.  
Branch: `MDC-1-monorepo-scaffold-and-readme`.

Our **`docs/V1-ACCEPTANCE-CATALOG.md`** used **`MDC-001`** only as a **recommended label** for “first foundation task.” If your first real issue is **MDC-1** or **MDC-101**, that’s fine — the **title text** is what should match the checklist in `V1-ACCEPTANCE-CATALOG.md`, not the digits.

### Example B — typical real life

Backlog in `V1-ACCEPTANCE-CATALOG.md` says conceptually: *first do monorepo, then contracts, then ingest…*

In Jira you create issues over two sprints:

| Order you do work | Jira assigns | Summary (you type) |
|-------------------|-------------|---------------------|
| 1st | **MDC-101** | Monorepo scaffold and README |
| 2nd | **MDC-102** | Engine data contracts |
| 3rd | **MDC-103** | DOCX body ingest |

Branches: `MDC-101-monorepo-scaffold-and-readme`, `MDC-102-engine-data-contracts`, etc.

**Rule:** Treat **`docs/V1-ACCEPTANCE-CATALOG.md`** as a **template and acceptance criteria library**. The **live backlog** is **Jira**; issue keys come from Jira.

---

## What lives where (recommended)

| Artifact | Source of truth | Purpose |
|----------|-----------------|---------|
| **Every task, status, assignee, sprint** | **Jira** | Day-to-day work; nothing to replace this. |
| **Phases, milestones, “what is v1”** | **`docs/PROJECT-PLAN-V1.md`** + **`docs/PRODUCT-DECISIONS.md`** | Stable narrative; change rarely. |
| **Detailed acceptance criteria for v1 foundation** | **`docs/V1-ACCEPTANCE-CATALOG.md`** (optional to shrink over time) | Copy/paste into Jira when creating issues; or link “see V1-ACCEPTANCE-CATALOG § MDC-xxx equivalent”. |
| **BMad / sprint tooling** | **`_bmad-output/planning-artifacts/epics-v1.md`** | Optional; sync titles with Jira when you run BMad. |
| **Design / decisions** | **`docs/`** (short ADRs or updates to `PRODUCT-DECISIONS`) | Why we chose X; not a task list. |

**Do not** try to mirror **every** new Jira task in Markdown long term. That duplicates Jira and goes stale.

---

## Connecting Jira to GitHub (for the whole team)

Useful integrations (pick what your org allows):

1. **Official Jira ↔ GitHub integration** (Atlassian marketplace: “Jira Software + GitHub”)  
   - Links commits, branches, PRs to Jira issues.  
   - Developers see repo activity on the Jira ticket; reviewers see ticket context on the PR.

2. **Branch and commit naming** (works even without full integration)  
  - Branch: `MDC-103-docx-body-ingest`  
  - Commit: `MDC-103: parse document.xml into IR`  
  - Many setups auto-link `MDC-103` from the GitHub side if the integration is on.

3. **PR template** (you already have one)  
  - Always paste **Jira: MDC-xxx** + link. That alone helps humans and some bots.

4. **GitHub Actions + Jira** (optional)  
   - e.g. comment on issue when CI fails — only if the team wants the automation overhead.

5. **Jira automation**  
   - When PR merged → transition issue to Done (requires integration + rules).

**“Better than Markdown for tasks”** = **Jira is the task system**; the repo holds **plan, policies, and technical criteria**, not a duplicate backlog.

---

## Evolving backlog as development continues

**Recommended habit**

1. **New work** → create a **Jira issue** (summary = `KEY-### Short title`, description + acceptance criteria).  
2. If it’s a **small follow-up** on the same feature, use a **sub-task** or **linked issue** instead of a new epic doc.  
3. Update **`PROJECT-PLAN-V1.md`** only when **phases or scope** change (new milestone, new v1.1 section), not per ticket.  
4. Update **`V1-ACCEPTANCE-CATALOG.md`** only when you want a **curated v1 reference** — e.g. trim it to “epic-level” rows and link to Jira filters, **or** archive it as “initial backlog seed” and stop editing.

**Optional:** Add a **Jira saved filter** (e.g. “MDC v1 engine”) and put its URL in **`README.md`** under “Active backlog.”

---

## Summary

- **`MDC-001` in docs** = naming **convention** / seed order, not a guarantee Jira will use those digits.  
- **Jira** = canonical task list for the team.  
- **Repo** = plan, decisions, playbooks, and **reusable** acceptance text — not a mirror of every future ticket.  
- **Connect** Jira and GitHub via official integration + branch/PR discipline for the best team experience.
