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
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ADS_TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes", "carrara", "worongary", "merrimac"]
CORE_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
SUBURB_DISPLAY = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
    "carrara": "Carrara",
    "worongary": "Worongary",
    "merrimac": "Merrimac",
    "mudgeeraba": "Mudgeeraba",
    "reedy_creek": "Reedy Creek",
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
    # Normalize whitespace around $
    p = re.sub(r'\$\s+', '$', p)
    # Shorten "Offers Over" / "Offers above" to just the price or short prefix
    p = re.sub(r'(?i)offers?\s+over\s+', '', p)
    p = re.sub(r'(?i)offers?\s+above\s+', '', p)
    p = re.sub(r'(?i)offers?\s+from\s+', 'From ', p)
    p = re.sub(r'(?i)price\s+guide\s*-?\s*', '', p)
    p = re.sub(r'(?i)PRICE GUIDE\s*', '', p)
    p = re.sub(r'(?i)expressions?\s+of\s+interest.*', 'EOI', p)
    p = re.sub(r'(?i)present\s+all\s+offers.*', 'EOI', p)
    p = re.sub(r'(?i)best\s+offers?\s+by.*', 'EOI', p)
    p = re.sub(r'(?i)EOI\s+ending.*', 'EOI', p)
    p = re.sub(r'(?i)submit\s+all\s+offers.*', 'EOI', p)
    p = re.sub(r'(?i)by\s+negotiation', 'By negotiation', p)
    p = re.sub(r'(?i)for\s+sale\s*$', 'Contact agent', p)
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


# ── Data collection ──────────────────────────────────────────────────────

def get_suburb_data():
    """Pull aggregate listing data per suburb for aggregate templates."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast_Currently_For_Sale"]

    suburbs = {}
    for suburb in TARGET_SUBURBS:
        listings = list(db[suburb].find({}, {
            "price": 1, "bedrooms": 1, "bathrooms": 1,
            "property_type": 1, "address": 1, "suburb": 1,
        }))
        if not listings:
            continue

        prices = []
        for l in listings:
            val = parse_price_value(l.get("price", ""))
            if val:
                prices.append(val)

        types = {}
        for l in listings:
            pt = l.get("property_type", "Unknown")
            types[pt] = types.get(pt, 0) + 1

        beds = {}
        for l in listings:
            b = l.get("bedrooms")
            if b:
                beds[str(b)] = beds.get(str(b), 0) + 1

        suburbs[suburb] = {
            "display_name": SUBURB_DISPLAY.get(suburb, suburb.replace("_", " ").title()),
            "total": len(listings),
            "prices": sorted(prices),
            "median_price": sorted(prices)[len(prices) // 2] if prices else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "types": types,
            "beds": beds,
        }

    client.close()
    return suburbs


def get_individual_properties():
    """Pull individual property records with full detail for property-level templates."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast_Currently_For_Sale"]

    properties = []
    for suburb in CORE_SUBURBS:
        listings = list(db[suburb].find({}, {
            "address": 1, "street_address": 1, "suburb": 1,
            "price": 1, "property_type": 1, "bedrooms": 1,
            "bathrooms": 1, "carspaces": 1, "inspection_times": 1,
            "listing_url": 1, "days_on_domain": 1,
            "first_listed_full": 1, "first_seen": 1,
            "first_listed_timestamp": 1,
            "valuation_data.subject_property.valuation_price": 1,
            "valuation_data.summary.value_gap_pct": 1,
        }))
        for l in listings:
            l["_suburb_key"] = suburb
            l["_suburb_display"] = SUBURB_DISPLAY.get(suburb, suburb.replace("_", " ").title())
        properties.extend(listings)

    client.close()
    return properties


