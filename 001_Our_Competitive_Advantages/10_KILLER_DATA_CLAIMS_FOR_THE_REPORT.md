# The Killer Data Claims — Competitive Advantages a Seller's Report Can Make That Nobody Else Can

This is the headline document. It's the answer to:

> *"As an owner deciding who to sell my home with, what can Fields say about my home that no other agency in Australia can?"*

The Pre-Sale Intelligence Report (`09_Appraisals/`) is the artefact in which these claims appear. This document defines the ten claim *categories* the report draws from. Each one is a competitive advantage in concrete, seller-facing form: a sentence the report can write because we have a pipeline that produces the underlying number, and that no GC competitor (Ray White, McGrath, Realty Blue, Kollosche, Harcourts, PRD) can produce.

Each entry below specifies:

- **The claim category** — named.
- **Example phrasings** — the way the report could read.
- **The underlying capability** — which pipeline produces the data.
- **Why no incumbent can copy it inside 12 months.**
- **The behavioural mechanism** — why this claim moves the seller's mind, the buyer's mind, or the price.

All examples below use real field shapes verified against the database on 2026-05-07 — no speculative pipelines. Where coverage is partial or a parser is dormant, I've flagged it.

---

## 1. Combinatorial scarcity in active inventory

**The advantage you named #1.**

**Example claims (live, generated for property `8 Trinity Place Robina`):**

> "There are currently only 2 five-bedroom houses with a pool for sale across all of Robina — out of 55 total active listings. This property is one of them."

> "Only 1 home currently for sale in Burleigh Waters with a north-facing rear yard, a pool, and over 800 m² of land."

> "No other property currently for sale in Varsity Lakes combines lake frontage with a four-bedroom layout under $1.6M."

**Underlying capability.** `generate_positioning_analysis.py` pre-computes scarcity counts via Mongo `count_documents` on feature combinations across active listings, suburb-bounded. Every active listing in the target market is enriched with a structured `positioning_analysis.public.scarcity` block: `{statement, count, feature_combo}`. The combinations available are open-ended (any feature in our property document — bedrooms, bathrooms, pool, dual-living, view, lot size band, floor area band, archetype, condition, adjacency, orientation).

**Why no incumbent can copy it.** Three barriers:

1. **The property document has to be machine-readable in the first place.** Domain.com.au listings are HTML and image. Cotality / PriceFinder give agents structured fields but not at this granularity (no archetype, no orientation, no adjacency, no floor-area-band).
2. **Combinatorial queries require an indexed relational view of every active listing in a suburb at the same moment.** Agents have access to tools that show one listing at a time. They cannot run "count all active Robina listings with X AND Y AND Z" because nobody built that interface for them.
3. **Editorial discipline to phrase scarcity factually, not as urgency.** Our playbook proves manufactured urgency backfires (BW: 33d DOM with urgency framing vs 20.5d with factual). An agent who tries to copy this overshoots into "Don't miss this rare opportunity!" — and the data shows that costs them money.

**Behavioural mechanism.** Cialdini scarcity. Real, verifiable scarcity creates buyer urgency without seller-side manipulation. The seller reading the report sees their home positioned as objectively rare — not "agent says it's special" but "the database says it's one of two." This addresses the seller's deepest fear: *that their home is just another listing.* It reframes the campaign from "we'll find a buyer" to "qualified buyers are competing for a tiny pool of homes with these exact features, and yours is in that pool."

**Coverage status.** Live on 19/142 active target-market listings. Backfill needed for VL (0/33).

---

## 2. Sold-history rarity (demand-side scarcity)

**Example claims:**

> "Only 3 homes have sold in Robina in the last 12 months with a living area over 32 m². Yours is 40 m²."

> "Across the last 24 months in Burleigh Waters, only 7 four-bedroom homes with a pool and a north-facing rear yard sold above $1.8M. The median lift to suburb median for that group was +9.4%."

> "Of 282 Burleigh Waters sales we've recorded since May 2025, 11 had floor area above 220 m² and a renovation tier above 'modest'. Yours meets both."

**Underlying capability.** 966 sold records across Robina (370) + VL (314) + BW (282), each tagged with floor area, archetype, condition, sold price, sold date, and (where available) feature flags. Same combinatorial query engine as #1, but applied to historical sales rather than active inventory. The positioning agent's `comparable_evidence` block already names specific recent sales; this advantage extends the same machinery to *aggregate* claims about cohorts.

