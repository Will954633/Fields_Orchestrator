#!/usr/bin/env python3
"""Morning Focus Analyser — Sprint-aware CEO proposal triage.

Reads the daily CEO agent summary and the current sprint plan, then triages
proposals into three buckets:
  - ai_doing_now:    safe internal engineering/data tasks aligned with sprint
  - needs_approval:  budget, ads, product, public-facing, or low-confidence items
  - noted_for_later: outside current sprint, low priority, or deferred

Usage:
  python3 scripts/morning-focus-analyser.py
  python3 scripts/morning-focus-analyser.py --date 2026-03-30
  python3 scripts/morning-focus-analyser.py --output /tmp/morning-brief.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path("/home/fields/Fields_Orchestrator")
SUMMARY_PATH = BASE_DIR / "artifacts" / "ceo-runs" / "LATEST_SUMMARY.md"
SPRINTS_DIR = BASE_DIR / "07_Focus" / "sprints"

# ---------------------------------------------------------------------------
# Q3 target date (June 30 end of quarter)
# ---------------------------------------------------------------------------
Q3_END = date(2026, 6, 30)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class SprintInfo:
    number: int
    title: str
    theme: str
    week_of: str
    q3_countdown: int
    goal_progress: str


@dataclass
class DayCheckpoint:
    date_str: str  # YYYY-MM-DD
    day_label: str  # e.g. "Tuesday March 31"
    checkpoint: Optional[str] = None
    grind: Optional[str] = None
    content: Optional[str] = None
    ai_parallel: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    agent: str
    title: str
    priority: str  # HIGH, MEDIUM, LOW, CRITICAL
    owner: str
    time_horizon: str
    decision_required: bool
    problem: str
    proposal_text: str
    confidence: str
    depends_on: str
    blocked_by: str


@dataclass
class Finding:
    agent: str
    priority: str
    title: str
    summary: str


# ---------------------------------------------------------------------------
# Sprint plan parsing
# ---------------------------------------------------------------------------
def find_current_sprint(target: date) -> Optional[Path]:
    """Find which sprint file covers the target date."""
    for sprint_file in sorted(SPRINTS_DIR.glob("sprint-??.md")):
        text = sprint_file.read_text(encoding="utf-8")
        # Parse "Week of: March 31 — April 4, 2026" or similar
        week_match = re.search(r"\*\*Week of:\*\*\s*(.+)", text)
        if not week_match:
            continue
        week_str = week_match.group(1).strip()
        # Try to extract start and end dates from the week string
        # Format: "March 31 — April 4, 2026" or "April 7-11, 2026"
        sprint_dates = extract_sprint_dates(text, target.year)
        if sprint_dates:
            start, end = sprint_dates
            # Give a 1-day buffer on each side (Saturday catchup, Sunday before)
            if start - timedelta(days=1) <= target <= end + timedelta(days=1):
                return sprint_file
    # Fallback: return the latest sprint
    files = sorted(SPRINTS_DIR.glob("sprint-??.md"))
    return files[-1] if files else None


def extract_sprint_dates(text: str, year: int) -> Optional[tuple[date, date]]:
    """Extract (start_date, end_date) from sprint markdown."""
    # Find all ### Day Month DD lines to get the date range
    day_headings = re.findall(
        r"^### (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) (\w+ \d+)",
        text, re.MULTILINE,
    )
    if not day_headings:
        return None
    try:
        first = datetime.strptime(f"{day_headings[0]} {year}", "%B %d %Y").date()
        last = datetime.strptime(f"{day_headings[-1]} {year}", "%B %d %Y").date()
        return first, last
    except ValueError:
        return None


def parse_sprint_info(text: str) -> SprintInfo:
    """Extract sprint header metadata."""
    num_match = re.search(r"^# Sprint (\d+) — (.+)$", text, re.MULTILINE)
    number = int(num_match.group(1)) if num_match else 0
    title = num_match.group(2).strip() if num_match else "Unknown"

    theme_match = re.search(r"\*\*Theme:\*\*\s*(.+)", text)
    theme = theme_match.group(1).strip() if theme_match else title

    week_match = re.search(r"\*\*Week of:\*\*\s*(.+)", text)
    week_of = week_match.group(1).strip() if week_match else "Unknown"

    q3_match = re.search(r"\*\*Q3 countdown:\*\*\s*(\d+)", text)
    q3_countdown = int(q3_match.group(1)) if q3_match else (Q3_END - date.today()).days

    goal_match = re.search(r"\*\*Goal 1 progress:\*\*\s*(.+)", text)
    goal_progress = goal_match.group(1).strip() if goal_match else "Unknown"

    return SprintInfo(
        number=number,
        title=title,
        theme=theme,
        week_of=week_of,
        q3_countdown=q3_countdown,
        goal_progress=goal_progress,
    )


def parse_day_checkpoint(text: str, target: date) -> Optional[DayCheckpoint]:
    """Find the checkpoint block for a specific date in the sprint plan."""
    year = target.year
    # Find all day headings
    pattern = r"^### ((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) (\w+ \d+))(?:\s*\(([^)]+)\))?"
    matches = list(re.finditer(pattern, text, re.MULTILINE))

    for i, match in enumerate(matches):
        day_label = match.group(1)
        month_day = match.group(2)
        try:
            heading_date = datetime.strptime(f"{month_day} {year}", "%B %d %Y").date()
        except ValueError:
            continue

        if heading_date != target:
            continue

        # Extract the block between this heading and the next
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        checkpoint = DayCheckpoint(
            date_str=target.isoformat(),
            day_label=day_label,
        )

        # Parse CHECKPOINT
        cp_match = re.search(r"\*\*CHECKPOINT:\*\*\s*(.+)", block)
        if cp_match:
            checkpoint.checkpoint = cp_match.group(1).strip()

        # Parse checklist items under CHECKPOINT
        cp_section = block
        tasks_match = re.search(r"\*\*CHECKPOINT:\*\*.*?\n((?:\s*- \[.\].*\n)*)", block)
        if tasks_match:
            for task_line in tasks_match.group(1).strip().split("\n"):
                task_line = task_line.strip()
                if task_line.startswith("- ["):
                    checkpoint.tasks.append(task_line)

        # Parse GRIND
        grind_match = re.search(r"\*\*GRIND:\*\*\s*(.+)", block)
        if grind_match:
            checkpoint.grind = grind_match.group(1).strip()

        # Parse CONTENT
        content_match = re.search(r"\*\*CONTENT:\*\*\s*(.+)", block)
        if content_match:
            checkpoint.content = content_match.group(1).strip()

        # Parse AI parallel tasks
        ai_match = re.search(
            r"\*\*AI does in parallel[^*]*:\*\*\s*\n((?:\s*-\s+.+\n)*)",
            block,
        )
        if ai_match:
            for line in ai_match.group(1).strip().split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    checkpoint.ai_parallel.append(line[2:].strip())

        return checkpoint

    return None


def find_yesterday_checkpoint(text: str, target: date) -> Optional[DayCheckpoint]:
    """Find yesterday's checkpoint for status review."""
    yesterday = target - timedelta(days=1)
    # Skip weekends
    if yesterday.weekday() >= 5:  # Saturday or Sunday
        yesterday = yesterday - timedelta(days=yesterday.weekday() - 4)
    return parse_day_checkpoint(text, yesterday)


