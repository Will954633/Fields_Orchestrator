#!/bin/bash
#
# run_monthly_market_precompute.sh — the whole 1st-of-month market-metrics rebuild, in order.
#
# WHY THIS EXISTS (2026-08-02, fix-history [UNION-MEDIANS-REVERTED-NIGHTLY]):
# These six steps used to be six separate cron lines whose correctness depended entirely on
# their 05:00→05:40 spacing and on nobody ever running one of them alone. Step 1 ends with a
# blind full-document `replace_one` on Gold_Coast.precomputed_indexed_prices, so if it runs
# without step 6 following it, every corrected median, 90% CI, sample size and method note is
# silently deleted and the live pages fall back to the raw, premium-skewed quarterly sample.
# That is exactly what happened: Burleigh Waters served $2,115,000 instead of $1,925,000 and
# +23.6% YoY instead of +6.9%, for roughly 29 days out of every 30, unnoticed.
#
# Ordering is now enforced by sequence, not by clock spacing. Run this and nothing else.
# For an off-cycle rebuild, run THIS script — never the individual precomputes.
#
# Step 6 MUST be last: it is the only writer of the Domain ∪ onthehouse medians, and steps 1
# and 5 both overwrite the document it writes into.
#
set -uo pipefail

cd /home/fields/Fields_Orchestrator || exit 1
set -a && . .env && set +a
source /home/fields/venv/bin/activate

PY=/home/fields/venv/bin/python3
ENGINE=/home/fields/Feilds_Website/08_Market_Narrative_Engine
failed=0

run_step() {
  local label="$1"; shift
  echo ""
  echo "───────────────────────────────────────────────────────────────"
  echo "$(date '+%Y-%m-%d %H:%M:%S %Z')  START  $label"
  if "$@"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z')  OK     $label"
  else
    local rc=$?
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z')  FAILED $label (exit $rc)"
    failed=1
  fi
  return 0
}

echo "==============================================================="
echo "Monthly market precompute — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "==============================================================="

run_step "1/6 indexed price data (raw rebuild)" \
  bash -c "cd '$ENGINE' && $PY precompute_indexed_price_data.py"

run_step "2/6 days-on-market backfill" \
  $PY scripts/backfill_days_on_market.py --apply

run_step "3/6 market charts — dom + cycle" \
  bash -c "cd '$ENGINE' && $PY precompute_market_charts.py --charts dom cycle"

run_step "4/6 market charts — volume + turnover" \
  bash -c "cd '$ENGINE' && $PY precompute_market_charts.py --charts volume turnover"

run_step "5/6 PropRadar VOLUME re-anchor" \
  $PY scripts/propradar/recalibrate_charts.py --all --apply

# If anything above failed the document may be in a half-rebuilt state, but the promote is
# still the right thing to do — it is what puts the defensible medians back on the pages.
# Never skip it on a partial failure; that is the state this whole script exists to prevent.
run_step "6/6 union medians + CIs — PROMOTE (must be last)" \
  $PY scripts/precompute_union_prices.py --promote

# Independent confirmation that step 6 actually landed and nothing reverted it.
run_step "verify: union median integrity" \
  $PY scripts/check_union_median_integrity.py

echo ""
echo "==============================================================="
if [ "$failed" -eq 0 ]; then
  echo "Monthly market precompute COMPLETE — all steps OK"
else
  echo "Monthly market precompute FINISHED WITH FAILURES — read the log above."
  echo "If the integrity check failed, the live pages are serving raw medians."
  echo "Re-run: $PY scripts/precompute_union_prices.py --promote"
fi
echo "==============================================================="
exit "$failed"
