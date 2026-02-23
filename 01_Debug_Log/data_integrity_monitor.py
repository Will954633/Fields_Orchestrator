#!/usr/bin/env python3
"""
Data Integrity Monitor for Fields Orchestrator

Last Updated: 05/02/2026, 8:16 AM (Wednesday) - Brisbane

This module monitors and verifies data integrity throughout the orchestrator processes:
1. Sold Property Migration - Verifies data preservation when moving properties from for_sale to sold
2. Static Record Updates - Verifies Gold_Coast database updates with sale information
3. New Listing Matching - Verifies newly listed properties are matched to static records

This script runs every time the orchestrator runs and maintains its own detailed log.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger import get_logger


@dataclass
class SoldPropertyCheck:
    """Results from checking a sold property migration"""
    address: str
    check_passed: bool
    issues: List[str]
    last_price_preserved: Optional[str]
    price_history_count: int
    agent_description_history_count: int
    moved_from_for_sale: bool
    exists_in_sold: bool
    static_record_updated: bool
    static_record_suburb: Optional[str]
    timestamp: str


@dataclass
class NewListingCheck:
    """Results from checking a newly listed property"""
    address: str
    check_passed: bool
    issues: List[str]
    has_static_record_link: bool
    static_record_found: bool
    static_record_suburb: Optional[str]
    gold_coast_doc_id: Optional[str]
    timestamp: str


@dataclass
class IntegrityReport:
    """Complete integrity check report"""
    run_id: str
    timestamp: str
    sold_properties_checked: int
    sold_properties_passed: int
    sold_properties_failed: int
    new_listings_checked: int
    new_listings_matched: int
    new_listings_unmatched: int
    static_update_failures: List[str]
    sold_property_details: List[SoldPropertyCheck]
    new_listing_details: List[NewListingCheck]
    errors: List[str]


class DataIntegrityMonitor:
    """
    Monitors data integrity across the orchestrator processes.
    
    Verifies:
    - Sold property data preservation (price history, agent descriptions)
    - Proper migration from for_sale to sold collections
    - Static record updates in Gold_Coast database
    - New listing matching to static records
    """
    
    def __init__(
        self,
        mongo_uri: str = "mongodb://127.0.0.1:27017/",
        property_database: str = "property_data",
        static_database: str = "Gold_Coast",
        log_dir: str = "01_Debug_Log/logs"
    ):
        self.logger = get_logger()
        self.mongo_uri = mongo_uri
        self.property_database = property_database
        self.static_database = static_database
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
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
            self.logger.info("✅ DataIntegrityMonitor: Connected to MongoDB")
            return True
        except ConnectionFailure as e:
            self.logger.error(f"❌ DataIntegrityMonitor: Failed to connect to MongoDB: {e}")
            return False
    
    def close(self) -> None:
        """Close MongoDB connection"""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.property_db = None
            self.static_db = None
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in Brisbane time"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _find_static_record(self, address: str) -> tuple[Optional[Dict], Optional[str]]:
        """
        Find a property's static record in the Gold_Coast database.
        
        Returns: (document, suburb_collection_name) or (None, None)
        """
        # Get all suburb collections
        collections = self.static_db.list_collection_names()
        
        # Try to find the property in each suburb collection
        for collection_name in collections:
            if collection_name.startswith("system."):
                continue
            
            collection = self.static_db[collection_name]
            doc = collection.find_one({"address": address})
            if doc:
                return doc, collection_name
        
        return None, None
    
    def check_sold_property(self, address: str, run_id: str) -> SoldPropertyCheck:
        """
        Verify a sold property's data integrity.
        
        Checks:
        1. Last known listing price is preserved
        2. Price history is maintained
        3. Agent description history is maintained
        4. Property was removed from for_sale collection
        5. Property exists in sold collection
        6. Static record was updated with sale information
        """
        issues = []
        timestamp = self._get_timestamp()
        
        # Check for_sale collection (should NOT exist)
        for_sale_col = self.property_db["properties_for_sale"]
        in_for_sale = for_sale_col.find_one({"address": address})
        moved_from_for_sale = in_for_sale is None
        
        if in_for_sale:
            issues.append("Property still exists in for_sale collection")
        
        # Check sold collection (should exist)
        sold_col = self.property_db["properties_sold"]
        sold_doc = sold_col.find_one({"address": address})
        exists_in_sold = sold_doc is not None
        
        if not sold_doc:
            issues.append("Property not found in sold collection")
            return SoldPropertyCheck(
                address=address,
                check_passed=False,
                issues=issues,
                last_price_preserved=None,
                price_history_count=0,
                agent_description_history_count=0,
                moved_from_for_sale=moved_from_for_sale,
                exists_in_sold=False,
                static_record_updated=False,
                static_record_suburb=None,
                timestamp=timestamp
            )
        
        # Check price preservation
        orch = sold_doc.get("orchestrator", {})
        history = orch.get("history", {})
        
        price_history = history.get("price", [])
        last_price = price_history[-1]["value"] if price_history else None
        
        # Verify last price is NOT overwritten by sold_price
        current_price = sold_doc.get("price")
        sold_price = sold_doc.get("sold_price")
        
        if sold_price and current_price == sold_price and last_price != sold_price:
            issues.append(f"Last listing price ({last_price}) was overwritten with sold price ({sold_price})")
        
        # Check agent description history
        agent_desc_history = history.get("agent_description", [])
        
        if len(price_history) == 0:
            issues.append("No price history found")
        
        # Check static record update
        static_doc, suburb = self._find_static_record(address)
        static_updated = False
        
        if static_doc:
            # Check if sale information was added
            sale_history = static_doc.get("sale_history", [])
            recent_sale = sale_history[-1] if sale_history else None
            
            if recent_sale and recent_sale.get("sold_price") == sold_price:
                static_updated = True
            else:
                issues.append(f"Static record in {suburb} not updated with sale information")
        else:
            issues.append("Static record not found in Gold_Coast database")
        
        check_passed = len(issues) == 0
        
        return SoldPropertyCheck(
            address=address,
            check_passed=check_passed,
            issues=issues,
            last_price_preserved=str(last_price) if last_price else None,
            price_history_count=len(price_history),
            agent_description_history_count=len(agent_desc_history),
            moved_from_for_sale=moved_from_for_sale,
            exists_in_sold=exists_in_sold,
            static_record_updated=static_updated,
            static_record_suburb=suburb,
            timestamp=timestamp
        )
    
    def check_new_listing(self, address: str) -> NewListingCheck:
        """
        Verify a newly listed property is matched to its static record.
        
        Checks:
        1. Property has a link to its Gold_Coast static record
        2. Static record exists and can be found
        3. Document ID is stored for future reference
        """
        issues = []
        timestamp = self._get_timestamp()
        
        # Get the listing document
        for_sale_col = self.property_db["properties_for_sale"]
        listing_doc = for_sale_col.find_one({"address": address})
        
        if not listing_doc:
            issues.append("Property not found in for_sale collection")
            return NewListingCheck(
                address=address,
                check_passed=False,
                issues=issues,
                has_static_record_link=False,
                static_record_found=False,
                static_record_suburb=None,
                gold_coast_doc_id=None,
                timestamp=timestamp
            )
        
        # Check for static record link
        orch = listing_doc.get("orchestrator", {})
        gold_coast_doc_id = orch.get("gold_coast_doc_id")
        has_link = gold_coast_doc_id is not None
        
        if not has_link:
            issues.append("No gold_coast_doc_id link found in orchestrator metadata")
        
        # Try to find the static record
        static_doc, suburb = self._find_static_record(address)
        static_found = static_doc is not None
        
        if not static_found:
            issues.append("Static record not found in Gold_Coast database")
        elif has_link and str(static_doc.get("_id")) != str(gold_coast_doc_id):
            issues.append("gold_coast_doc_id does not match actual static record _id")
        
        check_passed = len(issues) == 0
        
        return NewListingCheck(
            address=address,
            check_passed=check_passed,
            issues=issues,
            has_static_record_link=has_link,
            static_record_found=static_found,
            static_record_suburb=suburb,
            gold_coast_doc_id=str(gold_coast_doc_id) if gold_coast_doc_id else None,
            timestamp=timestamp
        )
    
    def run_integrity_check(self, run_id: str) -> IntegrityReport:
        """
        Run complete integrity check for the current orchestrator run.
        
        Returns detailed report of all checks performed.
        """
        self.logger.info("=" * 80)
        self.logger.info("STARTING DATA INTEGRITY CHECK")
        self.logger.info(f"Run ID: {run_id}")
        self.logger.info(f"Timestamp: {self._get_timestamp()}")
        self.logger.info("=" * 80)
        
        errors = []
        sold_checks = []
        new_listing_checks = []
        static_failures = []
        
        try:
            # Get recently moved sold properties
            sold_col = self.property_db["properties_sold"]
            recent_sold = sold_col.find({
                "orchestrator.migrated_to_sold.run_id": run_id
            })
            
            sold_count = 0
            for sold_doc in recent_sold:
                sold_count += 1
                address = sold_doc.get("address")
                if address:
                    check = self.check_sold_property(address, run_id)
                    sold_checks.append(check)
                    
                    if not check.check_passed:
                        self.logger.warning(f"❌ Sold property check FAILED: {address}")
                        for issue in check.issues:
                            self.logger.warning(f"   - {issue}")
                    else:
                        self.logger.info(f"✅ Sold property check PASSED: {address}")
                    
                    if not check.static_record_updated:
                        static_failures.append(address)
            
            # Get newly listed properties (added in this run)
            for_sale_col = self.property_db["properties_for_sale"]
            new_listings = for_sale_col.find({
                "orchestrator.first_seen_run_id": run_id
            })
            
            new_count = 0
            for listing_doc in new_listings:
                new_count += 1
                address = listing_doc.get("address")
                if address:
                    check = self.check_new_listing(address)
                    new_listing_checks.append(check)
                    
                    if not check.check_passed:
                        self.logger.warning(f"❌ New listing check FAILED: {address}")
                        for issue in check.issues:
                            self.logger.warning(f"   - {issue}")
                    else:
                        self.logger.info(f"✅ New listing check PASSED: {address}")
            
            self.logger.info("=" * 80)
            self.logger.info("INTEGRITY CHECK SUMMARY")
            self.logger.info(f"Sold Properties Checked: {len(sold_checks)}")
            self.logger.info(f"Sold Properties Passed: {sum(1 for c in sold_checks if c.check_passed)}")
            self.logger.info(f"Sold Properties Failed: {sum(1 for c in sold_checks if not c.check_passed)}")
            self.logger.info(f"New Listings Checked: {len(new_listing_checks)}")
            self.logger.info(f"New Listings Matched: {sum(1 for c in new_listing_checks if c.check_passed)}")
            self.logger.info(f"New Listings Unmatched: {sum(1 for c in new_listing_checks if not c.check_passed)}")
            self.logger.info(f"Static Record Update Failures: {len(static_failures)}")
            self.logger.info("=" * 80)
            
        except Exception as e:
            error_msg = f"Error during integrity check: {e}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        # Create report
        report = IntegrityReport(
            run_id=run_id,
            timestamp=self._get_timestamp(),
            sold_properties_checked=len(sold_checks),
            sold_properties_passed=sum(1 for c in sold_checks if c.check_passed),
            sold_properties_failed=sum(1 for c in sold_checks if not c.check_passed),
            new_listings_checked=len(new_listing_checks),
            new_listings_matched=sum(1 for c in new_listing_checks if c.check_passed),
            new_listings_unmatched=sum(1 for c in new_listing_checks if not c.check_passed),
            static_update_failures=static_failures,
            sold_property_details=sold_checks,
            new_listing_details=new_listing_checks,
            errors=errors
        )
        
        # Save report to file
        self._save_report(report)
        
        return report
    
    def _save_report(self, report: IntegrityReport) -> None:
        """Save integrity report to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"integrity_report_{report.run_id}_{timestamp}.json"
        filepath = self.log_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(asdict(report), f, indent=2, default=str)
            self.logger.info(f"📄 Integrity report saved: {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save integrity report: {e}")
    
    def get_recent_reports(self, limit: int = 10) -> List[Dict]:
        """Get the most recent integrity reports"""
        reports = []
        
        for filepath in sorted(self.log_dir.glob("integrity_report_*.json"), reverse=True)[:limit]:
            try:
                with open(filepath, 'r') as f:
                    reports.append(json.load(f))
            except Exception as e:
                self.logger.warning(f"Failed to load report {filepath}: {e}")
        
        return reports


