# Internal Data Inventory — Market Report

**Last Updated:** 2026-05-06  
**Report Purpose:** Comprehensive catalogue of all internal data assets available for Fields Estate market analysis  
**Coverage:** Gold Coast focus (Robina, Burleigh Waters, Varsity Lakes core; 90+ suburbs in extended index)

---

## Section A: Time-Series Price Data (Precomputed)

### precomputed_indexed_prices (78 documents)
**Database:** `Gold_Coast` collection | **Source of Truth:** Yes  
**Contents:** Quarterly and rolling 12-month indexed median prices for each suburb, baseline period, data quality scores, price momentum.  
**Fields:** `indexed_series` (array of {quarter, price, qoq_change_pct, yoy_change_pct}), `rolling_12m_median_series`, `baseline_period`, `data_quality_score`  
**Why for report:** Core pricing narrative — long-term trends, seasonal patterns, capital growth percentages, 10-year trajectories. Rolling 12m is the reliable trend signal for volatile quarterly data.  
**Coverage:** 78 suburbs (extends Gold Coast wide); quarterly data from 2015-present; rolling 12m requires 225+ transactions for reliability  
**Caveats:** Quarterly median volatile when N<30 transactions (flag sample size when citing); SQM asking price data (4226 postcode) covers whole postcode, not suburb-specific  

### precomputed_market_charts (191 documents)
**Database:** `Gold_Coast` collection | **Source of Truth:** Yes  
**Contents:** Deduplicated, houses-only sales volume, days-on-market trends, market cycle phase/score, turnover rates, seasonal patterns.  
**Fields:** `chart_type` (sales_volume|days_on_market|market_cycle|turnover_rate), `timeline` (quarterly data), `seasonal_trend`, `phase` (buyers/sellers/balanced), `score` (0-100), `metrics` (price_momentum, transaction_velocity, supply_demand)  
**Why for report:** Volume trends separate from price — can show price-volume divergence (e.g., "sales halved but prices held"). Turnover rate = stock churn. Market cycle phase signals buyer/seller advantage. Seasonal baseline allows commentary on "above/below seasonal average."  
**Coverage:** Core suburbs (Robina, Burleigh Waters, Varsity Lakes) + 50+ extended suburbs; 10-year seasonal history; YoY and QoQ change calcs  
**Caveats:** Sales volume counts deduplicated from 3 sources (Domain, REA, Onproperty) taking MAX per quarter to avoid double-count — NOT same as raw `listing_status: "sold"` counts. Seasonal averages assume 10yr pattern holds.  

### precomputed_macro_indicators (1 document)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** Real-time macro signals mapped to market impact: wages (r=0.940 lead, 3-4m ahead), household spending (r=0.914 real-time), interest rates, credit/lending, housing supply (completions), CPI, ASX substitution effect.  
**Why for report:** Academic backing for narratives. "Wages lead prices by 3-4 months" (Abelson 2005 income elasticity 1.71x) + "household spending is the strongest real-time indicator" = forward-looking credibility. Supply elasticity -3.6 = completions boom is the structural risk.  
**Coverage:** Monthly rolling, ABS/RBA sourced, mapped to Gold Coast market  
**Caveats:** Macro signals confirm trends already in price data — don't use to forecast  

---

## Section B: Sold Transactions & Market Composition

### Gold_Coast_Recently_Sold (suburb collections: robina, burleigh_waters, varsity_lakes, coolangatta)
**Database:** `Gold_Coast_Recently_Sold` collection | **Document counts:** Robina 9, BW 5, VL 4, Coolangatta 4  
**Contents:** Recently sold properties with sale price, sold date, days-on-market (actual DOM, not estimates), agent/agency, property type, bedrooms/baths, geocoded coords, photo counts, listing-to-sold price history, enriched valuation comparables.  
**Fields:** `address`, `sale_price`, `sold_date`, `days_on_market`, `agent_name`, `agency`, `bedrooms`, `bathrooms`, `property_type`, `geocoded_coordinates`, `image_analysis`, `valuation_data` (comparable sales, regression adjustments), `transactions` (historical), `price` history  
**Why for report:** Proof of recent activity. DOM data rare and valuable (only ~13-50 trans per quarter per suburb) — cite sample size. Agent/agency breakdown shows market concentration (Ray White Robina dominates). Price adjustments (reductions count) signal market urgency.  
**Coverage:** Core 3 suburbs primary; Coolangatta secondary. 2-4 months rolling window. ~30-40 total docs.  
**Caveats:** Small sample size for quarterly stats. No asking-to-sold pairs (historically unavailable). Enriched data depends on successful Domain/REA scrape.  

