#!/usr/bin/env python3
"""
Move Misplaced Property - One-time Fix Script
Created: 2026-02-17

Moves the property at "48 Peach Drive, Robina, QLD 4226" from the incorrect
"varsity_lakes" collection to the correct "robina" collection.

This script can be run manually to fix the specific known issue.
"""

import os
import sys
from pymongo import MongoClient
from datetime import datetime

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

def move_property():
    """Move the misplaced Robina property from varsity_lakes to robina collection"""
    try:
        # Connect to MongoDB
        client = MongoClient(MONGODB_URI)
        db = client[DATABASE_NAME]

        # Collections
        varsity_lakes_coll = db['varsity_lakes']
        robina_coll = db['robina']

        print("=" * 80)
        print("MOVE MISPLACED PROPERTY SCRIPT")
        print("=" * 80)
        print(f"Database: {DATABASE_NAME}")
        print(f"Source Collection: varsity_lakes")
        print(f"Target Collection: robina")
        print(f"Property: 48 Peach Drive, Robina, QLD 4226")
        print("=" * 80)

        # Find the misplaced document
        query = {"address": "48 Peach Drive, Robina, QLD 4226"}
        misplaced_doc = varsity_lakes_coll.find_one(query)

        if not misplaced_doc:
            print("❌ ERROR: Property not found in varsity_lakes collection")
            print("   The property may have already been moved or doesn't exist.")
            return False

        print("\n✓ Found misplaced property in varsity_lakes collection:")
        print(f"  - Address: {misplaced_doc.get('address')}")
        print(f"  - Suburb (current): {misplaced_doc.get('suburb')}")
        print(f"  - Listing URL: {misplaced_doc.get('listing_url')}")
        print(f"  - First Seen: {misplaced_doc.get('first_seen')}")
        print(f"  - Document ID: {misplaced_doc.get('_id')}")

        # Check if property already exists in robina collection
        existing_in_robina = robina_coll.find_one({"listing_url": misplaced_doc.get('listing_url')})

        if existing_in_robina:
            print("\n⚠️  WARNING: Property already exists in robina collection!")
            print("   This might indicate the property was already moved or exists as duplicate.")
            print(f"  - Robina Document ID: {existing_in_robina.get('_id')}")
            print(f"  - Robina First Seen: {existing_in_robina.get('first_seen')}")

            # Delete from varsity_lakes only (keep the one in robina)
            result = varsity_lakes_coll.delete_one({"_id": misplaced_doc['_id']})
            if result.deleted_count == 1:
                print("\n✅ Removed duplicate from varsity_lakes collection")
                print("   The property already exists in the correct robina collection.")
                return True
            else:
                print("\n❌ Failed to remove duplicate from varsity_lakes")
                return False

        # Update the suburb field to correct value
        misplaced_doc['suburb'] = 'Robina'

        # Add migration metadata
        if 'migration_history' not in misplaced_doc:
            misplaced_doc['migration_history'] = []

        misplaced_doc['migration_history'].append({
            'migrated_at': datetime.now(),
            'from_collection': 'varsity_lakes',
            'to_collection': 'robina',
            'reason': 'Cross-suburb misclassification bug fix',
            'bug_report': 'Property scraped during Varsity Lakes search but actual address is Robina',
            'script': 'move_misplaced_property.py'
        })

        # Insert into correct collection (robina)
        print("\n📝 Inserting property into robina collection...")
        robina_coll.insert_one(misplaced_doc)
        print("✅ Property inserted into robina collection")

        # Delete from incorrect collection (varsity_lakes)
        print("\n🗑️  Removing property from varsity_lakes collection...")
        result = varsity_lakes_coll.delete_one({"_id": misplaced_doc['_id']})

        if result.deleted_count == 1:
            print("✅ Property removed from varsity_lakes collection")
        else:
            print("❌ WARNING: Failed to remove from varsity_lakes!")
            print("   The property now exists in BOTH collections!")
            return False

        # Verify the move
        print("\n🔍 Verifying the move...")
        verify_robina = robina_coll.find_one({"address": "48 Peach Drive, Robina, QLD 4226"})
        verify_varsity = varsity_lakes_coll.find_one({"address": "48 Peach Drive, Robina, QLD 4226"})

        if verify_robina and not verify_varsity:
            print("✅ VERIFICATION PASSED:")
            print(f"   - Property EXISTS in robina collection (ID: {verify_robina['_id']})")
            print("   - Property REMOVED from varsity_lakes collection")
            print(f"   - Suburb field: {verify_robina.get('suburb')}")
            print("\n" + "=" * 80)
            print("✅ SUCCESS: Property successfully moved to correct collection!")
            print("=" * 80)
            return True
        else:
            print("❌ VERIFICATION FAILED:")
            if not verify_robina:
                print("   - Property NOT FOUND in robina collection!")
            if verify_varsity:
                print("   - Property STILL EXISTS in varsity_lakes collection!")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()

if __name__ == '__main__':
    success = move_property()
    sys.exit(0 if success else 1)
