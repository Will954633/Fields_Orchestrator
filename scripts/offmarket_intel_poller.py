#!/usr/bin/env python3
"""
offmarket_intel_poller.py — fast, NO-LLM "intel" for the off-market swipe deck.

Consumes `system_monitor.offmarket_intel` requests written by the website's
`offmarket-intel.mjs` (status="pending"), computes the DETERMINISTIC scarcity +
competition numbers for the subject address by reusing the existing mini-site
resolvers (no Opus, no vision — Mongo-only, ~1-4s), and writes the result back
(status="done"). The deck polls the same endpoint and streams the numbers into
its "how rare your home is" card.

Pattern mirrors the other VM pollers (offmarket_order_processor.py). Runs as
systemd service `fields-offmarket-intel-poller`.
"""
import argparse
import math
import re
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")  # repo root -> scripts.*, shared.*

from shared.db import get_client  # noqa: E402
from scripts.property_reports.inline_features import derive_features_basic  # noqa: E402
from scripts.property_reports.scarcity_features import resolve_scarcity_features  # noqa: E402
from scripts.property_reports.competitor_matcher import resolve_competitor_map  # noqa: E402
from scripts.property_reports.nearby_pois import resolve_nearby_pois, to_walking_poi_list  # noqa: E402
from scripts.property_reports.positioning_object import resolve_positioning_object  # noqa: E402
from scripts.property_reports import scarcity_narrative  # noqa: E402
from scripts.property_reports import personas_narrative  # noqa: E402

# The mini-site's narrative pipeline uses Opus (higher latency/cost, fine for
# a one-time build). This poller's positioning queue is a lighter, decoupled
# tier — cached forever per property once computed, but each NEW property's
# first computation should still be reasonably fast. Sonnet 5 measured ~11s
# for this exact prompt/output shape on 2026-07-23 (see fix-history) — good
# enough for a background, patiently-polled queue, not the fast intel path.
scarcity_narrative.MODEL = "claude-sonnet-5"
# personas_narrative is left on its own default (Opus 4.7, MAX_TOKENS=2200) —
# measured 2026-07-23: Sonnet 5 reliably produced MALFORMED JSON (unterminated
# strings, not just truncation) on this schema's 3-persona x 7-field
# complexity, even with MAX_TOKENS raised to 3600. Opus is the proven,
# already-in-production model for this exact prompt (used on 23 live
# mini-site reports) — one-time cached-forever cost per property, so
# reliability here matters more than the marginal cost saving.

# Gold_Coast suburb collections a slug might live in (mirrors db.server TARGET_SUBURBS).
TARGET_SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes", "burleigh_heads",
    "mudgeeraba", "reedy_creek", "merrimac", "worongary", "carrara",
]
POLL_SECONDS = 3
FRESH_DAYS = 14

# Schema versions — bump whenever compute_intel()'s or compute_positioning()'s
# OUTPUT SHAPE OR LOGIC changes (new/removed fields, different frame-scoring
# behaviour, etc.), not for unrelated changes elsewhere in this file. The
# matching Netlify endpoint (offmarket-intel.mjs / offmarket-positioning.mjs)
# compares its own hardcoded CURRENT_SCHEMA_VERSION against each cached doc's
# stamped version and re-queues on mismatch — so a stale doc self-heals on
# its next real pageview instead of silently serving old content until
# someone happens to notice and manually resets it (bit twice in one day,
# 2026-07-23, before this existed). Bump BOTH sides together — there is no
# shared constant between Python and JS in this codebase, so this is a
# manual-discipline contract, not an enforced one.
INTEL_SCHEMA_VERSION = 1
POSITIONING_SCHEMA_VERSION = 1


def _now():
    return datetime.now(timezone.utc).isoformat()


def _find_subject(gc, suburb, slug):
    """Load the Gold_Coast doc by url_slug — try the given suburb first, then scan."""
    tried = set()
    order = ([suburb] if suburb else []) + TARGET_SUBURBS
    for s in order:
        if not s or s in tried:
            continue
        tried.add(s)
        try:
            d = gc[s].find_one({"url_slug": slug})
        except Exception:
            d = None
        if d:
            d.setdefault("suburb_key", s)
            return d, s
    return None, None


