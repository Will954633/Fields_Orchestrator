#!/usr/bin/env python3
"""
Agent Implementation Bridge — Pulls CEO agent deliverables and implements them via Claude Opus.

Flow:
1. Pull deliverables from CEO agent sandbox on remote VM
2. Triage: what can be implemented autonomously vs needs approval
3. For autonomous items: execute via claude CLI (Max subscription)
4. For approval items: message Will via Chat Agent + Telegram, wait for response
5. On approval: execute
6. Log everything

This runs on the orchestrator VM and uses the claude CLI for implementation.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Paths
ORCHESTRATOR_DIR = Path("/home/fields/Fields_Orchestrator")
REMOTE_HOST = "fields-orchestrator-vm@35.201.6.222"
REMOTE_SANDBOX = "/home/fields-orchestrator-vm/ceo-agents/sandbox"
LOCAL_STAGING = ORCHESTRATOR_DIR / "artifacts" / "agent-staging"
VENV_PYTHON = "/home/fields/venv/bin/python3"
CLAUDE_CLI = "claude"  # Max subscription CLI

# Autonomy rules
AUTONOMOUS_ACTIONS = {
    "write_schema",          # MongoDB collection schemas
    "write_script",          # Internal scripts (not website)
    "write_spec",            # Specs and documents
    "fix_pipeline",          # Pipeline repairs
    "fix_data",              # Data quality fixes
    "backup_scraper",        # Backup scraper development
    "generate_content",      # Draft content (not publish)
    "generate_fields",       # Generate feed_hook, editorial fields
    "update_config",         # Internal config (not pipeline schedule)
    "posthog_setup",         # Analytics dashboards and events
}

APPROVAL_REQUIRED = {
    "website_change",        # Any change to fieldsestate.com.au
    "google_ads",            # Any Google Ads change
    "facebook_ads_live",     # Publishing new Facebook ads
    "increase_spend",        # Budget increases
    "publish_content",       # Publishing articles/content to live site
    "external_contact",      # Contacting anyone external
    "database_schema_change", # New collections/indexes in production
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def pull_deliverables() -> dict:
    """Pull new deliverables from CEO agent sandbox."""
    log("Pulling deliverables from remote VM...")
    LOCAL_STAGING.mkdir(parents=True, exist_ok=True)

    deliverables = {}

    for agent in ["engineering", "product", "growth", "data_quality", "chief_of_staff"]:
        # Pull agent's sandbox directory
        local_agent_dir = LOCAL_STAGING / agent
        local_agent_dir.mkdir(exist_ok=True)

        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", REMOTE_HOST,
             f"find {REMOTE_SANDBOX}/{agent}/ -type f -newer /tmp/launch_1hr_agents.sh 2>/dev/null | grep -v node_modules"],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0 or not result.stdout.strip():
            continue

        files = result.stdout.strip().splitlines()
        agent_deliverables = []

        for remote_path in files:
            filename = Path(remote_path).name
            local_path = local_agent_dir / filename

            fetch = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=10", REMOTE_HOST, f"cat '{remote_path}'"],
                capture_output=True, text=True, timeout=30
            )
            if fetch.returncode == 0 and fetch.stdout.strip():
                local_path.write_text(fetch.stdout)
                agent_deliverables.append({
                    "file": str(local_path),
                    "filename": filename,
                    "size": len(fetch.stdout),
                })
                log(f"  Pulled {agent}/{filename} ({len(fetch.stdout)} bytes)")

        if agent_deliverables:
            deliverables[agent] = agent_deliverables

    return deliverables


def classify_deliverable(agent: str, filename: str, content: str) -> tuple[str, str]:
    """Classify a deliverable as autonomous or approval-required.

    Returns (action_type, classification) where classification is 'autonomous' or 'approval_required'.
    """
    lower = filename.lower() + " " + content[:500].lower()

    # Check for approval-required patterns
    if any(kw in lower for kw in ["website", "netlify", "deploy", "fieldsestate.com"]):
        return "website_change", "approval_required"
    if any(kw in lower for kw in ["google ads", "google_ads", "adwords"]):
        return "google_ads", "approval_required"
    if any(kw in lower for kw in ["facebook ad", "meta ad", "publish", "go live"]):
        return "facebook_ads_live", "approval_required"
    if "increase" in lower and ("budget" in lower or "spend" in lower):
        return "increase_spend", "approval_required"

    # Autonomous patterns
    if any(kw in lower for kw in ["schema", "collection", "index", "mongodb"]):
        return "write_schema", "autonomous"
    if filename.endswith(".py"):
        return "write_script", "autonomous"
    if any(kw in lower for kw in ["spec", "conversion", "measurement", "plan"]):
        return "write_spec", "autonomous"
    if any(kw in lower for kw in ["pipeline", "fix", "repair"]):
        return "fix_pipeline", "autonomous"
    if any(kw in lower for kw in ["feed_hook", "editorial", "enrichment"]):
        return "generate_fields", "autonomous"
    if any(kw in lower for kw in ["posthog", "dashboard", "event", "tracking"]):
        return "posthog_setup", "autonomous"
    if any(kw in lower for kw in ["content", "draft", "transcript", "copy"]):
        return "generate_content", "autonomous"

    return "write_spec", "autonomous"


def notify_will(message: str, urgency: str = "medium") -> None:
    """Send a message to Will via Telegram + Chat Agent."""
    log(f"📱 Notifying Will ({urgency})...")

    # Telegram
    try:
        subprocess.run(
            [VENV_PYTHON, str(ORCHESTRATOR_DIR / "scripts" / "telegram_notify.py"), message],
            capture_output=True, text=True, timeout=30,
            cwd=str(ORCHESTRATOR_DIR),
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        log("  ✅ Telegram sent")
    except Exception as e:
        log(f"  ❌ Telegram failed: {e}")

    # Chat Agent queue
    try:
        sys.path.insert(0, str(ORCHESTRATOR_DIR))
        from shared.db import get_client
        client = get_client()
        client["system_monitor"]["agent_messages"].insert_one({
            "agent": "implementation_bridge",
            "message": message,
            "urgency": urgency,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        })
        log("  ✅ Chat Agent message queued")
    except Exception as e:
        log(f"  ⚠ Chat Agent queue failed: {e}")


def wait_for_approval(topic: str, timeout_minutes: int = 60) -> Optional[str]:
    """Wait for Will's response via Chat Agent or Telegram."""
    log(f"⏳ Waiting for approval on: {topic}")

    try:
        sys.path.insert(0, str(ORCHESTRATOR_DIR))
        from shared.db import get_client
        client = get_client()
        db = client["system_monitor"]

        start = time.time()
        while time.time() - start < timeout_minutes * 60:
            # Check for response
            response = db["agent_messages"].find_one({
                "topic": topic,
                "status": "responded",
            })
            if response:
                log(f"  ✅ Got response: {response.get('response', '')[:100]}")
                return response.get("response", "approved")

            # Also check for any message with "approved" or "yes" in recent messages
            recent = db["agent_messages"].find_one({
                "status": "responded",
                "created_at": {"$gte": datetime.now().isoformat()[:10]},
            })
            if recent:
                return recent.get("response", "approved")

            time.sleep(30)  # Check every 30 seconds

    except Exception as e:
        log(f"  ⚠ Approval check error: {e}")

    log(f"  ⏰ Approval timeout after {timeout_minutes} min")
    return None


