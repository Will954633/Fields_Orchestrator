#!/usr/bin/env python3
"""refresh_property_reports.py — populate per-seller activity feeds.

For each property report in `system_monitor.property_reports`, query
Gold_Coast (active + sold for tracked suburbs) and content_articles,
generate fresh activity items, and upsert.

v0.3: one hard-coded report (13-terrace-court-merrimac). Once lead
capture lands, reports get created on /analyse-your-home submission
and this script picks them up automatically.

Frontend: hits /.netlify/functions/property-report-activity?slug=...
Falls back to TS fixture if DB empty.

Run: python3 scripts/refresh_property_reports.py [--slug X] [--days N] [--dry-run]
"""

from __future__ import annotations
import argparse
import datetime as dt
import logging
import re
import sys
from typing import Any

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refresh_property_reports")

# ---------------------------------------------------------------------------
# Hard-coded report configs (v0.3 — moves to DB when lead capture lands)
# ---------------------------------------------------------------------------

REPORT_CONFIGS: dict[str, dict[str, Any]] = {
    "13-terrace-court-merrimac": {
        "subject": {
            "address": "13 Terrace Court",
            "suburb": "Merrimac",
            "bedrooms": 6,
            "bathrooms": 3,
            "land_area": 658,
            "internal_area": 221,
            "features": ["pool", "dual_living", "cul_de_sac", "bushland_adjacent", "north_facing_rear"],
            "condition": 9,
            "valuation_low": 1_884_000,
            "valuation_high": 2_073_000,
        },
        # Suburbs to monitor for competition + comp sales
        "competition_suburbs": ["merrimac", "robina", "varsity_lakes"],
        # Price band considered competing
        "competition_price_min": 1_500_000,
        "competition_price_max": 2_500_000,
        # Min bedrooms to flag as competitor
        "competition_min_bedrooms": 5,
    },
}

# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

PRICE_PATTERNS = [
    re.compile(r"\$([\d,]+(?:\.\d+)?)\s*(?:m|million)\b", re.I),  # $1.5m
    re.compile(r"\$([\d,]+(?:\.\d+)?)k\b", re.I),  # $950k
    re.compile(r"\$([\d,]+)"),  # $1,250,000
]


def parse_price(s: Any) -> float | None:
    """Return midpoint of price (handles ranges) or None."""
    if not s or not isinstance(s, str):
        return None
    # Strip everything after a dash to handle ranges, but average both sides
    values: list[float] = []
    parts = re.split(r"\s*[-–—]\s*", s)
    for part in parts:
        for pat in PRICE_PATTERNS:
            m = pat.search(part)
            if not m:
                continue
            raw = m.group(1).replace(",", "")
            try:
                n = float(raw)
            except ValueError:
                continue
            if "m" in part.lower()[m.end() - 1 : m.end() + 1] or "million" in part.lower():
                n *= 1_000_000
            elif "k" in part.lower()[m.end() - 1 : m.end() + 1]:
                n *= 1_000
            values.append(n)
            break
    if not values:
        return None
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def short_address(address: str) -> str:
    """'12 Bourton Road, Merrimac, QLD 4226' → '12 Bourton Road'."""
    return address.split(",")[0].strip() if address else address


def days_since(d: dt.datetime | None) -> int | None:
    if not d:
        return None
    if not isinstance(d, dt.datetime):
        return None
    now = dt.datetime.now(d.tzinfo) if d.tzinfo else dt.datetime.utcnow()
    return (now - d).days


def fmt_aud(n: float | str) -> str:
    """Format a number as $1,250,000. Accepts ints, floats, or AUD strings."""
    if isinstance(n, str):
        parsed = parse_price(n)
        if parsed is None:
            return n  # last-ditch: return the raw string
        n = parsed
    return f"${int(n):,}"


