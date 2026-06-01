"""comparable_feed.py — first-visit baseline + durable change log for the
"Your Home" tab activity feed, derived from the competitor_matcher engine
output already stored on each report doc.

Source of truth (written by the slot resolver):
    slots.competitor_map.competitors  — ranked active substitutes (distanceKm,
                                         priceText, daysOnMarket, combinatorialMatch)
    slots.competitor_map.aperture_*    — adaptive widening (honest "we widened" copy)
    slots.best_comp                    — single closest sold comparable
    slots.recent_comps                 — recent comparable sales

This module READS that output and diffs it over time into a durable change log.
No comparable matching is re-derived here — one engine, not two. Imported by
both scripts/refresh_property_reports.py (nightly, all reports) and
scripts/property_reports/slot_resolver.py (inline on resolve, so the feed is
live within seconds of submission).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# A freshly-seen listing / sale still counts as "new activity" this many days.
COMPARABLE_WINDOW_DAYS = 30
# Curiosity-drive guarantee window — aim to surface >=1 update per N days.
GUARANTEE_DAYS = 7
# Rolling caps on the durable event log.
EVENT_LOG_MAX = 250
EVENT_LOG_MAX_DAYS = 120

_PRICE_PATTERNS = [
    re.compile(r"\$([\d,]+(?:\.\d+)?)\s*(?:m|million)\b", re.I),
    re.compile(r"\$([\d,]+(?:\.\d+)?)k\b", re.I),
    re.compile(r"\$([\d,]+)"),
]


def parse_price(s: Any) -> float | None:
    """Midpoint of a price string (handles ranges) or None."""
    if not s or not isinstance(s, str):
        return None
    values: list[float] = []
    for part in re.split(r"\s*[-–—]\s*", s):
        for pat in _PRICE_PATTERNS:
            m = pat.search(part)
            if not m:
                continue
            try:
                n = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if "m" in part.lower()[m.end() - 1 : m.end() + 1] or "million" in part.lower():
                n *= 1_000_000
            elif "k" in part.lower()[m.end() - 1 : m.end() + 1]:
                n *= 1_000
            values.append(n)
            break
    return sum(values) / len(values) if values else None


def coerce_price(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return parse_price(v)
    return None


def fmt_aud(n: float | str) -> str:
    if isinstance(n, str):
        parsed = parse_price(n)
        if parsed is None:
            return n
        n = parsed
    return f"${int(n):,}"


def short_address(address: str) -> str:
    return address.split(",")[0].strip() if address else address


def normalize_address(address: str) -> str:
    if not address:
        return ""
    short = address.split(",")[0].strip().lower()
    abbrev = {
        " ct": " court", " st": " street", " rd": " road", " pl": " place",
        " dr": " drive", " ave": " avenue", " cres": " crescent", " cl": " close",
    }
    short = re.sub(r"[.]", "", short)
    short = re.sub(r"\s+", " ", short)
    for k, v in abbrev.items():
        if short.endswith(k):
            short = short[: -len(k)] + v
            break
    return short


_SALE_METHOD_LABELS = {
    "auction": "Auction",
    "eoi": "Expressions of interest",
    "offers_over": "Offers over",
    "price_guide": "Price guide",
    "fixed": "Fixed price",
    "contact_agent": "Contact agent",
}


def infer_sale_method(price: Any) -> tuple[str, str]:
    """Classify a listing's sale method from its price string (no method field)."""
    if not price or not isinstance(price, str):
        return "contact_agent", _SALE_METHOD_LABELS["contact_agent"]
    s = price.lower()
    if "auction" in s:
        key = "auction"
    elif "eoi" in s or "expression" in s or "best offer" in s or "best and final" in s:
        key = "eoi"
    elif "offers over" in s or "offers above" in s or "o/o" in s:
        key = "offers_over"
    elif "guide" in s:
        key = "price_guide"
    elif re.search(r"\$\s*[\d,]", s):
        key = "fixed"
    else:
        key = "contact_agent"
    return key, _SALE_METHOD_LABELS[key]


def _neg_datestr(s: Any) -> int:
    """ISO date string -> negative int so an ascending sort is newest-first."""
    if not s or not isinstance(s, str):
        return 0
    digits = re.sub(r"\D", "", s)[:8]
    return -int(digits) if digits else 0


def _to_int_or_none(v: Any) -> int | None:
    f = coerce_price(v)
    return int(f) if f is not None else None


