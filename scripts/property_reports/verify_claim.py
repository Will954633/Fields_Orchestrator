#!/usr/bin/env python3
"""
verify_claim.py — show the evidence behind any scarcity / positioning statement,
and prove it is reproducible.

This is what converts "we think it's rare" into "here is where every number came
from, here is the sample it's measured against, and here are the homes behind the
percentage." Three modes:

  --address "X"               Evidence chain: every canonical attribute with its
                              value, source field, method, model, confidence, date.

  --scarcity --address "X"    Sample-relative context: the disclosed sample (N,
                              suburb, window, source), the subject's percentile vs
                              the typical sampled home, the % of the sample sharing
                              the standout feature stack, and the member addresses
                              behind that %. Prints compliant draft sentences.

  --reproduce --address "X"   Re-resolve from current source docs and diff against
                              the stored golden record (confirms reproducibility,
                              flags drift).

Usage:
  python3 scripts/property_reports/verify_claim.py --address "39 Manakin Avenue, Burleigh Waters QLD 4220"
  python3 scripts/property_reports/verify_claim.py --scarcity --address "39 Manakin Avenue, Burleigh Waters QLD 4220"
  python3 scripts/property_reports/verify_claim.py --reproduce --address "39 Manakin Avenue, Burleigh Waters QLD 4220"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared.db import get_client, get_gold_coast_db  # noqa: E402
from scripts.property_reports import canonical_resolver as cr  # noqa: E402
from scripts.property_reports import sample_context as sc  # noqa: E402

CORE = ["robina", "burleigh_waters", "varsity_lakes"]


def _find(db, address: str, slug: Optional[str]):
    key, val = ("url_slug", slug) if slug else ("address", address)
    for suburb in CORE:
        d = db[suburb].find_one({key: val})
        if d:
            return suburb, d
    return None, None


def _golden(client, source_id: str) -> Optional[Dict[str, Any]]:
    return client["Gold_Coast"]["property_attributes"].find_one({"source_id": source_id})


def show_evidence(rec: Dict[str, Any]) -> None:
    print(f"\nEVIDENCE CHAIN — {rec['address']}  [{rec['suburb']}]")
    print(f"  schema v{rec['schema_version']}  resolved {rec['resolved_at']}  "
          f"in_sample={rec['in_sample']}  hash={rec['content_hash'][:12]}")
    print(f"  {'attribute':20} {'value':>10}   {'conf':>4}  method / source")
    for a, v in rec["attributes"].items():
        p = rec["provenance"][a]
        note = f"  [{p['note']}]" if p.get("note") else ""
        print(f"  {a:20} {str(v):>10}   {p['confidence']:>4}  "
              f"{p['method']} ({p['source_field']}){note}")
    print(f"  scarcity hits: {[h['key'] for h in rec['scarcity_hits']]}")


def show_scarcity(rec: Dict[str, Any], client) -> None:
    ctx = sc.compute_context(rec["attributes"], rec["scarcity_hits"],
                             suburb=rec["suburb"], same_type=rec.get("property_type"),
                             client=client)
    c = ctx["cohort"]
    print(f"\nSAMPLE-RELATIVE CONTEXT — {rec['address']}")
    print(f"  Cohort: {c['n']} sampled sold properties in {c['suburb']} "
          f"({c['window_start']} → {c['as_of']})")
    print(f"  Source: {c['source']}  | manifest {c['sample_id']}")
    print("\n  Position vs the typical sampled home:")
    for attr, p in ctx["positions"].items():
        print(f"    {attr:18} = {p['subject_value']:>8}  → above {p['larger_than_pct']}% "
              f"(n={p['cohort_n']})")
    fs = ctx["feature_stack"]
    print(f"\n  Standout stack: {fs['labels']}")
    if fs["share_pct_of_sample"] is not None:
        print(f"    {fs['share_pct_of_sample']}% of the sample share this full combination "
              f"({len(fs['members_matching'])}/{c['n']})")
        if not fs["meaningful"]:
            print(f"    ⚠ {fs['caveat']}")
        if fs["members_matching"]:
            print("    Members behind that share:")
            for m in fs["members_matching"][:25]:
                print(f"      - {m}")
    print("\n  Compliant draft sentences (sample disclosed, no census counts):")
    for s in sc.phrase(ctx):
        print(f"    • {s}")


def reproduce(rec_stored: Dict[str, Any], db, client) -> None:
    suburb = rec_stored["suburb"]
    doc = db[suburb].find_one({"_id": ObjectId(rec_stored["source_id"])})
    fresh = cr.build_record(doc, suburb, cr.load_spec(), rec_stored.get("in_sample", False))
    print(f"\nREPRODUCE — {rec_stored['address']}")
    print(f"  stored hash: {rec_stored['content_hash'][:16]}")
    print(f"  fresh  hash: {fresh['content_hash'][:16]}")
    if fresh["content_hash"] == rec_stored["content_hash"]:
        print("  ✓ identical — fully reproducible from current source docs")
        return
    print("  ✗ drift detected:")
    for a in fresh["attributes"]:
        if fresh["attributes"][a] != rec_stored["attributes"].get(a):
            print(f"    {a}: stored={rec_stored['attributes'].get(a)} → fresh={fresh['attributes'][a]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address")
    ap.add_argument("--slug")
    ap.add_argument("--scarcity", action="store_true")
    ap.add_argument("--reproduce", action="store_true")
    args = ap.parse_args()
    if not (args.address or args.slug):
        ap.error("provide --address or --slug")

    db = get_gold_coast_db()
    client = get_client()
    suburb, doc = _find(db, args.address, args.slug)
    if not doc:
        print("Property not found in core suburbs.")
        return 1

    rec = _golden(client, str(doc["_id"]))
    if not rec:
        # Resolve live (subject may be off-market / outside the sample).
        rec = cr.build_record(doc, suburb, cr.load_spec(), in_sample=False)
        print("(no stored golden record — resolved live)")

    if args.reproduce:
        reproduce(rec, db, client)
    elif args.scarcity:
        show_scarcity(rec, client)
    else:
        show_evidence(rec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
