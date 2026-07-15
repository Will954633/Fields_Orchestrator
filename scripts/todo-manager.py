#!/usr/bin/env python3
"""
todo-manager.py — Personal task & reminder system for Will.

Stores todos in system_monitor.user_todos (Cosmos DB).
Sends reminders via Telegram and SSE push.

Usage:
    python3 scripts/todo-manager.py add "Pay BAS instalment" --due 2026-04-28 --priority high --tags finance,tax
    python3 scripts/todo-manager.py add "Reply to Kara about Wed/Thu" --due 2026-04-02 --priority medium
    python3 scripts/todo-manager.py list                         # all open todos
    python3 scripts/todo-manager.py list --overdue               # overdue only
    python3 scripts/todo-manager.py list --due-today             # due today
    python3 scripts/todo-manager.py list --tag finance           # filter by tag
    python3 scripts/todo-manager.py done <id>                    # mark complete
    python3 scripts/todo-manager.py snooze <id> --days 3         # push due date
    python3 scripts/todo-manager.py delete <id>                  # remove
    python3 scripts/todo-manager.py remind                       # send Telegram digest of due/overdue
    python3 scripts/todo-manager.py session-check                # output for chat session context
    python3 scripts/todo-manager.py show <id>                    # show single todo detail
"""

import os
import sys
import argparse
import json
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from pymongo import ASCENDING

# Timezone
AEST = timezone(timedelta(hours=10))

def get_db():
    """Get system_monitor database connection."""
    from pymongo import MongoClient
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    client = MongoClient(conn)
    return client["system_monitor"]


def ensure_indexes(db):
    """Create lightweight indexes for common todo queries."""
    coll = db["user_todos"]
    try:
        coll.create_index([("status", ASCENDING), ("due_date", ASCENDING)])
        coll.create_index([("status", ASCENDING), ("priority", ASCENDING)])
        coll.create_index([("tags", ASCENDING)])
        coll.create_index([("created_at", ASCENDING)])
    except Exception:
        pass


def now_aest():
    return datetime.now(AEST)


def format_date(dt):
    """Format datetime for display."""
    if dt is None:
        return "no due date"
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=AEST)
    return dt.strftime("%a %d %b %Y")


def days_until(dt):
    """Days until due date. Negative = overdue."""
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=AEST)
    today = now_aest().replace(hour=0, minute=0, second=0, microsecond=0)
    due_day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return (due_day - today).days


def urgency_label(days):
    """Human-readable urgency."""
    if days is None:
        return ""
    if days < 0:
        return f"OVERDUE by {abs(days)}d"
    if days == 0:
        return "DUE TODAY"
    if days == 1:
        return "due tomorrow"
    if days <= 3:
        return f"due in {days}d"
    if days <= 7:
        return f"due in {days}d"
    return f"due in {days}d"


def priority_sort(p):
    """Sort order for priority."""
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(p, 4)


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_add(args):
    """Add a new todo."""
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    due_date = None
    if args.due:
        due_date = datetime.strptime(args.due, "%Y-%m-%d").replace(tzinfo=AEST)

    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",")]

    todo = {
        "title": args.title,
        "status": "open",
        "priority": args.priority or "medium",
        "due_date": due_date,
        "tags": tags,
        "notes": args.notes or "",
        "reminder_sent": False,
        "created_at": now_aest(),
        "updated_at": now_aest(),
        "completed_at": None,
        "source": args.source or "chat",
    }

    result = coll.insert_one(todo)
    todo_id = str(result.inserted_id)

    due_str = format_date(due_date) if due_date else "no due date"
    print(f"Added todo [{todo_id[-6:]}]: {args.title}")
    print(f"  Priority: {todo['priority']} | Due: {due_str} | Tags: {', '.join(tags) or 'none'}")

    return todo_id


