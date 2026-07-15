#!/usr/bin/env python3
"""
claude-agent.py
Fields Estate — Claude Code AI Repair Agent

Polls system_monitor.repair_requests every 60 seconds.
When a pending AI-repair request is found (type="claude"), it:
  1. Claims the request (status → running)
  2. Builds a context-rich prompt from the error details
  3. Runs `claude --print <prompt>` as a subprocess with allowed tools
  4. Captures the full output
  5. Writes result back to MongoDB (status → awaiting_approval, claude_output = full text)
  6. The Ops dashboard shows the output and presents Approve / Reject buttons

Normal repair requests (type="enrichment" or no type) are handled by repair-agent.py (unchanged).

Deployed to VM at: /home/fields/Fields_Orchestrator/claude-agent.py

Usage:
    python3 claude-agent.py
    python3 claude-agent.py --dry-run      # prints prompts but does not call claude
    python3 claude-agent.py --once         # process one item then exit
    python3 claude-agent.py --no-tools     # disable filesystem tools (text-only response)
"""

import os
import sys
import time
import signal
import logging
import argparse
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [claude-agent] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/fields/Fields_Orchestrator/logs/claude-agent.log"),
    ],
)
log = logging.getLogger("claude-agent")

POLL_INTERVAL_SECONDS = 60
CLAUDE_TIMEOUT_SECONDS = 300        # 5 minutes max per Claude invocation
CLAUDE_MAX_TURNS = 15               # Limit agentic turns to control cost
BASE_DIR = Path("/home/fields/Feilds_Website")
ORCHESTRATOR_DIR = Path("/home/fields/Fields_Orchestrator")

# Tools Claude is allowed to use.  Omit Write/Edit — Claude proposes changes
# as text output; a human applies them via the Approve button.
ALLOWED_TOOLS = "Bash,Read,Grep,Glob"

# ---------------------------------------------------------------------------
# System prompt injected before every repair prompt
# ---------------------------------------------------------------------------

SYSTEM_CONTEXT = """
You are the Fields Estate operations AI agent running on the Google Cloud VM.

Your role: investigate failures in the Fields Estate property data pipeline and
propose concrete fixes. You have read access to all relevant files.

Key directories on this VM:
- /home/fields/Feilds_Website/          — Website code (Netlify functions, React, scripts)
- /home/fields/Fields_Orchestrator/     — Orchestrator pipeline, config, logs
- /home/fields/Property_Data_Scraping/  — Scraping scripts
- /home/fields/Fields_Orchestrator/logs/ — Recent run logs

Key configuration:
- /home/fields/Fields_Orchestrator/config/settings.yaml
- /home/fields/Fields_Orchestrator/config/process_commands.yaml

Deployment: ALL code changes go to GitHub first (repo: Will954633/Website_Version_Feb_2026).
Netlify auto-deploys from GitHub. Use `gh api` for pushes (git push hangs).

Database: Azure Cosmos DB (MongoDB API). Connection string is in COSMOS_CONNECTION_STRING env var.
DO NOT print or log the connection string.

When investigating:
1. Read the relevant log files and scripts
2. Identify the root cause
3. Propose a specific fix (show the exact code change as a diff or before/after)
4. Keep your response focused and actionable

IMPORTANT: Do not apply any fixes. Only propose them. A human will review and approve.
""".strip()


def get_mongo_uri():
    settings_path = ORCHESTRATOR_DIR / "config" / "settings.yaml"
    with open(settings_path) as f:
        settings = yaml.safe_load(f)
    uri = settings.get("mongodb", {}).get("uri")
    if not uri:
        # Fallback: try environment variable
        uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        raise ValueError("Cannot find MongoDB URI in settings.yaml or COSMOS_CONNECTION_STRING")
    return uri


