#!/usr/bin/env python3
"""Comprehensive Facebook Ads data dump from MongoDB."""

import os
import sys
import json
from pymongo import MongoClient
from datetime import datetime, timedelta

uri = os.environ["COSMOS_CONNECTION_STRING"]
client = MongoClient(uri)
db = client["system_monitor"]


def pretty(obj):
    if isinstance(obj, dict):
        return {k: pretty(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [pretty(i) for i in obj]
    elif hasattr(obj, "__class__") and obj.__class__.__name__ in ("ObjectId",):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def section(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


# ---- AD PROFILES ----
section("AD PROFILES (all 69 documents)")
profiles = list(db.ad_profiles.find({}))
print(f"Total: {len(profiles)}\n")
for p in profiles:
    print(json.dumps(pretty(p), indent=2))
    print("-" * 40)

# ---- AD DAILY METRICS ----
section("AD DAILY METRICS (last 14 days, sorted by date desc)")
cutoff = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
daily = list(db.ad_daily_metrics.find({"date": {"$gte": cutoff}}).sort("date", -1))
print(f"Total (last 14d): {len(daily)}\n")
for d in daily:
    print(json.dumps(pretty(d), indent=2))
    print("-" * 40)

# ---- AD EXPERIMENTS ----
section("AD EXPERIMENTS (all documents)")
experiments = list(db.ad_experiments.find({}))
print(f"Total: {len(experiments)}\n")
for e in experiments:
    print(json.dumps(pretty(e), indent=2))
    print("-" * 40)

# ---- AD DECISIONS ----
section("AD DECISIONS (last 20, sorted by created_at desc)")
decisions = list(db.ad_decisions.find({}).sort("created_at", -1).limit(20))
print(f"Total returned: {len(decisions)}\n")
for d in decisions:
    print(json.dumps(pretty(d), indent=2))
    print("-" * 40)

# ---- AD DEMOGRAPHICS ----
section("AD DEMOGRAPHICS (latest 100 docs)")
demographics = list(db.ad_demographics.find({}).sort("date", -1).limit(100))
print(f"Total returned: {len(demographics)}\n")
for d in demographics:
    print(json.dumps(pretty(d), indent=2))
    print("-" * 40)

# ---- AD PLACEMENTS ----
section("AD PLACEMENTS (latest 100 docs)")
placements = list(db.ad_placements.find({}).sort("date", -1).limit(100))
print(f"Total returned: {len(placements)}\n")
for p in placements:
    print(json.dumps(pretty(p), indent=2))
    print("-" * 40)

# ---- COLLECTION STATS ----
section("COLLECTION STATS")
for coll in ["ad_profiles", "ad_daily_metrics", "ad_experiments", "ad_decisions", "ad_demographics", "ad_placements"]:
    count = db[coll].count_documents({})
    print(f"  {coll}: {count} total documents")

client.close()
