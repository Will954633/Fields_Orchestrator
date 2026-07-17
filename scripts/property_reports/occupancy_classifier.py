"""
occupancy_classifier — infer owner-occupier vs investor for a property_reports doc.

Why this exists
---------------
The Analyse Your Home funnel ends in a *physically posted* appraisal to the
address. If the property is tenanted, the person who entered the address is the
landlord/investor, NOT the resident — and we must never post owner-facing
appraisal material to their tenants. This module produces the occupancy signal
that gates physical dispatch (`print_appraisal.dispatch_hold`).

Signal source
-------------
Domain property-profile timeline (sale + rental listing events). The decisive
rule: a **Rental** listing dated *after* the most-recent **Sale (sold)** means
the current owner bought the home and then put it on the rental market — an
investor who tenants the property. Owner-occupier = the most recent major event
is the purchase, with no subsequent rental listing.

The timeline is pulled fresh via Bright Data (Domain is Akamai-walled) so the
classification reflects current tenancy, and the refreshed timeline + rental
estimate are written back to the Gold_Coast property document (useful to
valuation/comps too).

Default-safe: anything not positively resolved to owner_occupier keeps the
dispatch hold ON.
"""
from __future__ import annotations

import re
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger("occupancy_classifier")

# A rental listing within this many days *after* a purchase is a strong
# buy-to-let signal (high confidence). Beyond it, still investor, medium.
_STRONG_RENT_AFTER_BUY_DAYS = 730  # ~2 years


# --------------------------------------------------------------------------- #
# Timeline extraction
# --------------------------------------------------------------------------- #
def _to_date(v: Any) -> Optional[str]:
    """Normalise an event date to 'YYYY-MM-DD' (or None)."""
    if not v:
        return None
    s = str(v)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def extract_timeline_from_html(html: str) -> List[Dict[str, Any]]:
    """Parse the Domain property-profile __NEXT_DATA__ into normalised events.

    Returns a list of {date, category, is_sold, price, days_on_market, agency},
    newest-first. Empty list if nothing parseable.
    """
    if not html:
        return []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    apollo = (
        data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})
    )
    raw: List[Dict[str, Any]] = []
    rental_estimate = None
    for key, val in apollo.items():
        if not (key.startswith("Property:") and isinstance(val, dict)):
            continue
        if isinstance(val.get("timeline"), list) and val["timeline"]:
            raw = val["timeline"]
        re_obj = val.get("rentalEstimate")
        if isinstance(re_obj, dict):
            rental_estimate = {
                "weekly_rent": re_obj.get("weeklyRentEstimate"),
                "yield": re_obj.get("percentYieldRentEstimate"),
            }
        if raw:
            break

    events: List[Dict[str, Any]] = []
    for e in raw:
        cat = e.get("category")
        if cat not in ("Sale", "Rental"):
            continue
        meta = e.get("saleMetadata") or {}
        events.append(
            {
                "date": _to_date(e.get("eventDate")),
                "category": cat,
                "is_sold": bool(meta.get("isSold")) if cat == "Sale" else None,
                "price": e.get("eventPrice"),
                "days_on_market": e.get("daysOnMarket"),
                "agency": (e.get("agency") or {}).get("name"),
                "is_major_event": e.get("isMajorEvent"),
            }
        )
    events = [e for e in events if e["date"]]
    events.sort(key=lambda e: e["date"], reverse=True)
    # stash rental estimate on the first event's carrier via a side channel
    if events and rental_estimate:
        events[0]["_rental_estimate"] = rental_estimate
    return events


