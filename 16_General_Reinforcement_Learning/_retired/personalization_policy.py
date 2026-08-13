#!/usr/bin/env python3
"""
⚠ DEPRECATED 2026-07-29 — this hand-authored static table was the WRONG model (it pre-decided the
content instead of letting Claude hypothesise + test). REPLACED by the Claude-driven experiment loop:
`experiment_manager.py` (registry `rl_onsite_experiments` + PostHog flags) driven by the onsite cycle
(`onsite_prompt.md`), measured by `arm_grader.py`. Kept only for history; cron removed. Do not use.

personalization_policy.py — Phase 2 (P2.0): the onsite personalization DECISION layer.

Reads the reward ledger's milestone weights and emits a tiny lookup table
`system_monitor.rl_personalization_policy` (_id="latest"): per surface, per visitor
milestone-state → the slot variant that nudges toward the highest-value NEXT milestone.

This is the "server DECIDES" half (offline, precomputed — zero per-request compute, zero
render-path cost). The "client APPLIES late" half (P2.1) reads this table AFTER paint and
fills a reserved slot, so it can never affect TTFB/LCP (PHASE2_DESIGN.md).

The variants are the RL arms. v1 seeds them from the ledger (address-search is the 26× lever;
passive property-browse is dead) + the funnel laws (personal open loop + soft CTA). As per-variant
outcomes accrue, the ledger grades which variant lifts the target milestone and this policy updates.

Editorial: data-framed, soft CTA, no advice/predictions, comparable RANGES not single valuations.

Usage: python3 personalization_policy.py [--dry-run]
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_personalization_policy"
TARGET_MILESTONE = "searched_address"   # the 26× lever every nudge points at

# v1 seed variants. `state` = visitor milestone-state the client resolves from distinct_id.
# `default` renders in SSR (unchanged baseline); others swap in post-LCP for that state.
SURFACES = {
    "/analyse-your-home": [
        {"state": "default", "variant": "default", "headline": None, "sub": None,
         "cta_label": None, "cta_href": None, "note": "SSR default — unchanged, no swap"},
        {"state": "returning_searched", "variant": "resume",
         "headline": "Pick up where you left off",
         "sub": "See the comparable-sales range for your address.",
         "cta_label": "See my range", "cta_href": "/analyse-your-home",
         "note": "returned after an earlier address search"},
        {"state": "from_market_metrics", "variant": "bridge_from_data",
         "headline": "You were reading Gold Coast market data",
         "sub": "See how your home compares — a comparable-sales range for your address.",
         "cta_label": "See how my home compares", "cta_href": "/analyse-your-home",
         "note": "entered from a /market-metrics page — the proven converting path"},
        {"state": "viewed_property", "variant": "compare_to_viewed",
         "headline": "Curious how your own home compares?",
         "sub": "Enter your address for a comparable-sales range.",
         "cta_label": "Compare my home", "cta_href": "/analyse-your-home",
         "note": "browsed a listing but hasn't searched their own address"},
    ],
    "/for-sale-v3": [
        {"state": "default", "variant": "default", "headline": None, "sub": None,
         "cta_label": None, "cta_href": None, "note": "SSR default — unchanged, no swap"},
        {"state": "viewed_multiple_properties", "variant": "bridge_to_ayh",
         "headline": "Comparing homes?",
         "sub": "See the comparable-sales range for your own address alongside them.",
         "cta_label": "See what mine's worth", "cta_href": "/analyse-your-home",
         "note": "ledger: more listings don't convert; the address-search bridge does"},
    ],
}


def build(dry_run=False):
    sm = get_client()["system_monitor"]
    ledger = sm["rl_reward_ledger"].find_one({"_id": "latest"}) or {}
    weights = {m["milestone"]: m for m in ledger.get("milestones", [])}
    tgt = weights.get(TARGET_MILESTONE, {})

    policy = {
        "kind": "personalization_policy", "_id": "latest", "computed_at": NOW.isoformat(),
        "target_milestone": TARGET_MILESTONE,
        "target_weight": tgt.get("predictiveness"), "target_lift": tgt.get("lift_vs_base"),
        "reward_ledger_at": ledger.get("computed_at"),
        "surfaces": SURFACES,
        "delivery": {
            "mechanism": "server-decides / client-applies-late (deferred slot, post-LCP)",
            "perf_contract": "SSR renders `default`; variants swap after LCP via requestIdleCallback; "
                             "reserved height (no CLS); kill-switch flag; must not change TTFB/LCP.",
            "kill_switch_flag": "genrl_personalization_v1",
        },
        "note": ("v1 seeded from ledger weights + funnel laws. Variants are RL arms; grade which lifts "
                 f"{TARGET_MILESTONE} as per-variant outcomes accrue, then update this table."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, policy, upsert=True)
        c.insert_one({k: v for k, v in {**policy, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return policy


def _summary(p):
    print(f"\n=== PERSONALIZATION POLICY  (target: {p['target_milestone']} "
          f"@ {p['target_lift']}× lift) ===")
    for surface, variants in p["surfaces"].items():
        print(f"\n{surface}:")
        for v in variants:
            hl = v["headline"] or "(SSR default — no change)"
            print(f"  [{v['state']:<26}] {v['variant']:<18} {hl}")
            if v.get("sub"):
                print(f"  {'':<28} {'':<18} \"{v['sub']}\" → {v['cta_href']}")
    print(f"\ndelivery: {p['delivery']['mechanism']}")
    print(f"perf: {p['delivery']['perf_contract']}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("rl_personalization_policy", cadence_hours=24,
                     title="General RL — onsite personalization policy (Phase 2 decision layer)") as beat:
            p = build(dry_run=False)
            _summary(p)
            beat.detail = f"{sum(len(v) for v in p['surfaces'].values())} variants across {len(p['surfaces'])} surfaces"
    else:
        p = build(dry_run=args.dry_run)
        _summary(p)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()
