#!/bin/bash
# Egress attribution snapshotter — 24h diagnostic, one-shot (NOT a cron).
#
# Why this exists
# ---------------
# The June 2026 GCP invoice was 45% network egress (642 GiB, $167.72 ex-GST) and
# point-sampling with tcpdump kept landing in quiet windows — three separate
# captures showed ~0 while the daily average was ~20 GB/day. The traffic is
# bursty and tied to scheduled jobs, so it can only be attributed by sampling
# across a full day.
#
# What it records, every INTERVAL seconds:
#   1. iptables byte counters (installed separately) — cumulative + delta.
#      These are accounting rules with no target: they count and fall through,
#      so they cannot filter or alter traffic.
#   2. A short tcpdump of outbound :443, to name the destinations behind the
#      largest line. Short samples miss quiet windows individually but catch the
#      bursts across ~96 ticks.
#
# Output is CSV appended to disk, so a reboot loses only the counters (which
# reset) and not the history already captured.
#
# Rule 7 note: this is a one-shot diagnostic that exits after DURATION, not an
# ongoing process, so it carries no job_run heartbeat. If it is ever turned into
# a recurring job it MUST be wrapped per CLAUDE.md Rule 7 first.
#
# Usage:  sudo nohup setsid bash scripts/egress_attribution_snapshot.sh &

set -uo pipefail

INTERVAL="${INTERVAL:-900}"          # 15 minutes
DURATION="${DURATION:-86400}"        # 24 hours
CAP_SECONDS="${CAP_SECONDS:-20}"     # tcpdump window per tick
IFACE="${IFACE:-ens4}"
OUT_DIR="/home/fields/Fields_Orchestrator/logs"
COUNTERS_CSV="$OUT_DIR/egress_counters.csv"
DESTS_CSV="$OUT_DIR/egress_destinations.csv"

mkdir -p "$OUT_DIR"
[ -s "$COUNTERS_CSV" ] || echo "timestamp,label,cumulative_bytes,delta_bytes" >> "$COUNTERS_CSV"
[ -s "$DESTS_CSV" ]    || echo "timestamp,dest_ip,bytes_in_window,window_seconds" >> "$DESTS_CSV"

declare -A PREV

read_counters() {
    # Emit "label<TAB>bytes" for each acct: rule in the OUTPUT chain.
    iptables -L OUTPUT -v -n -x 2>/dev/null | awk '
        /acct:/ {
            for (i = 1; i <= NF; i++) if ($i ~ /^acct:/) { label = $i; break }
            if (label != "") printf "%s\t%s\n", label, $2
            label = ""
        }'
}

END_AT=$(( $(date +%s) + DURATION ))

while [ "$(date +%s)" -lt "$END_AT" ]; do
    TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    while IFS=$'\t' read -r label bytes; do
        [ -z "${label:-}" ] && continue
        prev="${PREV[$label]:-}"
        if [ -n "$prev" ] && [ "$bytes" -ge "$prev" ]; then
            delta=$(( bytes - prev ))
        else
            delta=""   # first tick, or counters reset (reboot / iptables flush)
        fi
        PREV[$label]="$bytes"
        echo "$TS,$label,$bytes,$delta" >> "$COUNTERS_CSV"
    done < <(read_counters)

    # Name the destinations behind outbound HTTPS. `|| true` so a capture
    # failure never kills the 24h run.
    # NOTE: with -q, tcpdump prints "tcp <bytes>" — NOT "length <bytes>".
    # Matching /length/ here silently matches only UDP lines and reports ~0,
    # which is exactly how an earlier hand-run capture produced a false
    # "egress is basically zero" reading. Verified against generated traffic.
    timeout $((CAP_SECONDS + 5)) tcpdump -i "$IFACE" -nn -q "tcp and dst port 443" 2>/dev/null \
      | awk -v ts="$TS" -v w="$CAP_SECONDS" '
            match($0, /IP (10\.152\.[0-9.]+)\.[0-9]+ > ([0-9.]+)\.443: tcp ([0-9]+)/, m) {
                bytes[m[2]] += m[3]
            }
            END { for (d in bytes) printf "%s,%s,%d,%d\n", ts, d, bytes[d], w }' \
      | sort -t, -k3 -rn | head -5 >> "$DESTS_CSV" || true

    sleep "$INTERVAL"
done

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ'),DONE,,"  >> "$COUNTERS_CSV"
