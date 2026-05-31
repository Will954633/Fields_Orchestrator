"""
Competitor matcher — the live "substitute homes" set for the mini-site
Market tab competitor map.

A *substitute* is a home a buyer is actually choosing between, not a home
that merely shares the subject's signature features (that feature-twin count
is a separate claim, owned by scarcity_features.py). Substitutability is
driven by budget, bedroom band, and property type — the portal-search
reality. So the matcher:

  1. Hard-filters candidates to genuine substitutes: same property-type GROUP
     (House+Duplex never mixes in a Unit), within the catchment, for_sale,
     within a price band, within a bedroom band.
  2. Ranks survivors by a weighted similarity score (price-led).
  3. Uses an ADAPTIVE APERTURE — expanding tolerance rings — so a common home
     finds a tight set and a unique home still surfaces at least the floor,
     by progressively widening the suburb net, price band, and bedroom band.
  4. Geocodes the chosen handful on-demand (most already carry coordinates).

Output is the `CompetitorMapData` shape the frontend CompetitorMap.tsx
already renders:

    {
      "subject": {"lat", "lng", "address"},
      "competitors": [ {id, address, suburb, lat, lng, priceText, priceLow,
                        bedrooms, bathrooms, carSpaces, daysOnMarket,
                        features[], combinatorialMatch, listingUrl, imageSrc,
                        differenceVsSubject}, ... ],
      "aperture_ring": 1,          # which ring yielded the set (narrative asset)
      "aperture_label": "...",     # plain-language description of the widening
      "catchment": ["robina", ...],
      "active_in_band": 23,        # substitutes found before trim (context)
    }

The aperture ring is load-bearing narrative: a home that only matched at the
loosest ring has literally proven its scarcity ("we widened the search to ±2
bedrooms and 30% on price before comparable homes appeared").
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from pymongo.database import Database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------- #
# Configuration
# ---------------------------------------------------------------------- #

TARGET_MIN = 4   # aim for at least this many before we stop widening
TARGET_MAX = 6   # never plot more than this many substitutes
FLOOR_MIN = 1    # if even the loosest ring is thin, accept down to this many

# Catchment — the subject's own suburb is always prepended at runtime.
# Ordered by how directly each competes with the southern-GC premium market.
DEFAULT_CATCHMENT = [
    "robina", "varsity_lakes", "clear_island_waters", "merrimac",
    "mudgeeraba", "reedy_creek", "worongary", "burleigh_waters", "carrara",
]

# Property-type groups — a buyer shopping for a house does not substitute a
# unit. Duplex/semi sits close enough to a house to share its buyer.
PROPERTY_TYPE_GROUPS = {
    "house": {"house", "duplex/semi-detached", "duplex", "semi-detached"},
    "townhouse": {"townhouse", "villa"},
    "unit": {"unit/apartment", "unit", "apartment", "flat"},
}

# Expanding tolerance rings. Index 0 = tightest. The matcher walks down the
# list until a ring yields >= TARGET_MIN survivors (or the list is exhausted).
#   geo:  "own"      = subject's suburb only
#         "adjacent" = own + first 4 catchment suburbs
#         "full"     = whole catchment
#   price: fractional band around the anchor (±)
#   beds:  absolute bedroom tolerance (±)
APERTURE_RINGS = [
    {"geo": "own",      "price": 0.10, "beds": 0,
     "label": "homes in your own suburb within 10% of your price guide"},
    {"geo": "adjacent", "price": 0.15, "beds": 1,
     "label": "homes in your suburb and its neighbours within 15% on price and one bedroom either way"},
    {"geo": "adjacent", "price": 0.20, "beds": 1,
     "label": "the wider neighbourhood within 20% on price"},
    {"geo": "full",     "price": 0.30, "beds": 2,
     "label": "the whole southern-Gold-Coast premium market within 30% on price and two bedrooms either way"},
]

# Similarity score weights. Lower score = closer substitute. Weights are
# renormalised at runtime over whichever factors both homes actually carry,
# so a missing floor area neither helps nor unfairly hurts a candidate.
SCORE_WEIGHTS = {
    "price": 0.35,
    "bedrooms": 0.20,
    "floor": 0.10,
    "land": 0.10,
    "bathrooms": 0.10,
    "features": 0.10,
    "car": 0.05,
}

# A candidate is shown in the prominent "closest match" tier (yellow marker +
# match card) when its normalised score is at or below this. The single best
# match is always promoted regardless, so the map never shows zero close tier.
CLOSE_MATCH_THRESHOLD = 0.22

# Geocoding (only ever runs for the final <=6 picks that lack coordinates).
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1
USER_AGENT = "FieldsEstate/1.0 (will@fieldsestate.com.au)"

# Signature features that genuinely differentiate substitutes (used for the
# Jaccard overlap term and for the honest "difference vs your home" line).
# Air-con/dishwasher are deliberately excluded — they are table stakes, not
# differentiators, and would wash out the overlap signal.
SIGNATURE_FEATURE_KEYWORDS = {
    "pool": ["pool"],
    "study": ["study", "home office"],
    "shed": ["shed", "workshop"],
    "dual_living": ["dual living", "dual occupancy", "granny flat", "self-contained", "in-law"],
    "waterfront": ["waterfront", "water frontage", "canal", "lake front", "lakefront", "riverfront"],
    "water_views": ["water view", "ocean view", "canal view"],
    "deck": ["deck", "alfresco"],
    "ensuite": ["ensuite"],
    "views": ["views", "outlook", "elevated"],
}


# ---------------------------------------------------------------------- #
# Small parsing helpers
# ---------------------------------------------------------------------- #

def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_PRICE_RE = re.compile(r"\$?\s*([\d][\d,]{4,})")


def _parse_price(*vals: Any) -> Optional[int]:
    """Best-effort price in whole dollars from any of the supplied values.
    Accepts ints, floats, and strings like '$1,365,000' or
    'Offers over $2,450,000'. Ignores small numbers (bed/bath counts)."""
    for v in vals:
        if v is None:
            continue
        if isinstance(v, (int, float)):
            iv = int(v)
            if iv >= 50_000:
                return iv
            continue
        if isinstance(v, str):
            m = _PRICE_RE.search(v)
            if m:
                digits = m.group(1).replace(",", "")
                try:
                    iv = int(digits)
                    if iv >= 50_000:
                        return iv
                except ValueError:
                    pass
    return None


def _doc_latlng(doc: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Coordinates already on a property doc, from any known source."""
    gc = doc.get("geocoded_coordinates")
    if isinstance(gc, dict):
        lat, lng = _to_float(gc.get("latitude")), _to_float(gc.get("longitude"))
        if lat is not None and lng is not None:
            return (lat, lng)
    lat = _to_float(doc.get("LATITUDE") or doc.get("latitude") or doc.get("lat"))
    lng = _to_float(doc.get("LONGITUDE") or doc.get("longitude") or doc.get("lng"))
    if lat is not None and lng is not None:
        return (lat, lng)
    return None


