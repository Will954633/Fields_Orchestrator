"""Tiny helper invoked by refresh-ops-state.py — keeps quoting sane."""
import os
import sys

try:
    from pymongo import MongoClient
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    c = MongoClient(uri, serverSelectionTimeoutMS=5000)
    parts = []
    for d in ["Gold_Coast", "property_data", "system_monitor"]:
        try:
            total = sum(
                c[d][n].estimated_document_count() for n in c[d].list_collection_names()
            )
            parts.append(f"{d}:{total}")
        except Exception as e:
            parts.append(f"{d}:err({type(e).__name__})")
    print("|".join(parts))
except Exception as e:
    print(f"probe-error:{type(e).__name__}:{e}", file=sys.stderr)
    sys.exit(1)
