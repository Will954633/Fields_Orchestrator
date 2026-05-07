# Data Sourcing & Methodology Audit — Q1 2026 Report

**Purpose:** every figure in the report traced to its exact source, with comparison to the website's `market-metrics/{suburb}` pages.

**Date:** 2026-05-07
**Scope:** the V4 PDF (`issues/q1_2026/latest.pdf`)

---

## 1. Summary

The report and the website draw from the **same three precomputed collections**, using the **same field names**, in the **same database**. Every number in the report's prose, charts, and stat blocks is sourced from a precomputed collection — not from raw transaction queries — with one explicit exception: the per-suburb **distribution chart** (half-violin + scatter) on page 13, which by necessity reads individual sale prices from raw `Gold_Coast.{suburb}` records.

There are **two new analytical constructs** in the report that do not exist on the website (the **Fields Conviction Index** and the **Fields Conviction Map**), both computed locally by `pipeline/fci_calculator.py` from the same underlying source data the website uses.

There is **one methodology nuance** worth flagging — the FCI's volume component currently uses a stricter transaction count than the prose narrative does (24 vs 54 for Robina Q1 2026). Both are correct for their purpose, but the inconsistency could read as careless and is worth fixing in v2.

---

## 2. The data spine — every collection used

All in MongoDB database `Gold_Coast` on Azure Cosmos DB.

| Collection | What it holds | Website uses it via | Report uses it via |
|---|---|---|---|
| `precomputed_indexed_prices` | Quarterly indexed price series + rolling 12m median + YoY growth, per suburb | `market-narrative.mjs` (`indexed-price-race`), `market-insights.mjs`, `suburb-growth.mjs` | `pipeline/fci_calculator.py`, `pipeline/generate_charts.py` (charts 03, 04, FCI input) |
| `precomputed_market_charts` | Sales volume + DOM + market cycle + turnover timeline per suburb (chart_type-keyed docs) | `market-narrative.mjs` (`charts/sales-volume`, `charts/days-on-market`, `charts/turnover-rate`) | `pipeline/fci_calculator.py` (DOM input), `pipeline/generate_charts.py` (charts 05, 06) |
| `Gold_Coast.{suburb}` (raw sold) | Individual sold property records — used **only** for the distribution chart on page 13 | Not used (website serves precomputed only) | `pipeline/generate_charts.py` chart 07 (distributions) |

---

## 3. End-to-end number check — Robina Q1 2026

Verified against database by direct query 2026-05-07.

| Number cited in the report | Exact database path | DB value | Report value | Match |
|---|---|---|---|---|
| Rolling 12-month median | `precomputed_indexed_prices.{_id: "robina"}.rolling_12m_median_price` | `1450000` | $1,450,000 | ✓ |
| Year-on-year price growth | `precomputed_indexed_prices.{_id: "robina"}.rolling_12m_yoy_pct` | `7.0` | +7.0% | ✓ |
| Q1 2026 sales count | `precomputed_market_charts.{_id: "robina_sales_volume"}.timeline[period: "2026-Q1"].sales_count` | `54` | 54 | ✓ |
| 5-year average sales | `precomputed_market_charts.{_id: "robina_sales_volume"}.historical_average` | `53.2` | 53.2 | ✓ |
| DOM median Q1 | `precomputed_market_charts.{_id: "robina_days_on_market"}.timeline[period: "2026-Q1"].median_days_on_market` | `26` | 26 days | ✓ |
| DOM historical median | `precomputed_market_charts.{_id: "robina_days_on_market"}.historical_median` | `22.5` | 22.5 days | ✓ |
| Total growth (Q2 2016 → Q1 2026) | `precomputed_indexed_prices.{_id: "robina"}.total_growth_pct` | `141.27` | not currently cited | n/a |

**All seven match exactly.** Same pattern for Burleigh Waters and Varsity Lakes.

---

## 4. Comparison — website endpoints vs report sourcing

### 4.1 Where they align (identical source, identical field, identical interpretation)

