# Macro / Micro Framework — What the Report Measures

**Document:** 06 of 7 (Strategy series)
**Source:** `research/market_analysis_frameworks.md`
**Purpose:** The data spine. Every quarterly issue tracks the same indicators in the same way. This is the framework — a designer or analyst can build a chart from this without reading the research.

---

## 1. Three forces, one stress dial

Professional analysts model residential property as a function of three forces:
1. **Money cost** — cash rate, lending standards, serviceability buffers
2. **Household formation** — overseas migration, internal migration, demographics
3. **Dwelling pipeline** — approvals, completions, build cost vs price

The report tracks one indicator from each, plus a stress dial. Each appears in the same place every issue. The framework's consistency is what makes year-on-year comparison meaningful.

## 2. Macro indicators — the 12 that matter

Reported on the macro page of each issue. Each row: the indicator, what it is, why we report it, source, cadence.

| # | Indicator | What | Why it matters | Source / cadence |
|---|---|---|---|---|
| 1 | **RBA Cash Rate Target** | Overnight policy rate (currently 4.35%) | Mortgage rates, asset discount rates, serviceability all anchor here. 25bp shifts borrowing capacity ~2-3%. | RBA — monthly + SMP quarterly |
| 2 | **APRA serviceability buffer** | Banks must assess loans at contract rate +3pp | The real "tightening" lever; binding more than the headline rate | APRA — annual review |
| 3 | **APRA DTI speed limit** | Live since Feb 2026: ≤20% of new lending at DTI ≥6× | First active macroprudential constraint since 2017; caps top of buyer pool | APRA letters to ADIs |
| 4 | **Net Overseas Migration** | Permanent + long-term arrivals minus departures (306k FY25, down from 429k) | ~120k household formations per year | ABS Cat. 3412.0, FY + quarterly |
| 5 | **QLD Net Interstate Migration** | +21,595 in year to June 2025 | Inflow from NSW/VIC supports SEQ price floor independent of NOM | ABS Cat. 3101.0, quarterly |
| 6 | **Building approvals** | Leading indicator, ~18-24 months ahead of supply | Approvals today determine completions in 2027-28 | ABS Cat. 8731.0, monthly |
| 7 | **Dwellings completed** | Coincident supply; tracks against household demand | Shortage = approvals consistently below demand for 3+ years (currently the case) | ABS Cat. 8752.0, quarterly |
| 8 | **Cordell Construction Cost Index** | Cotality build-cost measure (+2.5% YoY — slowest since Mar 2002) | Replacement cost is the long-run anchor; build cost rising faster than prices = supply slowdown | Cotality, quarterly |
| 9 | **Vacancy rate** | Share of rental stock advertised (national 1.0%; Gold Coast Main 1.1%) | Sub-2% = tenant-side bidding pressure, yields rise, investor demand returns | SQM Research, monthly |
| 10 | **Household debt-to-income** | Australia ~185% — among highest in developed world | Caps how far prices can run without income growth | RBA Chart Pack, quarterly |
| 11 | **Help to Buy + 5% Deposit Scheme** | Shared-equity scheme + LMI waiver | First-home demand is policy-driven; concessions move marginal buyers in/out | Treasury, Housing Australia |
| 12 | **QLD First Home concession** | Full transfer-duty exemption on new homes; existing exempt to $700k, taper to $800k | Concentrates entry-level FHB demand into specific brackets | QRO |

**Reporting rule:** every macro figure quoted as "as at [month] [year]" with source dataset and release date. Anything older than 90 days at publication needs an explicit "latest available" caveat.

## 3. Micro framework — 12 metrics per suburb

Reported in each suburb section. Same 12 metrics, every suburb, every issue.

