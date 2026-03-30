#!/usr/bin/env python3
"""
Agent-Opus Real-Time Bridge

Monitors CEO agent sessions for help requests. When an agent writes a request,
Opus on this VM handles it and writes the result back so the agent can continue.

The bridge polls the remote VM every 15 seconds for new requests in:
  /tmp/ceo_opus_requests/{agent_id}/request.json

Request format:
{
  "agent": "engineering",
  "type": "run_script|pull_data|fix_file|query_db|general",
  "description": "What I need",
  "command": "optional: exact command to run",
  "urgency": "blocking|helpful",
  "context": "why I need this"
}

The bridge:
1. Reads the request
2. If it's a simple command (run_script, query_db): executes directly
3. If it's complex (fix_file, general): spawns Opus via claude -p
4. Writes the result back to /tmp/ceo_opus_responses/{agent_id}/response.json
5. The agent reads the response and continues working

Run alongside the agent launcher:
  python3 scripts/agent-opus-bridge.py &
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REMOTE_HOST = "fields-orchestrator-vm@35.201.6.222"
ORCHESTRATOR_DIR = Path("/home/fields/Fields_Orchestrator")
REQUEST_DIR = "/tmp/ceo_opus_requests"
RESPONSE_DIR = "/tmp/ceo_opus_responses"
POLL_INTERVAL = 15  # seconds
AGENTS = ["engineering", "product", "growth", "data_quality", "chief_of_staff"]
VENV_PYTHON = "/home/fields/venv/bin/python3"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def ssh_run(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=5", REMOTE_HOST, cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def setup_remote_dirs():
    """Create request/response directories on remote VM."""
    for agent in AGENTS:
        ssh_run(f"mkdir -p {REQUEST_DIR}/{agent} {RESPONSE_DIR}/{agent}")
    log("Remote directories ready")


def check_for_requests() -> list[dict]:
    """Poll remote VM for new help requests from agents."""
    requests = []
    for agent in AGENTS:
        result = ssh_run(f"cat {REQUEST_DIR}/{agent}/request.json 2>/dev/null")
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            req = json.loads(result.stdout)
            req["agent"] = agent
            requests.append(req)
            log(f"📨 Request from {agent}: {req.get('description', '?')[:80]}")
        except json.JSONDecodeError:
            log(f"⚠ Invalid JSON from {agent}")
            # Clear bad request
            ssh_run(f"rm -f {REQUEST_DIR}/{agent}/request.json")
    return requests


def handle_request(req: dict) -> dict:
    """Handle a request and return the result."""
    agent = req["agent"]
    req_type = req.get("type", "general")
    command = req.get("command")
    description = req.get("description", "")

    log(f"🔧 Handling {req_type} request from {agent}...")

    if req_type == "run_script" and command:
        # Execute a specific command on this VM
        try:
            env = os.environ.copy()
            env.update({
                "GH_CONFIG_DIR": "/home/projects/.config/gh",
                "PATH": f"/home/fields/venv/bin:{env.get('PATH', '')}",
            })
            result = subprocess.run(
                ["bash", "-c", f"source /home/fields/venv/bin/activate && set -a && source /home/fields/Fields_Orchestrator/.env && set +a && {command}"],
                capture_output=True, text=True, timeout=120,
                cwd=str(ORCHESTRATOR_DIR), env=env,
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:] if result.returncode != 0 else "",
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "error": "Command timed out after 120s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    elif req_type == "pull_data":
        # Pull specific data from database or files
        try:
            env = os.environ.copy()
            result = subprocess.run(
                ["bash", "-c", f"source /home/fields/venv/bin/activate && set -a && source /home/fields/Fields_Orchestrator/.env && set +a && {command}"],
                capture_output=True, text=True, timeout=60,
                cwd=str(ORCHESTRATOR_DIR), env=env,
            )
            return {
                "status": "success",
                "data": result.stdout[-8000:],
                "error": result.stderr[-1000:] if result.returncode != 0 else "",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    elif req_type == "query_db":
        # Run a ceo-query-broker command
        query = command or description
        try:
            result = subprocess.run(
                [VENV_PYTHON, str(ORCHESTRATOR_DIR / "scripts" / "ceo-query-broker.py")] + query.split(),
                capture_output=True, text=True, timeout=60,
                cwd=str(ORCHESTRATOR_DIR),
            )
            return {
                "status": "success",
                "data": result.stdout[-8000:],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    elif req_type == "fix_file" or req_type == "general":
        # Complex request — spawn Opus
        prompt = f"""An AI agent ({agent}) running on a remote VM needs your help.

