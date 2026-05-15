"""Substantiation file writer — dual-write to MongoDB + flat JSON.

Per framework doc Rule 5 (`09_Appraisals/Scarcity_Legality/07_amendments_and_operating_framework.md`):

    > For every forward-looking number — target sale price, willingness-to-pay
    > range, campaign reach forecast, days-on-market projection — the
    > substantiation file is saved at the moment of issue, not reconstructed
    > later. 7-year retention. ACL s4 puts the burden of proof on Fields.

Dual-write rationale (Will's call 2026-05-15): MongoDB gives queryability and
ops-dashboard access; flat JSON gives durable on-disk audit trail that survives
DB migrations. Long-term canonical store TBD.

File path: 09_Appraisals/Substantiation/<subject_id>_<section>_<utc_timestamp>.json
Mongo:     system_monitor.appraisal_substantiation
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from bson import ObjectId  # type: ignore
from shared.db import get_client  # type: ignore

SUBSTANTIATION_DIR = REPO_ROOT / "09_Appraisals" / "Substantiation"


def save(record: dict) -> dict:
    """Dual-write `record` to MongoDB and a flat JSON file.

    `record` must include at minimum:
        - `section` (e.g. "01_right")
        - `subject_id` (string)

    Returns:
        {"mongo_id": "<oid>", "file_path": "<absolute path>"}
    """
    if "section" not in record or "subject_id" not in record:
        raise ValueError("substantiation.save() requires 'section' and 'subject_id'")

    # Add the timestamp under a consistent key, leave any pre-existing
    # 'as_at_date' untouched (callers may set their own meaning for that field).
    now = datetime.now(timezone.utc)
    record = {**record, "saved_at": now.isoformat()}

    # 1. MongoDB write
    db = get_client()["system_monitor"]
    mongo_result = db.appraisal_substantiation.insert_one(record)
    mongo_id = mongo_result.inserted_id

    # 2. Flat JSON write — strip the mongo-inserted _id, embed it as a string
    file_record = {k: v for k, v in record.items() if k != "_id"}
    file_record["mongo_id"] = str(mongo_id)

    SUBSTANTIATION_DIR.mkdir(parents=True, exist_ok=True)
    ts = now.strftime("%Y%m%dT%H%M%S")
    safe_section = str(record["section"]).replace("/", "_")
    safe_subject = str(record["subject_id"]).replace("/", "_")
    file_path = SUBSTANTIATION_DIR / f"{safe_subject}_{safe_section}_{ts}.json"
    file_path.write_text(json.dumps(file_record, indent=2, default=_json_default))

    return {"mongo_id": str(mongo_id), "file_path": str(file_path)}


def _json_default(o: Any) -> Any:
    """JSON encoder for ObjectId, datetime, and other Mongo-y types."""
    if isinstance(o, ObjectId):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def load_latest(subject_id: str, section: str) -> dict | None:
    """Read the most recent substantiation record for a subject+section.
    Used for verification and audit queries."""
    db = get_client()["system_monitor"]
    return db.appraisal_substantiation.find_one(
        {"subject_id": str(subject_id), "section": section},
        sort=[("saved_at", -1)],
    )
