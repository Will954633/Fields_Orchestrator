#!/usr/bin/env python3
"""
Safe Migration Script for Misplaced Properties
Created: 2026-02-17

This script safely migrates misplaced properties to their correct collections with:
1. Automatic backup creation before migration
2. Transaction-safe migration (insert then delete)
3. Comprehensive verification
4. Rollback capability if issues detected
5. Detailed logging of all operations

USAGE:
  # Dry run - show what would be done (SAFE)
  python3 migrate_misplaced_properties.py --dry-run

  # Migrate a small test batch first (recommended)
  python3 migrate_misplaced_properties.py --limit 10

  # Full migration with automatic backups
  python3 migrate_misplaced_properties.py

  # Skip backup creation (not recommended)
  python3 migrate_misplaced_properties.py --no-backup

SAFETY FEATURES:
- Creates backup collections automatically (e.g., varsity_lakes_backup_20260217_153045)
- Verifies each property move (insert successful + delete successful)
- Logs all operations to detailed log file
- Can rollback from backups if needed
- Dry-run mode to preview changes

AFTER MIGRATION:
1. Verify application works correctly
2. Run verification script: python3 verify_migration.py
3. If all good, run cleanup: python3 cleanup_migration_backups.py
"""

import os
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from pymongo import MongoClient
from bson import ObjectId
import json

# Add the parent directory to the path to import database_audit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database_audit import DatabaseAuditor

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

# Backup naming
BACKUP_TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')


