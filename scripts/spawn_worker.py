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

THE SANDBOX — READ THIS BEFORE CHANGING _sandbox_wrap(), _child_env() OR THE PROMPT

    Layers, in the order they are applied (the order MATTERS — see below):
      1. `unshare -rmpf --mount-proc` — private mount AND pid namespace, fresh
         /proc, so the session cannot read the worker's own environment.
      2. investigate scope only: /home/fields bind-mounted and remounted READ-ONLY.
      3. /dev/null bind-mounted over EVERY credential file found by
         _credential_paths() — ~34 of them, plus gh's hosts.yml.
      4. A self-check that aborts with exit 91 if any of those is still readable.
      5. CAP_SYS_ADMIN dropped from the bounding set, so the session cannot
         umount or remount anything back.

    Cosmos still works, deliberately — `shared.db` falls back to
    config/settings.yaml, which is NOT hidden. A session keeps the database access
    real diagnosis needs and loses GitHub, Netlify, Facebook, Google Ads, OpenAI,
    Square, Telegram and the rest.

⚠ WHAT IS PROVEN vs WHAT IS BEST-EFFORT. The read-only WRITE boundary held under
every adversarial test, including against uid 0 (`mount -o remount,rw` → denied).
The CREDENTIAL boundary is defence-in-depth: it enumerates a known surface, and a
credential in a file shape nobody thought of would not be covered. Do not describe
it as a guarantee. Describe it as: four attempts, four defeats, all closed, and a
self-check that fails closed rather than trusting the claim.

⚠ FOUR EARLIER VERSIONS OF THIS CONTROL WERE FALSE. Every one was found by
probing; not one was found by reading the code:
    1. `GH_CONFIG_DIR=/nonexistent` — gh reads GITHUB_TOKEN in preference to its
       config dir. The first spawned session ever run came back with push+admin.
    2. Stripping token vars from the child env — .env was mode 644 and the prompt
       ITSELF said `set -a && source .env`.
    3. /dev/null over .env, bound BEFORE the tree bind — a non-recursive bind of
       /home/fields shadowed the nested mount. findmnt showed the /dev/null bind
       existed while stat read the real 8,132-byte file through it. Only the
       MORE-restricted investigate scope leaked, because patch has no second bind.
    4. Correct ordering, but: uid 0 could simply `umount` the bind; `.env.bak-*`
       copies sat unshadowed beside it; a dozen sibling project .env files were
       open (including live SQUARE production tokens); /proc/<ppid>/environ leaked
       the worker's env; and gh's hosts.yml was world-readable with the oauth
       token in plaintext.
    The pattern every time: the control was asserted at one layer while the
    capability leaked through another. That is why layer 4 exists — the system
    now observes the boundary instead of assuming it.

⚠ DO NOT reintroduce `source .env` into the prompt, and do not "fix" a session
that reports missing credentials by handing them back. A session that cannot
reach Facebook Ads is working as designed.

⚠ `git push` hanging on this VM (CLAUDE.md Rule 2) is NOT a backstop — it covers
only the git transport. `gh api PUT .../contents/...` is the path this fleet
actually uses to write to GitHub, and it is unaffected by that hang.

⚠ ANTHROPIC_API_KEY MUST ALSO BE STRIPPED from the child env. With it set,
`claude -p` bills the metered API instead of the Max subscription — and that
account is out of credits, so the run fails looking like a model error.

⚠ investigate scope additionally remounts /home/fields READ-ONLY inside the
namespace. Bash is granted to both scopes (real diagnosis needs db_fields.py and
mongo queries), so tool restriction alone was never a control: the live tree
carries ~1,000 dirty files and a single `git checkout .` would be unrecoverable.
The read-only remount is what makes "investigate" mean it. Sessions write their
result to /tmp, which stays writable.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

AEST = timezone(timedelta(hours=10))    # Brisbane, no DST

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
MAX_ATTEMPTS = 2
CLAUDE_MODEL = "claude-opus-4-8"    # pin the full id — bare `opus` collapses to a stale tier
WORKTREE_ROOT = Path("/home/fields/spawn-worktrees")
RESULT_ROOT = Path("/home/fields/Fields_Orchestrator/artifacts/spawned-tasks")
WEBSITE_DIR = Path("/home/fields/Feilds_Website/01_Website")
ENV_FILE = REPO_ROOT / ".env"
FIELDS_ROOT = Path("/home/fields")

