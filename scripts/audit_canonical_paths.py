#!/usr/bin/env python3
"""
audit_canonical_paths.py — check `config/canonical_attributes.yaml` against reality.

WHY (2026-08-06). The config declares an ordered `source_priority` per attribute
and the resolver takes the first present value. But nothing ever verified that
the declared paths EXIST in the data, or that the ones lower down the chain agree
with the ones above. They had drifted:

  * `bathrooms` declared ONE path. 56% of the missing values were sitting in
    `scraped_data_v2.bathrooms`, undeclared.
  * `bedrooms` likewise — 72% of 4,941 nulls were recoverable, undeclared.

A missing bedroom count is not cosmetic: it returns `None` from the competitor
matcher, collapses the scarcity anchor stack, and (until fixed the same day) made
the valuation engine treat the home as having zero bedrooms.

This reports, per attribute per declared path:
  * coverage — how often the path holds a usable value
  * agreement — where two paths both hold a value, how often they match
  * dead paths — declared but never present anywhere (config rot)
  * undeclared — paths NOT in the config that hold values the config would miss

    python3 scripts/audit_canonical_paths.py
    python3 scripts/audit_canonical_paths.py --suburb robina --limit 800
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
import yaml
from dotenv import load_dotenv

from src.mongo_client_factory import get_mongo_client

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
CONFIG = "/home/fields/Fields_Orchestrator/config/canonical_attributes.yaml"

# Paths that exist in the data but may not be declared. Kept here so the audit
# can flag config rot in BOTH directions.
KNOWN_EXTRA = {
    "bedrooms": ["scraped_data_apr01_recovered.features.bedrooms", "enriched_data.bedrooms"],
    "bathrooms": ["scraped_data_apr01_recovered.features.bathrooms"],
    "land_size_sqm": ["scraped_data_v2.land_size", "scraped_data.features.land_size"],
    "floor_area_sqm": ["internal_living_area_sqm", "scraped_data_v2.floor_area"],
    "pool_present": ["valuation_data.subject_property.features.basic.pool_present"],
}


def dig(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def usable(v):
    if v is None or isinstance(v, bool):
        return isinstance(v, bool)
    return isinstance(v, (int, float)) or (isinstance(v, str) and v.strip() != "")


def norm(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    return str(v).strip().lower()


def differs(a, b, tol=0.02):
    """Numeric values within `tol` relative are the SAME fact rounded differently.
    An exact-match test flags lot_size_sqm vs lot_size_calc_sqm as 99% disagreement
    when the median difference is 0.1% — that noise buries the real conflicts."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        if a == 0 and b == 0:
            return False
        return abs(a - b) / max(abs(a), abs(b), 1e-9) > tol
    return a != b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--limit", type=int, default=600)
    args = ap.parse_args()

    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    cfg = yaml.safe_load(open(CONFIG))
    gc = get_mongo_client()["Gold_Coast"]
    subs = [args.suburb] if args.suburb else SUBURBS

    docs = []
    for s in subs:
        docs += list(gc[s].find({"property_type": "House"}).limit(args.limit))
    print(f"canonical_attributes.yaml v{cfg.get('schema_version')} — audited against "
          f"{len(docs):,} House docs in {', '.join(subs)}\n")

    problems = []
    for attr, spec in (cfg.get("attributes") or {}).items():
        paths = [p["path"] for p in (spec.get("source_priority") or [])]
        extra = [p for p in KNOWN_EXTRA.get(attr, []) if p not in paths]
        cover = Counter()
        vals_by_doc = []
        for d in docs:
            row = {}
            for p in paths + extra:
                v = dig(d, p)
                if usable(v):
                    cover[p] += 1
                    row[p] = norm(v)
            vals_by_doc.append(row)

        n = len(docs)
        resolved = sum(1 for r in vals_by_doc if any(p in r for p in paths))
        would_gain = sum(1 for r in vals_by_doc
                         if not any(p in r for p in paths) and any(p in r for p in extra))
        print(f"{attr}")
        print(f"   resolves from declared chain : {resolved:>5,}/{n:,} ({resolved/n*100:5.1f}%)")
        for p in paths:
            flag = "  ← DEAD, never present" if cover[p] == 0 else ""
            print(f"     {p:<52} {cover[p]:>5,} ({cover[p]/n*100:5.1f}%){flag}")
            if cover[p] == 0:
                problems.append(f"{attr}: declared path never present — {p}")
        for p in extra:
            if cover[p]:
                print(f"     {p:<52} {cover[p]:>5,} ({cover[p]/n*100:5.1f}%)  ← UNDECLARED")
        if would_gain:
            print(f"   ⚠ undeclared paths would resolve {would_gain} more ({would_gain/n*100:.1f}%)")
            problems.append(f"{attr}: {would_gain} docs resolvable only from undeclared paths")

        # agreement between the top declared path and each lower one
        top = paths[0] if paths else None
        for p in paths[1:] + extra:
            both = [(r[top], r[p]) for r in vals_by_doc if top in r and p in r]
            if len(both) >= 20:
                dis = sum(1 for a, b in both if differs(a, b))
                mark = "  ⚠" if dis / len(both) > 0.10 else ""
                print(f"       vs {top}: agree "
                      f"{(1-dis/len(both))*100:5.1f}% of {len(both):,}{mark}")
                if dis / len(both) > 0.10:
                    problems.append(f"{attr}: {p} disagrees with {top} on "
                                    f"{dis/len(both)*100:.0f}% of {len(both)} docs")
        print()

    print("=" * 72)
    if problems:
        print(f"{len(problems)} issue(s):\n")
        for x in problems:
            print(f"  · {x}")
    else:
        print("No config drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
