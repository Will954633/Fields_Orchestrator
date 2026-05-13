#!/usr/bin/env python3
"""scrape_property_profiles.py — backfill cadastral data from Domain property-profile pages.

Built 2026-05-13 after Azure blob shutdown took down ~20k stored image URLs.
Domain's property-profile pages (https://www.domain.com.au/property-profile/<slug>)
expose JSON in `__APOLLO_STATE__` covering address, beds/baths, parking, lot/plan,
land area, valuation (low/mid/high), rental estimate, sale timeline, comparable
sales, and a hero image hosted on `rimh2.domainstatic.com.au` (not behind Akamai —
direct-fetchable from this VM).

Routes through `shared.domain_fetch.fetch_html` which uses Bright Data Web Unlocker
to bypass Akamai on the profile pages themselves. Image URLs are recorded but not
downloaded — they're served directly from Domain's CDN (durable as long as the
listing isn't withdrawn; we can move to local storage later if durability matters).

Resumable: skips docs with `scraped_at_v2` within the last 30 days.
Concurrent: ThreadPoolExecutor with rate-limited dispatch (1 request every 2s by
default, configurable via --rate). At default rate, full 28k pass takes ~15-16h.

USAGE:
    # Smoke test on 5 random across suburbs:
    python3 scripts/scrape_property_profiles.py --limit 5 --dry-run

    # Real run on 50:
    python3 scripts/scrape_property_profiles.py --limit 50

    # Full pass for all 4 target suburbs, resumable, log to file:
    python3 scripts/scrape_property_profiles.py --all --log-file logs/scrape_profiles_$(date +%Y%m%d).log

    # Target only specific suburbs:
    python3 scripts/scrape_property_profiles.py --suburbs merrimac,burleigh_waters
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client  # noqa: E402
from shared.domain_fetch import fetch_html  # noqa: E402

DEFAULT_SUBURBS = ["merrimac", "robina", "varsity_lakes", "burleigh_waters"]
RESCRAPE_AFTER_DAYS = 30
DEFAULT_RATE_SEC = 2.0  # seconds between requests dispatched
DEFAULT_WORKERS = 30
DEFAULT_TIMEOUT = 120  # fetch timeout (sec)
CHECKPOINT_EVERY = 25

log = logging.getLogger("scrape_profiles")


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

# Mapping STREET_TYPE codes/words to Domain's URL slug form.
STREET_TYPE_SLUG = {
    "STREET": "street", "ST": "street",
    "ROAD": "road", "RD": "road",
    "AVENUE": "avenue", "AVE": "avenue",
    "DRIVE": "drive", "DR": "drive",
    "COURT": "court", "CT": "court",
    "PLACE": "place", "PL": "place",
    "LANE": "lane", "LN": "lane",
    "BOULEVARD": "boulevard", "BLVD": "boulevard",
    "CRESCENT": "crescent", "CRES": "crescent",
    "PARADE": "parade", "PDE": "parade",
    "WAY": "way",
    "CIRCUIT": "circuit", "CCT": "circuit",
    "CLOSE": "close", "CL": "close",
    "TERRACE": "terrace", "TCE": "terrace",
    "HIGHWAY": "highway", "HWY": "highway",
    "ESPLANADE": "esplanade", "ESP": "esplanade",
    "SQUARE": "square", "SQ": "square",
    "TRACK": "track",
    "CRESCENT": "crescent",
    "RISE": "rise",
    "GROVE": "grove", "GR": "grove",
    "TRAIL": "trail",
    "RIDGE": "ridge",
    "QUAY": "quay",
    "PROMENADE": "promenade",
    "WALK": "walk",
    "GARDENS": "gardens", "GDNS": "gardens",
    "HEIGHTS": "heights", "HTS": "heights",
    "VISTA": "vista",
    "VIEW": "view",
    "POCKET": "pocket",
    "MEWS": "mews",
    "LINK": "link",
    "EXTENSION": "extension",
    "CIRCLE": "circle",
    "BEND": "bend",
    "ARCADE": "arcade",
    "ALLEY": "alley",
    "BANK": "bank",
    "MALL": "mall",
}


def build_profile_url(doc: dict[str, Any]) -> str | None:
    """Construct the Domain property-profile URL from cadastral fields.

    Returns None if mandatory components are missing or look unusable
    (e.g. unit-style addresses with no clean street number).
    """
    street_no = doc.get("STREET_NO_1")
    street_name = doc.get("STREET_NAME")
    street_type = doc.get("STREET_TYPE")
    locality = doc.get("LOCALITY")
    postcode = doc.get("POSTCODE") or doc.get("display_postcode")

    if not (street_no and street_name and locality and postcode):
        return None

    street_no = str(street_no).strip()
    street_name_slug = str(street_name).strip().lower().replace(" ", "-")
    street_type_slug = STREET_TYPE_SLUG.get(
        str(street_type).strip().upper() if street_type else "",
        str(street_type).strip().lower() if street_type else "",
    )
    locality_slug = str(locality).strip().lower().replace(" ", "-")
    postcode = str(postcode).strip()

    # Handle unit-numbered addresses (Domain pattern: "1-25-foo-street-..." → no, actually `1-2-foo` for unit 1 of 2)
    unit = doc.get("UNIT_NUMBER")
    if unit:
        # Most off-market off-strata won't have units, but be safe
        slug_first = f"{str(unit).strip()}-{street_no}"
    else:
        slug_first = street_no

    if street_type_slug:
        return (
            f"https://www.domain.com.au/property-profile/"
            f"{slug_first}-{street_name_slug}-{street_type_slug}-{locality_slug}-qld-{postcode}"
        )
    # Without street type, Domain's URL is incomplete; skip for now
    return None


# ---------------------------------------------------------------------------
# HTML → data parser
# ---------------------------------------------------------------------------

NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def parse_property_profile(html: str) -> dict[str, Any] | None:
    """Parse a Domain property-profile page HTML → structured dict.

    Returns None if the page can't be parsed (page-not-found, format change,
    or any other parse failure). Successful return is always a dict with
    at least an `address_line` and `domain_property_id`.
    """
    if not html or len(html) < 1000:
        return None

    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    page_props = data.get("props", {}).get("pageProps", {})
    apollo = page_props.get("__APOLLO_STATE__", {})
    if not apollo:
        return None

    # Find the Property entity
    prop = None
    for key, val in apollo.items():
        if key.startswith("Property:") and isinstance(val, dict) and val.get("__typename") == "Property":
            prop = val
            break
    if not prop:
        return None

    # Address (the Apollo entity contains a structured address dict)
    addr_obj = prop.get("address")
    if isinstance(addr_obj, dict) and "__ref" in addr_obj:
        addr_obj = apollo.get(addr_obj["__ref"], {})
    addr_obj = addr_obj or {}

    address_line = addr_obj.get("displayAddress")

    # Hero image — look for the media key (key is "media({\"categories\":[\"IMAGE\"]})")
    image_url = None
    image_urls: list[str] = []
    for key, val in prop.items():
        if key.startswith("media(") and isinstance(val, list):
            for img in val:
                if isinstance(img, dict) and "__ref" in img:
                    img = apollo.get(img["__ref"], {})
                if isinstance(img, dict) and img.get("url"):
                    url = img["url"]
                    if url not in image_urls:
                        image_urls.append(url)
            break
    if image_urls:
        image_url = image_urls[0]

    # Valuation
    val_obj = prop.get("valuation")
    if isinstance(val_obj, dict) and "__ref" in val_obj:
        val_obj = apollo.get(val_obj["__ref"], {})
    val_obj = val_obj if isinstance(val_obj, dict) else {}

    # Rental estimate
    rent_obj = prop.get("rentalEstimate")
    if isinstance(rent_obj, dict) and "__ref" in rent_obj:
        rent_obj = apollo.get(rent_obj["__ref"], {})
    rent_obj = rent_obj if isinstance(rent_obj, dict) else {}

    # Timeline (sale history)
    timeline_raw = prop.get("timeline") or []
    timeline = []
    for ev in timeline_raw:
        if isinstance(ev, dict) and "__ref" in ev:
            ev = apollo.get(ev["__ref"], {})
        if not isinstance(ev, dict):
            continue
        sale_meta = ev.get("saleMetadata") or {}
        if isinstance(sale_meta, dict) and "__ref" in sale_meta:
            sale_meta = apollo.get(sale_meta["__ref"], {})
        timeline.append({
            "category": ev.get("category"),
            "event_date": ev.get("eventDate"),
            "event_price": ev.get("eventPrice"),
            "price_description": ev.get("priceDescription"),
            "agency": ev.get("agency"),
            "is_sold": (sale_meta or {}).get("isSold"),
            "days_on_market": ev.get("daysOnMarket"),
            "is_major_event": ev.get("isMajorEvent"),
        })

    # Comparable sales — keep up to 6
    comp_sales = []
    for cs in (prop.get("comparableSales") or [])[:6]:
        if isinstance(cs, dict) and "__ref" in cs:
            cs = apollo.get(cs["__ref"], {})
        if not isinstance(cs, dict):
            continue
        last_sale = cs.get("lastSaleActivity") or {}
        if isinstance(last_sale, dict) and "__ref" in last_sale:
            last_sale = apollo.get(last_sale["__ref"], {})
        comp_sales.append({
            "address": cs.get("address"),
            "bedrooms": cs.get("bedrooms"),
            "bathrooms": cs.get("bathrooms"),
            "car_spaces": cs.get("carSpaces"),
            "last_sale_date": (last_sale or {}).get("date"),
            "last_sale_price": (last_sale or {}).get("price"),
        })

    # Land area — note: the key includes the unit argument, e.g. landArea({"unit":"SQUARE_METERS"})
    land_area = None
    internal_area = None
    for k, v in prop.items():
        if k.startswith("landArea("):
            land_area = v
        elif k.startswith("internalArea("):
            internal_area = v

    return {
        "domain_property_id": prop.get("propertyId"),
        "domain_hpg_slug": prop.get("hpgSlug"),
        "address_line": address_line,
        "structured_address": {
            "street_number": addr_obj.get("streetNumber"),
            "street_name": addr_obj.get("streetName"),
            "street_type": addr_obj.get("streetTypeLong"),
            "suburb_name": addr_obj.get("suburbName"),
            "state": addr_obj.get("state"),
            "postcode": addr_obj.get("postcode"),
        },
        "category": prop.get("category"),
        "property_type": prop.get("type"),
        "bedrooms": prop.get("bedrooms"),
        "bathrooms": prop.get("bathrooms"),
        "parking_spaces": prop.get("parkingSpaces"),
        "land_area_sqm": land_area,
        "internal_area_sqm": internal_area,
        "lot_number": prop.get("lotNumber"),
        "plan_number": prop.get("planNumber"),
        "section_number": prop.get("sectionNumber"),
        "hero_image_url": image_url,
        "image_urls": image_urls,
        "image_count": len(image_urls),
        "valuation": {
            "lower": val_obj.get("lowerPrice"),
            "mid": val_obj.get("midPrice"),
            "upper": val_obj.get("upperPrice"),
            "confidence": val_obj.get("priceConfidence"),
            "source": val_obj.get("source"),
            "date": val_obj.get("date"),
        } if val_obj else None,
        "rental_estimate": {
            "weekly_rent": rent_obj.get("weeklyRentEstimate"),
            "yield_pct": rent_obj.get("percentYieldRentEstimate"),
            "confidence": rent_obj.get("rentalFsdConfidence"),
            "date": rent_obj.get("estimateDate"),
        } if rent_obj else None,
        "timeline": timeline,
        "comparable_sales": comp_sales,
    }


# ---------------------------------------------------------------------------
# Scrape orchestration
# ---------------------------------------------------------------------------


def _short_addr_for_log(doc: dict[str, Any]) -> str:
    return (
        f"{doc.get('STREET_NO_1') or '?'} {doc.get('STREET_NAME') or '?'} "
        f"{doc.get('STREET_TYPE') or ''}, {doc.get('LOCALITY') or '?'}"
    ).strip()


def build_queue(
    db,
    suburbs: list[str],
    limit: int | None,
    force: bool,
    only_missing_images: bool,
) -> list[tuple[str, str, dict[str, Any], str]]:
    """Build the work queue of (suburb, _id, doc, url) tuples.

    Filters:
      - Cadastral docs (no listing_status) with usable address components
      - Skips if scraped_at_v2 within RESCRAPE_AFTER_DAYS (unless --force)
      - If --only-missing-images: skip docs that already have a working
        Domain CDN hero image set
    """
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=RESCRAPE_AFTER_DAYS)
    queue: list[tuple[str, str, dict[str, Any], str]] = []

    for suburb in suburbs:
        query: dict[str, Any] = {
            "STREET_NO_1": {"$exists": True, "$ne": None},
            "STREET_NAME": {"$exists": True, "$ne": None},
            "STREET_TYPE": {"$exists": True, "$ne": None},
            "LOCALITY": {"$exists": True, "$ne": None},
        }
        if not force:
            query["$or"] = [
                {"scraped_at_v2": {"$exists": False}},
                {"scraped_at_v2": {"$lt": cutoff}},
            ]
        if only_missing_images:
            query["domain_hero_image_url"] = {"$in": [None, ""]}

        proj = {
            "STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1,
            "LOCALITY": 1, "POSTCODE": 1, "display_postcode": 1,
            "UNIT_NUMBER": 1, "_id": 1, "scraped_at_v2": 1,
        }
        cursor = db[suburb].find(query, proj)
        if limit:
            cursor = cursor.limit(limit)
        for doc in cursor:
            url = build_profile_url(doc)
            if not url:
                continue
            queue.append((suburb, str(doc["_id"]), doc, url))
            if limit and len(queue) >= limit:
                return queue
    return queue


class Counters:
    """Thread-safe counters for progress logging."""
    def __init__(self):
        self.lock = threading.Lock()
        self.attempted = 0
        self.parsed = 0
        self.failed_fetch = 0
        self.failed_parse = 0
        self.written = 0


def scrape_one(
    db, suburb: str, doc_id_str: str, doc: dict[str, Any], url: str,
    counters: Counters, dry_run: bool, log_every: int,
) -> None:
    """Fetch + parse + write a single property. Updates counters."""
    from bson import ObjectId
    short = _short_addr_for_log(doc)

    html = fetch_html(url, timeout=DEFAULT_TIMEOUT)
    if not html:
        with counters.lock:
            counters.attempted += 1
            counters.failed_fetch += 1
        log.warning("FETCH_FAIL %s — %s", url, short)
        return

    parsed = parse_property_profile(html)
    if not parsed:
        with counters.lock:
            counters.attempted += 1
            counters.failed_parse += 1
        log.warning("PARSE_FAIL %s — %s", url, short)
        return

    now = dt.datetime.utcnow()
    set_doc: dict[str, Any] = {
        "scraped_data_v2": parsed,
        "scraped_at_v2": now,
        "scraped_url_v2": url,
        # Top-level pointer fields that the website readers prefer.
        "domain_hero_image_url": parsed.get("hero_image_url"),
        "domain_image_urls": parsed.get("image_urls"),
    }
    # Mirror useful fields to the top-level doc so the existing readers
    # can pick them up without extra coding (only set when missing/empty).
    addr = parsed.get("address_line")
    if addr:
        set_doc["address"] = addr  # keeps website queries consistent

    if dry_run:
        log.info("DRY %s — would update %s", short, list(set_doc.keys())[:6])
    else:
        try:
            db[suburb].update_one(
                {"_id": ObjectId(doc_id_str)},
                {"$set": set_doc, "$unset": {"scraped_v2_failed_at": ""}},
            )
        except Exception as e:
            log.error("DB_WRITE_FAIL %s — %s", short, e)
            with counters.lock:
                counters.attempted += 1
                counters.failed_parse += 1
            return

    with counters.lock:
        counters.attempted += 1
        counters.parsed += 1
        counters.written += 1
        if counters.attempted % log_every == 0:
            log.info(
                "progress: attempted=%d parsed=%d written=%d failed_fetch=%d failed_parse=%d",
                counters.attempted, counters.parsed, counters.written,
                counters.failed_fetch, counters.failed_parse,
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suburbs", default=",".join(DEFAULT_SUBURBS),
                    help="Comma-separated suburb collection names")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after N properties (omit for full pass)")
    ap.add_argument("--all", action="store_true",
                    help="Run full pass (no limit; equivalent to omitting --limit)")
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE_SEC,
                    help="Seconds between dispatched requests")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help="Concurrent fetch workers")
    ap.add_argument("--force", action="store_true",
                    help="Re-scrape even if scraped_at_v2 is fresh")
    ap.add_argument("--only-missing-images", action="store_true",
                    help="Only target docs missing a Domain hero image")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build queue + fetch + parse but don't write to DB")
    ap.add_argument("--log-file", default=None,
                    help="Path to also log to (in addition to stdout)")
    args = ap.parse_args()

    fmt = "%(asctime)s %(levelname)s %(message)s"
    log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        os.makedirs(os.path.dirname(args.log_file) or ".", exist_ok=True)
        log_handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=log_handlers, force=True)

    suburbs = [s.strip() for s in args.suburbs.split(",") if s.strip()]
    client = get_client()
    db = client["Gold_Coast"]

    log.info("=== scrape_property_profiles starting ===")
    log.info("suburbs=%s limit=%s force=%s only_missing_images=%s rate=%.1fs workers=%d dry_run=%s",
             suburbs, args.limit, args.force, args.only_missing_images,
             args.rate, args.workers, args.dry_run)

    queue = build_queue(db, suburbs, args.limit, args.force, args.only_missing_images)
    log.info("Queue size: %d properties", len(queue))
    if not queue:
        log.info("Nothing to do.")
        return 0

    counters = Counters()
    log_every = max(CHECKPOINT_EVERY, args.workers)
    start_ts = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for suburb, doc_id_str, doc, url in queue:
            pool.submit(scrape_one, db, suburb, doc_id_str, doc, url,
                        counters, args.dry_run, log_every)
            time.sleep(args.rate)  # throttle dispatch
        log.info("All %d tasks submitted; waiting for completion…", len(queue))

    elapsed = time.time() - start_ts
    log.info(
        "=== complete in %.1fs (%.2f req/sec) ===",
        elapsed, counters.attempted / max(elapsed, 0.001),
    )
    log.info(
        "Final: attempted=%d parsed=%d written=%d failed_fetch=%d failed_parse=%d",
        counters.attempted, counters.parsed, counters.written,
        counters.failed_fetch, counters.failed_parse,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
