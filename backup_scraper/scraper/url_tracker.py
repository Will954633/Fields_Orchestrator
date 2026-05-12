#!/usr/bin/env python3
"""
URL Tracker — local MongoDB backend.

Replaces the original Azure Cosmos DB implementation (subscription expired
May 2026). All state now lives in local MongoDB at the Gold_Coast database:

  Gold_Coast.{suburb}                — cadastral baseline + denormalized
                                       current-listing snapshot per address
  Gold_Coast.property_url_tracking   — per-address URL state (known_urls,
                                       last_seen, check_count)
  Gold_Coast.new_url_discoveries     — historical log of every scrape with
                                       full raw_data + extracted payload

The public method surface matches the prior Cosmos-backed URLTracker so
continuous_monitor.py needs no changes.
"""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from pymongo import MongoClient, ReturnDocument

UTC = timezone.utc

LOCAL_URI_DEFAULT = "mongodb://localhost:27017/"
DB_NAME = "Gold_Coast"

# Fields we copy from extracted_data onto the cadastral property doc as the
# current snapshot. Keep this list tight — it mirrors what production stores
# on each property document. Anything more nuanced lives in the discoveries log.
SNAPSHOT_FIELDS = (
    "listing_status",
    "bedrooms",
    "bathrooms",
    "carspaces",
    "property_type",
    "sale_price",
    "sold_date",
    "land_size_sqm",
    "description",
    "features",
    "property_images",
    "listing_url",
    "extraction_method",
    "extraction_confidence",
    "agents_description",
    "og_title",
)


def _normalise_address(addr: str) -> str:
    """
    Uppercase, strip commas, collapse whitespace for stable address matching.
    JSON files use either "33 Trinity Place, Robina, QLD 4226" (with commas)
    or "33 TRINITY PLACE ROBINA QLD 4226" (cadastral format). Both reduce to
    "33 TRINITY PLACE ROBINA QLD 4226" after normalization.
    """
    if not addr:
        return ""
    return re.sub(r"\s+", " ", addr.replace(",", " ").strip().upper())