# Where a sandboxed session writes its result. Must be OUTSIDE /home/fields:
# investigate scope remounts that tree read-only, so the old in-repo path became
# unwritable the moment the sandbox landed.
SESSION_RESULT_ROOT = Path("/tmp/spawn-results")

# A task is stale once its own timeout plus this margin has elapsed — derived
# per-task, never a global constant. A fixed 5400s ceiling silently reintroduced
# the duplicate-run bug for any task given --timeout-s above it: the sweep
# reclaimed a task a live thread still held, rmtree'd the worktree it was editing
# and deleted its result file mid-run.
STALE_MARGIN_SECONDS = 900

# Refuse new claims while the nightly pipeline runs (20:30 AEST scrape, GPT-4
# vision steps, valuation). Two 45-minute Opus sessions on top of that is the
# profile behind the memory lockouts that forced the e2-standard-4 upsize.
QUIET_WINDOW_AEST = (20, 15, 2, 0)   # start_h, start_m, end_h, end_m
LOAD_CEILING = 16.0                  # 4 vCPU; this box idles high, so this is a ceiling not a target

# Markers that mean "the Max subscription is out of quota", copied from the
# established detection in scripts/samantha/max_client.py. Without this, a quota
# outage drains the ENTIRE pending queue to `failed` within two poll cycles —
# each one looking like a bad brief. Same class as [INDEXING-SILENT-ZERO].
QUOTA_MARKERS = ("usage limit", "rate limit", "quota", "exceeded your",
                 "too many requests", "resets at")
QUOTA_BACKOFF_SECONDS = 1800

VALID_OUTCOMES = ("resolved", "diagnosed", "could_not_reproduce")

TOOLS = {
    "investigate": "Bash,Read,Glob,Grep,WebSearch,WebFetch,TodoWrite",
    "patch": "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite",
}

# Set when a quota outage is detected; suppresses claiming until it passes.
_quota_paused_until = 0.0


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


# The ONLY variables a spawned session inherits. Everything else is dropped.
#
# ⚠ ALLOWLIST, NOT DENYLIST — this was a denylist matching TOKEN/SECRET/API_KEY/…
# and an adversarial session read POSTHOG_ALL_ACCESS_KEY straight out of
# /proc/1/environ: the name contains "ACCESS_KEY", which "API_KEY" does not match.
# A denylist has to anticipate every future variable name; an allowlist does not.
# The session's own environment is readable via /proc by anything it spawns, so
# whatever is in here IS exposed to it — add nothing casually.
_ENV_ALLOWLIST = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TERM", "TZ",
    "PWD", "TMPDIR", "VIRTUAL_ENV", "PYTHONPATH", "XDG_RUNTIME_DIR",
)


def _child_env(workdir: Path) -> dict:
    """Minimal env for the spawned session. See the module docstring for the rules."""
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOWLIST}
    # Defence in depth only — NOT the control. Kept so that a session which does
    # find a credential still has no hosts.yml to read it from.
    env["GH_CONFIG_DIR"] = "/nonexistent/spawn-no-github-credentials"
    env["SPAWN_WORKDIR"] = str(workdir)
    env["CI"] = "true"
    return env


