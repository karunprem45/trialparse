"""Command line: python -m trialparse <command> --help"""
from __future__ import annotations

import argparse

from . import db as dbm
from . import evaluate, fetch, gold, label, llm_extract, run_extract, tables


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="trialparse")
    ap.add_argument("--db", default=dbm.DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="pull trials from ClinicalTrials.gov")
    f.add_argument("--condition", default="type 2 diabetes")
    f.add_argument("--max", type=int, default=300)
    f.add_argument("--status", default="RECRUITING")

    e = sub.add_parser("extract", help="run extraction (cached; only new or changed trials)")
    e.add_argument("--method", choices=["regex", "llm", "both"], default="both")
    e.add_argument("--model", default=llm_extract.DEFAULT_MODEL)
    e.add_argument("--limit", type=int, default=None)
    e.add_argument("--force", action="store_true")
    e.add_argument("--gold-only", action="store_true", help="only extract trials in the gold set (cheap first run)")
    e.add_argument("--gold", default=gold.DEFAULT_GOLD)

    l = sub.add_parser("label", help="hand-label a random sample for the gold set")
    l.add_argument("--n", type=int, default=40)
    l.add_argument("--seed", type=int, default=7)
    l.add_argument("--gold", default=gold.DEFAULT_GOLD)

    v = sub.add_parser("evaluate", help="score methods against the gold set")
    v.add_argument("--gold", default=gold.DEFAULT_GOLD)
    v.add_argument("--split", choices=["dev", "test", "all"], default="test")
    v.add_argument("--threshold", type=float, default=0.5, help="token-overlap needed for a condition match")

    sub.add_parser("build-tables", help="flatten extractions into query tables")
    sub.add_parser("stats", help="row counts")

    a = ap.parse_args(argv)
    conn = dbm.connect(a.db)

    if a.cmd == "fetch":
        rows = fetch.fetch_studies(a.condition, a.max, a.status)
        new, changed = fetch.upsert(conn, rows, a.condition)
        print(f"fetched {len(rows)} trials: {new} new, {changed} with changed criteria")
    elif a.cmd == "extract":
        only = set(gold.load(a.gold)) if a.gold_only else None
        for m in (["regex", "llm"] if a.method == "both" else [a.method]):
            print(f"{m}: {run_extract.run(conn, m, a.model, a.limit, a.force, only)}")
    elif a.cmd == "label":
        label.run(conn, a.gold, a.n, a.seed)
    elif a.cmd == "evaluate":
        evaluate.run(conn, a.gold, a.split, a.threshold)
    elif a.cmd == "build-tables":
        print(tables.build(conn))
    elif a.cmd == "stats":
        for t in ("trials", "extractions", "eligibility_conditions", "eligibility_labs"):
            print(t, conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        for r in conn.execute("SELECT method, version, COUNT(*) n, SUM(error IS NOT NULL) failed "
                              "FROM extractions GROUP BY method, version"):
            print(f"  {r['method']} {r['version']}: {r['n']} rows, {r['failed']} failed")


if __name__ == "__main__":
    main()
