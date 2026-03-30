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
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ceo_agent_lib import get_client, load_env_file, now_aest, slugify
from validate_snapshot import build_report_from_manifest, SnapshotReport


REMOTE_HOST = "fields-orchestrator-vm@35.201.6.222"
REMOTE_DIR = "/home/fields-orchestrator-vm/ceo-agents"
CODEX_MODEL = "gpt-5.4"
SESSION_TIMEOUT_SECONDS = 3600  # 1 hour per agent session
TEAM_PLAN_PATH = Path(__file__).resolve().parent.parent / "config" / "codex_team_plan.yaml"
LOCAL_RUNS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "ceo-runs"
LOCAL_PROPOSALS_DIR = Path(__file__).resolve().parent.parent / "proposals"
FOUNDER_REQUESTS_DIR = Path(__file__).resolve().parent.parent / "ceo-founder-requests"
AGENT_MEMORY_DIR = Path(__file__).resolve().parent.parent / "ceo-agent-memory"
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

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "clear", "clearly",
    "current", "daily", "day", "days", "do", "for", "from", "general", "get", "had", "has", "have",
    "how", "i", "if", "im", "in", "into", "is", "it", "its", "me", "milestones", "monitor", "monitoring",
    "need", "needs", "new", "not", "of", "on", "or", "our", "out", "perhaps", "right", "should",
    "so", "some", "stage", "stats", "strategy", "system", "team", "that", "the", "their", "them",
    "there", "these", "they", "this", "to", "too", "up", "us", "we", "what", "where", "which", "will",
    "with", "work", "working", "you", "your",
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        return {}, raw
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.DOTALL)
    if not match:
        return {}, raw
    try:
        meta = yaml.safe_load(match.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    return meta, match.group(2)


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text.lower())
        if token not in STOP_WORDS and not token.isdigit()
    }


def is_template_request(path: Path, meta: dict[str, Any], body: str) -> bool:
    name = path.name.upper()
    if name.startswith("TEMPLATE"):
        return True
    body_lower = body.lower()
    placeholder_markers = (
        "describe the concern",
        "state the exact outcome",
        "add follow-up answers here",
    )
    return sum(1 for marker in placeholder_markers if marker in body_lower) >= 2


def load_founder_requests() -> list[dict[str, Any]]:
    open_dir = FOUNDER_REQUESTS_DIR / "open"
    if not open_dir.exists():
        return []

    requests: list[dict[str, Any]] = []
    for path in sorted(open_dir.glob("*.md")):
        meta, body = parse_frontmatter(path)
        if is_template_request(path, meta, body):
            continue
        request_id = str(meta.get("id") or path.stem)
        title = str(meta.get("title") or path.stem.replace("-", " ")).strip()
        combined = " ".join(part for part in [path.name, path.stem, request_id, title, body] if str(part).strip())
        requests.append(
            {
                "path": path,
                "filename": path.name,
                "stem": path.stem,
                "id": request_id,
                "title": title,
                "body": body,
                "tokens": tokenize(combined),
            }
        )
    return requests


def score_request_match(request: dict[str, Any], proposal: dict[str, Any], raw_text: str) -> int:
    score = 0
    lowered = raw_text.lower()
    direct_match = False
    for marker in (request["filename"].lower(), request["stem"].lower(), str(request["id"]).lower()):
        if marker and marker in lowered:
            score += 20
            direct_match = True
    score += len(request["tokens"] & tokenize(raw_text))
    if proposal.get("agent") == "chief_of_staff" and ("founder request" in lowered or "will asked" in lowered):
        score += 4
    return score, direct_match


def derive_request_status(matches: list[dict[str, Any]]) -> tuple[str, list[str]]:
    blocked_by = sorted(
        {item for match in matches for item in match.get("blocked_by", []) if str(item).strip()}
    )
    combined_text = " ".join(match["text"].lower() for match in matches)
    if "waiting on founder input" in combined_text or "waiting on will" in combined_text or "founder clarification" in combined_text:
        return "waiting_on_will", blocked_by
    if "blocked" in combined_text or blocked_by:
        return "action_now_blocked", blocked_by
    if "defer" in combined_text:
        return "deferred", blocked_by
    return "action_now", blocked_by


def mentions_other_request(text: str, request: dict[str, Any], all_requests: list[dict[str, Any]]) -> bool:
    lowered = text.lower()
    for other in all_requests:
        if other["filename"] == request["filename"]:
            continue
        markers = [other["filename"].lower(), other["stem"].lower(), str(other["id"]).lower()]
        if any(marker and marker in lowered for marker in markers):
            return True
    return False


