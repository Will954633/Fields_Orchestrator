#!/usr/bin/env python3
"""
ask-gpt.py — Consult GPT-5.4 for review, feedback, or second opinion.

Called by Claude Opus when it wants GPT-5.4's perspective on a concept,
code, task, or content. Opus assembles the question with full context.

Usage:
    python3 scripts/ask-gpt.py "Your question or prompt here"
    python3 scripts/ask-gpt.py --file /path/to/prompt.txt
    echo "question" | python3 scripts/ask-gpt.py --stdin

    # Optional: attach files for GPT to review
    python3 scripts/ask-gpt.py "Review this code" --attach src/foo.py --attach src/bar.py

    # Optional: skip auto-context (if Opus already embedded everything in the prompt)
    python3 scripts/ask-gpt.py --no-context "Fully self-contained question here"
"""

import argparse
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ORCHESTRATOR_DIR = Path("/home/fields/Fields_Orchestrator")
MEMORY_DIR = Path("/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory")
AEST = timezone(timedelta(hours=10))


def load_context() -> str:
    """Load project context documents for GPT."""
    sections = []

    # CLAUDE.md
    claude_md = ORCHESTRATOR_DIR / "CLAUDE.md"
    if claude_md.exists():
        sections.append(f"=== PROJECT OVERVIEW (CLAUDE.md) ===\n{claude_md.read_text()}")

    # OPS_STATUS.md
    ops = ORCHESTRATOR_DIR / "OPS_STATUS.md"
    if ops.exists():
        sections.append(f"=== LIVE SYSTEM STATUS ===\n{ops.read_text()}")

    # Memory index
    memory_md = MEMORY_DIR / "MEMORY.md"
    if memory_md.exists():
        sections.append(f"=== PERSISTENT MEMORY INDEX ===\n{memory_md.read_text()}")

    # Individual memory files
    if MEMORY_DIR.exists():
        memory_parts = []
        for f in sorted(MEMORY_DIR.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            content = f.read_text().strip()
            if content:
                memory_parts.append(f"### {f.stem}\n{content}")
        if memory_parts:
            sections.append(f"=== MEMORY FILES ===\n" + "\n\n".join(memory_parts))

    return "\n\n".join(sections)


def build_system_prompt(include_context: bool) -> str:
    """Build the system prompt for GPT-5.4."""
    base = f"""You are GPT-5.4, consulting for Fields Real Estate. Claude Opus (the primary operations agent) is asking for your review, feedback, or second opinion.

Your role:
- Provide thoughtful, specific analysis — not generic advice
- Challenge assumptions where warranted
- Flag risks or blind spots the primary agent may have missed
- Be direct and concise. Lead with your verdict, then support it
- If you disagree with an approach, say so clearly and explain why
- If you see a better alternative, propose it with specifics

You are NOT the executor. Your job is to think critically and provide perspective. Claude Opus will decide what to act on.

Current time: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}"""

    if include_context:
        context = load_context()
        base += f"\n\nBelow is the full project context so you can give informed, specific feedback.\n\n{context}"

    return base


def main():
    parser = argparse.ArgumentParser(description="Consult GPT-5.4")
    parser.add_argument("prompt", nargs="?", help="The question or prompt")
    parser.add_argument("--file", help="Read prompt from file")
    parser.add_argument("--stdin", action="store_true", help="Read prompt from stdin")
    parser.add_argument("--attach", action="append", default=[], help="Attach file contents (repeatable)")
    parser.add_argument("--no-context", action="store_true", help="Skip auto-loading project context")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max response tokens (default: 4096)")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature (default: 0.7)")
    args = parser.parse_args()

    # Resolve prompt
    if args.stdin:
        prompt = sys.stdin.read().strip()
    elif args.file:
        prompt = Path(args.file).read_text().strip()
    elif args.prompt:
        prompt = args.prompt
    else:
        print("Error: provide a prompt as argument, --file, or --stdin", file=sys.stderr)
        sys.exit(1)

    if not prompt:
        print("Error: empty prompt", file=sys.stderr)
        sys.exit(1)

    # Attach files if requested
    if args.attach:
        attachments = []
        for filepath in args.attach:
            p = Path(filepath)
            if p.exists():
                attachments.append(f"=== FILE: {filepath} ===\n{p.read_text()}")
            else:
                attachments.append(f"=== FILE: {filepath} ===\n[File not found]")
        prompt += "\n\n" + "\n\n".join(attachments)

    # Call GPT-5.4
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    system_prompt = build_system_prompt(include_context=not args.no_context)

    response = client.chat.completions.create(
        model="gpt-5.4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    reply = response.choices[0].message.content.strip()
    usage = response.usage

    # Output the response
    print(reply)

    # Log usage to stderr so it doesn't pollute stdout
    if usage:
        print(f"\n--- GPT-5.4 usage: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion tokens ---", file=sys.stderr)


if __name__ == "__main__":
    main()
