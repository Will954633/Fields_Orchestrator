#!/usr/bin/env bash
# Rebuild the homes that failed (or built degraded) during the 2026-08-05 sweep.
#
# The sweep process loaded fact_bundle / inline_features BEFORE the two fixes
# landed ([OFFMARKET-NULL-DISTANCE-BUILD-ABORT], [PVD-CLADDING-UNHASHABLE]), so
# its own run could not benefit from them. This re-runs just the affected homes
# against the fixed modules.
#
# MUST run only AFTER the sweep exits — otherwise the sweep reaches these homes
# later with the old module still loaded and re-breaks them.
set -uo pipefail
cd "$(dirname "$0")"
LOG=/home/fields/Fields_Orchestrator/logs/reachable_rebuild_all_20260805.log

if pgrep -f "offmarket_discovery_nightly.py --reachable --rebuild-all" >/dev/null; then
  echo "REFUSING: the sweep is still running. Wait for it to exit." >&2
  exit 1
fi

source /home/fields/venv/bin/activate 2>/dev/null
set -a; source /home/fields/Fields_Orchestrator/.env; set +a

# Failed slugs from the sweep log, plus the one home degraded by the cladding bug.
mapfile -t SLUGS < <(grep -oP '✗ \[main\] \K[a-z0-9-]+' "$LOG" | sort -u)
SLUGS+=("248-easthill-drive-robina")

echo "repairing ${#SLUGS[@]} home(s)"
ok=0; bad=0
for s in "${SLUGS[@]}"; do
  sub=$(python3 - "$s" <<'PY'
import sys, re
s = sys.argv[1]
for k in ("robina", "varsity-lakes", "burleigh-waters"):
    if s.endswith("-" + k) or re.search(r'-' + k + r'-\d+$', s):
        print(k.replace("-", "_")); break
else:
    print("")
PY
)
  if python3 offmarket_discovery_build.py --slug "$s" ${sub:+--suburb "$sub"} >/dev/null 2>&1; then
    echo "  ok  $s"; ok=$((ok+1))
  else
    echo "  FAIL $s"; bad=$((bad+1))
  fi
done
echo "repaired=$ok failed=$bad"
