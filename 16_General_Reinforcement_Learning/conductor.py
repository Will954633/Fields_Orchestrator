#!/usr/bin/env python3
"""
conductor.py — M7: the meta-conductor (cross-sphere coordinator; future-Samantha layer).

Independent self-pacing sub-workflows already give autonomous operation. The conductor sits over
the top and OPTIMISES ACROSS them: it reads every domain's signal + pacer state + heartbeat, the
shared reward ledger, and the arm grades, into ONE holistic board (`system_monitor.rl_conductor`)
— the "is everything running + what should we prioritise?" view. It surfaces the top cross-sphere
opportunity + any promote/retire verdicts, and produces a digest for Will. It is ADVISORY: it never
overrides a domain's self-pacing (one-writer-per-lever); it recommends priority, the domains act.

Read-only over the RL collections. Writes ONE collection + optional Telegram digest. job_run "rl_conductor".

Usage: python3 conductor.py [--dry-run] [--telegram]
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_conductor"
DOMAINS = ["geo", "seo", "ads", "articles", "onsite"]
# geo's pacer state lives in rl_geo_cycle_state (written by cycle_state.py); others by cycle_pacer.
PACER_COLL = {d: f"rl_{d}_cycle_state" for d in DOMAINS}


def _top_opportunity(sig):
    """Best one-line opportunity from a domain signal snapshot (best-effort across shapes)."""
    if not sig:
        return None
    for key in ("scale_candidates", "opportunities", "hot_individuals", "engines", "top_pages"):
        v = sig.get(key)
        if isinstance(v, dict):  # opportunities: {striking_distance:[...], ...}
            for k, lst in v.items():
                if lst:
                    return f"{k}: {len(lst)} (e.g. {str(lst[0].get('page') or lst[0].get('milestone') or '')[:40]})"
        elif isinstance(v, list) and v:
            r = v[0]
            return f"{key}: {str(r.get('ad_name') or r.get('page') or r.get('engine') or r.get('intent_reason') or '')[:44]}"
    return None


def build(dry_run=False, telegram=False):
    sm = get_client()["system_monitor"]
    ledger = sm["rl_reward_ledger"].find_one({"_id": "latest"}) or {}
    grades = sm["rl_arm_grades"].find_one({"_id": "latest"}) or {}

    board = []
    for d in DOMAINS:
        sig = sm[f"rl_{d}_signal"].find_one({"_id": "latest"})
        pacer = sm[PACER_COLL[d]].find_one({"_id": "state"}) or {}
        hb_c = sm["job_runs"].find_one({"$or": [{"job": f"{d}_cycle"}, {"name": f"{d}_cycle"}]}, sort=[("_id", -1)])
        hb_s = sm["job_runs"].find_one({"$or": [{"job": f"rl_{d}_signal"}, {"name": f"rl_{d}_signal"}]}, sort=[("_id", -1)])
        board.append({
            "domain": d,
            "signal_at": (sig or {}).get("computed_at"),
            "sensor_status": (hb_s or {}).get("status", "missing"),
            "cycle_status": (hb_c or {}).get("status", "never_run"),
            "next_run_at": pacer.get("next_run_at"),
            "cycles_today": pacer.get("cycles_today"),
            "last_reason": (pacer.get("last_reason") or "")[:120],
            "top_opportunity": _top_opportunity(sig),
        })

    # promote/retire recs from arm grades
    recs = []
    for e in grades.get("experiments", []):
        for v in e.get("variants", []):
            if v.get("verdict") == "leading":
                recs.append(f"PROMOTE {e['flag']}={v['variant']} (lift {v.get('lift_vs_control')}×, {v['conv']} conv)")
            elif v.get("verdict") == "lagging":
                recs.append(f"RETIRE {e['flag']}={v['variant']} (rate {v.get('rate',0)*100:.1f}% vs control)")

    # cross-sphere priority: domains with a live opportunity + a green sensor, ranked (simple heuristic)
    priority = [b["domain"] for b in board if b["top_opportunity"] and b["sensor_status"] == "success"]

    tr = ledger.get("true_reward", {})
    board_doc = {
        "kind": "conductor_board", "_id": "latest", "computed_at": NOW.isoformat(),
        "true_reward": {"total": tr.get("total_true_rewards"), "definition": (tr.get("definition") or "")[:120]},
        "domains": board,
        "arm_recommendations": recs,
        "cross_sphere_priority": priority,
        "health": {"sensors_ok": sum(1 for b in board if b["sensor_status"] == "success"),
                   "cycles_ok": sum(1 for b in board if b["cycle_status"] in ("success",)),
                   "domains": len(board)},
        "note": ("M7 meta-conductor. Advisory holistic board over all self-pacing sub-workflows: health, "
                 "each domain's top opportunity + next run, arm promote/retire recs, cross-sphere priority. "
                 "Never overrides a domain's self-pacing (one writer per lever)."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, board_doc, upsert=True)
        c.insert_one({k: v for k, v in {**board_doc, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})

    if telegram and not dry_run:
        try:
            sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
            from telegram_notify import send_message  # type: ignore
            lines = [f"🎛️ General RL board — {board_doc['health']['sensors_ok']}/{len(board)} sensors ok",
                     f"true reward (window): {board_doc['true_reward']['total']}"]
            for b in board:
                lines.append(f"• {b['domain']}: {b['top_opportunity'] or 'no live opp'}")
            if recs:
                lines.append("arms: " + "; ".join(recs[:3]))
            send_message("\n".join(lines))
        except Exception as e:
            print("telegram digest failed:", e)
    return board_doc


def _summary(b):
    h = b["health"]
    print(f"\n=== RL CONDUCTOR BOARD — {h['sensors_ok']}/{h['domains']} sensors ok · "
          f"true reward (window)={b['true_reward']['total']} ===")
    for d in b["domains"]:
        print(f"  {d['domain']:<9} sensor={d['sensor_status']:<8} cycle={d['cycle_status']:<10} "
              f"next={str(d['next_run_at'])[:16]}  opp: {d['top_opportunity'] or '—'}")
    if b["arm_recommendations"]:
        print("\n  ARM RECS:")
        for r in b["arm_recommendations"]:
            print(f"    {r}")
    print(f"\n  cross-sphere priority: {', '.join(b['cross_sphere_priority']) or '—'}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("rl_conductor", cadence_hours=24, title="General RL — meta-conductor board (M7)") as beat:
            b = build(dry_run=False, telegram=args.telegram)
            _summary(b)
            beat.detail = f"{b['health']['sensors_ok']}/{b['health']['domains']} sensors ok; {len(b['arm_recommendations'])} arm recs"
    else:
        b = build(dry_run=args.dry_run, telegram=args.telegram)
        _summary(b)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()