def _competitor_identity(c: dict[str, Any]) -> str:
    return c.get("listingUrl") or c.get("id") or normalize_address(c.get("address", ""))


def _sold_identity(c: dict[str, Any]) -> str:
    return c.get("listing_url") or normalize_address(c.get("address", ""))


def _active_card(c: dict[str, Any], aperture_ring: int | None, aperture_label: str | None) -> dict[str, Any]:
    """A `slots.competitor_map.competitors` entry -> a comparable card."""
    method_key, method_label = infer_sale_method(c.get("priceText"))
    dom = c.get("daysOnMarket")
    first_seen = (
        (dt.date.today() - dt.timedelta(days=int(dom))).isoformat()
        if isinstance(dom, (int, float)) and dom is not None else None
    )
    return {
        "identity": _competitor_identity(c),
        "status": "for_sale",
        "address": short_address(c.get("address", "")),
        "suburb": c.get("suburb"),
        "price": c.get("priceText"),
        "price_mid": _to_int_or_none(c.get("priceLow")),
        "sale_method": method_key,
        "sale_method_label": method_label,
        "bedrooms": c.get("bedrooms"),
        "bathrooms": c.get("bathrooms"),
        "distance_km": c.get("distanceKm"),
        "days_on_market": dom,
        "first_seen": first_seen,
        "combinatorial_match": bool(c.get("combinatorialMatch")),
        "difference_vs_subject": c.get("differenceVsSubject"),
        "aperture_ring": aperture_ring,
        "aperture_label": aperture_label,
        "image_src": c.get("imageSrc"),
        "href": c.get("listingUrl"),
    }


def _sold_card(c: dict[str, Any]) -> dict[str, Any]:
    """A `slots.best_comp` / `slots.recent_comps` entry -> a comparable (sold) card."""
    sold_price = coerce_price(c.get("sale_price"))
    sd = c.get("sale_date")
    sd = sd if isinstance(sd, str) else (sd.isoformat()[:10] if sd else None)
    return {
        "identity": _sold_identity(c),
        "status": "sold",
        "address": short_address(c.get("address", "")),
        "price": (f"${int(sold_price):,}" if sold_price else None),
        "sold_price": int(sold_price) if sold_price else None,
        "sale_date": sd,
        "bedrooms": c.get("bedrooms"),
        "bathrooms": c.get("bathrooms"),
        "image_src": c.get("photo_url"),
        "href": c.get("listing_url"),
    }