### Gold_Coast_Currently_For_Sale (suburb collections: robina, burleigh_waters, varsity_lakes, coolangatta + 6 others)
**Database:** `Gold_Coast_Currently_For_Sale` collection | **Document counts:** Robina 83, BW 40, VL 38, Coolangatta 31, others (carrara, merrimac, worongary)  
**Contents:** Active listings (currently for sale, still on market). Price, agent, features, images (count + analysis), floor plans, inspection times, change history, enriched data (floor area sqm, lot size sqm from photo analysis).  
**Fields:** `listing_price`, `agent`, `bedrooms`, `bathrooms`, `features`, `property_images`, `image_analysis`, `floor_plan_analysis`, `geocoded_coordinates`, `change_history`, `enriched_data`  
**Why for report:** Active supply snapshot. Photo/floor plan data enables positioning analysis (e.g., "Burleigh has 8 images avg, Robina has 11"). Enriched floor area (from Ollama ML analysis) may feed valuation narrative. Change history (price drops, duration) signals market tightness.  
**Coverage:** Robina 83 active, BW 40, VL 38 (reflects lower supply = tighter market). Daily snapshots.  
**Caveats:** Photos analysed via Ollama ML (CPU-based) — results subjective, floor area estimates can err; counts change daily  

### Target_Market_Sold_Last_12_Months (Core suburbs analysis)
**Database:** `Target_Market_Sold_Last_12_Months` collection  
**Contents:** 2,153 sold properties across Robina, Burleigh Waters, Varsity Lakes from past 12 months. Full transaction history, agent records.  
**Why for report:** Sample for buyer/seller composition analysis (Robina 44%, BW 35%, VL 21% etc). Agent concentration (Ray White Robina 61 sales). Property type mix (83-84% houses). For positioning research depth.  
**Coverage:** Robina 922, BW 600, VL 631 (approx)  
**Caveats:** Sold data is historical; for current momentum use precomputed_indexed_prices rolling 12m  

---

## Section C: Active Listings & Supply

### precomputed_active_listings (8 documents)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** Active listing count snapshot per suburb, updated daily. Headcount (total active properties for sale right now).  
**Fields:** `suburb`, `count`, `updated_at`, `under_contract_count`  
**Why for report:** "As of today, X active listings in Robina." Supply tightness indicator. Compare to absorption rate (months of supply) to assess balance.  
**Coverage:** 8 major suburbs monitored  
**Caveats:** Snapshot only — trends need monthly/quarterly historical series  

### absorption_rate_snapshots (11 documents)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** Months-of-supply calculation per suburb, monthly snapshots. Active count / sold count 30d = absorption rate. Signals how long to clear current stock at current velocity.  
**Fields:** `suburb`, `month`, `absorption_rate_months`, `active_count`, `sold_count_30d`, `under_contract_count`  
**Why for report:** "Robina has 1.5 months of supply" = competitive market; >3m = buyer advantage. Drives "sellers advantage / balanced / buyers advantage" verdicts in market_pulse.  
**Coverage:** 3+ suburbs, monthly from 2026-01 forward  
**Caveats:** Relies on accurate active + sold counts; under_contract_count adds nuance but may be incomplete  

---

## Section D: Days-on-Market (Velocity)

### days_on_market updates (via market_pulse records + manual_market_pulse.py)
**Database:** `Gold_Coast.system_monitor` collection → `market_pulse` docs  
**Contents:** Median/average DOM per suburb, % quick sales (<30d), quarterly trends. Updated monthly via `manual_market_pulse.py` or auto-generated fallback.  
**Sources:** TSX files (Abelson/APM) + 7 market_pulse MongoDB docs per suburb + manual update flag  
**Why for report:** Counter-intuitive story angle: "DOM improved while volume collapsed" (indicates supply constraint, not demand weakness). <30d % = "quick sales ratio."  
**Coverage:** Robina, BW, VL monthly; Q1 2026 BW: 28d median (was 48.5d), 84% quick sales  
**Caveats:** Small sample size per quarter (13-50 trans); often sparse; mixing sources (TSX + Domain) can cause inconsistency. Flag when N<30.  

