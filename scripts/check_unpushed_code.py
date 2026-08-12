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

# ── Out-of-tree live files ───────────────────────────────────────────────────
# Files that RUN from a directory no repo scans, but whose backup belongs at a
# path inside one. `REPOS` above can only see files under a repo root, so an
# out-of-tree live file is invisible to this checker no matter how stale it gets.
#
# The failure this exists to stop (2026-08-13): the house valuation engine runs
# from /home/fields/Feilds_Website/07_Valuation_Comps/ — outside BOTH repo roots.
# Someone had worked around that by hand-copying it into the orchestrator repo at
# a mirror path and pushing it; the mirror was later deleted from the working
# tree, leaving GitHub as the only copy. The 2026-08-12 [VALUATION-UNKNOWN-
# ASYMMETRY] fix then edited the LIVE file and never reached GitHub, and the two
# sat 254 lines apart with nothing to notice — the checker was scanning a
# directory the file no longer lived in.
#
# Pointing at the LIVE path (not a copy of it) is the whole point: there is no
# second file to drift. Add an entry here rather than copying a file into a repo.
EXTRA_FILES = [
    {"local": "/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py",
     "remote": "Will954633/Fields_Orchestrator",
     "rel": "07_Valuation_Comps/precompute_valuations.py"},
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


def ghost_files(repo):
    """Paths git tracks that no longer exist on disk — GitHub-only 'ghosts'.

    `code_files()` filters these out with `os.path.isfile`, which is right for
    hashing (there is nothing to hash) but made them SILENT. A ghost is not a
    backup gap in itself — GitHub holds more than the VM, not less — but it is
    how a stale mirror hides: the 07_Valuation_Comps/precompute_valuations.py
    ghost made GitHub's copy look authoritative while the file that actually ran
    lived somewhere else entirely. Reported, not alerted, since most ghosts are
    ordinary uncommitted deletions.
    """
    out = git(repo, "ls-files", "-d", "--exclude-standard", check=False)
    return sorted(r.strip() for r in out.splitlines()
                  if r.strip().endswith(CODE_EXT))


def classify_extra():
    """(in_sync, gaps) for EXTRA_FILES — out-of-tree live files, by content hash."""
    in_sync, gaps = [], []
    for e in EXTRA_FILES:
        if not os.path.isfile(e["local"]):
            # A vanished live file is a real problem: nothing to back up, and the
            # entry silently covering nothing is exactly the Rule 7b failure.
            gaps.append({**e, "state": "MISSING"})
            continue
        local = subprocess.run(["git", "hash-object", e["local"]],
                               capture_output=True, env=ENV).stdout.decode().strip()
        p = subprocess.run(["gh", "api", f"repos/{e['remote']}/contents/{e['rel']}",
                            "--jq", ".sha"], capture_output=True, env=ENV)
        remote = p.stdout.decode().strip() if p.returncode == 0 else None
        if remote and local == remote:
            in_sync.append(e)
        else:
            gaps.append({**e, "state": "MOD" if remote else "NEW"})
    return in_sync, gaps


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


def secret_hits(path):
    """Scan an ABSOLUTE path. Takes a path rather than (repo, rel) so an
    out-of-tree EXTRA_FILES live copy is scanned exactly like an in-repo file —
    the secret gate must not have a hole for the files that bypass the repo."""
    # This file DEFINES the patterns, so scanning it matches itself — SECRET_RE contains
    # the literal "AccountKey=", which made check_unpushed_code.py block its own backup
    # and raise a "possible secret" alert about a regex. A detector must not be its own
    # first false positive.
    if os.path.abspath(path) == os.path.abspath(__file__):
        return []
    hits = []
    with open(path, errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if SECRET_RE.search(line) and not SECRET_ALLOW.search(line):
                hits.append((i, line.strip()[:120]))
    return hits


def push_repo(repo, remote, files, message, localmap=None):
    """`files` are repo-relative paths. `localmap` overrides where a path's BYTES
    come from, for EXTRA_FILES whose live copy sits outside the repo tree."""
    localmap = localmap or {}
    base = json.loads(gh([f"repos/{remote}/git/ref/heads/main"]))["object"]["sha"]
    base_tree = json.loads(gh([f"repos/{remote}/git/commits/{base}"]))["tree"]["sha"]
    tree = []
    for rel in files:
        with open(localmap.get(rel) or os.path.join(repo, rel), "rb") as fh:
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

        # Out-of-tree live files claiming a path in THIS repo (see EXTRA_FILES).
        extra_sync, extra_gaps = classify_extra()
        extra_sync = [e for e in extra_sync if e["remote"] == remote]
        extra_gaps = [e for e in extra_gaps if e["remote"] == remote]
        localmap = {e["rel"]: e["local"] for e in extra_gaps if e["state"] != "MISSING"}
        for e in extra_sync:
            lines.append(f"✓ {remote}: {e['rel']} (out-of-tree live file) in sync")
        for e in extra_gaps:
            if e["state"] == "MISSING":
                lines.append(f"    ⚠ MISSING {e['rel']} — live file gone: {e['local']}")
                problems.append(f"⚠ {remote}: EXTRA_FILES entry {e['rel']} points at a live "
                                f"file that no longer exists ({e['local']})")
            else:
                lines.append(f"    {e['state']:<4} {e['rel']}   [out-of-tree: {e['local']}]")
                real_gaps.append(f"{remote}: {e['state']} {e['rel']} (out-of-tree)")

        ghosts = ghost_files(repo)
        if ghosts:
            lines.append(f"👻 {remote}: {len(ghosts)} tracked file(s) on GitHub but not on the VM "
                         f"(not a backup gap — but a stale mirror hides here)")
            for g in ghosts[:10]:
                lines.append(f"    GONE {g}")

        if linked:
            lines.append(f"↔ {remote}: {len(linked)} symlink(s) into another repo — "
                         f"backed up there, not here")
        if not new and not mod and not localmap:
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
            pushable += list(localmap)          # out-of-tree live files
            blocked = []
            for f in pushable:
                h = secret_hits(localmap.get(f) or os.path.join(repo, f))
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
                    commit = push_repo(repo, remote, pushable, msg, localmap=localmap)
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
