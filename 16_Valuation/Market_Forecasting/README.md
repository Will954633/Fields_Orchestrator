# Market Forecasting — Combination Model

A demand/rate-cycle model that predicts Australian capital-city **house-price
regimes ~6 months ahead** from four macro inputs. Built and de-risked 2026-09-06.

> **TL;DR** — Forecasting the *exact* price change 6 months out doesn't beat a
> naive "momentum continues" baseline. But **classifying the tails** — is a
> **decline** or a **dramatic upswing** coming? — works well out-of-sample
> (AUC ≈ 0.90). Two warning signals fall out of that. **Flat/stagnant markets are
> not predictable**, and the model is **blind to idiosyncratic regional shocks**
> (e.g. Perth/Darwin mining busts).

---

## 1. What the model is

| | |
|---|---|
| **Target** | House-price index year-ended momentum, **+2 quarters (6 months)** ahead |
| **Inputs** | **L** = new housing lending (YoY%, QoQ%) · **S** = retail turnover / consumer spending (YoY%, QoQ%) · **A** = ASX All Ordinaries (YoY%) · **C** = cash rate (level, 4-quarter change) |
| **Estimator** | Ridge regression (α = 8), expanding **walk-forward** (no lookahead), features standardised on the training window only |
| **Data** | ABS 8-capital-city quarterly panel, 2003–2021 (combos using ASX/cash run 2006–2021 by availability) |
| **Two operating models** | **Decline warning = L + S + C** · **Upswing warning = L + S + A + C** |

All features are **growth rates / changes**, not levels — that makes them
comparable across cities of very different size (Sydney vs Hobart) and is what the
cross-market panel needs.

---

## 2. Headline results (out-of-sample, pooled across 8 cities)

### Regime classification — the part that works (6-month horizon)

| regime | best inputs | AUC | notes |
|---|---|---|---|
| **Declines** (future momentum ≤ 0%) | **L + S + C** | **0.90** | cash rate is the key ingredient (rate/affordability channel) |
| **Dramatic upswings** (top 15%) | **L + S + A + C** | **0.90** | ASX earns its place here (equity booms lead property) |
| **Flat** (0–4%) | — | ≤ 0.68 | **not usefully predictable** |

Both tails are **best predicted at 6 months** and *degrade* at 9–12 months —
the opposite of the point-forecast R² pattern.

### Warning signals (what you'd actually act on)

**🔻 Decline warning — L + S + C @ 6mo** (base rate 24%)

| fire when | fires | precision | recall | lift |
|---|---|---|---|---|
| pred ≤ −1.5% (high-confidence) | 10% | **89%** | 38% | 3.8× |
| pred ≤ +0.8% | 20% | 73% | 62% | 3.1× |
| pred ≤ +1.4% (balanced) | 25% | 67% | 71% | 2.8× |

**🔺 Dramatic-upswing warning — L + S + A + C @ 6mo** (base rate 15%)

| fire when | fires | precision | recall | lift |
|---|---|---|---|---|
| pred ≥ +13.2% (high-confidence) | 10% | **83%** | 54% | 5.5× |
| pred ≥ +8.9% (balanced) | 20% | 54% | 71% | 3.6× |

### Point-forecast R² vs persistence — the part that *doesn't* work

| horizon | R² vs persistence |
|---|---|
| 6mo | ≈ 0.00 (persistence wins the smooth middle) |
| 9mo | +0.36 |
| 12mo | +0.37 |

…but even the 9–12mo R² only marginally beats a **no-data mean-reversion rule**
("shrink current momentum toward zero") which alone scores +0.16 (9mo) / +0.24
(12mo). **Do not use this model to predict the exact number.** Use the regime
warnings.

---

## 3. Why it's built this way — the investigation trail

This model is the survivor of a longer investigation into whether local
listing-liquidity and macro signals can predict Gold Coast / AU house-price
direction. The dead-ends are as important as the result:

