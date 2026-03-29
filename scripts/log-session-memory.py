#!/usr/bin/env python3
"""
Session Memory Logger — Records conversation takeaways to persistent memory.

Called at the end of each Claude Code session to capture:
- Decisions made
- Feedback received from Will
- New systems/features built
- Bug fixes and their patterns
- Strategy or business insights discussed

Usage:
    python3 scripts/log-session-memory.py --summary "What happened" --decisions "Key decisions" --feedback "Will's feedback" --systems "Systems changed"
    python3 scripts/log-session-memory.py --interactive  # Prompted mode
    python3 scripts/log-session-memory.py --from-file /tmp/session_notes.md  # Bulk import
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

AEST = timezone(timedelta(hours=10))
MEMORY_DIR = Path("/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory")
SESSION_LOG_DIR = MEMORY_DIR / "session_logs"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"


def ensure_dirs():
    SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_timestamp():
    return datetime.now(AEST)


def log_session(summary: str, decisions: str = "", feedback: str = "",
                systems: str = "", topics_file: str = "", raw_notes: str = ""):
    """Write a session log entry."""
    ensure_dirs()
    now = get_timestamp()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    # Find next sequence number for today
    existing = list(SESSION_LOG_DIR.glob(f"{date_str}_*.md"))
    seq = len(existing) + 1

    filename = f"{date_str}_{seq:02d}.md"
    filepath = SESSION_LOG_DIR / filename

    lines = [
        f"# Session Log — {date_str} {time_str} AEST",
        "",
        f"## Summary",
        summary.strip(),
        "",
    ]

    if decisions.strip():
        lines.extend([
            "## Decisions Made",
            decisions.strip(),
            "",
        ])

    if feedback.strip():
        lines.extend([
            "## Will's Feedback",
            feedback.strip(),
            "",
        ])

    if systems.strip():
        lines.extend([
            "## Systems Changed",
            systems.strip(),
            "",
        ])

    if raw_notes.strip():
        lines.extend([
            "## Additional Notes",
            raw_notes.strip(),
            "",
        ])

    # Write the log
    filepath.write_text("\n".join(lines))
    print(f"Session logged: {filepath}")

    # Also output which memory files should be updated
    print("\n--- Memory files that may need updating ---")
    suggest_memory_updates(summary, decisions, feedback, systems)

    return filepath


def suggest_memory_updates(summary: str, decisions: str, feedback: str, systems: str):
    """Suggest which persistent memory files might need updating based on session content."""
    all_text = f"{summary} {decisions} {feedback} {systems}".lower()

    suggestions = []

    keyword_map = {
        "editorial": "ai_property_editorial_system.md or editorial_pipeline_iteration.md",
        "valuation": "valuation_directional.md",
        "facebook": "fb_ads_experimentation_playbook.md or fb_ad_review_system.md",
        "google ads": "MEMORY.md (Google Ads section)",
        "pipeline": "watchdog_patterns.md",
        "website": "website_intelligence_system.md or website_ssr_seo.md",
        "voice agent": "voice_agent_system.md",
        "ceo agent": "ceo_agent_system.md",
        "posthog": "posthog_analytics.md",
        "market pulse": "market_pulse_workflow.md",
        "knowledge base": "knowledge_base_system.md",
        "experiment": "active_experiments.md",
        "scraper": "backup_scraper_system.md",
        "email": "email_agent_integration.md",
        "flood": "ai_property_editorial_system.md (flood section)",
        "content strategy": "content_curation_over_choice.md or content_information_gap.md",
        "decision feed": "decision_feed_product.md",
        "crash risk": "crash_risk_chart_data_review.md",
        "cosmos": "cosmos_ru_retry_strategy.md",
        "will's prefer": "claude_code_will_patterns.md",
        "business model": "business_model.md",
        "branding": "feedback_branding_slogan.md",
    }

    for keyword, file_suggestion in keyword_map.items():
        if keyword in all_text:
            suggestions.append(f"  - {file_suggestion} (matched: '{keyword}')")

    if suggestions:
        for s in suggestions:
            print(s)
    else:
        print("  No specific topic files matched. Check if MEMORY.md needs a new section.")


def review_recent_sessions(days: int = 7):
    """Show recent session logs for review."""
    ensure_dirs()
    now = get_timestamp()

    logs = sorted(SESSION_LOG_DIR.glob("*.md"), reverse=True)
    cutoff = now - timedelta(days=days)

    print(f"Session logs from the last {days} days:\n")

    found = 0
    for log in logs:
        date_part = log.stem.split("_")[0]
        try:
            log_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=AEST)
            if log_date >= cutoff:
                print(f"--- {log.name} ---")
                print(log.read_text()[:500])
                print()
                found += 1
        except ValueError:
            continue

    if found == 0:
        print("No session logs found in this period.")


def count_memory_stats():
    """Show memory system statistics."""
    topic_files = list(MEMORY_DIR.glob("*.md"))
    session_logs = list(SESSION_LOG_DIR.glob("*.md")) if SESSION_LOG_DIR.exists() else []

    total_size = sum(f.stat().st_size for f in topic_files)
    memory_lines = MEMORY_INDEX.read_text().count("\n") if MEMORY_INDEX.exists() else 0

    print(f"Memory System Stats:")
    print(f"  Topic files: {len(topic_files)}")
    print(f"  Session logs: {len(session_logs)}")
    print(f"  MEMORY.md lines: {memory_lines}/200 (max)")
    print(f"  Total memory size: {total_size / 1024:.1f} KB")

    # Check for stale files (not updated in 14+ days)
    now = get_timestamp()
    stale = []
    for f in topic_files:
        if f.name == "MEMORY.md":
            continue
        age_days = (now.timestamp() - f.stat().st_mtime) / 86400
        if age_days > 14:
            stale.append((f.name, int(age_days)))

    if stale:
        print(f"\n  Potentially stale files (>14 days old):")
        for name, age in sorted(stale, key=lambda x: -x[1]):
            print(f"    {name} — {age} days old")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Session Memory Logger")
    parser.add_argument("--summary", help="What happened this session")
    parser.add_argument("--decisions", default="", help="Key decisions made")
    parser.add_argument("--feedback", default="", help="Will's feedback received")
    parser.add_argument("--systems", default="", help="Systems built or changed")
    parser.add_argument("--notes", default="", help="Additional notes")
    parser.add_argument("--from-file", help="Read notes from a file")
    parser.add_argument("--review", type=int, nargs="?", const=7, help="Review recent sessions (default: 7 days)")
    parser.add_argument("--stats", action="store_true", help="Show memory system stats")

    args = parser.parse_args()

    if args.stats:
        count_memory_stats()
    elif args.review is not None:
        review_recent_sessions(args.review)
    elif args.from_file:
        notes = Path(args.from_file).read_text()
        log_session(summary=notes[:500], raw_notes=notes)
    elif args.summary:
        log_session(
            summary=args.summary,
            decisions=args.decisions,
            feedback=args.feedback,
            systems=args.systems,
            raw_notes=args.notes,
        )
    else:
        parser.print_help()
