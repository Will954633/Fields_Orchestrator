#!/usr/bin/env python3
"""
sample_context.py — sample-relative positioning context for a subject property.

We never had a census of all sold homes — only what we scraped from Domain, and
of that, a labelled indicative sample (system_monitor.sample_manifest). So every
rarity statement is framed RELATIVE to that disclosed sample:
  - where the subject sits vs the typical sampled home (percentile), and
  - what share of the sample shares the subject's standout feature combination.

We deliberately do NOT produce "only K homes" census counts.

Consumed by verify_claim.py and the appraisal/mini-site scarcity generators.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared.db import get_client  # noqa: E402

# n below which a percentage is too small to be meaningful — flag, don't claim.
MIN_COHORT_N = 20
CONTINUOUS = ["land_size_sqm", "floor_area_sqm", "bedrooms", "bathrooms"]


def latest_manifest(client=None) -> Dict[str, Any]:
    client = client or get_client()
    m = client["system_monitor"]["sample_manifest"].find_one(sort=[("created_at", -1)])
    if not m:
        raise SystemExit("No sample_manifest — run build_positioning_sample.py first.")
    return m


def _cohort(client, suburb: Optional[str], same_type: Optional[str]) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"in_sample": True}
    if suburb:
        q["suburb"] = suburb
    if same_type:
        # House-vs-house comparison: bucket the subject's type against like types.
        houses = {"House", "Duplex", "Semi-Detached"}
        q["property_type"] = {"$in": list(houses)} if same_type in houses \
            else {"$nin": list(houses)}
    return list(client["Gold_Coast"]["property_attributes"].find(q))


def _percentile(cohort_vals: List[float], v: float) -> Optional[float]:
    vals = [x for x in cohort_vals if x is not None]
    if not vals:
        return None
    below = sum(1 for x in vals if x <= v)
    return round(100.0 * below / len(vals), 1)


def compute_context(subject_attrs: Dict[str, Any],
                    subject_hits: List[Dict[str, str]],
                    suburb: str,
                    same_type: Optional[str] = None,
                    client=None) -> Dict[str, Any]:
    """Return a disclosed, sample-relative context block for the subject.

    If the subject's own suburb is not covered by the sample (sample is core-3
    only), or the suburb cohort is too small to be meaningful, fall back to the
    whole indicative sample (southern Gold Coast) and disclose that scope."""
    client = client or get_client()
    manifest = latest_manifest(client)
    cohort = _cohort(client, suburb, same_type)
    cohort_scope = suburb
    if len(cohort) < MIN_COHORT_N:
        cohort = _cohort(client, None, same_type)   # catchment-wide sample
        cohort_scope = None
    n = len(cohort)

    # Position vs the typical sampled home on each continuous attribute.
    positions: Dict[str, Any] = {}
    for attr in CONTINUOUS:
        sv = subject_attrs.get(attr)
        if sv is None:
            continue
        pct = _percentile([c["attributes"].get(attr) for c in cohort], sv)
        if pct is not None:
            positions[attr] = {
                "subject_value": sv,
                "percentile": pct,                  # subject ≥ pct% of sampled homes
                "larger_than_pct": pct,
                "cohort_n": sum(1 for c in cohort if c["attributes"].get(attr) is not None),
            }

    # Share of the sample carrying the subject's full standout stack.
    hit_keys = {h["key"] for h in subject_hits}
    members_matching: List[str] = []
    if hit_keys:
        for c in cohort:
            ck = {h["key"] for h in c.get("scarcity_hits", [])}
            if hit_keys.issubset(ck):
                members_matching.append(c.get("address") or c.get("source_id"))
    share_pct = round(100.0 * len(members_matching) / n, 1) if n else None

    return {
        "cohort": {
            "suburb": cohort_scope,
            "scope_label": (cohort_scope.replace("_", " ").title()
                            if cohort_scope else "southern Gold Coast"),
            "same_type_bucket": same_type,
            "n": n,
            "window_start": manifest["window_start"],
            "as_of": manifest["as_of"],
            "source": manifest["source"],
            "sample_id": manifest["sample_id"],
        },
        "positions": positions,
        "feature_stack": {
            "keys": sorted(hit_keys),
            "labels": [h["label"] for h in subject_hits],
            "share_pct_of_sample": share_pct,
            "members_matching": members_matching,
            "meaningful": n >= MIN_COHORT_N,
            "caveat": None if n >= MIN_COHORT_N else
                      f"Cohort n={n} is small; treat share as directional only.",
        },
    }


def phrase(context: Dict[str, Any]) -> List[str]:
    """Render context into compliant, sample-disclosed sentences (no census counts,
    no advice/predictions). Suburbs capitalised; sample always named."""
    c = context["cohort"]
    base = (f"our indicative sample of {c['n']} sold {c['scope_label']} properties "
            f"(Domain-scraped, {c['window_start']} to {c['as_of']})")
    out: List[str] = []
    fs = context["feature_stack"]
    if fs["labels"]:
        combo = " + ".join(fs["labels"])
        if fs["share_pct_of_sample"] is not None and fs["meaningful"]:
            out.append(f"Within {base}, {fs['share_pct_of_sample']}% combined {combo}.")
        elif fs["share_pct_of_sample"] is not None:
            out.append(f"Within {base}, {len(fs['members_matching'])} of {c['n']} combined "
                       f"{combo} ({fs['caveat']}).")
    label_map = {"land_size_sqm": "land size", "floor_area_sqm": "internal floor area",
                 "bedrooms": "bedroom count", "bathrooms": "bathroom count"}
    for attr, p in context["positions"].items():
        label = label_map.get(attr, attr.replace("_", " "))
        out.append(f"On {label}, this property sits above {p['larger_than_pct']}% of {base}.")
    return out
