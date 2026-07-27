#!/usr/bin/env python3
"""
resource_guard.py — fast on-VM resource governor (Layer 1 + early-warning Layer 3)

Runs every ~90s via the fields-resource-guard.timer systemd timer, as root.
Deliberately INDEPENDENT of the 60-minute orchestrator watchdog (watchdog.py),
which runs on the VM and therefore dies with it when the box wedges.

Context — why this exists (2026-07-27):
  The VM (e2-standard-2, 8 GB) OOM-cascaded and hung so hard that sshd and every
  service died; recovery needed an external `gcloud compute instances reset`.
  Root cause was Claude Code / code-server sessions accumulating memory (one
  `claude` process reached 3.8 GB) on top of scraper Chrome, exhausting RAM.
  The old watchdog only killed Chrome, every 60 min — useless against the real
  culprit and dead once the box wedged.

This guard is the PREVENTIVE on-VM layer. The hard memory bound is now the
systemd MemoryMax cap on code-server.service (all Claude sessions share that
cgroup), so the kernel kills a single session within-slice under pressure
rather than wedging the box. This guard adds, on a fast cadence:

  1. Disk guard    — clean journald/logs/caches before / fills (disk exhaustion
                     silently killed syslog weeks before the final OOM).
  2. Orphan reap   — kill PROVABLY-orphaned Claude/MCP/Chrome processes (PPID==1),
                     the leaked leftovers of torn-down sessions. Never touches a
                     live session (its parent is a live extension host, not init).
  3. Early warning — Telegram Will when memory or disk TREND toward the cliff,
                     WHILE the box is still reachable. This is the core ask:
                     capture the risk before the VM becomes unresponsive.
  4. OOM re-assert — keep mongod / orchestrator protected (negative oom_score_adj)
                     even across their restarts, until the drop-ins take effect.
  5. Audit         — every action -> system_monitor.resource_guard_actions + log.

Usage:
    sudo python3 scripts/resource_guard.py            # one pass (timer mode)
    python3 scripts/resource_guard.py --dry-run       # diagnose only, no actions
    python3 scripts/resource_guard.py --dry-run -v    # verbose
"""

import os
import re
import sys
import glob
import json
import time
import signal
import argparse
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --------------------------------------------------------------------------- #
# Config / thresholds
# --------------------------------------------------------------------------- #
BASE_DIR = Path("/home/fields/Fields_Orchestrator")
ENV_FILE = BASE_DIR / ".env"
LOG_FILE = BASE_DIR / "logs" / "resource-guard.log"
STATE_FILE = BASE_DIR / "logs" / "resource_guard_state.json"

MEM_WARN_PCT = 88.0   # sustained -> Telegram early warning
MEM_CRIT_PCT = 94.0   # reap orphans + Telegram
DISK_WARN_PCT = 85.0  # routine cleanup
DISK_CRIT_PCT = 92.0  # aggressive cleanup + Telegram
SUSTAIN_N = 3         # consecutive high checks (~90s each => ~4.5 min) before alerting
ALERT_COOLDOWN_H = 3  # min hours between alerts of the same category

# Process patterns considered reapable ONLY when orphaned (PPID==1).
ORPHAN_REAP_PATTERNS = [
    "native-binary/claude",
    "mcp-servers/gdrive/index.mjs",
    "chrome",  # scraper Chrome leftovers
]

# Services whose main process we keep protected from the OOM killer each pass.
PROTECT = {"mongod": -800, "fields-orchestrator": -500}

VERBOSE = False


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [resource-guard] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def vlog(msg: str):
    if VERBOSE:
        log(msg)


# --------------------------------------------------------------------------- #
# Env / state
# --------------------------------------------------------------------------- #
def load_env():
    """Parse .env (plain KEY=VALUE, last-wins, strip quotes) into os.environ."""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ[key] = val  # last occurrence wins, matching `source .env`


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"mem_high_streak": 0, "disk_high_streak": 0, "last_alert": {}}


def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log(f"WARN could not save state: {e}")


def alert_allowed(state: dict, category: str) -> bool:
    last = state.get("last_alert", {}).get(category)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return datetime.now(timezone.utc) - last_dt >= timedelta(hours=ALERT_COOLDOWN_H)


def mark_alerted(state: dict, category: str):
    state.setdefault("last_alert", {})[category] = datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def get_metrics() -> dict:
    import psutil
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    try:
        la = os.getloadavg()
    except Exception:
        la = (None, None, None)
    return {
        "mem_pct": mem.percent,
        "mem_used_gb": round(mem.used / 1e9, 2),
        "mem_total_gb": round(mem.total / 1e9, 2),
        "swap_pct": swap.percent,
        "disk_pct": disk.percent,
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "load_1m": la[0],
    }


