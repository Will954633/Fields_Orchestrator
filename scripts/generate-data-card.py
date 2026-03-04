#!/usr/bin/env python3
"""
Generate branded 1080×1080 data card images for Facebook posts.

Pulls live data from MongoDB and renders it onto a Fields Estate branded template.

Usage:
    python3 scripts/generate-data-card.py --template suburb_snapshot --suburb Robina --output /tmp/card.png
    python3 scripts/generate-data-card.py --template price_comparison --output /tmp/card.png
    python3 scripts/generate-data-card.py --template sold_highlight --suburb Robina --output /tmp/card.png
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient
from PIL import Image, ImageDraw, ImageFont

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

# ── Brand palette ─────────────────────────────────────────────────────────
NAVY = (27, 43, 59)        # #1B2B3B
GOLD = (200, 169, 110)     # #C8A96E
MID = (138, 155, 168)      # #8A9BA8
WHITE = (255, 255, 255)
DARK_BG = (18, 24, 33)     # #121821
CARD_BG = (24, 34, 48)     # #182230
LIGHT_TEXT = (226, 232, 240)  # #e2e8f0

# ── Fonts ─────────────────────────────────────────────────────────────────
FONT_DIR = "/usr/share/fonts/truetype/liberation"

def font(size, bold=False):
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    return ImageFont.truetype(f"{FONT_DIR}/{name}", size)


SUBURB_DISPLAY = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
    "carrara": "Carrara",
    "worongary": "Worongary",
    "merrimac": "Merrimac",
    "mudgeeraba": "Mudgeeraba",
    "reedy_creek": "Reedy Creek",
    "burleigh_heads": "Burleigh Heads",
}

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes", "carrara", "worongary", "merrimac"]


def fmt_price(p):
    if p is None:
        return "N/A"
    return f"${p:,.0f}"


# ── Data fetchers ─────────────────────────────────────────────────────────

def get_suburb_stats(suburb=None):
    """Get suburb statistics from MongoDB."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast_Currently_For_Sale"]

    if suburb:
        suburbs_to_check = [suburb.lower().replace(" ", "_")]
    else:
        suburbs_to_check = TARGET_SUBURBS

    results = {}
    for sub in suburbs_to_check:
        listings = list(db[sub].find({}, {"price": 1, "bedrooms": 1, "property_type": 1}))
        if not listings:
            continue

        import re
        prices = []
        for l in listings:
            p = l.get("price", "")
            if not isinstance(p, str):
                continue
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

        results[sub] = {
            "display_name": SUBURB_DISPLAY.get(sub, sub.replace("_", " ").title()),
            "total": len(listings),
            "prices": sorted(prices),
            "median_price": sorted(prices)[len(prices) // 2] if prices else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "types": types,
            "beds": beds,
        }

    client.close()
    return results


def get_recent_sold(suburb):
    """Get recent sold properties for a suburb."""
    client = MongoClient(COSMOS_URI)
    db = client["Gold_Coast_Recently_Sold"]
    sub_key = suburb.lower().replace(" ", "_")

    docs = list(db[sub_key].find(
        {},
        {"address": 1, "price": 1, "bedrooms": 1, "bathrooms": 1,
         "property_type": 1, "sold_date": 1}
    ).sort("_id", -1).limit(5))

    client.close()
    return docs


# ── Drawing helpers ───────────────────────────────────────────────────────

def draw_bottom_bar(draw, width, height):
    """Draw the branded bottom bar."""
    bar_h = 70
    draw.rectangle([(0, height - bar_h), (width, height)], fill=NAVY)
    # Gold accent line
    draw.rectangle([(0, height - bar_h), (width, height - bar_h + 3)], fill=GOLD)
    # Brand text
    f = font(18)
    text = "fieldsestate.com.au  •  Know your ground"
    bbox = draw.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, height - bar_h + 24), text, fill=GOLD, font=f)