def build_request_response_section(
    run_id: str,
    request: dict[str, Any],
    proposals: list[dict[str, Any]],
    all_requests: list[dict[str, Any]],
) -> str | None:
    matches: list[dict[str, Any]] = []
    for proposal in proposals:
        segments: list[tuple[str, dict[str, Any]]] = []
        if proposal.get("daily_brief"):
            segments.append((str(proposal["daily_brief"]), {}))
        for finding in proposal.get("findings", []):
            segments.append(
                (
                    " ".join(str(finding.get(key, "")) for key in ("title", "detail", "recommendation")),
                    finding,
                )
            )
        for item in proposal.get("proposals", []):
            segments.append(
                (
                    " ".join(str(item.get(key, "")) for key in ("title", "problem", "proposal")),
                    item,
                )
            )
        for text, payload in segments:
            if not text.strip():
                continue
            if mentions_other_request(text, request, all_requests):
                continue
            score, direct_match = score_request_match(request, proposal, text)
            if score <= 0:
                continue
            matches.append(
                {
                    "agent": proposal.get("agent", "unknown"),
                    "text": text.strip(),
                    "score": score,
                    "direct_match": direct_match,
                    "blocked_by": payload.get("blocked_by", []),
                    "title": payload.get("title"),
                    "recommendation": payload.get("recommendation") or payload.get("proposal"),
                }
            )

    matches.sort(key=lambda item: item["score"], reverse=True)
    direct_matches = [match for match in matches if match.get("direct_match")]
    if direct_matches:
        top_direct = direct_matches[0]["score"]
        matches = [
            match
            for match in matches
            if match.get("direct_match") or match["score"] >= max(10, top_direct - 20)
        ]
    matches = matches[:6]
    if not matches:
        return None

    status, blocked_by = derive_request_status(matches)
    timestamp = now_aest().strftime("%Y-%m-%d %H:%M AEST")
    agents = sorted({match["agent"] for match in matches})
    findings: list[str] = []
    next_steps: list[str] = []
    seen_titles: set[str] = set()
    seen_recommendations: set[str] = set()

    for match in matches:
        title = str(match.get("title") or "").strip()
        recommendation = str(match.get("recommendation") or "").strip()
        if title and title not in seen_titles:
            findings.append(f"{match['agent']}: {title}")
            seen_titles.add(title)
        if recommendation and recommendation not in seen_recommendations:
            next_steps.append(recommendation)
            seen_recommendations.add(recommendation)

    lines = [
        f"## {timestamp} - CEO Team",
        "",
        "### Status",
        status,
        "",
        "### Run",
        f"- `run_id`: `{run_id}`",
        f"- `agents`: {', '.join(agents)}",
        "",
        "### What we concluded",
    ]
    for line in [match["text"] for match in matches[:2] if match["text"]]:
        lines.append(f"- {line}")

    lines.extend(["", "### Findings"])
    if findings:
        lines.extend([f"- {item}" for item in findings[:5]])
    else:
        lines.append("- No structured findings captured for this thread in this run.")

    lines.extend(["", "### Blockers"])
    if blocked_by:
        lines.extend([f"- {item}" for item in blocked_by])
    else:
        lines.append("- None recorded.")

    lines.extend(["", "### Next steps"])
    if next_steps:
        lines.extend([f"- {item}" for item in next_steps[:4]])
    else:
        lines.append("- No next step recorded yet.")

    if status == "waiting_on_will":
        lines.extend(
            [
                "",
                "### Questions for Will",
                "- Please add the missing scope, desired outcome, and constraints in the original request file so we can schedule this properly.",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def sync_founder_request_responses(run_id: str, proposals: list[dict[str, Any]]) -> list[Path]:
    """Write CEO team responses as conversation threads.

    Recommendation 3 (OpenClaw pattern): Bidirectional founder request threads.
    Responses are appended directly to the original request file AND to the
    legacy responses/ directory for backwards compatibility.
    """
    responses_dir = FOUNDER_REQUESTS_DIR / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    updated_paths: list[Path] = []
    requests = load_founder_requests()
    for request in requests:
        section = build_request_response_section(run_id, request, proposals, requests)
        if not section:
            continue

        # Legacy: write to responses/ directory (backwards compat)
        response_path = responses_dir / request["filename"]
        existing_response = response_path.read_text(encoding="utf-8") if response_path.exists() else ""
        if run_id not in existing_response:
            prefix = "" if not existing_response.strip() else "\n"
            response_path.write_text(existing_response + prefix + section, encoding="utf-8")

        # Bidirectional: append to the original request file as a conversation
        request_path: Path = request["path"]
        existing_request = request_path.read_text(encoding="utf-8") if request_path.exists() else ""
        if run_id not in existing_request:
            # Add a separator if there isn't one already
            separator = "\n\n---\n\n" if not existing_request.rstrip().endswith("---") else "\n\n"
            request_path.write_text(existing_request.rstrip() + separator + section, encoding="utf-8")
            updated_paths.append(request_path)
    return updated_paths


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


def run_snapshot_guard(manifest: dict[str, Any]) -> SnapshotReport:
    """Run the engineering snapshot guard against the manifest.

    Returns the report. If Tuesday-critical inputs are missing on a Tuesday,
    raises RuntimeError to block the founder-facing review.
    """
    # Write manifest to a temp file so build_report_from_manifest can read it
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(manifest, f)
        tmp_path = Path(f.name)
    try:
        report = build_report_from_manifest(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if report.status == "degraded":
        log(f"Snapshot guard: DEGRADED — missing {len(report.missing_files)} files, {len(report.missing_dirs)} dirs")
        for path in report.missing_files:
            log(f"  missing file: {path}")
        for path in report.missing_dirs:
            log(f"  missing dir:  {path}")

    if report.missing_tuesday_critical:
        weekday = now_aest().strftime("%A")
        if weekday == "Tuesday":
            raise RuntimeError(
                "Tuesday-critical inputs missing; blocking founder-facing review.\n"
                + "\n".join(f"  - {p}" for p in report.missing_tuesday_critical)
            )
        else:
            log(f"Snapshot guard: Tuesday-critical inputs missing (non-Tuesday, continuing): "
                f"{report.missing_tuesday_critical}")

    return report


def start_run(
    sm,
    agents_requested: list[str],
    manifest: dict[str, Any],
    snapshot_guard: SnapshotReport | None = None,
) -> str:
    run_id = f"{DATE_STR}_{now_aest().strftime('%H%M%S')}"
    guard_dict = asdict(snapshot_guard) if snapshot_guard else None
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
            "snapshot_guard": guard_dict,
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

    # Each agent gets its own working directory to avoid parallel cp -r races
    # on the shared "context" dir in sandbox.
    agent_workdir = f"/tmp/ceo_workdir_{agent_id}"
    remote_cmd = f"""
set -e
rm -rf {agent_workdir}
mkdir -p {agent_workdir}/proposals {agent_workdir}/{agent_id} {agent_workdir}/agent-memory/{agent_id}
cp -r {REMOTE_DIR}/context {agent_workdir}/context
# Pre-populate with existing specialist proposals so chief_of_staff can read them
cp -f {REMOTE_DIR}/sandbox/proposals/{DATE_STR}_*.json {agent_workdir}/proposals/ 2>/dev/null || true
cd {agent_workdir}
bash {REMOTE_DIR}/ceo-agent-prompts.sh {agent_id} {DATE_STR} > /tmp/ceo_prompt_{agent_id}.txt
set +e
timeout {SESSION_TIMEOUT_SECONDS}s codex exec -m {CODEX_MODEL} --full-auto --skip-git-repo-check -o /tmp/ceo_output_{agent_id}.txt "$(cat /tmp/ceo_prompt_{agent_id}.txt)" >/tmp/ceo_stdout_{agent_id}.log 2>&1
rc=$?
set -e
# Copy outputs back to the persistent sandbox
mkdir -p {REMOTE_DIR}/sandbox/proposals {REMOTE_DIR}/sandbox/{agent_id} {REMOTE_DIR}/sandbox/agent-memory/{agent_id}
cp -f {agent_workdir}/proposals/{DATE_STR}_{agent_id}.json {REMOTE_DIR}/sandbox/proposals/ 2>/dev/null || true
cp -rf {agent_workdir}/agent-memory/{agent_id}/. {REMOTE_DIR}/sandbox/agent-memory/{agent_id}/ 2>/dev/null || true
cp -rf {agent_workdir}/{agent_id}/. {REMOTE_DIR}/sandbox/{agent_id}/ 2>/dev/null || true
echo "__AGENT_RC__:$rc"
if [ -f {REMOTE_DIR}/sandbox/proposals/{DATE_STR}_{agent_id}.json ]; then
  stat -c "__PROPOSAL__:%n|%Y|%s" {REMOTE_DIR}/sandbox/proposals/{DATE_STR}_{agent_id}.json
else
  echo "__PROPOSAL__:missing"
fi
tail -n 40 /tmp/ceo_stdout_{agent_id}.log 2>/dev/null || true
rm -rf {agent_workdir}
"""
    result = ssh_run(remote_cmd, timeout=SESSION_TIMEOUT_SECONDS + 300)  # session timeout + 5 min buffer
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

    # Check for Telegram messages from the agent
    _check_and_send_telegram(agent_id)

    # Check for deployment manifests and Will tasks
    _process_deploy_manifests(agent_id)
    _process_will_tasks(agent_id)

    return {
        "agent": agent_id,
        "success": success,
        "exit_code": rc,
        "proposal": proposal_meta,
        "stdout_tail": tail_lines[-20:],
        "stderr_excerpt": (result.stderr or "")[:800],
    }


def _check_and_send_telegram(agent_id: str) -> None:
    """Check if agent left a Telegram message for the founder and send it."""
    remote_msg_path = f"{REMOTE_DIR}/sandbox/agent-memory/{agent_id}/telegram_message.txt"
    result = ssh_run(f"cat {remote_msg_path} 2>/dev/null", timeout=15)
    if result.returncode != 0 or not result.stdout.strip():
        return

    msg_content = result.stdout.strip()
    log(f"📱 {agent_id} has a Telegram message for Will")

    # Send via both Telegram and Chat Agent
    telegram_text = f"🤖 *{agent_id.replace('_', ' ').title()} Agent*\n\n{msg_content}"
    orch_dir = Path(__file__).resolve().parent.parent
    try:
        import subprocess as _sp
        # Telegram notification
        _sp.run(
            ["/home/fields/venv/bin/python3", "scripts/telegram_notify.py", telegram_text],
            capture_output=True, text=True, timeout=30, cwd=str(orch_dir),
        )
        log(f"  ✅ Telegram message sent")
    except Exception as exc:
        log(f"  ❌ Telegram send failed: {exc}")

    try:
        import subprocess as _sp
        # Also post to Chat Agent as a system message so it shows in Will's next conversation
        from shared.db import get_client as _tg_client
        _client = _tg_client()
        _client["system_monitor"]["agent_messages"].insert_one({
            "agent": agent_id,
            "message": msg_content,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        })
        log(f"  ✅ Message queued for Chat Agent")
    except Exception as exc:
        log(f"  ⚠ Chat Agent queue failed (non-critical): {exc}")

    # Clear the message file so it doesn't re-send
    ssh_run(f"rm -f {remote_msg_path}", timeout=10)


def _process_deploy_manifests(agent_id: str) -> None:
    """Check for DEPLOY.json and trigger immediate implementation via Opus."""
    remote_deploy = f"{REMOTE_DIR}/sandbox/{agent_id}/DEPLOY.json"
    result = ssh_run(f"cat {remote_deploy} 2>/dev/null", timeout=15)
    if result.returncode != 0 or not result.stdout.strip():
        return

    log(f"🔧 {agent_id} has a DEPLOY.json — processing immediately")

    try:
        manifest = json.loads(result.stdout)
    except json.JSONDecodeError:
        log(f"  ❌ Invalid DEPLOY.json from {agent_id}")
        return

    requires_approval = manifest.get("requires_approval", True)
    description = manifest.get("description", "No description")

    if requires_approval:
        # Notify Will and wait
        approval_reason = manifest.get("approval_reason", "Approval required")
        msg = (
            f"🔧 *{agent_id}* wants to deploy:\n\n"
            f"{description}\n\n"
            f"Reason for approval: {approval_reason}\n\n"
            f"Reply 'approve' to proceed."
        )
        _check_and_send_telegram.__wrapped__ if hasattr(_check_and_send_telegram, '__wrapped__') else None
        # Use the telegram notify directly
        try:
            orch_dir = Path(__file__).resolve().parent.parent
            import subprocess as _sp
            _sp.run(
                ["/home/fields/venv/bin/python3", str(orch_dir / "scripts" / "telegram_notify.py"), msg],
                capture_output=True, text=True, timeout=30, cwd=str(orch_dir),
            )
            log(f"  📱 Approval request sent to Will: {description}")
        except Exception as exc:
            log(f"  ⚠ Telegram failed: {exc}")

        # Queue in DB for Chat Agent
        try:
            from shared.db import get_client as _deploy_client
            _client = _deploy_client()
            _client["system_monitor"]["agent_messages"].insert_one({
                "agent": agent_id,
                "type": "deploy_approval",
                "message": msg,
                "manifest": manifest,
                "status": "pending_approval",
                "created_at": datetime.now().isoformat(),
            })
        except Exception:
            pass

        log(f"  ⏳ Waiting for approval — implementation bridge will pick this up")
    else:
        # Autonomous — trigger implementation bridge immediately
        log(f"  ✅ Autonomous deployment — triggering bridge")
        try:
            orch_dir = Path(__file__).resolve().parent.parent
            import subprocess as _sp
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            env["GH_CONFIG_DIR"] = "/home/projects/.config/gh"
            _sp.Popen(
                ["/home/fields/venv/bin/python3", str(orch_dir / "scripts" / "agent-implementation-bridge.py")],
                cwd=str(orch_dir), env=env,
                stdout=open(str(orch_dir / "logs" / "implementation-bridge.log"), "a"),
                stderr=open(str(orch_dir / "logs" / "implementation-bridge.log"), "a"),
            )
            log(f"  🚀 Implementation bridge launched for {agent_id}")
        except Exception as exc:
            log(f"  ❌ Bridge launch failed: {exc}")

    # Clear the deploy manifest
    ssh_run(f"rm -f {remote_deploy}", timeout=10)


def _process_will_tasks(agent_id: str) -> None:
    """Check for will_tasks.json and merge into Will's task list."""
    remote_tasks = f"{REMOTE_DIR}/sandbox/agent-memory/{agent_id}/will_tasks.json"
    result = ssh_run(f"cat {remote_tasks} 2>/dev/null", timeout=15)
    if result.returncode != 0 or not result.stdout.strip():
        return

    log(f"📋 {agent_id} has tasks for Will")

    try:
        task_data = json.loads(result.stdout)
        tasks = task_data.get("tasks", [])
    except json.JSONDecodeError:
        log(f"  ❌ Invalid will_tasks.json from {agent_id}")
        return

    try:
        from shared.db import get_client as _task_client
        _client = _task_client()
        db = _client["system_monitor"]

        for task in tasks:
            task["assigned_by"] = agent_id
            task["assigned_at"] = datetime.now().isoformat()
            task["status"] = "pending"
            db["will_tasks"].insert_one(task)
            urgency = task.get("urgency", "this_week")
            log(f"  📌 [{urgency}] {task.get('title', '?')}")

            # Urgent tasks get a Telegram ping
            if urgency == "today":
                try:
                    orch_dir = Path(__file__).resolve().parent.parent
                    import subprocess as _sp
                    msg = f"📌 *Task from {agent_id}:*\n{task.get('title', '?')}\n\n{task.get('detail', '')}"
                    _sp.run(
                        ["/home/fields/venv/bin/python3", str(orch_dir / "scripts" / "telegram_notify.py"), msg],
                        capture_output=True, text=True, timeout=30, cwd=str(orch_dir),
                    )
                except Exception:
                    pass

    except Exception as exc:
        log(f"  ❌ Task processing failed: {exc}")

    # Clear the tasks file
    ssh_run(f"rm -f {remote_tasks}", timeout=10)


def _launch_opus_bridge() -> None:
    """Launch the Opus bridge in the background so agents can request help mid-session."""
    bridge_script = Path(__file__).resolve().parent / "agent-opus-bridge.py"
    if not bridge_script.exists():
        log("⚠ agent-opus-bridge.py not found — agents cannot call Opus for help")
        return
    try:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        env["GH_CONFIG_DIR"] = "/home/projects/.config/gh"
        log_file = Path(__file__).resolve().parent.parent / "logs" / "opus-bridge.log"
        subprocess.Popen(
            ["/home/fields/venv/bin/python3", str(bridge_script)],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env,
            stdout=open(str(log_file), "a"),
            stderr=open(str(log_file), "a"),
        )
        log("🌉 Opus bridge launched — agents can request help during sessions")
    except Exception as exc:
        log(f"⚠ Opus bridge launch failed: {exc}")


def fetch_agent_memory_updates(agent_ids: list[str]) -> int:
    """Fetch memory files written by agents during their run and save locally.

    Agents write to agent-memory/<agent_id>/MEMORY.md and daily log files.
    We pull these back so they persist across runs (Recommendation 2).
    """
    updated = 0
    for agent_id in agent_ids:
        remote_mem_dir = f"{REMOTE_DIR}/sandbox/agent-memory/{agent_id}"
        result = ssh_run(f"ls {remote_mem_dir}/*.md 2>/dev/null", timeout=15)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        local_dir = AGENT_MEMORY_DIR / agent_id
        local_dir.mkdir(parents=True, exist_ok=True)
        for remote_path in result.stdout.strip().splitlines():
            remote_path = remote_path.strip()
            if not remote_path:
                continue
            filename = Path(remote_path).name
            fetched = ssh_run(f"cat {remote_path}", timeout=15)
            if fetched.returncode != 0 or not fetched.stdout.strip():
                continue
            local_path = local_dir / filename
            # Only update if content differs from local
            existing = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
            if fetched.stdout.strip() != existing.strip():
                local_path.write_text(fetched.stdout, encoding="utf-8")
                updated += 1
                log(f"  Updated agent memory: {agent_id}/{filename}")
    return updated


def push_to_github() -> None:
    log("Pushing to GitHub sandbox repo...")
    result = ssh_run(
        f"""
GH_CONFIG_DIR=~/.config/gh gh auth setup-git >/dev/null 2>&1 || true
cd {REMOTE_DIR}/sandbox
rm -rf context context_*
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
    refs = [f"{REMOTE_DIR}/sandbox/proposals/{DATE_STR}_{agent}.json" for agent in agent_ids]
    proposals: list[dict[str, Any]] = []
    for ref in refs:
        result = ssh_run(f"cat {ref} 2>/dev/null", timeout=30)
        raw = (result.stdout or "").strip()
        if not raw:
            continue
        try:
            proposals.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            log(f"Skipping malformed proposal file {ref}: {exc}")
    return proposals


def fetch_available_remote_proposals() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result = ssh_run(
        f"cd {REMOTE_DIR}/sandbox/proposals && ls -1 {DATE_STR}_*.json 2>/dev/null | sed 's#^#{REMOTE_DIR}/sandbox/proposals/#'",
        timeout=30,
    )
    refs = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if not refs:
        return [], []
    proposals: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for ref in refs:
        fetched = ssh_run(f"cat {ref} 2>/dev/null", timeout=30)
        raw = (fetched.stdout or "").strip()
        if not raw:
            continue
        try:
            proposals.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            invalid.append({"path": ref, "raw": raw, "error": str(exc)})
    return proposals, invalid


def validate_proposal(proposal: dict[str, Any]) -> tuple[bool, list[str]]:
    """Recommendation 4: Quality gates for proposal output."""
    issues: list[str] = []
    agent = proposal.get("agent", "unknown")

    if not proposal.get("findings"):
        issues.append(f"{agent}: No findings produced")
    if not proposal.get("proposals"):
        issues.append(f"{agent}: No proposals produced")
    if not proposal.get("summary"):
        issues.append(f"{agent}: No summary produced")

    for finding in proposal.get("findings", []):
        if not finding.get("evidence_freshness"):
            issues.append(f"{agent}: Finding '{finding.get('title', '?')}' missing evidence_freshness")
        if finding.get("detail") and finding.get("detail") == finding.get("recommendation"):
            issues.append(f"{agent}: Finding '{finding.get('title', '?')}' has identical detail and recommendation")

    return len(issues) == 0, issues


def compute_staleness(proposal: dict[str, Any], previous_proposals: list[dict[str, Any]]) -> dict[str, Any]:
    """Recommendation 4: Detect recycled/stale proposals by comparing finding titles."""
    agent = proposal.get("agent", "unknown")
    current_titles = {f.get("title", "").strip().lower() for f in proposal.get("findings", []) if f.get("title")}
    if not current_titles:
        return {"agent": agent, "staleness_score": 0.0, "novel_count": 0, "recycled_count": 0, "is_stale": False}

    previous_titles: set[str] = set()
    for prev in previous_proposals:
        if prev.get("agent") == agent:
            for f in prev.get("findings", []):
                title = f.get("title", "").strip().lower()
                if title:
                    previous_titles.add(title)

    recycled = current_titles & previous_titles
    novel = current_titles - previous_titles
    staleness_score = len(recycled) / len(current_titles) if current_titles else 0.0

    return {
        "agent": agent,
        "staleness_score": round(staleness_score, 2),
        "novel_count": len(novel),
        "recycled_count": len(recycled),
        "novel_titles": sorted(novel),
        "recycled_titles": sorted(recycled),
        "is_stale": staleness_score > 0.8 and len(current_titles) >= 3,
    }


def normalize_proposal(proposal: dict[str, Any], run_id: str) -> dict[str, Any]:
    proposal.setdefault("status", "pending_review")
    proposal.setdefault("reviewed_by", None)
    proposal.setdefault("review_notes", None)
    proposal.setdefault("handoffs", [])
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


def format_list(values: list[Any]) -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    return ", ".join(clean) if clean else "None"


def render_findings_md(findings: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    if not findings:
        return ["No findings recorded.", ""]
    for finding in findings:
        severity = str(finding.get("severity", "unknown")).upper()
        title = finding.get("title", "Untitled finding")
        lines.append(f"- [{severity}] **{title}**")
        detail = finding.get("detail")
        if detail:
            lines.append(f"  {detail}")
        recommendation = finding.get("recommendation")
        if recommendation:
            lines.append(f"  Recommendation: {recommendation}")
        lines.append(
            f"  Confidence: `{finding.get('confidence', 'unknown')}` | Freshness: `{finding.get('evidence_freshness', 'unknown')}`"
        )
        blocked_by = format_list(finding.get("blocked_by", []))
        data_gaps = format_list(finding.get("data_gaps", []))
        lines.append(f"  Blocked by: {blocked_by}")
        lines.append(f"  Data gaps: {data_gaps}")
    lines.append("")
    return lines


def render_proposals_md(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    if not items:
        return ["No proposals recorded.", ""]
    for item in items:
        priority = str(item.get("priority", "unknown")).upper()
        title = item.get("title", "Untitled proposal")
        lines.append(f"- [{priority}] **{title}**")
        problem = item.get("problem")
        if problem:
            lines.append(f"  Problem: {problem}")
        detail = item.get("proposal") or item.get("description") or item.get("solution")
        if detail:
            lines.append(f"  Proposal: {detail}")
        lines.append(
            f"  Owner: `{item.get('owner', 'unknown')}` | Time horizon: `{item.get('time_horizon', 'unknown')}` | Decision required: `{item.get('decision_required', False)}`"
        )
        lines.append(
            f"  Confidence: `{item.get('confidence', 'unknown')}` | Freshness: `{item.get('evidence_freshness', 'unknown')}`"
        )
        lines.append(f"  Depends on: {format_list(item.get('depends_on', []))}")
        lines.append(f"  Blocks: {format_list(item.get('blocks', []))}")
        lines.append(f"  Blocked by: {format_list(item.get('blocked_by', []))}")
        lines.append(f"  Data gaps: {format_list(item.get('data_gaps', []))}")
    lines.append("")
    return lines


def render_run_summary(
    run_id: str,
    proposals: list[dict[str, Any]],
    manifest: dict[str, Any],
    agent_results: dict[str, Any],
    run_status: str = "unknown",
    error_message: str | None = None,
    invalid_files: list[dict[str, Any]] | None = None,
    snapshot_guard: SnapshotReport | None = None,
) -> str:
    generated_at = now_aest().strftime("%Y-%m-%d %H:%M:%S AEST")
    guard_status = snapshot_guard.status if snapshot_guard else "not_run"
    lines = [
        f"# CEO Agent Run Summary - {run_id}",
        "",
        f"- Date: `{DATE_STR}`",
        f"- Generated: `{generated_at}`",
        f"- Run status: `{run_status}`",
        f"- Context degraded: `{manifest.get('degraded', False)}`",
        f"- Snapshot guard: `{guard_status}`",
        f"- Agents with proposals: `{', '.join(sorted(p.get('agent', 'unknown') for p in proposals)) or 'none'}`",
        "",
    ]
    if error_message:
        lines.extend(["## Run Error", "", error_message, ""])
    if snapshot_guard and snapshot_guard.status == "degraded":
        lines.extend(["## Snapshot Guard", ""])
        if snapshot_guard.missing_files:
            lines.append("Missing files:")
            for path in snapshot_guard.missing_files:
                lines.append(f"- `{path}`")
            lines.append("")
        if snapshot_guard.missing_dirs:
            lines.append("Missing dirs:")
            for path in snapshot_guard.missing_dirs:
                lines.append(f"- `{path}`")
            lines.append("")
        if snapshot_guard.missing_tuesday_critical:
            lines.append("Tuesday-critical missing:")
            for path in snapshot_guard.missing_tuesday_critical:
                lines.append(f"- `{path}`")
            lines.append("")
    lines.extend(["## Agent Status", ""])
    if agent_results:
        for agent_id in sorted(agent_results):
            result = agent_results[agent_id]
            proposal_state = "present" if result.get("proposal", {}).get("present") else "missing"
            lines.append(
                f"- `{agent_id}`: success=`{result.get('success', False)}` exit_code=`{result.get('exit_code')}` proposal=`{proposal_state}`"
            )
    else:
        lines.append("- No agent execution metadata captured in this artifact.")
    lines.append("")
    if invalid_files:
        lines.extend(["## Parse Warnings", ""])
        for item in invalid_files:
            lines.append(f"- `{Path(item.get('path', 'unknown')).name}`: {item.get('error', 'Unknown parse error')}")
        lines.append("")

    for proposal in sorted(proposals, key=lambda item: item.get("agent", "")):
        agent = proposal.get("agent", "unknown")
        lines.extend(
            [
                f"## {agent.replace('_', ' ').title()}",
                "",
                f"**Summary:** {proposal.get('summary', 'No summary provided.')}",
                "",
                "### Findings",
                "",
            ]
        )
        lines.extend(render_findings_md(proposal.get("findings", [])))
        lines.extend(["### Proposals", ""])
        lines.extend(render_proposals_md(proposal.get("proposals", [])))
        if agent == "chief_of_staff":
            top_3 = proposal.get("top_3") or []
            do_not_do = proposal.get("do_not_do") or []
            sequence = proposal.get("recommended_sequence") or []
            lines.extend(["### Chief Of Staff Notes", ""])
            if top_3:
                lines.append("Top 3:")
                lines.extend([f"- {item}" for item in top_3])
                lines.append("")
            if do_not_do:
                lines.append("Do not do:")
                lines.extend([f"- {item}" for item in do_not_do])
                lines.append("")
            if sequence:
                lines.append("Recommended sequence:")
                lines.extend([f"{index}. {item}" for index, item in enumerate(sequence, start=1)])
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_local_run_artifacts(
    run_id: str,
    proposals: list[dict[str, Any]],
    manifest: dict[str, Any],
    agent_results: dict[str, Any],
    run_status: str = "unknown",
    snapshot_guard: SnapshotReport | None = None,
    error_message: str | None = None,
    invalid_files: list[dict[str, Any]] | None = None,
) -> Path:
    run_dir = LOCAL_RUNS_DIR / DATE_STR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / "summary.md"
    summary_path.write_text(
        render_run_summary(run_id, proposals, manifest, agent_results, run_status, error_message, invalid_files),
        encoding="utf-8",
    )

    metadata = {
        "run_id": run_id,
        "date": DATE_STR,
        "generated_at": now_aest().isoformat(),
        "run_status": run_status,
        "error_message": error_message,
        "context_degraded": manifest.get("degraded", False),
        "agent_results": agent_results,
        "proposal_agents": sorted(proposal.get("agent", "unknown") for proposal in proposals),
        "invalid_files": invalid_files or [],
    }
    (run_dir / "run.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (run_dir / "context_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    for proposal in proposals:
        agent = proposal.get("agent", "unknown")
        filename = f"{DATE_STR}_{agent}.json"
        (run_dir / filename).write_text(json.dumps(proposal, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    for item in invalid_files or []:
        path = Path(item.get("path", "unknown.json"))
        filename = f"{path.stem}.invalid.json"
        (run_dir / filename).write_text((item.get("raw", "") + "\n"), encoding="utf-8")
        (run_dir / f"{path.stem}.error.txt").write_text(f"{item.get('error', 'Unknown parse error')}\n", encoding="utf-8")

    latest_dir = LOCAL_RUNS_DIR
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "LATEST_RUN.txt").write_text(f"{run_dir}\n", encoding="utf-8")
    (latest_dir / "LATEST_SUMMARY.md").write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")

    # Mirror proposals to a stable root-level proposals/ directory so the
    # chief-of-staff agent (and the founder) can find them without digging
    # through timestamped run artifact directories.
    LOCAL_PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    for proposal in proposals:
        agent = proposal.get("agent", "unknown")
        filename = f"{DATE_STR}_{agent}.json"
        (LOCAL_PROPOSALS_DIR / filename).write_text(json.dumps(proposal, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (LOCAL_PROPOSALS_DIR / "LATEST_RUN.txt").write_text(f"{run_id}\n", encoding="utf-8")

    return run_dir


def write_run_failure_artifact(
    run_id: str,
    manifest: dict[str, Any] | None,
    agent_results: dict[str, Any],
    error_message: str,
    proposals: list[dict[str, Any]] | None = None,
    invalid_files: list[dict[str, Any]] | None = None,
) -> Path:
    return write_local_run_artifacts(
        run_id=run_id,
        proposals=proposals or [],
        manifest=manifest or {"degraded": True},
        agent_results=agent_results,
        run_status="failed",
        error_message=error_message,
        invalid_files=invalid_files,
    )


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
                "$setOnInsert": {"first_seen": now},
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
                "$setOnInsert": {"first_seen": now},
                "$inc": {"times_seen": 1},
            },
            upsert=True,
        )


def store_proposals(sm, run_id: str, proposals: list[dict[str, Any]]) -> list[str]:
    stored_agents: list[str] = []
    coll = sm["ceo_proposals"]

    # Recommendation 4: Fetch recent proposals for staleness comparison
    from datetime import timedelta as _td
    recent_cutoff = (now_aest() - _td(days=3)).strftime("%Y-%m-%d")
    previous_proposals = list(
        coll.find({"date": {"$gte": recent_cutoff}}, {"_id": 0, "agent": 1, "findings": 1}).limit(30)
    )

    for raw in proposals:
        proposal = normalize_proposal(raw, run_id)

        # Quality gate
        valid, issues = validate_proposal(proposal)
        if issues:
            log(f"  ⚠ Quality issues for {proposal['agent']}: {'; '.join(issues)}")
        proposal["quality_valid"] = valid
        proposal["quality_issues"] = issues

        # Staleness detection
        staleness = compute_staleness(proposal, previous_proposals)
        proposal["staleness"] = staleness
        if staleness["is_stale"]:
            log(f"  ⚠ STALE: {proposal['agent']} — {staleness['staleness_score']:.0%} recycled findings ({staleness['recycled_count']}/{staleness['recycled_count'] + staleness['novel_count']})")
        elif staleness["novel_count"] > 0:
            log(f"  ✓ {proposal['agent']}: {staleness['novel_count']} novel finding(s)")

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
    parser.add_argument("--sync-latest", action="store_true", help="Fetch today's remote proposals and write local artifacts only")
    return parser.parse_args()


def main() -> None:
    load_env_file()
    args = parse_args()
    team_plan = load_team_plan()
    run_id: str | None = None
    manifest: dict[str, Any] | None = None
    all_results: dict[str, Any] = {}
    successful_agents: list[str] = []
    client = None

    if args.list:
        print("Available agents:")
        for aid, agent in AGENTS.items():
            status = team_plan.get("team", {}).get(aid, {}).get("status", "untracked")
            cadence = team_plan.get("team", {}).get(aid, {}).get("cadence", "manual")
            print(f"  {aid:15s} — {agent['name']}: {agent['focus']} [{status}, {cadence}]")
        return

    # Launch the real-time Opus bridge alongside agents
    _launch_opus_bridge()

    specialists, chiefs = build_agent_plan(args.agent)
    agents_requested = specialists + chiefs
    print(f"CEO Agent Launcher — {DATE_STR}")
    print(f"Agents: {', '.join(agents_requested) if agents_requested else '(none)'}")
    print(f"Model:  {CODEX_MODEL}")
    if args.sync_latest:
        update_remote_repos()
        manifest = read_remote_context_manifest()
        run_id = f"{DATE_STR}_sync_{now_aest().strftime('%H%M%S')}"
        fetched, invalid_files = fetch_available_remote_proposals()
        proposals = [normalize_proposal(item, run_id) for item in fetched]
        if not proposals:
            raise RuntimeError("No remote proposals found to sync.")
        run_dir = write_local_run_artifacts(
            run_id,
            proposals,
            manifest,
            {},
            run_status="synced",
            invalid_files=invalid_files,
        )
        response_paths = sync_founder_request_responses(run_id, proposals)
        if response_paths:
            print(f"Updated founder responses: {', '.join(path.name for path in response_paths)}")
        print(f"Synced {len(proposals)} proposal files to {run_dir}")
        return
    if args.dry_run:
        print("[DRY RUN MODE]")
        return

    try:
        # Always run a fresh context export before launching agents
        print("Running fresh context export...")
        export_result = subprocess.run(
            ["/home/fields/venv/bin/python3", "scripts/ceo-context-export.py"],
            capture_output=True, text=True, timeout=600,
            cwd=str(Path(__file__).resolve().parent.parent),
            env={**os.environ},
        )
        if export_result.returncode == 0:
            print("Context export completed successfully.")
        else:
            log(f"Context export failed (exit {export_result.returncode}), proceeding with existing context")
            if export_result.stderr:
                log(f"  stderr: {export_result.stderr.strip()[:300]}")

        update_remote_repos()
        deploy_prompts()
        manifest = read_remote_context_manifest()
        run_id = f"{DATE_STR}_{now_aest().strftime('%H%M%S')}"
        ensure_context_is_healthy(manifest)

        # Run the engineering snapshot guard for fine-grained input validation
        snapshot_report = run_snapshot_guard(manifest)
        if snapshot_report.status == "ok":
            print("Snapshot guard: all required inputs present.")
        else:
            print(f"Snapshot guard: DEGRADED ({len(snapshot_report.missing_files)} missing files, "
                  f"{len(snapshot_report.missing_dirs)} missing dirs) — proceeding with caution.")

        client = get_client()
        sm = client["system_monitor"]
        run_id = start_run(sm, agents_requested, manifest, snapshot_guard=snapshot_report)

        # Recommendation 1: Run specialists in parallel (OpenClaw pattern)
        specialist_results = {}
        if len(specialists) > 1:
            log(f"Running {len(specialists)} specialists in parallel...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(specialists)) as pool:
                futures = {pool.submit(run_agent, aid): aid for aid in specialists}
                for future in concurrent.futures.as_completed(futures):
                    aid = futures[future]
                    try:
                        specialist_results[aid] = future.result()
                    except Exception as exc:
                        log(f"Agent {aid} raised exception: {exc}")
                        specialist_results[aid] = {
                            "agent": aid, "success": False, "exit_code": -1,
                            "proposal": {"present": False},
                            "stdout_tail": [str(exc)], "stderr_excerpt": str(exc),
                        }
                    update_run(sm, run_id, agent_results={**specialist_results})
        else:
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

        # Recommendation 2: Fetch back agent memory updates
        mem_updated = fetch_agent_memory_updates(successful_agents)
        if mem_updated:
            log(f"Fetched {mem_updated} agent memory updates")

        stored_agents = store_proposals(sm, run_id, proposals)
        response_paths = sync_founder_request_responses(run_id, proposals)

        status = "success" if len(successful_agents) == len(agents_requested if not chiefs or not specialist_failures else specialists) else "partial_failure"
        if specialist_failures:
            status = "partial_failure"
        run_dir = write_local_run_artifacts(run_id, proposals, manifest, all_results, run_status=status)
        update_run(
            sm,
            run_id,
            status=status,
            agents_completed=successful_agents,
            agent_results=all_results,
            specialist_failures=specialist_failures,
            chief_skipped=bool(chiefs and specialist_failures),
            stored_agents=stored_agents,
            founder_response_files=[str(path) for path in response_paths],
            local_artifact_dir=str(run_dir),
            finished_at=now_aest().isoformat(),
        )
        print(f"\nCEO agent run complete.\nLocal artifacts: {run_dir}")
    except Exception as exc:
        if run_id is None:
            run_id = f"{DATE_STR}_{now_aest().strftime('%H%M%S')}"
        error_message = str(exc)
        run_dir = write_run_failure_artifact(run_id, manifest, all_results, error_message)
        if client is not None:
            try:
                sm = client["system_monitor"]
                existing = sm["ceo_runs"].find_one({"_id": run_id}, {"_id": 1})
                if existing:
                    update_run(
                        sm,
                        run_id,
                        status="failed",
                        agents_completed=successful_agents,
                        agent_results=all_results,
                        local_artifact_dir=str(run_dir),
                        error_message=error_message,
                        finished_at=now_aest().isoformat(),
                    )
            except Exception as update_exc:
                log(f"Warning: could not update failed run record: {update_exc}")
        print(f"\nCEO agent run failed.\nLocal artifacts: {run_dir}", file=sys.stderr)
        raise
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
