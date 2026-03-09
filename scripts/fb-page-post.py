#!/usr/bin/env python3
"""
Post data-led content to the Fields Real Estate Facebook page.

Two categories of templates:
  AGGREGATE — suburb-level stats (existing: suburb_snapshot, price_comparison, etc.)
  PROPERTY  — individual property posts (new: open_home_spotlight, entry_price_watch, etc.)

Usage:
    python3 scripts/fb-page-post.py --generate                          # Random aggregate template
    python3 scripts/fb-page-post.py --generate --template weekend_preview  # Specific template
    python3 scripts/fb-page-post.py --generate --template entry_price_watch --post  # Generate + publish
    python3 scripts/fb-page-post.py --message "text" --post             # Custom message
    python3 scripts/fb-page-post.py --message "text" --image /tmp/card.png --post  # Photo post
"""

import os
import sys
import re
import random
import argparse
import time
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ADS_TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
CORE_SUBURBS = TARGET_SUBURBS
SUBURB_DISPLAY = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}

# Use classified_property_type (from GPT vision) when available, fall back to Domain's property_type
HOUSE_FILTER = {
    "listing_status": "for_sale",
    "$or": [
        {"classified_property_type": "House"},
        {"classified_property_type": {"$exists": False}, "property_type": "House"},
    ],
}
SOLD_HOUSE_FILTER = {
    "listing_status": "sold",
    "$or": [
        {"classified_property_type": "House"},
        {"classified_property_type": {"$exists": False}, "property_type": "House"},
    ],
}


# ── Facebook API ─────────────────────────────────────────────────────────

