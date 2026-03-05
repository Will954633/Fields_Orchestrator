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


def parse_price_value(price_str):
    """Extract numeric price from string like '$1,365,000' or 'Offers above $845,000'."""
    if not isinstance(price_str, str):
        return None
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


def get_properties_for_day(properties, target_day):
    """Filter properties that have inspections on a specific day (e.g. 'Saturday')."""
    result = []
    for prop in properties:
        inspections = prop.get("inspection_times") or []
        matching = []
        for insp in inspections:
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
    """Pull recently sold properties from Gold_Coast_Recently_Sold."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast_Recently_Sold"]

    sold = []
    for suburb in CORE_SUBURBS:
        try:
            listings = list(db[suburb].find({}, {
                "address": 1, "street_address": 1, "suburb": 1,
                "price": 1, "sale_price": 1, "sold_date": 1,
                "sold_date_text": 1, "property_type": 1,
                "bedrooms": 1, "bathrooms": 1, "days_on_market": 1,
                "moved_to_sold_date": 1,
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
    """Single suburb market snapshot."""
    candidates = [s for s in suburbs if suburbs[s]["total"] >= 10]
    if not candidates:
        return None, None
    suburb_key = random.choice(candidates)
    s = suburbs[suburb_key]
    name = s["display_name"]

    type_lines = []
    for pt, count in sorted(s["types"].items(), key=lambda x: -x[1]):
        pct = round(count / s["total"] * 100)
        type_lines.append(f"{pt}s: {count} ({pct}%)")

    msg = f"""{name} — Market Snapshot

{s['total']} properties currently for sale.

Price range: {fmt_price(s['min_price'])} to {fmt_price(s['max_price'])}
Median asking price: {fmt_price(s['median_price'])}

Property mix:
""" + "\n".join(f"  {line}" for line in type_lines[:4])

    msg += f"\n\nData from {datetime.now().strftime('%B %Y')}. Source: fieldsestate.com.au"
    return msg, "suburb_snapshot"


def template_price_comparison(suburbs, **kw):
    """What does $X buy across suburbs?"""
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
    lines = [f"  {r['name']}: {r['count']} options (of {r['total']} total)" for r in results[:4]]

    msg = f"""What does {fmt_price(price_point)} buy on the Southern Gold Coast?

We looked at every listing within 15% of {fmt_price(price_point)} across our target suburbs:

""" + "\n".join(lines)

    msg += f"""

{'More choice' if results[0]['count'] > results[-1]['count'] else 'Tight supply'} in {results[0]['name']}, {'fewer options' if results[-1]['count'] < 5 else 'solid selection'} in {results[-1]['name']}.

All data is live. Updated daily from {len(suburbs)} suburbs we track.

fieldsestate.com.au"""
    return msg, "price_comparison"


def template_listing_count(suburbs, **kw):
    """Total listings across all tracked suburbs."""
    total = sum(s["total"] for s in suburbs.values())
    by_count = sorted(suburbs.items(), key=lambda x: -x[1]["total"])

    lines = [f"  {s['display_name']}: {s['total']}" for key, s in by_count if s["total"] > 0]

    most = by_count[0][1]
    msg = f"""{total} properties are currently for sale across the Southern Gold Coast suburbs we track.

Breakdown:
""" + "\n".join(lines)

    msg += f"""

{most['display_name']} has the most choice right now with {most['total']} active listings.

We update this data every day. See the full breakdown at fieldsestate.com.au/for-sale"""
    return msg, "listing_count"


def template_bedroom_breakdown(suburbs, **kw):
    """What bedroom counts dominate in a suburb."""
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
        lines.append(f"  {bed_count}-bed: {count} listings ({pct}%)")

    most_common = max(s["beds"].items(), key=lambda x: x[1])

    msg = f"""What's actually for sale in {name}?

We broke down all {s['total']} active listings by bedroom count:

""" + "\n".join(lines)

    msg += f"""

