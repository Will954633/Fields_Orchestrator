#!/usr/bin/env python3
"""
Step 11 — Parse Room Dimensions (RU-guarded edition)

Extracts room dimensions from floor plan analysis outputs, computes per-room
areas, and stores aggregated totals for downstream enrichment steps.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

from pymongo.collection import Collection

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client, get_db, cosmos_retry, EmptyWorkSetError, sleep_with_jitter, FEATURED_SUBURBS  # type: ignore
from shared.monitor_client import MonitorClient  # type: ignore

load_env()

TARGET_SUBURBS = FEATURED_SUBURBS
LISTING_FILTER = {"listing_status": {"$in": ["for_sale", "sold"]}}


def _parse_dimension_string(dimensions_str: str) -> Tuple[float | None, float | None]:
    """Parse strings like '4.4m x 4.1m' into floats."""
    if not dimensions_str:
        return None, None

    patterns = [
        r"([\d.]+)\s*m?\s*[xX×]\s*([\d.]+)\s*m?",
        r"([\d.]+)\s*[xX×]\s*([\d.]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, str(dimensions_str))
        if match:
            try:
                width = float(match.group(1))
                length = float(match.group(2))
                return width, length
            except (ValueError, IndexError):
                continue
    return None, None


def _connect():
    return get_client()


def _suburb_collections(db) -> List[str]:
    excluded = {"suburb_statistics", "suburb_median_prices", "change_detection_snapshots"}
    collections = cosmos_retry(
        lambda: db.list_collection_names(),
        "list_collection_names",
        log=print,
    )
    return [c for c in collections if c in TARGET_SUBURBS and c not in excluded]


def _load_properties(col: Collection) -> List[Dict[str, Any]]:
    """Fetch properties that contain room data."""
    query = {
        "$and": [
            LISTING_FILTER,
            {
                "$or": [
                    {"floor_plan_analysis.rooms": {"$exists": True, "$ne": []}},
                    {
                        "ollama_floor_plan_analysis.floor_plan_data.rooms": {
                            "$exists": True,
                            "$ne": [],
                        }
                    },
                ]
            },
        ]
    }
    return cosmos_retry(lambda: list(col.find(query)), f"{col.name}.fetch_rooms", log=print)


def _extract_rooms(property_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    rooms = property_doc.get("floor_plan_analysis", {}).get("rooms", [])
    if rooms:
        return rooms
    ollama_fp = property_doc.get("ollama_floor_plan_analysis", {})
    fp_data = (
        ollama_fp.get("floor_plan_data", {})
        if isinstance(ollama_fp, dict)
        else {}
    )
    rooms = fp_data.get("rooms", []) if isinstance(fp_data, dict) else []
    return rooms


def _parse_rooms(rooms: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], float]:
    parsed_rooms: Dict[str, Dict[str, Any]] = {}
    total_area = 0.0

    for room in rooms:
        room_type = room.get("room_type", "").lower().strip()
        dimensions = room.get("dimensions")
        if not room_type:
            continue

        width = length = area = None
        if isinstance(dimensions, dict):
            width = dimensions.get("width")
            length = dimensions.get("length")
            area = dimensions.get("area")
            if area and not (width and length):
                width = length = None
            elif width and length and not area:
                area = round(float(width) * float(length), 2)
            if area:
                area = round(float(area), 2)
        elif dimensions:
            width, length = _parse_dimension_string(dimensions)
            if width and length:
                area = round(width * length, 2)

        if not area or area <= 0:
            continue

        base_type = room_type
        counter = 1
        final_type = base_type
        while final_type in parsed_rooms:
            counter += 1
            final_type = f"{base_type}_{counter}"

        parsed_rooms[final_type] = {
            "width": width,
            "length": length,
            "area": area,
            "source": room.get("source"),
            "room_name": room.get("room_name"),
        }
        total_area += area

    return parsed_rooms, round(total_area, 2)


def main() -> None:
    monitor = MonitorClient(
        system="orchestrator",
        pipeline="orchestrator_daily",
        process_id="11",
        process_name="Parse Room Dimensions",
    )
    monitor.start()

    client = _connect()
    db = client["Gold_Coast"]

    processed = updated = errors = 0

    try:
        print("=" * 80)
        print("PARSE ROOM DIMENSIONS — Guarded Run")
        print("=" * 80)
        print(f"Started: {datetime.now():%Y-%m-%d %H:%M:%S}\n")

        suburb_cols = _suburb_collections(db)
        if not suburb_cols:
            raise EmptyWorkSetError("No target suburb collections found with room data.")

        print(f"Processing suburbs: {', '.join(suburb_cols)}")

        properties: List[Dict[str, Any]] = []
        for suburb in suburb_cols:
            col = db[suburb]
            docs = _load_properties(col)
            for doc in docs:
                doc["_collection"] = suburb
                properties.append(doc)

        if not properties:
            raise EmptyWorkSetError("No properties contained room data for parsing.")

        print(f"Found {len(properties)} properties with candidate room data.\n")

        for prop in properties:
            processed += 1
            address = prop.get("address", "Unknown Address")
            collection = db[prop["_collection"]]

            try:
                rooms = _extract_rooms(prop)
                if not rooms:
                    continue

                parsed_rooms, total_area = _parse_rooms(rooms)
                if not parsed_rooms:
                    continue

                update_payload = {
                    "parsed_rooms": parsed_rooms,
                    "total_floor_area": total_area,
                    "parsed_rooms_updated": datetime.utcnow(),
                }

                cosmos_retry(
                    lambda coll=collection, pid=prop["_id"], payload=update_payload: coll.update_one(
                        {"_id": pid},
                        {"$set": payload},
                    ),
                    f"{collection.name}.update_rooms",
                    log=print,
                )
                updated += 1
                sleep_with_jitter()

                if processed % 25 == 0:
                    print(
                        f"[Progress] {processed}/{len(properties)} processed "
                        f"({updated} updated, {errors} errors)"
                    )

            except Exception as exc:  # pylint: disable=broad-except
                errors += 1
                print(f"✗ Error processing {address}: {exc}")

        error_ratio = errors / processed if processed else 1.0
        print("\n" + "=" * 80)
        print("Parse Room Dimensions Complete")
        print("=" * 80)
        print(f"Processed: {processed}")
        print(f"Updated: {updated}")
        print(f"Errors: {errors}")
        print(f"Error ratio: {error_ratio:.2%}")

        monitor.log_metric("properties_processed", processed)
        monitor.log_metric("properties_updated", updated)
        monitor.log_metric("errors", errors)
        monitor.log_metric("error_ratio", round(error_ratio, 4))

        if processed == 0:
            raise EmptyWorkSetError("No properties processed.")

        if error_ratio > 0.05:
            raise RuntimeError(
                f"Error ratio {error_ratio:.2%} exceeds threshold; marking step failed."
            )

        if errors:
            monitor.log_warning(
                f"{errors} properties failed ({error_ratio:.2%}); "
                "retryable on next run."
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
        client.close()


if __name__ == "__main__":
    try:
        main()
    except EmptyWorkSetError:
        # Propagate as non-zero exit to trigger orchestrator retry logic.
        sys.exit(2)
