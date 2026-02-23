#!/usr/bin/env python3
"""
Migration Verification Script
Last Edit: 07/02/2026, 6:31 PM (Wednesday) - Brisbane Time

Compares document counts between local MongoDB and Azure Cosmos DB
to verify that the migration was successful.

Usage:
    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 migration/03_verify_migration.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient

# Load .env file
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip('"').strip("'")
                os.environ[key.strip()] = value

LOCAL_URI = "mongodb://127.0.0.1:27017/"
COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "")

DATABASES = [
    "property_data",
    "Gold_Coast_Currently_For_Sale",
    "Gold_Coast",
    "Gold_Coast_Recently_Sold",
]


def connect(uri, name):
    """Connect to a MongoDB instance."""
    try:
        kwargs = {"serverSelectionTimeoutMS": 15000}
        if "cosmos.azure.com" in uri:
            kwargs["retryWrites"] = False
        client = MongoClient(uri, **kwargs)
        client.admin.command("ping")
        return client
    except Exception as e:
        print(f"   ❌ Cannot connect to {name}: {e}")
        return None


def get_db_stats(client, db_name):
    """Get collection names and document counts for a database."""
    db = client[db_name]
    stats = {}
    try:
        for coll_name in sorted(db.list_collection_names()):
            if coll_name.startswith("system."):
                continue
            try:
                count = db[coll_name].count_documents({})
                stats[coll_name] = count
            except Exception as e:
                stats[coll_name] = f"ERROR: {e}"
    except Exception as e:
        print(f"   ❌ Error listing collections: {e}")
    return stats


def main():
    print("=" * 70)
    print("  Migration Verification - Local MongoDB vs Azure Cosmos DB")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Brisbane)")
    print("=" * 70)

    if not COSMOS_URI:
        print("\n❌ COSMOS_CONNECTION_STRING not set in .env")
        sys.exit(1)

    # Connect to both
    print("\n🔌 Connecting to Local MongoDB...")
    local_client = connect(LOCAL_URI, "Local MongoDB")

    print("🔌 Connecting to Azure Cosmos DB...")
    cosmos_client = connect(COSMOS_URI, "Cosmos DB")

    if not local_client and not cosmos_client:
        print("\n❌ Cannot connect to either database. Aborting.")
        sys.exit(1)

    total_local = 0
    total_cosmos = 0
    total_match = 0
    total_mismatch = 0
    issues = []

    for db_name in DATABASES:
        print(f"\n{'='*70}")
        print(f"📦 Database: {db_name}")
        print(f"{'='*70}")

        local_stats = get_db_stats(local_client, db_name) if local_client else {}
        cosmos_stats = get_db_stats(cosmos_client, db_name) if cosmos_client else {}

        all_collections = sorted(set(list(local_stats.keys()) + list(cosmos_stats.keys())))

        if not all_collections:
            print("   (no collections)")
            continue

        print(f"\n   {'Collection':<35} {'Local':>10} {'Cosmos':>10} {'Status':>10}")
        print(f"   {'-'*35} {'-'*10} {'-'*10} {'-'*10}")

        for coll in all_collections:
            local_count = local_stats.get(coll, 0)
            cosmos_count = cosmos_stats.get(coll, 0)

            if isinstance(local_count, str) or isinstance(cosmos_count, str):
                status = "⚠️ ERROR"
                issues.append(f"{db_name}.{coll}: count error")
            elif local_count == cosmos_count:
                status = "✅ Match"
                total_match += 1
            elif cosmos_count == 0 and local_count > 0:
                status = "❌ Missing"
                total_mismatch += 1
                issues.append(f"{db_name}.{coll}: {local_count} docs missing in Cosmos")
            elif local_count == 0 and cosmos_count > 0:
                status = "➕ New"
                total_match += 1  # Not a problem
            else:
                diff = cosmos_count - local_count
                pct = (diff / local_count * 100) if local_count > 0 else 0
                if abs(pct) < 5:
                    status = "≈ Close"
                    total_match += 1
                else:
                    status = f"⚠️ {diff:+d}"
                    total_mismatch += 1
                    issues.append(f"{db_name}.{coll}: local={local_count}, cosmos={cosmos_count} (diff={diff})")

            local_display = str(local_count) if isinstance(local_count, int) else "ERR"
            cosmos_display = str(cosmos_count) if isinstance(cosmos_count, int) else "ERR"

            print(f"   {coll:<35} {local_display:>10} {cosmos_display:>10} {status:>10}")

            if isinstance(local_count, int):
                total_local += local_count
            if isinstance(cosmos_count, int):
                total_cosmos += cosmos_count

    # Summary
    print(f"\n{'='*70}")
    print("  VERIFICATION SUMMARY")
    print(f"{'='*70}")
    print(f"  Total documents (Local):  {total_local:,}")
    print(f"  Total documents (Cosmos): {total_cosmos:,}")
    print(f"  Collections matched:      {total_match}")
    print(f"  Collections mismatched:   {total_mismatch}")

    if issues:
        print(f"\n  ⚠️  Issues Found ({len(issues)}):")
        for issue in issues:
            print(f"    - {issue}")
        print(f"\n  💡 Re-run import for affected databases:")
        print(f"     cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash migration/02_import_to_cosmos.sh")
    else:
        print(f"\n  🎉 ALL COLLECTIONS VERIFIED - Migration successful!")

    print(f"{'='*70}")

    # Cleanup
    if local_client:
        local_client.close()
    if cosmos_client:
        cosmos_client.close()

    sys.exit(1 if total_mismatch > 0 else 0)


if __name__ == "__main__":
    main()
