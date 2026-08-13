#!/usr/bin/env python3
"""
spawn_worker.py — runs queued handoff tasks as separate headless Claude sessions.

Polls system_monitor.spawned_tasks for pending briefs written by
scripts/spawn_task.py, and executes each as its own `claude -p` session on the
Claude Max subscription. The spawned session starts with none of the parent
conversation — only the brief — which is exactly why spawn_task.py enforces the
brief's completeness.

Run as a service: fields-spawn-worker

EXECUTION MODEL
    Mirrors 16_General_Reinforcement_Learning/rl_cycle.sh, which is already the
    proven headless-Claude-on-Max runner on this VM: pinned model id, capped
    turns, hard timeout, self-reported outcome. The env recipe is _clean_env()
    from scripts/samantha/deep_research.py.

⚠ ANTHROPIC_API_KEY MUST BE STRIPPED from the child env. With it set, `claude -p`
bills the metered API instead of the Max subscription — and that account is out
of credits, so the run fails in a way that looks like a model error. CLAUDECODE
and CLAUDE_CODE_SSE_PORT must go too or the nested session refuses to start.

⚠ CONCURRENCY IS 2, DELIBERATELY. Nested sessions share one Max subscription's
rate limits. deep_research.py settled on 3 for short calls; these are 45-minute
sessions, so 2. Raising it does not buy throughput, it just moves the queue
somewhere less visible.

AUTONOMY — WHAT A SPAWNED SESSION MAY DO
    investigate : diagnosis only. No Write/Edit tools granted.
    patch       : may edit, but ONLY inside a git worktree of the orchestrator
                  repo, and can never push (see below).

    There is no `deploy` scope. Website deploys, ad changes and content
    publishing never run unattended — a spawned session produces a verified
    diagnosis and a reviewable diff, and Will ships it.

⚠ THE NO-PUSH GUARANTEE IS ENFORCED, NOT REQUESTED — via TOKEN STRIPPING.
_child_env() removes GITHUB_TOKEN / GH_TOKEN / GH_ENTERPRISE_TOKEN so `gh` has no
credential to fall back on. Prompt instructions alone would not survive a session
that decides it knows better.

⚠ The GH_CONFIG_DIR redirect is NOT the control and never was. gh reads the token
env vars in PREFERENCE to its config dir, and this module's own load_dotenv()
lifts GITHUB_TOKEN out of .env into os.environ. The first spawned session ever
run was tasked with testing this claim and disproved it: it reported back
authenticated as Will954633 with push+admin on both production repos. Do not
reinstate the redirect as the primary control.

⚠ `git push` hanging on this VM (CLAUDE.md Rule 2) is NOT a backstop — it covers
only the git transport. `gh api PUT .../contents/...` is the path this fleet
actually uses to write to GitHub, and it is unaffected by that hang.

⚠ Bash is granted to BOTH scopes because real diagnosis needs db_fields.py,
mongo queries and the venv. So "investigate" is read-only by tool grant and by
instruction, not by sandbox: Bash remains an escape hatch. The worktree, the
missing gh credentials and the absent deploy scope are the controls that hold.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

# Load our own environment rather than trusting the unit file (CLAUDE.md Rule 7.3).
load_dotenv(REPO_ROOT / ".env")

from pymongo import MongoClient  # noqa: E402

from scripts.job_status import job_run  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

COLLECTION = "spawned_tasks"
POLL_INTERVAL = 30
MAX_CONCURRENCY = 2
STALE_CLAIM_SECONDS = 5400          # > the longest permitted task timeout
MAX_ATTEMPTS = 2
CLAUDE_MODEL = "claude-opus-4-8"    # pin the full id — bare `opus` collapses to a stale tier
WORKTREE_ROOT = Path("/home/fields/spawn-worktrees")
RESULT_ROOT = Path("/home/fields/Fields_Orchestrator/artifacts/spawned-tasks")
WEBSITE_DIR = Path("/home/fields/Feilds_Website/01_Website")

TOOLS = {
    "investigate": "Bash,Read,Glob,Grep,WebSearch,WebFetch,TodoWrite",
    "patch": "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite",
}


def _as_utc(dt):
    """Attach UTC to a naive datetime read back from Mongo.

    ⚠ pymongo returns naive datetimes, and naive `.timestamp()` interprets them as
    LOCAL time — Brisbane, UTC+10 on this VM. Comparing that against a UTC epoch
    makes every in-flight task look 10 hours old, so the stale-claim sweep
    reclaimed tasks 30 seconds after starting them and ran a second session on
    top of the first. Measured on the first real run, 2026-08-13.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_client():
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        raise RuntimeError("COSMOS_CONNECTION_STRING not set — cannot poll")
    return MongoClient(uri, retryWrites=False, serverSelectionTimeoutMS=30000)


