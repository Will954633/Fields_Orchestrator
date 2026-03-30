#!/usr/bin/env python3
"""
Agent Session Runner — Manages a single agent's 1-hour session with pause/resume.

Instead of one monolithic codex exec call, this runner:
1. Starts the agent session
2. Monitors for Opus requests (request.json)
3. When agent writes a request: pauses the timer, waits for bridge response
4. When response arrives: starts a NEW codex exec with the response injected into context
5. Repeats until total active time reaches 60 minutes or agent stops

The key insight: each codex exec is a "segment" of the session. Between segments,
the runner can inject Opus responses, updated context, or new instructions.

Run on the REMOTE VM (property-scraper):
  python3 /tmp/agent-session-runner.py engineering 2026-03-30

Requires: codex CLI, agent prompts, context directory
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REMOTE_DIR = "/home/fields-orchestrator-vm/ceo-agents"
REQUEST_DIR = "/tmp/ceo_opus_requests"
RESPONSE_DIR = "/tmp/ceo_opus_responses"
SESSION_BUDGET_SECONDS = 3600  # 1 hour total active time
SEGMENT_TIMEOUT = 900  # 15 min per segment (agent can do multiple segments)
CODEX_MODEL = "gpt-5.4"
POLL_INTERVAL = 5  # seconds to check for Opus response


def log(agent, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{agent}] {msg}", flush=True)


def run_segment(agent, date, workdir, segment_num, extra_context=""):
    """Run one codex exec segment. Returns when codex finishes or times out."""

    # Build prompt
    if segment_num == 1:
        # First segment: use the standard prompt
        prompt_file = f"/tmp/ceo_session_prompt_{agent}.txt"
        subprocess.run(
            ["bash", f"{REMOTE_DIR}/ceo-agent-prompts.sh", agent, date],
            stdout=open(prompt_file, "w"), stderr=subprocess.DEVNULL,
        )
        prompt = open(prompt_file).read()
    else:
        # Continuation segment: tell agent to resume with new context
        prompt = f"""## CONTINUATION — Segment {segment_num}

You are resuming your session. Your previous segment ended because you requested help from Opus.

### Opus Response
{extra_context}

### Instructions
- Read the Opus response above
- Continue your work from where you left off
- Your previous deliverables are still in your working directory
- Read your agent-memory/{agent}/ notes to recall what you were doing
- Continue iterating: implement → review → reflect → improve
- All previous rules still apply (autonomy, self-healing, stopping conditions)

