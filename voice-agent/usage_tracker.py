"""
Usage Tracker for the Fields Chat Agent.

Logs every AI model call (Claude CLI, Claude SDK, GPT API) to MongoDB
with enough detail to diagnose session budget consumption patterns.

Collection: system_monitor.chat_agent_usage

Each document represents a single "interaction" — one user message and
all the AI calls it triggered. Sub-calls (router, converse, workers)
are nested inside the interaction document.

Also maintains a daily rollup in system_monitor.chat_agent_usage_daily
for quick dashboard queries.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from contextlib import contextmanager

log = logging.getLogger("voice-agent.usage")

AEST = timezone(timedelta(hours=10))
ORCHESTRATOR_DIR = "/home/fields/Fields_Orchestrator"
USAGE_COLL = "chat_agent_usage"
DAILY_COLL = "chat_agent_usage_daily"

# ---------------------------------------------------------------------------
# Lazy DB access
# ---------------------------------------------------------------------------

_db_client = None


def _get_sm():
    """Get system_monitor database (lazy init)."""
    global _db_client
    if _db_client is None:
        sys.path.insert(0, ORCHESTRATOR_DIR)
        from shared.db import get_client
        _db_client = get_client()
    return _db_client["system_monitor"]


# ---------------------------------------------------------------------------
# Call record — one AI model invocation
# ---------------------------------------------------------------------------

class CallRecord:
    """Tracks a single AI model call (router, converse, worker, etc.)."""

    def __init__(
        self,
        call_type: str,          # "haiku_router", "opus_converse", "opus_email",
                                 # "opus_full", "opus_worker", "gpt_converse",
                                 # "gpt_full", "gpt_worker"
        model: str,              # "haiku", "opus", "gpt-5.4", "gpt-5.4-mini"
        trigger: str,            # What caused this call: "auto_route", "model_lock_opus",
                                 # "router_bypass", "task_spawn", "session_resume"
        task_category: str = "", # "email", "dev", "kb_search", "accounting",
                                 # "conversation", "ops_check", "memory", ""
        task_title: str = "",    # Human-readable task title (for workers)
        parent_interaction_id: str = "",
    ):
        self.call_type = call_type
        self.model = model
        self.trigger = trigger
        self.task_category = task_category
        self.task_title = task_title
        self.parent_interaction_id = parent_interaction_id

        self.started_at = datetime.now(AEST)
        self.start_time = time.perf_counter()
        self.finished_at: Optional[datetime] = None
        self.duration_seconds: float = 0.0

        self.turns: int = 0             # SDK turns or 1 for CLI
        self.tool_calls: list[str] = [] # Tool names used (for SDK calls)
        self.input_chars: int = 0       # Approximate input size
        self.output_chars: int = 0      # Response size
        self.status: str = "running"    # "running", "completed", "failed", "timeout"
        self.error: str = ""
        self.session_id: Optional[str] = None
        self.session_resumed: bool = False

    def finish(self, status: str = "completed", output_chars: int = 0,
               turns: int = 0, error: str = "", session_id: str = None):
        self.finished_at = datetime.now(AEST)
        self.duration_seconds = time.perf_counter() - self.start_time
        self.status = status
        if output_chars:
            self.output_chars = output_chars
        if turns:
            self.turns = turns
        if error:
            self.error = error[:500]
        if session_id:
            self.session_id = session_id

    def add_tool_call(self, tool_name: str):
        self.tool_calls.append(tool_name)
        self.turns += 1

    def to_dict(self) -> dict:
        return {
            "call_type": self.call_type,
            "model": self.model,
            "trigger": self.trigger,
            "task_category": self.task_category,
            "task_title": self.task_title,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": round(self.duration_seconds, 2),
            "turns": self.turns,
            "tool_calls": self.tool_calls[-50:],  # Cap at 50
            "tool_call_count": len(self.tool_calls),
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
            "status": self.status,
            "error": self.error,
            "session_id": self.session_id,
            "session_resumed": self.session_resumed,
        }


# ---------------------------------------------------------------------------
# Interaction record — one user message and all calls it triggered
# ---------------------------------------------------------------------------

class InteractionRecord:
    """Tracks everything triggered by a single user message."""

    def __init__(
        self,
        user_text: str,
        source: str,           # "voice", "chat", "chat_stream"
        model_lock: str,       # "auto", "opus", "haiku"
    ):
        self.interaction_id = _make_interaction_id()
        self.user_text = user_text[:500]  # Truncate for storage
        self.source = source
        self.model_lock_at_start = model_lock

        self.started_at = datetime.now(AEST)
        self.start_time = time.perf_counter()
        self.finished_at: Optional[datetime] = None
        self.duration_seconds: float = 0.0

        self.route_mode: str = ""       # "direct", "converse", "email", "task"
        self.route_path: str = ""       # More detailed path: "opus_lock_dev_task",
                                        # "opus_lock_email", "router_bypass", "auto_route_task"
        self.calls: list[dict] = []     # CallRecord dicts
        self.task_ids: list[str] = []   # Background tasks spawned
        self.reply_chars: int = 0

        # Classification for analysis
        self.request_category: str = "" # "email", "dev", "conversation", "ops", "accounting", etc.

    def add_call(self, call: CallRecord):
        self.calls.append(call.to_dict())

    def finish(self, route_mode: str = "", route_path: str = "",
               reply_chars: int = 0, request_category: str = ""):
        self.finished_at = datetime.now(AEST)
        self.duration_seconds = time.perf_counter() - self.start_time
        if route_mode:
            self.route_mode = route_mode
        if route_path:
            self.route_path = route_path
        if reply_chars:
            self.reply_chars = reply_chars
        if request_category:
            self.request_category = request_category

    def to_dict(self) -> dict:
        # Compute aggregates
        total_turns = sum(c.get("turns", 0) for c in self.calls)
        total_tool_calls = sum(c.get("tool_call_count", 0) for c in self.calls)
        models_used = list(set(c.get("model", "") for c in self.calls))
        call_types = [c.get("call_type", "") for c in self.calls]

        return {
            "_id": self.interaction_id,
            "user_text": self.user_text,
            "source": self.source,
            "model_lock": self.model_lock_at_start,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": round(self.duration_seconds, 2),
            "route_mode": self.route_mode,
            "route_path": self.route_path,
            "request_category": self.request_category,
            "reply_chars": self.reply_chars,
            "calls": self.calls,
            "call_count": len(self.calls),
            "total_turns": total_turns,
            "total_tool_calls": total_tool_calls,
            "models_used": models_used,
            "call_types": call_types,
            "task_ids": self.task_ids,
            "date": self.started_at.strftime("%Y-%m-%d"),
            "hour": self.started_at.hour,
        }


def _make_interaction_id() -> str:
    ts = datetime.now(AEST).strftime("%Y%m%d_%H%M%S")
    import random
    suffix = random.randint(1000, 9999)
    return f"ix_{ts}_{suffix}"


# ---------------------------------------------------------------------------
# Classify user request
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS = None


def _get_category_patterns():
    global _CATEGORY_PATTERNS
    if _CATEGORY_PATTERNS is None:
        import re
        _CATEGORY_PATTERNS = [
            ("email", re.compile(
                r"\b(email|emails|inbox|mail|reply to|draft|send to|recipient|outlook)\b", re.I)),
            ("dev", re.compile(
                r"\b(build|code|script|fix|debug|implement|refactor|deploy|push|commit|test|bug)\b", re.I)),
            ("ops", re.compile(
                r"\b(pipeline|orchestrator|watchdog|service|systemctl|coverage|scraper|cron)\b", re.I)),
            ("accounting", re.compile(
                r"\b(accounting|ledger|tax|FY\d{2}|rossmax|maxamra|expense|transaction|bank)\b", re.I)),
            ("kb_search", re.compile(
                r"\b(knowledge base|KB|search.*docs|strategy docs|meeting notes|books?.*about)\b", re.I)),
            ("memory", re.compile(
                r"\b(remember|memory|save.*memory|conversation.*memory|persist)\b", re.I)),
            ("analytics", re.compile(
                r"\b(analytics|posthog|metrics|traffic|conversion|visitor|page ?view)\b", re.I)),
            ("ads", re.compile(
                r"\b(facebook|google ads|campaign|ad set|creative|audience|budget|ROAS)\b", re.I)),
            ("content", re.compile(
                r"\b(article|blog|market pulse|editorial|ghost|publish|draft.*article)\b", re.I)),
            ("valuation", re.compile(
                r"\b(valuation|comparable|comp|price estimate|what.*worth)\b", re.I)),
            ("website", re.compile(
                r"\b(website|netlify|frontend|component|page.*design|CSS|layout)\b", re.I)),
        ]
    return _CATEGORY_PATTERNS


def classify_request(user_text: str) -> str:
    """Classify user text into a request category."""
    for category, pattern in _get_category_patterns():
        if pattern.search(user_text):
            return category
    return "conversation"


# ---------------------------------------------------------------------------
# Classify task from title/prompt
# ---------------------------------------------------------------------------

def classify_task(title: str, prompt: str = "") -> str:
    """Classify a spawned task into a category from its title and prompt."""
    combined = f"{title} {prompt[:200]}".lower()

    if any(w in combined for w in ("email", "inbox", "mail", "reply", "draft")):
        return "email"
    if any(w in combined for w in ("knowledge base", "kb", "search-kb", "search kb")):
        return "kb_search"
    if any(w in combined for w in ("accounting", "ledger", "tax", "rossmax", "maxamra", "fy2")):
        return "accounting"
    if any(w in combined for w in ("memory", "persist", "remember", "save memory")):
        return "memory"
    if any(w in combined for w in ("pipeline", "orchestrator", "coverage", "service", "watchdog")):
        return "ops"
    if any(w in combined for w in ("build", "code", "script", "fix", "debug", "implement",
                                    "refactor", "deploy", "feature", "bug", "test")):
        return "dev"
    if any(w in combined for w in ("article", "publish", "ghost", "editorial", "market pulse")):
        return "content"
    if any(w in combined for w in ("facebook", "google ads", "campaign", "ad set")):
        return "ads"
    if any(w in combined for w in ("website", "netlify", "frontend", "component")):
        return "website"
    return "general"


# ---------------------------------------------------------------------------
# Persistence — write to MongoDB
# ---------------------------------------------------------------------------

def save_interaction(interaction: InteractionRecord):
    """Save a completed interaction to MongoDB. Non-blocking, best-effort."""
    try:
        sm = _get_sm()
        doc = interaction.to_dict()
        sm[USAGE_COLL].insert_one(doc)

        # Update daily rollup
        _update_daily_rollup(doc)
    except Exception as e:
        log.warning(f"Usage tracking save failed: {e}")


def save_worker_call(call: CallRecord):
    """Save a standalone worker call (background tasks that outlive the interaction).
    Appends to the daily rollup and stores as a standalone usage doc."""
    try:
        sm = _get_sm()
        doc = {
            "_id": f"worker_{call.parent_interaction_id}_{int(time.time())}",
            "type": "worker_standalone",
            "call": call.to_dict(),
            "date": datetime.now(AEST).strftime("%Y-%m-%d"),
            "hour": datetime.now(AEST).hour,
            "saved_at": datetime.now(AEST).isoformat(),
        }
        sm[USAGE_COLL].insert_one(doc)

        # Update daily rollup for the worker
        _update_daily_rollup_for_call(call)
    except Exception as e:
        log.warning(f"Worker usage tracking save failed: {e}")


def _update_daily_rollup(interaction_doc: dict):
    """Update the daily rollup document with this interaction's data."""
    try:
        sm = _get_sm()
        date = interaction_doc["date"]
        call_count = interaction_doc.get("call_count", 0)
        total_turns = interaction_doc.get("total_turns", 0)
        duration = interaction_doc.get("duration_seconds", 0)
        category = interaction_doc.get("request_category", "unknown")
        route_mode = interaction_doc.get("route_mode", "unknown")
        models = interaction_doc.get("models_used", [])

        update = {
            "$inc": {
                "total_interactions": 1,
                "total_calls": call_count,
                "total_turns": total_turns,
                "total_duration_seconds": duration,
                f"by_category.{category}.interactions": 1,
                f"by_category.{category}.calls": call_count,
                f"by_category.{category}.turns": total_turns,
                f"by_category.{category}.duration_seconds": duration,
                f"by_mode.{route_mode}.interactions": 1,
                f"by_mode.{route_mode}.calls": call_count,
                f"by_hour.h{interaction_doc.get('hour', 0):02d}": 1,
            },
            "$set": {
                "updated_at": datetime.now(AEST).isoformat(),
            },
            "$setOnInsert": {
                "created_at": datetime.now(AEST).isoformat(),
            },
        }

        for model in models:
            safe_model = model.replace(".", "_").replace("-", "_")
            update["$inc"][f"by_model.{safe_model}.calls"] = call_count

        # Count Opus calls specifically (the expensive ones)
        opus_calls = sum(
            1 for c in interaction_doc.get("calls", [])
            if c.get("model") in ("opus", "claude-opus")
        )
        haiku_calls = sum(
            1 for c in interaction_doc.get("calls", [])
            if c.get("model") in ("haiku", "claude-haiku")
        )
        if opus_calls:
            update["$inc"]["opus_calls"] = opus_calls
        if haiku_calls:
            update["$inc"]["haiku_calls"] = haiku_calls

        # Count task spawns
        task_count = len(interaction_doc.get("task_ids", []))
        if task_count:
            update["$inc"]["tasks_spawned"] = task_count

        sm[DAILY_COLL].update_one(
            {"_id": f"daily_{date}"},
            update,
            upsert=True,
        )
    except Exception as e:
        log.warning(f"Daily rollup update failed: {e}")


