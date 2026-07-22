#!/bin/bash
# Brain 3 (internal ops) NIGHTLY incremental refresh.
# delta-ingest (only new/changed source items) -> annotate ONLY what's new (cheap, OpenRouter) ->
# rebuild graph (dedupe supersedes changed content under its stable id; tombstones drop removed
# sources) -> freshness record -> Telegram only if something actually changed.
# Safe to run every night indefinitely: unchanged content costs ~0 — skipped at ingest, annotate
# no-ops on an empty todo list, graph rebuild is a few seconds of pure Python.
export PATH=/usr/bin:/usr/local/bin:$PATH
cd /home/fields/Fields_Orchestrator
B=/home/fields/brain3_ops
exec 9>"$B/.nightly.lock"
flock -n 9 || exit 0

STRIP="env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_SSE_PORT"
set -a && . /home/fields/Fields_Orchestrator/.env && set +a

BEFORE=$(wc -l < "$B/annotations_ops.jsonl" 2>/dev/null || echo 0)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$TS ===== nightly refresh start =====" >> "$B/nightly.log"

$STRIP python3 scripts/samantha/brain3_ops_ingest.py --delta --emit >> "$B/nightly.log" 2>&1
$STRIP python3 scripts/samantha/brain3_annotate.py --pool ops --base "$B" >> "$B/nightly.log" 2>&1
$STRIP python3 scripts/samantha/brain1_graph.py \
  --in "$B/annotations_ops.jsonl" --outdir "$B" --dedupe --tombstones "$B/tombstones.json" >> "$B/nightly.log" 2>&1

AFTER=$(wc -l < "$B/annotations_ops.jsonl" 2>/dev/null || echo 0)
NEW=$((AFTER - BEFORE))
TS2=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python3 -c "import json; json.dump({'last_run': '$TS2', 'new_or_updated_records': $NEW, 'total_annotation_records': $AFTER}, open('$B/freshness.json', 'w'), indent=2)"
echo "$TS2 nightly refresh done: +$NEW annotation record(s) (new units + updates), $AFTER total" >> "$B/nightly.log"

if [ "$NEW" -gt 0 ]; then
  /home/fields/venv/bin/python3 /home/fields/Fields_Orchestrator/scripts/telegram_notify.py \
    "🧠 Brain 3 nightly refresh: +$NEW new/updated unit(s) folded in (fix-logs, CEO memory, articles, decisions, focus docs). Total records: $AFTER. Graph rebuilt." \
    >> "$B/nightly.log" 2>&1
fi
