#!/bin/bash
# Save every downloaded study PDF into the Fields Knowledge Base (category=financial:
# academic RE-economics lives there; kb_ingest classifies academic papers PUBLIC-safe).
cd /home/fields/Fields_Orchestrator
source /home/fields/venv/bin/activate 2>/dev/null
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
DIR=14_Articles/Market_Research/downturn_studies/pdfs
TAGS="housing-downturn,leading-indicators,australia,academic-study,market-correction,early-warning"
OK=0; FAIL=0
: > 14_Articles/Market_Research/downturn_studies/kb_save_failures.txt
for f in "$DIR"/*.pdf; do
  [ -e "$f" ] || continue
  stem=$(basename "$f" .pdf)
  if ls /home/fields/knowledge-base/financial/ 2>/dev/null | grep -qF "$stem"; then
    echo "=== SKIP (already in KB): $stem ==="; OK=$((OK+1)); continue
  fi
  echo "=== saving: $(basename "$f") ==="
  if python3 scripts/save-to-kb.py --file "$f" --category financial --tags "$TAGS"; then
    OK=$((OK+1))
  else
    echo "$f" >> 14_Articles/Market_Research/downturn_studies/kb_save_failures.txt
    FAIL=$((FAIL+1))
  fi
done
echo "----- KB save: OK=$OK FAIL=$FAIL -----"
