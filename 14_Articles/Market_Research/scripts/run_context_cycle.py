#!/usr/bin/env python3
"""
run_context_cycle.py — the Market Context Engine orchestrator.

Chains Stages 0-8 (see ../DEV_MARKET_CONTEXT_ENGINE.md), manages the fortnightly gate, and
self-reports one heartbeat for the whole cycle (Rule 7 + 7b). Evolves run_research_cycle.py:
it keeps the same even-ISO-week cadence and the same market_research_briefs store, and adds the
demand-sensing (Stage 1-2), psychology (Stage 3) and suburb (Stage 5) layers around the existing
per-topic deep research (Stage 4).

    python3 run_context_cycle.py --dry-run     # plumbing only, no LLM/cost
    python3 run_context_cycle.py --test        # end-to-end, bounded: 3 tiers, 1 topic, 1 suburb
    python3 run_context_cycle.py --force       # full cycle now, ignore the fortnight gate
    python3 run_context_cycle.py               # scheduled fortnightly run (0 12 * * 0, on-week)

Stages read/write artifacts under data/<cycle>/, so a failed run can be resumed with
--start-stage N (0..8). Nothing publishes; the deliverable is reviewable briefs + a digest.
"""
from __future__ import annotations

import argparse
import json
import sys

import mce_common as mc


def _stage_data(cycle):
    import mce_stage0_data
    return mce_stage0_data.run(cycle)


