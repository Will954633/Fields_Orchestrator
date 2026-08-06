#!/usr/bin/env python3
"""
fact_bundle.py — harvest every deterministic FACT the 10-card Discovery
Experience needs for one property, from the resolvers that already exist.

This is the EXPENSIVE half of the pipeline (DB scans + optional Mapbox walk
routing). It is run once per property and cached to bundles/<slug>.json, so the
copy/assembly layer (assemble.py) can be re-run infinitely as we tune the
static framing text without paying the data cost again.

NO LLM. Every field here is deterministic:
  - scarcity / competition / proximity  -> offmarket_intel_poller.compute_intel
  - valuation range + comps             -> Gold_Coast.<suburb>.valuation_data
  - "obvious comp" deltas (card 06)     -> valuation_data.recent_sales (arithmetic)
  - value drivers / anti-frame / buyer  -> positioning_object.resolve_positioning_object
                                            (deterministic template engine, not LLM)

Usage:
  python3 fact_bundle.py --slug 38-beaconsfield-drive-burleigh-waters --suburb burleigh_waters
  python3 fact_bundle.py --slug X                 # suburb auto-detected
"""
import os
import sys
import json
import argparse
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent.parent  # Fields_Orchestrator
sys.path.insert(0, str(ORCH))
sys.path.insert(0, str(ORCH / "scripts"))

from src.mongo_client_factory import get_mongo_client  # noqa: E402
from offmarket_intel_poller import (  # noqa: E402
    compute_intel, _find_subject, estimate_price_range,
)

BUNDLE_DIR = HERE / "bundles"
BUNDLE_DIR.mkdir(exist_ok=True)

# The 9 southern-GC suburbs the scarcity/competition engine spans (mirrors
# scarcity_features.DEFAULT_CATCHMENT) — used for the "recent sales reviewed"
# credibility number so it reflects the real pool the analysis drew on.
CATCHMENT = [
    "robina", "burleigh_waters", "varsity_lakes",
    "merrimac", "mudgeeraba", "reedy_creek", "worongary",
    "burleigh_heads", "carrara",
]
_catchment_sold_cache = {}


def _catchment_sold(gc):
    if "n" not in _catchment_sold_cache:
        n = 0
        for s in CATCHMENT:
            try:
                n += gc[s].count_documents({"listing_status": "sold"})
            except Exception:
                pass
        _catchment_sold_cache["n"] = n
    return _catchment_sold_cache["n"]

# Feature-key -> short buyer-facing filter label (card 04 checklist).
FILTER_LABELS = {
    "bedrooms_anchor": None,   # rendered dynamically ("4+ bedrooms")
    "land_anchor": "large block",
    "floor_anchor": "generous floor area",
    "bathrooms_3plus": "multiple bathrooms",
    "pool": "pool",
    "water_views": "water views",
    "single_level": "single-level living",
    "waterfront": "waterfront",
}


def _int(v):
    try:
        return int(round(float(v)))
    except Exception:
        return None


def _short_address(address: str) -> str:
    return (address or "").split(",")[0].strip()


def _spf(sp: dict, key, default=None):
    """Read a subject feature from valuation_data.subject_property.

    ⚠ The features live at `subject_property.features.basic`, NOT on
    `subject_property` itself — that level carries only address/id/price/
    images/utility_index/evidence. Reading `sp.get("pool_present")` returns
    None for EVERY property, silently.

    Found 2026-08-06 on 28 Wedgebill Parade: the deck claimed "a pool" (scarcity,
    reading the correct path) while value-drivers said "no pool" (this file,
    reading the wrong one). Eight fields were affected — pool, renovation_level,
    build year, cladding, stories, kitchen and both quality scores — so the deck
    was under-claiming real, vision-verified features across the board.
    """
    basic = (sp.get("features") or {}).get("basic") or {}
    v = basic.get(key)
    if v is None:
        v = sp.get(key)          # tolerate a flattened shape
    return default if v is None else v


