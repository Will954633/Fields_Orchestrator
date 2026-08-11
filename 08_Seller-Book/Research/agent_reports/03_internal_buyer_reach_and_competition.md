I have a comprehensive picture. Here are the findings.

## Headline: the strongest evidence for your ad line is already written up — and it comes with an explicit internal block

`/home/fields/Fields_Orchestrator/08_Seller-Book/SYNOPSIS_listing_price_is_attraction_tool.md` (387 lines) is a full workup of almost exactly your sentence. Its verdict, verbatim:

> "**The statement is the book's own thesis, almost word for word — and it is half right. The half that is wrong is the expensive half.**"

And §10, caveat 1: *"Disclose the anchoring/ceiling qualification or the statement invites failure mode 2. **And resolve the three-way contradiction in §5 first** — the book, the playbook and the appraisal template currently disagree on where to set the price."*

The memory file `/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory/list_price_three_way_contradiction.md` (modified 2026-08-11, i.e. today) states: *"**resolve before any of this goes into customer-facing copy.**"* Facebook ad copy is customer-facing copy. Flagging that up front — the rest of this report is what's available, with quotability grades.

---

## 1. Buyer reach as a function of price

**Solid enough for an ad:**

- **72% of buyers skip a listing without a displayed price.** REA Property Seeker, **n > 6,000**, representative of the Australian population (not just REA users). REA calls it *"the number one source of dissatisfaction on our platform."* Files: `15_On_Market/01_Research/08_search_demand_and_buyer_journey.md` §2.1; `15_On_Market/02_Synthesis/MASTER_FINDINGS.md:44`. This is the single best-sourced "price controls who sees your home" number Fields holds.
- **Price is 76% used / 61% "most important"** to buyers — vs address 25%, features 22%, suburb 21%, photos 13%, floorplans 12%. Source: REA Property Seeker 2025, **n = 2,051 buyers**. File: `15_On_Market/02_Synthesis/EVIDENCE_UPDATE_2026-08-10.md`.
- **79% of live listings in Robina/Varsity Lakes/Burleigh Waters do not state an estimate of value.** Measured on Fields' own inventory 2026-08-10, **n = 205**: single price 40 (19.5%), genuine range 3 (1.5%), "Offers Over $X" 87 (42.4%), no number 75 (36.6%). File: `15_On_Market/04_Evidence/own_inventory_price_opacity_2026-08-10.md`. This is Fields' own original measurement and it is clean.

**The bracket argument — real, but qualitative, NOT measured:**

Book Ch 4, *Price Brackets and Portal Visibility* (`output/seller_book_draft_v4.md`), quoted in the synopsis:

> "A home listed at $1,510,000 is invisible to that buyer. A home listed at $1,495,000 appears in their search."
> "The difference between visibility and invisibility is $15,000 in listing price — which may or may not be $15,000 in achievable sale price."

Brackets named: $1,000,000–$1,250,000, $1,250,000–$1,500,000, $1,500,000–$2,000,000.

**NOT FOUND: any count of how many buyers sit in each bracket.** No portal search-filter volume data, no bracket population estimates, no enquiry-by-bracket data anywhere in the repo. The bracket argument is a plumbing/mechanism argument, not a measured one. Do not put a buyer count on it.

**Related, and quotable with care:** the competitive-set framing from Ch 2 p.26 (`12_Marketing/Market_Economics/Absorption_Rate/README.md`): *"55 Robina listings sounds crowded, but if only six are four-bedroom houses $1.3M–$1.5M, the competitive set is six, not fifty-five."* Absorption April 2026: Robina 55 active / ~30 sales per month = ~1.8 months; Varsity Lakes 32/~25 = ~1.3; Burleigh Waters 37/~23 = ~1.6.

---

## 2. Multiple offers / competition → price

**This is the weakest area. Fields holds no internal data at all here.**

