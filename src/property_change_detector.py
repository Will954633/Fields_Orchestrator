#!/usr/bin/env python3
"""
Property Change Detector for Fields Orchestrator

Detects and records changes in property listings between pipeline runs.
Operates per-suburb, storing snapshots and diffs in MongoDB.

Database schema:
    Gold_Coast_Currently_For_Sale.<suburb>  - one collection per suburb

Interface required by task_executor.py:
    detector = PropertyChangeDetector(mongo_uri=..., database=...)
    detector.connect()
    count = detector.create_snapshot(suburbs=[...], run_id=...)
    summary = detector.detect_and_record_changes(run_id=..., suburbs=[...])
    detector.close()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

from .logger import get_logger

# Fields to track for change detection
TRACKED_FIELDS = [
    "price",
    "display_price",
    "price_display",
    "inspections",
    "inspection_times",
    "agent_description",
    "description",
    "bedrooms",
    "bathrooms",
    "car_spaces",
    "land_size",
    "status",
]

# The database that holds per-suburb for-sale collections
FOR_SALE_DATABASE = "Gold_Coast_Currently_For_Sale"

# Snapshots stored in this collection within the for-sale database
SNAPSHOT_COLLECTION = "change_detection_snapshots"


@dataclass
class ChangeSummary:
    properties_examined: int = 0
    properties_with_changes: int = 0
    total_field_changes: int = 0
    new_properties: int = 0
    removed_properties: int = 0
    changes_by_field: Dict[str, int] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now()


class PropertyChangeDetector:
    """
    Detects and records property field changes between pipeline runs.

    Reads from: Gold_Coast_Currently_For_Sale.<suburb> (one collection per suburb)
    Snapshots stored in: Gold_Coast_Currently_For_Sale.change_detection_snapshots
    Changes recorded on each property doc under: orchestrator.change_history
    """

    def __init__(self, mongo_uri: str, database: str):
        # `database` arg comes from task_executor but we use FOR_SALE_DATABASE directly
        self.mongo_uri = mongo_uri
        self.logger = get_logger()
        self.client: Optional[MongoClient] = None
        self.for_sale_db = None

    def connect(self) -> bool:
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.for_sale_db = self.client[FOR_SALE_DATABASE]
            self.logger.info("✅ PropertyChangeDetector: connected to MongoDB")
            return True
        except Exception as e:
            self.logger.error(f"❌ PropertyChangeDetector: failed to connect: {e}")
            return False

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.for_sale_db = None

    def _get_suburb_docs(self, suburbs: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Return {suburb: [docs]} for each suburb collection."""
        result: Dict[str, List[Dict[str, Any]]] = {}
        for suburb in suburbs:
            col = self.for_sale_db[suburb]
            docs = list(col.find({}, {}))
            result[suburb] = docs
        return result

    def _build_snapshot_record(
        self, suburb_docs: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Build snapshot: address -> tracked field values, across all suburbs."""
        snapshot: Dict[str, Any] = {}
        for suburb, docs in suburb_docs.items():
            for doc in docs:
                address = doc.get("address") or doc.get("url") or str(doc.get("_id"))
                if not address:
                    continue
                snapshot[address] = {f: doc.get(f) for f in TRACKED_FIELDS}
        return snapshot

    def create_snapshot(self, suburbs: List[str], run_id: str) -> int:
        """
        Capture the current state of for-sale properties for the given suburbs.
        Stores the snapshot in change_detection_snapshots collection.
        Returns total count of properties snapshotted.
        """
        if self.for_sale_db is None:
            raise RuntimeError("PropertyChangeDetector not connected")

        suburb_docs = self._get_suburb_docs(suburbs)
        snapshot_record = self._build_snapshot_record(suburb_docs)

        total = sum(len(docs) for docs in suburb_docs.values())

        self.for_sale_db[SNAPSHOT_COLLECTION].update_one(
            {"_id": "current"},
            {
                "$set": {
                    "snapshot": snapshot_record,
                    "run_id": run_id,
                    "created_at": _now(),
                    "suburbs": suburbs,
                    "count": len(snapshot_record),
                }
            },
            upsert=True,
        )

        self.logger.info(
            f"📸 PropertyChangeDetector: snapshot created with {len(snapshot_record)} properties "
            f"across {len(suburbs)} suburbs (run_id={run_id})"
        )
        return len(snapshot_record)

    def detect_and_record_changes(
        self, run_id: str, suburbs: List[str]
    ) -> ChangeSummary:
        """
        Compare current for-sale properties against stored snapshot.
        Records changes on each property doc under orchestrator.change_history.
        Returns a ChangeSummary.
        """
        if self.for_sale_db is None:
            raise RuntimeError("PropertyChangeDetector not connected")

        # Load previous snapshot
        snap_doc = self.for_sale_db[SNAPSHOT_COLLECTION].find_one({"_id": "current"})
        prev_snapshot: Dict[str, Any] = {}
        if snap_doc and isinstance(snap_doc.get("snapshot"), dict):
            prev_snapshot = snap_doc["snapshot"]

        # Load current state
        suburb_docs = self._get_suburb_docs(suburbs)
        current_snapshot = self._build_snapshot_record(suburb_docs)

        prev_addresses = set(prev_snapshot.keys())
        current_addresses = set(current_snapshot.keys())

        new_addresses = current_addresses - prev_addresses
        removed_addresses = prev_addresses - current_addresses
        common_addresses = current_addresses & prev_addresses

        summary = ChangeSummary(
            new_properties=len(new_addresses),
            removed_properties=len(removed_addresses),
        )

        # Build address -> suburb lookup for targeted updates
        address_to_suburb: Dict[str, str] = {}
        for suburb, docs in suburb_docs.items():
            for doc in docs:
                address = doc.get("address") or doc.get("url") or str(doc.get("_id"))
                if address:
                    address_to_suburb[address] = suburb

        for address in common_addresses:
            summary.properties_examined += 1
            prev_fields = prev_snapshot[address]
            curr_fields = current_snapshot[address]

            field_changes: Dict[str, Any] = {}
            for f in TRACKED_FIELDS:
                old_val = prev_fields.get(f)
                new_val = curr_fields.get(f)
                if old_val != new_val:
                    field_changes[f] = {"old": old_val, "new": new_val}
                    summary.total_field_changes += 1
                    summary.changes_by_field[f] = summary.changes_by_field.get(f, 0) + 1

            if field_changes:
                summary.properties_with_changes += 1
                change_entry = {"run_id": run_id, "at": _now(), "changes": field_changes}
                suburb = address_to_suburb.get(address)
                if suburb:
                    self.for_sale_db[suburb].update_one(
                        {"address": address},
                        {"$push": {"orchestrator.change_history": change_entry}},
                    )

        self.logger.info(
            f"🔍 PropertyChangeDetector: examined={summary.properties_examined}, "
            f"with_changes={summary.properties_with_changes}, "
            f"total_field_changes={summary.total_field_changes}, "
            f"new={summary.new_properties}, removed={summary.removed_properties}"
        )

        return summary