def _subject_features(subject: dict) -> dict:
    """Best-effort physical attributes from the Gold_Coast doc + valuation_data."""
    vd = subject.get("valuation_data") or {}
    sp = (vd.get("subject_property") or {}).get("features", {}).get("basic", {}) or {}
    land = subject.get("land_size_sqm") or subject.get("lot_size_sqm") or sp.get("land_size_sqm")
    # Floor: prefer the VALUATION floor_area_sqm (floor-under-roof) so the subject
    # is measured on the SAME basis as the comps (whose floor also comes from
    # valuation features.basic) — the top-level field is often internal-living,
    # which made Card 06's floor delta apples-to-oranges.
    floor = (sp.get("floor_area_sqm") or subject.get("floor_area_sqm")
             or subject.get("internal_living_area_sqm"))
    stories = _int(_spf(sp, "number_of_stories") or subject.get("number_of_stories"))
    return {
        "bedrooms": _int(subject.get("bedrooms") or sp.get("bedrooms")),
        "bathrooms": _int(subject.get("bathrooms") or sp.get("bathrooms")),
        "car_spaces": _int(subject.get("carspaces") or subject.get("car_spaces") or sp.get("car_spaces")),
        "land_sqm": _int(land),
        "floor_sqm": _int(floor),
        "property_type": subject.get("property_type"),
        "year_built": _int(subject.get("year_built")),
        "build_year": _int(_spf(sp, "approximate_build_year") or subject.get("year_built")),
        "stories": stories,
        "single_level": stories == 1 if stories else None,
        "pool": bool(_spf(sp, "pool_present") or subject.get("pool")),
        "water_views": bool(_spf(sp, "water_views")),
        # GPT-4 vision reads (present only where the property was vision-analysed;
        # None otherwise → we make NO finish/renovation claim for that home).
        "renovation_level": _spf(sp, "renovation_level"),
        "renovation_quality_score": _spf(sp, "renovation_quality_score"),
    }


# Core suburbs we can honestly call family suburbs (buyer filter).
_FAMILY_SUBURBS = {"robina", "varsity_lakes", "burleigh_waters"}


def _buyer_filters(feat: dict, single_level: bool, suburb_key: str, cap: int = 4) -> list:
    """Card 04 'Buyer filters your home survives' — built from the home's ACTUAL
    features (not the rarity anchors), so the list is reliably 4-5 strong items.
    These are buyer SEARCH filters (generic language); the specific numbers live
    on Card 03."""
    f = []
    b = feat.get("bedrooms")
    if b and b >= 3:
        f.append(f"{b}+ bedrooms")
    if (feat.get("land_sqm") or 0) >= 600:
        f.append("large block")
    if (feat.get("floor_sqm") or 0) >= 200:
        f.append("generous floor area")
    ba = feat.get("bathrooms")
    if ba and ba >= 2:
        f.append("multiple bathrooms")
    if feat.get("pool"):
        f.append("pool")
    if single_level:
        f.append("single-level living")
    if feat.get("water_views"):
        f.append("water views")
    f = f[:cap]
    if suburb_key in _FAMILY_SUBURBS:
        f.append("family suburb")
    return f


def _negotiation_levers(feat: dict) -> list:
    """Card 07 'where a buyer may focus' — genuine, plainly-worded relative gaps
    (value-framed, never jargon). Empty when the home has no honest lever, in
    which case the card omits the second half rather than inventing one."""
    out = []
    rl = feat.get("renovation_level")
    if isinstance(rl, (int, float)) and rl <= 2:
        out.append("scope to modernise the interior")
    if feat.get("bathrooms") == 1:
        out.append("a single bathroom")
    if feat.get("car_spaces") is not None and feat["car_spaces"] < 2:
        out.append("single-car parking")
    if (feat.get("land_sqm") or 0) and feat["land_sqm"] < 500:
        out.append("a compact block")
    if not feat.get("pool"):
        out.append("no pool")
    return out[:3]


# Subject green-boundary kind -> the phrase for what the comp LACKS (Will's
# research: backing onto bushland / golf / water is a major valuation factor).
_COMP_MISSING_GREEN = {
    "bushland": "no bushland behind it",
    "golf course": "no golf-course frontage",
    "water": "no water at its boundary",
    "river": "no water at its boundary",
    "canal": "no water at its boundary",
    "creek": "no water at its boundary",
}


def _comp_coords(gc, comp):
    """Fetch the comp's coordinates from its Gold_Coast doc (recent_sales carry
    an `id` but no inline lat/lon)."""
    from bson import ObjectId
    cid = comp.get("id")
    if not cid:
        return None, None
    try:
        oid = ObjectId(str(cid))
    except Exception:
        return None, None
    for s in CATCHMENT:
        try:
            d = gc[s].find_one({"_id": oid},
                               {"LATITUDE": 1, "LONGITUDE": 1, "latitude": 1,
                                "longitude": 1, "geocoded_coordinates": 1})
        except Exception:
            d = None
        if d:
            gcc = d.get("geocoded_coordinates") or {}
            return (d.get("LATITUDE", d.get("latitude", gcc.get("latitude"))),
                    d.get("LONGITUDE", d.get("longitude", gcc.get("longitude"))))
    return None, None


