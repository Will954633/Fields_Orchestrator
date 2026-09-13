#!/usr/bin/env python3
"""
scrape_sqm_weekly_rents.py — Weekly asking RENTS from SQM Research, GC-wide.

Same page family and inline-JSON mechanism as scrape_sqm_asking_prices.py (verified
2026-09-14): every SQM chart page embeds the full weekly series as `var data = [...]`
rendered client-side by Highcharts, so one curl_cffi fetch per postcode returns the
whole history — no login, no XHR endpoint.

  URL:    https://sqmresearch.com.au/property/weekly-rents?postcode=NNNN
  Fields: date, houses_all, houses_3, units_all, units_2, combined  ($/week)

SQM data is per-POSTCODE (a postcode can cover several suburbs), so this stores one
doc per GC postcode in Gold_Coast.sqm_weekly_rents. All GC postcodes from
onthehouse.suburbs.ALL_GC (the set covering our 82 tracked suburbs) plus a few
adjacent GC postcodes; any postcode SQM has no data for is reported and skipped.

⚠ SQM ToS restricts scraping/commercial republication — same standing exposure as the
existing asking-prices ingest; a GC-wide rents page is a Will decision (see
gc_wide_overview_scoping memory).

Usage:
  python3 scripts/scrape_sqm_weekly_rents.py --dry-run
  python3 scripts/scrape_sqm_weekly_rents.py
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curl_cffi import requests
from pymongo import MongoClient
from job_status import job_run

# GC postcodes covering our tracked suburbs (from ALL_GC) + adjacent GC postcodes.
# SQM returns an empty series for any that don't exist; those are reported, not stored.
GC_POSTCODES = ["4207", "4208", "4209", "4210", "4211", "4212", "4213", "4214",
                "4215", "4216", "4217", "4218", "4219", "4220", "4221", "4222",
                "4223", "4224", "4225", "4226", "4227", "4228", "4229", "4230"]

FIELDS = ["houses_all", "houses_3", "units_all", "units_2", "combined"]


def load_mongo_uri():
    import yaml
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "config", "settings.yaml")
    with open(cfg) as f:
        return yaml.safe_load(f)["mongodb"]["uri"]


def scrape_postcode(postcode):
    url = f"https://sqmresearch.com.au/property/weekly-rents?postcode={postcode}"
    resp = requests.get(url, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    m = re.search(r"var\s+data\s*=\s*(\[\{.*?\}\])\s*;", resp.text, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1))


def transform(raw):
    out = []
    for row in raw or []:
        if not row.get("date"):
            continue
        out.append({"date": row["date"], **{f: row.get(f) for f in FIELDS}})
    return out


def main():
    dry = "--dry-run" in sys.argv
    client = MongoClient(load_mongo_uri())
    coll = client["Gold_Coast"]["sqm_weekly_rents"]

    with job_run("scrape_sqm_weekly_rents", cadence_hours=168,
                 title="SQM Weekly Rents (GC-wide, per postcode)") as beat:
        ok, empty, errors = {}, [], {}
        now = datetime.now(timezone.utc)
        for pc in GC_POSTCODES:
            try:
                points = transform(scrape_postcode(pc))
                if not points:
                    empty.append(pc)
                    print(f"{pc}: no data (skipped)")
                    continue
                ok[pc] = len(points)
                latest = points[-1]
                print(f"{pc}: {len(points)} weekly points ({points[0]['date']}→{latest['date']}) "
                      f"houses ${latest.get('houses_all')}/wk units ${latest.get('units_all')}/wk")
                if not dry:
                    coll.replace_one({"_id": pc}, {
                        "_id": pc, "postcode": pc, "source": "sqmresearch.com.au",
                        "metric": "weekly_rents_dollars", "frequency": "weekly",
                        "fields": FIELDS, "series": points,
                        "latest_date": latest["date"], "count": len(points),
                        "last_updated": now,
                    }, upsert=True)
            except Exception as e:
                errors[pc] = str(e)
                print(f"{pc}: ERROR {e}")
            time.sleep(1.0)

        # Rule 7b: a run that captured almost nothing is broken, not an empty market.
        if len(ok) < len(GC_POSTCODES) * 0.5:
            raise RuntimeError(
                f"only {len(ok)}/{len(GC_POSTCODES)} postcodes captured "
                f"({len(empty)} empty, {len(errors)} errored) — SQM layout changed or blocked")
        beat.detail = f"{len(ok)} postcodes captured, {len(empty)} empty, {len(errors)} errored"
        beat.metrics = {"captured": len(ok), "empty": len(empty), "errored": len(errors),
                        "points_total": sum(ok.values())}
        print(f"\n{len(ok)} captured, {len(empty)} empty ({empty}), {len(errors)} errored")
    client.close()


if __name__ == "__main__":
    main()