# ---------------------------------------------------------------------------
# LATEST_SUMMARY.md parsing
# ---------------------------------------------------------------------------
def parse_summary_header(text: str) -> dict:
    """Parse header metadata from LATEST_SUMMARY.md."""
    info = {}
    date_match = re.search(r"^- Date: `(.+?)`", text, re.MULTILINE)
    if date_match:
        info["date"] = date_match.group(1)
    gen_match = re.search(r"^- Generated: `(.+?)`", text, re.MULTILINE)
    if gen_match:
        info["generated"] = gen_match.group(1)
    status_match = re.search(r"^- Run status: `(.+?)`", text, re.MULTILINE)
    if status_match:
        info["status"] = status_match.group(1)
    agents_match = re.search(r"^- Agents with proposals: `(.+?)`", text, re.MULTILINE)
    if agents_match:
        info["agents"] = agents_match.group(1)
    return info


def parse_proposals(text: str) -> list[Proposal]:
    """Extract all proposals from the summary markdown."""
    proposals = []
    # Split by agent sections (## Agent Name)
    agent_sections = re.split(r"^## (\w[\w\s]+)$", text, flags=re.MULTILINE)

    # agent_sections[0] is header, then alternating: agent_name, section_content
    for i in range(1, len(agent_sections) - 1, 2):
        agent_name = agent_sections[i].strip().lower().replace(" ", "_")
        section = agent_sections[i + 1]

        # Skip Agent Status section
        if agent_name == "agent_status":
            continue

        # Find the ### Proposals subsection
        proposals_match = re.search(
            r"^### Proposals\s*\n(.*?)(?=^### |\Z)",
            section,
            re.MULTILINE | re.DOTALL,
        )
        if not proposals_match:
            continue

        proposals_block = proposals_match.group(1)

        # Each proposal starts with "- [PRIORITY] **Title**"
        prop_pattern = re.compile(
            r"^- \[(\w+)\] \*\*(.+?)\*\*\s*\n(.*?)(?=^- \[|\Z)",
            re.MULTILINE | re.DOTALL,
        )

        for pm in prop_pattern.finditer(proposals_block):
            priority = pm.group(1).strip()
            title = pm.group(2).strip()
            body = pm.group(3)

            problem = _extract_field(body, "Problem")
            proposal_text = _extract_field(body, "Proposal")
            owner = _extract_field(body, "Owner") or agent_name
            time_horizon = _extract_field(body, "Time horizon") or "unknown"
            decision_str = _extract_field(body, "Decision required") or "False"
            confidence = _extract_field(body, "Confidence") or "unknown"
            depends_on = _extract_field(body, "Depends on") or "None"
            blocked_by = _extract_field(body, "Blocked by") or "None"

            # Parse the combined Owner | Time horizon | Decision required line
            combo_match = re.search(
                r"Owner:\s*`([^`]+)`\s*\|\s*Time horizon:\s*`([^`]+)`\s*\|\s*Decision required:\s*`([^`]+)`",
                body,
            )
            if combo_match:
                owner = combo_match.group(1).strip()
                time_horizon = combo_match.group(2).strip()
                decision_str = combo_match.group(3).strip()

            conf_match = re.search(r"Confidence:\s*`([^`]+)`", body)
            if conf_match:
                confidence = conf_match.group(1).strip()

            dep_match = re.search(r"Depends on:\s*(.+?)(?:\n|$)", body)
            if dep_match:
                depends_on = dep_match.group(1).strip()

            blocked_match = re.search(r"Blocked by:\s*(.+?)(?:\n|$)", body)
            if blocked_match:
                blocked_by = blocked_match.group(1).strip()

            proposals.append(Proposal(
                agent=agent_name,
                title=title,
                priority=priority,
                owner=owner,
                time_horizon=time_horizon,
                decision_required=decision_str.lower() == "true",
                problem=problem or "",
                proposal_text=proposal_text or "",
                confidence=confidence,
                depends_on=depends_on,
                blocked_by=blocked_by,
            ))

    return proposals


