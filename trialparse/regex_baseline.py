"""Rule-based baseline. It only attempts the fields regex can reasonably get:
age, sex, pregnancy exclusion and numeric lab thresholds. Condition lists are
left empty on purpose and are reported as 'not attempted' in evaluation.
"""
from __future__ import annotations

import re
from typing import Optional

from .labs import LAB_ALIASES, canonical_test, normalize_operator, normalize_unit
from .schema import Eligibility, LabThreshold
from .text import split_sections

VERSION = "r1"

NUM = r"(\d+(?:\.\d+)?)"
DASH = r"(?:-|–|—|to)"
YRS = r"(?:years?|yrs?)"

AGE_RANGE = [
    re.compile(rf"\bbetween\s+(?:the\s+ages?\s+of\s+)?{NUM}\s*(?:{YRS}\s*)?and\s+{NUM}\s*{YRS}", re.I),
    re.compile(rf"\bage[sd]?\s*(?:of\s*)?(?:between\s*)?{NUM}\s*{DASH}\s*{NUM}\b", re.I),
    re.compile(rf"\b{NUM}\s*{DASH}\s*{NUM}\s*{YRS}\s*(?:old|of\s+age)", re.I),
]
AGE_MIN = [
    re.compile(rf"(?:≥|>=|at\s+least|minimum(?:\s+age)?(?:\s+of)?)\s*{NUM}\s*{YRS}", re.I),
    re.compile(rf"\b{NUM}\s*{YRS}(?:\s+old)?(?:\s+of\s+age)?\s*(?:or|and)\s*(?:older|above|over)", re.I),
    re.compile(rf"\bage[sd]?\s*(?:≥|>=)\s*{NUM}", re.I),
]
AGE_MAX = [
    re.compile(rf"(?:≤|<=|no\s+older\s+than|maximum(?:\s+age)?(?:\s+of)?)\s*{NUM}\s*{YRS}", re.I),
    re.compile(rf"\bage[sd]?\s*(?:≤|<=)\s*{NUM}", re.I),
    re.compile(rf"\b{NUM}\s*{YRS}(?:\s+old)?(?:\s+of\s+age)?\s*or\s*(?:younger|less|under)", re.I),
]

FEMALE_ONLY = re.compile(r"\b(only\s+(?:women|females?)|(?:women|females?)\s+only|postmenopausal\s+women|pregnant\s+women)\b", re.I)
MALE_ONLY = re.compile(r"\b(only\s+(?:men|males?)|(?:men|males?)\s+only)\b", re.I)
PREGNANCY = re.compile(r"pregnan", re.I)

_ALIAS_ALT = "|".join(re.escape(a) for a in sorted(LAB_ALIASES, key=len, reverse=True))
_LAB = rf"(?<![a-z])({_ALIAS_ALT})(?![a-z])"
_OPS = (r"(≥|>=|≤|<=|>|<|=|greater\s+than\s+or\s+equal\s+to|less\s+than\s+or\s+equal\s+to|"
        r"of\s+at\s+least|at\s+least|no\s+more\s+than|greater\s+than|more\s+than|less\s+than|above|below|over|under)")
_UNIT = r"(%|mg/dl|mmol/l|mmol/mol|kg/m2|kg/m²|ml/min(?:/1\.73\s*m(?:2|²))?|u/l|iu/l)?"
_GAP = r"(?:\s*\([^)]{0,30}\))?[\s:,]*(?:levels?|values?)?\s*"
LAB_RANGE = re.compile(rf"{_LAB}{_GAP}(?:between|of|from)?\s*{NUM}\s*{_UNIT}\s*(?:-|–|to|and)\s*{NUM}\s*{_UNIT}", re.I)
LAB_SINGLE = re.compile(rf"{_LAB}{_GAP}{_OPS}\s*{NUM}\s*{_UNIT}", re.I)


def _first(patterns: list[re.Pattern], text: str) -> Optional[re.Match]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m
    return None


def _ages(incl: str) -> tuple[Optional[float], Optional[float]]:
    m = _first(AGE_RANGE, incl)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo < hi <= 120:
            return lo, hi
    lo_m, hi_m = _first(AGE_MIN, incl), _first(AGE_MAX, incl)
    lo = float(lo_m.group(1)) if lo_m else None
    hi = float(hi_m.group(1)) if hi_m else None
    return lo, hi


def _labs(text: str, section: str) -> list[LabThreshold]:
    out: list[LabThreshold] = []
    taken: list[tuple[int, int]] = []
    for m in LAB_RANGE.finditer(text):
        lo, hi = float(m.group(2)), float(m.group(4))
        if lo >= hi:
            continue
        test = canonical_test(m.group(1))
        unit = normalize_unit(m.group(3) or m.group(5))
        out.append(LabThreshold(test, ">=", lo, section, unit))
        out.append(LabThreshold(test, "<=", hi, section, unit))
        taken.append(m.span())
    for m in LAB_SINGLE.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        out.append(LabThreshold(canonical_test(m.group(1)), normalize_operator(m.group(2)),
                                float(m.group(3)), section, normalize_unit(m.group(4))))
    return out


def extract(criteria_text: str) -> Eligibility:
    incl, excl = split_sections(criteria_text)
    lo, hi = _ages(incl)
    if FEMALE_ONLY.search(incl):
        sex = "FEMALE"
    elif MALE_ONLY.search(incl):
        sex = "MALE"
    else:
        sex = "ALL"
    return Eligibility(
        min_age_years=lo,
        max_age_years=hi,
        sex=sex,
        excludes_pregnancy=bool(PREGNANCY.search(excl)),
        lab_thresholds=_labs(incl, "inclusion") + _labs(excl, "exclusion"),
    )