def get_recently_sold_properties():
    """Pull recently sold properties from Gold_Coast_Recently_Sold with enrichment data."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast_Recently_Sold"]

    sold = []
    for suburb in CORE_SUBURBS:
        try:
            listings = list(db[suburb].find({}, {
                "address": 1, "street_address": 1, "suburb": 1,
                "price": 1, "sale_price": 1, "listing_price": 1,
                "sold_date": 1, "sold_date_text": 1,
                "property_type": 1, "bedrooms": 1, "bathrooms": 1,
                "carspaces": 1, "days_on_market": 1, "days_on_domain": 1,
                "moved_to_sold_date": 1, "listing_url": 1,
                # Enrichment data for insights
                "enriched_data.lot_size_sqm": 1,
                "enriched_data.floor_area_sqm": 1,
                "enriched_data.transactions": 1,
                "floor_plan_analysis.internal_floor_area": 1,
                "valuation_data.confidence": 1,
                "valuation_data.subject_property.predicted_value": 1,
                "property_insights": 1,
            }))
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
    """Single suburb market snapshot — what's the state of play."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 10]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    type_lines = []
    for pt, count in sorted(s["types"].items(), key=lambda x: -x[1]):
        pct = round(count / s["total"] * 100)
        pt_clean = clean_property_type(pt)
        type_lines.append(f"  {pluralize_type(pt_clean)}: {count} ({pct}%)")

    type_section = "\n".join(type_lines[:4])

    msg = f"""{name} right now — {s['total']} properties for sale

Price range: {fmt_price(s['min_price'])} to {fmt_price(s['max_price'])}
Median asking price: {fmt_price(s['median_price'])}

{type_section}

If you're a buyer, this tells you how much competition you're facing. If you're a seller, this is who you're competing against.

Follow us — we track this daily."""
    return msg, "suburb_snapshot"


def template_price_comparison(suburbs, **kw):
    """What does $X buy across suburbs — practical guide for buyers."""
    price_point = random.choice([700000, 800000, 900000, 1000000, 1200000])
    results = []

    for key, s in suburbs.items():
        if not s["prices"]:
            continue
        lower = price_point * 0.85
        upper = price_point * 1.15
        matches = [p for p in s["prices"] if lower <= p <= upper]
        if matches:
            results.append({
                "name": s["display_name"],
                "count": len(matches),
                "total": s["total"],
            })

    if len(results) < 2:
        return None, None

    results.sort(key=lambda x: -x["count"])
    lines = [f"  {r['name']}: {plural(r['count'], 'option')} (of {r['total']} total)" for r in results[:4]]

    most = results[0]

    msg = f"""Got {fmt_price(price_point)}? Here's where you have the most options.

Across our target suburbs, here's how many properties are listed within 15% of that budget:

""" + "\n".join(lines) + f"""

{most['name']} gives you the most to choose from at this price point. If you're flexible on suburb, that's where to start your search.

Follow us for daily market updates."""
    return msg, "price_comparison"


def template_listing_count(suburbs, **kw):
    """Total listings — are buyers or sellers in control right now?"""
    total = sum(s["total"] for s in suburbs.values())
    by_count = sorted(suburbs.items(), key=lambda x: -x[1]["total"])

    lines = [f"  {s['display_name']}: {s['total']}" for key, s in by_count if s["total"] > 0]

    most = by_count[0][1]
    least = by_count[-1][1] if by_count[-1][1]["total"] > 0 else by_count[-2][1]

    msg = f"""{total} properties for sale right now across the southern Gold Coast.

""" + "\n".join(lines) + f"""

Buyers have the most choice in {most['display_name']} ({most['total']} listings). {least['display_name']} is tighter with just {least['total']}.

More listings = more negotiating power for buyers. Fewer listings = sellers hold the cards. Follow us to see how this shifts week to week."""
    return msg, "listing_count"


def template_bedroom_breakdown(suburbs, **kw):
    """What bedroom counts are available — helps buyers gauge their options."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 10 and suburbs[s]["beds"]]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    total = sum(s["beds"].values())
    lines = []
    for bed_count in sorted(s["beds"].keys(), key=lambda x: int(x)):
        count = s["beds"][bed_count]
        pct = round(count / total * 100)
        lines.append(f"  {bed_count}-bed: {plural(count, 'listing')} ({pct}%)")

    most_common = max(s["beds"].items(), key=lambda x: x[1])
    least_common = min(
        ((k, v) for k, v in s["beds"].items() if v > 0),
        key=lambda x: x[1],
    )

    msg = f"""Looking for a specific size in {name}? Here's what's available.

{s['total']} properties for sale, broken down by bedrooms:

""" + "\n".join(lines) + f"""

{most_common[0]}-bedroom properties make up {round(most_common[1] / total * 100)}% of the market. If you need a {least_common[0]}-bed, {"there's" if least_common[1] == 1 else "there are"} only {least_common[1]} — worth moving quickly when one comes up.