def compute_intel(gc, suburb, slug):
    """Return the deck-shaped intel dict (all deterministic, no LLM)."""
    subject, matched = _find_subject(gc, suburb, slug)
    if not subject:
        return None, "subject_not_found"

    # Scarcity — derives features.basic internally; None if no bed/bath/land/floor.
    try:
        scarcity = resolve_scarcity_features(subject, gc)
    except Exception:
        traceback.print_exc()
        scarcity = None

    # Price anchor: engine reconciled-range midpoint if the doc already carries
    # one, else None (matcher ranks on physical attributes; price guard off).
    rng = ((subject.get("valuation_data") or {}).get("confidence") or {}).get("range") or {}
    price_anchor = None
    try:
        if rng.get("low") and rng.get("high"):
            price_anchor = int((rng["low"] + rng["high"]) / 2)
    except Exception:
        price_anchor = None

    try:
        features_basic = derive_features_basic(subject)
    except Exception:
        features_basic = None

    try:
        comp = resolve_competitor_map(
            subject, gc, features_basic,
            price_anchor=price_anchor,
            active_listings_total=(scarcity or {}).get("active_listings_total"),
            geocode_missing=True,
        )
    except Exception:
        traceback.print_exc()
        comp = None

    funnel = ((comp or {}).get("ranked_comparison") or {}).get("funnel") or {}
    notable = []
    for f in (scarcity or {}).get("notable_features", []) or []:
        phrase = (f or {}).get("phrase") or (f or {}).get("label") or (f or {}).get("value")
        if phrase:
            notable.append({
                "key": (f or {}).get("key"),
                "tier": (f or {}).get("tier"),
                "label": (f or {}).get("label"),
                "phrase": str(phrase),
            })

    # Nearest-POI-per-category — local haversine against the pre-harvested
    # Google Places dataset (Gold_Coast_POIs.pois). No external API calls.
    # Coordinate field shape varies by doc vintage (mirrors db.server.ts).
    gc_coords = subject.get("geocoded_coordinates") or {}
    lat = subject.get("LATITUDE", subject.get("latitude", gc_coords.get("latitude")))
    lon = subject.get("LONGITUDE", subject.get("longitude", gc_coords.get("longitude")))
    try:
        proximity = resolve_nearby_pois(lat, lon, gc)
    except Exception:
        traceback.print_exc()
        proximity = {}

    result = {
        "scarcity": {
            "active_total": (scarcity or {}).get("active_listings_total"),
            "active_matching": (scarcity or {}).get("active_matching_full_stack"),
            "notable": notable[:5],
            "query": (scarcity or {}).get("active_matching_query"),
        },
        "competition": {
            "n_compete": funnel.get("close_tier"),
            "n_total": funnel.get("active_total"),
        },
        "proximity": proximity,
        "matched_suburb": matched,
    }
    return result, None


def _parse_price(s):
    if not s or not isinstance(s, str):
        return None
    nums = re.findall(r"\$?([\d,]{6,})", s)
    vals = []
    for n in nums:
        try:
            v = float(n.replace(",", ""))
            if 50000 <= v <= 20_000_000:
                vals.append(v)
        except ValueError:
            pass
    return sum(vals) / len(vals) if vals else None


