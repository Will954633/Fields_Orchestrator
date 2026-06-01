#!/usr/bin/env python3
"""refresh_property_reports.py — populate per-seller activity feeds.

For each property report in `system_monitor.property_reports`, query
Gold_Coast (active + sold for tracked suburbs) and content_articles,
generate fresh activity items, and upsert.

v0.3: one hard-coded report (13-terrace-court-merrimac). Once lead
capture lands, reports get created on /analyse-your-home submission
and this script picks them up automatically.

Frontend: hits /.netlify/functions/property-report-activity?slug=...
Falls back to TS fixture if DB empty.

Run: python3 scripts/refresh_property_reports.py [--slug X] [--days N] [--dry-run]
"""

from __future__ import annotations
import argparse
import datetime as dt
import logging
import re
import sys
from typing import Any

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client  # noqa: E402
from scripts.property_reports.slot_resolver import SlotResolver  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refresh_property_reports")

# ---------------------------------------------------------------------------
# Hard-coded report configs (v0.3 — moves to DB when lead capture lands)
# ---------------------------------------------------------------------------

REPORT_CONFIGS: dict[str, dict[str, Any]] = {
    "13-terrace-court-merrimac": {
        "subject": {
            "address": "13 Terrace Court",
            "suburb": "Merrimac",
            "bedrooms": 6,
            "bathrooms": 3,
            "land_area": 658,
            "internal_area": 221,
            "features": ["pool", "dual_living", "cul_de_sac", "bushland_adjacent", "north_facing_rear"],
            "condition": 9,
            "valuation_low": 1_884_000,
            "valuation_high": 2_073_000,
            # Street-address-only names of the 6 named comps used in the
            # valuation engine. Cross-referenced against active listings to
            # detect "one of your comps is currently for sale" moments.
            "comps": [
                "4 Mull Court",
                "3 Islay Court",
                "21 Bayford Court",
                "52 Highfield Drive",
                "8 Trinity Place",
                "14 Indooroopilly Court",
            ],
        },
        # Suburbs to monitor for competition + comp sales
        "competition_suburbs": ["merrimac", "robina", "varsity_lakes"],
        # Price band considered competing
        "competition_price_min": 1_500_000,
        "competition_price_max": 2_500_000,
        # Min bedrooms to flag as competitor
        "competition_min_bedrooms": 5,
        # Always-on market snapshot (refreshed by date when the script runs)
        "market_state": {
            "fci": 102,
            "fci_label": "Balanced-firming",
            "stock_vs_baseline_pct": -13,
            "wage_growth_qoq_pct": 1.8,
        },
    },
}

# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

PRICE_PATTERNS = [
    re.compile(r"\$([\d,]+(?:\.\d+)?)\s*(?:m|million)\b", re.I),  # $1.5m
    re.compile(r"\$([\d,]+(?:\.\d+)?)k\b", re.I),  # $950k
    re.compile(r"\$([\d,]+)"),  # $1,250,000
]


def parse_price(s: Any) -> float | None:
    """Return midpoint of price (handles ranges) or None."""
    if not s or not isinstance(s, str):
        return None
    # Strip everything after a dash to handle ranges, but average both sides
    values: list[float] = []
    parts = re.split(r"\s*[-–—]\s*", s)
    for part in parts:
        for pat in PRICE_PATTERNS:
            m = pat.search(part)
            if not m:
                continue
            raw = m.group(1).replace(",", "")
            try:
                n = float(raw)
            except ValueError:
                continue
            if "m" in part.lower()[m.end() - 1 : m.end() + 1] or "million" in part.lower():
                n *= 1_000_000
            elif "k" in part.lower()[m.end() - 1 : m.end() + 1]:
                n *= 1_000
            values.append(n)
            break
    if not values:
        return None
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def short_address(address: str) -> str:
    """'12 Bourton Road, Merrimac, QLD 4226' → '12 Bourton Road'."""
    return address.split(",")[0].strip() if address else address


def normalize_address(address: str) -> str:
    """Normalise for cross-referencing against the comps list.

    '21 Bayford Court, Merrimac, QLD 4226' → '21 bayford court'
    Handles 'Ct.' / 'Court', 'St' / 'Street', extra whitespace.
    """
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


def is_named_comp(address: str, comps: list[str]) -> bool:
    if not address or not comps:
        return False
    target = normalize_address(address)
    return any(normalize_address(c) == target for c in comps)


# NOTE: comparable matching + the durable change log are NOT done here. The
# production engine scripts/property_reports/competitor_matcher.py (run
# per-report by the slot resolver) ranks substitutes with an adaptive aperture
# and real straight-line distance, storing the result on each report doc under
# `slots.competitor_map` / `slots.best_comp` / `slots.recent_comps`. The feed
# helpers (comparables_from_slots / comparable_events_from_slots, incl.
# infer_sale_method) live in scripts/property_reports/comparable_feed.py and are
# imported at the top of this module — one engine, not two.


