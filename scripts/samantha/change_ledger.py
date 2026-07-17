#!/usr/bin/env python3
"""
change_ledger.py — Samantha's measurable-change ledger ("close the loop").

Every change she ships that affects a measurable conversion metric (a CTA, a copy
change, an ad tweak) gets logged HERE with a BASELINE captured at ship-time and
scheduled re-measurement dates. On later runs she pulls the changes that are "due",
re-measures the metric (via PostHog), records the result + a verdict
(improved / no_change / worse / too_early), reflects, and — if a change made things
WORSE — reverts it (every change is one revertable commit).

Storage: system_monitor.samantha_changes (one doc per change).

Usage:
  # Log a change the moment you ship it (capture the CURRENT metric as baseline):
  change_ledger.py log --type website_cta --title "Crash-risk page CTA strip" \
      --url /market-metrics/Burleigh-Waters/crash-risk --metric bounce_rate \
      --metric-how "PostHog query-web-stats, breakdownBy Page, this page, 7d, includeBounceRate" \
      --baseline 64.5 --baseline-window "7d ending 2026-07-17" \
      --hypothesis "A CTA to /analyse-your-home converts some of the 31 weekly engaged readers" \
      --direction down --commit abc1234 --revert abc1234 --review-days 3,7

  change_ledger.py due                     # changes whose next review date has arrived
  change_ledger.py measure --id <id> --value 52.0 --note "3-day read"   # verdict auto-computed
  change_ledger.py list [--status live]
  change_ledger.py report                  # markdown block for the daily report
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from src.mongo_client_factory import get_mongo_client, cosmos_retry  # noqa: E402

AEST = timezone(timedelta(hours=10))
COLL = "samantha_changes"


def _db():
    return get_mongo_client()["system_monitor"]


def _now():
    return datetime.now(AEST)


def _today():
    return _now().strftime("%Y-%m-%d")


def _new_id(title: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"{_today()}_{slug}"


def _verdict(baseline: float, value: float, direction: str, min_pct: float = 5.0) -> str:
    """direction = 'down' if lower-is-better (e.g. bounce), 'up' if higher-is-better (e.g. CVR)."""
    if baseline in (None, 0):
        return "too_early"
    pct = (value - baseline) / abs(baseline) * 100.0
    better = pct < 0 if direction == "down" else pct > 0
    worse = pct > 0 if direction == "down" else pct < 0
    if abs(pct) < min_pct:
        return "no_change"
    return "improved" if better else ("worse" if worse else "no_change")


def cmd_log(a) -> int:
    review_days = [int(x) for x in (a.review_days or "3,7").split(",") if x.strip()]
    reviews = [( _now() + timedelta(days=d)).strftime("%Y-%m-%d") for d in review_days]
    doc = {
        "change_id": _new_id(a.title), "created_at": _now(), "type": a.type,
        "title": a.title, "url": a.url, "metric": a.metric, "metric_how": a.metric_how,
        "direction": a.direction,  # 'down' = lower is better, 'up' = higher is better
        "baseline": {"value": a.baseline, "window": a.baseline_window,
                     "captured_at": _now().isoformat()},
        "hypothesis": a.hypothesis, "commit": a.commit, "revert_commit": a.revert,
        "status": "live", "review_dates": reviews, "measurements": [],
        "latest_verdict": "too_early", "reflection": None,
    }
    cosmos_retry(lambda: _db()[COLL].update_one({"change_id": doc["change_id"]},
                                                {"$set": doc}, upsert=True))
    print(f"logged {doc['change_id']} | baseline {a.metric}={a.baseline} "
          f"({a.direction}-is-better) | reviews {reviews}")
    return 0


def cmd_due(a) -> int:
    today = _today()
    due = []
    for d in _db()[COLL].find({"status": "live"}):
        pending = [r for r in d.get("review_dates", []) if r <= today
                   and r not in [m.get("review_date") for m in d.get("measurements", [])]]
        if pending:
            due.append((d, min(pending)))
    if not due:
        print("no changes due for review")
        return 0
    for d, r in due:
        b = d.get("baseline", {})
        print(f"DUE {d['change_id']} | metric={d['metric']} baseline={b.get('value')} "
              f"({d.get('direction')}-better) | how: {d.get('metric_how')}")
        print(f"    → re-measure now, then: change_ledger.py measure --id {d['change_id']} --value <X>")
    return 0


def cmd_measure(a) -> int:
    d = _db()[COLL].find_one({"change_id": a.id})
    if not d:
        print(f"no such change: {a.id}")
        return 1
    baseline = (d.get("baseline") or {}).get("value")
    verdict = a.verdict or _verdict(baseline, a.value, d.get("direction", "down"))
    delta = None if baseline in (None, 0) else round((a.value - baseline) / abs(baseline) * 100, 1)
    m = {"date": _today(), "review_date": a.review_date or _today(), "value": a.value,
         "delta_pct_vs_baseline": delta, "verdict": verdict, "note": a.note}
    upd = {"$push": {"measurements": m}, "$set": {"latest_verdict": verdict}}
    if a.reflection:
        upd["$set"]["reflection"] = a.reflection
    if a.status:
        upd["$set"]["status"] = a.status  # e.g. 'validated' or 'rolled_back'
    cosmos_retry(lambda: _db()[COLL].update_one({"change_id": a.id}, upd))
    print(f"measured {a.id}: {d['metric']}={a.value} (Δ{delta}% vs baseline) → {verdict}")
    if verdict == "worse":
        print(f"  ⚠ WORSE — consider reverting commit {d.get('revert_commit')} "
              f"(then: measure --id {a.id} --status rolled_back)")
    return 0


def cmd_list(a) -> int:
    q = {"status": a.status} if a.status else {}
    for d in _db()[COLL].find(q).sort("created_at", -1):
        b = d.get("baseline", {})
        last = d.get("measurements", [])[-1] if d.get("measurements") else None
        print(f"[{d.get('status'):>10}] {d['change_id']} | {d['metric']} "
              f"base={b.get('value')} latest={(last or {}).get('value','-')} "
              f"verdict={d.get('latest_verdict')}")
    return 0


def cmd_report(a) -> int:
    rows = list(_db()[COLL].find().sort("created_at", -1))
    if not rows:
        print("_No tracked changes yet._")
        return 0
    print("| Change | Metric | Baseline | Latest | Verdict | Status |")
    print("|---|---|---|---|---|---|")
    for d in rows:
        b = d.get("baseline", {})
        last = d.get("measurements", [])[-1] if d.get("measurements") else {}
        print(f"| {d['title'][:38]} | {d['metric']} | {b.get('value')} | "
              f"{last.get('value','—')} ({last.get('delta_pct_vs_baseline','—')}%) | "
              f"{d.get('latest_verdict')} | {d.get('status')} |")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("log")
    p.add_argument("--type", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--url", default="")
    p.add_argument("--metric", required=True)
    p.add_argument("--metric-how", default="", help="exactly how to re-measure this metric later")
    p.add_argument("--baseline", type=float, required=True)
    p.add_argument("--baseline-window", default="")
    p.add_argument("--direction", choices=["down", "up"], required=True,
                   help="down = lower is better (bounce); up = higher is better (CVR)")
    p.add_argument("--hypothesis", default="")
    p.add_argument("--commit", default="")
    p.add_argument("--revert", default="")
    p.add_argument("--review-days", default="3,7")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("due"); p.set_defaults(func=cmd_due)

    p = sub.add_parser("measure")
    p.add_argument("--id", required=True)
    p.add_argument("--value", type=float, required=True)
    p.add_argument("--verdict", choices=["improved", "no_change", "worse", "too_early"])
    p.add_argument("--review-date", default="")
    p.add_argument("--note", default="")
    p.add_argument("--reflection", default="")
    p.add_argument("--status", choices=["live", "validated", "rolled_back"])
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("list"); p.add_argument("--status", default=""); p.set_defaults(func=cmd_list)
    p = sub.add_parser("report"); p.set_defaults(func=cmd_report)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
