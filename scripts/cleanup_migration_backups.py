#!/usr/bin/env python3
"""
Migration Backup Cleanup Script
Created: 2026-02-17

Safely removes backup collections created during migration.

⚠️  IMPORTANT: Only run this AFTER:
1. Migration completed successfully
2. Verification script passed all checks
3. Application has been tested and works correctly

This script:
1. Lists all backup collections
2. Shows what will be deleted
3. Requires explicit confirmation
4. Optionally exports backups to JSON before deletion
5. Deletes backup collections

USAGE:
  # List backups without deleting
  python3 cleanup_migration_backups.py --list

  # Export backups to JSON before cleanup (recommended)
  python3 cleanup_migration_backups.py --export /tmp/backups/

  # Delete all backup collections (interactive)
  python3 cleanup_migration_backups.py

  # Delete specific backup
  python3 cleanup_migration_backups.py --collection varsity_lakes_backup_20260217_153045
"""

import os
import sys
import argparse
import json
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'


class BackupCleaner:
    """Safely removes migration backup collections"""

    def __init__(self, mongodb_uri: str = MONGODB_URI, database_name: str = DATABASE_NAME):
        """Initialize cleaner"""
        self.mongodb_uri = mongodb_uri
        self.database_name = database_name
        self.client = None
        self.db = None
        self.stats = {
            'backups_found': 0,
            'backups_exported': 0,
            'backups_deleted': 0,
            'errors': [],
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

    def find_backup_collections(self) -> list:
        """
        Find all backup collections in the database.

        Returns:
            List of backup collection names
        """
        all_collections = self.db.list_collection_names()
        backup_collections = [c for c in all_collections if '_backup_' in c]

        # Sort by timestamp (newest first)
        backup_collections.sort(reverse=True)

        return backup_collections

    def get_backup_info(self, backup_name: str) -> dict:
        """
        Get information about a backup collection.

        Args:
            backup_name: Name of backup collection

        Returns:
            Dict with backup metadata
        """
        coll = self.db[backup_name]
        metadata_doc = coll.find_one({'_backup_metadata': {'$exists': True}})

        if metadata_doc and '_backup_metadata' in metadata_doc:
            metadata = metadata_doc['_backup_metadata']
            doc_count = coll.count_documents({'_backup_metadata': {'$exists': False}})

            return {
                'name': backup_name,
                'original_collection': metadata.get('original_collection', 'unknown'),
                'created_at': metadata.get('backup_created_at', 'unknown'),
                'document_count': doc_count,
                'purpose': metadata.get('purpose', 'unknown'),
                'has_metadata': True,
            }
        else:
            # No metadata, just count
            doc_count = coll.count_documents({})
            return {
                'name': backup_name,
                'original_collection': 'unknown',
                'created_at': 'unknown',
                'document_count': doc_count,
                'purpose': 'unknown',
                'has_metadata': False,
            }

    def list_backups(self):
        """List all backup collections with details"""
        backups = self.find_backup_collections()

        if not backups:
            print("\n✅ No backup collections found!")
            print("   Either no migration has been run, or backups were already cleaned up.")
            return

        print(f"\n{'=' * 80}")
        print(f"BACKUP COLLECTIONS FOUND: {len(backups)}")
        print(f"{'=' * 80}\n")

        total_docs = 0

        for i, backup_name in enumerate(backups, 1):
            info = self.get_backup_info(backup_name)
            total_docs += info['document_count']

            print(f"{i}. {backup_name}")
            print(f"   Original Collection: {info['original_collection']}")
            print(f"   Created: {info['created_at']}")
            print(f"   Documents: {info['document_count']:,}")
            print(f"   Purpose: {info['purpose']}")
            print()

        print(f"{'=' * 80}")
        print(f"Total: {len(backups)} backup collections, {total_docs:,} documents")
        print(f"{'=' * 80}\n")

        # Estimate size (very rough)
        # Assume ~5KB per document on average
        estimated_size_mb = (total_docs * 5) / 1024
        print(f"Estimated disk space: ~{estimated_size_mb:.1f} MB")
        print(f"{'=' * 80}\n")

        self.stats['backups_found'] = len(backups)

    def export_backup(self, backup_name: str, export_dir: str) -> bool:
        """
        Export a backup collection to JSON file.

        Args:
            backup_name: Name of backup collection
            export_dir: Directory to export to

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create export directory if it doesn't exist
            os.makedirs(export_dir, exist_ok=True)

            # Export file path
            export_file = os.path.join(export_dir, f"{backup_name}.json")

            print(f"Exporting {backup_name}...")

            coll = self.db[backup_name]
            docs = list(coll.find({}))

            # Convert ObjectId to string for JSON serialization
            def convert_objectid(obj):
                if isinstance(obj, ObjectId):
                    return str(obj)
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: convert_objectid(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_objectid(item) for item in obj]
                return obj

            docs_serializable = [convert_objectid(doc) for doc in docs]

            with open(export_file, 'w') as f:
                json.dump({
                    'backup_collection': backup_name,
                    'exported_at': datetime.now().isoformat(),
                    'document_count': len(docs_serializable),
                    'documents': docs_serializable,
                }, f, indent=2)

            print(f"  ✓ Exported {len(docs):,} documents to: {export_file}")
            self.stats['backups_exported'] += 1
            return True

        except Exception as e:
            print(f"  ✗ Export failed: {e}")
            self.stats['errors'].append({
                'operation': 'export',
                'backup': backup_name,
                'error': str(e),
            })
            return False

    def delete_backup(self, backup_name: str) -> bool:
        """
        Delete a backup collection.

        Args:
            backup_name: Name of backup collection to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            info = self.get_backup_info(backup_name)
            print(f"\nDeleting {backup_name}...")
            print(f"  Original: {info['original_collection']}")
            print(f"  Documents: {info['document_count']:,}")

            self.db[backup_name].drop()

            print(f"  ✓ Deleted successfully")
            self.stats['backups_deleted'] += 1
            return True

        except Exception as e:
            print(f"  ✗ Deletion failed: {e}")
            self.stats['errors'].append({
                'operation': 'delete',
                'backup': backup_name,
                'error': str(e),
            })
            return False

    def cleanup_all_backups(self, export_dir: str = None, specific_collection: str = None):
        """
        Clean up backup collections.

        Args:
            export_dir: If provided, export backups before deletion
            specific_collection: If provided, only clean up this collection
        """
        if specific_collection:
            backups = [specific_collection]
            print(f"\n{'=' * 80}")
            print(f"CLEANUP SPECIFIC BACKUP")
            print(f"{'=' * 80}\n")
        else:
            backups = self.find_backup_collections()
            print(f"\n{'=' * 80}")
            print(f"CLEANUP ALL BACKUP COLLECTIONS")
            print(f"{'=' * 80}\n")

        if not backups:
            print("✅ No backup collections to clean up!")
            return

        print(f"Found {len(backups)} backup collection(s) to clean up:")
        for backup in backups:
            info = self.get_backup_info(backup)
            print(f"  - {backup} ({info['document_count']:,} docs)")

        # Export if requested
        if export_dir:
            print(f"\n{'=' * 80}")
            print(f"STEP 1: Exporting Backups")
            print(f"{'=' * 80}\n")
            print(f"Export directory: {export_dir}")

            for backup in backups:
                self.export_backup(backup, export_dir)

            print(f"\n✅ Exported {self.stats['backups_exported']} backup(s)")

        # Confirm deletion
        print(f"\n{'=' * 80}")
        print(f"⚠️  WARNING: ABOUT TO DELETE BACKUP COLLECTIONS")
        print(f"{'=' * 80}")
        print(f"This will permanently delete {len(backups)} backup collection(s).")
        print(f"Make sure:")
        print(f"  1. Migration was successful")
        print(f"  2. Verification script passed")
        print(f"  3. Application is working correctly")

        if export_dir:
            print(f"  4. Backups were exported to: {export_dir}")

        print(f"\nContinue with deletion? (yes/no): ", end='')
        response = input().strip().lower()

        if response not in ['yes', 'y']:
            print("\nCleanup cancelled. Backups were NOT deleted.")
            if export_dir and self.stats['backups_exported'] > 0:
                print(f"Exported backups are saved in: {export_dir}")
            return

        # Delete backups
        print(f"\n{'=' * 80}")
        print(f"STEP {'2' if export_dir else '1'}: Deleting Backups")
        print(f"{'=' * 80}\n")

        for backup in backups:
            self.delete_backup(backup)

        # Summary
        print(f"\n{'=' * 80}")
        print(f"CLEANUP SUMMARY")
        print(f"{'=' * 80}")
        if export_dir:
            print(f"Backups Exported: {self.stats['backups_exported']}")
        print(f"Backups Deleted: {self.stats['backups_deleted']}")
        print(f"Errors: {len(self.stats['errors'])}")

        if self.stats['errors']:
            print(f"\nErrors encountered:")
            for error in self.stats['errors']:
                print(f"  - {error['operation']} {error['backup']}: {error['error']}")

        if self.stats['backups_deleted'] > 0:
            print(f"\n✅ Cleanup completed successfully!")
            if export_dir:
                print(f"   Exported backups saved to: {export_dir}")
        print(f"{'=' * 80}\n")

    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Clean up migration backup collections',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List backups without deleting
  python3 cleanup_migration_backups.py --list

  # Export and delete all backups
  python3 cleanup_migration_backups.py --export /tmp/backups/

  # Delete all backups (interactive confirmation)
  python3 cleanup_migration_backups.py

  # Delete specific backup
  python3 cleanup_migration_backups.py --collection varsity_lakes_backup_20260217_153045

IMPORTANT:
  Only run this after verifying migration was successful!
        """
    )

    parser.add_argument('--list', action='store_true',
                        help='List backup collections without deleting')
    parser.add_argument('--export', type=str, metavar='DIR',
                        help='Export backups to directory before deletion (recommended)')
    parser.add_argument('--collection', type=str, metavar='NAME',
                        help='Clean up specific backup collection only')

    args = parser.parse_args()

    cleaner = BackupCleaner()

    if not cleaner.connect():
        sys.exit(1)

    try:
        if args.list:
            # Just list backups
            cleaner.list_backups()
        else:
            # Clean up backups
            cleaner.cleanup_all_backups(
                export_dir=args.export,
                specific_collection=args.collection
            )

        exit_code = 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Cleanup interrupted by user")
        exit_code = 130
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        cleaner.close()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
