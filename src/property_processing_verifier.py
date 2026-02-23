#!/usr/bin/env python3
"""
Property Processing Verifier (Auditor) for Fields Orchestrator

Last Updated: 28/01/2026, 6:28 PM (Wednesday) - Brisbane
- Initial creation: conservative per-property verification + marking model (dry-run capable)

Implements the core requirement from ORCHESTRATOR_DAILY_INCREMENTAL_PLAN.md:
"Do not trust a step ran — trust required outputs exist and pass validation".

This module:
- verifies per-property artifacts for the v2 pipeline completeness definition
- writes verification results into `orchestrator.processing.steps.*`
- optionally marks `orchestrator.processing.status` as complete

Canonical key (current system): `address`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pymongo import MongoClient

from .logger import get_logger


def _now() -> datetime:
    return datetime.now()


def _get_nested(doc: Dict[str, Any], path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


@dataclass
class VerificationOutcome:
    address: str
    ok: bool
    missing: List[str]
    details: Dict[str, Any]


class PropertyProcessingVerifier:
    def __init__(
        self,
        mongo_uri: str = "mongodb://127.0.0.1:27017/",
        database: str = "property_data",
        for_sale_collection: str = "properties_for_sale",
        pipeline_version: int = 2,
        pipeline_signature: str = "",
        dry_run: bool = True,
        write_verification_results: bool = True,
        mark_complete: bool = False,
    ):
        self.logger = get_logger()
        self.mongo_uri = mongo_uri
        self.database_name = database
        self.collection_name = for_sale_collection
        self.pipeline_version = pipeline_version
        self.pipeline_signature = pipeline_signature
        self.dry_run = dry_run
        self.write_verification_results = write_verification_results
        self.mark_complete = mark_complete

        self.client: Optional[MongoClient] = None
        self.db = None

    def connect(self) -> bool:
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.db = self.client[self.database_name]
            return True
        except Exception as e:
            self.logger.error(f"❌ Verifier: failed to connect to MongoDB: {e}")
            return False

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None

    # ---------------------------------------------------------------------
    # Verification gates (v2 completeness)
    # ---------------------------------------------------------------------
    def _verify_scrape_for_sale(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        required = ["address"]
        missing = [f for f in required if not doc.get(f)]

        # Images may be called property_images/images/image_urls etc; be permissive but require at least one.
        images = doc.get("property_images") or doc.get("images") or doc.get("image_urls") or doc.get("photos")
        has_images = isinstance(images, list) and len(images) > 0
        if not has_images:
            missing.append("property_images")

        ok = len(missing) == 0
        msg = "ok" if ok else f"missing: {', '.join(missing)}"
        return ok, msg, {"missing": missing, "has_images": has_images}

    def _verify_gpt_photo_analysis(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        # We don't know exact field names; check common ones.
        candidates = [
            "gpt_photo_analysis",
            "photo_analysis",
            "image_analysis",
            "gpt_image_analysis",
        ]
        found = None
        for c in candidates:
            val = doc.get(c)
            if val:
                found = c
                break
        ok = found is not None
        msg = "ok" if ok else "missing photo analysis output"
        return ok, msg, {"field": found}

    def _verify_gpt_photo_reorder(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        order = doc.get("photo_tour_order")
        # Lowered threshold from ≥20 to ≥5 (real data shows max ~16, most have 5-12)
        ok = isinstance(order, list) and len(order) >= 5
        msg = "ok" if ok else "missing/short photo_tour_order (<5)"
        return ok, msg, {"length": len(order) if isinstance(order, list) else None}

    def _verify_floor_plan_enrichment(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        # from floor plan pipeline we expect either analysis exists or explicit "no floorplan" marker
        analysis = doc.get("floor_plan_analysis")
        no_marker = doc.get("no_floor_plan") or _get_nested(doc, "floor_plan_analysis.no_floor_plan")
        ok = bool(analysis) or bool(no_marker)
        msg = "ok" if ok else "missing floor_plan_analysis and no no-floor-plan marker"
        return ok, msg, {"has_analysis": bool(analysis), "no_floor_plan_marker": bool(no_marker)}

    def _verify_floor_plan_v2(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        # V2 artifacts: accept floor_plan_analysis.rooms as evidence of floor plan processing
        # (the v2 pipeline enriches this structure)
        rooms = _get_nested(doc, "floor_plan_analysis.rooms")
        has_rooms = isinstance(rooms, list) and len(rooms) > 0
        
        # Also check for explicit v2 fields if they exist
        candidates = [
            "floor_plan_v2",
            "floor_plan_v2_processing",
            "floor_plan_ocr",
            "floor_plan_rooms",
            "room_annotations",
        ]
        found = None
        for c in candidates:
            val = doc.get(c)
            if val:
                found = c
                break
        
        ok = has_rooms or (found is not None)
        msg = "ok" if ok else "missing floor plan v2 artifacts"
        return ok, msg, {"field": found, "has_rooms": has_rooms}

    def _verify_room_photo_matching(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        # Check for completion marker field (written by match_floor_plan_rooms_to_photos.py)
        completed_at = doc.get("room_photo_matching_completed_at")
        has_completed_marker = completed_at is not None
        
        # Also check legacy field names
        candidates = [
            "room_photo_matches",
            "room_to_photo_matches",
            "floor_plan_room_photo_matching",
        ]
        found = None
        for c in candidates:
            val = doc.get(c)
            if val:
                found = c
                break
        
        ok = has_completed_marker or (found is not None)
        msg = "ok" if ok else "missing room-to-photo matching artifacts"
        return ok, msg, {"field": found, "has_completed_marker": has_completed_marker}

    def _verify_valuation(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        val = _get_nested(doc, "iteration_08_valuation.predicted_value")
        ok = isinstance(val, (int, float))
        msg = "ok" if ok else "missing iteration_08_valuation.predicted_value"
        return ok, msg, {"predicted_value": val}

    def _verify_backend_enrichment(self, doc: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        # We expect these scripts to write a variety of fields.
        # Conservative minimal check: property_insights exists.
        # Extend later once field names are confirmed.
        candidates = ["property_insights", "rarity_insights", "unique_features"]
        found = None
        for c in candidates:
            val = doc.get(c)
            if val:
                found = c
                break
        ok = found is not None
        msg = "ok" if ok else "missing backend insights artifacts"
        return ok, msg, {"field": found}

    def verify_document(self, doc: Dict[str, Any], run_id: str) -> VerificationOutcome:
        address = doc.get("address")
        if not address:
            return VerificationOutcome(address="", ok=False, missing=["address"], details={})

        checks = {
            "scrape_for_sale": self._verify_scrape_for_sale,
            "gpt_photo_analysis": self._verify_gpt_photo_analysis,
            "gpt_photo_reorder": self._verify_gpt_photo_reorder,
            "floor_plan_enrichment": self._verify_floor_plan_enrichment,
            "floor_plan_v2": self._verify_floor_plan_v2,
            "room_photo_matching": self._verify_room_photo_matching,
            "valuation": self._verify_valuation,
            "backend_enrichment": self._verify_backend_enrichment,
        }

        missing: List[str] = []
        step_results: Dict[str, Any] = {}
        all_ok = True

        for step, fn in checks.items():
            ok, msg, details = fn(doc)
            if not ok:
                all_ok = False
                missing.append(step)
            step_results[step] = {
                "ok": bool(ok),
                "verified_at": _now(),
                "message": msg,
                "details": details,
            }

        return VerificationOutcome(
            address=address,
            ok=all_ok,
            missing=missing,
            details={
                "steps": step_results,
                "pipeline_signature": {"version": self.pipeline_version, "signature": self.pipeline_signature},
                "last_run_id": run_id,
            },
        )

    def verify_and_update(self, run_id: str, only_addresses: Optional[List[str]] = None) -> Dict[str, Any]:
        """Verify properties and (optionally) write results.

        Returns summary dict with counts.
        """
        if self.db is None:
            raise RuntimeError("Verifier not connected")

        col = self.db[self.collection_name]

        query: Dict[str, Any] = {}
        if only_addresses:
            query = {"address": {"$in": only_addresses}}

        examined = 0
        ok_count = 0
        incomplete_count = 0

        cursor = col.find(query, {})
        for doc in cursor:
            examined += 1
            outcome = self.verify_document(doc, run_id=run_id)
            if not outcome.address:
                continue

            if outcome.ok:
                ok_count += 1
            else:
                incomplete_count += 1

            if self.dry_run:
                continue

            if not self.write_verification_results:
                continue

            orch = doc.get("orchestrator") if isinstance(doc.get("orchestrator"), dict) else {}
            orch = {**orch}
            orch.setdefault("lifecycle", "for_sale")
            orch.setdefault("first_seen_at", doc.get("first_seen") or doc.get("first_seen_at"))
            orch["last_seen_at"] = _now()
            orch["pipeline_signature"] = {"version": self.pipeline_version, "signature": self.pipeline_signature}

            processing = orch.get("processing") if isinstance(orch.get("processing"), dict) else {}
            processing = {**processing}
            processing["last_run_id"] = run_id
            processing["last_attempt_at"] = _now()
            processing.setdefault("fully_processed_at", None)
            processing["steps"] = outcome.details["steps"]

            if self.mark_complete and outcome.ok:
                processing["status"] = "complete"
                processing["fully_processed_at"] = _now()
            else:
                processing["status"] = "incomplete" if not outcome.ok else processing.get("status", "incomplete")

            orch["processing"] = processing

            col.update_one({"address": outcome.address}, {"$set": {"orchestrator": orch}})

        return {
            "examined": examined,
            "verified_complete": ok_count,
            "verified_incomplete": incomplete_count,
            "dry_run": self.dry_run,
            "mark_complete": self.mark_complete,
        }
