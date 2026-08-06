#!/usr/bin/env bash
# write_heartbeat.sh — re-upload a tiny liveness object to GCS every minute.
#
# The off-VM watchdog (cloud-watcher/) reads this object's last-updated time to tell
# whether the VM is alive. A wedged/OOM-hung VM stops running this cron, so the object
# goes stale within minutes and the watchdog alerts Will. GCS is used (not Cosmos)
# because Cosmos/Azure firewalls off GCP Cloud Function egress. Authenticated via the
# VM's gcloud creds (will.simpson), same as the daily blob-backup cron.
#
# 2026-08-06: this is now a LIVENESS+USABILITY signal, not just "cron still runs".
# The Aug 1 / Aug 6 ugrep lockups left the box in disk thrash with the workbench dead
# while nginx/443 and sshd/22 kept answering, so the watchdog's "stale heartbeat AND
# dead port" test never fired. We therefore refuse to publish a heartbeat when the
# workbench itself is not serving: staleness then means "this VM is not usable",
# which is the thing we actually care about.
#
# The probe MUST be /healthz followed through redirects. A bare request to / returns
# 302 in ~27 ms even when the box is completely wedged (that handler never touches the
# extension host), and `systemctl is-active code-server` stays "active" throughout —
# both produced a false all-clear on 2026-08-06.
#
# Fail-safe direction: a probe failure withholds the heartbeat, which can only ever
# cause an ALERT, never a silent all-clear. The off-VM watcher requires ~20 minutes of
# staleness (HARD_STALE_MIN) before it escalates, so a transient blip cannot page Will.
set -uo pipefail
BUCKET="${HEARTBEAT_BUCKET:-fields-vm-watchdog}"
OBJECT="${HEARTBEAT_OBJECT:-vm-heartbeat.txt}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/healthz}"
TMP="/tmp/vm-heartbeat.txt"

# On a connection failure curl still prints "000" AND exits non-zero, so overwrite
# rather than append — otherwise the log reads a confusing "000000".
code=$(curl -sL -m 20 -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null) || code=000
code="${code:-000}"
if [ "$code" != "200" ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) workbench unhealthy (/healthz -> $code) — heartbeat withheld"
  exit 0   # exit 0: this is a deliberate decision, not a cron failure to be retried
fi

date -u +%Y-%m-%dT%H:%M:%SZ > "$TMP"
gcloud storage cp "$TMP" "gs://${BUCKET}/${OBJECT}" --quiet >/dev/null 2>&1
