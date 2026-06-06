"""
One-off: regenerate the `positioning.personas` and `buyers` slots in place for
existing property_reports, after the 2026-06-06 Track-A rewrite of
personas_narrative.py + buyers_narrative.py (which removed fabricated reach
channels and the fake "buyer-origin / open-home register" catchment claims).

Surgical: reads the inputs already stored on each doc (scarcity_features, pois,
valuation.model_range) and re-runs ONLY the two resolvers — it does NOT re-run
the full pipeline, so comps / market / scarcity / competitor slots are untouched.

  - personas regenerated wherever slot_status.positioning == "approved"
  - buyers regenerated wherever slot_status.buyers == "approved" (needs personas)

Run:  python3 -m scripts.property_reports.regen_buyers_personas [--dry-run] [--slug X]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone

from pymongo import MongoClient

from scripts.property_reports.personas_narrative import resolve_personas_narrative
from scripts.property_reports.buyers_narrative import resolve_buyers_narrative


def _retry_write(fn, attempts=5):
    """Minimal Cosmos RU-exhaustion retry (code 16500)."""
    delay = 1.0
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if "16500" in str(e) and i < attempts - 1:
                time.sleep(delay)
                delay *= 1.5
                continue
            raise


def regen_one(col, doc, dry_run: bool) -> dict:
    slug = doc["slug"]
    ss = doc.get("slot_status") or {}
    out = {"slug": slug, "personas": "skip", "buyers": "skip"}

    if ss.get("positioning") != "approved":
        return out  # nothing to regenerate

    sf = doc.get("scarcity_features") or {}
    notable = sf.get("notable_features") or []
    if not notable:
        out["personas"] = "skip (no notable_features)"
        return out

    suburb = doc.get("suburb") or (doc.get("suburb_key") or "").replace("_", " ").title()
    address = doc.get("address") or slug
    features_basic = sf.get("features_basic_snapshot") or {}
    matching = sf.get("active_matching_full_stack", 0)
    active_total = sf.get("active_listings_total", 0)
    cohort_premiums = sf.get("cohort_premiums") or []
    pois = doc.get("pois") or []
    val_range = (doc.get("valuation") or {}).get("model_range")

    personas_result = resolve_personas_narrative(
        address=address, suburb=suburb, features_basic=features_basic,
        notable_features=notable, matching_full_stack=matching,
        active_listings_total=active_total, cohort_premiums=cohort_premiums,
        pois=pois, valuation_range=val_range,
    )
    if not (personas_result and personas_result.get("personas")):
        out["personas"] = f"FAIL ({(personas_result or {}).get('error')})"
        return out
    personas = personas_result["personas"]
    out["personas"] = f"ok ({[p['label'] for p in personas]})"

    updates = {
        "positioning.personas": personas,
        "positioning.personas_regenerated_at": datetime.now(timezone.utc).isoformat(),
    }

    # buyers only where it was already approved (and we now have 3 fresh personas)
    if ss.get("buyers") == "approved" and len(personas) >= 3:
        buyers_result = resolve_buyers_narrative(
            address=address, suburb=suburb, features_basic=features_basic,
            notable_features=notable, matching_full_stack=matching,
            active_listings_total=active_total, cohort_premiums=cohort_premiums,
            personas=personas, pois=pois, valuation_range=val_range,
        )
        if buyers_result and buyers_result.get("thesis"):
            updates["buyers"] = {
                "thesis": buyers_result["thesis"],
                "catchment": buyers_result["catchment"],
                "campaignMath": buyers_result["campaignMath"],
                "generated_at": buyers_result["generated_at"],
                "model": buyers_result["model"],
                "attempt": buyers_result["attempt"],
            }
            out["buyers"] = "ok"
        else:
            out["buyers"] = f"FAIL ({(buyers_result or {}).get('error')})"

    if not dry_run:
        _retry_write(lambda: col.update_one({"_id": doc["_id"]}, {"$set": updates}))
        out["written"] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slug", help="limit to a single slug")
    args = ap.parse_args()

    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("COSMOS_CONNECTION_STRING not set", file=sys.stderr)
        sys.exit(1)
    col = MongoClient(conn)["system_monitor"]["property_reports"]

    q = {"slot_status.positioning": "approved"}
    if args.slug:
        q["slug"] = args.slug
    docs = list(col.find(q))
    print(f"{len(docs)} report(s) with positioning approved"
          f"{' (filtered)' if args.slug else ''}; dry_run={args.dry_run}\n")
    for doc in docs:
        res = regen_one(col, doc, args.dry_run)
        print(f"  {res['slug']}: personas={res['personas']} | buyers={res['buyers']}"
              f"{' | WRITTEN' if res.get('written') else ''}")


if __name__ == "__main__":
    main()
