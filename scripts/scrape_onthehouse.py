#!/usr/bin/env python3
"""Scrape OnTheHouse (CoreLogic) for cadastral records that have no Domain data.

Fills the coverage gap for properties that exist in the cadastral database
but where Domain.com.au has no property profile (Domain covers ~70-90% of
houses; OTH covers close to 100% via CoreLogic's RP Data).

Two API calls per property — no full-page fetch needed:
  1. /odin/api/locations?query={address}  → resolve OTH property ID
  2. /odin/api/properties/{id}            → beds, baths, floor/land area, year
  3. /odin/api/properties/{id}/images     → CoreLogic photo URLs (watermarked)

Data is written under `scraped_data_oth` (separate namespace from Domain data).
Image URLs stored as `oth_image_urls` — CoreLogic watermarked, for internal
use only (do not display publicly without a CoreLogic licence).

Idempotent: skips records with `oth_scraped_at` already set.
Use --reprocess to force re-scrape.

Cohort: houses (no UNIT_NUMBER) in the named suburb that have neither
scraped_data_v2 nor scraped_data_apr01_recovered — the pure Domain gap.

Run:
    python3 scripts/scrape_onthehouse.py --suburb robina --dry-run
    python3 scripts/scrape_onthehouse.py --suburb robina --limit 50
    python3 scripts/scrape_onthehouse.py --suburb burleigh_waters
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bson import ObjectId

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore

load_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("scrape_onthehouse")

BASE = "https://www.onthehouse.com.au/odin/api"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Fields/1.0"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# OTH API helpers
# ---------------------------------------------------------------------------

def _get(session: requests.Session, url: str) -> dict | list | None:
    """GET JSON endpoint with simple retry. Returns parsed body or None."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": UA,
                                     "Accept": "application/json",
                                     "Referer": "https://www.onthehouse.com.au/"})
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                time.sleep(5 + attempt * 5)
                continue
            else:
                return None
        except (requests.RequestException, ValueError):
            if attempt < MAX_RETRIES:
                time.sleep(2 + attempt)
                continue
            return None
    return None


_STREET_TYPE_ABBREV = {
    "AVENUE": "AVE", "BOULEVARD": "BVD", "CIRCUIT": "CCT", "CLOSE": "CL",
    "COURT": "CT", "CRESCENT": "CRES", "DRIVE": "DR", "GROVE": "GR",
    "HIGHWAY": "HWY", "LANE": "LN", "PARADE": "PDE", "PLACE": "PL",
    "ROAD": "RD", "STREET": "ST", "TERRACE": "TCE", "WAY": "WAY",
}


def _normalize_street_type(stype: str) -> str:
    return _STREET_TYPE_ABBREV.get(stype.upper(), stype.upper())


def _street_number_from_formatted(formatted: str) -> str | None:
    """Extract street number from '12 LONGUEVILLE CT, ROBINA...'"""
    parts = formatted.split(" ", 1)
    return parts[0].strip() if parts else None


def resolve_property_id(street_no: str, street_name: str, street_type: str,
                        locality: str, session: requests.Session) -> str | None:
    """Look up OTH property ID; returns None if no exact street-number match."""
    # Try abbreviated street type first (more reliable), then full name
    abbrev = _normalize_street_type(street_type)
    queries = [f"{street_no} {street_name} {abbrev} {locality}"]
    if abbrev != street_type.upper():
        queries.append(f"{street_no} {street_name} {street_type} {locality}")

    for query in queries:
        url = f"{BASE}/locations?query={requests.utils.quote(query)}"
        data = _get(session, url)
        if not data:
            continue
        content = data.get("content", [])
        if not content:
            continue
        match = content[0]
        # Strict validation: returned street number must equal our street number
        returned_no = _street_number_from_formatted(
            match.get("formattedAddress", ""))
        if returned_no and returned_no.upper() == str(street_no).upper():
            return match.get("propertyId")
    return None


def fetch_property(prop_id: str, session: requests.Session) -> dict | None:
    return _get(session, f"{BASE}/properties/{prop_id}")


