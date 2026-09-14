#!/usr/bin/env python3
"""
scrape_sqm_city_comparison.py — SQM weekly rents AND asking prices at CITY/REGION
level for the rental-yield comparison: Gold Coast vs Brisbane / Sydney / Melbourne.

Both metrics come from the same SQM inline-JSON pages (verified 2026-09-14), so one
fetch each. Rental yield = weekly_rent × 52 / asking_price is then computed downstream
by build_rental_yields.py — keeping rent and price on the SAME source and geography.

Geographies (SQM region param + type): type=c capital city, type=r sub-region.
  gold_coast  qld-Gold Coast  r
  brisbane    qld-Brisbane    c
  sydney      nsw-Sydney      c
  melbourne   vic-Melbourne   c

Stored one doc per geography in Gold_Coast.sqm_city_series with both series.

⚠ SQM ToS restricts scraping/commercial republication — standing exposure, same as
the postcode ingests; a public yield chart is a Will decision (he requested this).

Usage: python3 scripts/scrape_sqm_city_comparison.py [--dry-run]
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curl_cffi import requests
from pymongo import MongoClient
from job_status import job_run

GEOS = {
    "gold_coast": ("qld-Gold Coast", "r", "Gold Coast"),
    "brisbane": ("qld-Brisbane", "c", "Brisbane"),
    "sydney": ("nsw-Sydney", "c", "Sydney"),
    "melbourne": ("vic-Melbourne", "c", "Melbourne"),
}
FIELDS = ["houses_all", "houses_3", "units_all", "units_2", "combined"]
PAGES = {"rents": "weekly-rents", "asking": "asking-property-prices"}


def load_mongo_uri():
    import yaml
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "config", "settings.yaml")
    with open(cfg) as f:
        return yaml.safe_load(f)["mongodb"]["uri"]


def fetch(page, region, type_):
    url = f"https://sqmresearch.com.au/property/{page}?region={quote(region)}&type={type_}"
    r = requests.get(url, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    m = re.search(r"var\s+data\s*=\s*(\[\{.*?\}\])\s*;", r.text, re.DOTALL)
    if not m:
        return None
    return [{"date": row["date"], **{f: row.get(f) for f in FIELDS}}
            for row in json.loads(m.group(1)) if row.get("date")]


def main():
    dry = "--dry-run" in sys.argv
    client = MongoClient(load_mongo_uri())
    coll = client["Gold_Coast"]["sqm_city_series"]
    with job_run("scrape_sqm_city_comparison", cadence_hours=168,
                 title="SQM city rents+asking (GC vs capitals, for yields)") as beat:
        now = datetime.now(timezone.utc)
        ok = 0
        for key, (region, type_, label) in GEOS.items():
            rents = fetch(PAGES["rents"], region, type_)
            time.sleep(1.0)
            asking = fetch(PAGES["asking"], region, type_)
            time.sleep(1.0)
            if not rents or not asking:
                print(f"{key}: MISSING (rents={bool(rents)} asking={bool(asking)})")
                continue
            ok += 1
            rl, al = rents[-1], asking[-1]
            hy = rl["houses_all"] * 52 / al["houses_all"] * 100 if al["houses_all"] else None
            uy = rl["units_all"] * 52 / al["units_all"] * 100 if al["units_all"] else None
            print(f"{label}: rents→{rl['date']} asking→{al['date']} | "
                  f"house yield {hy:.2f}% unit yield {uy:.2f}%")
            if not dry:
                coll.replace_one({"_id": key}, {
                    "_id": key, "geography": key, "label": label,
                    "region": region, "type": type_, "source": "sqmresearch.com.au",
                    "rents_series": rents, "asking_series": asking,
                    "rents_latest": rl["date"], "asking_latest": al["date"],
                    "last_updated": now,
                }, upsert=True)
        if ok < len(GEOS):
            raise RuntimeError(f"only {ok}/{len(GEOS)} geographies captured — SQM layout/block")
        beat.detail = f"{ok}/{len(GEOS)} geographies (rents+asking)"
        beat.metrics = {"geographies": ok}
    client.close()


if __name__ == "__main__":
    main()
