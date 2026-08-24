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
  2b. Slice-hog reap — kill ANY single process in the Claude cgroup over an RSS
                     ceiling, whatever it is (reap_slice_hog). The orphan reaper
                     needs PPID==1 and the search reaper needs a search argv[0];
                     a runaway with a live parent that is not a search fell
                     through both and wedged the workbench for 70 min on
                     2026-08-24. Scoped to the cgroup, so it cannot reach sshd,
                     mongod or the orchestrator.
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

# When cleanup runs at CRITICAL and frees essentially nothing, the ordinary disk
# alert is actively misleading — it says "auto-cleanup ran", which reads as
# handled. That case gets its own category and a much shorter cooldown so it
# cannot be mistaken for the routine message. See 2026-08-15: cleanup reclaimed
# ~0 bytes on 976 consecutive critical passes while / sat at 100%, and the only
# messages sent were the routine 3-hourly ones.
CLEANUP_INEFFECTIVE_BYTES = 200 * 1024 * 1024   # < this freed == "did nothing"
INEFFECTIVE_COOLDOWN_H = 1.0
# Same escalation one band lower. Added 2026-08-18: the check above only ever ran
# inside `if aggressive`, i.e. at >= DISK_CRIT_PCT. Root sat at 90-91% — above
# WARN, below CRIT — for days while cleanup freed 0MB every 90s, and because the
# non-aggressive branch also left `level` at "ok", the guard's own heartbeat
# published `level=ok disk=90%`. Nothing alerted; the 12G that was actually
# filling the disk was found only by a manual audit. A longer cooldown than the
# critical one because 85-91% is not an emergency — but it must be visible.
INEFFECTIVE_WARN_COOLDOWN_H = 6.0
GROWTH_SCAN_ROOTS = ["/home/fields", "/var", "/tmp"]

# --------------------------------------------------------------------------- #
# Scratch directories this guard may sweep  (added 2026-08-15)
# --------------------------------------------------------------------------- #
# ⚠ THIS IS AN ALLOWLIST, AND IT MUST STAY ONE. Do not generalise it to
# "artifacts/" or to an age sweep over the whole tree. Two things there are NOT
# scratch and would be destroyed:
#   * artifacts/appraisals_v4/*.pdf — system_monitor.appraisal_pipeline docs
#     reference these paths by name. Re-measured 2026-08-18: 682 live refs
#     across 278 pipeline docs (the "95" this comment claimed since 2026-08-15
#     was already 7x stale), oldest file 2026-05-15. An age sweep is exactly
#     what kills them. Recount before trusting any number here:
#       python3 - <<'PY'
#       from shared.db import get_client; import re
#       refs={m for d in get_client()['system_monitor']['appraisal_pipeline']
#             .find({},{'_id':0})
#             for m in re.findall(r'appraisals_v4/([^\'"\s,\)\]]+)', str(d))}
#       print(len(refs))
#       PY
#   * assets/img/cover_hero_*.jpg — the durable pre-warm cache; deleting it
#     forces a full, expensive rebuild of the catchment.
#     ⚠ MOVED 2026-08-18: this is now a SYMLINK to
#     /data/blobs/appraisal_assets/img. It was 12G of the 23G under artifacts/
#     and sat on the 97G root disk (then 90% full) while /data/blobs is a
#     separate 738G disk at 53%. Nothing was deleted — rsync'd, checksum
#     -verified, symlinked, then the original removed; root fell 90% -> 79%.
#     A sweep here now deletes from the BLOB disk, which is worse, not better.
# The pre-warm already unlinks its own intermediates once published to blob
# storage (prewarm_offmarket_covers.py), so the top level is not ours to manage.
#
# ⚠ This guard reported `level=ok ... reclaimed 0MB, disk 90%->90%` every 90s
# while root filled up, because everything it is allowed to sweep is small and
# the thing that was actually growing is on the deny side of this allowlist.
# CLEANUP_INEFFECTIVE_BYTES (above) is the alert that is supposed to catch that
# — it fires on <200MB freed at CRITICAL (92%), and root sat at 90-91%, just
# under the threshold, for days. Consider whether DISK_WARN_PCT deserves the
# same ineffective-cleanup escalation, not just DISK_CRIT_PCT.
#
# Every entry below must be justified: pure scratch, regenerable, unreferenced.
#   aerial_tmp       render scratch; the generator copies to the shared cache and
#                    unlinks. This is belt-and-braces for the non-cover path.
#   browser_artifacts one timestamped dir per site-inspector run; only the newest
#                    is ever read (ceo-telegram-bridge treats it as "evidence
#                    gathered immediately before this reply"). 444 dirs back to
#                    April were sitting there at ~1GB.
SCRATCH_SWEEP = [
    (BASE_DIR / "artifacts" / "appraisals_v4" / "assets" / "aerial_tmp", 1),
    (BASE_DIR / "artifacts" / "browser_artifacts", 7),
]