def get_page_token():
    r = requests.get(f"{BASE}/{PAGE_ID}", params={
        "fields": "access_token",
        "access_token": ADS_TOKEN,
    }, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def post_to_page(message, link=None):
    """Post to the Facebook page. Returns post_id."""
    page_token = get_page_token()
    payload = {"message": message, "access_token": page_token}
    if link:
        payload["link"] = link
    r = requests.post(f"{BASE}/{PAGE_ID}/feed", data=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("id")


def post_photo_to_page(image_path, message):
    """Post a photo with caption to the Facebook page. Returns post_id."""
    page_token = get_page_token()
    with open(image_path, "rb") as img_file:
        r = requests.post(
            f"{BASE}/{PAGE_ID}/photos",
            data={"message": message, "access_token": page_token},
            files={"source": img_file},
            timeout=30,
        )
    r.raise_for_status()
    data = r.json()
    return data.get("post_id") or data.get("id")


def log_post(post_id, message, link, template_type, content_type="text"):
    """Log the post to MongoDB for tracking."""
    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]
    db["fb_page_posts"].insert_one({
        "post_id": post_id,
        "message": message[:200],
        "link": link,
        "template_type": template_type,
        "content_type": content_type,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "source": "fb-page-post.py",
        "finalized": False,
    })
    client.close()


# ── Helpers ──────────────────────────────────────────────────────────────

def fmt_price(p):
    """Format price as full dollar amount per editorial voice ($1,250,000 not $1.25m)."""
    if p is None:
        return "N/A"
    return f"${p:,.0f}"


def clean_property_type(ptype):
    """Normalize property type for display. 'Apartment / Unit / Flat' → 'unit'."""
    if not ptype:
        return "property"
    pt = ptype.lower().strip()
    if "apartment" in pt or "unit" in pt or "flat" in pt:
        return "unit"
    if "new apartments" in pt or "off the plan" in pt:
        return "off-the-plan unit"
    if "semi-detached" in pt:
        return "semi"
    if "retirement" in pt:
        return "retirement listing"
    if "acreage" in pt or "semi-rural" in pt:
        return "acreage"
    if "new house" in pt and "land" in pt:
        return "house & land package"
    if "vacant" in pt and "land" in pt:
        return "land"
    if pt == "duplex":
        return "duplex"
    return pt


def clean_price_display(price_str):
    """Clean up messy listing price text for display."""
    if not isinstance(price_str, str):
        return "Contact agent"
    p = price_str.strip()
    # Skip obviously non-price text (no dollar sign at all)
    skip_words = ["CANCELLED", "JUST LISTED", "CREEKSIDE", "FAMILY HOME"]
    if any(w in p.upper() for w in skip_words) and '$' not in p:
        return "Contact agent"
    # Strip "FOR SALE" / "FOR SALE -" prefix
    p = re.sub(r'(?i)^for\s+sale\s*[-–—]?\s*', '', p)
    # Strip property type suffixes that leak into price text
    p = re.sub(r'\s*[-–—]\s*(?:Retirement|House|Unit|Townhouse|Duplex)\s*$', '', p, flags=re.IGNORECASE)
    # Normalize whitespace around $
    p = re.sub(r'\$\s+', '$', p)
    # Shorten "Offers Over" / "Offers above" to just the price or short prefix
    p = re.sub(r'(?i)offers?\s+over\s+', '', p)
    p = re.sub(r'(?i)offers?\s+above\s+', '', p)
    p = re.sub(r'(?i)offers?\s+from\s+', 'From ', p)
    p = re.sub(r'(?i)offers?\s+(\$)', r'\1', p)
    p = re.sub(r'(?i)price\s+guide\s*-?\s*', '', p)
    p = re.sub(r'(?i)PRICE GUIDE\s*', '', p)
    p = re.sub(r'(?i)expressions?\s+of\s+interest.*', 'EOI', p)
    p = re.sub(r'(?i)present\s+all\s+offers.*', 'EOI', p)
    p = re.sub(r'(?i)best\s+offers?\s+by.*', 'EOI', p)
    p = re.sub(r'(?i)EOI\s+ending.*', 'EOI', p)
    p = re.sub(r'(?i)submit\s+all\s+offers.*', 'EOI', p)
    p = re.sub(r'(?i)by\s+negotiation', 'By negotiation', p)
    p = re.sub(r'(?i)for\s+sale\s*$', 'Contact agent', p)
    # Strip trailing "for" / "from" fragments
    p = re.sub(r'\s+(?:for|from)\s*$', '', p, flags=re.IGNORECASE)
    p = re.sub(r'(?i)open\s+to\s+offers?\s*', '', p)
    # Normalize "$975 000" → "$975,000" (space instead of comma)
    p = re.sub(r'\$(\d{1,3})\s(\d{3})\b', lambda m: f"${m.group(1)},{m.group(2)}", p)
    # Strip trailing "considered" / "negotiable" etc.
    p = re.sub(r'\s+(?:considered|neg|negotiable)\s*$', '', p, flags=re.IGNORECASE)
    # Normalize $1.5m / $1.45m+ / "$1.5m plus" → $1,500,000
    def _expand_m(match):
        val = float(match.group(1)) * 1_000_000
        return fmt_price(int(val))
    p = re.sub(r'\$([\d.]+)\s*[mM]\b\+?', _expand_m, p)
    # Clean trailing plus/EOI/above fragments
    p = re.sub(r'\s*/?\s*EOI\s*$', '', p)
    p = re.sub(r'\s+plus\s*$', '+', p, flags=re.IGNORECASE)
    p = re.sub(r'\s*Above\s*$', '', p)
    # Strip trailing .00 from prices like $2,259,000.00
    p = re.sub(r'(\$[\d,]+)\.00\b', r'\1', p)
    # Fix truncated prices like $1,099,00 (missing digit) → $1,099,000
    p = re.sub(r'(\$[\d,]+),(\d{2})\b(?!\d)', lambda m: m.group(1) + ',' + m.group(2) + '0', p)
    p = p.strip().rstrip('+').strip()
    if not p or p.lower() == "contact agent" or p.lower() == "auction":
        return p.title() if p else "Contact agent"
    return p


def plural(n, singular, plural_form=None):
    """Return singular or plural form based on count."""
    if n == 1:
        return f"{n} {singular}"
    if plural_form:
        return f"{n} {plural_form}"
    # Smart pluralization
    if singular.endswith('x') or singular.endswith('s') or singular.endswith('sh') or singular.endswith('ch'):
        return f"{n} {singular}es"
    if singular.endswith('y') and singular[-2] not in 'aeiou':
        return f"{n} {singular[:-1]}ies"
    return f"{n} {singular}s"


def pluralize_type(type_name):
    """Pluralize a property type name. 'duplex'→'Duplexes', 'unit'→'Units'."""
    t = type_name.lower()
    # Compound types — title-case all words, pluralize the last
    if ' ' in t:
        words = type_name.split(' ')
        last_plural = pluralize_type(words[-1])
        titled = [w.title() if w.lower() not in ('&', 'the') else w for w in words[:-1]]
        titled.append(last_plural)
        return ' '.join(titled)
    if t in ('land', 'acreage'):
        return type_name.title()  # Uncountable
    if t.endswith('x') or t.endswith('s') or t.endswith('sh') or t.endswith('ch'):
        return type_name.title() + 'es'
    if t.endswith('y') and len(t) > 1 and t[-2] not in 'aeiou':
        return type_name[:-1].title() + 'ies'
    return type_name.title() + 's'


def parse_price_value(price_str):
    """Extract numeric price from string like '$1,365,000' or 'Offers above $845,000'."""
    if not isinstance(price_str, str):
        return None
    # Handle $X.Xm format
    m_match = re.search(r'\$([\d.]+)\s*[mM]', price_str)
    if m_match:
        try:
            val = int(float(m_match.group(1)) * 1_000_000)
            if 100000 < val < 20000000:
                return val
        except (ValueError, TypeError):
            pass
    match = re.search(r'\$[\d,]+(?:\.\d+)?', price_str)
    if match:
        num_str = match.group().replace("$", "").replace(",", "")
        try:
            val = int(float(num_str))
            if 100000 < val < 20000000:
                return val
        except (ValueError, TypeError):
            pass
    return None


def parse_inspection_details(inspection_str):
    """Parse inspection string into structured data.
    Input: 'Thursday, 05 Mar 1:00pm - 1:30pm'
    Returns: {'day': 'Thursday', 'date_str': '05 Mar', 'start': '1:00pm', 'end': '1:30pm', 'full': '...'}
    """
    result = {"full": inspection_str}
    day_match = re.match(r'^(\w+),', inspection_str)
    result["day"] = day_match.group(1) if day_match else None
    date_match = re.search(r'(\d{1,2}\s+\w{3})', inspection_str)
    result["date_str"] = date_match.group(1) if date_match else None
    times = re.findall(r'(\d{1,2}:\d{2}(?:am|pm))', inspection_str)
    result["start"] = times[0] if times else None
    result["end"] = times[1] if len(times) > 1 else None
    return result


def time_sort_key(time_str):
    """Convert '9:30am' to minutes for proper sorting."""
    if not time_str:
        return 9999
    m = re.match(r'(\d{1,2}):(\d{2})(am|pm)', time_str.lower())
    if not m:
        return 9999
    h, mi, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
    if ampm == "pm" and h != 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    return h * 60 + mi


def is_cancelled(prop):
    """Check if an inspection/listing is cancelled."""
    price = (prop.get("price") or "").upper()
    inspections = prop.get("inspection_times") or []
    for insp in inspections:
        if "CANCELLED" in insp.upper():
            return True
    return "CANCELLED" in price


def get_properties_for_day(properties, target_day):
    """Filter properties that have inspections on a specific day (e.g. 'Saturday').
    Excludes cancelled inspections."""
    result = []
    for prop in properties:
        if is_cancelled(prop):
            continue
        inspections = prop.get("inspection_times") or []
        matching = []
        for insp in inspections:
            if "CANCELLED" in insp.upper():
                continue
            details = parse_inspection_details(insp)
            if details["day"] and details["day"].lower() == target_day.lower():
                matching.append(details)
        if matching:
            result.append({**prop, "_inspections": matching})
    return result


def get_aest_now():
    """Get current time in AEST (UTC+10)."""
    return datetime.now(timezone.utc) + timedelta(hours=10)


def query_with_retry(collection, filter_doc, projection, max_retries=5):
    """Query CosmosDB with retry on 429 rate limit errors."""
    for attempt in range(max_retries):
        try:
            return list(collection.find(filter_doc, projection))
        except OperationFailure as e:
            if e.code == 16500 and attempt < max_retries - 1:
                wait = (attempt + 1) * 1.0
                time.sleep(wait)
                continue
            raise


def normalise_address(prop):
    """Return a clean street address — no suburb/state/postcode, title-cased."""
    addr = prop.get("street_address") or prop.get("address") or ""
    # Strip trailing ", Suburb, QLD 4226" style suffixes
    addr = re.sub(r',\s*(?:Robina|Burleigh Waters|Varsity Lakes)\b.*$', '', addr, flags=re.IGNORECASE)
    # Strip standalone QLD / postcode fragments
    addr = re.sub(r',?\s*QLD\s*\d{4}\s*$', '', addr, flags=re.IGNORECASE)
    # Title-case if ALL CAPS
    if addr == addr.upper() and len(addr) > 3:
        addr = addr.title()
    return addr.strip()


# ── Data collection ──────────────────────────────────────────────────────

def get_suburb_data():
    """Pull aggregate listing data per suburb — houses only, with market intelligence."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast"]

    suburbs = {}
    for suburb in TARGET_SUBURBS:
        listings = query_with_retry(db[suburb], HOUSE_FILTER, {
            "price": 1, "bedrooms": 1, "bathrooms": 1,
            "property_type": 1, "address": 1, "suburb": 1,
            "days_on_domain": 1,
            "valuation_data.summary.positioning": 1,
            "valuation_data.summary.insufficient_data": 1,
            "valuation_data.confidence.reconciled_valuation": 1,
        })
        if not listings:
            continue

        prices = []
        days_list = []
        underpriced_count = 0
        overpriced_count = 0
        for l in listings:
            val = parse_price_value(l.get("price", ""))
            if val:
                prices.append(val)
            dom = l.get("days_on_domain")
            if isinstance(dom, (int, float)):
                days_list.append(dom)
            vd = l.get("valuation_data", {}) or {}
            pos = (vd.get("summary") or {}).get("positioning")
            insuf = (vd.get("summary") or {}).get("insufficient_data", True)
            if not insuf:
                if pos in ("underpriced", "good_value"):
                    underpriced_count += 1
                elif pos == "overpriced":
                    overpriced_count += 1

        beds = {}
        for l in listings:
            b = l.get("bedrooms")
            if b:
                beds[str(b)] = beds.get(str(b), 0) + 1

        days_list.sort()
        suburbs[suburb] = {
            "display_name": SUBURB_DISPLAY.get(suburb, suburb.replace("_", " ").title()),
            "total": len(listings),
            "priced_count": len(prices),
            "prices": sorted(prices),
            "median_price": sorted(prices)[len(prices) // 2] if prices else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "beds": beds,
            # Market intelligence
            "median_dom": days_list[len(days_list) // 2] if days_list else None,
            "avg_dom": round(sum(days_list) / len(days_list)) if days_list else None,
            "new_this_week": len([d for d in days_list if d <= 7]),
            "stale_listings": len([d for d in days_list if d >= 60]),
            "underpriced_count": underpriced_count,
            "overpriced_count": overpriced_count,
        }

    client.close()
    return suburbs


def get_individual_properties():
    """Pull individual house listings from target suburbs with full intelligence data."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast"]

    properties = []
    for suburb in CORE_SUBURBS:
        listings = query_with_retry(db[suburb], HOUSE_FILTER, {
            "address": 1, "street_address": 1, "suburb": 1,
            "price": 1, "property_type": 1, "bedrooms": 1,
            "bathrooms": 1, "carspaces": 1, "inspection_times": 1,
            "listing_url": 1, "days_on_domain": 1,
            "first_listed_full": 1, "first_seen": 1,
            "first_listed_timestamp": 1,
            # Valuation intelligence
            "valuation_data.confidence.reconciled_valuation": 1,
            "valuation_data.confidence.confidence": 1,
            "valuation_data.confidence.range": 1,
            "valuation_data.summary.value_gap_pct": 1,
            "valuation_data.summary.positioning": 1,
            "valuation_data.summary.insufficient_data": 1,
            # Domain's own valuation
            "domain_valuation_at_listing.mid": 1,
            "domain_valuation_at_listing.low": 1,
            "domain_valuation_at_listing.high": 1,
            # Property condition (GPT photo assessment) — full PVD for Value Drivers data
            "property_valuation_data.condition_summary": 1,
            "property_valuation_data.kitchen.condition_score": 1,
            "property_valuation_data.kitchen.benchtop_material": 1,
            "property_valuation_data.kitchen.island_bench": 1,
            "property_valuation_data.bathrooms": 1,
            "property_valuation_data.exterior.condition_score": 1,
            "property_valuation_data.outdoor.outdoor_entertainment_score": 1,
            "property_valuation_data.layout.study_present": 1,
            "property_valuation_data.property_overview": 1,
            # Room dimensions + percentiles
            "parsed_rooms": 1,
            # Georeference / location intelligence
            "georeference_data.summary_stats": 1,
            "georeference_data.distances": 1,
            # Enriched data
            "enriched_data.floor_area_sqm": 1,
            "enriched_data.lot_size_sqm": 1,
            "enriched_data.capital_gain": 1,
            "lot_size_sqm": 1,
            # Rarity insights
            "property_insights": 1,
            # Features list
            "features": 1,
            # History
            "history": 1,
        })
        for l in listings:
            l["_suburb_key"] = suburb
            l["_suburb_display"] = SUBURB_DISPLAY.get(suburb, suburb.replace("_", " ").title())
        properties.extend(listings)
        time.sleep(0.5)  # Cosmos 429 rate limit spacing

    client.close()
    return properties


