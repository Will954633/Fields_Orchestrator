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

# GC-wide days-on-market (houses/units) JSON behind /news/gold-coast. Reads the same
# timeline DOM data step 2 backfilled + step 3 recomputed, so it runs after them.
# Bakes public/data/gc_dom_by_type.json — push that file to the website repo to deploy
# (same as gc_overview.json; the git push is not part of this precompute).
run_step "4b market charts — GC days-on-market by type (houses/units)" \
  $PY scripts/build_gc_dom_by_type.py

# GC-vs-capitals days-on-market JSON. Reads system_monitor.domain_sold (GC, refreshed by
# the month-end domain_sold_sync_gc_wide cron) + domain_sold_capitals (refreshed by the
# month-end scrape_capitals cron) — both run on the last day of the month, so this bake
# on the 1st sees fresh data. Push public/data/gc_vs_capitals_dom.json to deploy.
run_step "4c market charts — GC vs capitals days-on-market" \
  $PY scripts/capitals_dom/build_capitals_dom_json.py

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
