"""SQLite storage: raw trials, cached extractions, and flattened query tables."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

from .schema import Eligibility

DEFAULT_DB = os.path.join("data", "trialparse.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (
    nct_id        TEXT PRIMARY KEY,
    title         TEXT,
    conditions    TEXT,          -- JSON list from the registry
    criteria_text TEXT,
    criteria_hash TEXT,
    reg_min_age   REAL,
    reg_max_age   REAL,
    reg_sex       TEXT,
    query         TEXT,
    fetched_at    TEXT
);
CREATE TABLE IF NOT EXISTS extractions (
    nct_id         TEXT,
    method         TEXT,         -- 'regex' or 'llm'
    version        TEXT,         -- regex rule version or LLM prompt version
    model          TEXT,
    criteria_hash  TEXT,
    output_json    TEXT,
    error          TEXT,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    latency_ms     REAL,
    created_at     TEXT,
    PRIMARY KEY (nct_id, method, version)
);
CREATE TABLE IF NOT EXISTS eligibility_conditions (
    nct_id TEXT, method TEXT, version TEXT, kind TEXT, condition TEXT
);
CREATE TABLE IF NOT EXISTS eligibility_labs (
    nct_id TEXT, method TEXT, version TEXT, test TEXT, canonical_test TEXT,
    operator TEXT, value REAL, unit TEXT, section TEXT
);
"""


def connect(path: str = DEFAULT_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def predictions(conn: sqlite3.Connection, method: str, version: Optional[str] = None) -> dict[str, Eligibility]:
    """Successful extractions for one method (and version, if given) keyed by NCT ID."""
    sql = "SELECT nct_id, output_json FROM extractions WHERE method = ? AND error IS NULL"
    args: list = [method]
    if version:
        sql += " AND version = ?"
        args.append(version)
    sql += " ORDER BY created_at"
    out: dict[str, Eligibility] = {}
    for row in conn.execute(sql, args):
        out[row["nct_id"]] = Eligibility.from_dict(json.loads(row["output_json"]))
    return out


def latest_version(conn: sqlite3.Connection, method: str) -> Optional[str]:
    row = conn.execute(
        "SELECT version FROM extractions WHERE method = ? ORDER BY created_at DESC LIMIT 1", (method,)
    ).fetchone()
    return row["version"] if row else None
