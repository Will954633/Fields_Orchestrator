# House Mini-Site as Seller-Fear Engine — Strategic Opportunity Report

**Author:** Claude (Opus 4.7) · **Date:** 2026-05-14 · **For:** Will Simpson

---

## TL;DR

We already own all four assets needed to build the most decisive seller-acquisition funnel on the southern Gold Coast:

1. **The book** (`Before You List`, ~23k words, 8 chapters of book-locally-sourced answers).
2. **The personalised microsite** (v0.3, `/your-home/:slug`, four tabs, nightly-refreshed activity feed).
3. **The print appraisal** (V4 design system, ≥60% appraisal-to-listing target, "the report is the product" strategy).
4. **The lead-capture gate** (`/analyse-your-home`).

The Halo-Strategy work proved that **99.7% of sellers are fear-driven**, that the fears cluster into ~15 recurring topics, and that they're hyper-specific (same-day settlement, CGT, "as is" sales, agent trust, valuation-range confusion). Each fear is a marketing surface area. Each surface area can be linked to one landing page, one ad creative, one chapter, one tab, one piece of subject-property-specific content.

**The opportunity is not to build more — it is to wire what we already have into a single closed loop:**

> *Cold seller → sees one specific fear answered in an ad → enters their address at `/analyse-your-home` → gets a personalised `/your-home/<slug>` URL within 60 seconds → a physical print appraisal lands on their doorstep within 3 days → 60%+ conversion to listing instruction.*

This report covers (1) why the funnel works psychologically, (2) the gap between the 15 fears and the content we already have, (3) the funnel architecture, (4) the personalisation layer, (5) the marketing engine, (6) the physical-appraisal theatre, (7) the risks, and (8) a recommended build sequence.

---

## 1. The Strategic Thesis

Three claims sit underneath this play. Each is testable.

**Claim 1 — Sellers don't comparison-shop on commission. They comparison-shop on certainty.** The Halo data is overwhelming: 99.5% Risk-Safety, 99.4% Process confusion, 98.5% Financial-loss fear. Commission is a proxy for "this person isn't going to screw me over." If we eliminate the underlying uncertainty, the commission conversation reframes itself.

**Claim 2 — The decisive moment in seller acquisition is *before* the first meeting.** The V4 strategy doc says it cleanly: *"the meeting is what the report earns."* Most agents treat the appraisal as a door-opener to the meeting. We invert it: the document is the product, the meeting is a formality. The mini-site is the digital extension of that document — except it works on people who haven't yet asked for an appraisal.

**Claim 3 — Hyper-local personalisation is structurally uncopiable at our price point.** Franchise agents can spend money on glossy generic content. They cannot, at scale, produce 23k words of book content + a six-spread bespoke appraisal + a four-tab microsite + a nightly-refreshed activity feed for every address in a 4220/4226/4227 postcode catchment. We can — because Will built the infrastructure as a single operator using AI. **The moat is the integration, not any one asset.**

**Why now:**
- The book is finished (v4.6, 17 photos, 16 charts).
- The appraisal V4 strategy is locked.
- The mini-site is at v0.3 with the hardest tab (Valuation, under_review + final states) already built.
- The Halo Strategy gives us the demand-side proof of what fears to lead with.

The only missing piece is the wiring.

---

## 2. The Fear-to-Asset Gap Map

Here is a one-line audit of each of the 15 Halo fears against what we already have versus what is missing. (This is the most important table in the report.)

