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

BUYER_CTA = "Looking to buy? Message us your budget and the type of home you're after — we'll personally search for properties that match, including ones that haven't listed yet. Complimentary Fields buyer assist."
SELLER_CTA = "Thinking about selling? Message us your address and we'll send you a complimentary property report — what your home is worth, how it compares, and what the current market means for your timeline. No obligation."
TAGLINE = "Fields Real Estate: Smarter with data."


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


def post_photo_url_to_page(image_url, message):
    """Post a photo by URL with caption to the Facebook page. Returns post_id."""
    page_token = get_page_token()
    r = requests.post(
        f"{BASE}/{PAGE_ID}/photos",
        data={"message": message, "url": image_url, "access_token": page_token},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("post_id") or data.get("id")


def stage_post(message, template_type, image_url=None, slot=None):
    """Save a generated post to fb_pending_posts for approval in the Marketing Monitor."""
    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]
    now_aest = datetime.now(timezone.utc) + timedelta(hours=10)
    doc = {
        "message": message,
        "template_type": template_type,
        "image_url": image_url,
        "content_type": "photo" if image_url else "text",
        "slot": slot,
        "status": "pending",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_date": now_aest.strftime("%Y-%m-%d"),
        "generated_day": now_aest.strftime("%A"),
    }
    result = db["fb_pending_posts"].insert_one(doc)
    client.close()
    return str(result.inserted_id)


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
            # Comparables for context (id, price, adjustment_result, weight, included_in_valuation)
            "valuation_data.recent_sales.id": 1,
            "valuation_data.recent_sales.price": 1,
            "valuation_data.recent_sales.adjustment_result.adjusted_price": 1,
            "valuation_data.recent_sales.weight.raw_weight": 1,
            "valuation_data.recent_sales.included_in_valuation": 1,
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
            "property_valuation_data.outdoor": 1,
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
            # Images for photo posts
            "photo_tour_order": 1,
            "property_images": 1,
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
            insights.append((2, f"Standout rooms: {best[0]} ({best[1]:.0f}m²) and {second[0]} ({second[1]:.0f}m²) are larger than most in {suburb}."))
        else:
            insights.append((2, f"{best[0]} is {best[1]:.0f}m² — larger than most in {suburb}."))

    if compact_rooms and not standout_rooms:
        compact_rooms.sort(key=lambda x: x[2])
        worst = compact_rooms[0]
        insights.append((3, f"Trade-off: {worst[0]} is {worst[1]:.0f}m² — smaller than most in {suburb}."))

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


def get_market_context():
    """Load quarterly market data for narrative context across target suburbs.

    Returns a dict keyed by suburb (lowercase_with_underscores) containing:
        median_trend    — last 4 quarters of median prices
        latest_median   — most recent quarter median
        yoy_change_pct  — year-over-year percentage change
        dom_trend       — last 4 quarters of days-on-market stats
        latest_dom_median — most recent quarter DOM median
        market_phase    — current market cycle phase (e.g. "balanced")
        market_score    — numeric market cycle score
    """
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast"]
    result = {}

    for suburb in TARGET_SUBURBS:
        display_name = SUBURB_DISPLAY.get(suburb, suburb.replace("_", " ").title())
        entry = {
            "median_trend": [],
            "latest_median": None,
            "yoy_change_pct": None,
            "dom_trend": [],
            "latest_dom_median": None,
            "market_phase": None,
            "market_score": None,
        }

        # --- Median price trend from suburb_median_prices ---
        try:
            median_col = db["suburb_median_prices"]
            median_docs = list(query_with_retry(
                median_col,
                {"suburb": suburb, "property_type": "House"},
                None,
                max_retries=3,
            ))
            # Each doc may have quarterly data; extract the last 4 quarters
            # suburb_median_prices stores one doc per suburb with quarterly arrays
            if median_docs:
                doc = median_docs[0]
                quarterly = doc.get("quarterly_medians", doc.get("quarterly", []))
                if isinstance(quarterly, list) and quarterly:
                    # Sort by quarter string (e.g. "2025-Q3")
                    quarterly.sort(key=lambda x: x.get("q", x.get("quarter", "")))
                    last_4 = quarterly[-4:]
                    entry["median_trend"] = [
                        {
                            "q": q.get("q", q.get("quarter", "")),
                            "median": q.get("median", q.get("median_price", 0)),
                            "count": q.get("count", q.get("sales_count", 0)),
                        }
                        for q in last_4
                    ]
                    if entry["median_trend"]:
                        entry["latest_median"] = entry["median_trend"][-1]["median"]
                    # YoY change: compare latest to 4 quarters ago if available
                    if len(quarterly) >= 5:
                        old_median = quarterly[-5].get("median", quarterly[-5].get("median_price", 0))
                        if old_median and old_median > 0 and entry["latest_median"]:
                            entry["yoy_change_pct"] = round(
                                (entry["latest_median"] - old_median) / old_median * 100, 1
                            )
        except Exception as e:
            print(f"  [market_context] median query failed for {suburb}: {e}")

        time.sleep(0.3)

        # --- Days on market from precomputed_market_charts ---
        try:
            charts_col = db["precomputed_market_charts"]
            dom_doc = query_with_retry(
                charts_col,
                {"suburb": display_name, "chart_type": "days_on_market"},
                None,
                max_retries=3,
            )
            dom_docs = list(dom_doc) if dom_doc else []
            if dom_docs:
                doc = dom_docs[0]
                quarterly = doc.get("quarterly", doc.get("data", []))
                if isinstance(quarterly, list) and quarterly:
                    quarterly.sort(key=lambda x: x.get("q", x.get("quarter", "")))
                    last_4 = quarterly[-4:]
                    entry["dom_trend"] = [
                        {
                            "q": q.get("q", q.get("quarter", "")),
                            "avg": q.get("avg", q.get("average", 0)),
                            "median": q.get("median", 0),
                            "quick_pct": q.get("quick_pct", q.get("quick_sale_pct", 0)),
                        }
                        for q in last_4
                    ]
                    if entry["dom_trend"]:
                        entry["latest_dom_median"] = entry["dom_trend"][-1]["median"]
        except Exception as e:
            print(f"  [market_context] DOM query failed for {suburb}: {e}")

        time.sleep(0.3)

        # --- Market cycle phase from precomputed_market_charts ---
        try:
            charts_col = db["precomputed_market_charts"]
            cycle_doc = query_with_retry(
                charts_col,
                {"suburb": display_name, "chart_type": "market_cycle"},
                None,
                max_retries=3,
            )
            cycle_docs = list(cycle_doc) if cycle_doc else []
            if cycle_docs:
                doc = cycle_docs[0]
                # Latest data point
                data_points = doc.get("data", doc.get("quarterly", []))
                if isinstance(data_points, list) and data_points:
                    latest = data_points[-1]
                    entry["market_phase"] = latest.get("phase", latest.get("market_phase", "unknown"))
                    entry["market_score"] = latest.get("score", latest.get("market_score", None))
        except Exception as e:
            print(f"  [market_context] cycle query failed for {suburb}: {e}")

        time.sleep(0.3)

        result[suburb] = entry

    client.close()
    return result


# ── Article index — mapping of topic keywords to published article URLs ──
# Buy/sell articles are refreshed from Ghost API to always use the latest slug.

def _refresh_article_slugs():
    """Fetch latest 'Is now a good time to buy/sell' article slugs from Ghost.
    Returns dict of updates to merge into ARTICLE_INDEX."""
    try:
        import requests
        ghost_key = os.environ.get("GHOST_CONTENT_API_KEY", "")
        if not ghost_key:
            return {}
        url = f"https://fields-articles.ghost.io/ghost/api/content/posts/?key={ghost_key}&fields=title,slug,updated_at&order=updated_at%20desc&limit=50"
        r = requests.get(url, timeout=10)
        posts = r.json().get("posts", [])

        # Match patterns: "Is Now a Good Time to Buy/Sell in <Suburb>?"
        # Keep the most recently updated slug for each suburb+action combo
        suburb_map = {
            "robina": {"buy": "buy_robina", "sell": "sell_robina"},
            "burleigh waters": {"buy": "buy_burleigh", "sell": "sell_burleigh"},
            "varsity lakes": {"buy": "buy_varsity", "sell": "sell_varsity"},
        }
        updates = {}
        seen = set()
        for p in posts:
            title_lower = p["title"].lower()
            if "good time to" not in title_lower:
                continue
            action = "buy" if "buy" in title_lower else "sell" if "sell" in title_lower else None
            if not action:
                continue
            for suburb_name, keys in suburb_map.items():
                if suburb_name in title_lower:
                    key = keys[action]
                    if key not in seen:  # First match = most recently updated
                        seen.add(key)
                        updates[key] = {
                            "title": p["title"],
                            "url": f"fieldsestate.com.au/articles/{p['slug']}"
                        }
                    break
        return updates
    except Exception:
        return {}


ARTICLE_INDEX = {
    "buy_robina": {"title": "Is Now a Good Time to Buy in Robina?", "url": "fieldsestate.com.au/articles/is-now-a-good-time-to-buy-in-robina-2"},
    "buy_burleigh": {"title": "Is Now a Good Time to Buy in Burleigh Waters?", "url": "fieldsestate.com.au/articles/is-now-a-good-time-to-buy-in-burleigh-waters"},
    "buy_varsity": {"title": "Is Now a Good Time to Buy in Varsity Lakes?", "url": "fieldsestate.com.au/articles/is-now-a-good-time-to-buy-in-varsity-lakes"},
    "sell_robina": {"title": "Is Now a Good Time to Sell in Robina?", "url": "fieldsestate.com.au/articles/is-now-a-good-time-to-sell-in-robina-2"},
    "sell_burleigh": {"title": "Is Now a Good Time to Sell in Burleigh Waters?", "url": "fieldsestate.com.au/articles/is-now-a-good-time-to-sell-in-burleigh-waters-2"},
    "sell_varsity": {"title": "Is Now a Good Time to Sell in Varsity Lakes?", "url": "fieldsestate.com.au/articles/is-now-a-good-time-to-sell-in-varsity-lakes-2"},
    "beach_distance": {"title": "How Much Does Beach Distance Actually Cost You?", "url": "fieldsestate.com.au/articles/beach-distance-price-impact"},
    "indicators": {"title": "Stop Watching Interest Rates", "url": "fieldsestate.com.au/articles/leading-vs-lagging-indicators"},
    "december_listing": {"title": "Why January and February Are the Worst Months to Sell", "url": "fieldsestate.com.au/articles/december-listing-paradox"},
    "oil_war": {"title": "War, Oil and Your Home", "url": "fieldsestate.com.au/articles/oil-shocks-gold-coast-house-prices"},
    "robina_market": {"title": "Robina's Fastest-Moving Year in Half a Decade", "url": "fieldsestate.com.au/articles/robinas-market-has-shifted-the-2025-numbers-show-it-clearly"},
    "varsity_market": {"title": "Every Home Sold in Under 30 Days", "url": "fieldsestate.com.au/articles/varsity-lakes-every-home-sold-in-under-30-days-the-window-is-narrowing"},
    "robina_conditions": {"title": "Robina's Buyer-Friendly Conditions", "url": "fieldsestate.com.au/articles/robinas-buyer-friendly-conditions-hold-but-watch-the-early-signals"},
    "bw_surge": {"title": "Burleigh Waters +38.7% Quarterly Surge", "url": "fieldsestate.com.au/articles/burleigh-waters-posts-a-38-7-quarterly-surge-the-strongest-single-quarter-move-across-the-corridor"},
    "light_rail": {"title": "Gold Coast Light Rail Stage 4", "url": "fieldsestate.com.au/articles/the-missing-link-nerang-to-broadbeach-public-transport-corridor"},
    "m1_upgrade": {"title": "M1 Motorway Upgrade Complete", "url": "fieldsestate.com.au/articles/m1-pacific-motorway-upgrade-five-years-1-5-billion-and-its-finally-done"},
    "apartment_boom": {"title": "Southern Gold Coast Apartment Boom", "url": "fieldsestate.com.au/articles/the-southern-gold-coast-apartment-boom-a-suburb-by-suburb-guide"},
    "market_robina": {"title": "fieldsestate.com.au/market-metrics/Robina", "url": "fieldsestate.com.au/market-metrics/Robina"},
    "market_burleigh": {"title": "fieldsestate.com.au/market-metrics/Burleigh Waters", "url": "fieldsestate.com.au/market-metrics/Burleigh%20Waters"},
    "market_varsity": {"title": "fieldsestate.com.au/market-metrics/Varsity Lakes", "url": "fieldsestate.com.au/market-metrics/Varsity%20Lakes"},
}