def build_prompt(doc):
    """Build the investigation prompt from a repair_request document."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    aest = datetime.now(timezone.utc).astimezone(__import__("zoneinfo", fromlist=["ZoneInfo"]).ZoneInfo("Australia/Brisbane"))
    date_line = f"Today's date and time: {now} / {aest.strftime('%Y-%m-%d %H:%M AEST')}"
    lines = [SYSTEM_CONTEXT, "", date_line, "", "---", ""]

    error_id = doc.get("error_id", "unknown")
    context = doc.get("context") or ""
    suburb = doc.get("suburb") or ""
    metric = doc.get("metric") or ""
    error_detail = doc.get("error_detail") or ""
    process_id = doc.get("process_id") or ""
    process_name = doc.get("process_name") or ""
    step_name = doc.get("step_name") or ""
    log_snippet = doc.get("log_snippet") or ""
    error_message = doc.get("error_message") or ""

    lines.append(f"## Repair Request: {error_id}")
    lines.append("")

    if process_id or process_name or step_name:
        lines.append("### Failing Process")
        if process_id:
            lines.append(f"- Process ID: {process_id}")
        if process_name:
            lines.append(f"- Process Name: {process_name}")
        if step_name:
            lines.append(f"- Step: {step_name}")
        lines.append("")

    if suburb or metric:
        lines.append("### Scope")
        if suburb:
            lines.append(f"- Suburb: {suburb}")
        if metric:
            lines.append(f"- Metric: {metric}")
        lines.append("")

    if error_message:
        lines.append("### Error Message")
        lines.append("```")
        lines.append(error_message[:2000])
        lines.append("```")
        lines.append("")

    if log_snippet:
        lines.append("### Log Snippet")
        lines.append("```")
        lines.append(log_snippet[:3000])
        lines.append("```")
        lines.append("")

    if error_detail:
        lines.append("### Additional Context")
        lines.append(error_detail[:1000])
        lines.append("")

    if context and context not in (suburb, error_id):
        lines.append("### Context")
        lines.append(context[:500])
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Please investigate the above failure:")
    lines.append("1. Read any relevant log files and scripts")
    lines.append("2. Identify the root cause")
    lines.append("3. Propose a concrete fix (show exact code changes)")
    lines.append("4. Confirm whether the fix is safe to apply automatically")

    return "\n".join(lines)


def run_claude(prompt, dry_run=False, no_tools=False):
    """
    Run `claude --print <prompt>` as a subprocess and return (output, exit_code).
    """
    if dry_run:
        log.info("[DRY RUN] Would run claude with prompt:\n" + prompt[:500] + "…")
        return "[DRY RUN] Claude not called.", 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "ERROR: ANTHROPIC_API_KEY not set in environment.", 1

    cmd = [
        "claude",
        "--print",
        "--max-turns", str(CLAUDE_MAX_TURNS),
        "--output-format", "text",
    ]

    if not no_tools:
        cmd += ["--allowedTools", ALLOWED_TOOLS]

    # Prompt is passed via stdin (--print reads from stdin when no positional arg given)
    log.info(f"Running claude (max-turns={CLAUDE_MAX_TURNS}, tools={'off' if no_tools else ALLOWED_TOOLS})")

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_SECONDS,
            cwd=str(BASE_DIR),
            env={**os.environ},
        )
        output = result.stdout.strip()
        if result.stderr:
            log.warning(f"claude stderr: {result.stderr[-500:]}")
        return output, result.returncode
    except subprocess.TimeoutExpired:
        log.error(f"claude timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        return f"ERROR: Claude timed out after {CLAUDE_TIMEOUT_SECONDS}s.", 124
    except FileNotFoundError:
        return "ERROR: claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code", 127
    except Exception as e:
        log.error(f"claude subprocess error: {e}")
        return f"ERROR: {e}", 1


def poll_once(db, dry_run=False, no_tools=False):
    """Find one pending claude repair request, process it, update MongoDB."""
    col = db["repair_requests"]

    # Only handle requests explicitly flagged as claude type, or those with error_message
    # (auto-raised by MonitorClient or OpsPage "Ask Claude" button)
    docs = list(col.find(
        {"status": "pending", "$or": [{"type": "claude"}, {"type": {"$exists": False}}]},
    ).limit(10))

    # Filter to only claude-type (skip pure enrichment requests which repair-agent.py handles)
    claude_docs = [
        d for d in docs
        if d.get("type") == "claude"
        or d.get("error_message")
        or d.get("log_snippet")
        or d.get("process_id")
    ]

    if not claude_docs:
        return 0

    claude_docs.sort(key=lambda d: d.get("created_at") or datetime.min)
    doc = claude_docs[0]
    repair_id = doc["_id"]

    # Claim it atomically
    claimed = col.find_one_and_update(
        {"_id": repair_id, "status": "pending"},
        {"$set": {
            "status": "running",
            "started_at": datetime.now(timezone.utc),
            "agent": "claude",
        }},
    )
    if claimed is None:
        return 0  # Another agent claimed it first

    log.info(f"Processing repair {repair_id} (error_id={doc.get('error_id', 'n/a')})")

    prompt = build_prompt(doc)
    output, exit_code = run_claude(prompt, dry_run=dry_run, no_tools=no_tools)

    status = "awaiting_approval" if exit_code == 0 else "failed"
    log.info(f"Claude finished (exit={exit_code}, status={status}, output_len={len(output)})")

    col.update_one(
        {"_id": repair_id},
        {"$set": {
            "status": status,
            "finished_at": datetime.now(timezone.utc),
            "claude_output": output,
            "exit_code": exit_code,
            "result_summary": output[:300] + ("…" if len(output) > 300 else ""),
            "error": None if exit_code == 0 else f"claude exited {exit_code}",
        }},
    )

    _write_fix_history(doc, output, status)
    return 1


def _write_fix_history(doc, claude_output, status):
    """
    Append an entry to today's fix history log after Claude completes an investigation.
    All auto-repair work is documented here — not just manual session fixes.
    """
    try:
        from zoneinfo import ZoneInfo
        aest = datetime.now(timezone.utc).astimezone(ZoneInfo("Australia/Brisbane"))
        date_str = aest.strftime("%Y-%m-%d")
        time_str = aest.strftime("%H:%M")

        fix_dir = Path("/home/fields/Fields_Orchestrator/logs/fix-history")
        fix_dir.mkdir(parents=True, exist_ok=True)
        fix_file = fix_dir / f"{date_str}.md"

        error_id    = doc.get("error_id", "unknown")
        process_id  = doc.get("process_id", "?")
        process_name = doc.get("process_name", "unknown step")
        triage      = doc.get("triage") or {}
        failure_class = triage.get("failure_class", "unknown")
        cause       = triage.get("cause", doc.get("error_message", "")[:200])
        root_step   = triage.get("root_step")
        action      = triage.get("action", "escalate")

        # First ~600 chars of Claude's output as the summary
        summary = claude_output.strip()[:600].replace("\n", "\n  ")
        if len(claude_output) > 600:
            summary += "\n  […truncated — full output in system_monitor.repair_requests]"

        root_line = f"\n**Root step:** {root_step}" if root_step else ""

        entry = f"""