# Process patterns considered reapable ONLY when orphaned (PPID==1).
ORPHAN_REAP_PATTERNS = [
    "native-binary/claude",
    "mcp-servers/gdrive/index.mjs",
    "chrome",  # scraper Chrome leftovers
]

# --------------------------------------------------------------------------- #
# Runaway search-process ceiling  (added 2026-08-06 after the ugrep lockups)
# --------------------------------------------------------------------------- #
# Claude Code installs a bash *function* named `grep` that rewrites every shell
# `grep` into:
#     exec -a ugrep <claude-binary> -G --ignore-files --hidden -I --exclude-dir=...
# so ugrep 7.5.0 (statically linked into the claude binary) is what actually
# runs. Bounded BRE repeats on BOTH sides of a literal -- e.g.
#     grep -o -i "price[^<]\{0,120\}auction[^<]\{0,120\}\|auction[^<]\{0,120\}price[^<]\{0,120\}"
# -- combined with -o and -i, over a file with very long lines (minified HTML,
# base64 data: URIs) make ugrep's RE/flex matcher allocate without bound. Aug 1
# and Aug 6 2026 each wedged the VM this way; one instance ran 9h20m at 6.3 GB.
#
# CRITICAL IMPLEMENTATION DETAIL (verified on this box):
#   /proc/<pid>/comm  == "claude"   (comm follows the executable, not argv[0])
#   argv[0]           == "ugrep"    (set by `exec -a`)
# So this MUST match on argv[0]. Matching on the process *name* would either
# miss every runaway or, worse, match every legitimate Claude session.
RUNAWAY_ARGV0 = {"ugrep", "ug", "grep", "egrep", "fgrep", "rg", "ag", "ack"}
# Env-overridable so thresholds can be tuned (or driven down for a live drill)
# without editing and redeploying the guard.
RUNAWAY_RSS_GB = float(os.environ.get("GUARD_RUNAWAY_RSS_GB", 2.0))      # no sane grep needs 2 GB resident
RUNAWAY_MIN_AGE_S = float(os.environ.get("GUARD_RUNAWAY_MIN_AGE_S", 60))  # don't race a just-started legitimate search
RUNAWAY_MAX_AGE_S = float(os.environ.get("GUARD_RUNAWAY_MAX_AGE_S", 900))  # 15 min ...
RUNAWAY_MAX_CPU_S = float(os.environ.get("GUARD_RUNAWAY_MAX_CPU_S", 300))  # ... AND burning CPU => spinning, not blocked on I/O

