"""Helpers for registry text: section splitting, registry age parsing, hashing."""
from __future__ import annotations

import hashlib
import re
from typing import Optional

_EXCL = re.compile(r"exclusion\s+criteria\s*:?", re.I)
_INCL = re.compile(r"inclusion\s+criteria\s*:?", re.I)
_AGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(year|month|week|day)s?\s*$", re.I)
_AGE_FACTOR = {"year": 1.0, "month": 1 / 12, "week": 1 / 52, "day": 1 / 365}


def split_sections(text: Optional[str]) -> tuple[str, str]:
    """Return (inclusion, exclusion). If no exclusion header, everything is inclusion."""
    if not text:
        return "", ""
    m = _EXCL.search(text)
    if not m:
        return _INCL.sub("", text, count=1).strip(), ""
    incl = _INCL.sub("", text[: m.start()], count=1)
    return incl.strip(), text[m.end():].strip()


def parse_registry_age(s: Optional[str]) -> Optional[float]:
    """'18 Years' -> 18.0, '6 Months' -> 0.5, 'N/A' or None -> None."""
    if not s:
        return None
    m = _AGE.match(s)
    if not m:
        return None
    return round(float(m.group(1)) * _AGE_FACTOR[m.group(2).lower()], 2)


def text_hash(text: Optional[str]) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]
