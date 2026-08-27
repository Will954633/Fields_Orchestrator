#!/usr/bin/env bash
# Waits for the out-of-place re-annotation to COMPLETE, then safely swaps the new
# annotations into the live corpus and rebuilds the Brain 1 graph.
# Conservative: aborts (leaving the live corpus untouched) unless every gate passes.
set -uo pipefail

REANNOT=/home/fields/brain1_reannot
B1=/home/fields/brain1_build
LOG=/home/fields/Fields_Orchestrator/scratchpad/brain1_dm/swap_and_rebuild.log
TS=$(date +%Y%m%d-%H%M)
say(){ echo "$(date -Is) $*" | tee -a "$LOG"; }

# 1) Wait for COMPLETE (max ~4h; deadline well before the 03:10 nightly).
say "watcher started; waiting for $REANNOT/COMPLETE"
for i in $(seq 1 480); do
  [ -f "$REANNOT/COMPLETE" ] && break
  sleep 30
done
if [ ! -f "$REANNOT/COMPLETE" ]; then
  say "ABORT: COMPLETE marker never appeared within deadline. Live corpus untouched."
  exit 1
fi

# 2) Gate: new annotations must hold ~all 3,084 original u#### units.
NEW="$REANNOT/annotations.jsonl"
NLINES=$(grep -c '"unit_id"' "$NEW" 2>/dev/null || echo 0)
NU=$(python3 - "$NEW" <<'PY'
import json,sys
n=0
for l in open(sys.argv[1],encoding='utf-8',errors='replace'):
    try:
        if json.loads(l).get('unit_id','').startswith('u'): n+=1
    except: pass
print(n)
PY
)
say "new annotations: $NLINES lines, $NU u#### units"
if [ "$NU" -lt 3000 ]; then
  say "ABORT: only $NU u#### units (<3000). Not swapping. Live corpus untouched."
  exit 1
fi
if [ -f "$REANNOT/failures.txt" ]; then
  say "NOTE: $(wc -l < "$REANNOT/failures.txt") batch(es) in failures.txt (per-unit fallback still recovers most)."
fi

# 3) Back up live annotations, then swap in the new file.
cp "$B1/annotations.jsonl" "$B1/annotations.jsonl.bak-preswap-$TS"
cp "$NEW" "$B1/annotations.jsonl"
say "swapped new annotations into $B1/annotations.jsonl (backup: annotations.jsonl.bak-preswap-$TS)"

# 4) Back up package + rebuild graph with the exact nightly source set (existing files only).
cp "$B1/package.json" "$B1/package.json.bak-preswap-$TS"
cd /home/fields/Fields_Orchestrator
CMD=(python3 scripts/samantha/brain1_graph.py --in "$B1/annotations.jsonl" --outdir "$B1" --dedupe)
MERGES=()
for p in /home/fields/brain3_build/annotations_public.jsonl \
         /home/fields/brain_drive/annotations_b1.jsonl \
         /home/fields/brain1_yt/annotations.jsonl \
         /home/fields/brain1_books/annotations.jsonl \
         /home/fields/brain1_build/Spotify/annotations.jsonl; do
  [ -f "$p" ] && MERGES+=("$p")
done
[ ${#MERGES[@]} -gt 0 ] && CMD+=(--merge "${MERGES[@]}")
[ -f /home/fields/brain_drive/tombstones_b1.json ] && CMD+=(--tombstones /home/fields/brain_drive/tombstones_b1.json)
say "rebuild: ${CMD[*]}"
"${CMD[@]}" >>"$LOG" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  say "REBUILD FAILED (rc=$RC). Restoring package.json from backup. annotations.jsonl already swapped (safe — nightly will rebuild)."
  cp "$B1/package.json.bak-preswap-$TS" "$B1/package.json"
  exit 1
fi

# 5) Report before/after.
say "DONE. graph_stats now:"
python3 - <<'PY' | tee -a "$LOG"
import json
s=json.load(open('/home/fields/brain1_build/graph_stats.json'))
print("  n_units:", s.get('n_units'))
bl=s.get('by_library',{})
for k in ('RealEstate_Gym','Sell It','Agent School'):
    print(f"  {k}: {bl.get(k)}")
PY
say "watcher finished OK"