def _credential_paths() -> list[str]:
    """Every credential-bearing file a session must not be able to read.

    ⚠ Shadowing ONE .env was never enough, and an adversarial session proved it by
    reading `.env.bak-20260807-092602` — a full unshadowed copy of every secret
    sitting beside the file we hid. It also found live SQUARE production tokens in
    the website's .env and the GitHub oauth_token in plaintext in gh's hosts.yml
    (mode 664). Enumerate the surface; do not protect one path and call it a
    boundary.

    ⚠ config/settings.yaml is deliberately NOT here: it carries the DB URI only,
    and keeping it visible is what preserves Cosmos access for real diagnosis.
    """
    paths = []
    # ⚠ NOT JUST .env. An adversarial session found three GCP service-account keys
    # (live 1704-char RSA private keys), the Google Drive OAuth refresh token and
    # client secret, and the self-hosted Actions runner's RSA credentials — none of
    # which match an ".env" shape. Match by name pattern AND by content signature.
    patterns = [".env*", "*.env", "*service-account*.json", "client_secret*.json",
                ".gcp-*.json", ".gdrive-*.json", ".credentials", ".credentials_rsaparams",
                ".git-credentials", "*.pem", "*.key"]
    try:
        expr = []
        for i, pat in enumerate(patterns):
            if i:
                expr.append("-o")
            expr += ["-name", pat]
        r = subprocess.run(["find", str(FIELDS_ROOT), "-maxdepth", "5", "-type", "f",
                            "("] + expr + [")"],
                           capture_output=True, text=True, timeout=120)
        paths += [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    except Exception as exc:
        logger.warning("credential sweep failed: %s", exc)
    for extra in ("/home/projects/.config/gh/hosts.yml",
                  "/home/projects/.git-credentials",
                  str(Path.home() / ".git-credentials")):
        if Path(extra).is_file():
            paths.append(extra)
    return sorted(set(p for p in paths if Path(p).is_file()))


def _sandbox_wrap(inner_cmd: str, scope: str) -> list[str]:
    """Wrap the session in a user+mount namespace that hides the credentials.

    `unshare -rm` gives an unprivileged user namespace (root-mapped inside, no
    real privilege outside) plus a private mount namespace, so the binds below
    are visible ONLY to this session and cannot affect the host or another task.

    - /dev/null over .env  : the session cannot read the credential file at all.
                             config/settings.yaml is deliberately left alone so
                             Cosmos access still works.
    - /home/fields ro      : investigate scope only. Bash is granted, so without
                             this "read-only" was a request, not a property, on a
                             working tree with ~1,000 dirty files.
    """
    parts = []
    if scope == "investigate":
        parts += [
            f"mount --bind {FIELDS_ROOT} {FIELDS_ROOT}",
            f"mount -o remount,bind,ro {FIELDS_ROOT}",
        ]

    # ⚠ CREDENTIAL BINDS COME AFTER THE TREE BIND. They used to come first, and a
    # plain (non-recursive) bind of the whole tree afterwards SHADOWED them — the
    # nested /dev/null mounts still existed (findmnt showed them) while stat/cat
    # read straight through to the real files. Topmost mount wins.
    creds = _credential_paths()
    parts += [f"mount --bind /dev/null {shlex.quote(p)}" for p in creds]

    # ⚠ FAIL CLOSED, AND CHECK THE WHOLE SET. Four versions of this control were
    # asserted correct; four were defeated. The session does not start until the
    # boundary is OBSERVED to hold. Exit 91 is distinct from any claude exit code.
    checks = " ".join(f"-s {shlex.quote(p)} -o" for p in creds).rstrip(" -o")
    if checks:
        parts.append(
            f'if [ {checks} ]; then echo "SANDBOX SELF-CHECK FAILED: a credential '
            f'file is still readable — refusing to start" >&2; exit 91; fi'
        )

    # ⚠ DROP CAP_SYS_ADMIN BEFORE HANDING OVER. Inside `unshare -r` the session is
    # uid 0 and therefore able to `umount` the binds above — an adversarial session
    # did exactly that (exit 0) and read the real 8,132-byte .env underneath.
    # Removing sys_admin from the bounding set makes umount/remount impossible for
    # the session and everything it spawns, while leaving the mounts in place.
    parts.append(f"exec setpriv --bounding-set=-sys_admin bash -c {shlex.quote(inner_cmd)}")

    # `-p --mount-proc` gives a private PID namespace with a fresh /proc, closing
    # the /proc/<ppid>/environ route: an adversarial session read the WORKER's own
    # environment that way and recovered POSTHOG_ALL_ACCESS_KEY and GOOGLE_VISION_SA_KEY.
    return ["unshare", "-rmpf", "--mount-proc", "bash", "-c", " && ".join(parts)]


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
            "  - COMMIT your work. An uncommitted worktree reads as 'changed nothing'\n"
            "    to the checks downstream, and your task will be recorded as a failure.\n"
            "  - You CANNOT push and must not try: this session has no GitHub credentials.\n"
            "  - Do NOT edit the live tree at /home/fields/Fields_Orchestrator.\n"
        )
    else:
        scope_rules = (
            "SCOPE: investigate. Diagnosis only.\n"
            "  - You have no Write or Edit tool, AND /home/fields is mounted READ-ONLY\n"
            "    for this session. Attempts to write there will fail; that is not a bug\n"
            "    to work around. /tmp is writable if you need scratch space.\n"
            "  - If the fix is obvious, include a unified diff in your result. Do not apply it.\n"
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
  - MongoDB: `from shared.db import get_client` — this WORKS, via config/settings.yaml.
  - ⚠ You have NO credentials beyond the database, by design. .env is not readable
    from this session (do not try to source it, cat it, or reconstruct it), and
    there are no GitHub, Netlify, Facebook, Google Ads or OpenAI tokens in your
    environment. If your task appears to need one, it has exceeded its scope:
    say so in `blocked` and stop. Do not look for another way in.
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
    # ⚠ Branch name carries the ATTEMPT. It used to be `spawn/<task_id>` flat, and
    # because the worktree was never cleaned (see _worktree_diffstat below), every
    # retry died on "a branch named 'spawn/<id>' already exists" — recorded as
    # "worktree setup failed", which blamed the wrong thing entirely.
    attempt = int(task.get("attempts") or 1)
    wt = WORKTREE_ROOT / f"{task_id}_a{attempt}"
    branch = f"spawn/{task_id}/a{attempt}"
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=str(REPO_ROOT),
                       capture_output=True, timeout=60)
    subprocess.run(
        ["git", "worktree", "add", "-B", branch, str(wt), "HEAD"],
        cwd=str(REPO_ROOT), check=True, capture_output=True, text=True, timeout=120,
    )
    return wt


