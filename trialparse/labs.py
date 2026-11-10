"""Lab-name canonicalization shared by the baseline and the evaluator."""
from __future__ import annotations

import re

LAB_ALIASES: dict[str, str] = {
    "hba1c": "hba1c", "hb a1c": "hba1c", "a1c": "hba1c", "hemoglobin a1c": "hba1c",
    "glycated hemoglobin": "hba1c", "glycosylated hemoglobin": "hba1c",
    "bmi": "bmi", "body mass index": "bmi",
    "egfr": "egfr", "estimated glomerular filtration rate": "egfr",
    "fasting plasma glucose": "fpg", "fpg": "fpg", "fasting glucose": "fpg",
    "ldl-c": "ldl_c", "ldl cholesterol": "ldl_c", "ldl-cholesterol": "ldl_c", "ldl": "ldl_c",
    "triglycerides": "triglycerides", "tg": "triglycerides",
    "alt": "alt", "alanine aminotransferase": "alt",
    "ast": "ast", "aspartate aminotransferase": "ast",
    "serum creatinine": "creatinine", "creatinine": "creatinine",
    "c-peptide": "c_peptide", "c peptide": "c_peptide",
    "systolic blood pressure": "sbp", "sbp": "sbp",
    "diastolic blood pressure": "dbp", "dbp": "dbp",
}

OPERATOR_WORDS: dict[str, str] = {
    "≥": ">=", ">=": ">=", "≤": "<=", "<=": "<=", ">": ">", "<": "<", "=": "=",
    "greater than or equal to": ">=", "less than or equal to": "<=",
    "at least": ">=", "of at least": ">=", "no more than": "<=",
    "greater than": ">", "more than": ">", "above": ">", "over": ">",
    "less than": "<", "below": "<", "under": "<",
}

_SORTED_ALIASES = sorted(LAB_ALIASES, key=len, reverse=True)


def canonical_test(name: str) -> str:
    n = re.sub(r"\s+", " ", name.lower().replace("haemoglobin", "hemoglobin")).strip()
    if n in LAB_ALIASES:
        return LAB_ALIASES[n]
    for alias in _SORTED_ALIASES:
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", n):
            return LAB_ALIASES[alias]
    return n


def normalize_operator(op: str) -> str:
    return OPERATOR_WORDS[re.sub(r"\s+", " ", op.lower()).strip()]


def normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    return re.sub(r"\s+", "", unit.lower()).replace("²", "2")