def _update_daily_rollup_for_call(call: CallRecord):
    """Update daily rollup for a standalone worker call."""
    try:
        sm = _get_sm()
        date = datetime.now(AEST).strftime("%Y-%m-%d")
        hour = datetime.now(AEST).hour
        category = call.task_category or "general"

        update = {
            "$inc": {
                "total_calls": 1,
                "total_turns": call.turns,
                "total_duration_seconds": call.duration_seconds,
                f"by_category.{category}.calls": 1,
                f"by_category.{category}.turns": call.turns,
                f"by_category.{category}.duration_seconds": call.duration_seconds,
                f"by_hour.h{hour:02d}": 1,
                "worker_calls": 1,
                f"worker_by_category.{category}.calls": 1,
                f"worker_by_category.{category}.turns": call.turns,
                f"worker_by_category.{category}.duration_seconds": call.duration_seconds,
            },
            "$set": {"updated_at": datetime.now(AEST).isoformat()},
            "$setOnInsert": {"created_at": datetime.now(AEST).isoformat()},
        }

        safe_model = call.model.replace(".", "_").replace("-", "_")
        update["$inc"][f"by_model.{safe_model}.calls"] = 1

        if call.model in ("opus", "claude-opus"):
            update["$inc"]["opus_calls"] = 1

        sm[DAILY_COLL].update_one(
            {"_id": f"daily_{date}"},
            update,
            upsert=True,
        )
    except Exception as e:
        log.warning(f"Worker daily rollup failed: {e}")