def _obvious_comp(subject_feat: dict, recent_sales: list, gc=None,
                  subject_green: dict | None = None, subject_id=None,
                  subject_addr: str | None = None) -> dict | None:
    """Card 06 — the comp a layperson would seize on (closest by distance), with
    the STRONGEST material differences vs the subject (land, floor on a matched
    basis, build year, and a green-boundary difference), computed arithmetically."""
    if not recent_sales:
        return None
    # Exclude the subject's OWN prior sale (it sits in recent_sales at distance 0).
    sid = str(subject_id) if subject_id else None
    saddr = _short_address(subject_addr or "").lower()
    priced = [c for c in recent_sales if c.get("price")
              and str(c.get("id")) != sid
              and _short_address(c.get("address") or "").lower() != saddr]
    if not priced:
        return None
    # `.get(k, default)` returns the DEFAULT only when the key is absent — a key
    # present with an explicit None still yields None, and min() then compares
    # None against floats and raises. That killed the WHOLE build for the home
    # (no deck at all -> back to the classic page), not just this card: 4 homes in
    # the first 9,200 of the 2026-08-05 rebuild. Comps carry a null distance
    # whenever the comp's own coordinates are missing, so treat null as "furthest"
    # rather than trusting the default to fire.
    def _dist(c):
        d = c.get("distance_km")
        return d if isinstance(d, (int, float)) else 9e9

    comp = min(priced, key=_dist)
    cf = (comp.get("features") or {}).get("basic", {}) or {}
    deltas = []

    # Land
    s, c = subject_feat.get("land_sqm"), _int(cf.get("land_size_sqm"))
    if s and c and abs(s - c) >= 50:
        d = c - s  # comp minus subject
        deltas.append(f"{abs(d)}m² {'more' if d > 0 else 'less'} land")
    # Floor (subject now on the same valuation basis as the comp — see _subject_features)
    s, c = subject_feat.get("floor_sqm"), _int(cf.get("floor_area_sqm"))
    if s and c and abs(s - c) >= 20:
        d = c - s
        deltas.append(f"{abs(d)}m² {'more' if d > 0 else 'less'} floor area")
    # Build year
    s, c = subject_feat.get("build_year"), _int(cf.get("approximate_build_year"))
    if s and c and abs(s - c) >= 8:
        d = c - s
        deltas.append(f"built {abs(d)} years {'later' if d > 0 else 'earlier'}")
    # Bedrooms / bathrooms (only when genuinely different — a strong differentiator)
    s, c = subject_feat.get("bedrooms"), _int(cf.get("bedrooms"))
    if s and c and s != c:
        deltas.append(f"{c} bedrooms vs your {s}")
    s, c = subject_feat.get("bathrooms"), _int(cf.get("bathrooms"))
    if s and c and s != c:
        deltas.append(f"{c} bathrooms vs your {s}")
    # Pool
    if subject_feat.get("pool") and not cf.get("pool_present"):
        deltas.append("no pool")
    # Green boundary — fires ONLY when the subject has one and the comp genuinely
    # doesn't (both often back onto a reserve in these suburbs → no false delta).
    sg = (subject_green or {}).get("premium") or {}
    if gc is not None and sg.get("relation") in ("backs onto", "adjoins"):
        clat, clon = _comp_coords(gc, comp)
        if clat and clon:
            try:
                from green_space import classify as gs_classify
                cg = (gs_classify(clat, clon) or {}).get("premium") or {}
                if cg.get("relation") not in ("backs onto", "adjoins"):
                    deltas.append(_COMP_MISSING_GREEN.get(sg.get("kind"), "no parkland behind it"))
            except Exception:
                pass

    return {
        "address": _short_address(comp.get("address")),
        "price": _int(comp.get("price")),
        "original_sale_price": _int(comp.get("original_sale_price")),
        "distance_m": _int((comp.get("distance_km") or 0) * 1000),
        "sale_quarter": ((comp.get("time_adjustment") or {}).get("sale_quarter")),
        "deltas": deltas,
    }


