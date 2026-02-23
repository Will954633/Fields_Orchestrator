#!/usr/bin/env python3
"""
Daily Incremental Utilities for Fields Orchestrator

Last Updated: 28/01/2026, 6:34 PM (Wednesday) - Brisbane
- Initial creation: build daily snapshot + candidate selection (new/incomplete/stale)

This module supports the operating model from ORCHESTRATOR_DAILY_INCREMENTAL_PLAN.md.

Current schema constraints observed in MongoDB:
- `properties_for_sale` documents reliably have `address`
- `url` is not currently populated (so we use address as canonical key)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pymongo import MongoClient

from .logger import get_logger


@dataclass
class CandidateSets:
    new_addresses: List[str]
    incomplete_addresses: List[str]
    stale_addresses: List[str]
    all_candidates: List[str]


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_snapshot_addresses(snapshot_file: Path) -> Set[str]:
    if not snapshot_file.exists():
        return set()
    try:
        data = json.loads(snapshot_file.read_text(encoding="utf-8"))
        props = data.get("properties", [])
        return set(p.get("address") for p in props if p.get("address"))
    except Exception:
        return set()


def write_for_sale_snapshot(
    base_dir: Path,
    mongo_uri: str,
    database: str,
    for_sale_collection: str = "properties_for_sale",
) -> Dict[str, Any]:
    """Write a daily snapshot of current for-sale addresses to state/for_sale_snapshot.json."""
    logger = get_logger()
    state_dir = base_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = state_dir / "for_sale_snapshot.json"

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[database]
    col = db[for_sale_collection]

    props = list(col.find({}, {"address": 1, "_id": 0}))
    addresses = sorted([p.get("address") for p in props if p.get("address")])

    payload = {
        "timestamp": _now_str(),
        "count": len(addresses),
        "properties": [{"address": a} for a in addresses],
    }
    snapshot_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"📌 Wrote for-sale snapshot: {len(addresses)} properties -> {snapshot_file}")
    client.close()

    return {"count": len(addresses), "file": str(snapshot_file)}


def compute_candidate_sets(
    base_dir: Path,
    mongo_uri: str,
    database: str,
    pipeline_signature: Dict[str, Any],
    for_sale_collection: str = "properties_for_sale",
) -> CandidateSets:
    """Compute daily candidates: new (vs prior snapshot), incomplete, stale signature."""
    logger = get_logger()
    snapshot_file = base_dir / "state" / "for_sale_snapshot.json"
    prev_addresses = _load_snapshot_addresses(snapshot_file)

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[database]
    col = db[for_sale_collection]

    current = list(col.find({}, {"address": 1, "orchestrator": 1, "_id": 0}))
    current_addresses = set(d.get("address") for d in current if d.get("address"))

    new_addresses = sorted(list(current_addresses - prev_addresses))

    incomplete_addresses: List[str] = []
    stale_addresses: List[str] = []

    for d in current:
        address = d.get("address")
        if not address:
            continue

        orch = d.get("orchestrator") if isinstance(d.get("orchestrator"), dict) else {}
        processing = orch.get("processing") if isinstance(orch.get("processing"), dict) else {}
        status = processing.get("status")

        if status in ("incomplete", "needs_review", "new", "processing"):
            incomplete_addresses.append(address)

        sig = orch.get("pipeline_signature") if isinstance(orch.get("pipeline_signature"), dict) else {}
        if sig.get("signature") and sig.get("signature") != pipeline_signature.get("signature"):
            stale_addresses.append(address)

    # Union while keeping order stable
    all_candidates = sorted(set(new_addresses) | set(incomplete_addresses) | set(stale_addresses))

    logger.info(
        f"Daily candidates computed: new={len(new_addresses)}, incomplete={len(incomplete_addresses)}, stale={len(stale_addresses)}, total={len(all_candidates)}"
    )

    client.close()
    return CandidateSets(
        new_addresses=new_addresses,
        incomplete_addresses=sorted(set(incomplete_addresses)),
        stale_addresses=sorted(set(stale_addresses)),
        all_candidates=all_candidates,
    )