def get_suburb_dom_stats(properties):
    """Calculate days-on-market stats per suburb from property data."""
    stats = {}
    for suburb in TARGET_SUBURBS:
        days_list = [
            p["days_on_domain"] for p in properties
            if p.get("_suburb_key") == suburb
            and isinstance(p.get("days_on_domain"), (int, float))
        ]
        if days_list:
            days_list.sort()
            stats[suburb] = {
                "median_dom": days_list[len(days_list) // 2],
                "avg_dom": round(sum(days_list) / len(days_list)),
                "min_dom": min(days_list),
                "max_dom": max(days_list),
                "count": len(days_list),
            }
    return stats


def property_intel(prop, suburbs=None, all_properties=None):
    """Generate actionable intelligence bullets for a single property.

    Uses Value Drivers data: room dimensions, condition scores, location,
    valuation gap, days on market, lot/floor percentiles, capital gain.

    Returns a list of (priority, text) tuples sorted by impact.
    Priority: 1=urgent/actionable, 2=high-value context, 3=useful background.
    """
    insights = []
    price_val = parse_price_value(prop.get("price", ""))
    suburb = prop.get("_suburb_display", "")
    suburb_key = prop.get("_suburb_key", "")
    days = prop.get("days_on_domain")
    bed = prop.get("bedrooms")
    bath = prop.get("bathrooms")

    # ── Valuation gap (highest impact — is this property priced well?) ──
    vd = prop.get("valuation_data", {}) or {}
    summary = vd.get("summary", {}) or {}
    conf = vd.get("confidence", {}) or {}
    reconciled = conf.get("reconciled_valuation")
    positioning = summary.get("positioning")
    insufficient = summary.get("insufficient_data", True)

    if reconciled and price_val and not insufficient:
        gap_pct = (price_val - reconciled) / reconciled * 100
        val_range = conf.get("range", {}) or {}
        if gap_pct < -10:
            insights.append((1, f"Listed {abs(gap_pct):.0f}% below our valuation of {fmt_price(int(reconciled))}. Worth a closer look."))
        elif gap_pct < -3:
            insights.append((2, f"Asking price sits below our {fmt_price(int(reconciled))} valuation — could be a negotiation opportunity."))
        elif gap_pct > 20:
            insights.append((2, f"Priced {gap_pct:.0f}% above our {fmt_price(int(reconciled))} valuation. Expect room to negotiate."))
        elif gap_pct > 10:
            insights.append((3, f"Listed above our valuation of {fmt_price(int(reconciled))} — typical in this suburb."))
        elif val_range:
            low_r = val_range.get("low")
            high_r = val_range.get("high")
            if low_r and high_r and price_val:
                if low_r <= price_val <= high_r:
                    insights.append((2, f"Priced within our valuation range ({fmt_price(int(low_r))} – {fmt_price(int(high_r))}). Fair asking."))

    # ── Days on market (urgency signal) ──
    if isinstance(days, (int, float)):
        suburb_median_dom = None
        if all_properties:
            suburb_days = [
                p["days_on_domain"] for p in all_properties
                if p.get("_suburb_key") == suburb_key
                and isinstance(p.get("days_on_domain"), (int, float))
            ]
            if suburb_days:
                suburb_days.sort()
                suburb_median_dom = suburb_days[len(suburb_days) // 2]

        if days <= 3:
            insights.append((1, f"Brand new listing — {days} days on market. Be early if this ticks your boxes."))
        elif days <= 7:
            insights.append((2, f"Fresh to market ({days} days). Still in the first-inspection window."))
        elif days >= 90 and suburb_median_dom and days > suburb_median_dom * 2:
            insights.append((1, f"On the market {days} days ({suburb} median is {suburb_median_dom}). Vendor may be open to offers below asking."))
        elif days >= 60:
            insights.append((2, f"{days} days on market — been around a while. The price may need to come to buyers."))
        elif days >= 45:
            insights.append((3, f"{days} days on market. Getting past the fresh-listing phase."))

    # ── Room dimensions from parsed_rooms (Value Drivers data) ──
    rooms = prop.get("parsed_rooms", {}) or {}
    pvd = prop.get("property_valuation_data", {}) or {}
    cs = pvd.get("condition_summary", {}) or {}

    # Standout rooms (large for the suburb)
    standout_rooms = []
    compact_rooms = []
    for room_key, room_data in rooms.items():
        if not isinstance(room_data, dict):
            continue
        area = room_data.get("area")
        pctl = room_data.get("percentile")
        if area and pctl is not None:
            room_label = room_key.replace("_", " ").title()
            if pctl >= 85:
                standout_rooms.append((room_label, area, pctl))
            elif pctl <= 15:
                compact_rooms.append((room_label, area, pctl))

    if standout_rooms:
        standout_rooms.sort(key=lambda x: -x[2])
        best = standout_rooms[0]
        if len(standout_rooms) >= 2:
            second = standout_rooms[1]
            insights.append((2, f"Standout rooms: {best[0]} ({best[1]:.0f}m², top {100-best[2]}%) and {second[0]} ({second[1]:.0f}m², top {100-second[2]}%) are larger than most in {suburb}."))
        else:
            insights.append((2, f"{best[0]} is {best[1]:.0f}m² — larger than {best[2]}% of {suburb} listings."))

    if compact_rooms and not standout_rooms:
        compact_rooms.sort(key=lambda x: x[2])
        worst = compact_rooms[0]
        insights.append((3, f"Trade-off: {worst[0]} is {worst[1]:.0f}m² ({worst[2]}th percentile) — compact for {suburb}."))

    # ── Condition assessment (from GPT photo analysis) ──
    overall_score = cs.get("overall_score")
    kitchen_cond = (pvd.get("kitchen") or {}).get("condition_score")
    kitchen_bench = (pvd.get("kitchen") or {}).get("benchtop_material")
    kitchen_island = (pvd.get("kitchen") or {}).get("island_bench")
    outdoor_score = (pvd.get("outdoor") or {}).get("outdoor_entertainment_score")

    if overall_score and overall_score >= 8:
        extras = []
        if kitchen_bench and kitchen_bench.lower() in ("stone", "marble", "granite", "quartz", "engineered stone"):
            extras.append(f"stone kitchen")
        if kitchen_island:
            extras.append("island bench")
        if outdoor_score and outdoor_score >= 8:
            extras.append("great outdoor entertaining")
        cond_note = f"Condition: {overall_score}/10"
        if extras:
            cond_note += f" — {', '.join(extras)}"
        cond_note += ". Move-in ready."
        insights.append((2, cond_note))
    elif overall_score and overall_score <= 5:
        insights.append((2, f"Condition: {overall_score}/10 — could need renovation. Factor $20K-80K into your budget."))
    elif kitchen_cond and kitchen_cond >= 9:
        extras = []
        if kitchen_bench and kitchen_bench.lower() in ("stone", "marble", "granite", "quartz", "engineered stone"):
            extras.append(kitchen_bench.lower())
        if kitchen_island:
            extras.append("island bench")
        detail = f" ({', '.join(extras)})" if extras else ""
        insights.append((3, f"Kitchen rated {kitchen_cond}/10{detail} — standout feature."))

    # ── Location intelligence (from georeference_data) ──
    geo = prop.get("georeference_data", {}) or {}
    geo_stats = geo.get("summary_stats", {}) or {}
    geo_dists = geo.get("distances", {}) or {}

    closest_school = geo_stats.get("closest_primary_school_km")
    closest_beach = geo_stats.get("closest_beach_km")
    amenities_1km = geo_stats.get("total_amenities_within_1km")

    if closest_school and closest_school < 0.8:
        school_name = None
        primary = geo_dists.get("primary_schools") or geo_dists.get("schools") or []
        if primary and isinstance(primary, list) and len(primary) > 0:
            school_name = primary[0].get("name")
        if school_name:
            insights.append((2, f"Walking distance to {school_name} ({closest_school*1000:.0f}m)."))
        else:
            insights.append((2, f"Primary school within walking distance ({closest_school*1000:.0f}m)."))

    if closest_beach and closest_beach < 2:
        insights.append((3, f"Beach {closest_beach:.1f}km away."))

    if amenities_1km and amenities_1km >= 10:
        insights.append((3, f"High walkability — {amenities_1km} amenities within 1km."))

    # ── Lot size comparison ──
    pi = prop.get("property_insights", {}) or {}
    lot = prop.get("lot_size_sqm") or (prop.get("enriched_data") or {}).get("lot_size_sqm")
    lot_pi = pi.get("lot_size", {})
    lot_pctl = (lot_pi.get("suburbComparison") or {}).get("percentile")
    if lot and lot_pctl:
        if lot_pctl >= 90:
            insights.append((2, f"{lot:.0f}sqm lot — larger than {lot_pctl}% of houses in {suburb}. Hard to find this size."))
        elif lot_pctl <= 20 and lot < 400:
            insights.append((3, f"Compact {lot:.0f}sqm lot — smaller side for {suburb}."))

    # ── Floor area ──
    floor = (prop.get("enriched_data") or {}).get("floor_area_sqm")
    floor_pi = pi.get("floor_area", {})
    floor_pctl = (floor_pi.get("suburbComparison") or {}).get("percentile")
    if floor and floor_pctl and floor_pctl >= 85:
        insights.append((2, f"{floor:.0f}sqm of living space — top {100-floor_pctl}% for {suburb}."))

    # ── Bedroom rarity ──
    bed_pi = pi.get("bedrooms", {})
    bed_pctl = (bed_pi.get("suburbComparison") or {}).get("percentile")
    if bed and bed_pctl and bed_pctl >= 90:
        insights.append((2, f"{bed}-bed houses are rare in {suburb} — only {100-bed_pctl}% of current listings."))

    # ── Price per sqm (land) ──
    if lot and price_val and lot > 100:
        ppsqm = price_val / lot
        insights.append((3, f"{fmt_price(int(ppsqm))}/sqm of land."))

    # ── Capital gain history ──
    cg = (prop.get("enriched_data") or {}).get("capital_gain", {}) or {}
    if cg.get("has_data"):
        oldest_price = cg.get("oldest_transaction_price")
        oldest_year = str(cg.get("oldest_transaction_date", ""))[:4]
        years = cg.get("years_held")
        if oldest_price and oldest_year and years and price_val:
            gain_pct = (price_val - oldest_price) / oldest_price * 100
            if gain_pct > 50 and years > 5:
                insights.append((3, f"Last sold in {oldest_year} for {fmt_price(int(oldest_price))}. Asking {gain_pct:.0f}% more after {years:.0f} years."))

    # Sort by priority (1 = most actionable)
    insights.sort(key=lambda x: x[0])
    return insights


def get_recently_sold_properties():
    """Pull recently sold houses from target suburbs with valuation data."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast"]

    sold = []
    for suburb in CORE_SUBURBS:
        try:
            listings = query_with_retry(db[suburb], SOLD_HOUSE_FILTER, {
                "address": 1, "street_address": 1, "suburb": 1,
                "price": 1, "sale_price": 1, "listing_price": 1,
                "sold_date": 1, "sold_date_text": 1,
                "property_type": 1, "bedrooms": 1, "bathrooms": 1,
                "carspaces": 1, "days_on_market": 1, "days_on_domain": 1,
                "moved_to_sold_date": 1, "listing_url": 1,
                "enriched_data.lot_size_sqm": 1,
                "enriched_data.floor_area_sqm": 1,
                "enriched_data.transactions": 1,
                "floor_plan_analysis.internal_floor_area": 1,
                "valuation_data.confidence": 1,
                "valuation_data.confidence.reconciled_valuation": 1,
                "valuation_data.subject_property.predicted_value": 1,
                "property_insights": 1,
                "lot_size_sqm": 1,
                # Domain valuation accuracy (computed at sale time)
                "domain_valuation_accuracy": 1,
            })
            for l in listings:
                l["_suburb_key"] = suburb
                l["_suburb_display"] = SUBURB_DISPLAY.get(suburb, suburb.replace("_", " ").title())
            sold.extend(listings)
        except Exception:
            continue

    client.close()
    return sold


# ── AGGREGATE TEMPLATES (suburb-level stats) ─────────────────────────────

def template_suburb_snapshot(suburbs, **kw):
    """Single suburb market snapshot — with real market intelligence."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 5]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    # Bedroom breakdown
    bed_lines = []
    for bed_count in sorted(s["beds"].keys(), key=lambda x: int(x)):
        count = s["beds"][bed_count]
        bed_lines.append(f"  {bed_count}-bed: {count}")
    bed_section = "\n".join(bed_lines) if bed_lines else ""

    msg = f"""{name} right now — {s['total']} houses for sale

{fmt_price(s['min_price'])} to {fmt_price(s['max_price'])}
Median asking: {fmt_price(s['median_price'])}

{bed_section}"""

    # Market speed
    if s.get("median_dom"):
        msg += f"\n\nMedian time on market: {s['median_dom']} days."
        if s.get("new_this_week"):
            msg += f" {s['new_this_week']} listed in the last 7 days."
        if s.get("stale_listings"):
            msg += f" {s['stale_listings']} have been on for 60+ days."

    # Valuation positioning
    if s.get("underpriced_count") or s.get("overpriced_count"):
        total_valued = s["underpriced_count"] + s["overpriced_count"]
        if s["underpriced_count"] > 0:
            msg += f"\n\nOur valuation analysis flags {s['underpriced_count']} of {total_valued} valued houses as below estimated market value."

    msg += f"""

For buyers: {s['total']} houses means {"strong choice" if s['total'] >= 20 else "limited options" if s['total'] <= 10 else "moderate competition"}. For sellers: {"plenty of competition" if s['total'] >= 20 else "you have scarcity on your side" if s['total'] <= 10 else "typical stock levels"}.

fieldsestate.com.au/for-sale — every house with an independent valuation."""
    return msg, "suburb_snapshot"


def template_price_comparison(suburbs, **kw):
    """What does $X buy across suburbs — with valuation context and what you actually get."""
    price_point = random.choice([1000000, 1300000, 1500000, 1800000, 2200000])
    properties = get_individual_properties()

    results = []
    for key, s in suburbs.items():
        if not s["prices"]:
            continue
        lower = price_point * 0.85
        upper = price_point * 1.15
        matches = [p for p in s["prices"] if lower <= p <= upper]
        if matches:
            # Find properties in this bracket with intel
            suburb_props = [p for p in properties if p.get("_suburb_key") == key]
            bracket_props = []
            for p in suburb_props:
                pv = parse_price_value(p.get("price", ""))
                if pv and lower <= pv <= upper:
                    bracket_props.append(p)

            # Count underpriced in this bracket
            underpriced = 0
            for p in bracket_props:
                vd = p.get("valuation_data", {}) or {}
                pos = (vd.get("summary") or {}).get("positioning")
                insuf = (vd.get("summary") or {}).get("insufficient_data", True)
                if not insuf and pos in ("underpriced", "good_value"):
                    underpriced += 1

            # Average lot size in bracket
            lots = [p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm") for p in bracket_props]
            lots = [l for l in lots if l and l > 50]
            avg_lot = round(sum(lots) / len(lots)) if lots else None

            results.append({
                "name": s["display_name"],
                "count": len(matches),
                "total": s["total"],
                "underpriced": underpriced,
                "avg_lot": avg_lot,
                "median_dom": s.get("median_dom"),
            })

    if len(results) < 2:
        return None, None

    results.sort(key=lambda x: -x["count"])
    lines = []
    for r in results[:3]:
        line = f"  {r['name']}: {plural(r['count'], 'house', 'houses')} (of {r['total']} total)"
        extras = []
        if r["avg_lot"]:
            extras.append(f"avg lot {r['avg_lot']}sqm")
        if r["median_dom"]:
            extras.append(f"{r['median_dom']}d median on market")
        if extras:
            line += f"\n    {' · '.join(extras)}"
        if r["underpriced"] > 0:
            line += f"\n    {r['underpriced']} flagged below our valuation estimate"
        lines.append(line)

    most = results[0]

    msg = f"""Got {fmt_price(price_point)}? Here's where you have the most options.

Houses listed within 15% of that budget:

""" + "\n\n".join(lines) + f"""

{most['name']} gives you the most choice at this budget."""

    # Add value insight
    total_underpriced = sum(r["underpriced"] for r in results[:3])
    if total_underpriced > 0:
        msg += f" {total_underpriced} of these are priced below what our analysis says they're worth."

    msg += """

fieldsestate.com.au/for-sale — every house with an independent valuation estimate."""
    return msg, "price_comparison"


def template_listing_count(suburbs, **kw):
    """Total listings — with market speed and valuation context per suburb."""
    total = sum(s["total"] for s in suburbs.values())
    by_count = sorted(suburbs.items(), key=lambda x: -x[1]["total"])

    lines = []
    for key, s in by_count:
        if s["total"] == 0:
            continue
        line = f"  {s['display_name']}: {s['total']} houses"
        extras = []
        if s.get("median_dom"):
            extras.append(f"{s['median_dom']}d median on market")
        if s.get("new_this_week"):
            extras.append(f"{s['new_this_week']} new this week")
        if extras:
            line += f" ({', '.join(extras)})"
        lines.append(line)

    most = by_count[0][1]
    least = by_count[-1][1] if by_count[-1][1]["total"] > 0 else by_count[-2][1]

    total_new = sum(s.get("new_this_week", 0) for s in suburbs.values())
    total_stale = sum(s.get("stale_listings", 0) for s in suburbs.values())
    total_underpriced = sum(s.get("underpriced_count", 0) for s in suburbs.values())

    msg = f"""{total} houses for sale right now across Robina, Burleigh Waters and Varsity Lakes.

""" + "\n".join(lines)

    # Market dynamics
    dynamics = []
    if total_new > 0:
        dynamics.append(f"{total_new} new listings appeared this week")
    if total_stale > 0:
        dynamics.append(f"{total_stale} have been sitting 60+ days")
    if dynamics:
        msg += "\n\n" + ". ".join(dynamics) + "."

    if total_underpriced > 0:
        msg += f"\n\n{total_underpriced} houses are currently priced below our independent valuation estimate."

    msg += f"""

{most['display_name']} ({most['total']} houses) gives buyers the most choice. {least['display_name']} ({least['total']}) is where sellers have more leverage.

fieldsestate.com.au/for-sale — every house with an independent valuation."""
    return msg, "listing_count"


def template_bedroom_breakdown(suburbs, **kw):
    """Bedroom breakdown with median prices and market speed per config."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 5 and suburbs[s]["beds"]]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    # Get properties to compute median price per bedroom count
    properties = get_individual_properties()
    suburb_props = [p for p in properties if p.get("_suburb_key") == suburb_key]

    total = sum(s["beds"].values())
    lines = []
    for bed_count in sorted(s["beds"].keys(), key=lambda x: int(x)):
        count = s["beds"][bed_count]
        pct = round(count / total * 100)
        line = f"  {bed_count}-bed: {plural(count, 'house', 'houses')} ({pct}%)"

        # Median price for this bedroom count
        bed_prices = []
        for p in suburb_props:
            if str(p.get("bedrooms")) == bed_count:
                pv = parse_price_value(p.get("price", ""))
                if pv:
                    bed_prices.append(pv)
        if bed_prices:
            bed_prices.sort()
            bed_median = bed_prices[len(bed_prices) // 2]
            line += f" — median {fmt_price(bed_median)}"

        lines.append(line)

    most_common = max(s["beds"].items(), key=lambda x: x[1])
    least_common = min(
        ((k, v) for k, v in s["beds"].items() if v > 0),
        key=lambda x: x[1],
    )

    msg = f"""What can you get in {name}? {s['total']} houses by bedroom count.

""" + "\n".join(lines)

    # Add scarcity insight
    if least_common[1] <= 3:
        house_word = "house" if least_common[1] == 1 else "houses"
        msg += f"\n\nOnly {least_common[1]} {least_common[0]}-bed {house_word} on the market. If that's your size, the window is small."

    # Add market speed context
    if s.get("median_dom"):
        msg += f"\n\nMedian time on market in {name}: {s['median_dom']} days."

    msg += f"""

The median prices above show what each size actually costs — not what agents are marketing, but what's listed right now.

fieldsestate.com.au/for-sale — every house with an independent valuation."""
    return msg, "bedroom_breakdown"


def template_seller_insight(suburbs, **kw):
    """Actionable insight for sellers — competition, market speed, and pricing intelligence."""
    candidates = [s for s in suburbs if suburbs[s]["priced_count"] >= 5]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    prices = s["prices"]
    median = s["median_price"]
    below_median = len([p for p in prices if p <= median])
    above_median = len([p for p in prices if p > median])
    unpriced = s["total"] - s["priced_count"]

    msg = f"""Selling in {name}? Here's what you're up against.

{s['total']} houses for sale right now. Of {s['priced_count']} with a listed price, {below_median} at or below {fmt_price(median)} and {above_median} above it."""

    if unpriced > 0:
        msg += f" {unpriced} listed without a public price."

    # Market speed — critical for sellers
    if s.get("median_dom"):
        msg += f"\n\nMedian days on market: {s['median_dom']}."
        if s.get("stale_listings"):
            msg += f" {s['stale_listings']} houses have been sitting 60+ days — overpriced stock that drags out campaigns."
        if s.get("new_this_week"):
            msg += f" {s['new_this_week']} new listings this week means fresh competition."

    # Valuation positioning — what does the data say about pricing accuracy
    if s.get("overpriced_count") and s["overpriced_count"] > 0:
        msg += f"\n\nOur valuation analysis flags {s['overpriced_count']} current listings as above estimated market value. These are the ones most likely to sit."
    if s.get("underpriced_count") and s["underpriced_count"] > 0:
        msg += f" {s['underpriced_count']} are priced below — expect them to move faster."

    # Bedroom competition
    beds = s["beds"]
    if beds:
        most_bed = max(beds.items(), key=lambda x: x[1])
        most_pct = round(most_bed[1] / s["total"] * 100)
        msg += f"\n\n{most_bed[0]}-bed houses make up {most_pct}% of listings — the most direct competition. If yours is a different size, your buyer pool is different too."

    msg += f"""

The sellers who price right sell fastest. The ones who overshoot join the 60+ day club.

fieldsestate.com.au — independent property intelligence."""

    return msg, "seller_insight"


def template_buyer_intelligence(suburbs, **kw):
    """Cross-suburb comparison with valuation context and market speed per bracket."""
    brackets = [
        (800000, 1300000, "under $1,300,000"),
        (1300000, 1700000, "$1,300,000 – $1,700,000"),
        (1700000, 2200000, "$1,700,000 – $2,200,000"),
        (2200000, 3500000, "$2,200,000 – $3,500,000"),
    ]

    properties = get_individual_properties()

    random.shuffle(brackets)
    for low, high, label in brackets:
        results = []
        for key, s in suburbs.items():
            matches = [p for p in s["prices"] if low <= p <= high]
            if matches:
                # Find matching properties for intel
                suburb_props = [p for p in properties if p.get("_suburb_key") == key]
                bracket_props = []
                for p in suburb_props:
                    pv = parse_price_value(p.get("price", ""))
                    if pv and low <= pv <= high:
                        bracket_props.append(p)

                # Days on market for this bracket
                dom_list = [p["days_on_domain"] for p in bracket_props if isinstance(p.get("days_on_domain"), (int, float))]
                dom_list.sort()
                bracket_median_dom = dom_list[len(dom_list) // 2] if dom_list else None

                # Underpriced count
                underpriced = 0
                for p in bracket_props:
                    vd = p.get("valuation_data", {}) or {}
                    pos = (vd.get("summary") or {}).get("positioning")
                    insuf = (vd.get("summary") or {}).get("insufficient_data", True)
                    if not insuf and pos in ("underpriced", "good_value"):
                        underpriced += 1

                # New this week
                new = len([p for p in bracket_props if isinstance(p.get("days_on_domain"), (int, float)) and p["days_on_domain"] <= 7])

                results.append({
                    "name": s["display_name"],
                    "key": key,
                    "count": len(matches),
                    "min": min(matches),
                    "max": max(matches),
                    "median_dom": bracket_median_dom,
                    "underpriced": underpriced,
                    "new": new,
                })
        if len(results) >= 2:
            break
    else:
        return None, None

    results.sort(key=lambda x: -x["count"])
    lines = []
    for r in results[:3]:
        line = f"  {r['name']}: {plural(r['count'], 'house', 'houses')} ({fmt_price(r['min'])} – {fmt_price(r['max'])})"
        extras = []
        if r["median_dom"]:
            extras.append(f"{r['median_dom']}d median on market")
        if r["new"] > 0:
            extras.append(f"{r['new']} new this week")
        if extras:
            line += f"\n    {' · '.join(extras)}"
        if r["underpriced"] > 0:
            line += f"\n    {r['underpriced']} below our valuation estimate"
        lines.append(line)

    most = results[0]

    msg = f"""Buying {label}? Here's what the market actually looks like.

Houses in this price range right now:

""" + "\n\n".join(lines)

    # Add insight
    fastest = min((r for r in results[:3] if r["median_dom"]), key=lambda r: r["median_dom"], default=None)
    if fastest and fastest["median_dom"] and fastest["median_dom"] <= 25:
        msg += f"\n\n{fastest['name']} is moving fastest at this price point ({fastest['median_dom']}-day median). If you see something you like, don't wait for the second open home."

    total_underpriced = sum(r["underpriced"] for r in results[:3])
    if total_underpriced > 0:
        msg += f"\n\n{total_underpriced} of these are priced below what our analysis says they're worth."

    msg += """

fieldsestate.com.au/for-sale — every house with an independent valuation."""

    return msg, "buyer_intelligence"


def template_weekly_wrap(suburbs, **kw):
    """Sunday evening — the week's intelligence summary."""
    total = sum(s["total"] for s in suburbs.values())
    total_new = sum(s.get("new_this_week", 0) for s in suburbs.values())
    total_stale = sum(s.get("stale_listings", 0) for s in suburbs.values())
    total_underpriced = sum(s.get("underpriced_count", 0) for s in suburbs.values())

    suburb_lines = []
    for key in sorted(suburbs.keys(), key=lambda k: -suburbs[k]["total"]):
        s = suburbs[key]
        if s["total"] == 0:
            continue
        line = f"  {s['display_name']}: {s['total']} houses"
        if s["median_price"] and s["median_price"] >= 200000:
            line += f" | median {fmt_price(s['median_price'])}"
        if s.get("median_dom"):
            line += f" | {s['median_dom']}d avg on market"
        suburb_lines.append(line)

    msg = f"""Southern Gold Coast — your weekly market briefing

{total} houses for sale across our 3 suburbs.

""" + "\n".join(suburb_lines)

    # Market dynamics
    dynamics = []
    if total_new > 0:
        dynamics.append(f"{total_new} new listings this week")
    if total_stale > 0:
        dynamics.append(f"{total_stale} on the market 60+ days")
    if total_underpriced > 0:
        dynamics.append(f"{total_underpriced} flagged below estimated value by our analysis")

    if dynamics:
        msg += "\n\n" + ". ".join(dynamics) + "."

    # Fastest/slowest market
    suburbs_with_dom = [(k, v) for k, v in suburbs.items() if v.get("median_dom")]
    if suburbs_with_dom:
        fastest = min(suburbs_with_dom, key=lambda x: x[1]["median_dom"])
        slowest = max(suburbs_with_dom, key=lambda x: x[1]["median_dom"])
        if fastest[1]["median_dom"] != slowest[1]["median_dom"]:
            msg += f"\n\nFastest-moving suburb: {fastest[1]['display_name']} ({fastest[1]['median_dom']}-day median). Slowest: {slowest[1]['display_name']} ({slowest[1]['median_dom']} days)."

    msg += """

Most people make property decisions based on emotion and agent marketing. These numbers are what the market actually looks like right now.

fieldsestate.com.au — independent property intelligence."""

    return msg, "weekly_wrap"


# ── PROPERTY TEMPLATES (individual property posts) ───────────────────────

def template_open_home_spotlight(suburbs, properties=None, **kw):
    """Individual property spotlight — deep intelligence on why this specific home is worth seeing."""
    if not properties:
        properties = get_individual_properties()

    for target_day in ["Saturday", "Sunday", "Thursday", "Friday", "Wednesday", "Tuesday"]:
        candidates = get_properties_for_day(properties, target_day)
        if candidates:
            break
    else:
        return None, None

    if not candidates:
        return None, None

    # Score candidates by how interesting their intelligence is
    scored = []
    for p in candidates:
        intel = property_intel(p, suburbs, properties)
        # Prefer properties with strong insights (priority 1 or 2)
        score = sum(3 - pri for pri, _ in intel[:3])
        price_val = parse_price_value(p.get("price", ""))
        scored.append((p, intel, score, price_val))

    # Pick from top 3 most interesting
    scored.sort(key=lambda x: -x[2])
    top = scored[:3]
    prop, intel, _, price_val = random.choice(top) if top else (None, [], 0, None)
    if not prop:
        return None, None

    suburb = prop["_suburb_display"]
    insp = prop["_inspections"][0]
    bed = prop.get("bedrooms", "?")
    bath = prop.get("bathrooms", "?")
    days = prop.get("days_on_domain")
    address = normalise_address(prop)
    lot = prop.get("lot_size_sqm") or (prop.get("enriched_data") or {}).get("lot_size_sqm")

    # Build the property card
    specs = [f"{bed}-bed", f"{bath}-bath"]
    car = prop.get("carspaces")
    if car:
        specs.append(f"{car}-car")
    if lot:
        specs.append(f"{lot:.0f}sqm")
    spec_line = " · ".join(specs)

    msg = f"""{address}, {suburb}
{spec_line} — {clean_price_display(prop.get('price', ''))}
Open {insp['day']} at {insp['start']}"""

    # Add top 2 intelligence insights
    intel_lines = [text for pri, text in intel[:2]]
    if intel_lines:
        msg += "\n\n" + "\n".join(intel_lines)

    # Add market context
    median = suburbs.get(prop.get("_suburb_key"), {}).get("median_price")
    dom_median = suburbs.get(prop.get("_suburb_key"), {}).get("median_dom")
    if median and price_val:
        diff_pct = (price_val - median) / median * 100
        if abs(diff_pct) <= 10:
            msg += f"\n\nThis house sits right at the {suburb} median. Walk through it and you'll know exactly what middle-of-the-market buys here."
        elif diff_pct < -10:
            msg += f"\n\nOne of the more affordable houses in {suburb} right now. Entry-level price — go see what you actually get for the money."

    msg += "\n\nfieldsestate.com.au — independent property intelligence for the southern Gold Coast."

    return msg, "open_home_spotlight"


def template_entry_price_watch(suburbs, properties=None, **kw):
    """The cheapest house per suburb — with valuation context and what you actually get."""
    if not properties:
        properties = get_individual_properties()

    entries = []
    for suburb_key in CORE_SUBURBS:
        suburb_props = [p for p in properties if p["_suburb_key"] == suburb_key]
        priced = []
        for p in suburb_props:
            val = parse_price_value(p.get("price", ""))
            if val and val >= 300000:
                priced.append((p, val))
        if priced:
            priced.sort(key=lambda x: x[1])
            cheapest_prop, cheapest_price = priced[0]
            entries.append({
                "prop": cheapest_prop,
                "price_val": cheapest_price,
                "suburb": SUBURB_DISPLAY.get(suburb_key, suburb_key),
                "suburb_key": suburb_key,
                "total": len(suburb_props),
                "median": suburbs.get(suburb_key, {}).get("median_price"),
            })

    if not entries:
        return None, None

    lines = []
    for e in entries:
        p = e["prop"]
        bed = p.get("bedrooms", "?")
        bath = p.get("bathrooms", "?")
        addr = normalise_address(p)
        days = p.get("days_on_domain")
        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")

        gap = ""
        if e["median"]:
            pct_below = round((1 - e["price_val"] / e["median"]) * 100)
            if pct_below > 0:
                gap = f" ({pct_below}% below median)"

        specs = [f"{bed}bd {bath}ba"]
        if lot:
            specs.append(f"{lot:.0f}sqm")
        spec = " · ".join(specs)

        line = f"  {e['suburb']}: {fmt_price(e['price_val'])} — {addr}{gap}\n  {spec}"

        # Add valuation context
        vd = p.get("valuation_data", {}) or {}
        conf = (vd.get("confidence") or {})
        reconciled = conf.get("reconciled_valuation")
        insufficient = (vd.get("summary") or {}).get("insufficient_data", True)
        if reconciled and not insufficient:
            val_gap = (e["price_val"] - reconciled) / reconciled * 100
            if val_gap < -5:
                line += f" — Listed below our {fmt_price(int(reconciled))} valuation."
            elif val_gap > 15:
                line += f" — Our valuation: {fmt_price(int(reconciled))}. Room to negotiate."

        if isinstance(days, (int, float)) and days >= 45:
            line += f" {days} days on market."

        lines.append(line)

    cheapest_overall = min(entries, key=lambda e: e["price_val"])

    msg = f"""Entry-level house prices — what does the cheapest way in actually look like?

""" + "\n\n".join(lines) + f"""

{cheapest_overall['suburb']} has the lowest entry point at {fmt_price(cheapest_overall['price_val'])}. When this sells, it sets the floor for the suburb.

fieldsestate.com.au/for-sale — every house with an independent valuation estimate."""

    return msg, "entry_price_watch"


def template_median_showcase(suburbs, properties=None, **kw):
    """What does median money buy? Deep look at the house that defines 'middle of the market'."""
    if not properties:
        properties = get_individual_properties()

    candidates = [s for s in CORE_SUBURBS if s in suburbs and suburbs[s].get("median_price")]
    if not candidates:
        return None, None

    suburb_key = random.choice(candidates)
    median = suburbs[suburb_key]["median_price"]
    suburb_name = SUBURB_DISPLAY.get(suburb_key, suburb_key)
    total_listings = suburbs[suburb_key]["total"]

    suburb_props = [p for p in properties if p["_suburb_key"] == suburb_key]
    priced = [(p, parse_price_value(p.get("price", ""))) for p in suburb_props]
    priced = [(p, v) for p, v in priced if v is not None]
    if not priced:
        return None, None

    priced.sort(key=lambda x: abs(x[1] - median))
    prop, price = priced[0]

    bed = prop.get("bedrooms", "?")
    bath = prop.get("bathrooms", "?")
    car = prop.get("carspaces", "?")
    lot = prop.get("lot_size_sqm") or (prop.get("enriched_data") or {}).get("lot_size_sqm")
    days = prop.get("days_on_domain")

    specs = [f"{bed} bed", f"{bath} bath"]
    if car:
        specs.append(f"{car} car")
    if lot:
        specs.append(f"{lot:.0f}sqm")
    spec_line = " · ".join(specs)

    insp_line = ""
    inspections = prop.get("inspection_times") or []
    if inspections:
        details = parse_inspection_details(inspections[0])
        if details["start"]:
            insp_line = f"\nOpen {details['day']} at {details['start']}."

    address = normalise_address(prop)

    msg = f"""What does {fmt_price(median)} buy in {suburb_name}?

{total_listings} houses for sale. Half above {fmt_price(median)}, half below. This one sits right on the line:

{address}
{spec_line}
{clean_price_display(prop.get('price', ''))}{insp_line}"""

    # Add intelligence
    intel = property_intel(prop, suburbs, properties)
    non_timing = [(pri, t) for pri, t in intel if "Brand new" not in t and "Fresh to" not in t]
    if non_timing:
        msg += f"\n\n{non_timing[0][1]}"

    msg += f"""

Walk through the median house and you'll know what "average" actually means in {suburb_name}. Everything else is either a step up or a compromise from here.

fieldsestate.com.au/for-sale — every house, independently valued."""

    return msg, "median_showcase"


def template_weekend_preview(suburbs, properties=None, **kw):
    """Friday post — curated picks for the weekend with specific intelligence on each."""
    if not properties:
        properties = get_individual_properties()

    sat_props = get_properties_for_day(properties, "Saturday")
    sun_props = get_properties_for_day(properties, "Sunday")

    all_weekend = []
    seen_ids = set()
    for p in sat_props + sun_props:
        pid = str(p.get("_id", ""))
        if pid not in seen_ids:
            seen_ids.add(pid)
            all_weekend.append(p)

    if len(all_weekend) < 3:
        return None, None

    total_weekend = len(all_weekend)

    # Score every property by intelligence value
    scored = []
    for p in all_weekend:
        intel = property_intel(p, suburbs, properties)
        price_val = parse_price_value(p.get("price", ""))
        # Weight: priority 1 insights = 3pts, priority 2 = 2pts, priority 3 = 1pt
        score = sum(4 - pri for pri, _ in intel[:3])
        scored.append((p, intel, score, price_val))

    scored.sort(key=lambda x: -x[2])

    # Pick top 4, ensuring suburb diversity
    picks = []
    seen_suburbs = {}
    for p, intel, score, price_val in scored:
        sk = p.get("_suburb_key", "")
        if seen_suburbs.get(sk, 0) >= 2:
            continue
        seen_suburbs[sk] = seen_suburbs.get(sk, 0) + 1
        picks.append((p, intel, price_val))
        if len(picks) >= 4:
            break

    # If not enough diverse picks, fill from top scores
    if len(picks) < 3:
        for p, intel, score, price_val in scored:
            if all(str(p.get("_id")) != str(pk[0].get("_id")) for pk in picks):
                picks.append((p, intel, price_val))
                if len(picks) >= 4:
                    break

    lines = []
    for prop, intel, price_val in picks:
        insp = prop["_inspections"][0]
        suburb = prop["_suburb_display"]
        bed = prop.get("bedrooms", "?")
        bath = prop.get("bathrooms", "?")
        addr = normalise_address(prop)
        lot = prop.get("lot_size_sqm") or (prop.get("enriched_data") or {}).get("lot_size_sqm")
        price_str = clean_price_display(prop.get("price", ""))

        specs = [f"{bed}bd {bath}ba"]
        if lot:
            specs.append(f"{lot:.0f}sqm")
        spec = " · ".join(specs)

        # Use the top intelligence insight as the reason
        reason = intel[0][1] if intel else ""
        second = intel[1][1] if len(intel) > 1 and intel[1][0] <= 2 else ""

        entry = f"  {addr}, {suburb}\n  {spec} — {price_str} — Open {insp['day']} {insp['start']}"
        if reason:
            entry += f"\n  {reason}"
        if second:
            entry += f"\n  {second}"
        lines.append(entry)

    msg = f"""{total_weekend} houses open this weekend. Here are {len(picks)} that stood out in our data.

""" + "\n\n".join(lines) + """

These picks are based on valuation analysis, days on market, and suburb comparisons — not agent marketing.

fieldsestate.com.au/for-sale — full listings with valuations."""

    return msg, "weekend_preview"


def template_saturday_open_list(suburbs, properties=None, **kw):
    """Saturday 6am — today's open homes with brief intelligence tags."""
    if not properties:
        properties = get_individual_properties()

    sat_props = get_properties_for_day(properties, "Saturday")

    if not sat_props:
        return None, None

    MAX_PER_SUBURB = 8

    # Group by suburb
    by_suburb = {}
    for p in sat_props:
        suburb = p["_suburb_display"]
        if suburb not in by_suburb:
            by_suburb[suburb] = []
        by_suburb[suburb].append(p)

    # Quick-tag function: one short label per property
    def quick_tag(p):
        days = p.get("days_on_domain")
        vd = p.get("valuation_data", {}) or {}
        positioning = (vd.get("summary") or {}).get("positioning")
        insufficient = (vd.get("summary") or {}).get("insufficient_data", True)
        if isinstance(days, (int, float)) and days <= 3:
            return "NEW"
        if isinstance(days, (int, float)) and days >= 90:
            return f"{days}d"
        if not insufficient and positioning in ("underpriced", "good_value"):
            return "VALUE"
        if isinstance(days, (int, float)) and days <= 7:
            return "FRESH"
        return ""

    # Build highlights
    all_priced = [(p, parse_price_value(p.get("price", ""))) for p in sat_props]
    all_priced = [(p, v) for p, v in all_priced if v and v >= 300000]
    highlights = []
    if all_priced:
        all_priced.sort(key=lambda x: x[1])
        cheapest = all_priced[0]
        highlights.append(f"  Cheapest: {normalise_address(cheapest[0])} ({cheapest[0]['_suburb_display']}) — {fmt_price(cheapest[1])}")
        most_exp = all_priced[-1]
        if most_exp[1] != cheapest[1]:
            highlights.append(f"  Premium: {normalise_address(most_exp[0])} ({most_exp[0]['_suburb_display']}) — {fmt_price(most_exp[1])}")

    sections = []
    unique_count = 0
    for suburb in sorted(by_suburb.keys()):
        props = by_suburb[suburb]
        props.sort(key=lambda p: time_sort_key(p["_inspections"][0].get("start", "")))

        seen_addrs = set()
        prop_lines = []
        for p in props:
            addr = normalise_address(p)
            if addr in seen_addrs or not addr:
                continue
            seen_addrs.add(addr)
            unique_count += 1
            insp = p["_inspections"][0]
            price = clean_price_display(p.get("price", ""))
            bed = p.get("bedrooms", "?")
            tag = quick_tag(p)
            tag_str = f" [{tag}]" if tag else ""
            prop_lines.append(f"  {insp['start']} — {addr} ({bed}bd, {price}){tag_str}")

        shown = prop_lines[:MAX_PER_SUBURB]
        overflow = len(prop_lines) - MAX_PER_SUBURB
        section = f"{suburb}:\n" + "\n".join(shown)
        if overflow > 0:
            section += f"\n  + {overflow} more"
        sections.append(section)

    new_count = len([p for p in sat_props if isinstance(p.get("days_on_domain"), (int, float)) and p["days_on_domain"] <= 7])

    msg = f"""Open homes today — {unique_count} houses across 3 suburbs.

""" + "\n".join(highlights) + "\n\n" + "\n\n".join(sections)

    msg += "\n\nNEW = listed this week. FRESH = under 7 days. VALUE = below our valuation estimate."

    if new_count > 0:
        msg += f"\n\n{new_count} of these are first or second open homes — expect the most buyer interest there."

    msg += "\n\nfieldsestate.com.au/for-sale — full details + valuations on every house."

    return msg, "saturday_open_list"


def _sold_insight(p, all_sold):
    """Generate a specific insight for one sold property using enriched data."""
    address = p.get("street_address", "")
    sale_price = p.get("sale_price", "")
    sale_val = parse_price_value(str(sale_price)) if sale_price else None
    listing_price = p.get("listing_price", "")
    list_val = parse_price_value(str(listing_price)) if listing_price else None
    days = p.get("days_on_market")
    bed = p.get("bedrooms")
    suburb = p.get("_suburb_display", "")
    ed = p.get("enriched_data") or {}
    lot = ed.get("lot_size_sqm")
    floor = ed.get("floor_area_sqm")
    if not floor:
        fp = p.get("floor_plan_analysis", {})
        floor = fp.get("internal_floor_area", {}).get("value") if fp else None
    txns = ed.get("transactions", [])
    pi = p.get("property_insights", {})

    # Priority-ordered insights — we'll pick the best 1-2
    high = []   # Most compelling
    medium = []  # Good context
    low = []     # Fallback

    # Speed of sale (high impact — people notice fast/slow sales)
    if days is not None:
        all_days = [s.get("days_on_market") for s in all_sold if s.get("days_on_market")]
        avg_days = sum(all_days) / len(all_days) if all_days else 25
        if days <= 5:
            high.append(f"Sold in just {days} days — fastest confirmed sale this period.")
        elif days <= 10 and avg_days > 20:
            high.append(f"Sold in {days} days, well under the {avg_days:.0f}-day average.")
        elif days >= 45:
            medium.append(f"Took {days} days — longer campaigns usually mean the price needed adjusting.")

    # Prior transaction history / capital gain (high impact — people love growth stories)
    if txns and sale_val:
        prior_sales = [t for t in txns if t.get("price") and t.get("price") < sale_val * 0.95]
        if prior_sales:
            last = prior_sales[-1]
            prior_price = last.get("price", 0)
            prior_date = str(last.get("date", ""))[:4]
            if prior_price > 0 and prior_date:
                gain_pct = (sale_val - prior_price) / prior_price * 100
                high.append(f"Last sold in {prior_date} for {fmt_price(int(prior_price))} — a {gain_pct:.0f}% gain.")

    # Listing vs sale price gap (medium — interesting but common)
    if sale_val and list_val and list_val > 0:
        gap_pct = (sale_val - list_val) / list_val * 100
        if gap_pct >= 5:
            medium.append(f"Sold {abs(gap_pct):.0f}% above asking — multiple buyers likely competed.")
        elif gap_pct <= -5:
            medium.append(f"Sold {abs(gap_pct):.0f}% below asking — initial price was ahead of the market.")

    # Our valuation vs sale price (high impact — validates or challenges our model)
    vd = p.get("valuation_data", {}) or {}
    reconciled = (vd.get("confidence") or {}).get("reconciled_valuation")
    if sale_val and reconciled:
        val_error = (sale_val - reconciled) / reconciled * 100
        if abs(val_error) <= 5:
            high.append(f"Sold within 5% of our {fmt_price(int(reconciled))} valuation.")
        elif val_error > 10:
            medium.append(f"Sold {val_error:.0f}% above our {fmt_price(int(reconciled))} estimate — we undervalued this one.")
        elif val_error < -10:
            medium.append(f"Sold {abs(val_error):.0f}% below our {fmt_price(int(reconciled))} estimate.")

    # Rarity / percentile (medium — useful for scarcity signal)
    if pi:
        beds_pi = pi.get("bedrooms", {})
        sc = beds_pi.get("suburbComparison", {})
        pctl = sc.get("percentile")
        if pctl and pctl >= 85 and bed:
            medium.append(f"{bed}-bed houses are top {100-pctl}% for size in {suburb} — rare stock.")
        lot_pi = pi.get("lot_size", {})
        lsc = lot_pi.get("suburbComparison", {})
        lpctl = lsc.get("percentile")
        if lpctl and lpctl >= 85 and lot:
            medium.append(f"{lot:.0f}sqm lot — larger than {lpctl}% of {suburb} listings.")

    # $/sqm (low priority — useful as fallback only)
    if lot and sale_val:
        price_per_sqm_land = sale_val / lot
        low.append(f"{lot:.0f}sqm lot at {fmt_price(int(price_per_sqm_land))}/sqm of land.")
    elif floor and sale_val:
        price_per_sqm_floor = sale_val / floor
        low.append(f"{floor:.0f}sqm internal at {fmt_price(int(price_per_sqm_floor))}/sqm of living space.")

    # Return best insights: up to 1 high + 1 medium, or fallback to low
    result = []
    if high:
        result.append(high[0])
    if medium:
        result.append(medium[0])
    if not result and low:
        result.append(low[0])
    return result


def _parse_sold_date(p):
    """Parse sold_date from a property record. Returns datetime or None."""
    raw = p.get("sold_date") or p.get("moved_to_sold_date") or p.get("sold_date_text")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def template_sold_results(suburbs, properties=None, **kw):
    """Monday — what sold last week, with context and insight per sale."""
    sold_properties = get_recently_sold_properties()

    if not sold_properties:
        msg = """Sales update — Robina, Burleigh Waters, Varsity Lakes

No confirmed house sales this past week. Settlement timelines and delayed reporting mean some sales take weeks to appear.

When they land, we break them down — what sold, what it sold for, and what it means for prices in your suburb.

Follow us to see them first."""
        return msg, "sold_results"

    # Filter to last 7 days only
    cutoff = datetime.now() - timedelta(days=7)
    time_filtered = []
    for p in sold_properties:
        sold_dt = _parse_sold_date(p)
        if sold_dt and sold_dt >= cutoff:
            p["_sold_dt"] = sold_dt
            time_filtered.append(p)

    # Dedup by address (keep most recent)
    seen_addrs = {}
    for p in time_filtered:
        addr = p.get("street_address", "")
        if addr not in seen_addrs:
            seen_addrs[addr] = p
        else:
            existing = seen_addrs[addr]
            if p.get("_sold_dt", datetime.min) > existing.get("_sold_dt", datetime.min):
                seen_addrs[addr] = p
    sold_deduped = list(seen_addrs.values())

    valid_sold = list(sold_deduped)

    # Sort by sold date (most recent first)
    valid_sold.sort(key=lambda p: p.get("_sold_dt", datetime.min), reverse=True)

    # Group by suburb in fixed order: Robina, Varsity Lakes, Burleigh Waters
    suburb_order = [
        ("robina", "Robina"),
        ("varsity_lakes", "Varsity Lakes"),
        ("burleigh_waters", "Burleigh Waters"),
    ]
    by_suburb = {}
    for p in valid_sold:
        key = p.get("_suburb_key", "")
        by_suburb.setdefault(key, []).append(p)

    # Count total
    total = len(valid_sold)

    # Build headline with counts per suburb in order
    headline_parts = []
    for key, display in suburb_order:
        count = len(by_suburb.get(key, []))
        headline_parts.append(f"{display}: {count}")
    headline_suburbs = " | ".join(headline_parts)

    if total == 0:
        msg = f"Sales update — {headline_suburbs}\n\n"
        msg += "No confirmed house sales this past week. Settlement timelines and delayed reporting mean some sales take weeks to appear.\n\n"
        msg += "Follow us — when they land, we break them down here."
        return msg, "sold_results"

    msg = f"What sold this week — {plural(total, 'confirmed sale')}\n{headline_suburbs}\n"

    for key, display in suburb_order:
        suburb_sold = by_suburb.get(key, [])
        if not suburb_sold:
            msg += f"\n{display} — no house sales this week\n"
            continue

        msg += f"\n{display}\n"
        for p in suburb_sold[:4]:
            address = normalise_address(p)
            sale_price = p.get("sale_price", "")
            sale_val = parse_price_value(str(sale_price)) if sale_price else None
            days = p.get("days_on_market")
            bed = p.get("bedrooms", "?")

            if sale_val:
                price_str = fmt_price(sale_val)
            elif sale_price and str(sale_price).strip() and str(sale_price).strip().lower() != "none":
                price_str = clean_price_display(str(sale_price))
            else:
                price_str = "price undisclosed"
            dom_str = f", {days} days on market" if days else ""
            line = f"  {address} — {bed}-bed house, {price_str}{dom_str}"

            insights = _sold_insight(p, valid_sold)
            if insights:
                line += "\n    " + " ".join(insights[:2])

            msg += line + "\n"

    msg += "\nFollow us — we track every sale and break down what it means for your suburb."

    return msg, "sold_results"


def template_new_to_market(suburbs, properties=None, **kw):
    """Monday evening — new listings with intelligence on each."""
    if not properties:
        properties = get_individual_properties()

    cutoff = datetime.now() - timedelta(days=7)

    new_listings = []
    for p in properties:
        listed_str = p.get("first_listed_timestamp") or p.get("first_seen", "")
        if not listed_str:
            continue
        try:
            listed_date = datetime.fromisoformat(str(listed_str).replace("Z", "").split(".")[0])
            if listed_date >= cutoff:
                new_listings.append((p, listed_date))
        except (ValueError, TypeError):
            continue

    if not new_listings:
        for p in properties:
            days = p.get("days_on_domain", 999)
            if isinstance(days, (int, float)) and days <= 7:
                new_listings.append((p, datetime.now()))

    if not new_listings:
        return None, None

    new_listings.sort(key=lambda x: x[1], reverse=True)

    # Count by suburb
    suburb_counts = {}
    for p, _ in new_listings:
        s = p["_suburb_display"]
        suburb_counts[s] = suburb_counts.get(s, 0) + 1

    total = len(new_listings)
    suburb_summary = ", ".join(f"{c} in {s}" for s, c in sorted(suburb_counts.items(), key=lambda x: -x[1]))

    lines = []
    for p, dt in new_listings[:6]:
        suburb = p["_suburb_display"]
        price = clean_price_display(p.get("price", ""))
        price_val = parse_price_value(p.get("price", ""))
        bed = p.get("bedrooms", "?")
        bath = p.get("bathrooms", "?")
        addr = normalise_address(p)
        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")

        specs = [f"{bed}bd {bath}ba"]
        if lot:
            specs.append(f"{lot:.0f}sqm")
        spec = " · ".join(specs)

        entry = f"  {addr}, {suburb} — {price}\n  {spec}"

        # Add one key insight
        intel = property_intel(p, suburbs, properties)
        # Skip the "brand new listing" insight since they're ALL new
        non_obvious = [(pri, t) for pri, t in intel if "Brand new" not in t and "Fresh to market" not in t]
        if non_obvious:
            entry += f"\n  {non_obvious[0][1]}"
        lines.append(entry)

    median_dom = suburbs.get("robina", {}).get("median_dom")
    speed_context = ""
    if median_dom and median_dom <= 30:
        speed_context = f" The median house in Robina is on the market {median_dom} days — first impressions count, so get to the first open home if you can."

    msg = f"""{plural(total, 'new house', 'new houses')} listed this week — {suburb_summary}

""" + "\n\n".join(lines)

    msg += f"""

New listings get the most attention in their first 2 weeks.{speed_context}

fieldsestate.com.au/for-sale — see every listing with our independent valuation."""

    return msg, "new_to_market"


# ── Template registry ────────────────────────────────────────────────────

AGGREGATE_TEMPLATES = {
    "suburb_snapshot": template_suburb_snapshot,
    "price_comparison": template_price_comparison,
    "listing_count": template_listing_count,
    "bedroom_breakdown": template_bedroom_breakdown,
    "seller_insight": template_seller_insight,
    "buyer_intelligence": template_buyer_intelligence,
    "weekly_wrap": template_weekly_wrap,
}

PROPERTY_TEMPLATES = {
    "open_home_spotlight": template_open_home_spotlight,
    "entry_price_watch": template_entry_price_watch,
    "median_showcase": template_median_showcase,
    "weekend_preview": template_weekend_preview,
    "saturday_open_list": template_saturday_open_list,
    "sold_results": template_sold_results,
    "new_to_market": template_new_to_market,
}

TEMPLATE_MAP = {**AGGREGATE_TEMPLATES, **PROPERTY_TEMPLATES}


def generate_post(suburbs, template_name=None):
    """Pick a template and generate a post. If template_name given, use that specific one."""
    properties = None

    if template_name:
        fn = TEMPLATE_MAP.get(template_name)
        if not fn:
            print(f"ERROR: Unknown template '{template_name}'. Available: {', '.join(TEMPLATE_MAP.keys())}")
            return None, None

        if template_name in PROPERTY_TEMPLATES:
            properties = get_individual_properties()
            msg, ttype = fn(suburbs, properties=properties)
        else:
            msg, ttype = fn(suburbs)
        return msg, ttype

    # Random selection (excluding scheduler-only templates)
    scheduler_only = {"weekly_wrap", "saturday_open_list", "weekend_preview", "sold_results"}
    daily_templates = [(name, fn) for name, fn in TEMPLATE_MAP.items() if name not in scheduler_only]
    random.shuffle(daily_templates)

    for name, template_fn in daily_templates:
        if name in PROPERTY_TEMPLATES:
            if properties is None:
                properties = get_individual_properties()
            msg, template_type = template_fn(suburbs, properties=properties)
        else:
            msg, template_type = template_fn(suburbs)
        if msg:
            return msg, template_type
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Post to Fields Real Estate Facebook page")
    parser.add_argument("--generate", action="store_true", help="Auto-generate a data-led post")
    parser.add_argument("--template", type=str, help=f"Use specific template: {', '.join(TEMPLATE_MAP.keys())}")
    parser.add_argument("--post", action="store_true", help="Actually publish (default: dry run)")
    parser.add_argument("--message", type=str, help="Custom message to post")
    parser.add_argument("--link", type=str, help="URL to attach to the post")
    parser.add_argument("--image", type=str, help="Path to image file to post as photo")
    args = parser.parse_args()

    if args.generate:
        print("Pulling suburb data...")
        suburbs = get_suburb_data()
        message, template_type = generate_post(suburbs, template_name=args.template)
        if not message:
            print("ERROR: Could not generate a post from available data.")
            sys.exit(1)
        print(f"\n--- Generated post (template: {template_type}) ---\n")
        print(message)
        print("\n---")

        if args.post:
            print("\nPublishing to Facebook page...")
            post_id = post_to_page(message)
            log_post(post_id, message, None, template_type)
            print(f"Published! Post ID: {post_id}")
            print(f"View: https://facebook.com/{post_id}")
        else:
            print("\n(Dry run — add --post to publish)")

    elif args.message:
        print(f"Message: {args.message[:100]}...")
        if args.post:
            if args.image:
                print(f"Publishing photo to Facebook page ({args.image})...")
                post_id = post_photo_to_page(args.image, args.message)
                log_post(post_id, args.message, args.link, "manual", content_type="image")
            else:
                print("Publishing to Facebook page...")
                post_id = post_to_page(args.message, args.link)
                log_post(post_id, args.message, args.link, "manual")
            print(f"Published! Post ID: {post_id}")
            print(f"View: https://facebook.com/{post_id}")
        else:
            print("(Dry run — add --post to publish)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