def _map_slots(slots: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Map the engine's stored output into (active_cards, sold_cards, aperture)."""
    cm = slots.get("competitor_map") or {}
    aperture = {"ring": cm.get("aperture_ring"), "label": cm.get("aperture_label"),
                "active_in_band": cm.get("active_in_band")}
    active = [_active_card(c, aperture["ring"], aperture["label"])
              for c in (cm.get("competitors") or []) if isinstance(c, dict)]
    sold: list[dict[str, Any]] = []
    seen: set[str] = set()
    best = slots.get("best_comp")
    if isinstance(best, dict) and best.get("address"):
        card = _sold_card(best)
        sold.append(card)
        seen.add(card["identity"])
    for rc in (slots.get("recent_comps") or []):
        if not isinstance(rc, dict):
            continue
        card = _sold_card(rc)
        if card["identity"] in seen:
            continue
        seen.add(card["identity"])
        sold.append(card)
    return active, sold, aperture


def comparables_from_slots(slots: dict[str, Any]) -> dict[str, Any] | None:
    """First-visit baseline: top closest active + closest sold, from engine output.

    Returns None when the report has no competitor map yet (resolver not run)."""
    cm = slots.get("competitor_map") or {}
    if not cm.get("competitors"):
        return None
    active, sold, aperture = _map_slots(slots)
    return {
        "closest_active": active[:6],
        "closest_sold": sold[:3],
        "aperture_ring": aperture["ring"],
        "aperture_label": aperture["label"],
        "active_in_band": aperture["active_in_band"],
        "generated_at": dt.datetime.utcnow().isoformat(),
    }


def _comparable_state(active: list[dict[str, Any]], sold: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    today = dt.date.today().isoformat()
    state: dict[str, dict[str, Any]] = {}
    for c in active:
        state[c["identity"]] = {
            "status": "for_sale", "price": c.get("price_mid"),
            "sale_method": c.get("sale_method"), "days_on_market": c.get("days_on_market"),
            "last_seen": today,
        }
    for c in sold:
        state.setdefault(c["identity"], {
            "status": "sold", "price": c.get("sold_price"),
            "sale_date": c.get("sale_date"), "last_seen": today,
        })
    return state


def _new_listing_event(c: dict[str, Any], date: str) -> dict[str, Any]:
    near = ""
    if isinstance(c.get("distance_km"), (int, float)):
        near = f" {c['distance_km']:.1f} km from your home."
    return {
        "id": f"new_listing:{c['identity']}:{date}", "date": date, "ts": dt.datetime.utcnow().isoformat(),
        "type": "new_listing", "kind": "new_listing",
        "ring": c.get("aperture_ring"), "ring_label": c.get("aperture_label"),
        "address": c["address"], "image_src": c.get("image_src"), "href": c.get("href"),
        "price": c.get("price_mid"), "sale_method": c.get("sale_method"),
        "headline": f"{c['address']} just listed at {fmt_aud(c['price_mid']) if c.get('price_mid') else (c.get('price') or 'an undisclosed price')}",
        "body": f"A comparable home came to market — {c.get('bedrooms') or '?'}-bed, {c.get('bathrooms') or '?'}-bath, by {c.get('sale_method_label','private treaty').lower()}.{near}",
        "effect_on_your_home": "Another home now competing for the same buyer. How it is priced and how long it sits become live reference points for yours.",
    }


def _sold_event(c: dict[str, Any]) -> dict[str, Any]:
    date = c.get("sale_date") or dt.date.today().isoformat()
    return {
        "id": f"sold:{c['identity']}:{date}", "date": date, "ts": dt.datetime.utcnow().isoformat(),
        "type": "sold", "kind": "comp_sold", "ring": None, "ring_label": None,
        "address": c["address"], "image_src": c.get("image_src"), "href": c.get("href"),
        "price": c.get("sold_price"),
        "headline": f"{c['address']} sold for {fmt_aud(c['sold_price']) if c.get('sold_price') else 'an undisclosed price'}",
        "body": f"A comparable home transacted — {c.get('bedrooms') or '?'}-bed, {c.get('bathrooms') or '?'}-bath. The valuation engine re-weights to actual sale prices as they land.",
        "effect_on_your_home": "A completed sale is the cleanest evidence of what buyers actually paid for a home like yours — stronger than any asking price.",
    }


def comparable_events_from_slots(
    slots: dict[str, Any], existing: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Diff the engine's comparable set against the persisted snapshot, append
    change events to the durable log, and enforce the 7-day curiosity guarantee.
    Returns (event_log, new_state)."""
    today = dt.date.today().isoformat()
    now_iso = dt.datetime.utcnow().isoformat()
    active, sold, aperture = _map_slots(slots)
    new_state = _comparable_state(active, sold)

    prior_state = dict((existing or {}).get("comparable_state") or {})
    prior_log = list((existing or {}).get("comparable_events") or [])
    seen_ids = {e.get("id") for e in prior_log}
    new_events: list[dict[str, Any]] = []

    def _add(ev: dict[str, Any]) -> bool:
        if ev.get("id") and ev["id"] not in seen_ids:
            seen_ids.add(ev["id"])
            new_events.append(ev)
            return True
        return False

    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=COMPARABLE_WINDOW_DAYS)).date().isoformat()

    # Active: newly-seen -> new_listing (tight rings 0/1 only — the wide ring's
    # firehose surfaces via the guarantee). Already-tracked -> price/method change.
    for c in active:
        ident = c["identity"]
        prior = prior_state.get(ident)
        if prior is None:
            dom = c.get("days_on_market")
            first_date = (
                (dt.date.today() - dt.timedelta(days=int(dom))).isoformat()
                if isinstance(dom, (int, float)) and dom is not None else today
            )
            ring = c.get("aperture_ring")
            if (ring is None or ring <= 1) and first_date >= cutoff:
                _add(_new_listing_event(c, first_date))
            continue
        cur_p, pri_p = c.get("price_mid"), prior.get("price")
        if cur_p and pri_p and abs(cur_p - pri_p) >= 5_000:
            direction = "lifted" if cur_p > pri_p else "reduced"
            _add({
                "id": f"price_change:{ident}:{cur_p}", "date": today, "ts": now_iso,
                "type": "price_change", "kind": "comp_price_change",
                "ring": c.get("aperture_ring"), "ring_label": c.get("aperture_label"),
                "address": c["address"], "image_src": c.get("image_src"), "href": c.get("href"),
                "price": cur_p, "prior_price": pri_p,
                "headline": f"{c['address']} {direction} its asking price by {fmt_aud(abs(cur_p - pri_p))} to {fmt_aud(cur_p)}",
                "body": f"A comparable home moved its asking price. Previous: {fmt_aud(pri_p)}. Current: {fmt_aud(cur_p)}.",
                "effect_on_your_home": ("A reduction signals the original ask was above where buyers are — a downside reference for your pricing."
                                        if direction == "reduced" else
                                        "A lift signals a seller testing higher — an upside reference, but watch days-on-market for confirmation."),
            })
        cur_m, pri_m = c.get("sale_method"), prior.get("sale_method")
        if cur_m and pri_m and cur_m != pri_m:
            _add({
                "id": f"method_change:{ident}:{cur_m}", "date": today, "ts": now_iso,
                "type": "method_change", "kind": "method_change",
                "ring": c.get("aperture_ring"), "ring_label": c.get("aperture_label"),
                "address": c["address"], "image_src": c.get("image_src"), "href": c.get("href"),
                "sale_method": cur_m, "prior_sale_method": pri_m,
                "headline": f"{c['address']} switched to {c.get('sale_method_label', cur_m).lower()}",
                "body": f"A comparable home changed how it is being sold — from {_SALE_METHOD_LABELS.get(pri_m, pri_m).lower()} to {c.get('sale_method_label', cur_m).lower()}.",
                "effect_on_your_home": "A change in method often signals a change in strategy — a switch to auction or offers-over can mean the fixed price wasn't drawing buyers.",
            })

    # Sold comparables with a recent sale date.
    for c in sold:
        if (c.get("sale_date") or "") >= cutoff:
            _add(_sold_event(c))

    # Withdrawn — was for_sale in prior, now absent from the current set.
    cur_idents = {c["identity"] for c in active} | {c["identity"] for c in sold}
    for ident, prior in prior_state.items():
        if prior.get("status") == "for_sale" and ident not in cur_idents:
            _add({
                "id": f"withdrawn:{ident}:{today}", "date": today, "ts": now_iso,
                "type": "withdrawn", "kind": "comp_withdrawn", "ring": None, "ring_label": None,
                "address": ident if not str(ident).startswith("http") else "A comparable listing",
                "headline": "A comparable listing was withdrawn from market",
                "body": "A home that was competing with yours is no longer listed — withdrawal, off-market sale, or a refresh.",
                "effect_on_your_home": "Withdrawn stock tightens visible supply at your bed + price band.",
            })

    log_combined = prior_log + new_events

    # Curiosity guarantee — ensure a new_listing/sold inside the trailing 7 days.
    g_cutoff = (dt.datetime.utcnow() - dt.timedelta(days=GUARANTEE_DAYS)).date().isoformat()
    has_recent = any(
        e.get("type") in ("new_listing", "sold") and (e.get("date") or "") >= g_cutoff
        for e in log_combined
    )
    if not has_recent and (active or sold):
        act_fresh = sorted(
            [c for c in active if isinstance(c.get("days_on_market"), (int, float))],
            key=lambda c: c["days_on_market"],
        )
        sold_fresh = sorted(sold, key=lambda c: _neg_datestr(c.get("sale_date")))
        cand = None
        if act_fresh:
            dom = act_fresh[0]["days_on_market"]
            cand = ("new_listing", act_fresh[0], (dt.date.today() - dt.timedelta(days=int(dom))).isoformat())
        if sold_fresh and (cand is None or (sold_fresh[0].get("sale_date") or "") >= (cand[2] or "")):
            cand = ("sold", sold_fresh[0], sold_fresh[0].get("sale_date") or today)
        if cand:
            etype, c, date = cand
            ev = _new_listing_event(c, date) if etype == "new_listing" else _sold_event(c)
            ev["ring_widened"] = True
            if _add(ev):
                log_combined = prior_log + new_events
                log.info("Curiosity guarantee: widened (%s) — surfaced %s", aperture.get("label"), ev.get("headline"))

    # Sort + cap the durable log (date desc, ts desc).
    log_combined.sort(key=lambda e: (e.get("date") or "", e.get("ts") or ""), reverse=True)
    keep_cutoff = (dt.datetime.utcnow() - dt.timedelta(days=EVENT_LOG_MAX_DAYS)).date().isoformat()
    log_combined = [e for e in log_combined if (e.get("date") or "") >= keep_cutoff][:EVENT_LOG_MAX]
    return log_combined, new_state