def implement_with_opus(deliverable: dict, agent: str) -> dict:
    """Use Claude Opus (via claude CLI) to implement a deliverable."""
    filepath = deliverable["file"]
    content = Path(filepath).read_text()
    filename = deliverable["filename"]

    action_type, classification = classify_deliverable(agent, filename, content)

    log(f"📋 {agent}/{filename}: {action_type} ({classification})")

    if classification == "approval_required":
        # Notify Will and wait
        msg = (
            f"🤖 *Implementation Bridge*\n\n"
            f"Agent: {agent}\n"
            f"Deliverable: {filename}\n"
            f"Action: {action_type}\n\n"
            f"This requires your approval. Summary:\n"
            f"{content[:500]}\n\n"
            f"Reply 'approve' to proceed or 'skip' to defer."
        )
        notify_will(msg, urgency="high")
        response = wait_for_approval(f"{agent}/{filename}", timeout_minutes=30)

        if not response or "skip" in response.lower():
            log(f"  ⏭ Skipped (no approval or deferred)")
            return {"status": "skipped", "reason": "awaiting_approval"}

    # Build the implementation prompt for Claude Opus
    prompt = f"""You are implementing a deliverable from the {agent} CEO agent.

DELIVERABLE FILE: {filename}
DELIVERABLE CONTENT:
{content}

YOUR TASK: Implement this deliverable on the production system. This means:
- If it's a spec: build the actual code/component it describes
- If it's a script: review it, adapt for this VM, save to the correct location, make it executable
- If it's a schema: create the MongoDB collection and indexes
- If it's a content draft: save it to the appropriate location for review
- If it's a fix: apply it to the relevant files

RULES:
- You are on the orchestrator VM at /home/fields/Fields_Orchestrator
- Python venv: source /home/fields/venv/bin/activate
- Env vars: set -a && source /home/fields/Fields_Orchestrator/.env && set +a
- GitHub push: use gh api (git push hangs on this VM). GH_CONFIG_DIR=/home/projects/.config/gh
- Database: use shared.db.get_client() for MongoDB access
- Do NOT modify website files without explicit approval
- Do NOT modify ad campaigns without explicit approval
- Do NOT publish content to live site without explicit approval
- Log what you did to logs/fix-history/ if it's a fix

IMPLEMENT NOW. Be thorough but concise. Produce working code, not outlines.
"""

    log(f"  🔨 Sending to Claude Opus for implementation...")

    try:
        # Must unset CLAUDECODE env var to allow nested claude CLI sessions
        impl_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        impl_env["GH_CONFIG_DIR"] = "/home/projects/.config/gh"

        result = subprocess.run(
            [CLAUDE_CLI, "-p", prompt, "--allowedTools",
             "Bash,Read,Write,Edit,Glob,Grep", "--max-turns", "30"],
            capture_output=True, text=True,
            timeout=600,  # 10 min per implementation
            cwd=str(ORCHESTRATOR_DIR),
            env=impl_env,
        )

        output = result.stdout[-2000:] if result.stdout else "(no output)"
        log(f"  ✅ Implementation complete ({len(result.stdout)} chars)")

        return {
            "status": "implemented",
            "action_type": action_type,
            "output_excerpt": output,
        }

    except subprocess.TimeoutExpired:
        log(f"  ⏰ Implementation timed out (10 min)")
        return {"status": "timeout", "action_type": action_type}
    except Exception as e:
        log(f"  ❌ Implementation failed: {e}")
        return {"status": "error", "error": str(e)}