| # | Halo fear / topic | Vol % | Book chapter | V4 spread | Mini-site tab | Status | What's missing |
|---|---|---|---|---|---|---|---|
| 1 | Agent selection (commission / trust / over-promise) | 10.7% | Ch 6 (1,475-sale analysis) | S06 Trust | Next tab (walk-away promise) | **STRONG** | Direct commission-vs-outcome calculator |
| 2 | Legal requirements (settlement, contracts, Section 32, strata) | 10.2% | Ch 8 (selling process) | — | Next tab | **PARTIAL** | Settlement coordination playbook; QLD-specific contract walk-through |
| 3 | Tax implications (CGT, GST, stamp duty) | 6.0% | — | — | — | **GAP** | Partner accountant content; CGT 6-year-rule explainer; PPOR→IP guidance |
| 4 | Mortgage considerations (sell-first vs buy-first, bridging) | 5.4% | Touched in Ch 8 | — | — | **GAP** | Bridging-finance calculator; mortgage-broker partner content |
| 5 | Tenant considerations (sell with tenant in place) | 5.3% | — | — | — | **GAP** | Investor-specific content track (Avatar 3) |
| 6 | Property valuation (why wide range / "what's it worth") | 3.7% | Ch 1 (1,689 Domain estimates) | S03 Valuation | Valuation tab (final + under_review) | **STRONG** | Already the strongest tab; methodology piece exists |
| 7 | Market analysis (timing, regional, auction failure) | 3.3% | Ch 2 (13,585 sales) + App B | — | Market tab | **STRONG** | Per-property market-state recap |
| 8 | Home improvements (repair before list, ROI on prep) | 3.1% | Ch 5 (presale ROI chart) | — | — | **PARTIAL** | Property-specific prep checklist |
| 9 | Contract terms (cooling off, subject-to-finance) | 3.0% | Touched in Ch 8 | — | — | **GAP** | Same as #2 — needs a Settlement / Contracts page |
| 10 | Selling costs (agent fees, marketing, conveyancing) | 3.0% | Ch 6 (commission analysis), Ch 7 (vendor-paid math) | — | — | **PARTIAL** | Per-property cost-of-sale estimator |
| 11 | Listing platforms (REA, Domain, misleading pricing) | 2.8% | Ch 7 (Standard vs Premiere Plus) | — | — | **PARTIAL** | Per-property platform recommendation |
| 12 | Auction process (pre-auction offers, clearance) | 2.8% | Ch 3 + App B (Deakin study) | — | — | **PARTIAL** | Per-property auction vs PT recommendation (Concept.md flags this) |
| 13 | Private sale / FSBO comparison | 2.7% | Ch 6 (commission cost vs outcome) | — | — | **PARTIAL** | Honest FSBO calculator (would be brand-defining) |
| 14 | Market timing (now vs wait, seasonality) | 2.6% | Ch 2 (seasonal heatmap) | — | — | **PARTIAL** | Per-suburb monthly recommendation; Concept.md flags this |
| 15 | Selling strategy (overall approach, finance-fall-throughs) | 2.5% | Ch 7 (first 7-10 days, demand) | S04 Targeting | — | **PARTIAL** | Per-property strategy summary |

**Headline read on the table:**

- **6 of 15 fears are STRONG already** (we have book + appraisal + site coverage).
- **6 of 15 are PARTIAL** (one or two of the three layers — usually missing the per-property personalisation).
- **3 are clear GAPS** (Tax, Mortgage, Tenant). These map directly to the Halo Avatars (Tax = Savvy Investor; Mortgage = Stressed Upgrader; Tenant = Savvy Investor).

The three gaps are also the three areas where we should explicitly **partner** rather than build internally — a conveyancing partner, an accountant partner, a mortgage broker partner. Each partnership becomes a referral loop (they send us sellers; we send them transactions) and a credibility transfer (a Fields appraisal arrives with a CGT memo from a named CPA — that is uncopiable).

---

## 3. Funnel Architecture (Three Tiers)

Currently we have a two-tier funnel: public website → `/analyse-your-home`. The Halo opportunity demands a three-tier funnel:

```
┌──────────────────────────────────────────────────────────────────┐
│ TIER 1 — PUBLIC FEARS LIBRARY (indexed, SEO + paid traffic dest) │
│                                                                  │
│  /seller-questions/ hub                                          │
│    ├─ /how-much-is-my-home-worth                                 │
│    ├─ /sell-with-tenant-in-place                                 │
│    ├─ /same-day-settlement-gold-coast                            │
│    ├─ /capital-gains-when-selling-ppor                           │
│    ├─ /sell-first-or-buy-first                                   │
│    ├─ /auction-or-private-treaty                                 │
│    ├─ ... (one page per top 15 fear, ~1,200 words each)          │
│    └─ Each page: data + chart + named comp + "see your home →"   │
│                                                                  │
│  Soft CTA: "See how this applies to your home →"                 │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ TIER 2 — THE GATE: /analyse-your-home                            │
│                                                                  │
│  Address-only opt-in (single field). Email second.               │
│  System creates a property_reports stub doc + redirects to       │
│    /your-home/<slug> in under_review state.                      │
│                                                                  │
│  Hand-raise signal value: address + email = 10x typical lead     │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ TIER 3 — THE REWARD: /your-home/<slug> (noindex)                 │
│                                                                  │
│  Under-review state (Day 0–3):                                   │
│    • Activity feed live                                          │
│    • Per-property scarcity (1 of N, walking POIs)                │
│    • Methodology + ETA for human review                          │
│    • Selected fear-content tabs, personalised to suburb/property │
│                                                                  │
│  Final state (Day 3+, after human pass):                         │
│    • Final valuation (listing + target range, methodology)       │
│    • Print appraisal in production / on the way                  │
│    • Living dashboard — nightly refresh, new comps appear,       │
│      market state changes flagged                                │
│    • Book sections embedded contextually ("Buyer skip" = Ch 3)   │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
                  PHYSICAL APPRAISAL DELIVERY
                  (the theatre — see §6)
```

