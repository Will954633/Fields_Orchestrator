#!/usr/bin/env python3
"""
offmarket_sitemap_release.py — the watched-wave GSC governor for off-market coverage.

Increments the per-suburb sitemap release counter by STEP (default 500) each run, so
newly-covered off-market pages enter Google's sitemap as a steady daily trickle, not a
sudden +thousands (protects a young domain's crawl budget; scoping §7 Phase-1). The counter
lives in `Gold_Coast.offmarket_sitemap_release` and is read by `generate-sitemap.mjs`
(release-gated expansion suburbs). The existing 06:15 VM regen (`regenerate-sitemap.sh`)
picks up the new count and pushes the sitemap live — so this job only moves the number.

**GSC-governed:** hold or reduce STEP if GSC shows a "discovered/crawled – not indexed"
backlog building (the authority ceiling); scale up only while indexation keeps pace.

Usage: python3 offmarket_sitemap_release.py [--suburb nerang] [--step 500] [--show] [--set N]
"""
import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db  # noqa: E402

ELIGIBLE = {"url_slug": {"$exists": True, "$ne": None},
            "enriched_data.transactions.0": {"$exists": True},
            "listing_status": {"$nin": ["for_sale", "under_contract"]},
            "is_waterfront": {"$ne": True}}


def run(args):
    db = get_gold_coast_db()
    cfg = db["offmarket_sitemap_release"]
    doc = cfg.find_one({"_id": "release"}) or {"limits": {}}
    limits = doc.get("limits", {})
    current = limits.get(args.suburb, 0)
    eligible = db[args.suburb].count_documents(ELIGIBLE)

    if args.show:
        print(f"{args.suburb}: released {current} / {eligible} eligible "
              f"({round(100*current/eligible) if eligible else 0}%). all limits: {limits}")
        return {"suburb": args.suburb, "released": current, "eligible": eligible}

    # FROZEN suburbs must never widen. A frozen suburb keeps the slice it has already
    # released (those URLs stay in the sitemap and keep their decks) but the deck builder
    # no longer builds it — so widening here would publish URLs with no deck, which is
    # precisely the 2026-07-29 drift that served the OLD classic page on ~985 Nerang URLs.
    # Unfreezing is a deliberate act: drop the name from `frozen` in the config doc.
    if args.suburb in set(doc.get("frozen") or []):
        print(f"{args.suburb} is FROZEN — release held at {current} "
              f"(unfreeze by removing it from `frozen` in the release config doc)")
        return {"suburb": args.suburb, "released": current, "delta": 0,
                "eligible": eligible, "frozen": True}

    target = args.set if args.set is not None else min(current + args.step, eligible)
    target = min(target, eligible)
    limits[args.suburb] = target
    cfg.update_one({"_id": "release"},
                   {"$set": {"limits": limits, "updated_at": datetime.now(timezone.utc).isoformat()}},
                   upsert=True)
    delta = target - current
    print(f"{args.suburb}: {current} -> {target} released (+{delta}); {eligible} eligible "
          f"({round(100*target/eligible) if eligible else 0}%). "
          f"{'ALL RELEASED' if target >= eligible else 'more to go'}")
    print("  → the 06:15 VM sitemap regen will push these live; watch GSC indexed-vs-discovered.")
    return {"suburb": args.suburb, "released": target, "delta": delta, "eligible": eligible}


def main():
    ap = argparse.ArgumentParser(description="Increment off-market sitemap release counter.")
    ap.add_argument("--suburb", default="nerang")
    ap.add_argument("--step", type=int, default=500)
    ap.add_argument("--set", type=int, default=None, help="set the release count explicitly")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        return run(args)
    try:
        from job_status import job_run
        with job_run("offmarket_sitemap_release", cadence_hours=24,
                     title="Off-Market Sitemap Release (500/day, GSC-governed)") as beat:
            res = run(args)
            beat.detail = f"{args.suburb}: {res['released']}/{res['eligible']} released (+{res['delta']})"
            beat.metrics = {"released": res["released"], "eligible": res["eligible"]}
            return res
    except ImportError:
        return run(args)


if __name__ == "__main__":
    main()
