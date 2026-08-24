#!/usr/bin/env python3
"""
update_macro_context.py -- recompute the `derived` block of macro_context.json
from its accumulating monthly `history`.

Why this exists
---------------
The owner-subject article's national heading wants two claims the raw monthly
figures don't state outright: how many months the southern capitals have been
falling, and whether Brisbane -- long the exception -- has just turned. Both are
FUNCTIONS of the monthly history, so they must be computed from it, never typed by
hand (a hand-typed "falling for 4 months" silently rots the moment a new release
lands). This script is that computation. Append the month to `history` after each
Cotality release; this recomputes `derived`; the article reads `derived`.

It is deliberately pure data-hygiene: it reads and writes ONE json file, touches
no database, and is safe to run any number of times.

Self-monitoring (CLAUDE.md Rule 7 + 7b): wrapped in job_run so a silent failure
surfaces on the health board, and it RAISES on the zero-output path -- an empty or
all-null history is a broken input, not a quiet success.

    python3 update_macro_context.py            # recompute in place
    python3 update_macro_context.py --show      # recompute and print derived
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

MACRO_PATH = os.path.join(HERE, "macro_context.json")
DEFAULT_SOUTHERN = ["sydney", "melbourne"]


def _month_label(month: str) -> str:
    """'2026-06' -> 'June 2026'."""
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return month


def compute_derived(data: dict) -> dict:
    history = sorted((data.get("history") or []), key=lambda e: e.get("month", ""))
    southern = data.get("southern_cities") or DEFAULT_SOUTHERN

    d = {
        "_comment": "COMPUTED by update_macro_context.py from history. Do not hand-edit.",
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "history_months": len(history),
        "southern_cities": southern,
        "southern_falling_streak_months": None,
        "southern_streak_from_month": None,
        "brisbane_latest_pct": None,
        "brisbane_latest_month": None,
        "brisbane_latest_month_name": None,
        "brisbane_just_turned": None,
        "brisbane_prev_positive_month": None,
        # True when any month CONTRIBUTING to the streak/flip claim is flagged
        # provisional -- the article reads this and warns at build time so a
        # placeholder-fed headline cannot silently reach print.
        "uses_provisional": False,
    }
    if not history:
        return d

    def city(entry, name):
        return (entry.get("cities") or {}).get(name)

    # Southern falling streak: count back from the newest month while EVERY named
    # southern city has a negative figure. A null (not-yet-entered) breaks the run
    # rather than being read as a fall.
    streak = 0
    start_month = None
    provisional_in_streak = False
    for entry in reversed(history):
        vals = [city(entry, c) for c in southern]
        if vals and all(isinstance(v, (int, float)) and v < 0 for v in vals):
            streak += 1
            start_month = entry.get("month")
            if entry.get("provisional"):
                provisional_in_streak = True
        else:
            break
    d["southern_falling_streak_months"] = streak
    d["southern_streak_from_month"] = start_month

    # Brisbane: latest figure, and whether it JUST turned negative (i.e. the most
    # recent month is < 0 and the immediately preceding month with a figure was >= 0).
    bris = [(e.get("month"), city(e, "brisbane"), e.get("provisional"))
            for e in history if isinstance(city(e, "brisbane"), (int, float))]
    if bris:
        last_month, last_val, last_prov = bris[-1]
        d["brisbane_latest_pct"] = last_val
        d["brisbane_latest_month"] = last_month
        d["brisbane_latest_month_name"] = _month_label(last_month).split()[0] \
            if last_month else None
        if last_val < 0 and len(bris) >= 2:
            prev_month, prev_val, prev_prov = bris[-2]
            d["brisbane_just_turned"] = prev_val >= 0
            if prev_val >= 0:
                d["brisbane_prev_positive_month"] = prev_month
                if prev_prov:
                    provisional_in_streak = True
        else:
            d["brisbane_just_turned"] = False
        if last_prov:
            provisional_in_streak = True

    d["uses_provisional"] = provisional_in_streak
    return d


def run(show: bool = False) -> dict:
    with open(MACRO_PATH) as fh:
        data = json.load(fh)

    history = data.get("history") or []
    # Zero-output assertion (Rule 7b): a run that computed nothing because the input
    # is empty/degenerate is a failure, not a quiet success.
    usable = [e for e in history
              if any(isinstance(v, (int, float))
                     for v in (e.get("cities") or {}).values())]
    if not usable:
        raise RuntimeError(
            "macro history has no month with any city figure -- nothing to derive "
            "(seed history in macro_context.json before running)")

    derived = compute_derived(data)
    data["derived"] = derived
    with open(MACRO_PATH, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")

    if show:
        print(json.dumps(derived, indent=2))
    return derived


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="print the derived block")
    ap.add_argument("--no-heartbeat", action="store_true",
                    help="skip job_status heartbeat (for ad-hoc local runs)")
    a = ap.parse_args()

    if a.no_heartbeat:
        d = run(a.show)
        print(f"derived: streak={d['southern_falling_streak_months']} "
              f"brisbane={d['brisbane_latest_pct']} "
              f"just_turned={d['brisbane_just_turned']}", file=sys.stderr)
        return 0

    try:
        from job_status import job_run
    except Exception:                                   # helper not importable -> run bare
        run(a.show)
        return 0

    with job_run("owner_article_macro_context", cadence_hours=744,
                 title="Owner-article macro context") as beat:
        d = run(a.show)
        beat.metrics = {
            "history_months": d["history_months"],
            "southern_streak_months": d["southern_falling_streak_months"] or 0,
        }
        beat.detail = (f"streak {d['southern_falling_streak_months']} mo, "
                       f"Brisbane {d['brisbane_latest_pct']} "
                       f"({'just turned' if d['brisbane_just_turned'] else 'no flip'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