def _property_type_group(doc: Dict[str, Any]) -> Optional[str]:
    """Map a doc's property type onto a substitution group key."""
    raw = (doc.get("classified_property_type") or doc.get("property_type") or "").strip().lower()
    if not raw:
        return None
    for group, members in PROPERTY_TYPE_GROUPS.items():
        if raw in members:
            return group
    # Loose contains-match for unseen labels (e.g. "House with granny flat")
    for group, members in PROPERTY_TYPE_GROUPS.items():
        if any(m in raw for m in members):
            return group
    return None


def _signature_features(doc: Dict[str, Any], features_basic: Optional[Dict[str, Any]] = None) -> set:
    """The set of signature-feature keys a property carries. Reads the clean
    valuation-engine booleans where available and the raw `features` /
    `description` text otherwise."""
    keys: set = set()

    fb = features_basic or {}
    if fb.get("pool_present"):
        keys.add("pool")
    if fb.get("water_views"):
        keys.add("water_views")

    # Raw feature strings + description text for keyword detection.
    blob_parts: List[str] = []
    for f in (doc.get("features") or []):
        if isinstance(f, str):
            blob_parts.append(f)
    desc = doc.get("description") or doc.get("agents_description") or ""
    if isinstance(desc, str):
        blob_parts.append(desc)
    blob = " ".join(blob_parts).lower()

    for key, needles in SIGNATURE_FEATURE_KEYWORDS.items():
        if any(n in blob for n in needles):
            keys.add(key)
    return keys


# ---------------------------------------------------------------------- #
# Subject normalisation
# ---------------------------------------------------------------------- #

