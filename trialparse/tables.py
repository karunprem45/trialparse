"""Flatten extractions into relational tables you can query with plain SQL."""
from __future__ import annotations

import sqlite3

from . import db as dbm
from .labs import canonical_test


def build(conn: sqlite3.Connection) -> dict[str, int]:
    conn.execute("DELETE FROM eligibility_conditions")
    conn.execute("DELETE FROM eligibility_labs")
    n_c = n_l = 0
    for method in ("regex", "llm"):
        version = dbm.latest_version(conn, method)
        if not version:
            continue
        for nct, e in dbm.predictions(conn, method, version).items():
            for kind, items in (("required", e.required_conditions), ("excluded", e.excluded_conditions)):
                for c in items:
                    conn.execute("INSERT INTO eligibility_conditions VALUES (?,?,?,?,?)",
                                 (nct, method, version, kind, c.lower()))
                    n_c += 1
            for t in e.lab_thresholds:
                conn.execute("INSERT INTO eligibility_labs VALUES (?,?,?,?,?,?,?,?,?)",
                             (nct, method, version, t.test, canonical_test(t.test), t.operator,
                              t.value, t.unit, t.section))
                n_l += 1
    conn.commit()
    return {"condition_rows": n_c, "lab_rows": n_l}