{most_common[0]}-bedroom properties dominate — {round(most_common[1] / total * 100)}% of all listings.

Price range: {fmt_price(s['min_price'])} to {fmt_price(s['max_price'])}

Live data, updated daily.
fieldsestate.com.au"""
    return msg, "bedroom_breakdown"


def template_seller_insight(suburbs, **kw):
    """Actionable insight for sellers — pricing competition."""
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
    below_median = [p for p in prices if p <= median]
    above_median = [p for p in prices if p > median]

    types = s["types"]
    dominant_type = max(types.items(), key=lambda x: x[1]) if types else ("properties", 0)
    dominant_pct = round(dominant_type[1] / s["total"] * 100) if s["total"] > 0 else 0

    msg = f"""{name} — What sellers should know right now

{s['total']} properties are competing for buyer attention in {name}.

{len(below_median)} are listed at or below the median ({fmt_price(median)}), and {len(above_median)} are above it. {dominant_type[0]}s make up {dominant_pct}% of all listings.

If you're selling in {name}, your pricing relative to this competition matters. A property priced at {fmt_price(median)} sits right in the middle of {s['total']} active listings — above it, you need a clear reason for buyers to pay more. Below it, you've got the volume advantage.

The data updates daily. Full suburb analysis at fieldsestate.com.au/for-sale"""

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
    lines = [f"  {r['name']}: {r['count']} properties ({fmt_price(r['min'])} – {fmt_price(r['max'])})" for r in results[:4]]

    most = results[0]
    least = results[-1]

    msg = f"""Buying {label}? Here's where your options are.

We track every active listing across {len(suburbs)} Southern Gold Coast suburbs. In this price range right now:

""" + "\n".join(lines)

    msg += f"""

{most['name']} gives you the most choice with {most['count']} listings in this range. """

    if least["count"] <= 3:
        msg += f"{least['name']} is tight — only {least['count']}."
    else:
        msg += f"{least['name']} has {least['count']}."

    msg += """

This changes daily. See every listing with our analysis at fieldsestate.com.au/for-sale"""

    return msg, "buyer_intelligence"


def template_weekly_wrap(suburbs, **kw):
    """Sunday weekly market wrap — summary of the week across all suburbs."""
    total = sum(s["total"] for s in suburbs.values())

    suburb_lines = []
    for key in sorted(suburbs.keys(), key=lambda k: -suburbs[k]["total"]):
        s = suburbs[key]
        if s["total"] == 0:
            continue
        line = f"  {s['display_name']}: {s['total']} listings"
        if s["median_price"]:
            line += f", median {fmt_price(s['median_price'])}"
        suburb_lines.append(line)

    most_listings = max(suburbs.values(), key=lambda s: s["total"])
    highest_median = max(
        (s for s in suburbs.values() if s["median_price"]),
        key=lambda s: s["median_price"],
        default=None,
    )
    most_houses = max(
        (s for s in suburbs.values() if s["types"].get("House", 0) > 0),
        key=lambda s: s["types"].get("House", 0),
        default=None,
    )

    msg = f"""Southern Gold Coast — Weekly Market Summary

{total} properties are currently for sale across the suburbs we track.

""" + "\n".join(suburb_lines[:6])

    msg += "\n\nThis week's numbers:\n"
    if most_listings:
        msg += f"  Most choice: {most_listings['display_name']} ({most_listings['total']} active listings)\n"
    if highest_median:
        msg += f"  Highest median: {highest_median['display_name']} ({fmt_price(highest_median['median_price'])})\n"
    if most_houses:
        msg += f"  Most houses: {most_houses['display_name']} ({most_houses['types'].get('House', 0)} houses for sale)\n"

    msg += """
We update every number on this page daily. If you're buying or selling on the southern Gold Coast, this is your starting point.

