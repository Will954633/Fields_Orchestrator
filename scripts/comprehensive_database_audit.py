#!/usr/bin/env python3
"""
Comprehensive Database Audit for Gold_Coast_Currently_For_Sale
Detects Issues #2, #3, and #4 from DATABASE_CORRUPTION_REPORT.md

Date: 2026-02-17
Purpose: Scan database for:
  - Issue #2: Listing pages scraped instead of individual properties
  - Issue #3: Address format inconsistencies (slashes/dashes converted to spaces)
  - Issue #4: Photo/floor plan mismatches (already resolved by Issue #1 fix)
"""

import os
import sys
import json
import re
from datetime import datetime
from pymongo import MongoClient
from typing import Dict, List, Optional

# MongoDB connection
MONGODB_URI = os.environ.get('COSMOS_CONNECTION_STRING') or os.environ.get('MONGODB_URI')
if not MONGODB_URI:
    print("ERROR: COSMOS_CONNECTION_STRING or MONGODB_URI environment variable not set")
    sys.exit(1)

DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

# Audit results
audit_results = {
    'issue_2_listing_pages': [],
    'issue_3_format_inconsistencies': [],
    'issue_4_wrong_suburb_photos': [],  # Should be zero after Issue #1 fix
    'summary': {}
}


def normalize_address(address: str) -> str:
    """Normalize address for comparison"""
    if not address:
        return ''
    # Remove extra spaces, convert to lowercase
    normalized = ' '.join(address.lower().split())
    # Remove punctuation for comparison
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    return ' '.join(normalized.split())


def check_listing_page(doc: Dict) -> Optional[Dict]:
    """
    Issue #2: Check if this is a listing page instead of individual property

    Indicators:
    - og_title contains "Real Estate Properties for Sale"
    - og_title contains "Properties for Sale in"
    - address field contains URL (https://)
    - street_address and address are completely different
    """
    og_title = doc.get('og_title', '')
    address = doc.get('address', '')
    street_address = doc.get('street_address', '')

    issues = []

    # Check og_title for listing page keywords
    if og_title:
        og_title_lower = og_title.lower()
        listing_keywords = [
            'real estate properties for sale',
            'properties for sale in',
            'real estate for sale',
            'property for sale in'
        ]
        for keyword in listing_keywords:
            if keyword in og_title_lower:
                issues.append(f"og_title contains '{keyword}'")

    # Check if address contains URL
    if address and ('http://' in address.lower() or 'https://' in address.lower()):
        issues.append("address field contains URL")

    # Check if address and street_address are completely different
    if address and street_address:
        norm_address = normalize_address(address)
        norm_street = normalize_address(street_address)

        # Check if street_address is contained in address field
        if norm_street not in norm_address and norm_address not in norm_street:
            # They don't match at all
            if len(norm_street) > 5:  # Avoid false positives on very short addresses
                issues.append(f"address '{address[:50]}' doesn't match street_address '{street_address[:50]}'")

    if issues:
        return {
            '_id': str(doc['_id']),
            'collection': doc.get('collection_name', 'unknown'),
            'address': address[:100],
            'street_address': street_address[:100],
            'og_title': og_title[:150],
            'listing_url': doc.get('listing_url', ''),
            'issues': issues,
            'severity': 'CRITICAL'
        }

    return None


