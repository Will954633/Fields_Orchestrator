#!/usr/bin/env python3
"""
Setup script for system_monitor Cosmos DB database.

Creates:
  - system_monitor.process_runs       (pipeline run records)
  - system_monitor.api_health_checks  (website API health results)
  - system_monitor.data_integrity     (DB reconciliation results)
  - system_monitor.repair_requests    (Claude Code repair queue)

Indexes:
  - process_runs: system, pipeline, started_at (TTL 90 days), status
  - api_health_checks: endpoint, checked_at
  - data_integrity: check_name, checked_at
  - repair_requests: status, created_at

Run once before first use:
  python3 shared/setup_monitor_db.py

Safe to re-run — skips existing indexes.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, OperationFailure


MONITOR_DB = "system_monitor"

# 90-day TTL in seconds
TTL_90_DAYS = 90 * 24 * 60 * 60


def get_client(uri: str) -> MongoClient:
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=15_000,
        socketTimeoutMS=20_000,
        connectTimeoutMS=15_000,
        retryWrites=False,  # Required for Cosmos DB
    )


def create_index_safe(collection, keys, **kwargs):
    """Create an index, skipping if it already exists."""
    name = kwargs.get("name", str(keys))
    try:
        collection.create_index(keys, **kwargs)
        print(f"    ✅ Index created: {name}")
    except OperationFailure as e:
        if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
            print(f"    ⏭  Index already exists: {name}")
        else:
            print(f"    ⚠️  Index error ({name}): {e}")
    except Exception as e:
        print(f"    ⚠️  Index error ({name}): {e}")


def setup(uri: str) -> None:
    print(f"\nConnecting to Cosmos DB...")
    client = get_client(uri)

    try:
        client.admin.command("ping")
        print("✅ Connected\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

    db = client[MONITOR_DB]

    # ------------------------------------------------------------------
    # 1. process_runs
    # ------------------------------------------------------------------
    print("Setting up process_runs collection...")
    col = db["process_runs"]

    # Seed one document to ensure collection exists (Cosmos DB requires this)
    if col.count_documents({}) == 0:
        col.insert_one({
            "_id": "setup_seed",
            "system": "setup",
            "pipeline": "setup",
            "process_id": "setup",
            "process_name": "Database Setup",
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "status": "success",
            "duration_seconds": 0,
            "error_count": 0,
            "warning_count": 0,
            "metrics": {},
            "errors": [],
        })
        print("  Seed document inserted")

    create_index_safe(col, [("system", ASCENDING)], name="idx_system")
    create_index_safe(col, [("pipeline", ASCENDING)], name="idx_pipeline")
    create_index_safe(col, [("status", ASCENDING)], name="idx_status")
    create_index_safe(col, [("started_at", DESCENDING)], name="idx_started_at_desc")
    create_index_safe(
        col,
        [("system", ASCENDING), ("pipeline", ASCENDING), ("started_at", DESCENDING)],
        name="idx_system_pipeline_started"
    )
    # TTL index — auto-delete records older than 90 days
    create_index_safe(
        col,
        [("started_at", ASCENDING)],
        name="idx_ttl_90d",
        expireAfterSeconds=TTL_90_DAYS
    )

    # ------------------------------------------------------------------
    # 2. api_health_checks
    # ------------------------------------------------------------------
    print("\nSetting up api_health_checks collection...")
    col = db["api_health_checks"]

    if col.count_documents({}) == 0:
        col.insert_one({
            "_id": "setup_seed",
            "endpoint": "/api/setup",
            "checked_at": datetime.now(timezone.utc),
            "status_code": 200,
            "response_ms": 0,
            "healthy": True,
            "data": {},
        })
        print("  Seed document inserted")

    create_index_safe(col, [("endpoint", ASCENDING)], name="idx_endpoint")
    create_index_safe(col, [("checked_at", DESCENDING)], name="idx_checked_at_desc")
    create_index_safe(
        col,
        [("endpoint", ASCENDING), ("checked_at", DESCENDING)],
        name="idx_endpoint_checked"
    )
    create_index_safe(
        col,
        [("checked_at", ASCENDING)],
        name="idx_ttl_90d",
        expireAfterSeconds=TTL_90_DAYS
    )

    # ------------------------------------------------------------------
    # 3. data_integrity
    # ------------------------------------------------------------------
    print("\nSetting up data_integrity collection...")
    col = db["data_integrity"]

    if col.count_documents({}) == 0:
        col.insert_one({
            "_id": "setup_seed",
            "check_name": "setup",
            "checked_at": datetime.now(timezone.utc),
            "db_count": 0,
            "expected_count": 0,
            "variance_pct": 0.0,
            "status": "ok",
            "details": "Initial setup",
        })
        print("  Seed document inserted")

    create_index_safe(col, [("check_name", ASCENDING)], name="idx_check_name")
    create_index_safe(col, [("checked_at", DESCENDING)], name="idx_checked_at_desc")
    create_index_safe(
        col,
        [("checked_at", ASCENDING)],
        name="idx_ttl_90d",
        expireAfterSeconds=TTL_90_DAYS
    )

    # ------------------------------------------------------------------
    # 4. repair_requests
    # ------------------------------------------------------------------
    print("\nSetting up repair_requests collection...")
    col = db["repair_requests"]

    if col.count_documents({}) == 0:
        col.insert_one({
            "_id": "setup_seed",
            "status": "setup",
            "created_at": datetime.now(timezone.utc),
            "error_id": None,
            "approved_by": None,
            "approved_at": None,
            "diff": None,
            "deployed_at": None,
            "claude_output": None,
        })
        print("  Seed document inserted")

    create_index_safe(col, [("status", ASCENDING)], name="idx_status")
    create_index_safe(col, [("created_at", DESCENDING)], name="idx_created_at_desc")

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    print("\n✅ system_monitor database setup complete")
    print(f"   Database: {MONITOR_DB}")
    print(f"   Collections: process_runs, api_health_checks, data_integrity, repair_requests")
    print(f"   TTL: 90 days on process_runs, api_health_checks, data_integrity")

    client.close()


if __name__ == "__main__":
    uri = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("MONGODB_URI")
    if not uri:
        print("❌ COSMOS_CONNECTION_STRING environment variable not set")
        sys.exit(1)
    setup(uri)