fieldsestate.com.au/for-sale"""

    return msg, "weekly_wrap"


# ── PROPERTY TEMPLATES (individual property posts) ───────────────────────

def template_open_home_spotlight(suburbs, properties=None, **kw):
    """Individual property spotlight with open home time, positioned vs median."""
    if not properties:
        properties = get_individual_properties()

    # Look for properties with inspections coming up
    for target_day in ["Saturday", "Sunday", "Thursday", "Friday", "Wednesday", "Tuesday"]:
        candidates = get_properties_for_day(properties, target_day)
        if candidates:
            break
    else:
        return None, None

    # Prefer properties near median or at price extremes for more interesting posts
    priced_candidates = [(p, parse_price_value(p.get("price", ""))) for p in candidates]
    priced_candidates = [(p, v) for p, v in priced_candidates if v is not None]
    if not priced_candidates:
        return None, None

    prop, price = random.choice(priced_candidates)
    suburb = prop["_suburb_display"]
    suburb_key = prop["_suburb_key"]

    median = suburbs.get(suburb_key, {}).get("median_price")

    insp = prop["_inspections"][0]
    bed = prop.get("bedrooms", "?")
    bath = prop.get("bathrooms", "?")
    ptype = prop.get("property_type", "property")

    positioning = ""
    if price and median:
        diff_pct = (price - median) / median * 100
        if abs(diff_pct) <= 10:
            positioning = f"It's right on the {suburb} median ({fmt_price(median)}), so it'll give you a good sense of what middle-of-the-market money buys here right now."
        elif diff_pct < -20:
            positioning = f"At {fmt_price(price)}, it's well below the {suburb} median of {fmt_price(median)} — this is entry-level territory."
        elif diff_pct < 0:
            positioning = f"Listed below the {suburb} median of {fmt_price(median)} — more affordable end of the market."
        elif diff_pct > 20:
            positioning = f"At {fmt_price(price)}, it's above the {suburb} median of {fmt_price(median)} — premium end of the market."
        else:
            positioning = f"Listed just above the {suburb} median of {fmt_price(median)}."

    address = prop.get("street_address", prop.get("address", "A property"))

    msg = f"""{address} — {suburb}

Open {insp['day']} at {insp['start']}.

{bed}-bed {bath}-bath {ptype.lower()}, listed at {prop.get('price', 'contact agent')}.

{positioning}

Follow us to see how much it sells for.

fieldsestate.com.au/for-sale"""

    return msg, "open_home_spotlight"


def template_entry_price_watch(suburbs, properties=None, **kw):
    """The cheapest listed property in each core suburb — what entry level looks like."""
    if not properties:
        properties = get_individual_properties()

    entries = []
    for suburb_key in CORE_SUBURBS:
        suburb_props = [p for p in properties if p["_suburb_key"] == suburb_key]
        priced = [(p, parse_price_value(p.get("price", ""))) for p in suburb_props]
        priced = [(p, v) for p, v in priced if v is not None]
        if priced:
            priced.sort(key=lambda x: x[1])
            cheapest_prop, cheapest_price = priced[0]
            entries.append({
                "prop": cheapest_prop,
                "price_val": cheapest_price,
                "suburb": SUBURB_DISPLAY.get(suburb_key, suburb_key),
                "total": len(suburb_props),
            })

    if not entries:
        return None, None

    lines = []
    for e in entries:
        p = e["prop"]
        bed = p.get("bedrooms", "?")
        ptype = p.get("property_type", "property")
        addr = p.get("street_address", "")
        lines.append(f"  {e['suburb']}: {fmt_price(e['price_val'])} — {bed}-bed {ptype.lower()} at {addr}")

    cheapest_overall = min(entries, key=lambda e: e["price_val"])

    msg = f"""What does entry-level money buy right now?

Here's the cheapest listed property in each of our target suburbs:

""" + "\n".join(lines) + f"""

{cheapest_overall['suburb']} has the lowest entry point at {fmt_price(cheapest_overall['price_val'])}.

