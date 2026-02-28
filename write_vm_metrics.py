#!/usr/bin/env python3
"""
write_vm_metrics.py
Collects CPU, memory, disk, and load metrics from the VM and writes
a snapshot to MongoDB system_monitor.vm_metrics.

Run every minute via cron:
  * * * * * /home/fields/.venv/bin/python /home/fields/Fields_Orchestrator/write_vm_metrics.py >> /tmp/vm_metrics.log 2>&1
"""

import os
import time
from datetime import datetime, timezone

import psutil
from pymongo import MongoClient

COSMOS_CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING")
if not COSMOS_CONNECTION_STRING:
    raise RuntimeError("COSMOS_CONNECTION_STRING env var is not set")

client = MongoClient(
    COSMOS_CONNECTION_STRING,
    serverSelectionTimeoutMS=10000,
    socketTimeoutMS=15000,
    retryWrites=False,
)
db = client["system_monitor"]
col = db["vm_metrics"]

# Collect metrics
cpu_percent = psutil.cpu_percent(interval=1)
cpu_count = psutil.cpu_count(logical=True)

mem = psutil.virtual_memory()
memory_percent = mem.percent
memory_used_gb = round(mem.used / 1e9, 2)
memory_total_gb = round(mem.total / 1e9, 2)

disk = psutil.disk_usage("/")
disk_root_used_gb = round(disk.used / 1e9, 2)
disk_root_total_gb = round(disk.total / 1e9, 2)
disk_root_percent = disk.percent

try:
    load_avg_1m, load_avg_5m, load_avg_15m = [round(x, 2) for x in os.getloadavg()]
except AttributeError:
    # Windows doesn't have getloadavg
    load_avg_1m = load_avg_5m = load_avg_15m = None

uptime_hours = round((time.time() - psutil.boot_time()) / 3600, 2)

now = datetime.now(timezone.utc)

doc = {
    "recorded_at": now,
    "cpu_percent": cpu_percent,
    "cpu_count": cpu_count,
    "memory_percent": memory_percent,
    "memory_used_gb": memory_used_gb,
    "memory_total_gb": memory_total_gb,
    "disk_root_used_gb": disk_root_used_gb,
    "disk_root_total_gb": disk_root_total_gb,
    "disk_root_percent": disk_root_percent,
    "load_avg_1m": load_avg_1m,
    "load_avg_5m": load_avg_5m,
    "load_avg_15m": load_avg_15m,
    "uptime_hours": uptime_hours,
}

col.insert_one(doc)

# Trim: keep only the 60 most recent docs (Cosmos DB doesn't index recorded_at by default,
# so we sort by _id which is always indexed, then delete everything older than the 60th doc).
recent = list(col.find({}, {"_id": 1}).sort("_id", -1).limit(61))
if len(recent) == 61:
    cutoff_id = recent[-1]["_id"]
    result = col.delete_many({"_id": {"$lt": cutoff_id}})
else:
    result = type("r", (), {"deleted_count": 0})()

print(
    f"[{now.isoformat()}] CPU={cpu_percent}% MEM={memory_percent}% "
    f"DISK={disk_root_percent}% LOAD={load_avg_1m} "
    f"trimmed={result.deleted_count}"
)