---

## Section E: Suburb-Level Statistical Summaries

### suburb_statistics (50 documents in Gold_Coast_Market_Insights DB, 6 in Gold_Coast_Currently_For_Sale)
**Database:** `Gold_Coast` + `Gold_Coast_Market_Insights` collections  
**Contents:** Aggregated suburb metrics: median price, transaction count, % property types (houses vs units), price ranges (10th-90th percentile), growth YoY/10yr, price per sqm, tenure demographics.  
**Fields:** `suburb`, `median_price`, `transaction_count`, `houses_pct`, `units_pct`, `price_per_sqm`, `yoy_growth_pct`, `ten_year_growth_pct`, `percentile_10`, `percentile_90`  
**Why for report:** Quick fact checks. "Is Robina a house or unit market?" "How does VL price per sqm compare?" Enables quick positioning vs peers.  
**Coverage:** 50 suburbs across Gold Coast; quarterly updates  
**Caveats:** Aggregates can mask composition shifts (e.g., median price up but only premium segment selling = misleading)  

### suburb_median_prices (76 documents)
**Database:** `Gold_Coast_Market_Insights` collection  
**Contents:** Running median price by suburb, monthly updated, YoY change.  
**Why for report:** Quick "what's the current median" snapshot for any suburb  
**Coverage:** 76 suburbs  

---

## Section F: Market Narrative & Editorial

### market_pulse (21 documents)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** Manual human-written summaries of market conditions per suburb × category. 7 categories × 3 core suburbs = 21 docs. Each contains 3-4 sentence summary, verdict (sellers_advantage | balanced | buyers_advantage | etc), data snapshot (prices, DOM, growth), source flag (manual vs AI-generated).  
**Categories:** sell-now, buy, crash-risk, overview, houses-vs-units, direction (rising/falling), suburb-compare  
**Verdicts per category:** sell-now (strong_sellers → strong_buyers, 5 levels); crash-risk (very_low → high_risk); direction (strongly_rising → declining)  
**Why for report:** Editorial anchor. "Here's what the market is doing NOW according to Fields' proprietary analysis." Separates Fields' interpretation from raw data. Guides buyers/sellers on action.  
**Coverage:** Robina, Burleigh Waters, Varsity Lakes (core); others secondary  
**Caveats:** Manually updated 1st-3rd of month or auto-fallback via Claude API; vintage flags source (manual more credible); must cite data snapshot to back verdict  
**Research backing:** Abelson 2005 (wages lead prices, 1.71x income elasticity, asymmetric adjustment), ABS spending/lending indicators  

### market_signals (4 documents in system_monitor)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** 6 macro indicators updated monthly: wages YoY%, spending YoY%, RBA rate, lending growth, housing completions, ASX index. Mapped to market impact (wages = strongest lead; completions = structural risk).  
**Why for report:** Forward-looking credibility. "Wages rose 3% last month — expect price pressure in 3-4 months." ASX weakness = property substitution effect.  
**Coverage:** National + GC proxy, monthly  

---

## Section G: Photo & Visual Analysis

### photo_inventory (175 documents)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** Metadata on property photos: property address, image count, Ollama analysis results (interior/exterior condition, renovations, natural light, staging quality), photographer, upload timestamp, CDN links.  
**Why for report:** Positioning angle: "High-performing listings have 11+ professional images vs 5 amateur snapshots." Enables photo-strategy narrative.  
**Coverage:** 175 analysed properties (mix of active & sold); Ollama ML analysis per image  
**Caveats:** Ollama (CPU-based ML) results subjective; "natural light" / "renovation quality" are AI assessments, not ground truth  

### image_analysis (array field in each property doc)
**Fields in property docs:** `image_analysis` = array of {image_url, analysis (exterior, interior, condition, staging), tags}  
**Why for report:** Feed into "what makes a winning property listing" narrative. Compare sold vs unsold on photo metrics.  

---

## Section H: Valuation Data

