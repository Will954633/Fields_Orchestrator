# Operations Directory

Single source of truth for "where does this thing live, who owns it, how do I recover it." Mirrored to `Will954633/Fields_Orchestrator` on GitHub so it survives a VM loss.

## Files

| File | Type | Purpose |
|------|------|---------|
| [STATE.md](STATE.md) | **Auto** (nightly 02:50 AEST) | Live snapshot: services, disks, crons, backup freshness, mongod status |
| [infrastructure.md](infrastructure.md) | Manual | VMs, GCP project, DNS, certs, domains |
| [services.md](services.md) | Manual | Every `fields-*` systemd service: purpose, ports, logs, restart |
| [backups.md](backups.md) | Manual | What's backed up, where, how to restore. **Read this first when something is lost.** |
| [vendors.md](vendors.md) | Manual | Every paid/free vendor account: what it does, billing, where credentials live, cancellation path |

## Update Discipline

- **STATE.md is auto-generated.** Do not edit by hand — the nightly cron overwrites it. Look at it; if a number looks wrong, fix the underlying problem, not the file.
- **The other four are manual.** When you change infra, add a vendor, add a service, change a backup target — update the corresponding file in the same change. Same rigor as fix-history logging.
- **Pushed to GitHub nightly** by `scripts/refresh-ops-state.py` after STATE.md regenerates. If you edit a manual file mid-day and want it on GitHub immediately, run the script by hand: `python3 scripts/refresh-ops-state.py --push`.

## Recovery Use Case

If this VM is destroyed:
1. New VM, clone `Will954633/Fields_Orchestrator`
2. Read `00_Run_Commands/operations/backups.md` for restore procedures
3. Read `infrastructure.md` for what DNS/GCP/certs to recreate
4. Read `services.md` to know what to bring back up
5. Read `vendors.md` for billing/account contacts

This directory is your disaster runbook. Treat it accordingly.
