#!/usr/bin/env python3
"""
Static Record Matcher for Fields Orchestrator

Last Updated: 05/02/2026, 8:18 AM (Wednesday) - Brisbane

This module matches newly listed properties to their static records in the Gold_Coast database.
It adds the gold_coast_doc_id to the orchestrator metadata for future reference.

This should run as part of the orchestrator pipeline to ensure all new listings are matched
to their static records BEFORE they are sold, preventing matching issues later.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger import get_logger


@dataclass
class MatchResult:
    """Result of matching a property to its static record"""
    address: str
    matched: bool
    suburb: Optional[str]
    gold_coast_doc_id: Optional[str]
    confidence: str  # "exact", "fuzzy", "none"
    notes: List[str]


class StaticRecordMatcher:
    """
    Matches properties in properties_for_sale to their static records in Gold_Coast database.
    
    Matching strategy:
    1. Exact address match (preferred)
    2. Fuzzy address match (normalized, case-insensitive)
    3. Match by coordinates if available
    """
    
    def __init__(
        self,
        mongo_uri: str = "mongodb://127.0.0.1:27017/",
        property_database: str = "property_data",
        static_database: str = "Gold_Coast"
    ):
        self.logger = get_logger()
        self.mongo_uri = mongo_uri
        self.property_database = property_database
        self.static_database = static_database
        
        self.client: Optional[MongoClient] = None
        self.property_db = None
        self.static_db = None
    
    def connect(self) -> bool:
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.property_db = self.client[self.property_database]
            self.static_db = self.client[self.static_database]
            self.logger.info("✅ StaticRecordMatcher: Connected to MongoDB")
            return True
        except ConnectionFailure as e:
            self.logger.error(f"❌ StaticRecordMatcher: Failed to connect to MongoDB: {e}")
            return False
    
    def close(self) -> None:
        """Close MongoDB connection"""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.property_db = None
            self.static_db = None
    
    def _normalize_address(self, address: str) -> str:
        """Normalize address for fuzzy matching"""
        if not address:
            return ""
        
        # Convert to lowercase and remove extra whitespace
        normalized = " ".join(address.lower().split())
        
        # Common normalizations
        replacements = {
            " street": " st",
            " road": " rd",
            " avenue": " ave",
            " drive": " dr",
            " court": " ct",
            " place": " pl",
            " terrace": " tce",
            " crescent": " cres",
            " boulevard": " blvd",
            " highway": " hwy",
            " lane": " ln",
            " parade": " pde",
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def _find_static_record(self, address: str) -> Tuple[Optional[Dict], Optional[str], str]:
        """
        Find a property's static record in the Gold_Coast database.
        
        Returns: (document, suburb_collection_name, confidence)
        confidence: "exact", "fuzzy", or "none"
        """
        # Get all suburb collections
        collections = self.static_db.list_collection_names()
        
        # Try exact match first
        for collection_name in collections:
            if collection_name.startswith("system."):
                continue
            
            collection = self.static_db[collection_name]
            doc = collection.find_one({"address": address})
            if doc:
                return doc, collection_name, "exact"
        
        # Try fuzzy match
        normalized_search = self._normalize_address(address)
        
        for collection_name in collections:
            if collection_name.startswith("system."):
                continue
            
            collection = self.static_db[collection_name]
            
            # Get all documents and check normalized addresses
            for doc in collection.find({}):
                doc_address = doc.get("address", "")
                if self._normalize_address(doc_address) == normalized_search:
                    return doc, collection_name, "fuzzy"
        
        return None, None, "none"
    
    def match_property(self, address: str, run_id: str) -> MatchResult:
        """
        Match a single property to its static record.
        
        Args:
            address: Property address to match
            run_id: Current orchestrator run ID
        
        Returns:
            MatchResult with matching details
        """
        notes = []
        
        # Find the static record
        static_doc, suburb, confidence = self._find_static_record(address)
        
        if not static_doc:
            notes.append("No static record found in Gold_Coast database")
            return MatchResult(
                address=address,
                matched=False,
                suburb=None,
                gold_coast_doc_id=None,
                confidence=confidence,
                notes=notes
            )
        
        # Get the document ID
        doc_id = str(static_doc.get("_id"))
        
        # Update the for_sale document with the link
        for_sale_col = self.property_db["properties_for_sale"]
        listing_doc = for_sale_col.find_one({"address": address})
        
        if not listing_doc:
            notes.append("Property not found in for_sale collection")
            return MatchResult(
                address=address,
                matched=False,
                suburb=suburb,
                gold_coast_doc_id=doc_id,
                confidence=confidence,
                notes=notes
            )
        
        # Update orchestrator metadata
        orch = listing_doc.get("orchestrator", {})
        orch["gold_coast_doc_id"] = doc_id
        orch["gold_coast_suburb"] = suburb
        orch["static_record_matched_at"] = datetime.now()
        orch["static_record_matched_run_id"] = run_id
        orch["match_confidence"] = confidence
        
        # Save the update
        for_sale_col.update_one(
            {"address": address},
            {"$set": {"orchestrator": orch}}
        )
        
        if confidence == "fuzzy":
            notes.append(f"Matched using fuzzy address matching to {suburb}")
        else:
            notes.append(f"Exact match found in {suburb}")
        
        return MatchResult(
            address=address,
            matched=True,
            suburb=suburb,
            gold_coast_doc_id=doc_id,
            confidence=confidence,
            notes=notes
        )
    
    def match_all_unmatched(self, run_id: str) -> Dict[str, Any]:
        """
        Match all properties in for_sale that don't have a gold_coast_doc_id.
        
        Args:
            run_id: Current orchestrator run ID
        
        Returns:
            Summary dictionary with matching statistics
        """
        self.logger.info("=" * 80)
        self.logger.info("STARTING STATIC RECORD MATCHING")
        self.logger.info(f"Run ID: {run_id}")
        self.logger.info("=" * 80)
        
        for_sale_col = self.property_db["properties_for_sale"]
        
        # Find all properties without a gold_coast_doc_id
        unmatched = for_sale_col.find({
            "$or": [
                {"orchestrator.gold_coast_doc_id": {"$exists": False}},
                {"orchestrator.gold_coast_doc_id": None}
            ]
        })
        
        results = []
        exact_matches = 0
        fuzzy_matches = 0
        no_matches = 0
        
        for doc in unmatched:
            address = doc.get("address")
            if not address:
                continue
            
            result = self.match_property(address, run_id)
            results.append(result)
            
            if result.matched:
                if result.confidence == "exact":
                    exact_matches += 1
                    self.logger.info(f"✅ Exact match: {address} → {result.suburb}")
                elif result.confidence == "fuzzy":
                    fuzzy_matches += 1
                    self.logger.info(f"🔍 Fuzzy match: {address} → {result.suburb}")
            else:
                no_matches += 1
                self.logger.warning(f"❌ No match: {address}")
        
        total_processed = len(results)
        total_matched = exact_matches + fuzzy_matches
        
        self.logger.info("=" * 80)
        self.logger.info("STATIC RECORD MATCHING SUMMARY")
        self.logger.info(f"Total Processed: {total_processed}")
        self.logger.info(f"Exact Matches: {exact_matches}")
        self.logger.info(f"Fuzzy Matches: {fuzzy_matches}")
        self.logger.info(f"No Matches: {no_matches}")
        self.logger.info(f"Success Rate: {(total_matched/total_processed*100) if total_processed > 0 else 0:.1f}%")
        self.logger.info("=" * 80)
        
        return {
            "run_id": run_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_processed": total_processed,
            "exact_matches": exact_matches,
            "fuzzy_matches": fuzzy_matches,
            "no_matches": no_matches,
            "success_rate": (total_matched/total_processed*100) if total_processed > 0 else 0,
            "results": [
                {
                    "address": r.address,
                    "matched": r.matched,
                    "suburb": r.suburb,
                    "confidence": r.confidence,
                    "notes": r.notes
                }
                for r in results
            ]
        }
    
    def match_new_listings(self, run_id: str) -> Dict[str, Any]:
        """
        Match only newly added properties from the current run.
        
        Args:
            run_id: Current orchestrator run ID
        
        Returns:
            Summary dictionary with matching statistics
        """
        self.logger.info("=" * 80)
        self.logger.info("MATCHING NEW LISTINGS TO STATIC RECORDS")
        self.logger.info(f"Run ID: {run_id}")
        self.logger.info("=" * 80)
        
        for_sale_col = self.property_db["properties_for_sale"]
        
        # Find properties added in this run without a gold_coast_doc_id
        new_listings = for_sale_col.find({
            "orchestrator.first_seen_run_id": run_id,
            "$or": [
                {"orchestrator.gold_coast_doc_id": {"$exists": False}},
                {"orchestrator.gold_coast_doc_id": None}
            ]
        })
        
        results = []
        exact_matches = 0
        fuzzy_matches = 0
        no_matches = 0
        
        for doc in new_listings:
            address = doc.get("address")
            if not address:
                continue
            
            result = self.match_property(address, run_id)
            results.append(result)
            
            if result.matched:
                if result.confidence == "exact":
                    exact_matches += 1
                    self.logger.info(f"✅ Exact match: {address} → {result.suburb}")
                elif result.confidence == "fuzzy":
                    fuzzy_matches += 1
                    self.logger.info(f"🔍 Fuzzy match: {address} → {result.suburb}")
            else:
                no_matches += 1
                self.logger.warning(f"❌ No match: {address}")
        
        total_processed = len(results)
        total_matched = exact_matches + fuzzy_matches
        
        self.logger.info("=" * 80)
        self.logger.info("NEW LISTING MATCHING SUMMARY")
        self.logger.info(f"Total New Listings: {total_processed}")
        self.logger.info(f"Exact Matches: {exact_matches}")
        self.logger.info(f"Fuzzy Matches: {fuzzy_matches}")
        self.logger.info(f"No Matches: {no_matches}")
        self.logger.info(f"Success Rate: {(total_matched/total_processed*100) if total_processed > 0 else 0:.1f}%")
        self.logger.info("=" * 80)
        
        return {
            "run_id": run_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_processed": total_processed,
            "exact_matches": exact_matches,
            "fuzzy_matches": fuzzy_matches,
            "no_matches": no_matches,
            "success_rate": (total_matched/total_processed*100) if total_processed > 0 else 0,
            "results": [
                {
                    "address": r.address,
                    "matched": r.matched,
                    "suburb": r.suburb,
                    "confidence": r.confidence,
                    "notes": r.notes
                }
                for r in results
            ]
        }


def main():
    """Main entry point for standalone execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Static Record Matcher for Fields Orchestrator")
    parser.add_argument('--run-id', required=True, help='Orchestrator run ID')
    parser.add_argument('--mode', choices=['new', 'all'], default='new',
                       help='Match only new listings or all unmatched properties')
    parser.add_argument('--mongo-uri', default='mongodb://127.0.0.1:27017/', help='MongoDB URI')
    parser.add_argument('--property-db', default='property_data', help='Property database name')
    parser.add_argument('--static-db', default='Gold_Coast', help='Static records database name')
    
    args = parser.parse_args()
    
    matcher = StaticRecordMatcher(
        mongo_uri=args.mongo_uri,
        property_database=args.property_db,
        static_database=args.static_db
    )
    
    if not matcher.connect():
        sys.exit(1)
    
    try:
        if args.mode == 'new':
            summary = matcher.match_new_listings(args.run_id)
        else:
            summary = matcher.match_all_unmatched(args.run_id)
        
        # Print summary
        print("\n" + "=" * 80)
        print("STATIC RECORD MATCHING COMPLETE")
        print("=" * 80)
        print(f"Run ID: {summary['run_id']}")
        print(f"Timestamp: {summary['timestamp']}")
        print(f"Total Processed: {summary['total_processed']}")
        print(f"Exact Matches: {summary['exact_matches']}")
        print(f"Fuzzy Matches: {summary['fuzzy_matches']}")
        print(f"No Matches: {summary['no_matches']}")
        print(f"Success Rate: {summary['success_rate']:.1f}%")
        print("=" * 80)
        
        # Exit with error if there were unmatched properties
        if summary['no_matches'] > 0:
            print(f"\n⚠️  Warning: {summary['no_matches']} properties could not be matched")
            sys.exit(1)
        
    finally:
        matcher.close()


if __name__ == "__main__":
    main()
