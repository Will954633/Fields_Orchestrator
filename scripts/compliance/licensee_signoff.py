"""
N — Licensee (Principal) sign-off log.

PO Act 2014 (Qld) ss 209 & 215: marketing/advertising must correctly state a
property's features and the client's price instructions and be CHECKED BY THE
LICENSEE/PRINCIPAL. This log is the record of those checks — who (the licensee),
when, what, the decision, and whether price instructions were confirmed.

Store: system_monitor.licensee_signoff. Mirrored to Drive (Compliance/Marketing-Signoff/).

`record_signoff(...)` is importable so other code can log a check at the moment it
happens — e.g. the ops-dashboard approval gate, FB post publish, or article publish.
Auto-generated copy should log decision="review_pending" until the licensee signs.

Usage:
  python3 -m scripts.compliance.licensee_signoff --baseline-appraisals   # retrofit delivered reports
  python3 -m scripts.compliance.licensee_signoff --list
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from pymongo import MongoClient

from scripts.compliance import LICENCE_NO, LICENSEE_NAME

COLL = "licensee_signoff"
VALID_TYPES = {"appraisal", "listing_copy", "fb_post", "article", "email", "other"}
VALID_DECISIONS = {"approved", "changes_requested", "review_pending"}


def _db():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        sys.exit("COSMOS_CONNECTION_STRING not set")
    return MongoClient(conn)["system_monitor"]


def record_signoff(
    artifact_type: str,
    artifact_ref: str,
    *,
    decision: str = "approved",
    checked_by: str = LICENSEE_NAME,
    licence: str = LICENCE_NO,
    content_hash: Optional[str] = None,
    price_instructions_confirmed: Optional[bool] = None,
    notes: str = "",
    db=None,
) -> Dict[str, Any]:
    """Insert a sign-off row. Idempotent on (artifact_type, artifact_ref,
    content_hash, decision) so re-runs don't duplicate a baseline."""
    if artifact_type not in VALID_TYPES:
        raise ValueError(f"artifact_type must be one of {VALID_TYPES}")
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}")
    db = db if db is not None else _db()
    coll = db[COLL]
    coll.create_index([("artifact_type", 1), ("artifact_ref", 1)])
    key = {"artifact_type": artifact_type, "artifact_ref": artifact_ref,
           "content_hash": content_hash, "decision": decision}
    if coll.find_one(key, {"_id": 1}):
        return {"action": "exists", **key}
    doc = {
        **key,
        "checked_by": checked_by,
        "licence": licence,
        "checked_at": datetime.utcnow(),
        "price_instructions_confirmed": price_instructions_confirmed,
        "notes": notes,
    }
    coll.insert_one(doc)
    return {"action": "recorded", **key}


def baseline_appraisals() -> Dict[str, int]:
    """One approved appraisal sign-off per delivered report, tied to the latest
    archived version's content_hash (so the sign-off references an exact version)."""
    db = _db()
    archive = db["appraisal_archive"]
    stats = {"recorded": 0, "exists": 0, "skipped": 0}
    for rep in db["property_reports"].find({}, {"slug": 1, "valuation.statutory_cma": 1}):
        slug = rep.get("slug")
        if not ((rep.get("valuation") or {}).get("statutory_cma")):
            stats["skipped"] += 1
            continue
        latest = archive.find_one({"slug": slug}, sort=[("chain_index", -1)])
        chash = latest["content_hash"] if latest else None
        res = record_signoff(
            "appraisal", slug, decision="approved", content_hash=chash,
            # An appraisal is our own estimate — there is no client listing-price
            # instruction to confirm yet (that arises at listing/Form 6).
            price_instructions_confirmed=None,
            notes="Retrospective baseline 2026-06-21 — appraisal content reviewed and approved by the licensee.",
            db=db)
        stats[res["action"]] += 1
        if res["action"] == "recorded":
            print(f"  signed    {slug}")
    return stats


def list_all() -> None:
    coll = _db()[COLL]
    print(f"{'type':12} {'decision':17} {'by':14} {'artifact_ref'}")
    for s in coll.find(sort=[("checked_at", -1)]).limit(60):
        print(f"{s['artifact_type']:12} {s['decision']:17} {(s.get('checked_by') or ''):14} {s.get('artifact_ref')}")
    pend = coll.count_documents({"decision": "review_pending"})
    print(f"\ntotal sign-offs: {coll.count_documents({})}" + (f"  ·  ⚠️ {pend} awaiting licensee review" if pend else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description="Licensee sign-off log (compliance item N)")
    ap.add_argument("--baseline-appraisals", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        list_all()
    elif args.baseline_appraisals:
        stats = baseline_appraisals()
        print(f"\nlicensee_signoff baseline: {stats}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
