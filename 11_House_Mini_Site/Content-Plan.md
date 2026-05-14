# House Mini-Site — Content Plan

**Version:** 1.0 · **Date:** 2026-05-14 · **Status:** Build-ready content brief
**Parent docs:** [Design.md](Design.md) · [Concept.md](Concept.md)
**Source content:** [`08_Seller-Book/Fields_book.pdf`](../08_Seller-Book/Fields_book.pdf) · [`09_Appraisals/Version_Four/`](../09_Appraisals/Version_Four/)

---

## 1. Scope

This document is the **bridge between the book and the mini-site**. It maps every one of the 15 Halo seller fears to:

1. The source content (which book chapter, which V4 spread, which DB query).
2. The mini-site location (which tab, which block).
3. The copy pattern (headline + thesis + applied-to-your-home).
4. The personalisation slots (what swaps per property).
5. The data sources that fill the slots.

Once this document is signed off, an implementer can build each `FearSection.tsx` instance with no further briefing.

---

## 2. The Copy Pattern (Universal Template)

Every fear section in `#process` (and most blocks elsewhere) follows the same skeleton:

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADLINE                                                       │
│  [Fear restated in seller's own words]                          │
│  e.g. "Will the buyer's finance fall through?"                  │
│                                                                 │
│  SUBHEAD                                                        │
│  [Reframe in one sentence with a number]                        │
│  e.g. "It happens in ~7% of southern Gold Coast sales.          │
│         Here is how we manage the risk."                        │
├─────────────────────────────────────────────────────────────────┤
│  THESIS PANE                            APPLIED-TO-YOUR-HOME    │
│  ─────────────                          ─────────────────────   │
│  [Data from book]                       [Same data, specific    │
│  [Chart]                                 to subject property]   │
│  [Citation]                             [Property-specific      │
│                                          number]                │
├─────────────────────────────────────────────────────────────────┤
│  CITATION STRIP                                                 │
│  Source: [book Ch X / DB query / appraisal section]             │
│  Last reviewed: [date]                                          │
└─────────────────────────────────────────────────────────────────┘
```

This is the same pattern V4 print uses across all six spreads. **Pattern repetition is what makes the document feel authored, not assembled.**

---

## 3. The Fear-by-Fear Content Matrix

Below: every one of the 15 Halo fears, fully briefed for build.

The legend used throughout:

- **Slot syntax:** `{slot_name}` — server-side substitution from `property_reports` doc.
- **Suburb-aware:** ✅ means copy adapts per suburb.
- **State-aware:** ✅ means content changes between under-review and final states.

---

### Fear #1 — Agent Selection (Halo vol: 10.7%, #1 topic)

> *"How do I know which agent to trust? Are they all just trying to win the listing with an inflated price?"*

| Field | Value |
|---|---|
| **Tabs** | `#next` (primary) + `#process` (Agent Scorecard section) |
| **Book source** | Chapter 6 (1,475-sale agent volume analysis) + Chapter 6 (9.6% premium gap finding) |
| **V4 source** | S06 Trust spread |
| **DB queries** | `system_monitor.fb_agent_comparisons` (if exists), agent listing volume from `Gold_Coast.<suburb>` |
| **Personalisation** | Suburb-aware ✅ |

**Headline:** "How do you choose an agent without rolling a dice?"

**Subhead:** "We analysed 1,475 Gold Coast sales by agent volume. The busiest agent does not get the best price — and the difference is bigger than most sellers realise."

**Thesis pane:**
> Chart CH6-1 ("Does the busiest agent get the best price?"). The data: agents in the top decile by volume achieve median sale prices indistinguishable from the median across all agents — within 0.4%. Specialist agents (5-15 sales/year in a single suburb) outperformed by 2.8% on average, controlling for property and timing.

**Applied-to-your-home pane:**
> "In {suburb}, {n_active_agents} agents have sold a property in your price bracket in the last 12 months. Of those, {n_specialists} fit the specialist profile. The single best comparable transaction in your price range was sold by {agent_name} on {date} for {price}."

**Citation strip:** Source: 1,475 GC sales analysis, Before You List Ch 6 · Last reviewed: {data_pull_date}

**CTA:** *"Compare us against any agent. We will prepare the comparison ourselves."*

---

### Fear #2 — Legal Requirements / Settlement Coordination (Halo vol: 10.2%, #2 topic)

> *"What if my settlement falls over? What if I'm homeless between the sale and the next purchase?"*

| Field | Value |
|---|---|
| **Tab** | `#process` (Settlement section) |
| **Book source** | Chapter 8 (selling process — 5 phases) |
| **V4 source** | — |
| **DB queries** | `Gold_Coast.<suburb>` for typical settlement durations |
| **Personalisation** | Suburb-aware ✅ |

**Headline:** "Same-day settlement on the southern Gold Coast — what it actually requires."

**Subhead:** "QLD law allows it. Most agents won't coordinate it. Here is the playbook we use, step-by-step."

**Thesis pane:**
> The five phases of a QLD sale: contract → finance approval → building & pest → unconditional → settlement. Median elapsed time across {suburb} for the last 12 months: {avg_days} days. The single most common failure point is finance falling through during the {finance_window}-day window.

**Applied-to-your-home pane:**
> "For {address}, a standard 30-day contract gives us {n_business_days} business days to coordinate buyer-side conveyancing, building & pest, and your onward purchase. If you need same-day settlement on a forward purchase, we start that coordination on Day 1 of the contract — not Day 25."

**Citation strip:** Source: Before You List Ch 8, QLD Property Law Act 2023, {n_sales} recent {suburb} sales · Last reviewed: {data_pull_date}

---

### Fear #3 — Tax Implications / CGT (Halo vol: 6.0%)

> *"If I sell, what's my CGT bill? Am I going to give a third of my gain to the ATO?"*

| Field | Value |
|---|---|
| **Tab** | `#process` (Tax Considerations section) |
| **Book source** | None directly — we have CGT research separately |
| **V4 source** | — |
| **DB queries** | Historical purchase price (if in DB) + suburb median growth from `precomputed_indexed_prices` |
| **Personalisation** | Suburb-aware ✅, state-aware ✅ |

**Headline:** "What you may owe in tax — and the rules that matter most."

**Subhead:** "We do not give tax advice. We do show you the questions to ask, the rules that apply most commonly, and a worked example anchored to your suburb."

**Thesis pane:**
> The four rules that decide whether CGT applies:
> 1. Was this your principal place of residence (PPOR) throughout ownership?
> 2. If it became an investment property, did you nominate the six-year rule?
> 3. Was it purchased before 20 September 1985 (pre-CGT)?
> 4. Are you an Australian tax resident?
>
> The Sarah-and-Mark worked example from the book — adapted to your suburb's growth profile — sits below.

**Applied-to-your-home pane:**
> "Properties in {suburb} have appreciated a median {growth_pct}% over the last {years} years. If your home was purchased in {est_purchase_year}, indicative capital gain on a {price_bracket} sale would land in the {indicative_gain_range}. **This is illustrative, not advice. We always recommend a tax professional reviews your specific case before contract.**"

**Citation strip:** Source: ATO CGT rules, indexed price data from {n_sales} {suburb} sales · Last reviewed: {data_pull_date}

**Editorial note:** This section must include the disclaimer in bold. It also must not include a single CGT figure as a single number — always a range.

---

### Fear #4 — Mortgage / Sell-First vs Buy-First (Halo vol: 5.4%)

> *"Should I sell first or buy first? What if I can't find a new home in time?"*

| Field | Value |
|---|---|
| **Tab** | `#process` (Sell First or Buy First section) |
| **Book source** | Chapter 8 (selling process) — touched but expand |
| **V4 source** | — |
| **DB queries** | Days-on-market for both target sale price bracket and likely purchase price bracket |
| **Personalisation** | Suburb-aware ✅ |

**Headline:** "Sell first or buy first? The maths is rarely about preference."

**Subhead:** "The right answer depends on your equity, your loan-to-value, and how long the market in your *next* suburb takes to find you a home."

**Thesis pane:**
> The four scenarios:
> 1. **Sell first, rent in between** — lowest risk, but you carry move costs twice. Recommended when LVR is high or market is uncertain.
> 2. **Sell first, buy with bridging** — moderate risk, banks lend on a documented sale contract. Most common option.
> 3. **Buy first, contingent contract** — rare in QLD because contingent clauses lengthen buyer-side commitment.
> 4. **Buy first with bridging finance** — highest risk, requires strong equity buffer. Capital costs $X-$Y per month while you hold two properties.

**Applied-to-your-home pane:**
> "Median days-on-market in {suburb} right now: {dom_sell} days. Median days-on-market in your likely next suburb({next_suburb}) for a property at your indicative purchase budget: {dom_buy} days. That gives you a typical window of {gap} days to coordinate. For your situation we would model {recommended_scenario} — and would discuss this in the consultation."

**Citation strip:** Source: Before You List Ch 8, current {suburb} market data · Last reviewed: {data_pull_date}

---

### Fear #5 — Tenant in Place / Investor Sale (Halo vol: 5.3%)

> *"Can I sell with my tenant in place? Will tenants kill my sale price?"*

| Field | Value |
|---|---|
| **Tab** | `#process` (Tenant in Place section) |
| **Book source** | None directly — we have investor analytical assets separately |
| **V4 source** | — |
| **DB queries** | Recent IP sales in suburb with/without tenant — `Gold_Coast.<suburb>` filtered by `was_tenanted` |
| **Personalisation** | Conditional render — only if avatar = Savvy Investor, otherwise hidden in low-priority position |

**Headline:** "Selling with a tenant in place — the discount, the upside, and when each matters."

**Subhead:** "Tenanted investment sales typically transact 2-5% below comparable vacant-possession sales — but the buyer pool is different, and so is the campaign."

**Thesis pane:**
> Two buyer pools matter:
> 1. **Investor buyers** — value continuing rental income, will pay the going yield. Tenanted sale is a feature.
> 2. **Owner-occupier buyers** — value vacant possession, will not buy with a fixed-term tenancy.
>
> The premium-vs-discount question depends entirely on which pool dominates your price bracket in your suburb.

**Applied-to-your-home pane:**
> "In {suburb}, {investor_pct}% of sales in your price bracket over the last 12 months went to investor buyers. Median yield: {yield_pct}%. Your current tenancy expires {tenancy_end_date} (if known). For your property we would advise (in the consultation) whether to sell tenanted or vacant — based on your indicative buyer pool."

**Citation strip:** Source: {n_sales} {suburb} investor sales · Last reviewed: {data_pull_date}

---

### Fear #6 — Property Valuation (Halo vol: 3.7%)

> *"Why do three agents give me three different valuations? Which one is real?"*

| Field | Value |
|---|---|
| **Tab** | `#valuation` (already built at v0.3) |
| **Book source** | Chapter 1 (1,689 Domain estimates tested, 89% overvalued) |
| **V4 source** | S03 Valuation / Hedonic Decomposition |
| **DB queries** | Comp engine, `valuation_data` field on subject property |
| **Personalisation** | Suburb-aware ✅, state-aware ✅ |

**Headline:** "What is your home worth — and how do we know?"

**Subhead:** "We tested 1,689 Domain estimates against actual sale prices on the Gold Coast. 89% were over by an average of 11.4%. Our model is built on the alternative: comparable sales, transparent adjustments, and a human review."

**Thesis pane:**
> The hedonic decomposition method: a base land value + improvements value + adjustments (land area, condition, location, view, internal area). Each adjustment is sourced from a regression of {n_sales} sales within {suburb}. The output is a range, not a number — because no two properties are identical and we are honest about the uncertainty.

**Applied-to-your-home pane:**
> For State 1 (under-review): "Mac is selecting the six comparable sales that anchor your valuation. The working range based on our model alone is {model_range}. We will replace this with the final reconciled range once Mac has walked through your home." For State 2 (final): the full V4 page 11 pattern — listing price, target sale price, four-condition checklist, six named comps line-itemised with adjustments.

**Citation strip:** Source: Before You List Ch 1, Domain backtest of 1,689 estimates, six named comparable sales · Last reviewed: {data_pull_date}

---

### Fear #7 — Market Analysis (Halo vol: 3.3%)

> *"Is now actually the right time to list? What's the market doing?"*

| Field | Value |
|---|---|
| **Tab** | `#market` (primary) |
| **Book source** | Chapter 2 (13,585 GC sales seasonal analysis) + Appendix C (wage growth, population) |
| **V4 source** | — |
| **DB queries** | `precomputed_market_charts` + `precomputed_indexed_prices` for {suburb} |
| **Personalisation** | Suburb-aware ✅ |

**Headline:** "The market you are selling into — read clearly."

**Subhead:** "{suburb} has cleared {sale_count} sales in the last 12 months. The leading indicator is wage growth (r = 0.940 with prices, Abelson et al. 2005). Here is where the suburb sits right now."

**Thesis pane:**
> The four-tile grid: Fields Confidence Index (FCI), median days on market, active listings, wage-growth indicator. Each tile shows the value, the 12-month trend, and the historical reference range. The chart underneath: prices indexed to 100 = January five years ago, with the subject suburb plotted against the Gold Coast index.

**Applied-to-your-home pane:**
> Direct reading: "For a {bed}-bedroom home priced {price_bracket} in {suburb}, the current absorption rate is {absorption} listings per month against {sales_rate} sales per month. The {n}-week trend in active listings is {trend_direction}."

**Citation strip:** Source: {data_source_count} {suburb} sales, Before You List Appendix C · Last reviewed: {data_pull_date}

---

### Fear #8 — Home Improvements / Pre-Sale Prep (Halo vol: 3.1%)

> *"Should I renovate before I sell? What if I spend $30K and don't get it back?"*

| Field | Value |
|---|---|
| **Tabs** | `#process` (Property Prep Checklist) + `#positioning` |
| **Book source** | Chapter 5 (presale ROI), Appendix A (room-by-room checklist) |
| **V4 source** | — |
| **DB queries** | Subject property listing photos for condition assessment |
| **Personalisation** | Property-specific ✅ |

**Headline:** "What to fix, what to leave, what to *never* spend money on."

**Subhead:** "Chart 5-4 shows where your pre-sale dollars have the highest return on the southern Gold Coast. The pattern is consistent: presentation > kitchens > bathrooms > extensions."

**Thesis pane:**
> The five categories of pre-sale spending:
> 1. **Free presentation** (declutter, deep clean, gardens) — typical return: $15K-$45K on a $1M home.
> 2. **$500-$2,000 cosmetic** (paint touch-ups, light fixtures) — typical return: 5-8× spend.
> 3. **$5,000-$15,000 kitchen refresh** (new benchtop, doors, splashback) — typical return: 2-3× spend.
> 4. **$30,000+ renovations** — typical return: rarely better than 1.2× spend, often less.
> 5. **Structural changes** — almost never recovered within 12 months.

**Applied-to-your-home pane:**
> Generated from listing photos (where available): "Your kitchen appears in {condition_grade} condition (based on the photo analysis we run on every listing). The most likely opportunities for return are {top_three}. We would only recommend spending in categories 1-2 unless the property has been off-market for 5+ years."

**Citation strip:** Source: Before You List Ch 5, photo analysis pipeline · Last reviewed: {data_pull_date}

---

### Fear #9 — Contract Terms (Halo vol: 3.0%)

> *"What happens during the cooling-off period? What if finance falls through?"*

| Field | Value |
|---|---|
| **Tab** | `#process` (Contract Terms section) |
| **Book source** | Chapter 8 (selling process — surprises) |
| **V4 source** | — |
| **DB queries** | Subject property metadata |
| **Personalisation** | Suburb-aware ✅ (QLD-specific) |

**Headline:** "The clauses that decide whether your sale actually settles."

**Subhead:** "Four standard clauses do most of the work. Knowing them in advance prevents the three most common surprises."

**Thesis pane:**
> 1. **Cooling-off** (QLD: 5 business days, buyer-side, 0.25% penalty if rescinded).
> 2. **Subject to finance** (typical 14-21 days, extensible by mutual agreement).
> 3. **Subject to building & pest** (typical 7-14 days, must be reasonable grounds to terminate).
> 4. **Settlement date** (typically 30-60 days from contract, longer for new-build chains).
>
> The three common surprises: (1) buyer asking for finance extension in the final 48 hours; (2) building & pest used as price-renegotiation lever; (3) settlement delay due to bank operational issues.

**Applied-to-your-home pane:**
> "For {address}, our standard contract structure on similar QLD properties has been {standard_pattern}. We would discuss whether to vary this — for example, shorter cooling-off in exchange for a higher offer — in your consultation."

**Citation strip:** Source: Before You List Ch 8, QLD Property Law Act · Last reviewed: {data_pull_date}

---

### Fear #10 — Selling Costs (Halo vol: 3.0%)

> *"What is this *actually* going to cost me?"*

| Field | Value |
|---|---|
| **Tab** | `#process` (Cost-of-Sale section) |
| **Book source** | Chapter 6 (commission analysis), Chapter 7 (vendor-paid math) |
| **V4 source** | — |
| **DB queries** | Subject property estimated price for commission calculation |
| **Personalisation** | Property-specific ✅ |

**Headline:** "Every cost. Every line. No surprises."

**Subhead:** "Commission, marketing, conveyancing, mortgage discharge, agent's-trust fees. Here is the full picture, scaled to your property."

**Thesis pane:**
> Chart CH6-2 ("Commission is a cost. But not the biggest."). The full cost map of a typical $1.2M GC sale: commission (~$28K-$36K), marketing (~$3K-$8K vendor-paid), conveyancing (~$1.5K-$2.5K), mortgage discharge (~$300-$1.5K), miscellaneous (~$1K). Total: ~5-7% of sale price. The biggest single cost is *not* commission — it is the gap between an excellent and an adequate campaign, which Chapter 7 shows is typically $50K-$100K.

**Applied-to-your-home pane:**
> "For an indicative sale price of {price_range}, the cost stack we would model is:
> - Commission (Fields): {fields_commission_range}
> - Marketing (vendor-paid, REA Premiere Plus + curated): {marketing_estimate}
> - Conveyancing (your solicitor): {conveyancing_estimate}
> - Mortgage discharge: {discharge_estimate}
>
> Total estimated cost: {total_estimate} ({pct_of_sale}% of sale price)."

**Citation strip:** Source: Before You List Ch 6 & Ch 7, {n_recent_sales} recent {suburb} sales · Last reviewed: {data_pull_date}

---

### Fear #11 — Listing Platforms (Halo vol: 2.8%)

> *"Where should my home actually appear online?"*

| Field | Value |
|---|---|
| **Tabs** | `#positioning` + `#market` |
| **Book source** | Chapter 7 (Standard vs Premiere Plus, demand concentration) |
| **V4 source** | S04 Targeting / Reach |
| **DB queries** | — |
| **Personalisation** | Suburb-aware ✅ |

**Headline:** "REA, Domain, Facebook, Google — where buyers actually look for a home like yours."

**Subhead:** "Chart 7-1 shows the split: 28% of buyers are *active* (browse the portals), 72% are *passive* (won't see your home unless we put it in front of them)."

**Thesis pane:**
> Two buyer pools:
> 1. **Active buyers (28%)** — already on REA/Domain searching. The portal listing reaches them. Premiere Plus expands reach within the active pool by ~3×.
> 2. **Passive buyers (72%)** — not browsing, but will buy if shown the right property. Reached only via Facebook/Instagram/Google paid campaigns, agent database, or off-market network.
>
> Most campaigns spend 100% of vendor-paid marketing on the active 28%. We design campaigns that allocate to both pools.

**Applied-to-your-home pane:**
> "For your property in {suburb}, our indicative campaign mix is: REA Premiere Plus ({rea_share}%), Domain Gold ({domain_share}%), Facebook+Instagram retargeting ({fb_share}%), Google Display for nearby suburb interest ({google_share}%). Total reach estimate: {reach_estimate} relevant impressions over the first 14 days."

**Citation strip:** Source: Before You List Ch 7, V4 spread S04 · Last reviewed: {data_pull_date}

---

### Fear #12 — Auction Process (Halo vol: 2.8%)

> *"Auction or private treaty? What happens if no one bids?"*

| Field | Value |
|---|---|
| **Tab** | `#market` (Auction vs Private Treaty section) |
| **Book source** | Chapter 3 (Univ Sydney 1.2M study, QLD legislation, 72% buyer skip rate), Appendix B (Deakin study) |
| **V4 source** | — |
| **DB queries** | Method-of-sale outcomes by suburb + property type |
| **Personalisation** | Suburb-aware ✅, property-type-aware ✅ |

**Headline:** "Auction or private treaty? The honest version."

**Subhead:** "On the southern Gold Coast, auction works well in a small number of specific situations. For most properties, private treaty achieves a higher sale price. Here is how the data lands for your property type."

**Thesis pane:**
> Chart CH3-1 ("72 out of 100 buyers scroll past"). Auction listings — "Auction" or "Contact Agent" — are skipped by 72% of buyers who would otherwise click. The Univ Sydney study of 1.2M listings found auction underperformed private treaty by 1.7% on average. Auction works when (a) genuine multi-buyer competition exists; (b) the property is highly atypical and hard to comp; (c) timing pressure favours the seller. Otherwise: private treaty.

**Applied-to-your-home pane:**
> "In {suburb} over the last 12 months, {auction_pct}% of homes in your price bracket sold by auction. Of those that did go to auction, {clearance_rate}% cleared on the day. For a {bed}-bedroom, {property_type} home, our indicative recommendation is {recommendation} — we would refine this based on current buyer demand in your bracket during the consultation."

**Citation strip:** Source: Before You List Ch 3 & App B, {n_sales} {suburb} sales · Last reviewed: {data_pull_date}

---

### Fear #13 — FSBO / Private Sale (Halo vol: 2.7%)

> *"Should I just sell it myself and save the commission?"*

| Field | Value |
|---|---|
| **Tab** | `#process` (FSBO Honest Comparison section) |
| **Book source** | Chapter 6 (commission as cost vs outcome) — plus the existing US academic research (Hendel/Nevo, Bernheim/Meer, Levitt/Syverson) we already have in memory |
| **V4 source** | — |
| **DB queries** | — |
| **Personalisation** | Property-specific ✅ |

**Headline:** "You could sell it yourself. Here is exactly what the gap looks like."

**Subhead:** "The US academic literature is consistent: FSBO sales transact at 3.7-4.5% below agent-sold properties, after controlling for property and market. Here is what that means for your property — honestly."

**Thesis pane:**
> Four US studies (Hendel/Nevo 2007, Bernheim/Meer 2013, Levitt/Syverson 2008, Rutherford et al.) consistently find FSBO sales 3.7-4.5% below comparable agent-sold properties. The gap is structural: agents add **liquidity** (more buyers seeing the property), not pricing magic. Where agents do *not* add value: agents selling their own homes also achieve 3.7-4.5% higher prices than their own client homes — same buyer pool, same agent, different incentive alignment.

**Applied-to-your-home pane:**
> "For a property priced in your range, the indicative FSBO discount is {fsbo_range}. The indicative agent commission is {commission_range}. The crossover point — where commission exceeds the FSBO discount — sits at a sale price of approximately {crossover}. **We will tell you honestly which side of that line your property sits on, in the consultation.**"

**Citation strip:** Source: Hendel-Nevo, Bernheim-Meer, Levitt-Syverson, Before You List Ch 6 · Last reviewed: {data_pull_date}

**Editorial note:** This section is brand-defining. The honesty here is what builds trust. Do not soften it.

---

### Fear #14 — Market Timing (Halo vol: 2.6%)

> *"Should I sell now or wait? Is the market about to turn?"*

| Field | Value |
|---|---|
| **Tab** | `#market` (Seasonality section) |
| **Book source** | Chapter 2 (seasonal heatmap, 13,585 sales) + Appendix C (wage growth) |
| **V4 source** | — |
| **DB queries** | `precomputed_market_charts` for seasonal pattern |
| **Personalisation** | Suburb-aware ✅, time-of-year-aware ✅ |

**Headline:** "When to list — month by month, suburb by suburb."

**Subhead:** "Chart 2-1 plots 13,585 Gold Coast sales by month. The pattern is consistent year over year: {peak_months} are the strongest listing windows on the southern Gold Coast."

**Thesis pane:**
> The seasonal heatmap shows median sale-price-to-list ratio by month across the last 6 years. Stronger months see ratios 1.5-3% above weakest months. The driver is *buyer concentration*, not seller scarcity — September-November and February-April have the most buyer activity. December-January is a graveyard for everything except holiday-rental flips.

**Applied-to-your-home pane:**
> "Today is {current_date}. For {suburb}, the next strong listing window opens {next_window_start} and runs through {next_window_end}. From contract to settlement typically takes {avg_contract_days} days, so listing in {recommended_month} would settle around {indicative_settlement}. **We do not believe in predicting where the market will be in 6 months. We do believe in showing you the historical pattern.**"

**Citation strip:** Source: Before You List Ch 2, 13,585 GC sales · Last reviewed: {data_pull_date}

---

### Fear #15 — Selling Strategy / Finance Fall-Through (Halo vol: 2.5%)

> *"What if the buyer can't get finance? What if my campaign just dies?"*

| Field | Value |
|---|---|
| **Tabs** | `#process` (Finance Fall-Through section) + `#positioning` |
| **Book source** | Chapter 7 (first 7-10 days, demand concentration) |
| **V4 source** | S04 Targeting |
| **DB queries** | — |
| **Personalisation** | Property-specific ✅ |

**Headline:** "The first ten days decide the next ninety."

**Subhead:** "Chart 7-1 + Chart 7-3 together tell the story: ~70% of qualified buyer interest concentrates in the first 7-10 days. If a campaign is going to fail, this is where it fails — and where we intervene."

**Thesis pane:**
> The buyer-arrival curve: ~70% of qualified-buyer enquiries arrive in days 1-10, ~20% in days 11-30, ~10% beyond day 30. The implication: if the first 10 days don't produce 3-5 inspections per week and at least one credible offer trajectory, the campaign needs intervention — *price refinement*, *positioning shift*, or *channel reallocation*. The biggest single risk to settlement is not finding a buyer; it is finding a buyer whose finance then falls through. The mitigation: pre-qualified buyer screening before contract.

**Applied-to-your-home pane:**
> "Our standard 10-day milestone for a property like yours in {suburb} is {target_inspections} inspections, {target_enquiries} qualified enquiries, and {target_offers} offer trajectories. We measure these daily. If we are tracking below by Day 7, we adjust — and we tell you exactly what we are adjusting and why."

**Citation strip:** Source: Before You List Ch 7 · Last reviewed: {data_pull_date}

---

## 4. Master Copy Conventions

These apply across every section above.

### 4.1 Headlines
- Must be a question or a calm statement of fact.
- No exclamation marks.
- No superlatives. "The best" → "What the data shows."
- Maximum 12 words.

### 4.2 Subheads
- Always include one specific number.
- Maximum 30 words.
- Always end with a period, never an em-dash.

### 4.3 Body
- Active voice.
- Short sentences. Maximum 25 words per sentence, target 15.
- Specificity over fluency. "658m² lot" beats "generous block."
- Cite within the paragraph, not in a footnote.

### 4.4 Numbers
- Prices always to the dollar: `$1,275,000` not `$1.3M`.
- Percentages to one decimal: `11.4%` not `11%`.
- Ranges use en-dash: `$1,250,000–$1,400,000`.
- Days, months, years spelled out in body, numerals in stats.

### 4.5 Forbidden Words (auto-rejected)
- stunning, nestled, boasting, rare opportunity, robust market
- generous, immaculate, must-see, unique opportunity
- "will" in any predictive sense ("the market will...")
- "you should" (replace with "we would" or "the data suggests")

### 4.6 Citation Strip Format

```
Source: [primary source], [secondary source] · Last reviewed: YYYY-MM-DD
```

Every block has one. No exceptions. The citation strip is the trust mechanism.

---

## 5. The Master Personalisation Slot Registry

Every `{slot_name}` used in this document, plus its source:

| Slot | Source | Type |
|---|---|---|
| `{address}` | Address geocode | string |
| `{suburb}` | Address geocode | string |
| `{bed}` `{bath}` `{car}` | `Gold_Coast.<suburb>` listing or cadastral | int |
| `{price_bracket}` | CatBoost ballpark or final reconciled | range string |
| `{model_range}` | CatBoost output | range string |
| `{n_competitors}` | `Gold_Coast.<suburb>` filtered query | int |
| `{n_active_agents}` | DB query on recent sales | int |
| `{n_specialists}` | DB query on agent volume by suburb | int |
| `{agent_name}` | DB query on best comp | string |
| `{date}` | DB query on best comp | ISO date |
| `{growth_pct}` | `precomputed_indexed_prices` | percentage |
| `{years}` | computed | int |
| `{est_purchase_year}` | DB query if available | int |
| `{indicative_gain_range}` | computed | range string |
| `{dom_sell}` `{dom_buy}` | `precomputed_market_charts` | int |
| `{next_suburb}` | inferred from price tier | string |
| `{tenancy_end_date}` | listing metadata | date |
| `{investor_pct}` | DB query | percentage |
| `{yield_pct}` | DB query | percentage |
| `{sale_count}` | DB query | int |
| `{condition_grade}` | photo analysis pipeline | grade |
| `{top_three}` | photo analysis pipeline | list |
| `{rea_share}` `{domain_share}` `{fb_share}` `{google_share}` | campaign allocation engine | percentages |
| `{reach_estimate}` | computed | int |
| `{auction_pct}` `{clearance_rate}` | DB query | percentages |
| `{recommendation}` | rules engine on property type + market | enum |
| `{fsbo_range}` `{commission_range}` `{crossover}` | computed | numerics |
| `{peak_months}` `{next_window_start}` `{next_window_end}` | seasonal data | dates |
| `{current_date}` | server time | ISO date |
| `{recommended_month}` `{indicative_settlement}` | computed | dates |
| `{target_inspections}` `{target_enquiries}` `{target_offers}` | benchmark table | integers |
| `{data_pull_date}` | last refresh time | ISO date |
| `{n_sales}` `{n_recent_sales}` | DB count | int |

**Implementation rule:** all slots resolve server-side before render. Never client-side. Missing slot data → block hides, never renders an empty `{slot_name}`.

---

## 6. Content Production Workflow

For each new mini-site:

```
Step 0 (the gate):
  - Seller enters their address. Nothing else.
  - No email, no phone, no name.
  - Server issues an anonymous device_token, persisted in localStorage.
  - This is the lowest-friction gate possible. Re-engagement is via the
    printed appraisal (delivered to the address) and voluntary in-page capture.

Step 1 (auto, < 60s):
  - Address geocode → suburb, lat/lng, cadastral lookup
  - DB query to populate {slot_name} values
  - Render under-review state with thesis content from book + applied-to-your-home with slot substitution

Step 2 (auto, nightly):
  - refresh_property_reports.py adds new activity items
  - Citation strip {data_pull_date} updates
  - Comp set refreshed if new sales recorded

Step 3 (optional, T+24h):
  - Day-1 postcard sent to the address. Printed with the mini-site URL
    and a one-line "Mac is reviewing your home — watch progress here."
  - Costs ~$2/unit. Secondary nudge; not load-bearing.

Step 4 (human, T+1 to T+3):
  - Property consultant (Mac) reviews and refines
  - Final valuation published
  - State transitions to "final"
  - Print appraisal triggered
  - If owner.email was voluntarily captured: email sent
  - Otherwise: notification appears in activity feed on next visit, and the
    physical print arrival (Day 5) becomes the notification

Step 5 (ongoing):
  - Living dashboard refreshes
  - Activity feed receives new items
  - Citations stay current
  - Voluntary contact-capture CTAs remain available throughout
```

**The strategic stance:** we do not gate the seller. We earn the right to contact them by delivering work worth being contacted about. The print appraisal is the contact channel — the address is the email.

---

## 7. Content Reuse Inventory (What We Already Have)

The book and V4 appraisal already provide ~85% of the content. Specifically:

**From Before You List (immediate use):**
- All 8 chapter texts
- All 9 charts (PNG, ready to embed)
- All 7 figures (PNG, ready to embed)
- All 17 photographs
- Appendix A (room-by-room checklist)
- Appendix B (auction clearance research)
- Appendix C (Gold Coast price drivers)

**From V4 Appraisal:**
- S02 Buyer thesis copy
- S03 Valuation methodology copy
- S04 Targeting copy
- S05 Positioning copy
- S06 Trust copy

**From Halo Strategy work:**
- The 15 fears in their final form
- The 3 avatar definitions
- The exact seller-language vocabulary

**From mini-site v0.3:**
- 7 React components
- Activity feed system
- Valuation tab (both states)
- Print appraisal reference pattern

**Net new content required:** approximately 6,000-8,000 words across the new `#process` tab — most of which can be extracted from the book and re-cast into the universal template in §2.

---

*Filed: `11_House_Mini_Site/Content-Plan.md` · Owner: Will Simpson · Updated 2026-05-14*
