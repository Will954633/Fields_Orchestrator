#!/usr/bin/env python3
"""
waterfront_flag_offmarket.py — persist `is_waterfront: true` on OFF-MARKET houses.

WHY THIS EXISTS (2026-09-15)
  `waterfront_backfill_and_suppress.py` only touches LISTED/SOLD documents
  (`listing_status ∈ {for_sale, sold, under_contract, withdrawn}`). Off-market
  cadastral docs carry NO `listing_status`, so a canal home like
  42 Dipper Drive detected as waterfront live but was never flagged — and the
  whole off-market waterfront treatment (Domain-estimate fallback valuation,
  waterfront-only "near you"/"new this week"/comps rails, noindex gate) keys off
  the persisted `is_waterfront` boolean the loader reads.

  This sweep closes that gap for the off-market book. Once a home is flagged, the
  existing nightly `batch_value_offmarket.py` (same query: off-market Houses)
  attaches waterfront comparables on its next run — no separate comps job.

WHAT IT DOES NOT DO
  It does not scrape Domain estimates. The fallback range reads
  `scraped_data.valuation` where present and degrades to "no figure" where not;
  it reports coverage so the gap is visible, but scraping is a separate concern.

  python3 scripts/waterfront_flag_offmarket.py               # dry-run
  python3 scripts/waterfront_flag_offmarket.py --commit       # apply
  python3 scripts/waterfront_flag_offmarket.py --commit --limit 500
"""
import argparse
import os
import sys

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from shared.env import load_env
from shared.db import get_client
from shared.waterfront import detect_waterfront

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def run(commit: bool, limit: int | None):
    gc = get_client()["Gold_Coast"]
    scanned = flagged = already = with_estimate = 0
    for s in SUBURBS:
        coll = gc[s]
        # The off-market book: houses with no listing_status (cadastral / never
        # listed). Mirrors batch_value_offmarket.py's own selection so the two
        # stay in agreement about what "off-market" means.
        cur = coll.find(
            {"listing_status": {"$exists": False}, "property_type": "House"},
            {"is_waterfront": 1, "waterfront_premium_eligible": 1,
             "satellite_analysis": 1, "gpt_photo_analysis": 1,
             "description": 1, "raw_description": 1,
             "scraped_data": 1, "domain_valuation_at_listing": 1,
             "address": 1, "url_slug": 1},
        )
        for d in cur:
            scanned += 1
            try:
                res = detect_waterfront(d)
            except Exception:
                continue
            if not res.get("is_waterfront"):
                continue
            # A waterfront home. Track Domain-estimate coverage for the fallback.
            est = (d.get("scraped_data") or {}).get("valuation") or d.get("domain_valuation_at_listing")
            if est and (est.get("low") is not None or est.get("high") is not None or est.get("mid") is not None):
                with_estimate += 1
            if d.get("is_waterfront"):
                already += 1
                continue
            flagged += 1
            if commit:
                coll.update_one({"_id": d["_id"]}, {"$set": {
                    "is_waterfront": True,
                    "waterfront_meta": {
                        "reason": res.get("reason"),
                        "signals": res.get("signals"),
                        "borderline": res.get("borderline"),
                        "source": "waterfront_flag_offmarket",
                    },
                }})
            if limit and flagged >= limit:
                break
        if limit and flagged >= limit:
            break

    return {
        "scanned": scanned,
        "newly_flagged": flagged,
        "already_flagged": already,
        "waterfront_total": flagged + already,
        "waterfront_with_domain_estimate": with_estimate,
        "committed": commit,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="Apply writes (default: dry-run)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    load_env()
    res = run(args.commit, args.limit)
    print(f"  scanned off-market houses     : {res['scanned']:,}")
    print(f"  newly flagged is_waterfront   : {res['newly_flagged']:,}"
          + ("" if args.commit else "  (dry-run — not written)"))
    print(f"  already flagged               : {res['already_flagged']:,}")
    print(f"  waterfront total              : {res['waterfront_total']:,}")
    print(f"  ...with a Domain estimate     : {res['waterfront_with_domain_estimate']:,}"
          f"  ({res['waterfront_with_domain_estimate']}/{res['waterfront_total']} have a fallback figure)")
    return res


if __name__ == "__main__":
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    # Rule 7 — ongoing sweep, self-reports. Weekly cadence: new off-market homes
    # arrive slowly and detection is deterministic, so re-flagging is cheap and
    # rare. Only self-registers/heartbeats on a committed run (dry-runs are dev).
    if job_run and "--commit" in sys.argv:
        with job_run("waterfront_flag_offmarket", cadence_hours=168,
                     title="Waterfront flagger — off-market book") as beat:
            res = main()
            beat.metrics = res
            # Rule 7b — the zero-output path. Scanning zero off-market houses means
            # the query broke (the book is never empty), not that there is no work.
            if res["scanned"] == 0:
                raise RuntimeError(
                    "scanned 0 off-market houses — the selection query is broken, "
                    "not the book empty")
            beat.detail = (f"{res['newly_flagged']} newly flagged, "
                           f"{res['waterfront_total']} waterfront total, "
                           f"{res['waterfront_with_domain_estimate']} with Domain estimate")
        sys.exit(0)
    main()
    sys.exit(0)
