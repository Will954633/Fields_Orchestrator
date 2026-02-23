#!/usr/bin/env python3
"""
Database Audit Script - Property Collection Validation
Created: 2026-02-17

This script audits the MongoDB database to find properties stored in incorrect collections.
It detects when a property's address suburb doesn't match its collection name, which happens
when Domain.com.au search returns cross-suburb results and the scraper assigns based on
search parameter instead of actual address.

ROOT CAUSE DETECTION:
- Bug in run_parallel_suburb_scrape.py (line 540) where property_data['suburb'] was set
  to self.suburb_name (search parameter) instead of extracting from actual address
- Domain.com.au returns properties from nearby suburbs with same postcode (e.g., Varsity Lakes
  4227 search returns Reedy Creek 4227 properties)
- Properties were inserted into wrong collection because collection assignment happened at
  initialization time based on search suburb

USAGE:
  python3 database_audit.py                 # Audit only, no fixes
  python3 database_audit.py --fix           # Audit and auto-fix issues
  python3 database_audit.py --verbose       # Show all details
  python3 database_audit.py --collection varsity_lakes  # Audit specific collection

INTEGRATION:
  This script is designed to run at the end of the orchestrator pipeline to verify
  data quality after scraping operations.
"""

import os
import sys
import argparse
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from pymongo import MongoClient
from bson import ObjectId

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

# Australian states for address parsing
AUSTRALIAN_STATES = ['QLD', 'NSW', 'VIC', 'SA', 'WA', 'TAS', 'NT', 'ACT']