def _base_sha(wt: Path) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(wt),
                       capture_output=True, text=True, timeout=60)
    return (r.stdout or "").strip()


def _worktree_diffstat(wt: Path, base_sha: str) -> str:
    """What the SESSION changed, measured against where the worktree started.

    ⚠ This used to diff `HEAD~1..HEAD`, which on a fresh worktree is the repo's
    last PRE-EXISTING commit — always non-empty. Two silent consequences: the
    Rule 7b guard ("resolved but changed nothing") could never fire, and the
    keep/cleanup decision below was always "keep", so every worktree and branch
    leaked forever with nothing to garbage-collect them.
    """
    if not base_sha:
        return ""
    try:
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=str(wt),
                               capture_output=True, text=True, timeout=60)
        committed = subprocess.run(["git", "diff", "--stat", f"{base_sha}..HEAD"], cwd=str(wt),
                                   capture_output=True, text=True, timeout=60)
        return ((dirty.stdout or "") + (committed.stdout or "")).strip()
    except Exception:
        return ""


def _cleanup_worktree(wt: Path, keep: bool):
    """Keep a worktree that holds a real diff — it is the deliverable. Remove empty ones.

    Failures are logged rather than swallowed: `subprocess.run` without check=True
    never raises, so the previous `except Exception` here was unreachable and a
    failed removal disappeared entirely.
    """
    if keep:
        logger.info("Keeping worktree %s (holds a diff)", wt)
        return
    for cmd in (["git", "worktree", "remove", "--force", str(wt)],
                ["git", "worktree", "prune"]):
        r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                           text=True, timeout=120)
        if r.returncode != 0:
            logger.warning("cleanup %s failed: %s", " ".join(cmd),
                           (r.stderr or "").strip()[:200])


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
    global _quota_paused_until
    task_id = str(task["_id"])
    queue = client["system_monitor"][COLLECTION]
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)

    # The session writes here (outside /home/fields, which investigate mounts
    # read-only); the worker copies it into artifacts/ afterwards for keeping.
    session_dir = SESSION_RESULT_ROOT / task_id
    session_dir.mkdir(parents=True, exist_ok=True)
    result_file = session_dir / "result.json"
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

    base_sha = _base_sha(wt) if task["scope"] == "patch" else ""
    prompt = _build_prompt(task, result_file, wt)
    timeout_s = int(task.get("timeout_s") or 2700)

    # ⚠ NO MCP. Connected MCP servers (posthog exec, google-drive read/write) are
    # injected into a session as callable tools and grant PRODUCTION access with no
    # filesystem credential at all — an adversarial session confirmed both were
    # available to it. --strict-mcp-config with an empty config loads none.
    empty_mcp = SESSION_RESULT_ROOT / "no-mcp.json"
    empty_mcp.parent.mkdir(parents=True, exist_ok=True)
    empty_mcp.write_text('{"mcpServers": {}}')

    inner = " ".join([
        "exec", "claude", "--model", CLAUDE_MODEL,
        "--mcp-config", str(empty_mcp), "--strict-mcp-config",
        "--allowedTools", shlex.quote(TOOLS[task["scope"]]),
        "--max-turns", str(int(task.get("max_turns") or 60)),
        "-p", shlex.quote(prompt),
    ])
    cmd = _sandbox_wrap(inner, task["scope"])

    rc, tail = -1, ""
    try:
        with open(log_file, "w") as lf:
            proc = subprocess.run(cmd, cwd=str(wt), env=_child_env(wt),
                                  stdout=lf, stderr=subprocess.STDOUT,
                                  timeout=timeout_s)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        rc = -9
        logger.error("%s timed out after %ss", task_id, timeout_s)
    except Exception as exc:
        logger.error("%s failed to launch: %s", task_id, exc)

    if log_file.exists():
        tail = log_file.read_text(errors="replace")[-3000:]

    # Exit 91 = the sandbox self-check refused to start the session. That is an
    # infrastructure fault, never the task's fault: requeue it and stop claiming,
    # rather than burning attempts on a broken boundary.
    if rc == 91:
        _quota_paused_until = time.time() + QUOTA_BACKOFF_SECONDS
        queue.update_one({"_id": task["_id"]}, {"$set": {
            "status": "pending", "started_at": None,
            "error": "sandbox self-check failed — credential boundary not in place"},
            "$inc": {"attempts": -1}})
        logger.critical("%s: SANDBOX SELF-CHECK FAILED — pausing worker. %s",
                        task_id, tail[-400:])
        if task["scope"] == "patch":
            _cleanup_worktree(wt, keep=False)
        return False

    # ⚠ Quota exhaustion is an UPSTREAM outage, not a bad task. Without this the
    # loop claims the next two tasks, they fail in seconds, and the entire pending
    # queue drains to `failed` inside two poll cycles — each with an error that
    # reads like a bad brief, and none of them retried. Requeue and back off.
    if rc != 0 and any(m in tail.lower() for m in QUOTA_MARKERS):
        _quota_paused_until = time.time() + QUOTA_BACKOFF_SECONDS
        queue.update_one({"_id": task["_id"]}, {"$set": {
            "status": "pending", "started_at": None,
            "error": "Max quota exhausted — requeued, worker backing off"},
            "$inc": {"attempts": -1}})
        logger.error("%s: Max quota exhausted — requeued, pausing %ss",
                     task_id, QUOTA_BACKOFF_SECONDS)
        _cleanup_worktree(wt, keep=False) if task["scope"] == "patch" else None
        return False

    result = None
    if result_file.exists():
        try:
            parsed = json.loads(result_file.read_text())
            # Any valid JSON used to be accepted. A list or string then reached
            # result.get() below, raised AttributeError outside the try, and left
            # the task stranded in `running` until the stale sweep.
            result = parsed if isinstance(parsed, dict) else None
            if result is None:
                logger.warning("%s wrote non-object JSON (%s)", task_id, type(parsed).__name__)
        except json.JSONDecodeError as exc:
            logger.warning("%s wrote unparseable result: %s", task_id, exc)

    diffstat = _worktree_diffstat(wt, base_sha) if task["scope"] == "patch" else ""

    # The result file is the contract, and it must ASSERT AN OUTCOME (Rule 7b).
    # `blocked` and unrecognised values are NOT successes: the prompt tells the
    # session to write the file even when blocked, so accepting any value here
    # recorded "I achieved nothing" as ✅ with a success heartbeat.
    outcome = (result or {}).get("outcome")
    ok = bool(result) and rc == 0 and outcome in VALID_OUTCOMES \
        and bool(str((result or {}).get("summary") or "").strip())

    if ok and task["scope"] == "patch" and outcome == "resolved" and not diffstat:
        # "resolved" with an empty worktree means it believes it fixed something
        # it never touched.
        ok = False
        result["outcome"] = "diagnosed"
        result.setdefault("open_questions", []).append(
            "Reported 'resolved' but the worktree is empty — no change was actually made."
        )

    # Persist the session's result next to its log, so artifacts/ remains the
    # one place to look even though the session wrote to /tmp.
    if result is not None:
        (RESULT_ROOT / f"{task_id}.json").write_text(json.dumps(result, indent=2))
    shutil.rmtree(session_dir, ignore_errors=True)

    update = {
        "status": "completed" if ok else "failed",
        "finished_at": datetime.now(timezone.utc),
        "result": result,
        "exit_code": rc,
        "output_tail": tail[-3000:],
        "diffstat": diffstat or None,
        "worktree": str(wt) if (task["scope"] == "patch" and diffstat) else None,
        "log_file": str(log_file),
    }
    if not ok:
        if not result:
            update["error"] = f"exit={rc}, no usable result file written"
        elif outcome not in VALID_OUTCOMES:
            update["error"] = f"exit={rc}, outcome={outcome!r} is not a completed outcome"
        else:
            update["error"] = f"exit={rc}"

        # ⚠ Retry TRANSIENT failures. MAX_ATTEMPTS used to govern only the
        # crash-reclaim path, because every failure here wrote status="failed"
        # and claim_pending only ever selects "pending" — so a CLI blip or a
        # Cosmos timeout was terminal on the first try while the constant implied
        # otherwise. A session that ran and reported a bad outcome is NOT
        # transient: re-running it would just burn another 45 minutes.
        transient = (result is None) and rc != 0
        if transient and int(task.get("attempts") or 1) < MAX_ATTEMPTS:
            update["status"] = "pending"
            update["started_at"] = None
            update["finished_at"] = None
            logger.warning("%s failed transiently (exit=%s) — requeued", task_id, rc)
    queue.update_one({"_id": task["_id"]}, {"$set": update})

    if task["scope"] == "patch":
        _cleanup_worktree(wt, keep=bool(diffstat))
    _notify({**task, "error": update.get("error")}, result, ok)
    logger.info("%s -> %s (%s)", task_id, update["status"], outcome or "no result")
    return ok


