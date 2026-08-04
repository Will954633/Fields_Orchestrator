#!/usr/bin/env python3
"""
ssd_quota_autoresize.py
=======================
*** RETIRED 2026-08-05 — DO NOT RE-CRON. Kept for reference only. ***

Superseded by hardware: rather than wait on the SSD quota grant, a separate
750 GB `blobs-hdd` disk was attached and /data/blobs moved onto it (/dev/sdc,
738 G usable, 43% used). That is already well past this script's TARGET_BLOB of
700 GB, so there is nothing left for it to do. It also still points at
DEV=/dev/sdb (the old 400 GB `fields-blob-storage`), which is no longer the
volume serving blobs — running it now would grow the wrong disk.

Its cron line was lost in the 2026-07-30 [OPS-CRONTAB-WIPE] restore and has
deliberately NOT been reinstated; its system_monitor.job_runs heartbeat was
deleted in the same pass, so it no longer occupies a STALE row on the Fields
Systems Health board. To genuinely revive this, first re-point DEV at the disk
actually mounted at /data/blobs.

Original purpose follows.
---------------------------------------------------------------------------
Watcher that finishes the SSD-headroom job automatically once Google grants the
quota increase we filed 2026-07-30 (australia-southeast1 SSD_TOTAL_GB 500 -> 1000,
pending manual approval — the prior 600 request sat ungranted for 9 days).

While the quota is still 500 it's a silent no-op. The moment the effective limit
is >= NEEDED_LIMIT it resizes the fields-blob-storage disk 400 -> TARGET_BLOB GB
and grows its ext4 filesystem online (no downtime), then Telegram-alerts and
self-disables (sentinel + removes its own cron line).

Safe to run repeatedly:
  - idempotent: skips the disk resize if already >= target; always (re)runs
    resize2fs (a no-op if the fs already fills the disk) so a partial failure
    (disk grown but fs not) is repaired on the next tick rather than stranded.
  - only ever GROWS (pd can't shrink; resize2fs online-grow is safe on ext4).

Cron: every 6h. Re-arm by deleting /home/fields/.ssd-resized.
Self-reports to system_monitor.job_runs (CLAUDE.md Rule 7).
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from job_status import job_run  # noqa: E402

GCLOUD = "/snap/bin/gcloud"
REGION = "australia-southeast1"
ZONE = "australia-southeast1-b"
DISK = "fields-blob-storage"
DEV = "/dev/sdb"
TARGET_BLOB = 700          # grow the blob disk to this (GB)
NEEDED_LIMIT = 800         # 700 blob + 100 boot must fit under the SSD quota
SENTINEL = Path("/home/fields/.ssd-resized")


def sh(args, sudo=False, timeout=300):
    if sudo:
        args = ["sudo", "-n"] + args
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def ssd_limit():
    r = sh([GCLOUD, "compute", "regions", "describe", REGION, "--format=json"])
    data = json.loads(r.stdout or "{}")
    for q in data.get("quotas", []):
        if q.get("metric") == "SSD_TOTAL_GB":
            return float(q.get("limit", 0)), float(q.get("usage", 0))
    return 0.0, 0.0


def blob_size_gb():
    r = sh([GCLOUD, "compute", "disks", "describe", DISK, f"--zone={ZONE}", "--format=value(sizeGb)"])
    return int((r.stdout or "0").strip() or 0)


def fs_size_gb():
    r = sh(["df", "-BG", "--output=size", DEV])
    lines = [l.strip().rstrip("G") for l in (r.stdout or "").splitlines()[1:] if l.strip()]
    return int(lines[0]) if lines else 0


def alert(text):
    try:
        from telegram_notify import send_message
        send_message(text, parse_mode=None)
    except Exception as e:
        print(f"(telegram alert failed: {e})", file=sys.stderr)


def remove_own_cron():
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        new = "\n".join(l for l in cur.splitlines() if "ssd_quota_autoresize" not in l)
        subprocess.run(["crontab", "-"], input=new + "\n", text=True)
    except Exception as e:
        print(f"(cron self-remove failed: {e})", file=sys.stderr)


def main():
    with job_run("ssd_quota_autoresize", cadence_hours=6,
                 title="SSD quota → blob disk auto-resize") as beat:
        if SENTINEL.exists():
            beat.detail = "already resized (sentinel present) — noop"
            return

        limit, usage = ssd_limit()
        cur = blob_size_gb()
        fs = fs_size_gb()
        beat.metrics = {"ssd_limit": limit, "ssd_usage": usage, "blob_gb": cur, "fs_gb": fs}

        # Not ready: quota still too low AND disk not yet grown → wait quietly.
        if cur < TARGET_BLOB and limit < NEEDED_LIMIT:
            beat.detail = f"quota not ready (limit={limit:.0f}, need {NEEDED_LIMIT}) — waiting"
            return

        # Grow the disk if needed (quota is sufficient at this point).
        if cur < TARGET_BLOB:
            r = sh([GCLOUD, "compute", "disks", "resize", DISK, f"--zone={ZONE}",
                    f"--size={TARGET_BLOB}", "--quiet"])
            if r.returncode != 0:
                raise RuntimeError(f"disk resize failed: {r.stderr[:300]}")
            cur = TARGET_BLOB

        # Grow the filesystem online (idempotent — no-op if already full-size).
        g = sh(["resize2fs", DEV], sudo=True)
        if g.returncode != 0:
            raise RuntimeError(f"resize2fs failed: {g.stderr[:300]}")

        new_fs = fs_size_gb()
        SENTINEL.write_text(f"resized: disk={cur}GB fs={new_fs}GB\n")
        remove_own_cron()
        beat.detail = f"RESIZED {DISK} -> {cur}GB, grew {DEV} fs to ~{new_fs}GB"
        alert(f"✅ SSD quota granted (limit={limit:.0f}GB). Auto-resized {DISK} to "
              f"{cur}GB and grew {DEV} filesystem to ~{new_fs}GB — blob store now "
              f"has ~{new_fs - 394}GB extra headroom. Watcher self-disabled.")


if __name__ == "__main__":
    main()