REQUEST: {description}
{f"COMMAND SUGGESTION: {command}" if command else ""}
CONTEXT: {req.get('context', 'No additional context')}

Handle this request. You are on the orchestrator VM at /home/fields/Fields_Orchestrator.
Python venv: source /home/fields/venv/bin/activate
Env vars: set -a && source /home/fields/Fields_Orchestrator/.env && set +a

Do what the agent needs and report what you did. Be concise — the agent is waiting for your response."""

        try:
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            env["GH_CONFIG_DIR"] = "/home/projects/.config/gh"

            result = subprocess.run(
                ["claude", "-p", prompt, "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep", "--max-turns", "15"],
                capture_output=True, text=True, timeout=300,
                cwd=str(ORCHESTRATOR_DIR), env=env,
            )
            return {
                "status": "success",
                "response": result.stdout[-4000:],
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "error": "Opus timed out after 5 minutes"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    return {"status": "error", "error": f"Unknown request type: {req_type}"}


def send_response(agent: str, response: dict):
    """Write response back to remote VM for the agent to read."""
    response["handled_at"] = datetime.now().isoformat()
    response_json = json.dumps(response, indent=2)

    # Write to remote
    ssh_run(f"cat > {RESPONSE_DIR}/{agent}/response.json << 'JSONEOF'\n{response_json}\nJSONEOF")

    # Clear the request
    ssh_run(f"rm -f {REQUEST_DIR}/{agent}/request.json")

    status = response.get("status", "?")
    log(f"  ✅ Response sent to {agent} ({status})")


def notify_will(agent: str, req: dict):
    """Send Telegram + Chat Agent notification about agent activity."""
    try:
        msg = f"🔧 *{agent}* requested Opus help:\n{req.get('description', '?')[:200]}"
        subprocess.run(
            [VENV_PYTHON, str(ORCHESTRATOR_DIR / "scripts" / "telegram_notify.py"), msg],
            capture_output=True, text=True, timeout=30, cwd=str(ORCHESTRATOR_DIR),
        )
    except Exception:
        pass


def run_bridge():
    """Main bridge loop."""
    log("=" * 50)
    log("AGENT-OPUS BRIDGE — Starting")
    log(f"Polling every {POLL_INTERVAL}s for requests")
    log("=" * 50)

    # Load env
    env_file = ORCHESTRATOR_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

    setup_remote_dirs()

    idle_cycles = 0
    max_idle = 240  # Stop after 1 hour of no requests (240 * 15s)

    while idle_cycles < max_idle:
        try:
            requests = check_for_requests()

            if not requests:
                idle_cycles += 1
                time.sleep(POLL_INTERVAL)
                continue

            idle_cycles = 0  # Reset on activity

            for req in requests:
                agent = req["agent"]

                # Notify Will about the activity
                notify_will(agent, req)

                # Handle the request
                response = handle_request(req)

                # Send response back
                send_response(agent, response)

        except KeyboardInterrupt:
            log("Bridge interrupted")
            break
        except Exception as e:
            log(f"⚠ Bridge error: {e}")
            time.sleep(POLL_INTERVAL)

    log("Bridge exiting (no requests for 1 hour or interrupted)")


if __name__ == "__main__":
    run_bridge()
