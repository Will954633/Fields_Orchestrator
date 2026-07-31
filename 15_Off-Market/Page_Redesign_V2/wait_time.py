#!/usr/bin/env python3
"""
wait_time.py — PROTOTYPE: "how long until a home like this comes up again?"

Rarity across SPACE (how many homes share the combination right now) is what the
scarcity engine and poi_rarity answer. This answers rarity across TIME: given the
subject's combination, how often does one actually come to market? We count homes
matching the combination that SOLD in a trailing window, turn that into an
arrival rate, and express it as a typical interval between listings.

It mirrors the home's real rarity story so we never overclaim:
  * physically-rare home  -> count on the physical combination
  * common-but-cluster-rare -> count on physical ∩ the POI lifestyle cluster
  * genuinely common home -> returns None (it comes up often; no wait story)

Honesty:
  * Sold VOLUME is our least-reliable figure (Domain under-captures ~40-50% vs
    PropRadar). Under-capture means the TRUE arrival rate is HIGHER and the true
    wait SHORTER — so our number is a conservative-LONG estimate. We say "tracked"
    and carry a disclaimer (Will, 2026-07-30). Counts are exact tracked facts;
    the interval is hedged and stated as an OBSERVED past pattern, not a forecast
    (editorial: no predictions, no advice).
  * Matches sold docs on their well-populated TOP-LEVEL fields (bedrooms,
    bathrooms, land_size_sqm, floor_area_sqm — ~97% coverage) rather than the
    _F engine fields (11% on sold), so the count isn't starved.

Standalone harness module — does not touch production.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

from property_reports.scarcity_features import DEFAULT_CATCHMENT  # noqa: E402
from poi_rarity import _coords, _poi_profile, _join, POI_THRESH  # noqa: E402

# Only surface a wait story when the combination is genuinely uncommon on the
# ground — at most this many tracked arrivals per year (=> interval >= ~2 months).
MAX_ARRIVALS_PER_YEAR = 6


def _band_down(v, step=50):
    try:
        return int(v) // step * step
    except Exception:
        return None


def _physical_query(feat, cutoff):
    q = {
        "listing_status": "sold",
        "bedrooms": {"$gte": feat["bedrooms"]},
        "$and": [{"$or": [{"sold_date": {"$gte": cutoff}}, {"sale_date": {"$gte": cutoff}}]}],
    }
    land_band = _band_down(feat.get("land_sqm"))
    if land_band:
        q["$and"].append({"$or": [{"land_size_sqm": {"$gte": land_band}},
                                  {"lot_size_sqm": {"$gte": land_band}}]})
    if feat.get("bathrooms") and feat["bathrooms"] >= 2:
        q["bathrooms"] = {"$gte": feat["bathrooms"]}
    floor_band = _band_down(feat.get("floor_sqm"), 10)
    if floor_band:
        q["floor_area_sqm"] = {"$gte": floor_band}
    return q, land_band


def _interval_phrase(arrivals, months):
    if arrivals <= 0:
        return f"we tracked none coming up in the past {months} months", None
    per_year = arrivals * 12 / months
    if per_year <= 1.3:
        return "about once a year", 12
    if per_year <= 2.5:
        return "about twice a year", 6
    every = max(2, round(12 / per_year))
    return f"about every {every} months", every


def compute_wait_time(subject, gc, subject_feat, cluster_features=None,
                      months=12, catchment=None):
    feat = subject_feat or {}
    if not feat.get("bedrooms"):
        return None
    catch = catchment or DEFAULT_CATCHMENT
    cutoff = (date.today() - timedelta(days=int(30.4 * months))).isoformat()
    query, land_band = _physical_query(feat, cutoff)

    # Physical arrivals (fast count).
    physical = 0
    for s in catch:
        try:
            physical += gc[s].count_documents(query)
        except Exception:
            pass

    # Cluster arrivals — physical ∩ the subject's POI lifestyle cluster.
    cluster_arrivals = None
    if cluster_features:
        cf = set(cluster_features)
        cluster_arrivals = 0
        proj = {"LATITUDE": 1, "LONGITUDE": 1, "latitude": 1, "longitude": 1,
                "geocoded_coordinates": 1, "_id": 0}
        for s in catch:
            try:
                cur = gc[s].find(query, proj)
            except Exception:
                continue
            for d in cur:
                lat, lon = _coords(d)
                dfeats, _ = _poi_profile(lat, lon, gc)
                if cf.issubset({k for k, v in dfeats.items() if v}):
                    cluster_arrivals += 1

    # Choose the combination that both matches the rarity story AND is rare
    # enough to be a "wait": physical if already rare, else the cluster.
    per_year_phys = physical * 12 / months
    used, arrivals, combo = None, None, None
    if per_year_phys <= MAX_ARRIVALS_PER_YEAR:
        used, arrivals = "physical", physical
        combo = _physical_phrase(feat, land_band)
    elif cluster_arrivals is not None and (cluster_arrivals * 12 / months) <= MAX_ARRIVALS_PER_YEAR:
        used, arrivals = "cluster", cluster_arrivals
        combo = _physical_phrase(feat, land_band) + " " + _cluster_phrase(cluster_features)
    if used is None:
        return None  # comes up often — no honest wait story

    phrase, interval_months = _interval_phrase(arrivals, months)
    return {
        "used": used,
        "arrivals": arrivals,
        "window_months": months,
        "per_year": round(arrivals * 12 / months, 1),
        "interval_phrase": phrase,
        "interval_months": interval_months,
        "combo_phrase": combo,
        "physical_arrivals": physical,
        "cluster_arrivals": cluster_arrivals,
    }


def _physical_phrase(feat, land_band):
    p = f"{feat['bedrooms']}-bedroom homes"
    if land_band:
        p += f" on {land_band:,}m²+ blocks"
    if feat.get("pool"):
        p += " with a pool"
    return p


def _cluster_phrase(cluster_features):
    labels = [POI_THRESH[k][3] for k in cluster_features if k in POI_THRESH]
    return "within reach of " + _join(labels) if labels else ""