These numbers shift daily. If you're watching for a way in, follow us — we'll track what these sell for.

fieldsestate.com.au/for-sale"""

    return msg, "entry_price_watch"


def template_median_showcase(suburbs, properties=None, **kw):
    """What does median money buy? Find the property closest to median in a suburb."""
    if not properties:
        properties = get_individual_properties()

    candidates = [s for s in CORE_SUBURBS if s in suburbs and suburbs[s].get("median_price")]
    if not candidates:
        return None, None

    suburb_key = random.choice(candidates)
    median = suburbs[suburb_key]["median_price"]
    suburb_name = SUBURB_DISPLAY.get(suburb_key, suburb_key)

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
    ptype = prop.get("property_type", "property")

    insp_line = ""
    inspections = prop.get("inspection_times") or []
    if inspections:
        details = parse_inspection_details(inspections[0])
        if details["start"]:
            insp_line = f"\nOpen for inspection: {details['day']} at {details['start']}.\n"

    msg = f"""What does {fmt_price(median)} buy in {suburb_name}?

The median asking price in {suburb_name} right now is {fmt_price(median)}. Here's a property right on that mark:

{prop.get('street_address', prop.get('address', ''))}
{bed} bed · {bath} bath · {car} car — {ptype}
Listed at {prop.get('price', 'N/A')}
{insp_line}
This is what middle-of-the-market money gets you in {suburb_name} today. {suburbs[suburb_key]['total']} properties are currently for sale here.

fieldsestate.com.au/for-sale"""

    return msg, "median_showcase"


def template_weekend_preview(suburbs, properties=None, **kw):
    """Friday post — 3-5 notable open homes for the weekend."""
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
            day = "Saturday" if p in sat_props else "Sunday"
            all_weekend.append({**p, "_weekend_day": day})

    if len(all_weekend) < 2:
        return None, None

    # Price all candidates
    entries = []
    for p in all_weekend:
        price = parse_price_value(p.get("price", ""))
        if price:
            entries.append((p, price))

    if len(entries) < 2:
        return None, None

    entries.sort(key=lambda x: x[1])

    # Pick: cheapest, one near median, most expensive, one random
    selected = [entries[0]]  # cheapest
    if len(entries) > 2:
        mid_idx = len(entries) // 2
        selected.append(entries[mid_idx])
    selected.append(entries[-1])  # most expensive
    remaining = [e for e in entries if e not in selected]
    if remaining and len(selected) < 5:
        selected.append(random.choice(remaining))

    # Deduplicate
    seen = set()
    unique = []
    for s in selected:
        pid = str(s[0].get("_id", ""))
        if pid not in seen:
            seen.add(pid)
            unique.append(s)
    selected = unique[:5]

    total_weekend = len(all_weekend)

    lines = []
    for prop, price in selected:
        insp = prop["_inspections"][0]
        suburb = prop["_suburb_display"]
        bed = prop.get("bedrooms", "?")
        ptype = prop.get("property_type", "property")
        addr = prop.get("street_address", "")
        lines.append(f"  {addr} ({suburb}) — {bed}-bed {ptype.lower()}, {fmt_price(price)}\n  Open {insp['day']} {insp['start']}")

    msg = f"""Weekend Open Home Preview — {total_weekend} homes open this weekend

Here are a few worth seeing if you want to get a read on the market:

""" + "\n\n".join(lines) + f"""

These range from {fmt_price(selected[0][1])} to {fmt_price(selected[-1][1])} — a good cross-section of what's available.

Full list tomorrow morning. Follow us so you don't miss it.

