#!/usr/bin/env python3
"""
Marketing Executor — picks up approved marketing actions and executes them.

Polls system_monitor.marketing_actions for status='approved',
executes each action, and updates the status to 'executed' or 'failed'.

Usage:
    python3 scripts/marketing-executor.py              # Execute all approved actions
    python3 scripts/marketing-executor.py --dry-run     # Show what would execute
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
SCRIPTS_DIR = "/home/fields/Fields_Orchestrator/scripts"
VENV_PYTHON = "/home/fields/venv/bin/python3"


def get_approved_actions():
    """Fetch all approved actions from the queue."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    actions = list(sm["marketing_actions"].find(
        {"status": "approved"}
    ).sort("priority", 1))  # priority 1 first
    client.close()
    return actions


def update_action_status(action_id, status, result=None):
    """Update action status in MongoDB."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    update = {
        "status": status,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    if result:
        update["execution_result"] = result
    sm["marketing_actions"].update_one(
        {"_id": action_id},
        {"$set": update}
    )
    client.close()


def execute_page_post(action):
    """Execute a suggest_page_post action."""
    details = action.get("details", {})
    message = details.get("message", "")
    link = details.get("link")

    if not message:
        return {"success": False, "error": "No message in action details"}

    # Call fb-page-post.py with the message
    cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-page-post.py", "--message", message, "--post"]
    if link:
        cmd.extend(["--link", link])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PATH": os.environ.get("PATH", "")}
        )
        if result.returncode == 0:
            # Extract post ID from output
            post_id = None
            for line in result.stdout.split("\n"):
                if "Post ID:" in line:
                    post_id = line.split("Post ID:")[-1].strip()
            return {
                "success": True,
                "post_id": post_id,
                "output": result.stdout[-500:],
            }
        else:
            return {
                "success": False,
                "error": result.stderr[-500:],
                "output": result.stdout[-500:],
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timed out after 30s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_pipeline_run(action):
    """Execute a suggest_pipeline_run action."""
    details = action.get("details", {})
    pipeline = details.get("pipeline", "")

    pipeline_map = {
        "how_it_sold": "run_how_it_sold.py",
        "watch_this_sale": "run_watch_this_sale.py",
        "is_now_good_time": "run_is_now_good_time.py",
        "light_rail": "run_light_rail.py",
        "update_pass": "run_update_pass.py",
    }

    script = pipeline_map.get(pipeline)
    if not script:
        return {"success": False, "error": f"Unknown pipeline: {pipeline}"}

    # Trigger via GitHub Actions dispatch
    try:
        workflow_name = f"{pipeline.replace('_', '-')}.yml"
        result = subprocess.run(
            ["gh", "api", f"repos/Will954633/fields-automation/actions/workflows/{workflow_name}/dispatches",
             "--method", "POST", "--field", "ref=main"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "GH_CONFIG_DIR": "/home/projects/.config/gh"}
        )
        if result.returncode == 0:
            return {"success": True, "triggered": workflow_name}
        else:
            return {"success": False, "error": result.stderr[-300:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_insight(action):
    """Insights don't need execution — just mark as acknowledged."""
    return {"success": True, "note": "Insight acknowledged"}


def execute_ad_edit(action):
    """Ad edits are not yet automated — log for manual execution."""
    return {
        "success": True,
        "note": "Ad edit logged. Manual execution required at this stage.",
        "manual_action_needed": True,
    }


EXECUTORS = {
    "suggest_page_post": execute_page_post,
    "suggest_ad_edit": execute_ad_edit,
    "suggest_pipeline_run": execute_pipeline_run,
    "suggest_insight": execute_insight,
}


def main():
    parser = argparse.ArgumentParser(description="Execute approved marketing actions")
    parser.add_argument("--dry-run", action="store_true", help="Show what would execute")
    args = parser.parse_args()

    actions = get_approved_actions()

    if not actions:
        print("No approved actions to execute.")
        return

    print(f"Found {len(actions)} approved action(s):")
    for action in actions:
        action_type = action.get("action_type", "unknown")
        summary = action.get("summary", "")
        priority = action.get("priority", "?")
        print(f"  [{priority}] {action_type}: {summary}")

        if args.dry_run:
            continue

        executor = EXECUTORS.get(action_type)
        if not executor:
            print(f"    -> No executor for {action_type}, skipping")
            update_action_status(action["_id"], "failed",
                                 {"error": f"No executor for {action_type}"})
            continue

        print(f"    -> Executing...")
        result = executor(action)

        if result.get("success"):
            update_action_status(action["_id"], "executed", result)
            print(f"    -> Done: {result.get('note', result.get('post_id', 'OK'))}")
        else:
            update_action_status(action["_id"], "failed", result)
            print(f"    -> FAILED: {result.get('error', 'Unknown error')}")

    if args.dry_run:
        print("\n(Dry run — nothing executed)")


if __name__ == "__main__":
    main()
