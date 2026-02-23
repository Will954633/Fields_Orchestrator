#!/usr/bin/env python3
"""
Field Change Tracker for Fields Orchestrator

Last Updated: 28/01/2026, 6:35 PM (Wednesday) - Brisbane
- Initial creation: preserve historical changes for selected fields (price/inspections/agent description)

User requirement:
"update price/inspections for complete properties and any changes in agents descriptions.
Note that all previous data must be preserved and new fields added..."

This module provides a minimal, explicit pattern:
- Track snapshots of key mutable fields under `orchestrator.history.<field>`
- Append new entries only when the value changes

Canonical key: address.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

from .logger import get_logger


def _now() -> datetime:
    return datetime.now()


def _safe_get(doc: Dict[str, Any], key: str) -> Any:
    return doc.get(key)


@dataclass
class ChangeTrackSummary:
    examined: int
    updated: int
    changes: Dict[str, int]


class FieldChangeTracker:
    def __init__(
        self,
        mongo_uri: str,
        database: str,
        for_sale_collection: str = "properties_for_sale",
    ):
        self.logger = get_logger()
        self.mongo_uri = mongo_uri
        self.database_name = database
        self.collection_name = for_sale_collection

        self.client: Optional[MongoClient] = None
        self.db = None

    def connect(self) -> bool:
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.db = self.client[self.database_name]
            return True
        except Exception as e:
            self.logger.error(f"❌ FieldChangeTracker: failed to connect: {e}")
            return False

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None

    def _append_history_if_changed(
        self,
        doc: Dict[str, Any],
        orch: Dict[str, Any],
        field_name: str,
        current_value: Any,
    ) -> bool:
        """Returns True if a new history entry was added."""
        history = orch.get("history") if isinstance(orch.get("history"), dict) else {}
        history = {**history}

        entries = history.get(field_name)
        if not isinstance(entries, list):
            entries = []

        last_value = entries[-1]["value"] if entries else None
        if current_value == last_value:
            orch["history"] = history
            return False

        entries.append({"at": _now(), "value": current_value})
        history[field_name] = entries
        orch["history"] = history
        return True

    def track_fields(self, run_id: str, only_addresses: Optional[List[str]] = None) -> ChangeTrackSummary:
        if self.db is None:
            raise RuntimeError("FieldChangeTracker not connected")

        col = self.db[self.collection_name]
        query: Dict[str, Any] = {}
        if only_addresses:
            query = {"address": {"$in": only_addresses}}

        examined = 0
        updated = 0
        changes = {"price": 0, "inspections": 0, "agent_description": 0}

        for doc in col.find(query, {}):
            examined += 1
            address = doc.get("address")
            if not address:
                continue

            orch = doc.get("orchestrator") if isinstance(doc.get("orchestrator"), dict) else {}
            orch = {**orch}
            orch.setdefault("lifecycle", "for_sale")

            changed_any = False

            # Price field name is not guaranteed; try common keys.
            price = _safe_get(doc, "price") or _safe_get(doc, "display_price") or _safe_get(doc, "price_display")
            if self._append_history_if_changed(doc, orch, "price", price):
                changes["price"] += 1
                changed_any = True

            inspections = _safe_get(doc, "inspections") or _safe_get(doc, "inspection_times")
            if self._append_history_if_changed(doc, orch, "inspections", inspections):
                changes["inspections"] += 1
                changed_any = True

            agent_desc = _safe_get(doc, "agent_description") or _safe_get(doc, "description")
            if self._append_history_if_changed(doc, orch, "agent_description", agent_desc):
                changes["agent_description"] += 1
                changed_any = True

            if changed_any:
                orch["last_refresh_at"] = _now()
                orch["last_refresh_run_id"] = run_id
                col.update_one({"address": address}, {"$set": {"orchestrator": orch}})
                updated += 1

        self.logger.info(
            f"FieldChangeTracker summary: examined={examined}, updated={updated}, changes={changes}"
        )
        return ChangeTrackSummary(examined=examined, updated=updated, changes=changes)