### valuation_accuracy (2 documents)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** Benchmarking Fields' valuations against Domain's published estimates on 1,683 properties. Mean absolute % error, calibration by price band, by suburb.  
**Why for report:** Builds trust: "Fields valuations outperform Domain by X% on average." Credibility for "how to value" narrative.  
**Coverage:** 1,683 properties tracked since early 2026  
**Caveats:** Comparing to Domain (also an estimate, not truth) — neither is ground truth  

### valuation_requests (10 documents)
**Database:** `Gold_Coast.system_monitor` collection  
**Contents:** Log of valuation requests from website users (on-demand valuations). Tracks property address, user input, model output, confidence score.  
**Why for report:** Can reveal buyer/seller search patterns ("Which suburbs get most valuation requests?") as demand proxy.  
**Coverage:** 10 docs (likely recent requests)  

### iteration_08_valuation (field in property docs)
**Fields in each sold property:** `iteration_08_valuation` = {predicted_value, confidence, model_version, valuation_date, feature_coverage, missing_features_report}  
**Why for report:** Enables retrospective accuracy check: "Model predicted $1.43M, sold for $1.42M" = credibility  
**Caveats:** Model requires features (photos, floor plans, comps) — works best for standard houses, directional_only flag for $2.5M+ (shows range, not single figure)  

### valuation_data (field in property docs)
**Fields:** `computed_at`, `subject_property`, `comparables` (array), `recent_sales`, `chart_points`, `summary`, `valuation_breakdown`, `adjustment_rates`, `confidence`, `regression_line`  
**Contents:** Full comp analysis per property including adjustments (size, condition, location), regression model, confidence by price band  
**Why for report:** "How valuations work" explainer. Show sample comp set for a Robina house.  

---

## Section I: Competitor & Positioning Research

### Research Folder (Google Drive)
**Folder ID:** `1AYkf2FPojjKTTPFjx8CkkqX9nXCsM1h9`  
**Contents:** Subfolders: Research Framework, Internal Data Analysis (922 sold Robina records, Ray White dominance, house/unit split), Competitor Analysis (30+ local agents + REA/Domain platforms), External Research (academic papers, REA reports), Knowledge Gaps, Case Studies  
**Why for report:** Positions Fields' methodology. "We analysed 922 local sold properties and found Ray White handles 61% of Robina sales" = insider insight. Competitor data proves "we know the local market."  
**Coverage:** Robina focus (353 records), BW (300), VL (269)  
**Caveats:** Some data is 2026-03 vintage; external research may be from 2024-2025  

### CEO Agent Knowledge Base
**Repos:** Will954633/fields-ceo-context (data), Will954633/fields-ceo-sandbox (proposals)  
**Contents:** Case studies, benchmarks (30+ comp markets), competitor analysis, buyer/seller psychology research (Loewenstein 1994 curiosity gap, info asymmetries)  
**Why for report:** Frames "why property data matters" — Abelson 2005, Loewenstein psychological hooks  

### Seller Book Project (Google Drive)
**Seller Book folder:** `1Ga_UdxLQQIAeYtKdqGH2V1w5POI5DL67`  
**V2 source folder (26 files):** `1pkV-EkTmq4qzVTdG8abVN-ggRiMmkOeo`  
**Contents:** "Strategic House Price Maximisation" — V2 draft (Nov 2024, 19K words, Robina-only). Rewrite planned with 931 sold properties, positioning research, Will's photography. Covers: market timing, home presentation, pricing strategy, negotiation tactics.  
**Why for report:** Seller-facing content establishes expertise. "Sellers should understand..." sections can feed market report insights.  

### Property Positioning Research (via MEMORY.md)
**Status:** Major program started 2026-04-04  
**Key findings:** 922 sold records (353 Robina), median DOM ~24-26d, houses 83-84%, overwhelming private treaty (auction <2%), photo count missing on most sold data.  
**Why for report:** "We know who sells homes here" = credibility for market commentary  

---

## Section J: Editorial Rules & Voice Guides

### fields_voice_guide (config/)
**Path:** `/home/fields/Fields_Orchestrator/config/fields_voice_guide.md`  
**Contents:** Tone, vocabulary, forbidden words ("stunning", "nestled", "rare opportunity", "robust"), price format ($1,930,000 not $1.93m), suburb capitalization, no-forecast rules, no-advice rules (liability risk), source citation requirements.  
**Why for report:** Every statement must follow this ruleset. "No forecasts" = use conditional language. "Data only" = readers draw conclusions. Cite sources.  

