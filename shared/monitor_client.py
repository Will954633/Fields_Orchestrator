#!/usr/bin/env python3
"""
MonitorClient — Fields System Monitor
Writes process run records to the system_monitor MongoDB database.

Usage (drop-in for any script):

    from shared.monitor_client import MonitorClient

    monitor = MonitorClient(
        system="orchestrator",
        pipeline="orchestrator_daily",
        process_id="101",
        process_name="Scrape Target Suburbs"
    )
    monitor.start()
    try:
        # ... script logic ...
        monitor.log_metric("properties_scraped", 45)
        monitor.finish(status="success")
    except Exception as e:
        monitor.log_error(str(e), file=__file__)
        monitor.finish(status="failed")
        raise

Design principles:
- Non-blocking: DB writes happen synchronously but failures are swallowed
- Fallback: if DB unavailable, logs to /tmp/monitor_fallback.log
- Low overhead: single upsert on start, single upsert on finish
- Safe: never raises exceptions that could break the wrapped script
"""

import os
import json
import traceback
from datetime import datetime, timezone
from typing import Optional, Any
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_MONITOR_DB = "system_monitor"
PROCESS_RUNS_COLLECTION = "process_runs"
FALLBACK_LOG = "/tmp/monitor_fallback.log"

VALID_SYSTEMS = {"orchestrator", "website", "hypebeast"}
VALID_STATUSES = {"running", "success", "failed", "skipped"}


# ---------------------------------------------------------------------------
# MonitorClient
# ---------------------------------------------------------------------------