def normalise_stored_timeline(gc_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fallback: normalise an already-stored timeline from the Gold_Coast doc
    (scraped_data.property_timeline or scraped_data_v2.timeline)."""
    scraped = gc_doc.get("scraped_data") or {}
    tl = scraped.get("property_timeline")
    events: List[Dict[str, Any]] = []
    if isinstance(tl, list) and tl:
        for e in tl:
            cat = e.get("category")
            if cat not in ("Sale", "Rental"):
                continue
            events.append(
                {
                    "date": _to_date(e.get("date")),
                    "category": cat,
                    "is_sold": e.get("is_sold") if cat == "Sale" else None,
                    "price": e.get("price"),
                    "days_on_market": e.get("days_on_market"),
                    "agency": e.get("agency_name"),
                }
            )
    else:
        tl2 = (gc_doc.get("scraped_data_v2") or {}).get("timeline")
        if isinstance(tl2, list):
            for e in tl2:
                cat = e.get("category")
                if cat not in ("Sale", "Rental"):
                    continue
                events.append(
                    {
                        "date": _to_date(e.get("event_date")),
                        "category": cat,
                        "is_sold": e.get("is_sold") if cat == "Sale" else None,
                        "price": e.get("event_price"),
                        "days_on_market": e.get("days_on_market"),
                        "agency": (e.get("agency") or {}).get("name")
                        if isinstance(e.get("agency"), dict)
                        else None,
                    }
                )
    events = [e for e in events if e["date"]]
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


# --------------------------------------------------------------------------- #
# Classification (pure)
# --------------------------------------------------------------------------- #
def _days_between(later: str, earlier: str) -> Optional[int]:
    try:
        return (
            datetime.strptime(later, "%Y-%m-%d")
            - datetime.strptime(earlier, "%Y-%m-%d")
        ).days
    except Exception:
        return None


def classify_from_timeline(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Owner-occupier vs investor from a normalised, newest-first timeline.

    Returns an occupancy dict. Default-safe: only returns owner_occupier when a
    purchase is the latest signal with no subsequent rental.
    """
    now = datetime.now(timezone.utc).isoformat()

    def result(type_, owner_occupier, confidence, signals, evidence=None):
        return {
            "type": type_,
            "owner_occupier": owner_occupier,
            "confidence": confidence,
            "source": "timeline",
            "signals": signals,
            "evidence": evidence or {},
            "classified_at": now,
        }

    if not events:
        return result("unknown", None, "low", ["no timeline data available"])

    sold = [e for e in events if e["category"] == "Sale" and e.get("is_sold")]
    rentals = [e for e in events if e["category"] == "Rental"]
    last_sale = sold[0] if sold else None  # events are newest-first

    if last_sale:
        rentals_after = [r for r in rentals if r["date"] > last_sale["date"]]
        if rentals_after:
            most_recent_rental = rentals_after[0]
            gap = _days_between(most_recent_rental["date"], last_sale["date"])
            confidence = (
                "high"
                if gap is not None and gap <= _STRONG_RENT_AFTER_BUY_DAYS
                else "medium"
            )
            price_str = f"${last_sale['price']:,}" if last_sale.get("price") else "undisclosed"
            signals = [
                f"Sold {last_sale['date']} for {price_str}, then listed for rent "
                f"{most_recent_rental['date']}"
                + (f" ({gap} days later)" if gap is not None else "")
                + " — owner rented the property out.",
            ]
            return result(
                "investor",
                False,
                confidence,
                signals,
                {
                    "last_sale_date": last_sale["date"],
                    "last_sale_price": last_sale.get("price"),
                    "rental_after_sale_date": most_recent_rental["date"],
                    "rental_after_sale_gap_days": gap,
                },
            )
        # Purchase is the most recent major event, no rental since → owner-occupier
        return result(
            "owner_occupier",
            True,
            "medium",
            [
                f"Purchased {last_sale['date']} with no rental listing since — "
                "consistent with owner-occupier.",
            ],
            {"last_sale_date": last_sale["date"], "last_sale_price": last_sale.get("price")},
        )

    # No recorded sale-sold event
    if rentals:
        return result(
            "investor",
            False,
            "medium",
            [
                f"Rental listing history ({len(rentals)} events, most recent "
                f"{rentals[0]['date']}) with no recorded owner-occupier purchase.",
            ],
            {"rental_events": len(rentals), "most_recent_rental": rentals[0]["date"]},
        )

    return result("unknown", None, "low", ["timeline present but no sale/rental events"])


# --------------------------------------------------------------------------- #
# Orchestration: refresh + classify a report
# --------------------------------------------------------------------------- #
def _find_gc_doc(report_doc: Dict[str, Any], gc_db) -> Optional[Dict[str, Any]]:
    from bson import ObjectId

    suburb_key = (report_doc.get("suburb_key") or "").strip().lower()
    coll = gc_db[suburb_key] if suburb_key else None
    pid = report_doc.get("property_id")
    if coll is not None and pid:
        try:
            d = coll.find_one({"_id": ObjectId(str(pid))})
            if d:
                return d
        except Exception:
            pass
    if coll is not None:
        slug = report_doc.get("slug")
        addr = report_doc.get("address", "")
        street = re.escape(addr.split(",")[0]) if addr else None
        q = {"$or": []}
        if slug:
            q["$or"].append({"url_slug": slug})
        if street:
            q["$or"].append({"display_address": {"$regex": street, "$options": "i"}})
            q["$or"].append({"address": {"$regex": street, "$options": "i"}})
        if q["$or"]:
            return coll.find_one(q)
    return None


def _profile_url(gc_doc: Dict[str, Any]) -> Optional[str]:
    if gc_doc.get("scraped_url_v2"):
        return gc_doc["scraped_url_v2"]
    slug = gc_doc.get("url_slug")
    pc = gc_doc.get("POSTCODE") or gc_doc.get("display_postcode")
    if slug and pc:
        return f"https://www.domain.com.au/property-profile/{slug}-qld-{pc}"
    return None


def refresh_and_classify(
    report_doc: Dict[str, Any],
    gc_db,
    fetch_fresh: bool = True,
) -> Dict[str, Any]:
    """Pull a fresh Domain timeline for the report's property (Bright Data),
    write it back to the Gold_Coast doc, then classify occupancy.

    Falls back to the stored timeline if the fresh fetch fails. Never raises —
    on total failure returns an 'unknown' occupancy (which keeps dispatch held).
    """
    gc_doc = _find_gc_doc(report_doc, gc_db)
    if not gc_doc:
        logger.warning("occupancy: no Gold_Coast doc for %s", report_doc.get("slug"))
        occ = classify_from_timeline([])
        occ["signals"] = ["property record not found — cannot classify"]
        return occ

    events: List[Dict[str, Any]] = []
    fresh_ok = False
    rental_estimate = None

    if fetch_fresh:
        url = _profile_url(gc_doc)
        if url:
            try:
                import sys

                sys.path.insert(0, "/home/fields")
                from shared.domain_fetch import fetch_html

                html = fetch_html(url)
                events = extract_timeline_from_html(html)
                if events:
                    fresh_ok = True
                    rental_estimate = events[0].pop("_rental_estimate", None)
            except Exception as e:  # noqa: BLE001
                logger.warning("occupancy: fresh fetch failed for %s: %s", url, e)

    if not events:
        events = normalise_stored_timeline(gc_doc)

    occ = classify_from_timeline(events)
    occ["timeline_source"] = "fresh_brightdata" if fresh_ok else "stored_fallback"
    occ["timeline_event_count"] = len(events)

    # Write the refreshed timeline back to the Gold_Coast doc (best-effort).
    if fresh_ok:
        now = datetime.utcnow()
        set_doc = {
            "occupancy_timeline": events,
            "occupancy_timeline_refreshed_at": now,
        }
        if rental_estimate and rental_estimate.get("weekly_rent"):
            set_doc["rental_estimate_fresh"] = rental_estimate
            occ["evidence"]["rental_estimate_weekly"] = rental_estimate["weekly_rent"]
        try:
            suburb_key = (report_doc.get("suburb_key") or "").strip().lower()
            gc_db[suburb_key].update_one({"_id": gc_doc["_id"]}, {"$set": set_doc})
        except Exception as e:  # noqa: BLE001
            logger.warning("occupancy: timeline writeback failed: %s", e)

    return occ


# --------------------------------------------------------------------------- #
# Report-doc application (occupancy block + dispatch interlock)
# --------------------------------------------------------------------------- #
def occupancy_updates(occ: Dict[str, Any]) -> Dict[str, Any]:
    """Build the $set payload for a property_reports doc from an occupancy dict.

    Releases the physical-dispatch hold ONLY when owner_occupier is True.
    Investor / unknown → hold stays on with a reason.
    """
    hold = occ.get("owner_occupier") is not True
    if occ.get("type") == "investor":
        reason = "occupancy_investor_tenanted"
    elif occ.get("owner_occupier") is True:
        reason = None
    else:
        reason = "occupancy_unconfirmed"
    return {
        "occupancy": occ,
        "print_appraisal.dispatch_hold": hold,
        "print_appraisal.dispatch_hold_reason": reason,
        "print_appraisal.dispatch_hold_set_at": datetime.utcnow(),
    }