def cmd_list(args):
    """List todos with optional filters."""
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    query = {"status": "open"}

    if args.overdue:
        query["due_date"] = {"$lt": now_aest(), "$ne": None}
    elif args.due_today:
        today_start = now_aest().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        query["due_date"] = {"$gte": today_start, "$lt": today_end}
    elif args.due_week:
        today_start = now_aest().replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = today_start + timedelta(days=7)
        query["due_date"] = {"$gte": today_start, "$lt": week_end}

    if args.tag:
        query["tags"] = args.tag

    if args.all:
        del query["status"]

    todos = list(coll.find(query))

    if not todos:
        print("No matching todos.")
        return

    # Sort: overdue first, then by priority, then by due date
    def sort_key(t):
        d = days_until(t.get("due_date"))
        if d is None:
            d = 999
        return (0 if d < 0 else 1, priority_sort(t.get("priority", "medium")), d)

    todos.sort(key=sort_key)

    print(f"\n{'─' * 70}")
    print(f"  {'ID':<8} {'Priority':<10} {'Due':<16} {'Status':<12} Title")
    print(f"{'─' * 70}")

    for t in todos:
        tid = str(t["_id"])[-6:]
        pri = t.get("priority", "medium")
        due = t.get("due_date")
        status = t.get("status", "open")
        title = t.get("title", "")

        d = days_until(due)
        urgency = urgency_label(d)

        # Visual indicators
        if d is not None and d < 0:
            marker = "!!"
        elif d is not None and d == 0:
            marker = "!!"
        elif d is not None and d <= 3:
            marker = " !"
        else:
            marker = "  "

        due_display = format_date(due) if due else "—"
        if urgency and d is not None and d <= 3:
            due_display = urgency

        if status == "done":
            marker = " ✓"

        print(f"{marker}{tid:<8} {pri:<10} {due_display:<16} {status:<12} {title}")
        if t.get("tags"):
            print(f"          tags: {', '.join(t['tags'])}")

    print(f"{'─' * 70}")

    open_count = sum(1 for t in todos if t.get("status") == "open")
    overdue_count = sum(1 for t in todos if t.get("status") == "open" and days_until(t.get("due_date")) is not None and days_until(t.get("due_date")) < 0)

    if overdue_count:
        print(f"  {open_count} open, {overdue_count} OVERDUE")
    else:
        print(f"  {open_count} open")
    print()


def cmd_done(args):
    """Mark a todo as done."""
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    # Find by partial ID suffix
    todo = _find_by_partial_id(coll, args.id)
    if not todo:
        return

    coll.update_one(
        {"_id": todo["_id"]},
        {"$set": {"status": "done", "completed_at": now_aest(), "updated_at": now_aest()}}
    )
    print(f"Completed: {todo['title']}")


def cmd_snooze(args):
    """Push a todo's due date forward."""
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    todo = _find_by_partial_id(coll, args.id)
    if not todo:
        return

    current_due = todo.get("due_date") or now_aest()
    if isinstance(current_due, str):
        current_due = datetime.fromisoformat(current_due)
    if current_due.tzinfo is None:
        current_due = current_due.replace(tzinfo=AEST)

    # If overdue, snooze from today instead of the past date
    today = now_aest().replace(hour=0, minute=0, second=0, microsecond=0)
    base = max(current_due, today)

    new_due = base + timedelta(days=args.days)

    coll.update_one(
        {"_id": todo["_id"]},
        {"$set": {"due_date": new_due, "reminder_sent": False, "updated_at": now_aest()}}
    )
    print(f"Snoozed: {todo['title']} → {format_date(new_due)}")


def cmd_delete(args):
    """Delete a todo."""
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    todo = _find_by_partial_id(coll, args.id)
    if not todo:
        return

    coll.delete_one({"_id": todo["_id"]})
    print(f"Deleted: {todo['title']}")


def cmd_show(args):
    """Show detail for a single todo."""
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    todo = _find_by_partial_id(coll, args.id)
    if not todo:
        return

    print(f"\nTodo: {todo['title']}")
    print(f"  ID:       {str(todo['_id'])}")
    print(f"  Status:   {todo.get('status', 'open')}")
    print(f"  Priority: {todo.get('priority', 'medium')}")
    print(f"  Due:      {format_date(todo.get('due_date'))}")
    d = days_until(todo.get("due_date"))
    if d is not None:
        print(f"  Urgency:  {urgency_label(d)}")
    print(f"  Tags:     {', '.join(todo.get('tags', [])) or 'none'}")
    print(f"  Notes:    {todo.get('notes') or '—'}")
    print(f"  Source:   {todo.get('source', '—')}")
    print(f"  Created:  {todo.get('created_at', '—')}")
    if todo.get("completed_at"):
        print(f"  Done:     {todo['completed_at']}")
    print()