| Metric | Definition | Interpretation | Common errors | Fields source |
|---|---|---|---|---|
| **Indexed price (hedonic)** | Quality-adjusted price level, rebased to 100 | The only honest single-number price track. Smooths composition and quality drift. | Treating 0.3% monthly moves as signal | Cotality Hedonic + Fields' suburb-level reconciled valuations |
| **Median sale price (12mo rolling)** | Middle transaction price across last 12 months | Useful as a level reference, not a change indicator. Always paired with volume. | Quoting single-month medians on small samples (<30 sales) | Fields DB transaction data |
| **Sales volume (12mo)** | Count of arms-length transactions | Volume is the most under-reported number. 10% price rise on 30% lower volume ≠ 10% rise on stable volume. | Conflating listing count with sales count | Fields DB |
| **DOM — distribution** | List-to-unconditional, reported as median + IQR | Full distribution shows whether the suburb has a long tail of stale stock | Reporting only the median; mixing private treaty + auction times | Fields DB |
| **Sale-to-list ratio** | (Sale ÷ first list) − 1, median across all sales | Direct read on negotiability | Using "current asking" not "first listed" | Fields DB |
| **Months of supply** | Active listings ÷ avg monthly sales | <6 months = sellers' market, >6 = buyers' | Confusing total-listings (with relistings) with unique-property listings | Fields DB |
| **Median rent + gross yield** | Median advertised rent ÷ median price × 52 | Yield is the value floor — investor return point | Comparing advertised rents to sold prices (timing mismatch) | SQM/REIQ + Fields DB |
| **Vacancy rate (postcode)** | % rental stock advertised | Sub-2% = rents +6-8% likely next 12mo | Postcode-level samples can be tiny | SQM Research |
| **Auction clearance rate** | % of auctions clearing | **Only meaningful in auction-dominated markets.** Gold Coast is mostly private treaty — see §4 | Reporting GC clearance with low N | Cotality, weekly |
| **Buyer/seller demographics** | Age, household type, owner-occupier vs investor share at sale | Tells you who is bidding now — predicts what stock will sell next cycle | Generic ABS census 5+ years stale by mid-cycle | ABS + Fields scraped buyer signals |
| **Supply pipeline** | DAs lodged, DAs approved, off-the-plan units in marketing | Tomorrow's sales volume | Counting marketing brochures as guaranteed completions | GCCC PD Online + Fields enrichment |
| **Comparable sales selection** | 3-8 properties matched on: distance ≤500m, recency ≤6mo, beds/baths, floor area ±15%, land ±20%, condition, position, view | The honest single-property valuation. Confidence reflects spread of adjusted comps. | Picking comps to support a target price; ignoring adjustment magnitude (>15% adjustment = not comparable) | Fields' `precompute_valuations.py` reconciled valuation |

## 4. Signal vs noise — what we deliberately do not report

Credibility depends on refusing the noise. Each item: what it is, why misleading, what we report instead.

| Noisy data point | Why it's misleading | What we report instead |
|---|---|---|
| **Single-month median moves on <30 sales** | Suburb-level monthly medians swing 5-10% on composition alone | Indexed price + 12mo rolling + sales count |
| **Asking-price indices** | Selection bias (only listed; vendors anchor on prior cycle); the asking-vs-sale gap is itself the volatility | Sale-to-list ratio applied to closed transactions |
| **Auction clearance on the Gold Coast** | Most GC sales are private treaty; weekly samples <30; dominated by prestige and probate | DOM distribution + sale-to-list |
| **YoY median without composition control** | A suburb that sold five $3M canal homes this April but none last April will print a fake +30% YoY | Hedonic / indexed comparison or stratified medians |
| **"Most expensive sale this week" headlines** | Single transactions are PR for the agent — not market signals | Aggregate top-decile movement over trailing year |
| **Total listing count without relisted/withdrawn split** | Online portal counts include relisted properties | Unique-property listings deduplicated on address |
| **DOM mixing auction + private treaty** | Auction campaigns end at auction date; private treaty at unconditional contract — different definitions | Split by sale method, or report private-treaty-only |
| **Forecast price growth as a single number** | Predictions presented as data | Current state of leading indicators (vacancy, approvals, rates) — let reader weigh |
| **Investor "yield + capital growth" total** | Combines rental yield with capital growth as one return; ignores tax, vacancy losses, maintenance, advertised-rent selection bias | Each separately with caveats |

This list is published in the Methodology chapter every issue. It is part of what differentiates Fields.

## 5. Methodology — the four price-measurement methods

Every method handles composition differently. We pick the right one for the question.

| Method | How it works | Strength | Weakness | Fields use |
|---|---|---|---|---|
| **Simple median** | Middle transaction price | Cheap, easy | Volatile; quality drift contaminates every reading | Used only as a level reference, never as the change indicator |
| **Stratified median** (Domain) | Bucketed by dwelling type, long-term price tier, SEIFA score; within-stratum changes reweighted | Better, but only as good as strata definitions | Postcode-level used as a sanity check |
| **Hedonic** (Cotality / CoreLogic) | Models price as sum of attribute contributions via regression | Uses every transaction; adjusts for quality | Black-box; dependent on attribute coverage | **Suburb-level — the primary** |
| **Repeat sales** (Case-Shiller) | Only properties that sold ≥2 times | Eliminates between-property heterogeneity | Ignores new builds, single-owner homes; sensitive to renovations between sales | Long-cycle indicator on stable inner suburbs |