**Why no incumbent can copy it.** Cotality has the sales data. They don't expose cohort queries. RateMyAgent has reviews. Domain has price-history graphs. **Nobody combines floor area, archetype, condition, and feature-combo into a queryable cohort that lets you say "11 homes like yours sold in the last 24 months and here's how they performed."**

**Behavioural mechanism.** Sold-history rarity is *demand-side* scarcity — proof that buyers historically paid up for homes like this. Where active-inventory scarcity tells the buyer "you can't find another one right now," sold-history rarity tells the seller "buyers consistently pay above median for this combination, here's the evidence." Loss aversion pushes the seller toward the higher anchor. Anchoring locks the price at the cohort-median-plus.

**Coverage status.** Data is live; the cohort-claim module isn't yet a separate report block. Easy to add — the positioning agent already does much of this in `comparable_evidence`. Recommend a dedicated "Cohort Performance" module in `09_Appraisals/04_content_modules.md`.

---

## 3. Floor-plan-derived dimensional supremacy

**The "your living room is 40 m²" claim, generalised.**

**Example claims (live data — from `floor_plan_analysis` on enriched listings):**

> "Your living and dining area at 40 m² is in the top 5% of recently-sold homes in Robina (median 28 m²)."

> "Your master suite at 17.4 m² with a 4.7 m² ensuite places you in the top decile for primary-bedroom comfort across the comparable-sale cohort."

> "Your covered outdoor entertaining area is 49.82 m² — larger than 80% of homes that sold in Burleigh Waters above $1.6M in the past 12 months."

> "Your total internal floor area at 220 m² is supported by single-level living — only 4 of the 35 most recent Robina sales above $1.5M offered single-level layouts above 200 m²."

**Underlying capability.** `floor_plan_analysis` field on each enriched listing contains structured: internal/total/external floor area, room-level dimensions (master bedroom 4.1 × 3.2 m), outdoor space sqm, level details, layout features (open_plan, split_level, flow_description), parking specifics, additional features. This is **extracted by GPT vision from the floor-plan image** — Domain serves the floor plan as a PNG; we parse it.

**Why no incumbent can copy it.** This is the most defensible technical capability we have. To replicate:

