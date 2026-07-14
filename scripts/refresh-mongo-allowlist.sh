#!/bin/bash
# Refresh GCP firewall rule `allow-mongodb` from AWS published IP ranges.
#
# Purpose: mongod (port 27017) is exposed for Netlify Functions running on
# AWS Lambda in us-east-1. This script keeps the firewall allowlist in sync
# with the AWS-published EC2 ranges so new AWS subnets don't break Netlify
# and removed ranges don't keep exposing us.
#
# Behavior:
#   - Downloads https://ip-ranges.amazonaws.com/ip-ranges.json
#   - Extracts service=EC2 + region=us-east-1, collapses adjacent CIDRs
#   - If the resulting set differs from the current rule's sourceRanges,
#     updates the rule via gcloud (delete + recreate).
#   - Always preserves the static safety-net IPs in $EXTRA_RANGES.
#   - No-op when nothing has changed (idempotent).
#
# Scheduled via cron (see install instructions at bottom).
# History: created 2026-05-19 after VM crash post-mortem (P2.7-Phase-3).

set -euo pipefail

# Static extra ranges always included (sole-operator safety net).
# Add Will's home IP and any other emergency-access IPs here.
EXTRA_RANGES=(
    "60.240.77.229/32"   # Will home (Telstra AU)
)

RULE_NAME="allow-mongodb"
TARGET_TAG="fields-orchestrator"
AWS_URL="https://ip-ranges.amazonaws.com/ip-ranges.json"
TMP_JSON=$(mktemp /tmp/aws-ip-ranges.XXXXXX.json)
TMP_NEW=$(mktemp /tmp/mongo-allowlist-new.XXXXXX.txt)
TMP_CUR=$(mktemp /tmp/mongo-allowlist-cur.XXXXXX.txt)
trap 'rm -f "$TMP_JSON" "$TMP_NEW" "$TMP_CUR"' EXIT

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

log "Fetching AWS IP ranges..."
if ! curl -sS --max-time 30 "$AWS_URL" -o "$TMP_JSON"; then
    log "ERROR: AWS IP ranges fetch failed; aborting (current rule unchanged)"
    exit 1
fi

SYNC_TOKEN=$(/usr/bin/python3 -c "import json; print(json.load(open('$TMP_JSON'))['syncToken'])")
log "AWS syncToken: $SYNC_TOKEN"

# Extract + collapse EC2 us-east-1, append extras
/usr/bin/python3 - "$TMP_JSON" "$TMP_NEW" "${EXTRA_RANGES[@]}" <<'PY'
import json, ipaddress, sys
in_path, out_path = sys.argv[1], sys.argv[2]
extras = sys.argv[3:]
data = json.load(open(in_path))
ec2 = [p['ip_prefix'] for p in data['prefixes']
       if p['region'] == 'us-east-1' and p['service'] == 'EC2']
nets = [ipaddress.IPv4Network(p) for p in ec2]
collapsed = sorted(str(c) for c in ipaddress.collapse_addresses(nets))
combined = sorted(set(collapsed + extras))
if len(combined) > 256:
    print(f"ERROR: {len(combined)} ranges exceeds GCP firewall limit (256)", file=sys.stderr)
    sys.exit(2)
with open(out_path, 'w') as f:
    f.write('\n'.join(combined) + '\n')
print(f"New rule would have {len(combined)} source ranges")
PY

# Read current rule's sourceRanges. If the rule is missing (e.g. a prior
# delete+recreate deleted it but the create failed — as happened 2026-07-11
# during a transient billing outage), treat current as empty so the diff below
# registers a change and the rule gets created fresh (self-heal).
if CUR_JSON=$(gcloud compute firewall-rules describe "$RULE_NAME" --format=json 2>/dev/null); then
    printf '%s' "$CUR_JSON" \
        | /usr/bin/python3 -c "import json,sys; print('\n'.join(sorted(json.load(sys.stdin).get('sourceRanges', []))))" \
        > "$TMP_CUR"
else
    log "Rule $RULE_NAME not found — self-heal: will create it fresh."
    : > "$TMP_CUR"
fi

NEW_COUNT=$(wc -l < "$TMP_NEW")
CUR_COUNT=$(wc -l < "$TMP_CUR")
log "Current rule: $CUR_COUNT ranges"
log "Computed new: $NEW_COUNT ranges"

if cmp -s "$TMP_NEW" "$TMP_CUR"; then
    log "No change — rule already up to date."
    exit 0
fi

ADDED=$(comm -13 "$TMP_CUR" "$TMP_NEW" | wc -l)
REMOVED=$(comm -23 "$TMP_CUR" "$TMP_NEW" | wc -l)
log "Change detected: +$ADDED ranges, -$REMOVED ranges"

NEW_RANGES_CSV=$(tr '\n' ',' < "$TMP_NEW" | sed 's/,$//')

log "Recreating firewall rule $RULE_NAME..."
gcloud compute firewall-rules delete "$RULE_NAME" --quiet 2>&1 | tail -2 || true
gcloud compute firewall-rules create "$RULE_NAME" \
    --direction=INGRESS \
    --action=ALLOW \
    --rules=tcp:27017 \
    --target-tags="$TARGET_TAG" \
    --source-ranges="$NEW_RANGES_CSV" \
    --description="mongod allowlist (auto-refreshed). AWS us-east-1 EC2 + extras. syncToken=$SYNC_TOKEN updated $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    2>&1 | tail -3

log "Done."
