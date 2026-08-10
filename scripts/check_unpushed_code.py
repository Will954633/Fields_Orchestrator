#!/usr/bin/env python3
"""Flag code files whose LOCAL content != the GitHub remote — the DR gap the
gh-api-only workflow hides.

Why this exists: pushes go out via `gh api contents PUT`, which commits straight
to GitHub and never touches local git; `git push` hangs on this VM so nobody
pulls/commits locally either. Local git therefore drifts and `git status` becomes
noise (byte-identical files show as "modified", new files hide in untracked). The
only trustworthy signal is content-hash vs the remote blob — which is what this
does. See fix-history [GIT-DR-GAP] 2026-07-15.

Usage:
  python3 scripts/check_unpushed_code.py            # report gaps (exit 1 if any)
  python3 scripts/check_unpushed_code.py --push      # push the real gaps (1 commit/repo)
  python3 scripts/check_unpushed_code.py --quiet      # only print if gaps exist (for cron)

Excludes scratch/experiment/e2e dirs from --push (still reported). Secret-scans
every file before pushing and refuses any that looks like it embeds a credential.
"""
import base64, json, os, re, subprocess, sys

REPOS = [
    {"path": "/home/fields/Fields_Orchestrator",   "remote": "Will954633/Fields_Orchestrator"},
    {"path": "/home/fields/Property_Data_Scraping", "remote": "Will954633/Property_Data_Scraping"},
]
CODE_EXT = (".py", ".mjs", ".js", ".sh", ".yaml", ".yml")
# One-off, per-cycle FB ad builders (Home Owner Lead Funnel): each ran once to push a
# specific batch of ads to Meta and is never re-run — the durable record lives in that
# folder's 00_MASTER_LEDGER.md / 03_MONITORING.md and on Meta itself, so they are
# intentionally not backed up. The reusable core of that funnel (build_campaign,
# build_copy_lab, checkpoint, create_lead_forms) is NOT scratch and is pushed.
SCRATCH_RE = re.compile(
    r"11_House_Mini_Site/|13_Will-Learns-to-Code/|08_Seller-Book/|v2-e2e|v3-[a-z]|-e2e-test|-e2e-wave"
    r"|Home_Owner_Lead_Funnel_Search/(build_cycle|build_market_test|build_morning_batch|create_test_forms|render_launch_cards|render_test_cards)"
)
SECRET_RE = re.compile(
    r"mongodb(\+srv)?://[^ '\"]*:[^ '\"]*@|AccountKey=|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|ghp_[A-Za-z0-9]{20,}|xox[baprs]-|(secret|password|passwd|token|api_key|apikey)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"
)
SECRET_ALLOW = re.compile(r"os\.environ|getenv|process\.env|load_dotenv|placeholder|your_|xxxx|example", re.I)

PUSH = "--push" in sys.argv
QUIET = "--quiet" in sys.argv
NOTIFY = "--notify" in sys.argv        # Telegram-alert on real (non-scratch) gaps — for cron

ENV = dict(os.environ)
ENV.pop("GITHUB_TOKEN", None)                      # invalid token overrides gh auth
ENV.setdefault("GH_CONFIG_DIR", "/home/projects/.config/gh")


def git(repo, *args, check=True, timeout=120):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, env=ENV, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.decode().strip()}")
    return p.stdout.decode()


def gh(repo_remote_args, body=None):
    p = subprocess.run(["gh", "api", *repo_remote_args],
                       input=(json.dumps(body).encode() if body is not None else None),
                       capture_output=True, env=ENV)
    if p.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(repo_remote_args)}: {p.stderr.decode().strip()}")
    return p.stdout.decode()


def code_files(repo):
    # non-ignored files (tracked-per-index + untracked), robust to a stale index
    out = git(repo, "ls-files", "-co", "--exclude-standard")
    seen = set()
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel or rel in seen:
            continue
        seen.add(rel)
        if rel.endswith(CODE_EXT) and os.path.isfile(os.path.join(repo, rel)):
            yield rel