1. **Sell-through rate** (sold ÷ listed) — strong in-sample (+2q, r 0.73) but the
   observation lag (wait for listings to resolve) cancels the lead → coincident
   "market-heat" gauge, not a forecaster.
2. **Days-on-market ≥ 80 / stale-listing rate** — real but modest; the "80-day"
   cutoff isn't special (monotonic across 50–90 days); mostly a days-on-market
   liquidity signal.
3. **DOM-bucket composition** — looked strong single-market (OOS R² 0.79) …
4. **Macro-demand (lending + spending)** — looked *very* strong single-market
   (OOS R² **+0.82** at 6mo) …
5. **De-risking exposed 4 as a mirage.** On the single Gold-Coast series the
   target's lag-1 autocorrelation is 0.98 → **effective sample size ≈ 1**. A
   permutation null reached R² 0.83 on *shuffled* targets; R² rose monotonically
   with feature count; the "answer" swung with the regularisation knob. The +0.82
   was small-sample overfitting.
6. **The fix was a multi-market panel** (independent price cycles = real effective
   sample). Built the ABS 8-capital-city panel. On it, point-forecast R² collapsed
   to ≈ 0 at 6mo and the model did *worst* on the crashed markets (Perth, Darwin) —
   confirming the mirage.
7. **But the tails survived.** Switching from R² (average fit) to regime AUC
   (tail classification) showed the model reliably ranks crash-bound and boom-bound
   markets at 6 months (AUC 0.90). That's the real, de-risked result above.
8. **CatBoost was tested and lost** — at ~120–700 rows vs ~50 features it overfits;
   regularised linear (ridge/lasso) beat it decisively and is interpretable. ML is
   the wrong tool at this sample size.

**Lesson worth keeping:** on smooth, autocorrelated targets, in-sample R² and even
single-series walk-forward R² are dangerously optimistic. Always validate on a
multi-market panel and against a trivial baseline (persistence / mean-reversion).

---

## 4. Caveats & limitations (read before using)

- **Regimes, not levels.** Predicts *direction/regime*, not the exact %.
- **Flat is unpredictable** (AUC ≤ 0.68) — stagnation looks like both mild-up and
  mild-down.
- **Blind to idiosyncratic regional shocks.** It's a demand/rate-*cycle* tool;
  it missed the Perth & Darwin mining busts (per-city point-forecast negative).
- **Deepest crash not OOS-validated.** The GFC sits in the training window (OOS
  starts ~2011), so genuine deep-crash calling is inferred, not proven.
- **Data window.** Combos using ASX/cash cover 2006–2021. ABS discontinued the
  price *index* after 2021-Q4 (only medians since), so the 2022 rate correction is
  out of range.
- **6-month lead, ~4–5mo usable** after the ~1–2 month data-release lag on lending
  /retail.
- **AUC ≠ accuracy.** 0.90 is rank quality; pick an operating point from the
  precision/recall tables for a real decision rule.
- Pooled across cities; per-city skill varies (Adelaide/Brisbane/Sydney strong,
  Perth/Darwin weak).

---

## 5. Files

| file | what |
|---|---|
| `README.md` | this document |
| `market_forecasting_model.py` | **the model** — loads the two CSVs, trains walk-forward ridge, prints regime AUC + warning-signal tables + R² context. Run: `python3 market_forecasting_model.py` |
| `build_panel.py` | reproducible ABS panel builder (pulls RPPI / LEND_HOUSING / RT / LF / CPI_Q from the ABS Data API and writes `abs_panel.csv`) |
| `abs_panel.csv` | the panel: `city, state, quarter, price_index, lending, retail, unemployment, cpi` (8 cities × 76 quarters) |
| `abs_panel_meta.json` | provenance: exact ABS dataflow IDs, query URLs, dimension codes, coverage per series |
| `national_macro.csv` | national ASX All Ords + cash rate (quarterly), used for the A and C inputs |

## 6. Reproduce