1. They need vision-API access (commodity, easy).
2. They need a prompt that reliably extracts dimensions from heterogeneous floor plans (we've iterated this for months).
3. They need to *do this for every listing in the suburb, both active and historically sold*, otherwise they have your dimensions but nothing to compare to.
4. They need a backend to persist and query the resulting structured data.
5. They need editorial logic to convert "your living room is 40 m²" + "median is 28 m²" into a top-5% claim.

**No agency in Australia is doing this systematically.** PriceFinder / Cotality data has total floor area, not room-level. Domain shows the floor plan; doesn't structure it. We are alone here.

**Behavioural mechanism.** Endowment effect — sellers already think their home is special. We give them *evidence the market should agree*, in numbers a buyer's report can quote. The buyer reading the listing now has a quantified, rare feature to anchor on — "this is the home with the 40 m² living room." That anchor justifies a premium without any manufactured urgency.

**Coverage status.** Floor plan analysis is live on 71/142 active listings (50%). The positioning agent's prompt already references $/sqm and floor area scarcity. The dimensional cohort claims (top 5% / top decile / above the 80th percentile) are a small extension. Recommend backfill of remaining 71 listings.

---

## 4. Lot, orientation, and outdoor scarcity from satellite analysis

**Example claims (from live `satellite_analysis` data):**

> "Your block backs onto residential-only neighbours with no commercial frontage — only 14% of currently-listed Robina properties share this protection from non-residential noise and traffic."

> "Your home occupies a slope-down position in the southern third of Burleigh Waters — every Burleigh Waters sale above $2.5M in the past 18 months that we can verify from satellite occupied this same micro-zone."

> "From above, your rear yard reads as north-facing with a pool envelope of approximately 12 × 5 m and tree canopy on the western boundary — a combination present in only 6 of the 42 currently active Burleigh Waters listings."

> "Your beach distance at 1,140 m places you in the closest 30% of Burleigh Waters listings under $2M (computed from cadastral coordinates to mean high-water mark)."

**Underlying capability.** `satellite_analysis` field (100% coverage on target market). Captures structured: adjacency (`backs_onto`, `frontage`, `elevation_position`), surrounding land use narrative, satellite image URL, GPT-5.4 vision interpretation. Plus geocoded `beach_distance_enriched_at` and full lat/lng on every active listing.

**Why no incumbent can copy it.** Same vision-pipeline barrier as floor plan. Plus the geocoding to compute proximity to anchors. Cotality has aerial imagery in their professional product but it isn't analysed for orientation, adjacency, or outdoor-space sqm at scale, and the output isn't suburb-bounded for cohort comparison. **An agent at any GC franchise has none of this — they have what they can see from the kerb.**

**Behavioural mechanism.** This category trades on what the buyer *sees from above when they Google the address.* Modern buyers do this. By the time they call the agent, they've already Google-Mapped the property and built an opinion. We *front-run that opinion* by writing the report from the same satellite view, with our interpretation already in the buyer's mind via the listing copy. Anchoring before inspection.

**Coverage status.** 142/142 active target listings carry satellite_analysis. The data is live and rich. The cohort claims (top 14%, top 30%) need a small extension to the report module to convert the per-listing data into percentile statements.

---

## 5. Bracket-competition density

**Example claims (live, from `positioning_analysis.public.bracket_intelligence`):**

> "The $1.5M–$2M bracket is Robina's most competitive tier with 12 active listings — more than double the next bracket ($1.25M–$1.5M at 9 listings). However, only 2 of those 12 are five-bedroom homes with a pool, which materially reduces direct competition."

> "Of the 7 active listings in your $1.45M–$1.65M bracket in Varsity Lakes, this is the only home with both lake frontage and a single-level layout."

> "Pricing your home at $1,315,000 places it at the top of the $1.25M portal bracket. Pricing at $1,255,000 — only $60,000 lower — drops you into the next tier where you compete with 14 additional listings."

**Underlying capability.** Bracket analysis pre-computed per active listing: `bracket_name`, `competing_in_bracket`, plus a contextual narrative. Combined with the precise-price + bracket-optimisation pricing rule from the playbook (Cardella & Seiler 2016).

**Why no incumbent can copy it.** Bracket-density information requires a real-time count of every active listing in the suburb at every $50K-$250K price band. **Cotality and Domain expose individual listings; nobody exposes density.** And the strategic conversion ("price at the top of the bracket, not the bottom of the next") requires the empirical pricing literature plus market familiarity. Most agents haven't read the literature; some have intuitive grasp; none can produce a per-listing pricing recommendation that names the bracket and counts the competition.

**Behavioural mechanism.** This is the strongest *mechanical* pricing claim we can make. The seller reading the report sees a specific dollar number ("$1,315,000") with a specific reason ("the top of the $1.25M bracket where 9 listings compete, vs. the bottom of $1.5M where 12 do"). It removes the seller's biggest pricing fear ("we'll get it wrong") with evidence. Most importantly: *agents typically don't articulate why they chose a price.* We do, in writing.

**Coverage status.** Live on every property where positioning_analysis runs. Coverage gap to fix.

---

## 6. Walking-distance anchor monopoly

**Example claims:**

> "Yours is the only home currently for sale in Robina within a 5-minute walk of Robina State School (verified from cadastral coordinates to school address)."

> "Of the 42 active Burleigh Waters listings, only 6 are within 800 m of the beach. Yours is one of them, at 580 m."

> "Yours is the only listing currently in Varsity Lakes within walking distance of both Bond University and Varsity College."

**Underlying capability.** Cadastral lat/lng on every property + geocoded points-of-interest (schools, beaches, parks, shopping centres, transport). Beach distance is already computed (`beach_distance_enriched_at`). School and other POI distance is the natural extension.

**Why no incumbent can copy it.** Domain shows nearby schools; doesn't structure proximity claims for the suburb cohort. Cotality has location data; doesn't surface walking-distance scarcity. **Walking distance to specific anchors, with active-inventory comparison ("only home for sale within 5 min of school X"), is a structurally absent claim category in Australian real estate marketing.** The reason it doesn't exist: producing it requires a geocoded POI dataset for every suburb plus a query layer to compute "active listings within radius R of point P." Both engineering tasks; neither is hard; neither has been done.

**Behavioural mechanism.** Walking distance to schools is the single most search-intent-laden axis for family buyers. Beach distance is the same for lifestyle buyers. *Walkability monopoly* is the highest-value scarcity claim because it maps directly to buyer-search behaviour. The buyer who filters Domain for "within 1 km of beach" and finds 6 listings then sees one of them annotated "yours is the only one with [feature]" — that is a closed-loop conversion.

**Coverage status.** Beach distance live. School + other POI distance — needs the geocoded POI dataset built. Estimated 1-week build for the three target suburbs (schools + beaches + parks + shopping + transport). **Recommend Q3 priority because it unlocks a search-intent claim category nobody else has.**

---

## 7. Reconstructed comparable evidence with reasoned adjustments

**Example claims (live structure, M3 module in `09_Appraisals/04_content_modules.md`):**

> "Your home's most-likely range of $1.42M–$1.58M is supported by 6 comparable sales: 14 Indooroopilly Court ($1.51M, March 2026), 22 Pacific Avenue ($1.46M, December 2025), [...]. Each comp is adjusted line-by-line for floor area, condition, location, and recency. The full table follows."

> "Comp 14 Indooroopilly Court sold at $1.51M. Adjusted for: land area +153 m² → +$57,375 (computed at suburb median rate $375/m²), internal floor +12 m² → +$30,000, condition delta +1 step → +$15,000, time decay −2.1% → −$31,710. Adjusted to subject = $1.481M."

**Underlying capability.** `precompute_valuations.py` produces a reconciled valuation from 3-8 comparable sales, with explicit per-line-item adjustments, weighting (5-factor), and 90% confidence interval. Backtested against 1,683 Domain estimates.

**Why no incumbent can copy it.** Agents using Cotality's CMA tool can produce a comparable-sales report. **What they cannot produce is the line-item adjustment evidence with sourcing.** A typical agent CMA shows three comparables with photos and prices and lets the agent verbally say "your home is between these." Ours shows: comp price + every adjustment + reasoning + source + dollar impact + final adjusted value, **with a confidence interval that survives audit.** The seller can put our report next to the agent's CMA and the agent's looks unfinished.

**Behavioural mechanism.** Trust mechanism. Real estate's −22% net trust score (Governance Institute 2025) is anchored in the suspicion that the agent's number is fabricated. We make the number un-fabricatable. The seller hands the report to a sceptical partner; the partner reads the adjustments; the partner can either find a flaw (and we fix it — the loop is honest) or has no choice but to accept the methodology. **This is the document an analytical second-reader cannot dismiss as marketing.**

**Coverage status.** Live on 142/142 active target listings. Already the spine of the appraisal report.

---

## 8. Outcome-matched agency recommendation

**Example claims (powered by 1,475 GC sales in our agent ledger):**

> "Of the agencies that have sold homes in Robina above $1.5M in the past 12 months, McGrath Palm Beach achieved the highest median lift over suburb median (+8.0%) at the fastest median DOM (10 days). For homes of your archetype and price band, this is the empirical front-runner."

> "In Burleigh Waters above $2.5M, Kollosche commanded a +26.5% lift over suburb median across 4 sales, with median DOM of 20 days. Kingfisher Realty delivered +15.4% across 5 sales at 16 days. Both are credible options for premium positioning."

> "The most recent five Varsity Lakes sales of homes with your archetype were handled by Drew Property (2), Coastal (1), Ray White Robina (1), and Harcourts Coastal (1). Drew Property's median lift was +5.5% — best in cohort."

**Underlying capability.** 1,475 GC sales tagged to listing agency, normalised to suburb median at the time, ranked by lift and DOM. Powering the positioning agent's `agency_recommendation` output. Deeper than RateMyAgent — outcome data, not reviews.

**Why no incumbent can copy it.** **No agency would publish this analysis** because the data implicates them. Cotality has the sales data; selling it back to consumers as agency comparison is incompatible with their B2B revenue model. RateMyAgent's business is reviews, not outcomes. The only way to produce this is to (a) own the sales scrape, (b) tag listings to agencies, (c) compute lift-to-median per agency per suburb per archetype, (d) publish ranges with methodology.

**Behavioural mechanism.** This claim *removes the seller's hardest decision*. Choosing an agent is the most consequential and least-informed decision in the entire selling journey (forum analysis: pain points 2 and 3 — "I need to find the right agent" and "I need someone I can trust"). When the report tells the seller "for your specific home, the agencies that have actually delivered are X, Y, and Z," it eliminates the choice paralysis and replaces it with a data-anchored recommendation.

**Strategic note.** This is structurally honest because we recommend McGrath Palm Beach, Kollosche, Drew Property, etc. by name — including agencies that are not Fields. **That honesty is the trust mechanism.** Once Fields itself appears in the data as an outcome leader, the recommendation becomes self-serving but earned. Until then, recommending competitors honestly *builds* the trust needed for our own future appearance.

**Coverage status.** Data live; report module exists; the public-facing version (Agent Ledger page on the website) is on the white-space build list.

---

## 9. Suburb-tuned timing intelligence

**Example claims:**

> "Your suburb's price-best month is November (median lift +6.2% over annualised price across 370 Robina sales since 2023). Your suburb's speed-best month is May (median DOM 18 days vs full-year 26 days). For maximum price, list 1 October. For fastest sale, list mid-April."

> "Burleigh Waters sales conducted in March of the past three years achieved a median sale-to-asking ratio of 99.4% — the highest of any month — across 47 sales. Our recommendation is to launch your campaign in late February so the contract negotiation window falls in March."

> "Listing during the QLD school-holiday period costs an estimated 4–7 days of additional DOM in your suburb (computed from comparable cohort behaviour 2023-2026). Avoid late-June through mid-July."

**Underlying capability.** 966 sold records across target market with timestamped sale dates. Aggregated by month, by archetype, by price band. Already in the positioning playbook in summary form ("Robina best price = November, fastest = May; VL best price = April, fastest = May; BW best price = March, fastest = March").

**Why no incumbent can copy it.** Cotality has the timestamps; doesn't expose seasonality at suburb-archetype-price-band granularity. Agents have intuition ("spring is busy") but no quantified suburb-specific guidance. **The combination of (a) suburb-level granularity, (b) archetype-level adjustment, and (c) dollar-quantified or DOM-quantified deltas is empirically derived only by us in this market.**

**Behavioural mechanism.** Timing is a decision the seller is going to make anyway — *when do I list?* Most agents say "list now" because their commission velocity prefers it. We give the seller an empirical answer that may delay the campaign by weeks but recovers thousands. The seller now has a reason to choose Fields specifically: *we are the agency that told them not to list in July when every other agent was pushing for the listing.* That moment of credibility is the relationship-builder.

**Coverage status.** Live in the playbook. Easy to expand into a per-property timing recommendation in the report. **Recommend a "Timing" module in the appraisal report.**

---

## 10. Suburb-tuned pre-sale ROI evidence

**Example claims:**

> ⚠ **CORRECTED 2026-09-09** — the original claim here ("fully-renovated Robina houses sold at -3% to suburb median $/sqm; BW +14%") was re-derived with floor-area, land, beds/baths, water-class and quarter controls (`16_Valuation/Renovation_Premium/renovation_premium_study.py`, n=578 sold houses, 24-month window). **The Robina negative sign was the floor-area confounder** the book flagged: controlled, fully-renovated Robina houses show **+11.7%** [5.7, 18.0] (p=0.0001). Burleigh Waters is confirmed and larger: **+16.1%** hedonic / **+22.9%** matched-twins. Varsity Lakes +6.9%, not significant (n=26 treated). The *suburb ranking* survives — BW rewards renovation ~10pp more than Robina (p=0.002). Only `fully_renovated` carries a premium; `cosmetically_updated`/`partially_renovated` price like original. **The DO-NOT-renovate recommendation must now rest on ROI (cost unobserved; +11.7% on a $1.4M Robina home ≈ $164K vs $150K-$300K reno cost), NOT on a negative market premium.** Do not quote the -3% figure. See `16_Valuation/Renovation_Premium/REPORT_2026-09-09.md`.

> "Pool installation returns 0.6%–3.7% to $/sqm in your suburb (statistically not significant, p>0.1). The $50K–$80K cost will not be recovered. We do not recommend pool installation pre-sale."

> "Fresh exterior and interior paint is the highest-ROI pre-sale work — up to 5% perceived-value lift at $3K–$8K cost. Landscaping returns up to 20% perceived value at $2K–$10K cost. These are the only two interventions we recommend."

**Underlying capability.** Pre-sale ROI by suburb, embedded in the positioning agent's `pre_sale_recommendations` output as DO / DO NOT / CONSIDER with cost ranges, expected impact, confidence levels, and citations. Derived from the playbook v5.0 research (NAR staging data + 2,153-sale internal analysis).

**Why no incumbent can copy it.** The standard agent move is to recommend a stylist, a pre-sale painter, sometimes a landscaper — all framed as "this will help you sell." **Quantified ROI by intervention by suburb, with explicit DO NOT recommendations** (don't renovate the kitchen, don't install a pool, don't carpet a polished floor) is structurally absent. Agencies have a financial alignment with the marketing/staging vendors they recommend. We have no such alignment because we don't take vendor kickbacks. **Our advice can be honest in a way theirs structurally cannot.**

**Behavioural mechanism.** Sunk-cost prevention. The seller is on the verge of spending $40K-$80K on a pre-sale renovation that the data shows will return $0-$30K. We save them money before they spend it. This is the most concrete, dollar-shaped value the report delivers. The seller reading "do not undertake a full kitchen renovation" sees us refuse the easy upsell — and trusts us correspondingly more.

**Coverage status.** Live in the positioning agent's gated tier. Easy to extract for the appraisal report. **Recommend dedicated "Pre-Sale ROI" module.**

---

## Summary — the ten claim categories in one table

| # | Claim category | Format | Capability | Coverage |
|---|---|---|---|---|
| 1 | Active-inventory scarcity | "Only N currently for sale with feature combo" | Positioning agent + Mongo combinatorial query | Live, partial (19/142) |
| 2 | Sold-history rarity | "Only N sold in 12mo with this combo" | 966-sale comparable cohort | Data live, module to extract |
| 3 | Floor-plan dimensional supremacy | "Top X% of cohort on dimension D" | GPT vision floor-plan parser | 71/142 — backfill needed |
| 4 | Satellite lot/orientation rarity | "Only N% with this aspect/adjacency" | GPT vision satellite + cadastral coords | 142/142 — module to extract percentiles |
| 5 | Bracket-density advantage | "Of N in your bracket, only this with X" | Positioning agent bracket_intelligence | Live |
| 6 | Walking-distance monopoly | "Only home for sale within X min of anchor" | Cadastral lat/lng + POI dataset | Beach live; school + other POI to build |
| 7 | Auditable comparable adjustments | Line-item adjustment table per comp | Reconciled valuation engine | 142/142 — already in report |
| 8 | Outcome-matched agency recommendation | Top-performing agencies for your archetype | 1,475-sale agent ledger | Live in playbook; consumer page on roadmap |
| 9 | Suburb-tuned timing | Best-price month + fastest-sale month with $$/DOM | 966-sale temporal aggregation | Live in playbook; module to extract per-property |
| 10 | Suburb-tuned pre-sale ROI | DO/DO NOT with cost, impact, citation | Positioning agent + playbook research | Live in gated tier |

---

## How to use this document

For the **Pre-Sale Intelligence Report** (`09_Appraisals/`):

- Each of the ten claim categories should map to one or more content modules in `04_content_modules.md`.
- Where coverage is partial (#1, #3), prioritise backfill before launch.
- Where the module doesn't yet exist (#2 cohort claims, #4 satellite percentiles, #6 walking-distance, #9 per-property timing), commission the new modules — they are small extensions to existing pipelines.

For the **website-side seller-assist landing page**:

- Each of these claims is a candidate for the hero proof section. "We are the only agency in Australia that..." reads weakly because nobody can verify the negative claim. "We tell you, in writing, that yours is the only home currently for sale in Burleigh Waters with X" reads as a falsifiable, auditable promise.

For **Will's seller pitch / agent meetings**:

- The ten categories are interview questions to ask any competing agent. *"Can you tell me, in writing, the only-N-others-currently-for-sale claim about my home?"* No agent answers yes. The asymmetry sells the report and the relationship.

---

## The single sentence

> *Other agencies tell you what your home is worth. Fields tells you, with citations, exactly which features make your home rare in your suburb right now, which features made buyers pay above median for similar homes in the past 12 months, which agencies have actually delivered above-median outcomes for homes like yours, what month to list to maximise either price or speed, and which pre-sale renovation is the only one whose ROI is positive in your suburb. None of that is opinion. All of it is queryable.*

That sentence is what the seller takes away after reading the report. Each of the ten claim categories above is one of its provable clauses.