class URLTracker:
    """Track URLs found for each property and detect changes (local-Mongo backed)."""

    def __init__(self, mongo_uri: Optional[str] = None):
        if mongo_uri is None:
            mongo_uri = LOCAL_URI_DEFAULT
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client[DB_NAME]

        self.tracking_collection = self.db["property_url_tracking"]
        self.discoveries_collection = self.db["new_url_discoveries"]

        self.tracking_collection.create_index(
            [("complete_address_norm", 1), ("suburb", 1)], unique=True
        )
        self.tracking_collection.create_index([("last_checked", -1)])
        self.discoveries_collection.create_index([("discovered_at", -1)])
        self.discoveries_collection.create_index([("complete_address_norm", 1), ("suburb", 1)])
        self.discoveries_collection.create_index([("suburb", 1), ("discovered_at", -1)])

        print(f"✅ URL Tracker initialized (local Mongo: {mongo_uri})")

    def get_known_urls(self, address: str, suburb: str) -> Set[str]:
        doc = self.tracking_collection.find_one(
            {"complete_address_norm": _normalise_address(address), "suburb": suburb}
        )
        if not doc:
            return set()
        return {u["url"] for u in doc.get("known_urls", [])}

    def detect_new_urls(
        self, address: str, suburb: str, current_url_data: List[Dict]
    ) -> List[Dict]:
        known_urls = self.get_known_urls(address, suburb)
        current_urls = {u["url"] for u in current_url_data}
        new_urls = current_urls - known_urls
        return [u for u in current_url_data if u["url"] in new_urls]

    def update_tracking(
        self,
        address: str,
        suburb: str,
        current_url_data: List[Dict],
        original_doc_id: Optional[str] = None,
    ):
        now = datetime.now(UTC)
        addr_norm = _normalise_address(address)

        existing = self.tracking_collection.find_one(
            {"complete_address_norm": addr_norm, "suburb": suburb}
        )

        if not existing:
            known_urls = [
                {
                    "url": u["url"],
                    "agency_keyword": u.get("agency_keyword", "unknown"),
                    "title": u.get("title", ""),
                    "first_seen": now,
                    "last_seen": now,
                    "check_count": 1,
                }
                for u in current_url_data
            ]
            self.tracking_collection.insert_one(
                {
                    "complete_address": address,
                    "complete_address_norm": addr_norm,
                    "suburb": suburb,
                    "known_urls": known_urls,
                    "total_urls_found": len(known_urls),
                    "last_checked": now,
                    "check_count": 1,
                    "original_doc_id": original_doc_id,
                }
            )
            return

        known_urls = existing.get("known_urls", [])
        known_url_set = {u["url"] for u in known_urls}
        current_url_set = {u["url"] for u in current_url_data}

        for entry in known_urls:
            if entry["url"] in current_url_set:
                entry["last_seen"] = now
                entry["check_count"] = entry.get("check_count", 0) + 1

        for u in current_url_data:
            if u["url"] not in known_url_set:
                known_urls.append(
                    {
                        "url": u["url"],
                        "agency_keyword": u.get("agency_keyword", "unknown"),
                        "title": u.get("title", ""),
                        "first_seen": now,
                        "last_seen": now,
                        "check_count": 1,
                    }
                )

        self.tracking_collection.update_one(
            {"complete_address_norm": addr_norm, "suburb": suburb},
            {
                "$set": {
                    "known_urls": known_urls,
                    "total_urls_found": len(known_urls),
                    "last_checked": now,
                },
                "$inc": {"check_count": 1},
            },
        )

    def record_discovery(
        self,
        address: str,
        suburb: str,
        new_url_data: Dict,
        raw_data: Dict,
        extracted_data: Dict,
    ) -> str:
        """
        Insert a discovery log entry AND update the snapshot on the cadastral
        property doc (Gold_Coast.{suburb}). Returns the discovery _id as a string.
        """
        now = datetime.now(UTC)
        addr_norm = _normalise_address(address)

        known_urls = list(self.get_known_urls(address, suburb))
        is_first_url = len(known_urls) == 0

        discovery = {
            "complete_address": address,
            "complete_address_norm": addr_norm,
            "suburb": suburb,
            "new_url": new_url_data["url"],
            "agency_keyword": new_url_data.get("agency_keyword", "unknown"),
            "title": new_url_data.get("title", ""),
            "is_recheck": bool(new_url_data.get("recheck")),
            "discovered_at": now,
            "raw_data": raw_data,
            "extracted_data": extracted_data,
            "previous_urls": known_urls,
            "is_first_url": is_first_url,
            "total_urls_now": len(known_urls) + 1,
            "processed": True,
            "saved_to_json": False,
            "json_file_path": None,
        }
        result = self.discoveries_collection.insert_one(discovery)

        self._upsert_property_snapshot(
            address=address,
            suburb=suburb,
            agency_keyword=new_url_data.get("agency_keyword", "unknown"),
            listing_url=new_url_data["url"],
            extracted_data=extracted_data,
            scraped_at=now,
        )

        return str(result.inserted_id)

    def _upsert_property_snapshot(
        self,
        address: str,
        suburb: str,
        agency_keyword: str,
        listing_url: str,
        extracted_data: Dict,
        scraped_at: datetime,
    ):
        """
        Merge the current listing snapshot onto the cadastral property doc in
        Gold_Coast.{suburb}. Match on complete_address (case-insensitive).
        If no cadastral match, create a listings-only doc keyed by address so
        we still capture data — coverage check will flag it for review.
        """
        suburb_coll = self.db[suburb.lower()]
        addr_norm = _normalise_address(address)
        new_status = extracted_data.get("listing_status")

        snapshot = {
            f"backup_scraper.{k}": extracted_data.get(k)
            for k in SNAPSHOT_FIELDS
            if extracted_data.get(k) is not None
        }
        snapshot.update(
            {
                "backup_scraper.listing_url": listing_url,
                "backup_scraper.agency": agency_keyword,
                "backup_scraper.last_scraped_at": scraped_at,
                "backup_scraper.address_input": address,
            }
        )
        if new_status:
            snapshot["listing_status"] = new_status
            snapshot["scrape_source"] = "backup_scraper"
            snapshot["last_updated"] = scraped_at

        # Match on complete_address_norm — populated by remediate_cadastral_norm.py
        # for cadastral docs, set on insert for listings-only stubs.
        existing = suburb_coll.find_one(
            {"complete_address_norm": addr_norm},
            {"_id": 1},
        )
        if existing:
            suburb_coll.update_one({"_id": existing["_id"]}, {"$set": snapshot})
            return

        # No cadastral match — insert a listings-only stub so data isn't lost.
        # `cadastral_match: false` flags it for later cleanup/review.
        suburb_coll.insert_one(
            {
                "complete_address": address,
                "complete_address_norm": addr_norm,
                "cadastral_match": False,
                "scrape_source": "backup_scraper",
                "first_seen_at": scraped_at,
                "last_updated": scraped_at,
                **snapshot,
            }
        )

    def mark_json_saved(self, discovery_id, json_path: str):
        """Mark a discovery as saved to JSON file. Accepts str or ObjectId."""
        from bson import ObjectId

        oid = discovery_id if isinstance(discovery_id, ObjectId) else ObjectId(str(discovery_id))
        self.discoveries_collection.update_one(
            {"_id": oid},
            {"$set": {"saved_to_json": True, "json_file_path": json_path}},
        )

    def get_stats(self) -> Dict:
        total_properties = self.tracking_collection.count_documents({})
        total_discoveries = self.discoveries_collection.count_documents({})
        pipeline = [{"$group": {"_id": "$suburb", "count": {"$sum": 1}}}]
        by_suburb = list(self.tracking_collection.aggregate(pipeline))
        return {
            "total_properties_tracked": total_properties,
            "total_discoveries": total_discoveries,
            "by_suburb": {item["_id"]: item["count"] for item in by_suburb},
        }


def _smoke_test():
    """Minimal smoke test against local Mongo."""
    print("=" * 80)
    print("URL TRACKER SMOKE TEST (local Mongo)")
    print("=" * 80)
    tracker = URLTracker()
    print("Stats:", tracker.get_stats())


if __name__ == "__main__":
    _smoke_test()
