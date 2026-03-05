#!/usr/bin/env python3
"""
Unknown Status Property Detector for Fields Orchestrator
Last Updated: 27/01/2026, 10:45 AM (Monday) - Brisbane

Last Updated: 28/01/2026, 6:33 PM (Wednesday) - Brisbane
- Snapshot/diff now uses `address` as canonical key (the DB currently has no `url` field)
- Snapshot file renamed to `state/pre_phase2_snapshot.json` to avoid collisions with daily snapshots

This module detects properties that remain in the properties_for_sale collection
after Phase 2 completes but were not found as currently listed on Domain.
These are properties of "unknown status" that require manual investigation.

Features:
- Takes snapshot of properties_for_sale before Phase 2 begins
- Compares snapshot with post-Phase 2 state
- Identifies properties that weren't moved to sold and weren't found as for-sale
- Shows popup alert with caution symbol
- Logs unknown status properties clearly
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from pymongo import MongoClient

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger import get_logger


class UnknownStatusDetector:
    """
    Detects properties with unknown status after Phase 2 pipeline.
    
    This class:
    1. Takes a snapshot of properties_for_sale before Phase 2
    2. Tracks which properties were found during Phase 2 scraping
    3. Identifies properties that remain but weren't found
    4. Alerts user via popup and logging
    """
    
    def __init__(self, mongodb_uri: str = "mongodb://localhost:27017/",
                 for_sale_db: str = "Gold_Coast",
                 target_suburbs: Optional[List[str]] = None):
        """
        Initialize the unknown status detector.

        Args:
            mongodb_uri: MongoDB connection URI
            for_sale_db: Database containing the per-suburb for-sale collections
            target_suburbs: Collection names (suburb slugs) to monitor,
                            e.g. ["robina", "varsity_lakes"]. If None, no snapshot is taken.
        """
        self.logger = get_logger()
        self.mongodb_uri = mongodb_uri
        self.for_sale_db = for_sale_db
        self.target_suburbs = target_suburbs or []
        self.client: Optional[MongoClient] = None
        self.db = None

        # Snapshot storage
        self.snapshot_file = Path(__file__).parent.parent / "state" / "pre_phase2_snapshot.json"
        self.pre_phase2_snapshot: Set[str] = set()  # canonical key: address
        self.unknown_properties: List[Dict[str, Any]] = []
    
    def connect_mongodb(self) -> bool:
        """
        Connect to MongoDB.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000,
                                      retryWrites=False, tls=True, tlsAllowInvalidCertificates=True)
            self.client.admin.command('ping')
            self.db = self.client[self.for_sale_db]
            self.logger.info("✅ Connected to MongoDB")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to MongoDB: {e}")
            return False
    
    def disconnect_mongodb(self) -> None:
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            self.logger.info("Disconnected from MongoDB")
    
    def take_pre_phase2_snapshot(self) -> bool:
        """
        Take a snapshot of all properties in properties_for_sale collection
        before Phase 2 begins.
        
        Returns:
            True if snapshot successful, False otherwise
        """
        try:
            if self.db is None:
                self.logger.error("Not connected to MongoDB")
                return False

            if not self.target_suburbs:
                self.logger.warning("⚠️ No target suburbs configured — skipping pre-Phase 2 snapshot")
                return False

            snapshot_data = []
            for suburb in self.target_suburbs:
                col = self.db[suburb]
                for prop in col.find({}, {'address': 1, 'last_updated': 1, '_id': 0}):
                    address = prop.get('address')
                    if address:
                        self.pre_phase2_snapshot.add(address)
                        snapshot_data.append({
                            'address': address,
                            'suburb': suburb,
                            'last_updated': str(prop.get('last_updated', '')),
                        })

            # Save snapshot to file
            self.snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.snapshot_file, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'count': len(snapshot_data),
                    'properties': snapshot_data
                }, f, indent=2)

            self.logger.info(f"📸 Pre-Phase 2 Snapshot: {len(snapshot_data)} properties across {len(self.target_suburbs)} suburb collections")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to take pre-Phase 2 snapshot: {e}")
            return False
    
    def load_snapshot(self) -> bool:
        """
        Load the pre-Phase 2 snapshot from file.
        
        Returns:
            True if snapshot loaded successfully, False otherwise
        """
        try:
            if not self.snapshot_file.exists():
                self.logger.warning("⚠️ No pre-Phase 2 snapshot found")
                return False
            
            with open(self.snapshot_file, 'r') as f:
                snapshot = json.load(f)

            self.pre_phase2_snapshot = set(prop['address'] for prop in snapshot['properties'] if prop.get('address'))
            
            self.logger.info(f"📂 Loaded snapshot: {len(self.pre_phase2_snapshot)} properties from {snapshot['timestamp']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load snapshot: {e}")
            return False
    
    def detect_unknown_status_properties(self) -> List[Dict[str, Any]]:
        """
        Detect properties with unknown status after Phase 2.
        
        This identifies properties that:
        1. Were in properties_for_sale before Phase 2
        2. Are still in properties_for_sale after Phase 2
        3. Were NOT found as currently listed during Phase 2 scraping
        4. Were NOT moved to properties_sold
        
        Returns:
            List of unknown status properties with details
        """
        try:
            if self.db is None:
                self.logger.error("Not connected to MongoDB")
                return []
            
            if not self.pre_phase2_snapshot:
                self.logger.warning("⚠️ No pre-Phase 2 snapshot available")
                return []

            # Get current addresses across all target suburb collections
            current_for_sale_by_address = {}
            for suburb in self.target_suburbs:
                col = self.db[suburb]
                for prop in col.find({}, {'address': 1, 'last_updated': 1, '_id': 0}):
                    address = prop.get('address')
                    if address:
                        current_for_sale_by_address[address] = prop

            # Get properties moved to sold (now in Gold_Coast with listing_status: "sold")
            moved_to_sold_addresses: Set[str] = set()
            for suburb in self.target_suburbs:
                try:
                    sold_col = self.for_sale_db[suburb]
                    for prop in sold_col.find(
                        {'listing_status': 'sold', 'address': {'$in': list(self.pre_phase2_snapshot)}},
                        {'address': 1, '_id': 0}
                    ):
                        if prop.get('address'):
                            moved_to_sold_addresses.add(prop['address'])
                except Exception:
                    pass
            
            # Identify unknown status properties
            self.unknown_properties = []
            
            for address in self.pre_phase2_snapshot:
                # Check if still in for_sale
                if address in current_for_sale_by_address:
                    # Check if it was moved to sold (shouldn't be in both, but check anyway)
                    if address not in moved_to_sold_addresses:
                        # This property is still in for_sale and wasn't moved to sold
                        # Check if it was recently scraped (found during Phase 2)
                        prop = current_for_sale_by_address[address]
                        last_updated = prop.get('last_updated')

                        # If last_updated is recent (within last 24 hours), it was re-scraped
                        is_recent = False
                        if last_updated:
                            try:
                                if isinstance(last_updated, str):
                                    updated_time = datetime.strptime(last_updated[:19], "%Y-%m-%dT%H:%M:%S")
                                else:
                                    updated_time = last_updated
                                time_diff = (datetime.now() - updated_time).total_seconds()
                                is_recent = time_diff < 86400  # 24 hours
                            except Exception:
                                pass

                        if not is_recent:
                            self.unknown_properties.append({
                                'address': prop.get('address', 'Unknown Address'),
                                'last_updated': str(last_updated) if last_updated else 'Never',
                            })
            
            # Log results
            if self.unknown_properties:
                self.logger.warning(f"⚠️ UNKNOWN STATUS DETECTED: {len(self.unknown_properties)} properties")
                self.logger.warning("=" * 80)
                self.logger.warning("The following properties are in 'for_sale' collection but were NOT found")
                self.logger.warning("as currently listed on Domain during Phase 2 scraping:")
                self.logger.warning("=" * 80)
                
                for i, prop in enumerate(self.unknown_properties, 1):
                    self.logger.warning(f"\n{i}. {prop['address']}")
                    self.logger.warning(f"   Last Updated: {prop['last_updated']}")
                
                self.logger.warning("\n" + "=" * 80)
                self.logger.warning("⚠️ MANUAL INVESTIGATION REQUIRED")
                self.logger.warning("These properties may have:")
                self.logger.warning("  - Been delisted without selling")
                self.logger.warning("  - Changed URLs on Domain")
                self.logger.warning("  - Temporarily removed from market")
                self.logger.warning("  - Data quality issues")
                self.logger.warning("=" * 80 + "\n")
            else:
                self.logger.info("✅ No unknown status properties detected")
            
            return self.unknown_properties
            
        except Exception as e:
            self.logger.error(f"❌ Failed to detect unknown status properties: {e}")
            return []
    
    def show_alert_popup(self) -> None:
        """
        Show a popup alert with caution symbol listing unknown status properties.
        Uses AppleScript for macOS native dialog.
        """
        if not self.unknown_properties:
            return
        
        # Build property list for dialog
        property_list = []
        for i, prop in enumerate(self.unknown_properties[:10], 1):  # Limit to 10 for display
            address = prop['address'][:60]  # Truncate long addresses
            property_list.append(f"{i}. {address}")
        
        if len(self.unknown_properties) > 10:
            property_list.append(f"... and {len(self.unknown_properties) - 10} more")
        
        properties_text = "\\n".join(property_list)
        
        # Create AppleScript dialog
        script = f'''
        tell application "System Events"
            activate
            display dialog "⚠️ UNKNOWN STATUS PROPERTIES DETECTED" & return & return & ¬
                "{len(self.unknown_properties)} properties remain in 'for_sale' collection but were NOT found as currently listed on Domain:" & return & return & ¬
                "{properties_text}" & return & return & ¬
                "These properties require MANUAL INVESTIGATION." & return & ¬
                "Check the orchestrator logs for full details." ¬
                buttons {{"View Logs", "OK"}} ¬
                default button "OK" ¬
                with icon caution
            
            if button returned of result is "View Logs" then
                do shell script "open -a Console /Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log"
            end if
        end tell
        '''
        
        try:
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=300)
            self.logger.info("✅ Alert popup displayed to user")
        except Exception as e:
            self.logger.error(f"❌ Failed to show alert popup: {e}")
    
    def save_unknown_status_report(self) -> None:
        """Save a detailed report of unknown status properties to file."""
        if not self.unknown_properties:
            return

        try:
            report_file = Path(__file__).parent.parent / "logs" / "unknown_status_report.json"
            report_file.parent.mkdir(parents=True, exist_ok=True)

            # Load existing history or start fresh
            history = []
            if report_file.exists():
                try:
                    history = json.loads(report_file.read_text(encoding="utf-8"))
                    if not isinstance(history, list):
                        history = []
                except Exception:
                    history = []

            history.append({
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'count': len(self.unknown_properties),
                'properties': self.unknown_properties,
                'action_required': 'Manual investigation needed for these properties'
            })

            report_file.write_text(json.dumps(history, indent=2), encoding="utf-8")

            self.logger.info(f"📄 Unknown status report saved: {report_file} ({len(history)} total entries)")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save report: {e}")
    
    def run_detection(self) -> bool:
        """
        Run the complete unknown status detection process.
        
        Returns:
            True if detection completed (regardless of findings), False on error
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("🔍 UNKNOWN STATUS DETECTION - Starting")
        self.logger.info("=" * 80 + "\n")
        
        try:
            # Connect to MongoDB
            if not self.connect_mongodb():
                return False
            
            # Load snapshot
            if not self.load_snapshot():
                self.logger.warning("⚠️ Cannot detect unknown status without pre-Phase 2 snapshot")
                return False
            
            # Detect unknown status properties
            unknown = self.detect_unknown_status_properties()
            
            # If unknown properties found, alert user
            if unknown:
                self.save_unknown_status_report()
                self.show_alert_popup()
            
            self.logger.info("\n" + "=" * 80)
            self.logger.info("🔍 UNKNOWN STATUS DETECTION - Complete")
            self.logger.info("=" * 80 + "\n")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Unknown status detection failed: {e}")
            return False
        finally:
            self.disconnect_mongodb()


def main():
    """Main entry point for standalone execution."""
    from src.logger import setup_logger
    
    setup_logger(level="INFO", console_output=True)
    
    detector = UnknownStatusDetector()
    success = detector.run_detection()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