- **NOT FOUND: any Fields dataset of offers received per listing.** I checked `SCHEMA_PATHS.tsv` — the only offer-related fields are `system_monitor.onthehouse_listings.under_offer` (a boolean, 172/172) and `positioning_analysis.gated.negotiation_positioning.counter_offer_approach` / `first_offer_advice` (**4/300 coverage**, and they are generated advice text, not observations). There is no offer count, no offer amount, no number-of-bidders field.
- **NOT FOUND: open-home group counts vs offers.** Per `memory/minisite_buyer_reach_honesty.md`, verbatim: **"Fields has NO buyer-origin dataset and has held NO open homes."** A live report previously cited an "open-home register"; it was found fabricated and removed.
- **NOT FOUND: any Fields measurement of homes selling above asking price.**

**What the evidence actively says against this angle** — from the do-not-claim register, `08_Seller-Book/SYNOPSIS_higher_price_evidence.md` §8.6, item 9:

> "**Do not claim underpricing creates bidding wars in private treaty.**"

Backing it: Bucchianeri & Minson (2013), *JEBO* 89, 76–92, 14,000+ transactions — *"there are seldom enough buyers to create a 'herding effect'"*. And Han & Strange (2014), *Real Estate Economics* 42(1):1–32 (`12_Marketing/Pricing_Strategy/Underpricing_Strategy/README.md`): the price-to-list ratio shifts above 1.0 **only when the listing is *visibly* contested — and in private treaty, buyers rarely see competing offers.** Southern Gold Coast is ~95% private treaty (auction measured at **4.9%** of the n=205 own-inventory sample).

**Above-asking external numbers exist but measure something different** (underquoting, not competition):
- Guardian (2024): final sale exceeded the agent's price guide in **92%** of sales, but exceeded the automated estimate in only **44%**.
- Homer, 6 months to ~May 2026, Sydney: median sale **$117,500 above the top of the advertised range**; 49.8% above guide, 39.7% below, 10.5% at guide.
- CPRC Victoria, **n = 500 buyers**: **34%** of properties purchased sold above the top of the indicative price.

The synopsis's own reading of the Guardian figure: *"not because the model is precise, but because **the guide is a marketing instrument and the model isn't**."* That is a strong line for your thesis — but note it is evidence that guides are set low, which cuts against "the price signals the value we believe it holds."

**Fields' strongest artefact for your exact sentence** is the shipped appraisal template, `scripts/appraisal_template/render.py:1548–1570`, live copy:

> "The listing price sits in the **lower end** of the derived $X – $Y range. The target sits in the **upper end**. The **$A – $B gap** between them is **intentional** — it is the stretch room buyers reach through competitive bidding, not the price the seller hopes to defend through negotiation. *Multiple interested buyers move from the listing price toward the target. A single buyer moves the other way.*"

The synopsis calls this *"the strongest internal artefact supporting the statement"* — and in the same breath notes it **directly contradicts** Positioning Playbook v5.0 Step 2, which sets the list price at true value **+2–4%**.

---

## 3. The buyer pool itself

**Solid, and the best number in this whole report:**

- **4.2m properties tracked by their owner on realestate.com.au, +29% YoY ≈ 39% of every dwelling in Australia; ~45% of all REA seller leads come from owner experiences.** Source: REA Group Investor and Analyst Presentation H1 FY25, pp. 8, 12 (Tier A, ASX investor deck), against ABS 2021's 10,852,208 private dwellings. File: `15_On_Market/01_Research/08_search_demand_and_buyer_journey.md` §1.3. Corroborated: ~**40% of REA listings were owner-tracked before being listed.**
- **REA H1 FY25 scale:** 11.9m monthly uniques, 130.7m monthly visits, **2.2m average monthly buyer enquiries**, ~11 visits per unique per month. Derived enquiry rate ≈1.7% of visits — but the file warns *"Both denominators are wrong for different reasons; use the ratio as an order of magnitude only."*
- **PropTrack Buyer Impact Model**, **1.3m+ Australian sales Aug 2023 – Nov 2025**, 25 behavioural signals, methodology independently validated by Deloitte: the eventual buyer spends **~7 cumulative hours on the one listing they buy**, views **28× more images than non-buyers**, and buyer engagement is recorded on **9 in 10** properties that sell. Files: `15_On_Market/01_Research/01_buyer_information_needs_evidence.md:182`, `08_search_demand_and_buyer_journey.md` §2.3. Caveat stated at source: excludes unsold listings, is REA's own commercial evidence.
- Australians are in-market **~40 weeks** (up from 23 in two years) and **100% of the growth is pre-inspection research**.