Follow us — we flag new listings the week they appear."""
    return msg, "bedroom_breakdown"


def template_seller_insight(suburbs, **kw):
    """Actionable insight for sellers — your competition and what it means."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 10]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    prices = s["prices"]
    if len(prices) < 5:
        return None, None

    median = s["median_price"]
    below_median = len([p for p in prices if p <= median])
    above_median = len([p for p in prices if p > median])

    types = s["types"]
    dominant_type = max(types.items(), key=lambda x: x[1]) if types else ("properties", 0)
    dominant_pct = round(dominant_type[1] / s["total"] * 100) if s["total"] > 0 else 0

    msg = f"""Selling in {name}? Here's your competition.

Right now there are {s['total']} properties for sale in {name}. {below_median} are priced at or below {fmt_price(median)}, and {above_median} are above it.

{clean_property_type(dominant_type[0]).title()}s make up {dominant_pct}% of all listings. If you're selling a different type, that's either an advantage (less direct competition) or a challenge (fewer comparable sales).

The question for every seller: at your price point, how many other properties is a buyer choosing between? The answer changes every week.

Follow us to track the numbers."""

    return msg, "seller_insight"


def template_buyer_intelligence(suburbs, **kw):
    """Cross-suburb comparison for buyers at a specific price point."""
    brackets = [
        (500000, 700000, "under $700,000"),
        (700000, 900000, "$700,000 – $900,000"),
        (900000, 1200000, "$900,000 – $1,200,000"),
        (1200000, 1800000, "$1,200,000 – $1,800,000"),
    ]

    random.shuffle(brackets)
    for low, high, label in brackets:
        results = []
        for key, s in suburbs.items():
            matches = [p for p in s["prices"] if low <= p <= high]
            if matches:
                results.append({
                    "name": s["display_name"],
                    "count": len(matches),
                    "min": min(matches),
                    "max": max(matches),
                })
        if len(results) >= 2:
            break
    else:
        return None, None

    results.sort(key=lambda x: -x["count"])
    lines = [f"  {r['name']}: {plural(r['count'], 'property', 'properties')} ({fmt_price(r['min'])} – {fmt_price(r['max'])})" for r in results[:4]]

    most = results[0]

    msg = f"""Buying {label}? Here's where to look.

Active listings in this price range right now:

""" + "\n".join(lines) + f"""

{most['name']} gives you the most choice at this budget. If you're flexible on suburb, that's where the numbers are in your favour.

More options = more leverage. Fewer = expect competition. Follow us to see how this changes week to week."""

    return msg, "buyer_intelligence"


def template_weekly_wrap(suburbs, **kw):
    """Sunday evening — the week's market summary."""
    total = sum(s["total"] for s in suburbs.values())

    # Only show suburbs with meaningful data (> 2 listings)
    suburb_lines = []
    for key in sorted(suburbs.keys(), key=lambda k: -suburbs[k]["total"]):
        s = suburbs[key]
        if s["total"] <= 2:
            continue
        line = f"  {s['display_name']}: {s['total']} listings"
        if s["median_price"] and s["median_price"] >= 200000:
            line += f", median {fmt_price(s['median_price'])}"
        suburb_lines.append(line)

    most_listings = max(suburbs.values(), key=lambda s: s["total"])
    highest_median_suburbs = [s for s in suburbs.values() if s.get("median_price") and s["median_price"] >= 200000]
    highest_median = max(highest_median_suburbs, key=lambda s: s["median_price"], default=None)

    msg = f"""Southern Gold Coast — This week's market in numbers

{total} properties for sale across the suburbs we track.

""" + "\n".join(suburb_lines[:6])

    msg += "\n\n"
    if most_listings:
        msg += f"Most buyer choice: {most_listings['display_name']} ({most_listings['total']} listings).\n"
    if highest_median:
        msg += f"Highest median asking price: {highest_median['display_name']} at {fmt_price(highest_median['median_price'])}.\n"

    msg += """
Whether you're buying or selling, knowing the numbers puts you ahead of most people in the market. Follow us for daily updates."""

    return msg, "weekly_wrap"


# ── PROPERTY TEMPLATES (individual property posts) ───────────────────────

