# VM Resource Safety Layer

Added **2026-07-27** after `fields-orchestrator-vm` OOM-cascaded and hung so hard that
sshd and every service died — recovery required an external `gcloud compute instances
reset` from Will's laptop. See `logs/fix-history/2026-07-27.md` (`[VM-WEDGE-PREVENTION]`).

## Root cause
On the 8 GB `e2-standard-2`, Claude Code / code-server sessions accumulate memory (one
`claude` process reached 3.8 GB) on top of scraper Chrome, exhausting RAM. The OOM killer
cascaded and took the whole guest down. The old on-VM `watchdog.py` (60-min, Chrome-only)
couldn't help — and once the box wedged it died with it.

## Three layers

**Layer 1 — Prevent (on-VM).** In this folder.
- Memory caps via systemd drop-ins. Crucially, **all Claude Code sessions share the
  `code-server.service` cgroup**, so its `MemoryMax=5G` bounds the entire session blast
  radius; if exceeded the kernel kills a *session*, not mongod/the pipeline.
- `OOMScoreAdjust`: mongod `-800`, orchestrator `-500` (protected); sessions `+500`,
  ollama `+300`, runner `+400` (sacrificed first).
- Swap raised 2 GB → 4 GB.
- `fields-resource-guard.timer` runs `scripts/resource_guard.py` every 90 s.

**Layer 3 — Early warning (on-VM).** In `resource_guard.py`: Telegrams Will when memory
or disk *trend* toward the cliff, while the box is still reachable.

**Layer 2 — Detect + recover (off-VM).** In `../../cloud-watcher/`. A GCP Cloud Function
(Scheduler every 3 min) reads the `vm_metrics` heartbeat + TCP-probes ports 22/443; on a
confirmed wedge it Telegrams Will with a one-tap reset (alert-first — never automatic).
Deploy per `cloud-watcher/DEPLOY.md` (needs Will's GCP creds; the VM SA is read-only).

## Reinstall (e.g. after a rebuild)
```bash
bash deploy/vm-resource-safety/install.sh
```

## Verify
```bash
systemctl list-timers fields-resource-guard.timer
systemctl show code-server -p MemoryMax          # 5368709120
cat /proc/$(pgrep -x mongod)/oom_score_adj        # -800
free -h                                           # swap 4.0Gi
python3 scripts/resource_guard.py --dry-run -v
```