**Fields' choice:** hedonic at suburb level + stratified-median sanity check at postcode level + repeat-sales for 10-year cycle context.

## 6. Comparable-sales valuation — why over CatBoost

Fields stores both a CatBoost ML estimate (`iteration_08_valuation`) and a comparable-sales **`reconciled_valuation`**. We publish the latter on property pages and in this report.

**Reasons:**
- **Auditability** — every adjustment traceable to a real sold property within 500m.
- **Honesty** — the buyer can test the result.
- **Confidence intervals** — derived from the weighted standard deviation of adjusted comps (1.645 × σ for a 90% CI). Honest about disagreement.
- **Range, not figure** — directional valuations ($2.5M+) display range only because comp scarcity widens the CI.

The CatBoost number is used internally for benchmarking, not published.

## 7. Time horizons — when to use which

| Horizon | Use for | Caveat |
|---|---|---|
| 1 month | Direction only, never magnitude | Sub-30-sales suburbs: ignore entirely |
| 12 months | Headline change, paired with volume | Composition risk — verify with hedonic |
| 5 years | Cycle context — was the last move structural or rate-driven? | Cycle-to-cycle, not peak-to-peak |
| 10 years | Long-run growth, real (CPI-adjusted) returns | Compare nominal *and* real |
| Full cycle | Top-of-market vs trough comparison (e.g. 2017 peak → 2019 trough → 2022 peak → 2026) | Use real prices and adjust for stamp-duty / tax regime changes |

**Real vs nominal:** all multi-year prints are reported in both. The 5-year nominal figure looks great; the 5-year real figure tells the purchasing-power story. The Real Pain & Gain section uses real-after-cost.

## 8. Suburb-specific dimensions

Same 12 metrics for each suburb — *plus* the suburb-specific dimension that defines its market.

### 8.1 Robina (4226)
- **Master-planned vs older estate split** — Robina is dominated by Robin Group / Robina Land Corp planned releases (1980s-2010s). Newer pockets (Robina Quays, Cottesloe Reach) trade on a different multiple than older Bond Estate. **Always report median + indexed price by estate, not just suburb.**
- **House (61%) vs unit/townhouse (39%) split** — minimum split is dwelling type.
- **Robina Town Centre / hospital / Bond Uni / train station proximity** — walking-distance-to-station premium is a measurable hedonic adjustment.
- **3.3 bedrooms per dwelling, owner-occupier 64%** — stable family-buyer base.
- **Master-planned covenant constraints** (build envelope, fence height, colour palette) — reduces variance in stock and tightens comparability of comps.

### 8.2 Burleigh Waters (4220)
- **Canal-front vs non-canal split** — canal-front trades on a 30-50% premium. **Combining them is the biggest reporting error in this suburb.**
- **Flood overlay vs ICA flood zone** — two distinct definitions:
  - GCCC City Plan overlay (planning-conservative)
  - ICA Insurance Probability Zones (insurer-pricing)
  - Many properties under council overlay are *not* in any ICA zone — insurers don't price them as flood risk even though council does.
  - Fields reports both. Recommends FloodWise as the third-party detail source.
- **Insurance availability** — some insurers refuse cover or load premiums by thousands on canal properties. ICA paid >$1.5bn on Cyclone Alfred (2025); premium pressure is real and ongoing.
- **Family-premium suburb with limited supply** — land-locked between Burleigh Heads, ridge, and motorway. Physical supply ceiling supports prices.
- **Median house price ~$1.4-1.68M (2026, sources vary)** — wide source variance is itself a signal that a single median is unreliable. Use indexed price.

### 8.3 Varsity Lakes (4227)
- **Lake-frontage vs non-lake** — direct equivalent of canal-front. Premium is measurable and significant.
- **Townhouse / unit dominance** — historically high townhouse share. Dwelling-type split non-negotiable.
- **Bond University proximity** — student / young-professional rental demand floor; yields tend higher than surrounding family suburbs.
- **Younger demographic, more transient ownership tenure** — higher turnover means more comparable sales available, but more renovation drift between repeat sales (favours hedonic over repeat-sales).
- **Population ~14,500** — mixed family / student / retiree base.