**DO NOT USE — Fields' own buyer numbers are explicitly banned:**

`15_On_Market/02_Synthesis/THE_ATTRACTANT_SET.md:126-130`, verbatim:

> "⚠ **Honest constraint.** The obvious implementation — 'N buyers viewed this' from our own audience — **is not available to us.** Our property pages draw **288 views by 202 people per 90 days**. Any buyer-count we published would be embarrassing and would undercut the pitch."

**DO NOT USE — the appraisal buyer-pool numbers are modelled, not measured.** `09_Appraisals/Version_Two/spreads/` contains attractive-looking figures: *"an addressable buyer pool of ~340 qualified searchers"* (`S03_data_pull.md:4`), *"~380 qualified buyers"* / *"~440"* (`S10_optimal_timing.md:70`), *"Most premium $1.95M listings receive 30-60 buyer enquiries over a 4-week campaign"* with a 35/30/20/15 persona split (`S03_data_pull.md:149`, `S03_buyer_personas.md`). Three reasons to leave them alone:
1. The caption itself says *"Shares are **modelled estimates**"*, and the working file labels the headline *"(provisional)"*.
2. The cited authorities — "REA Insights 2024 *Premium Listing Enquiry Mix Report*", "REA Insights 2024 *Agent Operations Benchmark Report* (survey of 240+ agents in coastal QLD)", "REA Insights *Premium Listing Spend Benchmarks 2024*" — appear **nowhere else in the repo and nowhere in the research corpus**. I could not verify that any of these reports exist.
3. The raw model in `S03_data_pull.md:143` actually output **13%/15%/70%**, materially different from the published 35/30/20/15, which was then re-anchored on those unverified benchmarks.

**Active vs passive split — NOT measured locally.** `12_Marketing/Buyer_Psychology/Active_vs_Passive_Buyers/README.md`, Open Questions: *"**We don't yet have a measured local active/passive ratio.**"* The circulating splits are: 5/95 (Ehrenberg-Bass / LinkedIn B2B, transferred), 70/30 ("a softer variant"), and the book's 60–70% active / 30–40% passive strong market flipping to 40–50%/50–60% soft — the last sourced in `SYNOPSIS_higher_price_evidence.md` §B3 only as *"Research consistently shows"*. And `memory/minisite_buyer_reach_honesty.md` records that a previously shipped **"28%/72% active/passive precision"** was **invented** and removed. Do not put an active/passive number in an ad.

---

## 4. Days-on-market vs price accuracy — well-sourced only

**Internal DOM is unusable, and this is formally recorded.** `SYNOPSIS_higher_price_evidence.md` §8.4: `time_on_market_days` coverage is **17 / 2,153 = 0.8%**; `first_listed_date` 14/2,153 = 0.7%; the DOM model's cross-validated **R² = 0.006**. Do-not-claim register item 11: *"Do not treat any days-on-market claim from the 2,153 corpus as robust."* This invalidates the 33-vs-20.5-days manufactured-urgency finding, the "3× longer" Burleigh Waters renovation claim, the "25% faster" paint claim, and the "10 days faster" Premiere Plus figure. Verified independently at `output/positioning_research/phase_0_summary.md:54,59`.

**External, well-sourced, and usable directionally:**
- **Taylor (1999)**, *Review of Economic Studies* 66(3), 555–578 — >10% overpricing is **2–5× slower**.
- **Anglin, Rutherford & Springer (2003)**, *JREFE* 26(1), 95–111 — each **10% above market value adds ~20–30% to time on market**.
- **Khezr (2015)**, *Applied Economics* 47(29), 3049–3060, **25,000+ Sydney sales** — overpriced homes take longer and sell for less. (Australian, large sample — the best one for an AU audience.)
- **Knight (2002)** — **38.4% of listed properties undergo price changes**; repricers achieve lower final prices than day-one-correct sellers. ⚠ Citation disputed between two journals.
- **Zillow Research** — 12%+ over → ~**50% less likely to sell within 60 days**.
- **CoreLogic Australia** — listed 10–15% above eventual sale price → **2–3× longer** on market.