fieldsestate.com.au/for-sale"""

    return msg, "weekend_preview"


def template_saturday_open_list(suburbs, properties=None, **kw):
    """Saturday 6am — full curated open home list for today."""
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

    sections = []
    for suburb in sorted(by_suburb.keys()):
        props = by_suburb[suburb]
        props.sort(key=lambda p: p["_inspections"][0].get("start", ""))

        # Deduplicate by address
        seen_addrs = set()
        prop_lines = []
        for p in props:
            addr = p.get("street_address", "")
            if addr in seen_addrs:
                continue
            seen_addrs.add(addr)
            insp = p["_inspections"][0]
            price = p.get("price", "Contact agent")
            bed = p.get("bedrooms", "?")
            ptype = p.get("property_type", "")
            prop_lines.append(f"  {insp['start']} — {addr} ({bed}-bed {ptype.lower()}, {price})")

        sections.append(f"{suburb}:\n" + "\n".join(prop_lines))

    total = len(sat_props)

    msg = f"""Your open home list for today — {total} properties open across the southern Gold Coast.

""" + "\n\n".join(sections) + """

Get out and see a few. Even if you're not buying today, walking through 2-3 homes gives you a real sense of what the market feels like right now.

We'll follow up with what sells. Follow us to track it.

fieldsestate.com.au/for-sale"""

    return msg, "saturday_open_list"


def template_sold_results(suburbs, properties=None, **kw):
    """Monday — what sold recently."""
    sold_properties = get_recently_sold_properties()

    if not sold_properties:
        msg = """Last Week's Sales — Southern Gold Coast

No confirmed sales recorded in our target suburbs this past week.

Settlement timelines, delayed reporting, and private treaty deals mean some sales take time to appear in the data.

We track every sale across Robina, Burleigh Waters, and Varsity Lakes. When they land, you'll see them here.

fieldsestate.com.au"""
        return msg, "sold_results"

    # Sort by most recently detected
    sold_properties.sort(key=lambda p: p.get("moved_to_sold_date", p.get("sold_date", "")), reverse=True)

    # Take the most recent ones (up to 8)
    recent = sold_properties[:8]

    lines = []
    for p in recent:
        address = p.get("street_address", p.get("address", ""))
        suburb = p.get("_suburb_display", "")
        sale_price = p.get("sale_price", "undisclosed")
        days = p.get("days_on_market")
        ptype = p.get("property_type", "")
        bed = p.get("bedrooms", "?")
        sold_text = p.get("sold_date_text", "")

        line = f"  {address} ({suburb}) — {bed}-bed {ptype.lower()}"
        if sale_price and "undisclosed" not in str(sale_price).lower():
            line += f", sold {sale_price}"
        if days:
            line += f" ({days} days on market)"
        lines.append(line)

    total = len(recent)

    msg = f"""Recent Sales Results — {total} {'sale' if total == 1 else 'sales'} in our target suburbs

""" + "\n".join(lines) + """

We track every listing from day one through to sale. Follow us to see what's coming up next — and what it eventually sells for.

fieldsestate.com.au"""

    return msg, "sold_results"


def template_new_to_market(suburbs, properties=None, **kw):
    """Freshest listings this week."""
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
        # Fallback: use days_on_domain <= 7
        for p in properties:
            days = p.get("days_on_domain", 999)
            if isinstance(days, (int, float)) and days <= 7:
                new_listings.append((p, datetime.now()))

    if not new_listings:
        return None, None

    new_listings.sort(key=lambda x: x[1], reverse=True)

    lines = []
    for p, dt in new_listings[:8]:
        suburb = p["_suburb_display"]
        price = p.get("price", "Contact agent")
        bed = p.get("bedrooms", "?")
        ptype = p.get("property_type", "property")
        addr = p.get("street_address", "")
        days = p.get("days_on_domain", "")
        day_str = f" (listed {days} days ago)" if days and isinstance(days, int) else ""
        lines.append(f"  {addr} ({suburb}) — {bed}-bed {ptype.lower()}, {price}{day_str}")

    total = len(new_listings)

    msg = f"""New to market this week — {total} fresh {'listing' if total == 1 else 'listings'}

""" + "\n".join(lines) + """

New stock means new data points. We track every listing from day one through to sale.

fieldsestate.com.au/for-sale"""

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