def _subject_profile(
    subject_doc: Dict[str, Any],
    features_basic: Optional[Dict[str, Any]],
    price_anchor: Optional[int],
) -> Dict[str, Any]:
    """Collapse the subject into the handful of axes we match on."""
    fb = features_basic or {}
    bed = _to_int(fb.get("bedrooms")) or _to_int(subject_doc.get("bedrooms"))
    bath = _to_int(fb.get("bathrooms")) or _to_int(subject_doc.get("bathrooms"))
    car = (_to_int(fb.get("car_spaces"))
           or _to_int(subject_doc.get("car_spaces"))
           or _to_int(subject_doc.get("carspaces")))
    floor = _to_float(fb.get("floor_area_sqm")) or _to_float(subject_doc.get("total_floor_area"))
    land = _to_float(fb.get("land_size_sqm")) or _to_float(subject_doc.get("lot_size_sqm"))
    anchor = price_anchor or _parse_price(
        subject_doc.get("price"), subject_doc.get("price_numeric"), subject_doc.get("listing_price")
    )
    return {
        "id": subject_doc.get("_id"),
        "group": _property_type_group(subject_doc) or "house",
        "bedrooms": bed,
        "bathrooms": bath,
        "car": car,
        "floor": floor,
        "land": land,
        "price": anchor,
        "features": _signature_features(subject_doc, fb),
        "latlng": _doc_latlng(subject_doc),
        "address": subject_doc.get("address") or subject_doc.get("street_address") or "",
    }


# ---------------------------------------------------------------------- #
# Candidate gathering + scoring
# ---------------------------------------------------------------------- #

_CANDIDATE_PROJECTION = {
    "address": 1, "street_address": 1, "suburb": 1, "price": 1,
    "price_numeric": 1, "listing_price": 1, "bedrooms": 1, "bathrooms": 1,
    "carspaces": 1, "car_spaces": 1, "lot_size_sqm": 1, "land_size_sqm": 1,
    "total_floor_area": 1, "property_type": 1, "classified_property_type": 1,
    "features": 1, "description": 1, "agents_description": 1,
    "domain_hero_image_url": 1, "domain_image_urls": 1, "property_images": 1,
    "listing_url": 1, "url_slug": 1, "days_on_domain": 1, "days_on_market": 1,
    "geocoded_coordinates": 1, "LATITUDE": 1, "LONGITUDE": 1,
    "valuation_data": 1,
}


def _geo_for_ring(geo: str, own_suburb: str, catchment: List[str]) -> List[str]:
    if geo == "own":
        return [own_suburb] if own_suburb else []
    if geo == "adjacent":
        adj = [own_suburb] + [s for s in catchment if s != own_suburb][:4]
        return [s for s in adj if s]
    return [own_suburb] + [s for s in catchment if s != own_suburb]


def _gather_candidates(
    db: Database,
    subject: Dict[str, Any],
    suburbs: List[str],
    price_band: float,
    bed_band: int,
) -> List[Dict[str, Any]]:
    """All for_sale substitutes across `suburbs` that clear the hard filters
    for this ring. Returns enriched candidate dicts (raw doc + parsed price)."""
    out: List[Dict[str, Any]] = []
    anchor = subject["price"]
    bed = subject["bedrooms"]
    group_members = PROPERTY_TYPE_GROUPS.get(subject["group"], set())

    query: Dict[str, Any] = {"listing_status": "for_sale"}
    if bed:
        query["bedrooms"] = {"$in": list(range(bed - bed_band, bed + bed_band + 1))}

    for suburb in suburbs:
        try:
            cursor = db[suburb].find(query, _CANDIDATE_PROJECTION)
        except Exception as e:
            logger.debug(f"  candidate query failed for {suburb}: {e}")
            continue
        for doc in cursor:
            if doc.get("_id") == subject["id"]:
                continue
            # Property-type group hard filter
            grp = _property_type_group(doc)
            if grp is not None and grp != subject["group"]:
                continue
            if grp is None and group_members:
                # Unknown type — only keep it if it has no type at all to judge
                continue
            cprice = _parse_price(
                doc.get("price"), doc.get("price_numeric"), doc.get("listing_price"),
                ((doc.get("valuation_data") or {}).get("reconciled_valuation")),
            )
            # Price band hard filter (only when we have both numbers)
            if anchor and cprice:
                if abs(cprice - anchor) / anchor > price_band:
                    continue
            elif anchor and not cprice:
                # No usable price — can't confirm it's a budget substitute. Skip.
                continue
            doc["_suburb_key"] = suburb
            doc["_price"] = cprice
            out.append(doc)
    return out