def run(*, cycle=None, dry_run=False, test=False, force=False, notify=None,
        start_stage=0, stop_stage=8, n_promoted=None) -> dict:
    now = mc.now_tz()
    cycle = cycle or mc.cycle_id(now)
    # notify defaults: real run notifies, test/dry does not (don't spam Will during tests)
    if notify is None:
        notify = not (test or dry_run)

    if not force and not dry_run and not test and not mc.is_on_week(now):
        print(f"off-week ({cycle}, ISO week {now.isocalendar().week}) — fortnightly cadence, "
              f"skipping", file=sys.stderr)
        return {"skipped_off_week": True, "cycle": cycle, "refreshed": 0}

    topic_limit = 1 if test else None
    suburb_only = [mc.TARGET_SUBURBS[0]] if test else None
    hl_turns = 14 if test else 20
    result = {"cycle": cycle, "test": test, "stages": {}}

    def _do(n): return start_stage <= n <= stop_stage

    # ---- Stage 0: data pull -------------------------------------------------
    if _do(0):
        print("── Stage 0: data pull", file=sys.stderr)
        if dry_run:
            import mce_stage0_data
            pack = mce_stage0_data.build_pack(cycle)      # builds but still writes artifact
            result["stages"]["0"] = {"live_listings": pack["total_live_listings"]}
        else:
            pack = _stage_data(cycle)
            result["stages"]["0"] = {"live_listings": pack["total_live_listings"],
                                     "demand": bool((pack.get("search_intent") or {}).get("available"))}
    if dry_run:
        print("[dry-run] Stage 0 done; Stages 1-8 need the LLM — stopping.", file=sys.stderr)
        return result

    # ---- Stage 1: headline scan --------------------------------------------
    if _do(1):
        print("── Stage 1: headline scan (national → QLD → Gold Coast)", file=sys.stderr)
        import mce_stage1_headlines
        h = mce_stage1_headlines.run(cycle, max_turns=hl_turns)
        result["stages"]["1"] = {"headlines": h["count"], "per_tier": h["per_tier"]}

    # ---- Stage 2: topic rank -----------------------------------------------
    if _do(2):
        print("── Stage 2: topic ranking", file=sys.stderr)
        import mce_stage2_rank
        s = mce_stage2_rank.build_slate(cycle, n_promoted=n_promoted
                                        if n_promoted is not None
                                        else (2 if test else mce_stage2_rank.DEFAULT_N_PROMOTED))
        result["stages"]["2"] = {"candidates": s["n_candidates"], "slate": len(s["slate"]),
                                 "promoted": s["n_promoted"]}

    # ---- Stage 3: psychology -----------------------------------------------
    if _do(3):
        print("── Stage 3: psychology synthesis", file=sys.stderr)
        import mce_stage3_psychology
        p = mce_stage3_psychology.run(cycle)
        result["stages"]["3"] = {"words": p.get("words"), "qa": len(p.get("qa", []))}

    # ---- Stage 4: deep research --------------------------------------------
    if _do(4):
        print(f"── Stage 4: deep research ({'1 topic (test)' if test else 'full slate'})",
              file=sys.stderr)
        import mce_stage4_research
        r4 = mce_stage4_research.run(cycle, limit=topic_limit)
        result["stages"]["4"] = {"refreshed": r4["refreshed"], "topics": r4["n_topics"],
                                 "failures": r4["failures"]}
        result["refreshed"] = r4["refreshed"]

    # ---- Stage 5: suburb context -------------------------------------------
    if _do(5):
        print(f"── Stage 5: suburb context ({'1 suburb (test)' if test else 'core three'})",
              file=sys.stderr)
        import mce_stage5_suburb
        r5 = mce_stage5_suburb.run(cycle, only=suburb_only)
        result["stages"]["5"] = {"done": r5["done"], "failures": r5["failures"]}

    # ---- Stage 6: index -----------------------------------------------------
    if _do(6):
        print("── Stage 6: synthesis & index", file=sys.stderr)
        import mce_stage6_index
        r6 = mce_stage6_index.run(cycle)
        result["stages"]["6"] = r6

    # ---- Stage 8: QA + digest ----------------------------------------------
    if _do(8):
        print("── Stage 8: QA + digest", file=sys.stderr)
        import mce_qa
        r8 = mce_qa.run(cycle, notify=notify)
        result["stages"]["8"] = {"qa_errors": r8["qa"]["n_errors"],
                                 "qa_warns": r8["qa"]["n_warns"],
                                 "digest_sent": r8["digest_sent"]}

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Stage 0 only, no LLM/cost")
    ap.add_argument("--test", action="store_true",
                    help="end-to-end but bounded: 3 tiers, 1 topic, 1 suburb, no Telegram")
    ap.add_argument("--force", action="store_true", help="ignore the fortnight gate")
    ap.add_argument("--cycle", default=None)
    ap.add_argument("--start-stage", type=int, default=0)
    ap.add_argument("--stop-stage", type=int, default=8)
    ap.add_argument("--n-promoted", type=int, default=None)
    ap.add_argument("--notify", dest="notify", action="store_true", default=None)
    ap.add_argument("--no-notify", dest="notify", action="store_false")
    ap.add_argument("--no-heartbeat", action="store_true")
    a = ap.parse_args()

    def _go():
        return run(cycle=a.cycle, dry_run=a.dry_run, test=a.test, force=a.force,
                   notify=a.notify, start_stage=a.start_stage, stop_stage=a.stop_stage,
                   n_promoted=a.n_promoted)

    if a.no_heartbeat or a.dry_run:
        res = _go()
        print(json.dumps(res, indent=2, default=str))
        return 0

    try:
        from job_status import job_run
    except Exception:
        res = _go(); print(json.dumps(res, indent=2, default=str)); return 0

    job = "market_context_cycle_test" if a.test else "market_context_cycle"
    with job_run(job, cadence_hours=336,
                 title="Market Context Engine — fortnightly cycle") as beat:
        res = _go()
        s4 = res.get("stages", {}).get("4", {})
        beat.metrics = {"headlines": res.get("stages", {}).get("1", {}).get("headlines", 0),
                        "topics_refreshed": s4.get("refreshed", 0),
                        "suburbs": res.get("stages", {}).get("5", {}).get("done", 0)}
        # Rule 7b: a live cycle that refreshed nothing is a failure.
        if not res.get("skipped_off_week") and "4" in res.get("stages", {}) \
                and s4.get("refreshed", 0) == 0 and s4.get("topics", 0) > 0:
            raise RuntimeError(f"cycle refreshed 0/{s4.get('topics')} topics — failure "
                               f"(failures={s4.get('failures')})")
        beat.detail = (f"{beat.metrics['topics_refreshed']} topics, "
                       f"{beat.metrics['suburbs']} suburbs, "
                       f"{beat.metrics['headlines']} headlines"
                       if not res.get("skipped_off_week") else "off-week skip")
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