Resume now.
"""

    log(agent, f"Starting segment {segment_num} ({SEGMENT_TIMEOUT}s timeout)")

    result = subprocess.run(
        ["timeout", str(SEGMENT_TIMEOUT), "codex", "exec", "-m", CODEX_MODEL,
         "--full-auto", "--skip-git-repo-check", prompt],
        capture_output=True, text=True,
        cwd=workdir,
        timeout=SEGMENT_TIMEOUT + 60,
    )

    log(agent, f"Segment {segment_num} finished (rc={result.returncode})")
    return result


def check_for_request(agent):
    """Check if the agent wrote an Opus request."""
    req_path = f"{REQUEST_DIR}/{agent}/request.json"
    if os.path.exists(req_path):
        try:
            with open(req_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def wait_for_response(agent, timeout=300):
    """Wait for the Opus bridge to deliver a response."""
    resp_path = f"{RESPONSE_DIR}/{agent}/response.json"
    start = time.time()

    while time.time() - start < timeout:
        if os.path.exists(resp_path):
            try:
                with open(resp_path) as f:
                    response = json.load(f)
                # Clear the response file
                os.remove(resp_path)
                return response
            except (json.JSONDecodeError, IOError):
                pass
        time.sleep(POLL_INTERVAL)

    return None


def copy_outputs(agent, workdir):
    """Copy agent outputs back to persistent sandbox."""
    sandbox = f"{REMOTE_DIR}/sandbox"
    os.makedirs(f"{sandbox}/{agent}", exist_ok=True)
    os.makedirs(f"{sandbox}/agent-memory/{agent}", exist_ok=True)

    # Copy deliverables
    agent_dir = f"{workdir}/{agent}"
    if os.path.isdir(agent_dir):
        subprocess.run(["cp", "-rf"] + [f"{agent_dir}/{f}" for f in os.listdir(agent_dir) if not f.startswith("__")] + [f"{sandbox}/{agent}/"], capture_output=True)

    # Copy memory
    mem_dir = f"{workdir}/agent-memory/{agent}"
    if os.path.isdir(mem_dir):
        subprocess.run(["cp", "-rf"] + [f"{mem_dir}/{f}" for f in os.listdir(mem_dir)] + [f"{sandbox}/agent-memory/{agent}/"], capture_output=True)

    # Copy proposals
    for f in Path(f"{workdir}/proposals").glob(f"*_{agent}.json"):
        subprocess.run(["cp", "-f", str(f), f"{sandbox}/proposals/"], capture_output=True)


def run_session(agent, date):
    """Run a full agent session with pause/resume capability."""
    log(agent, f"=== SESSION START (budget: {SESSION_BUDGET_SECONDS}s) ===")

    # Setup workdir
    workdir = f"/tmp/ceo_session_{agent}"
    subprocess.run(["rm", "-rf", workdir])
    os.makedirs(f"{workdir}/proposals", exist_ok=True)
    os.makedirs(f"{workdir}/{agent}", exist_ok=True)
    os.makedirs(f"{workdir}/agent-memory/{agent}", exist_ok=True)

    # Copy context
    subprocess.run(["cp", "-r", f"{REMOTE_DIR}/context", f"{workdir}/context"])
    # Fix symlinks for focus/founder-requests
    os.symlink(f"{workdir}/context/context/focus", f"{workdir}/context/focus") if os.path.isdir(f"{workdir}/context/context/focus") and not os.path.exists(f"{workdir}/context/focus") else None
    os.symlink(f"{workdir}/context/context/founder-requests", f"{workdir}/context/founder-requests") if os.path.isdir(f"{workdir}/context/context/founder-requests") and not os.path.exists(f"{workdir}/context/founder-requests") else None

    # Copy existing proposals and memory
    subprocess.run(["bash", "-c", f"cp -f {REMOTE_DIR}/sandbox/proposals/{date}_*.json {workdir}/proposals/ 2>/dev/null"], capture_output=True)
    subprocess.run(["bash", "-c", f"cp -rf {REMOTE_DIR}/sandbox/agent-memory/{agent}/. {workdir}/agent-memory/{agent}/ 2>/dev/null"], capture_output=True)

    # Setup Opus request/response dirs
    os.makedirs(f"{REQUEST_DIR}/{agent}", exist_ok=True)
    os.makedirs(f"{RESPONSE_DIR}/{agent}", exist_ok=True)

    active_time = 0
    segment_num = 0
    extra_context = ""

    while active_time < SESSION_BUDGET_SECONDS:
        segment_num += 1
        remaining = SESSION_BUDGET_SECONDS - active_time
        segment_timeout = min(SEGMENT_TIMEOUT, remaining)

        log(agent, f"Active time: {active_time}s / {SESSION_BUDGET_SECONDS}s | Segment {segment_num}")

        # Run a segment
        seg_start = time.time()
        result = run_segment(agent, date, workdir, segment_num, extra_context)
        seg_duration = time.time() - seg_start
        active_time += seg_duration

        log(agent, f"Segment {segment_num} ran for {seg_duration:.0f}s | Total active: {active_time:.0f}s")

        # Copy outputs after each segment
        copy_outputs(agent, workdir)

        # Check if agent wrote an Opus request
        request = check_for_request(agent)
        if request:
            log(agent, f"📨 Opus request: {request.get('description', '?')[:80]}")

            # Timer PAUSES here — waiting does not count toward the hour
            log(agent, "⏸ Timer paused — waiting for Opus response")
            response = wait_for_response(agent, timeout=300)

            if response:
                log(agent, f"✅ Opus response received ({response.get('status', '?')})")
                # Format response as context for next segment
                extra_context = json.dumps(response, indent=2)[:4000]
                # Clear the request
                try:
                    os.remove(f"{REQUEST_DIR}/{agent}/request.json")
                except OSError:
                    pass
                # Continue to next segment with response injected
                continue
            else:
                log(agent, "⏰ Opus response timed out (5 min)")
                extra_context = '{"status": "timeout", "note": "Opus did not respond within 5 minutes. Try self-healing or continue with available data."}'
                continue

        # No Opus request — check if agent stopped
        # BUT: do NOT accept a stop in the first 3 segments. Force continuation.
        agent_wants_stop = False
        stop_reason = ""

        stop_file = f"{workdir}/agent-memory/{agent}/session_status.json"
        if os.path.exists(stop_file):
            try:
                status = json.load(open(stop_file))
                if status.get("action") == "STOP":
                    agent_wants_stop = True
                    stop_reason = status.get("reason", "")
            except Exception:
                pass

        if not agent_wants_stop and "STOP_REASON" in (result.stderr or ""):
            agent_wants_stop = True
            # Extract the stop reason
            for line in (result.stderr or "").splitlines():
                if "STOP_REASON" in line:
                    stop_reason = line.strip()
                    break

        if agent_wants_stop and segment_num < 3:
            # FORCE RESTART — too early to stop
            log(agent, f"⚡ Agent tried to stop after segment {segment_num} — FORCING CONTINUATION")
            log(agent, f"  Reason given: {stop_reason[:100]}")

            # List what files exist so far
            existing_files = []
            agent_dir = f"{workdir}/{agent}"
            if os.path.isdir(agent_dir):
                for f in os.listdir(agent_dir):
                    if not f.startswith("__"):
                        existing_files.append(f)

            extra_context = f"""## FORCED CONTINUATION — You stopped too early.