def template_open_home_spotlight(suburbs, properties=None, **kw):
    """Individual property spotlight — why this specific home is worth seeing."""
    if not properties:
        properties = get_individual_properties()

    for target_day in ["Saturday", "Sunday", "Thursday", "Friday", "Wednesday", "Tuesday"]:
        candidates = get_properties_for_day(properties, target_day)
        if candidates:
            break
    else:
        return None, None

    # Price all candidates and filter to standard residential (skip retirement)
    priced = []
    for p in candidates:
        ptype = (p.get("property_type") or "").lower()
        if "retirement" in ptype:
            continue
        price = parse_price_value(p.get("price", ""))
        if price and price >= 300000:
            priced.append((p, price))

    if not priced:
        return None, None

    # Pick strategically: near median, entry level, or premium — with reason
    random.shuffle(priced)
    prop, price = priced[0]
    suburb = prop["_suburb_display"]
    suburb_key = prop["_suburb_key"]
    median = suburbs.get(suburb_key, {}).get("median_price")

    insp = prop["_inspections"][0]
    bed = prop.get("bedrooms", "?")
    bath = prop.get("bathrooms", "?")
    ptype = clean_property_type(prop.get("property_type", ""))

    # Build the "why you should see this" angle
    why = ""
    action = ""
    if price and median:
        diff_pct = (price - median) / median * 100
        if abs(diff_pct) <= 12:
            why = f"It's priced right on the {suburb} median of {fmt_price(median)}. If you want to understand what middle-of-the-market money actually buys in {suburb} right now, this is the one to walk through."
            action = "See it, then compare it to what else is out there at this price."
        elif diff_pct < -15:
            why = f"At {fmt_price(price)}, this is well below the {suburb} median of {fmt_price(median)}. If you're looking for a way into this suburb, this is what entry-level looks like right now."
            action = "Worth seeing in person — entry-level homes set the floor for the whole suburb."
        elif diff_pct < 0:
            why = f"Listed below the {suburb} median of {fmt_price(median)}, this is on the more affordable side of the market."
            action = "A good benchmark if you're comparing value across suburbs."
        else:
            why = f"At {fmt_price(price)}, this is above the {suburb} median of {fmt_price(median)}. If you're a seller wondering what buyers pay for a premium {ptype} here, this sale will tell you."
            action = "Follow us to see what it sells for — it'll set a benchmark."

    address = prop.get("street_address", prop.get("address", "A property"))

    msg = f"""{address}, {suburb}
{bed}-bed {bath}-bath {ptype} — {clean_price_display(prop.get('price', ''))}

Open {insp['day']} at {insp['start']}.

{why}

{action}"""

    return msg, "open_home_spotlight"


def template_entry_price_watch(suburbs, properties=None, **kw):
    """The cheapest standard-residential property per suburb — what entry level looks like."""
    if not properties:
        properties = get_individual_properties()

    entries = []
    for suburb_key in CORE_SUBURBS:
        suburb_props = [p for p in properties if p["_suburb_key"] == suburb_key]
        # Filter: skip retirement, management rights, sub-$200k outliers
        priced = []
        for p in suburb_props:
            ptype = (p.get("property_type") or "").lower()
            if "retirement" in ptype:
                continue
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
                "total": len(suburb_props),
                "median": suburbs.get(suburb_key, {}).get("median_price"),
            })

    if not entries:
        return None, None

    lines = []
    for e in entries:
        p = e["prop"]
        bed = p.get("bedrooms", "?")
        ptype = clean_property_type(p.get("property_type", ""))
        addr = p.get("street_address", "")
        gap = ""
        if e["median"]:
            pct_below = round((1 - e["price_val"] / e["median"]) * 100)
            gap = f" — {pct_below}% below median"
        lines.append(f"  {e['suburb']}: {fmt_price(e['price_val'])} — {bed}-bed {ptype}, {addr}{gap}")

    cheapest_overall = min(entries, key=lambda e: e["price_val"])

    msg = f"""Entry-level prices right now — what's the cheapest way in?

The lowest-priced property in each of our target suburbs today:

""" + "\n".join(lines) + f"""

{cheapest_overall['suburb']} has the lowest entry point at {fmt_price(cheapest_overall['price_val'])}. If it sells near asking, it sets the new floor price for the suburb.

These shift as new stock comes on. Follow us — we track entry prices daily and we'll show you what they sell for."""

    return msg, "entry_price_watch"