```bash
cd 16_Valuation/Market_Forecasting
python3 build_panel.py          # (optional) rebuild abs_panel.csv from ABS API
python3 market_forecasting_model.py
```

## 7. Data provenance

- **Prices / lending / retail / unemployment / CPI** — ABS Data API
  (`https://data.api.abs.gov.au/rest/`), dataflows `RPPI`, `LEND_HOUSING`, `RT`,
  `LF`, `CPI_Q`. Exact keys in `abs_panel_meta.json`.
- **ASX All Ordinaries & cash rate** — internal leading-indicators snapshot
  (quarterly), 2006-Q1 onward.
- Investigation & build date: **2026-09-06**.

---

## 8. Does it work for Robina specifically? (and local-signal follow-ups)

The panel model is validated on **capital-city** indices. Applying it to **Robina**
(a Gold Coast suburb) was tested directly and **does not work** — and the reason is
data, not a missing signal:

- **The combined model does NOT predict Robina.** Robina decline-AUC ≈ **0.51
  (chance)**; it fired "decline" through Robina's entire 2022–25 boom (predicted
  −0.3% to −4.4% while Robina rose +6% to +20%). Robina **decoupled** from the
  national credit cycle (migration/lifestyle-driven, not credit-driven).
- **Is the signal absent, or is there too little data? → too little data (proven).**
  Robina's own decline-AUC 95% CI is **[0.37, 0.85]** — it contains both chance
  (0.5) and "strong" (0.85), so the data *cannot distinguish them*. Robina has only
  **7 decline quarters in ~18 years** (Varsity 4, Burleigh **1**), from essentially
  the GFC + a couple of 2019 blips. You need ~40+ decline cases to pin an AUC to
  ±0.10. **You cannot build or validate a decline predictor for a market that
  barely declines** — its greatest strength (rarely falling) is what makes one
  unfittable. For contrast, the capital-city panel (80 declines) gives AUC 0.90 with
  a tight [0.85, 0.95] CI — declines *are* predictable in aggregate.

**Local signals tested (to find something Robina-native):**
- **Neighbouring suburbs (Varsity, Burleigh, Nerang, Merrimac, Mudgeeraba, Carrara)**
  — the **best Robina signal found.** They co-move tightly (r 0.77–0.92); the
  *basket* beats persistence at predicting Robina (**OOS R² +0.35 @ +2q**, bootstrap
  CI **[+0.03, +0.55]**, permutation **p = 0.056**). It **partially survives
  de-risking** (unlike the macro model), but is **borderline, not conclusive**, and
  is mechanically just "Robina rides its neighbours' denoised regional cycle."
- **"Expensive homes move down first" (top price quartile vs affordable tier)** —
  **mildly supported.** Top-tier momentum leads the affordable tier by ~1 quarter
  (r 0.85); in the GFC the top tier fell first and hardest (−10.5% in 2009-Q2) while
  the affordable tier lagged (−1.4%) and kept falling into 2012 after the top
  recovered. But the lead is small (mostly co-moving), rests on the one GFC downturn,
  and **Robina is mid-market** so it doesn't sit in the lagging tier — top-tier →
  Robina is only coincident-to-weak (+0.28 @ +2q).
- **Waterfront tier (`is_waterfront`)** — **not supported / too thin.** Only 328
  waterfront sold events over 20 years; the series is noisy and shows no lead over
  Robina (peaks at lag −1, i.e. slightly lags). No evidence for the hypothesis on
  usable data.

**Bottom line for Robina:** short-term moves are **weakly predictable via the
neighbouring-suburb regional cycle** (borderline +0.35 @6mo), marginally better than
national macro (~0). "Expensive leads affordable" is real but mild and Robina
doesn't benefit. **Robina *declines* remain unpredictable from its own history** —
not because no signal exists, but because Robina has hardly ever declined. Scripts
for these follow-ups live in session scratchpad (not persisted — modest/borderline
results not worth productionising).
