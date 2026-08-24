#!/usr/bin/env python3
"""Set (or clear) a persistent manual listing-price override on a property.

Why this exists
---------------
The frontend can read the asking price from THREE surfaces, and different arms /
components read different ones:

  1. ``price``           — the display string (e.g. "$1,915,000"). Control arm + hero fallback.
  2. ``price_numeric``   — top-level numeric. V2 cost/bridge/trade-off components.
  3. ``price_history``   — the latest *numeric* entry is what PropertyHeroV2 shows.

A manual DB edit that touches only ONE of these leaves the others stale, which is
exactly how 93 Burleigh St showed $1,915,000 on the control arm but the old
$1,990,000 on the V2 arm (see logs/fix-history/2026-08-24.md
[MANUAL-PRICE-OVERRIDE-V2-HERO]). This script writes all three at once, plus the
``manual_price_override`` guard that stops the nightly scrape reverting ``price``.

Usage
-----
  python3 scripts/set_manual_price_override.py \
      --suburb burleigh_waters --address "93 Burleigh Street" --price "$1,915,000"

  # target by _id instead of address:
  python3 scripts/set_manual_price_override.py \
      --suburb burleigh_waters --id 690bd81b8b8f546592617fbb --price "$1,915,000"

  # remove the override (lets Domain's price flow again on the next scrape):
  python3 scripts/set_manual_price_override.py --suburb burleigh_waters \
      --address "93 Burleigh Street" --clear

  # preview without writing:
  ... --dry-run
"""
import argparse
import re
import sys
from datetime import datetime

sys.path.insert(0, '/home/fields/Fields_Orchestrator')

from shared.env import load_env
from shared.db import get_gold_coast_db

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None


def parse_price_numeric(price_text):
    """Extract a single dollar figure from a price string. Returns int or None.

    Deliberately conservative: only fires on a clean single figure. Ranges and
    non-numeric strings ("Offers Over", "Contact Agent") return None so a
    manually-set numeric is never guessed from an ambiguous string.
    """
    if not price_text or not isinstance(price_text, str):
        return None
    # Grab all $-amounts / bare numbers with thousands separators.
    nums = re.findall(r"\$?\s*([\d]{1,3}(?:,\d{3})+|\d{6,7})(?:\.\d+)?", price_text)
    vals = []
    for n in nums:
        try:
            vals.append(int(n.replace(",", "")))
        except ValueError:
            pass
    vals = [v for v in vals if 50_000 <= v <= 50_000_000]
    if len(vals) != 1:
        # 0 => nothing numeric; >1 => a range, ambiguous. Caller may still set the
        # string; we just won't invent a numeric.
        return None
    return vals[0]


def resolve_doc(col, args):
    if args.id:
        if ObjectId is None:
            sys.exit("bson not available to parse --id")
        doc = col.find_one({"_id": ObjectId(args.id)})
        if not doc:
            doc = col.find_one({"_id": args.id})  # some collections store string _ids
        return doc
    q = {"address": {"$regex": re.escape(args.address), "$options": "i"},
         "listing_status": "for_sale"}
    matches = list(col.find(q).limit(5))
    if len(matches) > 1:
        print("Multiple for_sale matches — narrow the address or use --id:")
        for m in matches:
            print(f"  {m['_id']}  {m.get('address')}")
        sys.exit(1)
    return matches[0] if matches else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburb", required=True, help="collection name, e.g. burleigh_waters")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--address", help="address substring (must match one for_sale doc)")
    g.add_argument("--id", help="document _id")
    ap.add_argument("--price", help='display string, e.g. "$1,915,000" (required unless --clear)')
    ap.add_argument("--price-numeric", type=int,
                    help="override the parsed numeric (use when --price is a range/non-numeric)")
    ap.add_argument("--by", default="manual", help="who/why, stored in manual_price_override_by")
    ap.add_argument("--clear", action="store_true",
                    help="remove the override so Domain's scraped price flows again")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    db = get_gold_coast_db()
    col = db[args.suburb]
    doc = resolve_doc(col, args)
    if not doc:
        sys.exit(f"No property found in {args.suburb} for that address/id.")

    _id = doc["_id"]
    print(f"Target: {_id}  {doc.get('address')}")
    print(f"  before: price={doc.get('price')!r}  price_numeric={doc.get('price_numeric')!r}"
          f"  override={doc.get('manual_price_override')!r}")

    now = datetime.now().isoformat()

    if args.clear:
        ops = {"$unset": {"manual_price_override": "", "manual_price_override_at": "",
                          "manual_price_override_by": ""}}
        print("  action: CLEAR override (price/price_numeric left as-is; next scrape may change them)")
        if not args.dry_run:
            col.update_one({"_id": _id}, ops)
        print("  done." if not args.dry_run else "  (dry-run, no write)")
        return

    if not args.price:
        sys.exit("--price is required unless --clear")

    text = args.price.strip()
    numeric = args.price_numeric if args.price_numeric is not None else parse_price_numeric(text)
    if numeric is None:
        print("  WARNING: could not parse a single numeric from the price string; "
              "price_numeric will be left unset (pass --price-numeric to force). "
              "The V2 hero will fall back to the latest numeric price_history entry.")

    set_fields = {
        "price": text,
        "manual_price_override": True,
        "manual_price_override_at": now,
        "manual_price_override_by": f"{args.by} ({doc.get('address','?')})",
    }
    if numeric is not None:
        set_fields["price_numeric"] = numeric

    ops = {"$set": set_fields}

    # Append a price_history entry so summarisePriceHistory().latestPrice tracks the
    # override and the price timeline shows the real current figure. Skip if the
    # latest entry already matches (keeps track_price_changes.py from duplicating).
    hist = doc.get("price_history", [])
    latest_text = (hist[-1].get("price_text") or "").strip() if hist else ""
    if latest_text != text:
        entry = {
            "price_text": text,
            "price_numeric": numeric,
            "recorded_at": now,
            "run_id": f"manual_override_{now[:10]}",
            "event": "manual_override",
        }
        ops["$push"] = {"price_history": entry}
        print(f"  action: SET price={text!r} price_numeric={numeric!r}; append history entry")
    else:
        print(f"  action: SET price={text!r} price_numeric={numeric!r}; history already current")

    if args.dry_run:
        print("  (dry-run, no write)")
        return

    col.update_one({"_id": _id}, ops)
    after = col.find_one({"_id": _id})
    print(f"  after:  price={after.get('price')!r}  price_numeric={after.get('price_numeric')!r}"
          f"  override={after.get('manual_price_override')!r}")
    print(f"  last history: {after.get('price_history', [])[-1]}")


if __name__ == "__main__":
    main()
