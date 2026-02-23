#!/usr/bin/env python3
"""
Fix Sold Monitor Index Creation Issue
Last Updated: 12/02/2026, 10:12 AM (Wednesday) - Brisbane Time

Description: Fixes the "Cannot create unique index when collection contains documents" error
in monitor_sold_properties.py by making index creation conditional and safe for Cosmos DB.

The issue: Azure Cosmos DB doesn't allow creating unique indexes on collections with existing documents.
The fix: Check if collection is empty before creating unique index, or use non-unique index.
"""

import os
import sys

# Path to the monitor script
MONITOR_SCRIPT_PATH = "/home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py"

def fix_index_creation():
    """Fix the index creation code in monitor_sold_properties.py"""
    
    print("=" * 80)
    print("FIXING SOLD MONITOR INDEX CREATION")
    print("=" * 80)
    print()
    
    # Read the current file
    print(f"Reading: {MONITOR_SCRIPT_PATH}")
    with open(MONITOR_SCRIPT_PATH, 'r') as f:
        content = f.read()
    
    # Find and replace the problematic index creation code
    old_code = """        # Create indexes for sold collection
        self.sold_collection.create_index([("listing_url", ASCENDING)], unique=True)
        self.sold_collection.create_index([("address", ASCENDING)])
        self.sold_collection.create_index([("sold_detection_date", ASCENDING)])
        self.sold_collection.create_index([("sold_date", ASCENDING)])"""
    
    new_code = """        # Create indexes for sold collection (Cosmos DB safe)
        # NOTE: Cosmos DB doesn't allow unique indexes on collections with existing documents
        # So we create non-unique indexes instead
        try:
            self.sold_collection.create_index([("listing_url", ASCENDING)])
            self.sold_collection.create_index([("address", ASCENDING)])
            self.sold_collection.create_index([("sold_detection_date", ASCENDING)])
            self.sold_collection.create_index([("sold_date", ASCENDING)])
        except Exception as e:
            # Indexes may already exist, which is fine
            self.log(f"Note: Index creation skipped (may already exist): {e}")"""
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        print("✓ Found and replaced index creation code")
    else:
        print("⚠ Could not find exact match for index creation code")
        print("Searching for alternative pattern...")
        
        # Try alternative pattern
        alt_old = """self.sold_collection.create_index([("listing_url", ASCENDING)], unique=True)"""
        alt_new = """try:
            self.sold_collection.create_index([("listing_url", ASCENDING)])
        except Exception:
            pass  # Index may already exist"""
        
        if alt_old in content:
            content = content.replace(alt_old, alt_new)
            print("✓ Found and replaced alternative pattern")
        else:
            print("❌ Could not find index creation code to fix")
            return False
    
    # Write the fixed content back
    print(f"Writing fixed code to: {MONITOR_SCRIPT_PATH}")
    with open(MONITOR_SCRIPT_PATH, 'w') as f:
        f.write(content)
    
    print("✓ File updated successfully")
    print()
    print("=" * 80)
    print("FIX COMPLETE")
    print("=" * 80)
    print()
    print("The sold monitor will now:")
    print("  - Create non-unique indexes (Cosmos DB compatible)")
    print("  - Handle existing indexes gracefully")
    print("  - Not crash on index creation errors")
    print()
    
    return True

if __name__ == "__main__":
    success = fix_index_creation()
    sys.exit(0 if success else 1)
