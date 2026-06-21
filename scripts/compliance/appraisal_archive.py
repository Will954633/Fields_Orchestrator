"""
K — Immutable appraisal / CMA archive.

Property Occupations Act 2014 (Qld): an agent must retain a copy of the CMA and
supporting information, and (s212(5)/s215) must be able to prove reasonable grounds
for a price representation. The live `property_reports` doc is overwritten on every
rebuild, so it can't prove what a seller actually saw on a given date. This module
writes an APPEND-ONLY, tamper-evident snapshot of each delivered appraisal.

Store: system_monitor.appraisal_archive (never updated — one row per delivered
version). Mirrored to Google Drive by compliance/drive_backup.py.

Integrity: each row carries
  content_hash : sha256 of the canonical appraisal payload (stable across reruns)
  prev_hash    : content_hash of the previous row in the global chain
  chain_index  : position in the chain
Re-running is idempotent: a (slug, content_hash) already present is skipped, so a
new row appears only when the appraisal genuinely changed.

Usage:
  python3 -m scripts.compliance.appraisal_archive            # archive all delivered reports
  python3 -m scripts.compliance.appraisal_archive --slug X   # one report
  python3 -m scripts.compliance.appraisal_archive --list     # latest per slug
  python3 -m scripts.compliance.appraisal_archive --verify   # re-verify the hash chain
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from pymongo import ASCENDING, MongoClient

from scripts.compliance import AGENCY, LICENCE_NO, LICENSEE_NAME

ARCHIVE_COLL = "appraisal_archive"
REPORTS_COLL = "property_reports"


def _client() -> MongoClient:
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        sys.exit("COSMOS_CONNECTION_STRING not set")
    return MongoClient(conn)


def _canonical(obj: Any) -> str:
    """Deterministic JSON for hashing — sorted keys, compact, str-coerced."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _content_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _extract_payload(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The meaningful, hashable appraisal content from a property_reports doc.
    Returns None when the doc carries no real appraisal (nothing to archive)."""
    val = doc.get("valuation") or {}
    cma = val.get("statutory_cma")
    model_range = val.get("model_range")
    comps = val.get("comps")
    if not (cma or model_range or comps):
        return None  # no appraisal content yet

    ev_conf = ((val.get("evidence") or {}).get("confidence")) or {}
    confidence = {
        "reconciled": ev_conf.get("reconciled"),
        "range_low": ev_conf.get("rangeLow"),
        "range_high": ev_conf.get("rangeHigh"),
        "level": ev_conf.get("level"),
    } if ev_conf else None

    # as_at: prefer the statutory CMA's own date, then the data pull date.
    as_at = None
    if isinstance(cma, dict):
        as_at = cma.get("as_at")
    if not as_at:
        dpd = (doc.get("slots") or {}).get("data_pull_date") or doc.get("data_pull_date")
        if isinstance(dpd, datetime):
            as_at = dpd.strftime("%Y-%m-%d")
        elif isinstance(dpd, str):
            as_at = dpd[:10]

    return {
        "slug": doc.get("slug"),
        "address": doc.get("address"),
        "suburb": doc.get("suburb"),
        "as_at": as_at,
        "valid_until": cma.get("valid_until") if isinstance(cma, dict) else None,
        "appraisal_kind": "your_home_minisite",
        "model_range": model_range,
        "confidence": confidence,
        "statutory_cma": cma,
        "comps": comps,
        "prepared_by": LICENSEE_NAME,
        "licence": LICENCE_NO,
        "agency": AGENCY,
    }


def _last_chain_row(coll) -> Optional[Dict[str, Any]]:
    return coll.find_one(sort=[("chain_index", -1)])


def archive_report(coll, doc: Dict[str, Any], now: datetime) -> Optional[str]:
    """Archive one report if its appraisal content is new. Returns the action:
    'archived' | 'unchanged' | 'no_appraisal'."""
    payload = _extract_payload(doc)
    if payload is None:
        return "no_appraisal"
    chash = _content_hash(payload)
    slug = payload["slug"]
    if coll.find_one({"slug": slug, "content_hash": chash}, {"_id": 1}):
        return "unchanged"
    last = _last_chain_row(coll)
    prev_hash = last["content_hash"] if last else None
    chain_index = (last["chain_index"] + 1) if last else 0
    coll.insert_one({
        "archived_at": now,
        "source_report_id": doc.get("_id"),
        "slot_status": doc.get("slot_status"),
        "analyst_approved_at": doc.get("analyst_approved_at"),
        "analyst_approved_by": doc.get("analyst_approved_by"),
        **payload,
        "content_hash": chash,
        "prev_hash": prev_hash,
        "chain_index": chain_index,
    })
    return "archived"


def run_baseline(slug: Optional[str] = None) -> Dict[str, int]:
    client = _client()
    sm = client["system_monitor"]
    coll = sm[ARCHIVE_COLL]
    coll.create_index([("slug", ASCENDING), ("content_hash", ASCENDING)])
    coll.create_index([("chain_index", ASCENDING)])
    now = datetime.utcnow()
    q = {"slug": slug} if slug else {}
    stats = {"archived": 0, "unchanged": 0, "no_appraisal": 0}
    for doc in sm[REPORTS_COLL].find(q):
        action = archive_report(coll, doc, now)
        stats[action] += 1
        if action == "archived":
            print(f"  archived  {doc.get('slug')}")
    return stats


def verify_chain() -> bool:
    client = _client()
    coll = client["system_monitor"][ARCHIVE_COLL]
    rows = list(coll.find(sort=[("chain_index", ASCENDING)]))
    ok = True
    prev = None
    for r in rows:
        payload = {k: r.get(k) for k in (
            "slug", "address", "suburb", "as_at", "valid_until", "appraisal_kind",
            "model_range", "confidence", "statutory_cma", "comps",
            "prepared_by", "licence", "agency")}
        if _content_hash(payload) != r["content_hash"]:
            print(f"  ✗ content_hash mismatch at chain_index {r['chain_index']} ({r.get('slug')})")
            ok = False
        if r.get("prev_hash") != prev:
            print(f"  ✗ prev_hash break at chain_index {r['chain_index']} ({r.get('slug')})")
            ok = False
        prev = r["content_hash"]
    print(f"  chain length {len(rows)} — {'OK' if ok else 'INTEGRITY FAILURE'}")
    return ok


def list_latest() -> None:
    client = _client()
    coll = client["system_monitor"][ARCHIVE_COLL]
    pipeline = [
        {"$sort": {"chain_index": -1}},
        {"$group": {"_id": "$slug", "as_at": {"$first": "$as_at"},
                    "archived_at": {"$first": "$archived_at"},
                    "versions": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    rows = list(coll.aggregate(pipeline))
    print(f"{'slug':46} {'as_at':12} {'versions':>8}")
    for r in rows:
        print(f"{r['_id']:46} {str(r.get('as_at')):12} {r['versions']:>8}")
    print(f"total archived rows: {coll.count_documents({})}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Immutable appraisal/CMA archive (compliance item K)")
    ap.add_argument("--slug", help="archive a single report by slug")
    ap.add_argument("--list", action="store_true", help="show latest archive per slug")
    ap.add_argument("--verify", action="store_true", help="re-verify the hash chain")
    args = ap.parse_args()

    if args.list:
        list_latest()
        return
    if args.verify:
        sys.exit(0 if verify_chain() else 1)

    stats = run_baseline(args.slug)
    print(f"\nappraisal_archive: {stats}")


if __name__ == "__main__":
    main()
