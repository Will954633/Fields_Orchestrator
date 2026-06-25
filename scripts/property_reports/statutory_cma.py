"""
Statutory Comparative Market Analysis — Property Occupations Act 2014 (Qld).

WHY THIS EXISTS
---------------
The "your home" mini-site is a digital property appraisal. Under s 215 of the
PO Act, when a seller asks an agent for information about a likely sale price the
agent MUST provide a Comparative Market Analysis (CMA) — or, if a CMA can't be
prepared, a written explanation of how market value was decided. Schedule 2
defines a CMA as a document comparing the subject with **at least 3 properties
sold within the previous 6 months, of similar standard or condition, within 5 km**.

The valuation ENGINE (Feilds_Website/07_Valuation_Comps/precompute_valuations.py)
selects comps suburb-first over a ~12-month window and time-adjusts them. That is
a sound estimate but is NOT, on its face, the Schedule 2 CMA. This module builds
the statutory CMA as a separate, explicit layer.

DESIGN DECISION (2026-06, audit item A — "display + light support only")
------------------------------------------------------------------------
This layer SELECTS and SURFACES the statutory comparables. It does NOT re-base the
engine's math. Cross-suburb 5 km comps (used only to rescue thin suburbs) need
full location-adjustment + a backtest before they may feed the figure. So:
  * core suburbs almost never leave their own suburb (data analysis: 0% needed the
    ring; 35-62 qualifying sales each), so the displayed CMA == the basis the
    engine already used; and
  * thin suburbs reach into the 5 km ring purely to satisfy the statutory minimum.

SELECTION RULE (sold limb)
--------------------------
A comparable QUALIFIES when it is: listing_status == "sold"; sold within the last
`window_months`; same property-type group as the subject; bedrooms within ±1;
HAS coordinates; and is within `radius_km` of the subject. Suburb-first — only
reach into the cross-suburb 5 km ring when the home suburb yields < `min_comps`.
If still short, `compliant=False` and the s 215 written-explanation fallback flags.

Source: ONLY the fresh, coordinate-bearing Gold_Coast sold collections. The legacy
Target_Market_Sold_Last_12_Months source is stale (Feb 2026) and carries no
coordinates, so it cannot support a 6-month / 5 km test and is never used here.

CURRENT-ON-MARKET LIMB (industry standard)
------------------------------------------
The OFT/REIQ "Sales and Marketing" training manual (the industry articulation of
the s 215 CMA duty) adds that the CMA "should also include information on at least
three properties currently on the market that are comparable". Note: NO radius and
NO time window attach to this limb — Schedule 2's 6-month / 5 km qualifiers apply
ONLY to the sold limb. Current listings just have to be "comparable".

We do NOT re-select these. They are sourced from the SAME competitor matcher that
powers the Competition map (`comparables.closest_active`) — single source of truth —
mapped to a compact CMA shape by `current_listings_from_comparables()` and injected
into this payload by the resolver (so the archived CMA of record carries both limbs).
These are ASKING-PRICE GUIDES, display-only — never fed into the valuation figure
(asking prices are not transaction prices).

See: 09_Appraisals/your-home-minisite-compliance-audit-2026-06-21.md
     00_Run_Commands/Industry_Governance/Sales and Marketing - Part 1 (1).pdf (§3.5)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pymongo.database import Database

from scripts.property_reports.competitor_matcher import (
    CATCHMENT_CENTROIDS,
    PROPERTY_TYPE_GROUPS,
    _doc_latlng,
    _haversine_km,
    _parse_price,
    _property_type_group,
    _to_int,
)

logger = logging.getLogger(__name__)

# Statutory parameters (PO Act 2014 Sch 2). Kept as named constants so the rule
# is auditable and a single edit changes the whole pipeline.
WINDOW_MONTHS = 6
RADIUS_KM = 5.0
MIN_COMPS = 3
TARGET_COMPS = 8
BED_BAND = 1          # "similar standard" proxy — bedrooms within ±1
VALIDITY_DAYS = 90    # how long the CMA is presented as current (audit item E)
MIN_CURRENT = 3       # industry standard: "at least three" current-on-market comps
TARGET_CURRENT = 6    # how many current listings to surface (matches the competitor feed)

_PROJECTION = {
    "address": 1, "street_address": 1, "suburb": 1,
    "sale_price": 1, "sold_price": 1, "price": 1,
    "sale_date": 1, "sold_date": 1,
    "bedrooms": 1, "bathrooms": 1,
    "land_size_sqm": 1, "lot_size_sqm": 1,
    "total_floor_area": 1, "floor_area_sqm": 1, "internal_living_area_sqm": 1,
    "property_type": 1, "classified_property_type": 1,
    "geocoded_coordinates": 1, "LATITUDE": 1, "LONGITUDE": 1,
    "listing_status": 1,
}


def _sold_date(doc: Dict[str, Any]) -> Optional[datetime]:
    """Parse a sold date (ISO string or epoch) to a datetime; None if absent."""
    for field in ("sold_date", "sale_date"):
        v = doc.get(field)
        if not v:
            continue
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v[:10])
            except (ValueError, TypeError):
                pass
        if isinstance(v, (int, float)) and v > 1_000_000_000:
            try:
                return datetime.fromtimestamp(v / 1000 if v > 1e12 else v)
            except (ValueError, OSError):
                pass
    return None


def _beds(doc: Dict[str, Any]) -> Optional[int]:
    return _to_int(doc.get("bedrooms"))


def _land(doc: Dict[str, Any]) -> Optional[int]:
    return _to_int(doc.get("land_size_sqm") or doc.get("lot_size_sqm"))


def _internal(doc: Dict[str, Any]) -> Optional[int]:
    return _to_int(
        doc.get("internal_living_area_sqm")
        or doc.get("floor_area_sqm")
        or doc.get("total_floor_area")
    )


def _clean_address(doc: Dict[str, Any]) -> str:
    addr = (doc.get("address") or doc.get("street_address") or "").strip()
    addr = re.sub(r",?\s*(QLD|VIC|NSW|ACT|NT|SA|TAS|WA)\s*\d{4}\s*$", "", addr, flags=re.I)
    addr = re.sub(r"\s{2,}", " ", addr).rstrip(",").strip()
    return addr or "Address withheld"


def _ring_suburbs(suburb_key: str, subject_ll: Optional[Tuple[float, float]]) -> List[str]:
    """Catchment suburbs to scan for the 5 km ring, nearest-centroid first,
    excluding the home suburb. Limited to the southern-GC catchment we cover."""
    others = [s for s in CATCHMENT_CENTROIDS if s != suburb_key]
    anchor = subject_ll or CATCHMENT_CENTROIDS.get(suburb_key)
    if anchor:
        others.sort(key=lambda s: _haversine_km(anchor, CATCHMENT_CENTROIDS[s]))
    return others


def _qualify(
    doc: Dict[str, Any],
    subject_ll: Optional[Tuple[float, float]],
    subj_group: Optional[str],
    subj_beds: Optional[int],
    window_start: datetime,
    radius_km: float,
) -> Optional[Dict[str, Any]]:
    """Return a normalised comparable dict if `doc` satisfies the statutory test,
    else None. Requires coordinates + a measurable distance ≤ radius_km."""
    sd = _sold_date(doc)
    if not sd or sd < window_start:
        return None
    price = _parse_price(doc.get("sale_price"), doc.get("sold_price"), doc.get("price"))
    if not price:
        return None
    # Same property-type group (house-group never mixes with unit-group).
    grp = _property_type_group(doc)
    if subj_group is not None and grp is not None and grp != subj_group:
        return None
    # Similar standard proxy — bedrooms within band.
    b = _beds(doc)
    if subj_beds is not None and b is not None and abs(b - subj_beds) > BED_BAND:
        return None
    # Distance — must be measurable and within radius to count statutorily.
    ll = _doc_latlng(doc)
    if not (ll and subject_ll):
        return None
    dist = _haversine_km(subject_ll, ll)
    if dist > radius_km:
        return None
    return {
        "address": _clean_address(doc),
        "suburb": (doc.get("suburb") or "").strip(),
        "sold_price": int(price),
        "sold_date": sd.strftime("%Y-%m-%d"),
        "distance_km": round(dist, 2),
        "bedrooms": b,
        "bathrooms": _to_int(doc.get("bathrooms")),
        "land_sqm": _land(doc),
        "internal_sqm": _internal(doc),
        "property_type": (doc.get("classified_property_type") or doc.get("property_type") or "").strip(),
        "_recency_days": None,  # filled below
        "_sd": sd,
    }


def _rank_key(subj_beds: Optional[int]):
    """Display ranking: nearer + more recent first; bed match breaks ties."""
    def key(c: Dict[str, Any]):
        bed_gap = abs((c.get("bedrooms") or 0) - subj_beds) if subj_beds and c.get("bedrooms") else 9
        return (round(c["distance_km"], 1), bed_gap, -c["_sd"].timestamp())
    return key


def current_listings_from_comparables(
    comparables: Optional[Dict[str, Any]],
    limit: int = TARGET_CURRENT,
) -> List[Dict[str, Any]]:
    """Map the competitor matcher's `closest_active` feed onto the compact CMA
    current-on-market shape. Single source of truth: these are the SAME ranked
    listings shown on the Competition map — no re-selection, no divergence.

    Asking-price guides are kept verbatim (e.g. "Offers Over $1,595,000",
    "Contact agent", "Auction") — never coerced into a single number for the
    figure. `price_mid` carries the matcher's numeric midpoint where one exists,
    for display ordering only.
    """
    if not isinstance(comparables, dict):
        return []
    rows = comparables.get("closest_active") or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        addr = (r.get("address") or "").strip()
        if not addr:
            continue
        out.append({
            "address": addr,
            "suburb": (r.get("suburb") or "").strip(),
            "price_guide": r.get("price"),            # raw agent guide, verbatim
            "price_mid": r.get("price_mid"),          # numeric midpoint or None (display only)
            "sale_method": r.get("sale_method_label") or r.get("sale_method"),
            "bedrooms": r.get("bedrooms"),
            "bathrooms": r.get("bathrooms"),
            "distance_km": r.get("distance_km"),
            "days_on_market": r.get("days_on_market"),
        })
        if len(out) >= limit:
            break
    return out


def build_statutory_cma(
    db: Database,
    subject_doc: Dict[str, Any],
    suburb_key: str,
    today: Optional[datetime] = None,
    *,
    radius_km: float = RADIUS_KM,
    window_months: int = WINDOW_MONTHS,
    min_comps: int = MIN_COMPS,
    target: int = TARGET_COMPS,
) -> Dict[str, Any]:
    """Build the s 215 / Sch 2 statutory CMA for a subject.

    Returns a dict shaped for property_reports.valuation.statutory_cma and the
    mini-site StatutoryCMA component. `compliant` is True when ≥ min_comps
    qualifying sales were found within the window/radius; otherwise `fallback`
    is set to "written_explanation" (the s 215 alternative path)."""
    today = today or datetime.utcnow()
    window_start = today - timedelta(days=int(window_months * 30.44))
    subject_ll = _doc_latlng(subject_doc) or CATCHMENT_CENTROIDS.get(suburb_key)
    subj_group = _property_type_group(subject_doc)
    subj_beds = _beds(subject_doc)
    subj_id = subject_doc.get("_id")

    def _scan(suburb: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            cursor = db[suburb].find({"listing_status": "sold"}, _PROJECTION)
        except Exception as e:  # collection may not exist / RU pressure
            logger.debug(f"  statutory_cma scan failed for {suburb}: {e}")
            return out
        for doc in cursor:
            if subj_id is not None and doc.get("_id") == subj_id:
                continue
            q = _qualify(doc, subject_ll, subj_group, subj_beds, window_start, radius_km)
            if q:
                out.append(q)
        return out

    # 1) Suburb-first.
    in_suburb = _scan(suburb_key) if suburb_key else []
    comps = list(in_suburb)
    used_ring = False

    # 2) 5 km cross-suburb ring — only when the home suburb is short.
    if len(comps) < max(min_comps, target):
        seen = {(c["address"], c["sold_price"]) for c in comps}
        for nb in _ring_suburbs(suburb_key, subject_ll):
            if len([c for c in comps if c["distance_km"] <= radius_km]) >= max(min_comps, target):
                break
            for c in _scan(nb):
                key = (c["address"], c["sold_price"])
                if key in seen:
                    continue
                seen.add(key)
                comps.append(c)
                used_ring = True

    # Fill recency + rank for display.
    for c in comps:
        c["_recency_days"] = (today - c["_sd"]).days
    comps.sort(key=_rank_key(subj_beds))
    display = comps[:target]
    for c in comps:
        c.pop("_sd", None)

    n_total = len(comps)
    n_suburb = len(in_suburb)
    compliant = n_total >= min_comps
    as_at = today.strftime("%Y-%m-%d")
    valid_until = (today + timedelta(days=VALIDITY_DAYS)).strftime("%Y-%m-%d")

    if compliant:
        basis = "ring" if (used_ring and n_suburb < min_comps) else "suburb"
        statement = (
            f"This comparative market analysis compares your home with {n_total} "
            f"properties sold within the previous {window_months} months and within "
            f"{int(radius_km)} km, of a similar type and size — meeting the requirements "
            f"of the Property Occupations Act 2014 (Qld). Prepared as at {as_at}."
        )
    else:
        basis = "insufficient"
        statement = (
            f"Fewer than {min_comps} comparable sales from the previous {window_months} "
            f"months within {int(radius_km)} km were available for a property of this type. "
            f"In line with s 215 of the Property Occupations Act 2014 (Qld), the valuation "
            f"is instead supported by a written explanation of how market value was "
            f"determined (see the methodology below). Prepared as at {as_at}."
        )

    return {
        "as_at": as_at,
        "valid_until": valid_until,
        "window_months": window_months,
        "radius_km": int(radius_km),
        "min_comps": min_comps,
        "compliant": compliant,
        "basis": basis,
        "used_ring": used_ring,
        "n_within_suburb": n_suburb,
        "n_total": n_total,
        "comparables": display,
        # Current-on-market limb — injected by the resolver from the competitor
        # feed (single source of truth). Seeded empty so the field always exists
        # and the archived payload is self-describing even before the feed runs.
        "current_listings": [],
        "n_current": 0,
        "fallback": None if compliant else "written_explanation",
        "statement": statement,
        "source": "Fields sold-sales record (Gold_Coast), exact unrounded prices.",
    }
