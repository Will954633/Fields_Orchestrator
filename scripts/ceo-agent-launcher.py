#!/usr/bin/env python3
"""
CEO Agent Launcher — runs the remote management team and stores structured output.

Key protections:
  - Refuses to run when CONTEXT_MANIFEST.json reports degraded required inputs
  - Runs Chief of Staff only after successful specialist runs
  - Stores ceo_runs, ceo_briefs, ceo_tasks, and ceo_memory records
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ceo_agent_lib import get_client, load_env_file, now_aest, slugify


REMOTE_HOST = "fields-orchestrator-vm@35.201.6.222"
REMOTE_DIR = "/home/fields-orchestrator-vm/ceo-agents"
CODEX_MODEL = "gpt-5.1-codex"
TEAM_PLAN_PATH = Path(__file__).resolve().parent.parent / "config" / "codex_team_plan.yaml"
DATE_STR = now_aest().strftime("%Y-%m-%d")

PROPOSAL_DEFAULTS = {
    "priority_score": None,
    "time_horizon": "today",
    "depends_on": [],
    "blocks": [],
    "owner": "will",
    "decision_required": True,
}
FINDING_DEFAULTS = {
    "confidence": "medium",
    "evidence_freshness": "current_snapshot",
    "blocked_by": [],
    "data_gaps": [],
}

AGENTS = {
    "engineering": {
        "name": "Engineering Agent",
        "focus": "Pipeline reliability, code quality, technical debt, infrastructure",
    },
    "growth": {
        "name": "Growth Agent",
        "focus": "Marketing, ads, content strategy, conversion, customer acquisition",
    },
    "product": {
        "name": "Product Agent",
        "focus": "Data quality, user experience, feature prioritisation, competitive edge",
    },
    "data_quality": {
        "name": "Data Quality Agent",
        "focus": "Coverage, freshness, schema drift, trust risks, enrichment gaps",
    },
    "chief_of_staff": {
        "name": "Chief of Staff Agent",
        "focus": "Synthesis, prioritisation, conflict resolution, founder brief",
    },
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_team_plan() -> dict[str, Any]:
    if not TEAM_PLAN_PATH.exists():
        return {}
    try:
        return yaml.safe_load(TEAM_PLAN_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        log(f"Warning: could not load {TEAM_PLAN_PATH.name}: {exc}")
        return {}


def build_agent_plan(agent_filter: str | None) -> tuple[list[str], list[str]]:
    if agent_filter:
        if agent_filter not in AGENTS:
            raise RuntimeError(f"Unknown agent: {agent_filter}")
        if agent_filter == "chief_of_staff":
            return [], ["chief_of_staff"]
        return [agent_filter], []

    team = load_team_plan().get("team", {})
    specialists: list[str] = []
    chiefs: list[str] = []
    for agent_id, cfg in team.items():
        if agent_id not in AGENTS:
            continue
        if cfg.get("cadence") != "daily" or cfg.get("status") != "active":
            continue
        if agent_id == "chief_of_staff":
            chiefs.append(agent_id)
        else:
            specialists.append(agent_id)

    if not specialists:
        specialists = ["engineering", "growth", "product"]
    return specialists, chiefs


def ssh_run(cmd: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "ServerAliveInterval=30", REMOTE_HOST, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def update_remote_repos() -> None:
    log("Updating repos on property-scraper...")
    setup_git = "GH_CONFIG_DIR=~/.config/gh gh auth setup-git >/dev/null 2>&1 || true"
    context = ssh_run(f"{setup_git} && cd {REMOTE_DIR}/context && git pull --ff-only origin main 2>&1 | tail -3")
    sandbox = ssh_run(
        f"""{setup_git} && cd {REMOTE_DIR}/sandbox && \
if git status --porcelain | grep -q .; then
    echo 'dirty worktree; skipping pull'
else
    git pull --ff-only origin main 2>&1 | tail -3