def top_mem_processes(n=6) -> list:
    """Return list of (pid, rss_mb, user, cmd) for the top-n memory processes."""
    import psutil
    procs = []
    for p in psutil.process_iter(["pid", "memory_info", "username", "cmdline"]):
        try:
            rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
            cmd = " ".join(p.info["cmdline"] or [])[:80]
            procs.append((p.info["pid"], rss // (1024 * 1024), p.info["username"], cmd))
        except Exception:
            continue
    procs.sort(key=lambda x: x[1], reverse=True)
    return procs[:n]


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def reassert_oom_protection(dry: bool) -> list:
    """Keep mongod/orchestrator protected from the OOM killer, live, each pass."""
    actions = []
    for name, score in PROTECT.items():
        try:
            out = subprocess.run(
                ["systemctl", "show", name if name.startswith("fields") else f"{name}.service",
                 "-p", "MainPID", "--value"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            pid = int(out) if out.isdigit() else 0
        except Exception:
            pid = 0
        # mongod may not be a "fields-" unit; resolve by name fallback
        if not pid:
            try:
                pid = int(subprocess.run(["pgrep", "-x", name], capture_output=True, text=True).stdout.split()[0])
            except Exception:
                pid = 0
        if not pid:
            continue
        path = f"/proc/{pid}/oom_score_adj"
        try:
            cur = Path(path).read_text().strip()
            if cur == str(score):
                continue
            if not dry:
                Path(path).write_text(str(score))
            actions.append(f"oom_protect {name} pid={pid} {cur}->{score}")
        except Exception as e:
            vlog(f"oom protect {name}: {e}")
    return actions


def reap_orphans(dry: bool) -> list:
    """Kill PROVABLY-orphaned reapable processes (parent == init/1)."""
    import psutil
    actions = []
    for p in psutil.process_iter(["pid", "ppid", "cmdline", "memory_info", "create_time"]):
        try:
            if p.info["ppid"] != 1:
                continue  # only genuine orphans; a live session's parent is its extension host
            cmd = " ".join(p.info["cmdline"] or [])
            if not any(pat in cmd for pat in ORPHAN_REAP_PATTERNS):
                continue
            # guard against reaping something that just reparented milliseconds ago
            age_s = time.time() - p.info["create_time"]
            if age_s < 120:
                continue
            rss_mb = (p.info["memory_info"].rss if p.info["memory_info"] else 0) // (1024 * 1024)
            label = next(pat for pat in ORPHAN_REAP_PATTERNS if pat in cmd)
            if not dry:
                try:
                    os.kill(p.info["pid"], signal.SIGTERM)
                    time.sleep(0.5)
                    if psutil.pid_exists(p.info["pid"]):
                        os.kill(p.info["pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass
            actions.append(f"reap_orphan {label} pid={p.info['pid']} rss={rss_mb}MB age={int(age_s)}s")
        except Exception:
            continue
    return actions


def _run(cmd: list, dry: bool):
    vlog(f"{'DRY ' if dry else ''}run: {' '.join(cmd)}")
    if dry:
        return
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        vlog(f"cmd failed {cmd}: {e}")


def disk_cleanup(aggressive: bool, dry: bool) -> list:
    """Reclaim disk. `aggressive` when past DISK_CRIT_PCT."""
    actions = []
    # 1. journald — cap ring buffer
    size = "150M" if aggressive else "300M"
    _run(["journalctl", f"--vacuum-size={size}"], dry)
    actions.append(f"journald vacuum -> {size}")
    # 2. apt / pip caches
    _run(["apt-get", "clean"], dry)
    if os.path.isdir("/home/fields/venv"):
        _run(["/home/fields/venv/bin/pip", "cache", "purge"], dry)
    actions.append("apt+pip cache cleared")
    # 3. truncate oversized logs (>100MB) under logs/ and /tmp/vm_metrics.log
    big = []
    for pat in [str(BASE_DIR / "logs" / "**" / "*.log"), "/tmp/vm_metrics.log"]:
        for f in glob.glob(pat, recursive=True):
            try:
                if os.path.getsize(f) > 100 * 1024 * 1024:
                    if not dry:
                        # keep the tail, drop the head
                        subprocess.run(f"tail -c 5242880 '{f}' > '{f}.tmp' && mv '{f}.tmp' '{f}'",
                                       shell=True, timeout=60)
                    big.append(os.path.basename(f))
            except Exception:
                continue
    if big:
        actions.append(f"truncated big logs: {', '.join(big[:8])}")
    # 4. prune old per-run logs (>14d)
    runs = BASE_DIR / "logs" / "runs"
    if runs.is_dir():
        cutoff = time.time() - 14 * 86400
        pruned = 0
        for d in runs.iterdir():
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    if not dry:
                        subprocess.run(["rm", "-rf", str(d)], timeout=30)
                    pruned += 1
            except Exception:
                continue
        if pruned:
            actions.append(f"pruned {pruned} old run-logs (>14d)")
    return actions


# --------------------------------------------------------------------------- #
# Alerting + audit
# --------------------------------------------------------------------------- #
def send_telegram(text: str, dry: bool):
    if dry:
        log(f"DRY telegram: {text.splitlines()[0]}")
        return
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import telegram_notify
        telegram_notify.BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        telegram_notify.CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
        telegram_notify.send_message(text)
    except Exception as e:
        log(f"WARN telegram send failed: {e}")


def audit(metrics: dict, actions: list, level: str):
    """Write a record to system_monitor.resource_guard_actions (best-effort)."""
    if not actions and level == "ok":
        return  # don't spam the DB on healthy passes
    try:
        from pymongo import MongoClient
        conn = os.environ.get("COSMOS_CONNECTION_STRING")
        if not conn:
            return
        client = MongoClient(conn, serverSelectionTimeoutMS=8000, socketTimeoutMS=12000, retryWrites=False)
        client["system_monitor"]["resource_guard_actions"].insert_one({
            "recorded_at": datetime.now(timezone.utc),
            "level": level,
            "metrics": metrics,
            "actions": actions,
        })
        client.close()
    except Exception as e:
        vlog(f"audit write failed: {e}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="diagnose only, take no actions")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose
    dry = args.dry_run

    load_env()
    state = load_state()
    m = get_metrics()
    actions = []
    level = "ok"

    vlog(f"mem={m['mem_pct']}% swap={m['swap_pct']}% disk={m['disk_pct']}% "
         f"used={m['mem_used_gb']}/{m['mem_total_gb']}GB load={m['load_1m']}")

    # --- always: keep critical services protected ---
    actions += reassert_oom_protection(dry)

    # --- memory ---
    if m["mem_pct"] >= MEM_WARN_PCT:
        state["mem_high_streak"] = state.get("mem_high_streak", 0) + 1
    else:
        state["mem_high_streak"] = 0

    if m["mem_pct"] >= MEM_CRIT_PCT:
        level = "critical"
        actions += reap_orphans(dry)
        if alert_allowed(state, "mem"):
            top = top_mem_processes()
            body = "\n".join(f"  {rss}MB {user} {cmd}" for _, rss, user, cmd in top)
            send_telegram(
                f"\U0001F534 *VM memory CRITICAL* {m['mem_pct']:.0f}% "
                f"({m['mem_used_gb']}/{m['mem_total_gb']}GB), swap {m['swap_pct']:.0f}%\n"
                f"Top consumers:\n{body}\n"
                f"code-server slice is capped at 5G so a session (not mongod) will be "
                f"OOM-killed if it climbs further. Reachable now — check if action needed.",
                dry)
            mark_alerted(state, "mem")
    elif state.get("mem_high_streak", 0) >= SUSTAIN_N:
        level = "warn" if level == "ok" else level
        if alert_allowed(state, "mem"):
            top = top_mem_processes()
            body = "\n".join(f"  {rss}MB {user} {cmd}" for _, rss, user, cmd in top)
            send_telegram(
                f"⚠️ *VM memory high* {m['mem_pct']:.0f}% for "
                f"{state['mem_high_streak']} checks ({m['mem_used_gb']}/{m['mem_total_gb']}GB), "
                f"swap {m['swap_pct']:.0f}%\nTop consumers:\n{body}\n"
                f"Box still healthy — flagging early. Likely accumulated Claude Code sessions.",
                dry)
            mark_alerted(state, "mem")

    # --- disk ---
    if m["disk_pct"] >= DISK_WARN_PCT:
        state["disk_high_streak"] = state.get("disk_high_streak", 0) + 1
        aggressive = m["disk_pct"] >= DISK_CRIT_PCT
        actions += disk_cleanup(aggressive, dry)
        # re-measure after cleanup
        m_after = get_metrics()
        actions.append(f"disk {m['disk_pct']:.0f}%->{m_after['disk_pct']:.0f}% after cleanup")
        if aggressive:
            level = "critical"
            if alert_allowed(state, "disk"):
                send_telegram(
                    f"\U0001F534 *VM disk CRITICAL* {m['disk_pct']:.0f}% on / "
                    f"({m['disk_used_gb']}/{m['disk_total_gb']}GB). Auto-cleanup ran "
                    f"(now {m_after['disk_pct']:.0f}%). Reachable now — investigate growth.",
                    dry)
                mark_alerted(state, "disk")
    else:
        state["disk_high_streak"] = 0

    save_state(state)
    if actions:
        log(f"level={level} actions={actions}")
    else:
        vlog("level=ok no actions")
    audit(m, actions, level)


if __name__ == "__main__":
    main()
