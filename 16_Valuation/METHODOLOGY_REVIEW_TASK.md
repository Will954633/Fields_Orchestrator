# Valuation methodology & accuracy — full review

**Status:** OPEN
**Raised:** 2026-08-20 (Will + Claude session on the valuation report page)
**Cadence of reminder:** weekly Monday 08:00 AEST via Telegram until this file's Status line reads DONE.
**To stop the reminder:** change the `**Status:**` line above to `DONE`.

This is a *collaborative* review (Will + Claude), not an autonomous job. The reminder
exists so it is not forgotten, not to hand it off.

---

## Why this is on the list

Building the formal valuation report page surfaced three things that each point back at
the method itself rather than at any one property. None is a quick fix; together they say
the accuracy story needs a full pass.

### 1. The published 80% bands no longer contain 80% — measured 2026-08-20

The per-suburb bands are stored as an **empirical 80% band** — the width that contained
four sales in five when last measured (2026-08-08). Re-measured on 2026-08-20, on the
**same method** (confirmed by A/B: the floor-area fix made 0 difference to this), against
freshly settled sales:

| suburb | published band | contains today | width now needed for 80% |
|---|---|---|---|
| Robina | ±12.2% | **~72%** | ~±14.7% |
| Varsity Lakes | ±11.2% | **~75%** | ~±12.5% |
| Burleigh Waters | ±14.0% | **~76%** | ~±15.5% |

The engine comment at `precompute_valuations.py:2150` is explicit: *"if a measurement
shows coverage below 80%, the band WIDENS — it does not get quietly left alone."*
**Will's decision 2026-08-20: leave the bands as-is for now and review the whole method
here rather than reflexively widening.** That is a deliberate, logged hold — but until it
is resolved, the stored `range_basis.note` ("Four in five sales land inside this band")
overstates for all three suburbs, and the report page repeats it. Do not ship that page to
real buyers until this is settled.

Open question for the review: is the drift real degradation, sampling noise on a small
recent-sales window (n≈150–260 per suburb), or a market move the method hasn't absorbed?
Re-measure across a longer window before deciding to widen.

### 2. A recalibration was measured and deliberately HELD on 2026-08-13

Commit `Fields_Orchestrator` 2026-08-13 08:58 ("valuation: measure the recalibration,
hold the release; burleigh refit is wrong") records a prior session that:
- Measured a hardening + refit on the full backtest, then **reverted to the incumbent
  config** so the nightly recompute stayed unchanged — because shipping the calibration
  without also shipping the matching page tables "publishes a track record for a method
  the site stopped running."
- Found `burleigh_waters 1.0177` (from the 2026-08-10 refit) is **wrong**:
  `calibration_refit.py` fits with **empty median/street_premium caches**, so it measures a
  method missing ~21% of gross adjustment dollars. Burleigh reads as undervaluing there; on
  the real method it overvalues. Applied, it moved MAE 9.3 → 10.4, bias +3.8 → +6.6.

So there is a **known-broken refit tool** (`calibration_refit.py` fits on empty caches) and
a **queued-but-held recalibration**. The review must decide the calibration story end to
end, and fix the refit harness before trusting any number it produces.

### 3. The confidence tier is still not calibrated

Within-10% by tier is non-monotonic (very_low and low both beat high in past runs; this
run: Robina very_low 20.6% MAE vs low 8.1%). `emit_v4.py` already emits `confidence_reason`
only, never the bare tier, and the report page suppresses it — but the tier is still stored
and still drives nothing trustworthy. Decide whether to recalibrate it or retire it.

---

## Scope for the review

1. **Accuracy, re-measured properly.** Full backtest per suburb, `--price-filter none
   --blind-subject`, over a window long enough that n is not driven by a handful of recent
   sales. Decide the honest published figures and bands from that, not from a 12-day window.
   Reproduce: `python3 scripts/valuation_backtest.py --suburb <s> --price-filter none
   --blind-subject --min-price 1000000 --max-price 2000000`.
2. **The band promise.** Either widen to the measured 80% widths and update every surface
   that quotes them (report page, `MethodologyPage`, appraisal PDFs, `range_basis.note`,
   `measured_on`), or change the framing away from "four in five". Pick one; do not leave
   the current mismatch.
3. **Calibration.** Fix `calibration_refit.py` (empty-cache bug) first. Then decide whether
   to ship the held recalibration, and if so, ship the page tables in the same change.
4. **Confidence tier.** Recalibrate or retire.
5. **Floor-area coverage.** 48.7% of off-market homes still resolve to no floor area — the
   single biggest adjustment, missing on half the book (see
   `valuation_noise_floor_and_enrichment` memory). This caps achievable accuracy; worth a
   pass on enrichment coverage.
6. **Small item, can fold in or do anytime:** `precompute_valuations_PATCHED.py` (a forked
   engine copy that wrote to the DB with the floor-area defects) was deleted 2026-08-20.
   Confirm no prototype workflow silently depended on it.

## Guardrails (do not relitigate — from memory + fix-history)

- Never claim "more accurate than Domain" in public content (ACCC substantiation; falsifiable
  from our own tables in Robina/BW). Sayable: "we publish our error rate; we haven't found
  another agency or portal that publishes theirs."
- Never quote a "90% confidence interval" — the band is not a CI and never contained 90%.
- The method is scoped to **detached houses $1M–$2M**; outside it, suppress figure AND range.
- The band width is an OUTPUT of the backtest, not a tuning knob.

See: `16_Valuation/accuracy/`, `logs/fix-history/2026-08-20.md`, and memories
`valuation_accuracy_figures_2026-08`, `valuation_backtest_claim_constraints`,
`valuation_design_envelope`, `valuation_noise_floor_and_enrichment`.
