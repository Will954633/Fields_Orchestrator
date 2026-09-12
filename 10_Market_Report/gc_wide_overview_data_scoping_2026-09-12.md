# Scoping: Gold Coast–Wide Market Overview vs Brisbane / Sydney / Melbourne

**Date:** 2026-09-12
**Question:** Can we replicate (or partly replicate) the single-suburb market overview (e.g. `/news/robina` + `/market-intelligence/robina/*`) at Gold-Coast-wide level, with comparisons to Brisbane, Sydney and Melbourne? What data do we have, what is freely available, and what would need new scraping?

**Verdict up front:** Yes — a substantial GC-wide overview is buildable, and most of it needs **no new data source**, only extensions of pipelines we already run. The Bris/Syd/Melb comparison layer is the genuinely new part, and nearly all of it is free: some via clean JSON/API/Excel, some via the same inline-JSON scrape pattern our SQM scraper already uses, some via PDF parsing. The two real gaps are (1) **no free daily/monthly price *index* exists for Gold Coast alone** anywhere (Cotality folds GC into Brisbane), and (2) **bulk QLD sales transactions are paid-only** (QVAS brokers). Neither blocks the page — our own 77-suburb transaction series covers the GC side of prices.

---

## 1. What the suburb overview shows today (and where each number comes from)

The suburb experience is ~19 charts/tiles across `/news/:suburb` (Data Insights Strip, 8 tiles) and 7 category tabs on `/market-intelligence/:suburb/:category`. Provenance breakdown:

| Provenance | Charts |
|---|---|
| **Own scrape** (Domain ∪ onthehouse union, via `precompute_union_prices.py` → `precomputed_indexed_prices` / `precomputed_market_charts` / `precomputed_active_listings`) | median price, price growth QoQ/YoY, capital-gain comparison, sales volume, days on market, turnover rate, active listings, new listings, price adjustments, vendor discount |
| **External — SQM Research** (`scrape_sqm_asking_prices.py` → `Gold_Coast.sqm_asking_prices`) | asking-price trends (weekly, houses + units) |
| **External — ABS** (`fetch_abs_market_signals.py` → `system_monitor.market_signals`) | market-signals panel + crash-risk SignalCards (WPI, lending, dwelling completions, CPI, HSI; all QLD state-level) |
| **External — FRED/RBA** (`fetch_macro_indicators.py` → `precomputed_macro_indicators`) | macro crash-risk charts (currently imported but not rendered) |
| **External — PropRadar** | absorption rate (primary source; own-data fallback) |
| **Static/bundled** | suburb-price-vs-growth scatter, 10-year price journey, suburb DNA, price forecast JSON |
| **LLM precompute** | category verdict/summary (`generate_market_pulse.py` → `system_monitor.market_pulse`, 3 suburbs × 7 categories) |

A GC-wide rollup **already exists**: `precompute_gold_coast_aggregate.py` writes `_id=gold_coast` docs — but it aggregates only the 3 target suburbs (a `gold_coast_average` variant covers the 8 tracked suburbs, 10,957 transactions).

---

## 2. What we already hold (DB inventory, verified 2026-09-12)

**Much wider than the 3 target suburbs:**

- **`Gold_Coast.precomputed_indexed_prices` — 79 docs**: quarterly median-price series **with transaction counts for ~77 GC suburbs** (e.g. helensvale 2,329 tx, southport 1,895, palm_beach 1,418). This is the best existing basis for a genuine GC-wide price series — a transaction-weighted all-suburb aggregate is a precompute change, not a data acquisition.
  - **Currency (verified 2026-09-12 after Will queried it):** the collection is live, NOT switched off. 69/79 docs were rewritten 2026-09-01 05:00 AEST by the monthly cron (`run_monthly_market_precompute.sh` — the individual cron entries were consolidated into it 2026-08-02, which makes the old commented lines *look* disabled). `gold_coast` aggregate refreshed 2026-09-02 by its own cron. Series complete through **Q2 2026**, Q3 tracked as in-progress → at most ~6 weeks behind, monthly refresh.
  - **Depth:** per-suburb series reach much further back than the aggregate — robina has 125 quarters to **Q3 1989** (early quarters `reliable: false`, Domain-only basis); the `gold_coast` aggregate starts Q3 2016 (40 quarters).
  - **Stale pocket:** 9 docs untouched since 2026-02-25 — eight tiny hinterland/rural suburbs (woongoolba, norwell, neranwood, numinbah_valley, luscombe, austinville, advancetown, natural_bridge) **plus main_beach** (a real premium suburb outside the refresh scope — include it before building the all-suburb aggregate).