class MonitorClient:
    """
    Drop-in monitor wrapper for any Fields pipeline script.

    Args:
        system:       One of "orchestrator", "website", "hypebeast"
        pipeline:     E.g. "orchestrator_daily", "how_it_sold", "market_monitor"
        process_id:   Step ID e.g. "101", "15", "fetch_articles"
        process_name: Human-readable name e.g. "Scrape Target Suburbs"
        uri:          MongoDB URI (defaults to COSMOS_CONNECTION_STRING env var)
    """

    def __init__(
        self,
        system: str,
        pipeline: str,
        process_id: str,
        process_name: str,
        uri: Optional[str] = None,
    ):
        self.system = system
        self.pipeline = pipeline
        self.process_id = process_id
        self.process_name = process_name
        self._uri = uri or os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("MONGODB_URI") or self._uri_from_settings()
        self._run_id: Optional[ObjectId] = None
        self._client: Optional[MongoClient] = None
        self._errors: list = []
        self._warnings: list = []
        self._metrics: dict = {}
        self._started_at: Optional[datetime] = None

    @staticmethod
    def _uri_from_settings() -> Optional[str]:
        """Fallback: read URI from orchestrator settings.yaml (VM deployment)."""
        try:
            import yaml
            settings_path = os.path.join(
                os.path.dirname(__file__), "..", "config", "settings.yaml"
            )
            with open(os.path.abspath(settings_path)) as f:
                s = yaml.safe_load(f)
            return s.get("mongodb", {}).get("uri")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Record that this process has started. Call once at the top of the script."""
        self._started_at = datetime.now(timezone.utc)
        self._run_id = ObjectId()

        doc = {
            "_id": self._run_id,
            "system": self.system,
            "pipeline": self.pipeline,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "started_at": self._started_at,
            "finished_at": None,
            "status": "running",
            "duration_seconds": None,
            "error_count": 0,
            "warning_count": 0,
            "metrics": {},
            "errors": [],
        }
        self._write(PROCESS_RUNS_COLLECTION, "insert", doc)

    def finish(self, status: str = "success") -> None:
        """
        Record that this process has finished.

        Args:
            status: "success", "failed", or "skipped"
        """
        if status not in VALID_STATUSES:
            status = "failed"

        finished_at = datetime.now(timezone.utc)
        duration = (
            int((finished_at - self._started_at).total_seconds())
            if self._started_at
            else None
        )

        update = {
            "$set": {
                "finished_at": finished_at,
                "status": status,
                "duration_seconds": duration,
                "error_count": len(self._errors),
                "warning_count": len(self._warnings),
                "metrics": self._metrics,
                "errors": self._errors,
            }
        }
        self._write(PROCESS_RUNS_COLLECTION, "update", update, run_id=self._run_id)
        self._close()

    def log_metric(self, key: str, value: Any) -> None:
        """Record a numeric or string metric (e.g. properties_scraped=45)."""
        self._metrics[key] = value

    def log_warning(self, message: str, file: Optional[str] = None, line: Optional[int] = None, **extra) -> None:
        """Record a non-fatal warning."""
        entry = self._build_log_entry("warn", message, file, line, extra)
        self._warnings.append(entry)
        # Push incrementally so partial runs are visible
        self._push_log_entry(entry)

    def log_error(self, message: str, file: Optional[str] = None, line: Optional[int] = None, **extra) -> None:
        """Record a fatal or non-fatal error."""
        # Auto-capture current traceback if available
        tb = traceback.format_exc()
        if tb and tb.strip() != "NoneType: None":
            extra["traceback"] = tb
        entry = self._build_log_entry("error", message, file, line, extra)
        self._errors.append(entry)
        self._push_log_entry(entry)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_log_entry(
        self,
        level: str,
        message: str,
        file: Optional[str],
        line: Optional[int],
        extra: dict,
    ) -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc),
            "level": level,
            "message": message,
        }
        if file:
            entry["file"] = os.path.basename(file)
        if line:
            entry["line"] = line
        if extra:
            entry.update({k: v for k, v in extra.items() if v is not None})
        return entry

    def _push_log_entry(self, entry: dict) -> None:
        """Push a single log entry to the DB incrementally (best-effort)."""
        if self._run_id is None:
            return
        update = {"$push": {"errors": entry}}
        self._write(PROCESS_RUNS_COLLECTION, "update", update, run_id=self._run_id)

    def _get_collection(self, collection_name: str):
        """Return a MongoDB collection, creating client if needed."""
        if not self._uri:
            raise RuntimeError("No MongoDB URI available. Set COSMOS_CONNECTION_STRING env var.")
        if self._client is None:
            self._client = MongoClient(
                self._uri,
                serverSelectionTimeoutMS=10_000,
                socketTimeoutMS=15_000,
                connectTimeoutMS=10_000,
                retryWrites=False,  # Required for Cosmos DB
                maxPoolSize=2,
            )
        db = self._client[SYSTEM_MONITOR_DB]
        return db[collection_name]

    def _write(self, collection: str, operation: str, data: Any, run_id: Optional[ObjectId] = None) -> None:
        """
        Write to MongoDB. All failures are swallowed and logged to fallback file.
        This ensures MonitorClient never breaks the script that uses it.
        """
        try:
            col = self._get_collection(collection)
            if operation == "insert":
                col.insert_one(data)
            elif operation == "update" and run_id is not None:
                col.update_one({"_id": run_id}, data)
        except Exception as e:
            self._write_fallback(operation, str(e), data)

    def _write_fallback(self, operation: str, error: str, data: Any) -> None:
        """Write to local fallback log if MongoDB is unavailable."""
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "operation": operation,
                "error": error,
                "system": self.system,
                "pipeline": self.pipeline,
                "process_id": self.process_id,
            }
            with open(FALLBACK_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Truly last resort — swallow silently

    def _close(self) -> None:
        """Close MongoDB connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


# ---------------------------------------------------------------------------
# Email alert hook (v1 design — inactive, ready for Phase 5)
# ---------------------------------------------------------------------------

def send_alert_email(subject: str, body: str) -> None:
    """
    Placeholder for email alerting. Not active in v1.
    Hook points:
      - Called after monitor.finish(status="failed")
      - Called after critical API health check failure
    To activate: implement SMTP send here and set ALERT_EMAIL env var.
    """
    alert_email = os.getenv("ALERT_EMAIL")
    if not alert_email:
        return
    # TODO: implement SMTP send (Phase 5)
    pass


# ---------------------------------------------------------------------------
# CLI test (run directly to verify DB connectivity)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing MonitorClient...")
    print(f"  URI set: {'yes' if os.getenv('COSMOS_CONNECTION_STRING') else 'NO — set COSMOS_CONNECTION_STRING'}")

    monitor = MonitorClient(
        system="orchestrator",
        pipeline="test",
        process_id="test-001",
        process_name="MonitorClient Test Run",
    )

    monitor.start()
    print("  start() — OK")

    monitor.log_metric("test_metric", 42)
    monitor.log_warning("This is a test warning", file=__file__, line=1)
    print("  log_metric + log_warning — OK")

    monitor.finish(status="success")
    print("  finish() — OK")
    print(f"\nCheck system_monitor.process_runs in Cosmos DB for run_id: {monitor._run_id}")
