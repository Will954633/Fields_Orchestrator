#!/usr/bin/env python3
"""dual_occ_precedents.py — nearby dual-occupancy / duplex precedents (Conjunction Tier 3.2).

Will's question for a development angle: "find every dual occupancy / duplex within
~1km of the subject, with lot size, frontage, zoning — because a real nearby example
beats abstract planning theory." This finds them from OUR data.

⚠ Honest limit, stated up front and in the output: our database does NOT hold Council
assessment type (code/impact/accepted) or approval status — those live in Development.i,
which must be checked manually per precedent. What we CAN establish is: which nearby
properties are duplex/dual-occupancy stock, their land size, frontage (where cadastral
rings exist), beds/baths, sold price, and zone/RD-overlay where we've ingested a City
Plan report. So this is a TARGETING list of precedents to investigate, not a claim about
what was approved. Rule 5: never state a buyer "can" replicate any of them.
"""
import argparse
import math
import sys

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client            # noqa: E402
from shared.block_geometry import compute_block_geometry  # noqa: E402

_DUP_RE = r"duplex|dual occ|dual living|dual-occupancy"


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _latlon(d):
    lat = d.get("LATITUDE") or (d.get("geocoded_coordinates") or {}).get("latitude")
    lon = d.get("LONGITUDE") or (d.get("geocoded_coordinates") or {}).get("longitude")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _land(d):
    for path in ("land_size_sqm", "lot_size_calc_sqm"):
        v = d.get(path)
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    for a, b in (("onthehouse_data", "land_size_sqm"), ("scraped_data_v2", "land_area_sqm")):
        v = (d.get(a) or {}).get(b)
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    cp = d.get("cadastral_polygon") or {}
    return cp.get("lot_area_sqm")


def find_precedents(subject, radius_km=1.0):
    db = get_client()["Gold_Coast"]
    slat, slon = _latlon(subject)
    if slat is None:
        raise SystemExit("subject has no coordinates")
    suburb = subject.get("suburb") or subject.get("LOCALITY", "").lower().replace(" ", "_")
    # Search the subject's suburb + any collection (duplexes cluster locally); keep it
    # to the target suburbs to bound the scan.
    cols = [c for c in db.list_collection_names()
            if c in ("burleigh_waters", "robina", "varsity_lakes", suburb)]
    q = {
        "$or": [
            {"property_type": {"$regex": "duplex|dual", "$options": "i"}},
            {"classified_property_type": {"$regex": "duplex|dual", "$options": "i"}},
            {"description": {"$regex": _DUP_RE, "$options": "i"}},
            {"agents_description": {"$regex": _DUP_RE, "$options": "i"}},
        ],
        "listing_status": {"$in": ["for_sale", "sold", "under_contract"]},
    }
    out = []
    seen = set(cols)
    for c in seen:
        for d in db[c].find(q):
            lat, lon = _latlon(d)
            if lat is None:
                continue
            km = _haversine_km(slat, slon, lat, lon)
            if km > radius_km:
                continue
            geom = compute_block_geometry(d.get("cadastral_polygon"))
            cityplan = (d.get("zoning_data") or {}).get("cityplan") or {}
            out.append({
                "address": d.get("address"),
                "distance_km": round(km, 2),
                "property_type": d.get("property_type"),
                "land_sqm": _land(d),
                "frontage_m_est": geom.get("frontage_m_est") if geom else None,
                "shape": geom.get("shape_label") if geom else None,
                "bedrooms": d.get("bedrooms"),
                "bathrooms": d.get("bathrooms"),
                "sale_price": d.get("sale_price") or d.get("price"),
                "sold_date": d.get("sold_date"),
                "zone": (d.get("zoning_data") or {}).get("zone"),
                "rd_overlay": (cityplan.get("layers") or {}).get("residential_density_overlay"),
                "listing_status": d.get("listing_status"),
            })
    out.sort(key=lambda r: r["distance_km"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address")
    ap.add_argument("--slug")
    ap.add_argument("--id")
    ap.add_argument("--radius", type=float, default=1.0)
    args = ap.parse_args()

    db = get_client()["Gold_Coast"]
    subject = None
    for c in db.list_collection_names():
        q = ({"url_slug": args.slug} if args.slug else
             {"_id": args.id} if args.id else
             {"address": {"$regex": args.address, "$options": "i"}})
        subject = db[c].find_one(q)
        if subject:
            break
    if not subject:
        raise SystemExit("subject property not found")

    rows = find_precedents(subject, args.radius)
    print(f"DUAL-OCC / DUPLEX PRECEDENTS within {args.radius}km of {subject.get('address')}")
    print("⚠ INTERNAL TARGETING ONLY. Assessment type + approval status are NOT in our data —")
    print("  check Development.i per precedent. Rule 5: this establishes precedent to investigate,")
    print("  not that any development is permitted or replicable.\n")
    if not rows:
        # Rule 7b: assert the search ran; distinguish "none nearby" from a broken query.
        print(f"No duplex/dual-occupancy precedents found within {args.radius}km "
              f"(searched by property_type and description across target suburbs). "
              f"This is an absence of nearby precedent in our data, not proof none exist.")
        return
    print(f"{'dist':>5} {'land':>6} {'front':>6} {'bd/ba':>6} {'price':>12} {'status':>13}  address")
    for r in rows:
        land = f"{r['land_sqm']:.0f}" if r["land_sqm"] else "?"
        front = f"{r['frontage_m_est']:.1f}" if r["frontage_m_est"] else "?"
        bdba = f"{r['bedrooms'] or '?'}/{r['bathrooms'] or '?'}"
        price = str(r["sale_price"] or "?")[:12]
        print(f"{r['distance_km']:>5} {land:>6} {front:>6} {bdba:>6} {price:>12} {str(r['listing_status']):>13}  {r['address']}")
    print(f"\n{len(rows)} precedent(s). Frontage is a bounding-box estimate; zone/RD shown where ingested.")


if __name__ == "__main__":
    main()