def remote_blob(repo, rel):
    """SHA of the file's blob on origin/main, or None if it's not there.
    `git rev-parse origin/main:PATH` prints the literal path (not a sha) and
    exits nonzero when the path is absent — use --verify --quiet for a clean
    None so new files aren't misread as modified."""
    p = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"origin/main:{rel}"],
                       capture_output=True, env=ENV)
    sha = p.stdout.decode().strip()
    return sha or None


def is_external_link(repo, rel):
    """True if `rel` is a symlink resolving OUTSIDE this repo.

    `git hash-object` FOLLOWS symlinks, so a link into another repo hashes as that
    repo's file content and reads here as an un-backed-up gap. It is not one: the
    file is version-controlled where it actually lives. Pushing it would (a) commit a
    duplicate copy of live website source into the orchestrator repo, and (b) flip
    straight back to MOD the next time the real file is edited — a nag that can never
    be cleared by acting on it. 10 of the 27 files in the 2026-08-10 alert were
    Break_glass_emergency/workbench/*.js links into
    Feilds_Website/01_Website/src/components/BreakGlass/, already backed up in
    Website_Version_Feb_2026.
    """
    p = os.path.join(repo, rel)
    if not os.path.islink(p):
        return False
    return not os.path.realpath(p).startswith(os.path.realpath(repo) + os.sep)


def classify(repo):
    """Return (new_only_on_vm, modified, linked) — real gaps only, by content hash."""
    new, mod, linked = [], [], []
    for rel in code_files(repo):
        if is_external_link(repo, rel):
            linked.append(rel)
            continue
        local = git(repo, "hash-object", rel).strip()
        remote = remote_blob(repo, rel)
        if remote is None:
            new.append(rel)
        elif local != remote:
            mod.append(rel)
    return sorted(new), sorted(mod), sorted(linked)


def secret_hits(repo, rel):
    # This file DEFINES the patterns, so scanning it matches itself — SECRET_RE contains
    # the literal "AccountKey=", which made check_unpushed_code.py block its own backup
    # and raise a "possible secret" alert about a regex. A detector must not be its own
    # first false positive.
    if os.path.abspath(os.path.join(repo, rel)) == os.path.abspath(__file__):
        return []
    hits = []
    with open(os.path.join(repo, rel), errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if SECRET_RE.search(line) and not SECRET_ALLOW.search(line):
                hits.append((i, line.strip()[:120]))
    return hits


def push_repo(repo, remote, files, message):
    base = json.loads(gh([f"repos/{remote}/git/ref/heads/main"]))["object"]["sha"]
    base_tree = json.loads(gh([f"repos/{remote}/git/commits/{base}"]))["tree"]["sha"]
    tree = []
    for rel in files:
        with open(os.path.join(repo, rel), "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        blob = json.loads(gh([f"repos/{remote}/git/blobs", "--input", "-"],
                             {"content": b64, "encoding": "base64"}))["sha"]
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob})
    tree_sha = json.loads(gh([f"repos/{remote}/git/trees", "--input", "-"],
                             {"base_tree": base_tree, "tree": tree}))["sha"]
    commit = json.loads(gh([f"repos/{remote}/git/commits", "--input", "-"],
                           {"message": message, "tree": tree_sha, "parents": [base]}))["sha"]
    gh([f"repos/{remote}/git/refs/heads/main", "-X", "PATCH", "--input", "-"], {"sha": commit})
    # reconcile local so status stays truthful
    git(repo, "fetch", "origin", "main", timeout=120)
    git(repo, "reset", "--mixed", "origin/main", check=False)
    return commit


def telegram(text, queue_as=None):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        if queue_as:
            from telegram_notify import queue_message
            queue_message(text, source=queue_as, heading="⚠️ Code backup")
        else:
            from telegram_notify import send_message
            send_message(text)
    except Exception as e:
        print(f"(telegram alert failed: {e})", file=sys.stderr)