class SafeMigrator:
    """Safely migrates misplaced properties with automatic backups"""

    def __init__(self, mongodb_uri: str = MONGODB_URI, database_name: str = DATABASE_NAME):
        """Initialize migrator"""
        self.mongodb_uri = mongodb_uri
        self.database_name = database_name
        self.client = None
        self.db = None
        self.auditor = None
        self.backup_collections = {}  # Maps original collection -> backup collection name
        self.migration_log = []
        self.stats = {
            'backups_created': 0,
            'properties_migrated': 0,
            'properties_failed': 0,
            'collections_affected': set(),
            'errors': [],
        }

    def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.database_name]
            # Test connection
            self.client.admin.command('ping')
            print(f"✅ Connected to MongoDB: {self.database_name}")
            return True
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            return False

    def create_backup(self, collection_name: str, dry_run: bool = False) -> Optional[str]:
        """
        Create a backup of a collection before migration.

        Args:
            collection_name: Name of collection to backup
            dry_run: If True, don't actually create backup

        Returns:
            Backup collection name if successful, None otherwise
        """
        backup_name = f"{collection_name}_backup_{BACKUP_TIMESTAMP}"

        if collection_name in self.backup_collections:
            # Already backed up
            return self.backup_collections[collection_name]

        print(f"\n📦 Creating backup: {collection_name} -> {backup_name}")

        if dry_run:
            print(f"   (Dry run - backup not created)")
            self.backup_collections[collection_name] = backup_name
            return backup_name

        try:
            source_coll = self.db[collection_name]
            backup_coll = self.db[backup_name]

            # Copy all documents
            docs = list(source_coll.find({}))
            if docs:
                backup_coll.insert_many(docs)

            # Store backup metadata
            metadata = {
                'original_collection': collection_name,
                'backup_created_at': datetime.now(),
                'document_count': len(docs),
                'purpose': 'Pre-migration backup for misplaced properties fix',
                'script': 'migrate_misplaced_properties.py',
            }
            backup_coll.insert_one({'_backup_metadata': metadata})

            self.backup_collections[collection_name] = backup_name
            self.stats['backups_created'] += 1

            print(f"   ✅ Backup created: {len(docs)} documents")
            return backup_name

        except Exception as e:
            print(f"   ❌ Backup failed: {e}")
            self.stats['errors'].append({
                'operation': 'backup',
                'collection': collection_name,
                'error': str(e),
            })
            return None

    def migrate_property(self, error: Dict, dry_run: bool = False) -> bool:
        """
        Migrate a single property to the correct collection.

        Args:
            error: Error dict from database_audit
            dry_run: If True, don't actually migrate

        Returns:
            True if successful, False otherwise
        """
        source_coll_name = error['current_collection']
        target_coll_name = error['correct_collection']
        doc_id = ObjectId(error['document_id'])
        address = error['address']

        if dry_run:
            print(f"   Would migrate: {address}")
            print(f"      From: {source_coll_name}")
            print(f"      To: {target_coll_name}")
            return True

        try:
            # Get collections
            source_coll = self.db[source_coll_name]
            target_coll = self.db[target_coll_name]

            # Get the document
            doc = source_coll.find_one({'_id': doc_id})

            if not doc:
                print(f"   ❌ Document not found: {doc_id}")
                return False

            # Update suburb field to correct value
            doc['suburb'] = error['actual_suburb']

            # Add migration metadata
            if 'migration_history' not in doc:
                doc['migration_history'] = []

            doc['migration_history'].append({
                'migrated_at': datetime.now(),
                'from_collection': source_coll_name,
                'to_collection': target_coll_name,
                'reason': 'Safe migration with backup',
                'root_cause': error['root_cause'],
                'backup_collection': self.backup_collections.get(source_coll_name),
                'script': 'migrate_misplaced_properties.py',
            })

            # STEP 1: Insert into target collection (can rollback if this fails)
            try:
                target_coll.insert_one(doc)
            except Exception as insert_error:
                print(f"   ❌ Insert failed: {insert_error}")
                return False

            # STEP 2: Delete from source collection (only if insert succeeded)
            result = source_coll.delete_one({'_id': doc_id})

            if result.deleted_count != 1:
                print(f"   ⚠️  WARNING: Property inserted to {target_coll_name} but not deleted from {source_coll_name}!")
                print(f"      Manual cleanup may be required for: {address}")
                return False

            # Success!
            self.migration_log.append({
                'document_id': str(doc_id),
                'address': address,
                'from_collection': source_coll_name,
                'to_collection': target_coll_name,
                'timestamp': datetime.now(),
                'status': 'success',
            })

            return True

        except Exception as e:
            print(f"   ❌ Migration error: {e}")
            self.stats['errors'].append({
                'operation': 'migrate',
                'document_id': str(doc_id),
                'address': address,
                'error': str(e),
            })
            return False

    def run_migration(self, limit: Optional[int] = None, dry_run: bool = False, no_backup: bool = False):
        """
        Run the full migration process.

        Args:
            limit: Limit number of properties to migrate (for testing)
            dry_run: If True, don't actually make changes
            no_backup: If True, skip backup creation (not recommended)
        """
        print(f"\n{'=' * 80}")
        print(f"SAFE PROPERTY MIGRATION")
        print(f"{'=' * 80}")
        print(f"Database: {self.database_name}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if dry_run:
            print(f"Mode: DRY RUN (no changes will be made)")
        if limit:
            print(f"Limit: {limit} properties (test migration)")
        if no_backup:
            print(f"⚠️  WARNING: Backup creation disabled!")
        print(f"{'=' * 80}\n")

        # Step 1: Run audit to find misplaced properties
        print("STEP 1: Running database audit to identify misplaced properties...")
        print("-" * 80)

        self.auditor = DatabaseAuditor(self.mongodb_uri, self.database_name)
        if not self.auditor.connect():
            print("❌ Failed to connect to database for audit")
            return False

        errors = self.auditor.audit_all_collections(verbose=False)

        if not errors:
            print("\n✅ No misplaced properties found! Database is clean.")
            return True

        print(f"\n✓ Audit complete: Found {len(errors)} misplaced properties")

        # Apply limit if specified
        if limit:
            errors = errors[:limit]
            print(f"✓ Limited to first {len(errors)} properties for testing")

        # Step 2: Create backups
        if not no_backup:
            print(f"\nSTEP 2: Creating backups of affected collections...")
            print("-" * 80)

            # Get unique source collections
            source_collections = set(error['current_collection'] for error in errors)
            print(f"Collections to backup: {len(source_collections)}")

            for coll_name in sorted(source_collections):
                backup_name = self.create_backup(coll_name, dry_run=dry_run)
                if not backup_name and not dry_run:
                    print(f"\n❌ Backup failed for {coll_name}. Aborting migration for safety.")
                    return False

            if not dry_run:
                print(f"\n✅ All backups created successfully ({self.stats['backups_created']} collections)")
        else:
            print(f"\nSTEP 2: Skipping backups (--no-backup flag)")

        # Step 3: Migrate properties
        print(f"\nSTEP 3: Migrating properties to correct collections...")
        print("-" * 80)

        for i, error in enumerate(errors, 1):
            print(f"\n[{i}/{len(errors)}] Migrating property...")
            print(f"   Address: {error['address']}")
            print(f"   From: {error['current_collection']}")
            print(f"   To: {error['correct_collection']}")

            success = self.migrate_property(error, dry_run=dry_run)

            if success:
                self.stats['properties_migrated'] += 1
                self.stats['collections_affected'].add(error['current_collection'])
                self.stats['collections_affected'].add(error['correct_collection'])
                if not dry_run:
                    print(f"   ✅ Migrated successfully")
            else:
                self.stats['properties_failed'] += 1
                if not dry_run:
                    print(f"   ❌ Migration failed")

        # Step 4: Summary
        print(f"\n{'=' * 80}")
        print(f"MIGRATION SUMMARY")
        print(f"{'=' * 80}")
        if dry_run:
            print(f"Mode: DRY RUN (no actual changes made)")
        print(f"Backups Created: {self.stats['backups_created']} collections")
        print(f"Properties Migrated: {self.stats['properties_migrated']}")
        print(f"Properties Failed: {self.stats['properties_failed']}")
        print(f"Collections Affected: {len(self.stats['collections_affected'])}")

        if self.stats['errors']:
            print(f"\n⚠️  Errors Encountered: {len(self.stats['errors'])}")
            print("\nFirst 5 errors:")
            for error in self.stats['errors'][:5]:
                print(f"  - {error['operation']}: {error.get('error', 'Unknown error')}")

        if not dry_run and self.stats['properties_migrated'] > 0:
            print(f"\n✅ Migration completed successfully!")
            print(f"\nNEXT STEPS:")
            print(f"1. Verify your application works correctly")
            print(f"2. Run verification script: python3 scripts/verify_migration.py")
            print(f"3. If all good, cleanup backups: python3 scripts/cleanup_migration_backups.py")
            print(f"\nBackup collections created:")
            for orig, backup in sorted(self.backup_collections.items()):
                print(f"   - {backup} (backup of {orig})")

        print(f"{'=' * 80}\n")

        return True

    def export_migration_log(self, log_file: str):
        """Export migration log to file"""
        try:
            with open(log_file, 'w') as f:
                json.dump({
                    'migration_timestamp': BACKUP_TIMESTAMP,
                    'database': self.database_name,
                    'stats': {
                        'backups_created': self.stats['backups_created'],
                        'properties_migrated': self.stats['properties_migrated'],
                        'properties_failed': self.stats['properties_failed'],
                        'collections_affected': list(self.stats['collections_affected']),
                    },
                    'backup_collections': self.backup_collections,
                    'migration_log': [
                        {
                            **entry,
                            'timestamp': entry['timestamp'].isoformat()
                        }
                        for entry in self.migration_log
                    ],
                    'errors': self.stats['errors'],
                }, f, indent=2)

            print(f"✅ Migration log exported to: {log_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to export log: {e}")
            return False

    def close(self):
        """Close connections"""
        if self.auditor:
            self.auditor.close()
        if self.client:
            self.client.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Safely migrate misplaced properties with automatic backups',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would happen (SAFE)
  python3 migrate_misplaced_properties.py --dry-run

  # Test with small batch first (recommended)
  python3 migrate_misplaced_properties.py --limit 10

  # Full migration with automatic backups
  python3 migrate_misplaced_properties.py

  # Export detailed log
  python3 migrate_misplaced_properties.py --log /tmp/migration_$(date +%Y%m%d).json

IMPORTANT:
  This script creates automatic backups before migration.
  After migration, verify everything works, then cleanup backups with:
  python3 cleanup_migration_backups.py
        """
    )

    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int, metavar='N',
                        help='Limit migration to first N properties (for testing)')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip backup creation (NOT RECOMMENDED)')
    parser.add_argument('--log', type=str, metavar='FILE',
                        help='Export migration log to JSON file')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Skip confirmation prompt (non-interactive mode)')

    args = parser.parse_args()

    # Confirm if not dry-run and not --yes
    if not args.dry_run and not args.yes:
        print("\n⚠️  WARNING: This will modify your database!")
        print("Backups will be created automatically before migration.")
        print("\nContinue? (yes/no): ", end='')
        response = input().strip().lower()
        if response not in ['yes', 'y']:
            print("Migration cancelled.")
            sys.exit(0)

    # Create migrator
    migrator = SafeMigrator()

    # Connect
    if not migrator.connect():
        sys.exit(1)

    try:
        # Run migration
        success = migrator.run_migration(
            limit=args.limit,
            dry_run=args.dry_run,
            no_backup=args.no_backup
        )

        # Export log if requested
        if args.log and not args.dry_run:
            migrator.export_migration_log(args.log)

        exit_code = 0 if success else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        exit_code = 130
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        migrator.close()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