def _score(subject: Dict[str, Any], cand: Dict[str, Any]) -> float:
    """Weighted, renormalised similarity distance in [0, 1]. 0 = identical."""
    parts: List[Tuple[float, float]] = []  # (weight, normalised_distance)

    # Price — full penalty at 30% off the anchor.
    if subject["price"] and cand.get("_price"):
        rel = abs(cand["_price"] - subject["price"]) / subject["price"]
        parts.append((SCORE_WEIGHTS["price"], min(rel / 0.30, 1.0)))

    # Bedrooms — full penalty at 2 apart.
    if subject["bedrooms"]:
        cb = _to_int(cand.get("bedrooms"))
        if cb is not None:
            parts.append((SCORE_WEIGHTS["bedrooms"], min(abs(cb - subject["bedrooms"]) / 2.0, 1.0)))

    # Bathrooms — full penalty at 2 apart.
    if subject["bathrooms"]:
        cv = _to_int(cand.get("bathrooms"))
        if cv is not None:
            parts.append((SCORE_WEIGHTS["bathrooms"], min(abs(cv - subject["bathrooms"]) / 2.0, 1.0)))

    # Car — full penalty at 2 apart.
    if subject["car"]:
        cv = _to_int(cand.get("carspaces") or cand.get("car_spaces"))
        if cv is not None:
            parts.append((SCORE_WEIGHTS["car"], min(abs(cv - subject["car"]) / 2.0, 1.0)))

    # Floor area — full penalty at 40% off.
    if subject["floor"]:
        cv = _to_float(cand.get("total_floor_area"))
        if cv:
            rel = abs(cv - subject["floor"]) / subject["floor"]
            parts.append((SCORE_WEIGHTS["floor"], min(rel / 0.40, 1.0)))

    # Land size — full penalty at 40% off.
    if subject["land"]:
        cv = _to_float(cand.get("lot_size_sqm") or cand.get("land_size_sqm"))
        if cv:
            rel = abs(cv - subject["land"]) / subject["land"]
            parts.append((SCORE_WEIGHTS["land"], min(rel / 0.40, 1.0)))

    # Signature-feature overlap (Jaccard distance).
    if subject["features"]:
        cf = _signature_features(cand)
        union = subject["features"] | cf
        if union:
            jaccard = len(subject["features"] & cf) / len(union)
            parts.append((SCORE_WEIGHTS["features"], 1.0 - jaccard))

    if not parts:
        return 1.0
    total_w = sum(w for w, _ in parts)
    return sum(w * d for w, d in parts) / total_w


# ---------------------------------------------------------------------- #
# Honest difference line
# ---------------------------------------------------------------------- #

def _difference_line(subject: Dict[str, Any], cand: Dict[str, Any]) -> str:
    """One factual sentence framing this listing AGAINST the subject. Keeps
    the match card a comparison, not an advertisement for the competition.
    Editorial: value-neutral, no advice, no superlatives."""
    shared: List[str] = []
    diffs: List[str] = []

    cb = _to_int(cand.get("bedrooms"))
    if subject["bedrooms"] and cb is not None:
        if cb == subject["bedrooms"]:
            shared.append(f"the same {cb} bedrooms")
        else:
            diffs.append(f"{cb} bedrooms versus your {subject['bedrooms']}")

    # Price comparison
    if subject["price"] and cand.get("_price"):
        pct = (cand["_price"] - subject["price"]) / subject["price"] * 100
        if abs(pct) >= 3:
            direction = "above" if pct > 0 else "below"
            diffs.append(f"listed {abs(pct):.0f}% {direction} your guide")
        else:
            shared.append("a near-identical price guide")

    # Land
    if subject["land"]:
        cv = _to_float(cand.get("lot_size_sqm") or cand.get("land_size_sqm"))
        if cv and abs(cv - subject["land"]) >= 50:
            delta = int(cv - subject["land"])
            direction = "larger" if delta > 0 else "smaller"
            diffs.append(f"a {abs(delta)} m² {direction} block")

    # Feature gap (what they have that subject doesn't, and vice versa)
    cf = _signature_features(cand)
    only_them = cf - subject["features"]
    only_you = subject["features"] - cf
    label = {
        "pool": "a pool", "study": "a study", "shed": "a shed",
        "dual_living": "dual living", "waterfront": "waterfront", "water_views": "water views",
        "deck": "an alfresco deck", "ensuite": "an ensuite", "views": "an elevated outlook",
    }
    if only_them:
        f = next(iter(only_them))
        diffs.append(f"adds {label.get(f, f.replace('_', ' '))}")
    elif only_you:
        f = next(iter(only_you))
        diffs.append(f"without {label.get(f, f.replace('_', ' '))}")

    suburb = (cand.get("suburb") or cand.get("_suburb_key", "").replace("_", " ")).title()

    head = shared[0].capitalize() if shared else f"In {suburb}"
    tail = ", ".join(diffs[:2]) if diffs else "a close like-for-like comparison"
    return f"{head}, but {tail}."


