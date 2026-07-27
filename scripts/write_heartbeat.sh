#!/usr/bin/env bash
# write_heartbeat.sh — re-upload a tiny liveness object to GCS every minute.
#
# The off-VM watchdog (cloud-watcher/) reads this object's last-updated time to tell
# whether the VM is alive. A wedged/OOM-hung VM stops running this cron, so the object
# goes stale within minutes and the watchdog alerts Will. GCS is used (not Cosmos)
# because Cosmos/Azure firewalls off GCP Cloud Function egress. Authenticated via the
# VM's gcloud creds (will.simpson), same as the daily blob-backup cron.
set -euo pipefail
BUCKET="${HEARTBEAT_BUCKET:-fields-vm-watchdog}"
OBJECT="${HEARTBEAT_OBJECT:-vm-heartbeat.txt}"
TMP="/tmp/vm-heartbeat.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$TMP"
gcloud storage cp "$TMP" "gs://${BUCKET}/${OBJECT}" --quiet >/dev/null 2>&1
