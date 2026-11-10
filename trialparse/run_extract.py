"""Run regex and/or LLM extraction over stored trials, skipping cached results."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from . import llm_extract, regex_baseline


def _cached(conn, nct_id, method, version, criteria_hash) -> bool:
    row = conn.execute(
        "SELECT criteria_hash, error FROM extractions WHERE nct_id=? AND method=? AND version=?",
        (nct_id, method, version),
    ).fetchone()
    return bool(row) and row["criteria_hash"] == criteria_hash and row["error"] is None


def _save(conn, nct_id, method, version, model, criteria_hash, output, error,
          input_tokens=None, output_tokens=None, latency_ms=None):
    conn.execute(
        """INSERT OR REPLACE INTO extractions
           (nct_id, method, version, model, criteria_hash, output_json, error,
            input_tokens, output_tokens, latency_ms, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (nct_id, method, version, model, criteria_hash,
         json.dumps(output.to_dict()) if output else None, error,
         input_tokens, output_tokens, latency_ms, datetime.now(timezone.utc).isoformat()),
    )


def run(conn: sqlite3.Connection, method: str, model: str = llm_extract.DEFAULT_MODEL,
        limit: Optional[int] = None, force: bool = False, only_ids: Optional[set[str]] = None) -> dict:
    trials = conn.execute("SELECT nct_id, title, criteria_text, criteria_hash FROM trials ORDER BY nct_id").fetchall()
    if only_ids is not None:
        trials = [t for t in trials if t["nct_id"] in only_ids]
    version = regex_baseline.VERSION if method == "regex" else llm_extract.PROMPT_VERSION
    client = llm_extract.make_client() if method == "llm" else None
    stats = {"done": 0, "skipped": 0, "failed": 0}
    for t in trials:
        if limit is not None and stats["done"] + stats["failed"] >= limit:
            break
        if not force and _cached(conn, t["nct_id"], method, version, t["criteria_hash"]):
            stats["skipped"] += 1
            continue
        if method == "regex":
            _save(conn, t["nct_id"], method, version, None, t["criteria_hash"],
                  regex_baseline.extract(t["criteria_text"]), None)
            stats["done"] += 1
        else:
            try:
                r = llm_extract.extract(client, model, t["title"] or "", t["criteria_text"])
                _save(conn, t["nct_id"], method, version, model, t["criteria_hash"], r["result"], None,
                      r["input_tokens"], r["output_tokens"], r["latency_ms"])
                stats["done"] += 1
                print(f"  {t['nct_id']}  ok  {r['latency_ms']:.0f} ms")
            except Exception as e:
                _save(conn, t["nct_id"], method, version, model, t["criteria_hash"], None, str(e))
                stats["failed"] += 1
                print(f"  {t['nct_id']}  FAILED  {e}")
        conn.commit()
    return stats