fi""",
    )
    print(f"  context: {context.stdout.strip()}")
    print(f"  sandbox: {sandbox.stdout.strip()}")


def deploy_prompts() -> None:
    result = subprocess.run(
        ["scp", "scripts/ceo-agent-prompts.sh", f"{REMOTE_HOST}:{REMOTE_DIR}/"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to sync ceo-agent-prompts.sh: {(result.stderr or '').strip()}")


def read_remote_context_manifest() -> dict[str, Any]:
    result = ssh_run(f"cat {REMOTE_DIR}/context/CONTEXT_MANIFEST.json 2>/dev/null", timeout=30)
    raw = (result.stdout or "").strip()
    if not raw:
        raise RuntimeError("Missing CONTEXT_MANIFEST.json on remote context repo.")
    return json.loads(raw)


def ensure_context_is_healthy(manifest: dict[str, Any]) -> None:
    if manifest.get("degraded"):
        failures = manifest.get("required_failures", [])
        lines = [f"{f.get('path')}: {f.get('error')}" for f in failures]
        raise RuntimeError("Context export is degraded; refusing agent run.\n" + "\n".join(lines))


def start_run(sm, agents_requested: list[str], manifest: dict[str, Any]) -> str:
    run_id = f"{DATE_STR}_{now_aest().strftime('%H%M%S')}"
    sm["ceo_runs"].insert_one(
        {
            "_id": run_id,
            "date": DATE_STR,
            "status": "running",
            "model": CODEX_MODEL,
            "agents_requested": agents_requested,
            "agents_completed": [],
            "agent_results": {},
            "context_manifest": manifest,
            "context_degraded": manifest.get("degraded", False),
            "started_at": now_aest().isoformat(),
            "updated_at": now_aest().isoformat(),
        }
    )
    return run_id


def update_run(sm, run_id: str, **updates: Any) -> None:
    updates["updated_at"] = now_aest().isoformat()
    sm["ceo_runs"].update_one({"_id": run_id}, {"$set": updates})


def run_agent(agent_id: str) -> dict[str, Any]:
    agent = AGENTS[agent_id]
    print(f"\n{'=' * 60}")
    print(f"Running: {agent['name']}")
    print(f"Focus:   {agent['focus']}")
    print(f"{'=' * 60}")

    remote_cmd = f"""
set -e
cd {REMOTE_DIR}/sandbox
mkdir -p proposals {agent_id}
rm -rf context
cp -r {REMOTE_DIR}/context context
bash {REMOTE_DIR}/ceo-agent-prompts.sh {agent_id} {DATE_STR} > /tmp/ceo_prompt_{agent_id}.txt
set +e
timeout 900s codex exec -m {CODEX_MODEL} --full-auto --skip-git-repo-check -o /tmp/ceo_output_{agent_id}.txt "$(cat /tmp/ceo_prompt_{agent_id}.txt)" >/tmp/ceo_stdout_{agent_id}.log 2>&1
rc=$?
set -e
echo "__AGENT_RC__:$rc"
if [ -f proposals/{DATE_STR}_{agent_id}.json ]; then
  stat -c "__PROPOSAL__:%n|%Y|%s" proposals/{DATE_STR}_{agent_id}.json
else
  echo "__PROPOSAL__:missing"
fi
tail -n 40 /tmp/ceo_stdout_{agent_id}.log 2>/dev/null || true
"""
    result = ssh_run(remote_cmd, timeout=1200)
    stdout_lines = (result.stdout or "").splitlines()
    rc = 999
    proposal_meta: dict[str, Any] = {"present": False}
    tail_lines: list[str] = []
    for line in stdout_lines:
        if line.startswith("__AGENT_RC__:"):
            rc = int(line.split(":", 1)[1].strip())
        elif line.startswith("__PROPOSAL__:"):
            payload = line.split(":", 1)[1]
            if payload != "missing":
                path, epoch, size = payload.split("|", 2)
                proposal_meta = {"present": True, "path": path, "updated_epoch": int(epoch), "bytes": int(size)}
        else:
            tail_lines.append(line)

    for line in tail_lines[-20:]:
        print(f"  │ {line}")
    if result.stderr:
        print(f"  ⚠ stderr: {result.stderr[:400]}")

    success = rc == 0 and proposal_meta.get("present", False)
    return {
        "agent": agent_id,
        "success": success,
        "exit_code": rc,
        "proposal": proposal_meta,
        "stdout_tail": tail_lines[-20:],
        "stderr_excerpt": (result.stderr or "")[:800],
    }


def push_to_github() -> None:
    log("Pushing to GitHub sandbox repo...")
    result = ssh_run(
        f"""