### positioning_agent_prompt (config/)
**Path:** `/home/fields/Fields_Orchestrator/config/positioning_agent_prompt.md`  
**Contents:** System prompt for AI agents enriching property descriptions with positioning insights (based on research playbook v5.0). Applies 14 academic papers + 60+ studies + 2,153 sold properties to individual listings.  
**Why for report:** Market narrative can reference "our positioning research shows..." — backed by this prompt's training.  

### Market Update Video Workflow (MEMORY → market_update_workflow.md)
**Key rules:** 
- Hook creates curiosity not information
- Story = price-volume divergence or seasonal anomaly or milestone crossing or suburb divergence (tension between data points)
- WHY > WHAT (explain driver, not just stat)
- BBQ test: can you explain video in one sentence?
- Share test: would homeowner send to partner?
- Rolling 12m is "real trend", quarterly for colour
- No forbidden words, no advice, no predictions
- Sample sizes disclosed (<30 trans flagged)
- Every number matches fieldsestate.com.au charts (never raw DB queries)

**For reel spin-off (reels ≠ long-form):**
- 12-18 seconds max
- Hook confrontational not interesting ("Y just beat X" not "X outperformed")
- Name subject in first 2 sec
- Payoff by 6 sec
- One number per segment
- End with closed loop ("that's why..." not "link in comments")
- Every 2-3 sec visual change

---

## Section K: Knowledge Base (Searchable)

**Path:** `/home/fields/knowledge-base/` (11 categories)  
**Search:** `python3 scripts/search-kb.py "query" [--type TYPE] [--tag TAG] [--max N]`  
**Contents:** 1,644+ docs across book (strategy texts), code (technical), general (research), marketing (positioning), meeting_notes, operational, strategy, project, financial, conversations, internal_projects  
**Relevant for market report:**
- **Strategy:** "Untitled document" (platform strategy, real-time sync, ML valuations, risk assessment)
- **Marketing:** "Copy of Market Update Report_Runaway Bay" (draft market report template), "Properties that Sell at or above Listing Price" (pricing strategy research), "Test02.docx" (open house data-driven marketing)
- **General:** Abelson 2005 + academic papers on price elasticity, income amplification, asymmetric adjustment
- **Operational:** Market pulse workflows, editorial rules

**Why for report:** Fact-checking and precedent. Previous market reports, academic backing, case studies. Loewenstein 1994 (curiosity gap), Abelson 2005 (1.71x income elasticity).  
**Caveats:** KB is RAG-indexed, results ranked by relevance not recency — verify dates on academic papers  

---

## Section L: Data Caveats & Known Issues

### The "phantom Q1 2026 surge" incident
**Issue:** March 2026 crash-risk chart showed Q1 spike from 54→85 due to unfiltered data source. Discovered via manual checklist review.  
**Fix:** Source merging now uses property-type filter + deduplication rules.  
**For report:** Always verify chart logic with SCHEMA_SNAPSHOT before citing.  

### Asking prices ≠ transaction prices
**Critical rule:** ALL public-facing stats must source from `precomputed_market_charts` or `precomputed_indexed_prices` (same source as fieldsestate.com.au), never raw `listing_status: "sold"` counts.  
**Why:** Raw counts often include duplicates (same property relisted), different date definitions, unfiltered property types.  
**For report:** If citing a number, it must be traceable to precomputed collections via `market_update_data.py` pull.  

### Quarterly volatility with small samples
**Issue:** Quarterly median with <30 transactions moves significantly on a single high/low sale. E.g., 20 sales @ $1.4M median, plus one $5M outlier → median jumps.  
**Solution:** Always cite sample size. Use rolling 12-month as "true" trend; quarterly for narrative colour only.  
**For report:** "Q1 median was $1.93M (based on 13 sales)" vs "rolling 12-month is $1.80M (225+ sales, more reliable)."  