# ---------------------------------------------------------------------- #
# Geocoding (final picks only)
# ---------------------------------------------------------------------- #

def _geocode(address: str) -> Optional[Tuple[float, float]]:
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "au"},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            r = resp.json()[0]
            return (float(r["lat"]), float(r["lon"]))
    except Exception as e:
        logger.debug(f"  geocode failed for {address}: {e}")
    return None


def _persist_geocode(db: Database, suburb_key: str, doc_id: Any, lat: float, lng: float) -> None:
    """Write a freshly-geocoded coordinate back to the listing so we never
    pay for it twice."""
    try:
        db[suburb_key].update_one(
            {"_id": doc_id},
            {"$set": {"geocoded_coordinates": {
                "latitude": lat, "longitude": lng,
                "source": "nominatim", "geocoded_at": datetime.now(timezone.utc),
            }}},
        )
    except Exception as e:
        logger.debug(f"  geocode persist failed: {e}")


def _hero_image(doc: Dict[str, Any]) -> Optional[str]:
    if doc.get("domain_hero_image_url"):
        return doc["domain_hero_image_url"]
    imgs = doc.get("domain_image_urls") or doc.get("property_images")
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url") or first.get("src")
    return None


# ---------------------------------------------------------------------- #
# Public entry point
# ---------------------------------------------------------------------- #

