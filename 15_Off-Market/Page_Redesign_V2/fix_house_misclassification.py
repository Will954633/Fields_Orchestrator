#!/usr/bin/env python3
"""
fix_house_misclassification.py — correct v2-scrape property_type regressions.

The v2 Domain scrape (2026-05) relabelled some standalone houses as non-house
types (Apartment/Duplex/Townhouse/…) and that value got promoted to the
top-level `property_type`, wrongly excluding them from BOTH the Google index
(sitemap getOffMarketUrls) and the off-market Discovery deck.

RULE (Will, 2026-07-31): when the stored non-house label conflicts with the
ORIGINAL scrape's "House" AND the address has no unit fraction ("x/y"), trust
"House". We keep the old value + provenance so it's auditable and reversible.

  python3 fix_house_misclassification.py            # dry-run (list, no writes)
  python3 fix_house_misclassification.py --apply
"""
import re
import sys
import argparse
import datetime

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

NON_HOUSE = {
    "Townhouse", "Apartment", "Apartment / Unit / Flat", "Unit", "Flat",
    "Duplex", "Villa", "Terrace", "Semi-Detached", "Studio",
    "Retirement Living", "New Apartments / Off the Plan",
    "Land", "Vacant land", "Industrial", "Development Site",
    "Leisure", "Sport", "Other", "Farm",
}
UNIT_ADDR_RE = re.compile(r"\d+\s*/\s*\d+")
CORE = ["robina", "varsity_lakes", "burleigh_waters"]


def orig_says_house(r):
    """An ORIGINAL-era scrape (pre-v2) says House."""
    for src in ("scraped_data", "scraped_data_apr01_recovered"):
        feats = (r.get(src) or {}).get("features") or {}
        if feats.get("property_type") == "House":
            return src
    return None


def main(apply=False):
    from src.mongo_client_factory import get_mongo_client, cosmos_retry
    gc = get_mongo_client()["Gold_Coast"]
    now = datetime.datetime.utcnow()
    total = fixed = 0
    from collections import Counter
    by_type = Counter()
    samples = []
    for c in CORE:
        coll = gc[c]
        cur = coll.find(
            {"property_type": {"$in": list(NON_HOUSE)}},
            {"property_type": 1, "address": 1, "url_slug": 1,
             "scraped_data.features.property_type": 1,
             "scraped_data_apr01_recovered.features.property_type": 1},
        )
        for r in cur:
            addr = str(r.get("address") or "")
            if UNIT_ADDR_RE.search(addr):
                continue  # genuine unit address — leave it
            src = orig_says_house(r)
            if not src:
                continue  # no original House to trust
            total += 1
            by_type[r.get("property_type")] += 1
            if len(samples) < 12:
                samples.append((r.get("url_slug"), r.get("property_type"), src))
            if apply:
                cosmos_retry(lambda _id=r["_id"], old=r.get("property_type"), _c=coll, _src=src: _c.update_one(
                    {"_id": _id},
                    {"$set": {
                        "property_type": "House",
                        "property_type_correction": {
                            "from": old, "to": "House", "at": now,
                            "reason": "v2-scrape non-house overrode original House; no unit-fraction address",
                            "trusted_source": _src, "rule": "will_2026-07-31",
                        },
                    }},
                ))
                fixed += 1
    print(f"{'APPLIED' if apply else 'DRY-RUN'}: {total} records match "
          f"(stored non-house + original scrape=House + no unit-fraction address)")
    print("by (wrong) stored type:")
    for t, n in by_type.most_common():
        print(f"   {n:5}  {t} -> House")
    print("\nsamples (slug | was | trusted_source):")
    for s in samples:
        print("  ", s)
    if apply:
        print(f"\ncorrected {fixed} records to House.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    main(apply=a.apply)
