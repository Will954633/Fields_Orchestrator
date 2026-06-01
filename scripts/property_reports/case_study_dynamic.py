"""
case_study_dynamic — CS0, the per-seller "a home like yours, recently sold" card.

The ONLY case-study card that runs unattended for every report, so it is built
to two hard gates rather than best-effort:

  (1) RELEVANCE gate — only renders if the best SOLD match is in the close tier
      (score <= competitor_matcher.CLOSE_MATCH_THRESHOLD) found at aperture
      ring <= 2. A home that only appears at the loosest ring is not "a home
      like yours" → return None (the frontend hides the card).

  (2) FACT gate — every printed fact must agree with the Domain property-profile
      timeline. Sale price + method must match the timeline's most-recent sold
      event; if that event predates the stored sale (the stale-timeline trap),
      the candidate is rejected. DOM is taken ONLY from the timeline (never the
      derived top-level days_on_market, which disagrees ~25% of the time). Any
      fact that can't be verified is omitted; if price+method can't be verified,
      the candidate is skipped for the next-best one.

Design corrections proven in 11_House_Mini_Site/cs0_prototype.py (2026-06-01):
  - recency comes from the timeline's newest is_sold event, NOT sale_date/
    sold_date (those frequently hold a PRIOR sale).
  - sold price parses from the timeline event price / listing_price / sale_price
    ("SOLD - $X"), NOT `price` (null on sold docs).

Returns a `case_studies.dynamic` dict ready to $set, or None to hide CS0.
No price-revision claims are ever made — the data has no intra-campaign
asking-price-cut trail.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional, Tuple

from pymongo.database import Database

from scripts.property_reports import competitor_matcher as cm

logger = logging.getLogger(__name__)

WINDOW_MONTHS = 12
MAX_RELEVANT_RING = 2          # ring 0-2 only; ring 3 is too loose to be "like yours"
DATE_TOLERANCE_DAYS = 21       # contract vs settlement gap we accept as "same sale"
# CS0 relevance band. The matcher's CLOSE_MATCH_THRESHOLD (0.22) is its display
# threshold for the active-listing map; for a rare home (e.g. a 6-bedroom) the
# genuinely tellable comp can sit just outside it. 0.33 ≈ ring-2's "wider
# neighbourhood within 20% on price" intent — still honestly "a home like
# yours" (same bedroom band, recent, one suburb over), and the difference_line
# states every difference plainly. A home with NO match this close is rare
# enough that CS0 hides rather than overclaim.
RELEVANCE_MAX_SCORE = 0.33

# Candidate projection — the matcher's set plus the sold/timeline fields CS0 needs.
_SOLD_PROJ = dict(
    cm._CANDIDATE_PROJECTION,
    scraped_data_v2=1, sale_price=1, sale_date=1, sold_date=1,
    sale_method=1, domain_valuation_at_listing=1,
)


def _newest_sold_event(doc: Dict[str, Any]) -> Tuple[Optional[dt.date], Optional[int], Optional[Dict[str, Any]]]:
    """The current sale = most-recent is_sold event on the Domain timeline.
    Returns (date, price, event) or (None, None, None)."""
    v2 = doc.get("scraped_data_v2") or {}
    tl = v2.get("timeline") if isinstance(v2, dict) else None
    if not tl:
        return None, None, None
    sales = [
        e for e in tl
        if isinstance(e, dict) and e.get("category") == "Sale"
        and e.get("is_sold") and e.get("event_date")
    ]
    if not sales:
        return None, None, None
    sales.sort(key=lambda e: str(e.get("event_date")), reverse=True)
    top = sales[0]
    try:
        d0 = dt.date.fromisoformat(str(top["event_date"])[:10])
    except (ValueError, TypeError):
        d0 = None
    return d0, cm._parse_price(top.get("event_price")), top


def _parse_iso(v: Any) -> Optional[dt.date]:
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def _gather_sold(
    db: Database, subject: Dict[str, Any], suburbs: List[str],
    price_band: float, bed_band: int, cutoff: dt.date,
) -> List[Dict[str, Any]]:
    """SOLD substitutes across `suburbs` clearing the hard filters: same
    property-type group, sold within the window (by TIMELINE date), price in
    band. Recency + price both come from the timeline, not the stale fields."""
    out: List[Dict[str, Any]] = []
    anchor = subject["price"]
    lo, hi = anchor * (1 - price_band), anchor * (1 + price_band)
    bed = subject["bedrooms"]
    try:
        cols = set(db.list_collection_names())
    except Exception:
        cols = set()
    for sub in suburbs:
        if sub not in cols:
            continue
        query: Dict[str, Any] = {"listing_status": "sold"}
        if bed is not None:
            query["bedrooms"] = {"$in": list(range(bed - bed_band, bed + bed_band + 1))}
        try:
            cursor = db[sub].find(query, _SOLD_PROJ)
        except Exception as e:
            logger.debug(f"  cs0 gather failed on {sub}: {e}")
            continue
        for d in cursor:
            d["_suburb_key"] = sub
            if cm._property_type_group(d) != subject["group"]:
                continue
            tl_date, tl_price, _ = _newest_sold_event(d)
            rd = tl_date or _parse_iso(d.get("sale_date") or d.get("sold_date"))
            if rd is None or rd < cutoff:
                continue
            price = tl_price or cm._parse_price(d.get("listing_price"), d.get("sale_price"))
            if not price or not (lo <= price <= hi):
                continue
            d["_price"] = price
            out.append(d)
    return out


def _verify_facts(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Apply the FACT gate. Returns the dict of verified facts, or None if the
    candidate's core facts (price + method) can't be trusted."""
    ev_date, ev_price, ev = _newest_sold_event(doc)
    stored_price = cm._parse_price(doc.get("listing_price"), doc.get("sale_price"))
    stored_method = (doc.get("sale_method") or "").strip().lower()
    facts: Dict[str, Any] = {}

    if ev:
        stored_date = _parse_iso(doc.get("sold_date") or doc.get("sale_date"))
        # Stale-timeline trap: the timeline's newest sold event must describe
        # THIS sale (recent + matching price), else the timeline predates it.
        gap_days = abs((stored_date - ev_date).days) if (stored_date and ev_date) else 9999
        price_ok = ev_price and stored_price and abs(ev_price - stored_price) <= 1000
        if gap_days <= DATE_TOLERANCE_DAYS and price_ok:
            facts["sale_price"] = ev_price
            facts["method"] = _normalise_method(ev.get("price_description"))
            facts["sale_date"] = str(ev.get("event_date"))[:10]
            if isinstance(ev.get("days_on_market"), (int, float)):
                facts["days_on_market"] = int(ev["days_on_market"])
            facts["_source"] = "timeline"
            return facts
        # Timeline exists but doesn't describe this sale → reject the candidate.
        logger.debug(
            f"  cs0 fact-gate reject (stale timeline): gap={gap_days}d "
            f"tl_price={ev_price} stored={stored_price}"
        )
        return None

    # No timeline: fall back to stored fields for price + method ONLY.
    # No DOM (we will not derive one), no Domain-vs-reality without a timeline.
    if stored_price:
        facts["sale_price"] = stored_price
        if stored_method:
            facts["method"] = _normalise_method(stored_method)
        facts["sale_date"] = str(doc.get("sold_date") or doc.get("sale_date") or "")[:10] or None
        facts["_source"] = "stored"
        return facts
    return None


