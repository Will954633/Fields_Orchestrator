#!/usr/bin/env python3
"""
Step 106 — Floor Plan Analysis (RU-guarded wrapper)

Wraps the legacy Ollama/OpenAI floor-plan analyzer with Cosmos DB retry logic,
empty-workset safeguards, and MonitorClient reporting.
"""

from __future__ import annotations

import importlib.util
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client, get_db, cosmos_retry, EmptyWorkSetError, sleep_with_jitter  # type: ignore
from shared.monitor_client import MonitorClient  # type: ignore

load_env()

REMOTE_DIR = Path(
    "/home/fields/Property_Data_Scraping/03_Gold_Coast/"
    "Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis"
)
if str(REMOTE_DIR) not in sys.path:
    sys.path.insert(0, str(REMOTE_DIR))

spec = importlib.util.spec_from_file_location(
    "legacy_floor_plan", REMOTE_DIR / "ollama_floor_plan_analysis.py"
)
legacy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(legacy)  # type: ignore

OllamaFloorPlanClient = legacy.OllamaFloorPlanClient
_legacy_process_property = legacy.process_property
get_property_images = legacy.get_property_images

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE_NAME = "Gold_Coast"

CANDIDATE_QUERY = {
    "$and": [
        {
            "ollama_image_analysis": {
                "$exists": True,
                "$type": "array",
                "$ne": [],
            }
        },
        {
            "$or": [
                {"ollama_floor_plan_analysis": {"$exists": False}},
                {"ollama_floor_plan_analysis.has_floor_plan": {"$ne": True}},
            ]
        },
        {
            "$or": [
                {
                    "scraped_data.images": {
                        "$exists": True,
                        "$type": "array",
                        "$ne": [],
                    }
                },
                {
                    "property_images": {
                        "$exists": True,
                        "$type": "array",
                        "$ne": [],
                    }
                },
                {
                    "images": {
                        "$exists": True,
                        "$type": "array",
                        "$ne": [],
                    }
                },
            ]
        },
    ]
}

PROPERTY_TIMEOUT_SECONDS = int(os.getenv("STEP106_PROPERTY_TIMEOUT_SECONDS", "180"))


@dataclass
class AnalysisStats:
    processed: int = 0
    successes: int = 0
    errors: int = 0
    skipped_no_images: int = 0


class PropertyProcessingTimeout(TimeoutError):
    """Raised when a single property takes too long to process."""


def _timeout_handler(signum, frame):  # type: ignore[unused-argument]
    raise PropertyProcessingTimeout(
        f"Property processing exceeded {PROPERTY_TIMEOUT_SECONDS}s"
    )