def template_median_showcase(suburbs, properties=None, **kw):
    """What does median money buy? Specific property at the median mark."""
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
    # Skip retirement
    priced = [(p, parse_price_value(p.get("price", ""))) for p in suburb_props
              if "retirement" not in (p.get("property_type") or "").lower()]
    priced = [(p, v) for p, v in priced if v is not None]
    if not priced:
        return None, None

    priced.sort(key=lambda x: abs(x[1] - median))
    prop, price = priced[0]

    bed = prop.get("bedrooms", "?")
    bath = prop.get("bathrooms", "?")
    car = prop.get("carspaces", "?")
    ptype = clean_property_type(prop.get("property_type", ""))

    # Count how many are above and below
    above = len([v for _, v in priced if v > median])
    below = len([v for _, v in priced if v <= median])

    insp_line = ""
    inspections = prop.get("inspection_times") or []
    if inspections:
        details = parse_inspection_details(inspections[0])
        if details["start"]:
            insp_line = f"Open for inspection {details['day']} at {details['start']}. "

    address = prop.get("street_address", prop.get("address", ""))

    msg = f"""What does {fmt_price(median)} buy in {suburb_name}?

{suburb_name} has {total_listings} properties for sale right now. Half are above {fmt_price(median)}, half below. This property is right on that line:

{address}
{bed} bed · {bath} bath · {car} car — {ptype}
{clean_price_display(prop.get('price', ''))}

{insp_line}Walk through a home at the median and you'll know what "average" really means in this suburb. Everything else is either a step up or a compromise from here.

Follow us — we post this data every day."""

    return msg, "median_showcase"


def template_weekend_preview(suburbs, properties=None, **kw):
    """Friday post — 3-5 notable open homes for the weekend, each with a reason."""
    if not properties:
        properties = get_individual_properties()

    sat_props = get_properties_for_day(properties, "Saturday")
    sun_props = get_properties_for_day(properties, "Sunday")

    all_weekend = []
    seen_ids = set()
    for p in sat_props + sun_props:
        pid = str(p.get("_id", ""))
        ptype = (p.get("property_type") or "").lower()
        if pid not in seen_ids and "retirement" not in ptype:
            seen_ids.add(pid)
            all_weekend.append(p)

    # Price all candidates
    entries = [(p, parse_price_value(p.get("price", ""))) for p in all_weekend]
    entries = [(p, v) for p, v in entries if v and v >= 300000]

    if len(entries) < 3:
        return None, None

    entries.sort(key=lambda x: x[1])
    total_weekend = len(all_weekend)

    # Curate picks with REASONS
    picks = []

    # 1. Entry-level pick
    ep = entries[0]
    picks.append((ep[0], ep[1], "Lowest asking price open this weekend"))

    # 2. Near-median pick (different suburb if possible)
    all_medians = {k: v.get("median_price") for k, v in suburbs.items() if v.get("median_price")}
    median_candidates = []
    for p, v in entries:
        m = all_medians.get(p["_suburb_key"])
        if m and abs(v - m) / m < 0.12 and str(p.get("_id")) != str(ep[0].get("_id")):
            median_candidates.append((p, v))
    if median_candidates:
        mp = median_candidates[0]
        picks.append((mp[0], mp[1], f"Right on the {mp[0]['_suburb_display']} median — what typical money buys"))

    # 3. Premium pick
    pp = entries[-1]
    if str(pp[0].get("_id")) not in {str(x[0].get("_id")) for x in picks}:
        picks.append((pp[0], pp[1], "Highest asking price this weekend"))

    # 4. One more if room — newest listing
    seen_pick_ids = {str(x[0].get("_id")) for x in picks}
    for p, v in entries:
        days = p.get("days_on_domain")
        if str(p.get("_id")) not in seen_pick_ids and isinstance(days, (int, float)) and days <= 7:
            picks.append((p, v, "Just listed this week — first open home"))
            break

    lines = []
    for prop, price, reason in picks[:4]:
        insp = prop["_inspections"][0]
        suburb = prop["_suburb_display"]
        bed = prop.get("bedrooms", "?")
        ptype = clean_property_type(prop.get("property_type", ""))
        addr = prop.get("street_address", "")
        lines.append(f"  {addr} ({suburb})\n  {bed}-bed {ptype}, {fmt_price(price)} — Open {insp['day']} {insp['start']}\n  Why: {reason}")

    msg = f"""Weekend open homes — {total_weekend} properties open, here are {len(picks)} worth your time

""" + "\n\n".join(lines) + f"""

Walking through homes at different price points is the fastest way to calibrate what the market actually feels like.

Follow us — tomorrow at 6am we'll post the full open home list."""

    return msg, "weekend_preview"