def _normalise_method(raw: Any) -> Optional[str]:
    s = (str(raw) if raw is not None else "").strip().lower()
    if not s:
        return None
    if "auction" in s:
        return "auction"
    if "private" in s or "treaty" in s:
        return "private treaty"
    return s


def _verification_rank(facts: Dict[str, Any]) -> int:
    """Higher = richer/more tellable. Prefer a full timeline (incl. DOM)."""
    score = 0
    if "days_on_market" in facts:
        score += 4
    if facts.get("_source") == "timeline":
        score += 2
    if "sale_date" in facts:
        score += 1
    return score


def resolve_dynamic_case_study(
    subject_doc: Dict[str, Any],
    db: Database,
    features_basic: Optional[Dict[str, Any]] = None,
    *,
    price_anchor: Optional[int] = None,
    catchment: Optional[List[str]] = None,
    today: Optional[dt.date] = None,
) -> Optional[Dict[str, Any]]:
    """CS0 resolver. Returns the `case_studies.dynamic` dict, or None to hide."""
    subject = cm._subject_profile(subject_doc, features_basic, price_anchor)
    if not subject["bedrooms"] or not subject["price"]:
        logger.info("  cs0: subject missing bedrooms or price anchor — hiding CS0")
        return None

    own = (subject_doc.get("suburb_key")
           or subject_doc.get("_suburb_key")
           or (subject_doc.get("suburb") or "").lower().replace(" ", "_"))
    catch = catchment or cm.DEFAULT_CATCHMENT
    subject["point"] = subject["latlng"] or cm.CATCHMENT_CENTROIDS.get(own)
    today = today or dt.date.today()
    cutoff = today.replace(year=today.year - 1)
    subj_id = subject_doc.get("_id")

    # Walk aperture rings; stop at the first ring (<= MAX_RELEVANT_RING) that
    # yields a close-tier match. A match only at ring 3 fails the relevance gate.
    best_close: List[Tuple[float, Dict[str, Any]]] = []
    chosen_ring: Optional[int] = None
    seen: set = set()
    for idx, ring in enumerate(cm.APERTURE_RINGS):
        if idx > MAX_RELEVANT_RING:
            break
        suburbs = cm._geo_for_ring(ring["geo"], own, catch)
        found = _gather_sold(db, subject, suburbs, ring["price"], ring["beds"], cutoff)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for c in found:
            if c["_id"] == subj_id or c["_id"] in seen:
                continue
            seen.add(c["_id"])
            scored.append((cm._score(subject, c), c))
        scored.sort(key=lambda x: x[0])
        # Relevance band + must have a real address (skip scrape-artefact docs
        # with no address — they can't be shown or verified by the seller).
        close = [
            (s, c) for s, c in scored
            if s <= RELEVANCE_MAX_SCORE and (c.get("address") or c.get("street_address"))
        ]
        if close:
            best_close = close
            chosen_ring = idx
            break

    if not best_close:
        logger.info("  cs0: no relevant sold match (score <= %.2f) at ring <= %d — hiding CS0",
                    RELEVANCE_MAX_SCORE, MAX_RELEVANT_RING)
        return None

    # Among close-tier matches, pick the one that BOTH verifies and tells the
    # richest story (full timeline incl. DOM > price+method+date > price+method).
    verified_pool: List[Tuple[int, float, Dict[str, Any], Dict[str, Any]]] = []
    for score, c in best_close[:12]:
        full = db[c["_suburb_key"]].find_one({"_id": c["_id"]}) or c
        full["_suburb_key"] = c["_suburb_key"]
        full["_price"] = c["_price"]
        facts = _verify_facts(full)
        if facts and facts.get("sale_price"):
            verified_pool.append((_verification_rank(facts), score, full, facts))

    if not verified_pool:
        logger.info("  cs0: close-tier matches found but none passed the fact gate — hiding CS0")
        return None

    # Best = richest verification, then closest score.
    verified_pool.sort(key=lambda t: (-t[0], t[1]))
    _, score, doc, facts = verified_pool[0]

    # Domain-vs-reality (only when we have a timeline-verified sale + estimate).
    domain_block = None
    dv = doc.get("domain_valuation_at_listing") or {}
    mid = dv.get("mid") if isinstance(dv, dict) else None
    if facts.get("_source") == "timeline" and mid and facts.get("sale_price"):
        diff_pct = (mid - facts["sale_price"]) / facts["sale_price"] * 100
        if abs(diff_pct) >= 3:
            domain_block = {
                "estimate_at_listing": int(mid),
                "grade": dv.get("accuracy"),
                "diff_pct": round(diff_pct, 1),
                "direction": "above" if diff_pct > 0 else "below",
            }

    suburb_disp = (doc.get("suburb") or doc.get("_suburb_key", "").replace("_", " ")).title()
    out: Dict[str, Any] = {
        "address": doc.get("address") or doc.get("street_address"),
        "suburb": suburb_disp,
        "bedrooms": cm._to_int(doc.get("bedrooms")),
        "bathrooms": cm._to_int(doc.get("bathrooms")),
        "property_type": doc.get("property_type"),
        "land_size_sqm": cm._to_int(doc.get("lot_size_sqm") or doc.get("land_size_sqm")),
        "sale_price": facts["sale_price"],
        "method": facts.get("method"),
        "sale_date": facts.get("sale_date"),
        "days_on_market": facts.get("days_on_market"),   # None if not timeline-verified
        "difference_line": cm._difference_line(subject, doc),
        "domain_vs_reality": domain_block,
        "match_score": round(score, 3),
        "aperture_ring": chosen_ring,
        "fact_source": facts.get("_source"),
        "resolved_at": today.isoformat(),
    }
    logger.info(
        "  cs0: rendered %s (score %.3f, ring %d, DOM=%s, source=%s)",
        out["address"], score, chosen_ring, out["days_on_market"], out["fact_source"],
    )
    return out
