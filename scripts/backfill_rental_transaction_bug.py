#!/usr/bin/env python3
"""
One-off backfill: RENTAL-AS-SALE bug fix (2026-07-22).

enrich_cadastral.py's extract_transactions() used to treat any
`is_major_event: true` timeline entry as a sale, but rental listings are ALSO
marked is_major_event=true (only `category` distinguishes 'Sale' from
'Rental'). Any cadastral/off-market property whose most recent major timeline
event was a rental listing therefore had a WEEKLY RENT figure ($695, $430...)
stored as its "last sale" in enriched_data.transactions — corrupting last-sale
price, growth %, and capital_gain for ~21% of already-enriched docs.

This script is a pure, deterministic RE-DERIVATION from already-stored
scraped_data.property_timeline — no scraping, no external calls. It only
touches docs where the currently-stored newest transaction doesn't match a
'Sale'-category raw event (i.e. provably bugged), and only rewrites
enriched_data.transactions + enriched_data.capital_gain.

Usage:
    python3 scripts/backfill_rental_transaction_bug.py --dry-run   # count only
    python3 scripts/backfill_rental_transaction_bug.py             # all suburbs
    python3 scripts/backfill_rental_transaction_bug.py --suburb robina
"""
import argparse
import sys
import time

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

from shared.db import get_client
from scripts.enrich_cadastral import extract_transactions, compute_capital_gain, cosmos_retry


def is_bugged(doc):
    txs = (doc.get("enriched_data") or {}).get("transactions") or []
    if not txs:
        return False
    newest = max(txs, key=lambda t: t.get("date") or "")
    tl = (doc.get("scraped_data") or {}).get("property_timeline") or []
    match = next(
        (ev for ev in tl if ev.get("date") == newest.get("date") and float(ev.get("price") or 0) == float(newest.get("price") or 0)),
        None,
    )
    return bool(match and match.get("category") == "Rental")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", help="single suburb collection (default: all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    client = get_client()
    db = client["Gold_Coast"]
    medians_coll = db["suburb_median_prices"]
    suburbs = [args.suburb] if args.suburb else db.list_collection_names()

    total_scanned = 0
    total_bugged = 0
    total_fixed = 0
    start = time.time()

    for suburb in suburbs:
        coll = db[suburb]
        cursor = cosmos_retry(
            coll.find, {"enriched_data.transactions.0": {"$exists": True}},
            {"enriched_data.transactions": 1, "scraped_data.property_timeline": 1},
        )
        n_this_suburb = 0
        for doc in cursor:
            total_scanned += 1
            if not is_bugged(doc):
                continue
            total_bugged += 1
            fixed_txs = extract_transactions(doc)
            cap_gain = compute_capital_gain(fixed_txs, medians_coll, suburb) if fixed_txs else None

            if args.dry_run:
                old_newest = max(doc["enriched_data"]["transactions"], key=lambda t: t.get("date") or "")
                new_newest = fixed_txs[0] if fixed_txs else None
                print(f"  [{suburb}] {doc['_id']}: was last-sale={old_newest} -> now={new_newest}")
            else:
                # transactions=[] when no genuine sale remains (all real timeline
                # events were rentals) — clears the corrupted field rather than
                # leaving a rental price behind. capital_gain always unset first
                # since it's derived from the (possibly now-empty) transactions.
                op = {"$set": {"enriched_data.transactions": fixed_txs}, "$unset": {"enriched_data.capital_gain": ""}}
                if cap_gain:
                    op["$set"]["enriched_data.capital_gain"] = cap_gain
                    del op["$unset"]
                cosmos_retry(coll.update_one, {"_id": doc["_id"]}, op)
                total_fixed += 1

            n_this_suburb += 1
            if args.limit and total_bugged >= args.limit:
                break
        if n_this_suburb:
            print(f"{suburb}: {n_this_suburb} bugged docs found" + (" (dry-run)" if args.dry_run else " (fixed)"))
        if args.limit and total_bugged >= args.limit:
            break

    elapsed = time.time() - start
    print(f"\nScanned {total_scanned} enriched docs across {len(suburbs)} collections in {elapsed:.0f}s")
    print(f"Bugged (rental stored as last sale): {total_bugged}")
    if not args.dry_run:
        print(f"Fixed (enriched_data.transactions rewritten): {total_fixed}")


if __name__ == "__main__":
    main()
