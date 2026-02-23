#!/usr/bin/env python3
"""
Sold Mover for Fields Orchestrator

Last Updated: 28/01/2026, 6:28 PM (Wednesday) - Brisbane
- Initial creation: idempotent sold migration (copy/upsert into sold, then delete from for_sale)

This module implements the "sold transition procedure" required by:
ORCHESTRATOR_DAILY_INCREMENTAL_PLAN.md

Policy (per user decision):
- copy to `properties_sold` then delete from `properties_for_sale`

We detect sold candidates conservatively by looking for markers set by the sold monitor.
Because external scripts may differ in what fields they write, we support multiple possible
marker locations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pymongo import MongoClient

from .logger import get_logger


@dataclass
class SoldMoveResult:
    examined: int
    moved: int
    deleted_from_for_sale: int
    errors: int
    moved_addresses: List[str]


class SoldMover:
    def __init__(
        self,
        mongo_uri: str = "mongodb://127.0.0.1:27017/",
        database: str = "property_data",
        for_sale_collection: str = "properties_for_sale",
        sold_collection: str = "properties_sold",
    ):
        self.logger = get_logger()
        self.mongo_uri = mongo_uri
        self.database_name = database
        self.for_sale_collection_name = for_sale_collection
        self.sold_collection_name = sold_collection

        self.client: Optional[MongoClient] = None
        self.db = None

    def connect(self) -> bool:
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.db = self.client[self.database_name]
            return True
        except Exception as e:
            self.logger.error(f"❌ SoldMover: failed to connect to MongoDB: {e}")
            return False

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None

    @staticmethod
    def _is_marked_sold(doc: Dict[str, Any]) -> bool:
        """Heuristic: check multiple possible marker locations."""
        orch = doc.get("orchestrator", {}) if isinstance(doc.get("orchestrator"), dict) else {}

        lifecycle = orch.get("lifecycle")
        if lifecycle == "sold":
            return True

        if orch.get("sold_detected_at"):
            return True

        # common alternative field names from scrapers/monitors
        status = doc.get("status") or doc.get("listing_status") or doc.get("sale_status")
        if isinstance(status, str) and status.lower() == "sold":
            return True

        if doc.get("sold_price") is not None or doc.get("sold_date") is not None:
            # not perfect, but useful as a fallback marker
            return True

        return False

    def move_sold_properties(self, run_id: str) -> SoldMoveResult:
        if self.db is None:
            raise RuntimeError("SoldMover not connected")

        for_sale = self.db[self.for_sale_collection_name]
        sold = self.db[self.sold_collection_name]

        examined = 0
        moved = 0
        deleted = 0
        errors = 0
        moved_addresses: List[str] = []

        cursor = for_sale.find({}, {})
        for doc in cursor:
            examined += 1
            try:
                if not self._is_marked_sold(doc):
                    continue

                address = doc.get("address")
                if not address:
                    # Without canonical key we can't safely dedupe.
                    self.logger.warning("SoldMover: skipping sold doc without address")
                    continue

                # annotate sold doc
                orch = doc.get("orchestrator") if isinstance(doc.get("orchestrator"), dict) else {}
                orch = {**orch}
                orch["lifecycle"] = "sold"
                orch["migrated_to_sold"] = {
                    "at": datetime.now(),
                    "run_id": run_id,
                    "method": "sold_mover",
                    "policy": "copy_then_delete",
                    "source_collection": self.for_sale_collection_name,
                }
                doc["orchestrator"] = orch

                # Upsert into sold by address
                sold.replace_one({"address": address}, doc, upsert=True)
                moved += 1
                moved_addresses.append(address)

                # Delete from for_sale by _id (strongest) else by address
                if "_id" in doc:
                    res = for_sale.delete_one({"_id": doc["_id"]})
                else:
                    res = for_sale.delete_one({"address": address})
                deleted += int(res.deleted_count or 0)

            except Exception as e:
                errors += 1
                self.logger.error(f"SoldMover: error migrating doc: {e}")

        self.logger.info(
            f"SoldMover summary: examined={examined}, moved={moved}, deleted_from_for_sale={deleted}, errors={errors}"
        )
        return SoldMoveResult(
            examined=examined,
            moved=moved,
            deleted_from_for_sale=deleted,
            errors=errors,
            moved_addresses=moved_addresses,
        )
