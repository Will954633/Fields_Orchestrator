#!/usr/bin/env python3
"""
sync-memory-to-codex.py — Sync Claude's persistent memory into AGENTS.md

Reads all memory files from Claude's memory directory and rewrites the
[AUTO-SYNCED MEMORY] section at the bottom of AGENTS.md.

Run manually or via cron (nightly recommended).
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MEMORY_DIR = Path("/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory")
AGENTS_MD = Path("/home/fields/Fields_Orchestrator/AGENTS.md")
AEST = ZoneInfo("Australia/Brisbane")

START_MARKER = "<!-- MEMORY_SECTION_START -->"
END_MARKER = "<!-- MEMORY_SECTION_END -->"

# Files to skip (index file, not a memory)
SKIP_FILES = {"MEMORY.md"}

# Map memory type to section header
TYPE_LABELS = {
    "feedback": "User Feedback & Corrections",
    "project": "Project State & Decisions",
    "user": "User Profile",
    "reference": "External References",
}


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a memory file."""
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
    """Load all memory files, grouped by type."""
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
            entry = {"name": name, "type": mem_type, "body": body, "file": path.name}
            memories.setdefault(mem_type, []).append(entry)
        except Exception as e:
            print(f"Warning: could not parse {path.name}: {e}", file=sys.stderr)

    return memories


def render_memory_section(memories: dict[str, list[dict]]) -> str:
    """Render the memory section as markdown."""
    now = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")
    lines = [f"_Last synced: {now}_\n"]

    # Order: feedback first (most actionable), then project, user, reference
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

    return "\n".join(lines)


def update_agents_md(memory_content: str) -> None:
    """Replace the memory section in AGENTS.md between the markers."""
    if not AGENTS_MD.exists():
        print(f"Error: {AGENTS_MD} not found", file=sys.stderr)
        sys.exit(1)

    original = AGENTS_MD.read_text(encoding="utf-8")

    start_idx = original.find(START_MARKER)
    end_idx = original.find(END_MARKER)

    if start_idx == -1 or end_idx == -1:
        print(f"Error: markers not found in {AGENTS_MD}", file=sys.stderr)
        print(f"Expected: {START_MARKER!r} and {END_MARKER!r}")
        sys.exit(1)

    new_content = (
        original[: start_idx + len(START_MARKER)]
        + "\n"
        + memory_content
        + "\n"
        + original[end_idx:]
    )

    AGENTS_MD.write_text(new_content, encoding="utf-8")


def main():
    print("Loading Claude memory files...")
    memories = load_memories()

    total = sum(len(v) for v in memories.values())
    if total == 0:
        print("No memory files found — AGENTS.md memory section will be empty.")
    else:
        for mem_type, entries in memories.items():
            print(f"  {mem_type}: {len(entries)} entries")

    print("Rendering memory section...")
    memory_content = render_memory_section(memories)

    print(f"Updating {AGENTS_MD}...")
    update_agents_md(memory_content)

    print(f"Done. Synced {total} memory entries into AGENTS.md.")


if __name__ == "__main__":
    main()
