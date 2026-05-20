#!/usr/bin/env python3
"""Scrape OnTheHouse (CoreLogic) for cadastral records that have no Domain data.

Fills the coverage gap for properties that exist in the cadastral database
but where Domain.com.au has no property profile (Domain covers ~70-90% of
houses; OTH covers close to 100% via CoreLogic's RP Data).

Three steps per matched property:
  1. /odin/api/locations?query={address}  → resolve OTH property ID
                                            (strict street-number validation)
  2. /odin/api/properties/{id}            → beds, baths, floor/land area, year
                                            built, last sale, rental, guesstimate
  3. Full property page (~124KB gzipped)  → all photos + floor plans from
                                            inline Redux JSON

Steps 2 and 3 only happen when step 1 finds a match (~30% hit rate).

Data written to MongoDB:
  scraped_data_oth        — structured property fields
  oth_image_urls          — CoreLogic photo URLs (watermarked — internal use)
  oth_floorplan_urls      — CoreLogic floor plan URLs (watermarked — internal)
  oth_scraped_at          — timestamp marker (idempotency)
  oth_not_found           — True if OTH has no record for this address

Cohort: houses (no UNIT_NUMBER) with neither scraped_data_v2 nor
scraped_data_apr01_recovered — the pure Domain coverage gap.

Run:
    python3 scripts/scrape_onthehouse.py --suburb robina --dry-run
    python3 scripts/scrape_onthehouse.py --suburb robina --limit 50
    python3 scripts/scrape_onthehouse.py --suburb burleigh_waters
    python3 scripts/scrape_onthehouse.py --suburb robina --reprocess
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
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
REQUEST_TIMEOUT = 25
MAX_RETRIES = 2

_STREET_TYPE_ABBREV = {
    "AVENUE": "AVE", "BOULEVARD": "BVD", "CIRCUIT": "CCT", "CLOSE": "CL",
    "COURT": "CT", "CRESCENT": "CRES", "DRIVE": "DR", "GROVE": "GR",
    "HIGHWAY": "HWY", "LANE": "LN", "PARADE": "PDE", "PLACE": "PL",
    "ROAD": "RD", "STREET": "ST", "TERRACE": "TCE", "WAY": "WAY",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_get(session: requests.Session, url: str) -> dict | list | None:
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
            else:
                return None
        except (requests.RequestException, ValueError):
            if attempt < MAX_RETRIES:
                time.sleep(2 + attempt)
            else:
                return None
    return None


def _html_get(session: requests.Session, url: str) -> str | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": UA,
                                     "Accept": "text/html",
                                     "Accept-Encoding": "gzip, deflate, br",
                                     "Referer": "https://www.onthehouse.com.au/"})
            if r.status_code == 200:
                return r.text
            elif r.status_code == 429:
                time.sleep(5 + attempt * 5)
            else:
                return None
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(2 + attempt)
            else:
                return None
    return None


def _normalize_street_type(stype: str) -> str:
    return _STREET_TYPE_ABBREV.get(stype.upper(), stype.upper())


def _street_number_from_formatted(formatted: str) -> str | None:
    parts = formatted.split(" ", 1)
    return parts[0].strip() if parts else None


# ---------------------------------------------------------------------------
# OTH API
# ---------------------------------------------------------------------------

def resolve_property_id(street_no: str, street_name: str, street_type: str,
                        locality: str, session: requests.Session) -> str | None:
    """Resolve OTH property ID from address. Returns None if no exact match."""
    abbrev = _normalize_street_type(street_type)
    queries = [f"{street_no} {street_name} {abbrev} {locality}"]
    if abbrev != street_type.upper():
        queries.append(f"{street_no} {street_name} {street_type} {locality}")

    for query in queries:
        url = f"{BASE}/locations?query={requests.utils.quote(query)}"
        data = _json_get(session, url)
        if not data:
            continue
        content = data.get("content", [])
        if not content:
            continue
        match = content[0]
        returned_no = _street_number_from_formatted(
            match.get("formattedAddress", ""))
        if returned_no and returned_no.upper() == str(street_no).upper():
            return match.get("propertyId")
    return None


def fetch_property_api(prop_id: str, session: requests.Session) -> dict | None:
    return _json_get(session, f"{BASE}/properties/{prop_id}")


def extract_media_from_page(html: str) -> tuple[list[str], list[str]]:
    """Extract photo URLs and floor plan URLs from the OTH page inline JSON.

    Returns (image_urls, floorplan_urls).
    """
    # The page embeds a large Redux state as inline JS. Find the media section
    # under propertyDetail.property.media
    idx = html.find('"propertyDetail":{"status":"success"')
    if idx == -1:
        return [], []

    start = html.index('{', idx + len('"propertyDetail":'))
    depth = 0
    end = start
    for i, c in enumerate(html[start:], start):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    import json
    try:
        pd = json.loads(html[start:end])
    except (json.JSONDecodeError, ValueError):
        return [], []

    prop = pd.get("property", {})
    media = prop.get("media") or {}

    image_urls = [item["url"] for item in media.get("images", [])
                  if item.get("url")]
    floorplan_urls = [item["url"] for item in media.get("floorplan", [])
                      if item.get("url")]
    return image_urls, floorplan_urls


# ---------------------------------------------------------------------------
# Per-record scraper
# ---------------------------------------------------------------------------

def process_record(doc: dict, db, suburb: str, session: requests.Session,
                   reprocess: bool) -> dict:
    oid = str(doc["_id"])

    if doc.get("oth_scraped_at") and not reprocess:
        return {"oid": oid, "status": "already_done"}

    no = doc.get("STREET_NO_1")
    name = doc.get("STREET_NAME")
    stype = doc.get("STREET_TYPE")
    locality = doc.get("LOCALITY", "")
    if not all([no, name, stype]):
        return {"oid": oid, "status": "no_address"}

    # Step 1: resolve property ID
    prop_id = resolve_property_id(no, name, stype, locality, session)
    if not prop_id:
        db[suburb].update_one(
            {"_id": ObjectId(oid)},
            {"$set": {"oth_scraped_at": dt.datetime.utcnow(),
                      "oth_not_found": True}},
        )
        return {"oid": oid, "status": "not_found"}

    # Step 2: structured data via API
    prop = fetch_property_api(prop_id, session)
    if not prop:
        return {"oid": oid, "status": "fetch_fail"}

    g = prop.get("guesstimate") or {}
    ls = prop.get("lastSale") or {}
    lr = prop.get("lastRental") or {}
    la = prop.get("legalAttributes") or {}
    addr = prop.get("address") or {}

    oth_web_url = next(
        (lk["href"] for lk in prop.get("links", [])
         if lk.get("rel") == "othWebUrl"), None
    )

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
        "oth_web_url": oth_web_url,
        "scraped_at": dt.datetime.utcnow().isoformat(),
    }

    # Step 3: fetch full page for photos + floor plans
    image_urls: list[str] = []
    floorplan_urls: list[str] = []
    if oth_web_url:
        html = _html_get(session, oth_web_url)
        if html:
            image_urls, floorplan_urls = extract_media_from_page(html)
    oth_data["image_count"] = len(image_urls)
    oth_data["floorplan_count"] = len(floorplan_urls)

    update: dict = {
        "scraped_data_oth": oth_data,
        "oth_scraped_at": dt.datetime.utcnow(),
        "oth_not_found": False,
    }
    if image_urls:
        update["oth_image_urls"] = image_urls
    if floorplan_urls:
        update["oth_floorplan_urls"] = floorplan_urls

    db[suburb].update_one({"_id": ObjectId(oid)}, {"$set": update})
    return {
        "oid": oid, "status": "done", "prop_id": prop_id,
        "beds": oth_data.get("beds"),
        "images": len(image_urls),
        "floorplans": len(floorplan_urls),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suburb", required=True,
                    help="Collection name (e.g. robina, burleigh_waters, varsity_lakes)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8,
                    help="Concurrent workers (default 8)")
    ap.add_argument("--rate", type=float, default=1.0,
                    help="Min seconds between dispatched requests (default 1.0)")
    ap.add_argument("--reprocess", action="store_true",
                    help="Re-scrape records already marked done")
    ap.add_argument("--matched-only", action="store_true",
                    help="With --reprocess: only re-process confirmed matches "
                         "(oth_not_found=False). Skips the not-found majority.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = get_client()
    db = client["Gold_Coast"]
    coll = db[args.suburb]

    locality = args.suburb.replace("_", " ").upper()

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
    elif args.matched_only:
        # Only re-process records that previously matched OTH
        query["oth_scraped_at"] = {"$exists": True}
        query["oth_not_found"] = {"$ne": True}

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
                 f"{_normalize_street_type(doc.get('STREET_TYPE', ''))} "
                 f"{doc.get('LOCALITY', '')}")
            log.info("  %s → '%s'", doc["_id"], q.strip())
        log.info("(dry run — no API calls)")
        return 0

    counters: dict = {"done": 0, "not_found": 0, "fetch_fail": 0,
                      "no_address": 0, "already_done": 0, "total": 0,
                      "images": 0, "floorplans": 0}
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
            r = process_record(doc, db, args.suburb, s, args.reprocess)
        except Exception as e:
            log.error("EXCEPTION %s: %s", doc.get("_id"), e)
            r = {"status": "fetch_fail"}
        with lock:
            counters["total"] += 1
            counters[r["status"]] = counters.get(r["status"], 0) + 1
            counters["images"] += r.get("images", 0)
            counters["floorplans"] += r.get("floorplans", 0)
            if counters["total"] % 50 == 0:
                elapsed = time.time() - t0
                rate = counters["total"] / max(elapsed, 1)
                eta = (len(docs) - counters["total"]) / max(rate, 0.01) / 60
                log.info(
                    "progress: %d/%d done=%d not_found=%d fail=%d "
                    "images=%d floorplans=%d rate=%.1f/s ETA=%.0fmin",
                    counters["total"], len(docs), counters["done"],
                    counters["not_found"], counters["fetch_fail"],
                    counters["images"], counters["floorplans"], rate, eta)
        return r

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(worker, d) for d in docs]
        for _ in as_completed(futures):
            pass

    elapsed = time.time() - t0
    log.info("DONE in %.0fs", elapsed)
    log.info(
        "FINAL total=%d done=%d not_found=%d no_address=%d fail=%d already=%d "
        "images=%d floorplans=%d",
        counters["total"], counters.get("done", 0), counters.get("not_found", 0),
        counters.get("no_address", 0), counters.get("fetch_fail", 0),
        counters.get("already_done", 0), counters["images"], counters["floorplans"])
    if counters.get("done", 0):
        hit_pct = 100 * counters["done"] / max(
            counters["done"] + counters.get("not_found", 0), 1)
        log.info("OTH hit rate: %.1f%%", hit_pct)
    return 0


if __name__ == "__main__":
    sys.exit(main())