**Fields' own price-change data is clean and reproducible** (this is your best internal DOM-adjacent proof): `system_monitor.price_change_events`, writer `scripts/track_price_changes.py`, **786 events / 322 distinct properties, 2026-03-21 → 2026-08-06**, verified against production:
- **130 price-reduction events across 98 distinct properties** (Robina 61, Burleigh Waters 38, Varsity Lakes 31). **Median reduction 3.29%.**
- **n = 54** properties with both a parsed first ask and a sale price: **median first-ask → sale gap −2.5%; worst −12.8%.**
- **n = 142** sold homes with first ask + sale price: **48% sold below their first ask; 25% finished more than 5% away** (>$70,000 on a $1.4M home). ⚠ No committed reproduction script for the n=142 figure.
- **58 of 77 = 75%** of live listings *with ≥2 recorded price points* cut their price; median **4.3%**, mean 4.8%, max 17.6%.

⚠ **Denominator discipline, stated twice in the source:** do **not** say "30% of listings cut their price" (the tracker only writes an event on change), and do **not** say "75% of listings change price" (it is 58/77 listings with ≥2 price points).

⚠ **Do not reuse** the "$1,700,000 in Robina: How 16 Collingwood Avenue Beat the Suburb Median by 11.8%" case study — it is logged as an accuracy incident (first asked $1,949,000, cut to $1,749,000, sold $1,700,000 after 127 days, and the reduced price was called "the guide").

The "sold homes that cut their price ran a median **68 days vs 37**" figure appears **once**, parenthetically, in `SYNOPSIS_higher_price_evidence.md:474`, with no sample size and no source file. Not quotable.

---

## 5. The "concentrate buyers into a narrow window" thesis

**Fields states it clearly, but has measured none of it.**

The canonical statement, Ch 7 of *Before You List*, appearing in at least six files (`output/seller_book_draft_v4.md:1014`, `12_Marketing/Marketing_The_Listing/00_book_extract.md:64`, `12_Marketing/01_Videos/Fields Mini-Site Video Scripts - V3.md:528`, both synopses):

> "The goal of marketing is not exposure for its own sake. **The goal is to concentrate as many qualified buyers as possible into the same narrow window of time.** When ten serious buyers inspect a property in the same week, each one knows the others exist… When those same ten buyers are spread across six weeks, they never compete."

Paired with Ch 4: *"When multiple buyers want the same property, they stop negotiating against the seller and start negotiating against each other."*

**These are assertions with no supporting measurement.** The "ten buyers" is illustrative. Every quantified version I found is weakly sourced:

- **"Brisbane 6-year study (144 properties): 49% sold in week one, average premium $69K"** — appears in five playbook versions (`FIELDS_POSITIONING_PLAYBOOK_v5_0_ACADEMIC_EVIDENCE_EDITION.md:675` and v3/v4/v5.0/`POSITIONING_PLAYBOOK_v2.md:549`). It sits under a **"Local Evidence"** bullet in the **staging** section, with **no citation, no author, no publication**. Not quotable.
- **Redfin view-decay curve** — *"A home viewed by 100 buyers online on Day 1 receives an average of just 17 views per day by Day 30. Day 2: half the views of Day 1. After 1 week: a quarter. Price drops temporarily boost views to 29/day — for a SINGLE DAY before falling back to 18/day."* This is the only view-decay curve in the repo. It exists **only** in an ad-generation working file, `03_Facebook/Home_Owner_Lead_Funnel_Search/cycles/cycle_20260728_1801.md:148`, with **no URL and no date**, and does not appear in any research corpus. US data. Not quotable without finding the primary source.
- **"Three-Week Sweet Spot" / 44,937 GC sales / week-3 sales achieve 4% higher prices** — the narrative is in `output/seller_book_draft_v3.md:350`; the 44,937 sample and 4% premium appear only in `logs/fix-history/2026-05-06.md:71` and two FB ad cycle files attributed to "Brain 3". It is a DOM-based finding, so it falls under the 0.8%-coverage problem. Not quotable.
- **"~70% inspection volume in first 14 days, 50% in first week"** — appears **once**, in `logs/fix-history/2026-05-06.md:71`, describing a callout card built for appraisal module M20. No source. Not quotable.
- **"Days 1–14: Peak engagement window. Maximum inquiry."** — `output/positioning_research/POSITIONING_PLAYBOOK_v2.md:49`, no citation.

