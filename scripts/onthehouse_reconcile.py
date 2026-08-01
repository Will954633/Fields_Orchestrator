#!/usr/bin/env python3
"""onthehouse_reconcile.py — what each source sees, and where they disagree.

This is the job that makes the two-source setup safe to rely on. It never merges
anything: it measures coverage, and it QUARANTINES disagreements for a human.

Why quarantine rather than auto-merge: matched sale prices agreed on 539/554 pairs
(97%) when measured 2026-08-01. The interesting information is entirely in the 3% — an
auto-merge would pick a winner silently and destroy exactly the signal worth looking at.

Writes:
  system_monitor.onthehouse_coverage   one doc per run — the board
  system_monitor.onthehouse_conflicts  one doc per disagreeing address

Usage:
  python3 scripts/onthehouse_reconcile.py
  python3 scripts/onthehouse_reconcile.py --show
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client
from job_status import job_run
from onthehouse.matching import address_key
from onthehouse.suburbs import CORE

COVERAGE_COLL = "onthehouse_coverage"
CONFLICT_COLL = "onthehouse_conflicts"
WINDOW_START = "2025-08-01"
# Below this the two sources are quoting the same sale with rounding noise; above it
# they disagree about what the home sold for.
PRICE_TOLERANCE = 0.01
HOUSE = re.compile(r"^house$", re.I)


def _num(v):
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        digits = re.sub(r"[^0-9]", "", v)
        return int(digits) if digits else None
    return None


def domain_side(gc, sub: dict, sold: bool) -> dict:
    """{address_key: doc} of Domain-derived HOUSES for one suburb."""
    q = ({"listing_status": "sold", "sold_date": {"$gte": WINDOW_START}}
         if sold else {"listing_status": "for_sale"})
    out = {}
    for d in gc[sub["collection"]].find(q, {"address": 1, "street_address": 1,
                                            "full_address": 1, "property_type": 1,
                                            "sale_price": 1, "sold_date": 1}):
        if not HOUSE.match((d.get("property_type") or "").strip()):
            continue
        addr = d.get("street_address") or d.get("address") or d.get("full_address") or ""
        # suburb= is REQUIRED: many for-sale docs store no suburb in the address.
        k = address_key(addr, suburb=sub["suburb"])
        if k:
            out.setdefault(k, d)
    return out


def oth_side(sm, sub: dict, sold: bool) -> dict:
    coll = sm["onthehouse_sold" if sold else "onthehouse_listings"]
    q = {"suburb_key": sub["slug"]}
    if sold:
        q["sold_date"] = {"$gte": WINDOW_START}
    else:
        q["active"] = True
    out = {}
    for d in coll.find(q):
        out.setdefault(d["match_key"], d)
    return out


def reconcile(sm, gc) -> dict:
    now = datetime.now(timezone.utc)
    report = {"generated_at": now, "window_start": WINDOW_START, "suburbs": {},
              "totals": {}, "conflicts": 0}
    conflicts = []

    for kind, sold in (("for_sale", False), ("sold", True)):
        tot = {"domain": 0, "oth": 0, "matched": 0, "domain_only": 0, "oth_only": 0}
        for sub in CORE:
            dom, oth = domain_side(gc, sub, sold), oth_side(sm, sub, sold)
            both = set(dom) & set(oth)
            row = {"domain": len(dom), "oth": len(oth), "matched": len(both),
                   "domain_only": len(set(dom) - set(oth)),
                   "oth_only": len(set(oth) - set(dom))}
            row["union"] = row["domain"] + row["oth"] - row["matched"]
            row["domain_pct_of_union"] = round(100 * row["domain"] / row["union"]) if row["union"] else None
            report["suburbs"].setdefault(sub["slug"], {})[kind] = row
            for k in tot:
                tot[k] += row[k]

            if not sold:
                continue
            for key in both:
                dp, op = _num(dom[key].get("sale_price")), oth[key].get("sale_price")
                if not dp or not op:
                    continue
                if abs(dp - op) / max(dp, op) > PRICE_TOLERANCE:
                    conflicts.append({
                        "_id": key,
                        "address": oth[key].get("address") or dom[key].get("address"),
                        "suburb_key": sub["slug"],
                        "domain_price": dp, "onthehouse_price": op,
                        "diff": op - dp,
                        "diff_pct": round(100 * (op - dp) / dp, 2),
                        "domain_sold_date": dom[key].get("sold_date"),
                        "onthehouse_sold_date": oth[key].get("sold_date"),
                        "onthehouse_source": oth[key].get("sale_source"),
                        "detected_at": now, "resolved": False,
                    })
        tot["union"] = tot["domain"] + tot["oth"] - tot["matched"]
        tot["domain_pct_of_union"] = round(100 * tot["domain"] / tot["union"]) if tot["union"] else None
        report["totals"][kind] = tot

    report["conflicts"] = len(conflicts)
    for c in conflicts:
        sm[CONFLICT_COLL].update_one(
            {"_id": c["_id"]},
            {"$set": {k: v for k, v in c.items() if k != "_id"}},
            upsert=True)
    sm[COVERAGE_COLL].insert_one(dict(report))
    return report


def show(report):
    for kind in ("for_sale", "sold"):
        t = report["totals"][kind]
        print(f"\n{kind.upper()} — houses"
              + (f", sold since {report['window_start']}" if kind == "sold" else ""))
        print(f"  {'suburb':22s} {'Domain':>7} {'OTH':>6} {'match':>6} {'D-only':>7} {'O-only':>7} {'union':>6}")
        for slug, per in report["suburbs"].items():
            r = per[kind]
            print(f"  {slug:22s} {r['domain']:>7} {r['oth']:>6} {r['matched']:>6} "
                  f"{r['domain_only']:>7} {r['oth_only']:>7} {r['union']:>6}")
        print(f"  {'TOTAL':22s} {t['domain']:>7} {t['oth']:>6} {t['matched']:>6} "
              f"{t['domain_only']:>7} {t['oth_only']:>7} {t['union']:>6}")
        print(f"  Domain sees {t['domain_pct_of_union']}% of the union; "
              f"onthehouse adds {t['oth_only']} houses Domain does not have.")
    print(f"\nprice conflicts quarantined: {report['conflicts']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="print the latest stored report and exit")
    args = ap.parse_args()
    c = get_client()
    sm, gc = c["system_monitor"], c["Gold_Coast"]

    if args.show:
        r = sm[COVERAGE_COLL].find_one(sort=[("generated_at", -1)])
        if not r:
            print("no coverage report yet")
            return
        show(r)
        return

    with job_run("onthehouse_reconcile", cadence_hours=24,
                 title="onthehouse vs Domain Coverage + Conflicts") as beat:
        r = reconcile(sm, gc)
        show(r)
        fs, sd = r["totals"]["for_sale"], r["totals"]["sold"]
        beat.detail = (f"for-sale: Domain {fs['domain']}/{fs['union']} of union "
                       f"(+{fs['oth_only']} from onthehouse); "
                       f"sold: Domain {sd['domain']}/{sd['union']} (+{sd['oth_only']}); "
                       f"{r['conflicts']} price conflict(s) quarantined")
        beat.metrics = {"for_sale": fs, "sold": sd, "conflicts": r["conflicts"]}


if __name__ == "__main__":
    main()