def check_address_format(doc: Dict) -> Optional[Dict]:
    """
    Issue #3: Check for address format inconsistencies

    Indicators:
    - address has spaces where og_title has slashes/dashes
    - Example: address "205 107 109" vs og_title "205/107 - 109"
    """
    og_title = doc.get('og_title', '')
    address = doc.get('address', '')

    if not og_title or not address:
        return None

    # Extract address portion from og_title: "Address, Suburb QLD PostCode | Domain"
    og_address_match = re.search(r'^([^|]+?)\s*\|\s*Domain', og_title)
    if not og_address_match:
        return None

    og_address = og_address_match.group(1).strip()

    # Check if og_address contains slashes or dashes
    if '/' in og_address or ' - ' in og_address:
        # Check if address field has spaces instead
        # Convert og_address slashes/dashes to spaces for comparison
        og_normalized = og_address.replace('/', ' ').replace(' - ', ' ')
        og_normalized = ' '.join(og_normalized.split())  # Normalize spaces

        address_normalized = ' '.join(address.split())

        # If they match after this conversion, it means the scraper removed slashes/dashes
        if og_normalized.lower() == address_normalized.lower():
            return {
                '_id': str(doc['_id']),
                'collection': doc.get('collection_name', 'unknown'),
                'address_in_db': address,
                'address_in_og_title': og_address,
                'issue': 'Slashes/dashes converted to spaces',
                'severity': 'MEDIUM'
            }

    return None


def check_suburb_mismatch(doc: Dict) -> Optional[Dict]:
    """
    Issue #4 (verification): Check if suburb in address matches collection

    This should be ZERO if Issue #1 fix is working correctly.
    If we find any, it means:
    - Either new properties scraped before deployment
    - Or the fix isn't working as expected
    """
    og_title = doc.get('og_title', '')
    collection_name = doc.get('collection_name', '')
    doc_suburb = doc.get('suburb', '')

    if not og_title or not collection_name:
        return None

    # Extract suburb from og_title: "Address, Suburb QLD PostCode | Domain"
    og_suburb_match = re.search(r',\s*([A-Za-z\s]+)\s+(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s+\d{4}', og_title)
    if not og_suburb_match:
        return None

    og_suburb = og_suburb_match.group(1).strip()
    og_suburb_normalized = og_suburb.lower().replace(' ', '_')
    collection_normalized = collection_name.lower().replace(' ', '_')

    # Compare with collection name
    if og_suburb_normalized != collection_normalized:
        return {
            '_id': str(doc['_id']),
            'collection': collection_name,
            'suburb_in_doc': doc_suburb,
            'suburb_in_og_title': og_suburb,
            'address': doc.get('address', '')[:100],
            'og_title': og_title[:150],
            'issue': f"Property from {og_suburb} stored in {collection_name} collection",
            'severity': 'CRITICAL',
            'note': 'This should be ZERO if Issue #1 fix is deployed correctly'
        }

    return None


def audit_collection(db, collection_name: str, limit: Optional[int] = None):
    """Audit a single collection"""
    print(f"\n📁 Auditing collection: {collection_name}")

    collection = db[collection_name]
    query = {}

    # Get total count
    total_count = collection.count_documents(query)
    print(f"  Total properties: {total_count}")

    # Set limit if specified
    cursor = collection.find(query)
    if limit:
        cursor = cursor.limit(limit)
        print(f"  Scanning first {limit} properties...")
    else:
        print(f"  Scanning all properties...")

    count = 0
    for doc in cursor:
        count += 1
        if count % 100 == 0:
            print(f"  Progress: {count}/{total_count if not limit else limit}", end='\r')

        # Add collection name to doc for reporting
        doc['collection_name'] = collection_name

        # Check Issue #2: Listing pages
        issue_2 = check_listing_page(doc)
        if issue_2:
            audit_results['issue_2_listing_pages'].append(issue_2)

        # Check Issue #3: Format inconsistencies
        issue_3 = check_address_format(doc)
        if issue_3:
            audit_results['issue_3_format_inconsistencies'].append(issue_3)

        # Check Issue #4: Suburb mismatches (should be zero)
        issue_4 = check_suburb_mismatch(doc)
        if issue_4:
            audit_results['issue_4_wrong_suburb_photos'].append(issue_4)

    print(f"  ✓ Completed: {count} properties scanned")