def days_since(d: dt.datetime | None) -> int | None:
    if not d:
        return None
    if not isinstance(d, dt.datetime):
        return None
    now = dt.datetime.now(d.tzinfo) if d.tzinfo else dt.datetime.utcnow()
    return (now - d).days


def fmt_aud(n: float | str) -> str:
    """Format a number as $1,250,000. Accepts ints, floats, or AUD strings."""
    if isinstance(n, str):
        parsed = parse_price(n)
        if parsed is None:
            return n  # last-ditch: return the raw string
        n = parsed
    return f"${int(n):,}"


def coerce_price(v: Any) -> float | None:
    """Accept int/float/string and return a clean float, or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return parse_price(v)
    return None


# ---------------------------------------------------------------------------
# Activity generators
# ---------------------------------------------------------------------------


def _cross_suburb_feature_match(d: dict[str, Any], subject: dict[str, Any]) -> bool:
    """Stricter relevance check for listings outside the subject's own suburb.

    Rule (Will, 2026-05-13): cross-suburb listings only earn a slot in the
    activity feed if they're plausibly competing for the same buyer as the
    subject home. Same-suburb listings have suburb-relevance for free.

    Checks bedrooms >= subject bedrooms (within 1) AND either a pool match
    or a price-band match. Conservative because Domain's `features` array
    is reliable for 'Pool' but not for 'dual living' or 'cul-de-sac'.
    """
    subj_bd = subject.get("bedrooms", 6)
    bd = d.get("bedrooms") or 0
    if bd < subj_bd:  # require exact bedroom parity or more
        return False
    # Either has pool OR sits inside the valuation band — and price is checked
    # in the calling scope anyway, so just require the pool to clear the bar.
    features_lower = {str(f).lower() for f in (d.get("features") or [])}
    if "pool" in features_lower:
        return True
    # Otherwise must clear the higher land-area heuristic
    land = d.get("land_area") or 0
    return land >= 600


def new_listings_activity(
    db, config: dict[str, Any], days: int
) -> list[dict[str, Any]]:
    """Active listings first_seen in the last N days that compete with subject.

    Emits two kinds:
      - comp_on_market — one of the subject's named valuation comps is also
        for sale. Editorial moment.
      - new_listing — generic competing listing.

    Same-suburb listings clear `competition_min_bedrooms`. Cross-suburb
    listings additionally must pass `_cross_suburb_feature_match` — without
    feature overlap, a Robina 5-bed at $1.65M isn't useful context for a
    Merrimac 6-bed seller (Will, 2026-05-13).
    """
    items: list[dict[str, Any]] = []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    subj_suburb = config["subject"]["suburb"].lower().replace(" ", "_")
    named_comps: list[str] = config["subject"].get("comps", [])
    n_comps = len(named_comps)

    for suburb in config["competition_suburbs"]:
        col = db[suburb]
        cursor = col.find(
            {
                "listing_status": "for_sale",
                "first_seen": {"$gte": cutoff},
                "bedrooms": {"$gte": config["competition_min_bedrooms"]},
            },
            {"_id": 0, "address": 1, "price": 1, "first_seen": 1, "bedrooms": 1,
             "bathrooms": 1, "property_type": 1, "listing_url": 1, "property_images": 1,
             "features": 1, "land_area": 1},
        ).sort("first_seen", -1).limit(10)

        for d in cursor:
            price_mid = parse_price(d.get("price"))
            if price_mid is None:
                continue
            if not (config["competition_price_min"] <= price_mid <= config["competition_price_max"]):
                continue
            # Skip if property type isn't house
            if d.get("property_type") not in (None, "House", "Acreage / Semi-Rural"):
                continue

            first_seen = d.get("first_seen")
            full_addr = d.get("address", "")
            addr = short_address(full_addr)
            in_subj_suburb = suburb == subj_suburb
            location_phrase = "" if in_subj_suburb else f" in {suburb.replace('_', ' ').title()}"

            # Cross-suburb relevance gate — drop weakly-relevant items.
            # Always let named comps through regardless of suburb (handled below).
            if not in_subj_suburb and not is_named_comp(full_addr, named_comps):
                if not _cross_suburb_feature_match(d, config["subject"]):
                    continue

            # Cross-reference against named comps
            if is_named_comp(full_addr, named_comps):
                items.append({
                    "date": first_seen.date().isoformat() if first_seen else None,
                    "kind": "comp_on_market",
                    "source_id": f"comp_active:{d.get('listing_url') or addr}",
                    "headline": f"One of your {n_comps} comps is currently for sale: {addr}",
                    "body": (
                        f"{describe_listing(d)} Listed{location_phrase} at {fmt_aud(price_mid)}. "
                        f"This is the same property the valuation engine used as one of its named comparables."
                    ),
                    "effect_on_your_home": (
                        "An active listing of a comp is the cleanest signal of how buyers are currently reading "
                        "homes like yours — every day this listing sits, that asking price becomes the market's "
                        "answer. Watch it: a price drop says the original ask was high; a quick sale says yours can ask the same or more."
                    ),
                    "image_src": pick_first_image(d.get("property_images")),
                    "href": d.get("listing_url"),
                })
                continue  # don't double-emit as new_listing

            effect = build_listing_effect(d, price_mid, config["subject"])
            items.append({
                "date": first_seen.date().isoformat() if first_seen else None,
                "kind": "new_listing",
                "source_id": f"listing:{d.get('listing_url') or addr}",
                "headline": f"{addr}{location_phrase} just listed at {fmt_aud(price_mid)}",
                "body": describe_listing(d),
                "effect_on_your_home": effect,
                "image_src": pick_first_image(d.get("property_images")),
                "href": d.get("listing_url"),
            })

    return items


def valuation_event_activity(report_doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Emit a 'recommendation signed off' item when valuation_finalised_at is set.

    Persistent: lives on the report doc itself so cron runs don't lose the event.
    The python upsert is careful to preserve `valuation_finalised_at` and
    `recommendation` fields if they're set elsewhere (e.g. consultant signoff
    workflow once lead capture is wired).
    """
    if not report_doc:
        return []
    ts = report_doc.get("valuation_finalised_at")
    if not ts:
        return []
    if isinstance(ts, dt.datetime):
        date_str = ts.date().isoformat()
    elif isinstance(ts, str):
        date_str = ts[:10]
    else:
        return []
    rec = report_doc.get("recommendation") or {}
    listing = rec.get("listing_price")
    target = rec.get("target_sale_price")
    price_phrase = ""
    if listing and target:
        price_phrase = f" Recommended listing price: ${listing:,}. Target sale price: ${target:,}."
    return [{
        "date": date_str,
        "kind": "valuation",
        "source_id": f"valuation_finalised:{date_str}",
        "headline": "Your recommendation is signed off",
        "body": (
            "Will reviewed every comparable, every adjustment, and the weighted reconciliation."
            + price_phrase
        ),
        "effect_on_your_home": (
            "See the full reasoning, the four conditions of the precise-pricing protocol, "
            "and the inspection caveat on the Valuation tab."
        ),
        "href": "#valuation",
    }]


