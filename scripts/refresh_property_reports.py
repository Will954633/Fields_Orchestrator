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
            # Street-address-only names of the 6 named comps used in the
            # valuation engine. Cross-referenced against active listings to
            # detect "one of your comps is currently for sale" moments.
            "comps": [
                "4 Mull Court",
                "3 Islay Court",
                "21 Bayford Court",
                "52 Highfield Drive",
                "8 Trinity Place",
                "14 Indooroopilly Court",
            ],
        },
        # Suburbs to monitor for competition + comp sales
        "competition_suburbs": ["merrimac", "robina", "varsity_lakes"],
        # Price band considered competing
        "competition_price_min": 1_500_000,
        "competition_price_max": 2_500_000,
        # Min bedrooms to flag as competitor
        "competition_min_bedrooms": 5,
        # Always-on market snapshot (refreshed by date when the script runs)
        "market_state": {
            "fci": 102,
            "fci_label": "Balanced-firming",
            "stock_vs_baseline_pct": -13,
            "wage_growth_qoq_pct": 1.8,
        },
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


def normalize_address(address: str) -> str:
    """Normalise for cross-referencing against the comps list.

    '21 Bayford Court, Merrimac, QLD 4226' → '21 bayford court'
    Handles 'Ct.' / 'Court', 'St' / 'Street', extra whitespace.
    """
    if not address:
        return ""
    short = address.split(",")[0].strip().lower()
    abbrev = {
        " ct": " court", " st": " street", " rd": " road", " pl": " place",
        " dr": " drive", " ave": " avenue", " cres": " crescent", " cl": " close",
    }
    short = re.sub(r"[.]", "", short)
    short = re.sub(r"\s+", " ", short)
    for k, v in abbrev.items():
        if short.endswith(k):
            short = short[: -len(k)] + v
            break
    return short


def is_named_comp(address: str, comps: list[str]) -> bool:
    if not address or not comps:
        return False
    target = normalize_address(address)
    return any(normalize_address(c) == target for c in comps)


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
    """Active listings first_seen in the last N days that compete with subject.

    Emits two kinds:
      - comp_on_market — one of the subject's named valuation comps is also
        for sale. Editorial moment.
      - new_listing — generic competing listing.
    """
    items: list[dict[str, Any]] = []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    subj_suburb = config["subject"]["suburb"].lower().replace(" ", "_")
    named_comps: list[str] = config["subject"].get("comps", [])
    n_comps = len(named_comps)

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
            full_addr = d.get("address", "")
            addr = short_address(full_addr)
            in_subj_suburb = suburb == subj_suburb
            location_phrase = "" if in_subj_suburb else f" in {suburb.replace('_', ' ').title()}"

            # Cross-reference against named comps
            if is_named_comp(full_addr, named_comps):
                items.append({
                    "date": first_seen.date().isoformat() if first_seen else None,
                    "kind": "comp_on_market",
                    "source_id": f"comp_active:{d.get('listing_url') or addr}",
                    "headline": f"One of your {n_comps} comps is currently for sale: {addr}",
                    "body": (
                        f"{describe_listing(d)} Listed{location_phrase} at {fmt_aud(price_mid)}. "
                        f"This is the same property the valuation engine used as one of its named comparables."
                    ),
                    "effect_on_your_home": (
                        "An active listing of a comp is the cleanest signal of how buyers are currently reading "
                        "homes like yours — every day this listing sits, that asking price becomes the market's "
                        "answer. Watch it: a price drop says the original ask was high; a quick sale says yours can ask the same or more."
                    ),
                    "image_src": pick_first_image(d.get("property_images")),
                    "href": d.get("listing_url"),
                })
                continue  # don't double-emit as new_listing

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
            })

    return items


