#!/usr/bin/env python3
"""
sync-memory-to-codex.py — Sync Claude's persistent memory + CEO agent proposals into AGENTS.md

Sources:
  1. Claude memory files at /home/projects/.claude/projects/.../memory/
  2. Pending CEO agent proposals from system_monitor.ceo_proposals in MongoDB

Rewrites the [AUTO-SYNCED MEMORY] section at the bottom of AGENTS.md.
Run manually or via cron (nightly at 01:30 AEST).
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MEMORY_DIR = Path("/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory")
AGENTS_MD = Path("/home/fields/Fields_Orchestrator/AGENTS.md")
ENV_FILE = Path("/home/fields/Fields_Orchestrator/.env")
AEST = ZoneInfo("Australia/Brisbane")

START_MARKER = "<!-- MEMORY_SECTION_START -->"
END_MARKER = "<!-- MEMORY_SECTION_END -->"

SKIP_FILES = {"MEMORY.md"}

TYPE_LABELS = {
    "feedback": "User Feedback & Corrections",
    "project": "Project State & Decisions",
    "user": "User Profile",
    "reference": "External References",
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# ── Claude memory ──────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict, str]:
    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip()
            body = parts[2].strip()
    return meta, body


def load_memories() -> dict[str, list[dict]]:
    memories: dict[str, list[dict]] = {}
    if not MEMORY_DIR.exists():
        print(f"Warning: memory dir not found at {MEMORY_DIR}", file=sys.stderr)
        return memories
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if path.name in SKIP_FILES:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(raw)
            mem_type = meta.get("type", "reference")
            name = meta.get("name", path.stem)
            memories.setdefault(mem_type, []).append(
                {"name": name, "type": mem_type, "body": body}
            )
        except Exception as e:
            print(f"Warning: could not parse {path.name}: {e}", file=sys.stderr)
    return memories


def render_memories(memories: dict[str, list[dict]]) -> list[str]:
    lines = []
    order = ["feedback", "project", "user", "reference"]
    all_types = order + [t for t in memories if t not in order]
    for mem_type in all_types:
        if mem_type not in memories:
            continue
        label = TYPE_LABELS.get(mem_type, mem_type.title())
        lines.append(f"\n### {label}\n")
        for entry in memories[mem_type]:
            lines.append(f"#### {entry['name']}\n")
            lines.append(entry["body"])
            lines.append("")
    return lines


# ── CEO proposals ──────────────────────────────────────────────────────────────

def load_env():
    """Load .env file into os.environ."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)


def load_ceo_proposals() -> list[dict]:
    """Fetch pending/recent CEO proposals from MongoDB."""
    try:
        from pymongo import MongoClient
    except ImportError:
        print("Warning: pymongo not available — skipping CEO proposals", file=sys.stderr)
        return []

    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("Warning: COSMOS_CONNECTION_STRING not set — skipping CEO proposals", file=sys.stderr)
        return []

    try:
        client = MongoClient(conn, serverSelectionTimeoutMS=8000)
        proposals = list(client["system_monitor"]["ceo_proposals"].find(
            {"agent": {"$ne": "system"}}  # exclude test/init docs
        ))
        client.close()

        # Sort in Python to avoid Cosmos compound-index limitation
        proposals.sort(key=lambda x: (x.get("date", ""), x.get("agent", "")), reverse=True)

        # Keep: all pending_review + completed from last 7 days
        cutoff = (datetime.now(AEST) - timedelta(days=7)).strftime("%Y-%m-%d")
        relevant = [
            p for p in proposals
            if p.get("status") == "pending_review"
            or (p.get("status") == "completed" and p.get("date", "") >= cutoff)
        ]
        return relevant
    except Exception as e:
        print(f"Warning: could not load CEO proposals: {e}", file=sys.stderr)
        return []


def render_proposals(proposals: list[dict]) -> list[str]:
    if not proposals:
        return ["\n### CEO Agent Proposals\n", "_No pending proposals._\n"]

    lines = ["\n### CEO Agent Proposals — Action Required\n"]
    lines.append("> These are findings and proposals from the management agent team. Pending items need implementation.\n")

    for p in proposals:
        agent = p.get("agent", "unknown").upper()
        date = p.get("date", "?")
        status = p.get("status", "?")
        status_badge = "⚠️ PENDING" if status == "pending_review" else "✅ COMPLETED"
        lines.append(f"\n#### {agent} Agent — {date} [{status_badge}]\n")
        lines.append(f"{p.get('summary', '')}\n")

        findings = p.get("findings", [])
        if findings:
            findings_sorted = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 99))
            lines.append("**Findings:**\n")
            for f in findings_sorted:
                sev = f.get("severity", "?").upper()
                title = f.get("title", "")
                detail = f.get("detail", "")[:200]
                lines.append(f"- `[{sev}]` **{title}** — {detail}")
            lines.append("")

        proposals_list = p.get("proposals", [])
        if proposals_list:
            proposals_sorted = sorted(proposals_list, key=lambda pr: PRIORITY_ORDER.get(pr.get("priority", "low"), 99))
            lines.append("**Proposed fixes:**\n")
            for pr in proposals_sorted:
                pri = pr.get("priority", "?").upper()
                title = pr.get("title", "")
                solution = pr.get("solution", pr.get("description", ""))[:200]
                lines.append(f"- `[{pri}]` **{title}** — {solution}")
            lines.append("")

        if status == "pending_review":
            lines.append("> To mark implemented: update `status` to `'completed'` in `system_monitor.ceo_proposals` where `agent='{p.get('agent')}'` and `date='{date}'`\n")

    return lines


# ── Main ───────────────────────────────────────────────────────────────────────

def update_agents_md(content: str) -> None:
    if not AGENTS_MD.exists():
        print(f"Error: {AGENTS_MD} not found", file=sys.stderr)
        sys.exit(1)
    original = AGENTS_MD.read_text(encoding="utf-8")
    start_idx = original.find(START_MARKER)
    end_idx = original.find(END_MARKER)
    if start_idx == -1 or end_idx == -1:
        print(f"Error: markers not found in {AGENTS_MD}", file=sys.stderr)
        sys.exit(1)
    AGENTS_MD.write_text(
        original[: start_idx + len(START_MARKER)] + "\n" + content + "\n" + original[end_idx:],
        encoding="utf-8",
    )


def main():
    load_env()
    now = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")

    print("Loading Claude memory files...")
    memories = load_memories()
    mem_total = sum(len(v) for v in memories.values())
    for t, entries in memories.items():
        print(f"  {t}: {len(entries)} entries")

    print("Loading CEO agent proposals...")
    proposals = load_ceo_proposals()
    pending = sum(1 for p in proposals if p.get("status") == "pending_review")
    print(f"  {len(proposals)} relevant proposals ({pending} pending review)")

    lines = [f"_Last synced: {now}_\n"]
    lines += render_proposals(proposals)
    lines += render_memories(memories)

    print(f"Updating {AGENTS_MD}...")
    update_agents_md("\n".join(lines))
    print(f"Done. {mem_total} memory entries + {len(proposals)} proposals synced into AGENTS.md.")


if __name__ == "__main__":
    main()