def parse_findings(text: str) -> list[Finding]:
    """Extract top findings from each agent section."""
    findings = []
    agent_sections = re.split(r"^## (\w[\w\s]+)$", text, flags=re.MULTILINE)

    for i in range(1, len(agent_sections) - 1, 2):
        agent_name = agent_sections[i].strip().lower().replace(" ", "_")
        section = agent_sections[i + 1]

        if agent_name == "agent_status":
            continue

        findings_match = re.search(
            r"^### Findings\s*\n(.*?)(?=^### |\Z)",
            section,
            re.MULTILINE | re.DOTALL,
        )
        if not findings_match:
            continue

        finding_pattern = re.compile(
            r"^- \[(\w+)\] \*\*(.+?)\*\*\s*\n(.*?)(?=^- \[|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        for fm in finding_pattern.finditer(findings_match.group(1)):
            # Just grab the first line of the finding body as summary
            body_lines = [l.strip() for l in fm.group(3).strip().split("\n") if l.strip() and not l.strip().startswith("Recommendation:") and not l.strip().startswith("Confidence:") and not l.strip().startswith("Blocked by:") and not l.strip().startswith("Data gaps:")]
            summary = body_lines[0] if body_lines else ""
            findings.append(Finding(
                agent=agent_name,
                priority=fm.group(1).strip(),
                title=fm.group(2).strip(),
                summary=summary[:200],
            ))

    return findings


def parse_chief_of_staff_notes(text: str) -> dict:
    """Extract Top 3 and Do-not-do from Chief of Staff notes."""
    notes = {"top3": [], "do_not_do": []}

    cos_match = re.search(
        r"^### Chief Of Staff Notes\s*\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not cos_match:
        return notes

    block = cos_match.group(1)

    # Top 3 — they're Python dict-like strings in the markdown
    top3_match = re.search(r"Top 3:\s*\n(.*?)(?=Do not do:|\Z)", block, re.DOTALL)
    if top3_match:
        for line in top3_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- {"):
                # Extract title from the dict-like string
                title_match = re.search(r"'title':\s*'([^']+)'", line)
                owner_match = re.search(r"'owner':\s*'([^']+)'", line)
                if title_match:
                    notes["top3"].append({
                        "title": title_match.group(1),
                        "owner": owner_match.group(1) if owner_match else "unknown",
                    })

    # Do not do
    dnd_match = re.search(r"Do not do:\s*\n(.*?)(?=Recommended sequence:|\Z)", block, re.DOTALL)
    if dnd_match:
        for line in dnd_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                notes["do_not_do"].append(line[2:].strip())

    return notes


def _extract_field(body: str, field_name: str) -> Optional[str]:
    """Extract a simple field value from proposal body."""
    match = re.search(rf"{re.escape(field_name)}:\s*(.+?)(?:\n|$)", body)
    if match:
        val = match.group(1).strip()
        # Strip backticks
        val = val.strip("`")
        return val
    return None


# ---------------------------------------------------------------------------
# Triage logic
# ---------------------------------------------------------------------------

# Keywords that indicate public-facing / budget / ad changes
APPROVAL_KEYWORDS = {
    "ad", "ads", "meta", "google", "facebook", "cta", "website", "page",
    "article", "content", "youtube", "feed", "pricing", "customer",
    "landing", "campaign", "budget", "spend", "funnel", "badge",
    "trust", "messaging",
}

# Owners that always need approval
APPROVAL_OWNERS = {"will", "growth", "product"}

# Safe engineering owners
SAFE_OWNERS = {"engineering", "data_quality", "chief_of_staff"}


def triage_proposal(proposal: Proposal, sprint_theme: str, day_checkpoint: Optional[DayCheckpoint]) -> tuple[str, str]:
    """Triage a proposal into a bucket. Returns (bucket, reason)."""

    title_lower = proposal.title.lower()
    problem_lower = proposal.problem.lower()
    combined = f"{title_lower} {problem_lower} {proposal.proposal_text.lower()}"
    tokens = set(re.findall(r"[a-z0-9]+", combined))

    # 1. Deferred items go to noted_for_later
    if proposal.time_horizon in ("later", "next_sprint", "next_week"):
        return "noted_for_later", f"deferred ({proposal.time_horizon})"

    if proposal.priority == "LOW":
        return "noted_for_later", "low priority"

    # 2. Anything owned by Will or requiring a decision -> needs_approval
    if proposal.owner.lower() in APPROVAL_OWNERS:
        return "needs_approval", f"owner is {proposal.owner}"

    if proposal.decision_required:
        return "needs_approval", "decision required"

    # 3. Public-facing keyword check
    if tokens & APPROVAL_KEYWORDS:
        matching = tokens & APPROVAL_KEYWORDS
        return "needs_approval", f"touches public-facing area ({', '.join(sorted(matching)[:3])})"

    # 4. Low confidence -> needs_approval
    if proposal.confidence in ("low", "medium"):
        return "needs_approval", f"confidence is {proposal.confidence}"

    # 5. Safe internal engineering work
    if proposal.owner.lower() in SAFE_OWNERS and proposal.priority in ("HIGH", "CRITICAL"):
        # Check alignment with sprint theme
        sprint_tokens = set(re.findall(r"[a-z0-9]+", sprint_theme.lower()))
        if sprint_tokens & tokens:
            return "ai_doing_now", "high-confidence engineering work aligned with sprint"
        return "ai_doing_now", "safe internal engineering work"

    # 6. Medium priority, this_week horizon
    if proposal.time_horizon == "this_week" and proposal.priority == "MEDIUM":
        return "noted_for_later", "medium priority, this_week — review later"

    # Default: needs_approval (safe default)
    return "needs_approval", "default — review needed"


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def format_brief(
    target: date,
    sprint: SprintInfo,
    day_cp: Optional[DayCheckpoint],
    yesterday_cp: Optional[DayCheckpoint],
    proposals: list[Proposal],
    findings: list[Finding],
    cos_notes: dict,
    summary_header: dict,
    buckets: dict[str, list[tuple[Proposal, str]]],
) -> str:
    """Format the morning checkpoint brief."""
    lines = []
    q3_days = (Q3_END - target).days

    # Header
    lines.append("=" * 68)
    lines.append(f"  MORNING FOCUS BRIEF — {target.strftime('%A %B %d, %Y')}")
    lines.append("=" * 68)
    lines.append("")
    lines.append(f"  Q3 countdown:    {q3_days} days")
    lines.append(f"  Sprint {sprint.number}:       {sprint.title}")
    lines.append(f"  Sprint theme:    {sprint.theme}")
    lines.append(f"  Goal progress:   {sprint.goal_progress}")
    lines.append("")

    # CEO run info
    if summary_header:
        lines.append(f"  CEO run:         {summary_header.get('date', 'unknown')} ({summary_header.get('status', 'unknown')})")
        lines.append(f"  Generated:       {summary_header.get('generated', 'unknown')}")
        lines.append(f"  Agents:          {summary_header.get('agents', 'unknown')}")
        lines.append("")

    lines.append("-" * 68)

    # Today's checkpoint
    if day_cp:
        lines.append("")
        lines.append(f"  TODAY'S CHECKPOINT: {day_cp.day_label}")
        lines.append(f"  {'-' * 40}")
        if day_cp.checkpoint:
            lines.append(f"  Goal: {day_cp.checkpoint}")
        lines.append("")
        if day_cp.tasks:
            lines.append("  Tasks:")
            for task in day_cp.tasks:
                lines.append(f"    {task}")
            lines.append("")
        if day_cp.grind:
            lines.append(f"  GRIND: {day_cp.grind}")
        if day_cp.content:
            lines.append(f"  CONTENT: {day_cp.content}")
        if day_cp.ai_parallel:
            lines.append("")
            lines.append("  AI parallel (no Will needed):")
            for task in day_cp.ai_parallel:
                lines.append(f"    - {task}")
        lines.append("")
    else:
        lines.append("")
        lines.append(f"  No sprint checkpoint for {target.strftime('%A %B %d')}")
        lines.append("  (This date is outside the current sprint schedule)")
        lines.append("")

    lines.append("-" * 68)

    # Chief of Staff top 3
    if cos_notes.get("top3"):
        lines.append("")
        lines.append("  CHIEF OF STAFF — TOP 3 PRIORITIES")
        lines.append(f"  {'-' * 40}")
        for i, item in enumerate(cos_notes["top3"], 1):
            lines.append(f"  {i}. [{item['owner'].upper()}] {item['title']}")
        lines.append("")

    # Do not do
    if cos_notes.get("do_not_do"):
        lines.append("  DO NOT DO:")
        for item in cos_notes["do_not_do"]:
            lines.append(f"    x {item}")
        lines.append("")

    lines.append("-" * 68)

    # Bucket: AI doing now
    lines.append("")
    ai_items = buckets.get("ai_doing_now", [])
    lines.append(f"  AI DOING NOW ({len(ai_items)} items)")
    lines.append(f"  {'-' * 40}")
    if ai_items:
        for proposal, reason in ai_items:
            lines.append(f"  [{proposal.priority}] {proposal.title}")
            lines.append(f"    Agent: {proposal.agent} | Owner: {proposal.owner}")
            lines.append(f"    Reason: {reason}")
            lines.append("")
    else:
        lines.append("  (none — all proposals need review or are deferred)")
        lines.append("")

    # Bucket: Needs approval
    approval_items = buckets.get("needs_approval", [])
    lines.append(f"  NEEDS WILL'S APPROVAL ({len(approval_items)} items)")
    lines.append(f"  {'-' * 40}")
    if approval_items:
        for proposal, reason in approval_items:
            lines.append(f"  [{proposal.priority}] {proposal.title}")
            lines.append(f"    Agent: {proposal.agent} | Owner: {proposal.owner} | Horizon: {proposal.time_horizon}")
            if proposal.problem:
                # Truncate long problem statements
                problem_short = proposal.problem[:150]
                if len(proposal.problem) > 150:
                    problem_short += "..."
                lines.append(f"    Problem: {problem_short}")
            lines.append(f"    Triage reason: {reason}")
            lines.append("")
    else:
        lines.append("  (none)")
        lines.append("")

    # Bucket: Noted for later
    later_items = buckets.get("noted_for_later", [])
    lines.append(f"  NOTED FOR LATER ({len(later_items)} items)")
    lines.append(f"  {'-' * 40}")
    if later_items:
        for proposal, reason in later_items:
            lines.append(f"  [{proposal.priority}] {proposal.title}")
            lines.append(f"    Agent: {proposal.agent} | Reason: {reason}")
        lines.append("")
    else:
        lines.append("  (none)")
        lines.append("")

    lines.append("-" * 68)

    # Key findings summary (CRITICAL and HIGH only)
    critical_findings = [f for f in findings if f.priority in ("CRITICAL", "HIGH")]
    if critical_findings:
        lines.append("")
        lines.append(f"  KEY FINDINGS ({len(critical_findings)} critical/high)")
        lines.append(f"  {'-' * 40}")
        for f in critical_findings:
            lines.append(f"  [{f.priority}] [{f.agent}] {f.title}")
        lines.append("")

    # Yesterday's checkpoint
    if yesterday_cp:
        lines.append("-" * 68)
        lines.append("")
        lines.append(f"  YESTERDAY: {yesterday_cp.day_label}")
        lines.append(f"  {'-' * 40}")
        if yesterday_cp.checkpoint:
            lines.append(f"  Was: {yesterday_cp.checkpoint}")
        if yesterday_cp.tasks:
            lines.append("  Tasks were:")
            for task in yesterday_cp.tasks:
                lines.append(f"    {task}")
        lines.append("")

    lines.append("=" * 68)
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    lines.append("=" * 68)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Morning Focus Analyser — sprint-aware CEO proposal triage",
    )
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD). Defaults to today AEST.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=SUMMARY_PATH,
        help=f"Path to LATEST_SUMMARY.md (default: {SUMMARY_PATH})",
    )
    parser.add_argument(
        "--sprint",
        type=Path,
        help="Path to sprint plan. Auto-detected if not specified.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file path. Also prints to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted text.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Determine target date
    if args.date:
        target = date.fromisoformat(args.date)
    else:
        # Use AEST
        try:
            from zoneinfo import ZoneInfo
            target = datetime.now(ZoneInfo("Australia/Brisbane")).date()
        except ImportError:
            target = date.today()

    # Find and read sprint plan
    sprint_path = args.sprint or find_current_sprint(target)
    if not sprint_path or not sprint_path.exists():
        print(f"ERROR: No sprint plan found for {target}", file=sys.stderr)
        print(f"Looked in: {SPRINTS_DIR}", file=sys.stderr)
        sys.exit(1)

    sprint_text = sprint_path.read_text(encoding="utf-8")
    sprint = parse_sprint_info(sprint_text)

    # Parse day checkpoints
    day_cp = parse_day_checkpoint(sprint_text, target)
    yesterday_cp = find_yesterday_checkpoint(sprint_text, target)

    # Read and parse CEO summary
    summary_text = ""
    summary_header = {}
    proposals = []
    findings = []
    cos_notes = {"top3": [], "do_not_do": []}

    if args.summary.exists():
        summary_text = args.summary.read_text(encoding="utf-8")
        summary_header = parse_summary_header(summary_text)
        proposals = parse_proposals(summary_text)
        findings = parse_findings(summary_text)
        cos_notes = parse_chief_of_staff_notes(summary_text)
    else:
        print(f"WARNING: Summary not found at {args.summary}", file=sys.stderr)

    # Triage proposals
    buckets: dict[str, list[tuple[Proposal, str]]] = {
        "ai_doing_now": [],
        "needs_approval": [],
        "noted_for_later": [],
    }

    seen_titles = set()
    for proposal in proposals:
        # Deduplicate by title (agents often echo the same proposal)
        if proposal.title in seen_titles:
            continue
        seen_titles.add(proposal.title)

        bucket, reason = triage_proposal(proposal, sprint.theme, day_cp)
        buckets[bucket].append((proposal, reason))

    # Sort each bucket: CRITICAL > HIGH > MEDIUM > LOW
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    for bucket in buckets.values():
        bucket.sort(key=lambda x: (priority_order.get(x[0].priority, 9), x[0].title))

    if args.json:
        import json
        output = {
            "date": target.isoformat(),
            "q3_countdown": (Q3_END - target).days,
            "sprint": {
                "number": sprint.number,
                "title": sprint.title,
                "theme": sprint.theme,
            },
            "checkpoint": {
                "label": day_cp.day_label if day_cp else None,
                "goal": day_cp.checkpoint if day_cp else None,
                "grind": day_cp.grind if day_cp else None,
            },
            "summary_date": summary_header.get("date"),
            "buckets": {
                name: [
                    {"agent": p.agent, "title": p.title, "priority": p.priority,
                     "owner": p.owner, "reason": r}
                    for p, r in items
                ]
                for name, items in buckets.items()
            },
            "proposal_count": len(proposals),
            "top3": cos_notes.get("top3", []),
        }
        print(json.dumps(output, indent=2))
    else:
        brief = format_brief(
            target=target,
            sprint=sprint,
            day_cp=day_cp,
            yesterday_cp=yesterday_cp,
            proposals=proposals,
            findings=findings,
            cos_notes=cos_notes,
            summary_header=summary_header,
            buckets=buckets,
        )
        print(brief)

        if args.output:
            args.output.write_text(brief, encoding="utf-8")
            print(f"\nSaved to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