def cmd_remind(args):
    """Send Telegram digest of due/overdue todos."""
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    today_start = now_aest().replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = today_start + timedelta(days=7)

    # Get overdue
    overdue = list(coll.find({
        "status": "open",
        "due_date": {"$lt": today_start, "$ne": None}
    }))

    # Get due today
    today_end = today_start + timedelta(days=1)
    due_today = list(coll.find({
        "status": "open",
        "due_date": {"$gte": today_start, "$lt": today_end}
    }))

    # Get due this week (not today)
    due_week = list(coll.find({
        "status": "open",
        "due_date": {"$gte": today_end, "$lt": week_end}
    }))

    if not overdue and not due_today and not due_week:
        if not args.quiet:
            print("Nothing due — no reminder sent.")
        return

    # Build message
    lines = ["📋 *Fields Todo Digest*\n"]

    if overdue:
        lines.append("🔴 *OVERDUE:*")
        for t in overdue:
            d = abs(days_until(t["due_date"]))
            pri = t.get("priority", "")
            pri_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(pri, "")
            lines.append(f"  {pri_icon} {t['title']} ({d}d overdue)")
        lines.append("")

    if due_today:
        lines.append("⚡ *DUE TODAY:*")
        for t in due_today:
            pri = t.get("priority", "")
            pri_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(pri, "")
            lines.append(f"  {pri_icon} {t['title']}")
        lines.append("")

    if due_week:
        lines.append("📅 *This week:*")
        for t in due_week:
            d = days_until(t["due_date"])
            lines.append(f"  • {t['title']} ({format_date(t['due_date'])})")
        lines.append("")

    total_open = coll.count_documents({"status": "open"})
    lines.append(f"_{total_open} total open tasks_")

    message = "\n".join(lines)

    # Send via Telegram
    try:
        from scripts.telegram_notify import send_message as tg_send
    except ImportError:
        # Direct import fallback
        sys.path.insert(0, os.path.dirname(__file__))
        try:
            from telegram_notify import send_message as tg_send
        except ImportError:
            # Inline send
            import requests
            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
            if bot_token and chat_id:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                    timeout=10
                )
                print("Telegram reminder sent.")
            else:
                print("WARNING: Telegram not configured — printing instead:")
                print(message)
            return

    tg_send(message)
    print("Telegram reminder sent.")

    # Mark reminders as sent for today
    all_reminded = overdue + due_today
    for t in all_reminded:
        coll.update_one(
            {"_id": t["_id"]},
            {"$set": {"reminder_sent": True, "last_reminded_at": now_aest()}}
        )


