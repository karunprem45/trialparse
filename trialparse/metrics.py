"""Matching and scoring. Condition names match by token overlap (Jaccard), because
'type 2 diabetes' and 'type 2 diabetes mellitus' are the same answer."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .labs import canonical_test
from .schema import LabThreshold

STOP = {"the", "of", "a", "an", "with", "or", "and", "known", "history", "any", "diagnosis",
        "diagnosed", "current", "active", "prior", "previous"}
SYNONYMS = {"mellitus": "", "t2d": "type 2 diabetes", "t2dm": "type 2 diabetes", "t1d": "type 1 diabetes",
            "ckd": "chronic kidney disease", "copd": "chronic obstructive pulmonary disease",
            "mi": "myocardial infarction", "hf": "heart failure"}


def tokens(s: str) -> frozenset[str]:
    out: list[str] = []
    for t in re.findall(r"[a-z0-9]+", s.lower()):
        t = SYNONYMS.get(t, t)
        out.extend(t.split())
    return frozenset(t for t in out if t and t not in STOP)


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_strings(pred: list[str], gold: list[str], threshold: float = 0.5) -> list[tuple[int, int, float]]:
    """Greedy one-to-one matching, best pairs first."""
    pairs = sorted(((jaccard(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gold)), reverse=True)
    used_p: set[int] = set()
    used_g: set[int] = set()
    out = []
    for score, i, j in pairs:
        if score < threshold:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        out.append((i, j, score))
    return out


def lab_key(t: LabThreshold) -> tuple:
    return (canonical_test(t.test), t.operator, round(float(t.value), 3), t.section)


def match_labs(pred: list[LabThreshold], gold: list[LabThreshold]) -> int:
    remaining = [lab_key(g) for g in gold]
    tp = 0
    for p in {lab_key(p) for p in pred}:
        if p in remaining:
            remaining.remove(p)
            tp += 1
    return tp


def scalar_equal(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) < 0.01
    return a == b


@dataclass
class PRF:
    tp: int = 0
    n_pred: int = 0
    n_gold: int = 0

    def add(self, tp: int, n_pred: int, n_gold: int) -> None:
        self.tp += tp
        self.n_pred += n_pred
        self.n_gold += n_gold

    @property
    def precision(self) -> Optional[float]:
        return self.tp / self.n_pred if self.n_pred else None

    @property
    def recall(self) -> Optional[float]:
        return self.tp / self.n_gold if self.n_gold else None

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None if p is None or r is None else 0.0
        return 2 * p * r / (p + r)

    def as_dict(self) -> dict:
        return {"tp": self.tp, "n_pred": self.n_pred, "n_gold": self.n_gold,
                "precision": self.precision, "recall": self.recall, "f1": self.f1}