def _child_env(workdir: Path) -> dict:
    """Env for the spawned session. See the module docstring for why each key goes."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                        "CLAUDECODE", "CLAUDE_CODE_SSE_PORT",
                        # ⚠ THE ACTUAL no-push control. gh reads GITHUB_TOKEN /
                        # GH_TOKEN in PREFERENCE to GH_CONFIG_DIR, and this module's
                        # own load_dotenv() pulls GITHUB_TOKEN out of .env into
                        # os.environ — so the config-dir redirect below was a no-op
                        # and the first spawned session ever run proved it: it came
                        # back authenticated as Will954633 with push+admin on both
                        # production repos. Strip the tokens; the redirect alone
                        # guarantees nothing. See fix-history 2026-08-13
                        # [SPAWN-GH-TOKEN-ESCAPE].
                        "GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN")}
    # Defence in depth only — NOT the control. Kept so that a session which does
    # find a credential still has no hosts.yml to read it from.
    env["GH_CONFIG_DIR"] = "/nonexistent/spawn-no-github-credentials"
    env["SPAWN_WORKDIR"] = str(workdir)
    return env


def _build_prompt(task: dict, result_file: Path, workdir: Path) -> str:
    """Render the brief into a standalone prompt.

    Everything the session knows arrives here. It has no transcript, no memory of
    the conversation that found the problem, and no way to ask a follow-up
    question — so the brief is restated in full rather than summarised.
    """
    b = task["brief"]
    scope = task["scope"]
    files = "\n".join(f"  - {f}" for f in b["known_files"])
    constraints = b.get("constraints") or "(none stated)"

    if scope == "patch":
        scope_rules = (
            f"SCOPE: patch. You are in an isolated git worktree at {workdir}.\n"
            "  - Edit freely HERE. This is a throwaway branch; nothing you do reaches main.\n"
            "  - You CANNOT push, and must not try: gh has no credentials in this session\n"
            "    and `git push` hangs on this VM. Leave your work as commits on this branch.\n"
            "  - Do NOT edit the live tree at /home/fields/Fields_Orchestrator.\n"
        )
    else:
        scope_rules = (
            "SCOPE: investigate. Diagnosis only — you have no Write or Edit tool.\n"
            "  - Do not modify files, even via Bash. If the fix is obvious, describe it\n"
            "    and include a unified diff in your result; do not apply it.\n"
        )

    return f"""You are a Claude session spawned to work ONE task to completion, alone.

You have no prior context. Everything known about this task is below. Nobody is
watching the session and you cannot ask a question — if something is ambiguous,
state the ambiguity in your result and proceed with the most defensible reading.

================ TASK ================
{task['title']}

HOW IT WAS DETECTED (evidence from the session that found it):
{b['detection']}

REPRODUCE IT WITH:
{b['repro']}

FILES/PLACES ALREADY KNOWN TO BE INVOLVED:
{files}

DEFINITION OF DONE (you are judged on exactly this):
{b['success_criteria']}

CONSTRAINTS — things that would make an otherwise-correct answer wrong:
{constraints}
======================================

{scope_rules}
ENVIRONMENT
  - Working directory: {workdir}
  - Orchestrator repo: /home/fields/Fields_Orchestrator (read from here for context)
  - Website code: {WEBSITE_DIR} (NOT a git repo on this VM — never try to commit there)
  - Python venv: source /home/fields/venv/bin/activate
  - Env vars: set -a && source /home/fields/Fields_Orchestrator/.env && set +a
  - MongoDB: from shared.db import get_client
  - Read /home/fields/CLAUDE.md and follow its Mandatory Rules — in particular
    Rule 8: never report data as missing based on a field name you guessed.
    Use `python3 scripts/db_fields.py --find <word>` before any such claim.

METHOD
  1. Reproduce the problem yourself before theorising. A brief can be wrong;
     if you cannot reproduce it, that IS the finding — report it and stop.
  2. Establish the root cause with evidence, not plausibility. Show the query,
     the log line, or the diff that proves it.
  3. State your confidence honestly. "Unverified hypothesis" is a useful result;
     a confident wrong answer is worse than no answer, because it will be acted on.

REPORTING — MANDATORY
Write a JSON file to exactly this path before you finish:
  {result_file}

Shape:
{{
  "outcome": "resolved" | "diagnosed" | "could_not_reproduce" | "blocked",
  "summary": "<3-6 sentences: what you found, and what should happen next>",
  "root_cause": "<the mechanism, with the evidence that proves it>",
  "evidence": ["<command or query>: <what it returned>", ...],
  "confidence": "high" | "medium" | "low",
  "files_touched": ["<paths you changed, [] if none>"],
  "next_step": "<the single most useful next action for a human>",
  "open_questions": ["<anything you could not settle>"]
}}

