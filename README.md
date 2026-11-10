# TrialParse

Turns free-text clinical trial eligibility criteria from ClinicalTrials.gov into structured,
queryable records, and measures how well an LLM does that compared with a regex baseline
on a hand-labeled gold set.

Pipeline: **fetch** (ClinicalTrials.gov v2 API) → **extract** (regex rules and Claude with a
forced tool schema, cached by criteria hash and prompt version) → **evaluate** (field-level
accuracy and P/R/F1 against the gold set, plus agreement with the registry's own structured
age and sex fields) → **build-tables** (flat SQLite tables for plain SQL queries).
A weekly GitHub Actions job refreshes trials and only re-extracts new or changed ones.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v       # 15 tests, no network needed
export ANTHROPIC_API_KEY=...                  # needed only for the LLM step
```

## Run it

```bash
# 1. Pull trials
python -m trialparse fetch --condition "type 2 diabetes" --max 300

# 2. Regex baseline (free, instant)
python -m trialparse extract --method regex

# 3. Hand-label 40 trials. Read LABELING_GUIDE.md first. Do this BEFORE looking at LLM output.
python -m trialparse label --n 40

# 4. LLM on the gold trials only (cheap), then score on the dev split
python -m trialparse extract --method llm --gold-only
python -m trialparse evaluate --split dev
#    Read results/errors_llm_dev_*.jsonl. If you change SYSTEM_PROMPT,
#    bump PROMPT_VERSION in trialparse/llm_extract.py and re-run step 4.
#    Only ever tune on dev. Never look at test errors while changing the prompt.

# 5. Final numbers: LLM on every trial, then the test split
python -m trialparse extract --method llm
python -m trialparse evaluate --split test

# 6. Query tables
python -m trialparse build-tables
```

Example query: recruiting trials that accept HbA1c around 7% and exclude kidney disease.

```sql
SELECT DISTINCT t.nct_id, t.title
FROM eligibility_labs l JOIN trials t USING (nct_id)
WHERE l.method = 'llm' AND l.canonical_test = 'hba1c' AND l.section = 'inclusion'
  AND l.operator IN ('>=', '>') AND l.value <= 7.5
  AND t.nct_id IN (SELECT nct_id FROM eligibility_conditions
                   WHERE method = 'llm' AND kind = 'excluded' AND condition LIKE '%kidney%');
```

Run with `sqlite3 data/trialparse.db`.

## How scoring works

- Age, sex, pregnancy: exact accuracy (ages within 0.01 years). A failed extraction counts as wrong.
- Condition lists: micro precision, recall and F1. A predicted condition matches a gold one when
  their word sets overlap by at least 50% (Jaccard), one-to-one. Change with `--threshold`.
- Lab thresholds: exact match on (canonical test, operator, value, section).
- The regex baseline does not attempt condition lists; they show as "not attempted".
- Registry agreement compares extracted age and sex with the registry's structured fields on every
  trial in the database, not just the gold set.
- Split: about 25% of gold trials are dev (for prompt changes), the rest are test (for reporting).

## Weekly refresh

Add `ANTHROPIC_API_KEY` as a repository secret. The `refresh` job runs Mondays and on manual
dispatch, keeps the database in the Actions cache, and uploads it as an artifact.
