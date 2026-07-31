#!/usr/bin/env python3
"""
poi_rarity.py — PROTOTYPE: proximity as part of the combination match.

The production scarcity engine (scarcity_features.py) counts rarity on PHYSICAL
features only (bed/bath/land/floor/pool). This asks the next question Will
raised: of the homes that share your physical combination, how many ALSO share
your best lifestyle proximity — a park at the end of the street, a walk to
school, the beach around the corner?

Method (no divergence from the production number, no external API):
  1. Rebuild the EXACT physical $and clauses count_active_matches() uses.
  2. find() the physically-matching for-sale listings (not just count them).
  3. Compute each one's nearest-POI profile with the same resolve_nearby_pois
     used everywhere else (local haversine over the pre-harvested POI dataset).
  4. Count how many also clear the subject's proximity thresholds.

Output is a conditional rarity: "6 share your combination — only 2 are also
within a 5-minute walk of a park." That turns even a common physical combo into
a genuinely rarer one, honestly.

This is a standalone harness module — it does NOT modify scarcity_features.py.
Promotion into the production engine is a separate, deliberate step.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent.parent
sys.path.insert(0, str(ORCH))
sys.path.insert(0, str(ORCH / "scripts"))

from property_reports.scarcity_features import (  # noqa: E402
    _features_from_subject, identify_features, compute_cohort_medians,
    FEATURE_RULES, DEFAULT_CATCHMENT, _F,
)
from property_reports.nearby_pois import resolve_nearby_pois  # noqa: E402

# Proximity "rarity features" — walkable thresholds that genuinely differentiate
# a home. distance is straight-line metres (haversine), so phrasing stays honest
# ("within X of" / "this close to", never "a walk to" for the raw number).
# Tuple: (proximity_category, threshold_m, long_label, short_label)
POI_THRESH = {
    "beach":       ("beach", 1500, "within 1.5km of the beach", "the beach"),
    "school":      ("primary_school", 800, "within 800m of a primary school", "a school"),
    "park":        ("park", 400, "within 400m of a park", "a park"),
    "childcare":   ("childcare", 600, "within 600m of childcare", "childcare"),
    "cafe":        ("cafe", 450, "within 450m of a café", "a café"),
    "supermarket": ("supermarket", 1000, "within 1km of a supermarket", "a supermarket"),
}

# Story resonance — which proximities lead the cluster claim (beach/school/park
# read stronger than café/supermarket). Also the order we drop from if the full
# cluster intersects to zero: least-resonant goes first.
RESONANCE = ["beach", "school", "park", "childcare", "cafe", "supermarket"]


def _coords(doc):
    gc_coords = doc.get("geocoded_coordinates") or {}
    lat = doc.get("LATITUDE", doc.get("latitude", gc_coords.get("latitude")))
    lon = doc.get("LONGITUDE", doc.get("longitude", gc_coords.get("longitude")))
    return lat, lon


def _poi_profile(lat, lon, gc):
    """Boolean proximity feature set at the thresholds above, + the distances."""
    if lat is None or lon is None:
        return {}, {}
    try:
        prox = resolve_nearby_pois(lat, lon, gc)
    except Exception:
        return {}, {}
    feats, dists = {}, {}
    for key, (cat, thr, _long, _short) in POI_THRESH.items():
        d = (prox.get(cat) or {}).get("distance_m")
        feats[key] = bool(d and d <= thr)
        if d:
            dists[key] = d
    return feats, dists


def _join(labels):
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def compute_poi_rarity(subject, gc, catchment=None, min_pool=1):
    """Returns the conditional-rarity structure, or None if not computable."""
    features_basic = _features_from_subject(subject)
    if not features_basic:
        return None
    catch = catchment or DEFAULT_CATCHMENT
    cohort = compute_cohort_medians(gc, catch)
    anchors, _diffs = identify_features(features_basic, cohort)

    # Rebuild the physical match clauses exactly as count_active_matches does.
    rule_by_key = {r["key"]: r for r in FEATURE_RULES}
    and_clauses = []
    for a in anchors:
        rule = rule_by_key.get(a["key"])
        if not rule:
            continue
        try:
            clause = rule["count_clause"](features_basic)
        except Exception:
            clause = None
        if clause:
            and_clauses.append(clause)
    if not and_clauses:
        return None

    # Subject's own proximity profile, ordered by story resonance.
    slat, slon = _coords(subject)
    subj_feats, subj_dists = _poi_profile(slat, slon, gc)
    subject_has = [k for k in RESONANCE if subj_feats.get(k)]
    if not subject_has:
        return None

    base = {"listing_status": "for_sale", f"{_F}.bedrooms": {"$exists": True}}
    proj = {"LATITUDE": 1, "LONGITUDE": 1, "latitude": 1, "longitude": 1,
            "geocoded_coordinates": 1, "_id": 0}

    # Scan the physically-matching pool once; record which of the subject's
    # proximity features each home also satisfies (kept in memory so we can
    # intersect any sub-cluster without re-querying).
    physical_matching = 0
    home_sets = []          # per matching home: set of subject features it shares
    per_feature = {k: 0 for k in subject_has}
    for suburb in catch:
        try:
            coll = gc[suburb]
        except Exception:
            continue
        try:
            cursor = coll.find({**base, "$and": and_clauses}, proj)
        except Exception:
            continue
        for d in cursor:
            physical_matching += 1
            dlat, dlon = _coords(d)
            dfeats, _ = _poi_profile(dlat, dlon, gc)
            sat = {k for k in subject_has if dfeats.get(k)}
            home_sets.append(sat)
            for k in sat:
                per_feature[k] += 1

    if physical_matching < min_pool:
        return None

    def cluster_count(feats):
        fs = set(feats)
        return sum(1 for h in home_sets if fs.issubset(h))

    # Build the richest honest cluster: take the subject's whole walkable set
    # (capped at 4 for readability, resonance-ordered), then drop the
    # least-resonant feature until the intersection is non-empty.
    cluster = subject_has[:4]
    while len(cluster) >= 2 and cluster_count(cluster) == 0:
        cluster = cluster[:-1]
    cluster_matching = cluster_count(cluster)

    per_feature_out = [
        {"feature": k, "label": POI_THRESH[k][2], "short": POI_THRESH[k][3],
         "distance_m": subj_dists.get(k), "matching": per_feature[k],
         "share_pct": round(100 * per_feature[k] / physical_matching, 1) if physical_matching else None}
        for k in subject_has
    ]

    return {
        "physical_matching": physical_matching,
        "subject_has": subject_has,
        "features": per_feature_out,
        "cluster": {
            "features": cluster,
            "labels": [POI_THRESH[k][3] for k in cluster],
            "phrase": _join([POI_THRESH[k][3] for k in cluster]),
            "matching": cluster_matching,
            "share_pct": round(100 * cluster_matching / physical_matching, 1) if physical_matching else None,
        },
    }