def _positioning(subject, gc, suburb, matched, scarcity_raw):
    """Cards 07/08/10 via the deterministic positioning template engine.
    Returns None on any failure (cards degrade)."""
    try:
        from property_reports.positioning_object import resolve_positioning_object
        from property_reports.nearby_pois import resolve_nearby_pois, to_walking_poi_list
        from property_reports.scarcity_features import resolve_scarcity_features
        scarcity = scarcity_raw or resolve_scarcity_features(subject, gc)
        if not scarcity or not scarcity.get("notable_features"):
            return None
        gc_coords = subject.get("geocoded_coordinates") or {}
        lat = subject.get("LATITUDE", subject.get("latitude", gc_coords.get("latitude")))
        lon = subject.get("LONGITUDE", subject.get("longitude", gc_coords.get("longitude")))
        try:
            proximity = resolve_nearby_pois(lat, lon, gc)
            walk_pois = to_walking_poi_list(proximity, lat, lon)
        except Exception:
            walk_pois = []
        suburb_display = (matched or suburb or "").replace("_", " ").title()
        try:
            price_range = estimate_price_range(gc, matched, lat, lon, subject.get("bedrooms"))
            price_anchor = price_range["mid"] if price_range else None
        except Exception:
            price_anchor = None
        po = resolve_positioning_object(
            subject, gc, suburb_display, scarcity=scarcity, pois=walk_pois,
            price_anchor=price_anchor,
        )
        return po
    except Exception:
        traceback.print_exc()
        return None