def claim_pending(client, n: int) -> list[dict]:
    """Claim up to n pending tasks, oldest first."""
    queue = client["system_monitor"][COLLECTION]

    # Reclaim anything a crash or restart left mid-flight, otherwise a task
    # strands in "running" forever and silently never gets done.
    #
    # ⚠ The cutoff is PER TASK — its own timeout plus a margin. A global constant
    # reclaims any task granted a longer timeout while a worker thread still holds
    # it, and the reclaim then rmtree's the worktree that live session is editing.
    now_ts = datetime.now(timezone.utc).timestamp()
    for stuck in queue.find({"status": "running"}):
        started = _as_utc(stuck.get("started_at"))
        budget = int(stuck.get("timeout_s") or 2700) + STALE_MARGIN_SECONDS
        if started and started.timestamp() < (now_ts - budget):
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


def _in_quiet_window() -> bool:
    """True during the nightly pipeline window (AEST), when we must not claim."""
    now = datetime.now(timezone.utc).astimezone(AEST)
    sh, sm, eh, em = QUIET_WINDOW_AEST
    start, end = sh * 60 + sm, eh * 60 + em
    cur = now.hour * 60 + now.minute
    return cur >= start or cur < end        # window wraps midnight


def _should_claim() -> tuple[bool, str]:
    """Gate on quota backoff, the nightly window and machine load."""
    if time.time() < _quota_paused_until:
        return False, f"quota backoff for {int(_quota_paused_until - time.time())}s"
    if _in_quiet_window():
        return False, "nightly pipeline window (20:15-02:00 AEST)"
    load = os.getloadavg()[0]
    if load > LOAD_CEILING:
        return False, f"load {load:.1f} > ceiling {LOAD_CEILING}"
    return True, ""