class DatabaseAuditor:
    """Audits database for properties stored in incorrect collections"""

    def __init__(self, mongodb_uri: str = MONGODB_URI, database_name: str = DATABASE_NAME):
        """Initialize auditor"""
        self.mongodb_uri = mongodb_uri
        self.database_name = database_name
        self.client = None
        self.db = None
        self.errors = []
        self.stats = {
            'total_properties': 0,
            'total_collections': 0,
            'misplaced_properties': 0,
            'collections_with_errors': set(),
            'error_types': defaultdict(int),
            'suburbs_affected': set(),
        }

    def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.database_name]
            # Test connection
            self.client.admin.command('ping')
            return True
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            return False

    def extract_suburb_from_address(self, address: str) -> Optional[str]:
        """
        Extract suburb from address string.
        Example: "48 Peach Drive, Robina, QLD 4226" → "Robina"

        This is the CORRECT way to determine suburb from address.
        """
        if not address:
            return None

        # Match pattern: ", <SUBURB>, <STATE>"
        pattern = r',\s*([^,]+),\s*(' + '|'.join(AUSTRALIAN_STATES) + r')'
        match = re.search(pattern, address, re.IGNORECASE)

        if match:
            return match.group(1).strip()

        return None

    def normalize_suburb(self, suburb: str) -> str:
        """
        Normalize suburb name to collection name format.
        Example: "Varsity Lakes" → "varsity_lakes"
        """
        if not suburb:
            return ""
        return suburb.lower().replace(' ', '_').replace('-', '_')

    def audit_collection(self, collection_name: str, verbose: bool = False) -> List[Dict]:
        """
        Audit a single collection for misplaced properties.

        Returns:
            List of error dictionaries for misplaced properties
        """
        collection = self.db[collection_name]
        errors = []

        # Get all properties in this collection
        properties = list(collection.find({}))
        self.stats['total_properties'] += len(properties)

        if verbose:
            print(f"\n📂 Auditing collection: {collection_name} ({len(properties)} properties)")

        for prop in properties:
            address = prop.get('address', '')
            suburb_field = prop.get('suburb', '')
            listing_url = prop.get('listing_url', 'N/A')
            doc_id = prop.get('_id', 'N/A')

            # Extract actual suburb from address
            actual_suburb = self.extract_suburb_from_address(address)

            if not actual_suburb:
                # Can't validate without address suburb
                if verbose:
                    print(f"  ⚠️  Cannot extract suburb from: {address}")
                continue

            # Normalize for comparison
            actual_suburb_normalized = self.normalize_suburb(actual_suburb)
            collection_normalized = self.normalize_suburb(collection_name)
            suburb_field_normalized = self.normalize_suburb(suburb_field)

            # Check for mismatch between collection and actual suburb
            if actual_suburb_normalized != collection_normalized:
                error = {
                    'error_type': 'WRONG_COLLECTION',
                    'severity': 'HIGH',
                    'document_id': str(doc_id),
                    'address': address,
                    'actual_suburb': actual_suburb,
                    'actual_suburb_normalized': actual_suburb_normalized,
                    'current_collection': collection_name,
                    'correct_collection': actual_suburb_normalized,
                    'suburb_field_value': suburb_field,
                    'suburb_field_normalized': suburb_field_normalized,
                    'listing_url': listing_url,
                    'first_seen': prop.get('first_seen'),
                    'last_updated': prop.get('last_updated'),
                    'root_cause': self._determine_root_cause(
                        collection_normalized,
                        suburb_field_normalized,
                        actual_suburb_normalized
                    ),
                    'detected_at': datetime.now(),
                }

                errors.append(error)
                self.stats['misplaced_properties'] += 1
                self.stats['collections_with_errors'].add(collection_name)
                self.stats['error_types'][error['root_cause']] += 1
                self.stats['suburbs_affected'].add(actual_suburb)

                if verbose:
                    print(f"  ❌ MISMATCH FOUND:")
                    print(f"     Address: {address}")
                    print(f"     Actual Suburb: {actual_suburb}")
                    print(f"     Current Collection: {collection_name}")
                    print(f"     Should Be In: {actual_suburb_normalized}")
                    print(f"     Root Cause: {error['root_cause']}")

        return errors

    def _determine_root_cause(self, collection: str, suburb_field: str, actual_suburb: str) -> str:
        """
        Determine the root cause of the mismatch.

        Returns:
            Description of the root cause
        """
        if suburb_field == collection and suburb_field != actual_suburb:
            return (
                "BUG_IN_SCRAPER: Both suburb field and collection match the search parameter "
                "(not actual address). This indicates the scraper assigned suburb based on "
                "search parameter instead of extracting from address. "
                "Bug location: run_parallel_suburb_scrape.py line 540 (pre-fix version). "
                "Domain.com.au search returned cross-suburb results."
            )
        elif suburb_field == actual_suburb and collection != actual_suburb:
            return (
                "COLLECTION_ASSIGNMENT_BUG: Suburb field is correct but collection is wrong. "
                "This indicates the suburb was extracted correctly from address but the "
                "save_to_mongodb function used self.collection (search-based) instead of "
                "determining collection from actual suburb."
            )
        elif suburb_field != actual_suburb and collection == suburb_field:
            return (
                "ADDRESS_EXTRACTION_FAILURE: Suburb field matches collection but both are wrong. "
                "This indicates complete failure to extract suburb from address, falling back "
                "to search parameter for both field and collection."
            )
        else:
            return (
                "UNKNOWN: Complex mismatch pattern. Manual investigation required. "
                f"Collection={collection}, SuburbField={suburb_field}, ActualSuburb={actual_suburb}"
            )

    def audit_all_collections(self, specific_collection: Optional[str] = None, verbose: bool = False) -> List[Dict]:
        """
        Audit all collections (or specific collection) in the database.

        Args:
            specific_collection: If provided, only audit this collection
            verbose: Show detailed progress

        Returns:
            List of all errors found
        """
        all_errors = []

        # Collections to exclude (catch-all/aggregate collections with intentional cross-suburb data)
        EXCLUDED_COLLECTIONS = [
            'Gold_Coast_Recently_Sold',  # Catch-all for sold properties across all suburbs
        ]

        # Get collections to audit
        if specific_collection:
            collections = [specific_collection]
        else:
            collections = self.db.list_collection_names()
            # Filter out system collections, backups, and excluded collections
            collections = [c for c in collections
                          if not c.startswith('system.')
                          and '_backup_' not in c
                          and c not in EXCLUDED_COLLECTIONS]

        self.stats['total_collections'] = len(collections)

        if not specific_collection and EXCLUDED_COLLECTIONS:
            print(f"Note: Excluding {len(EXCLUDED_COLLECTIONS)} catch-all collection(s): {', '.join(EXCLUDED_COLLECTIONS)}\n")

        print(f"\n{'=' * 80}")
        print(f"DATABASE AUDIT STARTED")
        print(f"{'=' * 80}")
        print(f"Database: {self.database_name}")
        print(f"Collections to audit: {len(collections)}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 80}\n")

        for coll_name in sorted(collections):
            errors = self.audit_collection(coll_name, verbose=verbose)
            all_errors.extend(errors)

        self.errors = all_errors
        return all_errors

    def print_summary(self):
        """Print audit summary"""
        print(f"\n{'=' * 80}")
        print(f"AUDIT SUMMARY")
        print(f"{'=' * 80}")
        print(f"Total Properties Audited: {self.stats['total_properties']:,}")
        print(f"Total Collections Audited: {self.stats['total_collections']}")
        print(f"Misplaced Properties Found: {self.stats['misplaced_properties']}")
        print(f"Collections With Errors: {len(self.stats['collections_with_errors'])}")
        print(f"Suburbs Affected: {len(self.stats['suburbs_affected'])}")

        if self.stats['error_types']:
            print(f"\n{'=' * 80}")
            print("ERROR BREAKDOWN BY ROOT CAUSE:")
            print(f"{'=' * 80}")
            for root_cause, count in sorted(self.stats['error_types'].items(), key=lambda x: -x[1]):
                print(f"\n{count} properties - {root_cause[:80]}...")

        if self.stats['collections_with_errors']:
            print(f"\n{'=' * 80}")
            print("COLLECTIONS WITH ERRORS:")
            print(f"{'=' * 80}")
            for coll in sorted(self.stats['collections_with_errors']):
                coll_errors = [e for e in self.errors if e['current_collection'] == coll]
                print(f"  - {coll}: {len(coll_errors)} misplaced properties")

        print(f"\n{'=' * 80}\n")

    def print_detailed_errors(self, limit: int = 50):
        """Print detailed error reports"""
        if not self.errors:
            print("✅ No errors found!")
            return

        print(f"\n{'=' * 80}")
        print(f"DETAILED ERROR REPORT (showing first {min(limit, len(self.errors))} of {len(self.errors)})")
        print(f"{'=' * 80}\n")

        for i, error in enumerate(self.errors[:limit], 1):
            print(f"Error #{i}:")
            print(f"  Severity: {error['severity']}")
            print(f"  Document ID: {error['document_id']}")
            print(f"  Address: {error['address']}")
            print(f"  Actual Suburb: {error['actual_suburb']}")
            print(f"  Current Collection: {error['current_collection']}")
            print(f"  Correct Collection: {error['correct_collection']}")
            print(f"  Suburb Field Value: {error['suburb_field_value']}")
            print(f"  Listing URL: {error['listing_url'][:100]}")
            print(f"  First Seen: {error['first_seen']}")
            print(f"\n  ROOT CAUSE:")
            print(f"  {error['root_cause']}\n")
            print(f"  {'-' * 80}\n")

    def export_errors_to_log(self, log_file: str):
        """Export errors to detailed log file"""
        try:
            with open(log_file, 'w') as f:
                f.write(f"Database Audit Report\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Database: {self.database_name}\n")
                f.write(f"{'=' * 100}\n\n")

                f.write(f"SUMMARY\n")
                f.write(f"{'=' * 100}\n")
                f.write(f"Total Properties Audited: {self.stats['total_properties']:,}\n")
                f.write(f"Misplaced Properties Found: {self.stats['misplaced_properties']}\n")
                f.write(f"Collections With Errors: {len(self.stats['collections_with_errors'])}\n\n")

                f.write(f"DETAILED ERRORS\n")
                f.write(f"{'=' * 100}\n\n")

                for i, error in enumerate(self.errors, 1):
                    f.write(f"Error #{i}\n")
                    f.write(f"{'-' * 100}\n")
                    for key, value in error.items():
                        if key != 'root_cause':
                            f.write(f"{key}: {value}\n")
                    f.write(f"\nROOT CAUSE:\n{error['root_cause']}\n")
                    f.write(f"\n{'=' * 100}\n\n")

            print(f"\n✅ Detailed error log exported to: {log_file}")
            return True
        except Exception as e:
            print(f"\n❌ Failed to export error log: {e}")
            return False

    def fix_errors(self, dry_run: bool = False) -> int:
        """
        Fix all detected errors by moving properties to correct collections.

        Args:
            dry_run: If True, only show what would be done without making changes

        Returns:
            Number of properties fixed
        """
        if not self.errors:
            print("\n✅ No errors to fix!")
            return 0

        print(f"\n{'=' * 80}")
        print(f"{'DRY RUN - ' if dry_run else ''}FIXING ERRORS")
        print(f"{'=' * 80}")
        print(f"Properties to fix: {len(self.errors)}")
        if dry_run:
            print("(DRY RUN MODE - No actual changes will be made)")
        print(f"{'=' * 80}\n")

        fixed_count = 0
        failed_count = 0

        for i, error in enumerate(self.errors, 1):
            try:
                source_coll_name = error['current_collection']
                target_coll_name = error['correct_collection']
                doc_id = ObjectId(error['document_id'])

                print(f"[{i}/{len(self.errors)}] Moving property...")
                print(f"  From: {source_coll_name}")
                print(f"  To: {target_coll_name}")
                print(f"  Address: {error['address']}")

                if dry_run:
                    print("  ✓ Would move (dry run)\n")
                    fixed_count += 1
                    continue

                # Get collections
                source_coll = self.db[source_coll_name]
                target_coll = self.db[target_coll_name]

                # Get the document
                doc = source_coll.find_one({'_id': doc_id})

                if not doc:
                    print(f"  ✗ Document not found!\n")
                    failed_count += 1
                    continue

                # Update suburb field to correct value
                doc['suburb'] = error['actual_suburb']

                # Add migration metadata
                if 'migration_history' not in doc:
                    doc['migration_history'] = []

                doc['migration_history'].append({
                    'migrated_at': datetime.now(),
                    'from_collection': source_coll_name,
                    'to_collection': target_coll_name,
                    'reason': 'Automated audit fix - wrong collection',
                    'root_cause': error['root_cause'],
                    'script': 'database_audit.py'
                })

                # Insert into target collection
                target_coll.insert_one(doc)

                # Delete from source collection
                result = source_coll.delete_one({'_id': doc_id})

                if result.deleted_count == 1:
                    print(f"  ✓ Successfully moved\n")
                    fixed_count += 1
                else:
                    print(f"  ✗ Failed to delete from source\n")
                    failed_count += 1

            except Exception as e:
                print(f"  ✗ Error: {e}\n")
                failed_count += 1

        print(f"\n{'=' * 80}")
        print(f"FIX SUMMARY")
        print(f"{'=' * 80}")
        print(f"Successfully fixed: {fixed_count}")
        print(f"Failed: {failed_count}")
        print(f"{'=' * 80}\n")

        return fixed_count

    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Audit Gold Coast property database for misplaced properties',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 database_audit.py                          # Audit all collections
  python3 database_audit.py --verbose                # Show detailed progress
  python3 database_audit.py --collection varsity_lakes  # Audit specific collection
  python3 database_audit.py --fix                    # Audit and auto-fix errors
  python3 database_audit.py --fix --dry-run          # Show what would be fixed
  python3 database_audit.py --export audit_log.txt   # Export to log file
        """
    )

    parser.add_argument('--collection', type=str, help='Audit specific collection only')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed progress')
    parser.add_argument('--fix', action='store_true', help='Automatically fix errors')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (show fixes without applying)')
    parser.add_argument('--export', type=str, metavar='FILE', help='Export detailed errors to log file')
    parser.add_argument('--limit', type=int, default=50, help='Limit detailed errors shown (default: 50)')
    parser.add_argument('--no-fail', action='store_true', help='Exit with 0 even when errors found (for orchestrator integration)')

    args = parser.parse_args()

    # Create auditor
    auditor = DatabaseAuditor()

    # Connect to database
    if not auditor.connect():
        sys.exit(1)

    try:
        # Run audit
        errors = auditor.audit_all_collections(
            specific_collection=args.collection,
            verbose=args.verbose
        )

        # Print summary
        auditor.print_summary()

        # Print detailed errors
        if not args.verbose:  # Don't duplicate if already shown in verbose mode
            auditor.print_detailed_errors(limit=args.limit)

        # Export to log file if requested
        if args.export:
            auditor.export_errors_to_log(args.export)

        # Fix errors if requested
        if args.fix:
            auditor.fix_errors(dry_run=args.dry_run)

        # Exit code based on errors found
        # Use --no-fail flag to exit 0 even when errors found (for orchestrator integration)
        exit_code = 0 if args.no_fail else (1 if errors else 0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Audit interrupted by user")
        exit_code = 130
    except Exception as e:
        print(f"\n❌ Audit failed: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        auditor.close()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