def valuation_event_activity(report_doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Emit a 'recommendation signed off' item when valuation_finalised_at is set.

    Persistent: lives on the report doc itself so cron runs don't lose the event.
    The python upsert is careful to preserve `valuation_finalised_at` and
    `recommendation` fields if they're set elsewhere (e.g. consultant signoff
    workflow once lead capture is wired).
    """
    if not report_doc:
        return []
    ts = report_doc.get("valuation_finalised_at")
    if not ts:
        return []
    if isinstance(ts, dt.datetime):
        date_str = ts.date().isoformat()
    elif isinstance(ts, str):
        date_str = ts[:10]
    else:
        return []
    rec = report_doc.get("recommendation") or {}
    listing = rec.get("listing_price")
    target = rec.get("target_sale_price")
    price_phrase = ""
    if listing and target:
        price_phrase = f" Recommended listing price: ${listing:,}. Target sale price: ${target:,}."
    return [{
        "date": date_str,
        "kind": "valuation",
        "source_id": f"valuation_finalised:{date_str}",
        "headline": "Your recommendation is signed off",
        "body": (
            "Will reviewed every comparable, every adjustment, and the weighted reconciliation."
            + price_phrase
        ),
        "effect_on_your_home": (
            "See the full reasoning, the four conditions of the precise-pricing protocol, "
            "and the inspection caveat on the Valuation tab."
        ),
        "href": "#valuation",
    }]


def market_state_activity(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Always-on freshness item dated today: current suburb market snapshot.

    Provides a dated-today item at the top of every feed so sellers never
    arrive to a feed whose most recent item is months old. Refresh values
    later by querying market_metrics (v0.4).
    """
    ms = config.get("market_state")
    if not ms:
        return []

    today = dt.date.today().isoformat()
    suburb_pretty = config["subject"]["suburb"]
    fci = ms["fci"]
    fci_label = ms["fci_label"].lower()
    stock_delta = ms["stock_vs_baseline_pct"]
    wage = ms["wage_growth_qoq_pct"]

    stock_phrase = (
        f"{abs(stock_delta)}% below" if stock_delta < 0 else f"{stock_delta}% above"
    )

    return [{
        "date": today,
        "kind": "market_state",
        "source_id": f"market_state:{today}",
        "headline": f"{suburb_pretty} is {fci_label} today (FCI {fci}). Stock {stock_phrase} the 5-year baseline.",
        "body": (
            f"The Fields Conviction Index for {suburb_pretty} sits at {fci} ({fci_label}). "
            f"Active listings remain {stock_phrase} the five-year baseline. "
            f"Wage growth — the leading indicator for Gold Coast prices (Abelson et al. 2005, r=0.940) — "
            f"is running at +{wage}% QoQ."
        ),
        "effect_on_your_home": (
            "Tighter supply at the top of the bracket favours sellers. The wage growth indicator gives an "
            "early read on where prices are likely to sit 9-12 months from now."
        ),
    }]


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
    """Generate a balanced 10-item feed.

    Mix discipline: market_state (always-on, dated today) sits at the top.
    Then per-kind caps so a flood of new articles can't drown out the rarer
    but more interesting listings + sales. Articles are capped at 2 because
    they publish far more frequently than property events.

    Cold-start safety: if real estate activity in `days` is thin, widen the
    lookback to 90 days before bailing — better to show "from 60 days ago"
    than nothing.
    """
    config = REPORT_CONFIGS.get(slug)
    if not config:
        log.error("No config for slug %s", slug)
        return []

    db_gc = client["Gold_Coast"]
    db_sm = client["system_monitor"]

    # Load existing doc to pick up persistent fields (valuation_finalised_at,
    # recommendation, manual_items[])
    existing = db_sm["property_reports"].find_one({"slug": slug})

    def _generate(window_days: int) -> dict[str, list[dict[str, Any]]]:
        listings_raw = new_listings_activity(db_gc, config, window_days)
        return {
            "market_state": market_state_activity(config),
            "valuation": valuation_event_activity(existing),
            "comp_on_market": [i for i in listings_raw if i["kind"] == "comp_on_market"],
            "sold": recent_sales_activity(db_gc, config, window_days),
            "new_listing": [i for i in listings_raw if i["kind"] == "new_listing"],
            "article": new_articles_activity(db_sm, config["subject"]["suburb"], window_days),
        }

    by_kind = _generate(days)
    # Cold-start: widen lookback if the property-event side is thin
    estate_count = (
        len(by_kind["comp_on_market"]) + len(by_kind["sold"]) + len(by_kind["new_listing"])
    )
    if estate_count < 3 and days < 90:
        log.info("Only %d estate items at %dd; widening to 90 days", estate_count, days)
        by_kind = _generate(90)

    # Sort each kind desc by date
    for k in by_kind:
        by_kind[k].sort(key=lambda x: x.get("date") or "", reverse=True)

    # Priority allocation + per-kind caps (totals to <= 13 to allow some slack)
    CAPS = {
        "market_state": 1,
        "valuation": 1,
        "comp_on_market": 2,
        "sold": 3,
        "new_listing": 4,
        "article": 2,
    }
    selected: list[dict[str, Any]] = []
    for kind, cap in CAPS.items():
        selected.extend(by_kind.get(kind, [])[:cap])

    # Dedup + final sort. market_state + valuation pinned to top, then by date desc.
    seen: set[str] = set()
    final: list[dict[str, Any]] = []
    pinned = [i for i in selected if i["kind"] in ("market_state", "valuation")]
    rest = [i for i in selected if i["kind"] not in ("market_state", "valuation")]
    rest.sort(key=lambda x: x.get("date") or "", reverse=True)
    for item in pinned + rest:
        sid = item.get("source_id") or ""
        if sid in seen:
            continue
        seen.add(sid)
        final.append(item)
    return final[:10]


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