def fetch_images(prop_id: str, session: requests.Session) -> list[str]:
    data = _get(session, f"{BASE}/properties/{prop_id}/images")
    if not data:
        return []
    return [item["url"] for item in data.get("content", []) if item.get("url")]


# ---------------------------------------------------------------------------
# Per-record scraper
# ---------------------------------------------------------------------------


def process_record(doc: dict, db, suburb: str, session: requests.Session,
                   reprocess: bool, fetch_images_flag: bool) -> dict:
    oid = str(doc["_id"])

    if doc.get("oth_scraped_at") and not reprocess:
        return {"oid": oid, "status": "already_done"}

    no = doc.get("STREET_NO_1")
    name = doc.get("STREET_NAME")
    stype = doc.get("STREET_TYPE")
    locality = doc.get("LOCALITY", "")
    if not all([no, name, stype]):
        return {"oid": oid, "status": "no_address"}

    prop_id = resolve_property_id(no, name, stype, locality, session)
    if not prop_id:
        # Write a not-found marker so we don't keep retrying
        db[suburb].update_one(
            {"_id": ObjectId(oid)},
            {"$set": {"oth_scraped_at": dt.datetime.utcnow(),
                      "oth_not_found": True}},
        )
        return {"oid": oid, "status": "not_found"}

    prop = fetch_property(prop_id, session)
    if not prop:
        return {"oid": oid, "status": "fetch_fail"}

    # Build structured payload
    g = prop.get("guesstimate") or {}
    ls = prop.get("lastSale") or {}
    lr = prop.get("lastRental") or {}
    la = prop.get("legalAttributes") or {}
    addr = prop.get("address") or {}

    oth_data: dict = {
        "oth_property_id": prop.get("othPropertyId") or prop_id,
        "cl_property_id": prop.get("clPropertyId"),
        "formatted_address": addr.get("formattedAddress"),
        "lat": addr.get("location", {}).get("lat"),
        "lon": addr.get("location", {}).get("lon"),
        "beds": prop.get("beds"),
        "baths": prop.get("baths"),
        "car_spaces": prop.get("carSpaces"),
        "floor_size_sqm": prop.get("floorSize"),
        "land_size_sqm": prop.get("landSize"),
        "land_size_unit": prop.get("landSizeUnit"),
        "year_built": prop.get("yearBuilt"),
        "property_type": prop.get("type"),
        "lot_plan": la.get("Lot/Plan"),
        "real_property_desc": la.get("Real Property Description"),
        "last_sale_date": ls.get("eventDate"),
        "last_sale_price": ls.get("salePrice"),
        "last_sale_type": ls.get("saleType"),
        "last_rental_price": lr.get("rentedPrice"),
        "last_rental_date": lr.get("eventDate"),
        "guesstimate_price": g.get("price"),
        "guesstimate_from": g.get("fromPrice"),
        "guesstimate_to": g.get("toPrice"),
        "guesstimate_confidence": g.get("confidence"),
        "guesstimate_date": g.get("calculationDate"),
        "oth_web_url": next(
            (lk["href"] for lk in prop.get("links", [])
             if lk.get("rel") == "othWebUrl"), None
        ),
        "scraped_at": dt.datetime.utcnow().isoformat(),
    }

    image_urls: list[str] = []
    if fetch_images_flag:
        image_urls = fetch_images(prop_id, session)
        oth_data["image_url_count"] = len(image_urls)

    update: dict = {
        "scraped_data_oth": oth_data,
        "oth_scraped_at": dt.datetime.utcnow(),
        "oth_not_found": False,
    }
    if image_urls:
        update["oth_image_urls"] = image_urls

    db[suburb].update_one({"_id": ObjectId(oid)}, {"$set": update})
    return {"oid": oid, "status": "done", "prop_id": prop_id,
            "beds": oth_data.get("beds"), "images": len(image_urls)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suburb", required=True,
                    help="Collection name (e.g. robina, burleigh_waters, varsity_lakes)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=10,
                    help="Concurrent workers (default 10)")
    ap.add_argument("--rate", type=float, default=1.0,
                    help="Min seconds between dispatched requests (default 1.0)")
    ap.add_argument("--fetch-images", action="store_true",
                    help="Also fetch CoreLogic image URLs (watermarked — internal use only)")
    ap.add_argument("--reprocess", action="store_true",
                    help="Re-scrape records already marked done")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = get_client()
    db = client["Gold_Coast"]
    coll = db[args.suburb]

    locality = args.suburb.replace("_", " ").upper()

    # Cohort: houses with NO Domain data at all
    query: dict = {
        "LOCALITY": locality,
        "UNIT_NUMBER": {"$in": [None, ""]},
        "STREET_NO_1": {"$exists": True, "$ne": None},
        "STREET_NAME": {"$exists": True, "$ne": None},
        "STREET_TYPE": {"$exists": True, "$ne": None},
        "$nor": [
            {"scraped_data_v2": {"$exists": True}},
            {"scraped_data_apr01_recovered": {"$exists": True}},
        ],
    }
    if not args.reprocess:
        query["oth_scraped_at"] = {"$exists": False}

    total = coll.count_documents(query)
    log.info("Suburb: %s — eligible records (no Domain data): %d", args.suburb, total)

    proj = {"STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1,
            "LOCALITY": 1, "POSTCODE": 1, "_id": 1, "oth_scraped_at": 1}
    cursor = coll.find(query, proj)
    if args.limit:
        cursor = cursor.limit(args.limit)

    docs = list(cursor)
    log.info("Loaded %d records.", len(docs))

    if args.dry_run:
        log.info("Dry run — sample 5:")
        for doc in docs[:5]:
            q = (f"{doc.get('STREET_NO_1')} {doc.get('STREET_NAME')} "
                 f"{_normalize_street_type(doc.get('STREET_TYPE',''))} "
                 f"{doc.get('LOCALITY','')}")
            log.info("  %s → query: '%s'", doc["_id"], q.strip())
        log.info("(dry run — no API calls)")
        return 0

    counters: dict = {"done": 0, "not_found": 0, "fetch_fail": 0, "no_address": 0,
                      "already_done": 0, "total": 0}
    lock = threading.Lock()
    rate_lock = threading.Lock()
    next_dispatch = [time.time()]
    t0 = time.time()

    session_local = threading.local()

    def get_session():
        if not hasattr(session_local, "s"):
            session_local.s = requests.Session()
        return session_local.s

    def worker(doc):
        with rate_lock:
            wait = next_dispatch[0] - time.time()
            if wait > 0:
                time.sleep(wait)
            next_dispatch[0] = time.time() + args.rate
        s = get_session()
        try:
            r = process_record(doc, db, args.suburb, s, args.reprocess,
                               args.fetch_images)
        except Exception as e:
            log.error("EXCEPTION %s: %s", doc.get("_id"), e)
            r = {"status": "fetch_fail"}
        with lock:
            counters["total"] += 1
            counters[r["status"]] = counters.get(r["status"], 0) + 1
            if r["status"] == "done":
                log.debug("  done %s → OTH#%s beds=%s images=%s",
                          r["oid"], r.get("prop_id"), r.get("beds"), r.get("images"))
            if counters["total"] % 50 == 0:
                elapsed = time.time() - t0
                rate = counters["total"] / max(elapsed, 1)
                eta = (len(docs) - counters["total"]) / max(rate, 0.01) / 60
                log.info("progress: %d/%d done=%d not_found=%d fail=%d rate=%.1f/s ETA=%.0fmin",
                         counters["total"], len(docs), counters["done"],
                         counters["not_found"], counters["fetch_fail"], rate, eta)
        return r

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(worker, d) for d in docs]
        for _ in as_completed(futures):
            pass

    elapsed = time.time() - t0
    log.info("DONE in %.0fs", elapsed)
    log.info("FINAL total=%d done=%d not_found=%d no_address=%d fail=%d already=%d",
             counters["total"], counters.get("done", 0), counters.get("not_found", 0),
             counters.get("no_address", 0), counters.get("fetch_fail", 0),
             counters.get("already_done", 0))
    if counters.get("done", 0):
        hit_rate = 100 * counters["done"] / max(
            counters["done"] + counters.get("not_found", 0), 1)
        log.info("OTH hit rate: %.1f%%", hit_rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