def _haversine_km_local(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def estimate_price_range(gc, suburb_key, lat, lon, bedrooms, radius_km=2.5, limit=6):
    """Coarse comps-based price range — mirrors the off-market deck's own
    'wealth reveal' card (getNearbySoldComps + a percentile range, in
    db.server.ts) so the positioning path's affordable/not read agrees with
    what the same visitor already saw on an earlier card. Off-market docs
    almost never carry a cached valuation_data range (that's a client-side
    calc for this specific deck), so this fills that gap here — not a
    valuation, not displayed as one, just an anchor for the suburb price-tier
    comparison and the personas prompt's working range. Returns
    {"low", "mid", "high"} or None."""
    if lat is None or lon is None or not suburb_key:
        return None
    try:
        coll = gc[suburb_key]
    except Exception:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%d")
    query = {"listing_status": "sold", "sold_date": {"$gte": cutoff}}
    if isinstance(bedrooms, (int, float)) and bedrooms > 0:
        query["bedrooms"] = {"$gte": int(bedrooms) - 1, "$lte": int(bedrooms) + 1}
    try:
        candidates = list(coll.find(
            query, {"sale_price": 1, "LATITUDE": 1, "LONGITUDE": 1, "latitude": 1, "longitude": 1},
        ).limit(400))
    except Exception:
        return None

    scored = []
    for d in candidates:
        clat = d.get("LATITUDE", d.get("latitude"))
        clon = d.get("LONGITUDE", d.get("longitude"))
        try:
            clat, clon = float(clat), float(clon)
        except (TypeError, ValueError):
            continue
        dist = _haversine_km_local(lat, lon, clat, clon)
        if dist > radius_km:
            continue
        price = _parse_price(d.get("sale_price"))
        if price:
            scored.append((dist, price))
    if len(scored) < 3:
        return None
    scored.sort(key=lambda x: x[0])
    prices = sorted(p for _, p in scored[:limit])
    n = len(prices)
    lo = prices[max(0, int(n * 0.15))]
    hi = prices[min(n - 1, int(n * 0.85))]
    return {"low": lo, "mid": (lo + hi) / 2, "high": hi}


def compute_positioning(gc, suburb, slug):
    """The deck's 'Combination' / 'Right Buyer' / 'How we'd position it' cards.
    Decoupled from compute_intel() — includes a real Sonnet 5 generation
    (~11s), so it runs on its own slower, patiently-polled queue and is
    cached forever once computed (a home's feature combination doesn't
    change; the LLM call has real per-property cost, so it should never
    silently regenerate on a later visit).
    """
    subject, matched = _find_subject(gc, suburb, slug)
    if not subject:
        return None, "subject_not_found"

    try:
        scarcity = resolve_scarcity_features(subject, gc)
    except Exception:
        traceback.print_exc()
        scarcity = None

    # Honest degrade: no usable feature stack, no story to tell — matches
    # resolve_positioning_object's/resolve_scarcity_narrative's own gates.
    if not scarcity or not scarcity.get("notable_features"):
        return {"positioning": None, "narrative": None, "feature_combination": None, "persona": None}, None

    gc_coords = subject.get("geocoded_coordinates") or {}
    lat = subject.get("LATITUDE", subject.get("latitude", gc_coords.get("latitude")))
    lon = subject.get("LONGITUDE", subject.get("longitude", gc_coords.get("longitude")))
    try:
        proximity = resolve_nearby_pois(lat, lon, gc)
        # Real routed walking distance for the handful of walkable candidates
        # only — never label a straight-line figure "a walk to X" (see
        # OFFMARKET-RARITY-POI-SOURCE fix-history). Cheap here: a few targeted
        # Mapbox calls, once per property, on the decoupled/patient queue.
        walk_pois = to_walking_poi_list(proximity, lat, lon)
    except Exception:
        traceback.print_exc()
        proximity, walk_pois = {}, []

    # Patch beach distance into the features snapshot from our proximity data
    # when the valuation engine's own figure is missing (~99.8% of docs) —
    # otherwise positioning_object's beach-related flags are silently blind.
    fb = dict(scarcity.get("features_basic_snapshot") or {})
    beach_km = (proximity.get("beach") or {}).get("distance_km")
    if not fb.get("beach_distance_km") and beach_km is not None:
        fb["beach_distance_km"] = beach_km
    scarcity_patched = dict(scarcity)
    scarcity_patched["features_basic_snapshot"] = fb

    address = subject.get("address") or subject.get("complete_address") or ""
    suburb_display = (matched or suburb or "").replace("_", " ").title()

    try:
        price_range = estimate_price_range(gc, matched, lat, lon, subject.get("bedrooms"))
    except Exception:
        traceback.print_exc()
        price_range = None
    price_anchor = price_range["mid"] if price_range else None

    try:
        positioning = resolve_positioning_object(
            subject, gc, suburb_display, scarcity=scarcity_patched, pois=walk_pois,
            price_anchor=price_anchor,
        )
    except Exception:
        traceback.print_exc()
        positioning = None

    narrative = None
    try:
        narrative = scarcity_narrative.resolve_scarcity_narrative(scarcity, walk_pois, suburb_display, address)
        if narrative and narrative.get("error"):
            narrative = None  # permanent generation failure — degrade quietly, don't cache an error string as content
    except Exception:
        traceback.print_exc()

    # Primary buyer persona — reuses the mini-site's exact, battle-tested
    # personas_narrative prompt (3-persona output, forbidden-channel guards,
    # honest-hesitation requirement) rather than writing a new one; the off-
    # market card only shows persona[0], but generating 3 costs nothing extra
    # (one call either way) and keeps this in lockstep with the mini-site's
    # proven quality bar. Sonnet 5 (see MODEL override above), same decoupled/
    # cached-forever queue as narrative above.
    persona = None
    try:
        valuation_range = {"low": price_range["low"], "high": price_range["high"]} if price_range else None
        persona_result = personas_narrative.resolve_personas_narrative(
            address, suburb_display, fb, scarcity.get("notable_features") or [],
            scarcity.get("active_matching_full_stack") or 0, scarcity.get("active_listings_total") or 0,
            scarcity.get("cohort_premiums") or [], walk_pois, valuation_range,
        )
        if persona_result and not persona_result.get("error") and persona_result.get("personas"):
            persona = persona_result["personas"][0]
    except Exception:
        traceback.print_exc()

    feature_combination = _build_feature_combination(scarcity, walk_pois)

    return {
        "positioning": positioning,
        "narrative": narrative,
        "feature_combination": feature_combination,
        "persona": persona,
    }, None


def _build_feature_combination(scarcity, walk_pois):
    """Same join used on the mini-site's 'Right Buyer' tab hero
    (YourHomePage.tsx) — the curated scarcity feature phrases, plus the
    nearest walkable school if no phrase already mentions a walk, Oxford-comma
    joined. Kept server-side (not reimplemented in TS) so both surfaces build
    the identical string from the identical inputs."""
    phrases = [
        (f.get("phrase") or "").strip()
        for f in (scarcity.get("notable_features") or [])
        if (f.get("phrase") or "").strip()
    ]
    mentions_walk = any("walk" in p.lower() for p in phrases)
    if not mentions_walk:
        schools = [p for p in (walk_pois or []) if p.get("category") == "school"]
        if schools:
            nearest = min(schools, key=lambda p: p["walkMetres"])
            phrases.append(f"a {nearest['walkMetres']}-metre walk to {nearest['name']}")
    if not phrases:
        return None
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " and " + phrases[-1]


def run_once(client):
    sysdb = client["system_monitor"]
    gc = client["Gold_Coast"]
    col = sysdb["offmarket_intel"]
    pending = list(col.find({"status": "pending"}).sort("requested_at", 1).limit(10))
    for doc in pending:
        slug = doc.get("slug") or doc.get("_id")
        suburb = doc.get("suburb") or ""
        try:
            result, err = compute_intel(gc, suburb, slug)
            if err:
                col.update_one({"_id": doc["_id"]},
                               {"$set": {"status": "error", "error": err, "computed_at": _now(),
                                         "schema_version": INTEL_SCHEMA_VERSION}})
                print(f"[intel] {slug}: ERROR {err}")
            else:
                col.update_one({"_id": doc["_id"]},
                               {"$set": {"status": "done", "result": result, "computed_at": _now(),
                                         "schema_version": INTEL_SCHEMA_VERSION},
                                "$unset": {"error": ""}})
                sc = result["scarcity"]; cp = result["competition"]
                print(f"[intel] {slug}: active_match={sc['active_matching']}/{sc['active_total']} "
                      f"compete={cp['n_compete']}/{cp['n_total']}")
        except Exception as e:
            traceback.print_exc()
            col.update_one({"_id": doc["_id"]},
                           {"$set": {"status": "error", "error": str(e)[:300], "computed_at": _now(),
                                     "schema_version": INTEL_SCHEMA_VERSION}})
    return len(pending)


def run_once_positioning(client):
    """Same shape as run_once(), but for the slower/decoupled positioning
    queue. limit=1 — each request can take ~15s (Sonnet call included), and
    volume on this dormant-arm feature is near-zero, so there's no need to
    batch; keeping it to one at a time stops a slow positioning computation
    from starving the fast intel queue's 3s cadence for long."""
    sysdb = client["system_monitor"]
    gc = client["Gold_Coast"]
    col = sysdb["offmarket_positioning"]
    pending = list(col.find({"status": "pending"}).sort("requested_at", 1).limit(1))
    for doc in pending:
        slug = doc.get("slug") or doc.get("_id")
        suburb = doc.get("suburb") or ""
        try:
            result, err = compute_positioning(gc, suburb, slug)
            if err:
                col.update_one({"_id": doc["_id"]},
                               {"$set": {"status": "error", "error": err, "computed_at": _now(),
                                         "schema_version": POSITIONING_SCHEMA_VERSION}})
                print(f"[positioning] {slug}: ERROR {err}")
            else:
                col.update_one({"_id": doc["_id"]},
                               {"$set": {"status": "done", "result": result, "computed_at": _now(),
                                         "schema_version": POSITIONING_SCHEMA_VERSION},
                                "$unset": {"error": ""}})
                has_narrative = bool(result.get("narrative"))
                has_positioning = bool(result.get("positioning"))
                print(f"[positioning] {slug}: narrative={has_narrative} positioning={has_positioning}")
        except Exception as e:
            traceback.print_exc()
            col.update_one({"_id": doc["_id"]},
                           {"$set": {"status": "error", "error": str(e)[:300], "computed_at": _now(),
                                     "schema_version": POSITIONING_SCHEMA_VERSION}})
    return len(pending)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single pass then exit")
    ap.add_argument("--interval", type=int, default=POLL_SECONDS)
    ap.add_argument("--slug", help="compute a single slug ad-hoc (test) and print")
    ap.add_argument("--suburb", default="", help="suburb hint for --slug")
    ap.add_argument("--positioning", action="store_true", help="with --slug, compute positioning instead of intel")
    args = ap.parse_args()

    client = get_client()

    if args.slug:
        fn = compute_positioning if args.positioning else compute_intel
        result, err = fn(client["Gold_Coast"], args.suburb, args.slug)
        print("ERR:", err) if err else __import__("json").dump(result, sys.stdout, indent=2, default=str)
        print()
        return

    if args.once:
        n = run_once(client)
        n2 = run_once_positioning(client)
        print(f"[intel] processed {n} pending, [positioning] processed {n2} pending")
        return

    print(f"[intel] poller started (interval={args.interval}s)")
    while True:
        try:
            run_once(client)
            run_once_positioning(client)
        except Exception:
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