You completed segment {segment_num} and tried to stop with reason: "{stop_reason[:200]}"

That is NOT acceptable. You have used {int(active_time)} seconds of your {SESSION_BUDGET_SECONDS} second budget.
You have {int(SESSION_BUDGET_SECONDS - active_time)} seconds remaining.

Files you have produced so far: {', '.join(existing_files) or 'none'}

## YOUR TASK NOW: Build your own task list and work through it.

Step 1: Create your task list. Write it to agent-memory/{agent}/my_task_list.json
Think about:
- What does the sprint need that doesn't exist yet?
- What would make the biggest difference to the business right now?
- What can YOU specifically build with your skills?
- What are the other agents NOT covering that you could do?
- Include at least ONE exploration task (research something new that might uncover breakthrough ideas)

Step 2: Work through the list, highest value first. Build real deliverables, not proposals.

Step 3: After completing each task, update your task list — mark it done and see if completing it revealed NEW tasks.

You are responsible for finding your own work. You are an employee who looks around and sees what needs doing. The sprint plan is at context/focus/current_sprint.md. The backlog is at context/focus/agent-backlog.md. The milestones are at context/focus/milestone_status.md.

Coordinate with the other agents — read their proposals in proposals/ to see what they are covering. Do NOT duplicate their work. Find the gaps.

You MUST complete at least 2 deliverables before you may stop. Your proposal does not count.
"""
            continue

        elif agent_wants_stop and segment_num >= 3:
            log(agent, f"🛑 Agent stopped after {segment_num} segments: {stop_reason[:100]}")
            break

        if segment_num >= 6:
            log(agent, "🛑 Max segments reached (6)")
            break

        extra_context = ""  # No extra context for natural continuation

    # Final copy
    copy_outputs(agent, workdir)
    log(agent, f"=== SESSION END | {segment_num} segments | {active_time:.0f}s active ===")

    # Write session summary
    summary = {
        "agent": agent,
        "date": date,
        "segments": segment_num,
        "active_seconds": round(active_time),
        "budget_seconds": SESSION_BUDGET_SECONDS,
        "ended_at": datetime.now().isoformat(),
    }
    with open(f"{workdir}/agent-memory/{agent}/session_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    copy_outputs(agent, workdir)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <agent_id> <date>")
        sys.exit(1)

    agent_id = sys.argv[1]
    date_str = sys.argv[2]
    run_session(agent_id, date_str)
