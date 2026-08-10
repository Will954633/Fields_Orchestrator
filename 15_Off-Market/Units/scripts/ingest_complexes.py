#!/usr/bin/env python3
"""ingest_complexes.py — build the COMPLEX entity for attached dwellings. (Plan E1/E4)

For a house the unit of analysis is the lot. For a unit it is the scheme: the same
2-bed in the same building is a near-identical substitute in a way no detached house
ever is. Measured on our own data, $/m2 dispersion inside a complex is 11.2% against
27.0% across a suburb, and same-complex same-bed floor-area imputation is 5.2% median
error against 15.9% suburb-wide. So the complex is what the unit page should be built
on, and this is the collection that makes that possible.

SOURCE — Queensland cadastre, CC-BY 4.0, commercially republishable with attribution.
    .../PlanningCadastre/LandParcelPropertyFramework/MapServer/4  (Cadastral parcels)

FIELD NAMES ARE NOT THE OBVIOUS ONES. Verified live 2026-08-10; the research that
proposed this named them wrongly and would have produced a silent zero:

    complex name    -> feat_name       (NOT complex_name)
    CTS / CMS no.   -> alias_name      (NOT cms_number)
    join key        -> lotplan          = our LOT + PLAN concatenated
    lot area        -> lot_area         lot "0" is COMMON PROPERTY, not a dwelling

TWO TRAPS THAT COST TIME:
  * `locality` is TITLE CASE. locality='ROBINA' returns 0 rows and no error - a silent
    false absence, the exact Rule 8 failure mode. Use UPPER(locality)=...
  * `feat_name` on unscoped rows is mostly ROAD names (Pacific Highway). It only means
    "complex" once scoped to strata plans. Always filter the plan prefix.
  * Layer 10 "Strata Parcels Only" is NOT community-title lots (Robina returns 59).
    It means volumetric parcels. The unit stock is layer 4 + a plan prefix.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.db import get_client                    # noqa: E402
from scripts.job_status import job_run              # noqa: E402

SERVICE = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
           "PlanningCadastre/LandParcelPropertyFramework/MapServer/4/query")
UA = {"User-Agent": "FieldsEstate/1.0 (property research; will@fieldsestate.com.au)"}
PAGE = 2000

SUBURBS = {"robina": "Robina", "varsity_lakes": "Varsity Lakes",
           "burleigh_waters": "Burleigh Waters"}

# BUP = Building Units Plan  - a building with common property; lift plausible.
# GTP = Group Titles Plan    - villa / townhouse group, ground level.
# SP  = Survey Plan          - modern, used for BOTH strata and freehold subdivision,
#                              so it is kept but never treated as proof of attachment.
SUBTYPE = {"BUP": "building_units", "GTP": "group_title", "SP": "survey_plan"}


def _get(params, retries=4):
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            if a == retries - 1:
                raise
            time.sleep(2 * (a + 1))
            print(f"    retry {a+1}: {type(e).__name__}", file=sys.stderr)


def fetch_parcels(locality: str):
    """Every strata-plan parcel in a locality. Pages until the server stops
    flagging exceededTransferLimit — never trusts a single page to be complete."""
    where = (f"UPPER(locality)='{locality.upper()}' AND ("
             "plan LIKE 'BUP%' OR plan LIKE 'GTP%' OR plan LIKE 'SP%')")
    out, offset = [], 0
    while True:
        d = _get({"where": where,
                  "outFields": "lotplan,lot,plan,feat_name,alias_name,lot_area,locality",
                  "returnGeometry": "false", "resultOffset": offset,
                  "resultRecordCount": PAGE, "f": "json"})
        if "error" in d:
            raise RuntimeError(f"ArcGIS error for {locality}: {d['error']}")
        feats = [f["attributes"] for f in (d.get("features") or [])]
        out += feats
        if not d.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
        print(f"    {locality}: {len(out)} parcels…", file=sys.stderr)
    return out


def build_complexes(parcels, suburb_key):
    """Group parcels into schemes. The scheme is the PLAN, not the CMS — one CMS can
    span several plans in a layered arrangement, but every lot sits in exactly one
    plan, and the plan is what our own documents carry."""
    by_plan = defaultdict(list)
    for p in parcels:
        plan = (p.get("plan") or "").strip().upper()
        if plan:
            by_plan[plan].append(p)

    docs = []
    for plan, rows in by_plan.items():
        m = re.match(r"^([A-Z]+)", plan)
        pre = m.group(1) if m else ""
        # lot "0" is common property, not a dwelling. Counting it as a lot would
        # inflate every scheme by one and make a duplex look like a triplex.
        lots = [r for r in rows if str(r.get("lot") or "").strip() not in ("0", "")]
        common = [r for r in rows if str(r.get("lot") or "").strip() == "0"]
        areas = sorted(a for a in (r.get("lot_area") for r in lots) if a and a > 0)
        names = {(r.get("feat_name") or "").strip() for r in rows if r.get("feat_name")}
        cms = {(r.get("alias_name") or "").strip() for r in rows if r.get("alias_name")}
        docs.append({
            "_id": f"{suburb_key}:{plan}",
            "plan": plan,
            "plan_prefix": pre,
            "subtype": SUBTYPE.get(pre, "unknown"),
            "suburb_key": suburb_key,
            "cms_number": sorted(cms)[0] if cms else None,
            "complex_name": sorted(names)[0] if names else None,
            "lot_count": len(lots),
            "common_property_sqm": round(sum(r.get("lot_area") or 0 for r in common)) or None,
            "lot_area_median_sqm": areas[len(areas) // 2] if areas else None,
            "lot_area_min_sqm": areas[0] if areas else None,
            "lot_area_max_sqm": areas[-1] if areas else None,
            "source": "qld_cadastre_layer4",
            "source_licence": "CC-BY 4.0 — © State of Queensland (Department of Resources)",
        })
    return docs


def link_properties(gc, suburb_key, complexes):
    """Stamp complex_plan onto each property via LOT+PLAN. Reports how many of OUR
    documents actually matched — a link rate is the only way to tell 'no complexes
    here' from 'the join key is wrong'."""
    from pymongo import UpdateOne
    by_plan = {c["plan"]: c for c in complexes}
    linked = missed = 0
    coll = gc[suburb_key]
    ops = []

    def flush():
        # Cosmos is RU-limited, not CPU-limited (~5000 RU/s burst). One update_one per
        # document over ~20k docs exhausts the budget and 16500s; batched bulk_write
        # with a small chunk keeps it inside. See CLAUDE.md "Cosmos DB 16500".
        nonlocal ops
        if ops:
            coll.bulk_write(ops, ordered=False)
            ops = []

    for d in coll.find({"PLAN": {"$exists": True, "$ne": None}}, {"PLAN": 1}):
        plan = str(d.get("PLAN") or "").strip().upper()
        c = by_plan.get(plan)
        if not c:
            missed += 1
            continue
        ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {
            "complex_plan": c["plan"],
            "complex_cms": c["cms_number"],
            "complex_name_cadastre": c["complex_name"],
            "complex_lot_count": c["lot_count"],
            "complex_subtype": c["subtype"],
        }}))
        linked += 1
        if len(ops) >= 250:
            flush()
    flush()
    return linked, missed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", help="one suburb key; default all three")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets = ({args.suburb: SUBURBS[args.suburb]} if args.suburb else SUBURBS)

    with job_run("units_complex_ingest", cadence_hours=168,
                 title="Units — QLD complex/scheme ingest") as beat:
        gc = get_client()["Gold_Coast"]
        total_c = total_linked = total_parcels = 0
        per = {}
        for key, locality in targets.items():
            parcels = fetch_parcels(locality)
            comps = build_complexes(parcels, key)
            total_parcels += len(parcels)
            named = sum(1 for c in comps if c["complex_name"])
            withcms = sum(1 for c in comps if c["cms_number"])
            print(f"  {key}: {len(parcels)} parcels -> {len(comps)} schemes "
                  f"({named} named, {withcms} with CMS)")
            if not args.dry_run:
                col = gc["complexes"]
                for c in comps:
                    col.update_one({"_id": c["_id"]}, {"$set": c}, upsert=True)
                linked, missed = link_properties(gc, key, comps)
                print(f"    linked {linked} property docs ({missed} no matching scheme)")
                total_linked += linked
            total_c += len(comps)
            per[key] = {"parcels": len(parcels), "schemes": len(comps), "named": named}

        beat.metrics = {"schemes": total_c, "linked": total_linked,
                        "parcels": total_parcels, **{f"{k}_schemes": v["schemes"]
                                                     for k, v in per.items()}}
        beat.detail = f"{total_c} schemes, {total_linked} properties linked"

        # Rule 7b — an empty result where input existed is a failure, not an empty
        # queue. The cadastre is a static public dataset; zero parcels means the
        # service changed or the query broke, never that the suburbs emptied.
        if total_parcels == 0:
            raise RuntimeError("0 parcels returned from the QLD cadastre — the service "
                               "or the query is broken, not the data")
        if total_c == 0:
            raise RuntimeError(f"{total_parcels} parcels but 0 schemes built — grouping is broken")
        if not args.dry_run and total_linked == 0:
            raise RuntimeError(f"{total_c} schemes built but 0 property documents linked — "
                               "the LOT/PLAN join key is wrong")
    return 0


if __name__ == "__main__":
    sys.exit(main())
