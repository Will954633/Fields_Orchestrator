#!/usr/bin/env python3
"""
Push the House Mini-Site "Source Layer" change to the website repo in a
SINGLE commit via the GitHub Git Data (tree) API.

Why a single commit: the contents API creates one commit per file, and N
rapid commits to Netlify leaves the final build `ready` but `published_at:
null` (see memory netlify_rapid_commits_unpublished). One tree → one commit
→ one build → published cleanly.

Auth: uses the `gh` CLI (GH_CONFIG_DIR already exported in ~/.bashrc).
"""
import base64
import json
import subprocess
import sys

REPO = "Will954633/Website_Version_Feb_2026"
BRANCH = "main"
LOCAL_ROOT = "/home/fields/Feilds_Website/01_Website"

# repo_path (root-relative)  ->  local_path
FILES = {
    # Code — the Source Layer
    "src/pages/YourHomePage/data/references.ts":            f"{LOCAL_ROOT}/src/pages/YourHomePage/data/references.ts",
    "src/pages/YourHomePage/components/CitationStrip.tsx":  f"{LOCAL_ROOT}/src/pages/YourHomePage/components/CitationStrip.tsx",
    "src/pages/YourHomePage/components/ResearchLibrary.tsx":f"{LOCAL_ROOT}/src/pages/YourHomePage/components/ResearchLibrary.tsx",
    "src/pages/YourHomePage/data/homeFixture.ts":           f"{LOCAL_ROOT}/src/pages/YourHomePage/data/homeFixture.ts",
    "src/pages/YourHomePage/tabs/ProcessTab.tsx":           f"{LOCAL_ROOT}/src/pages/YourHomePage/tabs/ProcessTab.tsx",
    "public/robots.txt":                                    f"{LOCAL_ROOT}/public/robots.txt",
}

# Mirrored research PDFs (public/research/*) added programmatically below.
import glob, os
for p in sorted(glob.glob(f"{LOCAL_ROOT}/public/research/*.pdf")):
    FILES[f"public/research/{os.path.basename(p)}"] = p

COMMIT_MSG = (
    "feat(your-home): Source Layer — clickable academic citations + research library\n\n"
    "Every claim on the mini-site now links to the underlying paper "
    "(Opportunity-Report-v2 §1.2). Adds a references registry, makes "
    "CitationStrip render clickable sources, wires the agent-selection and "
    "FSBO sections to the papers behind them, adds a ResearchLibrary index on "
    "the Process tab, and mirrors 22 freely-redistributable PDFs under "
    "/research/ (Disallow'd in robots.txt). No watermark on third-party papers.\n\n"
    "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
)


def gh_api(path, method="GET", payload=None):
    cmd = ["gh", "api", f"repos/{REPO}/{path}", "-X", method]
    if payload is not None:
        cmd += ["--input", "-"]
        inp = json.dumps(payload)
    else:
        inp = None
    r = subprocess.run(cmd, input=inp, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gh api {method} {path} failed:\n{r.stderr}\n{r.stdout}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def main():
    # 1. base ref + commit + tree
    ref = gh_api(f"git/ref/heads/{BRANCH}")
    base_commit_sha = ref["object"]["sha"]
    base_commit = gh_api(f"git/commits/{base_commit_sha}")
    base_tree_sha = base_commit["tree"]["sha"]
    print(f"base commit {base_commit_sha[:8]} tree {base_tree_sha[:8]}")

    # 2. blobs
    tree_entries = []
    for repo_path, local_path in FILES.items():
        with open(local_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()
        blob = gh_api("git/blobs", "POST", {"content": content_b64, "encoding": "base64"})
        tree_entries.append({"path": repo_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"blob {blob['sha'][:8]}  {repo_path}")

    # 3. tree
    tree = gh_api("git/trees", "POST", {"base_tree": base_tree_sha, "tree": tree_entries})
    print(f"tree {tree['sha'][:8]}")

    # 4. commit
    commit = gh_api("git/commits", "POST", {
        "message": COMMIT_MSG,
        "tree": tree["sha"],
        "parents": [base_commit_sha],
    })
    print(f"commit {commit['sha'][:8]}")

    # 5. move ref
    gh_api(f"git/refs/heads/{BRANCH}", "PATCH", {"sha": commit["sha"], "force": False})
    print(f"\nPushed {len(FILES)} files in one commit: {commit['sha']}")
    print(f"https://github.com/{REPO}/commit/{commit['sha']}")


if __name__ == "__main__":
    main()
