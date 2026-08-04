#!/usr/bin/env python3
"""Push N files to a GitHub repo as ONE commit, then verify the bytes landed.

Why this exists
---------------
`gh api .../contents/<path>` is one commit per file, and every commit to
`Website_Version_Feb_2026` triggers its own Netlify build at ~15 credits against
a 3,000/month allowance. A 10-file change pushed file-by-file is 10 builds, of
which Netlify cancels most as each supersedes the last — so you pay for builds
that produce nothing and the real one lands last.

On 2026-07-23 that pattern (79 deploys in a session) exhausted the allowance and
Netlify served 503 `usage_exceeded` to real visitors site-wide. On 2026-08-04 it
happened again at smaller scale: ~29 commits for one feature, 38 errored deploys
across the day. Both times the lesson already existed and was not applied. This
script exists so the correct path is the easy one.

It also re-fetches every file after pushing and compares md5, because the
contents API has returned success while storing empty or stale bytes, and its
read-after-write is not immediately consistent (a mismatch on the first read is
often lag, so verification retries before failing).

Usage
-----
    python3 scripts/push_website_files.py -m "feat: message" \\
        src/components/Foo/Foo.tsx public/foo/bar.webp

Paths are given relative to the website root and are used unchanged as repo
paths (the website lives at the repo root; local `01_Website/` is not part of
the repo path). Use --root/--repo for other repos.
"""

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time

DEFAULT_REPO = "Will954633/Website_Version_Feb_2026"
DEFAULT_ROOT = "/home/fields/Feilds_Website/01_Website/"
VERIFY_ATTEMPTS = 4
VERIFY_WAIT_S = 4


def gh(args, payload=None, raw=False):
    """Call gh api.

    Payload goes via --input rather than --field to dodge arg-length limits on
    large blobs. `raw=True` returns stdout verbatim — needed for `--jq`, which
    emits a bare unquoted string that is not valid JSON.
    """
    cmd = ["gh", "api"] + args
    if payload is not None:
        with open("/tmp/_ghpayload.json", "w") as fh:
            json.dump(payload, fh)
        cmd += ["--input", "/tmp/_ghpayload.json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {args[0]} failed: {r.stderr.strip()[:300]}")
    if raw:
        return r.stdout.strip()
    return json.loads(r.stdout) if r.stdout.strip() else {}


def push(repo, root, message, rel_paths, branch="main"):
    # 1. current head + its tree
    ref = gh([f"repos/{repo}/git/ref/heads/{branch}"])
    head_sha = ref["object"]["sha"]
    base_tree = gh([f"repos/{repo}/git/commits/{head_sha}"])["tree"]["sha"]

    # 2. a blob per file. Base64 keeps binaries (webp/mp3/pdf) intact — the
    #    "utf-8" encoding would corrupt them.
    local_md5 = {}
    tree = []
    for rel in rel_paths:
        with open(root + rel, "rb") as fh:
            raw = fh.read()
        local_md5[rel] = hashlib.md5(raw).hexdigest()
        blob = gh([f"repos/{repo}/git/blobs", "--method", "POST"],
                  {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"  blob  {rel:<58} {len(raw):>8}B")

    # 3. one tree, one commit, one ref move -> one Netlify build
    new_tree = gh([f"repos/{repo}/git/trees", "--method", "POST"],
                  {"base_tree": base_tree, "tree": tree})
    commit = gh([f"repos/{repo}/git/commits", "--method", "POST"],
                {"message": message, "tree": new_tree["sha"], "parents": [head_sha]})
    gh([f"repos/{repo}/git/refs/heads/{branch}", "--method", "PATCH"],
       {"sha": commit["sha"]})
    print(f"\n  commit {commit['sha'][:8]}  ({len(rel_paths)} files, 1 build)")

    # 4. verify bytes actually landed
    print()
    ok = True
    for rel in rel_paths:
        remote = "?"
        for attempt in range(VERIFY_ATTEMPTS):
            try:
                content = gh([f"repos/{repo}/contents/{rel}", "--jq", ".content"], raw=True)
                remote = hashlib.md5(base64.b64decode(content)).hexdigest() if content else "?"
            except (RuntimeError, ValueError):
                remote = "?"  # transient read failure; retry below
            if remote == local_md5[rel]:
                print(f"  OK    {rel:<58} {local_md5[rel][:8]}")
                break
            if attempt < VERIFY_ATTEMPTS - 1:
                time.sleep(VERIFY_WAIT_S)  # read-after-write lag, usually clears
        else:
            print(f"  MISMATCH {rel:<55} local {local_md5[rel][:8]} != remote {remote[:8]}")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="paths relative to --root")
    ap.add_argument("-m", "--message", required=True, help="commit message")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--branch", default="main")
    a = ap.parse_args()
    root = a.root if a.root.endswith("/") else a.root + "/"
    ok = push(a.repo, root, a.message, a.files, a.branch)
    print(f"\n{'all files verified' if ok else 'VERIFICATION FAILED — check above'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
