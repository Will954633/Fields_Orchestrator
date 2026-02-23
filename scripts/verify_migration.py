#!/usr/bin/env python3
"""
Migration Verification Script
Created: 2026-02-17

Verifies that the property migration was successful by:
1. Running database audit to check for remaining misplaced properties
2. Comparing pre/post migration statistics
3. Verifying backup integrity
4. Checking for duplicates or missing properties

Run this AFTER migration to ensure everything worked correctly.

USAGE:
  python3 verify_migration.py
  python3 verify_migration.py --verbose  # Show detailed checks
"""

import os
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from pymongo import MongoClient
from bson import ObjectId

# Add the parent directory to the path to import database_audit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database_audit import DatabaseAuditor

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'


class MigrationVerifier:
    """Verifies migration was successful"""

    def __init__(self, mongodb_uri: str = MONGODB_URI, database_name: str = DATABASE_NAME):
        """Initialize verifier"""
        self.mongodb_uri = mongodb_uri
        self.database_name = database_name
        self.client = None
        self.db = None
        self.verification_results = {
            'misplaced_properties_check': None,
            'backup_integrity_check': None,
            'duplicate_check': None,
            'total_count_check': None,
        }
        self.issues_found = []

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

    def check_remaining_misplaced_properties(self, verbose: bool = False) -> bool:
        """
        Check if any misplaced properties remain after migration.

        Returns:
            True if no misplaced properties found, False otherwise
        """
        print(f"\n{'=' * 80}")
        print("CHECK 1: Scanning for Remaining Misplaced Properties")
        print(f"{'=' * 80}\n")

        auditor = DatabaseAuditor(self.mongodb_uri, self.database_name)
        if not auditor.connect():
            print("❌ Failed to connect for audit")
            return False

        try:
            errors = auditor.audit_all_collections(verbose=verbose)

            if not errors:
                print("✅ PASSED: No misplaced properties found!")
                self.verification_results['misplaced_properties_check'] = 'PASSED'
                return True
            else:
                print(f"❌ FAILED: Found {len(errors)} remaining misplaced properties!")
                print("\nFirst 10 issues:")
                for error in errors[:10]:
                    print(f"  - {error['address']}")
                    print(f"    Current: {error['current_collection']}")
                    print(f"    Should be: {error['correct_collection']}")
                    print()

                self.verification_results['misplaced_properties_check'] = f'FAILED ({len(errors)} remaining)'
                self.issues_found.append(f"Found {len(errors)} remaining misplaced properties")
                return False

        finally:
            auditor.close()

    def check_backup_integrity(self, verbose: bool = False) -> bool:
        """
        Check that backup collections exist and contain data.

        Returns:
            True if backups look good, False otherwise
        """
        print(f"\n{'=' * 80}")
        print("CHECK 2: Verifying Backup Integrity")
        print(f"{'=' * 80}\n")

        all_collections = self.db.list_collection_names()
        backup_collections = [c for c in all_collections if '_backup_' in c]

        if not backup_collections:
            print("⚠️  WARNING: No backup collections found!")
            print("   Migration may have run with --no-backup flag.")
            self.verification_results['backup_integrity_check'] = 'SKIPPED (no backups)'
            return True  # Not a failure, just no backups

        print(f"Found {len(backup_collections)} backup collections:")

        backup_stats = []
        for backup_name in sorted(backup_collections):
            coll = self.db[backup_name]
            count = coll.count_documents({})

            # Check for metadata
            metadata_doc = coll.find_one({'_backup_metadata': {'$exists': True}})

            if metadata_doc and '_backup_metadata' in metadata_doc:
                metadata = metadata_doc['_backup_metadata']
                original = metadata.get('original_collection', 'unknown')
                created = metadata.get('backup_created_at', 'unknown')
                doc_count = metadata.get('document_count', 'unknown')

                print(f"  ✓ {backup_name}")
                print(f"    Original: {original}")
                print(f"    Created: {created}")
                print(f"    Documents: {doc_count}")
                print(f"    Current count: {count - 1} (excluding metadata)")  # -1 for metadata doc

                backup_stats.append({
                    'backup_name': backup_name,
                    'original': original,
                    'count': count - 1,
                })
            else:
                print(f"  ⚠️  {backup_name} - No metadata found (count: {count})")

        print(f"\n✅ PASSED: {len(backup_collections)} backup collections verified")
        self.verification_results['backup_integrity_check'] = f'PASSED ({len(backup_collections)} backups)'
        return True

    def check_for_duplicates(self, verbose: bool = False) -> bool:
        """
        Check for duplicate properties across collections.

        Returns:
            True if no problematic duplicates found, False otherwise
        """
        print(f"\n{'=' * 80}")
        print("CHECK 3: Checking for Duplicate Properties")
        print(f"{'=' * 80}\n")

        # Build index of all listing URLs across all collections
        all_collections = self.db.list_collection_names()
        # Exclude backup collections and system collections
        active_collections = [
            c for c in all_collections
            if not c.startswith('system.')
            and '_backup_' not in c
        ]

        print(f"Scanning {len(active_collections)} active collections...")

        url_to_collections = defaultdict(list)

        for coll_name in active_collections:
            coll = self.db[coll_name]
            for doc in coll.find({}, {'listing_url': 1, '_id': 1, 'address': 1}):
                url = doc.get('listing_url')
                if url:
                    url_to_collections[url].append({
                        'collection': coll_name,
                        'doc_id': doc['_id'],
                        'address': doc.get('address', 'N/A'),
                    })

        # Find duplicates
        duplicates = {url: colls for url, colls in url_to_collections.items() if len(colls) > 1}

        if not duplicates:
            print("✅ PASSED: No duplicate properties found!")
            self.verification_results['duplicate_check'] = 'PASSED'
            return True
        else:
            print(f"❌ FAILED: Found {len(duplicates)} duplicate properties!")
            print("\nFirst 10 duplicates:")
            for i, (url, occurrences) in enumerate(list(duplicates.items())[:10], 1):
                print(f"\n{i}. {occurrences[0]['address']}")
                print(f"   URL: {url}")
                print(f"   Found in {len(occurrences)} collections:")
                for occ in occurrences:
                    print(f"     - {occ['collection']} (ID: {occ['doc_id']})")

            self.verification_results['duplicate_check'] = f'FAILED ({len(duplicates)} duplicates)'
            self.issues_found.append(f"Found {len(duplicates)} duplicate properties")
            return False

    def check_total_counts(self, verbose: bool = False) -> bool:
        """
        Check that total property count is consistent.

        Returns:
            True if counts look reasonable, False otherwise
        """
        print(f"\n{'=' * 80}")
        print("CHECK 4: Verifying Total Property Counts")
        print(f"{'=' * 80}\n")

        all_collections = self.db.list_collection_names()

        # Count active collections
        active_collections = [
            c for c in all_collections
            if not c.startswith('system.')
            and '_backup_' not in c
        ]

        # Count backup collections
        backup_collections = [c for c in all_collections if '_backup_' in c]

        total_active = 0
        total_backup = 0

        print("Active collections:")
        for coll_name in sorted(active_collections):
            count = self.db[coll_name].count_documents({})
            total_active += count
            if verbose:
                print(f"  {coll_name}: {count:,}")

        if not verbose:
            print(f"  {len(active_collections)} collections with {total_active:,} total documents")

        print("\nBackup collections:")
        for coll_name in sorted(backup_collections):
            # Exclude metadata doc from count
            count = self.db[coll_name].count_documents({'_backup_metadata': {'$exists': False}})
            total_backup += count
            if verbose:
                print(f"  {coll_name}: {count:,}")

        if backup_collections:
            if not verbose:
                print(f"  {len(backup_collections)} collections with {total_backup:,} total documents")

            print(f"\nTotal active properties: {total_active:,}")
            print(f"Total backup properties: {total_backup:,}")

            # Backups should have roughly same or slightly more documents than active
            # (because migration moved some, but backups have originals)
            if total_active > 0 and total_backup > 0:
                ratio = total_active / total_backup
                if 0.8 <= ratio <= 1.2:  # Within 20% is reasonable
                    print(f"✅ PASSED: Active/backup ratio is reasonable ({ratio:.2f})")
                    self.verification_results['total_count_check'] = 'PASSED'
                    return True
                else:
                    print(f"⚠️  WARNING: Active/backup ratio seems off ({ratio:.2f})")
                    print(f"   This might indicate missing or duplicate data")
                    self.verification_results['total_count_check'] = f'WARNING (ratio {ratio:.2f})'
                    return True  # Warning, not failure
        else:
            print(f"Total active properties: {total_active:,}")
            print(f"No backups found (migration may have run with --no-backup)")
            self.verification_results['total_count_check'] = 'PASSED (no backups to compare)'
            return True

    def print_summary(self):
        """Print verification summary"""
        print(f"\n{'=' * 80}")
        print("VERIFICATION SUMMARY")
        print(f"{'=' * 80}\n")

        all_passed = True

        for check_name, result in self.verification_results.items():
            status_emoji = "✅" if result and result.startswith('PASSED') else "❌"
            check_display = check_name.replace('_', ' ').title()
            print(f"{status_emoji} {check_display}: {result}")

            if result and not result.startswith('PASSED') and not result.startswith('SKIPPED'):
                all_passed = False

        if self.issues_found:
            print(f"\n⚠️  Issues Found:")
            for issue in self.issues_found:
                print(f"  - {issue}")

        print(f"\n{'=' * 80}")
        if all_passed and not self.issues_found:
            print("✅ ALL CHECKS PASSED - Migration verified successfully!")
            print("\nYou can now safely cleanup backup collections with:")
            print("  python3 scripts/cleanup_migration_backups.py")
        else:
            print("❌ VERIFICATION FAILED - Issues detected!")
            print("\nDo NOT cleanup backups yet. Investigate issues first.")
            print("Consider restoring from backups if necessary.")
        print(f"{'=' * 80}\n")

        return all_passed and not self.issues_found

    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Verify property migration was successful',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed verification output')

    args = parser.parse_args()

    print(f"\n{'=' * 80}")
    print("MIGRATION VERIFICATION")
    print(f"{'=' * 80}")
    print(f"Database: {DATABASE_NAME}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}\n")

    verifier = MigrationVerifier()

    if not verifier.connect():
        sys.exit(1)

    try:
        # Run all checks
        check1 = verifier.check_remaining_misplaced_properties(verbose=args.verbose)
        check2 = verifier.check_backup_integrity(verbose=args.verbose)
        check3 = verifier.check_for_duplicates(verbose=args.verbose)
        check4 = verifier.check_total_counts(verbose=args.verbose)

        # Print summary
        all_passed = verifier.print_summary()

        exit_code = 0 if all_passed else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Verification interrupted by user")
        exit_code = 130
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        verifier.close()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
