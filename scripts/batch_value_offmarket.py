#!/usr/bin/env python3
"""
batch_value_offmarket.py — compute adjusted-comparables valuations across the
off-market book.

WHY THIS IS A BATCH, NOT ON-DEMAND (established 2026-08-06)
  The valuation engine makes NO AI call. `precompute_valuations.py` imports only
  os/sys/time/math/datetime/dotenv/pymongo/statistics/re/numpy — no model client,
  no HTTP. Vision runs SEPARATELY (pipeline steps 105/106/108/117) and writes
  `property_valuation_data`; the valuation merely reads it, and 84% of off-market
  houses already have it.

  So the cost profile is the opposite of what on-demand assumes: the expensive
  part is the SHARED caches (sold catchment, coordinates, timelines, medians,
  street premiums) at ~25-130s, built ONCE. Per property is ~100ms. The on-demand
  path rebuilds those caches for every single request.

WHAT IT UNBLOCKS
  A valuation is the gate on the adjusted comparables (§2), the obvious-comparable
  card, and the scarcity anchors. `fact_bundle._obvious_comp` reads
  `valuation_data.recent_sales`, which is why that card rendered on 22 of 400
  live decks.

    python3 scripts/batch_value_offmarket.py --dry-run
    python3 scripts/batch_value_offmarket.py --limit 200
    python3 scripts/batch_value_offmarket.py                 # the whole book
    python3 scripts/batch_value_offmarket.py --force         # recompute everything

Skips homes valued within --max-age-days (default 30) unless --force.
"""
import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv
from src.mongo_client_factory import get_mongo_client

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-age-days", type=int, default=30)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv(os.path.join(ORCH, ".env"))
    import precompute_valuations as pv
    client = get_mongo_client()
    gc = client["Gold_Coast"]
    subs = [args.suburb] if args.suburb else SUBURBS
    cutoff = datetime.utcnow() - timedelta(days=args.max_age_days)

    todo = []
    for s in subs:
        for d in gc[s].find({"listing_status": {"$exists": False}, "property_type": "House"},
                            {"address": 1, "valuation_data.computed_at": 1,
                             "valuation_data.adjusted_comparables": 1}):
            vd = d.get("valuation_data") or {}
            ca = vd.get("computed_at")
            fresh = bool(ca and hasattr(ca, "year") and ca > cutoff
                         and vd.get("adjusted_comparables"))
            if args.force or not fresh:
                todo.append((s, d["_id"], d.get("address")))
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo):,} homes to value across {', '.join(subs)}")
    if args.dry_run:
        return {"queued": len(todo), "written": 0, "errors": 0, "dry_run": True}

    t0 = time.time()
    print("Building shared caches (once) …")
    sold = pv._load_sold_comparables(client)
    keys = list(sold.keys())
    coords = pv._preload_gc_coordinates(client, keys)
    timelines = pv._preload_gc_timelines(client, keys)
    mc = pv._build_suburb_median_cache(sold)
    sc = pv._build_street_premium_cache(sold, mc)
    print(f"  caches ready in {time.time()-t0:.0f}s\n")

    out = Counter()
    t1 = time.time()
    for i, (suburb, _id, address) in enumerate(todo, 1):
        try:
            doc = gc[suburb].find_one({"_id": _id})
            # ⚠ The engine resolves its comparable pool from `_collection` or
            # `suburb` — and `suburb` is NULL on every off-market doc. Without
            # this the pool is empty and every valuation returns insufficient_data.
            doc["_collection"] = suburb
            vd = pv.precompute_property_valuation(
                gc, doc, gc[suburb], sold, coords, timelines, mc, sc)
            if not vd:
                out["no_result"] += 1
            else:
                gc[suburb].update_one({"_id": _id}, {"$set": {"valuation_data": vd}})
                conf = (vd.get("confidence") or {}).get("confidence")
                out["written"] += 1
                out[f"  conf:{conf}"] += 1
                if vd.get("adjusted_comparables"):
                    out["with_comparables"] += 1
        except Exception as e:
            out["error"] += 1
            if out["error"] <= 3:
                print(f"  ! {str(address)[:40]}: {type(e).__name__}: {e}")
        if i % 250 == 0:
            rate = i / (time.time() - t1)
            print(f"  {i:,}/{len(todo):,}  ({rate:.0f}/s, "
                  f"{(len(todo)-i)/rate/60:.0f} min left)")

    el = time.time() - t1
    print(f"\ndone in {el/60:.1f} min ({len(todo)/el:.0f}/s)")
    for k, v in out.most_common():
        print(f"  {k:<20} {v:,}")
    return {"queued": len(todo), "written": out["written"],
            "with_comparables": out["with_comparables"],
            "no_result": out["no_result"], "errors": out["error"],
            "minutes": round(el / 60, 1)}


if __name__ == "__main__":
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and "--dry-run" not in sys.argv:
        # Rule 7 — this is intended to run on an interval, so it self-reports.
        # Scheduled nightly 02:10 AEST (crontab). Was unscheduled until
        # 2026-08-14: it carried a heartbeat and a declared cadence but nothing
        # ever fired it, so the off-market book was only revalued when a human
        # remembered. See logs/fix-history/2026-08-14.md.
        with job_run("batch_value_offmarket", cadence_hours=24,
                     title="Batch valuation — off-market book") as beat:
            res = main()
            beat.metrics = res
            # Rule 7b — a clean exit is not an outcome. Nightly the queue is
            # usually small (only homes stale past --max-age-days) and an empty
            # queue is a legitimate success. A queue with work in it that wrote
            # NOTHING is the upstream breaking, and must not report success.
            if res["queued"] and not res["written"]:
                raise RuntimeError(
                    f"{res['queued']} homes queued, 0 valuations written "
                    f"({res['errors']} errors, {res['no_result']} no_result) — "
                    "the engine or its caches are broken, not the queue empty")
            beat.detail = (f"{res['written']:,} of {res['queued']:,} valued, "
                           f"{res['errors']} errors")
        sys.exit(0)
    main()
    sys.exit(0)