# Refresh buy/sell slugs from Ghost on import (overrides hardcoded defaults if newer versions exist)
ARTICLE_INDEX.update(_refresh_article_slugs())


def get_article_index():
    """Return the full article index dict mapping topic keywords to article info."""
    return ARTICLE_INDEX


def article_link(key):
    """Return a formatted article reference for a post, or empty string if key not found."""
    a = ARTICLE_INDEX.get(key)
    if not a:
        return ""
    return a["url"]


def get_recently_sold_properties():
    """Pull recently sold houses from target suburbs with valuation data."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast"]

    sold = []
    for suburb in CORE_SUBURBS:
        try:
            listings = query_with_retry(db[suburb], SOLD_HOUSE_FILTER, {
                "_id": 1, "address": 1, "street_address": 1, "suburb": 1,
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
    """Single suburb market snapshot — narrative framing with actionable advice."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 5]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    # Suburb-specific article/market link keys
    _article_keys = {"robina": "buy_robina", "burleigh_waters": "buy_burleigh", "varsity_lakes": "buy_varsity"}
    _market_keys = {"robina": "market_robina", "burleigh_waters": "market_burleigh", "varsity_lakes": "market_varsity"}

    # Market context for YoY trend
    market_ctx = get_market_context()
    ctx = market_ctx.get(suburb_key, {})

    msg = f"""{name} has {s['total']} houses for sale. Here's what that means if you're looking."""

    # YoY median trend
    if ctx.get("latest_median") and ctx.get("yoy_change_pct") is not None:
        direction = "up" if ctx["yoy_change_pct"] > 0 else "down"
        msg += f"\n\nThe median sale price has moved {direction} {abs(ctx['yoy_change_pct'])}% over the past year to {fmt_price(ctx['latest_median'])}."
        if ctx["yoy_change_pct"] > 5:
            msg += " Sellers have momentum. Buyers need to be realistic on price."
        elif ctx["yoy_change_pct"] < -2:
            msg += " That shift gives buyers more room to negotiate."
        else:
            msg += " Relatively steady — neither side has a clear edge on price."
    elif s.get("median_price"):
        msg += f"\n\nMedian asking price right now: {fmt_price(s['median_price'])} (range {fmt_price(s['min_price'])} to {fmt_price(s['max_price'])})."

    # Bedroom breakdown with competitive insight
    if s.get("beds"):
        most_common = max(s["beds"].items(), key=lambda x: x[1])
        total_beds = sum(s["beds"].values())
        bed_lines = []
        for bed_count in sorted(s["beds"].keys(), key=lambda x: int(x)):
            count = s["beds"][bed_count]
            bed_lines.append(f"  {bed_count}-bed: {count}")
        msg += "\n\n" + "\n".join(bed_lines)
        most_pct = round(most_common[1] / total_beds * 100)
        msg += f"\n\n{most_common[0]}-bed houses dominate ({most_pct}% of stock)."
        # Find scarce segments
        scarce = [(k, v) for k, v in s["beds"].items() if v > 0 and v <= 3]
        if scarce:
            sc = scarce[0]
            article = 'an' if sc[0] in ('8', '11', '18') else 'a'
            msg += f" If you want {article} {sc[0]}-bed, there {'is' if sc[1] == 1 else 'are'} only {sc[1]} — fewer options but less competition."

    # Market speed as advice
    if s.get("median_dom"):
        dom = s["median_dom"]
        msg += f"\n\nThe average house sells in {dom} days."
        if dom <= 30:
            msg += " If you see something you like at an open home this weekend, decide fast — this market doesn't wait."
        elif dom <= 60:
            msg += " You have a reasonable window, but the good ones still move quickly."
        else:
            msg += " Houses are sitting longer than usual. That's leverage for buyers — use it."

    # Valuation insight
    if s.get("underpriced_count") and s["underpriced_count"] > 0:
        total_valued = s.get("underpriced_count", 0) + s.get("overpriced_count", 0)
        msg += f"\n\n{s['underpriced_count']} of {total_valued} valued houses are priced below our estimate. Worth a closer look."

    # Close with article link
    buy_link = article_link(_article_keys.get(suburb_key, ""))
    market_link = article_link(_market_keys.get(suburb_key, ""))
    links = []
    if buy_link:
        links.append(buy_link)
    if market_link:
        links.append(market_link)
    if links:
        msg += f"\n\n{links[0]}"

    msg += f"\n\n{TAGLINE}"

    # Hero image — pick an underpriced or notable property from this suburb
    properties = get_individual_properties()
    suburb_props = [p for p in properties if p.get("_suburb_key") == suburb_key]
    hero_image = None
    # Prefer underpriced
    for p in suburb_props:
        vd = p.get("valuation_data", {}) or {}
        pos = (vd.get("summary") or {}).get("positioning")
        insuf = (vd.get("summary") or {}).get("insufficient_data", True)
        if not insuf and pos in ("underpriced", "good_value"):
            hero_image = _get_hero_image(p)
            if hero_image:
                break
    if not hero_image and suburb_props:
        hero_image = _get_hero_image(suburb_props[0])

    return msg, "suburb_snapshot", hero_image


def template_price_comparison(suburbs, **kw):
    """Side-by-side comparison: two houses at similar prices in different suburbs."""
    properties = get_individual_properties()

    # Build priced list per suburb
    suburb_priced = {}
    for key in CORE_SUBURBS:
        suburb_props = [p for p in properties if p.get("_suburb_key") == key]
        for p in suburb_props:
            pv = parse_price_value(p.get("price", ""))
            if pv and pv >= 300000:
                suburb_priced.setdefault(key, []).append((p, pv))

    # Need at least 2 suburbs with priced listings
    if len(suburb_priced) < 2:
        return None, None

    # Find the best pair: two properties from different suburbs within 10% of each other
    best_pair = None
    best_diff = float("inf")
    suburb_keys = list(suburb_priced.keys())

    for i, sk1 in enumerate(suburb_keys):
        for sk2 in suburb_keys[i+1:]:
            for p1, v1 in suburb_priced[sk1]:
                for p2, v2 in suburb_priced[sk2]:
                    pct_diff = abs(v1 - v2) / max(v1, v2) * 100
                    if pct_diff <= 10:
                        # Prefer pairs with good data (valuation + condition)
                        has_val = bool((p1.get("valuation_data") or {}).get("confidence")) and bool((p2.get("valuation_data") or {}).get("confidence"))
                        has_pvd = bool(p1.get("property_valuation_data")) and bool(p2.get("property_valuation_data"))
                        score = pct_diff - (20 if has_val else 0) - (10 if has_pvd else 0)
                        if score < best_diff:
                            best_diff = score
                            best_pair = (p1, v1, sk1, p2, v2, sk2)

    if not best_pair:
        return None, None

    p1, v1, sk1, p2, v2, sk2 = best_pair
    name1 = SUBURB_DISPLAY.get(sk1, sk1)
    name2 = SUBURB_DISPLAY.get(sk2, sk2)

    avg_price = (v1 + v2) / 2
    msg = f"Same budget, different suburbs. Here's what {fmt_price(round(avg_price / 50000) * 50000)} buys you right now.\n"

    # Build side-by-side for each property
    for idx, (p, pv, sk, name) in enumerate([(p1, v1, sk1, name1), (p2, v2, sk2, name2)]):
        addr = normalise_address(p)
        bed = p.get("bedrooms", "?")
        bath = p.get("bathrooms", "?")
        car = p.get("carspaces", "?")
        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")
        days = p.get("days_on_domain")

        specs = [f"{bed}bd {bath}ba"]
        if car:
            specs.append(f"{car}car")
        if lot:
            specs.append(f"{lot:.0f}sqm")
        spec_line = " · ".join(specs)

        msg += f"\n{'—' * 30}"
        msg += f"\n{name} — {addr}"
        msg += f"\n{fmt_price(pv)} · {spec_line}"

        # Value Drivers summary
        suburb_props = [pr for pr in properties if pr.get("_suburb_key") == sk]
        vd_section = _build_value_drivers_section(p, suburb_props)
        if vd_section:
            msg += f"\n{vd_section}"

        if isinstance(days, (int, float)):
            if days <= 7:
                msg += f"\nJust listed."
            elif days >= 45:
                msg += f"\n{int(days)} days on market — room to negotiate."

        # Property link
        prop_id = str(p.get("_id", ""))
        if prop_id:
            msg += f"\nFull report: fieldsestate.com.au/property/{prop_id}"

    msg += f"\n\n{'—' * 30}"
    msg += "\n\nSame money, different trade-offs. Which one works for your life?"

    msg += f"\n\n{TAGLINE}"

    # Hero image from the better-value property
    hero_image = _get_hero_image(p1) or _get_hero_image(p2)
    return msg, "price_comparison", hero_image


def template_listing_count(suburbs, **kw):
    """Total listings — framed as supply narrative with buyer/seller advice."""
    total = sum(s["total"] for s in suburbs.values())
    by_count = sorted(suburbs.items(), key=lambda x: -x[1]["total"])

    total_new = sum(s.get("new_this_week", 0) for s in suburbs.values())
    total_stale = sum(s.get("stale_listings", 0) for s in suburbs.values())
    total_underpriced = sum(s.get("underpriced_count", 0) for s in suburbs.values())

    msg = f"{total} houses across 3 suburbs. Is that a lot? Here's why it matters."

    # Supply narrative
    if total_new > 0 or total_stale > 0:
        msg += "\n\n"
        if total_new > 0:
            msg += f"{total_new} new listings this week"
        if total_new > 0 and total_stale > 0:
            msg += f", {total_stale} sitting 60+ days"
        elif total_stale > 0:
            msg += f"{total_stale} have been sitting 60+ days"
        msg += ". "
        # Interpret the supply signal
        if total_new > total_stale:
            msg += "The market is absorbing supply fast — fresh stock is outpacing stale listings."
        elif total_stale > total_new * 2:
            msg += "Stock is building up. Sellers who've been sitting are getting stale — that creates opportunity for buyers."
        else:
            msg += "Supply is steady. Not flooding, not drying up."

    # Per-suburb leverage advice
    most = by_count[0]
    least = by_count[-1] if by_count[-1][1]["total"] > 0 else by_count[-2]
    msg += "\n"
    for key, s in by_count:
        if s["total"] == 0:
            continue
        if s["total"] <= 10:
            msg += f"\n{s['display_name']} ({s['total']} houses): the seller has leverage here. If you're buying, bring a strong offer — don't lowball."
        elif s["total"] >= 20:
            msg += f"\n{s['display_name']} ({s['total']} houses): you have choices. Take your time, compare, and negotiate."
        else:
            msg += f"\n{s['display_name']} ({s['total']} houses): balanced market. Neither side has a clear upper hand."

    # Close with article link
    link = article_link("indicators")
    if link:
        msg += f"\n\n{link}"

    msg += f"\n\n{SELLER_CTA}"

    # Hero image — pick a property with the most days on market
    properties = get_individual_properties()
    hero_image = None
    if properties:
        hero_image = _get_hero_image(properties[0])

    return msg, "listing_count", hero_image


