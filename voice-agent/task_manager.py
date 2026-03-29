"""
Task Manager for the Fields Voice Agent.

Manages background Claude Code (Opus) workers via the Agent SDK.
Up to 3 concurrent workers, tracked in MongoDB with heartbeat.
"""

import asyncio
import json
import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

log = logging.getLogger("voice-agent.tasks")

AEST = timezone(timedelta(hours=10))
ORCHESTRATOR_DIR = "/home/fields/Fields_Orchestrator"
MEMORY_DIR = "/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory"

MAX_CONCURRENT_WORKERS = 3
WORKER_TIMEOUT_SECONDS = 1200  # 20 minutes
HEARTBEAT_INTERVAL_SECONDS = 15

TASK_COLL = "voice_agent_tasks"


def _now_iso() -> str:
    return datetime.now(AEST).isoformat()


def _task_id(title: str) -> str:
    ts = datetime.now(AEST).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower().strip())[:40].strip("_")
    return f"task_{ts}_{slug}"


def _load_context_docs() -> str:
    """Load dynamic context for worker system prompt.
    NOTE: CLAUDE.md is loaded automatically by the Agent SDK via cwd."""
    sections = []

    memory_md = Path(MEMORY_DIR) / "MEMORY.md"
    if memory_md.exists():
        sections.append(f"=== PERSISTENT MEMORY ===\n{memory_md.read_text()}")

    memory_dir = Path(MEMORY_DIR)
    if memory_dir.exists():
        parts = []
        for f in sorted(memory_dir.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            content = f.read_text().strip()
            if content:
                parts.append(f"### {f.stem}\n{content}")
        if parts:
            sections.append(f"=== MEMORY FILES ===\n" + "\n\n".join(parts))

    ops = Path(ORCHESTRATOR_DIR) / "OPS_STATUS.md"
    if ops.exists():
        sections.append(f"=== LIVE OPS STATUS ===\n{ops.read_text()}")

    return "\n\n".join(sections)


class TaskManager:
    """Manages background Claude Code worker tasks."""

    def __init__(self, db_client, sse_broadcaster):
        self._sm = db_client["system_monitor"]
        self._sse = sse_broadcaster
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)
        self._active_tasks: dict[str, asyncio.Event] = {}  # cancel events per task
        self._cleanup_orphans()

    def _cleanup_orphans(self):
        """Mark any running tasks as failed on startup (server restarted)."""
        result = self._sm[TASK_COLL].update_many(
            {"status": {"$in": ["running", "queued"]}},
            {"$set": {
                "status": "failed",
                "error_text": "Server restarted during execution",
                "finished_at": _now_iso(),
            }},
        )
        if result.modified_count:
            log.warning(f"Marked {result.modified_count} orphaned task(s) as failed")

    def spawn_task(self, title: str, prompt: str, user_message: str,
                   model: str = "opus") -> str:
        """Create a task and launch a background worker. Returns task_id."""
        task_id = _task_id(title)
        doc = {
            "_id": task_id,
            "title": title,
            "status": "queued",
            "prompt": prompt,
            "user_message": user_message,
            "model": model,
            "pid": None,
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "last_heartbeat_at": None,
            "result_summary": None,
            "result_full": None,
            "error_text": None,
            "notified": False,
        }
        self._sm[TASK_COLL].insert_one(doc)
        log.info(f"Task created: {task_id} — {title} (model: {model})")

        self._sse.broadcast("task_started", {
            "task_id": task_id,
            "title": title,
            "status": "queued",
        })

        # Fire and forget — the worker coroutine manages its own lifecycle
        asyncio.get_event_loop().create_task(self._run_worker(task_id, prompt, model))
        return task_id

    async def _run_worker(self, task_id: str, prompt: str, model: str = "opus"):
        """Worker coroutine: acquire semaphore, run worker, track lifecycle."""
        async with self._semaphore:
            await self._execute(task_id, prompt)

    async def _execute(self, task_id: str, prompt: str):
        """Execute Claude Code worker via Agent SDK with heartbeat tracking."""
        context = _load_context_docs()
        worker_system = (
            f"You are a background worker agent for Fields Estate. "
            f"Complete the task below thoroughly, then provide a clear summary of what you did. "
            f"Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}\n\n"
            f"KNOWLEDGE BASE: You have access to a 1,644-document knowledge base with 7,000+ chunks "
            f"covering books, strategy docs, marketing plans, meeting notes, code, financials, and operations. "
            f"Search it with: python3 scripts/search-kb.py \"query\" [--type TYPE] [--max N] [--tag TAG]\n"
            f"Categories: book, strategy, marketing, code, financial, operational, meeting_notes, general, project, conversations\n"
            f"Get full chunk: python3 scripts/search-kb.py --chunk CHUNK_ID --file path/to/index.json\n"
            f"List categories: python3 scripts/search-kb.py --list-categories\n\n"
            f"ACCOUNTING SYSTEM: Financial data for William Simpson Personal, Maxamra Trust, and Rossmax Pty Ltd.\n"
            f"Data: /home/fields/samantha-accounting/ (bank statements, JSON ledgers, investments, CGT, property, tax)\n"
            f"All commands run from: cd /home/fields/samantha-accounting && source /home/fields/venv/bin/activate && set -a && source /home/fields/Fields_Orchestrator/.env && set +a\n\n"
            f"Accounting commands:\n"
            f"  python3 update_ledgers.py                           — Rebuild all ledgers from CSV/PDF sources\n"
            f"  python3 run_accounting_summary.py <entity> <fy>     — FY summary for an entity\n"
            f"    Entities: William_Simpson_Personal, Maxamra_Trust, Rossmax_Pty_Ltd\n"
            f"    FYs: FY22, FY23, FY24, FY25\n\n"
            f"For direct ledger queries, use Python:\n"
            f"  import sys; sys.path.insert(0, '/home/fields/samantha-accounting/finance-module')\n"
            f"  from ledger_search import search_transactions, summarize_by_category\n"
            f"  # Search: search_transactions(entity='Rossmax_Pty_Ltd', fy='FY25', vendor='next Thursday')\n"
            f"  # Summary: summarize_by_category(entity='William_Simpson_Personal', fy='FY24')\n"
            f"  from tax_summary import generate_tax_summary\n"
            f"  # Tax report: generate_tax_summary('Maxamra_Trust', 'FY24')\n\n"
            f"Ledger JSON files: /home/fields/samantha-accounting/Ledgers/\n"
            f"  Format: {{entity}}_{{account}}_{{fy}}_Bank.json\n"
            f"  Each entry: date, amount, currency, balance, vendor, description, expense_category\n"
            f"Bank statements: /home/fields/samantha-accounting/Bank_Statements/\n"
            f"Investments: /home/fields/samantha-accounting/Investments/\n"
            f"CGT data: /home/fields/samantha-accounting/CGT/\n"
            f"Property (rental): /home/fields/samantha-accounting/Property/46_Balderstone_St_Rental/\n"
            f"Historical ledgers (Excel): /home/fields/samantha-accounting/Historical_Ledgers/\n\n"
            f"{context}"
        )

        self._update_task(task_id, {
            "status": "running",
            "started_at": _now_iso(),
            "last_heartbeat_at": _now_iso(),
        })
        self._sse.broadcast("task_started", {
            "task_id": task_id,
            "title": self._get_task(task_id).get("title", ""),
            "status": "running",
        })
        log.info(f"Worker started (SDK): {task_id}")

        # Background heartbeat
        hb_running = True
        async def heartbeat():
            while hb_running:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                if hb_running:
                    self._update_task(task_id, {"last_heartbeat_at": _now_iso()})
                    self._sse.broadcast("task_progress", {
                        "task_id": task_id,
                        "status": "running",
                    })

        hb_task = asyncio.create_task(heartbeat())

        options = ClaudeAgentOptions(
            model="opus",
            cwd=ORCHESTRATOR_DIR,
            env={"ANTHROPIC_API_KEY": ""},
            permission_mode="bypassPermissions",
            system_prompt=worker_system,
            max_turns=30,
        )

        response = ""
        try:
            async def _run():
                nonlocal response
                async for msg in query(prompt=prompt, options=options):
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                response = block.text
                    elif isinstance(msg, ResultMessage):
                        if msg.result:
                            response = msg.result

            await asyncio.wait_for(_run(), timeout=WORKER_TIMEOUT_SECONDS)

        except asyncio.TimeoutError:
            log.error(f"Worker timed out: {task_id}")
            self._update_task(task_id, {
                "status": "failed",
                "finished_at": _now_iso(),
                "error_text": f"Timed out after {WORKER_TIMEOUT_SECONDS}s",
            })
            self._sse.broadcast("task_failed", {
                "task_id": task_id,
                "error": f"Timed out after {WORKER_TIMEOUT_SECONDS}s",
            })
            return
        except Exception as e:
            log.error(f"Worker error: {task_id}: {e}")
            self._update_task(task_id, {
                "status": "failed",
                "finished_at": _now_iso(),
                "error_text": str(e)[:1200],
            })
            self._sse.broadcast("task_failed", {
                "task_id": task_id,
                "error": str(e)[:200],
            })
            return
        finally:
            hb_running = False
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

        if not response:
            log.error(f"Worker returned empty: {task_id}")
            self._update_task(task_id, {
                "status": "failed",
                "finished_at": _now_iso(),
                "error_text": "Empty response from worker",
            })
            self._sse.broadcast("task_failed", {
                "task_id": task_id,
                "error": "Empty response",
            })
        else:
            summary = response[:300]
            if len(response) > 300:
                summary += "..."
            log.info(f"Worker completed: {task_id} ({len(response)} chars)")
            self._update_task(task_id, {
                "status": "completed",
                "finished_at": _now_iso(),
                "result_summary": summary,
                "result_full": response,
                "notified": False,
            })
            task = self._get_task(task_id)
            self._sse.broadcast("task_completed", {
                "task_id": task_id,
                "title": task.get("title", ""),
                "summary": summary,
            })


    def _update_task(self, task_id: str, updates: dict):
        """Update task document in MongoDB."""
        try:
            self._sm[TASK_COLL].update_one(
                {"_id": task_id},
                {"$set": updates},
            )
        except Exception as e:
            log.error(f"Failed to update task {task_id}: {e}")

    def _get_task(self, task_id: str) -> dict:
        """Get task document from MongoDB."""
        return self._sm[TASK_COLL].find_one({"_id": task_id}) or {}

    # --- Public API ---

    def get_active_tasks(self) -> list[dict]:
        """Return tasks that are queued or running."""
        tasks = list(self._sm[TASK_COLL].find(
            {"status": {"$in": ["queued", "running"]}},
            {"prompt": 0, "result_full": 0},
        ))
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks

    def get_recent_tasks(self, limit: int = 10) -> list[dict]:
        """Return recent tasks (all statuses). Sorted in Python (Cosmos has no index)."""
        tasks = list(self._sm[TASK_COLL].find(
            {},
            {"prompt": 0, "result_full": 0},
        ).limit(limit + 10))  # fetch a few extra to compensate for no server sort
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks[:limit]

    def get_task_detail(self, task_id: str) -> Optional[dict]:
        """Return full task document including result."""
        return self._sm[TASK_COLL].find_one({"_id": task_id})

    def get_unnotified_completed(self) -> list[dict]:
        """Return completed tasks that haven't been reported to the user yet."""
        return list(self._sm[TASK_COLL].find(
            {"status": "completed", "notified": False},
            {"prompt": 0},
        ))

    def mark_notified(self, task_ids: list[str]):
        """Mark tasks as notified after the user has been told about them."""
        if task_ids:
            self._sm[TASK_COLL].update_many(
                {"_id": {"$in": task_ids}},
                {"$set": {"notified": True}},
            )

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running/queued task. Returns True if cancelled."""
        task = self._get_task(task_id)
        if not task or task.get("status") not in ("queued", "running"):
            return False

        # Signal the cancel event so the SDK query loop can break
        cancel_event = self._active_tasks.get(task_id)
        if cancel_event:
            cancel_event.set()

        self._update_task(task_id, {
            "status": "cancelled",
            "finished_at": _now_iso(),
            "error_text": "Cancelled by user",
        })
        self._sse.broadcast("task_failed", {
            "task_id": task_id,
            "error": "Cancelled by user",
        })
        log.info(f"Task cancelled: {task_id}")
        return True

    @property
    def active_count(self) -> int:
        return MAX_CONCURRENT_WORKERS - self._semaphore._value

    @property
    def queued_count(self) -> int:
        # Tasks waiting for semaphore
        waiters = getattr(self._semaphore, '_waiters', [])
        return len([w for w in waiters if not w.done()]) if waiters else 0
