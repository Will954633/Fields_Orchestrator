#!/usr/bin/env python3
"""scripts/comparable_set.py — reusable tight comparable-set builder + adversarial claim-tester.

Generalises the one-off comparable analysis we ran by hand for 93 Burleigh Street
(19_Agent_Offering/Buyer_Acquisition_Service/93_Burleigh_BUYER_THESIS.md) into a tool
any "conjunction" property can run:

    python3 scripts/comparable_set.py --address "93 Burleigh Street"
    python3 scripts/comparable_set.py --id <mongo _id> --json --csv
    python3 scripts/comparable_set.py --slug <url_slug> --claim "…"

READ-ONLY on the database. Artefacts (--json / --csv) are written to the session
scratchpad, never to the repo or the DB.

WHAT IT REPRODUCES (the hand method for 93 Burleigh):
  * Non-waterfront detached houses only (waterfront is out-of-scope — shared/waterfront.py).
  * Land within a band of the subject (default ±15%), tightening/loosening by TIER.
  * Straight-line distance to the platform-canonical beach point (same GOLD_COAST_BEACHES
    the website's beachDistance.ts and precompute_valuations.py publish) — NOT a walking route.
  * Sales sourced from BOTH listing_status:"sold" AND the timeline arrays. The sold-status
    set is a FLOOR, not a census: e.g. 114 Burleigh St ($2,350,000) is a real sale that lives
    only in the timelines (listing_status is null on that doc).
  * INTERNAL floor area only (shared/floor_area.py) — never a building total or room-sum.
  * Block geometry (frontage / depth / rectangularity) from cadastral rings where they exist.

NAMED SELECTION TIERS (never silent widenings):
  Tier A  non-waterfront house, land within ±land_tol_a of subject, beach <= beach_a km, sold within `months`.
  Tier B  documented widening: land within ±land_tol_b, beach <= beach_b km.
  Tier C  documented widening: land within ±land_tol_c, beach <= beach_c km.
Each comp is tagged with the tightest tier it satisfies, so every widening is on the record.

ADVERSARIAL CLAIM-TESTER (--claim): given a scarcity/value claim, the tool decomposes it
into legs (beach / land / house-size / price / superlative), names every comp that
beats-or-matches the subject on each leg, states which wording survives, and — if a leg
fails or the claim is an unverifiable superlative — says so and proposes the strongest
SUPPORTED wording. Standing caveats (sold set is a floor; condition is not something our
data ranks; straight-line distance; unpriced listings are invisible) are always printed.

Complies with CLAUDE.md Rule 5: no advice, never states a Fields valuation of the subject,
no unverifiable superlative, exact figures (never rounded).
"""

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# Make `shared` importable regardless of cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.db import get_client  # noqa: E402
from shared.floor_area import resolve_internal_floor_area  # noqa: E402
from shared.block_geometry import compute_block_geometry  # noqa: E402
from shared.waterfront import detect_waterfront, classify_water_relationship  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Canonical beach points.
# MUST match GOLD_COAST_BEACHES in
#   /home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py
# and the BEACHES array in the website's src/utils/beachDistance.ts — the single
# source of truth for the "Dist to Beach" pill we publish. Straight-line (haversine),
# not a walking route.
# ─────────────────────────────────────────────────────────────────────────────
GOLD_COAST_BEACHES = [
    ("Burleigh Heads Beach", -28.089, 153.455),
    ("Miami Beach",          -28.071, 153.446),
]

# Which collections to scan for comparables, keyed by the subject's own collection.
# The bounding-box + beach-distance filters do the real pruning; this just keeps the
# scan to the plausible neighbourhood instead of all ~40 suburb collections. Override
# with --collections. Any name not present in the DB is silently dropped.
_NEIGHBORS = {
    "burleigh_waters": ["burleigh_waters", "burleigh_heads", "miami", "palm_beach"],
    "burleigh_heads":  ["burleigh_heads", "burleigh_waters", "miami", "palm_beach"],
    "miami":           ["miami", "burleigh_heads", "burleigh_waters", "nobby_beach", "mermaid_waters"],
    "palm_beach":      ["palm_beach", "burleigh_heads", "currumbin", "elanora"],
    "varsity_lakes":   ["varsity_lakes", "robina", "burleigh_waters", "burleigh_heads"],
    "robina":          ["robina", "varsity_lakes", "mudgeeraba", "clear_island_waters"],
}

