#!/usr/bin/env python3
"""
Fix Malformed Addresses in Database
Created: 2026-02-17

Fixes addresses with misplaced commas in multi-word suburb names.

ISSUE:
- Current: "5306 5 Harbour Side Court Biggera, Waters, QLD 4216"
- Should be: "5306 5 Harbour Side Court, Biggera Waters, QLD 4216"

The comma appears BEFORE the second word of the suburb instead of before the suburb.

USAGE:
  # Dry run - show fixes without applying (SAFE)
  python3 fix_malformed_addresses.py --dry-run --limit 5

  # Fix specific collection
  python3 fix_malformed_addresses.py --collection biggera_waters --dry-run

  # Apply fixes to all collections
  python3 fix_malformed_addresses.py

  # Apply fixes with limit
  python3 fix_malformed_addresses.py --limit 100
"""

import os
import sys
import argparse
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pymongo import MongoClient
from bson import ObjectId

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

# Known multi-word suburbs on Gold Coast
# These are suburbs where the comma incorrectly appears in the middle
MULTI_WORD_SUBURBS = [
    ('Biggera', 'Waters', 'Biggera Waters'),
    ('Burleigh', 'Waters', 'Burleigh Waters'),
    ('Burleigh', 'Heads', 'Burleigh Heads'),
    ('Reedy', 'Creek', 'Reedy Creek'),
    ('Varsity', 'Lakes', 'Varsity Lakes'),
    ('Hope', 'Island', 'Hope Island'),
    ('Main', 'Beach', 'Main Beach'),
    ('Palm', 'Beach', 'Palm Beach'),
    ('Mermaid', 'Beach', 'Mermaid Beach'),
    ('Paradise', 'Point', 'Paradise Point'),
    ('Runaway', 'Bay', 'Runaway Bay'),
    ('Pacific', 'Pines', 'Pacific Pines'),
    ('Clear Island', 'Waters', 'Clear Island Waters'),
    ('Currumbin', 'Waters', 'Currumbin Waters'),
    ('Currumbin', 'Valley', 'Currumbin Valley'),
    ('Tallebudgera', 'Valley', 'Tallebudgera Valley'),
    ('Upper', 'Coomera', 'Upper Coomera'),
    ('Broadbeach', 'Waters', 'Broadbeach Waters'),
    ('Highland', 'Park', 'Highland Park'),
    ('Mermaid', 'Waters', 'Mermaid Waters'),
]