def template_saturday_open_list(suburbs, properties=None, **kw):
    """Saturday 6am — full curated open home list for today, sorted by time."""
    if not properties:
        properties = get_individual_properties()

    sat_props = get_properties_for_day(properties, "Saturday")

    if not sat_props:
        return None, None

    # Group by suburb
    by_suburb = {}
    for p in sat_props:
        suburb = p["_suburb_display"]
        if suburb not in by_suburb:
            by_suburb[suburb] = []
        by_suburb[suburb].append(p)

    # Build highlights: cheapest, most expensive, newest
    all_priced = [(p, parse_price_value(p.get("price", ""))) for p in sat_props]
    all_priced = [(p, v) for p, v in all_priced if v and v >= 300000]
    highlights = []
    if all_priced:
        all_priced.sort(key=lambda x: x[1])
        cheapest = all_priced[0]
        highlights.append(f"  Cheapest open today: {cheapest[0].get('street_address', '')} ({cheapest[0]['_suburb_display']}) at {fmt_price(cheapest[1])}")
        most_exp = all_priced[-1]
        highlights.append(f"  Most expensive: {most_exp[0].get('street_address', '')} ({most_exp[0]['_suburb_display']}) at {fmt_price(most_exp[1])}")

    sections = []
    unique_count = 0
    for suburb in sorted(by_suburb.keys()):
        props = by_suburb[suburb]
        # Sort by actual time (not string sort)
        props.sort(key=lambda p: time_sort_key(p["_inspections"][0].get("start", "")))

        seen_addrs = set()
        prop_lines = []
        for p in props:
            addr = p.get("street_address", "")
            if addr in seen_addrs:
                continue
            seen_addrs.add(addr)
            unique_count += 1
            insp = p["_inspections"][0]
            price = clean_price_display(p.get("price", ""))
            bed = p.get("bedrooms", "?")
            ptype = clean_property_type(p.get("property_type", ""))
            prop_lines.append(f"  {insp['start']} — {addr} ({bed}-bed {ptype}, {price})")

        sections.append(f"{suburb}:\n" + "\n".join(prop_lines))

    msg = f"""Your open home list for today — {unique_count} properties open.

""" + "\n\n".join(highlights) + "\n\n" + "\n\n".join(sections) + """

Even if you're not buying today, walking through 2-3 homes gives you a real feel for what the market looks like right now.

Follow us — Monday we'll post what sold and for how much."""

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
    ptype = clean_property_type(p.get("property_type", ""))
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

    # Rarity / percentile (medium — useful for scarcity signal)
    if pi:
        beds_pi = pi.get("bedrooms", {})
        sc = beds_pi.get("suburbComparison", {})
        pctl = sc.get("percentile")
        if pctl and pctl >= 85 and bed:
            medium.append(f"{bed}-bed homes are top {100-pctl}% for size in {suburb} — rare stock.")
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