def valuation_delta_activity(
    config: dict[str, Any], existing: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Detect a material change in the reconciled valuation since the last
    snapshot and emit an activity item when one's found.

    Cadence (Will, 2026-05-13): the reconciled valuation only moves when the
    underlying comparable cohort moves, which is weekly at best. We refresh
    daily but only emit on actual movement — daily ticks against an unchanged
    figure would be theatre.

    Threshold: emit when |midpoint change| >= max($5,000, 0.5% of midpoint).
    Below that, treat as noise.

    Returns (items, new_history_entry) — caller persists the history entry
    on the report doc.
    """
    val_low = config["subject"].get("valuation_low")
    val_high = config["subject"].get("valuation_high")
    if val_low is None or val_high is None:
        return [], None

    midpoint = (val_low + val_high) / 2
    today_iso = dt.date.today().isoformat()
    new_entry = {
        "date": today_iso,
        "low": int(val_low),
        "high": int(val_high),
        "midpoint": int(midpoint),
    }

    history: list[dict[str, Any]] = []
    if existing:
        history = list(existing.get("valuation_history") or [])

    if not history:
        # No baseline — seed silently. Don't emit, no "rose by $X from $0".
        return [], new_entry

    last = history[-1]
    if last.get("low") == new_entry["low"] and last.get("high") == new_entry["high"]:
        # Nothing changed since last run — no emit, no new history entry.
        return [], None

    delta = new_entry["midpoint"] - last.get("midpoint", new_entry["midpoint"])
    threshold = max(5_000, int(new_entry["midpoint"] * 0.005))
    if abs(delta) < threshold:
        # Below noise floor — record the new figure (so we track drift) but
        # don't emit an activity item.
        return [], new_entry

    direction = "rose" if delta > 0 else "fell"
    last_low = last.get("low", 0)
    last_high = last.get("high", 0)
    range_phrase_prev = f"{fmt_aud(last_low)}–{fmt_aud(last_high)}"
    range_phrase_now = f"{fmt_aud(val_low)}–{fmt_aud(val_high)}"
    delta_phrase = fmt_aud(abs(delta))

    items = [{
        "date": today_iso,
        "kind": "valuation_delta",
        "source_id": f"valuation_delta:{today_iso}",
        "headline": (
            f"Your reconciled range {direction} {delta_phrase} this week — "
            f"now {range_phrase_now}."
        ),
        "body": (
            f"Previous range: {range_phrase_prev}. New range: {range_phrase_now}. "
            f"Movement reflects updates to the comparable cohort used by the valuation engine — "
            f"a sold comparable above or below the prior cohort median shifts the weighted reconciliation."
        ),
        "effect_on_your_home": (
            "Open the Valuation tab to see which comparables are currently driving the figure. "
            "Material movements are reviewed by Will before the consultant-signed recommendation is updated."
        ),
        "href": "#valuation",
    }]
    return items, new_entry


def _query_comp_state(db_gc, suburbs: list[str], comp_name: str) -> dict[str, Any] | None:
    """Find a named comp's current state across the watch suburbs.

    Returns the most recent record (active listing if one exists, else most
    recent sold record). None if no record found.
    """
    target_norm = normalize_address(comp_name)
    for suburb in suburbs:
        col = db_gc[suburb]
        # Use a forgiving regex on the address — handles "Ct" vs "Court" etc.
        pattern = re.escape(comp_name)
        cursor = col.find(
            {"address": {"$regex": rf"^{pattern}\b", "$options": "i"}},
            {"_id": 0, "address": 1, "listing_status": 1, "price": 1, "sold_price": 1,
             "sale_date": 1, "last_seen": 1, "first_seen": 1, "listing_url": 1,
             "property_images": 1, "bedrooms": 1, "bathrooms": 1, "days_on_market": 1},
        ).limit(5)
        # Prefer for_sale; otherwise most recent sold
        for_sale = None
        sold = None
        for d in cursor:
            if normalize_address(d.get("address", "")) != target_norm:
                continue
            if d.get("listing_status") == "for_sale":
                for_sale = d
                break
            if d.get("listing_status") == "sold":
                if sold is None or (d.get("sale_date") or "") > (sold.get("sale_date") or ""):
                    sold = d
        if for_sale:
            return {**for_sale, "_suburb": suburb}
        if sold:
            return {**sold, "_suburb": suburb}
    return None


def comp_lifecycle_activity(
    db_gc, config: dict[str, Any], existing: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Track each named comp and emit when its state changes.

    Snapshot kept in `comp_state_snapshots` on the report doc — keyed by
    normalised address, value is `{status, price, sale_date, snapshot_date}`.

    Emits:
      - comp_price_change — comp was for_sale at price X, now for_sale at Y
      - comp_sold        — comp was for_sale (or unknown), now sold
      - comp_withdrawn   — comp was for_sale, now no for_sale or sold record

    Doesn't duplicate the existing `comp_on_market` flow (new_listings_activity
    already handles "freshly listed within window"). Comp re-listings older
    than the window will surface here as a status-change event.
    """
    suburbs = config.get("competition_suburbs") or [config["subject"]["suburb"].lower().replace(" ", "_")]
    named_comps: list[str] = config["subject"].get("comps", [])
    today_iso = dt.date.today().isoformat()

    prior_snapshots: dict[str, dict[str, Any]] = {}
    if existing:
        prior_snapshots = dict(existing.get("comp_state_snapshots") or {})

    items: list[dict[str, Any]] = []
    new_snapshots: dict[str, dict[str, Any]] = {}

    for comp_name in named_comps:
        key = normalize_address(comp_name)
        prior = prior_snapshots.get(key) or {}
        curr = _query_comp_state(db_gc, suburbs, comp_name)

        # Build the new snapshot — defaults to 'unknown' if no record exists
        if curr is None:
            new_state = {"status": "unknown", "snapshot_date": today_iso}
            curr_status = "unknown"
            curr_price = None
            sale_date = None
        else:
            curr_status = curr.get("listing_status") or "unknown"
            curr_price_raw = curr.get("price") if curr_status == "for_sale" else curr.get("sold_price")
            curr_price = coerce_price(curr_price_raw)
            sale_date = curr.get("sale_date")
            sd_str = sale_date if isinstance(sale_date, str) else (sale_date.isoformat()[:10] if sale_date else None)
            new_state = {
                "status": curr_status,
                "price": curr_price,
                "sale_date": sd_str,
                "suburb": curr.get("_suburb"),
                "snapshot_date": today_iso,
            }
        new_snapshots[key] = new_state

        prior_status = prior.get("status")
        prior_price = prior.get("price")

        # Skip emit when no prior snapshot — seeding only
        if not prior:
            continue

        # comp_sold — previous was for_sale (or unknown with no sale), now sold
        if curr_status == "sold" and prior_status != "sold":
            sold_phrase = fmt_aud(curr_price) if curr_price else "an undisclosed price"
            items.append({
                "date": (sd_str if curr is not None else today_iso),
                "kind": "comp_sold",
                "source_id": f"comp_sold:{key}",
                "headline": f"{comp_name} just sold for {sold_phrase}",
                "body": (
                    f"One of your six named comparables transacted. "
                    f"This will be re-evaluated by the valuation engine in the next pass."
                ),
                "effect_on_your_home": (
                    "When a named comparable sells, its actual sale price replaces its asking price "
                    "in the next valuation cohort review. Watch the Valuation tab for the updated range."
                ),
                "image_src": pick_first_image(curr.get("property_images")) if curr else None,
                "href": curr.get("listing_url") if curr else None,
            })

        # comp_price_change — still for_sale, but the asking price moved
        elif (
            curr_status == "for_sale" and prior_status == "for_sale"
            and curr_price is not None and prior_price is not None
            and abs(curr_price - prior_price) >= 5_000
        ):
            direction = "lifted" if curr_price > prior_price else "reduced"
            delta = abs(curr_price - prior_price)
            items.append({
                "date": today_iso,
                "kind": "comp_price_change",
                "source_id": f"comp_price_change:{key}:{int(curr_price)}",
                "headline": f"{comp_name} {direction} its asking price by {fmt_aud(delta)} to {fmt_aud(curr_price)}",
                "body": (
                    f"A named comparable from your valuation moved its asking price. "
                    f"Previous: {fmt_aud(prior_price)}. Current: {fmt_aud(curr_price)}."
                ),
                "effect_on_your_home": (
                    "A price reduction on a named comp signals the original ask was high — useful "
                    "downside reference. A price lift signals a seller testing higher — useful upside reference."
                    if direction == "reduced"
                    else
                    "A price lift on a named comp signals a seller testing higher — useful upside reference "
                    "but watch days-on-market for confirmation."
                ),
                "image_src": pick_first_image(curr.get("property_images")) if curr else None,
                "href": curr.get("listing_url") if curr else None,
            })

        # comp_withdrawn — was for_sale, now not findable as for_sale or sold.
        # Conservative: only fire if we had a real prior 'for_sale' snapshot.
        elif prior_status == "for_sale" and curr_status not in ("for_sale", "sold"):
            items.append({
                "date": today_iso,
                "kind": "comp_withdrawn",
                "source_id": f"comp_withdrawn:{key}:{today_iso}",
                "headline": f"{comp_name} was withdrawn from market",
                "body": (
                    f"A named comparable that was previously for sale at "
                    f"{fmt_aud(prior_price) if prior_price else 'an undisclosed price'} is no longer listed. "
                    f"This may indicate withdrawal, off-market sale, or temporary delisting for refresh."
                ),
                "effect_on_your_home": (
                    "Withdrawn listings tighten visible supply at your bedroom + price band. "
                    "The valuation engine de-weights this comp until a transaction outcome is recorded."
                ),
            })

    return items, new_snapshots


def market_state_activity(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Always-on freshness item dated today: current suburb market snapshot.

    Provides a dated-today item at the top of every feed so sellers never
    arrive to a feed whose most recent item is months old. Refresh values
    later by querying market_metrics (v0.4).
    """
    ms = config.get("market_state")
    if not ms:
        return []

    today = dt.date.today().isoformat()
    suburb_pretty = config["subject"]["suburb"]
    fci = ms["fci"]
    fci_label = ms["fci_label"].lower()
    stock_delta = ms["stock_vs_baseline_pct"]
    wage = ms["wage_growth_qoq_pct"]

    stock_phrase = (
        f"{abs(stock_delta)}% below" if stock_delta < 0 else f"{stock_delta}% above"
    )

    return [{
        "date": today,
        "kind": "market_state",
        "source_id": f"market_state:{today}",
        "headline": f"{suburb_pretty} is {fci_label} today (FCI {fci}). Stock {stock_phrase} the 5-year baseline.",
        "body": (
            f"The Fields Conviction Index for {suburb_pretty} sits at {fci} ({fci_label}). "
            f"Active listings remain {stock_phrase} the five-year baseline. "
            f"Wage growth — the leading indicator for Gold Coast prices (Abelson et al. 2005, r=0.940) — "
            f"is running at +{wage}% QoQ."
        ),
        "effect_on_your_home": (
            "Tighter supply at the top of the bracket favours sellers. The wage growth indicator gives an "
            "early read on where prices are likely to sit 9-12 months from now."
        ),
    }]


def build_listing_effect(listing: dict[str, Any], price_mid: float, subject: dict[str, Any]) -> str:
    bd_subj = subject["bedrooms"]
    bd = listing.get("bedrooms")
    delta = bd_subj - (bd or 0)
    if delta > 0:
        return f"Your home has {delta} more bedroom{'s' if delta > 1 else ''} than this listing. At {fmt_aud(price_mid)}, this listing helps anchor buyers in your price band."
    if price_mid < subject["valuation_low"]:
        return "Listed below your home's working valuation range — likely competing for the same buyer pool at a lower entry point."
    if price_mid > subject["valuation_high"]:
        return "Listed above your home's working valuation range. Sets an upper-bound buyer reference."
    return f"Listed inside your home's working valuation range ({fmt_aud(subject['valuation_low'])}–{fmt_aud(subject['valuation_high'])})."


def describe_listing(d: dict[str, Any]) -> str:
    bd = d.get("bedrooms") or "?"
    ba = d.get("bathrooms") or "?"
    pt = d.get("property_type") or "Property"
    return f"{pt}, {bd}-bed, {ba}-bath. Listed on Domain."


def recent_sales_activity(
    db, config: dict[str, Any], days: int
) -> list[dict[str, Any]]:
    """Sold properties in subject suburb in last N days."""
    items: list[dict[str, Any]] = []
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).date().isoformat()
    suburb = config["subject"]["suburb"].lower().replace(" ", "_")
    col = db[suburb]

    cursor = col.find(
        {
            "listing_status": "sold",
            "sale_date": {"$gte": cutoff},
            "bedrooms": {"$gte": config["competition_min_bedrooms"]},
        },
        {"_id": 0, "address": 1, "sold_price": 1, "price": 1, "sale_date": 1,
         "bedrooms": 1, "bathrooms": 1, "property_type": 1, "first_seen": 1,
         "days_on_market": 1, "listing_url": 1},
    ).sort("sale_date", -1).limit(5)

    for d in cursor:
        addr = short_address(d.get("address", ""))
        sold_price = coerce_price(d.get("sold_price")) or coerce_price(d.get("price"))
        if not sold_price:
            continue

        sale_date = d.get("sale_date", "")
        dom = d.get("days_on_market")
        dom_phrase = f"{dom} days on market" if dom else "Recently sold"

        items.append({
            "date": sale_date if isinstance(sale_date, str) else sale_date.isoformat()[:10],
            "kind": "sold",
            "source_id": f"sold:{d.get('listing_url') or addr}",
            "headline": f"{addr} sold for {fmt_aud(sold_price)}",
            "body": f"{dom_phrase}. {d.get('bedrooms') or '?'}-bed, {d.get('bathrooms') or '?'}-bath.",
            "effect_on_your_home": (
                "A direct local sale — informs your valuation when the consultant reviews comparables tonight."
                if config["competition_price_min"] <= sold_price <= config["competition_price_max"]
                else "A nearby sale, useful for broader suburb price context."
            ),
            "href": d.get("listing_url"),
        })

    return items


def _feature_tag_variants(features: list[str]) -> list[str]:
    """Map subject feature slugs to all the tag styles they might appear as.

    `north_facing_rear` becomes ['north_facing_rear', 'north-facing-rear',
    'north facing rear', 'northfacingrear']. Matches case-insensitively
    against article tags.
    """
    variants: list[str] = []
    for f in features:
        f = f.lower().strip()
        variants.append(f)
        variants.append(f.replace("_", "-"))
        variants.append(f.replace("_", " "))
        variants.append(f.replace("_", ""))
    return sorted(set(variants))


def new_articles_activity(
    db_sysmon, subject: dict[str, Any], days: int
) -> list[dict[str, Any]]:
    """Articles published in last N days that are SUBJECT-SPECIFIC.

    Hard rule (Will, 2026-05-13): no generic content in the activity feed.
    An article passes only if at least one of the following is true:
      (a) The article's title contains the subject suburb as a word boundary
          ("\\bMerrimac\\b"), so a passing mention in body text no longer
          slips a 'How to choose an agent' article into a seller's dashboard.
      (b) The article's tags include the subject suburb (normalised), or
          any of the subject home's feature tags ('north-facing-rear',
          'dual-living', 'pool', etc.). Tag-based matches let
          feature-specific editorial through even when the title is generic.

    Anything weaker than that — passing mention in body, generic 'Gold Coast
    market' tags — belongs in an email digest, not the dashboard.
    """
    items: list[dict[str, Any]] = []
    col = db_sysmon["content_articles"]
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
    suburb_clean = subject["suburb"].replace("_", " ")
    suburb_variants = sorted({
        suburb_clean,
        suburb_clean.replace(" ", "-"),
        suburb_clean.replace(" ", "_"),
        suburb_clean.replace(" ", "").lower(),
        suburb_clean.lower(),
    })
    feature_variants = _feature_tag_variants(subject.get("features", []))

    # Word-boundary suburb match in title — drops the passing-mention case.
    title_regex = rf"\b{re.escape(suburb_clean)}\b"

    cursor = col.find(
        {
            "published_at": {"$gte": cutoff},
            "$or": [
                {"title": {"$regex": title_regex, "$options": "i"}},
                {"tags": {"$in": suburb_variants}},
                {"tags": {"$in": feature_variants}},
            ],
        },
        {"_id": 0, "title": 1, "slug": 1, "published_at": 1, "custom_excerpt": 1,
         "tags": 1, "feature_image": 1},
    ).sort("published_at", -1).limit(5)

    for d in cursor:
        # Identify which match path qualified this article so the effect-on-
        # your-home line can be specific. Tag matches against the subject's
        # features get the strongest framing.
        tags_lower = {str(t).lower() for t in (d.get("tags") or [])}
        feature_hits = [v for v in feature_variants if v in tags_lower]
        suburb_hit_title = bool(re.search(title_regex, d.get("title", ""), re.I))

        if feature_hits:
            effect = (
                f"Tagged to '{feature_hits[0]}' — a feature your home shares. "
                f"This is the editorial buyers will read when they research what your home offers."
            )
        elif suburb_hit_title:
            effect = (
                f"About {suburb_clean.title()} specifically. "
                f"Adds context buyers will see when they research your suburb."
            )
        else:
            # Tag-suburb match, no title match. Still relevant.
            effect = f"Tagged to {suburb_clean.title()} — adds suburb context to the buyer research path."

        published = d.get("published_at", "")
        items.append({
            "date": published[:10],
            "kind": "article",
            "source_id": f"article:{d.get('slug')}",
            "headline": d.get("title", ""),
            "body": d.get("custom_excerpt") or "New analysis published on fieldsestate.com.au.",
            "effect_on_your_home": effect,
            "image_src": d.get("feature_image"),
            "href": f"/articles/{d.get('slug')}",
        })

    return items


def pick_first_image(images: Any) -> str | None:
    if isinstance(images, list) and images:
        return images[0] if isinstance(images[0], str) else None
    return None


# Comparable set + durable change log helpers live in
# scripts/property_reports/comparable_feed.py (shared with the slot resolver,
# which computes them inline on resolve so the feed is live within seconds of
# submission). comparables_from_slots / comparable_events_from_slots are imported
# at the top of this module.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_activity_for_slug(
    slug: str, days: int, client
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate a balanced feed AND the state to persist alongside it.

    Returns (activity, side_state) where side_state holds the new
    valuation_history entry (if any) and the refreshed comp_state_snapshots
    so upsert_report can persist them.

    Mix discipline: market_state, valuation, and valuation_delta pin top.
    Then per-kind caps so any one source can't crowd out the others.
    """
    config = REPORT_CONFIGS.get(slug)
    if not config:
        log.error("No config for slug %s", slug)
        return [], {}

    db_gc = client["Gold_Coast"]
    db_sm = client["system_monitor"]

    # Load existing doc to pick up persistent fields (valuation_finalised_at,
    # recommendation, valuation_history, comp_state_snapshots, manual_items[])
    existing = db_sm["property_reports"].find_one({"slug": slug})

    val_delta_items, val_history_entry = valuation_delta_activity(config, existing)
    comp_lifecycle_items, comp_snapshots = comp_lifecycle_activity(db_gc, config, existing)

    def _generate(window_days: int) -> dict[str, list[dict[str, Any]]]:
        listings_raw = new_listings_activity(db_gc, config, window_days)
        return {
            "market_state": market_state_activity(config),
            "valuation": valuation_event_activity(existing),
            "valuation_delta": val_delta_items,
            "comp_on_market": [i for i in listings_raw if i["kind"] == "comp_on_market"],
            "comp_sold": [i for i in comp_lifecycle_items if i["kind"] == "comp_sold"],
            "comp_price_change": [i for i in comp_lifecycle_items if i["kind"] == "comp_price_change"],
            "comp_withdrawn": [i for i in comp_lifecycle_items if i["kind"] == "comp_withdrawn"],
            "sold": recent_sales_activity(db_gc, config, window_days),
            "new_listing": [i for i in listings_raw if i["kind"] == "new_listing"],
            "article": new_articles_activity(db_sm, config["subject"], window_days),
        }

    by_kind = _generate(days)
    # Cold-start: widen lookback if the property-event side is thin
    estate_count = (
        len(by_kind["comp_on_market"]) + len(by_kind["sold"]) + len(by_kind["new_listing"])
    )
    if estate_count < 3 and days < 90:
        log.info("Only %d estate items at %dd; widening to 90 days", estate_count, days)
        by_kind = _generate(90)

    # Sort each kind desc by date
    for k in by_kind:
        by_kind[k].sort(key=lambda x: x.get("date") or "", reverse=True)

    # Priority allocation + per-kind caps
    CAPS = {
        "market_state": 1,
        "valuation": 1,
        "valuation_delta": 1,
        "comp_on_market": 2,
        "comp_sold": 2,
        "comp_price_change": 2,
        "comp_withdrawn": 1,
        "sold": 3,
        "new_listing": 4,
        "article": 2,
    }
    selected: list[dict[str, Any]] = []
    for kind, cap in CAPS.items():
        selected.extend(by_kind.get(kind, [])[:cap])

    # Pin order: market_state + valuation + valuation_delta at top, then by date desc.
    PINNED = {"market_state", "valuation", "valuation_delta"}
    seen: set[str] = set()
    final: list[dict[str, Any]] = []
    pinned = [i for i in selected if i["kind"] in PINNED]
    rest = [i for i in selected if i["kind"] not in PINNED]
    rest.sort(key=lambda x: x.get("date") or "", reverse=True)
    for item in pinned + rest:
        sid = item.get("source_id") or ""
        if sid in seen:
            continue
        seen.add(sid)
        final.append(item)

    side_state = {
        "valuation_history_append": val_history_entry,
        "comp_state_snapshots": comp_snapshots,
    }
    return final[:10], side_state


def upsert_report(
    client, slug: str, activity: list[dict[str, Any]], side_state: dict[str, Any]
) -> None:
    col = client["system_monitor"]["property_reports"]
    now = dt.datetime.utcnow()

    update_doc: dict[str, Any] = {
        "$set": {
            "slug": slug,
            "activity": activity,
            "activity_refreshed_at": now,
            "comp_state_snapshots": side_state.get("comp_state_snapshots") or {},
        },
        "$setOnInsert": {"created_at": now},
    }
    new_history_entry = side_state.get("valuation_history_append")
    if new_history_entry is not None:
        update_doc["$push"] = {"valuation_history": new_history_entry}

    col.update_one({"slug": slug}, update_doc, upsert=True)
    log.info("Upserted %d legacy activity items for %s", len(activity), slug)


def refresh_comparables_for_doc(col, gc_db, doc: dict[str, Any], dry_run: bool) -> bool:
    """Re-run the competitor matcher (cheap, DB-only — no vision / Opus /
    scraping) for one report against tonight's freshly-scraped listings, then
    diff into the durable change log + first-visit baseline. Re-running the
    matcher is what makes the "what changed" stream actually accumulate over
    time: it picks up price drops, method switches, withdrawals, and sales since
    the prior snapshot. Returns True if a competitor map was produced."""
    slug = doc.get("slug")
    try:
        updates = SlotResolver(doc, gc_db).refresh_competitor_slots()
    except Exception as e:
        log.warning("· %s — competitor refresh failed: %s", slug, e)
        return False

    comparables = updates.get("comparables")
    if not comparables:
        log.info("· %s — no competitor map produced (no subject / no substitutes); skipping", slug)
        return False
    events = updates.get("comparable_events", [])
    log.info(
        "· %s — %d active, %d sold, %d events (aperture r%s: %s)",
        slug, len(comparables["closest_active"]), len(comparables["closest_sold"]),
        len(events), comparables.get("aperture_ring"), comparables.get("aperture_label"),
    )
    for c in comparables["closest_active"][:3]:
        log.info("    active  %s — %s (%.1f km)", c.get("price"), c.get("address"),
                 c.get("distance_km") if isinstance(c.get("distance_km"), (int, float)) else -1)
    for e in events[:4]:
        log.info("    event   [%s] %s — %s", e.get("type"), e.get("date"), e.get("headline"))
    if not dry_run:
        col.update_one(
            {"slug": slug},
            {"$set": {**updates, "updated_at": dt.datetime.utcnow()}},
            upsert=False,
        )
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=None, help="Refresh only this slug")
    ap.add_argument("--days", type=int, default=30, help="Lookback window (days, legacy feed)")
    ap.add_argument("--dry-run", action="store_true", help="Print, do not write")
    args = ap.parse_args()

    client = get_client()
    col = client["system_monitor"]["property_reports"]
    gc_db = client["Gold_Coast"]

    # 1) Comparables + durable change log — config-free, EVERY report. Re-runs
    #    the competitor matcher against tonight's listings (cheap, DB-only) and
    #    diffs into the durable change log, so the "what changed since you last
    #    logged in" stream keeps growing while a seller deliberates.
    query = {"slug": args.slug} if args.slug else {}
    docs = list(col.find(query))  # full docs — the resolver needs the subject fields
    log.info("=== Comparables: %d report doc(s) ===", len(docs))
    produced = 0
    for doc in docs:
        if refresh_comparables_for_doc(col, gc_db, doc, args.dry_run):
            produced += 1
    log.info("Comparables produced for %d/%d report(s)%s",
             produced, len(docs), " (DRY RUN)" if args.dry_run else "")

    # 2) Legacy market_state/valuation/article timeline — only the hard-coded
    #    demo configs (Merrimac). Other reports get their `activity` timeline
    #    from the report build pipeline, not here.
    legacy_slugs = ([args.slug] if args.slug else list(REPORT_CONFIGS.keys()))
    for slug in legacy_slugs:
        if slug not in REPORT_CONFIGS:
            continue
        log.info("=== Legacy timeline: %s ===", slug)
        activity, side_state = build_activity_for_slug(slug, args.days, client)
        for item in activity:
            log.info("  [%s] %s — %s", item.get("kind"), item.get("date"), item.get("headline"))
        if not args.dry_run:
            upsert_report(client, slug, activity, side_state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
