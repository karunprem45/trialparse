"""Interactive labeling in the terminal. Label BEFORE looking at any model output,
so the gold set isn't biased toward what the model said. See LABELING_GUIDE.md."""
from __future__ import annotations

import random
import re
import sqlite3
import textwrap

from . import gold as gold_io
from .schema import Eligibility, LabThreshold, SchemaError

_LAB = re.compile(r"^\s*(.+?)\s*(>=|<=|>|<|=)\s*(-?\d+(?:\.\d+)?)\s*([^\s]*)\s+(incl|excl)\s*$", re.I)


def parse_labs(s: str) -> list[LabThreshold]:
    out = []
    for part in [p for p in s.split(";") if p.strip()]:
        m = _LAB.match(part)
        if not m:
            raise SchemaError(f"can't read {part!r}. Format: hba1c >= 7 % incl")
        out.append(LabThreshold(m.group(1).strip(), m.group(2), float(m.group(3)),
                                "inclusion" if m.group(5).lower() == "incl" else "exclusion",
                                m.group(4) or None))
    return out


def _ask(prompt: str, parse, allow_blank=True):
    while True:
        raw = input(prompt).strip()
        if raw == "" and allow_blank:
            return parse("")
        try:
            return parse(raw)
        except (ValueError, SchemaError) as e:
            print(f"    -> {e}. Try again.")


def _num(s):
    return None if s == "" else float(s)


def _sex(s):
    s = (s or "ALL").upper()
    if s not in ("ALL", "FEMALE", "MALE"):
        raise ValueError("ALL, FEMALE or MALE")
    return s


def _yn(s):
    if s.lower() not in ("y", "n"):
        raise ValueError("y or n")
    return s.lower() == "y"


def _list(s):
    return [x.strip() for x in s.split(";") if x.strip()]


def sample_ids(conn: sqlite3.Connection, n: int, seed: int) -> list[str]:
    ids = [r["nct_id"] for r in conn.execute("SELECT nct_id FROM trials ORDER BY nct_id")]
    rng = random.Random(seed)
    return rng.sample(ids, min(n, len(ids)))


def run(conn: sqlite3.Connection, gold_path: str, n: int, seed: int) -> None:
    done = gold_io.load(gold_path)
    todo = [i for i in sample_ids(conn, n, seed) if i not in done]
    print(f"{len(done)} already labeled, {len(todo)} to go. Ctrl+C any time; progress is saved per trial.\n")
    for k, nct in enumerate(todo, 1):
        t = conn.execute("SELECT title, criteria_text FROM trials WHERE nct_id=?", (nct,)).fetchone()
        print("=" * 90)
        print(f"[{k}/{len(todo)}] {nct}  {t['title']}")
        print("-" * 90)
        for line in (t["criteria_text"] or "").splitlines():
            print(textwrap.fill(line, 90, subsequent_indent="    ") if line.strip() else "")
        print("-" * 90)
        label = Eligibility(
            min_age_years=_ask("min age in years (blank = none): ", _num),
            max_age_years=_ask("max age in years (blank = none): ", _num),
            sex=_ask("sex ALL/FEMALE/MALE (blank = ALL): ", _sex),
            excludes_pregnancy=_ask("excludes pregnancy? y/n: ", _yn, allow_blank=False),
            required_conditions=_ask("required conditions (; separated): ", _list),
            excluded_conditions=_ask("excluded conditions (; separated): ", _list),
            lab_thresholds=_ask("lab thresholds, e.g. 'hba1c >= 7 % incl; bmi > 45 kg/m2 excl': ", parse_labs),
        )
        note = input("note (optional): ").strip()
        gold_io.append(gold_path, nct, label, note)
        print(f"saved {nct} ({gold_io.split_of(nct)})\n")
