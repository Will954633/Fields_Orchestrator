#!/usr/bin/env python3
"""
mint_offmarket_report.py — give an off-market address a `property_reports` doc so
the nightly competitor/change-log pipeline can run against it.

WHY. `scripts/refresh_property_reports.py::refresh_comparables_for_doc()` is
"config-free, EVERY report" — it re-runs the competitor matcher against tonight's
listings and diffs the result into a durable change log, which is what makes
"what's changed since you last looked" accumulate. But it iterates
`system_monitor.property_reports`, and those docs are only minted on
`/analyse-your-home` submission. 70 exist; there are 26,297 off-market decks.

`SlotResolver` needs only four fields — `suburb_key`, `suburb`, `address`,
`property_id` — so a stub is cheap.

Docs minted here carry `source: "offmarket_v4_mint"` so they are distinguishable
from real homeowner submissions and can be removed with --revert. They are
deliberately NOT given an `owner`, and state stays `offmarket` rather than any
value the seller pipeline acts on.

    python3 mint_offmarket_report.py --slug 28-wedgebill-parade-burleigh-waters --suburb burleigh_waters
    python3 mint_offmarket_report.py --slug ... --refresh     # also run the matcher
    python3 mint_offmarket_report.py --revert
"""
import argparse
import os
import sys
from datetime import datetime, timezone

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from dotenv import load_dotenv
from src.mongo_client_factory import get_mongo_client

MARK = "offmarket_v4_mint"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--suburb")
    ap.add_argument("--refresh", action="store_true",
                    help="run refresh_comparables_for_doc after minting")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    load_dotenv(os.path.join(ORCH, ".env"))
    client = get_mongo_client()
    col = client["system_monitor"]["property_reports"]
    gc = client["Gold_Coast"]

    if args.revert:
        r = col.delete_many({"source": MARK})
        print(f"removed {r.deleted_count} minted stub(s)")
        return 0

    if not (args.slug and args.suburb):
        ap.error("--slug and --suburb required")

    # Resolve the subject from Gold_Coast. Match the full address, never a
    # street-number fragment — that trap cost us a wrong sale history earlier.
    stem = " ".join(args.slug.split("-")[:-1]).replace(" place", " Place")
    subject = gc[args.suburb].find_one(
        {"address": {"$regex": "^" + args.slug.split("-")[0] + r"\s+"
                              + args.slug.split("-")[1], "$options": "i"}})
    if not subject:
        sys.exit(f"subject not found for {args.slug} in {args.suburb}")

    existing = col.find_one({"slug": args.slug})
    if existing:
        print(f"already exists: {args.slug} (source={existing.get('source')})")
    else:
        col.insert_one({
            "slug": args.slug,
            "address": subject.get("address"),
            "suburb": args.suburb.replace("_", " ").title(),
            "suburb_key": args.suburb,
            "property_id": str(subject["_id"]),
            "state": "offmarket",          # not a seller-pipeline state
            "source": MARK,
            "build_mode": "no_llm",        # deterministic slots only — no vision, no Opus
            "created_at": datetime.now(timezone.utc),
            "schema_version": 1,
        })
        print(f"minted stub for {subject.get('address')}")

    if args.refresh:
        from refresh_property_reports import refresh_comparables_for_doc
        doc = col.find_one({"slug": args.slug})
        ok = refresh_comparables_for_doc(col, gc, doc, False)
        print(f"refresh_comparables_for_doc -> {ok}")
        doc = col.find_one({"slug": args.slug})
        comps = doc.get("comparables") or {}
        print(f"  closest_active: {len(comps.get('closest_active') or [])}")
        print(f"  closest_sold  : {len(comps.get('closest_sold') or [])}")
        print(f"  aperture      : r{comps.get('aperture_ring')} {comps.get('aperture_label')}")
        print(f"  events        : {len(doc.get('comparable_events') or [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