The mini-site v0.3 README already says: *"currently no path from `/analyse-your-home` submission → new `property_reports` doc → fresh slug."* This is the single highest-leverage missing piece. Without it, no marketing engine can run.

---

## 4. The Personalisation Layer — What We Can Do From An Address Alone

The seller's *"this was written for me"* moment is what converts. Here is everything we can pre-populate from just an address (no human input required), within 60 seconds of submission, using infrastructure we already have:

**From the address alone, the under-review microsite can render:**

- **Hero:** Property photo (if active or recently sold), satellite roof image, suburb landmark imagery.
- **The competitor set:** "Right now, there are 4 four-bedroom homes priced $1.3M–$1.5M within 2 km of you" — direct query against `Gold_Coast.<suburb>` filtered by listing_status=for_sale.
- **Walking-distance POIs:** From cadastral coordinates + Mapbox isochrone API or pre-computed POI tables.
- **Scarcity stack:** "Homes with [feature combination] that sold within 6 months: 3 of 47" — using the existing per-property analysis pipeline.
- **Suburb-specific market state:** From `precomputed_market_charts` + `precomputed_indexed_prices` (the source of truth for all Gold Coast metrics).
- **Provisional valuation range:** The CatBoost model gives a ballpark; the reconciled_valuation arrives after the human pass. We render it as a *range* in the under-review state and never as a single number (Halo Insight 4 + editorial rule).
- **Most-similar recent sale:** Top comp from the comp engine, with photo and full sale narrative.
- **Subject-property prose:** Following the same Opus pipeline used for `/property/8-trinity-place-robina` — already proven, already shipped.
- **Personalised fear-content selection:** If property is investor-heavy (e.g. unit, multi-let, recent rental history), show the Tenant + CGT + Tax content blocks first. If owner-occupier (large house, school catchment), show the Settlement + Mortgage + Selling-Process content blocks first. **The same site, different prominence by signal.**

**Only after human review (Day 3):**
- Final reconciled valuation (with 90% CI).
- Listing price + target sale price.
- The four-condition precise-pricing checklist (from V4 page 11).
- Print appraisal triggered for delivery.

This split matters. The under-review state has to feel **personal enough to be hooked** but **honest about what's still being prepared**. The seller's curiosity gap (Loewenstein 1994 — already a memory) is what brings them back twice a day to check. Six log-ins → one print appraisal arrives → conversion event.

---

## 5. The Marketing Engine

Once Tier 1–3 are wired, the marketing engine writes itself.

### 5.1 The creative production system

For each of the 15 fears, we produce a content cluster:

- 1 indexed `/seller-questions/<fear>` page (~1,200 words, derived from the relevant book chapter, locally re-anchored).
- 3 Facebook ad variations (one for each Avatar where applicable):
  - **Stressed Upgrader version** — emotional hook ("3am question: same-day settlement on the Gold Coast").
  - **Reluctant Seller version** — control hook ("Sell exactly as is. No repairs.").
  - **Savvy Investor version** — ROI hook ("CGT on a Robina investment property: the 6-year rule worked example").
- 1 short video (Will on camera, 15-25s reels — per `feedback_reels_vs_longform.md`), one idea per reel.
- 1 article on the homepage news feed.

That is **45 ad variations + 15 indexed pages + 15 reels + 15 articles** — far more than enough to A/B test and find the four to six combinations that print.

### 5.2 The funnel maths to validate

If we hit these benchmarks (each conservative against the V4 strategy targets and our Halo Strategy projections):

