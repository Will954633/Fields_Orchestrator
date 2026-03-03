#!/usr/bin/env python3
"""
API Health Checker — polls all website API endpoints and writes results to MongoDB.
Designed to be run via cron every 30 minutes.

Usage:
    python3 scripts/api-health-check.py          # Run health checks
    python3 scripts/api-health-check.py --dry-run # Print results without writing to DB
"""

import os
import sys
import time
import argparse
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone

# Load .env from orchestrator root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)

from pymongo import MongoClient

BASE_URL = "https://fieldsestate.com.au"

# Endpoints to check, grouped by type
ENDPOINTS = [
    # Health endpoints (fast, no auth)
    {"path": "/api/v1/properties/health", "expect_key": None},
    {"path": "/api/v1/recently-sold/health", "expect_key": None},
    {"path": "/api/v1/address-search/health", "expect_key": None},
    {"path": "/api/v1/analyse-property/health", "expect_key": None},
    {"path": "/api/market-narrative/robina/health", "expect_key": None},
    # Data endpoints (slower, validate response has content)
    {"path": "/api/v1/properties/for-sale", "expect_key": "properties"},
    {"path": "/api/v1/properties/recently-sold", "expect_key": "properties"},
    {"path": "/api/v1/address-search?q=robina", "expect_key": None},
    {"path": "/api/market-narrative/robina", "expect_key": None},
    {"path": "/api/market-narrative/varsity_lakes", "expect_key": None},
    {"path": "/api/market-insights?suburb=robina", "expect_key": None},
]

# Generous timeout — some Cosmos queries are slow on cold start
REQUEST_TIMEOUT = 15


def check_endpoint(endpoint_info):
    """Hit an endpoint and return health check result."""
    path = endpoint_info["path"]
    url = f"{BASE_URL}{path}"

    start = time.monotonic()
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "FieldsHealthChecker/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            elapsed_ms = int((time.monotonic() - start) * 1000)

            # Healthy = 2xx status and non-empty body
            healthy = 200 <= status_code < 300 and len(body) > 2

            return {
                "endpoint": path,
                "status_code": status_code,
                "response_ms": elapsed_ms,
                "healthy": healthy,
                "checked_at": datetime.now(timezone.utc),
                "body_length": len(body),
            }
    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "endpoint": path,
            "status_code": e.code,
            "response_ms": elapsed_ms,
            "healthy": False,
            "checked_at": datetime.now(timezone.utc),
            "error": str(e),
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "endpoint": path,
            "status_code": 0,
            "response_ms": elapsed_ms,
            "healthy": False,
            "checked_at": datetime.now(timezone.utc),
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="API health checker")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to DB")
    args = parser.parse_args()

    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str and not args.dry_run:
        print("ERROR: COSMOS_CONNECTION_STRING not set", file=sys.stderr)
        sys.exit(1)

    results = []
    for ep in ENDPOINTS:
        result = check_endpoint(ep)
        status = "OK" if result["healthy"] else "FAIL"
        ms = result["response_ms"]
        code = result["status_code"]
        print(f"  [{status}] {ep['path']} — {code} in {ms}ms")
        results.append(result)

    healthy = sum(1 for r in results if r["healthy"])
    total = len(results)
    print(f"\nSummary: {healthy}/{total} healthy")

    if args.dry_run:
        print("(dry-run — not writing to DB)")
        return

    # Write to MongoDB
    client = MongoClient(conn_str)
    col = client["system_monitor"]["api_health_checks"]

    # Upsert by endpoint so we don't accumulate stale records forever
    for r in results:
        col.update_one(
            {"endpoint": r["endpoint"]},
            {"$set": r},
            upsert=True,
        )

    client.close()
    print(f"Wrote {len(results)} health check results to system_monitor.api_health_checks")


if __name__ == "__main__":
    main()