def build(slug: str, suburb: str | None = None, with_positioning: bool = True) -> dict:
    client = get_mongo_client()
    gc = client["Gold_Coast"]
    subject, matched = _find_subject(gc, suburb, slug)
    if not subject:
        raise SystemExit(f"subject not found for slug={slug} suburb={suburb}")

    address = subject.get("address") or subject.get("complete_address") or slug
    suburb_display = (matched or suburb or "").replace("_", " ").title()
    feat = _subject_features(subject)
    vd = subject.get("valuation_data") or {}
    conf_range = ((vd.get("confidence") or {}).get("range")) or {}
    summary = vd.get("summary") or {}
    recent_sales = vd.get("recent_sales") or []

    intel, err = compute_intel(gc, suburb, slug)
    intel = intel or {}
    scarcity = intel.get("scarcity") or {}
    competition = intel.get("competition") or {}
    proximity = intel.get("proximity") or {}

    # --- Green-space adjacency (OSM polygons, high-confidence edge distance) ---
    green_space = None
    try:
        from green_space import classify as gs_classify
        gcc = subject.get("geocoded_coordinates") or {}
        glat = subject.get("LATITUDE", subject.get("latitude", gcc.get("latitude")))
        glon = subject.get("LONGITUDE", subject.get("longitude", gcc.get("longitude")))
        green_space = gs_classify(glat, glon)
    except Exception:
        traceback.print_exc()

    # --- Card 07 buyer-leverage points (real feature gaps, plainly worded) ---
    negotiation_levers = _negotiation_levers(feat)

    # --- Card 04 filter checklist (from the home's ACTUAL features) ---
    single_level = bool(feat.get("single_level")) or any(
        (nf or {}).get("key") == "single_level" for nf in (scarcity.get("notable") or []))
    checklist = _buyer_filters(feat, single_level, matched or "")

    # --- Card 06 obvious comp ---
    obvious_comp = _obvious_comp(feat, recent_sales, gc, green_space,
                                 subject_id=subject.get("_id"), subject_addr=address)

    # --- POI-aware rarity (prototype): proximity ∩ physical combination ---
    poi_rarity = None
    try:
        from poi_rarity import compute_poi_rarity
        poi_rarity = compute_poi_rarity(subject, gc)
    except Exception:
        traceback.print_exc()

    # --- Wait-time (prototype): how often the combination comes to market ---
    wait_time = None
    try:
        from wait_time import compute_wait_time
        cluster_feats = ((poi_rarity or {}).get("cluster") or {}).get("features")
        wait_time = compute_wait_time(subject, gc, feat, cluster_features=cluster_feats)
    except Exception:
        traceback.print_exc()

    # --- Cards 07/08/10 positioning (deterministic engine) ---
    po = _positioning(subject, gc, suburb, matched, None) if with_positioning else None
    value_drivers, buyer, positioning_render = None, None, None
    if po:
        pos = po.get("positioning") or po
        drivers = (pos.get("drivers") or {})
        value_drivers = {
            "carries_price": drivers.get("price") or [],
            "attracts_buyer": drivers.get("buyer") or [],
        }
        render = (pos.get("render") or {})
        af = (render.get("antiFrame") or {})
        thesis = (render.get("thesis") or {})
        positioning_render = {
            "frame_line": thesis.get("frameLine"),
            "lead_line": thesis.get("leadLine"),
            "avoid": af.get("items") or [],
            "scarcity_verdict": pos.get("scarcity_verdict"),
        }
        # buyer archetype (card 08): the positioning engine picks one deterministically
        lead_buyer = (render.get("leadBuyer") or {})
        if pos.get("buyer") or lead_buyer:
            buyer = {
                "label": pos.get("buyer"),
                "primary_frame": pos.get("primary_frame"),  # archetype key for the human portrait
                "headline": lead_buyer.get("headline"),
                "body": lead_buyer.get("body"),
            }

    # --- Card 01 credibility numbers (all real, from the DB) ---
    # characteristics: distinct property characteristics our analysis evaluates
    #   for this home (subject attributes + POI categories + scarcity feature
    #   rules + positioning archetype flags + valuation adjustment dimensions).
    #   A genuine per-home dimension count — see build-notes / README for the
    #   definition if we want to reframe it as data-points-across-comparison.
    adj_dims = len((vd.get("adjustment_rates") or {}) or {})
    characteristics = (
        sum(1 for v in feat.values() if v not in (None, "", False))
        + len(proximity)
        + len(scarcity.get("notable") or [])
        + (14 if po else 0)          # positioning archetype flags evaluated
        + adj_dims                    # valuation adjustment dimensions
    )
    try:
        suburb_stock = gc[matched].count_documents({}) if matched else None
    except Exception:
        suburb_stock = None
    credibility = {
        "characteristics": characteristics,
        "sales_reviewed": _catchment_sold(gc) or None,       # catchment-wide sold pool
        "homes_compared": suburb_stock,                       # cadastral homes in suburb
        "active_compared": scarcity.get("active_total"),      # active listings scored
    }

    # --- Card 09 valuation (tiered, mirrors the mini-site's working_valuation_range) ---
    # Tier 1 engine range -> Tier 2 exterior-evidence dispersion -> Tier 3 thin
    # median band, so Card 09 degrades honestly instead of vanishing when the
    # full engine excluded the property. We deliberately SKIP the mini-site's
    # Tier 1b (a live on-demand engine run) — the harness is read-only, no writes
    # / no GPT cost.
    valuation = None
    try:
        from property_reports.slot_resolver import SlotResolver
        _rd = {"suburb_key": matched, "suburb": suburb_display,
               "address": address, "property_id": subject.get("_id")}
        _r = SlotResolver(_rd, gc)
        _r._subject = subject
        mr = (_r._engine_valuation_range()
              or _r.valuation_exterior_range()
              or _r._thin_valuation_range())
        if mr and mr.get("low") and mr.get("high"):
            valuation = {
                "low": _int(mr["low"]),
                "high": _int(mr["high"]),
                "point": _int(mr.get("point")),
                "method": mr.get("method"),           # engine | exterior_evidence | thin
                "confidence": mr.get("confidence"),
                "confidence_reason": mr.get("confidence_reason"),
                "n_comps": mr.get("comp_count") or summary.get("n_comps"),
            }
    except Exception:
        traceback.print_exc()

    # --- gaps: honest record of what's missing (so cards omit, never fake) ---
    gaps = []
    if not feat.get("bedrooms"):
        gaps.append("bedrooms unknown")
    if not feat.get("bathrooms"):
        gaps.append("bathrooms unknown")
    if valuation is None:
        gaps.append("no valuation range")
    if not obvious_comp:
        gaps.append("no comparable sale")
    if competition.get("n_compete") is None:
        gaps.append("competition count unavailable")
    if po is None:
        gaps.append("positioning/value-drivers unavailable")

    bundle = {
        "slug": slug,
        "suburb_key": matched,
        "suburb_display": suburb_display,
        "address": address,
        "address_short": _short_address(address),
        "subject": feat,
        "credibility": credibility,
        "scarcity": scarcity,
        "competition": competition,
        "filter_checklist": checklist,
        "obvious_comp": obvious_comp,
        "green_space": green_space,
        "poi_rarity": poi_rarity,
        "wait_time": wait_time,
        "negotiation_levers": negotiation_levers,
        "value_drivers": value_drivers,
        "buyer": buyer,
        "valuation": valuation,
        "positioning": positioning_render,
        "proximity": proximity,
        "gaps": gaps,
    }
    return bundle


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--no-positioning", action="store_true",
                    help="skip the positioning engine (faster, drops cards 07/08/10 drivers)")
    ap.add_argument("--print", action="store_true", help="print JSON to stdout")
    args = ap.parse_args()
    bundle = build(args.slug, args.suburb, with_positioning=not args.no_positioning)
    out = BUNDLE_DIR / f"{args.slug}.json"
    out.write_text(json.dumps(bundle, indent=2, default=str))
    if args.print:
        print(json.dumps(bundle, indent=2, default=str))
    print(f"→ {out}  (gaps: {bundle['gaps'] or 'none'})", file=sys.stderr)


if __name__ == "__main__":
    main()