def template_sold_results(suburbs, properties=None, **kw):
    """Monday — what sold, with context and insight per sale."""
    sold_properties = get_recently_sold_properties()

    if not sold_properties:
        msg = """Sales update — Robina, Burleigh Waters, Varsity Lakes

No confirmed sales this past week. Settlement timelines and delayed reporting mean some sales take weeks to appear.

When they land, we break them down — what sold, what it sold for, and what it means for prices in your suburb.

Follow us to see them first."""
        return msg, "sold_results"

    # Dedup by address (keep most recent)
    seen_addrs = {}
    for p in sold_properties:
        addr = p.get("street_address", "")
        if addr not in seen_addrs:
            seen_addrs[addr] = p
        else:
            # Keep the one with more data
            existing = seen_addrs[addr]
            if ("valuation_data" in p and "valuation_data" not in existing) or \
               (p.get("days_on_market") and not existing.get("days_on_market")):
                seen_addrs[addr] = p
    sold_deduped = list(seen_addrs.values())

    # Validate: filter out suspect prices (>$5M for <5 beds, or no sale price)
    valid_sold = []
    for p in sold_deduped:
        sp = parse_price_value(str(p.get("sale_price", "")))
        beds = p.get("bedrooms", 0) or 0
        if sp and sp > 5_000_000 and beds < 5:
            continue  # Likely corrupt
        # Must have address and listing URL in correct suburb
        url = p.get("listing_url", "")
        suburb_key = p.get("_suburb_key", "")
        if url and suburb_key:
            expected = suburb_key.replace("_", "-")
            addr_in_url = p.get("street_address", "").lower().replace(" ", "-")
            if expected not in url and addr_in_url not in url:
                continue  # URL doesn't match suburb or address — cross-contaminated
        valid_sold.append(p)

    if not valid_sold:
        msg = """Sales update — Robina, Burleigh Waters, Varsity Lakes

No verified sales to report this week. We only publish confirmed results we can validate.

Follow us — when sales land, we'll break down what they mean for prices in your suburb."""
        return msg, "sold_results"

    # Sort by sold date (most recent first), fall back to _id
    valid_sold.sort(key=lambda p: str(p.get("sold_date", p.get("_id", ""))), reverse=True)
    recent = valid_sold[:6]  # Top 6 for readability

    # Count by suburb for headline
    suburb_counts = {}
    for p in recent:
        s = p.get("_suburb_display", "")
        suburb_counts[s] = suburb_counts.get(s, 0) + 1
    suburb_parts = [f"{count} in {name}" for name, count in sorted(suburb_counts.items(), key=lambda x: -x[1])]
    headline_suburbs = ", ".join(suburb_parts)

    entries = []
    for p in recent:
        address = p.get("street_address", p.get("address", ""))
        suburb = p.get("_suburb_display", "")
        sale_price = p.get("sale_price", "")
        sale_val = parse_price_value(str(sale_price)) if sale_price else None
        days = p.get("days_on_market")
        ptype = clean_property_type(p.get("property_type", ""))
        bed = p.get("bedrooms", "?")

        # Build the property line
        if sale_val:
            price_str = fmt_price(sale_val)
        elif sale_price and str(sale_price).strip() and str(sale_price).strip().lower() != "none":
            price_str = clean_price_display(str(sale_price))
        else:
            price_str = "price undisclosed"
        dom_str = f", {days} days on market" if days else ""
        header = f"{address} ({suburb}) — {bed}-bed {ptype}, {price_str}{dom_str}"

        # Generate insights
        insights = _sold_insight(p, valid_sold)

        if insights:
            # Pick the best 1-2 insights
            entry = header + "\n  " + " ".join(insights[:2])
        else:
            entry = header

        entries.append(entry)

    total = len(recent)
    msg = f"What sold this week — {plural(total, 'confirmed sale')} ({headline_suburbs})\n\n"
    msg += "\n\n".join(entries)
    msg += "\n\nFollow us — we track every sale and break down what it means for your suburb."

    return msg, "sold_results"


def template_new_to_market(suburbs, properties=None, **kw):
    """Monday evening — freshest listings, what they mean for the market."""
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

    lines = []
    for p, dt in new_listings[:8]:
        suburb = p["_suburb_display"]
        price = clean_price_display(p.get("price", ""))
        bed = p.get("bedrooms", "?")
        ptype = clean_property_type(p.get("property_type", ""))
        addr = p.get("street_address", "")
        lines.append(f"  {addr} ({suburb}) — {bed}-bed {ptype}, {price}")

    total = len(new_listings)
    suburb_summary = ", ".join(f"{c} in {s}" for s, c in sorted(suburb_counts.items(), key=lambda x: -x[1]))

    msg = f"""{plural(total, 'new listing')} this week — {suburb_summary}

""" + "\n".join(lines)

    # Add buyer/seller relevance
    if total >= 10:
        msg += f"""

More new stock means more choice for buyers, and more competition for sellers. If you're selling, these are the properties your home is now being compared against."""
    else:
        msg += """

Fewer new listings this week. Less choice for buyers, but less competition for sellers already on the market."""

    msg += """

Follow us — we track every listing from day one through to sale."""

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
