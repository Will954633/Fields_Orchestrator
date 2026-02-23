#!/usr/bin/env python3
"""
Migrate Old Properties with Malformed Data

This script fixes properties scraped before 2026-02-17 that have:
1. Malformed addresses (e.g., "Biggera, Waters" instead of "Biggera Waters")
2. Wrong suburb assignments (properties in wrong collections)

Date: 2026-02-17
Purpose: Clean up 1,072 properties identified by database_audit.py
"""

import os
import sys
import re
import time
from datetime import datetime
from typing import Dict, List, Optional
from pymongo import MongoClient
from pymongo.errors import WriteError
from bson import ObjectId

# MongoDB connection
MONGODB_URI = os.environ.get('COSMOS_CONNECTION_STRING') or os.environ.get('MONGODB_URI')
if not MONGODB_URI:
    print("ERROR: COSMOS_CONNECTION_STRING or MONGODB_URI environment variable not set")
    sys.exit(1)

DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

# Multi-word suburb patterns to fix
SUBURB_PATTERNS = {
    'Biggera Waters': ['Biggera', 'Waters'],
    'Burleigh Waters': ['Burleigh', 'Waters'],
    'Varsity Lakes': ['Varsity', 'Lakes'],
    'Reedy Creek': ['Reedy', 'Creek'],
    'Broadbeach Waters': ['Broadbeach', 'Waters'],
    'Clear Island Waters': ['Clear Island', 'Waters'],
    'Currumbin Waters': ['Currumbin', 'Waters'],
    'Paradise Waters': ['Paradise', 'Waters'],
    'Runaway Bay': ['Runaway', 'Bay'],
    'Surfers Paradise': ['Surfers', 'Paradise'],
    'Tallebudgera Valley': ['Tallebudgera', 'Valley'],
    'Upper Coomera': ['Upper', 'Coomera'],
    'Palm Beach': ['Palm', 'Beach'],
    'Mermaid Beach': ['Mermaid', 'Beach'],
    'Miami Keys': ['Miami', 'Keys'],
    'Sanctuary Cove': ['Sanctuary', 'Cove'],
    'Hope Island': ['Hope', 'Island'],
    'Mermaid Waters': ['Mermaid', 'Waters'],
    'Bundall': ['Bundall'],
    'Southport': ['Southport'],
}


def extract_suburb_from_address(address: str) -> Optional[str]:
    """Extract suburb from address string"""
    if not address:
        return None

    # Pattern: "Address, Suburb, QLD Postcode"
    match = re.search(r',\s*([^,]+),\s*(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s+\d{4}', address)
    if match:
        return match.group(1).strip()

    return None


def fix_malformed_address(address: str) -> str:
    """Fix malformed multi-word suburb addresses"""
    if not address:
        return address

    for correct_suburb, parts in SUBURB_PATTERNS.items():
        if len(parts) == 1:
            continue  # Skip single-word suburbs

        part1, part2 = parts[0], parts[1] if len(parts) > 1 else ''

        # Pattern: "123 Street Part1, Part2, QLD 4216"
        pattern = rf'(.+)\s+{re.escape(part1)},\s*{re.escape(part2)},\s*(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s+(\d{{4}})'

        def replacer(match):
            street = match.group(1).strip()
            state = match.group(2)
            postcode = match.group(3)
            return f"{street}, {correct_suburb}, {state} {postcode}"

        fixed = re.sub(pattern, replacer, address, flags=re.IGNORECASE)
        if fixed != address:
            return fixed

    return address


def migrate_properties(dry_run: bool = True, cutoff_date: str = '2026-02-17'):
    """Migrate properties scraped before cutoff_date"""
    print("=" * 80)
    print("PROPERTY MIGRATION SCRIPT")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")
    print(f"Cutoff Date: {cutoff_date}")
    print()

    # Connect to MongoDB
    print("🔌 Connecting to MongoDB...")
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    # Get all collections
    collections = db.list_collection_names()
    print(f"✓ Found {len(collections)} collections")
    print()

    total_properties = 0
    fixed_addresses = 0
    moved_properties = 0

    for collection_name in sorted(collections):
        collection = db[collection_name]

        # Query properties before cutoff date
        query = {
            'first_seen': {'$lt': datetime.fromisoformat(cutoff_date)}
        }

        properties = list(collection.find(query))
        if not properties:
            continue

        print(f"📁 {collection_name}: {len(properties)} properties")
        total_properties += len(properties)

        for prop in properties:
            address = prop.get('address', '')
            if not address:
                continue

            # Fix malformed address
            fixed_address = fix_malformed_address(address)
            if fixed_address != address:
                print(f"  🔧 Fix address: {address[:60]} → {fixed_address[:60]}")
                if not dry_run:
                    # Retry logic for Cosmos DB rate limiting
                    max_retries = 5
                    for retry in range(max_retries):
                        try:
                            collection.update_one(
                                {'_id': prop['_id']},
                                {'$set': {'address': fixed_address}}
                            )
                            break  # Success
                        except WriteError as e:
                            if '429' in str(e) or 'TooManyRequests' in str(e):
                                if retry < max_retries - 1:
                                    wait_time = 0.5 * (2 ** retry)  # Exponential backoff
                                    time.sleep(wait_time)
                                else:
                                    print(f"    ⚠️  Failed after {max_retries} retries (rate limit)")
                                    raise
                            else:
                                raise
                    time.sleep(0.1)  # Base throttle between operations
                fixed_addresses += 1

            # Extract suburb from fixed address
            actual_suburb = extract_suburb_from_address(fixed_address)
            if not actual_suburb:
                continue

            # Check if in wrong collection
            actual_collection = actual_suburb.lower().replace(' ', '_')
            if actual_collection != collection_name and actual_collection in collections:
                print(f"  🔀 Move: {collection_name} → {actual_collection} ({address[:60]})")
                if not dry_run:
                    # Retry logic for Cosmos DB rate limiting
                    max_retries = 5
                    for retry in range(max_retries):
                        try:
                            # Insert into correct collection
                            target_collection = db[actual_collection]
                            prop['suburb'] = actual_suburb
                            target_collection.insert_one(prop)

                            # Remove from wrong collection
                            collection.delete_one({'_id': prop['_id']})
                            break  # Success
                        except WriteError as e:
                            if '429' in str(e) or 'TooManyRequests' in str(e):
                                if retry < max_retries - 1:
                                    wait_time = 0.5 * (2 ** retry)  # Exponential backoff
                                    time.sleep(wait_time)
                                else:
                                    print(f"    ⚠️  Failed after {max_retries} retries (rate limit)")
                                    raise
                            else:
                                raise
                    time.sleep(0.1)  # Base throttle between operations

                moved_properties += 1

    print()
    print("=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)
    print(f"Total Properties Scanned: {total_properties}")
    print(f"Addresses Fixed: {fixed_addresses}")
    print(f"Properties Moved: {moved_properties}")
    print()

    if dry_run:
        print("⚠️  DRY RUN MODE - No changes were made")
        print("Run with --live to apply changes")
    else:
        print("✅ Migration complete!")

    client.close()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Migrate old properties with malformed data',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--live', action='store_true', help='Apply changes (default is dry run)')
    parser.add_argument('--cutoff-date', type=str, default='2026-02-17',
                        help='Only migrate properties before this date (default: 2026-02-17)')

    args = parser.parse_args()

    dry_run = not args.live

    if not dry_run:
        print("\n⚠️  WARNING: This will modify the database!")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled.")
            sys.exit(0)
        print()

    migrate_properties(dry_run=dry_run, cutoff_date=args.cutoff_date)


if __name__ == '__main__':
    main()
