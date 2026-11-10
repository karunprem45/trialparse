"""Pull trials from the ClinicalTrials.gov v2 API into SQLite."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .text import parse_registry_age, text_hash

API = "https://clinicaltrials.gov/api/v2/studies"


def parse_study(study: dict[str, Any]) -> Optional[dict[str, Any]]:
    ps = study.get("protocolSection") or {}
    ident = ps.get("identificationModule") or {}
    elig = ps.get("eligibilityModule") or {}
    cond = ps.get("conditionsModule") or {}
    nct = ident.get("nctId")
    text = elig.get("eligibilityCriteria")
    if not nct or not text:
        return None
    return {
        "nct_id": nct,
        "title": ident.get("briefTitle"),
        "conditions": json.dumps(cond.get("conditions") or []),
        "criteria_text": text,
        "criteria_hash": text_hash(text),
        "reg_min_age": parse_registry_age(elig.get("minimumAge")),
        "reg_max_age": parse_registry_age(elig.get("maximumAge")),
        "reg_sex": (elig.get("sex") or None),
    }


def fetch_studies(condition: str, max_trials: int, status: str = "RECRUITING") -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "query.cond": condition,
        "filter.overallStatus": status,
        "pageSize": min(100, max_trials),
        "format": "json",
    }
    out: list[dict[str, Any]] = []
    token = None
    while len(out) < max_trials:
        if token:
            params["pageToken"] = token
        req = Request(f"{API}?{urlencode(params)}", headers={"User-Agent": "trialparse/0.1 (student project)"})
        with urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        for s in data.get("studies", []):
            rec = parse_study(s)
            if rec:
                out.append(rec)
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(0.5)  # be polite to the public API
    return out[:max_trials]


def upsert(conn: sqlite3.Connection, rows: list[dict[str, Any]], query: str) -> tuple[int, int]:
    """Insert new trials, update changed ones. Returns (new, changed)."""
    now = datetime.now(timezone.utc).isoformat()
    new = changed = 0
    for r in rows:
        old = conn.execute("SELECT criteria_hash FROM trials WHERE nct_id = ?", (r["nct_id"],)).fetchone()
        if old is None:
            new += 1
        elif old["criteria_hash"] != r["criteria_hash"]:
            changed += 1
        conn.execute(
            """INSERT INTO trials (nct_id, title, conditions, criteria_text, criteria_hash,
                                   reg_min_age, reg_max_age, reg_sex, query, fetched_at)
               VALUES (:nct_id, :title, :conditions, :criteria_text, :criteria_hash,
                       :reg_min_age, :reg_max_age, :reg_sex, :query, :fetched_at)
               ON CONFLICT(nct_id) DO UPDATE SET
                   title = excluded.title, conditions = excluded.conditions,
                   criteria_text = excluded.criteria_text, criteria_hash = excluded.criteria_hash,
                   reg_min_age = excluded.reg_min_age, reg_max_age = excluded.reg_max_age,
                   reg_sex = excluded.reg_sex, fetched_at = excluded.fetched_at""",
            {**r, "query": query, "fetched_at": now},
        )
    conn.commit()
    return new, changed