### 8.4 Cross-suburb dimension
All three suburbs sit within 30 minutes of:
- Coomera Connector corridor
- Cross River Rail Gold Coast extensions (Hope Island Station)
- 2032 Olympics infrastructure spend ($4.5bn announced + transport infrastructure pipeline)

We report infrastructure progress as a **coincident factor**, not as forecast price growth.

## 9. The cycle context — May 2026

This is the macro state every Issue 1 acknowledges, then localises.

- **RBA cash rate 4.35%** after May 2026 hike (8/9 board members in favour). Market path implies 4.70% by year-end.
- **Headline inflation 4.6%** (March), expected to peak 4.8% mid-2026; underlying inflation expected above 3% until mid-2027.
- **Macro stance:** late-cycle tightening. APRA buffer 3pp held. **APRA DTI speed limit live since Feb 2026** — first active macroprudential constraint in nearly a decade.
- **Migration:** NOM 306k (FY25), QLD net-interstate +21,595 (year to June 2025). Brisbane population +2.1%.
- **Supply:** QLD March 2026 dwelling approvals -6.4% m/m (private houses +7.2%); construction cost growth at 24-year low (CCCI +2.5% YoY). Approvals → completions gap continues to widen.
- **National prices:** Cotality HVI +0.3% in April 2026 (slowest in nearly a year). Sydney/Melbourne -0.6%, Perth +2.1%, Brisbane +1.1%, Adelaide +1.2%.
- **Gold Coast:** Houses ~$1.32-1.40M city-wide median, +10-12% YoY. Units median ~$956k (overtook Sydney median in Oct 2025 — first time on record). Vacancy 1.1%, listings ~20% below 5-yr average.
- **Household stress:** Severe-stress mortgagor share has *declined* since mid-2024 (RBA FSR Mar 2026). Arrears low. Some investor DTI risk creeping up — exactly what the new APRA limit targets.

**The question Fields' report should answer:** with rates rising, supply still constrained, and migration easing from peaks but well above pre-COVID, **which way does the southern Gold Coast resolve in H2 2026?**

We will not predict. We will lay out the indicator state and the conditional logic ("if vacancy stays sub-1.5% and approvals don't recover, then…").

## 10. Open questions / what we admit we don't know

A short list, prominent in the report's "What this report does not answer" page:

1. **Sub-suburb sample size** — Burleigh Waters canal-front had ~X transactions in the last 12 months. Below 30, indexed prices have wide confidence bands.
2. **Selection bias on sold-only data** — hedonic uses sold transactions to estimate value of unsold stock. If marginal seller is unrepresentative (distressed, divorce, estate), index drifts.
3. **Insurance premium trajectory** — ICA paid ~$3.5bn on extreme weather in 2025 + Cyclone Alfred ($1.5bn). Premium pricing for 2026-27 not yet in published indices.
4. **DTI speed-limit response** — active for ~3 months. Banks may front-load DTI≥6× in some quarters and ration in others. Effect on sub-$1M FHB market monitored, not modelled.
5. **Help to Buy uptake** — launched 5 Dec 2025, only 2 lender panels live (CBA, Bank Australia) at start of 2026. Volume too thin to call structural impact.
6. **Olympics infrastructure timing** — Cross River Rail and Coomera Connector completion dates are policy-sensitive. We track announced schedules, not assumed delivery.
7. **The CatBoost vs reconciled valuation gap** — where the two diverge by >15% on a property, neither is reliable; the gap itself is a flag.
8. **Composition drift in our own dataset** — Fields' active-listing scrape is comprehensive but sold-record coverage varies by source. Coverage gaps for non-core suburbs are documented and disclosed.

## 11. Reporting cadence by indicator

| Cadence | Indicators |
|---|---|
| Daily (internal) | Cotality HVI; SQM (some) |
| Weekly | Auction clearance (cited rarely); SQM weekly sales |
| Monthly | Vacancy; cash rate decision; pulse email |
| Quarterly | RBA SMP; ABS approvals; Fields Quarterly issue |
| Annually | NOM (full), Year-in-Review issue |

The Quarterly is the integration point. The Pulse is the in-between reminder. The weekly email (Issue 4+) is the rhythm.