def template_bedroom_breakdown(suburbs, **kw):
    """Bedroom breakdown — framed as competition and price step-ups."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 5 and suburbs[s]["beds"]]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    # Suburb-specific market link keys
    _market_keys = {"robina": "market_robina", "burleigh_waters": "market_burleigh", "varsity_lakes": "market_varsity"}

    # Get properties to compute median price per bedroom count
    properties = get_individual_properties()
    suburb_props = [p for p in properties if p.get("_suburb_key") == suburb_key]

    total = sum(s["beds"].values())
    most_common = max(s["beds"].items(), key=lambda x: x[1])
    most_pct = round(most_common[1] / total * 100)

    # Build bed data with medians for step-up narrative
    bed_data = []
    for bed_count in sorted(s["beds"].keys(), key=lambda x: int(x)):
        count = s["beds"][bed_count]
        pct = round(count / total * 100)
        bed_prices = []
        for p in suburb_props:
            if str(p.get("bedrooms")) == bed_count:
                pv = parse_price_value(p.get("price", ""))
                if pv:
                    bed_prices.append(pv)
        bed_prices.sort()
        bed_median = bed_prices[len(bed_prices) // 2] if bed_prices else None
        bed_data.append({"beds": bed_count, "count": count, "pct": pct, "median": bed_median})

    msg = f"Looking for a {most_common[0]}-bed in {name}? Here's what you're competing for."

    # Listing with medians
    bd_lines = []
    for bd in bed_data:
        bdl = f"  {bd['beds']}-bed: {plural(bd['count'], 'house', 'houses')} ({bd['pct']}%)"
        if bd["median"]:
            bdl += f" — median {fmt_price(bd['median'])}"
        bd_lines.append(bdl)
    msg += "\n\n" + "\n".join(bd_lines)

    # Competition framing for dominant segment
    msg += f"\n\n{most_common[1]} of {total} houses are {most_common[0]}-bed ({most_pct}% of stock). That's the busiest segment — more buyers chasing the same listings."

    # Scarcity insight for smallest segment
    least_common = min(
        ((k, v) for k, v in s["beds"].items() if v > 0),
        key=lambda x: x[1],
    )
    if least_common[1] <= 3:
        house_word = "house" if least_common[1] == 1 else "houses"
        msg += f"\n\nOnly {least_common[1]} {least_common[0]}-bed {house_word}. If that's your size, the window is small — "
        if least_common[1] == 1:
            msg += "it could sell this week."
        else:
            msg += "both could sell this month."

    # Price step-up narrative
    priced_beds = [bd for bd in bed_data if bd["median"]]
    if len(priced_beds) >= 2:
        best_step = None
        best_ratio = 0
        for i in range(len(priced_beds) - 1):
            lower = priced_beds[i]
            upper = priced_beds[i + 1]
            if lower["median"] > 0:
                ratio = upper["median"] / lower["median"]
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_step = (lower, upper)

        if best_step:
            lo, hi = best_step
            gap = hi["median"] - lo["median"]
            if gap < 100000:
                msg += f"\n\nGoing from {lo['beds']}-bed ({fmt_price(lo['median'])}) to {hi['beds']}-bed ({fmt_price(hi['median'])}) costs almost nothing — {fmt_price(gap)} difference."
            elif gap > 500000:
                msg += f"\n\nThe jump from {lo['beds']}-bed ({fmt_price(lo['median'])}) to {hi['beds']}-bed ({fmt_price(hi['median'])}) is steep — {fmt_price(gap)} more. You're buying a fundamentally different house at that point."
            else:
                msg += f"\n\nStepping up from {lo['beds']}-bed ({fmt_price(lo['median'])}) to {hi['beds']}-bed ({fmt_price(hi['median'])}) adds {fmt_price(gap)}."

    # Close with suburb market metrics link
    market_link = article_link(_market_keys.get(suburb_key, ""))
    if market_link:
        msg += f"\n\n{market_link}"

    msg += f"\n\n{TAGLINE}"

    # Hero image from the dominant bedroom count in this suburb
    hero_image = None
    most_bed_count = most_common[0]
    for p in suburb_props:
        if str(p.get("bedrooms")) == most_bed_count:
            hero_image = _get_hero_image(p)
            if hero_image:
                break
    if not hero_image and suburb_props:
        hero_image = _get_hero_image(suburb_props[0])

    return msg, "bedroom_breakdown", hero_image


def template_seller_insight(suburbs, **kw):
    """Actionable insight for sellers — competition, market speed, and pricing intelligence."""
    candidates = [s for s in suburbs if suburbs[s]["priced_count"] >= 5]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    total = s["total"]

    msg = f"Thinking about selling in {name}? Before you list, here's what the data says about your competition."

    # Stock context with advice
    if total >= 40:
        msg += f"\n\nThere are {total} houses for sale right now. That's a lot of competition — your pricing strategy matters more than ever."
    elif total <= 15:
        msg += f"\n\nThere are {total} houses for sale right now. Limited stock works in your favour — but only if you price right."
    else:
        msg += f"\n\nThere are {total} houses for sale right now."

    # DOM as seller advice
    if s.get("median_dom"):
        dom = s["median_dom"]
        msg += f"\n\nThe median house sells in {dom} days."
        if dom <= 25:
            msg += " The market is absorbing stock quickly — well-priced homes are finding buyers."
        elif dom >= 40:
            msg += " Campaigns are dragging. The common mistake? Listing 10-15% above market and waiting for someone to meet you. They don't."
        else:
            msg += " Not fast, not slow — but the well-priced ones are moving noticeably quicker than the rest."

    # Stale listings as warning
    if s.get("stale_listings") and s["stale_listings"] > 0:
        msg += f"\n\n{s['stale_listings']} listings have been on the market 60+ days. The pattern is almost always the same: priced too high at launch, then a slow grind of price cuts. Don't be one of them."

    # Bedroom competition
    beds = s["beds"]
    if beds:
        most_bed = max(beds.items(), key=lambda x: x[1])
        most_pct = round(most_bed[1] / total * 100)
        msg += f"\n\n{most_bed[0]}-bed houses make up {most_pct}% of listings."
        others = [(k, v) for k, v in beds.items() if k != most_bed[0] and v > 0]
        if others:
            least_bed = min(others, key=lambda x: x[1])
            if least_bed[1] <= 5:
                msg += f" If yours is {'an' if least_bed[0] in ('8', '11', '18') else 'a'} {least_bed[0]}-bed, you have a smaller pool of competitors — that's an advantage."
            else:
                msg += f" If yours is a different size, your competitive set is smaller — use that."

    # Close with sell article
    sell_key = {"robina": "sell_robina", "burleigh_waters": "sell_burleigh", "varsity_lakes": "sell_varsity"}.get(suburb_key)
    link = article_link(sell_key) if sell_key else ""
    if link:
        msg += f"\n\nFull seller analysis for {name}: {link}"
    else:
        msg += "\n\nfieldsestate.com.au — independent property intelligence."

    msg += f"\n\n{SELLER_CTA}"

    # Hero image from a property in this suburb
    properties = get_individual_properties()
    suburb_props = [p for p in properties if p.get("_suburb_key") == suburb_key]
    hero_image = None
    if suburb_props:
        hero_image = _get_hero_image(suburb_props[0])

    return msg, "seller_insight", hero_image


def template_buyer_intelligence(suburbs, **kw):
    """Thursday evening — cross-suburb value comparison for a price bracket."""
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
                suburb_props = [p for p in properties if p.get("_suburb_key") == key]
                bracket_props = []
                for p in suburb_props:
                    pv = parse_price_value(p.get("price", ""))
                    if pv and low <= pv <= high:
                        bracket_props.append(p)

                dom_list = [p["days_on_domain"] for p in bracket_props if isinstance(p.get("days_on_domain"), (int, float))]
                dom_list.sort()
                bracket_median_dom = dom_list[len(dom_list) // 2] if dom_list else None

                results.append({
                    "name": s["display_name"],
                    "key": key,
                    "count": len(matches),
                    "min": min(matches),
                    "max": max(matches),
                    "median_dom": bracket_median_dom,
                    "bracket_props": bracket_props,
                })
        if len(results) >= 2:
            break
    else:
        return None, None

    results.sort(key=lambda x: -x["count"])

    msg = f"If your budget is {label}, here's what each suburb offers right now.\n"

    for r in results[:3]:
        msg += f"\n{r['name']}: {plural(r['count'], 'house', 'houses')} ({fmt_price(r['min'])} – {fmt_price(r['max'])})"
        if r["median_dom"]:
            if r["median_dom"] >= 45:
                msg += f"\nSelling in {r['median_dom']} days on average — slower market, more negotiation leverage."
            elif r["median_dom"] <= 25:
                msg += f"\nSelling in {r['median_dom']} days — fast-moving, don't wait for the second open home."
            else:
                msg += f"\nSelling in {r['median_dom']} days — time to inspect, but don't sit on a good one."

    # Find properties with extended days on market (negotiation opportunities)
    long_dom_props = []
    for r in results[:3]:
        for p in r["bracket_props"]:
            pv = parse_price_value(p.get("price", ""))
            dom = p.get("days_on_domain")
            if not pv or not isinstance(dom, (int, float)):
                continue
            if dom >= 45:
                long_dom_props.append((p, pv, dom, r["name"]))

    hero_image = None
    if long_dom_props:
        long_dom_props.sort(key=lambda x: -x[2])
        hero_image = _get_hero_image(long_dom_props[0][0])
        msg += "\n\nBeen sitting — room to negotiate:"
        for p, pv, dom, suburb_name in long_dom_props[:4]:
            addr = normalise_address(p)
            bed = p.get("bedrooms", "?")
            prop_id = str(p.get("_id", ""))
            msg += f"\n{addr}, {suburb_name} — {bed}bd, {fmt_price(pv)} — {int(dom)} days"
            if prop_id:
                msg += f"\nfieldsestate.com.au/property/{prop_id}"

    msg += "\n\nFull property reports with condition data, room sizes, and comparable sales at fieldsestate.com.au/for-sale"

    msg += f"\n\n{BUYER_CTA}"
    return msg, "buyer_intelligence", hero_image



def template_sold_preview(suburbs, properties=None, **kw):
    """Sunday evening — preview of what sold this weekend, full breakdown tomorrow."""
    sold_properties = get_recently_sold_properties()

    # Filter to last 3 days (weekend window: Fri-Sun)
    cutoff = datetime.now() - timedelta(days=3)
    weekend_sold = []
    for p in sold_properties:
        sold_dt = _parse_sold_date(p)
        if sold_dt and sold_dt >= cutoff:
            p["_sold_dt"] = sold_dt
            weekend_sold.append(p)

    # Dedup by address
    seen_addrs = {}
    for p in weekend_sold:
        addr = p.get("street_address", "")
        if addr not in seen_addrs or p.get("_sold_dt", datetime.min) > seen_addrs[addr].get("_sold_dt", datetime.min):
            seen_addrs[addr] = p
    weekend_sold = list(seen_addrs.values())

    # Count per suburb
    suburb_counts = {}
    for p in weekend_sold:
        key = p.get("_suburb_key", "unknown")
        display = p.get("_suburb_display", key.replace("_", " ").title())
        suburb_counts[key] = suburb_counts.get(key, {"count": 0, "display": display})
        suburb_counts[key]["count"] += 1

    total = len(weekend_sold)

    if total == 0:
        msg = "Quiet weekend — no confirmed sales yet across the southern Gold Coast."
        msg += "\n\nNo confirmed sales doesn't mean nothing happened — settlement reporting lags by days or weeks. Properties that exchanged this weekend may not appear in the data for a while."
        msg += "\n\nTomorrow morning: the full weekly breakdown — what each sold for, how long it took, and what it means for your suburb."
        msg += f"\n\n{BUYER_CTA}"
        # Still attach a property image for engagement
        active = get_individual_properties()
        hero = _get_hero_image(active[0]) if active else None
        return msg, "sold_preview", hero

    # Build suburb breakdown
    suburb_parts = []
    for key in ["robina", "varsity_lakes", "burleigh_waters"]:
        if key in suburb_counts:
            sc = suburb_counts[key]
            word = "sale" if sc["count"] == 1 else "sales"
            suburb_parts.append(f"{sc['display']}: {sc['count']} {word}")

    for key, sc in suburb_counts.items():
        if key not in ["robina", "varsity_lakes", "burleigh_waters"]:
            word = "sale" if sc["count"] == 1 else "sales"
            suburb_parts.append(f"{sc['display']}: {sc['count']} {word}")

    sale_word = "house sold" if total == 1 else "houses sold"
    msg = f"{total} {sale_word} this weekend across the southern Gold Coast."

    msg += f"\n\n{chr(10).join('  ' + s for s in suburb_parts)}"

    # Price range with narrative interpretation
    prices = []
    for p in weekend_sold:
        sp = p.get("sale_price")
        if sp:
            val = parse_price_value(str(sp))
            if val and val >= 200000:
                prices.append(val)

    if prices and len(prices) >= 2:
        low = min(prices)
        high = max(prices)
        msg += f"\n\nThe price range tells you something: {fmt_price(low)} to {fmt_price(high)}."
        if high > low * 2.5:
            msg += " Both ends of the market were active this weekend."
        elif low >= 1500000:
            msg += " Activity concentrated in the premium segment."
        elif high <= 1200000:
            msg += " The entry-level segment drove most of the activity."
        else:
            msg += " The middle of the market is where most of the action was."
    elif prices and len(prices) == 1:
        msg += f"\n\nSale price: {fmt_price(prices[0])}."

    msg += "\n\nTomorrow morning: the full breakdown — what each sold for, how long it took, and what it means for your suburb."

    msg += f"\n\n{BUYER_CTA}"

    # Hero image from the first sold property or fall back to active listing
    hero_image = None
    if weekend_sold:
        hero_image = _get_hero_image(weekend_sold[0])
    if not hero_image:
        active = get_individual_properties()
        if active:
            hero_image = _get_hero_image(active[0])

    return msg, "sold_preview", hero_image


def template_price_movement(suburbs, properties=None, **kw):
    """Stale and fresh listings reframed as two types of buyer opportunity."""
    if not properties:
        properties = get_individual_properties()

    # Get overall market DOM for context
    all_dom = [p.get("days_on_domain") for p in properties if isinstance(p.get("days_on_domain"), (int, float))]
    all_dom.sort()
    overall_median_dom = all_dom[len(all_dom) // 2] if all_dom else None

    # Split into stale (60+ days) and fresh (7 days or less)
    stale = []
    fresh = []
    for p in properties:
        dom = p.get("days_on_domain") or p.get("days_on_market")
        if not dom:
            continue
        if dom >= 60:
            stale.append(p)
        elif dom <= 7:
            fresh.append(p)

    stale.sort(key=lambda p: -(p.get("days_on_domain") or p.get("days_on_market", 0)))
    fresh.sort(key=lambda p: (p.get("days_on_domain") or p.get("days_on_market", 999)))

    if not stale and not fresh:
        return None, None

    msg = "Two types of opportunity in the market right now — properties where sellers may be ready to deal, and brand-new listings where you can be first.\n"

    # Stale listings section
    if stale:
        dom_context = f" In a market where the average house sells in {overall_median_dom} days, that's a signal." if overall_median_dom else ""
        msg += f"\nThese have been sitting 60+ days.{dom_context} Either the price is wrong, the marketing hasn't found the right buyer, or both. Either way, there's room to negotiate.\n"

        for p in stale[:5]:
            address = normalise_address(p)
            dom = p.get("days_on_domain") or p.get("days_on_market", 0)
            price_str = p.get("price", "")
            price_val = parse_price_value(str(price_str)) if price_str else None

            line = f"\n{address} — {dom} days"
            if price_val and price_val >= 200000:
                line += f" — {fmt_price(price_val)}"

            # Extended DOM as negotiation signal
            if dom >= 90:
                line += f"\n  {dom} days and counting. The longer it sits, the more flexible the seller becomes."
            elif dom >= 60:
                line += f"\n  {dom} days on market — that's well beyond the typical selling window. There's room to negotiate."

            msg += line

    # Fresh listings section
    if fresh:
        msg += "\n"
        msg += f"\n{plural(len(fresh), 'new listing')} this week. First open homes draw the biggest crowds and the best offers tend to come early.\n"

        for p in fresh[:5]:
            address = normalise_address(p)
            price_str = p.get("price", "")
            price_val = parse_price_value(str(price_str)) if price_str else None
            beds = p.get("bedrooms", "")
            suburb = p.get("_suburb_display", "")

            line = f"\n{address}"
            if suburb:
                line += f", {suburb}"
            if beds:
                line += f" — {beds}-bed"
            if price_val and price_val >= 200000:
                line += f" — {fmt_price(price_val)}"

            msg += line

    # Close with link
    suburb_counts = {}
    for p in (stale[:5] + fresh[:5]):
        sk = p.get("_suburb_key", "")
        suburb_counts[sk] = suburb_counts.get(sk, 0) + 1
    most_common = max(suburb_counts, key=suburb_counts.get) if suburb_counts else None
    buy_key = {"robina": "buy_robina", "varsity_lakes": "buy_varsity", "burleigh_waters": "buy_burleigh"}.get(most_common)
    link = article_link(buy_key) if buy_key else ""
    if link:
        msg += f"\n\nFull analysis: {link}"
    msg += "\n\nfieldsestate.com.au/for-sale — every listing with days on market, price history, and suburb data."

    msg += f"\n\n{TAGLINE}"

    # Hero image — prefer the top stale listing (negotiation angle), fall back to fresh
    hero_image = None
    if stale:
        hero_image = _get_hero_image(stale[0])
    if not hero_image and fresh:
        hero_image = _get_hero_image(fresh[0])

    return msg, "price_movement", hero_image



# ── PROPERTY TEMPLATES (individual property posts) ───────────────────────

def template_open_home_spotlight(suburbs, properties=None, **kw):
    """Individual property spotlight — intelligence reframed as reasons to act."""
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
        score = sum(3 - pri for pri, _ in intel[:3])
        price_val = parse_price_value(p.get("price", ""))
        scored.append((p, intel, score, price_val))

    scored.sort(key=lambda x: -x[2])
    top = scored[:3]
    prop, intel, _, price_val = random.choice(top) if top else (None, [], 0, None)
    if not prop:
        return None, None

    suburb = prop["_suburb_display"]
    suburb_key = prop.get("_suburb_key", "")
    insp = prop["_inspections"][0]
    bed = prop.get("bedrooms", "?")
    bath = prop.get("bathrooms", "?")
    days = prop.get("days_on_domain")
    address = normalise_address(prop)
    lot = prop.get("lot_size_sqm") or (prop.get("enriched_data") or {}).get("lot_size_sqm")

    # Property card (the hook)
    specs = [f"{bed}-bed", f"{bath}-bath"]
    car = prop.get("carspaces")
    if car:
        specs.append(f"{car}-car")
    if lot:
        specs.append(f"{lot:.0f}sqm")
    spec_line = " · ".join(specs)

    msg = f"{address}, {suburb}\n{spec_line} — {clean_price_display(prop.get('price', ''))}\nOpen {insp['day']} at {insp['start']}\n"

    # Value Drivers — strengths and trade-offs
    suburb_props = [p for p in properties if p.get("_suburb_key") == suburb_key]
    vd_section = _build_value_drivers_section(prop, suburb_props)
    if vd_section:
        msg += f"\n{vd_section}"

    # DOM context as advice
    if isinstance(days, (int, float)):
        if days <= 3:
            msg += "\nJust listed — first open homes attract the most serious buyers."
        elif days <= 7:
            msg += "\nFirst week on market."
        elif days >= 60:
            msg += f"\n{int(days)} days on market — the seller may be more flexible than you think."
        elif days >= 45:
            msg += f"\n{int(days)} days on market — there may be room to negotiate."

    # Property link
    prop_id = str(prop.get("_id", ""))
    if prop_id:
        msg += f"\n\nFull report: fieldsestate.com.au/property/{prop_id}"
    else:
        msg += "\n\nfieldsestate.com.au/for-sale"

    msg += f"\n\n{TAGLINE}"
    hero = _get_hero_image(prop)
    return msg, "open_home_spotlight", hero



def template_entry_price_watch(suburbs, properties=None, **kw):
    """The cheapest house per suburb -- framed as trade-offs and buyer advice."""
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

    entries.sort(key=lambda e: e["price_val"])

    msg = "What's the absolute cheapest way into each suburb right now? These are the floor prices — when they sell, they reset what 'affordable' means.\n"

    for e in entries:
        p = e["prop"]
        bed = p.get("bedrooms", "?")
        bath = p.get("bathrooms", "?")
        addr = normalise_address(p)
        days = p.get("days_on_domain")
        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")

        lot_note = f" on {lot:.0f}sqm" if lot else ""
        msg += f"\n{e['suburb']} at {fmt_price(e['price_val'])} — {addr}. {bed}-bed {bath}-bath{lot_note}."

        # Frame as trade-off with specific condition data
        if e["median"]:
            pct_below = round((1 - e["price_val"] / e["median"]) * 100)
            if pct_below >= 10:
                tradeoff_note = _get_condition_tradeoffs(p)
                if pct_below >= 20:
                    if tradeoff_note:
                        msg += f" That's {pct_below}% below the suburb median. {tradeoff_note}"
                    else:
                        msg += f" That's {pct_below}% below the suburb median — worth investigating what's behind that discount."
                else:
                    if tradeoff_note:
                        msg += f" {pct_below}% under the median. {tradeoff_note}"
                    else:
                        msg += f" {pct_below}% under the median — entry-level price, check the details on-site."

        # DOM as leverage
        if isinstance(days, (int, float)) and days >= 45:
            msg += f" {days} days on market means the seller has been waiting. That's your leverage."
        elif isinstance(days, (int, float)) and days <= 7:
            msg += " Just listed — be early if the numbers work for you."

    # Close with article link for cheapest suburb
    cheapest = entries[0]
    buy_key = {"robina": "buy_robina", "varsity_lakes": "buy_varsity", "burleigh_waters": "buy_burleigh"}.get(cheapest["suburb_key"])
    link = article_link(buy_key) if buy_key else ""
    if link:
        msg += f"\n\nFull suburb breakdown: {link}"
    else:
        msg += "\n\nfieldsestate.com.au/for-sale — every house with days on market, price history, and suburb data."

    msg += f"\n\n{BUYER_CTA}"

    # Hero image — pick the entry with most reasons to click (below valuation, or best condition)
    best_hero = None
    for e in entries:
        p = e["prop"]
        vd = p.get("valuation_data", {}) or {}
        reconciled = (vd.get("confidence") or {}).get("reconciled_valuation")
        insufficient = (vd.get("summary") or {}).get("insufficient_data", True)
        if reconciled and not insufficient and e["price_val"] < reconciled:
            best_hero = p
            break
    if not best_hero:
        best_hero = entries[0]["prop"]
    hero_image = _get_hero_image(best_hero)

    return msg, "entry_price_watch", hero_image



def template_median_showcase(suburbs, properties=None, **kw):
    """What does median money buy? The house that defines 'average' with YoY context."""
    if not properties:
        properties = get_individual_properties()

    mkt = get_market_context()

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

    msg = f"Half the houses in {suburb_name} are above {fmt_price(median)}. Half below. This is the one sitting right on the line — and it tells you exactly what 'average' costs here.\n"
    msg += f"\n{address}\n{spec_line}\n{clean_price_display(prop.get('price', ''))}{insp_line}\n"

    # Value Drivers summary — what you get for median money
    vd_section = _build_value_drivers_section(prop, suburb_props)
    if vd_section:
        msg += f"\n{vd_section}"

    # YoY median context from market data
    suburb_mkt = mkt.get(suburb_key, {})
    yoy = suburb_mkt.get("yoy_change_pct")
    if yoy is not None:
        if abs(yoy) < 2:
            msg += f"\n\nA year ago, the median was roughly the same. Steady — but 'average' hasn't moved much, which means buyers have time to be selective."
        elif yoy > 0:
            msg += f"\n\nA year ago, the median was {abs(yoy):.1f}% lower. That context matters — 'average' keeps moving, and this is where it sits today."
        else:
            msg += f"\n\nA year ago, the median was {abs(yoy):.1f}% higher. The market has softened — what felt expensive a year ago is closer to the norm now."

    # Intelligence insight
    intel = property_intel(prop, suburbs, properties)
    non_timing = [(pri, t) for pri, t in intel if "Brand new" not in t and "Fresh to" not in t]
    if non_timing:
        msg += f"\n\n{non_timing[0][1]}"

    # Buyer advice
    msg += f"\n\nIf this house feels like good value, anything below it is worth a closer look. If it feels overpriced, adjust your expectations — the market has moved."

    # Property link + market data link
    prop_id = str(prop.get("_id", ""))
    if prop_id:
        msg += f"\n\nFull report: fieldsestate.com.au/property/{prop_id}"

    market_key = {"robina": "market_robina", "varsity_lakes": "market_varsity", "burleigh_waters": "market_burleigh"}.get(suburb_key)
    link = article_link(market_key) if market_key else ""
    if link:
        msg += f"\n{suburb_name} market data: {link}"

    msg += f"\n\n{SELLER_CTA}"

    hero = _get_hero_image(prop)
    return msg, "median_showcase", hero



def template_weekend_preview(suburbs, properties=None, **kw):
    """Friday post — top 4 open homes worth seeing this weekend, with reasons."""
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

    # Score every property
    scored = []
    for p in all_weekend:
        pv = parse_price_value(p.get("price", ""))
        vd = p.get("valuation_data", {}) or {}
        reconciled = (vd.get("confidence") or {}).get("reconciled_valuation")
        insufficient = (vd.get("summary") or {}).get("insufficient_data", True)
        pvd = p.get("property_valuation_data", {}) or {}
        overall = (pvd.get("condition_summary") or {}).get("overall_score")
        days = p.get("days_on_domain")

        score = 0
        reasons = []

        if overall and overall >= 8:
            score += 15
            kitchen = pvd.get("kitchen", {}) or {}
            bench = kitchen.get("benchtop_material", "")
            island = kitchen.get("island_bench")
            outdoor = pvd.get("outdoor", {}) or {}
            extras = []
            if bench and bench.lower() in ("stone", "marble", "granite", "quartz", "engineered stone"):
                extras.append(f"{bench.lower()} kitchen")
            if island:
                extras.append("island bench")
            if outdoor.get("pool_present"):
                extras.append("pool")
            cond = f"Condition {overall}/10"
            if extras:
                cond += f" — {', '.join(extras)}"
            reasons.append(cond)
        elif overall and overall <= 5:
            reasons.append(f"Condition {overall}/10 — renovation upside")

        if isinstance(days, (int, float)) and days >= 60:
            score += 10
            reasons.append(f"{int(days)} days on market — seller may be ready to deal")
        elif isinstance(days, (int, float)) and days <= 3:
            score += 10
            reasons.append("Just listed — first open home")

        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")
        if lot and lot >= 800:
            score += 5
            reasons.append(f"{lot:.0f}sqm lot")

        scored.append((p, pv, score, reasons))

    scored.sort(key=lambda x: -x[2])

    # Pick top 4 with suburb diversity
    picks = []
    seen_suburbs = {}
    for p, pv, score, reasons in scored:
        sk = p.get("_suburb_key", "")
        if seen_suburbs.get(sk, 0) >= 2:
            continue
        seen_suburbs[sk] = seen_suburbs.get(sk, 0) + 1
        picks.append((p, pv, reasons))
        if len(picks) >= 4:
            break

    if len(picks) < 3:
        for p, pv, score, reasons in scored:
            if all(str(p.get("_id")) != str(pk[0].get("_id")) for pk in picks):
                picks.append((p, pv, reasons))
                if len(picks) >= 4:
                    break

    hero_image = _get_hero_image(picks[0][0]) if picks else None

    msg = f"{total_weekend} houses open this weekend. These {len(picks)} are the ones we'd walk through first.\n"

    for prop, pv, reasons in picks:
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

        msg += f"\n{addr}, {suburb}"
        msg += f"\n{' · '.join(specs)} — {price_str} — Open {insp['day']} {insp['start']}"
        display_reasons = [r for r in reasons if "sqm lot" not in r]
        if display_reasons:
            msg += f"\n{'. '.join(display_reasons)}."
        prop_id = str(prop.get("_id", ""))
        if prop_id:
            msg += f"\nfieldsestate.com.au/property/{prop_id}"
        msg += "\n"

    remaining = total_weekend - len(picks)
    if remaining > 0:
        msg += f"\n{remaining} more open this weekend — full list at fieldsestate.com.au/for-sale"

    msg += f"\n\n{BUYER_CTA}"
    return msg, "weekend_preview", hero_image



def template_saturday_open_list(suburbs, properties=None, **kw):
    """Saturday 6am — today's top open homes with reasons, link to full list."""
    if not properties:
        properties = get_individual_properties()

    sat_props = get_properties_for_day(properties, "Saturday")

    if not sat_props:
        return None, None

    # Score every property for top picks
    scored_picks = []
    for p in sat_props:
        pv = parse_price_value(p.get("price", ""))
        vd = p.get("valuation_data", {}) or {}
        reconciled = (vd.get("confidence") or {}).get("reconciled_valuation")
        insufficient = (vd.get("summary") or {}).get("insufficient_data", True)
        pvd = p.get("property_valuation_data", {}) or {}
        overall = (pvd.get("condition_summary") or {}).get("overall_score")
        days = p.get("days_on_domain")

        score = 0
        reasons = []

        if overall and overall >= 8:
            score += 15
            kitchen = pvd.get("kitchen", {}) or {}
            bench = kitchen.get("benchtop_material", "")
            island = kitchen.get("island_bench")
            outdoor_data = pvd.get("outdoor", {}) or {}
            extras = []
            if bench and bench.lower() in ("stone", "marble", "granite", "quartz", "engineered stone"):
                extras.append(bench.lower() + " kitchen")
            if island:
                extras.append("island bench")
            if outdoor_data.get("pool_present"):
                extras.append("pool")
            cond = f"Condition {overall}/10"
            if extras:
                cond += f" — {', '.join(extras)}"
            reasons.append(cond)
        elif overall and overall <= 5:
            score += 5
            reasons.append(f"Condition {overall}/10 — renovation upside")

        if isinstance(days, (int, float)) and days >= 60:
            score += 10
            reasons.append(f"{int(days)} days on market — room to negotiate")
        elif isinstance(days, (int, float)) and days <= 3:
            score += 10
            reasons.append("Just listed — first open home")

        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")
        if lot and lot >= 800:
            score += 5
            reasons.append(f"{lot:.0f}sqm lot")

        if reasons:
            scored_picks.append((p, pv, score, reasons))

    scored_picks.sort(key=lambda x: -x[2])

    # Pick top 4 with suburb diversity
    top_picks = []
    seen_suburbs = {}
    for p, pv, score, reasons in scored_picks:
        sk = p.get("_suburb_key", "")
        if seen_suburbs.get(sk, 0) >= 2:
            continue
        seen_suburbs[sk] = seen_suburbs.get(sk, 0) + 1
        top_picks.append((p, pv, reasons))
        if len(top_picks) >= 4:
            break

    # Unique count
    unique_addrs = set()
    for p in sat_props:
        addr = normalise_address(p)
        if addr:
            unique_addrs.add(addr)
    unique_count = len(unique_addrs)
    suburb_count = len(set(p["_suburb_display"] for p in sat_props))

    hero_image = _get_hero_image(top_picks[0][0]) if top_picks else None

    msg = f"Your open home list for today. {unique_count} houses across {suburb_count} suburbs."

    if top_picks:
        msg += f"\n\nIf you only have time for a few, these are the ones we'd prioritise:\n"

        for p, pv, reasons in top_picks:
            addr = normalise_address(p)
            suburb = p["_suburb_display"]
            bed = p.get("bedrooms", "?")
            bath = p.get("bathrooms", "?")
            lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")
            insp = p["_inspections"][0]
            price_str = clean_price_display(p.get("price", ""))
            specs = [f"{bed}bd {bath}ba"]
            if lot:
                specs.append(f"{lot:.0f}sqm")

            display_reasons = [r for r in reasons if "sqm lot" not in r]

            msg += f"\n{addr}, {suburb}"
            msg += f"\n{' · '.join(specs)} — {price_str} — {insp['start']}"
            if display_reasons:
                msg += f"\n{'. '.join(display_reasons)}."
            prop_id = str(p.get("_id", ""))
            if prop_id:
                msg += f"\nfieldsestate.com.au/property/{prop_id}"
            msg += "\n"

    remaining = unique_count - len(top_picks)
    if remaining > 0:
        msg += f"\n{remaining} more open today — full list with times and prices at fieldsestate.com.au/for-sale"

    msg += f"\n\n{TAGLINE}"
    return msg, "saturday_open_list", hero_image