def _ensure_indexes(client):
    """The stale sweep scans by status every 30s and claims sorted by created_at."""
    try:
        client["system_monitor"][COLLECTION].create_index(
            [("status", 1), ("created_at", 1)], name="status_created")
    except Exception as exc:
        logger.warning("index creation skipped: %s", exc)


def _prune_artifacts(days: int = 30):
    """Age out per-task logs/results so artifacts/ cannot grow without bound."""
    cutoff = time.time() - days * 86400
    for p in RESULT_ROOT.glob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
        except Exception:
            pass


def _heartbeat(client):
    """Daemon liveness + a queue-health assertion, ONE doc, every cycle.

    ⚠ Do NOT move this back to per-task heartbeats under a fixed job name.
    job_status writes one document per job name (replace_one upsert), so with
    concurrency 2 a task failing at 11:50:00 and one succeeding at 11:50:04
    left the board reading `success` with the failure's traceback overwritten —
    the exact silent failure Rule 7 exists to prevent. The per-task record lives
    in spawned_tasks; this heartbeat is about the WORKER.

    It also beats every cycle, not only when a task is claimed: the old version
    heartbeated on claim alone, so a worker that died with an empty queue read
    OK for 252 hours.
    """
    queue = client["system_monitor"][COLLECTION]
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    pending = queue.count_documents({"status": "pending"})
    running = queue.count_documents({"status": "running"})
    done = queue.count_documents({"status": "completed", "finished_at": {"$gte": since}})
    failed = queue.count_documents({"status": "failed", "finished_at": {"$gte": since}})

    with job_run("spawn_worker", cadence_hours=1, stale_hours=3,
                 title="Spawned Task Worker (handoff sessions)") as beat:
        beat.metrics = {"pending": pending, "running": running,
                        "completed_24h": done, "failed_24h": failed}
        # Rule 7b — a worker that turned every task into a failure is broken
        # upstream (quota, missing CLI), not merely busy. Same class as
        # [INDEXING-SILENT-ZERO]: an outage consumed as per-item failure.
        if failed and not done:
            raise RuntimeError(
                f"{failed} spawned task(s) failed and none succeeded in 24h — "
                f"check quota and {RESULT_ROOT}")
        beat.detail = f"{pending} pending, {running} running, {done} ok / {failed} failed (24h)"


