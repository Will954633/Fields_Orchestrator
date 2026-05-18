#!/usr/bin/env python3
"""Re-scrape records that have apr01-recovered images but no v2 scrape yet.

Phase 2 of the coverage backfill (Phase 1 was CA-003 / CA-007 — postcode
normalisation + targeted rescrape on the wrong-postcode tail).

Cohort logic:
  - Record has `scraped_data_apr01_recovered.images` → property was listed on
    Domain when the apr01 mongodump was taken, so a Domain profile page
    almost certainly still exists.
  - Record does NOT have `scraped_data_v2.image_urls` → we never ran the v2
    scraper against this profile.
  - URL is buildable (STREET_NO_1, STREET_NAME, STREET_TYPE, no UNIT_NUMBER).

Adds (per record): valuation low/mid/upper, up to 6 comparable sales,
hero_image_url + image_urls (current Domain CDN), timeline, rental estimate,
bedrooms/bathrooms/parking/land area.

This script does NOT touch records that already have v2 data, nor records
that have been previously postcode-flagged. Idempotent within a run.

Run:
    python3 scripts/rescrape_apr01_no_v2.py --suburb varsity_lakes --limit 50
    python3 scripts/rescrape_apr01_no_v2.py --suburb burleigh_waters
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore
from scrape_property_profiles import (  # type: ignore
    build_profile_url, Counters, scrape_one,
)

load_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("rescrape_apr01_no_v2")
logging.getLogger("scrape_profiles").setLevel(logging.INFO)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suburb", required=True,
                    help="Collection name (e.g. burleigh_waters, varsity_lakes, robina)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap on records (omit for full cohort)")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--rate", type=float, default=1.5,
                    help="Seconds between dispatched requests (default 1.5)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    locality = args.suburb.replace("_", " ").upper()

    client = get_client()
    db = client["Gold_Coast"]
    coll = db[args.suburb]

    query = {
        "LOCALITY": locality,
        "scraped_data_apr01_recovered.images": {"$exists": True},
        "scraped_data_v2.image_urls": {"$exists": False},
        "STREET_NO_1": {"$exists": True, "$ne": None},
        "STREET_NAME": {"$exists": True, "$ne": None},
        "STREET_TYPE": {"$exists": True, "$ne": None},
        "UNIT_NUMBER": {"$in": [None, ""]},
    }
    total_eligible = coll.count_documents(query)
    log.info("Suburb: %s (LOCALITY=%s)", args.suburb, locality)
    log.info("Eligible records (apr01-image cohort, no v2 yet): %d", total_eligible)

    proj = {
        "STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1,
        "LOCALITY": 1, "POSTCODE": 1, "display_postcode": 1,
        "UNIT_NUMBER": 1, "_id": 1,
    }
    cursor = coll.find(query, proj)
    if args.limit:
        cursor = cursor.limit(args.limit)

    queue = []
    for doc in cursor:
        url = build_profile_url(doc)
        if not url:
            continue
        queue.append((args.suburb, str(doc["_id"]), doc, url))
    log.info("Queued: %d (skipped %d due to missing URL components)",
             len(queue), (args.limit or total_eligible) - len(queue))

    if args.dry_run:
        log.info("Dry run — sample 5:")
        for s, _id, d, url in queue[:5]:
            log.info("  %s %s", url, _id)
        return 0

    counters = Counters()
    rate_lock = threading.Lock()
    next_dispatch = [time.time()]

    def dispatch(item):
        with rate_lock:
            wait = next_dispatch[0] - time.time()
            if wait > 0:
                time.sleep(wait)
            next_dispatch[0] = time.time() + args.rate
        s, _id, d, url = item
        try:
            scrape_one(db, s, _id, d, url, counters, dry_run=False, log_every=50)
        except Exception as e:
            log.error("EXCEPTION %s: %s", _id, e)

    log.info("Starting: %d workers, %.1fs rate", args.workers, args.rate)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(dispatch, item) for item in queue]
        for _ in as_completed(futures):
            pass

    elapsed = time.time() - t0
    log.info("DONE in %.1fs", elapsed)
    log.info("FINAL attempted=%d parsed=%d written=%d failed_fetch=%d failed_parse=%d",
             counters.attempted, counters.parsed, counters.written,
             counters.failed_fetch, counters.failed_parse)
    if counters.attempted:
        log.info("Success rate: %.1f%%", 100 * counters.parsed / counters.attempted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
