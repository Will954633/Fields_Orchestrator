#!/usr/bin/env python3
"""
cadence.py — self-paced, work-driven cadence for the Off-Market RL cycle (Will, 2026-07-29).

The cycle decides its OWN next wake: chain straight into another cycle when it has queued
work; sleep to the data-accrual point when it's waiting on an experiment; long-sleep when
there's nothing to do. Two hard rails enforced HERE (not trusted to the cycle):
  * MAX 6 full cycles per rolling 24h  (runaway backstop — cost + don't thrash the live site)
  * MIN 15 min between any two cycles   (a reward verdict can't change faster than that anyway)

A cheap */15 tick (`tick.sh`) calls `--should-run`; a cycle ends by calling `--set-next`.
State: `system_monitor.rl_cadence_state` (_id="offmarket").

  cadence.py --should-run                 -> prints RUN or SKIP:<reason> (exit 0/1)
  cadence.py --record-run                 -> stamp a run start (tick calls this before launching)
  cadence.py --set-next MIN [--chain] [--reason "..."]   -> cycle sets its next wake
  cadence.py --show
"""
import argparse
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

MAX_PER_24H = 6
MIN_GAP_MIN = 15
DEFAULT_NEXT_MIN = 360   # if a cycle forgets to set next_due, don't spin — wait 6h

def _coll():
    return get_client()["system_monitor"]["rl_cadence_state"]

def _state():
    return _coll().find_one({"_id": "offmarket"}) or {"_id": "offmarket", "runs_24h": [], "next_due": None,
                                                       "work_queued": False, "last_run": None}

def _now():
    return datetime.now(timezone.utc)

def _parse(s):
    try:
        return datetime.fromisoformat(str(s))
    except Exception:
        return None

def should_run():
    s = _state()
    now = _now()
    runs = [r for r in (s.get("runs_24h") or []) if (_parse(r) and _parse(r) > now - timedelta(hours=24))]
    if len(runs) >= MAX_PER_24H:
        return False, f"cap:{len(runs)}/{MAX_PER_24H} in 24h"
    last = _parse(s.get("last_run"))
    if last and last > now - timedelta(minutes=MIN_GAP_MIN):
        return False, f"floor:<{MIN_GAP_MIN}min since last"
    if s.get("work_queued"):
        return True, "work_queued"
    nd = _parse(s.get("next_due"))
    if nd is None or now >= nd:
        return True, "due" if nd else "no_next_due"
    return False, f"not_due (next {nd.isoformat()})"

def record_run():
    s = _state()
    now = _now()
    runs = [r for r in (s.get("runs_24h") or []) if (_parse(r) and _parse(r) > now - timedelta(hours=24))]
    runs.append(now.isoformat())
    # clearing work_queued + next_due; the cycle re-sets them via --set-next at its end
    _coll().update_one({"_id": "offmarket"},
        {"$set": {"runs_24h": runs, "last_run": now.isoformat(),
                  "work_queued": False, "next_due": (now + timedelta(minutes=DEFAULT_NEXT_MIN)).isoformat()}},
        upsert=True)
    print(f"recorded run; {len(runs)}/{MAX_PER_24H} in last 24h")

def set_next(minutes, chain, reason):
    now = _now()
    nd = (now + timedelta(minutes=max(MIN_GAP_MIN, int(minutes)))).isoformat()
    _coll().update_one({"_id": "offmarket"},
        {"$set": {"next_due": nd, "work_queued": bool(chain), "next_reason": reason or "",
                  "next_set_at": now.isoformat()}}, upsert=True)
    print(f"next cycle {'CHAIN (work queued, next tick)' if chain else 'due '+nd}; reason: {reason}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--should-run", action="store_true")
    ap.add_argument("--record-run", action="store_true")
    ap.add_argument("--set-next", type=int, metavar="MIN")
    ap.add_argument("--chain", action="store_true")
    ap.add_argument("--reason", default="")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    if a.should_run:
        ok, why = should_run()
        print("RUN" if ok else f"SKIP:{why}")
        sys.exit(0 if ok else 1)
    if a.record_run:
        record_run(); return
    if a.set_next is not None:
        set_next(a.set_next, a.chain, a.reason); return
    # default / --show
    s = _state()
    now = _now()
    runs = [r for r in (s.get("runs_24h") or []) if (_parse(r) and _parse(r) > now - timedelta(hours=24))]
    print(f"cadence: {len(runs)}/{MAX_PER_24H} in 24h | last_run={s.get('last_run')} | "
          f"next_due={s.get('next_due')} | work_queued={s.get('work_queued')} | reason={s.get('next_reason')}")

if __name__ == "__main__":
    main()
