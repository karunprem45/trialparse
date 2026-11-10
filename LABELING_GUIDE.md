# Labeling guide

These rules match the LLM prompt in `trialparse/llm_extract.py`. If you change one, change the other.

Label each trial from the criteria text alone. Do not look at the LLM output first.

| Field | What to enter |
|---|---|
| min age / max age | In years, as stated in the text. Months to years (6 months = 0.5). Blank if no limit is stated. |
| sex | ALL unless the text limits enrollment to one sex. |
| excludes pregnancy | y if pregnant people are excluded, otherwise n. |
| required conditions | Diseases or conditions a participant must have. Short names, `;` separated. Example: `type 2 diabetes; obesity` |
| excluded conditions | Diseases or conditions that keep someone out. Short names. Example: `type 1 diabetes; pancreatitis; chronic kidney disease` |
| lab thresholds | `test op value unit incl/excl`, `;` separated. A range is two entries. Example: `hba1c >= 7 % incl; hba1c <= 10.5 % incl; egfr < 30 excl` |

Not conditions: drugs and treatments ("on metformin"), procedures ("bariatric surgery"), lab values, consent, contraception rules, "investigator judgment".

Hard cases: write a short note when prompted. These notes become your error-analysis examples.

Keep it consistent. When a rule feels unclear, decide once, add it here, and apply it to every trial after that.
