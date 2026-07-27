#!/usr/bin/env python3
"""
Reconcile `sold` records against their own Domain property_timeline.

Motivation (2026-07-26): 64 Parnell Boulevard, Robina was stored as
`listing_status: sold`, `sold_date: 2025-01-10` — but that date is a $880/wk
RENTAL event in the property's own scraped_data.property_timeline. The real sale
was 2024-11-25 ($870,000 private treaty, is_sold=true). The sold-ingestion
pipeline (steps 103/104/111) trusts a listing-level "Sold" signal and never
cross-checks the authoritative timeline it already stores, and `sold` is a
terminal state that is never re-verified. This script is the safety net.

For every `listing_status: sold` doc that carries a scraped_data.property_timeline
it classifies the record:

  LEASE_STAMPED  our sold_date lands on a Rental event and matches NO sale event,
                 while a real sale event exists in the timeline.
                 -> unambiguous defect. Auto-correctable with --apply.
  NO_SALE_EVENT  timeline is present but has no Sale/is_sold event and our
                 sold_date is not in the timeline at all. Usually a STALE timeline
                 (sale happened after the timeline was scraped) or a genuine sale
                 with a thin history — NOT auto-corrected, report only.
  DATE_DRIFT     a sale event exists but our sold_date differs from every sale
                 event date by more than --drift-days. Report only.
  OK             sold_date matches a sale event (or no/empty timeline to check).

Default is a dry run (report only). Only LEASE_STAMPED records are ever written,
and only with --apply. Corrections are audited on the document
(sold_date_original, sold_date_corrected_at, sold_date_correction_note).

Usage:
    python3 scripts/reconcile_sold_against_timeline.py                 # dry run, target suburbs
    python3 scripts/reconcile_sold_against_timeline.py --all           # dry run, every suburb collection
    python3 scripts/reconcile_sold_against_timeline.py --suburb robina
    python3 scripts/reconcile_sold_against_timeline.py --apply         # fix LEASE_STAMPED records
    python3 scripts/reconcile_sold_against_timeline.py --json out.json # machine-readable report
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.db import get_gold_coast_db, cosmos_retry  # noqa: E402

# Default target-market collections (mirrors config/settings.yaml target_market).
TARGET_COLLECTIONS = [
    "robina", "varsity_lakes", "burleigh_waters",
    "mudgeeraba", "reedy_creek", "worongary", "merrimac",
]

# Collections that are never suburb property collections.
NON_SUBURB = {"address_search_index", "system_monitor", "counters", "meta"}

PROJECTION = {
    "address": 1, "sold_date": 1, "sale_date": 1, "sale_price": 1,
    "sale_method": 1, "listing_url": 1, "domain_says_text": 1,
    "previous_sale_year": 1, "scraped_data.property_timeline": 1,
}


def _d10(v) -> str:
    """Normalise a date-ish value to YYYY-MM-DD (empty string if unusable)."""
    if not v:
        return ""
    return str(v)[:10]


def _timeline(doc):
    return (doc.get("scraped_data") or {}).get("property_timeline") or []


def _sale_events(tl):
    out = []
    for e in tl:
        cat = (e.get("category") or "").lower()
        if cat == "sale" or e.get("is_sold") is True:
            if e.get("date"):
                out.append(e)
    return out


def _rental_dates(tl):
    return {_d10(e.get("date")) for e in tl
            if (e.get("category") or "").lower() == "rental" and e.get("date")}


def classify(doc, drift_days: int):
    """Return (verdict, detail_dict). Only LEASE_STAMPED is auto-correctable."""
    tl = _timeline(doc)
    if not tl:
        return "OK", {"reason": "no_timeline"}

    sold = _d10(doc.get("sold_date"))
    sales = _sale_events(tl)
    sale_dates = {_d10(e.get("date")) for e in sales}
    rental_dates = _rental_dates(tl)

    # Latest real sale event (by date), used as the corrected value.
    latest_sale = max(sales, key=lambda e: _d10(e.get("date"))) if sales else None

    if sold and sold in rental_dates and sold not in sale_dates and latest_sale:
        return "LEASE_STAMPED", {
            "our_sold_date": sold,
            "our_sale_price": doc.get("sale_price"),
            "true_sale_date": _d10(latest_sale.get("date")),
            "true_sale_price": latest_sale.get("price"),
            "true_sale_method": latest_sale.get("type"),
        }

    if not sales:
        if sold and sold not in {_d10(e.get("date")) for e in tl}:
            return "NO_SALE_EVENT", {
                "our_sold_date": sold,
                "domain_says": doc.get("domain_says_text"),
                "previous_sale_year": doc.get("previous_sale_year"),
                "hint": "likely stale timeline (sale after last scrape) — verify manually",
            }
        return "OK", {"reason": "no_sale_event_but_sold_date_in_timeline"}

    if sold and sold not in sale_dates and latest_sale:
        # Only the "timeline knows a MORE RECENT sale than we recorded" direction is
        # actionable — it means we may be displaying a stale/older sale. The opposite
        # direction (our sold_date newer than the timeline's latest sale) is normal
        # lag: the sold-listings scrape detects a fresh sale before the property-profile
        # history is re-scraped, so it is expected and treated as OK.
        latest_sale_date = _d10(latest_sale.get("date"))
        if re.match(r"\d{4}-\d{2}-\d{2}", latest_sale_date) and latest_sale_date > sold:
            try:
                gap = (datetime.strptime(latest_sale_date, "%Y-%m-%d")
                       - datetime.strptime(sold, "%Y-%m-%d")).days
                if gap > drift_days:
                    return "DATE_DRIFT", {
                        "our_sold_date": sold,
                        "nearest_sale_date": latest_sale_date,
                        "min_gap_days": gap,
                        "hint": "timeline has a more recent sale than our sold_date — possibly stale",
                    }
            except ValueError:
                pass

    return "OK", {"reason": "sold_date_matches_sale_event"}


def apply_correction(coll, doc, detail) -> bool:
    """Write a LEASE_STAMPED correction. Returns True if modified."""
    true_date = detail["true_sale_date"]
    method = (detail.get("true_sale_method") or "").strip().lower() or None
    note = (
        f"sold_date was {detail['our_sold_date']} which is a RENTAL event in "
        f"scraped_data.property_timeline. Real sale per timeline is_sold=true: "
        f"{true_date}"
        + (f" (${detail['true_sale_price']:,})" if isinstance(detail.get("true_sale_price"), (int, float)) else "")
        + f". Corrected {datetime.now(timezone.utc).date()} by reconcile_sold_against_timeline."
    )
    update = {
        "sold_date": true_date,
        "sale_date": true_date,
        "sold_date_original": detail["our_sold_date"],
        "sold_date_corrected_at": datetime.now(timezone.utc).isoformat(),
        "sold_date_correction_note": note,
    }
    if method:
        update["sale_method"] = method
    res = cosmos_retry(
        lambda: coll.update_one({"_id": doc["_id"]}, {"$set": update}),
        f"reconcile_sold:{doc['_id']}",
    )
    return res.modified_count == 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburb", help="Single collection name (e.g. robina)")
    ap.add_argument("--all", action="store_true", help="Scan every suburb collection, not just target market")
    ap.add_argument("--apply", action="store_true", help="Write corrections for LEASE_STAMPED records (default: dry run)")
    ap.add_argument("--drift-days", type=int, default=45, help="DATE_DRIFT threshold in days (default 45)")
    ap.add_argument("--json", help="Write full machine-readable report to this path")
    args = ap.parse_args()

    db = get_gold_coast_db()

    if args.suburb:
        collections = [args.suburb]
    elif args.all:
        collections = [c for c in db.list_collection_names()
                       if c not in NON_SUBURB and not c.startswith("_")]
    else:
        collections = [c for c in TARGET_COLLECTIONS if c in db.list_collection_names()]

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"reconcile_sold_against_timeline — {mode} — {len(collections)} collection(s)\n")

    buckets = {"LEASE_STAMPED": [], "NO_SALE_EVENT": [], "DATE_DRIFT": []}
    scanned = 0
    corrected = 0

    for cn in collections:
        coll = db[cn]
        cursor = cosmos_retry(
            lambda: list(coll.find({"listing_status": "sold",
                                    "scraped_data.property_timeline": {"$exists": True}},
                                   PROJECTION)),
            f"scan_sold:{cn}",
        )
        for doc in cursor:
            scanned += 1
            verdict, detail = classify(doc, args.drift_days)
            if verdict == "OK":
                continue
            row = {"collection": cn, "address": doc.get("address"),
                   "id": str(doc.get("_id")), "verdict": verdict, **detail}
            buckets[verdict].append(row)
            if verdict == "LEASE_STAMPED" and args.apply:
                if apply_correction(coll, doc, detail):
                    corrected += 1
                    row["applied"] = True

    print(f"Scanned {scanned} sold docs with a timeline.\n")
    for verdict in ("LEASE_STAMPED", "NO_SALE_EVENT", "DATE_DRIFT"):
        rows = buckets[verdict]
        print(f"### {verdict}: {len(rows)}")
        for r in rows[:40]:
            extra = ""
            if verdict == "LEASE_STAMPED":
                extra = (f"  sold_date {r['our_sold_date']} (rental) -> true sale "
                         f"{r['true_sale_date']} ${r.get('true_sale_price')}"
                         + ("  [APPLIED]" if r.get("applied") else ""))
            elif verdict == "NO_SALE_EVENT":
                extra = f"  sold_date {r['our_sold_date']} | domain_says: {str(r.get('domain_says'))[:70]}"
            elif verdict == "DATE_DRIFT":
                extra = f"  sold_date {r['our_sold_date']} vs sale {r.get('nearest_sale_date')} (gap {r.get('min_gap_days')}d)"
            print(f"   - {r['collection']} | {r['address']}{extra}")
        if len(rows) > 40:
            print(f"   ... and {len(rows) - 40} more")
        print()

    if args.apply:
        print(f"Applied {corrected} LEASE_STAMPED correction(s).")
    else:
        n = len(buckets["LEASE_STAMPED"])
        if n:
            print(f"Dry run. Re-run with --apply to correct {n} LEASE_STAMPED record(s). "
                  "NO_SALE_EVENT / DATE_DRIFT are report-only (verify manually).")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"mode": mode, "scanned": scanned, "corrected": corrected,
                       "buckets": buckets}, f, indent=2, default=str)
        print(f"\nWrote report to {args.json}")


if __name__ == "__main__":
    main()