def main():
    logger.info("Spawn worker starting (poll %ss, concurrency %s)",
                POLL_INTERVAL, MAX_CONCURRENCY)
    client = get_client()
    _ensure_indexes(client)
    pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
    inflight: list = []
    last_beat, last_prune, last_gate_log = 0.0, 0.0, ""

    while True:
        try:
            inflight = [f for f in inflight if not f.done()]
            slots = MAX_CONCURRENCY - len(inflight)
            may_claim, why = _should_claim()
            if why and why != last_gate_log:
                logger.info("Not claiming: %s", why)
            last_gate_log = why

            if slots > 0 and may_claim:
                for task in claim_pending(client, slots):
                    # Each task gets its own Mongo client: pymongo is thread-safe
                    # but a long session holding one connection across a 45-minute
                    # run invites a Cosmos idle disconnect on the write-back.
                    inflight.append(pool.submit(_run_isolated, task))

            if time.time() - last_beat > 1800:
                _heartbeat(client)
                last_beat = time.time()
            if time.time() - last_prune > 86400:
                _prune_artifacts()
                last_prune = time.time()
        except Exception as exc:
            logger.error("Poll cycle failed: %s", exc)
        time.sleep(POLL_INTERVAL)


def _run_isolated(task: dict):
    """Run one task on its own connection. The per-task record is the queue doc;
    worker health is reported separately by _heartbeat()."""
    task_id = str(task["_id"])
    client = get_client()
    try:
        run_task(client, task)
    except Exception as exc:
        logger.error("Task %s crashed: %s", task_id, exc, exc_info=True)
        try:
            client["system_monitor"][COLLECTION].update_one(
                {"_id": task["_id"]},
                {"$set": {"status": "failed", "error": f"worker crash: {exc}"[:400],
                          "finished_at": datetime.now(timezone.utc)}})
        except Exception:
            logger.error("Could not record crash for %s", task_id)
    finally:
        client.close()


if __name__ == "__main__":
    main()