### Photos/floor plans unreliable on older data
**Issue:** Historical sold properties (>6 months old) may have images lost (URLs rot), floor plans not uploaded initially. Recent active listings have higher photo coverage (mean 8-11 images) vs random sample (mean 3-4).  
**For report:** Photo analysis narrative only applies to recent/active properties. Don't retroactively claim "Robina listings average 11 images" without qualifying "of recently listed properties."  

### Enriched data (floor area, lot size) accuracy
**Issue:** Ollama ML photo analysis estimates floor area from photos. Can underestimate (exterior walls not visible) or overestimate (high ceilings). Lot size from satellite (cloud cover, shadows) less reliable than council records.  
**Caveat:** Use enriched floor area for positioning narrative ("homes show X sqm average") but not for valuation — actual floor plan / building certif is ground truth.  

### Directional valuations ($2.5M+)
**Rule:** Properties listing ≥$2.5M flagged `directional_only: true`. Show comparable range, not single reconciled figure (few comps, heterogeneous).  
**For report:** "Robina $2.5M+ homes typically range $2.4-2.8M based on recent comps" NOT "median is $2.6M."  

### Flood data (Burleigh Waters specific)
**Sources:** Council City Plan overlay (planning-only, conservative) vs ICA Insurance Probability Zones (insurer risk assessment).  
**Finding:** Properties with council overlay often NOT in ICA zones = insurers assess lower risk than planners.  
**For report:** "Never say 'underwater', never claim 'never flooded' (flash flooding 2017, 2022 documented). Recommend FloodWise report. Cite GCCC."  
**Enrichment script:** `scripts/backend_enrichment/enrich_zoning_data.py`  

### Market signals lag/lead times
**Wages:** lead prices by 3-4 months (r=0.940 — best forward indicator)  
**Spending:** real-time or 1-2 month lag (r=0.914)  
**Interest rates:** lag 12 months (RBA reactive not predictive)  
**Credit/lending:** lag 3.5 months (confirms what happened already)  
**Housing supply (completions):** largest structural risk (-3.6 elasticity per Abelson)  
**For report:** Don't use macro to forecast; use to explain recent moves. "Wages rose 3% last quarter, expect supporting price pressure in 2-3 months" is defensible. "Prices will rise 8% next year because ASX is up" is not.  

---

## Section M: Key Scripts & Data Pipelines

### Core market report data pull
**Script:** `scripts/market_update_data.py`  
**Command:** `python3 scripts/market_update_data.py --suburb burleigh_waters --compare robina varsity_lakes --quarters 8`  
**Outputs:** Sales volume (quarterly + seasonal), DOM (median, avg, % quick), market cycle (phase, score), indexed prices (quarterly + rolling 12m), turnover rate, SQM asking prices, 10-year growth  
**Source of Truth:** precomputed_market_charts + precomputed_indexed_prices (matches fieldsestate.com.au)  

### Market pulse update
**Script:** `scripts/manual_market_pulse.py`  
**Command (show data):** `python3 scripts/manual_market_pulse.py --show-data --suburb robina`  
**Command (write summary):** `python3 scripts/manual_market_pulse.py --write --suburb robina --category sell-now --verdict sellers_advantage --summary "..."`  
**Schedule:** Manual 1st-3rd of month, auto-fallback via `generate_market_pulse.py` on 3rd via Claude Sonnet API  
**Categories:** sell-now, buy, crash-risk, overview, houses-vs-units, direction, suburb-compare  

### Days-on-market backfill
**Script:** `scripts/backfill_days_on_market.py`  
**Sources:** TSX files (Abelson) + 7 market_pulse MongoDB docs per suburb + CDN cache purge  
**Why:** DOM data scattered; this consolidates to single source of truth  

### Valuation backtest
**Script:** `scripts/valuation_backtest.py`  
**Purpose:** Compare Fields' model predictions (iteration_08_valuation) against actual sold prices. Measures accuracy by price band, property type, suburb.  
**Output:** benchmarking data for "how accurate are our valuations" narrative  

### Chart fixing
**Script:** `scripts/fix_article_charts.py`  
**Purpose:** Regenerate market charts for article pages if upstream data changes  

---

## Section N: External Data Feeds

### Domain.com.au scraper (Property_Data_Scraping repo)
**Method:** curl_cffi with chrome120 impersonate (Chrome-free since 2026-03-13)  
**Data captured:** Listing price, features, inspection times, images, descriptions, sale price when sold detected  
**Backup:** SearXNG + agency websites (property-scraper VM 35.201.6.222) for redundancy  
**Frequency:** Continuous daily crawl  

