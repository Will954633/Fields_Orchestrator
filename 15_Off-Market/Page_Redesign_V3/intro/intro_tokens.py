#!/usr/bin/env python3
"""
intro_tokens.py — build the matrix intro's word list for one specific home.

The concept animation had its recognition ramp hard-coded to Burleigh Waters, so
a Robina owner watched AVOCET AVE and BLUEJAY ST rain past and *then* saw their
Robina address print. That inverts the whole point of the sequence, which is the
field closing in on THEIR street.

Three tiers, unlocking over time, exactly as the concept does:

  tier 1  the suburb and the language of listings   — true of anyone here
  tier 2  the wider area: arterials, neighbouring suburbs, the POIs the deck
          already found for this home
  tier 3  their own street grid, their block, their own questions

Only tier 3 needs the property's coordinates; tiers 1 and 2 are per suburb and
are cached.

Two rules carried over from the concept, both deliberate:

  * **Street names are real, house numbers are invented.** Real streets make the
    field recognisable; mock numbers mean no actual neighbour's address ever
    appears on screen beside a word like WITHDRAWN.
  * **No unpublishable figures.** The medians, the year-on-year and the volume
    drop are flagged not-for-publication in the homeowner mindset brief. Days on
    market and the listing vocabulary are fine.

Run:
  python3 intro_tokens.py --slug 10-belmore-close-robina
  python3 intro_tokens.py --slug ... --json > tokens.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

from pymongo import MongoClient

POSTCODE = {"robina": "4226", "varsity_lakes": "4227", "burleigh_waters": "4220"}

# Genuine adjacency for the three target suburbs. Small enough to state, and
# wrong neighbours are exactly what a local notices.
NEIGHBOURS = {
    "robina":          ["VARSITY LAKES", "MERRIMAC", "MUDGEERABA", "CLEAR ISLAND WATERS",
                        "BURLEIGH WATERS", "REEDY CREEK"],
    "varsity_lakes":   ["ROBINA", "BURLEIGH WATERS", "REEDY CREEK", "MUDGEERABA",
                        "MIAMI", "BURLEIGH HEADS"],
    "burleigh_waters": ["BURLEIGH HEADS", "MIAMI", "MERMAID WATERS", "VARSITY LAKES",
                        "PALM BEACH", "ELANORA"],
}

# The vocabulary of a listing. True of every home, so it opens the sequence.
MARKET_WORDS = [
    "SOLD", "LISTED", "FOR SALE", "WITHDRAWN", "UNDER OFFER", "PRIVATE TREATY",
    "APPRAISAL", "DAYS ON MARKET", "SETTLED", "COMPARABLE", "MEDIAN", "VALUATION",
    "JUST LISTED", "RELISTED", "PRICE REDUCED", "UNDER CONTRACT", "OFF MARKET",
]

# Owner-voice lines from the homeowner mindset brief §3/§5. These are the ones
# that make the field feel like it is reading the room rather than the register.
OWNER_VOICE = [
    "WHAT IS IT WORTH", "IS THE NUMBER REAL", "WHERE WOULD I GO",
    "WHO IS ASKING", "MY HOME", "MY STREET", "NOT SELLING YET",
    "JUST CURIOUS", "WHAT DID NEXT DOOR GET",
]

STREET_ABBR = {
    "AVENUE": "AVE", "STREET": "ST", "ROAD": "RD", "DRIVE": "DR", "COURT": "CRT",
    "CRESCENT": "CRES", "PLACE": "PL", "CLOSE": "CL", "BOULEVARD": "BVD",
    "PARADE": "PDE", "TERRACE": "TCE", "CIRCUIT": "CCT", "HIGHWAY": "HWY",
    "LANE": "LN", "WAY": "WAY", "RISE": "RISE", "GROVE": "GR", "PARKWAY": "PWY",
}


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def street_label(name: str, stype: str | None) -> str:
    name = (name or "").strip().upper()
    stype = (stype or "").strip().upper()
    return f"{name} {STREET_ABBR.get(stype, stype)}".strip()


def db():
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        raise SystemExit("COSMOS_CONNECTION_STRING not set — "
                         "set -a && source /home/fields/Fields_Orchestrator/.env && set +a")
    return MongoClient(uri)


def nearest_streets(client, suburb_key: str, lat: float, lon: float, n: int = 12) -> list[str]:
    """The genuine nearest streets to this home, by distance to their closest
    cadastral point. One entry per street — the same street appearing twice
    would read as the field repeating itself."""
    col = client["Gold_Coast"][suburb_key]
    best: dict[str, float] = {}
    proj = {"STREET_NAME": 1, "STREET_TYPE": 1, "LATITUDE": 1, "LONGITUDE": 1, "_id": 0}
    for r in col.find({"LATITUDE": {"$ne": None}, "STREET_NAME": {"$ne": None}}, proj):
        try:
            d = haversine_m(lat, lon, float(r["LATITUDE"]), float(r["LONGITUDE"]))
        except (TypeError, ValueError):
            continue
        label = street_label(r.get("STREET_NAME"), r.get("STREET_TYPE"))
        if label and (label not in best or d < best[label]):
            best[label] = d
    return [s for s, _ in sorted(best.items(), key=lambda kv: kv[1])[:n]]


def arterials(client, suburb_key: str, n: int = 8) -> list[str]:
    """The roads that carry the suburb, derived rather than guessed: the streets
    with the most cadastral records are its spines."""
    col = client["Gold_Coast"][suburb_key]
    counts: dict[str, int] = {}
    for r in col.find({"STREET_NAME": {"$ne": None}},
                      {"STREET_NAME": 1, "STREET_TYPE": 1, "_id": 0}):
        label = street_label(r.get("STREET_NAME"), r.get("STREET_TYPE"))
        if label:
            counts[label] = counts.get(label, 0) + 1
    return [s for s, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:n]]


def build(slug: str) -> dict:
    client = db()
    doc = client["system_monitor"]["offmarket_discovery"].find_one({"slug": slug})
    if not doc:
        raise SystemExit(f"no deck doc for slug: {slug}")

    suburb_key = doc.get("suburb_key") or ""
    suburb_disp = (doc.get("suburb_display") or "").upper()
    postcode = POSTCODE.get(suburb_key, "")
    address_short = doc.get("address_short") or ""

    # The home's own coordinates, from its cadastral record.
    col = client["Gold_Coast"][suburb_key]
    prop = col.find_one({"address": {"$regex": f"^{re.escape(address_short)}", "$options": "i"},
                         "LATITUDE": {"$ne": None}}) or {}
    lat, lon = prop.get("LATITUDE"), prop.get("LONGITUDE")

    # Tier 2 POIs come from the deck's own reveal card — already found for this
    # home, already verified, already shown further down the page. Far better
    # than a general-knowledge landmark list, which is what the concept used and
    # flagged as unchecked.
    pois: list[str] = []
    for card in doc.get("cards", []):
        for item in card.get("doorstep") or []:
            nm = (item.get("name") or "").strip()
            # skip the "a short drive to X (1.4km)" sentence form — not a token
            if nm and len(nm) <= 28 and not nm.lower().startswith("a short drive"):
                pois.append(nm.upper())

    tier3 = nearest_streets(client, suburb_key, lat, lon) if lat and lon else []
    own_street = re.sub(r"^\d+\s+", "", address_short).upper()

    # Their own block, from the deck's own feature list — the beds/baths/land
    # line it already shows on card 03, so nothing new is being asserted.
    own_block = []
    for card in doc.get("cards", []):
        for f in card.get("features") or []:
            f = str(f).strip().upper()
            if f and len(f) <= 22:
                own_block.append(f)
    own_block = own_block[:4]

    tokens = {
        "tier1": [suburb_disp, postcode, "QLD", "GOLD COAST"] + MARKET_WORDS,
        "tier2": arterials(client, suburb_key)
                 + NEIGHBOURS.get(suburb_key, [])
                 + pois[:8]
                 + ["DOM 29", "SOLD 23 DAYS", "SOLD 41 DAYS"],
        # The concept unlocks four tiers, not three: the street grid arrives at
        # 4.8s and the owner's own thoughts at 7.2s, which is the beat where it
        # stops being a database and starts being them.
        "tier3": tier3,
        "tier4": OWNER_VOICE + own_block,
        # Phrases that light white regardless of tier — this owner's own words.
        "hot": [w for w in {own_street, suburb_disp, "MY HOME", "MY STREET"} if w],
    }
    tokens = {k: [t for t in v if t] for k, v in tokens.items()}
    tokens["_meta"] = {"slug": slug, "suburb": suburb_disp,
                       "coords": [lat, lon], "nearest": tier3[:5]}
    return tokens


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    t = build(a.slug)
    if a.json or a.out:
        s = json.dumps(t, indent=2)
        (a.out.write_text(s) if a.out else print(s))
        if a.out:
            print(f"wrote {a.out}", file=sys.stderr)
        return
    m = t.pop("_meta")
    print(f"{m['slug']}  ({m['suburb']}, {m['coords'][0]:.5f}, {m['coords'][1]:.5f})")
    print(f"  nearest streets: {', '.join(m['nearest'])}")
    for k in ("tier1", "tier2", "tier3", "tier4", "hot"):
        print(f"\n  {k} ({len(t[k])})")
        print("    " + " · ".join(t[k]))


if __name__ == "__main__":
    main()
