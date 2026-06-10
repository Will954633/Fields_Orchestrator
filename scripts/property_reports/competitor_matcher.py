"""
Competitor matcher — the live "substitute homes" set for the mini-site
Market tab competitor map.

A *substitute* is a home a buyer is actually choosing between, not a home
that merely shares the subject's signature features (that feature-twin count
is a separate claim, owned by scarcity_features.py). Substitutability is
defined by the stable, observable attributes both homes carry — property type,
bedroom band, bathrooms, land, floor area, features and proximity — NOT by a
price the analyst hasn't set yet. So the matcher:

  1. Hard-filters candidates to genuine substitutes: same property-type GROUP
     (House+Duplex never mixes in a Unit), within the catchment, for_sale,
     within a bedroom band. Price is NOT a gather filter, so auction / EOI /
     price-withheld listings are tracked like any other competitor.
  2. Ranks survivors by a weighted, PHYSICAL-LED similarity score; price enters
     only as a soft, low-weight term plus a wide guardrail on the close tier.
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
loosest ring has literally proven its scarcity ("we widened the search to the
whole catchment and ±2 bedrooms before comparable homes appeared"). Rings widen
on geography and bedroom band only — price is never a gather gate, so auction
and price-withheld listings are always in scope.
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
# list until a ring yields >= TARGET_MIN candidates (or the list is exhausted).
# Rings widen on geography and bedroom band ONLY — price is never a gather gate
# (see SCORE_WEIGHTS / PRICE_GUARD_BAND), so auction and price-withheld homes
# are always in scope.
#   geo:  "own"      = subject's suburb only
#         "adjacent" = own + first 4 catchment suburbs
#         "full"     = whole catchment
#   beds:  absolute bedroom tolerance (±)
APERTURE_RINGS = [
    {"geo": "own",      "beds": 1,
     "label": "houses in your own suburb within one bedroom of yours"},
    {"geo": "adjacent", "beds": 1,
     "label": "houses in your suburb and its neighbours within one bedroom of yours"},
    {"geo": "full",     "beds": 1,
     "label": "houses across the southern-Gold-Coast catchment within one bedroom of yours"},
    {"geo": "full",     "beds": 2,
     "label": "houses across the whole southern-Gold-Coast catchment within two bedrooms either way"},
]

# Similarity score weights. Lower score = closer substitute. Weights are
# renormalised at runtime over whichever factors both homes actually carry,
# so a missing floor area neither helps nor unfairly hurts a candidate.
#
# Ranking is PHYSICAL-LED, not price-led, and deliberately so. At report-build
# time the analyst has not yet set the subject's price, so we only have a model
# working range — ranking on closeness to a number we invented is circular. And
# the page's job is to track every competitor a buyer sees, including auction /
# EOI / "contact agent" listings that publish no figure at all. So substitut-
# ability is defined by the stable, observable attributes both homes actually
# carry: bedroom band, bathrooms, land, floor area, signature features, and
# proximity. Price is a SOFT, low-weight term (used only when both homes quote
# one) plus a wide guardrail on the "close" tier (see PRICE_GUARD_BAND) — never
# a ranking lead and never a gate that deletes listings.
#
# Distance is a meaningful secondary factor — a nearer home outranks a farther
# one all else equal ("local first") — by straight-line distance, not suburb
# name (which mis-ranks homes near a boundary).
SCORE_WEIGHTS = {
    "bedrooms": 0.22,
    "land": 0.20,
    "distance": 0.18,
    "bathrooms": 0.13,
    "features": 0.11,
    "car": 0.06,
    "floor": 0.05,
    "price": 0.05,
}

# Distance term reaches full penalty at this straight-line distance (km) from
# the subject. The southern-GC catchment spans ~15-20km; 8km cleanly separates
# "same suburb / next door" from "across the catchment" without flattening the
# near tail. Beyond it, every candidate is equally "far".
DISTANCE_FULL_PENALTY_KM = 8.0

# Suburb centroids (median of geocoded listings) — the cheap ranking proxy for
# candidates that aren't individually geocoded yet (~28%). Avoids adding a
# Nominatim call per candidate to every build; exact coords are used for the
# final picks' display distance. Regenerate if the catchment list changes.
CATCHMENT_CENTROIDS = {
    "robina": (-28.07251, 153.39525),
    "varsity_lakes": (-28.08250, 153.40787),
    "clear_island_waters": (-28.03986, 153.40086),
    "merrimac": (-28.04707, 153.36040),
    "mudgeeraba": (-28.08741, 153.36523),
    "reedy_creek": (-28.11016, 153.39886),
    "worongary": (-28.04128, 153.33947),
    "burleigh_waters": (-28.08920, 153.42811),
    "carrara": (-28.02123, 153.37140),
}

# A candidate is shown in the prominent "closest match" tier (yellow marker +
# match card) when its PHYSICAL similarity score is at or below this AND it
# clears the price guardrail below. This is the honest "truly compete" count —
# there is no floor: if nothing clears the bar, the close tier is genuinely 0
# (a strong scarcity signal), and the map still plots the nearest homes, just
# without the close-match styling.
CLOSE_MATCH_THRESHOLD = 0.20

# Price guardrail for the "close" tier ONLY (never a gather filter). A home that
# quotes a price more than this fraction away from the subject's working-range
# anchor is in a different budget bracket, so it is tracked and ranked on
# physical merit but kept OUT of the "competes closely" tier — a $2.4M home is
# not direct competition for a ~$1.3M one even if the bedrooms match. Listings
# with no published price (auction / EOI / contact agent) are NEVER excluded by
# this: they pass the guard and rank purely on physical similarity. When the
# subject has no price anchor at all (pre-valuation), the guard is inactive.
PRICE_GUARD_BAND = 0.50

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


# Long comma/long-form numbers ($1,190,000 / 1450000). Needs a 5+ digit run so
# bed/bath counts and street numbers don't read as prices.
_FULL_NUM_RE = re.compile(r"\$?\s*([\d][\d,]{4,})")
# Abbreviated millions/thousands ($1.3M, $1.9m+, $1.695m, $950k). Agents quote
# guides this way constantly — the long-form regex above can't see them.
_ABBR_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*([mMkK])")


def _money_tokens(s: str) -> List[int]:
    """Every dollar figure in a string, in whole dollars, in order of
    appearance. Handles '$1.3M', '$950k' and '$1,190,000' forms together, so a
    range like 'Price Guide $1.3M - $1.4M' yields [1300000, 1400000]."""
    out: List[Tuple[int, int]] = []
    abbr_spans: List[Tuple[int, int]] = []
    for m in _ABBR_RE.finditer(s):
        mult = 1_000_000 if m.group(2).lower() == "m" else 1_000
        out.append((m.start(), int(float(m.group(1)) * mult)))
        abbr_spans.append((m.start(), m.end()))
    for m in _FULL_NUM_RE.finditer(s):
        # Skip digits already consumed by an abbreviated match (e.g. the "1" in "$1.3M").
        if any(a <= m.start() < b for a, b in abbr_spans):
            continue
        try:
            iv = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if iv >= 50_000:
            out.append((m.start(), iv))
    out.sort()
    return [v for _, v in out]


def _parse_price(*vals: Any) -> Optional[int]:
    """Best-effort price in whole dollars from any of the supplied values.
    Accepts ints, floats, and strings like '$1,365,000', 'Offers over
    $2,450,000', '$1.3M', '$1.9m+', and ranges like '$1.3M - $1.4M' (returns
    the range midpoint). Ignores small numbers (bed/bath counts). Returns None
    only when there is genuinely no figure (e.g. 'Auction', 'Contact Agent')."""
    for v in vals:
        if v is None:
            continue
        if isinstance(v, (int, float)):
            iv = int(v)
            if iv >= 50_000:
                return iv
            continue
        if isinstance(v, str):
            toks = _money_tokens(v)
            if toks:
                # Range -> midpoint; single figure -> itself.
                return int((min(toks) + max(toks)) / 2)
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


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lng) points."""
    import math
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _candidate_point(doc: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Best available (lat, lng) for ranking — the doc's own coordinates if it
    has them, else its suburb centroid (the cheap proxy). None if neither."""
    exact = _doc_latlng(doc)
    if exact:
        return exact
    return CATCHMENT_CENTROIDS.get(doc.get("_suburb_key", ""))


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
    bed_band: int,
) -> List[Dict[str, Any]]:
    """All for_sale substitutes across `suburbs` that clear the hard filters
    for this ring — same property-type GROUP and within the bedroom band.

    Price is deliberately NOT a hard filter: a listing with no published price
    (auction / EOI / contact agent) is still a home the buyer is choosing
    between, and the page's job is to track every competitor. Price, where
    quoted, is captured for the soft scoring term and the close-tier guardrail.
    Returns enriched candidate dicts (raw doc + parsed price, or None price)."""
    out: List[Dict[str, Any]] = []
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
            doc["_suburb_key"] = suburb
            doc["_price"] = _parse_price(
                doc.get("price"), doc.get("price_numeric"), doc.get("listing_price"),
                ((doc.get("valuation_data") or {}).get("reconciled_valuation")),
            )
            out.append(doc)
    return out


def _score(subject: Dict[str, Any], cand: Dict[str, Any]) -> float:
    """Weighted, renormalised similarity distance in [0, 1]. 0 = identical.

    Thin wrapper over `_score_with_breakdown` for the hot ranking path where
    only the float is needed."""
    return _score_with_breakdown(subject, cand)[0]


# Plain-language labels for each scoring axis — used in the "show our working"
# per-home breakdown. Kept here so the model is documented in one place.
SCORE_FACTOR_LABELS = {
    "price": "Price guide",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "car": "Car spaces",
    "floor": "Internal floor area",
    "land": "Land size",
    "features": "Signature features",
    "distance": "Proximity",
}


def _score_with_breakdown(
    subject: Dict[str, Any], cand: Dict[str, Any]
) -> Tuple[float, List[Dict[str, Any]]]:
    """Weighted, renormalised similarity distance in [0, 1] PLUS a per-axis
    breakdown for the transparency panel. 0 = identical.

    The breakdown is the literal "why this ranks here": one row per factor we
    could actually compare (a factor is skipped, not penalised, when either
    home lacks the data — and the remaining weights renormalise). Each row:
        {factor, label, weight, subjectValue, candidateValue,
         normalisedDistance, contribution}
    where contribution is the renormalised weight*distance (sums to `score`).
    """
    # (weight, normalised_distance, factor_key, subject_value, candidate_value)
    parts: List[Tuple[float, float, str, Any, Any]] = []

    # Price — full penalty at 30% off the anchor.
    if subject["price"] and cand.get("_price"):
        rel = abs(cand["_price"] - subject["price"]) / subject["price"]
        parts.append((SCORE_WEIGHTS["price"], min(rel / 0.30, 1.0),
                      "price", subject["price"], cand["_price"]))

    # Bedrooms — full penalty at 2 apart.
    if subject["bedrooms"]:
        cb = _to_int(cand.get("bedrooms"))
        if cb is not None:
            parts.append((SCORE_WEIGHTS["bedrooms"], min(abs(cb - subject["bedrooms"]) / 2.0, 1.0),
                          "bedrooms", subject["bedrooms"], cb))

    # Bathrooms — full penalty at 2 apart.
    if subject["bathrooms"]:
        cv = _to_int(cand.get("bathrooms"))
        if cv is not None:
            parts.append((SCORE_WEIGHTS["bathrooms"], min(abs(cv - subject["bathrooms"]) / 2.0, 1.0),
                          "bathrooms", subject["bathrooms"], cv))

    # Car — full penalty at 2 apart.
    if subject["car"]:
        cv = _to_int(cand.get("carspaces") or cand.get("car_spaces"))
        if cv is not None:
            parts.append((SCORE_WEIGHTS["car"], min(abs(cv - subject["car"]) / 2.0, 1.0),
                          "car", subject["car"], cv))

    # Floor area — full penalty at 60% off. Scraped internal-area figures are
    # noisy and inconsistently defined (garage in/out, "legacy_layout"
    # estimates), so floor is a low-weight, wide-tolerance signal — land size is
    # the reliable size axis. A modest internal-area gap must not disqualify an
    # otherwise direct competitor.
    if subject["floor"]:
        cv = _to_float(cand.get("total_floor_area"))
        if cv:
            rel = abs(cv - subject["floor"]) / subject["floor"]
            parts.append((SCORE_WEIGHTS["floor"], min(rel / 0.60, 1.0),
                          "floor", subject["floor"], cv))

    # Land size — full penalty at 40% off.
    if subject["land"]:
        cv = _to_float(cand.get("lot_size_sqm") or cand.get("land_size_sqm"))
        if cv:
            rel = abs(cv - subject["land"]) / subject["land"]
            parts.append((SCORE_WEIGHTS["land"], min(rel / 0.40, 1.0),
                          "land", subject["land"], cv))

    # Signature-feature coverage — asymmetric, anchored on the SUBJECT's
    # features. We ask "does this competitor carry what makes the subject
    # desirable?" (e.g. its pool), NOT symmetric Jaccard — a candidate must
    # never be penalised for offering MORE than the subject (an extra ensuite
    # doesn't make it less of a competitor).
    if subject["features"]:
        cf = _signature_features(cand)
        covered = len(subject["features"] & cf) / len(subject["features"])
        parts.append((SCORE_WEIGHTS["features"], 1.0 - covered,
                      "features", sorted(subject["features"]), sorted(cf)))

    # Distance — secondary "closer ranks first" term. Full penalty at
    # DISTANCE_FULL_PENALTY_KM. Uses exact coords where available, suburb
    # centroid otherwise; skipped entirely if neither point is resolvable.
    subj_pt = subject.get("point")
    cand_pt = _candidate_point(cand)
    if subj_pt and cand_pt:
        dist = _haversine_km(subj_pt, cand_pt)
        parts.append((SCORE_WEIGHTS["distance"], min(dist / DISTANCE_FULL_PENALTY_KM, 1.0),
                      "distance", None, round(dist, 1)))

    if not parts:
        return 1.0, []

    total_w = sum(w for w, _, _, _, _ in parts)
    score = sum(w * d for w, d, _, _, _ in parts) / total_w

    breakdown = [
        {
            "factor": key,
            "label": SCORE_FACTOR_LABELS.get(key, key),
            "weight": round(w / total_w, 4),          # renormalised share
            "subjectValue": sv,
            "candidateValue": cv,
            "normalisedDistance": round(d, 4),         # 0 = identical, 1 = full penalty
            "contribution": round((w * d) / total_w, 4),
        }
        for w, d, key, sv, cv in parts
    ]
    return score, breakdown


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


def _within_price_guard(subject: Dict[str, Any], cand: Dict[str, Any]) -> bool:
    """True if `cand` may sit in the close ("truly compete") tier on price.

    Listings with no published price (auction / EOI / contact agent) always
    pass — they are tracked competitors and rank on physical merit. A home that
    DOES quote a price more than PRICE_GUARD_BAND away from the subject's anchor
    is a different budget bracket and is held out of the close tier. When the
    subject has no anchor yet (pre-valuation), the guard is inactive."""
    anchor = subject.get("price")
    cprice = cand.get("_price")
    if not anchor or not cprice:
        return True
    return abs(cprice - anchor) / anchor <= PRICE_GUARD_BAND


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

# How many ranked rows to persist for the "show our working" panel. Enough to
# show the similarity cliff after the close tier without dumping the whole
# catchment (which would bury the proof). The map still plots only TARGET_MAX.
RANKED_COMPARISON_KEEP = 20


def _ranked_home_row(subject: Dict[str, Any], cand: Dict[str, Any], rank: int) -> Dict[str, Any]:
    """One row of the transparency ranked list. matchPct is the model's
    closeness as a percentage (100 = identical) — a documented heuristic
    output, NOT a valuation or a guarantee. Carries the per-axis breakdown
    and a live listing link so the seller can verify every home themselves."""
    score = cand["_score"]
    price_int = cand.get("_price")
    price_text = (cand.get("price") if isinstance(cand.get("price"), str) and "$" in (cand.get("price") or "")
                  else (f"${price_int:,}" if price_int else "Contact agent"))
    suburb_disp = (cand.get("suburb") or cand.get("_suburb_key", "").replace("_", " ")).title()
    cand_pt = _candidate_point(cand)
    subj_pt = subject.get("point")
    distance_km = (round(_haversine_km(subj_pt, cand_pt), 1)
                   if subj_pt and cand_pt else None)
    return {
        "rank": rank,
        "matchPct": round((1.0 - score) * 100),
        "score": round(score, 4),
        "address": cand.get("address") or cand.get("street_address"),
        "suburb": suburb_disp,
        "priceText": price_text,
        "priceLow": price_int,
        "bedrooms": _to_int(cand.get("bedrooms")),
        "bathrooms": _to_int(cand.get("bathrooms")),
        "carSpaces": _to_int(cand.get("carspaces") or cand.get("car_spaces")),
        "landSqm": _to_int(cand.get("lot_size_sqm") or cand.get("land_size_sqm")),
        "floorSqm": _to_int(cand.get("total_floor_area")),
        "distanceKm": distance_km,
        "features": sorted(_signature_features(cand)),
        "listingUrl": cand.get("listing_url"),
        "imageSrc": _hero_image(cand),
        "isClose": cand["_score"] <= CLOSE_MATCH_THRESHOLD and _within_price_guard(subject, cand),
        "breakdown": cand.get("_breakdown", []),
    }


def resolve_competitor_map(
    subject_doc: Dict[str, Any],
    db: Database,
    features_basic: Optional[Dict[str, Any]] = None,
    *,
    price_anchor: Optional[int] = None,
    catchment: Optional[List[str]] = None,
    geocode_missing: bool = True,
    active_listings_total: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Build the CompetitorMapData for one subject. Returns None when the
    subject lacks the minimum data to define substitutes (no bedrooms / no
    price anchor), or when not a single substitute exists anywhere.

    price_anchor: the subject's valuation working-range midpoint (preferred
    for off-market submissions). Falls back to the subject's own price string.

    active_listings_total: the catchment-wide active count (from
    scarcity_features) used as the TOP of the transparency funnel — so the
    panel's "174 active → N substitutes → ranked" story reconciles with the
    Market-tab headline. Omitted → funnel top falls back to in-band count.
    """
    subject = _subject_profile(subject_doc, features_basic, price_anchor)
    if not subject["bedrooms"]:
        logger.info(
            "  competitor_matcher: subject missing bedroom count — cannot define "
            "a substitute set, skipping"
        )
        return None
    if not subject["price"]:
        # No price anchor yet (analyst hasn't valued the home) — ranking is
        # purely physical and the price guardrail is inactive. This is expected
        # for fresh off-market submissions, not an error.
        logger.info("  competitor_matcher: no price anchor — ranking on physical attributes only")

    own = (subject_doc.get("suburb_key")
           or subject_doc.get("_suburb_key")
           or (subject_doc.get("suburb") or "").lower().replace(" ", "_"))
    catch = catchment or DEFAULT_CATCHMENT

    # Origin point for the distance term — the subject's own coordinates if it
    # has them, else its suburb centroid. Set before scoring so "closer ranks
    # first" applies even for off-market subjects not yet individually geocoded.
    subject["point"] = subject["latlng"] or CATCHMENT_CENTROIDS.get(own)

    # Walk the aperture rings until one yields TARGET_MIN survivors.
    chosen_ring = None
    candidates: List[Dict[str, Any]] = []
    for idx, ring in enumerate(APERTURE_RINGS):
        suburbs = _geo_for_ring(ring["geo"], own, catch)
        found = _gather_candidates(db, subject, suburbs, ring["beds"])
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
            f"  competitor_matcher ring {idx} ({ring['geo']}, ±{ring['beds']}bd): "
            f"{len(candidates)} substitutes"
        )
        if len(candidates) >= TARGET_MIN:
            break

    if len(candidates) < FLOOR_MIN:
        logger.info("  competitor_matcher: no substitutes found at any aperture")
        return None

    # Rank by similarity, keep the closest TARGET_MAX. Capture each candidate's
    # per-axis breakdown here so the transparency panel can show the working
    # for the whole ranked tail, not just the plotted few.
    for c in candidates:
        c["_score"], c["_breakdown"] = _score_with_breakdown(subject, c)
    candidates.sort(key=lambda c: c["_score"])
    active_in_band = len(candidates)
    chosen = candidates[:TARGET_MAX]

    # Resolve the subject's display coordinates up-front so the per-competitor
    # distance is measured from the real home, not a centroid. Falls back to
    # the centroid only if the subject can't be geocoded at all.
    subj_latlng = subject["latlng"]
    if subj_latlng is None and geocode_missing and subject["address"]:
        subj_latlng = _geocode(subject["address"])
    if subj_latlng is None:
        logger.info("  competitor_matcher: subject has no coordinates — cannot anchor map")
        return None
    subject["point"] = subj_latlng  # exact origin for display distances

    # Resolve coordinates for the chosen few — reuse what's on the doc,
    # geocode the rest (rate-limited; final set is <=6 so cost is trivial).
    competitors: List[Dict[str, Any]] = []
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

        # Closest tier: physical similarity at/under threshold AND within the
        # price guardrail (price-withheld homes always clear the guard). No
        # auto-promotion of the top home — if nothing qualifies, the close tier
        # is honestly empty.
        is_close = c["_score"] <= CLOSE_MATCH_THRESHOLD and _within_price_guard(subject, c)
        price_int = c.get("_price")
        price_text = (c.get("price") if isinstance(c.get("price"), str) and "$" in (c.get("price") or "")
                      else (f"${price_int:,}" if price_int else "Contact agent"))
        suburb_disp = (c.get("suburb") or c.get("_suburb_key", "").replace("_", " ")).title()
        slug = c.get("url_slug") or str(c.get("_id"))
        distance_km = round(_haversine_km(subj_latlng, latlng), 1)

        competitors.append({
            "id": f"{c['_suburb_key']}-{slug}",
            "address": c.get("address") or c.get("street_address"),
            "suburb": suburb_disp,
            "lat": latlng[0],
            "lng": latlng[1],
            "distanceKm": distance_km,
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

    ring_meta = APERTURE_RINGS[chosen_ring]

    # "Show our working" — the ranked comparison the headline rests on. The
    # whole sorted set is in `candidates`; we persist the top RANKED_COMPARISON_KEEP
    # (each with its per-axis breakdown) plus the funnel counts that bridge the
    # broad catchment count to the substitute set. n_close is computed over the
    # full ranked set, not just the plotted few, so "only N truly compete"
    # matches what the seller counts in the list.
    n_close = sum(
        1 for c in candidates
        if c["_score"] <= CLOSE_MATCH_THRESHOLD and _within_price_guard(subject, c)
    )
    ranked_homes = [
        _ranked_home_row(subject, c, i + 1)
        for i, c in enumerate(candidates[:RANKED_COMPARISON_KEEP])
    ]
    funnel_top = active_listings_total if (active_listings_total and active_listings_total > 0) else active_in_band
    ranked_comparison = {
        "funnel": {
            "active_total": funnel_top,
            "in_band": active_in_band,
            "ranked_shown": len(ranked_homes),
            "close_tier": n_close,
        },
        "weights": dict(SCORE_WEIGHTS),
        "aperture_label": ring_meta["label"],
        "close_match_threshold_pct": round((1.0 - CLOSE_MATCH_THRESHOLD) * 100),
        "homes": ranked_homes,
    }

    return {
        "subject": {
            "lat": subj_latlng[0],
            "lng": subj_latlng[1],
            "address": subject["address"],
            # Real subject specs for the map popup (no hardcoded values).
            "bedrooms": subject["bedrooms"],
            "bathrooms": subject["bathrooms"],
            "carSpaces": subject["car"],
            "landSqm": int(subject["land"]) if subject["land"] else None,
            "features": sorted(subject["features"]),
        },
        "competitors": competitors,
        "aperture_ring": chosen_ring,
        "aperture_label": ring_meta["label"],
        "catchment": _geo_for_ring(ring_meta["geo"], own, catch),
        "active_in_band": active_in_band,
        "ranked_comparison": ranked_comparison,
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
