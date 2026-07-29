#!/usr/bin/env python3
"""
arm_grader.py — M4: the learning/grading loop (closes the RL heart).

Turns reinforcement-*informed* into reinforcement-*learning*: for every live experiment ARM
(a PostHog feature-flag variant), measure its real effect on the true reward vs control, grade it,
and write the verdict to `system_monitor.rl_arm_grades` for the domain cycles + personalization
policy to consume (promote winners, retire losers). Honest min-N gate: at our volume most verdicts
are "inconclusive — need more N", which is the correct call, not a fake winner (the Goodhart guard).

Reads PostHog HogQL (person-on-events: each event carries the active flag variant as
`$feature/<flag>`). Read-only. Writes ONE collection. job_run "rl_arm_grades".

Usage: python3 arm_grader.py [--dry-run] [--days 60]
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "brain2")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_arm_grades"

# The live experiment flags (arms) to grade. Extend as new flag experiments ship.
FLAGS = ["for_sale_page_v1", "discover_mode_v1", "offmarket_gate_v1", "genrl_personalization_v1"]
# Events that count as the true reward (identified-seller candidate).
REWARD_EVENTS = ["analyse_home_address_submit", "analyse_home_submit_success",
                 "offmarket_qualify", "forsale_ladder_complete"]
MIN_USERS_PER_ARM = 50     # below this a variant can't be called
MIN_TOTAL_CONV = 5         # below this the whole experiment is inconclusive


def _grade(variants):
    """variants: [{variant, users, conv}]. Returns verdict per arm vs the control/lowest variant."""
    tot_conv = sum(v["conv"] for v in variants)
    total_users = sum(v["users"] for v in variants)
    if tot_conv < MIN_TOTAL_CONV or total_users < 2 * MIN_USERS_PER_ARM:
        for v in variants:
            v["rate"] = round(v["conv"] / v["users"], 4) if v["users"] else 0
            v["verdict"] = "inconclusive_need_more_N"
        return variants, f"inconclusive (N={total_users} users, {tot_conv} conv — need ≥{MIN_TOTAL_CONV} conv & ≥{2*MIN_USERS_PER_ARM} users)"
    # pick control = the variant named control/false/off, else the lowest-rate one
    for v in variants:
        v["rate"] = v["conv"] / v["users"] if v["users"] else 0
    ctrl = next((v for v in variants if str(v["variant"]).lower() in ("control", "false", "off", "0")), None) \
        or min(variants, key=lambda v: v["rate"])
    base = ctrl["rate"] or 1e-9
    for v in variants:
        v["lift_vs_control"] = round(v["rate"] / base, 2) if base else None
        v["rate"] = round(v["rate"], 4)
        if v is ctrl:
            v["verdict"] = "control"
        elif v["users"] < MIN_USERS_PER_ARM:
            v["verdict"] = "inconclusive_need_more_N"
        elif v["rate"] > ctrl["rate"] and v["conv"] >= 2:
            v["verdict"] = "leading"        # promote candidate
        elif v["rate"] < ctrl["rate"] and v["users"] >= MIN_USERS_PER_ARM:
            v["verdict"] = "lagging"        # kill candidate
        else:
            v["verdict"] = "inconclusive_need_more_N"
    return variants, "graded"


def build(days=60, dry_run=False):
    from brain2_util import hog_retry
    pid = os.environ["POSTHOG_PROJECT_ID"]
    key = os.environ["POSTHOG_PERSONAL_API_KEY"]
    reward_in = ", ".join(f"'{e}'" for e in REWARD_EVENTS)

    experiments = []
    for flag in FLAGS:
        sql = f"""
        SELECT properties['$feature/{flag}'] AS variant,
               count(DISTINCT person_id) AS users,
               count(DISTINCT if(event IN ({reward_in}), person_id, NULL)) AS conv
        FROM events
        WHERE timestamp > now() - INTERVAL {int(days)} DAY
          AND notEmpty(properties['$feature/{flag}'])
        GROUP BY variant
        """
        try:
            rows = hog_retry(pid, key, sql)
        except Exception as e:
            experiments.append({"flag": flag, "error": str(e)[:120], "variants": []})
            continue
        variants = [{"variant": r[0], "users": int(r[1]), "conv": int(r[2])} for r in rows if r[0]]
        if not variants:
            experiments.append({"flag": flag, "status": "no_exposures", "variants": []})
            continue
        graded, status = _grade(variants)
        experiments.append({"flag": flag, "status": status,
                            "variants": sorted(graded, key=lambda v: -v.get("rate", 0))})

    snapshot = {
        "kind": "arm_grades", "_id": "latest", "computed_at": NOW.isoformat(), "window_days": days,
        "reward_events": REWARD_EVENTS, "min_users_per_arm": MIN_USERS_PER_ARM,
        "experiments": experiments,
        "note": ("M4 learning loop. Grades PostHog flag-variant arms by true-reward lift vs control, "
                 "min-N gated (inconclusive is a valid, honest verdict — the Goodhart guard). Domain "
                 "cycles + personalization_policy read this to promote/retire arms. Extends to content/"
                 "ad arms via each domain's rl_<domain>_actions change-epochs as those accrue outcomes."),
    }
    if not dry_run:
        c = get_client()["system_monitor"][COLL]
        c.replace_one({"_id": "latest"}, snapshot, upsert=True)
        c.insert_one({k: v for k, v in {**snapshot, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return snapshot


def _summary(s):
    print(f"\n=== ARM GRADES ({s['window_days']}d, reward={'/'.join(s['reward_events'][:2])}…) ===")
    for e in s["experiments"]:
        if e.get("error"):
            print(f"\n{e['flag']}: ERROR {e['error']}"); continue
        print(f"\n{e['flag']}: {e.get('status')}")
        for v in e["variants"]:
            lift = f" lift={v.get('lift_vs_control')}×" if v.get("lift_vs_control") is not None else ""
            print(f"  {str(v['variant'])[:20]:<20} users={v['users']:>4} conv={v['conv']:>3} "
                  f"rate={v.get('rate',0)*100:>4.1f}%{lift}  → {v['verdict']}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=60)
    args = ap.parse_args()
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("rl_arm_grades", cadence_hours=24, title="General RL — arm grading loop (M4)") as beat:
            s = build(days=args.days, dry_run=False)
            _summary(s)
            graded = sum(1 for e in s["experiments"] if e.get("status") == "graded")
            beat.detail = f"{len(s['experiments'])} experiments, {graded} gradable"
    else:
        s = build(days=args.days, dry_run=args.dry_run)
        _summary(s)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()
