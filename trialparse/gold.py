"""Gold set file (JSONL) and the fixed dev/test split.

About a quarter of labeled trials land in 'dev' (use these while you adjust the
prompt). The rest are 'test'. Only report test numbers on your resume.
"""
from __future__ import annotations

import hashlib
import json
import os

from .schema import Eligibility

DEFAULT_GOLD = os.path.join("data", "gold.jsonl")


def split_of(nct_id: str) -> str:
    return "dev" if int(hashlib.sha1(nct_id.encode()).hexdigest(), 16) % 4 == 0 else "test"


def load(path: str = DEFAULT_GOLD) -> dict[str, Eligibility]:
    out: dict[str, Eligibility] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                out[rec["nct_id"]] = Eligibility.from_dict(rec["label"])
    return out


def append(path: str, nct_id: str, label: Eligibility, note: str = "") -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"nct_id": nct_id, "label": label.to_dict(), "note": note}) + "\n")