**The one genuinely first-week-adjacent measured finding, and it is unhelpful to the ad:** the positioning corpus's own conclusion, `POSITIONING_PLAYBOOK_v2.md:39`:

> "**The honest answer: price drives speed, not quality.** Properties priced 10%+ below cohort median sell in 16 days (Robina) vs 28-29 days at market. Higher condition/presentation scores = **SLOWER** sales (r = +0.13)… **The only controllable speed lever is pricing.** Everything else is noise."

Directionally supports "price sets the response", but it comes from the same corpus with 0.8% DOM coverage, so treat as internal reasoning only.

**Module M20 "The First Seven Days"** is specified at `09_Appraisals/04_content_modules.md:279` — *"Asserts: 'Demand is concentrated in the first seven days. Here's how we pre-load it.'"* Its stated input is *"suburb-specific demand-concentration figures from `seller_book_draft_v4.md` Chapter 7"* — i.e. it sources from the book, which sources from nothing. Circular.

---

## 6. Asking price vs enquiry volume

- **REA Premiere Plus vs Standard: 2.6× email enquiries, 2.9× listing views, 2.1× search appearances, 10 days faster to sale.** File: `SYNOPSIS_higher_price_evidence.md` §B2, `12_Marketing/Marketing_The_Listing/README.md`. ⚠ Graded **Tier B — "Industry / platform data (real numbers, thin sourcing)"**, and the "10 days faster" is separately invalidated by §8.4. Also: this is about *listing tier*, not asking price.
- **"Never use 'Contact Agent' — 72% of buyers skip it, 20–30% less engagement."** Positioning Playbook v5.0 "What NOT To Do". The 72% is solid; the 20–30% engagement figure has no independent citation.
- **Domain, October 2025:** 9M unique audience (+21% YoY), 55M visits (+39%), **listing views +25% YoY, email enquiries to agents +31% YoY**. Tier A (Domain HY25 deck / CoStar release) — but not price-related.
- **Nikiforou, Dimopoulos & Sivitanides (2022)**, *J. European Real Estate Research*, **538 transactions, Cyprus** — optimal Degree of Overpricing **~1.5%**; **each 1% increase in DOP raises the probability of selling within 30 days by 1.23%.** This is the *only* study in the entire base that measures the listing price's attraction effect separately from its price effect. ⚠⚠ **BANNED FROM SHIPPING COPY.** Synopsis §2.4: *"Do not publish this figure. The paper is not held on file and is not in `references.ts`."* Do-not-publish item 5.

**NOT FOUND: any Fields listing data relating asking price to enquiry volume.** No REA or Domain per-listing performance exports are held locally. `12_Marketing/Marketing_The_Listing/references.md` links only the PropTrack **Off-Market** Sales Performance Report 2023 (off-market sells 3.6% below on-market in Brisbane), which is a different question.

---

## 7. Memory directory — the four files you named

**`property_page_visitor_behaviour.md`** (measured 2026-08-05, PostHog + GSC 90d). Directly on "how many buyers look at one address": **99% of Google impressions to `/property/` are bare-address queries** with no qualifier. **7,448 impressions / 141 clicks, CTR 1.9%, avg position 7.8.** Visitors start scrolling at a **median 2 seconds**, and **65% leave the site** — statistically identical to the 68% exit of people who never scrolled. Carries a hard warning: **do not headline "% reached bottom"** (page height is bimodal with zero overlap). Also: comparable-sales ranges exist on only **7% of sold (221/2,947)**, 44% of for-sale, 23% of under-contract.