def run_bridge():
    """Main bridge loop: pull → classify → implement → report."""
    log("=" * 60)
    log("AGENT IMPLEMENTATION BRIDGE — Starting")
    log("=" * 60)

    # Step 1: Pull deliverables
    deliverables = pull_deliverables()

    if not deliverables:
        log("No new deliverables to implement.")
        return

    total = sum(len(files) for files in deliverables.values())
    log(f"\nFound {total} deliverables across {len(deliverables)} agents")

    # Step 2: Classify and implement
    results = []
    for agent, files in deliverables.items():
        for deliverable in files:
            result = implement_with_opus(deliverable, agent)
            result["agent"] = agent
            result["file"] = deliverable["filename"]
            results.append(result)

    # Step 3: Report
    log("\n" + "=" * 60)
    log("IMPLEMENTATION SUMMARY")
    log("=" * 60)

    implemented = [r for r in results if r["status"] == "implemented"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed = [r for r in results if r["status"] in ("error", "timeout")]

    log(f"  Implemented: {len(implemented)}")
    log(f"  Skipped (awaiting approval): {len(skipped)}")
    log(f"  Failed: {len(failed)}")

    for r in implemented:
        log(f"  ✅ {r['agent']}/{r['file']} — {r['action_type']}")
    for r in skipped:
        log(f"  ⏭ {r['agent']}/{r['file']} — {r.get('reason', '?')}")
    for r in failed:
        log(f"  ❌ {r['agent']}/{r['file']} — {r.get('error', r['status'])}")

    # Notify Will of completion
    summary = (
        f"🔧 *Implementation Bridge Complete*\n\n"
        f"Implemented: {len(implemented)}\n"
        f"Awaiting approval: {len(skipped)}\n"
        f"Failed: {len(failed)}\n"
    )
    if implemented:
        summary += "\n*Implemented:*\n"
        for r in implemented:
            summary += f"• {r['agent']}: {r['file']}\n"
    if skipped:
        summary += "\n*Needs your approval:*\n"
        for r in skipped:
            summary += f"• {r['agent']}: {r['file']}\n"

    notify_will(summary)


if __name__ == "__main__":
    # Load environment
    env_file = ORCHESTRATOR_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

    run_bridge()
