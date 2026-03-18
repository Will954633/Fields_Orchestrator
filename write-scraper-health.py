#!/usr/bin/env python3
"""
write-scraper-health.py
Fields Orchestrator — Scraper Health Snapshot Writer

Called by the orchestrator after each for-sale scrape run (processes 101/102).
Reads the most recent listing counts from Gold_Coast_Currently_For_Sale and
writes a health snapshot to system_monitor.scraper_health.

Called with: python3 write-scraper-health.py

Designed to run as a post-step hook from the orchestrator after process 101/102.
"""

import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scraper-health] %(levelname)s %(message)s")
log = logging.getLogger("scraper-health")

TARGET_SUBURBS = [
    "robina", "mudgeeraba", "varsity_lakes", "carrara",
    "reedy_creek", "burleigh_waters", "merrimac", "worongary",
]


def get_mongo_uri():
    settings_path = Path("/home/fields/Fields_Orchestrator/config/settings.yaml")
    with open(settings_path) as f:
        settings = yaml.safe_load(f)
    return settings["mongodb"]["uri"]


def main():
    try:
        from pymongo import MongoClient
        uri = get_mongo_uri()
        client = MongoClient(uri, serverSelectionTimeoutMS=15000, retryWrites=False)
        data_db = client["Gold_Coast"]
        monitor_db = client["system_monitor"]
    except Exception as e:
        log.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    checked_at = datetime.now(timezone.utc)
    saved = 0

    for suburb in TARGET_SUBURBS:
        try:
            col = data_db[suburb]
            total = col.count_documents({"listing_status": "for_sale"})

            # Find the most recently updated for-sale document as proxy for last scrape time
            # Fetch a sample and sort in Python to avoid Cosmos index requirement
            sample = list(col.find({"listing_status": "for_sale"}, {"last_updated": 1}).limit(200))
            sample.sort(key=lambda d: d.get("last_updated") or "", reverse=True)
            last_scraped_at = sample[0].get("last_updated") if sample else None

            # Get previous snapshot to compute delta (sort in Python — no Cosmos index needed)
            prev_snaps = list(monitor_db["scraper_health"].find({"suburb": suburb}).limit(10))
            prev_snaps.sort(key=lambda d: d.get("checked_at") or datetime.min, reverse=True)
            prev_total = prev_snaps[0]["total_listings"] if prev_snaps else None

            new_listings = (total - prev_total) if prev_total is not None and total > prev_total else None
            removed_listings = (prev_total - total) if prev_total is not None and total < prev_total else None

            # Compute status based on how recently data was scraped
            # Pipeline runs nightly so anything under 26h is healthy
            if last_scraped_at:
                last_dt = last_scraped_at
                # Handle timezone-naive datetimes from Cosmos DB (treat as UTC)
                if last_dt and not getattr(last_dt, 'tzinfo', None):
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if last_dt:
                    age_hours = (checked_at - last_dt).total_seconds() / 3600
                else:
                    age_hours = None
                if age_hours is None:
                    status = "unknown"
                elif age_hours <= 26:
                    status = "healthy"
                elif age_hours <= 50:
                    status = "stale"
                else:
                    status = "critical"
            else:
                status = "unknown"

            monitor_db["scraper_health"].insert_one({
                "suburb": suburb,
                "checked_at": checked_at,
                "total_listings": total,
                "last_scraped_at": last_scraped_at,
                "last_scrape_time": last_scraped_at,
                "staleness_hours": round(age_hours, 1) if age_hours is not None else None,
                "new_listings": new_listings,
                "removed_listings": removed_listings,
                "prev_total": prev_total,
                "status": status,
            })
            saved += 1
            log.info(f"{suburb}: total={total}, last_scraped={last_scraped_at}")

        except Exception as e:
            log.error(f"Failed for {suburb}: {e}")

    log.info(f"Done. Saved {saved}/{len(TARGET_SUBURBS)} suburbs.")


if __name__ == "__main__":
    main()
