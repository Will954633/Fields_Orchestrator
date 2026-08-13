#!/usr/bin/env python3
"""
article_chain.py — lets the ARTICLES domain run again soon instead of waiting a week.

WHY (Will, 2026-08-13): "it should work continuously until it reaches a point where it
believes everything that should be done now has been done and that most benefit would be in
waiting till the next scheduled wake cycle."

⚠ THIS IS SELF-PACING, WHICH IS THE THING THAT BROKE THE PREVIOUS SYSTEM. That system let
six domains each schedule themselves up to 14 times a day, each with its own Telegram line
to Will; it produced 27 cycles and 31 decision items in 48 hours and was switched off. So
this is deliberately narrower, and the difference is worth stating precisely:

  - ONE domain has it, not six.
  - The cap that actually mattered is untouched: articles still cannot message Will, and
    still cannot hold more than 2 open recommendations. **The cap is on Will's attention,
    not on the agent's effort** — which is the whole reason chaining is safe here.
  - Chaining requires a STATED NEXT TASK. "More work exists" is not a reason.
  - A chain that produces no artefact stops the chain. Working without output is exactly
    how the old system looked productive while achieving nothing.

Guards (not overridable by the agent):
  MAX_PER_DAY / MAX_PER_WEEK   hard ceilings on chained runs
  MIN_GAP_MINUTES              floor between sessions
  MAX_BARREN                   consecutive no-artefact sessions before a forced stop

State: system_monitor.rl_article_chain (_id="state") + an append-only decision log.
A cheap cron polls --claim; the expensive agent runs only when a chain is genuinely due.

CLI (the agent calls exactly one of the first two, every session):
  article_chain.py --continue --reason "revise the flagship body; scroll is 10.1% on n=37"
  article_chain.py --stop     --reason "blocked on Will for both open recommendations"
  article_chain.py --claim     # cron: exit 0 = run now, exit 10 = not due
  article_chain.py --show
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    AEST = ZoneInfo("Australia/Brisbane")
except Exception:  # pragma: no cover
    AEST = timezone(timedelta(hours=10))

COLL = "rl_article_chain"
SID = "state"

MAX_PER_DAY = 6          # chained runs per AEST day, on top of the weekly scheduled cycle
MAX_PER_WEEK = 20
MIN_GAP_MINUTES = 20
MAX_BARREN = 2           # consecutive sessions producing no artefact -> forced stop


def _now():
    return datetime.now(timezone.utc)


def _today():
    return _now().astimezone(AEST).strftime("%Y-%m-%d")


def _week():
    return _now().astimezone(AEST).strftime("%G-W%V")


def _c():
    return get_client()["system_monitor"][COLL]


def _load():
    d = _c().find_one({"_id": SID})
    if not d:
        d = {"_id": SID, "next_run_at": None, "day": _today(), "runs_today": 0,
             "week": _week(), "runs_week": 0, "barren_streak": 0,
             "last_reason": None, "last_decision": None, "log": []}
        _c().insert_one(dict(d))
    if d.get("day") != _today():
        d["day"], d["runs_today"] = _today(), 0
    if d.get("week") != _week():
        d["week"], d["runs_week"] = _week(), 0
    return d


def _save(d):
    _c().replace_one({"_id": SID}, d, upsert=True)


def _artefacts_since(since_iso):
    """Did the last session actually DO anything? Chaining while producing nothing is the
    failure mode this exists to stop, so 'productive' is defined by artefacts on disk or in
    the database, never by the agent's own say-so."""
    sm = get_client()["system_monitor"]
    n = 0
    try:
        n += sm["rl_articles_actions"].count_documents({"created_at": {"$gt": since_iso}})
    except Exception:
        pass
    for coll, field in (("article_pending_approval", "created_at"),
                        ("content_article_revisions", "snapshot_at"),
                        ("rl_recommendations", "created_at")):
        try:
            q = {field: {"$gt": since_iso}}
            if coll == "rl_recommendations":
                q["domain"] = "articles"
            n += sm[coll].count_documents(q)
        except Exception:
            pass
    return n