# --------------------------------------------------------------------------- #
# Generic slice-hog ceiling  (added 2026-08-24 after [SLICE-THRASH-MONGO-LIST])
# --------------------------------------------------------------------------- #
# reap_runaway_search() above matches on argv[0] against RUNAWAY_ARGV0, because
# it was written for the Aug 1 / Aug 6 ugrep lockups. On 2026-08-24 the SAME
# failure mode (page cache -> 0, whole slice in D-state on
# mem_cgroup_handle_over_hi, workbench dead for 70 min) was produced by a
# process that is not a search at all: an ad-hoc
#     python3 - <<PY ... list(col.find({...}, {... "valuation_data": 1 ...})) ... PY
# from an agent session, which materialised a full Mongo cursor to 9.24 GB RSS.
# It had a live parent (claude -> bash -> python3) so reap_orphans() skipped it,
# and argv[0] was "python3" so reap_runaway_search() skipped it. The guard
# detected the thrash and Telegrammed for ~70 minutes with no action available.
#
# This reaper is deliberately process-AGNOSTIC: any single process in the shared
# Claude slice above the ceiling is killed, whatever it is. The next runaway will
# be `node` or `duckdb` or something we have not thought of, and an argv[0]
# allowlist can only ever chase the last incident.
#
# SAFETY — why this cannot kill anything important. Membership is read from the
# code-server.service cgroup, which contains ONLY Claude Code sessions and what
# they spawn. Verified on this box 2026-08-24: sshd sessions live in
# user.slice/user-<uid>.slice/session-N.scope, and mongod / fields-orchestrator
# in their own system.slice units — none can appear in cgroup.procs here. The
# slice is flat (no nested cgroups), so a single read of cgroup.procs is total.
SLICE_CGROUP = Path("/sys/fs/cgroup/system.slice/code-server.service")
# Steady-state peak in this slice is ~650 MB (the extensionHost), measured
# 2026-08-24 across 42 procs, and the worst legitimate `claude` on record is
# 3.8 GB (2026-07-27). 6 GB is far above both and still well under the 9 GB
# MemoryHigh, so a hog is killed BEFORE it can push the slice into the
# throttle band where it starves its siblings.
SLICE_HOG_RSS_GB = float(os.environ.get("GUARD_SLICE_HOG_RSS_GB", 6.0))
# Once the slice is confirmed thrashing, the damage is already happening and a
# lower ceiling is justified — still comfortably above any normal session.
SLICE_HOG_THRASH_RSS_GB = float(os.environ.get("GUARD_SLICE_HOG_THRASH_RSS_GB", 4.0))
SLICE_HOG_MIN_AGE_S = float(os.environ.get("GUARD_SLICE_HOG_MIN_AGE_S", 60))
# Structural processes: killing one of these does not free a session, it takes
# down the workbench (and every other session) with it. A hog here is a genuine
# leak in code-server itself and needs a human, so we alert instead of killing.
SLICE_STRUCTURAL = ("out/node/entry", "--type=extensionHost", "--type=ptyHost")

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


def alert_allowed(state: dict, category: str, cooldown_h: float = None) -> bool:
    last = state.get("last_alert", {}).get(category)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    hours = ALERT_COOLDOWN_H if cooldown_h is None else cooldown_h
    return datetime.now(timezone.utc) - last_dt >= timedelta(hours=hours)


def mark_alerted(state: dict, category: str, dry: bool = False):
    """Record that `category` alerted, starting its cooldown.

    ⚠ Must be a no-op on a dry run. `send_telegram` returns early when dry, so
    marking anyway starts a cooldown for a message nobody received — a
    diagnostic run then silently suppresses the next REAL alert. Observed
    2026-08-15: a --dry-run consumed the disk_ineffective budget and the live
    run 67s later stayed silent at 94% disk.
    """
    if dry:
        return
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


