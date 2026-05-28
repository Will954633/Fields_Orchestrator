# Systemd Services

All `fields-*` services on `fields-orchestrator-vm`. Manage with `sudo systemctl {status|start|stop|restart} <name>`. STATE.md has the live up/down view; this file documents what each one does.

| Service | Purpose | Port | Logs |
|---------|---------|------|------|
| `fields-orchestrator` | Nightly 20:30 AEST pipeline (30 processes) | — | `logs/orchestrator.log` + `logs/runs/<ts>/` |
| `fields-watchdog` | Self-healing watchdog over the orchestrator + restarts stuck steps | — | `journalctl -u fields-watchdog` |
| `fields-trigger-poller` | Polls `system_monitor.triggers` and runs ad-hoc requests | — | `journalctl -u fields-trigger-poller` |
| `fields-valuation-api` | On-demand valuation HTTP service | TBD | `journalctl -u fields-valuation-api` |
| `fields-valuation-poller` | Polls `system_monitor.valuation_requests` and dispatches | — | `journalctl -u fields-valuation-poller` |
| `fields-voice-agent` | Two-tier chat agent (Haiku router + Opus workers + SSE) | 8090 | `journalctl -u fields-voice-agent` |
| `fields-ceo-telegram` | Telegram bridge for CEO agent proposals | — | `journalctl -u fields-ceo-telegram` |
| `fields-builder-telegram` | Telegram bridge for builder agent | — | `journalctl -u fields-builder-telegram` |
| `fields-bridge-sync` | Inter-system sync bridge | — | `journalctl -u fields-bridge-sync` |
| `fields-ai-analysis-poller` | Polls and runs AI property editorial generation | — | `journalctl -u fields-ai-analysis-poller` |
| `fields-appraisal-poller` | Polls for appraisal V4 generation requests | — | `journalctl -u fields-appraisal-poller` |
| `fields-property-report-poller` | Polls for property report generation requests | — | `journalctl -u fields-property-report-poller` |
| `fields-tracking` | Tracking / analytics ingest service | TBD | `journalctl -u fields-tracking` |

## Adjacent services (not `fields-*`)

| Service | Purpose |
|---------|---------|
| `mongod` | Local MongoDB (replaced Cosmos DB 2026-05-28) — `mongodb://localhost:27017`, data at `/var/lib/mongodb` |
| `nginx` | Reverse proxy + static blob server. Configs: `/etc/nginx/sites-available/{blobs,fields-vm}` |
| `cron` (user `projects`) | Daily 03:00 GCS rsync — see [backups.md](backups.md) |

## Common Tasks

```bash
# Live snapshot of all fields-* services
systemctl list-units --state=active --type=service | grep fields-

# Tail recent activity for one service
journalctl -u fields-watchdog -n 200 --no-pager

# Restart everything (rare — only after major config change)
for s in $(systemctl list-units --state=active --type=service | grep -oE 'fields-[a-z-]+\.service'); do
  sudo systemctl restart "$s"
done
```

## TODO
- Fill in TBD ports
- Add restart-order dependency graph if any service depends on another being healthy first