def _coerce_url_list(items: Any) -> List[str]:
    """Normalize mixed image payloads into raw URL strings."""
    if not isinstance(items, list):
        return []

    urls: List[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            urls.append(item.strip())
            continue

        if isinstance(item, dict):
            for key in ("url", "src", "image_url"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    urls.append(value.strip())
                    break

    return urls


def _normalize_property_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Copy a property doc and normalize legacy image/floor-plan fields."""
    normalized = dict(doc)

    if isinstance(doc.get("scraped_data"), dict):
        scraped_data = dict(doc["scraped_data"])
        scraped_data["images"] = _coerce_url_list(scraped_data.get("images"))
        normalized["scraped_data"] = scraped_data

    normalized["property_images"] = _coerce_url_list(doc.get("property_images"))
    normalized["images"] = _coerce_url_list(doc.get("images"))
    normalized["floor_plans"] = _coerce_url_list(doc.get("floor_plans"))

    return normalized


class GuardedFloorPlanRepository:
    """Thin wrapper around MongoDB with RU-aware retries."""

    def __init__(self) -> None:
        self.client = get_client()
        self.db = get_db(DATABASE_NAME)
        self._collections = set(
            cosmos_retry(lambda: self.db.list_collection_names(), "list_collections", log=print)
        )
        self.suburbs = [s for s in TARGET_SUBURBS if s in self._collections]

    def fetch_candidates(self, limit: int | None = None) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for suburb in self.suburbs:
            collection = self.db[suburb]
            def _load(coll=collection):
                cursor = coll.find(CANDIDATE_QUERY)
                if limit:
                    cursor = cursor.limit(limit)
                return list(cursor)

            docs = cosmos_retry(_load, f"{suburb}.fetch_candidates", log=print)
            for doc in docs:
                doc["_collection"] = suburb
                candidates.append(doc)
        return candidates

    def count_needing_analysis(self) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for suburb in self.suburbs:
            collection = self.db[suburb]
            count = cosmos_retry(
                lambda coll=collection: coll.count_documents(CANDIDATE_QUERY),
                f"{suburb}.count_candidates",
                log=print,
            )
            stats[suburb] = count
        return stats

    def update_with_floor_plan_analysis(
        self, document_id, suburb, floor_plan_analysis, processing_time=None
    ):
        suburb_key = suburb.lower()
        collection = self.db[suburb_key]
        cosmos_retry(
            lambda coll=collection: coll.update_one(
                {"_id": document_id},
                {
                    "$set": {
                        "ollama_floor_plan_analysis": {
                            **floor_plan_analysis,
                            "processed_at": datetime.utcnow(),
                            "processing_duration_seconds": processing_time,
                        }
                    }
                },
            ),
            f"{suburb_key}.update_floor_plan",
            log=print,
        )
        sleep_with_jitter()

    def close(self) -> None:
        self.client.close()


def main() -> None:
    monitor = MonitorClient(
        system="orchestrator",
        pipeline="orchestrator_daily",
        process_id="106",
        process_name="Floor Plan Analysis",
    )
    monitor.start()

    repo = GuardedFloorPlanRepository()
    stats = AnalysisStats()

    try:
        print("=" * 80)
        print("FLOOR PLAN ANALYSIS — Guarded Run")
        print("=" * 80)
        print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        if not repo.suburbs:
            raise EmptyWorkSetError("No target suburb collections available.")

        backlog = repo.count_needing_analysis()
        print("Needing analysis per suburb:")
        for suburb, count in backlog.items():
            print(f"  - {suburb}: {count}")

        candidates = repo.fetch_candidates()
        if not candidates:
            raise EmptyWorkSetError("No properties need floor plan analysis.")

        print(f"\nLoaded {len(candidates)} candidate properties\n")

        vision_client = OllamaFloorPlanClient()

        for idx, prop in enumerate(candidates, 1):
            stats.processed += 1
            start = time.time()
            try:
                safe_prop = _normalize_property_doc(prop)

                # Check if the property actually has usable images after normalization.
                # If not, write a stub so it graduates out of the candidate query
                # and does not re-enter on subsequent runs. This is a data gap, not an error.
                resolved_images = get_property_images(safe_prop)
                if not resolved_images:
                    stats.skipped_no_images += 1
                    suburb_key = prop.get("_collection", "unknown")
                    repo.update_with_floor_plan_analysis(
                        document_id=prop["_id"],
                        suburb=suburb_key,
                        floor_plan_analysis={
                            "has_floor_plan": False,
                            "skip_reason": "no_images_after_normalization",
                        },
                    )
                    print(f"⊘ Skipped {prop.get('_id')} — no usable images (stub written)")
                    continue

                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(PROPERTY_TIMEOUT_SECONDS)
                success = _legacy_process_property(safe_prop, vision_client, repo)
                duration = time.time() - start
                if success:
                    stats.successes += 1
                else:
                    stats.errors += 1
            except PropertyProcessingTimeout as exc:
                stats.errors += 1
                print(f"✗ Timeout processing property {prop.get('_id')}: {exc}")
            except Exception as exc:  # pylint: disable=broad-except
                stats.errors += 1
                print(f"✗ Error processing property {prop.get('_id')}: {exc}")
            finally:
                signal.alarm(0)

            if idx % 10 == 0:
                print(
                    f"[Progress] {idx}/{len(candidates)} "
                    f"(successes: {stats.successes}, errors: {stats.errors}, "
                    f"skipped: {stats.skipped_no_images})"
                )

        # Error ratio excludes skipped (no-images) properties — they are data gaps, not failures
        actionable = stats.processed - stats.skipped_no_images
        error_ratio = stats.errors / actionable if actionable else 0.0
        monitor.log_metric("properties_processed", stats.processed)
        monitor.log_metric("properties_succeeded", stats.successes)
        monitor.log_metric("properties_skipped_no_images", stats.skipped_no_images)
        monitor.log_metric("errors", stats.errors)
        monitor.log_metric("error_ratio", round(error_ratio, 4))

        if stats.skipped_no_images:
            print(
                f"\nℹ️  {stats.skipped_no_images} properties skipped (no usable images) "
                f"— stubs written to prevent re-processing."
            )

        if actionable == 0 and stats.skipped_no_images > 0:
            print("All candidates were no-image skips. Nothing to process — marking success.")
        elif stats.processed == 0:
            raise EmptyWorkSetError("No properties were processed.")
        elif error_ratio > 0.05:
            raise RuntimeError(
                f"Error ratio {error_ratio:.2%} exceeds threshold "
                f"({stats.errors} errors out of {actionable} actionable); marking failure."
            )
        if stats.errors:
            monitor.log_warning(
                f"{stats.errors} properties failed ({error_ratio:.2%}) — retry next run."
            )

        monitor.finish(status="success")

    except EmptyWorkSetError as exc:
        monitor.log_error(str(exc))
        monitor.finish(status="failed")
        raise
    except Exception as exc:  # pylint: disable=broad-except
        monitor.log_error(f"Unhandled error: {exc}")
        monitor.finish(status="failed")
        raise
    finally:
        repo.close()


if __name__ == "__main__":
    main()