def reap_runaway_search(dry: bool) -> list:
    """Kill runaway grep/ugrep-family processes, on EVERY pass.

    Deliberately different from reap_orphans() in two ways, both of which are
    why the Aug 1 / Aug 6 2026 lockups went unhandled through hundreds of guard
    passes:

      1. It does NOT require PPID==1. The runaway's parent was a live Claude
         session the whole time, so the orphan reaper skipped it ~370 times.
      2. It is NOT gated on system-wide MEM_CRIT_PCT. The code-server cgroup cap
         confined the damage to that slice, so system memory sat near 71% while
         code-server suffocated and the root disk saturated on cache misses.

    A search process is killed if EITHER:
      * RSS > RUNAWAY_RSS_GB and age > RUNAWAY_MIN_AGE_S   (fast blowup), or
      * age > RUNAWAY_MAX_AGE_S and CPU time > RUNAWAY_MAX_CPU_S
        (slow burn -- catches a runaway before it reaches the RSS ceiling).
    """
    import psutil
    actions = []
    for p in psutil.process_iter(["pid", "cmdline", "memory_info", "create_time"]):
        try:
            cmdline = p.info["cmdline"] or []
            if not cmdline:
                continue
            # argv[0], not comm -- see RUNAWAY_ARGV0 note above.
            if os.path.basename(cmdline[0]) not in RUNAWAY_ARGV0:
                continue

            rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
            rss_gb = rss / 1e9
            age_s = time.time() - p.info["create_time"]
            try:
                cpu_s = sum(p.cpu_times()[:2])  # user + system
            except Exception:
                cpu_s = 0.0

            blown = rss_gb > RUNAWAY_RSS_GB and age_s > RUNAWAY_MIN_AGE_S
            stuck = age_s > RUNAWAY_MAX_AGE_S and cpu_s > RUNAWAY_MAX_CPU_S
            if not (blown or stuck):
                continue

            reason = "rss" if blown else "runtime"
            snippet = " ".join(cmdline)[:160]
            if not dry:
                # A runaway is spinning inside the matcher and will not service
                # SIGTERM promptly -- give it a moment, then SIGKILL.
                try:
                    os.kill(p.info["pid"], signal.SIGTERM)
                    time.sleep(1.0)
                    if psutil.pid_exists(p.info["pid"]):
                        os.kill(p.info["pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass
            actions.append(
                f"reap_runaway_search[{reason}] pid={p.info['pid']} "
                f"rss={rss_gb:.2f}GB age={int(age_s)}s cpu={int(cpu_s)}s :: {snippet}"
            )
        except Exception:
            continue
    return actions


def slice_pids() -> list:
    """PIDs in the shared Claude cgroup. Empty list if the cgroup is absent."""
    try:
        raw = (SLICE_CGROUP / "cgroup.procs").read_text().split()
    except Exception:
        return []
    out = []
    for tok in raw:
        try:
            out.append(int(tok))
        except ValueError:
            continue
    return out


def reap_slice_hog(dry: bool, thrashing: bool = False) -> list:
    """Kill any single process in the Claude slice above the RSS ceiling.

    Process-agnostic by design — see the SLICE_* block above for why an argv[0]
    allowlist (reap_runaway_search) structurally cannot catch the general case.

    Scoped to SLICE_CGROUP membership, which is what makes it safe: sshd, mongod
    and fields-orchestrator are in different cgroups and can never be candidates.

    Structural code-server processes are reported, never killed — taking those
    down would destroy every session to save one.
    """
    import psutil
    actions = []
    ceiling = SLICE_HOG_THRASH_RSS_GB if thrashing else SLICE_HOG_RSS_GB
    for pid in slice_pids():
        try:
            p = psutil.Process(pid)
            rss_gb = p.memory_info().rss / 1e9
            if rss_gb <= ceiling:
                continue
            age_s = time.time() - p.create_time()
            if age_s <= SLICE_HOG_MIN_AGE_S:
                continue

            cmdline = " ".join(p.cmdline() or [])
            snippet = cmdline[:160] or p.name()

            if any(tok in cmdline for tok in SLICE_STRUCTURAL):
                actions.append(
                    f"slice_hog_structural[NOT killed] pid={pid} "
                    f"rss={rss_gb:.2f}GB age={int(age_s)}s :: {snippet}"
                )
                continue

            if not dry:
                # A process this large is usually deep in an allocation and slow
                # to service SIGTERM — give it a moment, then SIGKILL.
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(1.0)
                    if psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            actions.append(
                f"reap_slice_hog[{'thrash' if thrashing else 'rss'}] pid={pid} "
                f"rss={rss_gb:.2f}GB age={int(age_s)}s ceiling={ceiling}GB :: {snippet}"
            )
        except Exception:
            continue
    return actions


def cgroup_pressure(slice_name: str = "code-server.service") -> dict:
    """Per-cgroup memory health for the slice all Claude sessions share.

    System-wide mem_pct is blind to a cgroup suffocating under its own cap --
    the exact blind spot that let the ugrep runaway thrash the root disk for
    9 hours while free(1) looked fine. The signature is anon high / file ~0
    with workingset_refault_file climbing: the slice has evicted all its page
    cache, so every read goes back to disk.
    """
    base = Path("/sys/fs/cgroup/system.slice") / slice_name
    out = {}
    try:
        stat = {}
        for line in (base / "memory.stat").read_text().splitlines():
            k, _, v = line.partition(" ")
            try:
                stat[k] = int(v)
            except ValueError:
                continue
        cur = int((base / "memory.current").read_text().strip())
        out = {
            "anon_gb": round(stat.get("anon", 0) / 1e9, 2),
            "file_gb": round(stat.get("file", 0) / 1e9, 2),
            "refault_file": stat.get("workingset_refault_file", 0),
            "current_gb": round(cur / 1e9, 2),
        }
        try:
            mx = (base / "memory.max").read_text().strip()
            out["max_gb"] = None if mx == "max" else round(int(mx) / 1e9, 2)
        except Exception:
            out["max_gb"] = None
        # Thrashing: cache collapsed to near-zero while anon dominates.
        out["thrashing"] = (
            out["anon_gb"] > 3.0
            and out["file_gb"] < 0.20
            and (out["max_gb"] is None or out["current_gb"] > 0.85 * out["max_gb"])
        )
    except Exception:
        return {}
    return out


def workbench_healthy() -> dict:
    """Probe code-server the way a browser experiences it.

    VERIFICATION TRAP (cost us a false all-clear on 2026-08-06): a bare
        curl http://127.0.0.1:8080/
    returns 302 in ~27 ms even when the workbench is completely wedged, because
    that redirect handler never touches the extension host. `systemctl is-active`
    is equally useless — the unit stays "active" throughout. Only a followed
    request to /healthz exercises enough of the stack to tell the truth.
    """
    try:
        out = subprocess.run(
            ["curl", "-sL", "-m", "30", "-o", "/dev/null",
             "-w", "%{http_code} %{time_total}", "http://127.0.0.1:8080/healthz"],
            capture_output=True, text=True, timeout=40,
        ).stdout.strip().split()
        code = int(out[0]) if out else 0
        secs = float(out[1]) if len(out) > 1 else -1.0
        return {"code": code, "secs": round(secs, 2), "ok": code == 200}
    except Exception as e:
        return {"code": 0, "secs": -1.0, "ok": False, "error": str(e)[:120]}


def _run(cmd: list, dry: bool):
    vlog(f"{'DRY ' if dry else ''}run: {' '.join(cmd)}")
    if dry:
        return
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        vlog(f"cmd failed {cmd}: {e}")


def disk_cleanup(aggressive: bool, dry: bool) -> tuple:
    """Reclaim disk. `aggressive` when past DISK_CRIT_PCT.

    Returns (actions, bytes_freed). ⚠ Report the bytes, not the fact that it
    ran: every target below is a *cache or log*, so when the growth is anywhere
    else (an artifacts/ or scratch dir) this function is structurally incapable
    of helping and will still happily report a list of actions it performed.
    The caller must assert on the outcome. See Rule 7b.
    """
    import shutil as _shutil
    before = _shutil.disk_usage("/").free
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
    # 5. allowlisted scratch dirs (see SCRATCH_SWEEP — do NOT widen this)
    for target, age_days in SCRATCH_SWEEP:
        if not target.is_dir():
            continue
        cutoff = time.time() - age_days * 86400
        n = 0
        for entry in target.iterdir():
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue  # too new — may be a render in flight
                if not dry:
                    if entry.is_dir():
                        subprocess.run(["rm", "-rf", str(entry)], timeout=60)
                    else:
                        entry.unlink()
                n += 1
            except Exception:
                continue
        if n:
            actions.append(f"swept {n} from {target.name} (>{age_days}d)")
    freed = max(0, _shutil.disk_usage("/").free - before)
    actions.append(f"reclaimed {freed / 1e6:.0f}MB")
    return actions, freed


# --------------------------------------------------------------------------- #
# Alerting + audit
# --------------------------------------------------------------------------- #
def top_growth_dirs(limit: int = 5) -> list:
    """Largest directories on /, to name the culprit in an alert.

    ⚠ Deliberately NOT called on a routine pass. `du` over /home/fields is
    itself heavy I/O, and the guard runs every 90s on a box that is by
    definition already under pressure — scanning every pass would make the
    problem worse. Only the ineffective-cleanup alert path calls this.

    `-x` keeps it on the root filesystem (so /data/blobs, a separate 738G
    device, is not walked). Depth 2 is enough to point at a directory a human
    can act on without walking millions of inodes.
    """
    found = []
    for root in GROWTH_SCAN_ROOTS:
        if not os.path.isdir(root):
            continue
        try:
            out = subprocess.run(
                ["du", "-x", "--block-size=1M", "--max-depth=2", root],
                capture_output=True, text=True, timeout=60,
            )
            for line in out.stdout.splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                try:
                    mb = int(parts[0])
                except ValueError:
                    continue
                if parts[1].rstrip("/") != root.rstrip("/"):
                    found.append((mb, parts[1]))
        except Exception as e:
            vlog(f"growth scan failed for {root}: {e}")
    found.sort(reverse=True)
    # Drop a parent when a listed child already accounts for most of it —
    # "24.8G Fields_Orchestrator / 19.7G Fields_Orchestrator/artifacts" spends
    # two of five lines saying one thing. Keep the deeper path: it is the one
    # someone can actually act on.
    kept = []
    for mb, path in found:
        redundant = any(
            child.startswith(path.rstrip("/") + "/") and child_mb >= 0.7 * mb
            for child_mb, child in found
        )
        if not redundant:
            kept.append((mb, path))
        if len(kept) >= limit:
            break
    return kept


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

    # --- always: per-cgroup pressure on the shared Claude slice ---
    # Read BEFORE the reapers (moved 2026-08-24): reap_slice_hog drops to a lower
    # ceiling once the slice is confirmed thrashing, so it needs this first.
    cg = cgroup_pressure()
    if cg:
        m["cgroup_code_server"] = cg  # carried into the audit record
        vlog(f"code-server cgroup: {cg}")
    thrashing = bool(cg.get("thrashing")) if cg else False

    # --- always: runaway search-process ceiling (NOT gated on mem_pct) ---
    # This must run every pass regardless of system memory, because a cgroup-
    # confined runaway never moves the system-wide number. See the Aug 2026
    # ugrep lockups. At the 90s timer cadence this bounds exposure to ~2 min.
    runaway = reap_runaway_search(dry)
    if runaway:
        level = "critical"
        actions += runaway
        m_r = get_metrics()
        if alert_allowed(state, "runaway"):
            send_telegram(
                "\U0001F6D1 *Runaway search process killed*\n"
                + "\n".join(f"  {a}" for a in runaway[:4])
                + f"\n\nmem {m_r['mem_pct']:.0f}%, load {m_r['load_1m']}. "
                  "Cause is almost always a bounded-repeat regex "
                  "(`\\{0,120\\}`) with -o -i over a long-line file — "
                  "ugrep allocates without bound. Use -F, or -P for PCRE.",
                dry)
            mark_alerted(state, "runaway", dry)

    # --- always: generic slice-hog ceiling (NOT gated on mem_pct, NOT on argv[0]) ---
    # The catch-all the argv[0] reaper above cannot be. See [SLICE-THRASH-MONGO-LIST]
    # 2026-08-24 — a 9.24GB `python3 -` Mongo list() wedged the workbench for 70 min
    # while both existing reapers skipped it.
    hogs = reap_slice_hog(dry, thrashing)
    if hogs:
        killed = [a for a in hogs if a.startswith("reap_slice_hog")]
        level = "critical"
        actions += hogs
        m_h = get_metrics()
        if alert_allowed(state, "slice_hog"):
            if killed:
                send_telegram(
                    "\U0001F6D1 *Runaway process killed in Claude slice*\n"
                    + "\n".join(f"  {a}" for a in killed[:4])
                    + f"\n\nmem {m_h['mem_pct']:.0f}%, load {m_h['load_1m']}. "
                      "Killed before it could throttle the slice and take the "
                      "workbench down with it. Usual cause is an unbounded "
                      "materialisation — `list(col.find(...))` over a big "
                      "projection. Iterate the cursor or project fewer fields.",
                    dry)
            else:
                send_telegram(
                    "\U0001F534 *code-server structural process is the hog*\n"
                    + "\n".join(f"  {a}" for a in hogs[:4])
                    + "\n\nNOT killed — that would take down every session. "
                      "This looks like a leak in code-server itself; needs a "
                      "human call on restarting the service.",
                    dry)
            mark_alerted(state, "slice_hog", dry)

    # --- cgroup thrashing (evaluated after the reapers, so the alert can say
    #     whether we already acted on it this pass) ---
    if cg and cg.get("thrashing"):
        level = "critical" if level == "ok" else level
        actions.append(
            f"cgroup_thrashing code-server anon={cg['anon_gb']}GB "
            f"file={cg['file_gb']}GB refaults={cg['refault_file']}"
        )
        if alert_allowed(state, "cgroup"):
            acted = " A runaway was killed this pass — expect recovery within ~2 min." if hogs else ""
            send_telegram(
                f"\U0001F534 *code-server cgroup thrashing*\n"
                f"anon {cg['anon_gb']}GB, page cache {cg['file_gb']}GB "
                f"(collapsed), refaults {cg['refault_file']}, "
                f"current {cg['current_gb']}/{cg['max_gb']}GB.\n"
                f"System memory looks fine but the Claude slice has evicted "
                f"all page cache — every read now hits disk. The workbench "
                f"will stop loading shortly. Check for a runaway process.{acted}",
                dry)
            mark_alerted(state, "cgroup", dry)

    # --- always: is the workbench actually usable? ---
    wb = workbench_healthy()
    m["workbench"] = wb
    vlog(f"workbench: {wb}")
    if not wb["ok"]:
        state["wb_bad_streak"] = state.get("wb_bad_streak", 0) + 1
    else:
        state["wb_bad_streak"] = 0
    if state.get("wb_bad_streak", 0) >= 2:  # ~3 min of a genuinely dead workbench
        level = "critical"
        actions.append(f"workbench_unhealthy {wb} streak={state['wb_bad_streak']}")
        if alert_allowed(state, "workbench"):
            send_telegram(
                f"\U0001F534 *code-server workbench not responding*\n"
                f"/healthz -> {wb['code']} after {wb['secs']}s, "
                f"{state['wb_bad_streak']} consecutive checks.\n"
                f"systemd still reports active — that means nothing here. "
                f"vm.fieldsestate.com.au is likely not loading.",
                dry)
            mark_alerted(state, "workbench", dry)

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
            mark_alerted(state, "mem", dry)
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
            mark_alerted(state, "mem", dry)

    # --- disk ---
    if m["disk_pct"] >= DISK_WARN_PCT:
        state["disk_high_streak"] = state.get("disk_high_streak", 0) + 1
        streak = state["disk_high_streak"]
        aggressive = m["disk_pct"] >= DISK_CRIT_PCT
        cleanup_actions, freed = disk_cleanup(aggressive, dry)
        actions += cleanup_actions
        # re-measure after cleanup
        m_after = get_metrics()
        free_gb = m_after["disk_total_gb"] - m_after["disk_used_gb"]
        actions.append(f"disk {m['disk_pct']:.0f}%->{m_after['disk_pct']:.0f}% after cleanup")
        if aggressive:
            level = "critical"
            still_critical = m_after["disk_pct"] >= DISK_CRIT_PCT
            ineffective = freed < CLEANUP_INEFFECTIVE_BYTES and still_critical
            if ineffective:
                # The routine message below says "auto-cleanup ran", which reads
                # as handled. It is not handled: cleanup only clears caches and
                # logs, so growth anywhere else is invisible to it. Say that
                # plainly, name the directories, and use a shorter cooldown so
                # this cannot be mistaken for the routine 3-hourly message.
                if alert_allowed(state, "disk_ineffective", INEFFECTIVE_COOLDOWN_H):
                    growth = top_growth_dirs()
                    lines = "\n".join(f"  {mb / 1024:.1f}G  {p}" for mb, p in growth) or "  (scan failed)"
                    send_telegram(
                        f"\U0001F534 *VM disk CRITICAL — cleanup is NOT working*\n"
                        f"{m_after['disk_pct']:.0f}% on / — *{free_gb:.1f}GB free* "
                        f"({m_after['disk_used_gb']}/{m_after['disk_total_gb']}GB).\n"
                        f"Auto-cleanup reclaimed only {freed / 1e6:.0f}MB this pass, and disk has been "
                        f"critical for {streak} consecutive checks. It only clears caches and logs, so "
                        f"whatever is growing is somewhere it cannot see.\n\n"
                        f"*Largest on /:*\n{lines}\n\n"
                        f"This needs a human — it will not resolve itself.",
                        dry)
                    mark_alerted(state, "disk_ineffective", dry)
            elif alert_allowed(state, "disk"):
                send_telegram(
                    f"\U0001F534 *VM disk CRITICAL* {m['disk_pct']:.0f}% on / "
                    f"({m['disk_used_gb']}/{m['disk_total_gb']}GB). Auto-cleanup freed "
                    f"{freed / 1e6:.0f}MB (now {m_after['disk_pct']:.0f}%, {free_gb:.1f}GB free).",
                    dry)
                mark_alerted(state, "disk", dry)
        else:
            # WARN band (DISK_WARN_PCT .. DISK_CRIT_PCT). This branch used to do
            # nothing but run cleanup and leave level="ok" — see the note on
            # INEFFECTIVE_WARN_COOLDOWN_H. A disk that is high AND not responding
            # to cleanup is the same problem at 90% as at 92%; the only
            # difference is urgency, so it gets the same diagnosis (name the
            # directories) at a calmer cadence.
            level = "warn" if level == "ok" else level
            still_high = m_after["disk_pct"] >= DISK_WARN_PCT
            if (freed < CLEANUP_INEFFECTIVE_BYTES and still_high
                    and streak >= SUSTAIN_N
                    and alert_allowed(state, "disk_ineffective_warn",
                                      INEFFECTIVE_WARN_COOLDOWN_H)):
                growth = top_growth_dirs()
                lines = "\n".join(f"  {mb / 1024:.1f}G  {p}" for mb, p in growth) or "  (scan failed)"
                send_telegram(
                    f"\U0001F7E0 *VM disk high — cleanup is not reclaiming*\n"
                    f"{m_after['disk_pct']:.0f}% on / — *{free_gb:.1f}GB free* "
                    f"({m_after['disk_used_gb']}/{m_after['disk_total_gb']}GB).\n"
                    f"Auto-cleanup freed only {freed / 1e6:.0f}MB, and / has been above "
                    f"{DISK_WARN_PCT:.0f}% for {streak} consecutive checks. Not critical yet "
                    f"(alerts at {DISK_CRIT_PCT:.0f}%), but it is not trending back down "
                    f"on its own and cleanup only touches caches and logs.\n\n"
                    f"*Largest on /:*\n{lines}\n\n"
                    f"Worth a look before it becomes urgent.",
                    dry)
                mark_alerted(state, "disk_ineffective_warn", dry)
    else:
        state["disk_high_streak"] = 0

    save_state(state)
    if actions:
        log(f"level={level} actions={actions}")
    else:
        vlog("level=ok no actions")
    audit(m, actions, level)

    # --- Rule 7: the guard must not be able to die silently itself ---
    # This is the box's last line of defence; before 2026-08-06 it had no
    # heartbeat at all, so a dead guard would have been invisible. Reported on
    # every pass (dry-runs excluded so a manual diagnose doesn't fake a beat).
    # cadence 1h against a 90s timer => STALE only after a real outage.
    # Throttled: the timer fires every 90s but a 1h cadence only needs a beat
    # every ~10 min, so this costs ~144 Cosmos upserts/day instead of ~960.
    # Anything non-OK always beats immediately.
    last_beat = state.get("last_heartbeat_ts", 0)
    beat_due = (time.time() - last_beat) > 600 or level != "ok" or bool(actions)
    if not dry and beat_due:
        try:
            sys.path.insert(0, str(BASE_DIR / "scripts"))
            from job_status import record_job_result
            record_job_result(
                "resource_guard", "error" if level == "critical" else "success",
                detail=(f"level={level} mem={m['mem_pct']:.0f}% disk={m['disk_pct']:.0f}% "
                        f"wb={wb['code']}" + (f" actions={len(actions)}" if actions else "")),
                cadence_hours=1, title="VM Resource Guard",
                metrics={"mem_pct": m["mem_pct"], "disk_pct": m["disk_pct"],
                         "workbench_code": wb["code"], "actions": len(actions),
                         "cgroup": cg or {}},
            )
            state["last_heartbeat_ts"] = time.time()
            save_state(state)
        except Exception as e:
            vlog(f"heartbeat write failed: {e}")


if __name__ == "__main__":
    main()