def draw_header(draw, title, subtitle, width):
    """Draw card header with title and subtitle."""
    y = 50
    # Title
    f_title = font(42, bold=True)
    draw.text((60, y), title, fill=WHITE, font=f_title)
    y += 56
    # Subtitle
    f_sub = font(20)
    draw.text((60, y), subtitle, fill=MID, font=f_sub)
    # Gold underline
    y += 36
    draw.rectangle([(60, y), (width - 60, y + 3)], fill=GOLD)
    return y + 30


def draw_stat_box(draw, x, y, w, h, value, label):
    """Draw a stat box with value and label."""
    draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=12, fill=CARD_BG)
    # Value
    f_val = font(36, bold=True)
    draw.text((x + 20, y + 18), str(value), fill=WHITE, font=f_val)
    # Label
    f_lbl = font(14)
    draw.text((x + 20, y + h - 34), label, fill=MID, font=f_lbl)


# ── Card templates ────────────────────────────────────────────────────────

def card_suburb_snapshot(suburb_key, data):
    """Generate a suburb snapshot data card."""
    s = data[suburb_key]
    name = s["display_name"]

    img = Image.new("RGB", (1080, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Header
    y = draw_header(draw, name, "Market Snapshot  •  " + datetime.now().strftime("%B %Y"), 1080)
    y += 20

    # Stat boxes — row 1
    box_w = 290
    box_h = 110
    gap = 30
    start_x = 60

    draw_stat_box(draw, start_x, y, box_w, box_h,
                  str(s["total"]), "ACTIVE LISTINGS")
    draw_stat_box(draw, start_x + box_w + gap, y, box_w, box_h,
                  fmt_price(s["median_price"]), "MEDIAN PRICE")
    draw_stat_box(draw, start_x + 2 * (box_w + gap), y, box_w, box_h,
                  fmt_price(s["min_price"]), "FROM")
    y += box_h + 24

    # Row 2
    draw_stat_box(draw, start_x, y, box_w, box_h,
                  fmt_price(s["max_price"]), "UP TO")
    price_count = len(s["prices"])
    draw_stat_box(draw, start_x + box_w + gap, y, box_w, box_h,
                  str(price_count), "PRICED LISTINGS")

    # Beds stat
    most_common_bed = max(s["beds"].items(), key=lambda x: x[1]) if s["beds"] else ("?", 0)
    draw_stat_box(draw, start_x + 2 * (box_w + gap), y, box_w, box_h,
                  f"{most_common_bed[0]}-bed", "MOST COMMON")
    y += box_h + 40

    # Property type breakdown
    f_section = font(22, bold=True)
    draw.text((60, y), "Property Mix", fill=GOLD, font=f_section)
    y += 36

    f_row = font(20)
    sorted_types = sorted(s["types"].items(), key=lambda x: -x[1])
    for pt, count in sorted_types[:5]:
        pct = round(count / s["total"] * 100)
        # Bar
        bar_max_w = 500
        bar_w = int(bar_max_w * (count / s["total"]))
        draw.rounded_rectangle([(60, y + 2), (60 + bar_w, y + 28)], radius=4, fill=GOLD)
        # Label
        label = f"{pt}s: {count} ({pct}%)"
        draw.text((580, y), label, fill=LIGHT_TEXT, font=f_row)
        y += 40

    # Bottom bar
    draw_bottom_bar(draw, 1080, 1080)

    return img


def card_price_comparison(data):
    """Generate a price comparison across suburbs."""
    img = Image.new("RGB", (1080, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Header
    y = draw_header(draw, "Price Comparison", "Southern Gold Coast  •  " + datetime.now().strftime("%B %Y"), 1080)
    y += 20

    # Sort suburbs by median price
    suburbs_with_prices = [(k, v) for k, v in data.items() if v["median_price"]]
    suburbs_with_prices.sort(key=lambda x: -(x[1]["median_price"] or 0))

    f_name = font(24, bold=True)
    f_stat = font(18)
    f_price = font(32, bold=True)

    for key, s in suburbs_with_prices[:5]:
        # Suburb card
        draw.rounded_rectangle([(60, y), (1020, y + 130)], radius=12, fill=CARD_BG)

        # Name
        draw.text((80, y + 15), s["display_name"], fill=WHITE, font=f_name)

        # Median price
        draw.text((80, y + 50), fmt_price(s["median_price"]), fill=GOLD, font=f_price)

        # Stats on right
        stats_text = f"{s['total']} listings  •  {fmt_price(s['min_price'])} – {fmt_price(s['max_price'])}"
        draw.text((80, y + 95), stats_text, fill=MID, font=f_stat)

        y += 148

    # Bottom bar
    draw_bottom_bar(draw, 1080, 1080)

    return img


def card_sold_highlight(suburb_key, data, sold_docs):
    """Generate a sold property highlight card."""
    s = data.get(suburb_key, {})
    name = s.get("display_name", suburb_key.replace("_", " ").title())

    img = Image.new("RGB", (1080, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Header
    y = draw_header(draw, f"Recently Sold", f"{name}  •  " + datetime.now().strftime("%B %Y"), 1080)
    y += 20

    f_addr = font(22, bold=True)
    f_price = font(30, bold=True)
    f_detail = font(16)

    if not sold_docs:
        draw.text((60, y), "No recent sold data available", fill=MID, font=font(24))
    else:
        for doc in sold_docs[:4]:
            draw.rounded_rectangle([(60, y), (1020, y + 150)], radius=12, fill=CARD_BG)

            addr = doc.get("address", "Unknown address")
            draw.text((80, y + 18), addr[:40], fill=WHITE, font=f_addr)

            price = doc.get("price", "")
            draw.text((80, y + 52), str(price), fill=GOLD, font=f_price)

            beds = doc.get("bedrooms", "?")
            baths = doc.get("bathrooms", "?")
            ptype = doc.get("property_type", "")
            sold_date = doc.get("sold_date", "")
            detail = f"{beds} bed  •  {baths} bath  •  {ptype}"
            if sold_date:
                detail += f"  •  {sold_date}"
            draw.text((80, y + 100), detail[:60], fill=MID, font=f_detail)

            y += 168

    # Bottom bar
    draw_bottom_bar(draw, 1080, 1080)

    return img


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate branded data card images")
    parser.add_argument("--template", required=True,
                        choices=["suburb_snapshot", "price_comparison", "sold_highlight"],
                        help="Card template to generate")
    parser.add_argument("--suburb", type=str, help="Suburb name (required for snapshot/sold)")
    parser.add_argument("--output", type=str, default="/tmp/data-card.png",
                        help="Output PNG path")
    args = parser.parse_args()

    # Validate
    if args.template in ("suburb_snapshot", "sold_highlight") and not args.suburb:
        print("ERROR: --suburb is required for this template")
        sys.exit(1)

    suburb_key = args.suburb.lower().replace(" ", "_") if args.suburb else None

    # Fetch data
    print("Fetching data from MongoDB...")
    if args.template == "price_comparison":
        data = get_suburb_stats()
    else:
        data = get_suburb_stats(args.suburb)

    if suburb_key and suburb_key not in data and args.template != "price_comparison":
        print(f"ERROR: No data found for suburb '{args.suburb}'")
        sys.exit(1)

    # Generate card
    print(f"Generating {args.template} card...")
    if args.template == "suburb_snapshot":
        img = card_suburb_snapshot(suburb_key, data)
    elif args.template == "price_comparison":
        img = card_price_comparison(data)
    elif args.template == "sold_highlight":
        sold_docs = get_recent_sold(suburb_key)
        img = card_sold_highlight(suburb_key, data, sold_docs)

    # Save
    img.save(args.output, "PNG", quality=95)
    print(f"Saved: {args.output} ({os.path.getsize(args.output):,} bytes)")


if __name__ == "__main__":
    main()
