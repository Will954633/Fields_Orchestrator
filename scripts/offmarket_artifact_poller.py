#!/usr/bin/env python3
"""On-demand poller for V5 off-market artifacts (valuation-report, market-update).

Mirrors scripts/offmarket_report_poller.py. Claims queued rows from
`system_monitor.offmarket_artifact_requests` and runs the deterministic
generators via publish_offmarket_artifacts.publish(), which write to blob
(/data/blobs, served by nginx). The website's offmarket-artifact.mjs enqueues on
a cache miss and polls status; the pre-warm batch keeps most addresses warm.

Rule-7 self-monitored: heartbeats on the "Off-Market V5 Artifacts" job and
RAISES if it claimed work but published nothing (7b).

Run via systemd: fields-offmarket-artifact-poller.service
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path("/home/fields/Fields_Orchestrator")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from pymongo import MongoClient  # noqa: E402

from scripts.job_status import job_run  # noqa: E402
from scripts.publish_offmarket_artifacts import publish, artifact_fresh  # noqa: E402

POLL_INTERVAL = 15
STALE_CLAIM_SECONDS = 900
_KEEP = ("kind", "ok", "html_url", "cover_url", "cards_url", "aerial_url", "error", "declined")


def get_client() -> MongoClient:
    uri = os.environ["COSMOS_CONNECTION_STRING"]
    return MongoClient(uri, retryWrites=False, serverSelectionTimeoutMS=30000)


def poll_once(client: MongoClient) -> dict:
    q = client["system_monitor"]["offmarket_artifact_requests"]

    # Reclaim crashed jobs (Cosmos returns naive datetimes → compare in UTC).
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_CLAIM_SECONDS)
    for stuck in q.find({"status": "processing"}):
        started = stuck.get("started_at")
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started and started < cutoff:
            q.update_one({"_id": stuck["_id"]}, {"$set": {"status": "pending"}})

    req = q.find_one_and_update(
        {"status": "pending"},
        {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc)}},
        sort=[("requested_at", 1)],
    )
    if not req:
        return {"claimed": 0, "succeeded": 0, "failed": 0}

    slug = req.get("slug")
    kind = req.get("kind", "both")
    # Rebuild-on-stale: the website enqueues on every page load (it can't tell a
    # stale blob from a fresh one), so decide here. Rebuild only the kinds whose
    # blob is missing or older than the generator — a request for an already-fresh
    # artifact costs one stat() and no build, which is what makes always-enqueue
    # cheap enough to guarantee a viewed page self-heals within ~10s of a copy change.
    requested = ["market-update", "valuation-report"] if kind == "both" else [kind]
    stale = [k for k in requested if not artifact_fresh(slug, k)]
    if not stale:
        q.update_one(
            {"_id": req["_id"]},
            {"$set": {
                "status": "completed", "fresh": True,
                "finished_at": datetime.now(timezone.utc), "error": None,
            }},
        )
        return {"claimed": 1, "succeeded": 1, "failed": 0, "fresh": 1}
    rebuild_kind = "both" if len(stale) == 2 else stale[0]
    try:
        results = publish(slug, rebuild_kind, verbose=False)
        ok = bool(results) and all(r.get("ok") for r in results)
        declined = any(r.get("declined") for r in results)
        q.update_one(
            {"_id": req["_id"]},
            {"$set": {
                "status": "completed" if ok else ("declined" if declined else "failed"),
                "results": [{k: r.get(k) for k in _KEEP if k in r} for r in results],
                "finished_at": datetime.now(timezone.utc),
                "error": None if ok else "; ".join(r.get("error", "") for r in results if not r.get("ok")),
            }},
        )
        return {"claimed": 1, "succeeded": int(ok), "failed": int(not ok)}
    except Exception as exc:  # noqa: BLE001
        q.update_one(
            {"_id": req["_id"]},
            {"$set": {"status": "failed", "error": str(exc)[:400], "finished_at": datetime.now(timezone.utc)}},
        )
        return {"claimed": 1, "succeeded": 0, "failed": 1}


def main() -> None:
    client = get_client()
    while True:
        try:
            counters = poll_once(client)
        except Exception as exc:  # noqa: BLE001 — never let the daemon die on a transient DB error
            print(f"poll_once error: {exc}", file=sys.stderr)
            time.sleep(POLL_INTERVAL)
            continue
        if counters["claimed"]:
            with job_run("offmarket_artifact_poller", cadence_hours=24, title="Off-Market V5 Artifacts") as beat:
                beat.metrics = counters
                if counters["succeeded"] == 0:  # Rule 7b
                    raise RuntimeError(
                        f"claimed {counters['claimed']} request(s) and published none — "
                        f"see offmarket_artifact_requests.error"
                    )
                beat.detail = f"{counters['succeeded']} artifact set(s) published"
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