class AddressFixer:
    """Fixes malformed addresses in the database"""

    def __init__(self, mongodb_uri: str = MONGODB_URI, database_name: str = DATABASE_NAME):
        """Initialize fixer"""
        self.mongodb_uri = mongodb_uri
        self.database_name = database_name
        self.client = None
        self.db = None
        self.stats = {
            'total_scanned': 0,
            'malformed_found': 0,
            'fixed': 0,
            'failed': 0,
            'collections_processed': 0,
        }

    def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.database_name]
            self.client.admin.command('ping')
            return True
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            return False

    def detect_malformed_address(self, address: str) -> Optional[Tuple[str, str, str]]:
        """
        Detect if address has malformed suburb name.

        Args:
            address: Original address string

        Returns:
            Tuple of (part1, part2, correct_suburb) if malformed, None otherwise
        """
        if not address:
            return None

        # Check each known multi-word suburb
        for part1, part2, correct_suburb in MULTI_WORD_SUBURBS:
            # Pattern: "[anything] Part1, Part2, STATE postcode"
            # Example: "5 Court Biggera, Waters, QLD 4216"
            pattern = rf'(.+)\s+{re.escape(part1)},\s*{re.escape(part2)},\s*(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s+(\d{{4}})'

            match = re.search(pattern, address, re.IGNORECASE)
            if match:
                return (part1, part2, correct_suburb)

        return None

    def fix_address(self, address: str, part1: str, part2: str, correct_suburb: str) -> str:
        """
        Fix a malformed address.

        Args:
            address: Original malformed address
            part1: First part of suburb (e.g., "Biggera")
            part2: Second part of suburb (e.g., "Waters")
            correct_suburb: Correct full suburb name (e.g., "Biggera Waters")

        Returns:
            Fixed address string
        """
        # Pattern: "[street] Part1, Part2, STATE postcode"
        # Replace with: "[street], Part1 Part2, STATE postcode"
        pattern = rf'(.+)\s+{re.escape(part1)},\s*{re.escape(part2)},\s*(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s+(\d{{4}})'

        def replacer(match):
            street = match.group(1).strip()
            state = match.group(2)
            postcode = match.group(3)
            return f"{street}, {correct_suburb}, {state} {postcode}"

        fixed = re.sub(pattern, replacer, address, flags=re.IGNORECASE)
        return fixed

    def scan_and_fix_collection(self, collection_name: str, dry_run: bool = True, limit: Optional[int] = None) -> Dict:
        """
        Scan a collection for malformed addresses and fix them.

        Args:
            collection_name: Name of collection to scan
            dry_run: If True, don't actually update database
            limit: Maximum number of documents to fix

        Returns:
            Dict with statistics
        """
        coll = self.db[collection_name]
        results = {
            'collection': collection_name,
            'scanned': 0,
            'malformed': 0,
            'fixed': 0,
            'failed': 0,
            'examples': [],
        }

        # Get all documents (or up to limit)
        cursor = coll.find({})
        if limit:
            cursor = cursor.limit(limit * 10)  # Scan extra to find enough malformed ones

        for doc in cursor:
            results['scanned'] += 1
            self.stats['total_scanned'] += 1

            address = doc.get('address', '')
            if not address:
                continue

            # Check if malformed
            malformed_info = self.detect_malformed_address(address)
            if not malformed_info:
                continue

            results['malformed'] += 1
            self.stats['malformed_found'] += 1

            part1, part2, correct_suburb = malformed_info
            fixed_address = self.fix_address(address, part1, part2, correct_suburb)

            # Store example
            if len(results['examples']) < 10:  # Keep first 10 examples
                results['examples'].append({
                    'doc_id': str(doc['_id']),
                    'listing_url': doc.get('listing_url', 'N/A')[:80],
                    'before': address,
                    'after': fixed_address,
                    'suburb_field': doc.get('suburb', 'N/A'),
                })

            # Apply fix if not dry run
            if not dry_run:
                try:
                    update_result = coll.update_one(
                        {'_id': doc['_id']},
                        {
                            '$set': {
                                'address': fixed_address,
                                'address_fixed_at': datetime.now(),
                                'address_fix_script': 'fix_malformed_addresses.py',
                            }
                        }
                    )

                    if update_result.modified_count == 1:
                        results['fixed'] += 1
                        self.stats['fixed'] += 1
                    else:
                        results['failed'] += 1
                        self.stats['failed'] += 1
                except Exception as e:
                    results['failed'] += 1
                    self.stats['failed'] += 1
                    print(f"  ✗ Error updating {doc['_id']}: {e}")
            else:
                results['fixed'] += 1  # Count as "would fix" in dry run

            # Stop if we've processed enough
            if limit and results['malformed'] >= limit:
                break

        return results

    def fix_all_collections(self, specific_collection: Optional[str] = None,
                           dry_run: bool = True, limit: Optional[int] = None):
        """
        Fix malformed addresses across all (or specific) collections.

        Args:
            specific_collection: If provided, only fix this collection
            dry_run: If True, don't actually update database
            limit: Maximum number of documents to fix per collection
        """
        print(f"\n{'=' * 80}")
        print(f"{'DRY RUN - ' if dry_run else ''}FIX MALFORMED ADDRESSES")
        print(f"{'=' * 80}")
        print(f"Database: {self.database_name}")
        if dry_run:
            print(f"Mode: DRY RUN (no changes will be made)")
        if limit:
            print(f"Limit: {limit} properties per collection")
        print(f"{'=' * 80}\n")

        # Get collections to process
        if specific_collection:
            collections = [specific_collection]
        else:
            all_collections = self.db.list_collection_names()
            # Exclude system, backups, and catch-all collections
            collections = [c for c in all_collections
                          if not c.startswith('system.')
                          and '_backup_' not in c
                          and c != 'Gold_Coast_Recently_Sold']

        print(f"Collections to process: {len(collections)}\n")

        # Process each collection
        collection_results = []

        for i, coll_name in enumerate(sorted(collections), 1):
            print(f"[{i}/{len(collections)}] Processing {coll_name}...")

            results = self.scan_and_fix_collection(coll_name, dry_run=dry_run, limit=limit)
            collection_results.append(results)

            self.stats['collections_processed'] += 1

            if results['malformed'] > 0:
                print(f"  Found {results['malformed']} malformed addresses")
                if dry_run:
                    print(f"  Would fix {results['fixed']}")
                else:
                    print(f"  Fixed {results['fixed']}, Failed {results['failed']}")

                # Show examples
                if results['examples']:
                    print(f"\n  Examples from {coll_name}:")
                    for ex in results['examples'][:3]:  # Show first 3
                        print(f"\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                        print(f"  Suburb Field: {ex['suburb_field']}")
                        print(f"  BEFORE: {ex['before']}")
                        print(f"  AFTER:  {ex['after']}")
                        print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            else:
                print(f"  No malformed addresses found")

            print()

        # Summary
        print(f"\n{'=' * 80}")
        print(f"SUMMARY")
        print(f"{'=' * 80}")
        print(f"Collections processed: {self.stats['collections_processed']}")
        print(f"Documents scanned: {self.stats['total_scanned']:,}")
        print(f"Malformed addresses found: {self.stats['malformed_found']:,}")
        if dry_run:
            print(f"Would fix: {self.stats['fixed']:,}")
        else:
            print(f"Successfully fixed: {self.stats['fixed']:,}")
            print(f"Failed: {self.stats['failed']:,}")
        print(f"{'=' * 80}\n")

        if dry_run and self.stats['malformed_found'] > 0:
            print("To apply fixes, run without --dry-run flag:")
            print(f"  python3 scripts/fix_malformed_addresses.py")

    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Fix malformed addresses in Gold Coast property database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be fixed without making changes (SAFE)')
    parser.add_argument('--collection', type=str, metavar='NAME',
                        help='Fix specific collection only')
    parser.add_argument('--limit', type=int, metavar='N',
                        help='Limit fixes to first N properties per collection')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Skip confirmation prompt')

    args = parser.parse_args()

    # Confirm if not dry-run
    if not args.dry_run and not args.yes:
        print("\n⚠️  WARNING: This will modify addresses in your database!")
        print("Run with --dry-run first to preview changes.")
        print("\nContinue? (yes/no): ", end='')
        response = input().strip().lower()
        if response not in ['yes', 'y']:
            print("Operation cancelled.")
            sys.exit(0)

    # Create fixer
    fixer = AddressFixer()

    if not fixer.connect():
        sys.exit(1)

    try:
        # Fix addresses
        fixer.fix_all_collections(
            specific_collection=args.collection,
            dry_run=args.dry_run,
            limit=args.limit
        )

        exit_code = 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Operation interrupted by user")
        exit_code = 130
    except Exception as e:
        print(f"\n❌ Operation failed: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        fixer.close()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
