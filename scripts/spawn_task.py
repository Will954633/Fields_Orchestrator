#!/usr/bin/env python3
"""
spawn_task.py — hand a self-contained unit of work to a SEPARATE Claude session.

Enqueues one task onto system_monitor.spawned_tasks. scripts/spawn_worker.py
claims it and runs it as a headless `claude -p` session on the Claude Max
subscription, then writes the result back onto the same document.

    python3 scripts/spawn_task.py \
      --title "115 of 1,493 /property sitemap URLs render Property Not Found" \
      --scope investigate \
      --detection-file /tmp/brief.md \
      --repro "python3 scripts/sitemap_robots_invariant.py" \
      --known-files "01_Website/src/pages/PropertyPage/PropertyPage.tsx,01_Website/netlify/functions/property.mjs" \
      --success "Names the DB condition that distinguishes the 115 failing ids from the 1,378 working ones, with a query that reproduces the split."

WHY THIS EXISTS
    Work identified mid-session — "two live defects I found but haven't touched"
    — used to die with the session. Tier 1 parallelism (background agents inside
    one session) covers work that can finish before the session ends. This is
    Tier 2: work that should outlive it, run on fresh context, and report to Will
    rather than only back into a transcript nobody re-reads.

⚠ WHY NOT `trigger_requests`: that queue is strictly serial (one job per 30s
cycle), shared with the nightly scrape, and keyed to fixed process ids in
config/process_commands.yaml. It cannot carry a free-form brief. Same reasoning
that gave offmarket_report_requests its own queue.

⚠ THE BRIEF IS THE WHOLE GAME. A spawned session has ZERO context — none of the
conversation that found the problem. "115 sitemap URLs 404" is not a task: it is
missing how it was measured, which files are implicated, and what "done" means.
So the required fields below are enforced, not advisory, and thin briefs are
REJECTED rather than queued. If you cannot write the five fields, the task is not
ready to hand off — say so instead of lobbing a vague brief at a fresh session.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

# Load our own environment rather than trusting the caller (CLAUDE.md Rule 7.3).
load_dotenv(REPO_ROOT / ".env")

from pymongo import MongoClient  # noqa: E402

COLLECTION = "spawned_tasks"

# Scope classes, in ascending order of blast radius. `deploy` is deliberately
# absent: nothing that publishes to the live site, changes ad campaigns, or
# pushes code runs unattended. A spawned session's job is to arrive at a
# verified answer and a reviewable patch — Will ships it.
SCOPES = ("investigate", "patch")

# Text that means "I have not actually thought about this yet". Queuing one of
# these produces a session that burns an hour rediscovering what the caller
# already knew, so they fail the submission instead.
_PLACEHOLDER = re.compile(
    r"^\s*(tbd|tba|todo|fixme|n/?a|none|unknown|\?+|"
    r"(fix|investigate|look at|check|sort out|figure out)\s+(it|this|that)\s*\.?)\s*$",
    re.IGNORECASE,
)

_MINIMUMS = {
    "detection": 80,   # how it was found + the evidence: the single most-skipped field
    "repro": 10,
    "success_criteria": 40,
    "title": 10,
}


# Roots a path in a brief may be relative to. The website tree is a separate
# checkout, so "01_Website/src/..." resolves under Feilds_Website, not this repo.
_PATH_ROOTS = (
    REPO_ROOT,
    Path("/home/fields/Feilds_Website"),
    Path("/home/fields/Feilds_Website/01_Website"),
    Path("/home/fields"),
)

_CODE_EXT = (".py", ".sh", ".mjs", ".js", ".ts", ".tsx", ".jsx", ".json",
             ".yaml", ".yml", ".md", ".sql", ".css", ".html")


class ThinBrief(ValueError):
    """Raised when a brief is too thin to hand to a session with no context."""


class FictionalBrief(ValueError):
    """Raised when a brief cites a file or command that does not exist."""


def _resolves(token: str) -> bool:
    """Does this token name something that actually exists on disk?"""
    p = Path(token)
    if p.is_absolute():
        return p.exists()
    return any((root / token).exists() for root in _PATH_ROOTS)


def _looks_like_path(token: str) -> bool:
    return ("/" in token or token.endswith(_CODE_EXT)) and not token.startswith("-")


def _check_repro(repro: str) -> list[str]:
    """Verify the repro command's binary and file arguments exist.

    ⚠ THIS IS THE FIX FOR THE ONE FAILURE THE SHAPE GATE COULD NOT SEE. The first
    example brief ever written for this tool cited
    `python3 scripts/check_sitemap_urls.py` — a script that does not exist. Every
    length and placeholder check passed it, and a spawned session would have burnt
    45 minutes chasing a command that was never real. Shape validation cannot
    catch fiction; existence checks can.

    Deliberately static — we do NOT execute the repro. Running an arbitrary
    command at enqueue time would be a worse problem than the one it solves.
    """
    problems = []
    try:
        tokens = shlex.split(repro)
    except ValueError:
        # Unbalanced quotes etc. — not fatal on its own; the session gets the raw
        # string and can cope. Skip the check rather than reject a valid brief.
        return problems

    # shlex keeps shell separators glued to the word (`foo.py;`, `x.py&&`), which
    # made a perfectly valid multi-command repro fail the existence check on a
    # path that does exist. Strip the operators before testing.
    tokens = [t.strip(";&|()<>") for t in tokens]
    tokens = [t for t in tokens if t]

    if tokens:
        binary = tokens[0]
        if not _looks_like_path(binary) and not shutil.which(binary):
            problems.append(f"repro command `{binary}` is not on PATH")

    for tok in tokens[1:]:
        if _looks_like_path(tok) and not _resolves(tok):
            problems.append(f"repro references `{tok}`, which does not exist")
    return problems


def _check_known_files(files: list[str]) -> list[str]:
    """Verify each cited path exists. Entries containing spaces are treated as
    search commands/hints rather than paths and are left alone."""
    problems = []
    for f in files:
        if " " in f or "*" in f:      # a search hint or glob, not a literal path
            continue
        if not _resolves(f):
            problems.append(f"known-files references `{f}`, which does not exist")
    return problems


def _validate(field: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ThinBrief(f"--{field.replace('_', '-')} is required and was empty")
    if _PLACEHOLDER.match(value):
        raise ThinBrief(
            f"--{field.replace('_', '-')} is a placeholder ({value!r}). "
            f"A spawned session has none of your context; it cannot expand this."
        )
    floor = _MINIMUMS.get(field)
    if floor and len(value) < floor:
        raise ThinBrief(
            f"--{field.replace('_', '-')} is {len(value)} chars, needs >= {floor}. "
            f"Write what you actually know — the receiving session starts from nothing."
        )
    return value


def build_task(*, title, scope, detection, repro, known_files, success_criteria,
               repo, constraints, spawned_by, max_turns, timeout_s,
               skip_path_check=False) -> dict:
    # ⚠ Clamp. The worker reclaims a task once its timeout + margin elapses; an
    # unbounded value let the sweep reclaim a task a live thread still held,
    # rmtree the worktree it was editing, and delete its result file mid-run.
    timeout_s = max(300, min(int(timeout_s), 5400))

    if scope not in SCOPES:
        raise ThinBrief(f"--scope must be one of {SCOPES} (deploy is never autonomous)")

    title = _validate("title", title)
    detection = _validate("detection", detection)
    repro = _validate("repro", repro)
    success_criteria = _validate("success_criteria", success_criteria)

    files = [f.strip() for f in (known_files or "").split(",") if f.strip()]
    if not files:
        raise ThinBrief(
            "--known-files is required: at least one path, directory, or search "
            "command that gets the session to the right part of the tree. "
            "'I don't know where it lives' is itself the finding — say that in "
            "--detection and point at where you looked."
        )

    if not skip_path_check:
        problems = _check_repro(repro) + _check_known_files(files)
        if problems:
            raise FictionalBrief(
                "\n  ".join(problems)
                + "\n\n  A brief that cites something non-existent sends a session with no "
                  "context chasing your own fiction. Fix the paths, or pass "
                  "--skip-path-check if the target is genuinely created at run time."
            )

    # ⚠ /home/fields/Feilds_Website is NOT a git repo on this VM, so a website
    # task cannot be worktree-isolated. It runs read-only and returns a diff for
    # review; the worker enforces this rather than trusting the flag.
    if repo == "website" and scope == "patch":
        raise ThinBrief(
            "scope=patch is unavailable for repo=website: /home/fields/Feilds_Website "
            "is not a git repository, so there is no worktree to isolate edits in. "
            "Use --scope investigate; the session will produce a reviewable diff."
        )

    return {
        "title": title,
        "scope": scope,
        "repo": repo,
        "brief": {
            "detection": detection,
            "repro": repro,
            "known_files": files,
            "success_criteria": success_criteria,
            "constraints": (constraints or "").strip(),
        },
        "status": "pending",
        "spawned_by": spawned_by,
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "finished_at": None,
        "attempts": 0,
        "max_turns": max_turns,
        "timeout_s": timeout_s,
        "result": None,
        "error": None,
    }


def enqueue(task: dict) -> str:
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        raise RuntimeError("COSMOS_CONNECTION_STRING not set — cannot enqueue")
    client = MongoClient(uri, retryWrites=False, serverSelectionTimeoutMS=30000)
    try:
        res = client["system_monitor"][COLLECTION].insert_one(task)
        return str(res.inserted_id)
    finally:
        client.close()


def main():
    p = argparse.ArgumentParser(
        description="Hand a self-contained task to a separate headless Claude session.",
        epilog="Every field is required because the receiving session has zero context.",
    )
    p.add_argument("--title", required=True,
                   help="One line naming the problem, specific enough to recognise later.")
    p.add_argument("--scope", default="investigate", choices=SCOPES,
                   help="investigate = read-only diagnosis (default). "
                        "patch = may edit, inside a git worktree, and can never push.")
    p.add_argument("--repo", default="orchestrator", choices=("orchestrator", "website", "none"))
    p.add_argument("--detection",
                   help="How you found it and the evidence. Use --detection-file for long text.")
    p.add_argument("--detection-file", type=Path,
                   help="Read --detection from a file (preferred for anything substantial).")
    p.add_argument("--repro", required=True,
                   help="The exact command or query that reproduces it. Not a description of one.")
    p.add_argument("--known-files", required=True,
                   help="Comma-separated paths/dirs/search commands already known to be involved.")
    p.add_argument("--success", required=True, dest="success_criteria",
                   help="Falsifiable definition of done. 'Fixed' is not one.")
    p.add_argument("--constraints", default="",
                   help="Anything that would make an otherwise-correct answer wrong.")
    p.add_argument("--spawned-by", default=os.environ.get("SPAWN_PARENT", "claude-session"))
    p.add_argument("--max-turns", type=int, default=60)
    p.add_argument("--timeout-s", type=int, default=2700,
                   help="Wall clock for the spawned session (default 45 min, max 90).")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate the brief and print it without enqueuing.")
    p.add_argument("--skip-path-check", action="store_true",
                   help="Bypass the existence check on --repro and --known-files. "
                        "Only for targets created at run time — it exists to be "
                        "the exception, not the habit.")
    args = p.parse_args()

    detection = args.detection
    if args.detection_file:
        if not args.detection_file.exists():
            print(f"error: --detection-file not found: {args.detection_file}", file=sys.stderr)
            return 2
        detection = args.detection_file.read_text()

    try:
        task = build_task(
            title=args.title, scope=args.scope, detection=detection, repro=args.repro,
            known_files=args.known_files, success_criteria=args.success_criteria,
            repo=args.repo, constraints=args.constraints, spawned_by=args.spawned_by,
            max_turns=args.max_turns, timeout_s=args.timeout_s,
            skip_path_check=args.skip_path_check,
        )
    except ThinBrief as e:
        print(f"REJECTED — brief too thin to hand off:\n  {e}", file=sys.stderr)
        return 2
    except FictionalBrief as e:
        print(f"REJECTED — brief cites something that does not exist:\n  {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        import json
        print(json.dumps(task, indent=2, default=str))
        return 0

    task_id = enqueue(task)
    print(f"queued {task_id}  [{task['scope']}/{task['repo']}]  {task['title']}")
    print(f"  status: python3 scripts/spawn_status.py {task_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
