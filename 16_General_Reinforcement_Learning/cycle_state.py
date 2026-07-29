#!/usr/bin/env python3
"""
cycle_state.py — self-pacing scheduler state for the GEO analyst cycle.

The cycle decides its OWN cadence: do maximum work in minimum cycles. When it has
actionable work in hand it chains straight into another cycle; when it's blocked on
Will or the signal is quiet it backs off — all under a hard per-day cap so it can
never run away on cost. A cheap dispatcher cron (geo_dispatch.sh, every 20 min in
awake hours) polls this state; the heavy claude -p cycle only fires when due + under cap.

State doc: system_monitor.rl_geo_cycle_state (_id="state").

CLI:
  cycle_state.py --claim                 # dispatcher: exit 0 + print RUN if due & under cap, else exit 10 + SKIP
  cycle_state.py --set-next MIN --reason "..."   # the cycle: schedule its next run in MIN minutes
  cycle_state.py --show                  # print current state
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    AEST = ZoneInfo("Australia/Brisbane")
except Exception:
    AEST = timezone(timedelta(hours=10))

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

COLL = "rl_geo_cycle_state"
SID = "state"

# --- tunables -----------------------------------------------------------------
MAX_CYCLES_PER_DAY = 8       # hard cap — cycle can never exceed this in a rolling AEST day
MIN_GAP_MINUTES = 20         # floor on self-chosen delay (can't hammer)
MAX_GAP_MINUTES = 1440       # ceiling (a full day off)
DEFAULT_BACKOFF_MIN = 1200   # if a cycle forgets to set next_run_at: fail safe (~20h, ~next day)


def _now():
    return datetime.now(timezone.utc)


def _coll():
    return get_client()["system_monitor"][COLL]


def _load():
    d = _coll().find_one({"_id": SID})
    if not d:
        d = {"_id": SID, "next_run_at": _now().isoformat(), "cycles_today": 0,
             "cycles_today_date": _now().astimezone(AEST).strftime("%Y-%m-%d"),
             "max_cycles_per_day": MAX_CYCLES_PER_DAY, "last_run_at": None,
             "last_reason": "seeded", "history": []}
        _coll().insert_one(dict(d))
    return d


def _save(d):
    _coll().replace_one({"_id": SID}, d, upsert=True)


def _roll_day(d):
    today = _now().astimezone(AEST).strftime("%Y-%m-%d")
    if d.get("cycles_today_date") != today:
        d["cycles_today_date"] = today
        d["cycles_today"] = 0
    return d


def claim():
    """Dispatcher entry. If a cycle is due and we're under the daily cap, atomically
    increment the counter and return RUN; otherwise SKIP. Exit 0 = RUN, 10 = SKIP."""
    d = _roll_day(_load())
    cap = int(d.get("max_cycles_per_day", MAX_CYCLES_PER_DAY))
    now = _now()
    nxt = d.get("next_run_at")
    try:
        due = datetime.fromisoformat(nxt) <= now if nxt else True
    except Exception:
        due = True
    if d["cycles_today"] >= cap:
        print(f"SKIP cap-reached ({d['cycles_today']}/{cap} today)")
        _save(d)
        return 10
    if not due:
        print(f"SKIP not-due (next {nxt})")
        _save(d)
        return 10
    # claim it
    d["cycles_today"] += 1
    d["last_run_at"] = now.isoformat()
    # fail-safe: pre-set a long backoff; the cycle overrides via --set-next at its end
    d["next_run_at"] = (now + timedelta(minutes=DEFAULT_BACKOFF_MIN)).isoformat()
    d["last_reason"] = "claimed (awaiting cycle's --set-next)"
    _save(d)
    print(f"RUN (cycle {d['cycles_today']}/{cap} today)")
    return 0


def set_next(minutes, reason):
    d = _roll_day(_load())
    m = max(MIN_GAP_MINUTES, min(MAX_GAP_MINUTES, int(minutes)))
    when = _now() + timedelta(minutes=m)
    d["next_run_at"] = when.isoformat()
    d["last_reason"] = reason[:400]
    d.setdefault("history", []).append({"at": _now().isoformat(), "delay_min": m, "reason": reason[:200]})
    d["history"] = d["history"][-40:]
    _save(d)
    cap = int(d.get("max_cycles_per_day", MAX_CYCLES_PER_DAY))
    chain = "CHAIN (continue soon)" if m <= 60 else "BACK OFF"
    print(f"next cycle in {m} min ({when.astimezone(AEST):%H:%M AEST}) — {chain} · "
          f"{d['cycles_today']}/{cap} used today · reason: {reason[:80]}")


def show():
    d = _roll_day(_load())
    cap = int(d.get("max_cycles_per_day", MAX_CYCLES_PER_DAY))
    print(f"GEO cycle state: {d['cycles_today']}/{cap} cycles today ({d['cycles_today_date']})")
    print(f"  next_run_at: {d.get('next_run_at')}")
    print(f"  last_run_at: {d.get('last_run_at')}")
    print(f"  last_reason: {d.get('last_reason')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claim", action="store_true")
    ap.add_argument("--set-next", type=int, metavar="MIN")
    ap.add_argument("--reason", default="")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    if a.claim:
        sys.exit(claim())
    elif a.set_next is not None:
        set_next(a.set_next, a.reason or "unspecified")
    else:
        show()


if __name__ == "__main__":
    main()
