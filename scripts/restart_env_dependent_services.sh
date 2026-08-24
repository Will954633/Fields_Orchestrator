#!/usr/bin/env bash
# restart_env_dependent_services.sh — REC-ops-004 durable fix (2026-08-24).
#
# WHY: systemd reads EnvironmentFile= once, at unit start. Rotating a secret in
# .env therefore does NOT reach any already-running daemon — it keeps holding the
# dead credential until restarted. This silently kept Domain.com.au ingestion dead
# for 3 nights AFTER the Bright Data key was rotated on 2026-08-13. See fix-history
# [ROTATED-SECRET-NOT-DELIVERED] and REC-ops-004.
#
# MECHANISM: a hash-diff check, run every minute by fields-env-watch.timer. We tried
# a systemd .path unit first; its inotify watch fires reliably on in-place writes but
# NOT on cross-dir atomic replace (temp+mv), which is exactly how some rotations write
# the file — so a path unit would silently miss the case it exists to catch. A stored
# hash compared each minute catches EVERY write pattern deterministically, at the cost
# of up to ~60s latency (rotations are rare; that is fine).
#
# Modes:
#   --if-changed   restart only when .env's hash differs from the stored hash
#                  (used by the timer). No change -> silent no-op.
#   (no arg)       always restart now (manual use / first seed).
set -uo pipefail

ENV_FILE="/home/fields/Fields_Orchestrator/.env"
STATE="/home/fields/Fields_Orchestrator/logs/.env-watch.hash"
LOG="/home/fields/Fields_Orchestrator/logs/env-watch-restart.log"
mkdir -p "$(dirname "$LOG")"
ts() { date '+%Y-%m-%d %H:%M:%S %Z'; }

cur_hash="$(sha256sum "$ENV_FILE" 2>/dev/null | cut -d' ' -f1)"
if [ -z "$cur_hash" ]; then
  echo "$(ts) | ERROR: cannot read $ENV_FILE" >> "$LOG"; exit 1
fi

if [ "${1:-}" = "--if-changed" ]; then
  old_hash="$(cat "$STATE" 2>/dev/null || true)"
  if [ "$cur_hash" = "$old_hash" ]; then
    exit 0            # unchanged — silent no-op (the common case, every minute)
  fi
  # First run ever (no state file): record the hash but do NOT restart — we do not
  # want a spurious restart the first time the timer sees an already-stable file.
  if [ -z "$old_hash" ]; then
    echo "$cur_hash" > "$STATE"
    echo "$(ts) | seeded hash baseline (no restart on first observation)" >> "$LOG"
    exit 0
  fi
  echo "$(ts) | .env hash changed ($old_hash -> $cur_hash) — re-delivering to services" >> "$LOG"
fi

# Discover the target set dynamically — do not hardcode, so adding a service that
# reads this .env is automatically covered with no edit here.
mapfile -t UNITS < <(
  for f in /etc/systemd/system/fields-*.service; do
    grep -q "Fields_Orchestrator/.env" "$f" 2>/dev/null || continue
    svc="$(basename "$f")"
    [ "$(systemctl is-active "$svc" 2>/dev/null)" = "active" ] && echo "$svc"
  done
)

if [ "${#UNITS[@]}" -eq 0 ]; then
  echo "$(ts) | no active .env-dependent services found — nothing to restart" >> "$LOG"
  echo "$cur_hash" > "$STATE"
  exit 0
fi

echo "$(ts) | restarting ${#UNITS[@]} service(s): ${UNITS[*]}" >> "$LOG"
rc=0
for svc in "${UNITS[@]}"; do
  if systemctl restart "$svc" 2>>"$LOG"; then
    sleep 1
    state="$(systemctl is-active "$svc" 2>/dev/null)"
    echo "$(ts) |   $svc -> $state" >> "$LOG"
    [ "$state" = "active" ] || rc=1
  else
    echo "$(ts) |   $svc -> RESTART FAILED" >> "$LOG"
    rc=1
  fi
done
# Only advance the stored hash on a fully clean restart, so a partial failure is
# retried next minute instead of being marked done (Rule 7b: never advance a
# watermark on a failed run).
if [ "$rc" -eq 0 ]; then
  echo "$cur_hash" > "$STATE"
fi
echo "$(ts) | done (rc=$rc)" >> "$LOG"
exit "$rc"