def resolve_competitor_map(
    subject_doc: Dict[str, Any],
    db: Database,
    features_basic: Optional[Dict[str, Any]] = None,
    *,
    price_anchor: Optional[int] = None,
    catchment: Optional[List[str]] = None,
    geocode_missing: bool = True,
) -> Optional[Dict[str, Any]]:
    """Build the CompetitorMapData for one subject. Returns None when the
    subject lacks the minimum data to define substitutes (no bedrooms / no
    price anchor), or when not a single substitute exists anywhere.

    price_anchor: the subject's valuation working-range midpoint (preferred
    for off-market submissions). Falls back to the subject's own price string.
    """
    subject = _subject_profile(subject_doc, features_basic, price_anchor)
    if not subject["bedrooms"] or not subject["price"]:
        logger.info(
            "  competitor_matcher: subject missing bedrooms or price anchor "
            f"(beds={subject['bedrooms']}, price={subject['price']}) — skipping"
        )
        return None

    own = (subject_doc.get("suburb_key")
           or subject_doc.get("_suburb_key")
           or (subject_doc.get("suburb") or "").lower().replace(" ", "_"))
    catch = catchment or DEFAULT_CATCHMENT

    # Walk the aperture rings until one yields TARGET_MIN survivors.
    chosen_ring = None
    candidates: List[Dict[str, Any]] = []
    for idx, ring in enumerate(APERTURE_RINGS):
        suburbs = _geo_for_ring(ring["geo"], own, catch)
        found = _gather_candidates(db, subject, suburbs, ring["price"], ring["beds"])
        # De-dupe by _id (adjacent rings re-scan suburbs)
        seen = set()
        deduped = []
        for c in found:
            if c["_id"] in seen:
                continue
            seen.add(c["_id"])
            deduped.append(c)
        candidates = deduped
        chosen_ring = idx
        logger.info(
            f"  competitor_matcher ring {idx} ({ring['geo']}, ±{int(ring['price']*100)}%, "
            f"±{ring['beds']}bd): {len(candidates)} substitutes"
        )
        if len(candidates) >= TARGET_MIN:
            break

    if len(candidates) < FLOOR_MIN:
        logger.info("  competitor_matcher: no substitutes found at any aperture")
        return None

    # Rank by similarity, keep the closest TARGET_MAX.
    for c in candidates:
        c["_score"] = _score(subject, c)
    candidates.sort(key=lambda c: c["_score"])
    active_in_band = len(candidates)
    chosen = candidates[:TARGET_MAX]

    # Resolve coordinates for the chosen few — reuse what's on the doc,
    # geocode the rest (rate-limited; final set is <=6 so cost is trivial).
    competitors: List[Dict[str, Any]] = []
    best_score = chosen[0]["_score"] if chosen else 1.0
    for i, c in enumerate(chosen):
        latlng = _doc_latlng(c)
        if latlng is None and geocode_missing:
            addr = c.get("address") or c.get("street_address")
            if addr:
                latlng = _geocode(addr)
                if latlng:
                    _persist_geocode(db, c["_suburb_key"], c["_id"], latlng[0], latlng[1])
                time.sleep(NOMINATIM_DELAY)
        if latlng is None:
            # Can't plot it without coordinates — skip from the map set.
            logger.debug(f"  dropping {c.get('address')} — no coordinates")
            continue

        # Closest tier: at/under threshold, plus the single best is always in.
        is_close = c["_score"] <= CLOSE_MATCH_THRESHOLD or (i == 0)
        price_int = c.get("_price")
        price_text = (c.get("price") if isinstance(c.get("price"), str) and "$" in (c.get("price") or "")
                      else (f"${price_int:,}" if price_int else "Contact agent"))
        suburb_disp = (c.get("suburb") or c.get("_suburb_key", "").replace("_", " ")).title()
        slug = c.get("url_slug") or str(c.get("_id"))

        competitors.append({
            "id": f"{c['_suburb_key']}-{slug}",
            "address": c.get("address") or c.get("street_address"),
            "suburb": suburb_disp,
            "lat": latlng[0],
            "lng": latlng[1],
            "priceText": price_text,
            "priceLow": price_int,
            "bedrooms": _to_int(c.get("bedrooms")),
            "bathrooms": _to_int(c.get("bathrooms")),
            "carSpaces": _to_int(c.get("carspaces") or c.get("car_spaces")),
            "daysOnMarket": _to_int(c.get("days_on_domain") or c.get("days_on_market")),
            "features": sorted(_signature_features(c)),
            "combinatorialMatch": is_close,
            "listingUrl": c.get("listing_url"),
            "imageSrc": _hero_image(c) if is_close else None,
            "differenceVsSubject": _difference_line(subject, c) if is_close else None,
            "_score": round(c["_score"], 4),
        })

    if not competitors:
        return None

    subj_latlng = subject["latlng"]
    if subj_latlng is None and geocode_missing and subject["address"]:
        subj_latlng = _geocode(subject["address"])
    if subj_latlng is None:
        logger.info("  competitor_matcher: subject has no coordinates — cannot anchor map")
        return None

    ring_meta = APERTURE_RINGS[chosen_ring]
    return {
        "subject": {
            "lat": subj_latlng[0],
            "lng": subj_latlng[1],
            "address": subject["address"],
        },
        "competitors": competitors,
        "aperture_ring": chosen_ring,
        "aperture_label": ring_meta["label"],
        "catchment": _geo_for_ring(ring_meta["geo"], own, catch),
        "active_in_band": active_in_band,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------- #
# CLI — quick test against a real subject by suburb + address fragment
# ---------------------------------------------------------------------- #

def _main() -> int:
    import argparse
    import json
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    from shared.db import get_gold_coast_db  # noqa: E402
    from scripts.property_reports.inline_features import derive_features_basic  # noqa: E402

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Test the competitor matcher against a real property")
    ap.add_argument("--suburb", required=True, help="collection key, e.g. robina")
    ap.add_argument("--address", required=True, help="address fragment, e.g. '25 Huntingdale'")
    ap.add_argument("--anchor", type=int, default=None, help="price anchor override")
    ap.add_argument("--no-geocode", action="store_true", help="skip Nominatim lookups")
    args = ap.parse_args()

    db = get_gold_coast_db()
    subj = db[args.suburb].find_one({"address": {"$regex": args.address, "$options": "i"}})
    if not subj:
        print(f"No property matching '{args.address}' in {args.suburb}")
        return 1
    subj.setdefault("suburb_key", args.suburb)
    fb = derive_features_basic(subj)
    result = resolve_competitor_map(
        subj, db, fb, price_anchor=args.anchor, geocode_missing=not args.no_geocode
    )
    if not result:
        print("No competitor map produced.")
        return 1
    print(json.dumps(result, indent=2, default=str))
    print(
        f"\nSummary: {len(result['competitors'])} substitutes, "
        f"ring {result['aperture_ring']} ({result['aperture_label']}), "
        f"{sum(1 for c in result['competitors'] if c['combinatorialMatch'])} in closest tier, "
        f"{result['active_in_band']} in band before trim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
