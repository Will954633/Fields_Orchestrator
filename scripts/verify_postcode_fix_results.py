#!/usr/bin/env python3
"""Verify post-rescrape outcomes for the Robina postcode-fixed cohort.

Counts how many of the 1,968 normalised records gained a Domain hero image,
property data block, valuation, etc. Compares to the global Robina coverage
before/after for a sanity check.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore

load_env()


def main() -> int:
    db = get_client()["Gold_Coast"]
    coll = db["robina"]

    cohort = {"LOCALITY": "ROBINA", "POSTCODE_original_cadastral": {"$exists": True}}
    cohort_size = coll.count_documents(cohort)
    has_hero = coll.count_documents({**cohort, "domain_hero_image_url": {"$exists": True, "$ne": None, "$ne": ""}})
    has_v2 = coll.count_documents({**cohort, "scraped_data_v2": {"$exists": True, "$ne": None}})
    v2_with_images = coll.count_documents({**cohort, "scraped_data_v2.image_count": {"$gt": 0}})
    v2_with_val = coll.count_documents({**cohort, "scraped_data_v2.valuation.mid": {"$exists": True, "$ne": None}})
    v2_with_comps = coll.count_documents({**cohort, "scraped_data_v2.comparable_sales.0": {"$exists": True}})
    still_failed = coll.count_documents({**cohort, "scraped_v2_failed_at": {"$exists": True, "$ne": None}})

    print(f"=== Postcode-fixed Robina cohort ({cohort_size} records) ===")
    print(f"  has Domain hero image:         {has_hero} ({100*has_hero/cohort_size:.1f}%)")
    print(f"  has scraped_data_v2:           {has_v2} ({100*has_v2/cohort_size:.1f}%)")
    print(f"  scraped_data_v2 with images:   {v2_with_images} ({100*v2_with_images/cohort_size:.1f}%)")
    print(f"  scraped_data_v2 with mid val:  {v2_with_val} ({100*v2_with_val/cohort_size:.1f}%)")
    print(f"  scraped_data_v2 with comps:    {v2_with_comps} ({100*v2_with_comps/cohort_size:.1f}%)")
    print(f"  still flagged v2-failed:       {still_failed} ({100*still_failed/cohort_size:.1f}%)")

    # Global Robina recap
    total = coll.count_documents({})
    g_v2 = coll.count_documents({"scraped_data_v2": {"$exists": True, "$ne": None}})
    g_hero = coll.count_documents({"domain_hero_image_url": {"$exists": True, "$ne": None, "$ne": ""}})
    print(f"\n=== Global Robina ({total} records) ===")
    print(f"  has scraped_data_v2:           {g_v2} ({100*g_v2/total:.1f}%)")
    print(f"  has Domain hero image:         {g_hero} ({100*g_hero/total:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