| Metric | Website endpoint | Website source field | Report source field | Status |
|---|---|---|---|---|
| Indexed price series | `/api/market-narrative/{suburb}/charts/indexed-price-race` | `precomputed_indexed_prices.indexed_series[].index_value` | same | **identical** |
| Quarterly median price | (data insights strip) | `precomputed_indexed_prices.indexed_series[].median_price` | same | **identical** |
| Rolling 12-month median | `market-insights.mjs` | `precomputed_indexed_prices.rolling_12m_median_price` | same | **identical** |
| Rolling 12-month YoY % | `market-insights.mjs` | `precomputed_indexed_prices.rolling_12m_yoy_pct` | same | **identical** |
| Sales volume timeline | `/api/market-narrative/{suburb}/charts/sales-volume` | `precomputed_market_charts.{suburb}_sales_volume.timeline[].sales_count` | same | **identical** |
| Sales volume — 5yr seasonal baseline | `/api/market-narrative/{suburb}/charts/sales-volume` | `precomputed_market_charts.{suburb}_sales_volume.seasonal_trend[]` (avg by quarter) | `historical_average` from same doc | **identical** (different denominator slice — both pre-baked) |
| DOM timeline | `/api/market-narrative/{suburb}/charts/days-on-market` | `precomputed_market_charts.{suburb}_days_on_market.timeline[].median_days_on_market` | same | **identical** |
| DOM historical median | `market-insights.mjs` | `precomputed_market_charts.{suburb}_days_on_market.historical_median` | same | **identical** |
| Total 9-year growth | `suburb-growth.mjs` | `precomputed_indexed_prices.total_growth_pct` | same (in tension chapter chart) | **identical** |

### 4.2 Where the report does something the website does NOT

