# Market Analysis Frameworks — Fields Report Brief

*Drafted: May 2026 — for the flagship Fields property market update report*
*Geographic focus: Gold Coast (Robina 4226, Burleigh Waters 4220, Varsity Lakes 4227)*

---

## 1. The macro framework — what Fields will track and report

Professional analysts (RBA, Treasury, CoreLogic/Cotality, Domain, ANZ-CoreLogic, NAB Quarterly Property Survey) read residential property as a function of three forces: **money cost** (cash rate, lending standards), **household formation** (migration, demographics), and **the dwelling pipeline** (approvals → starts → completions vs absorption). Fields' macro page tracks one indicator from each, plus a stress dial.

| # | Indicator | What it is | Why it matters | Source / cadence |
|---|-----------|------------|----------------|------------------|
| 1 | **Cash Rate Target** | RBA's overnight policy rate. **Currently 4.35%** after a 25bp hike at the May 2026 meeting (8 of 9 board members in favour). Market pricing assumes a path toward 4.70% by year-end. | Mortgage rates, serviceability calculations, and asset-price discount rates all anchor here. A 25bp move shifts borrowing capacity ~2-3%. | RBA — monthly decision, quarterly Statement on Monetary Policy (SMP) |
| 2 | **APRA serviceability buffer** | Banks must assess loans at the contract rate **+3 percentage points**. Confirmed unchanged in July 2025 review. | Determines how much a borrower can actually borrow, regardless of headline rate. The buffer is the real "tightening" lever. | APRA — reviewed annually |
| 3 | **APRA DTI speed limit** (NEW Feb 2026) | New macroprudential limit: ≤20% of new mortgage lending may be at debt-to-income ≥6×, applied separately to owner-occupier and investor books. | First active macroprudential constraint since 2017. Caps the top of the buyer pool, especially in high-priced markets. | APRA letters to ADIs |
| 4 | **Net Overseas Migration (NOM)** | Permanent + long-term arrivals minus departures. **306,000 in 2024-25**, down from 429,000 the prior year. | Direct demand for dwellings (~2.5 persons per household = ~120k household formations). | ABS Cat. 3412.0, financial year + quarterly |
| 5 | **QLD Net Interstate Migration** | **+21,595 persons in year to June 2025**. Queensland and WA the only states with material net gains. | Inflow from NSW/VIC supports SEQ price floor independent of NOM. | ABS Cat. 3101.0, quarterly |
| 6 | **Building approvals** | Leading indicator, ~18-24 months ahead of supply. **March 2026: QLD total dwellings -6.4% m/m, private houses +7.2%**. | Dwellings approved today determine completions in 2027-28. The approvals→completions gap is the structural shortage signal. | ABS Cat. 8731.0, monthly |
| 7 | **Dwellings completed** | Coincident supply. Tracks against NOM + NIM-derived household demand. | Shortage = approvals consistently below household formation for 3+ years. Currently the case nationally. | ABS Cat. 8752.0, quarterly |
| 8 | **Cordell Construction Cost Index (CCCI)** | Cotality measure of build costs. **+1.0% Dec 2025 quarter, +2.5% YoY** — smallest annual rise since March 2002. | Replacement cost is the long-run anchor for established home prices. When build costs rise faster than prices, new supply slows. | Cotality, quarterly |
| 9 | **Vacancy rate (SQM Research)** | Share of rental stock advertised. **National 1.0% (April 2026); Gold Coast Main 1.1%**. Pre-COVID decade average ~2.5%. | Sub-2% vacancy means tenant-side bidding pressure. Yields rise → investor demand returns. | SQM Research, monthly |
| 10 | **Household debt-to-income** | Australia ~185% — among the highest in the developed world. | Caps how far prices can run without income growth. RBA Financial Stability Review tracks tail-risk (severe stress) and arrears separately. | RBA Chart Pack, quarterly |
| 11 | **Help to Buy + 5% Deposit Scheme** | Help to Buy launched 5 Dec 2025 (gov takes 30-40% equity, 2% deposit, $100k/$160k income caps). Home Guarantee scheme: 5% deposit, no LMI, place limits removed in 2026. | First-home-buyer demand is policy-driven. Concession schedules move marginal buyers in/out of the pool. | Treasury, Housing Australia |
| 12 | **QLD First Home concession** (1 May 2025) | Full transfer-duty exemption on **new** homes regardless of price; existing homes exempt to $700k, taper to $800k; vacant land uncapped. $30k First Home Owner Grant extended to 30 June 2026. | Concentrates entry-level FHB demand into specific price brackets and house types. Distorts the lower-quartile median. | Queensland Revenue Office |

