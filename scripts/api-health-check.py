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
import json
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

CONTRACT_PAIRS = [
    {
        "name": "recently_sold_public_contract",
        "health_path": "/api/v1/recently-sold/health",
        "data_path": "/api/v1/properties/recently-sold",
    },
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
            validation_error = None

            expect_key = endpoint_info.get("expect_key")
            if healthy and expect_key:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as exc:
                    healthy = False
                    validation_error = f"invalid json: {exc}"
                else:
                    value = payload.get(expect_key)
                    if not value:
                        healthy = False
                        validation_error = f"missing_or_empty_key:{expect_key}"

            return {
                "endpoint": path,
                "status_code": status_code,
                "response_ms": elapsed_ms,
                "healthy": healthy,
                "checked_at": datetime.now(timezone.utc),
                "body_length": len(body),
                "expected_key": expect_key,
                "validation_error": validation_error,
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
            "expected_key": endpoint_info.get("expect_key"),
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
            "expected_key": endpoint_info.get("expect_key"),
        }


def apply_contract_checks(results):
    """Mark paired health/data routes as mismatched when they diverge."""
    by_endpoint = {row["endpoint"]: row for row in results}
    for pair in CONTRACT_PAIRS:
        health = by_endpoint.get(pair["health_path"])
        data = by_endpoint.get(pair["data_path"])
        if not health or not data:
            continue

        mismatch = bool(health.get("healthy")) != bool(data.get("healthy"))
        issue = None
        if mismatch:
            issue = f"contract_mismatch:{pair['health_path']} vs {pair['data_path']}"

        for row, peer in ((health, data), (data, health)):
            row["contract_name"] = pair["name"]
            row["paired_endpoint"] = peer["endpoint"]
            row["contract_ok"] = not mismatch
            # Always set contract_issue (None clears stale mismatch flags)
            row["contract_issue"] = issue


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

    apply_contract_checks(results)

    for result in results:
        issue = result.get("contract_issue") or result.get("validation_error")
        if issue:
            print(f"    ↳ {result['endpoint']}: {issue}")

    healthy = sum(1 for r in results if r["healthy"])
    total = len(results)
    print(f"\nSummary: {healthy}/{total} healthy")

    if args.dry_run:
        print("(dry-run — not writing to DB)")
        return

    # Write to MongoDB
    client = MongoClient(conn_str)
    col = client["system_monitor"]["api_health_checks"]

    # Replace per-endpoint: delete old docs for this endpoint, then insert fresh
    # This avoids Cosmos DB RU throttle on bulk delete of accumulated duplicates
    import time as _time
    for r in results:
        ep = r["endpoint"]
        try:
            # Delete in small batches to stay within Cosmos RU limits
            while col.delete_one({"endpoint": ep}).deleted_count > 0:
                pass  # Keep deleting until no more docs for this endpoint
        except Exception:
            _time.sleep(0.5)
            try:
                while col.delete_one({"endpoint": ep}).deleted_count > 0:
                    pass
            except Exception:
                pass
        col.insert_one(r)
        _time.sleep(0.1)  # Spread RU consumption

    client.close()
    print(f"Wrote {len(results)} health check results to system_monitor.api_health_checks")


if __name__ == "__main__":
    main()