def cmd_continue(a):
    d = _load()
    reason = (a.reason or "").strip()
    if len(reason) < 15:
        sys.exit("REFUSED: --reason must name the SPECIFIC next task. 'more work exists' is "
                 "not a reason — if you cannot name what you would do next, stop instead.")

    # Rule 7b applied to chaining: assert the last session produced something.
    last = d.get("last_run_at")
    if last:
        made = _artefacts_since(last)
        if made == 0:
            d["barren_streak"] = int(d.get("barren_streak", 0)) + 1
        else:
            d["barren_streak"] = 0
        if d["barren_streak"] >= MAX_BARREN:
            d.update(next_run_at=None, last_decision="forced_stop_barren",
                     last_reason=f"{d['barren_streak']} consecutive sessions produced no "
                                 f"artefact; chain stopped")
            _save(d)
            sys.exit(f"CHAIN STOPPED: {d['barren_streak']} consecutive sessions produced "
                     f"nothing. Working without output is how the old system looked busy "
                     f"while achieving nothing. Wait for the scheduled cycle.")

    if d["runs_today"] >= MAX_PER_DAY:
        d.update(next_run_at=None, last_decision="capped_day")
        _save(d)
        sys.exit(f"CAP: {d['runs_today']}/{MAX_PER_DAY} chained runs today. Stopping until "
                 f"tomorrow — the remaining work keeps.")
    if d["runs_week"] >= MAX_PER_WEEK:
        d.update(next_run_at=None, last_decision="capped_week")
        _save(d)
        sys.exit(f"CAP: {d['runs_week']}/{MAX_PER_WEEK} chained runs this week. Stopping.")

    when = _now() + timedelta(minutes=MIN_GAP_MINUTES)
    d.update(next_run_at=when.isoformat(), last_decision="continue", last_reason=reason)
    d.setdefault("log", []).append({"at": _now().isoformat(), "decision": "continue",
                                    "reason": reason[:300]})
    d["log"] = d["log"][-60:]
    _save(d)
    print(f"CONTINUE — next session ~{when.astimezone(AEST):%H:%M AEST} "
          f"({d['runs_today']}/{MAX_PER_DAY} today, {d['runs_week']}/{MAX_PER_WEEK} this week)")
    print(f"  next task: {reason[:120]}")


def cmd_stop(a):
    d = _load()
    reason = (a.reason or "").strip() or "unspecified"
    d.update(next_run_at=None, last_decision="stop", last_reason=reason)
    d.setdefault("log", []).append({"at": _now().isoformat(), "decision": "stop",
                                    "reason": reason[:300]})
    d["log"] = d["log"][-60:]
    _save(d)
    print(f"STOP — waiting for the scheduled weekly cycle. Reason: {reason[:150]}")


def cmd_claim(a):
    """Cron entry. Exit 0 = launch a chained session, 10 = not due."""
    d = _load()
    nxt = d.get("next_run_at")
    if not nxt:
        print("SKIP no-chain-requested")
        _save(d)
        return 10
    if d["runs_today"] >= MAX_PER_DAY or d["runs_week"] >= MAX_PER_WEEK:
        d["next_run_at"] = None
        _save(d)
        print("SKIP cap-reached")
        return 10
    try:
        due = datetime.fromisoformat(nxt) <= _now()
    except Exception:
        due = True
    if not due:
        print(f"SKIP not-due (next {nxt})")
        _save(d)
        return 10
    d["runs_today"] += 1
    d["runs_week"] += 1
    d["last_run_at"] = _now().isoformat()
    d["next_run_at"] = None          # the agent must ask again to chain further
    _save(d)
    print(f"RUN chained session {d['runs_today']}/{MAX_PER_DAY} today")
    return 0


def cmd_show(a):
    d = _load()
    print(f"articles chain — {d['runs_today']}/{MAX_PER_DAY} today, "
          f"{d['runs_week']}/{MAX_PER_WEEK} this week, barren streak {d.get('barren_streak',0)}")
    print(f"  next_run_at : {d.get('next_run_at') or '(none — waiting for weekly cycle)'}")
    print(f"  last        : {d.get('last_decision')} — {str(d.get('last_reason'))[:120]}")
    for e in (d.get("log") or [])[-5:]:
        print(f"    {e['at'][:16]}  {e['decision']:9s} {e['reason'][:70]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--continue", dest="cont", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--claim", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--reason", default="")
    a = ap.parse_args()
    if a.cont:
        cmd_continue(a)
    elif a.stop:
        cmd_stop(a)
    elif a.claim:
        sys.exit(cmd_claim(a))
    else:
        cmd_show(a)


if __name__ == "__main__":
    main()
