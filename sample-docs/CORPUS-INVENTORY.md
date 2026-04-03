# Sample Corpus Inventory (SCRUM-40)

This inventory tracks sponsor-provided sample documents used for implementation
planning and verification.

## Corpus folders

- `sample-docs/email1docs/` - first sponsor email corpus
- `sample-docs/email2docs/` - second sponsor email corpus (GIP-focused)
- `sample-docs/email3docs/` - third sponsor email corpus (Protocol + IB-focused)

## Included compare sets

### Email 1

- `diversity-plan-bladder-cancer-version1.docx` (source)
- `diversity-plan-bladder-cancer-version2.docx` (source)
- `diversity-plan-bladder-cancer-version2_compare_against-version1.docx` (Merck compare output)
- `diversity-plan-cervical-cancer-version1.docx` (source)
- `diversity-plan-cervical-cancer-version2.docx` (source)
- `diversity-plan-cervical-cancer-version2_compare_against-version1.docx` (Merck compare output)

### Email 2 (GIP)

Some Jira repros name **`sample-docs/email2docs/diversity-plan-cervical-cancer-version{1,2}.docx`**.
That path is not in the committed corpus; use the same filenames under **`email1docs/`** (above) for
SCRUM-130 / abbreviations verification unless your team adds copies under `email2docs/`.

- `ind-general-investigation-plan-3475-v2.docx` (source)
- `ind-general-investigation-plan-3475-V2 compare to V1.docx` (Merck compare output)
- `ind-general-investigation-plan-V940-v1.docx` (source)
- `ind-general-investigation-plan-V940-v4.docx` (source)
- `ind-general-investigation-plan-V940-V4 compare to V1.docx` (Merck compare output)

### Email 3 (Protocol + IB)

#### Protocol

- `1026-010-02.docx` (source)
- `1026-010-04.docx` (source)
- `1026-010-04_version_compare_against-02.docx` (Merck compare output)
- `7902-010-04.docx` (source)
- `7902-010-05.docx` (source)
- `7902-010-05_version_compare_against-04.docx` (Merck compare output)

#### Investigational Brochure (IB)

- `ib-edition-6.docx` (source)
- `ib-edition-8.docx` (source)
- `ib-compare-edition-6-8.docx` (Merck compare output)
- `ib-edition-10.docx` (source)
- `ib-edition-11.docx` (source)
- `ib-compare-edition-10-11.docx` (Merck compare output)

## Engineering implications

- Use all three corpora together when defining acceptance and test coverage.
- Treat compare-output documents as expected-reference artifacts, not source inputs.
- Keep logic generic to `.docx` structure; do not hard-code GIP/Protocol/IB-specific names or templates.
- Source docs are expected to have tracked changes/comments absent before comparison.
- Email 3 introduces the highest complexity so far (large docs with many tables and headers/footers),
  so phase planning for structured parts and golden validation should prioritize these scenarios.
