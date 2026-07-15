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
SCRATCH_RE = re.compile(r"11_House_Mini_Site/|13_Will-Learns-to-Code/|08_Seller-Book/|v2-e2e|v3-[a-z]|-e2e-test|-e2e-wave")
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


def classify(repo):
    """Return (new_only_on_vm, modified) — real gaps only, by content hash."""
    new, mod = [], []
    for rel in code_files(repo):
        local = git(repo, "hash-object", rel).strip()
        remote = remote_blob(repo, rel)
        if remote is None:
            new.append(rel)
        elif local != remote:
            mod.append(rel)
    return sorted(new), sorted(mod)


def secret_hits(repo, rel):
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


def telegram(text):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from telegram_notify import send_message
        send_message(text)
    except Exception as e:
        print(f"(telegram alert failed: {e})", file=sys.stderr)


def main():
    any_gap = False
    real_gaps = []          # non-scratch gaps worth a human alert
    lines = []
    for r in REPOS:
        repo, remote = r["path"], r["remote"]
        try:
            git(repo, "fetch", "origin", "main", timeout=120)
        except Exception as e:
            lines.append(f"⚠ {remote}: fetch failed ({e}) — skipped")
            continue
        new, mod = classify(repo)
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
            if pushable:
                msg = f"backup: sync {len(pushable)} unpushed code files flagged by check_unpushed_code"
                commit = push_repo(repo, remote, pushable, msg)
                lines.append(f"    ⬆ pushed {len(pushable)} files as {commit[:8]}")

    # "Healthy" = no REAL gaps. Files matching SCRATCH_RE are intentionally
    # unpushed, so they don't count toward alerts, the exit code, or --quiet output.
    real = bool(real_gaps)
    report = "\n".join(lines)
    if real or not QUIET:
        print(report)
    if NOTIFY and real and not PUSH:
        msg = ("⚠️ *Unpushed code detected* — files on the VM not backed up to GitHub:\n\n"
               + "\n".join(f"• `{g}`" for g in real_gaps[:30])
               + (f"\n…and {len(real_gaps) - 30} more" if len(real_gaps) > 30 else "")
               + "\n\nRun `python3 scripts/check_unpushed_code.py --push` on the VM to sync.")
        telegram(msg)
    sys.exit(1 if real and not PUSH else 0)


if __name__ == "__main__":
    main()