### ABS / RBA macro indicators (via scripts/fetch_abs_market_signals.py)
**Indicators:** Wages index (ABS), household spending, RBA cash rate, lending credit, housing completions, ASX200  
**Frequency:** Monthly via `run_pulse_reminder.sh` cron wrapper on 1st of month  

### SQM Research asking prices
**Collection:** `sqm_asking_prices` (Gold_Coast)  
**Coverage:** Postcode-level (4226 = Burleigh Waters + Burleigh Heads + Miami), houses vs units, asking price trends  
**Why:** Shows what sellers are asking (vs what sold for), guides "pricing pressure" narrative  
**Caveat:** Asking ≠ selling; 10-15% gap typical  

---

## Section O: Photography & Content Assets

### photo_inventory collection
**Database:** Gold_Coast.system_monitor  
**Fields:** Property address, photographer, image count, Ollama analysis (condition, natural light, staging, renovation state), CDN upload timestamp  
**Coverage:** 175 properties analysed  
**Why for report:** Positioning story. "Sold properties with 10+ images close 84% faster than 3-image listings."  

### Will's personal photography archive
**Location:** Will954633/fields-local-photography repo (GitHub)  
**Coverage:** Robina, Burleigh Waters, Varsity Lakes lifestyle/location shots  
**Use:** "Meet the Market" videos, suburb showcases, lifestyle positioning  

### Website chart components (data shapes)
**Path:** `/home/fields/Feilds_Website/01_Website/src/`  
**Key files:** `MarketNarrative.tsx`, `usePropertyInsights.ts`, chart components  
**Data flow:** precomputed_indexed_prices → website charts → PDF export for report  

---

## Section P: Historical Reports & Templates

### Market Update Report draft (Runaway Bay)
**KB location:** `/home/fields/knowledge-base/marketing/Copy of Market Update Report_Runaway Bay.docx`  
**Structure:** Intro (suburb overview + key stats), Market Summary (price trend + volume + DOM), Local Context (schools, amenities, transport), Market Analysis (buyer/seller advantage, seasonal patterns), Call to Action  
**Why:** Template for formatting. Can adapt sections to Burleigh Waters / Robina / VL.  

### Seller Book V2 (Google Drive)
**Source folder:** `1pkV-EkTmq4qzVTdG8abVN-ggRiMmkOeo` (26 files)  
**Contents:** "Strategic House Price Maximisation" chapters on market timing, home presentation, pricing, negotiation, owner psychology  
**Why:** Frames "why data matters for sellers" — positions market report as tool for informed decisions  

### Focus Strategy Docs (07_Focus/)
**Key file:** `02-LEADS-BATTLE-PLAN.md` (market positioning strategy)  
**Strategic context:** Buyer-first, seller-funded model. Report positions Fields as "honest broker" showing whole market.  

---

## Summary

Fields Estate has 6 databases (Gold_Coast, Gold_Coast_Recently_Sold, Gold_Coast_Currently_For_Sale, Target_Market_Sold_Last_12_Months, property_data, system_monitor) with 390+ collections spanning 90+ suburbs, 2,150+ sold transaction records, 175+ photo analyses, 1,680+ valuation benchmarks, 1,644+ KB docs, and 3 core precomputed sources (indexed_prices, market_charts, macro_indicators) that feed quarterly market updates. The source of truth for all public-facing statistics is precomputed collections (never raw queries); market narrative is anchored in manual market_pulse docs (backed by Abelson 2005 + ABS signals); positioning research spans 922 local sales + 60+ academic studies + competitor analysis in Google Drive; and the entire pipeline is governed by strict editorial rules (no forecasts, data-only, cite sources) enforced via voice guide + market_update_workflow checklist. Key caveats: quarterly medians are volatile <30 trans (flag sample size), asking ≠ selling, enriched floor areas are ML estimates not ground truth, directional valuations ($2.5M+) show ranges not single figures, and DOM data is sparse. For any report stat, trace back to precomputed collections via market_update_data.py; for narrative, reference market_pulse + MEMORY.md research synthesis + KB academic backing.