def main():
    any_gap = False
    real_gaps = []          # non-scratch gaps found this run
    problems = []           # things a HUMAN must resolve — the only Telegram trigger in --push mode
    pushed_total = 0
    lines = []
    for r in REPOS:
        repo, remote = r["path"], r["remote"]
        try:
            git(repo, "fetch", "origin", "main", timeout=120)
        except Exception as e:
            lines.append(f"⚠ {remote}: fetch failed ({e}) — skipped")
            problems.append(f"⚠ {remote}: git fetch failed — backup state UNKNOWN ({str(e)[:150]})")
            continue
        new, mod, linked = classify(repo)
        if linked:
            lines.append(f"↔ {remote}: {len(linked)} symlink(s) into another repo — "
                         f"backed up there, not here")
        if not new and not mod:
            lines.append(f"✓ {remote}: in sync with GitHub")
            continue
        any_gap = True
        lines.append(f"✗ {remote}: {len(new)} only-on-VM, {len(mod)} modified-unpushed")
        for f in new:
            scratch = bool(SCRATCH_RE.search(f))
            lines.append(f"    NEW  {f}" + ("   [scratch]" if scratch else ""))
            if not scratch:
                real_gaps.append(f"{remote}: NEW {f}")
        for f in mod:
            scratch = bool(SCRATCH_RE.search(f))
            lines.append(f"    MOD  {f}" + ("   [scratch]" if scratch else ""))
            if not scratch:
                real_gaps.append(f"{remote}: MOD {f}")

        if PUSH:
            pushable = [f for f in (new + mod) if not SCRATCH_RE.search(f)]
            blocked = []
            for f in pushable:
                h = secret_hits(repo, f)
                if h:
                    blocked.append((f, h))
            pushable = [f for f in pushable if f not in {b[0] for b in blocked}]
            for f, h in blocked:
                lines.append(f"    ⛔ SKIPPED (possible secret) {f}: line {h[0][0]}")
                # A blocked file is the one case a human MUST see: it stays unbacked-up
                # until someone looks. Silently skipping it (the behaviour before
                # 2026-08-10) meant the only file that genuinely needed attention was
                # the only one nobody was told about.
                problems.append(f"⛔ {remote}: {f} not pushed — possible secret at line {h[0][0]}")
            if pushable:
                msg = f"backup: sync {len(pushable)} unpushed code files flagged by check_unpushed_code"
                try:
                    commit = push_repo(repo, remote, pushable, msg)
                    lines.append(f"    ⬆ pushed {len(pushable)} files as {commit[:8]}")
                    pushed_total += len(pushable)
                except Exception as e:
                    # Previously this raised straight out of main(), so a bad token or a
                    # GitHub outage killed the cron with nothing sent anywhere.
                    lines.append(f"    ✗ PUSH FAILED: {e}")
                    problems.append(f"✗ {remote}: push of {len(pushable)} file(s) FAILED — {str(e)[:200]}")

    # "Healthy" = no REAL gaps. Files matching SCRATCH_RE are intentionally
    # unpushed, so they don't count toward alerts, the exit code, or --quiet output.
    real = bool(real_gaps)
    report = "\n".join(lines)
    if real or problems or not QUIET:
        print(report)

    if NOTIFY:
        if PUSH:
            # Self-healing mode (cron default from 2026-08-10). The backup happens
            # automatically; Will only hears when something is left un-backed-up and
            # only a human can clear it — a blocked secret, a failed push, a failed
            # fetch. A clean run that pushed 27 files is not news, it is the job
            # working. Rule 7b still holds: silence here means "pushed or nothing to
            # push", never "could not tell" — every unknown path appends to problems.
            if problems:
                telegram("Auto-push could not complete:\n\n"
                         + "\n".join(f"• {p}" for p in problems[:20])
                         + (f"\n…and {len(problems) - 20} more" if len(problems) > 20 else "")
                         + "\n\nEverything else was pushed automatically.",
                         queue_as="check_unpushed_code.py")
        elif real:
            msg = ("⚠️ *Unpushed code detected* — files on the VM not backed up to GitHub:\n\n"
                   + "\n".join(f"• `{g}`" for g in real_gaps[:30])
                   + (f"\n…and {len(real_gaps) - 30} more" if len(real_gaps) > 30 else "")
                   + "\n\nRun `python3 scripts/check_unpushed_code.py --push` on the VM to sync.")
            telegram(msg)

    if PUSH:
        print(f"\n[summary] pushed {pushed_total} file(s); {len(problems)} needing a human.")
        sys.exit(1 if problems else 0)
    sys.exit(1 if real else 0)


if __name__ == "__main__":
    main()