# ---------------------------------------------------------------------------
# Query helpers — for the /api/usage endpoint
# ---------------------------------------------------------------------------

def get_daily_summary(date: str = None) -> dict:
    """Get usage summary for a given date (default: today)."""
    if not date:
        date = datetime.now(AEST).strftime("%Y-%m-%d")
    try:
        sm = _get_sm()
        doc = sm[DAILY_COLL].find_one({"_id": f"daily_{date}"})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc or {"_id": f"daily_{date}", "total_interactions": 0, "total_calls": 0}
    except Exception as e:
        log.warning(f"Daily summary query failed: {e}")
        return {"error": str(e)}


def get_daily_summaries(days: int = 7) -> list[dict]:
    """Get usage summaries for the last N days."""
    results = []
    for i in range(days):
        date = (datetime.now(AEST) - timedelta(days=i)).strftime("%Y-%m-%d")
        summary = get_daily_summary(date)
        results.append(summary)
    return results


def get_recent_interactions(limit: int = 50, category: str = None,
                            date: str = None) -> list[dict]:
    """Get recent interaction records with optional filters."""
    try:
        sm = _get_sm()
        # Use _id prefix filter instead of $exists (Cosmos-friendly)
        query_filter = {"_id": {"$regex": "^ix_"}}
        if category:
            query_filter["request_category"] = category
        if date:
            query_filter["date"] = date

        # Fetch extra and sort in Python (Cosmos has no index on started_at)
        docs = list(sm[USAGE_COLL].find(
            query_filter,
            {"calls.tool_calls": 0},
        ).limit(limit + 20))

        docs.sort(key=lambda d: d.get("started_at", ""), reverse=True)
        docs = docs[:limit]

        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs
    except Exception as e:
        log.warning(f"Recent interactions query failed: {e}")
        return []


def get_heavy_consumers(date: str = None, limit: int = 20) -> list[dict]:
    """Get the interactions with the most turns/calls for a given day.
    Useful for identifying what's burning session budget."""
    if not date:
        date = datetime.now(AEST).strftime("%Y-%m-%d")
    try:
        sm = _get_sm()
        docs = list(sm[USAGE_COLL].find(
            {"date": date, "_id": {"$regex": "^ix_"}},
            {"calls.tool_calls": 0},
        ).limit(limit + 20))

        # Sort by total_turns descending in Python
        docs.sort(key=lambda d: d.get("total_turns", 0), reverse=True)
        docs = docs[:limit]

        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs
    except Exception as e:
        log.warning(f"Heavy consumers query failed: {e}")
        return []


def get_category_breakdown(date: str = None) -> dict:
    """Get per-category breakdown for a day."""
    summary = get_daily_summary(date)
    return summary.get("by_category", {})


def get_worker_breakdown(date: str = None) -> dict:
    """Get per-category worker breakdown for a day."""
    summary = get_daily_summary(date)
    return summary.get("worker_by_category", {})