def main():
    """Main entry point for standalone execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data Integrity Monitor for Fields Orchestrator")
    parser.add_argument('--run-id', required=True, help='Orchestrator run ID to check')
    parser.add_argument('--mongo-uri', default='mongodb://127.0.0.1:27017/', help='MongoDB URI')
    parser.add_argument('--property-db', default='property_data', help='Property database name')
    parser.add_argument('--static-db', default='Gold_Coast', help='Static records database name')
    parser.add_argument('--log-dir', default='01_Debug_Log/logs', help='Log directory')
    
    args = parser.parse_args()
    
    monitor = DataIntegrityMonitor(
        mongo_uri=args.mongo_uri,
        property_database=args.property_db,
        static_database=args.static_db,
        log_dir=args.log_dir
    )
    
    if not monitor.connect():
        sys.exit(1)
    
    try:
        report = monitor.run_integrity_check(args.run_id)
        
        # Print summary
        print("\n" + "=" * 80)
        print("DATA INTEGRITY CHECK COMPLETE")
        print("=" * 80)
        print(f"Run ID: {report.run_id}")
        print(f"Timestamp: {report.timestamp}")
        print(f"\nSold Properties:")
        print(f"  Checked: {report.sold_properties_checked}")
        print(f"  Passed: {report.sold_properties_passed}")
        print(f"  Failed: {report.sold_properties_failed}")
        print(f"\nNew Listings:")
        print(f"  Checked: {report.new_listings_checked}")
        print(f"  Matched: {report.new_listings_matched}")
        print(f"  Unmatched: {report.new_listings_unmatched}")
        print(f"\nStatic Record Update Failures: {len(report.static_update_failures)}")
        
        if report.static_update_failures:
            print("\nFailed Static Updates:")
            for address in report.static_update_failures:
                print(f"  - {address}")
        
        print("=" * 80)
        
        # Exit with error code if there were failures
        if report.sold_properties_failed > 0 or report.new_listings_unmatched > 0:
            sys.exit(1)
        
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
