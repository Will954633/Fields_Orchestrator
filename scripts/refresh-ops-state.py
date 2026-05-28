#!/usr/bin/env python3
"""Refresh 00_Run_Commands/operations/STATE.md with a live snapshot of VM state.

Run nightly via cron, or by hand with --push to also mirror to GitHub.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/home/fields/Fields_Orchestrator")
OUT = REPO_ROOT / "00_Run_Commands" / "operations" / "STATE.md"
GH_REPO = "Will954633/Fields_Orchestrator"
GH_PATH = "00_Run_Commands/operations/STATE.md"


def sh(cmd: str, *, timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr if r.returncode and not r.stdout else "")
    except Exception as e:
        return f"<error: {e}>"


def services_block() -> str:
    out = sh("systemctl list-units --state=active --type=service | grep -E 'fields-|mongod|nginx' | awk '{print $1, $4}'")
    if not out.strip():
        return "_no fields-* services active_"
    rows = []
    for line in out.strip().splitlines():
        parts = line.split(None, 1)
        name = parts[0]
        state = parts[1] if len(parts) > 1 else ""
        rows.append(f"| `{name}` | {state} |")
    return "| Service | State |\n|---|---|\n" + "\n".join(rows)


def disks_block() -> str:
    out = sh("df -h --output=target,size,used,avail,pcent / 2>/dev/null | tail -n +2")
    rows = ["| Mount | Size | Used | Avail | Use% |", "|---|---|---|---|---|"]
    seen = set()
    for line in out.strip().splitlines():
        f = line.split()
        if len(f) >= 5 and f[0] not in seen:
            seen.add(f[0])
            rows.append(f"| {f[0]} | {f[1]} | {f[2]} | {f[3]} | {f[4]} |")
    return "\n".join(rows)


def blob_backup_block() -> str:
    # Avoid walking 994k files. Use df for disk pressure, gsutil for target.
    df_root = sh("df -h / 2>/dev/null | tail -1").strip()
    dst_size_h = sh("gsutil du -sh gs://fields-blob-backup/ 2>/dev/null | awk '{print $1, $2}'", timeout=120).strip() or "?"
    last_sync = sh("tail -1 /var/log/blob-backup/daily-sync.log 2>/dev/null").strip() or "_no daily-sync.log yet_"
    last_initial = sh("tail -1 /var/log/blob-backup/initial-sync.log 2>/dev/null").strip() or "_no initial-sync.log_"
    return (
        f"- **Source filesystem (`/`):** `{df_root}`\n"
        f"- **Target:** `gs://fields-blob-backup` — {dst_size_h}\n"
        f"- **Last daily sync log line:** `{last_sync[-200:]}`\n"
        f"- **Initial sync log last line:** `{last_initial[-200:]}`\n"
    )


def mongo_block() -> str:
    out = sh("systemctl is-active mongod 2>/dev/null").strip()
    rows = [f"- **mongod:** {out}"]
    probe = REPO_ROOT / "scripts" / "_ops_mongo_probe.py"
    counts = sh(
        f"bash -c 'set -a; source {REPO_ROOT}/.env; set +a; python3 {probe}'",
        timeout=60,
    ).strip()
    if counts and "|" in counts:
        rows.append("- **Estimated doc counts:**")
        for kv in counts.split("|"):
            rows.append(f"  - {kv}")
    else:
        rows.append(f"- **Doc count probe:** `{counts[:200]}`")
    return "\n".join(rows)


def crons_block() -> str:
    user_cron = sh("crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$'")
    # Skip root crontab — sudo would block from cron context.
    root_cron = "_(skipped — sudo unavailable from cron)_"
    out = "**User crontab:**\n```\n" + (user_cron.strip() or "(empty)") + "\n```\n"
    out += "**Root crontab:**\n```\n" + (root_cron.strip() or "(empty)") + "\n```\n"
    return out


def last_orchestrator_run() -> str:
    runs = REPO_ROOT / "logs" / "runs"
    if not runs.exists():
        return "_no logs/runs/_"
    subs = sorted(runs.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not subs:
        return "_no runs yet_"
    latest = subs[0]
    summary = latest / "run_summary.json"
    if summary.exists():
        try:
            d = json.loads(summary.read_text())
            return f"`{latest.name}` — started {d.get('start_time','?')}, status {d.get('status','?')}"
        except Exception:
            pass
    return f"`{latest.name}` — mtime {dt.datetime.fromtimestamp(latest.stat().st_mtime).isoformat(timespec='seconds')}"


def fix_history_recent() -> str:
    fh = REPO_ROOT / "logs" / "fix-history"
    files = sorted(fh.glob("*.md"), reverse=True)[:5]
    if not files:
        return "_none_"
    return "\n".join(f"- `{f.name}`" for f in files)


def push_to_github(content: str) -> str:
    sha_cmd = f"gh api 'repos/{GH_REPO}/contents/{GH_PATH}' --jq '.sha' 2>/dev/null"
    sha = sh(sha_cmd, timeout=20).strip()
    b64 = base64.b64encode(content.encode()).decode()
    payload_path = Path("/tmp/state-md-payload.json")
    msg = f"chore(ops): refresh STATE.md {dt.datetime.now().strftime('%Y-%m-%d %H:%M AEST')}"
    obj = {"message": msg, "content": b64}
    if sha and len(sha) == 40:
        obj["sha"] = sha
    payload_path.write_text(json.dumps(obj))
    res = sh(
        f"gh api 'repos/{GH_REPO}/contents/{GH_PATH}' --method PUT --input {payload_path}",
        timeout=60,
    )
    payload_path.unlink(missing_ok=True)
    return res[:400]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="Also push to GitHub via gh api")
    args = ap.parse_args()

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M AEST")
    content = f"""# STATE.md — Live VM Snapshot

> AUTO-GENERATED by `scripts/refresh-ops-state.py`. Last refresh: **{now}**.
> Do not edit by hand — your changes will be overwritten by the next cron run.
> See [README.md](README.md) for what's manual vs automatic.

## Services (active fields-* + adjacent)

{services_block()}

## Disk Usage

{disks_block()}

## Blob Backup (gs://fields-blob-backup)

{blob_backup_block()}

## MongoDB

{mongo_block()}

## Cron Jobs

{crons_block()}

## Latest Orchestrator Run

{last_orchestrator_run()}

## Recent Fix-History Files

{fix_history_recent()}
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content)
    print(f"Wrote {OUT} ({len(content)} bytes)")

    if args.push:
        print("Pushing to GitHub…")
        print(push_to_github(content))

    return 0


if __name__ == "__main__":
    sys.exit(main())