def _get_forward_impact(sold_prop, suburb_key):
    """Find active listings that use this sold property as a valuation comparable.
    Returns list of dicts with address, reconciled_valuation, bedrooms."""
    sold_id = str(sold_prop.get("_id", ""))
    if not sold_id:
        return []
    try:
        client = MongoClient(COSMOS_URI)
        db = client["Gold_Coast"]
        matches = list(query_with_retry(db[suburb_key], {
            "listing_status": "for_sale",
            "property_type": {"$in": ["House", "house"]},
            "valuation_data.recent_sales.id": sold_id
        }, {
            "street_address": 1, "address": 1, "bedrooms": 1, "price": 1,
            "valuation_data.confidence.reconciled_valuation": 1,
        }))
        client.close()
        return matches
    except Exception:
        return []


def _get_bedroom_median(active_properties, suburb_key, bedrooms):
    """Get median asking price for a specific bedroom count in a suburb from active listings."""
    if not bedrooms or not active_properties:
        return None
    prices = []
    for p in active_properties:
        if p.get("_suburb_key") == suburb_key and p.get("bedrooms") == bedrooms:
            val = parse_price_value(p.get("price", ""))
            if val:
                prices.append(val)
    if len(prices) >= 3:
        prices.sort()
        return prices[len(prices) // 2]
    return None


def _find_active_comparables(active_properties, sold_prop, sale_val):
    """Find active listings in same suburb with same bed count and similar price."""
    suburb_key = sold_prop.get("_suburb_key", "")
    bed = sold_prop.get("bedrooms")
    if not suburb_key or not bed or not sale_val:
        return []
    matches = []
    for p in active_properties:
        if p.get("_suburb_key") != suburb_key or p.get("bedrooms") != bed:
            continue
        asking = parse_price_value(p.get("price", ""))
        if not asking:
            continue
        # Within 25% of sale price
        if abs(asking - sale_val) / sale_val <= 0.25:
            matches.append(p)
    return matches


def _format_top_comps(p, n=3):
    """Format the top N valuation comparables for a property as a short text block.
    Returns (text, has_adjusted) tuple. text is empty string if no comps available.
    has_adjusted is True if any comp has an adjusted price (needs footnote)."""
    from bson import ObjectId
    vd = p.get("valuation_data") or {}
    rs = vd.get("recent_sales", [])
    if not rs:
        return "", False

    included = [r for r in rs if r.get("included_in_valuation")]
    if not included:
        return "", False
    included.sort(key=lambda r: (r.get("weight") or {}).get("raw_weight", 0), reverse=True)

    suburb_key = p.get("_suburb_key", "")
    suburbs_to_check = [suburb_key] if suburb_key else []
    # Also check neighbouring suburbs
    for s in CORE_SUBURBS:
        if s != suburb_key and s not in suburbs_to_check:
            suburbs_to_check.append(s)

    try:
        client = MongoClient(COSMOS_URI)
        db = client["Gold_Coast"]
        comp_lines = []
        has_adjusted = False
        for r in included[:n]:
            comp_id = r.get("id")
            sale_price = r.get("price")
            adj_price = (r.get("adjustment_result") or {}).get("adjusted_price")
            if not comp_id or not sale_price:
                continue

            # Resolve address from DB
            addr = None
            for s in suburbs_to_check:
                try:
                    sold_doc = db[s].find_one({"_id": ObjectId(comp_id)}, {"street_address": 1, "address": 1})
                    if sold_doc:
                        addr = sold_doc.get("street_address") or sold_doc.get("address")
                        break
                except Exception:
                    continue
            if not addr:
                continue
            # Clean address: strip suburb/state/postcode suffix, fix double spaces
            import re
            addr = re.sub(r',?\s*(Robina|Burleigh\s*Waters|Varsity\s*Lakes|Burleigh\s*Heads|Mudgeeraba|Reedy\s*Creek|Merrimac|Worongary|Carrara)\b.*$', '', addr, flags=re.IGNORECASE).strip()
            addr = re.sub(r'\s+', ' ', addr)

            if adj_price:
                comp_lines.append(f"{addr} (sold {fmt_price(int(sale_price))}, {fmt_price(int(adj_price))}*)")
                has_adjusted = True
            else:
                comp_lines.append(f"{addr} (sold {fmt_price(int(sale_price))})")

        client.close()
        if comp_lines:
            return "Valuation comparables: " + " · ".join(comp_lines), has_adjusted
    except Exception:
        pass
    return "", False


def _sold_insight(p, all_sold, active_properties=None):
    """Generate specific insights for one sold property — backward-looking data
    translated into forward-looking advice for buyers."""
    address = p.get("street_address", "")
    sale_price = p.get("sale_price", "")
    sale_val = parse_price_value(str(sale_price)) if sale_price else None
    listing_price = p.get("listing_price", "")
    list_val = parse_price_value(str(listing_price)) if listing_price else None
    days = p.get("days_on_market")
    bed = p.get("bedrooms")
    suburb = p.get("_suburb_display", "")
    suburb_key = p.get("_suburb_key", "")
    ed = p.get("enriched_data") or {}
    lot = ed.get("lot_size_sqm")
    floor = ed.get("floor_area_sqm")
    if not floor:
        fp = p.get("floor_plan_analysis", {})
        floor = fp.get("internal_floor_area", {}).get("value") if fp else None
    txns = ed.get("transactions", [])
    pi = p.get("property_insights", {})
    active_properties = active_properties or []

    # Priority-ordered insights — we'll pick the best 2-3
    high = []   # Most compelling
    medium = []  # Good context
    low = []     # Fallback

    # 1. Speed of sale (high impact — people notice fast/slow sales)
    if days is not None:
        all_days = [s.get("days_on_market") for s in all_sold if s.get("days_on_market")]
        avg_days = sum(all_days) / len(all_days) if all_days else 25
        if days <= 5:
            high.append(f"Sold in just {days} days — if you're watching a similar property, don't wait.")
        elif days <= 10 and avg_days > 20:
            high.append(f"Sold in {days} days, well under the {avg_days:.0f}-day average. Well-priced homes don't last here.")
        elif days >= 45:
            medium.append(f"Took {days} days — the seller may have had to adjust expectations. If you see similar DOM on a listing you like, there could be room to negotiate.")

    # 3. Bedroom median comparison (medium — contextualises the sale price)
    if sale_val and bed:
        bed_median = _get_bedroom_median(active_properties, suburb_key, bed)
        if bed_median:
            diff_pct = (sale_val - bed_median) / bed_median * 100
            if diff_pct <= -15:
                medium.append(f"Sold {abs(diff_pct):.0f}% below the current {bed}-bed median of {fmt_price(int(bed_median))} — could shift what 'affordable' looks like for {bed}-beds in {suburb}.")
            elif diff_pct >= 15:
                medium.append(f"Sold {diff_pct:.0f}% above the current {bed}-bed median of {fmt_price(int(bed_median))} — may push the benchmark up for similar homes.")
            elif abs(diff_pct) <= 5:
                medium.append(f"Right on the {bed}-bed median of {fmt_price(int(bed_median))} — textbook market-rate sale.")

    # 4. Forward impact — active listings using this sale as a comparable (highest impact for buyers)
    forward_matches = _get_forward_impact(p, suburb_key)
    if forward_matches:
        n = len(forward_matches)
        # Determine directional influence on valuations
        match_vals = [(m.get("valuation_data") or {}).get("confidence", {}).get("reconciled_valuation") for m in forward_matches]
        match_vals = [v for v in match_vals if v]
        if match_vals and sale_val:
            avg_val = sum(match_vals) / len(match_vals)
            direction = " lower" if sale_val < avg_val else " higher" if sale_val > avg_val else ""
        else:
            direction = ""
        # Pick the most notable one to mention
        named = []
        for m in forward_matches[:3]:
            maddr = normalise_address(m)
            if maddr:
                named.append(maddr)
        if named:
            if n == 1:
                high.append(f"This sale is a direct comparable for {named[0]} — it sets the benchmark{direction} for that listing.")
            elif n <= 3:
                high.append(f"This sale is a comp for {n} active listings including {named[0]}. It could shift expectations{direction}.")
            else:
                high.append(f"This sale is a comp for {n} active listings including {named[0]}. It could reprice a portion of the market{direction}.")

    # 5. Active comparable callout (medium — what's still available, with direction)
    if sale_val and active_properties:
        similar = _find_active_comparables(active_properties, p, sale_val)
        if similar and not forward_matches:  # Don't double up with forward impact
            # Determine directional influence
            sim_prices = [parse_price_value(s.get("price", "")) for s in similar]
            sim_prices = [sp for sp in sim_prices if sp]
            if sim_prices:
                sim_median = sorted(sim_prices)[len(sim_prices) // 2]
                direction = " lower" if sale_val < sim_median else " higher" if sale_val > sim_median else ""
            else:
                direction = ""
            n = len(similar)
            if n == 1:
                sim_addr = normalise_address(similar[0])
                if sim_addr:
                    medium.append(f"1 similar {bed}-bed still on market: {sim_addr}. This sale could reset its pricing benchmark{direction}.")
            elif n >= 2:
                medium.append(f"{n} similar {bed}-beds still on market in {suburb}. This sale could reset their pricing benchmark{direction}.")

    # 6. Prior transaction history / capital gain
    if txns and sale_val:
        prior_sales = [t for t in txns if t.get("price") and t.get("price") < sale_val * 0.95]
        if prior_sales:
            last = prior_sales[-1]
            prior_price = last.get("price", 0)
            prior_date = str(last.get("date", ""))[:4]
            if prior_price > 0 and prior_date:
                gain_pct = (sale_val - prior_price) / prior_price * 100
                medium.append(f"Last sold in {prior_date} for {fmt_price(int(prior_price))} — {gain_pct:.0f}% growth. That's the kind of equity this suburb builds.")

    # 7. Listing vs sale price gap
    if sale_val and list_val and list_val > 0:
        gap_pct = (sale_val - list_val) / list_val * 100
        if gap_pct >= 5:
            medium.append(f"Sold {abs(gap_pct):.0f}% above asking — multiple buyers competed for this one.")
        elif gap_pct <= -5:
            medium.append(f"Sold {abs(gap_pct):.0f}% below asking — the seller started too high. A lesson for overpriced listings.")

    # 8. Rarity / percentile
    if pi:
        beds_pi = pi.get("bedrooms", {})
        sc = beds_pi.get("suburbComparison", {})
        pctl = sc.get("percentile")
        if pctl and pctl >= 85 and bed:
            low.append(f"{bed}-bed houses are top {100-pctl}% for size in {suburb} — rare stock that rarely comes up.")

    # 9. $/sqm (fallback)
    if lot and sale_val:
        price_per_sqm_land = sale_val / lot
        low.append(f"{lot:.0f}sqm lot at {fmt_price(int(price_per_sqm_land))}/sqm of land.")
    elif floor and sale_val:
        price_per_sqm_floor = sale_val / floor
        low.append(f"{floor:.0f}sqm internal at {fmt_price(int(price_per_sqm_floor))}/sqm of living space.")

    # Return best insights: up to 2 high, then fill with medium, fallback to low
    result = []
    for h in high[:2]:
        result.append(h)
    for m in medium:
        if len(result) >= 3:
            break
        result.append(m)
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
    """Monday morning — what sold last week, narrative with top sales and market context."""
    sold_properties = get_recently_sold_properties()
    mkt = get_market_context()

    if not sold_properties:
        msg = "No confirmed house sales last week across Robina, Burleigh Waters or Varsity Lakes."
        msg += "\n\nThat doesn't mean nothing happened — settlement reporting lags by days or weeks. We'll publish them as soon as they land."
        msg += "\n\nFull suburb breakdowns updated daily at fieldsestate.com.au/for-sale"
        active = get_individual_properties()
        hero = _get_hero_image(active[0]) if active else None
        return msg, "sold_results", hero

    # Filter to last 7 days only
    cutoff = datetime.now() - timedelta(days=7)
    time_filtered = []
    for p in sold_properties:
        sold_dt = _parse_sold_date(p)
        if sold_dt and sold_dt >= cutoff:
            p["_sold_dt"] = sold_dt
            time_filtered.append(p)

    # Dedup by address
    seen_addrs = {}
    for p in time_filtered:
        addr = normalise_address(p)
        if not addr:
            seen_addrs[id(p)] = p
        elif addr not in seen_addrs:
            seen_addrs[addr] = p
        else:
            existing = seen_addrs[addr]
            if p.get("_sold_dt", datetime.min) > existing.get("_sold_dt", datetime.min):
                seen_addrs[addr] = p
    valid_sold = list(seen_addrs.values())
    valid_sold.sort(key=lambda p: p.get("_sold_dt", datetime.min), reverse=True)

    # Group by suburb
    suburb_order = [("robina", "Robina"), ("varsity_lakes", "Varsity Lakes"), ("burleigh_waters", "Burleigh Waters")]
    by_suburb = {}
    for p in valid_sold:
        by_suburb.setdefault(p.get("_suburb_key", ""), []).append(p)

    total = len(valid_sold)
    if total == 0:
        msg = "No confirmed house sales last week. We'll publish them as soon as settlement data comes through."
        active = get_individual_properties()
        hero = _get_hero_image(active[0]) if active else None
        return msg, "sold_results", hero

    busiest_key = max(by_suburb, key=lambda k: len(by_suburb[k]))
    busiest_display = SUBURB_DISPLAY.get(busiest_key, busiest_key.replace("_", " ").title())
    quiet_suburbs = [d for k, d in suburb_order if len(by_suburb.get(k, [])) == 0]

    sale_prices = []
    fast_sales = []
    slow_sales = []
    for p in valid_sold:
        sp = parse_price_value(str(p.get("sale_price", "")))
        if sp and sp >= 200000:
            sale_prices.append(sp)
        dom = p.get("days_on_market")
        if dom is not None:
            if dom <= 14:
                fast_sales.append(p)
            elif dom >= 45:
                slow_sales.append(p)

    msg = f"{plural(total, 'house')} sold last week — here's what it tells you.\n"

    # Suburb breakdown
    counts = [f"{len(by_suburb.get(k, []))} in {d}" for k, d in suburb_order if by_suburb.get(k)]
    if counts:
        msg += f"\n{', '.join(counts)}."
    if quiet_suburbs:
        msg += f" Nothing traded in {' or '.join(quiet_suburbs)}."

    # Speed narrative
    if fast_sales and slow_sales:
        fast_addr = normalise_address(fast_sales[0])
        slow_addr = normalise_address(slow_sales[0])
        msg += f"\n\nFastest: {fast_addr} ({fast_sales[0].get('days_on_market', 0)} days). Slowest: {slow_addr} ({slow_sales[0].get('days_on_market', 0)} days). That gap is pricing — the ones priced right sell before most buyers see them."
    elif fast_sales:
        fast_addr = normalise_address(fast_sales[0])
        msg += f"\n\n{fast_addr} sold in {fast_sales[0].get('days_on_market', 0)} days. Well-priced houses here don't last."
    elif slow_sales:
        slow_addr = normalise_address(slow_sales[0])
        msg += f"\n\n{slow_addr} took {slow_sales[0].get('days_on_market', 0)} days. That's your negotiation leverage."

    # Top 3-4 sales with key context
    msg += "\n"
    shown = 0
    for p in valid_sold[:4]:
        address = normalise_address(p)
        sale_price = p.get("sale_price", "")
        sale_val = parse_price_value(str(sale_price)) if sale_price else None
        days = p.get("days_on_market")
        bed = p.get("bedrooms", "?")
        suburb = p.get("_suburb_display", "")

        if sale_val:
            price_str = fmt_price(sale_val)
        elif sale_price and str(sale_price).strip() and str(sale_price).strip().lower() != "none":
            price_str = clean_price_display(str(sale_price))
        else:
            price_str = "price undisclosed"
        dom_str = f" · {days} days" if days else ""

        msg += f"\n{address}, {suburb} — {bed}bd, {price_str}{dom_str}"
        shown += 1

    remaining = total - shown
    if remaining > 0:
        msg += f"\n\n{remaining} more sales this week."

    # Price range context
    if sale_prices and len(sale_prices) >= 2:
        msg += f"\n\nSales ranged {fmt_price(min(sale_prices))} to {fmt_price(max(sale_prices))}."

    msg += "\n\nFull sold data with sale prices and days on market at fieldsestate.com.au/for-sale"

    msg += f"\n\n{SELLER_CTA}"

    # Hero image from the first sold property, fall back to active listing
    hero_image = None
    if valid_sold:
        hero_image = _get_hero_image(valid_sold[0])
    if not hero_image:
        active = get_individual_properties()
        if active:
            hero_image = _get_hero_image(active[0])

    return msg, "sold_results", hero_image


def template_new_to_market(suburbs, properties=None, **kw):
    """Monday evening — top new listings this week with why each matters."""
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

    # Count by suburb for headline
    suburb_counts = {}
    for p, _ in new_listings:
        s = p["_suburb_display"]
        suburb_counts[s] = suburb_counts.get(s, 0) + 1
    total = len(new_listings)
    suburb_summary = ", ".join(f"{c} in {s}" for s, c in sorted(suburb_counts.items(), key=lambda x: -x[1]))

    # Score each listing to find top picks
    scored = []
    for p, dt in new_listings:
        pv = parse_price_value(p.get("price", ""))
        vd = p.get("valuation_data", {}) or {}
        reconciled = (vd.get("confidence") or {}).get("reconciled_valuation")
        insufficient = (vd.get("summary") or {}).get("insufficient_data", True)
        pvd = p.get("property_valuation_data", {}) or {}
        overall = (pvd.get("condition_summary") or {}).get("overall_score")

        score = 0
        reasons = []

        # Condition
        if overall and overall >= 8:
            score += 15
            kitchen = pvd.get("kitchen", {}) or {}
            bench = kitchen.get("benchtop_material", "")
            island = kitchen.get("island_bench")
            outdoor = pvd.get("outdoor", {}) or {}
            extras = []
            if bench and bench.lower() in ("stone", "marble", "granite", "quartz", "engineered stone"):
                extras.append(f"{bench.lower()} kitchen")
            if island:
                extras.append("island bench")
            if outdoor.get("pool_present"):
                extras.append("pool")
            cond = f"Condition {overall}/10"
            if extras:
                cond += f" — {', '.join(extras)}"
            reasons.append(cond)
        elif overall and overall <= 5:
            reasons.append(f"Condition {overall}/10 — renovation upside, priced accordingly")

        # Large lot
        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")
        if lot and lot >= 750:
            score += 5
            reasons.append(f"{lot:.0f}sqm lot")

        scored.append((p, pv, score, reasons))

    scored.sort(key=lambda x: -x[2])

    # Pick top 4 with suburb diversity
    picks = []
    seen_suburbs = {}
    for p, pv, score, reasons in scored:
        sk = p.get("_suburb_key", "")
        if seen_suburbs.get(sk, 0) >= 2:
            continue
        seen_suburbs[sk] = seen_suburbs.get(sk, 0) + 1
        picks.append((p, pv, reasons))
        if len(picks) >= 4:
            break

    # Hero image from top pick
    hero_image = _get_hero_image(picks[0][0]) if picks else None

    msg = f"{plural(total, 'new house', 'new houses')} hit the market this week — {suburb_summary}."
    msg += "\n\nNew listings get the most attention in their first 14 days. These are the ones we'd look at first:\n"

    for p, pv, reasons in picks:
        addr = normalise_address(p)
        suburb = p["_suburb_display"]
        bed = p.get("bedrooms", "?")
        bath = p.get("bathrooms", "?")
        lot = p.get("lot_size_sqm") or (p.get("enriched_data") or {}).get("lot_size_sqm")
        price_str = clean_price_display(p.get("price", ""))
        specs = [f"{bed}bd {bath}ba"]
        if lot:
            specs.append(f"{lot:.0f}sqm")

        msg += f"\n{addr}, {suburb}"
        msg += f"\n{' · '.join(specs)} — {price_str}"
        # Show reasons (filter out lot size if already in specs)
        display_reasons = [r for r in reasons if "sqm lot" not in r]
        if display_reasons:
            msg += f"\n{'. '.join(display_reasons)}."
        prop_id = str(p.get("_id", ""))
        if prop_id:
            msg += f"\nfieldsestate.com.au/property/{prop_id}"
        msg += "\n"

    remaining = total - len(picks)
    if remaining > 0:
        msg += f"\n{remaining} more new listings this week — full list with property reports at fieldsestate.com.au/for-sale"

    msg += f"\n\n{BUYER_CTA}"
    return msg, "new_to_market", hero_image


def _get_hero_image(prop):
    """Get the best image URL for a property.

    Prefers photo_tour_order position 1 (curated front exterior),
    falls back to first property_image.
    """
    tour = prop.get("photo_tour_order") or []
    if tour:
        # Sort by reorder_position, take first
        sorted_tour = sorted(tour, key=lambda x: x.get("reorder_position", 999))
        url = sorted_tour[0].get("url")
        if url:
            return url

    images = prop.get("property_images") or []
    if images:
        return images[0]

    return None


def _compute_room_percentiles(subject_rooms, all_listings):
    """Compute room-size percentiles for a property vs all listings in the suburb.

    Mirrors the website's property-insights.mjs computeRoomPercentiles() logic.
    Returns list of dicts: {label, area, percentile, median}.
    """
    if not subject_rooms or not isinstance(subject_rooms, dict):
        return []

    # Collect room areas by normalised room type across all listings
    room_pools = {}
    for listing in all_listings:
        rooms = listing.get("parsed_rooms", {}) or {}
        for rk, rv in rooms.items():
            if not isinstance(rv, dict):
                continue
            area = rv.get("area")
            if area and area > 0:
                # Normalise: bedroom, bedroom_2, bedroom_3 → bedroom
                base = rk.split("_")[0] if rk.replace("_", "").replace("bedroom", "").isdigit() or rk.startswith("bedroom") else rk
                # Actually group all bedrooms together, all living rooms, etc.
                if rk.startswith("bedroom"):
                    base = "bedroom"
                elif rk.startswith("living"):
                    base = "living_room"
                elif rk.startswith("dining"):
                    base = "dining_room"
                else:
                    base = rk
                room_pools.setdefault(base, []).append(area)

    results = []
    for rk, rv in subject_rooms.items():
        if not isinstance(rv, dict):
            continue
        area = rv.get("area")
        if not area or area <= 0:
            continue

        # Match to pool
        if rk.startswith("bedroom"):
            base = "bedroom"
        elif rk.startswith("living"):
            base = "living_room"
        elif rk.startswith("dining"):
            base = "dining_room"
        else:
            base = rk

        pool = room_pools.get(base, [])
        if len(pool) < 3:
            continue

        pool_sorted = sorted(pool)
        count_below = sum(1 for v in pool_sorted if v < area)
        pctl = round(count_below / len(pool_sorted) * 100)
        median = pool_sorted[len(pool_sorted) // 2]

        label = rk.replace("_", " ").title()
        results.append({
            "label": label,
            "area": round(area, 1),
            "percentile": pctl,
            "median": round(median, 1),
            "key": rk,
        })

    return results


def _build_value_drivers_section(prop, suburb_props):
    """Build a Value Drivers summary section for a property.

    Computes room percentiles on the fly, extracts condition data,
    and formats strengths & trade-offs like the website's Value Drivers tab.
    """
    pvd = prop.get("property_valuation_data", {}) or {}
    cs = pvd.get("condition_summary", {}) or {}
    overall = cs.get("overall_score")
    kitchen = pvd.get("kitchen", {}) or {}
    kitchen_score = kitchen.get("condition_score")
    kitchen_bench = kitchen.get("benchtop_material", "")
    kitchen_island = kitchen.get("island_bench")
    outdoor_data = pvd.get("outdoor", {}) or {}
    outdoor_score = outdoor_data.get("outdoor_entertainment_score")

    strengths = []
    tradeoffs = []

    # Compute room percentiles vs suburb
    rooms = prop.get("parsed_rooms", {}) or {}
    room_pctls = _compute_room_percentiles(rooms, suburb_props)

    for rp in room_pctls:
        # Skip non-living rooms and rooms covered by condition section
        if rp["key"] in ("garage", "laundry", "hallway", "entry", "foyer",
                          "kitchen", "bathroom", "bathroom_2", "bathroom_3", "ensuite"):
            continue
        if rp["percentile"] >= 75:
            strengths.append(f"{rp['label']}: {rp['area']}m² — larger than most in the suburb")
        elif rp["percentile"] <= 20:
            tradeoffs.append(f"{rp['label']}: {rp['area']}m² — smaller than most in the suburb")

    # Kitchen
    if kitchen_score is not None:
        extras = []
        if kitchen_bench:
            extras.append(kitchen_bench.lower() + " benchtops")
        if kitchen_island:
            extras.append("island bench")
        detail = f" — {', '.join(extras)}" if extras else ""
        item = f"Kitchen: {kitchen_score}/10{detail}"
        if kitchen_score >= 7:
            strengths.append(item)
        else:
            tradeoffs.append(item)

    # Outdoor
    if outdoor_score is not None and outdoor_score >= 7:
        features = []
        if outdoor_data.get("pool_present"):
            pool_type = outdoor_data.get("pool_type", "")
            features.append(f"{pool_type} pool" if pool_type else "pool")
        if outdoor_data.get("alfresco_present"):
            covered = "covered " if outdoor_data.get("alfresco_covered") else ""
            features.append(f"{covered}alfresco")
        detail = f" — {', '.join(features)}" if features else ""
        strengths.append(f"Outdoor entertaining: {outdoor_score}/10{detail}")
    elif outdoor_score is not None and outdoor_score <= 4:
        tradeoffs.append(f"Outdoor entertaining: {outdoor_score}/10")

    if not strengths and not tradeoffs and overall is None:
        return ""

    lines = []

    # Overall condition header
    if overall is not None:
        if overall >= 8:
            cond_label = "move-in ready"
        elif overall >= 6:
            cond_label = "good condition"
        else:
            cond_label = "may need updating"
        lines.append(f"Condition: {overall}/10 — {cond_label}.")

    if strengths:
        lines.append("Strengths")
        for s in strengths[:4]:
            lines.append(f"  ✓ {s}")

    if tradeoffs:
        lines.append("Trade-offs")
        for t in tradeoffs[:3]:
            lines.append(f"  ↓ {t}")

    return "\n".join(lines)


def _get_condition_tradeoffs(prop):
    """Extract specific condition notes from Value Drivers data for entry-price properties.

    Returns a sentence describing the property's condition — either explaining
    why it's cheap (low scores) or noting it's good value (high scores at low price).
    """
    pvd = prop.get("property_valuation_data", {}) or {}
    if not pvd:
        return ""

    cs = pvd.get("condition_summary", {}) or {}
    overall = cs.get("overall_score")
    kitchen = pvd.get("kitchen", {}) or {}
    kitchen_score = kitchen.get("condition_score")
    benchtop = kitchen.get("benchtop_material", "")
    island = kitchen.get("island_bench")
    exterior = (pvd.get("exterior", {}) or {}).get("condition_score")
    outdoor = (pvd.get("outdoor", {}) or {}).get("outdoor_entertainment_score")

    negatives = []
    positives = []

    # Kitchen — the biggest renovation cost
    if kitchen_score is not None:
        bench_lower = benchtop.lower() if benchtop else ""
        premium_bench = bench_lower in ("stone", "marble", "granite", "quartz", "engineered stone")
        if kitchen_score <= 6:
            detail = f" ({bench_lower} benchtop)" if bench_lower else ""
            neg = f"kitchen {kitchen_score}/10{detail}"
            if not island:
                neg += ", no island bench"
            negatives.append(neg)
        elif kitchen_score >= 8:
            extras = []
            if premium_bench:
                extras.append(bench_lower + " benchtop")
            if island:
                extras.append("island bench")
            detail = f" ({', '.join(extras)})" if extras else ""
            positives.append(f"kitchen {kitchen_score}/10{detail}")
        else:
            # 7/10 — middling, still worth noting specifics
            details = []
            if bench_lower:
                details.append(f"{bench_lower} benchtop")
            if not island:
                details.append("no island bench")
            elif island:
                details.append("island bench")
            detail = f" ({', '.join(details)})" if details else ""
            negatives.append(f"kitchen {kitchen_score}/10{detail}")

    # Exterior
    if exterior is not None:
        if exterior <= 6:
            negatives.append(f"exterior {exterior}/10")
        elif exterior >= 8:
            positives.append(f"exterior {exterior}/10")

    # Overall as fallback if no kitchen data
    if overall is not None and not negatives and not positives:
        if overall <= 6:
            negatives.append(f"overall condition {overall}/10")
        elif overall >= 8:
            positives.append(f"overall condition {overall}/10")

    # Build output — trade-offs take priority (they explain the discount)
    if negatives:
        return f"Our data: {', '.join(negatives).capitalize()} — that's likely part of the discount."
    elif positives:
        return f"Our data: {', '.join(positives).capitalize()} — solid condition for an entry price."
    return ""


def _reframe_intel_as_advice(raw_insight, prop, price_val):
    """Reframe a raw property_intel string into actionable buyer advice."""
    # Skip valuation-based insights entirely
    if "above our valuation" in raw_insight or "above estimated" in raw_insight:
        days = prop.get("days_on_domain")
        if isinstance(days, (int, float)) and days >= 45:
            return f"{int(days)} days on market — there may be room to negotiate."
        return ""

    if "below our valuation" in raw_insight or "good value" in raw_insight.lower() or "underpriced" in raw_insight.lower():
        days = prop.get("days_on_domain")
        if isinstance(days, (int, float)) and days <= 7:
            return "Just listed — move early if the numbers work."
        return ""

    # Condition pattern: "Condition: X/10"
    if raw_insight.startswith("Condition:") or "condition" in raw_insight.lower()[:15]:
        detail = raw_insight.split("—", 1)[-1].strip() if "—" in raw_insight else ""
        # Strip trailing "Move-in ready." from detail to avoid duplication
        detail = re.sub(r'\s*Move-in ready\.?\s*$', '', detail).rstrip('. ')
        score_match = re.search(r"(\d+)/10", raw_insight)
        if score_match and int(score_match.group(1)) >= 8:
            if detail:
                return f"Move-in ready — {detail}. No renovation cost to factor in."
            return "Move-in ready — no major renovation costs to factor in."
        elif score_match and int(score_match.group(1)) <= 5:
            return "Needs work — factor renovation costs into your offer. That's also your negotiation leverage."
        return raw_insight

    # Walkability pattern: "High walkability" or "X amenities within"
    if "walkability" in raw_insight.lower() or "amenities within" in raw_insight.lower():
        count_match = re.search(r"(\d+)\s+amenities", raw_insight)
        if count_match:
            count = count_match.group(1)
            return f"{count} amenities within walking distance. If you're coming from further out, the lifestyle difference is real."
        return raw_insight

    # Default: return as-is
    return raw_insight


# ── Template registry ────────────────────────────────────────────────────

AGGREGATE_TEMPLATES = {
    "suburb_snapshot": template_suburb_snapshot,
    "price_comparison": template_price_comparison,
    "listing_count": template_listing_count,
    "bedroom_breakdown": template_bedroom_breakdown,
    "seller_insight": template_seller_insight,
    "buyer_intelligence": template_buyer_intelligence,
}

PROPERTY_TEMPLATES = {
    "open_home_spotlight": template_open_home_spotlight,
    "entry_price_watch": template_entry_price_watch,
    "median_showcase": template_median_showcase,
    "weekend_preview": template_weekend_preview,
    "saturday_open_list": template_saturday_open_list,
    "sold_results": template_sold_results,
    "new_to_market": template_new_to_market,
    "price_movement": template_price_movement,
    "sold_preview": template_sold_preview,
}

TEMPLATE_MAP = {**AGGREGATE_TEMPLATES, **PROPERTY_TEMPLATES}


def _unpack_template_result(result):
    """Unpack a template return value — handles both 2-tuple and 3-tuple.

    Templates return (message, template_type) or (message, template_type, image_url).
    """
    if result is None:
        return None, None, None
    if len(result) == 3:
        return result
    return result[0], result[1], None


def generate_post(suburbs, template_name=None):
    """Pick a template and generate a post. If template_name given, use that specific one.

    Returns (message, template_type, image_url). image_url may be None.
    """
    properties = None

    if template_name:
        fn = TEMPLATE_MAP.get(template_name)
        if not fn:
            print(f"ERROR: Unknown template '{template_name}'. Available: {', '.join(TEMPLATE_MAP.keys())}")
            return None, None, None

        if template_name in PROPERTY_TEMPLATES:
            properties = get_individual_properties()
            result = fn(suburbs, properties=properties)
        else:
            result = fn(suburbs)
        return _unpack_template_result(result)

    # Random selection (excluding scheduler-only templates)
    scheduler_only = {"sold_preview", "saturday_open_list", "weekend_preview", "sold_results", "price_movement"}
    daily_templates = [(name, fn) for name, fn in TEMPLATE_MAP.items() if name not in scheduler_only]
    random.shuffle(daily_templates)

    for name, template_fn in daily_templates:
        if name in PROPERTY_TEMPLATES:
            if properties is None:
                properties = get_individual_properties()
            result = template_fn(suburbs, properties=properties)
        else:
            result = template_fn(suburbs)
        msg, template_type, image_url = _unpack_template_result(result)
        if msg:
            return msg, template_type, image_url
    return None, None, None


def main():
    parser = argparse.ArgumentParser(description="Post to Fields Real Estate Facebook page")
    parser.add_argument("--generate", action="store_true", help="Auto-generate a data-led post")
    parser.add_argument("--template", type=str, help=f"Use specific template: {', '.join(TEMPLATE_MAP.keys())}")
    parser.add_argument("--post", action="store_true", help="Actually publish (default: dry run)")
    parser.add_argument("--stage", action="store_true", help="Stage post for approval in Marketing Monitor")
    parser.add_argument("--message", type=str, help="Custom message to post")
    parser.add_argument("--link", type=str, help="URL to attach to the post")
    parser.add_argument("--image", type=str, help="Path to image file to post as photo")
    parser.add_argument("--publish-approved", action="store_true", help="Publish all approved pending posts")
    args = parser.parse_args()

    if args.publish_approved:
        # Publish all approved pending posts from the Marketing Monitor
        from bson import ObjectId
        client = MongoClient(COSMOS_URI)
        db = client["system_monitor"]
        approved = list(db["fb_pending_posts"].find({"status": "approved"}))
        if not approved:
            print("No approved posts to publish.")
            client.close()
            return
        print(f"Found {len(approved)} approved post(s) to publish.\n")
        for doc in approved:
            doc_id = doc["_id"]
            msg = doc["message"]
            img = doc.get("image_url")
            ttype = doc.get("template_type", "unknown")
            print(f"Publishing {ttype}...")
            try:
                if img:
                    post_id = post_photo_url_to_page(img, msg)
                    log_post(post_id, msg, None, ttype, content_type="photo")
                else:
                    post_id = post_to_page(msg)
                    log_post(post_id, msg, None, ttype)
                db["fb_pending_posts"].update_one(
                    {"_id": doc_id},
                    {"$set": {"status": "published", "post_id": post_id, "published_at": datetime.now(timezone.utc).isoformat()}}
                )
                print(f"  Published! Post ID: {post_id}")
            except Exception as e:
                db["fb_pending_posts"].update_one(
                    {"_id": doc_id},
                    {"$set": {"status": "failed", "error": str(e)}}
                )
                print(f"  FAILED: {e}")
        client.close()
        return

    elif args.generate:
        print("Pulling suburb data...")
        suburbs = get_suburb_data()
        message, template_type, image_url = generate_post(suburbs, template_name=args.template)
        if not message:
            print("ERROR: Could not generate a post from available data.")
            sys.exit(1)
        print(f"\n--- Generated post (template: {template_type}) ---\n")
        print(message)
        if image_url:
            print(f"\n[Photo: {image_url}]")
        print("\n---")

        if args.post:
            if image_url:
                print(f"\nPublishing photo post to Facebook page...")
                post_id = post_photo_url_to_page(image_url, message)
                log_post(post_id, message, None, template_type, content_type="photo")
            else:
                print("\nPublishing to Facebook page...")
                post_id = post_to_page(message)
                log_post(post_id, message, None, template_type)
            print(f"Published! Post ID: {post_id}")
            print(f"View: https://facebook.com/{post_id}")
        elif args.stage:
            pending_id = stage_post(message, template_type, image_url)
            print(f"\nStaged for approval. Pending ID: {pending_id}")
            print("View in Marketing Monitor at https://fieldsestate.com.au/ops")
        else:
            print("\n(Dry run — add --post to publish or --stage to queue for approval)")

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
