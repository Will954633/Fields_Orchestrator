"""
enrich_coverage_gaps.py — recover the full property record for PropRadar coverage-gap
addresses (properties PropRadar sold but we don't hold) by scraping their Domain
property-profile via Bright Data (the working fetch path; raw curl_cffi is Domain-blocked).

Writes to a STAGING collection Gold_Coast.propradar_gap_enriched — NOT the live suburb
collection — because promoting these into public off-market pages needs deliberate
url_slug + twin-dedup handling (see [[offmarket_property_twin_dedup]]). This step proves
recovery + stages the data; promotion to live docs/pages is a separate, gated step.

Usage:
    python3 scripts/propradar/enrich_coverage_gaps.py --limit 1 --dry-run
    python3 scripts/propradar/enrich_coverage_gaps.py --limit 5 --apply
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Feilds_Website/03_For_Sale_Coverage")

from shared.db import get_gold_coast_db, cosmos_retry  # noqa: E402
from shared.domain_fetch import fetch_html  # noqa: E402
import domain_profile_scraper as dps  # noqa: E402  (build_profile_url, _extract_from_html)

STAGING = "propradar_gap_enriched"


def enrich_one(db, gap, apply):
    addr = gap.get("address")
    suburb = gap.get("suburb_key")
    url = dps.build_profile_url(addr)
    html = fetch_html(url)
    if not html:
        return "fetch_failed", None, url
    data = dps._extract_from_html(html)
    tl = (data or {}).get("property_timeline") or []
    sold = [e for e in tl if e.get("is_sold") or e.get("category") == "sale"]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    doc = {
        "_id": gap["_id"],                       # PropRadar property_id as key
        "address": addr, "suburb_key": suburb,
        "propradar_property_id": gap["_id"],
        "profile_url": url,
        "scraped_data": data,
        "timeline_events": len(tl), "sold_events": len(sold),
        "source": "propradar_coverage_gap",
        "enriched_at": now,
    }
    if apply:
        cosmos_retry(lambda: db[STAGING].replace_one({"_id": doc["_id"]}, doc, upsert=True),
                     f"gap-enrich:{gap['_id']}")
        cosmos_retry(lambda: db["propradar_coverage_gaps"].update_one(
            {"_id": gap["_id"]}, {"$set": {"status": "enriched", "enriched_at": now}}),
            f"gap-status:{gap['_id']}")
    return "ok", (len(tl), len(sold)), url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--suburb")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run
    db = get_gold_coast_db()
    q = {"status": {"$nin": ["invalid", "enriched"]}}
    if args.suburb:
        q["suburb_key"] = args.suburb
    gaps = list(db["propradar_coverage_gaps"].find(q).limit(args.limit))
    print(f"enriching {len(gaps)} gap(s){' [dry-run]' if not apply else ''}")
    for g in gaps:
        status, counts, url = enrich_one(db, g, apply)
        if status == "ok":
            tl, sold = counts
            print(f"  ✓ {g.get('address'):<48} → {tl} timeline events ({sold} sold) recovered")
        else:
            print(f"  ✗ {g.get('address'):<48} → {status} ({url})")


if __name__ == "__main__":
    main()
