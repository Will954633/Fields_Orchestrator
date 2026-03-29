#!/usr/bin/env python3
"""Email Triage Check — runs 2x/day to surface emails needing Will's attention.

Writes EMAIL_ATTENTION.md which gets injected into the Fields Chat Agent context.
The agent then naturally mentions pending emails in conversation.

Usage:
    python3 scripts/email-triage-check.py          # Run triage
    python3 scripts/email-triage-check.py --dry-run # Preview without writing file
"""

import json
import os
import sys
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load env
ENV_FILE = Path("/home/fields/Fields_Orchestrator/.env")
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)

# Also load /etc/environment for ANTHROPIC_API_KEY
etc_env = Path("/etc/environment")
if etc_env.exists():
    with open(etc_env) as f:
        for line in f:
            line = line.strip()
            if line and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

SCRIPT_DIR = Path(__file__).parent.parent
EMAIL_AGENT_DIR = Path("/home/fields/samantha-email-agent")
OUTPUT_FILE = SCRIPT_DIR / "EMAIL_ATTENTION.md"
AEST = timezone(timedelta(hours=10))

# Domains/senders to always ignore (newsletters, marketing, etc.)
IGNORE_DOMAINS = {
    "newsletter.agoda-emails.com", "sg.newsletter.agoda-emails.com",
    "booking.com", "noreply@booking.com", "sg.booking.com",
    "amazon.com.au", "auto-confirm@amazon.com.au",
    "newsletter.afr.com", "updates@newsletter.afr.com",
    "linkedin.com", "facebookmail.com",
    "noreply@medium.com", "noreply@substack.com",
    "no-reply@marketing.canva.com",
}

IGNORE_SUBJECTS_PATTERNS = [
    re.compile(r"unsubscribe", re.I),
    re.compile(r"newsletter", re.I),
    re.compile(r"weekly digest", re.I),
    re.compile(r"price alert", re.I),
    re.compile(r"pack your bags", re.I),
    re.compile(r"your booking", re.I),
]

# Senders that are always important
VIP_DOMAINS = {
    "fieldsestate.com.au",
    "moflow.au",       # Kara (coaching)
    "accrubris.com.au", # accountant
}


def load_graph_tools():
    """Load email graph tools with agents SDK mock."""
    import types
    agents_mock = types.ModuleType("agents")
    def function_tool(fn=None, **kwargs):
        return fn if fn else (lambda f: f)
    agents_mock.function_tool = function_tool
    agents_mock.Agent = type("Agent", (), {})
    agents_mock.Runner = type("Runner", (), {})
    sys.modules["agents"] = agents_mock

    if str(EMAIL_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(EMAIL_AGENT_DIR))

    import email_graph_tools as graph
    graph.ROOT_DIR = EMAIL_AGENT_DIR
    graph.TOOLS_DIR = EMAIL_AGENT_DIR
    return graph


def classify_email(email: dict) -> dict:
    """Classify a single email for attention-worthiness."""
    sender_email = (email.get("sender", {}).get("email") or "").lower()
    sender_name = email.get("sender", {}).get("name") or sender_email
    subject = email.get("subject") or ""
    domain = sender_email.split("@")[1] if "@" in sender_email else ""

    # Skip ignored domains
    if domain in IGNORE_DOMAINS or sender_email in IGNORE_DOMAINS:
        return None

    # Skip ignored subject patterns
    for pattern in IGNORE_SUBJECTS_PATTERNS:
        if pattern.search(subject):
            return None

    # Classify importance
    is_vip = domain in VIP_DOMAINS
    is_reply = subject.lower().startswith("re:")
    is_personal = not any(x in sender_email for x in ["noreply", "no-reply", "donotreply", "notification", "alert"])

    if is_vip:
        importance = "high"
    elif is_reply and is_personal:
        importance = "medium"
    elif is_personal:
        importance = "low"
    else:
        return None  # Skip automated/system emails

    return {
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "date": email.get("received_at", ""),
        "message_id": email.get("message_id", ""),
        "importance": importance,
        "is_reply": is_reply,
    }


def run_triage(dry_run=False):
    """Check inbox and write EMAIL_ATTENTION.md."""
    graph = load_graph_tools()

    # Get unread emails from last 24 hours
    result = graph.list_unread_important_candidates_core(limit=30, since_days=2)

    if result.get("status") != "success":
        print(f"Graph API error: {result.get('message', 'unknown')}")
        if not dry_run:
            # Write empty file so the agent knows triage ran but found nothing
            OUTPUT_FILE.write_text(
                f"# Email Attention\n\n"
                f"_Last checked: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}_\n\n"
                f"Could not check inbox: {result.get('message', 'Graph API unavailable')}\n"
            )
        return

    candidates = result.get("candidates", [])
    if not candidates:
        print("No unread emails found.")
        if not dry_run:
            OUTPUT_FILE.write_text(
                f"# Email Attention\n\n"
                f"_Last checked: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}_\n\n"
                f"No emails requiring attention.\n"
            )
        return

    # Classify each email
    attention_items = []
    for candidate in candidates:
        email_data = {
            "sender": candidate.get("sender", {}),
            "subject": candidate.get("subject", ""),
            "received_at": candidate.get("received_at", ""),
            "message_id": candidate.get("message_id", ""),
        }
        classified = classify_email(email_data)
        if classified:
            attention_items.append(classified)

    # Sort by importance (high first)
    importance_order = {"high": 0, "medium": 1, "low": 2}
    attention_items.sort(key=lambda x: importance_order.get(x["importance"], 3))

    # Build the markdown summary
    now = datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')
    lines = [
        f"# Email Attention",
        f"",
        f"_Last checked: {now}_",
        f"",
    ]

    if not attention_items:
        lines.append("No emails requiring attention.")
    else:
        high = [e for e in attention_items if e["importance"] == "high"]
        medium = [e for e in attention_items if e["importance"] == "medium"]
        low = [e for e in attention_items if e["importance"] == "low"]

        if high:
            lines.append(f"## Needs Reply ({len(high)})")
            for e in high:
                date_short = e["date"][:10] if e["date"] else ""
                lines.append(f"- **{e['sender_name']}** — {e['subject']} ({date_short})")
            lines.append("")

        if medium:
            lines.append(f"## Worth Reading ({len(medium)})")
            for e in medium:
                date_short = e["date"][:10] if e["date"] else ""
                lines.append(f"- {e['sender_name']} — {e['subject']} ({date_short})")
            lines.append("")

        if low:
            lines.append(f"## Low Priority ({len(low)})")
            for e in low:
                lines.append(f"- {e['sender_name']} — {e['subject']}")
            lines.append("")

    content = "\n".join(lines) + "\n"

    if dry_run:
        print(content)
        print(f"\n--- {len(attention_items)} items classified from {len(candidates)} candidates ---")
    else:
        OUTPUT_FILE.write_text(content)
        print(f"Wrote {OUTPUT_FILE} — {len(attention_items)} items from {len(candidates)} candidates")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_triage(dry_run=dry_run)