def cmd_session_check(args):
    """Output a concise summary for chat session context.

    This is called at session start to surface pending todos.
    Output is designed to be included in chat context, not for Telegram.
    """
    db = get_db()
    ensure_indexes(db)
    coll = db["user_todos"]

    today_start = now_aest().replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = today_start + timedelta(days=7)

    overdue = list(coll.find({
        "status": "open",
        "due_date": {"$lt": today_start, "$ne": None}
    }))

    today_end = today_start + timedelta(days=1)
    due_today = list(coll.find({
        "status": "open",
        "due_date": {"$gte": today_start, "$lt": today_end}
    }))

    due_week = list(coll.find({
        "status": "open",
        "due_date": {"$gte": today_end, "$lt": week_end}
    }))

    # Get ALL open todos and classify client-side (avoids Cosmos sort/index issues)
    all_open = list(coll.find({"status": "open"}))

    if not all_open:
        print("No pending todos.")
        return

    overdue = []
    due_today_list = []
    due_week_list = []
    later = []
    no_date = []

    for t in all_open:
        dd = t.get("due_date")
        if dd is None:
            no_date.append(t)
            continue
        d = days_until(dd)
        if d is None:
            no_date.append(t)
        elif d < 0:
            overdue.append(t)
        elif d == 0:
            due_today_list.append(t)
        elif d <= 7:
            due_week_list.append(t)
        else:
            later.append(t)

    lines = [f"PENDING TODOS ({len(all_open)} open):"]

    if overdue:
        for t in overdue:
            d = abs(days_until(t["due_date"]))
            lines.append(f"  !! OVERDUE ({d}d): {t['title']} [{t.get('priority','medium')}]")

    if due_today_list:
        for t in due_today_list:
            lines.append(f"  !! DUE TODAY: {t['title']} [{t.get('priority','medium')}]")

    if due_week_list:
        for t in due_week_list:
            d = days_until(t["due_date"])
            lines.append(f"  -> {format_date(t['due_date'])}: {t['title']} [{t.get('priority','medium')}]")

    if later:
        for t in later:
            lines.append(f"     {format_date(t['due_date'])}: {t['title']} [{t.get('priority','medium')}]")

    if no_date:
        for t in no_date:
            lines.append(f"     (no date): {t['title']} [{t.get('priority','medium')}]")

    print("\n".join(lines))


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _find_by_partial_id(coll, partial_id):
    """Find a todo by full ID or last 6 chars."""
    # Try full ObjectId first
    try:
        todo = coll.find_one({"_id": ObjectId(partial_id)})
        if todo:
            return todo
    except Exception:
        pass

    # Search by suffix match
    all_open = list(coll.find({"status": "open"}))
    matches = [t for t in all_open if str(t["_id"]).endswith(partial_id)]

    if not matches:
        # Try across all statuses
        all_todos = list(coll.find())
        matches = [t for t in all_todos if str(t["_id"]).endswith(partial_id)]

    if not matches:
        print(f"No todo found matching '{partial_id}'")
        return None
    if len(matches) > 1:
        print(f"Multiple matches for '{partial_id}' — use more characters:")
        for m in matches:
            print(f"  {str(m['_id'])}: {m['title']}")
        return None

    return matches[0]


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fields Estate personal todo & reminder system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Add a new todo")
    p_add.add_argument("title", help="Todo title")
    p_add.add_argument("--due", help="Due date (YYYY-MM-DD)")
    p_add.add_argument("--priority", choices=["critical", "high", "medium", "low"], default="medium")
    p_add.add_argument("--tags", help="Comma-separated tags")
    p_add.add_argument("--notes", help="Additional notes")
    p_add.add_argument("--source", default="chat", help="Source (chat, email, system)")

    # list
    p_list = sub.add_parser("list", help="List open todos")
    p_list.add_argument("--overdue", action="store_true", help="Show overdue only")
    p_list.add_argument("--due-today", action="store_true", help="Show due today only")
    p_list.add_argument("--due-week", action="store_true", help="Show due this week")
    p_list.add_argument("--tag", help="Filter by tag")
    p_list.add_argument("--all", action="store_true", help="Include completed todos")

    # done
    p_done = sub.add_parser("done", help="Mark a todo as done")
    p_done.add_argument("id", help="Todo ID (full or last 6 chars)")

    # snooze
    p_snooze = sub.add_parser("snooze", help="Push due date forward")
    p_snooze.add_argument("id", help="Todo ID")
    p_snooze.add_argument("--days", type=int, default=3, help="Days to snooze (default: 3)")

    # delete
    p_del = sub.add_parser("delete", help="Delete a todo")
    p_del.add_argument("id", help="Todo ID")

    # show
    p_show = sub.add_parser("show", help="Show detail for a todo")
    p_show.add_argument("id", help="Todo ID")

    # remind
    p_remind = sub.add_parser("remind", help="Send Telegram digest")
    p_remind.add_argument("--quiet", action="store_true", help="Silent if nothing due")

    # session-check
    sub.add_parser("session-check", help="Output for chat session context")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    {
        "add": cmd_add,
        "list": cmd_list,
        "done": cmd_done,
        "snooze": cmd_snooze,
        "delete": cmd_delete,
        "show": cmd_show,
        "remind": cmd_remind,
        "session-check": cmd_session_check,
    }[args.command](args)


if __name__ == "__main__":
    main()