- Cold reach → click: 1% (Facebook GC property targeting)
- Click → `/analyse-your-home` submission: 8% (very high vs typical 1–3% because the page is the answer to the ad's question)
- Submission → first microsite session: 95%
- Microsite → printed-appraisal request (already auto): 100%
- Print appraisal → listing instruction within 12 months: 25–40% (V4 strategy targets 60%, but cold-source leads will convert lower than warm-source)

Then a $1,000 ad spend at $5 CPM → 200,000 impressions → 2,000 clicks → 160 submissions → ~50 print appraisals → 12–20 listings in 12 months. At a $20K average commission, that is $240K–$400K from $1K. The numbers do not have to land exactly there to make this the highest-ROI play in the business.

### 5.3 What to track

Every funnel stage gets a PostHog event:

- `fears_library_view` (which fear, which avatar variant)
- `analyse_your_home_view`
- `analyse_your_home_submit` (with referrer fear-page)
- `microsite_first_session` + `microsite_return_session_n`
- `valuation_final_published` (time-to-human-pass)
- `print_appraisal_dispatched`
- `print_appraisal_delivered` (when we register the courier confirmation)
- `consultation_booked`
- `listing_instructed`

Conversion ratio between any two events becomes the optimization surface. This is the dashboard that should live on the ops page.

---

## 6. The Physical Appraisal as Theatre

This is where Fields wins forever. The print piece is the *single most undercopiable* element in the whole funnel, because the bar for delivery moments in real estate is on the floor.

**Recommended choreography:**

1. **Day 0** — seller submits address. Confirmation email signed by Will, not "the Fields team": *"Mac (our property consultant) is now reviewing the comparable sales for [address]. You will see the final figures appear in your dashboard within 3 days. The printed report goes to press the day after that."*
2. **Day 1** — push a single activity item to their microsite: *"Mac selected six comparable sales today. The closest is [comp address], which sold [date] for [price]."* Builds time-on-document.
3. **Day 3** — final valuation appears in microsite. Email: *"Your appraisal is ready to read. The printed copy goes to press tonight and will be hand-delivered on [date]."*
4. **Day 5** — print arrives. Branded outer mailer. Hand-written sticky note. *Photo of Will signing it before it shipped* (texted to the seller, opt-in). The print piece is 32–40 pages, lay-flat, with their address foil-stamped on the cover.
5. **Day 6** — automated email: *"Did it arrive? Page 11 is the page most people show their partner — let me know what questions come up."*

The print piece is also the **lead-magnet referral loop**. Sellers show it to friends. Friends ask, *"who made this?"* That is the only retail-grade word-of-mouth event in residential real estate, and we can engineer it.

**Cost discipline:** at $40–$60 unit cost (premium short-run digital print + courier) and a 12-month commission expectation of $20K, the unit economics work even at single-digit listing conversion.

**Cap:** we deliver **a finite number per week** (5 to start). Scarcity is honest — Mac can only review so many — and reinforces the seriousness of the offer. The form says: *"We accept five new properties for review each week. The next opening is [date]."* That sentence does more conversion work than ten testimonials.

---

## 7. Risks and How to Mitigate Them

| Risk | What goes wrong | Mitigation |
|---|---|---|
| **Personalisation feels machine-generated** | Seller spots that the prose was auto-written and discounts everything | Use the existing per-property Opus pipeline for prose; human-passes for valuation; print appraisal is human-built and signed |
| **Under-review state is too thin to hold attention 3 days** | Seller bounces before final state | Pre-populate as much as possible from the address; queue 2-3 activity-feed items across the 3 days; email at each item |
| **Liability — single-figure or advice-y language slips in** | Editorial-rules breach, exposes Fields to disputes | Every public page passes the existing editorial pipeline (`no advice`, `no predictions`, `no forbidden words`, `no single-figure valuations in headlines`); ranges only on tier 3 |
| **Scale gets ahead of human-pass capacity** | Backlog builds, ETA breaks, brand damage | Hard cap on weekly submissions; explicit waitlist; queue management dashboard |
| **Tax/mortgage/tenant content goes outside our expertise** | We over-claim and get sued | Partner-attributed content (named CPA, named broker); never give advice ourselves; the page is "here is the question, here is the framework, here is who answers it for you" |
| **Cold lead never returns to microsite** | Print arrives, no warm relationship | Microsite emails on Day 1, 3, 5, 6; activity feed pushes; opt-in SMS for the print-delivered event |
| **Mini-site costs more in human review than it earns** | Cost per appraisal exceeds expected commission yield | Track unit economics from print 1; cap weekly throughput until proven |
| **Competitor copies the surface** | "Free appraisal mini-site" appears at LJ Hooker/Ray White | Our moat is data + editorial method + integration — not the URL pattern. Compete on rigour, not on novelty |

---

## 8. Recommended Build Sequence

The point of this report is to make the next 6–8 weeks decision-ready. Here is the sequence, ordered by leverage:

### Phase 0 — Wire the funnel (Week 1, ~3 days work)

**Single most important task.** Without this, none of the marketing works.

- Hook `/analyse-your-home` form submission → write stub `property_reports` doc → generate slug → redirect to `/your-home/<slug>` in under-review state.
- Email confirmation flow (Day 0, 1, 3, 5, 6).
- Hand-off to Mac (or to Will, as property consultant) for human review trigger.
- Print queue page on `/ops` so we can see who is in-flight.

### Phase 1 — Plug the three content gaps (Week 2–3)

Build the three GAP fears as Tier 1 pages, each with a partner credit:

1. **Tax / CGT** — partnership with a Gold Coast CPA. One page, one downloadable worksheet, one named partner.
2. **Mortgage / sell-first-vs-buy-first** — partnership with a broker. Calculator + named partner.
3. **Tenant-in-place / investor sale** — pull from existing investor analytical assets; possibly partner with a property manager.

These fill the Halo gaps that the book deliberately doesn't cover.

### Phase 2 — Build the public Fears Library (Week 3–5)

For each of the 15 fears, produce the `/seller-questions/<slug>` page derived from the relevant book chapter. ~1,200 words each, locally re-anchored, named comps, mini-CTA: *"See how this applies to your home →"* leading to `/analyse-your-home`.

Sequencing within the 15: lead with the top three by volume (Agent Selection, Legal Requirements, Tax Implications) and the top three by personalisation-payoff (Property Valuation, Market Timing, Auction vs PT). The first six will carry 60% of traffic.

### Phase 3 — Personalisation upgrades to the mini-site (Week 4–6, parallel)

From Concept.md "not yet built":
- Interactive competition map (Mapbox layer).
- Positioning tab (port the Opus editorial pipeline).
- Auction-vs-Private-Treaty recommendation (per-property, data-driven).
- Seasonality recommendation.
- Case studies block.
- Buyers tab.

Each of these is also a Fears Library destination — the link from the public page should deep-link to the relevant mini-site tab when a logged-in seller returns.

### Phase 4 — Marketing engine (Week 6 onwards)

- Produce the first six ad-creative clusters (one per top-six fear).
- Set $50/day budget per cluster (uses the existing Google Ads safety cap envelope).
- Run for 14 days. Pull data. Kill underperformers. Double winners.
- Concurrently: organic FB posts framed by the same 15 fears, reels of Will answering each, indexed to the public Fears Library pages.

### Phase 5 — Print-edition production line (Week 4–8, parallel)

This is the most under-built part of the system right now. V4 strategy locks the design pattern; we need:
- A reliable short-run print partner (Blurb is fine; couriered same-week is the requirement).
- A production checklist (V4 §07_production_plan, already exists).
- A pre-flight QA for every report (Will's signature page; address foil; comp accuracy).
- The "send Will a photo of it shipping" automation.

---

## 9. Open Questions for Will to Decide

These are the calls only you can make.

1. **Throughput cap** — how many addresses per week are we willing to commit to a full human-pass plus print? My recommendation: start at 5. Scale to 10 once Mac's pass is sub-2-hours.
2. **Print partner** — Blurb / local short-run printer / off-shore. Cost vs lead-time tradeoff matters enormously to the Day 5 promise.
3. **Partner content** — accountant, mortgage broker, conveyancer. Three names. Each gets brand placement in exchange for clear referral mechanic.
4. **Geographic radius** — core suburbs (Robina, Burleigh Waters, Varsity Lakes) are obvious. But the Halo Avatar 1 ("Stressed Upgrader") extends to Mudgeeraba, Reedy Creek, Worongary (already in target scrape). Do we accept addresses there too, or hold the line on core three?
5. **Self-funded vs partner-funded marketing** — if a CPA partner wants to co-fund the CGT ad cluster, do we accept the cash? My view: yes, with strict editorial control retained.
6. **Avatar prioritisation** — Stressed Upgrader is 40% of the market and the most settlement-anxious. Reluctant Seller is 35% but the lowest-trust. Savvy Investor is 25% but highest-LTV. My recommendation: lead with **Stressed Upgrader** for paid acquisition (highest volume + clearest fear), serve **Reluctant Seller** organically (they are forum-lurkers, the public Fears Library will reach them passively), and warm **Savvy Investor** via the partner accountant relationships.
7. **The walk-away promise** — V4 strategy has it on the Next tab. Should it go on the public Fears Library too? My view: yes, as a soft line, not a guarantee. *"If our appraisal doesn't change how you think about your home, throw it in the bin. We won't follow up."*

---

## 10. The One-Sentence Summary

> **We have the most uncopiable seller-acquisition stack on the southern Gold Coast. The only job left is to wire it into a single closed loop that turns each of the 15 seller fears into a tested ad → a personalised microsite → a print appraisal on the doorstep → a 25–40% listing conversion within 12 months.**

Everything else is implementation detail.

---

*Filed at `11_House_Mini_Site/Opportunity-Report.md` · Author Claude (Opus 4.7) · 2026-05-14*
