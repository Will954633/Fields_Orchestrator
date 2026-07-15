#!/usr/bin/env python3
"""Prototype morning analyser for sprint-aware CEO proposal triage.

This script is intentionally lightweight. It can:

1. Read the sprint plan markdown and extract the checkpoint/grind/content block
   for a specific date.
2. Load proposal inputs from JSON proposal files for that date.
3. Optionally attempt a best-effort parse of `LATEST_SUMMARY.md` style markdown.
4. Bucket items into:
   - `ai_doing_now`
   - `needs_approval`
   - `noted_for_later`

The markdown summary parser is heuristic because the exported workspace does not
currently include a real `LATEST_SUMMARY.md` artifact. In this sandbox, the JSON
proposal files under `proposals/` are the most reliable input source.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


DATE_HEADING_RE = re.compile(r"^### ([A-Za-z]+) ([A-Za-z]+ \d+)(?: \(([^)]+)\))?$", re.MULTILINE)
SPRINT_HEADER_RE = re.compile(r"^# Sprint (\d+) — (.+)$", re.MULTILINE)


@dataclass
class SprintCheckpoint:
    sprint_number: int
    sprint_title: str
    sprint_theme: str | None
    checkpoint_date: str
    checkpoint_label: str
    checkpoint: str | None
    grind: str | None
    content: str | None
    ai_parallel: list[str] = field(default_factory=list)


@dataclass
class ProposalItem:
    agent: str
    title: str
    owner: str
    proposal_type: str
    decision_required: bool
    effort: str | None
    confidence: str | None
    time_horizon: str | None
    priority_score: int | None
    problem: str | None
    source_file: str


def normalise_token(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Target date in YYYY-MM-DD format.")
    parser.add_argument(
        "--proposal-date",
        help="Optional proposal date in YYYY-MM-DD format. Defaults to --date.",
    )
    parser.add_argument(
        "--sprint-plan",
        required=True,
        type=Path,
        help="Path to sprint_plans.md.",
    )
    parser.add_argument(
        "--proposals-dir",
        type=Path,
        default=Path("proposals"),
        help="Directory containing YYYY-MM-DD_agent.json proposal files.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="Optional LATEST_SUMMARY.md path. Parsed heuristically if present.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_sprint_checkpoints(markdown: str, year: int) -> list[SprintCheckpoint]:
    matches = list(SPRINT_HEADER_RE.finditer(markdown))
    checkpoints: list[SprintCheckpoint] = []

    for index, match in enumerate(matches):
        sprint_number = int(match.group(1))
        sprint_title = match.group(2).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sprint_block = markdown[start:end]

        theme_match = re.search(r"^\> \*\*Theme:\*\* (.+)$", sprint_block, re.MULTILINE)
        sprint_theme = theme_match.group(1).strip() if theme_match else None

        date_matches = list(DATE_HEADING_RE.finditer(sprint_block))
        for date_index, date_match in enumerate(date_matches):
            label = date_match.group(1)
            month_day = date_match.group(2)
            optional_note = date_match.group(3)
            block_start = date_match.start()
            block_end = (
                date_matches[date_index + 1].start()
                if date_index + 1 < len(date_matches)
                else len(sprint_block)
            )
            block = sprint_block[block_start:block_end]
            checkpoint_date = datetime.strptime(
                f"{label} {month_day} {year}",
                "%A %B %d %Y",
            ).date()
            ai_parallel = parse_ai_parallel(block)
            checkpoints.append(
                SprintCheckpoint(
                    sprint_number=sprint_number,
                    sprint_title=sprint_title,
                    sprint_theme=sprint_theme,
                    checkpoint_date=checkpoint_date.isoformat(),
                    checkpoint_label=f"{label} {month_day}" + (f" ({optional_note})" if optional_note else ""),
                    checkpoint=parse_inline_field(block, "CHECKPOINT"),
                    grind=parse_inline_field(block, "GRIND"),
                    content=parse_inline_field(block, "CONTENT"),
                    ai_parallel=ai_parallel,
                )
            )

    return checkpoints


def parse_inline_field(block: str, field_name: str) -> str | None:
    match = re.search(rf"\*\*{re.escape(field_name)}:\*\* (.+)", block)
    if not match:
        return None
    return match.group(1).strip()


def parse_ai_parallel(block: str) -> list[str]:
    match = re.search(
        r"\*\*AI (?:does in parallel|parallel)(?:[^*]*)\:\*\*(.*?)(?:\n\*\*GRIND:\*\*|\Z)",
        block,
        re.DOTALL,
    )
    if not match:
        return []
    lines = []
    for raw_line in match.group(1).splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    return lines


def load_proposals_for_date(proposals_dir: Path, target_date: str) -> list[ProposalItem]:
    items: list[ProposalItem] = []
    for path in sorted(proposals_dir.glob(f"{target_date}_*.json")):
        payload = json.loads(read_text(path))
        agent = str(payload.get("agent", path.stem.split("_", 1)[-1]))
        for proposal in payload.get("proposals", []):
            items.append(
                ProposalItem(
                    agent=agent,
                    title=str(proposal.get("title", "")).strip(),
                    owner=str(proposal.get("owner", agent)).strip(),
                    proposal_type=str(proposal.get("type", "unknown")).strip(),
                    decision_required=bool(proposal.get("decision_required", False)),
                    effort=proposal.get("effort"),
                    confidence=proposal.get("confidence"),
                    time_horizon=proposal.get("time_horizon"),
                    priority_score=int(proposal["priority_score"]) if proposal.get("priority_score") is not None else None,
                    problem=proposal.get("problem"),
                    source_file=str(path),
                )
            )
    return items


def parse_summary_markdown(summary_path: Path) -> list[ProposalItem]:
    if not summary_path.exists():
        return []

    text = read_text(summary_path)
    items: list[ProposalItem] = []
    current_agent = "unknown"

    for line in text.splitlines():
        agent_match = re.match(r"^##+\s+([A-Za-z _-]+)$", line.strip())
        if agent_match:
            current_agent = agent_match.group(1).strip().lower().replace(" ", "_")
            continue

        bullet_match = re.match(
            r"^- \[(?P<owner>[A-Za-z_ -]+)\]\s+(?P<title>.+?)(?:\s+\((?P<meta>.+)\))?$",
            line.strip(),
        )
        if not bullet_match:
            continue

        meta = bullet_match.group("meta") or ""
        items.append(
            ProposalItem(
                agent=current_agent,
                title=bullet_match.group("title").strip(),
                owner=bullet_match.group("owner").strip().lower().replace(" ", "_"),
                proposal_type="summary_item",
                decision_required="approval" in meta.lower() or "decide" in meta.lower(),
                effort=None,
                confidence="high" if "high" in meta.lower() else None,
                time_horizon="today" if "today" in meta.lower() else None,
                priority_score=None,
                problem=None,
                source_file=str(summary_path),
            )
        )

    return items


def token_overlap_score(checkpoint: SprintCheckpoint, proposal: ProposalItem) -> float:
    checkpoint_tokens = set(
        normalise_token(
            " ".join(
                value
                for value in (
                    checkpoint.sprint_title,
                    checkpoint.sprint_theme or "",
                    checkpoint.checkpoint or "",
                    checkpoint.grind or "",
                    " ".join(checkpoint.ai_parallel),
                )
            )
        )
    )
    proposal_tokens = set(normalise_token(" ".join(filter(None, [proposal.title, proposal.problem or ""]))))
    if not checkpoint_tokens or not proposal_tokens:
        return 0.0
    return len(checkpoint_tokens & proposal_tokens) / len(proposal_tokens)


def is_approval_type(proposal: ProposalItem) -> bool:
    approval_types = {
        "budget_reallocation",
        "experiment",
        "content_strategy",
        "pricing",
        "product_decision",
        "campaign_change",
    }
    if proposal.proposal_type in approval_types:
        return True
    if proposal.owner in {"will", "growth", "product"}:
        return True
    return proposal.decision_required


def is_safe_internal_work(proposal: ProposalItem) -> bool:
    safe_types = {
        "guardrail",
        "pipeline_fix",
        "monitoring",
        "config_change",
        "code_change",
        "investigation",
        "implementation",
        "defer",
    }
    public_change_tokens = {
        "ad",
        "ads",
        "meta",
        "google",
        "cta",
        "website",
        "page",
        "article",
        "content",
        "youtube",
        "feed",
        "report",
        "pricing",
        "customer",
    }
    tokens = set(normalise_token(" ".join(filter(None, [proposal.title, proposal.problem or ""]))))
    return (
        proposal.owner in {"engineering", "data_quality", "chief_of_staff"}
        and proposal.proposal_type in safe_types
        and not (tokens & public_change_tokens)
    )


def bucket_proposal(checkpoint: SprintCheckpoint, proposal: ProposalItem) -> tuple[str, str]:
    alignment = token_overlap_score(checkpoint, proposal)

    if proposal.time_horizon and proposal.time_horizon not in {"today", "this_week"}:
        return "noted_for_later", "outside immediate horizon"

    if alignment < 0.08:
        return "noted_for_later", "weak alignment to today's checkpoint"

    if is_safe_internal_work(proposal):
        return "ai_doing_now", "internal engineering/data work that fits the sprint"

    if is_approval_type(proposal):
        return "needs_approval", "decision-required or user-owned change"

    return "noted_for_later", "default defer"


def sort_key(item: ProposalItem) -> tuple[int, str]:
    score = item.priority_score if item.priority_score is not None else 0
    return (-score, item.title.lower())


def choose_current_checkpoint(checkpoints: Iterable[SprintCheckpoint], target_date: str) -> SprintCheckpoint:
    for checkpoint in checkpoints:
        if checkpoint.checkpoint_date == target_date:
            return checkpoint
    raise SystemExit(f"No checkpoint found for {target_date}.")


def infer_next_sprint_tasks(markdown: str, current_sprint_number: int) -> list[str]:
    target = current_sprint_number + 1
    sprint_match = re.search(
        rf"^# Sprint {target} .*?(?=^# Sprint {target + 1}\b|^# Sprints 5-12\b|\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )
    if not sprint_match:
        return []

    block = sprint_match.group(0)
    table_rows = re.findall(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$", block, re.MULTILINE)
    look_ahead = []
    for row in table_rows:
        cells = [cell.strip() for cell in row]
        if len(cells) >= 3 and cells[0] != "Task" and not set(cells[0]) <= {"-"}:
            look_ahead.append(f"{cells[0]}: {cells[1]}")
    return look_ahead[:5]


def main() -> None:
    args = parse_args()
    target_date = date.fromisoformat(args.date).isoformat()
    proposal_date = date.fromisoformat(args.proposal_date).isoformat() if args.proposal_date else target_date

    sprint_markdown = read_text(args.sprint_plan)
    checkpoints = parse_sprint_checkpoints(sprint_markdown, year=date.fromisoformat(target_date).year)
    checkpoint = choose_current_checkpoint(checkpoints, target_date)

    proposals = load_proposals_for_date(args.proposals_dir, proposal_date)
    if args.summary:
        proposals.extend(parse_summary_markdown(args.summary))

    ai_doing_now = []
    needs_approval = []
    noted_for_later = []
    seen = set()

    for proposal in sorted(proposals, key=sort_key):
        key = (proposal.agent, proposal.title, proposal.source_file)
        if key in seen:
            continue
        seen.add(key)

        bucket, reasoning = bucket_proposal(checkpoint, proposal)
        rendered = {
            "agent": proposal.agent,
            "title": proposal.title,
            "owner": proposal.owner,
            "type": proposal.proposal_type,
            "priority_score": proposal.priority_score,
            "reasoning": reasoning,
            "source_file": proposal.source_file,
        }
        if bucket == "ai_doing_now":
            ai_doing_now.append(rendered)
        elif bucket == "needs_approval":
            needs_approval.append(rendered)
        else:
            noted_for_later.append(rendered)

    output = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "target_date": target_date,
        "proposal_date": proposal_date,
        "checkpoint": asdict(checkpoint),
        "buckets": {
            "ai_doing_now": ai_doing_now,
            "needs_approval": needs_approval,
            "noted_for_later": noted_for_later,
        },
        "look_ahead": infer_next_sprint_tasks(sprint_markdown, checkpoint.sprint_number),
        "input_summary_available": bool(args.summary and args.summary.exists()),
        "proposal_count": len(proposals),
        "notes": [
            "Markdown summary parsing is heuristic until a real LATEST_SUMMARY.md sample is available.",
            "JSON proposal files are the reliable source in this sandbox prototype.",
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
