#!/usr/bin/env python3
"""
Push the House Mini-Site FAQ/Process tab split to the website repo in a
SINGLE commit via the GitHub Git Data (tree) API.

Splits the seller-concern Q&A out of The Process tab into a dedicated FAQ
tab; The Process tab now holds the seasonality (timing) analysis only.

Single commit → one Netlify build → published cleanly
(see memory netlify_rapid_commits_unpublished).
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
    "src/pages/YourHomePage/YourHomePage.tsx":             f"{LOCAL_ROOT}/src/pages/YourHomePage/YourHomePage.tsx",
    "src/pages/YourHomePage/tabs/FaqTab.tsx":              f"{LOCAL_ROOT}/src/pages/YourHomePage/tabs/FaqTab.tsx",
    "src/pages/YourHomePage/tabs/ProcessTab.tsx":          f"{LOCAL_ROOT}/src/pages/YourHomePage/tabs/ProcessTab.tsx",
    "src/pages/YourHomePage/components/FearSection.tsx":   f"{LOCAL_ROOT}/src/pages/YourHomePage/components/FearSection.tsx",
}

COMMIT_MSG = (
    "feat(your-home): split seller Q&A into a dedicated FAQ tab\n\n"
    "The Process tab was holding FAQ-style seller concerns (agent selection, "
    "settlement, sell-first/buy-first, cost of sale). Move those into a new "
    "FAQ tab (FaqTab) along with the Research Library bibliography and editorial "
    "footer. The Process tab now holds the seasonality (timing) analysis only, "
    "ready for further timing sections. FearSection eyebrow 'The process' -> "
    "'Common question'.\n\n"
    "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
)


def gh_api(path, method="GET", payload=None):
    cmd = ["gh", "api", f"repos/{REPO}/{path}", "-X", method]
    inp = None
    if payload is not None:
        cmd += ["--input", "-"]
        inp = json.dumps(payload)
    r = subprocess.run(cmd, input=inp, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gh api {method} {path} failed:\n{r.stderr}\n{r.stdout}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def main():
    ref = gh_api(f"git/ref/heads/{BRANCH}")
    base_commit_sha = ref["object"]["sha"]
    base_commit = gh_api(f"git/commits/{base_commit_sha}")
    base_tree_sha = base_commit["tree"]["sha"]
    print(f"base commit {base_commit_sha[:8]} tree {base_tree_sha[:8]}")

    tree_entries = []
    for repo_path, local_path in FILES.items():
        with open(local_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()
        blob = gh_api("git/blobs", "POST", {"content": content_b64, "encoding": "base64"})
        tree_entries.append({"path": repo_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"blob {blob['sha'][:8]}  {repo_path}")

    tree = gh_api("git/trees", "POST", {"base_tree": base_tree_sha, "tree": tree_entries})
    print(f"tree {tree['sha'][:8]}")

    commit = gh_api("git/commits", "POST", {
        "message": COMMIT_MSG,
        "tree": tree["sha"],
        "parents": [base_commit_sha],
    })
    print(f"commit {commit['sha'][:8]}")

    gh_api(f"git/refs/heads/{BRANCH}", "PATCH", {"sha": commit["sha"], "force": False})
    print(f"\nPushed {len(FILES)} files in one commit: {commit['sha']}")
    print(f"https://github.com/{REPO}/commit/{commit['sha']}")


if __name__ == "__main__":
    main()