- **Live listings:** 2,878 `for_sale` docs across **68 GC suburbs** (surfers_paradise 351, palm_beach 170, broadbeach 158, hope_island 155…). Good for point-in-time GC-wide stock composition. Gaps: southport, burleigh_heads, main_beach etc. have cadastral stubs but no active scraping.
- **Sold records:** 4,058 across 71 suburbs, but deep history only in the 8 tracked suburbs (653 robina → 254 worongary); other suburbs have a thin early-2026 window only. So GC-wide **volume/DOM/turnover from our own sold pipeline is not currently representative** outside the tracked 8 — the indexed-prices union series is the reliable wide asset.
- **SQM asking prices:** 3 postcodes (4226/4220/4227), weekly 2009-05-01 → 2026-08-28, houses/units splits. Scraper is trivially extensible (postcode dict).
- **Capital-city asking prices (Sydney/Melbourne/Brisbane): ALREADY IN THE DB** — `precomputed_macro_indicators.national_asking_prices`, weekly `{date, houses, units}` — but **frozen at 2026-03-13; the writer was retired** and `fetch_macro_indicators.py` preserves-without-refreshing it. Reviving it is a ~30-line fetcher using the same SQM pattern with `region=` instead of `postcode=`.
- **Macro suite:** RBA cash/mortgage/term-deposit rates, QLD CPI to 1948, Brent, FRED national house price index, mortgage-impact scenarios — all current (updated 2026-09-06).
- **ABS signals:** WPI, lending, dwelling completions, CPI, HSI — all **QLD state-level** (`REGION=3` hardcoded). NSW=1 / VIC=2 is a config change per dataflow, not new plumbing.
- **We hold zero auction/clearance data** (verified per Rule 8 — no fields by any related name).
- Stale-doc findings along the way: `property_data.properties_for_sale` no longer exists (CLAUDE.md stale — only `suburb_median_prices` remains); MarketSignals "Consumer Spending" still shows the dead ABS Retail Trade figure (known defect, memory'd).

---

## 3. External availability — source by source

### 3.1 SQM Research — the workhorse (free, but ToS-sensitive)

Verified by fetching actual pages. Every free chart page embeds the **full series history as inline JSON** (`var data = [...]` + Highcharts) — one curl per series, exactly the pattern `scrape_sqm_asking_prices.py` already parses. No login; no XHR endpoint needed.

**Gold Coast has its own region series** — `qld-Gold Coast` plus Main / North / South / West / Hinterland — alongside postcode, suburb, and capital-city (`type=c`) selectors:

| Series | GC region | Bris/Syd/Melb | History | Frequency |
|---|---|---|---|---|
| Asking prices (houses_all/3bed, units_all/2bed, combined) | ✅ | ✅ | weekly since 2009-05 | weekly |
| Stock on market (age buckets r30/r60/r90/r180/r180p; `?hu=1` houses-vs-units) | ✅ | ✅ | monthly since 2010-01 | monthly |
| New listings (= r30 bucket) / old listings (= r180p) | ✅ | ✅ | monthly 2010→ | monthly |
| Vacancy rates (raw counts + rate) | ✅ (GC Main verified) | ✅ | monthly since **2005-01** | monthly |
| Weekly rents (same splits, $/wk) | ✅ | ✅ | weekly since 2009-08 | weekly |
| Rental yield / total rent listings | same selector (pattern inferred, unverified) | ✅ | — | — |
| Days on market | ❌ no free series (only age buckets) | ❌ | — | — |
| Distressed listings | ❌ paid ($59.95/mo) | — | — | — |

⚠ **ToS:** SQM's terms prohibit scrapers and require written permission for commercial republication. **We already ingest and display SQM postcode data on-site**, so this is an existing exposure, not a new one — but a GC-wide page would widen it. Options: seek written permission/attribution arrangement (media cite SQM routinely), or keep SQM series internal and lean on licensing-clean sources for published charts. **Decision for Will.**

### 3.2 Cotality (formerly CoreLogic) — free indices + the only free weekly GC auction series

- **Daily Home Value Index — free unauthenticated JSON**: `https://au-indices.cotality.com/asx.json` — daily index + quarterly/annual change for Sydney, Melbourne, **"Brisbane (inc Gold Coast)"**, Adelaide, Perth, 5-cap aggregate, plus a full **365-day daily back-series** per city. Monthly block adds **"Brisbane" excluding Gold Coast** + house/unit splits. **No standalone GC index** — GC exists only as the delta between the two Brisbane composites. Trivial to ingest daily; marked "Proprietary", no republication licence.
- **Weekly auction PDFs (⭐ the find of this scoping):** twice-weekly free PDFs on `discover.cotality.com/hubfs/` — preliminary + finalised clearance — include a **Regional SA4 table with a Gold Coast row** (verified: w/e 16 Aug 2026 — GC 46.2% clearance, 64 auctions). This is the **only free, systematic, weekly Gold Coast auction clearance series in existence**. Capitals in the same PDFs. Caveats: PDF parsing, semi-predictable filenames, and GC weekly volumes are small (25–65 auctions) so single weeks are noisy — publish as 4-week rolling.
- **Monthly Housing Chart Pack** (40pp PDF, ungated on hubfs): capitals + combined regionals — days on market, vendor discount, clearance, rents/yields, listings. **No GC breakout.** Useful for capital-city DoM/vendor-discount comparisons (which SQM can't provide).
- **Mapping the Market:** capitals only — zero Gold Coast (verified via ArcGIS item JSON).

### 3.3 PropTrack — free monthly PDFs, no GC in the release

Monthly Home Price Index PDFs are **directly linked, ungated, full archive since Apr 2022** (capitals + rest-of-state). PropTrack computes a Gold Coast SA4 median (quoted in realestate.com.au news: $1.18M, June 2026) but doesn't publish it in the free release; realestate.com.au suburb pages are behind Kasada bot protection with explicit anti-scrape ToS — **not a viable pipeline**. Quarterly Rental Report PDFs also free.

### 3.4 Domain — GC covered, but bot-blocked; API is the clean path

Entire domain.com.au estate returns 403 (Akamai) to non-browser fetches from this VM. Their **quarterly House Price Report includes a Gold Coast regional median series** (house + unit) and their **Rent Report/vacancy series breaks out GC** (GC = Australia's most expensive rental market, $950/wk houses, 0.5% vacancy, June 2026) — but as articles, practically **cite-only** (numbers echo into unblocked news each quarter). The official **Domain developer API `GET /v1/salesResults/{city}`** returns weekly auction JSON (clearance, volumes, medians) for Sydney/Melbourne/Brisbane etc. — compliant and clean, but **no Gold Coast city**; free-tier availability unverified.

### 3.5 ABS — the licensing-clean backbone (all CC BY 4.0)

- **Total Value of Dwellings (TVD)** — the successor to the discontinued RPPI (no monthly ABS price index exists; verified absent). Quarterly: **Table 2 gives median transfer price + transfer counts for Greater Brisbane / Sydney / Melbourne (GCCSA)** back to ~2014; Table 1 gives state mean price/stock back to 2011. **No Gold Coast breakout** (GC = "Rest of Qld"). ~12-week lag. **This is the republishable capital-city price + volume series.**
- **Building Approvals** — monthly, **and Gold Coast IS broken out at SA4 + LGA** (GCCSA back to 2001). The best free ABS series with true GC granularity; direct GC-vs-Greater-Bris/Syd/Melb dwelling-supply chart.
- **Regional Population** — annual ERP, GC at LGA + SA4 since 2001.
- **Lending Indicators** — now quarterly (since Dec-2024 qtr), state-level only.
- **WPI (quarterly) + Household Spending (monthly)** — state-level, already ingested for QLD; NSW/VIC = key change.

### 3.6 QLD government

- **Bulk sales transactions (QVAS): paid-only via brokers** — no free QLD transaction dataset exists. Statutory land valuations are free (not sale prices).
- **QGSO Residential Land Development Activity** — free quarterly, Gold Coast (C) LGA: lot approvals/registrations, vacant-land and dwelling sales counts.
- **RTA median rents (⭐)** — free quarterly Excel: **median weekly rent by postcode/suburb/LGA, by dwelling type and bedroom count, plus bonds lodged/held** — bond-based *actual* rents, methodologically stronger than portal asking rents, with full Gold Coast granularity. QLD-only (capitals comparison needs SQM/Domain rents). © State of Qld, no explicit CC licence — attribution route, verify terms.

### 3.7 Sentiment & banks (context tiles, cite-only)

- **NAB Residential Property Survey** — free quarterly PDF since 2011: **QLD-vs-NSW/VIC property index, 12-month price and rent forecasts by state**. Best free state-level housing sentiment.
- **Westpac–MI Consumer Sentiment** — monthly free PDF (predictable URL pattern): national "time to buy a dwelling" + house price expectations. State detail is paid. MI copyright — quote-with-attribution only.
- **RBA** — free XLSX/CSV tables (housing lending rates, housing credit, debt-to-income) — national only. Chart Pack 8×/yr.
- CBA HSI / ANZ-Roy Morgan — no housing signal or no free state split; skip.

### 3.8 Auction clearance — summary

No free weekly GC series exists **except Cotality's Regional SA4 table** (§3.2). Ray White publishes weekly group-wide wraps + annual GC event articles (84% at The Event, Jan 2026) — episodic, single-network. Domain auction pages/API are capitals-only. Apollo Auctions homepage widget is network-wide with no archive.

---

## 4. Metric-by-metric: what the GC-wide page could show

**Tier A — buildable now from data we already hold (no new source):**

| Chart | GC-wide side | Bris/Syd/Melb side |
|---|---|---|
| Median price + QoQ/YoY growth + 10-yr indexed race | Extend `precompute_gold_coast_aggregate.py` to a transaction-weighted aggregate over all ~77 suburb docs (Q3 2016→) | *(needs Tier B source below)* |
| Asking price trends | SQM `qld-Gold Coast` region *(Tier B fetch)* — postcode series held since 2009 | **Already in DB** (frozen 2026-03-13) — revive fetcher |
| Active listings composition | 2,878 live listings across 68 suburbs, today | — |
| Macro/crash-risk signals (WPI, lending, completions, CPI, rates) | QLD series already live | NSW/VIC = region-key config change |
| Mortgage-impact scenarios, RBA rates, CPI | Already in `precomputed_macro_indicators` | national by nature |

**Tier B — small fetchers, same patterns we already run (each ~½–1 day):**

| Chart | Source | Notes |
|---|---|---|
| GC region asking prices + capitals (weekly, 2009→) | SQM inline JSON | Same regex pattern as existing scraper; also fixes the frozen city series. ⚠ ToS decision |
| Stock on market + new/old listings (GC + capitals, monthly, 2010→) | SQM | Age buckets are a genuinely good "market heat" visual |
| Vacancy rates (GC regions + capitals, monthly, 2005→) | SQM | Raw numerator/denominator included |
| Weekly rents (GC + capitals, 2009→) | SQM | Pairs with RTA for bond-based cross-check |
| Daily home value index, 5 capitals (365-day window) | Cotality `asx.json` — clean unauthenticated JSON | GC only inside Brisbane composite; "Brisbane inc GC vs ex GC" gap is itself a publishable GC signal. Proprietary — likely cite/attribution |
| Capital-city median price + transfer volumes (quarterly, 2014→) | **ABS TVD Table 2 (CC BY — clean to republish)** | The licensing-safe capitals price series to pair with our own GC medians |
| Building approvals: GC SA4/LGA vs Greater capitals (monthly, 2001→) | ABS (CC BY) | True GC granularity; new supply-side chart the suburb pages don't have |
| Population growth GC LGA vs capitals (annual, 2001→) | ABS (CC BY) | Context tile |
| RTA median rents by GC postcode/LGA (quarterly) | RTA Excel | GC rent detail no competitor publishes for free |

**Tier C — moderate builds (PDF parsing / weekly cadence):**

| Chart | Source | Notes |
|---|---|---|
| **GC auction clearance (weekly)** vs capitals | Cotality twice-weekly PDFs | Only free GC clearance series anywhere; publish as 4-week rolling (25–65 auctions/wk is noisy). PDF table parse + filename discovery |
| Capital-city days on market + vendor discount | Cotality monthly Chart Pack PDF | Lets us pair our own GC DoM/vendor-discount with capitals |
| PropTrack monthly HPI (capitals) | Free PDF archive since 2022 | Alternative/corroborating index; no GC |
| QGSO land development activity (GC LGA, quarterly) | Free XLSX | Supply-side depth |

**Tier D — cite-only (no pipeline; quote with attribution in narrative/pulse):**
Domain quarterly GC median + GC rents/vacancy (bot-blocked), NAB state sentiment + forecasts, Westpac national dwelling sentiment, REIQ media releases.

**Tier E — not obtainable / paid / doesn't exist:**
- A free **Gold Coast price *index*** (daily or monthly) — doesn't exist anywhere; our own transaction series is the GC price story (a competitive advantage, not a weakness).
- Bulk QLD sales transactions — QVAS brokers, paid (hundreds–thousands $; would make our GC-wide DoM/volume/vendor-discount bulletproof if ever bought).
- Free GC days-on-market from any third party — own data only (currently representative for the 8 tracked suburbs; widening = scaling our own sold detection GC-wide, which briefly ran in early 2026).
- SQM distressed listings ($59.95/mo), realestate.com.au suburb data (Kasada + ToS), Melbourne Institute state sentiment (paid).

**Charts that would NOT carry over well:** turnover rate, price adjustments, vendor discount, new-listings-from-Domain (own-scrape metrics whose GC-wide denominators we don't yet have — need either GC-wide sold detection or QVAS); absorption rate beyond the 3 PropRadar suburbs; forecast/DNA/journey statics (per-suburb hand-built).

---

## 5. Answers to the three questions

1. **Can we get the data?** Yes. Price (own series + ABS TVD for capitals), asking prices, rents, vacancy, stock on market, new listings, auction clearance (incl. GC!), building approvals, population, lending, sentiment — all obtainable free. The only things money can't freely buy: a GC-only price index (nobody publishes one — ours is the differentiator) and bulk transaction records (QVAS, paid).
2. **Scrape or available?** Roughly half is *cleanly* available (Cotality JSON feed, ABS API/XLSX under CC BY, RTA Excel, PropTrack/Cotality ungated PDFs, NAB/Westpac PDFs); the SQM family is "available via the scrape we already do" (inline JSON, trivial, but ToS-sensitive); Domain/realestate.com.au are actively bot-blocked → cite-only.
3. **What could we show now vs later?** Tier A ships from existing data; Tier B adds the full comparison layer with ~a week of small fetchers; Tier C (auction clearance + capitals DoM) is the most differentiated addition and the most build effort.

## 6. Licensing posture (needs Will's call before publishing)

- **Clean to republish:** ABS (CC BY 4.0, attribute), QGSO/data.qld (CC BY, check per dataset), our own computed series.
- **Attribution/verify:** RTA (© State of Qld, no explicit licence), RBA (generally reproducible with attribution).
- **Cite-only unless permission obtained:** SQM (ToS bans scraping + commercial republication — *existing exposure*: we already publish SQM postcode charts; a written-permission request would cover both), Cotality ("Proprietary"), PropTrack, Domain, NAB, Westpac-MI.
- Editorial rules apply as usual: data-only, no advice, no predictions; conditional framing for any forward-looking sentiment/forecast figures (NAB's are *their* survey forecasts — report as such).

## 7. Recommended build order (if green-lit)

1. **Revive + extend the SQM city fetcher** (fixes the frozen `national_asking_prices`, adds `qld-Gold Coast` region) — also independently valuable because the stale series sits in a live-served collection. *(Not dispatched during scoping — it presupposes the go-ahead and the ToS decision above.)*
2. **All-suburb GC aggregate** in `precompute_gold_coast_aggregate.py` (77-suburb transaction-weighted median/growth series).
3. **ABS TVD + Building Approvals fetchers** (CC BY backbone for capitals price/volume + GC supply).
4. **Cotality daily-index JSON + weekly auction PDF parser** (GC clearance, 4-week rolling).
5. **RTA rent Excel ingest**; NSW/VIC keys in `fetch_abs_market_signals.py`.
6. Page assembly as a new "gold-coast" geography through the existing precompute → market-insights/market-narrative → MarketMetricsPage chain, plus a GC-wide market_pulse.

All new fetchers get Rule 7/7b heartbeats (`job_run` + zero-output assertions) from day one.

---

*Compiled from four parallel research agents (page/code inventory, DB inventory, SQM verification, Cotality/PropTrack/Domain verification, ABS/QLD-gov, banks/auctions) — all external claims verified by fetching actual pages/PDFs/JSON on 2026-09-12 unless marked unverified.*

---

## Addendum (2026-09-12, on Will's request): "Which Signals Actually Lead Prices?" at GC level

The suburb-page signals board is the **IndicatorsExplorer** (shared engine, mounted by the `/news` split prototype via `MarketFlowProto`). It reads one static file — `public/data/leading_indicators.json` — carrying 82 quarters (2006→2026), price-momentum series (pooled + 3 suburbs), and 10 indicators each with full series + measured lag + r. **The matched-movement circles already exist in the engine**: in Actual-timing mode with one indicator, it circles the indicator's turning points, links each to the price-momentum turn ~lead later ("prices follow ~N mo later"), and draws the "if lead holds" projection — all computed client-side. A GC version therefore needs only a new JSON: GC-wide momentum series + recomputed lag/r. No chart code.

**First-pass GC-wide recomputation (done today):** composite built from `rolling_12m_median_series` across the 50 suburbs with ≥90% coverage 2017-Q3→2026-Q2, fixed transaction-count weights; momentum = YoY of the composite (31 pts, 2018-Q3→2026-Q1; latest +0.5% vs +9.5% a year earlier). Cross-correlated against the indicator series already in the JSON:

| Indicator | Old (3-suburb pooled, 2008–26) | GC-wide r at same lag | Notes |
|---|---|---|---|
| **New housing lending (QLD)** | **+4q, r 0.76** | **r 0.77 (n=31)** | **Survives cleanly — same 4-quarter lead. This is the headline number.** |
| Rate of sale | +2q, 0.73 | 0.75 | holds |
| Inflation (QLD CPI) | −3q lag, 0.72 | 0.86 | still a lagger |
| Unemployment change | −1q, −0.67 | −0.73 @ 0q | holds |
| Consumer spending | +7q, 0.56 | 0.64 | holds |
| Job vacancies | +2q, 0.39 | 0.62 | stronger on short window |
| ASX / cash rate / cash-rate change / clearance | various | unstable | short-window artifacts (e.g. clearance "r −0.91 @ +7q" on n=18 is spurious); pooled series shows the same drift on the identical window |

**Methodology decisions for production:** (1) keep the lag *structure* from the deep 2008–2026 pooled analysis and recompute r at those fixed lags on the GC series — don't re-pick best lags on a 31-point window; (2) weighting: the volume-weighted composite is dominated by the northern growth corridor (pimpama, upper_coomera, coomera, ormeau are the top weights) — decide whether that's the intended "Gold Coast" or whether to cap/stratify weights; (3) the wide-suburb rolling series start 2017-Q2 — a deep (2006→) GC series needs the union precompute extended, or the page ships with the 2018→ window honestly captioned.

**Build steps:** extend `precompute_union_prices.py`/aggregate for the GC momentum series → generator script writes `public/data/leading_indicators_gc.json` (same schema, `price.pooled` = GC-wide) → mount IndicatorsExplorer on the GC page. Copy updates: caption r values, and the prototype's existing "tested against Gold Coast house-price momentum" line finally becomes literally true.