def coerce_price(v: Any) -> float | None:
    """Accept int/float/string and return a clean float, or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return parse_price(v)
    return None


# ---------------------------------------------------------------------------
# Activity generators
# ---------------------------------------------------------------------------


def new_listings_activity(
    db, config: dict[str, Any], days: int
) -> list[dict[str, Any]]:
    """Active listings first_seen in the last N days that compete with subject."""
    items: list[dict[str, Any]] = []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    subj_suburb = config["subject"]["suburb"].lower().replace(" ", "_")

    for suburb in config["competition_suburbs"]:
        col = db[suburb]
        cursor = col.find(
            {
                "listing_status": "for_sale",
                "first_seen": {"$gte": cutoff},
                "bedrooms": {"$gte": config["competition_min_bedrooms"]},
            },
            {"_id": 0, "address": 1, "price": 1, "first_seen": 1, "bedrooms": 1,
             "bathrooms": 1, "property_type": 1, "listing_url": 1, "property_images": 1},
        ).sort("first_seen", -1).limit(10)

        for d in cursor:
            price_mid = parse_price(d.get("price"))
            if price_mid is None:
                continue
            if not (config["competition_price_min"] <= price_mid <= config["competition_price_max"]):
                continue
            # Skip if property type isn't house
            if d.get("property_type") not in (None, "House", "Acreage / Semi-Rural"):
                continue

            first_seen = d.get("first_seen")
            addr = short_address(d.get("address", ""))
            in_subj_suburb = suburb == subj_suburb
            location_phrase = "" if in_subj_suburb else f" in {suburb.replace('_', ' ').title()}"
            kind_phrase = (
                "Direct competitor" if in_subj_suburb else "Cross-suburb competitor"
            )

            effect = build_listing_effect(d, price_mid, config["subject"])

            items.append({
                "date": first_seen.date().isoformat() if first_seen else None,
                "kind": "new_listing",
                "source_id": f"listing:{d.get('listing_url') or addr}",
                "headline": f"{addr}{location_phrase} just listed at {fmt_aud(price_mid)}",
                "body": describe_listing(d),
                "effect_on_your_home": effect,
                "image_src": pick_first_image(d.get("property_images")),
                "href": d.get("listing_url"),
                "_kind_phrase": kind_phrase,
            })

    return items


def build_listing_effect(listing: dict[str, Any], price_mid: float, subject: dict[str, Any]) -> str:
    bd_subj = subject["bedrooms"]
    bd = listing.get("bedrooms")
    delta = bd_subj - (bd or 0)
    if delta > 0:
        return f"Your home has {delta} more bedroom{'s' if delta > 1 else ''} than this listing. At {fmt_aud(price_mid)}, this listing helps anchor buyers in your price band."
    if price_mid < subject["valuation_low"]:
        return "Listed below your home's working valuation range — likely competing for the same buyer pool at a lower entry point."
    if price_mid > subject["valuation_high"]:
        return "Listed above your home's working valuation range. Sets an upper-bound buyer reference."
    return f"Listed inside your home's working valuation range ({fmt_aud(subject['valuation_low'])}–{fmt_aud(subject['valuation_high'])})."


def describe_listing(d: dict[str, Any]) -> str:
    bd = d.get("bedrooms") or "?"
    ba = d.get("bathrooms") or "?"
    pt = d.get("property_type") or "Property"
    return f"{pt}, {bd}-bed, {ba}-bath. Listed on Domain."


def recent_sales_activity(
    db, config: dict[str, Any], days: int
) -> list[dict[str, Any]]:
    """Sold properties in subject suburb in last N days."""
    items: list[dict[str, Any]] = []
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).date().isoformat()
    suburb = config["subject"]["suburb"].lower().replace(" ", "_")
    col = db[suburb]

    cursor = col.find(
        {
            "listing_status": "sold",
            "sale_date": {"$gte": cutoff},
            "bedrooms": {"$gte": config["competition_min_bedrooms"]},
        },
        {"_id": 0, "address": 1, "sold_price": 1, "price": 1, "sale_date": 1,
         "bedrooms": 1, "bathrooms": 1, "property_type": 1, "first_seen": 1,
         "days_on_market": 1, "listing_url": 1},
    ).sort("sale_date", -1).limit(5)

    for d in cursor:
        addr = short_address(d.get("address", ""))
        sold_price = coerce_price(d.get("sold_price")) or coerce_price(d.get("price"))
        if not sold_price:
            continue

        sale_date = d.get("sale_date", "")
        dom = d.get("days_on_market")
        dom_phrase = f"{dom} days on market" if dom else "Recently sold"

        items.append({
            "date": sale_date if isinstance(sale_date, str) else sale_date.isoformat()[:10],
            "kind": "sold",
            "source_id": f"sold:{d.get('listing_url') or addr}",
            "headline": f"{addr} sold for {fmt_aud(sold_price)}",
            "body": f"{dom_phrase}. {d.get('bedrooms') or '?'}-bed, {d.get('bathrooms') or '?'}-bath.",
            "effect_on_your_home": (
                "A direct local sale — informs your valuation when the consultant reviews comparables tonight."
                if config["competition_price_min"] <= sold_price <= config["competition_price_max"]
                else "A nearby sale, useful for broader suburb price context."
            ),
            "href": d.get("listing_url"),
        })

    return items


def new_articles_activity(db_sysmon, suburb: str, days: int) -> list[dict[str, Any]]:
    """Articles published in last N days mentioning the suburb."""
    items: list[dict[str, Any]] = []
    col = db_sysmon["content_articles"]
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
    suburb_clean = suburb.replace("_", " ")

    cursor = col.find(
        {
            "published_at": {"$gte": cutoff},
            "$or": [
                {"title": {"$regex": suburb_clean, "$options": "i"}},
                {"tags": {"$regex": suburb_clean, "$options": "i"}},
                {"html": {"$regex": suburb_clean, "$options": "i"}},
            ],
        },
        {"_id": 0, "title": 1, "slug": 1, "published_at": 1, "custom_excerpt": 1,
         "tags": 1, "feature_image": 1},
    ).sort("published_at", -1).limit(5)

    for d in cursor:
        published = d.get("published_at", "")
        items.append({
            "date": published[:10],
            "kind": "article",
            "source_id": f"article:{d.get('slug')}",
            "headline": d.get("title", ""),
            "body": d.get("custom_excerpt") or "New analysis published on fieldsestate.com.au.",
            "effect_on_your_home": f"Fresh editorial about {suburb_clean.title()} — adds context buyers will see when they research your suburb.",
            "image_src": d.get("feature_image"),
            "href": f"/articles/{d.get('slug')}",
        })

    return items


def pick_first_image(images: Any) -> str | None:
    if isinstance(images, list) and images:
        return images[0] if isinstance(images[0], str) else None
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_activity_for_slug(slug: str, days: int, client) -> list[dict[str, Any]]:
    config = REPORT_CONFIGS.get(slug)
    if not config:
        log.error("No config for slug %s", slug)
        return []

    db_gc = client["Gold_Coast"]
    db_sm = client["system_monitor"]

    items: list[dict[str, Any]] = []
    items.extend(new_listings_activity(db_gc, config, days))
    items.extend(recent_sales_activity(db_gc, config, days))
    items.extend(new_articles_activity(db_sm, config["subject"]["suburb"], days))

    # Sort desc by date, dedup by source_id, cap at 10
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda x: x.get("date") or "", reverse=True):
        sid = item.get("source_id") or ""
        if sid in seen:
            continue
        seen.add(sid)
        unique.append(item)
    return unique[:10]


def upsert_report(client, slug: str, activity: list[dict[str, Any]]) -> None:
    col = client["system_monitor"]["property_reports"]
    now = dt.datetime.utcnow()
    col.update_one(
        {"slug": slug},
        {
            "$set": {
                "slug": slug,
                "activity": activity,
                "activity_refreshed_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    log.info("Upserted %d activity items for %s", len(activity), slug)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=None, help="Refresh only this slug")
    ap.add_argument("--days", type=int, default=30, help="Lookback window (days)")
    ap.add_argument("--dry-run", action="store_true", help="Print, do not write")
    args = ap.parse_args()

    slugs = [args.slug] if args.slug else list(REPORT_CONFIGS.keys())
    client = get_client()

    for slug in slugs:
        log.info("=== %s ===", slug)
        activity = build_activity_for_slug(slug, args.days, client)
        log.info("Built %d activity items", len(activity))
        for item in activity:
            log.info("  [%s] %s — %s", item.get("kind"), item.get("date"), item.get("headline"))
        if args.dry_run:
            log.info("DRY RUN — skipping write")
        else:
            upsert_report(client, slug, activity)

    return 0


if __name__ == "__main__":
    sys.exit(main())