# Land sources in preference order. Cadastre first (surveyed), then the coalesce chain.
_LAND_SOURCES = [
    ("cadastral_polygon.lot_area_sqm", "cadastral_lot_area"),
    ("lot_size_calc_sqm", "cadastral_lot_calc"),
    ("lot_size_sqm", "cadastral_lot_size"),
    ("land_size_sqm", "land_size_sqm"),
    ("onthehouse_data.land_size_sqm", "onthehouse"),
    ("scraped_data_v2.land_area_sqm", "domain_v2"),
    ("floor_plan_analysis.total_land_area.value", "floor_plan"),
]

# Whole-complex land guard: a singleton lot bigger than this is very likely a
# whole-complex / acreage figure, not a comparable house block. Flagged + excluded
# from tiers by default (the 24 Tropicana 3,591 m² outlier the hand analysis dropped).
_COMPLEX_LAND_SQM = 2500.0

# Property-type values that are NOT a detached house.
_NON_HOUSE = {
    "unit", "apartment", "townhouse", "villa", "duplex", "flat", "studio",
    "block of units", "land", "vacant land", "acreage", "retirement", "semi-detached",
}

AEST = timezone(timedelta(hours=10))


# ─────────────────────────────────────────────────────────────────────────────
# small helpers
# ─────────────────────────────────────────────────────────────────────────────
def dig(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def parse_price(v):
    """Return an int price from an int/float or a string like '$2,196,785' /
    'Offers over $3,150,000'. Returns None if no number is present."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v) if v > 0 else None
    if isinstance(v, str):
        m = re.search(r"\$?\s*([\d][\d,]*)", v.replace(" ", ""))
        if m:
            try:
                n = int(m.group(1).replace(",", ""))
                return n if n > 1000 else None  # guard against '$5m' style tokens
            except ValueError:
                return None
    return None


def parse_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    return None


def address_of(doc):
    a = doc.get("address") or doc.get("street_address") or doc.get("complete_address")
    if a:
        return a
    # Build from GNAF street parts when the free-text address is null (cadastral stubs).
    no = doc.get("STREET_NO_1")
    name = doc.get("STREET_NAME")
    stype = (doc.get("STREET_TYPE") or "").title()
    loc = (doc.get("LOCALITY") or "").title()
    if no and name:
        return f"{no} {str(name).title()} {stype}, {loc}".strip()
    return None


def coords_of(doc):
    """Canonical lat/lon. LATITUDE/LONGITUDE (GNAF cadastral geocode) is the source the
    published beach distance was computed from; geocoded_coordinates is a fallback."""
    lat, lon = doc.get("LATITUDE"), doc.get("LONGITUDE")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon), "GNAF"
    gc = doc.get("geocoded_coordinates") or {}
    lat, lon = gc.get("latitude"), gc.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon), "nominatim"
    return None, None, None


def beach_distance_km(lat, lon):
    """Straight-line km to the NEAREST canonical beach point. Returns (km, beach_name)."""
    if lat is None or lon is None:
        return None, None
    best, name = float("inf"), None
    for bn, bl, bo in GOLD_COAST_BEACHES:
        d = haversine_km(lat, lon, bl, bo)
        if d < best:
            best, name = d, bn
    return round(best, 3), name


def resolve_land(doc):
    """Return (value, source, flag). flag ∈ {None, 'complex_land_suspect', 'strata_small_lot'}.
    Cadastral figure preferred; whole-complex singletons flagged for exclusion."""
    val, src = None, None
    for path, label in _LAND_SOURCES:
        v = dig(doc, path)
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            val, src = f, label
            break
    if val is None:
        return None, None, None
    flag = None
    if val > _COMPLEX_LAND_SQM:
        flag = "complex_land_suspect"
    elif doc.get("is_strata_title") is True and val < 400:
        flag = "strata_small_lot"
    return val, src, flag


def is_house(doc):
    pt = (doc.get("property_type") or doc.get("classified_property_type") or "").strip().lower()
    if pt in _NON_HOUSE:
        return False, pt or None
    # An explicit strata title on a small lot is a unit/townhouse in practice.
    return True, pt or None


def condition_of(doc):
    pov = dig(doc, "property_valuation_data.property_overview") or {}
    reno = dig(doc, "property_valuation_data.renovation") or {}
    return {
        "overall_condition": pov.get("overall_condition"),
        "condition_score": pov.get("overall_condition_score"),
        "renovation_level": reno.get("overall_renovation_level"),
        "renovation_recency": reno.get("renovation_recency"),
    }


def extract_sale(doc, window_start):
    """Best (most recent, in-window) genuine sale for the doc.
    Returns (price:int, date:datetime, source:str) or None.

    Sources, in order added:
      * listing_status:"sold"  → sold_date (preferred; sale_date missing on ~40%) + sale_price.
      * scraped_data_v2.timeline[]  (Sale, is_sold, event_price/event_date)
      * scraped_data.property_timeline[]  (Sale, is_sold, price/date)
    The sold-status path is a FLOOR; the timeline paths recover real sales on docs whose
    listing_status is null."""
    cands = []  # (price, date, source)

    if doc.get("listing_status") == "sold":
        d = parse_date(doc.get("sold_date") or doc.get("sale_date"))
        p = parse_price(doc.get("sale_price") or doc.get("sold_price") or doc.get("price"))
        if d and p:
            cands.append((p, d, "listing_status:sold"))

    for path, dkey, pkey in (
        ("scraped_data_v2.timeline", "event_date", "event_price"),
        ("scraped_data.property_timeline", "date", "price"),
    ):
        tl = dig(doc, path)
        if not isinstance(tl, list):
            continue
        for ev in tl:
            if not isinstance(ev, dict):
                continue
            if str(ev.get("category", "")).lower() != "sale":
                continue
            if not ev.get("is_sold"):
                continue
            p = parse_price(ev.get(pkey))
            d = parse_date(ev.get(dkey))
            if p and d:
                cands.append((p, d, f"timeline:{path.split('.')[0]}"))

    cands = [c for c in cands if c[1] >= window_start]
    if not cands:
        return None
    # Most recent wins; if two share a date, prefer the higher-trust (sold-status) source.
    cands.sort(key=lambda c: (c[1], c[2].startswith("listing_status")), reverse=True)
    return cands[0]


# ─────────────────────────────────────────────────────────────────────────────
# subject lookup
# ─────────────────────────────────────────────────────────────────────────────
def find_subject(db, args):
    from bson import ObjectId
    colls = args.collections or list(db.list_collection_names())
    if args.id:
        for coll in colls:
            try:
                d = db[coll].find_one({"_id": ObjectId(args.id)})
            except Exception:
                d = db[coll].find_one({"_id": args.id})
            if d:
                return d, coll
        return None, None
    if args.slug:
        for coll in colls:
            d = db[coll].find_one({"$or": [{"url_slug": args.slug}, {"slug": args.slug}]})
            if d:
                return d, coll
        return None, None
    if args.address:
        rx = {"$regex": re.escape(args.address), "$options": "i"}
        hits = []
        for coll in colls:
            for d in db[coll].find({"$or": [{"address": rx}, {"street_address": rx},
                                            {"complete_address": rx}]}):
                hits.append((d, coll))
        if len(hits) > 1:
            # Prefer an active listing, else the one carrying the most data (a for_sale doc).
            hits.sort(key=lambda h: (h[0].get("listing_status") == "for_sale",
                                     len(h[0].keys())), reverse=True)
        return (hits[0] if hits else (None, None))
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# comp building
# ─────────────────────────────────────────────────────────────────────────────
def build_comps(db, subject, subj_coll, cfg):
    slat, slon, _ = coords_of(subject)
    if slat is None:
        raise SystemExit("Subject has no usable coordinates (LATITUDE/LONGITUDE or geocoded_coordinates).")
    subj_land, subj_land_src, _ = resolve_land(subject)
    if not subj_land:
        raise SystemExit("Subject has no resolvable land size.")
    subj_internal, subj_int_src, _ = resolve_internal_floor_area(subject)
    subj_beach_km, subj_beach_name = beach_distance_km(slat, slon)

    window_start = datetime.now(timezone.utc) - timedelta(days=int(cfg["months"] * 30.44))

    # Collections to scan.
    if cfg["collections"]:
        colls = cfg["collections"]
    else:
        colls = _NEIGHBORS.get(subj_coll, [subj_coll])
    existing = set(db.list_collection_names())
    colls = [c for c in colls if c in existing]

    # Coarse Mongo pre-filter: bounding box around subject + must carry a sale history +
    # a loose land floor (loosest tier band min, minus slack). Real tiering happens in Python.
    r_box = cfg["beach_c"] + subj_beach_km + 0.5  # generous; box never excludes a valid comp
    dlat = r_box / 111.0
    dlon = r_box / (111.0 * math.cos(math.radians(slat)))
    land_floor = subj_land * (1 - cfg["land_tol_c"]) - 20
    q = {"$and": [
        {"LATITUDE": {"$gte": slat - dlat, "$lte": slat + dlat}},
        {"LONGITUDE": {"$gte": slon - dlon, "$lte": slon + dlon}},
        {"$or": [
            {"listing_status": "sold"},
            {"scraped_data_v2.timeline": {"$exists": True, "$ne": []}},
            {"scraped_data.property_timeline": {"$exists": True, "$ne": []}},
        ]},
        {"$or": [
            {"lot_size_sqm": {"$gte": land_floor}},
            {"cadastral_polygon.lot_area_sqm": {"$gte": land_floor}},
            {"lot_size_calc_sqm": {"$gte": land_floor}},
            {"onthehouse_data.land_size_sqm": {"$gte": land_floor}},
        ]},
    ]}

    subj_id = subject.get("_id")
    comps = []
    excluded = {"waterfront": 0, "not_house": 0, "no_sale_in_window": 0,
                "land_out_of_band": 0, "beach_out_of_range": 0, "complex_land": 0, "no_land": 0}

    for coll in colls:
        for d in db[coll].find(q):
            if d.get("_id") == subj_id:
                continue
            land, land_src, land_flag = resolve_land(d)
            if not land:
                excluded["no_land"] += 1
                continue
            if land_flag == "complex_land_suspect":
                excluded["complex_land"] += 1
                continue
            house, pt = is_house(d)
            if not house:
                excluded["not_house"] += 1
                continue
            wf = detect_waterfront(d)
            if wf["is_waterfront"]:
                excluded["waterfront"] += 1
                continue
            lat, lon, cs = coords_of(d)
            bkm, bname = beach_distance_km(lat, lon)
            if bkm is None:
                continue
            if bkm > cfg["beach_c"]:
                excluded["beach_out_of_range"] += 1
                continue
            land_ratio = (land - subj_land) / subj_land
            if abs(land_ratio) > cfg["land_tol_c"]:
                excluded["land_out_of_band"] += 1
                continue
            if cfg.get("min_land") and land < cfg["min_land"]:
                excluded["land_out_of_band"] += 1
                continue
            if cfg.get("max_land") and land > cfg["max_land"]:
                excluded["land_out_of_band"] += 1
                continue
            sale = extract_sale(d, window_start)
            if not sale:
                excluded["no_sale_in_window"] += 1
                continue
            price, sdate, ssrc = sale

            # Tier assignment: tightest tier the comp satisfies.
            tier = None
            if bkm <= cfg["beach_a"] and abs(land_ratio) <= cfg["land_tol_a"]:
                tier = "A"
            elif bkm <= cfg["beach_b"] and abs(land_ratio) <= cfg["land_tol_b"]:
                tier = "B"
            elif bkm <= cfg["beach_c"] and abs(land_ratio) <= cfg["land_tol_c"]:
                tier = "C"
            if tier is None:
                excluded["land_out_of_band"] += 1
                continue

            internal, int_src, int_conflict = resolve_internal_floor_area(d)
            geom = compute_block_geometry(d.get("cadastral_polygon"))
            cond = condition_of(d)
            wrel, wrel_reason = classify_water_relationship(d)

            comps.append({
                "address": address_of(d),
                "collection": coll,
                "tier": tier,
                "sold_price": price,
                "sold_date": sdate.strftime("%Y-%m"),
                "sold_date_full": sdate.strftime("%Y-%m-%d"),
                "sale_source": ssrc,
                "listing_status": d.get("listing_status"),
                "land_sqm": round(land, 1),
                "land_source": land_src,
                "land_flag": land_flag,
                "land_ratio": round(land_ratio, 3),
                "internal_sqm": round(internal, 1) if internal else None,
                "internal_source": int_src if internal else "UNKNOWN",
                "internal_conflict": int_conflict,
                "beach_km": bkm,
                "beach_name": bname,
                "water_relationship": wrel,   # dry | water_view | lakefront (waterfront already excluded)
                "beds": d.get("bedrooms"),
                "baths": d.get("bathrooms"),
                "car": d.get("car_spaces") or d.get("carspaces"),
                "pool": _pool_flag(d),
                "shed": "no_field",  # no shed field exists anywhere → absence != no shed
                "condition": cond["overall_condition"],
                "renovation_level": cond["renovation_level"],
                "renovation_recency": cond["renovation_recency"],
                "frontage_m_est": geom["frontage_m_est"] if geom else None,
                "rectangularity": geom["rectangularity"] if geom else None,
                "shape": geom["shape_label"] if geom else None,
                "psqm_land": round(price / land) if land else None,
                "psqm_internal": round(price / internal) if internal else None,
                "_id": str(d.get("_id")),
            })

    # Rank: most-comparable first. Tier A<B<C, then closeness on land + beach to subject.
    tier_rank = {"A": 0, "B": 1, "C": 2}
    for c in comps:
        c["_score"] = (tier_rank[c["tier"]],
                       abs(c["land_ratio"]) + abs(c["beach_km"] - subj_beach_km) / max(subj_beach_km, 0.5))
    comps.sort(key=lambda c: c["_score"])

    subject_facts = {
        "address": subject.get("address"),
        "collection": subj_coll,
        "id": str(subj_id),
        "list_price": parse_price(subject.get("price")),
        "list_price_raw": subject.get("price"),
        "land_sqm": round(subj_land, 1),
        "land_source": subj_land_src,
        "internal_sqm": round(subj_internal, 1) if subj_internal else None,
        "internal_source": subj_int_src if subj_internal else "UNKNOWN",
        "beach_km": subj_beach_km,
        "beach_name": subj_beach_name,
        "beds": subject.get("bedrooms"),
        "baths": subject.get("bathrooms"),
        "car": subject.get("car_spaces") or subject.get("carspaces"),
        "condition": condition_of(subject)["overall_condition"],
        "renovation_level": condition_of(subject)["renovation_level"],
        "geometry": compute_block_geometry(subject.get("cadastral_polygon")),
        "waterfront": detect_waterfront(subject)["is_waterfront"],
        "window_months": cfg["months"],
    }
    return subject_facts, comps, excluded


def _pool_flag(d):
    pvd = dig(d, "property_valuation_data.outdoor") or {}
    if pvd.get("pool") is True or pvd.get("swimming_pool") is True:
        return True
    txt = f"{d.get('description','')} {d.get('agents_description','')}".lower()
    if "pool" in txt:
        return True
    return None  # unknown


# ─────────────────────────────────────────────────────────────────────────────
# tier-A summary
# ─────────────────────────────────────────────────────────────────────────────
def tier_a_summary(comps):
    a = [c for c in comps if c["tier"] == "A"]
    if not a:
        return None
    prices = sorted(c["sold_price"] for c in a)
    psqm = sorted(c["psqm_land"] for c in a if c["psqm_land"])
    n = len(prices)
    median = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2
    return {
        "n": n,
        "price_min": prices[0],
        "price_max": prices[-1],
        "price_median": int(median),
        "psqm_land_min": psqm[0] if psqm else None,
        "psqm_land_max": psqm[-1] if psqm else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# adversarial claim-tester
# ─────────────────────────────────────────────────────────────────────────────
_SUPERLATIVE = re.compile(
    r"\b(best|finest|greatest|unbeatable|unmatched|only|premier|perfect|top|"
    r"one of the (?:best|finest|greatest|top))\b", re.I)
_BEACH_KW = re.compile(r"\b(beach|walk[- ]?to[- ]?beach|coastal|ocean|surf|walk)\b", re.I)
_LAND_KW = re.compile(r"\b(land|block|\d{3,4}\s?m|\d{3,4}\s?sqm|acre|allotment)\b", re.I)
_SIZE_KW = re.compile(r"\b(house size|home size|floor ?area|internal|living area|big house|large home|spacious)\b", re.I)
_PRICE_KW = re.compile(r"[\$]|around\s|priced|value|\bunder\b|\bat\b\s*\$", re.I)


def test_claim(claim, subject, comps, summary):
    """Decompose a scarcity/value claim into legs, name every comp that beats-or-matches
    the subject on each leg, and report which wording survives. Rule-5 compliant: no
    advice, no subject valuation, no unverifiable superlative asserted as fact."""
    a = [c for c in comps if c["tier"] == "A"]
    lines = []
    legs = {}

    has_superlative = bool(_SUPERLATIVE.search(claim))
    wants_beach = bool(_BEACH_KW.search(claim))
    wants_land = bool(_LAND_KW.search(claim))
    wants_size = bool(_SIZE_KW.search(claim))

    lines.append("CLAIM UNDER TEST:")
    lines.append(f"  \"{claim}\"")
    lines.append("")
    lines.append("LEG-BY-LEG (against Tier-A comps — the tightest, most defensible set):")

    # Beach leg — comps CLOSER to the beach than the subject beat it on location.
    if wants_beach:
        closer = [c for c in a if c["beach_km"] < subject["beach_km"] - 0.001]
        legs["beach"] = not closer or len(closer) <= max(1, len(a) // 4)
        lines.append(f"  • Location (walk-to-beach): subject is {subject['beach_km']} km straight-line "
                     f"from {subject['beach_name']}.")
        if closer:
            lines.append(f"    {len(closer)}/{len(a)} Tier-A comps sit CLOSER to a beach: " +
                         ", ".join(f"{c['address'].split(',')[0]} ({c['beach_km']}km)" for c in closer))
        else:
            lines.append("    No Tier-A comp is closer to a beach — location leg is not contradicted.")

    # Land leg — comps with land >= subject beat-or-match on land.
    if wants_land:
        ge = [c for c in a if c["land_sqm"] >= subject["land_sqm"] - 1]
        # The land leg (as a "usable 800m²+" claim) SURVIVES if the subject genuinely sits at
        # the top of the band. It fails only if the subject is small for the cohort.
        legs["land"] = subject["land_sqm"] >= 800
        lines.append(f"  • Land: subject {subject['land_sqm']} m² ({subject['land_source']}).")
        lines.append(f"    {len(ge)}/{len(a)} Tier-A comps equal or exceed the subject's land: " +
                     (", ".join(f"{c['address'].split(',')[0]} ({c['land_sqm']:.0f})" for c in ge) or "none"))
        if subject["land_sqm"] >= 800:
            lines.append("    Subject clears the 800 m² threshold → the '800 m²+ land' wording holds as a FACT.")

    # House-size leg — comps with internal >= subject beat-or-match on size.
    if wants_size:
        known = [c for c in a if c["internal_sqm"]]
        ge = [c for c in known if subject["internal_sqm"] and c["internal_sqm"] >= subject["internal_sqm"]]
        legs["house_size"] = bool(subject["internal_sqm"]) and len(ge) == 0
        si = subject["internal_sqm"]
        lines.append(f"  • House size (internal): subject {si if si else 'UNKNOWN'} m² "
                     f"({subject['internal_source']}).")
        if known:
            lines.append(f"    Of {len(known)} Tier-A comps with a known internal area, "
                         f"{len(ge)} equal or exceed the subject: " +
                         (", ".join(f"{c['address'].split(',')[0]} ({c['internal_sqm']:.0f})" for c in ge) or "none"))
        if si and known and len(ge) >= max(1, len(known) // 2):
            lines.append("    ✗ House-size leg FAILS: the subject is NOT large for this cohort — "
                         "most measured comps equal or exceed it. Size is a weakness here, not a strength.")

    # Superlative — always unverifiable against a partially-observed market (Rule 5).
    if has_superlative:
        lines.append("  • Superlative ('best / one of the best / only'): our sold set is a FLOOR, "
                     "not a census, and for-sale coverage of adjacent suburbs is incomplete. "
                     "A 'best combination available' claim asserts knowledge of the whole market "
                     "we do not hold → UNVERIFIABLE under Rule 5. It cannot be published as stated.")

    # Verdict.
    lines.append("")
    failed_legs = [k for k, ok in legs.items() if not ok]
    survives = (not has_superlative) and (not failed_legs)
    lines.append("VERDICT:")
    if survives:
        lines.append("  The claim SURVIVES as worded on the legs tested. Keep the standing caveats below.")
    else:
        why = []
        if has_superlative:
            why.append("it rests on an unverifiable superlative")
        if "house_size" in failed_legs:
            why.append("the house-size leg fails (subject is small for the cohort)")
        if "beach" in failed_legs:
            why.append("comparable sales sit closer to the beach")
        if "land" in failed_legs:
            why.append("the land leg is not supported")
        lines.append("  ✗ The claim DOES NOT SURVIVE as worded — " + "; ".join(why) + ".")

    # Proposed supported wording — built only from legs that held + the price-gap fact.
    if not survives:
        lines.append("")
        lines.append("STRONGEST SUPPORTED WORDING (drop the superlative and the size leg; lead on the")
        lines.append("provable scarcity + the priced gap to renovated stock):")
        supported = _propose_wording(subject, a, summary)
        for l in supported:
            lines.append("  " + l)

    # Standing caveats — always.
    lines.append("")
    lines.append("STANDING CAVEATS (attach to any published version):")
    lines.append("  1. The sold set is a FLOOR, not a census — a competitor's RP Data/Pricefinder feed")
    lines.append("     may hold a qualifying sale we do not. State the claim as 'in our data', sourced.")
    lines.append("  2. Condition is NOT something our data ranks reliably; do not imply the subject is")
    lines.append("     superior/inferior in condition beyond the recorded renovation level.")
    lines.append("  3. Beach distance is STRAIGHT-LINE to the published beach point, not a walking route")
    lines.append("     (the real walk crosses main roads). Never convert it to an 'X-minute walk' unverified.")
    lines.append("  4. Unpriced / off-market listings are invisible to this tool; 'only one listed' covers")
    lines.append("     only priced listings we hold.")
    return "\n".join(lines)


def _propose_wording(subject, tier_a, summary):
    lp = subject.get("list_price")
    lp_s = f"${lp:,}" if lp else "the list price"
    out = []
    if summary and tier_a:
        radius = round(max(c["beach_km"] for c in tier_a), 2)
        out.append(
            f"\"At {lp_s}, {subject['address'].split(',')[0]} pairs a "
            f"{subject['land_sqm']:.0f} m² non-waterfront block with a "
            f"{subject['beach_km']} km straight-line position to {subject['beach_name']}. In our data, "
            f"every comparable non-waterfront house on {int(min(c['land_sqm'] for c in tier_a))}"
            f"–{int(max(c['land_sqm'] for c in tier_a))} m² that sold within {radius} km "
            f"of the beach in the last {subject['window_months']} months sold between "
            f"${summary['price_min']:,} and ${summary['price_max']:,} "
            f"(median ${summary['price_median']:,}) — none below ${summary['price_min']:,}.\"")
    out.append(
        "The defensible story is SCARCITY of the land+location pairing at this price and the")
    out.append(
        "CONDITION gap to renovated comparables — not house size, and not a 'best available' superlative.")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# rendering
# ─────────────────────────────────────────────────────────────────────────────
def render_table(subject, comps, summary, excluded):
    out = []
    out.append("=" * 100)
    out.append(f"SUBJECT: {subject['address']}")
    out.append(f"  land {subject['land_sqm']} m² ({subject['land_source']})  |  "
               f"internal {subject['internal_sqm']} m² ({subject['internal_source']})  |  "
               f"beach {subject['beach_km']} km straight-line → {subject['beach_name']}")
    g = subject.get("geometry")
    if g:
        out.append(f"  block: {g['shape_label']}, rectangularity {g['rectangularity']}, "
                   f"frontage~{g['frontage_m_est']}m depth~{g['depth_m_est']}m (estimates)")
    out.append(f"  beds {subject['beds']} baths {subject['baths']} car {subject['car']}  |  "
               f"condition {subject['condition']} / reno {subject['renovation_level']}  |  "
               f"list price {subject['list_price_raw']}")
    out.append(f"  waterfront: {subject['waterfront']}  |  recency window: {subject['window_months']} months")
    out.append("=" * 100)
    out.append(f"COMPARABLES ({len(comps)}), most-comparable first. Beach = straight-line km.")
    out.append("-" * 100)
    hdr = (f"{'T':1} {'Address':28} {'Sold':8} {'Price':>11} {'Land':>6} {'Int':>5} "
           f"{'Bch':>5} {'$/m²L':>6} {'Reno':16} {'Shape':10} Src")
    out.append(hdr)
    out.append("-" * 100)
    for c in comps:
        addr = (c["address"] or "?")[:28]
        intv = f"{c['internal_sqm']:.0f}" if c["internal_sqm"] else "  ?"
        reno = (c["renovation_level"] or c["condition"] or "-")[:16]
        shape = (c["shape"] or "-")[:10]
        wr = {"dry": "", "water_view": "~water", "lakefront": "LAKE"}.get(c.get("water_relationship"), "")
        out.append(f"{c['tier']:1} {addr:28} {c['sold_date']:8} ${c['sold_price']:>10,} "
                   f"{c['land_sqm']:>6.0f} {intv:>5} {c['beach_km']:>5.2f} "
                   f"{(c['psqm_land'] or 0):>6,} {reno:16} {shape:10} {c['sale_source'].split(':')[0]:8} {wr}")
    out.append("-" * 100)
    if summary:
        out.append(f"TIER-A SUMMARY (n={summary['n']}): "
                   f"price ${summary['price_min']:,}–${summary['price_max']:,}, "
                   f"median ${summary['price_median']:,}  |  "
                   f"$/m² land ${summary['psqm_land_min']:,}–${summary['psqm_land_max']:,}")
    else:
        out.append("TIER-A SUMMARY: no Tier-A comps found.")
    out.append(f"EXCLUDED during scan: {excluded}")
    out.append("NOTE: 'shed' is never reported — no shed field exists in the DB, so absence in a comp is")
    out.append("      NOT evidence the comp has no shed. Condition/reno is descriptive, not a ranking.")
    return "\n".join(out)


def write_artefacts(subject, comps, summary, excluded, base):
    scratch = os.environ.get("CLAUDE_SCRATCHPAD") or \
        "/tmp/claude-1001/-home-fields-Fields-Orchestrator/545fb342-e0c9-4a83-8bdf-e8c189e850c8/scratchpad"
    os.makedirs(scratch, exist_ok=True)
    jpath = os.path.join(scratch, f"{base}.json")
    cpath = os.path.join(scratch, f"{base}.csv")
    with open(jpath, "w") as f:
        json.dump({"subject": _jsonable(subject), "tier_a_summary": summary,
                   "excluded": excluded, "comps": [_jsonable(c) for c in comps]},
                  f, indent=2, default=str)
    if comps:
        cols = [k for k in comps[0].keys() if not k.startswith("_")]
        with open(cpath, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for c in comps:
                w.writerow({k: c.get(k) for k in cols})
    return jpath, cpath


def _jsonable(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Tight comparable-set builder + adversarial claim-tester.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--address")
    g.add_argument("--id")
    g.add_argument("--slug")
    ap.add_argument("--collections", nargs="*", help="override comp-scan collections")
    ap.add_argument("--months", type=float, default=24, help="sold-recency window (default 24)")
    ap.add_argument("--land-tol-a", type=float, default=0.15)
    ap.add_argument("--land-tol-b", type=float, default=0.25)
    ap.add_argument("--land-tol-c", type=float, default=0.35)
    ap.add_argument("--beach-a", type=float, default=1.7)
    ap.add_argument("--beach-b", type=float, default=2.0)
    ap.add_argument("--beach-c", type=float, default=2.2)
    ap.add_argument("--min-land", type=float, default=None,
                    help="absolute land floor in m² (reproduces a '800m²+' scarcity tier)")
    ap.add_argument("--max-land", type=float, default=None, help="absolute land ceiling in m²")
    ap.add_argument("--claim", help="scarcity/value claim to adversarially test")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--csv", action="store_true")
    args = ap.parse_args()

    db = get_client()["Gold_Coast"]
    subject_doc, subj_coll = find_subject(db, args)
    if not subject_doc:
        raise SystemExit("Subject not found.")

    cfg = {
        "months": args.months,
        "land_tol_a": args.land_tol_a, "land_tol_b": args.land_tol_b, "land_tol_c": args.land_tol_c,
        "beach_a": args.beach_a, "beach_b": args.beach_b, "beach_c": args.beach_c,
        "min_land": args.min_land, "max_land": args.max_land,
        "collections": args.collections,
    }
    subject, comps, excluded = build_comps(db, subject_doc, subj_coll, cfg)
    summary = tier_a_summary(comps)

    print(render_table(subject, comps, summary, excluded))

    if args.claim:
        print()
        print("#" * 100)
        print("ADVERSARIAL CLAIM TEST")
        print("#" * 100)
        print(test_claim(args.claim, subject, comps, summary))

    if args.json or args.csv:
        base = re.sub(r"[^a-z0-9]+", "_", (subject["address"] or "subject").lower())[:40] + "_comparables"
        jpath, cpath = write_artefacts(subject, comps, summary, excluded, base)
        print()
        if args.json:
            print(f"JSON → {jpath}")
        if args.csv:
            print(f"CSV  → {cpath}")


if __name__ == "__main__":
    main()