GH_CONFIG_DIR=~/.config/gh gh auth setup-git >/dev/null 2>&1 || true
cd {REMOTE_DIR}/sandbox
rm -rf context
if git status --porcelain | grep -q .; then
    git add -A
    git commit -m "CEO agents run {DATE_STR}"
    GH_CONFIG_DIR=~/.config/gh git push origin main 2>&1 | tail -3
else
    echo 'No new files to push'
fi
""",
        timeout=180,
    )
    print(f"  {result.stdout.strip()}")


def fetch_remote_proposals(agent_ids: list[str]) -> list[dict[str, Any]]:
    if not agent_ids:
        return []
    refs = " ".join(f"{REMOTE_DIR}/sandbox/proposals/{DATE_STR}_{agent}.json" for agent in agent_ids)
    result = ssh_run(f"cat {refs} 2>/dev/null", timeout=60)
    raw = (result.stdout or "").strip()
    if not raw:
        return []

    proposals: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        tail = raw[pos:].lstrip()
        if not tail:
            break
        pos += len(raw[pos:]) - len(tail)
        obj, consumed = decoder.raw_decode(tail)
        proposals.append(obj)
        pos += consumed
    return proposals


def normalize_proposal(proposal: dict[str, Any], run_id: str) -> dict[str, Any]:
    proposal.setdefault("status", "pending_review")
    proposal.setdefault("reviewed_by", None)
    proposal.setdefault("review_notes", None)
    proposal["run_id"] = run_id
    proposal["updated_at"] = now_aest().isoformat()
    for finding in proposal.get("findings", []):
        for key, value in FINDING_DEFAULTS.items():
            finding.setdefault(key, value if not isinstance(value, list) else list(value))
    for item in proposal.get("proposals", []):
        for key, value in PROPOSAL_DEFAULTS.items():
            item.setdefault(key, value if not isinstance(value, list) else list(value))
        item.setdefault("confidence", "medium")
        item.setdefault("evidence_freshness", "current_snapshot")
        item.setdefault("blocked_by", [])
        item.setdefault("data_gaps", [])
    return proposal


def upsert_memory(sm, proposal: dict[str, Any]) -> None:
    now = now_aest().isoformat()
    for finding in proposal.get("findings", []):
        title = finding.get("title")
        if not title:
            continue
        sm["ceo_memory"].update_one(
            {"record_type": "finding", "agent": proposal["agent"], "title": title},
            {
                "$set": {
                    "record_type": "finding",
                    "agent": proposal["agent"],
                    "date": proposal["date"],
                    "title": title,
                    "detail": finding.get("detail"),
                    "recommendation": finding.get("recommendation"),
                    "confidence": finding.get("confidence"),
                    "evidence_freshness": finding.get("evidence_freshness"),
                    "blocked_by": finding.get("blocked_by"),
                    "data_gaps": finding.get("data_gaps"),
                    "severity": finding.get("severity"),
                    "source": "ceo_proposals",
                    "last_seen": now,
                },
                "$setOnInsert": {"first_seen": now, "times_seen": 0},
                "$inc": {"times_seen": 1},
            },
            upsert=True,
        )
    for item in proposal.get("proposals", []):
        title = item.get("title")
        if not title:
            continue
        proposal_id = f"{proposal['date']}_{proposal['agent']}_{slugify(title)}"
        sm["ceo_tasks"].update_one(
            {"_id": proposal_id},
            {
                "$set": {
                    "agent": proposal["agent"],
                    "date": proposal["date"],
                    "title": title,
                    "status": "proposed",
                    "priority": item.get("priority"),
                    "proposal_type": item.get("type"),
                    "problem": item.get("problem"),
                    "proposal": item.get("proposal"),
                    "owner": item.get("owner"),
                    "depends_on": item.get("depends_on"),
                    "blocks": item.get("blocks"),
                    "decision_required": item.get("decision_required"),
                    "confidence": item.get("confidence"),
                    "evidence_freshness": item.get("evidence_freshness"),
                    "blocked_by": item.get("blocked_by"),
                    "data_gaps": item.get("data_gaps"),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        sm["ceo_memory"].update_one(
            {"record_type": "proposal", "agent": proposal["agent"], "title": title},
            {
                "$set": {
                    "record_type": "proposal",
                    "agent": proposal["agent"],
                    "date": proposal["date"],
                    "title": title,
                    "detail": item.get("proposal"),
                    "confidence": item.get("confidence"),
                    "evidence_freshness": item.get("evidence_freshness"),
                    "blocked_by": item.get("blocked_by"),
                    "data_gaps": item.get("data_gaps"),
                    "priority": item.get("priority"),
                    "source": "ceo_proposals",
                    "last_seen": now,
                },
                "$setOnInsert": {"first_seen": now, "times_seen": 0},
                "$inc": {"times_seen": 1},
            },
            upsert=True,
        )


def store_proposals(sm, run_id: str, proposals: list[dict[str, Any]]) -> list[str]:
    stored_agents: list[str] = []
    coll = sm["ceo_proposals"]
    for raw in proposals:
        proposal = normalize_proposal(raw, run_id)
        coll.update_one(
            {"agent": proposal["agent"], "date": proposal["date"]},
            {"$set": proposal, "$setOnInsert": {"created_at": now_aest().isoformat()}},
            upsert=True,
        )
        upsert_memory(sm, proposal)
        if proposal["agent"] == "chief_of_staff":
            sm["ceo_briefs"].update_one(
                {"date": proposal["date"]},
                {"$set": proposal, "$setOnInsert": {"created_at": now_aest().isoformat()}},
                upsert=True,
            )
        stored_agents.append(proposal["agent"])
        print(f"  ✓ Upserted: {proposal['agent']} / {proposal['date']}")
    return stored_agents


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the remote CEO agent team")
    parser.add_argument("--agent", help="Run one agent only")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--list", action="store_true", help="List configured agents")
    return parser.parse_args()


def main() -> None:
    load_env_file()
    args = parse_args()
    team_plan = load_team_plan()

    if args.list:
        print("Available agents:")
        for aid, agent in AGENTS.items():
            status = team_plan.get("team", {}).get(aid, {}).get("status", "untracked")
            cadence = team_plan.get("team", {}).get(aid, {}).get("cadence", "manual")
            print(f"  {aid:15s} — {agent['name']}: {agent['focus']} [{status}, {cadence}]")
        return

    specialists, chiefs = build_agent_plan(args.agent)
    agents_requested = specialists + chiefs
    print(f"CEO Agent Launcher — {DATE_STR}")
    print(f"Agents: {', '.join(agents_requested) if agents_requested else '(none)'}")
    print(f"Model:  {CODEX_MODEL}")
    if args.dry_run:
        print("[DRY RUN MODE]")
        return

    update_remote_repos()
    deploy_prompts()
    manifest = read_remote_context_manifest()
    ensure_context_is_healthy(manifest)

    client = get_client()
    sm = client["system_monitor"]
    run_id = start_run(sm, agents_requested, manifest)
    try:
        specialist_results = {}
        for agent_id in specialists:
            result = run_agent(agent_id)
            specialist_results[agent_id] = result
            update_run(sm, run_id, agent_results={**specialist_results})

        specialist_failures = [aid for aid, result in specialist_results.items() if not result.get("success")]
        chief_results = {}
        if chiefs and not specialist_failures:
            for agent_id in chiefs:
                result = run_agent(agent_id)
                chief_results[agent_id] = result
        elif chiefs:
            log("Skipping Chief of Staff because one or more specialist runs failed.")

        all_results = {**specialist_results, **chief_results}
        successful_agents = [aid for aid, result in all_results.items() if result.get("success")]

        push_to_github()
        proposals = fetch_remote_proposals(successful_agents)
        stored_agents = store_proposals(sm, run_id, proposals)

        status = "success" if len(successful_agents) == len(agents_requested if not chiefs or not specialist_failures else specialists) else "partial_failure"
        if specialist_failures:
            status = "partial_failure"
        update_run(
            sm,
            run_id,
            status=status,
            agents_completed=successful_agents,
            agent_results=all_results,
            specialist_failures=specialist_failures,
            chief_skipped=bool(chiefs and specialist_failures),
            stored_agents=stored_agents,
            finished_at=now_aest().isoformat(),
        )
        print("\nCEO agent run complete.")
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
