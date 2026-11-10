"""Score regex and LLM extractions against the gold set, plus a free check
against the registry's own structured age/sex fields on every trial."""
from __future__ import annotations

import json
import os
import statistics
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from . import db as dbm
from . import gold as gold_io
from .metrics import PRF, lab_key, match_labs, match_strings, scalar_equal
from .schema import Eligibility

SCALAR = ["min_age_years", "max_age_years", "sex", "excludes_pregnancy"]
LISTS = ["required_conditions", "excluded_conditions"]
REGEX_SKIPS = set(LISTS)  # regex baseline doesn't attempt these


def score(preds: dict[str, Eligibility], gold: dict[str, Eligibility], method: str,
          threshold: float) -> tuple[dict, list[dict]]:
    acc = {f: [0, 0] for f in SCALAR}
    prf = {f: PRF() for f in LISTS + ["lab_thresholds"]}
    errors: list[dict] = []
    missing = 0
    for nct, g in gold.items():
        p = preds.get(nct)
        if p is None:
            missing += 1
            p = Eligibility()  # a failed extraction counts as empty, not skipped
        for f in SCALAR:
            ok = scalar_equal(getattr(p, f), getattr(g, f))
            acc[f][0] += ok
            acc[f][1] += 1
            if not ok:
                errors.append({"nct_id": nct, "field": f, "pred": getattr(p, f), "gold": getattr(g, f)})
        for f in LISTS:
            pl, gl = getattr(p, f), getattr(g, f)
            m = match_strings(pl, gl, threshold)
            prf[f].add(len(m), len(pl), len(gl))
            hit_p = {i for i, _, _ in m}
            hit_g = {j for _, j, _ in m}
            if method != "regex" and (len(hit_p) < len(pl) or len(hit_g) < len(gl)):
                errors.append({"nct_id": nct, "field": f,
                               "extra": [x for i, x in enumerate(pl) if i not in hit_p],
                               "missed": [x for j, x in enumerate(gl) if j not in hit_g]})
        tp = match_labs(p.lab_thresholds, g.lab_thresholds)
        prf["lab_thresholds"].add(tp, len({lab_key(x) for x in p.lab_thresholds}), len(g.lab_thresholds))
    out = {f: {"accuracy": a / n if n else None, "correct": a, "n": n} for f, (a, n) in acc.items()}
    for f, v in prf.items():
        out[f] = None if (method == "regex" and f in REGEX_SKIPS) else v.as_dict()
    out["_missing_predictions"] = missing
    return out, errors


def registry_agreement(conn: sqlite3.Connection, preds: dict[str, Eligibility]) -> dict:
    counts = {"min_age_years": [0, 0], "max_age_years": [0, 0], "sex": [0, 0]}
    for r in conn.execute("SELECT nct_id, reg_min_age, reg_max_age, reg_sex FROM trials"):
        p = preds.get(r["nct_id"])
        if p is None:
            continue
        for f, reg in (("min_age_years", r["reg_min_age"]), ("max_age_years", r["reg_max_age"]), ("sex", r["reg_sex"])):
            if reg is None:
                continue  # registry left it blank, nothing to compare
            counts[f][0] += scalar_equal(getattr(p, f), reg)
            counts[f][1] += 1
    return {f: {"agreement": a / n if n else None, "n": n} for f, (a, n) in counts.items()}


def usage(conn: sqlite3.Connection, version: Optional[str]) -> dict:
    sql = "SELECT input_tokens, output_tokens, latency_ms, error FROM extractions WHERE method='llm'"
    args: list = []
    if version:
        sql += " AND version=?"
        args.append(version)
    rows = conn.execute(sql, args).fetchall()
    ok = [r for r in rows if r["error"] is None]
    lat = sorted(r["latency_ms"] for r in ok if r["latency_ms"] is not None)
    return {
        "calls_ok": len(ok), "calls_failed": len(rows) - len(ok),
        "input_tokens": sum(r["input_tokens"] or 0 for r in ok),
        "output_tokens": sum(r["output_tokens"] or 0 for r in ok),
        "latency_p50_ms": statistics.median(lat) if lat else None,
        "latency_p95_ms": lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else None,
    }


def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def _cell(m) -> str:
    if m is None:
        return "not attempted"
    if "accuracy" in m:
        return f"{_fmt(m['accuracy'])} ({m['correct']}/{m['n']})"
    return f"P {_fmt(m['precision'])}  R {_fmt(m['recall'])}  F1 {_fmt(m['f1'])}"


def run(conn: sqlite3.Connection, gold_path: str, split: str, threshold: float, out_dir: str = "results") -> dict:
    gold_all = gold_io.load(gold_path)
    gold = {k: v for k, v in gold_all.items() if split == "all" or gold_io.split_of(k) == split}
    if not gold:
        raise SystemExit(f"No gold trials in split '{split}'. Label more with: python -m trialparse label")
    llm_v = dbm.latest_version(conn, "llm")
    regex_v = dbm.latest_version(conn, "regex")
    methods = {}
    if regex_v:
        methods["regex"] = dbm.predictions(conn, "regex", regex_v)
    if llm_v:
        methods["llm"] = dbm.predictions(conn, "llm", llm_v)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": split, "n_gold": len(gold), "match_threshold": threshold,
        "versions": {"regex": regex_v, "llm": llm_v},
        "n_trials_in_db": conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0],
        "gold_scores": {}, "registry_agreement": {}, "llm_usage": usage(conn, llm_v) if llm_v else None,
    }
    all_errors = {}
    for name, preds in methods.items():
        report["gold_scores"][name], all_errors[name] = score(preds, gold, name, threshold)
        report["registry_agreement"][name] = registry_agreement(conn, preds)

    names = list(methods)
    print(f"\nGold set: {len(gold)} trials ({split} split). Trials in DB: {report['n_trials_in_db']}\n")
    print("| Field | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for f in SCALAR + LISTS + ["lab_thresholds"]:
        print(f"| {f} | " + " | ".join(_cell(report["gold_scores"][n][f]) for n in names) + " |")
    print("\nAgreement with registry structured fields (all trials in DB):")
    for n in names:
        ra = report["registry_agreement"][n]
        print(f"  {n}: " + ", ".join(f"{f} {_fmt(v['agreement'])} (n={v['n']})" for f, v in ra.items()))
    if report["llm_usage"]:
        u = report["llm_usage"]
        print(f"\nLLM usage: {u['calls_ok']} ok, {u['calls_failed']} failed, "
              f"{u['input_tokens']} in / {u['output_tokens']} out tokens, "
              f"p50 {_fmt(u['latency_p50_ms'])} ms, p95 {_fmt(u['latency_p95_ms'])} ms")

    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(out_dir, f"eval_{split}_{stamp}.json"), "w") as f:
        json.dump(report, f, indent=2)
    for n, errs in all_errors.items():
        with open(os.path.join(out_dir, f"errors_{n}_{split}_{stamp}.jsonl"), "w") as f:
            for e in errs:
                f.write(json.dumps(e, default=str) + "\n")
    print(f"\nSaved report and error lists to {out_dir}/")
    return report
