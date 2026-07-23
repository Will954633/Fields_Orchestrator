#!/usr/bin/env python3
"""
refresh_property_timelines.py — Refresh property_timeline data from Domain property profiles.

Fetches the __NEXT_DATA__ → __APOLLO_STATE__ → Property.timeline from Domain
property profile pages and updates scraped_data.property_timeline in Gold_Coast DB.

This fills the gap left when we migrated from Selenium to curl_cffi (March 2026) —
the curl_cffi scraper extracts listing data but not property transaction history.

Usage:
    python3 scripts/refresh_property_timelines.py                     # all target suburbs
    python3 scripts/refresh_property_timelines.py --suburb robina     # single suburb
    python3 scripts/refresh_property_timelines.py --limit 50          # process max N properties
    python3 scripts/refresh_property_timelines.py --dry-run           # fetch but don't write
    python3 scripts/refresh_property_timelines.py --stale-only        # only refresh if timeline is >30 days old
    python3 scripts/refresh_property_timelines.py --sold-since-days 120  # targeted: only recently-sold properties
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from shared.domain_fetch import fetch_html

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
DOMAIN_PROFILE_BASE = "https://www.domain.com.au/property-profile"

# Domain's URL slugs spell out street types in full — an abbreviated address
# ("8 Duxton Dr") 404s / hits a thin fallback page instead of the real one
# (confirmed 2026-07-23: "-dr-" returned a 1KB stub, "-drive-" returned 74KB
# of real data for the same property). Kept in sync with the equivalent map
# in 03_For_Sale_Coverage/enrich_property_timeline.py.
STREET_ABBREVS = {
    'crt': 'court', 'ct': 'court',
    'st': 'street',
    'tce': 'terrace', 'ter': 'terrace',
    'dr': 'drive',
    'ave': 'avenue', 'av': 'avenue',
    'rd': 'road',
    'pl': 'place',
    'cres': 'crescent', 'cr': 'crescent',
    'cir': 'circuit', 'cct': 'circuit',
    'blvd': 'boulevard',
    'pde': 'parade',
    'hwy': 'highway',
    'ln': 'lane',
}
RATE_LIMIT_DELAY = 6.0  # seconds between Domain requests — 2.0s let per-request failure
                         # rate climb steadily over a run (25%->50% within one suburb,
                         # confirmed 2026-07-23), consistent with Bright Data account-level
                         # rate limiting under sustained load rather than a content bug
COSMOS_RETRY_DELAY = 5.0


def get_db():
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    return MongoClient(conn_str)


def build_profile_url(address: str) -> str | None:
    """Convert an address to a Domain property profile URL slug."""
    if not address:
        return None
    # "21 Indooroopilly Court, Robina, QLD 4226" → "21-indooroopilly-court-robina-qld-4226"
    slug = address.lower().strip()
    slug = slug.replace(",", "").replace(".", "")
    # Unit-numbered addresses ("1/18 X St") use a hyphen on Domain, not the
    # slash — without this, "1/18" and "118" collapse to the same slug and
    # resolve to a thin/wrong page (confirmed 2026-07-23: the concatenated
    # slug returned a 1KB fallback page vs 98KB of real data for the
    # correctly-hyphenated URL).
    slug = slug.replace("/", "-")
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    parts = [STREET_ABBREVS.get(p, p) for p in slug.split("-")]
    slug = "-".join(parts)
    return f"{DOMAIN_PROFILE_BASE}/{slug}"


def _fetch_timeline_once(url: str) -> list[dict] | None:
    """Single fetch+parse attempt. Raises on JSON parse failure so the caller can retry."""
    html = fetch_html(url)
    if not html:
        return None

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None

    data = json.loads(match.group(1))  # raises if the body was truncated mid-transfer
    apollo = data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})

    # Find the Property object
    prop_key = next((k for k in apollo if k.startswith("Property:")), None)
    if not prop_key:
        return None

    prop = apollo[prop_key]
    timeline_raw = prop.get("timeline", [])

    # Resolve Apollo refs and normalize
    timeline = []
    for entry in timeline_raw:
        if isinstance(entry, dict) and "__ref" in entry:
            entry = apollo.get(entry["__ref"], entry)

        event_date = entry.get("eventDate", "")
        if not event_date:
            continue

        # Parse date
        date_str = event_date[:10]  # "2022-12-08T00:00:00.000Z" → "2022-12-08"

        category = entry.get("category", "")
        sale_meta = entry.get("saleMetadata") or {}
        if isinstance(sale_meta, dict) and "__ref" in sale_meta:
            sale_meta = apollo.get(sale_meta["__ref"], sale_meta)

        is_sold = (
            category == "Sale"
            or (isinstance(sale_meta, dict) and sale_meta.get("isSold"))
        )

        agency = entry.get("agency") or {}
        if isinstance(agency, dict) and "__ref" in agency:
            agency = apollo.get(agency["__ref"], agency)

        price_desc = entry.get("priceDescription", "")

        timeline.append({
            "date": date_str,
            "month_year": datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %Y"),
            "category": category or ("Sale" if is_sold else "Unknown"),
            "type": price_desc or (
                (isinstance(sale_meta, dict) and sale_meta.get("saleType")) or "PRIVATE TREATY"
            ),
            "price": entry.get("eventPrice"),
            "days_on_market": entry.get("daysOnMarket"),
            "is_major_event": True,
            "agency_name": agency.get("name") if isinstance(agency, dict) else None,
            "agency_url": agency.get("profileUrl") if isinstance(agency, dict) else None,
            "is_sold": is_sold or None,
        })

    return timeline


def fetch_timeline(url: str, retries: int = 3) -> list[dict] | None:
    """Fetch property timeline from Domain property profile page.

    Uses shared.domain_fetch (Bright Data Web Unlocker) — raw curl_cffi
    impersonation gets served an anti-bot challenge page on property-profile
    URLs (confirmed 2026-07-22: 3/3 requests returned a 2.5KB behavioral-
    challenge stub with no __NEXT_DATA__, while the same URL through
    domain_fetch.fetch_html returned the full page immediately).

    Retries the whole fetch+parse on JSON errors — domain_fetch's own retry
    logic only catches short/empty responses (its min_size check), not a
    response that's large enough to pass that check but got truncated
    mid-transfer (confirmed 2026-07-23: a property that failed with
    "Unterminated string" during a batch run parsed cleanly on immediate
    re-fetch — Bright Data Web Unlocker is "reliable but flaky per-request"
    per its own docstring, and this failure mode slips past that check).
    """
    for attempt in range(retries):
        try:
            return _fetch_timeline_once(url)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            if attempt < retries - 1:
                time.sleep(2.0)
                continue
            print(f"      Error fetching {url}: {e}")
            return None
        except Exception as e:
            print(f"      Error fetching {url}: {e}")
            return None
    return None


def refresh_suburb(gc_db, suburb, limit=None, dry_run=False, stale_only=False, sold_since_days=None,
                    houses_only=False, skip_refreshed=False):
    """Refresh property timelines for all properties in a suburb."""
    coll = gc_db[suburb]

    # Build query — all properties that have an address
    query = {"address": {"$exists": True, "$ne": None}}

    if sold_since_days is not None:
        # Target only recently-sold properties — much smaller set than the full
        # suburb stock, for quickly unblocking quarterly median/volume calcs
        # that read scraped_data.property_timeline.
        cutoff_str = (datetime.now() - timedelta(days=sold_since_days)).strftime("%Y-%m-%d")
        query["listing_status"] = "sold"
        query["sold_date"] = {"$gte": cutoff_str}
    elif stale_only:
        # Only refresh if timeline_updated_at is missing or >30 days old
        stale_cutoff = datetime.now() - timedelta(days=30)
        query["$or"] = [
            {"timeline_updated_at": {"$exists": False}},
            {"timeline_updated_at": {"$lt": stale_cutoff}},
        ]

    if houses_only:
        # Top-level Domain property_type — good enough as a pre-filter here since
        # this only trims the fetch queue; the precompute scripts do the real
        # (and more careful) property-type filtering downstream.
        query["property_type"] = "House"

    if skip_refreshed:
        # Don't re-fetch properties this session (or a prior run) already
        # refreshed successfully — narrows to exactly what's still missing.
        query["timeline_updated_at"] = {"$exists": False}

    total = coll.count_documents(query)
    if limit:
        total = min(total, limit)

    print(f"  {suburb}: {total} properties to refresh")

    updated = 0
    skipped = 0
    failed = 0

    cursor = coll.find(query, {"address": 1, "url_slug": 1, "_id": 1}).limit(limit or 0)

    for i, doc in enumerate(cursor):
        address = doc.get("address", "")
        url = build_profile_url(address)

        if not url:
            skipped += 1
            continue

        if i > 0 and i % 20 == 0:
            print(f"    Progress: {i}/{total} ({updated} updated, {failed} failed)")

        # Fetch from Domain
        timeline = fetch_timeline(url)
        time.sleep(RATE_LIMIT_DELAY)

        if timeline is None:
            failed += 1
            continue

        if dry_run:
            sold_count = len([t for t in timeline if t.get("is_sold")])
            print(f"    [DRY] {address[:50]}: {len(timeline)} events ({sold_count} sales)")
            updated += 1
            continue

        # Write to MongoDB
        try:
            coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "scraped_data.property_timeline": timeline,
                    "timeline_updated_at": datetime.now(),
                }},
            )
            updated += 1
        except Exception as e:
            if "16500" in str(e):
                time.sleep(COSMOS_RETRY_DELAY)
                try:
                    coll.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "scraped_data.property_timeline": timeline,
                            "timeline_updated_at": datetime.now(),
                        }},
                    )
                    updated += 1
                except Exception:
                    failed += 1
            else:
                failed += 1

    print(f"  ✅ {suburb}: {updated} updated, {skipped} skipped, {failed} failed")
    return updated


def main():
    parser = argparse.ArgumentParser(description="Refresh property timelines from Domain")
    parser.add_argument("--suburb", type=str, help="Single suburb")
    parser.add_argument("--limit", type=int, help="Max properties per suburb")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stale-only", action="store_true", help="Only refresh stale (>30 days) timelines")
    parser.add_argument("--sold-since-days", type=int, help="Only refresh properties sold within N days (targeted catch-up)")
    parser.add_argument("--houses-only", action="store_true", help="Restrict to property_type=House (skip units/townhouses/duplexes)")
    parser.add_argument("--skip-refreshed", action="store_true", help="Skip anything with timeline_updated_at already set (don't re-fetch known-good ones)")
    args = parser.parse_args()

    client = get_db()
    gc_db = client["Gold_Coast"]

    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
    total_updated = 0

    for suburb in suburbs:
        updated = refresh_suburb(
            gc_db, suburb,
            limit=args.limit,
            dry_run=args.dry_run,
            stale_only=args.stale_only,
            sold_since_days=args.sold_since_days,
            houses_only=args.houses_only,
            skip_refreshed=args.skip_refreshed,
        )
        total_updated += updated
        time.sleep(5)  # Pause between suburbs

    print(f"\nDone. Total updated: {total_updated}")
    client.close()


if __name__ == "__main__":
    main()