**Frequency rule for the report:** macro figures are quoted as "as at [month] [year]" with the source dataset and release date. Anything older than 90 days at publication needs an explicit "latest available" caveat.

---

## 2. The micro framework — suburb-level dashboard

The micro panel for each Fields report covers one suburb. The metric set borrows from CoreLogic Property Pulse, REIQ Quarterly, Domain Suburb Profiles, and academic real-estate finance literature, then strips the noisy ones.

| Metric | Definition | Interpretation | Common errors | Fields source |
|--------|------------|----------------|---------------|---------------|
| **Indexed price (hedonic)** | Quality-adjusted price level, rebased to 100. Cotality Hedonic methodology controls for property attributes per transaction (beds/baths/land/condition/location) — see §4. | The *only* honest single-number price track. Smooths composition and quality drift. | Treating 0.3% monthly moves as signal — see §3. | Cotality Hedonic series + Fields' own suburb-level reconciled valuations |
| **Median sale price (12-mo rolling)** | Middle transaction price across last 12 months. | Useful as a level reference, not a change indicator. Always paired with volume and an indexed comparison. | Quoting single-month medians on small samples (<30 sales). YoY moves on composition shifts (one Hedges Avenue sale moves a $1.5M median by 5%). | Fields DB transaction data |
| **Sales volume (12-mo)** | Count of arms-length transactions. | Volume is the most under-reported number. A 10% price rise on 30% lower volume is not the same market as a 10% rise on stable volume. | Conflating listing count with sales count. | Fields DB |
| **Days on Market — distribution** | Time from list to unconditional contract, reported as median + interquartile range. National median **30 days (Q1 2026)**, capital-city range Perth 9 → Darwin 47. <35 days = sellers' market, 35-90 = balanced, >90 = buyers' market. | The full distribution — not just the median — shows whether the suburb has a long tail of stale stock (a lead indicator of weakening). | Reporting only the median hides the tail. Mixing private treaty + auction times. | Fields DB |
| **Sale-to-list ratio / Vendor discount** | (Sale price ÷ first list price) – 1, median across all sales. Negative = discount, positive = above-list. | Direct read on price negotiability. >5-6% discount widening is an early warning of a turning Brisbane/SEQ market (per Cotality). | Using "current asking price" not "first listed price" — vendors revise lists, so sale-to-current-list understates discount. | Fields DB (requires first-list capture, which scraping pipeline preserves) |
| **Stock on market / Months of supply** | Active listings ÷ avg monthly sales. <6 months = sellers' market, >6 = buyers'. Gold Coast active listings reportedly **~20% below 5-year average** (Q1 2026). | Tightest measure of bargaining power. | Confusing total-listings (includes withdrawn/relisted) with unique-property listings. | Fields DB scraping pipeline |
| **Rent ($/wk) and gross yield** | Median advertised rent ÷ median price × 52. Gold Coast house rent ~$780/wk, units ~$600/wk. | Yield is the value floor — once it crosses cash deposit returns adjusted for tax, investor demand returns. | Comparing advertised rents to sold prices (timing mismatch). | SQM/REIQ + Fields DB |
| **Vacancy rate (postcode)** | % of rental stock advertised. Gold Coast Main 1.1%, national 1.0% (April 2026). | Sub-2% = rents likely +6-8% next 12mo. | Postcode-level samples can be tiny — annual averaging required for outer suburbs. | SQM Research |
| **Auction clearance rate** | % of auctions clearing on the day. National 57.3% (week ending 2 May 2026). | **Only meaningful in auction-dominated markets** (Sydney inner ring, Melbourne). The Gold Coast is mostly private treaty — see §3. | Reporting GC clearance with low N (often <20 auctions/week). | Cotality, weekly |
| **Buyer/seller demographics** | Age, household type, owner-occupier vs investor share at sale. | Tells you who is currently bidding — predicts what stock will sell in the next cycle. | Generic ABS census data is 5+ years stale by mid-cycle. Mortgage data (LVR, LMI, FHB share) is more current. | ABS + Fields scraped buyer profile signals |
| **Supply pipeline** | DAs lodged, DAs approved, off-the-plan units in marketing. | Tomorrow's sales volume. A flat off-the-plan pipeline + strong pre-sales = price support. | Counting marketing brochures as guaranteed completions. | GCCC PD Online + Fields enrichment |
| **Comparable sales selection** | 3-8 properties matched on: distance (≤500m preferred), sale recency (≤6mo), beds/baths, floor area (±15%), land size (±20%), condition, position, view. Fields applies floor-area, condition, location and view adjustments → weighted mean. | The honest single-property valuation. Confidence reflects the *spread* of adjusted comps, not just the mean. | Picking comps to support a target price. Ignoring adjustment magnitude (a comp needing >15% adjustment isn't comparable). | Fields' `precompute_valuations.py` reconciled valuation |

---

## 3. Signal vs noise — what Fields will deliberately not report

Fields' credibility depends on refusing the noisy data points other agencies quote. Each item below: what it is, why it's misleading, and what we report instead.

1. **Single-month median moves on <30 sales.** Suburb-level monthly medians swing 5-10% on composition alone. We will not run a "Burleigh Waters up 4% in April" headline. *Instead:* indexed price + 12-month rolling median + sales count.

2. **Asking-price indices.** SQM and others publish asking-price series. They suffer from selection bias (only listed properties; vendors anchor on the prior cycle), and the gap between asking and sale price is itself the volatility. *Instead:* sale-to-list ratio, applied to closed transactions.

3. **Auction clearance rate on the Gold Coast.** Most GC sales are private treaty. Weekly auction samples are <30, dominated by prestige and probate. The number is real but unrepresentative of the broader market. *Instead:* days-on-market distribution and sale-to-list ratio.

4. **Year-on-year median comparison without composition control.** A suburb that sold five $3M canal homes this April but none last April will print a fake +30% YoY. *Instead:* hedonic / indexed comparison, or stratified medians (Domain methodology).

5. **"Most expensive sale this week" / "record price" headlines.** Single transactions are not market signals. They are PR for the agent who sold them. *Instead:* aggregate top-decile movement over the trailing year.

6. **Total listing count without distinguishing relisted/withdrawn.** Online portal counts include relisted properties — same dwelling, new listing ID. *Instead:* unique-property listings, deduplicated on address.

7. **"Days on market" from auction campaigns reported alongside private-treaty DOM.** Auction campaigns end at the auction date; private-treaty DOM ends at the unconditional contract. Mixing them flatters the median. *Instead:* split DOM by sale method, or report private-treaty-only.

8. **Forecasts of price growth as a single number.** Internal forecasts can inform planning, but published predictions are opinion presented as data. We report the *current state* of leading indicators (vacancy, approvals, rates) and let the reader weigh them.

9. **Investor "yield + capital growth" totals.** Combining rental yield with hedonic capital growth as if they were one return ignores tax, vacancy losses, maintenance, and selection bias in advertised rents. *Instead:* report each separately with caveats.

---

## 4. Methodology — Fields' chosen approaches and why

### 4.1 Indexed prices over median (hedonic over arithmetic)

The four methods of measuring price change in housing — median, stratified median, hedonic, and repeat sales — each handle composition differently:

- **Simple median** (REIQ-style): cheap, easy, but volatile. Quality drift contaminates every reading.
- **Stratified median** (Domain): buckets dwellings by type, long-term price tier, and SEIFA score; calculates within-stratum changes; reweights to the stock. Better, but only as good as the strata definitions.
- **Hedonic** (Cotality / CoreLogic): models price as the sum of attribute contributions (bed, bath, land, location, condition) using regression. Each transaction yields an *implied* index point even if the property only sold once. **This is the methodology Fields adopts at suburb level** because it uses every transaction and adjusts for quality.
- **Repeat sales** (Case-Shiller): only properties that sold ≥2 times in the window. Eliminates between-property heterogeneity but ignores new builds, single-owner homes, and is sensitive to renovations between sales. Strong in mature US markets, weaker in Australian outer suburbs.

**Fields' choice:** hedonic at suburb level, with a stratified-median sanity check at postcode level. Repeat-sales only used as a 10-year-plus cycle indicator on stable inner Gold Coast suburbs where N is sufficient.

### 4.2 Comparable sales valuation over CatBoost ML

Fields stores both a CatBoost ML estimate (`iteration_08_valuation`) and a comparable-sales **`reconciled_valuation`**. We report the latter on property pages. Reasons:

- Comparable sales is auditable — every adjustment is traceable to a real sold property within 500m.
- ML estimates are accurate in aggregate but opaque per-property; a buyer cannot test the result.
- Confidence intervals on the comparable-sales method derive from the *weighted standard deviation* of adjusted comps (Fields uses 1.645 × σ for a 90% CI). This is honest about disagreement among comps.
- Fields publishes the **comparable range** in headlines, not a single figure, especially above $2.5M where comp scarcity widens the CI dramatically.

### 4.3 Time horizons — when to use which

| Horizon | Use for | Caveat |
|---------|---------|--------|
| 1 month | Direction only, never magnitude | Sub-30-sales suburbs: ignore entirely |
| 12 months | Headline change, paired with volume | Composition risk — verify with hedonic |
| 5 years | Cycle context — was the last move structural or rate-driven? | Cycle-to-cycle, not peak-to-peak |
| 10 years | Long-run growth, real (CPI-adjusted) returns | Compare nominal *and* real — at 3-4% CPI, the real number tells the story |
| Full cycle | Top-of-market vs trough comparison (e.g. 2017 peak → 2019 trough → 2022 peak → 2026) | Use real prices and adjust for stamp-duty/tax regime changes |

**Real vs nominal:** all multi-year prints are reported in both nominal and real (CPI-deflated) terms. The 5-year nominal Gold Coast figure looks great; the 5-year real figure tells the story of how much *purchasing power* a homeowner gained.

---

## 5. Suburb-specific dimensions

### 5.1 Robina (4226)

The dimensions that matter:

- **Master-planned vs older estate split.** Robina is dominated by the Robin Group / Robina Land Corp planned releases (1980s-2010s). Newer pockets (Robina Quays, Cottesloe Reach) trade on a different multiple than older Bond Estate. Always report median and indexed price by **estate**, not just suburb.
- **House (61% of stock) vs unit/townhouse (39%).** Roughly two-thirds detached houses, the rest apartments/townhouses. Median by dwelling type is the minimum split.
- **Robina Town Centre / hospital / Bond Uni / train station proximity.** Walking-distance-to-station premium is a measurable hedonic adjustment Fields can quantify.
- **3.3 bedrooms per dwelling, owner-occupier 64%.** Stable family-buyer base. Investor share at sale matters because it shifts with rental yield.
- **Master-planned covenant constraints** (build envelope, fence height, colour palette) — these reduce variance in stock and tighten comparability of comps.

### 5.2 Burleigh Waters (4220)

The dimensions that matter:

- **Canal-front vs non-canal split.** Canal-front = direct waterway access, larger lots, premium ~30-50% over non-canal equivalents. Always split medians by **canal/non-canal** — combining them is the biggest reporting error in this suburb.
- **Flood overlay vs ICA flood zone.** Two distinct flood definitions: GCCC City Plan overlay (planning-conservative) and ICA Insurance Probability Zones (insurer-pricing). Many properties under the council overlay are *not* in any ICA zone — i.e. insurers don't price them as flood risk even though council does. Fields reports both, and the FloodWise Property Report is the recommended source.
- **Insurance availability.** Some insurers refuse cover or load premiums by thousands on canal properties. ICA reports ~91,000 QLD properties at ≥2-5% annual flood probability. ICA paid out >$1.5bn on Cyclone Alfred (2025), so premium pressure is real and ongoing.
- **Family-premium suburb with limited supply.** Land-locked between Burleigh Heads, ridge, and motorway — physical supply ceiling supports prices.
- **Median house price ~$1.4-1.68M (2026, sources vary)**, capital growth ~10% YoY. Wide source variance is itself a signal that a single median is unreliable here — use Fields' indexed price.

### 5.3 Varsity Lakes (4227)

The dimensions that matter:

- **Lake-frontage vs non-lake.** Direct equivalent of canal-front in Burleigh Waters. The lake premium is measurable and significant.
- **Townhouse / unit dominance.** Historically high townhouse share. Dwelling-type split is non-negotiable for honest reporting.
- **Bond University proximity.** Student/young-professional rental demand floor — yields tend to be higher than the surrounding family suburbs.
- **Younger demographic, more transient ownership tenure.** Higher turnover → more comparable sales available, but more renovation drift between repeat sales (favours hedonic over repeat-sales index).
- **Population ~14,500** with mixed family/student/retiree base.

### 5.4 Cross-suburb dimension: Coomera Connector + 2032 Olympics + Cross River Rail

All three suburbs sit within 30 minutes of the Coomera Connector corridor and benefit from the new Cross River Rail Gold Coast extensions (Hope Island Station). The 2032 Olympic infrastructure spend ($4.5bn announced budget, with separate transport infrastructure pipeline) underpins a SEQ-wide premium that is *priced in* but not yet completed. We will report infrastructure progress as a coincident factor, not as forecast price growth.

---

## 6. Cycle context — May 2026

**Where we are:**

- **RBA cash rate 4.35%** after the May 2026 hike. Market path implies 4.70% by year-end. Headline inflation 4.6% (March), expected to peak at 4.8% mid-2026; underlying inflation expected above 3% until mid-2027.
- **Macro stance: late-cycle tightening.** APRA buffer 3pp held, DTI speed limit (≤20% at DTI≥6×) live since Feb 2026 — first active macroprudential tool in nearly a decade.
- **Migration:** NOM 306k (FY25), QLD net-interstate +21,595 (year to June 2025). Brisbane population +2.1%. Demand pressure remains strong, particularly for SEQ.
- **Supply:** QLD March 2026 dwelling approvals -6.4% m/m (private houses +7.2%); construction cost growth at a 24-year low (CCCI +2.5% YoY). Approvals → completions gap continues to widen.
- **National prices:** Cotality Home Value Index +0.3% in April 2026 (slowest in nearly a year). Sydney/Melbourne -0.6%, Perth +2.1%, Brisbane +1.1%, Adelaide +1.2%.
- **Gold Coast:** Houses ~$1.32-1.40M city-wide median, +10-12% YoY. Units median ~$956k (overtook Sydney median in Oct 2025 — first time on record). Vacancy 1.1%, listings ~20% below 5-yr average.
- **Household stress:** Severe-stress mortgagor share has *declined* since mid-2024 (RBA FSR Mar 2026). Arrears low. Some investor DTI risk creeping up — exactly what the new APRA limit targets.

**The question Fields' report should answer:** with rates rising, supply still constrained, and migration easing from peaks but well above pre-COVID, which way does the southern Gold Coast resolve in H2 2026?

We will not predict. We will lay out the indicator state and the conditional logic ("if vacancy stays sub-1.5% and approvals don't recover, then…").

---

## 7. Open questions / what we admit we don't know

A short list, prominent in the report:

1. **Sub-suburb sample size.** Burleigh Waters canal-front had ~X transactions in the last 12 months (to be calculated). Below 30, indexed prices have wide confidence bands. We will state N every time.
2. **Selection bias on sold-only data.** Hedonic indices use sold transactions to estimate the value of *unsold* stock. If the marginal seller is unrepresentative (e.g. distressed, divorce, deceased estate), the index drifts. We will not pretend this is solved.
3. **Insurance premium trajectory.** ICA paid ~$3.5bn on extreme weather in 2025 + Cyclone Alfred ($1.5bn). Premium pricing for 2026-27 is not yet in published indices. The flood-zone premium adjustment in our valuations will lag insurer repricing.
4. **DTI speed-limit response.** Active for ~3 months (Feb 2026). Banks may front-load DTI≥6× lending in some quarters and ration in others. Effect on the sub-$1M FHB market is monitored not modelled.
5. **Help to Buy uptake.** Launched 5 Dec 2025, only 2 lender panels live (CBA, Bank Australia) at start of 2026. Volume too thin to call structural impact yet.
6. **Olympics infrastructure timing.** Cross River Rail and Coomera Connector completion dates are policy-sensitive. We track announced schedules, not assumed delivery.
7. **The CatBoost vs reconciled valuation gap.** Where the two diverge by >15% on a property, neither is reliable — the gap itself is a flag to widen the comparable-range we publish.
8. **Composition drift in our own dataset.** Fields' active-listing scrape is comprehensive but sold-record coverage varies by source. Coverage gaps for non-core suburbs are documented and disclosed.

---

## Top-line summary (3 sentences)

Australia's housing market enters May 2026 in late-cycle tightening — RBA cash rate at 4.35% with a 4.70% year-end expectation, the new APRA DTI speed limit live since February, but record-tight rental vacancy (1.0% nationally, 1.1% Gold Coast Main) and structurally low approvals continuing to support prices, especially in SEQ where Queensland is gaining 21,595 interstate movers a year on top of strong overseas migration. Fields will report from a deliberately conservative methodology: hedonic indexed prices over headline medians, comparable-sales valuations with published 90% confidence intervals over single-figure ML estimates, days-on-market distributions over auction clearance rates (which are misleading on the private-treaty-dominated Gold Coast), and explicit canal/non-canal and lake/non-lake splits for Burleigh Waters and Varsity Lakes respectively. We will state what we do not know — sub-suburb sample sizes, insurer repricing of flood risk, DTI speed-limit adjustment, and our own data gaps — because a credible market report names its uncertainties as clearly as its findings.

---

## Sources

**Macro / RBA / APRA**
- [RBA Statement on Monetary Policy — May 2026 (PDF)](https://www.rba.gov.au/publications/smp/2026/may/pdf/statement-on-monetary-policy-2026-05.pdf)
- [RBA — In Brief: Statement on Monetary Policy — May 2026](https://www.rba.gov.au/publications/smp/2026/may/)
- [RBA — Outlook, Statement on Monetary Policy — May 2026](https://www.rba.gov.au/publications/smp/2026/may/outlook.html)
- [RBA — Cash Rate Target](https://www.rba.gov.au/statistics/cash-rate/)
- [RBA — Monetary Policy Decisions 2026](https://www.rba.gov.au/monetary-policy/int-rate-decisions/)
- [RBA — Resilience of Australian Households and Businesses, FSR March 2026](https://www.rba.gov.au/publications/fsr/2026/mar/resilience-of-australian-households-and-businesses.html)
- [RBA — Chart Pack: Household Sector](https://www.rba.gov.au/chart-pack/household-sector.html)
- [RBA — RDP 2006-04: Measuring Housing Price Growth (PDF)](https://www.rba.gov.au/publications/rdp/2006/pdf/rdp2006-04.pdf)
- [APRA — Update on Macroprudential Policy Settings](https://www.apra.gov.au/update-on-apra%E2%80%99s-macroprudential-policy-settings)
- [APRA — Activating debt-to-income limits as a macroprudential policy tool](https://www.apra.gov.au/activating-debt-to-income-limits-as-a-macroprudential-policy-tool)
- [APRA — System Risk Outlook November 2025](https://www.apra.gov.au/system-risk-outlook-november-2025)

**ABS / Treasury / Government schemes**
- [ABS — Building Approvals, Australia, March 2026](https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/latest-release)
- [ABS — Overseas Migration, 2024-25](https://www.abs.gov.au/statistics/people/population/overseas-migration/latest-release)
- [ABS — Residential Property Price Indexes Methodology, March 2020](https://www.abs.gov.au/methodologies/residential-property-price-indexes-eight-capital-cities-methodology/mar-2020)
- [Queensland Government Statistician — Building Approvals](https://www.qgso.qld.gov.au/statistics/theme/industry-development/housing-construction/building-approvals)
- [Queensland Government Statistician — Population Growth Highlights 2026 (PDF)](https://www.qgso.qld.gov.au/issues/3071/population-growth-highlights-trends-qld-2026-edn.pdf)
- [Treasury — Supporting people into home ownership](https://treasury.gov.au/policy-topics/housing/home-ownership-support)
- [Housing Australia — Help to Buy Scheme launch](https://www.housingaustralia.gov.au/media/more-australians-supported-home-ownership-launch-australian-government-help-buy-scheme)
- [First Home Buyers — gov portal](https://firsthomebuyers.gov.au/)
- [Queensland Revenue Office — First home (new home) concession](https://qro.qld.gov.au/duties/transfer-duty/concessions/homes/first-home-new-home/)

**CoreLogic / Cotality / Domain / SQM**
- [Cotality — Indices overview](https://www.cotality.com/au/our-data/indices)
- [CoreLogic Australia — Type of Indices](https://www.corelogic.com.au/our-data/corelogic-indices/type-of-indices)
- [Cotality — Residential Property Index Series FAQ (PDF)](https://pages.cotality.com/hubfs/CoreLogic%20AU/Indices/clau-indices-faq.pdf)
- [Cotality — Cordell Construction Cost Index](https://www.cotality.com/au/resources/downloads/cordell-construction-cost-index-ccci)
- [Cotality — Home Value Index Jan 2026 (PDF)](https://discover.cotality.com/hubfs/Article-Reports/COTALITY%20HVI%20Jan%202026%20FINAL.pdf)
- [Cotality — Auction Results](https://www.cotality.com/au/our-data/auction-results)
- [SQM Research — Vacancy Rates, Gold Coast Main](https://sqmresearch.com.au/graph_vacancy.php?sfx=&region=qld%3A%3AGold+Coast+Main&t=1)
- [SQM Research — National Vacancy Rates April 2026](https://propertyinvestmentprofessionals.com.au/research-insights/sqm-national-vacancy-1-percent-april-2026-analysis)
- [SQM Research — National Vacancy November 2025 (PDF)](https://sqmresearch.com.au/uploads/11_12_25_National_Vacancy_Rates_November_2025.pdf)

**Industry / market commentary**
- [REIA — Real Estate Institute of Australia](https://www.reia.com.au/)
- [REIQ — Real Estate Institute of Queensland](https://www.reiq.com/)
- [Insurance Council of Australia — Cyclone Alfred update](https://insurancecouncil.com.au/resource/ex-tropical-cyclone-alfred-insurance-update/)
- [Insurance Council of Australia — Flood insurance explained](https://insurancecouncil.com.au/resource/flood-insurance-explained/)
- [Property Update — Australian housing market April 2026](https://propertyupdate.com.au/national-housing-market-update-australia/)
- [Australian Property Institute — Q1 2026 Outlook](https://www.api.org.au/professional-development/knowledge-hub/australian-property-market-outlook-q1-2026/)
- [HTAG — Days on Market and Discounting Metrics](https://www.htag.com.au/days-on-market-discounting-data/)

**Gold Coast / suburb specific**
- [Gold Coast City Council — Flood maps](https://www.goldcoast.qld.gov.au/Planning-building/Buying-researching-property/Mapping-search/Flood-level-search/Flood-maps)
- [Gold Coast City Council — Buying or building in flood risk area](https://www.goldcoast.qld.gov.au/Planning-building/Buying-and-selling-property/Buying-or-building-in-a-flood-risk-area)
- [Which Real Estate Agent — Gold Coast 2026 prices](https://whichrealestateagent.com.au/property-market-update/gold-coast-qld-prices-trends-outlook/)
- [White Sands Buyers Agency — Varsity Lakes 2026](https://whitesandbuyersagency.com.au/varsity-lakes-property-market-2026-prices-growth-complete-investment-guide/)
- [PRD Robina — Varsity Lakes profile](https://www.prd.com.au/robina/suburb-profiles/varsity-lakes/)
- [Edwards & Smith — Burleigh Waters 2026 guide](https://www.edwardsandsmith.com.au/gold-coast/burleigh-waters)

**Methodology — academic**
- [St Louis Fed — A Closer Look at House Price Indexes](https://www.stlouisfed.org/publications/regional-economist/july-2011/a-closer-look-at-house-price-indexes)
- [MDPI — Transactional vs Hedonic Housing Price Indices](https://www.mdpi.com/2813-8090/2/4/19)
- [Wharton — Repeat Sales House Price Index Methodology (PDF)](https://realestate.wharton.upenn.edu/wp-content/uploads/2017/03/724.pdf)
- [Springer — Sample Selection Bias and Repeat-Sales Index Estimates](https://link.springer.com/article/10.1023/A:1007763816289)
- [Wiley — Selection Bias in Housing Price Indexes (Melser, 2023)](https://onlinelibrary.wiley.com/doi/full/10.1111/obes.12534)
- [Case-Shiller index — Wikipedia](https://en.wikipedia.org/wiki/Case%E2%80%93Shiller_index)

**Infrastructure**
- [Queensland Government — Delivering 2032: Transport](https://www.delivering2032.com.au/legacy-for-queensland/transport)
- [The Urban Developer — Brisbane Olympics 2032](https://www.theurbandeveloper.com/articles/brisbane-olympics-2032-development-infrastructure-projects)
- [WSP — Hope Island Station](https://www.wsp.com/en-au/projects/hope-island-station)
