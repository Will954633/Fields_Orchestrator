#!/usr/bin/env python3
"""
One-shot script: clear old floor plan data and rerun step 106 with gpt-5.4.
Run AFTER the nightly pipeline finishes to avoid RU contention.

Usage:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    python3 /home/fields/Fields_Orchestrator/scripts/rerun_floor_plans.py
"""
import os
import re
import subprocess
import sys
import time
from pymongo import MongoClient
from pymongo.errors import OperationFailure

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE = "Gold_Coast"
FIELDS_TO_CLEAR = ["ollama_floor_plan_analysis", "floor_plan_analysis"]


def safe_op(fn, retries=15, label="op"):
    for attempt in range(retries):
        try:
            return fn()
        except OperationFailure as e:
            if e.code == 16500:
                m = re.search(r"RetryAfterMs=(\d+)", str(e))
                wait = int(m.group(1)) / 1000 + 1.0 if m else (attempt + 1) * 3
                print(f"  [{label}] 429 — waiting {wait:.1f}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Max retries exceeded for {label}")


def main():
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(uri)
    db = client[DATABASE]

    print("=" * 60)
    print("FLOOR PLAN RERUN — Clear old data + reprocess with gpt-5.4")
    print("=" * 60)

    total_cleared = 0
    for suburb in TARGET_SUBURBS:
        print(f"\n--- {suburb} ---")
        time.sleep(3)

        # Build query for docs with any floor plan field
        or_clauses = [{f: {"$exists": True}} for f in FIELDS_TO_CLEAR]
        docs = safe_op(
            lambda s=suburb: list(db[s].find({"$or": or_clauses}, {"_id": 1})),
            label=f"{suburb}.find",
        )
        print(f"  Found {len(docs)} documents with floor plan data")

        for i, doc in enumerate(docs):
            time.sleep(1.5)
            unset = {f: "" for f in FIELDS_TO_CLEAR}
            safe_op(
                lambda d=doc, s=suburb: db[s].update_one(
                    {"_id": d["_id"]}, {"$unset": unset}
                ),
                label=f"{suburb}.clear[{i}]",
            )
            total_cleared += 1
            if (i + 1) % 10 == 0:
                print(f"  Cleared {i+1}/{len(docs)}")

        print(f"  Done: {len(docs)} cleared")

    print(f"\nTotal cleared: {total_cleared}")
    client.close()

    # Now run step 106
    print("\n" + "=" * 60)
    print("Running step 106 with updated model...")
    print("=" * 60)
    step106 = os.path.join(
        os.path.dirname(__file__), "step106_floor_plan.py"
    )
    result = subprocess.run(
        [sys.executable, step106],
        env={**os.environ},
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