def main():
    print("=" * 80)
    print("COMPREHENSIVE DATABASE AUDIT")
    print("Database:", DATABASE_NAME)
    print("Date:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 80)

    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Audit Gold Coast property database')
    parser.add_argument('--limit', type=int, help='Limit number of properties per collection')
    parser.add_argument('--export', type=str, help='Export results to JSON file')
    args = parser.parse_args()

    # Connect to MongoDB
    print("\n🔌 Connecting to MongoDB...")
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    # Get all collections
    collections = db.list_collection_names()
    print(f"✓ Found {len(collections)} collections")

    # Audit each collection
    for collection_name in sorted(collections):
        audit_collection(db, collection_name, limit=args.limit)

    # Generate summary
    audit_results['summary'] = {
        'total_collections': len(collections),
        'issue_2_count': len(audit_results['issue_2_listing_pages']),
        'issue_3_count': len(audit_results['issue_3_format_inconsistencies']),
        'issue_4_count': len(audit_results['issue_4_wrong_suburb_photos']),
        'audit_date': datetime.now().isoformat(),
        'limit_per_collection': args.limit
    }

    # Print summary
    print("\n" + "=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)
    print(f"\n📊 Issue #2 (Listing Pages): {audit_results['summary']['issue_2_count']} found")
    print(f"   Severity: CRITICAL - These are not individual properties")

    print(f"\n📊 Issue #3 (Format Inconsistencies): {audit_results['summary']['issue_3_count']} found")
    print(f"   Severity: MEDIUM - Address format differs from og_title")

    print(f"\n📊 Issue #4 (Wrong Suburb Photos): {audit_results['summary']['issue_4_count']} found")
    print(f"   Severity: CRITICAL - Should be ZERO after Issue #1 fix")
    if audit_results['summary']['issue_4_count'] > 0:
        print(f"   ⚠️  WARNING: Found {audit_results['summary']['issue_4_count']} mismatched properties!")
        print(f"   This indicates Issue #1 fix may not be working or new data was scraped before deployment")

    # Export results if requested
    if args.export:
        output_file = args.export
        print(f"\n💾 Exporting results to: {output_file}")
        with open(output_file, 'w') as f:
            json.dump(audit_results, f, indent=2)
        print(f"✓ Results exported successfully")

    # Show examples of each issue type
    if audit_results['issue_2_listing_pages']:
        print("\n" + "=" * 80)
        print("ISSUE #2 EXAMPLES (Listing Pages)")
        print("=" * 80)
        for i, issue in enumerate(audit_results['issue_2_listing_pages'][:3], 1):
            print(f"\nExample {i}:")
            print(f"  Collection: {issue['collection']}")
            print(f"  Address: {issue['address']}")
            print(f"  og_title: {issue['og_title']}")
            print(f"  Issues: {', '.join(issue['issues'])}")

    if audit_results['issue_3_format_inconsistencies']:
        print("\n" + "=" * 80)
        print("ISSUE #3 EXAMPLES (Format Inconsistencies)")
        print("=" * 80)
        for i, issue in enumerate(audit_results['issue_3_format_inconsistencies'][:3], 1):
            print(f"\nExample {i}:")
            print(f"  Collection: {issue['collection']}")
            print(f"  DB Address: {issue['address_in_db']}")
            print(f"  og_title Address: {issue['address_in_og_title']}")

    if audit_results['issue_4_wrong_suburb_photos']:
        print("\n" + "=" * 80)
        print("⚠️  ISSUE #4 EXAMPLES (Wrong Suburb - SHOULD BE ZERO!)")
        print("=" * 80)
        for i, issue in enumerate(audit_results['issue_4_wrong_suburb_photos'][:5], 1):
            print(f"\nExample {i}:")
            print(f"  Collection: {issue['collection']}")
            print(f"  Suburb in og_title: {issue['suburb_in_og_title']}")
            print(f"  Address: {issue['address']}")

    print("\n" + "=" * 80)
    print("✓ Audit complete")
    print("=" * 80)


if __name__ == '__main__':
    main()
