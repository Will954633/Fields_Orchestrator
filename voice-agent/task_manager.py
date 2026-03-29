"""
Task Manager for the Fields Voice Agent.

Manages background Claude Code (Opus) worker subprocesses.
Up to 3 concurrent workers, tracked in MongoDB with heartbeat.
Modelled on builder-telegram-bridge.py job lifecycle pattern.
"""

import asyncio
import json
import os
import re
import signal
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("voice-agent.tasks")

AEST = timezone(timedelta(hours=10))
CLAUDE_BIN = "/usr/bin/claude"
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
    """Load project context for worker append-system-prompt."""
    sections = []

    claude_md = Path(ORCHESTRATOR_DIR) / "CLAUDE.md"
    if claude_md.exists():
        sections.append(claude_md.read_text())

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
        self._active_processes: dict[str, asyncio.subprocess.Process] = {}
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
        """Create a task and launch a background worker. Returns task_id.
        model: 'opus' (default), 'gpt54', or 'gpt54mini'."""
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
        # Wait for a slot (stays queued until semaphore available)
        async with self._semaphore:
            if model in ("gpt54", "gpt54mini"):
                await self._execute_gpt(task_id, prompt, model)
            else:
                await self._execute(task_id, prompt)

    async def _execute(self, task_id: str, prompt: str):
        """Execute Claude Code subprocess with heartbeat tracking."""
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
            f"List categories: python3 scripts/search-kb.py --list-categories"
        )
        append_prompt = f"{worker_system}\n\n{context}"

        try:
            proc = await asyncio.create_subprocess_exec(
                CLAUDE_BIN, "-p", prompt,
                "--output-format", "text",
                "--model", "opus",
                "--append-system-prompt", append_prompt,
                "--dangerously-skip-permissions",
                cwd=ORCHESTRATOR_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"},
            )
        except Exception as e:
            log.error(f"Failed to launch worker for {task_id}: {e}")
            self._update_task(task_id, {
                "status": "failed",
                "finished_at": _now_iso(),
                "error_text": f"Failed to launch: {e}",
            })
            self._sse.broadcast("task_failed", {
                "task_id": task_id,
                "error": str(e),
            })
            return

        self._active_processes[task_id] = proc
        self._update_task(task_id, {
            "status": "running",
            "pid": proc.pid,
            "started_at": _now_iso(),
            "last_heartbeat_at": _now_iso(),
        })

        self._sse.broadcast("task_started", {
            "task_id": task_id,
            "title": self._get_task(task_id).get("title", ""),
            "status": "running",
        })

        log.info(f"Worker started: {task_id} (PID {proc.pid})")

        try:
            stdout, stderr = await asyncio.wait_for(
                self._monitor_process(task_id, proc),
                timeout=WORKER_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.error(f"Worker timed out: {task_id}")
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
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
        finally:
            self._active_processes.pop(task_id, None)

        response = stdout.decode().strip() if stdout else ""
        stderr_text = stderr.decode().strip() if stderr else ""

        if proc.returncode != 0 or not response:
            error = stderr_text[:1200] if stderr_text else "Empty response"
            log.error(f"Worker failed: {task_id} (rc={proc.returncode})")
            self._update_task(task_id, {
                "status": "failed",
                "finished_at": _now_iso(),
                "error_text": error,
                "result_full": response or None,
            })
            self._sse.broadcast("task_failed", {
                "task_id": task_id,
                "error": error[:200],
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

    async def _execute_gpt(self, task_id: str, prompt: str, model: str):
        """Execute a GPT-based worker (no subprocess — uses OpenAI API agent loop)."""
        from gpt_agent import gpt_worker, GPT54_MODEL, GPT54_MINI_MODEL

        gpt_model = GPT54_MINI_MODEL if model == "gpt54mini" else GPT54_MODEL

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
        log.info(f"GPT worker started: {task_id} (model: {gpt_model})")

        # Heartbeat in background
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

        try:
            response = await asyncio.wait_for(
                gpt_worker(prompt, model=gpt_model),
                timeout=WORKER_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.error(f"GPT worker timed out: {task_id}")
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
            log.error(f"GPT worker error: {task_id}: {e}")
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
            self._update_task(task_id, {
                "status": "failed",
                "finished_at": _now_iso(),
                "error_text": "Empty response from GPT",
            })
            self._sse.broadcast("task_failed", {
                "task_id": task_id,
                "error": "Empty response",
            })
        else:
            summary = response[:300]
            if len(response) > 300:
                summary += "..."
            log.info(f"GPT worker completed: {task_id} ({len(response)} chars)")
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

    async def _monitor_process(self, task_id: str, proc) -> tuple[bytes, bytes]:
        """Monitor process with heartbeat updates. Returns (stdout, stderr)."""
        # Use a heartbeat task alongside the process
        async def heartbeat():
            while proc.returncode is None:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                if proc.returncode is None:
                    self._update_task(task_id, {
                        "last_heartbeat_at": _now_iso(),
                    })
                    self._sse.broadcast("task_progress", {
                        "task_id": task_id,
                        "status": "running",
                    })

        hb_task = asyncio.create_task(heartbeat())
        try:
            stdout, stderr = await proc.communicate()
            return stdout, stderr
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

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

        # Kill the process if running
        proc = self._active_processes.get(task_id)
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

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