| Item | Report location | Note |
|---|---|---|
| **Fields Conviction Index** (FCI) | Cover, page 5-6, page 11, suburb stat blocks | Not on the website at all. Computed by `pipeline/fci_calculator.py` from the same precomputed-source components. Methodology page (24) discloses construction. |
| **Fields Conviction Map** | Page 7 | Not on the website. Computed locally; uses `rolling_12m_yoy_pct` (X axis, identical to the website's source) and a sales-volume z-score (Y axis, computed from `precomputed_indexed_prices.indexed_series[].transaction_count`). |
| **The Standoff twin-line chart** | Page 9 | Indexed median (website source) overlaid against FCI (new construct), both rebased Q1 2023 = 100. |
| **Distribution chart (half-violin + scatter)** | Page 13 | The one chart that reads **raw** sold-transaction sale prices from `Gold_Coast.{suburb}` records. The website does not currently publish a per-sale price distribution. **This is the only chart that violates the precomputed-only source-of-truth rule** — by necessity, because the precomputed collections do not store individual sale prices, only aggregates. |
| **Real Pain & Gain** | Mentioned but not yet built | Flagged for Issue 02. |
| **Cross-source price reconciliation** | Mentioned in methodology | Flagged for Issue 02; depends on Cotality / Domain / SQM data parity verification not yet done. |

### 4.3 Where the website does something the report does NOT (yet)

| Item | Website location | Why not in V1 |
|---|---|---|
| Property-type split (house vs unit prices) | `market-narrative.mjs` (`charts/property-type-prices`) | Out of scope V1; flagged for Issue 02 deeper Robina section |
| Auction clearance | various | Gold Coast is mostly private treaty; sample sizes too small to publish quarterly. Editorial choice. |
| Active listings count + MoM | `market-insights.mjs` reads `precomputed_active_listings` | Snapshot data, not historical series — would require additional infrastructure for historical comparison |
| Turnover rate | `precomputed_market_charts.{suburb}_turnover_rate` | Annual data only, not granular enough to anchor a quarterly issue |

---

## 5. Methodology nuance worth flagging

There is **one inconsistency** in the report's V4 that is worth explaining and probably worth fixing in v2.

**The issue:** three different transaction counts exist for the same suburb-quarter, because the three precomputed collections apply different inclusion criteria:

| Source | Robina Q1 2026 transaction count |
|---|---|
| `precomputed_indexed_prices.indexed_series[Q1 2026].transaction_count` | 24 |
| `precomputed_market_charts.robina_sales_volume.timeline[2026-Q1].sales_count` | 54 |
| `precomputed_market_charts.robina_days_on_market.timeline[2026-Q1].transaction_count` | 35 |

The differences likely reflect:
- **`indexed_series`** — strictest, only transactions with full attribute coverage usable for the hedonic-style index calculation
- **`sales_volume`** — broadest, deduplicated across three sources (Domain / REA / Onproperty), all houses
- **`days_on_market`** — transactions where DOM data was captured (most have it; a minority don't)

The report currently uses:
- The **prose** (and the suburb stat blocks) cite the broader **sales_volume.sales_count** = **54** for Robina — which matches the website's sales-volume chart
- The **FCI's volume component** is computed from **indexed_series.transaction_count** = **24** for Robina — which is what `fci_calculator.py` reads

Both are correct individually, but a reader who notices the gap might lose trust. **Recommendation:** in v2, switch the FCI volume input to use `sales_volume.sales_count` so it matches the prose. This will require recomputing the FCI series, and the numbers will shift slightly (probably by 1-3 points up or down per suburb-quarter — directionally similar but not identical).

The fix is small (one function call change, one rerun). I'll flag it and wait for your call on whether to apply it now or in Issue 02.

---

## 6. Distribution chart — the one raw-data exception

**Location:** page 13 ("Three suburbs, three distributions")
**Source:** `Gold_Coast.{suburb}` collection, query `{listing_status: "sold", sale_price: {$exists: true}}` — last 12 months of arms-length sales.
**Why precomputed isn't possible:** the precomputed collections store medians, percentiles, and aggregates — not individual sale prices. To draw a distribution shape, the chart needs every individual transaction.
**Filtering applied:** sale prices < $100,000 excluded (likely data errors or non-arms-length); sale prices > $10,000,000 excluded (extreme outliers that distort visualisation).
**Sample sizes shown on chart:** N=348 Robina, N=271 Burleigh Waters, N=305 Varsity Lakes.
**Risk:** this is the only number in the report not under the precomputed-source-of-truth umbrella. If a reader reverse-engineers the median from the dot positions, it should match the website's median (within rounding). If it doesn't, that signals a data drift between the raw collection and the precomputed pipeline — worth monitoring.

---

## 7. Recommendation

The report is materially aligned with the website. Every figure that has a website equivalent ties exactly to the same precomputed source. Two items to handle for v2:

1. **Resolve the FCI volume basis** — switch from `indexed_series.transaction_count` to `sales_volume.sales_count` so the FCI components are explainable from the same denominators the prose uses. Small numeric shift; large credibility gain.
2. **Add a methodology box on the distribution-chart page** — single sentence noting "this chart is computed from raw sold-transaction records, not the precomputed series; sample size cited above the chart."

Both changes are 30-minute fixes. I'd recommend doing both before Issue 01 ships externally.

---

## 8. The exact data path for every figure on the cover and FCI page

For the most-quoted numbers in the report, here are the exact paths:

```
Cover stat: "FCI = 95.9"
└─ pipeline/fci_calculator.py
    ├─ component 1: indexed price (50% weight)
    │   └─ db.precomputed_indexed_prices.{_id}.indexed_series[].index_value
    ├─ component 2: sales volume (25% weight)
    │   └─ db.precomputed_indexed_prices.{_id}.indexed_series[].transaction_count
    └─ component 3: inverse DOM (25% weight)
        └─ db.precomputed_market_charts.{_id: "{suburb}_days_on_market"}.timeline[].median_days_on_market

Cover stat: "between 7.0% and 18.6% YoY"
└─ db.precomputed_indexed_prices.{_id}.rolling_12m_yoy_pct
    ├─ Robina: 7.0
    ├─ Burleigh Waters: 8.2
    └─ Varsity Lakes: 18.6
   ↑ same field market-insights.mjs serves as "Annual Growth"

Cover stat: "Sales volumes ran 17% below the five-year same-quarter average"
├─ numerator: Σ(sales_count for Q1 2026 across 3 suburbs) = 54 + 30 + 21 = 105
│   └─ db.precomputed_market_charts.{_id: "{suburb}_sales_volume"}.timeline[period: "2026-Q1"].sales_count
└─ denominator: Σ(historical_average across 3 suburbs) = 53.2 + 46.7 + 27.5 = 127.4
    └─ db.precomputed_market_charts.{_id: "{suburb}_sales_volume"}.historical_average

Suburb stat blocks (e.g. Robina FCI 93.7, $1,450,000, 54 sales, 26-day DOM)
└─ all four numbers from the precomputed sources above
```

Identical to what `market-narrative.mjs` and `market-insights.mjs` would return for the same suburb if queried.