---

## [AUTO-REPAIR:{error_id}] Step {process_id} ({process_name}) — {time_str} AEST

**Trigger:** Auto-triage escalation
**Triage:** {failure_class.upper()} — {cause}{root_line}
**Action:** {action}
**Status:** {status} ({"awaiting approval" if status == "awaiting_approval" else status})

**Claude investigation summary:**
  {summary}

"""

        with open(fix_file, "a") as f:
            f.write(entry)

        log.info(f"Fix history written → logs/fix-history/{date_str}.md")
    except Exception as e:
        log.warning(f"Fix history write failed (non-fatal): {e}")


def main():
    parser = argparse.ArgumentParser(description="Fields Claude Code Repair Agent")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts but don't call Claude")
    parser.add_argument("--once", action="store_true", help="Process one item then exit")
    parser.add_argument("--no-tools", action="store_true", help="Disable filesystem tools")
    args = parser.parse_args()

    log.info("claude-agent starting up")

    shutdown = [False]
    def handle_sigterm(sig, frame):
        log.info("SIGTERM received, shutting down")
        shutdown[0] = True
    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        from pymongo import MongoClient
        uri = get_mongo_uri()
        client = MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=False)
        db = client["system_monitor"]
        # Ping to verify connection
        db.command("ping")
        log.info("Connected to MongoDB (system_monitor)")
    except Exception as e:
        log.error(f"MongoDB connection failed: {e}")
        sys.exit(1)

    log.info(f"Polling every {POLL_INTERVAL_SECONDS}s for Claude repair requests…")

    while not shutdown[0]:
        try:
            processed = poll_once(db, dry_run=args.dry_run, no_tools=args.no_tools)
            if processed == 0 and not args.once:
                for _ in range(POLL_INTERVAL_SECONDS):
                    if shutdown[0]:
                        break
                    time.sleep(1)
            elif args.once:
                log.info("--once: exiting")
                break
        except Exception as e:
            log.error(f"Poll error: {e}")
            if not args.once:
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                break

    log.info("claude-agent stopped")


if __name__ == "__main__":
    main()