**`offmarket_v4_reading_analytics.md`** — pure instrumentation (PostHog dashboard 1977712, event schema, sendBeacon gotchas). **No buyer-demand or search-behaviour figures.** Nothing usable for your ad.

**`contact_capture_reality_and_address_mail_strategy.md`** — contains a self-correction worth knowing: the widely-repeated *"1 email, 0 phone numbers"* claim is **false**. Measured: `analyse_leads` holds **11 records, 8 of them tests**; the **3 genuine submissions each supplied address + email + phone**; `/analyse-your-home` lifetime uniques = **298**. So 3 of 298 (1.0%) started the form, and 100% of starters gave a phone. Lifetime totals across every capture mechanism: `lead_signups` 2, `subscribers` 4, `five_property_friday_subscribers` 3, `launch_leads` 4, `analyse_leads` 11, `sms_claims` 12, `leads` 31. **Fields has no alert subscribers or watchlist base to cite.**

**`on_market_buyer_research_2026-08.md`** — the richest of the four; most of its content is reflected above. Additional: `/analyse-your-home` gets **75% of its traffic from Facebook/Instagram**; the entire website contributes 21 views / 15 people per quarter. Fields vs Domain on the same property (**n = 78**): median absolute disagreement **7.9%**, >5% on 72%, >10% on 42%, 90th pct 33.6% (≈$110k on a $1.4M home). And the governing constraint: *"**We CANNOT claim to be more accurate** — our band is also flat (±12%) and holds only 61% of the time. The differentiator is transparency, never accuracy."*

---

## Bottom line for the ad

**Put in the ad (solid):**
1. **72% of buyers skip a listing with no displayed price** (REA Property Seeker, n>6,000) — and REA calls pricing its platform's #1 source of dissatisfaction.
2. **Price is the #1 thing buyers use: 76% use it, 61% call it most important** — photos are 13% (REA Property Seeker 2025, n=2,051).
3. **79% of listings in Robina, Varsity Lakes and Burleigh Waters don't state an estimate of value** (Fields' own measurement, n=205, 2026-08-10) — 42.4% show only an "Offers Over" floor.
4. **48% of sold homes sold below their first asking price; 25% finished more than 5% away** (n=142) — the asking price is not the sale price.
5. **The eventual buyer spends ~7 cumulative hours on the one listing they buy and views 28× more images than non-buyers** (PropTrack, 1.3m sales, Deloitte-validated) — that's your "the right buyer has to see it" proof.
6. **39% of all Australian dwellings are owner-tracked on REA, +29% a year** (REA H1 FY25 investor deck) — proof the audience exists at scale.

**Keep out of the ad:**
- Any buyer count, buyer-origin split, or active/passive percentage — Fields has none, and the last one shipped (28%/72%) was fabricated and removed.
- Any number implying Fields' own audience size (288 views / 202 people per 90 days).
- The Nikiforou 1.23% figure (banned), Haurin/Merlo/Genesove magnitudes (glosses only), the Brisbane 144-property week-one study, the Redfin decay curve, the 44,937-sale three-week sweet spot, "70% of inspections in the first 14 days", 33-vs-20.5 days, and any DOM figure from the 2,153 corpus.
- Anything asserting multiple offers raise price in private treaty as a Fields finding — Fields holds no offer data, and its own register bans the adjacent claim.

**The reframe the evidence actually supports**, straight from `SYNOPSIS_listing_price_is_attraction_tool.md:29` — worth building the ad around instead:

> "The listing price is the primary tool for deciding **which buyers ever see your home**. It is not a prediction of the sale price, and it is not a negotiating cushion. But it also anchors the negotiation and, in private treaty, functions as a practical ceiling on offers — so it must be set close to true value, not high to leave room and not low to attract."

And the permitted asymmetry line, quoted verbatim in the synopsis as *"the most careful sentence anyone at Fields has written on this"*: **"the evidence is clearest about launching above what buyers can justify."** There is no measured penalty for underpricing in anything Fields holds — so the third clause of your sentence ("to get multiple people bidding for it") is the one with the least support behind it.
