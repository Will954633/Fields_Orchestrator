#!/usr/bin/env python3
"""
spawn_status.py — read back what spawned sessions found.

    python3 scripts/spawn_status.py              # queue overview
    python3 scripts/spawn_status.py <task_id>    # full result for one task
    python3 scripts/spawn_status.py --pending    # only work not yet done

This is how a LATER session picks up what an earlier one handed off. The whole
point of the queue is that the finding outlives the transcript that produced it,
so start here rather than re-deriving it.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from bson import ObjectId  # noqa: E402
from pymongo import MongoClient  # noqa: E402

COLLECTION = "spawned_tasks"
_ICON = {"pending": "·", "running": "▶", "completed": "✅", "failed": "⚠️"}


def _client():
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        raise RuntimeError("COSMOS_CONNECTION_STRING not set")
    return MongoClient(uri, retryWrites=False, serverSelectionTimeoutMS=30000)


def _age(dt) -> str:
    if not dt:
        return "—"
    mins = (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).total_seconds() / 60
    if mins < 60:
        return f"{mins:.0f}m ago"
    if mins < 1440:
        return f"{mins / 60:.1f}h ago"
    return f"{mins / 1440:.1f}d ago"


def show_one(coll, task_id: str) -> int:
    try:
        oid = ObjectId(task_id)
    except Exception:
        print(f"not a valid task id: {task_id}", file=sys.stderr)
        return 1
    task = coll.find_one({"_id": oid})
    if not task:
        print(f"no such task: {task_id}", file=sys.stderr)
        return 1

    print(f"{_ICON.get(task['status'], '?')} {task['title']}")
    print(f"   {task['status']} · {task['scope']}/{task['repo']} · "
          f"created {_age(task.get('created_at'))} · attempts {task.get('attempts', 0)}")

    result = task.get("result")
    if result:
        print(f"\n   OUTCOME: {result.get('outcome')} (confidence: {result.get('confidence')})")
        print(f"\n   {result.get('summary', '')}")
        if result.get("root_cause"):
            print(f"\n   ROOT CAUSE\n   {result['root_cause']}")
        for e in result.get("evidence") or []:
            print(f"     - {e}")
        if result.get("next_step"):
            print(f"\n   NEXT: {result['next_step']}")
        for q in result.get("open_questions") or []:
            print(f"     ? {q}")
        if result.get("files_touched"):
            print(f"\n   FILES: {', '.join(result['files_touched'])}")
    if task.get("diffstat"):
        print(f"\n   DIFF (worktree {task.get('worktree')})\n{task['diffstat']}")
    if task.get("error"):
        print(f"\n   ERROR: {task['error']}")
    if task.get("log_file"):
        print(f"\n   log: {task['log_file']}")
    return 0


def show_all(coll, pending_only: bool) -> int:
    q = {"status": {"$in": ["pending", "running"]}} if pending_only else {}
    tasks = list(coll.find(q).sort("created_at", -1).limit(40))
    if not tasks:
        print("no spawned tasks" + (" outstanding" if pending_only else ""))
        return 0
    for t in tasks:
        outcome = (t.get("result") or {}).get("outcome", "")
        print(f"{_ICON.get(t['status'], '?')} {str(t['_id'])}  {t['scope']:<11} "
              f"{_age(t.get('created_at')):>9}  {outcome:<20} {t['title'][:60]}")
    print(f"\n{len(tasks)} task(s). Detail: python3 scripts/spawn_status.py <task_id>")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:]]
    pending_only = "--pending" in args
    args = [a for a in args if not a.startswith("--")]

    client = _client()
    try:
        coll = client["system_monitor"][COLLECTION]
        if args:
            return show_one(coll, args[0])
        return show_all(coll, pending_only)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
