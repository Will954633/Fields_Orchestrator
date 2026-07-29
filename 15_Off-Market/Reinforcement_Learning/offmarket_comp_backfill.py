#!/usr/bin/env python3
"""
offmarket_comp_backfill.py — populate recent sold COMPS for a suburb from PropRadar,
so off-market pages in newly-covered suburbs render rich (wealth-reveal / capital-gain)
instead of hero-only. Companion to offmarket_coverage_scraper.py (Off-Market RL, cycle 2).

The problem it fixes (cycle-1 finding): `getNearbySoldComps` (website loader) selects comps
by `listing_status:"sold"` + a lat/lon box + `sale_price`. A freshly-covered suburb has ~no
`sold`-status docs, so the value cards gate off. PropRadar's suburb sold-feed has genuinely
RECENT house sales (the right comp signal) — but no coordinates. So we match each PropRadar
sale to our existing cadastral doc (which HAS coords) and stamp the sale onto it:
  listing_status:"sold" + sale_price + sold_date + beds/baths + comp_source:"propradar".

Cost: ~2 calls/suburb (cursor-paginated), serves EVERY page in the suburb, cache ~fortnightly.
Editorial: these are real transaction FACTS; the deck computes OUR comparable range from them
(no third-party AVM shown). Recency: recent sales (<12mo) are excluded from off-market page
eligibility, so a stamped comp never wrongly becomes an off-market page.

Usage: python3 offmarket_comp_backfill.py --suburb nerang [--months 12] [--dry-run]
"""
import argparse
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts/propradar")
from shared.db import get_gold_coast_db  # noqa: E402
import propradar_client as pr             # noqa: E402

try:
    from src.mongo_client_factory import cosmos_retry
except Exception:
    def cosmos_retry(fn, *a, **kw):
        return fn(*a, **kw)


def norm_addr(s):
    """Normalise an address for matching: upper, drop commas/periods, collapse spaces."""
    if not s:
        return ""
    s = re.sub(r"[.,]", " ", str(s).upper())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def short_key(s):
    """Fallback key: street-number + first street word + suburb tokens (type-agnostic)."""
    toks = norm_addr(s).split()
    if len(toks) < 3:
        return ""
    # drop a trailing 'QLD 4211' if present
    if toks[-1].isdigit():
        toks = toks[:-1]
    if toks and toks[-1] == "QLD":
        toks = toks[:-1]
    return " ".join([toks[0]] + toks[1:2] + toks[-1:]) if len(toks) >= 3 else ""


def build_lookup(coll):
    """normalized complete_address -> doc, plus a short-key fallback map."""
    full, short = {}, {}
    for d in coll.find({"complete_address": {"$exists": True, "$ne": None}},
                       {"complete_address": 1, "LATITUDE": 1, "LONGITUDE": 1,
                        "latitude": 1, "longitude": 1, "listing_status": 1,
                        "sale_price": 1, "sold_date": 1, "comp_source": 1}):
        ca = d.get("complete_address")
        full[norm_addr(ca)] = d
        sk = short_key(ca)
        if sk and sk not in short:
            short[sk] = d
    return full, short


def run(args):
    db = get_gold_coast_db()
    coll = db[args.suburb]
    recs, calls, headers = pr.fetch_all_sold("QLD", args.suburb.replace("_", " ").title(),
                                             months=args.months, property_type="House")
    print(f"PropRadar: {len(recs)} recent-sold houses ({args.months}mo) in {calls} calls "
          f"| rl-remaining={headers.get('x-ratelimit-remaining')}")
    full, short = build_lookup(coll)

    stamped = matched = unmatched = skipped_live = already = 0
    now = datetime.now(timezone.utc).isoformat()
    for r in recs:
        addr = r.get("address")
        price = r.get("sold_price")
        sdate = r.get("sold_date")
        if not addr or not price or not sdate:
            continue
        doc = full.get(norm_addr(addr)) or short.get(short_key(addr))
        if not doc:
            unmatched += 1
            continue
        matched += 1
        if doc.get("listing_status") in ("for_sale", "under_contract"):
            skipped_live += 1
            continue
        # idempotent: skip if already carrying this exact sold comp
        if (doc.get("comp_source") == "propradar" and doc.get("sale_price") == float(price)
                and str(doc.get("sold_date", ""))[:10] == str(sdate)[:10]):
            already += 1
            continue
        patch = {
            "listing_status": "sold",
            "sale_price": float(price),
            "sold_date": str(sdate),
            "property_type": r.get("property_type") or "House",
            "comp_source": "propradar",
            "comp_backfilled_at": now,
        }
        for k_out, k_in in (("bedrooms", "bedrooms"), ("bathrooms", "bathrooms"),
                            ("car_spaces", "parking")):
            if doc.get(k_out) is None and r.get(k_in) is not None:
                patch[k_out] = r.get(k_in)
        stamped += 1
        if not args.dry_run:
            cosmos_retry(coll.update_one, {"_id": doc["_id"]}, {"$set": patch})

    sold_after = coll.count_documents({"listing_status": "sold"})
    print(f"\n=== {args.suburb} comp backfill — {'DRY-RUN' if args.dry_run else 'WROTE'} ===")
    print(f"  matched to a cadastral doc : {matched}/{len(recs)}")
    print(f"  stamped as sold comp       : {stamped}")
    print(f"  already had it (idempotent): {already}")
    print(f"  skipped (live listing)     : {skipped_live}")
    print(f"  unmatched (no coords)      : {unmatched}")
    print(f"  suburb sold-comp docs now  : {sold_after}")
    return {"suburb": args.suburb, "propradar": len(recs), "matched": matched,
            "stamped": stamped, "unmatched": unmatched, "sold_after": sold_after,
            "dry_run": args.dry_run}


def main():
    ap = argparse.ArgumentParser(description="Backfill recent sold comps from PropRadar.")
    ap.add_argument("--suburb", required=True)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        return run(args)
    try:
        from job_status import job_run
        with job_run("offmarket_comp_backfill", cadence_hours=336,  # ~fortnightly refresh
                     title="Off-Market Comp Backfill (PropRadar sold, per suburb)") as beat:
            res = run(args)
            beat.detail = f"{args.suburb}: stamped {res['stamped']} comps ({res['matched']} matched)"
            beat.metrics = {"stamped": res["stamped"], "matched": res["matched"],
                            "sold_after": res["sold_after"]}
            return res
    except ImportError:
        return run(args)


if __name__ == "__main__":
    main()
