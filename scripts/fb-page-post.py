#!/usr/bin/env python3
"""
Post data-led content to the Fields Real Estate Facebook page.

Usage:
    python3 scripts/fb-page-post.py --generate          # Generate a post and print (don't publish)
    python3 scripts/fb-page-post.py --generate --post    # Generate and publish
    python3 scripts/fb-page-post.py --message "text"     # Post custom message
    python3 scripts/fb-page-post.py --message "text" --link https://fieldsestate.com.au/market
"""

import os
import sys
import json
import random
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ADS_TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes", "carrara", "worongary", "merrimac"]
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


def log_post(post_id, message, link, template_type):
    """Log the post to MongoDB for tracking."""
    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]
    db["fb_page_posts"].insert_one({
        "post_id": post_id,
        "message": message[:200],
        "link": link,
        "template_type": template_type,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "source": "fb-page-post.py",
    })
    client.close()


# ── Data collection ──────────────────────────────────────────────────────

def get_suburb_data():
    """Pull live listing data for post generation."""
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
            p = l.get("price", "")
            if not isinstance(p, str):
                continue
            # Extract first dollar amount from strings like "Offers above $845,000"
            import re
            match = re.search(r'\$[\d,]+(?:\.\d+)?', p)
            if match:
                num_str = match.group().replace("$", "").replace(",", "")
                try:
                    val = int(float(num_str))
                    if 100000 < val < 20000000:
                        prices.append(val)
                except (ValueError, TypeError):
                    pass

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


def fmt_price(p):
    if p is None:
        return "N/A"
    if p >= 1000000:
        m = p / 1000000
        return f"${m:.1f}M" if m != int(m) else f"${int(m)}M"
    return f"${p:,.0f}"


# ── Post templates ───────────────────────────────────────────────────────

def template_suburb_snapshot(suburbs):
    """Single suburb market snapshot."""
    suburb_key = random.choice([s for s in suburbs if suburbs[s]["total"] >= 10])
    s = suburbs[suburb_key]
    name = s["display_name"]

    # Property type breakdown
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


def template_price_comparison(suburbs):
    """What does $X buy across suburbs?"""
    # Pick a price point that's common
    price_point = random.choice([700000, 800000, 900000, 1000000, 1200000])
    results = []

    for key, s in suburbs.items():
        if not s["prices"]:
            continue
        # Count listings around this price (within 15%)
        lower = price_point * 0.85
        upper = price_point * 1.15
        matches = [p for p in s["prices"] if lower <= p <= upper]
        if matches:
            avg_beds = None
            results.append({
                "name": s["display_name"],
                "count": len(matches),
                "total": s["total"],
            })

    if len(results) < 2:
        return None, None

    results.sort(key=lambda x: -x["count"])
    lines = []
    for r in results[:4]:
        lines.append(f"  {r['name']}: {r['count']} options (of {r['total']} total)")

    msg = f"""What does {fmt_price(price_point)} buy on the Southern Gold Coast?

We looked at every listing within 15% of {fmt_price(price_point)} across our target suburbs:

""" + "\n".join(lines)

    msg += f"""

{'More choice' if results[0]['count'] > results[-1]['count'] else 'Tight supply'} in {results[0]['name']}, {'fewer options' if results[-1]['count'] < 5 else 'solid selection'} in {results[-1]['name']}.

All data is live. Updated daily from {len(suburbs)} suburbs we track.

fieldsestate.com.au"""
    return msg, "price_comparison"


def template_listing_count(suburbs):
    """Total listings across all tracked suburbs."""
    total = sum(s["total"] for s in suburbs.values())
    by_count = sorted(suburbs.items(), key=lambda x: -x[1]["total"])

    lines = []
    for key, s in by_count:
        if s["total"] > 0:
            lines.append(f"  {s['display_name']}: {s['total']}")

    msg = f"""{total} properties are currently for sale across the Southern Gold Coast suburbs we track.

Breakdown:
""" + "\n".join(lines)

    most = by_count[0][1]
    msg += f"""

{most['display_name']} has the most choice right now with {most['total']} active listings.

We update this data every day. See the full breakdown at fieldsestate.com.au/for-sale"""
    return msg, "listing_count"


def template_bedroom_breakdown(suburbs):
    """What bedroom counts dominate in a suburb."""
    suburb_key = random.choice([s for s in suburbs if suburbs[s]["total"] >= 10 and suburbs[s]["beds"]])
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


TEMPLATES = [
    template_suburb_snapshot,
    template_price_comparison,
    template_listing_count,
    template_bedroom_breakdown,
]


def generate_post(suburbs):
    """Pick a random template and generate a post."""
    random.shuffle(TEMPLATES)
    for template_fn in TEMPLATES:
        msg, template_type = template_fn(suburbs)
        if msg:
            return msg, template_type
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Post to Fields Real Estate Facebook page")
    parser.add_argument("--generate", action="store_true", help="Auto-generate a data-led post")
    parser.add_argument("--post", action="store_true", help="Actually publish (default: dry run)")
    parser.add_argument("--message", type=str, help="Custom message to post")
    parser.add_argument("--link", type=str, help="URL to attach to the post")
    args = parser.parse_args()

    if args.generate:
        print("Pulling suburb data...")
        suburbs = get_suburb_data()
        message, template_type = generate_post(suburbs)
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