If you finish without writing that file the run is recorded as a FAILURE
regardless of how much good work you did, because nothing downstream can read
your transcript. Write the file even when the outcome is "blocked".
"""


def _prepare_workdir(task_id: str, task: dict) -> Path:
    """Worktree for patch tasks; the live repo (read-only) for investigations."""
    if task["scope"] != "patch":
        return REPO_ROOT

    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    wt = WORKTREE_ROOT / task_id
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", f"spawn/{task_id}", str(wt), "HEAD"],
        cwd=str(REPO_ROOT), check=True, capture_output=True, text=True, timeout=120,
    )
    return wt


def _worktree_diffstat(wt: Path) -> str:
    """What the session actually changed. Used for the Rule 7b outcome assertion:
    a patch task that reports success having changed nothing has not done the job."""
    try:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=str(wt),
                           capture_output=True, text=True, timeout=60)
        committed = subprocess.run(["git", "diff", "--stat", "HEAD~1", "HEAD"], cwd=str(wt),
                                   capture_output=True, text=True, timeout=60)
        return ((r.stdout or "") + (committed.stdout or "")).strip()
    except Exception:
        return ""


def _cleanup_worktree(task_id: str, wt: Path, keep: bool):
    """Keep a worktree that holds a real diff — it is the deliverable. Remove empty ones."""
    if keep:
        return
    try:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                       cwd=str(REPO_ROOT), capture_output=True, timeout=120)
        subprocess.run(["git", "branch", "-D", f"spawn/{task_id}"],
                       cwd=str(REPO_ROOT), capture_output=True, timeout=60)
    except Exception as exc:
        logger.warning("worktree cleanup failed for %s: %s", task_id, exc)


def _notify(task: dict, result: dict | None, ok: bool):
    """Tell Will. A result nobody reads is the same as no result."""
    try:
        from scripts.telegram_notify import send_message
    except Exception:
        return
    icon = "✅" if ok else "⚠️"
    outcome = (result or {}).get("outcome", "failed")
    summary = (result or {}).get("summary") or (task.get("error") or "")[:400]
    try:
        send_message(
            f"{icon} *Spawned task {outcome}*\n\n"
            f"*{task['title']}*\n"
            f"scope: {task['scope']} · confidence: {(result or {}).get('confidence', 'n/a')}\n\n"
            f"{summary[:900]}\n\n"
            f"next: {(result or {}).get('next_step', '—')}"
        )
    except Exception as exc:
        logger.warning("telegram notify failed: %s", exc)


def run_task(client, task: dict) -> bool:
    """Execute one spawned session end to end. Returns True on a usable result."""
    task_id = str(task["_id"])
    queue = client["system_monitor"][COLLECTION]
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    result_file = RESULT_ROOT / f"{task_id}.json"
    result_file.unlink(missing_ok=True)
    log_file = RESULT_ROOT / f"{task_id}.log"

    logger.info("Running %s [%s] %s", task_id, task["scope"], task["title"][:70])

    wt = REPO_ROOT
    try:
        wt = _prepare_workdir(task_id, task)
    except subprocess.CalledProcessError as exc:
        err = f"worktree setup failed: {(exc.stderr or '')[:300]}"
        queue.update_one({"_id": task["_id"]}, {"$set": {
            "status": "failed", "error": err,
            "finished_at": datetime.now(timezone.utc)}})
        logger.error("%s: %s", task_id, err)
        return False

    prompt = _build_prompt(task, result_file, wt)
    timeout_s = int(task.get("timeout_s") or 2700)

    rc, tail = -1, ""
    try:
        with open(log_file, "w") as lf:
            proc = subprocess.run(
                ["claude", "--model", CLAUDE_MODEL, "-p", prompt,
                 "--allowedTools", TOOLS[task["scope"]],
                 "--max-turns", str(int(task.get("max_turns") or 60))],
                cwd=str(wt), env=_child_env(wt),
                stdout=lf, stderr=subprocess.STDOUT,
                timeout=timeout_s,
            )
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        rc = -9
        logger.error("%s timed out after %ss", task_id, timeout_s)
    except Exception as exc:
        logger.error("%s failed to launch: %s", task_id, exc)

    if log_file.exists():
        tail = log_file.read_text(errors="replace")[-3000:]

    # The result file is the contract. A session that ran cleanly but wrote
    # nothing has produced work no one can read, which is indistinguishable from
    # having done nothing — so it is a failure, not a success with a caveat.
    result = None
    if result_file.exists():
        try:
            result = json.loads(result_file.read_text())
        except json.JSONDecodeError as exc:
            logger.warning("%s wrote unparseable result: %s", task_id, exc)

    diffstat = _worktree_diffstat(wt) if task["scope"] == "patch" else ""
    ok = bool(result) and rc == 0

    if ok and task["scope"] == "patch" and result.get("outcome") == "resolved" and not diffstat:
        # Rule 7b applied to the session itself: "resolved" with an empty
        # worktree means it believes it fixed something it never touched.
        ok = False
        result["outcome"] = "diagnosed"
        result.setdefault("open_questions", []).append(
            "Reported 'resolved' but the worktree is empty — no change was actually made."
        )

    update = {
        "status": "completed" if ok else "failed",
        "finished_at": datetime.now(timezone.utc),
        "result": result,
        "exit_code": rc,
        "output_tail": tail[-3000:],
        "diffstat": diffstat or None,
        "worktree": str(wt) if task["scope"] == "patch" else None,
        "log_file": str(log_file),
    }
    if not ok:
        update["error"] = (
            f"exit={rc}, no result file written" if not result
            else f"exit={rc}"
        )
    queue.update_one({"_id": task["_id"]}, {"$set": update})

    _cleanup_worktree(task_id, wt, keep=bool(diffstat))
    _notify({**task, "error": update.get("error")}, result, ok)
    logger.info("%s -> %s (%s)", task_id, update["status"],
                (result or {}).get("outcome", "no result"))
    return ok


def claim_pending(client, n: int) -> list[dict]:
    """Claim up to n pending tasks, oldest first."""
    queue = client["system_monitor"][COLLECTION]

    # Reclaim anything a crash or restart left mid-flight, otherwise a task
    # strands in "running" forever and silently never gets done.
    cutoff = datetime.now(timezone.utc).timestamp() - STALE_CLAIM_SECONDS
    for stuck in queue.find({"status": "running"}):
        started = _as_utc(stuck.get("started_at"))
        if started and started.timestamp() < cutoff:
            attempts = stuck.get("attempts", 0)
            if attempts >= MAX_ATTEMPTS:
                queue.update_one({"_id": stuck["_id"]}, {"$set": {
                    "status": "failed",
                    "error": f"abandoned after {attempts} attempts (worker restarts)",
                    "finished_at": datetime.now(timezone.utc)}})
                logger.warning("Abandoned %s after %s attempts", stuck["_id"], attempts)
            else:
                queue.update_one({"_id": stuck["_id"]}, {"$set": {"status": "pending"}})
                logger.warning("Reclaimed stale task %s", stuck["_id"])

    claimed = []
    for _ in range(n):
        task = queue.find_one_and_update(
            {"status": "pending", "attempts": {"$lt": MAX_ATTEMPTS}},
            {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)},
             "$inc": {"attempts": 1}},
            sort=[("created_at", 1)],
        )
        if not task:
            break
        claimed.append(task)
    return claimed


def main():
    logger.info("Spawn worker starting (poll %ss, concurrency %s)",
                POLL_INTERVAL, MAX_CONCURRENCY)
    client = get_client()
    pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
    inflight: list = []

    while True:
        try:
            inflight = [f for f in inflight if not f.done()]
            slots = MAX_CONCURRENCY - len(inflight)
            if slots > 0:
                for task in claim_pending(client, slots):
                    # Each task gets its own Mongo client: pymongo is thread-safe
                    # but a long session holding one connection across a 45-minute
                    # run invites a Cosmos idle disconnect on the write-back.
                    inflight.append(pool.submit(_run_isolated, task))
        except Exception as exc:
            logger.error("Poll cycle failed: %s", exc)
        time.sleep(POLL_INTERVAL)


def _run_isolated(task: dict):
    """Run one task on its own connection, heartbeating the outcome."""
    task_id = str(task["_id"])
    client = get_client()
    try:
        # One heartbeat per claimed task rather than per idle tick — an empty
        # queue is a legitimate success, but recording it every 30s would bury
        # the runs that actually did work.
        with job_run("spawn_worker", cadence_hours=168,
                     title="Spawned Task Worker (handoff sessions)") as beat:
            ok = run_task(client, task)
            beat.metrics = {"task_id": task_id, "scope": task["scope"], "ok": int(ok)}
            # Rule 7b — a worker that claims tasks and produces no usable result
            # is broken, not idle. Without this it would report success while
            # every spawned session died on a missing credential.
            if not ok:
                raise RuntimeError(
                    f"spawned task {task_id} produced no usable result — "
                    f"see spawned_tasks.error and {RESULT_ROOT}/{task_id}.log"
                )
            beat.detail = f"{task['title'][:80]} — {(task.get('scope'))}"
    except Exception as exc:
        logger.error("Task %s failed: %s", task_id, exc)
    finally:
        client.close()


if __name__ == "__main__":
    main()
