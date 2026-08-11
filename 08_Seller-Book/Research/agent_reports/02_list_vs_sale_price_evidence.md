I have what I need. Here is the evidence, organised against your six questions.

---

# The claim: "The listing price is a buyer attraction tool — not your expected selling price"

## 0. There is a dedicated document on exactly this claim — and it says the claim is half wrong

**`/home/fields/Fields_Orchestrator/08_Seller-Book/SYNOPSIS_listing_price_is_attraction_tool.md`** (244 lines) is titled with your sentence verbatim. Its verdict, verbatim:

> "**The statement is the book's own thesis, almost word for word — and it is half right. The half that is wrong is the expensive half.**"
>
> "But if it is read as *'the listing price doesn't determine what you get'*, it is wrong, and wrong in a direction that costs money. In a private-treaty market — **92% of southern Gold Coast sales** — the listing price is also an **anchor** and behaves in practice as a **ceiling on offers**. The book says so itself, two pages after it makes the attraction argument."

Its proposed replacement wording, verbatim:

> "The listing price is the primary tool for deciding **which buyers ever see your home**. It is not a prediction of the sale price, and it is not a negotiating cushion. But it also anchors the negotiation and, in private treaty, functions as a practical ceiling on offers — so it must be set close to true value (the research says **~1.5% above**), not high to leave room and not low to attract."

It also records the book's self-contradiction (§3.1): Ch. 4 says *"The asking price is a marketing tool. The sale price is the outcome"* and, two pages later, *"When a buyer sees a property priced attractively, their instinct is not to offer more than the asking price. Their instinct is to offer the asking price, or slightly below… **The anchor works in the buyer's favour, not the seller's.**"* — "The book never reconciles this."

Its own §8 caveat list is the do-not-claim register for this specific sentence:
1. contradiction must be disclosed or it invites the underpricing failure mode;
2. the strongest Fields number (the +18% Robina gap) is **not currently reproducible**;
3. **all DOM figures here are weakly sourced** — native `time_on_market_days` coverage 0.8%, DOM model CV R² = 0.006;
4. editorial: data statement, not advice.

---

## 1. Empirical list-to-sale ratios in the Gold Coast data

### 1a. The best measurement (reproducible, run against production)
`/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning/AI_Collaboration_Experiement/runs/E4_unknown/claude_arm_final.md`, Finding 1, status **VERIFIED** ("I ran the queries and the join"):

- Source: `system_monitor.price_change_events`, writer `scripts/track_price_changes.py`, **786 events, 322 distinct properties, 2026-03-21 → 2026-08-06**.
- **130 `price_reduction` events across 98 distinct properties** (Robina 61, Burleigh Waters 38, Varsity Lakes 31). **Median reduction 3.29%.**
- 132 of the 322 tracked properties have flipped to `sold`; **54 have both a parsed first asking price and a sale price. Median first-ask→sale gap −2.5%; worst −12.8%.**
- Worked examples given: 16 Collingwood Ave, Robina $1,949,000 → $1,700,000 (−12.8%); 3/4 Ben Lexcen Pl, Robina $895,000 → $815,000 (−8.9%); 29 Lantau Cr, Varsity Lakes $1,249,000 → $1,150,000 (−7.9%).
- The existing `vendor_discount_pct` field is populated on only **46 of 1,566** sold properties in the three suburbs (**2.9%**).

⚠ **I verified the selection-bias caveat the file flags as its own falsifier, and it is real.** `scripts/track_price_changes.py` (lines ~181–233) inserts a `price_change_events` doc **only when `history[-1].price_text != current_price`**. So the 322 denominator is *properties that changed at least once*, not all tracked listings. **The derived statistic "98 of 322 tracked listings (30%) cut their asking price at least once" is not a valid base rate** and should not be quoted as one. The 54-pair median (−2.5%) is unaffected by that particular bias but is conditioned on the property having had ≥1 change during the window.

### 1b. The second measurement (used in the current synthesis)
`/home/fields/Fields_Orchestrator/15_On_Market/02_Synthesis/BUYER_TO_SELLER_BRIDGE.md` §1.4, marked `[I]` (internal):

> On live Fields listings **with two or more recorded price points**:
> | Listings that **reduced** their price | **58 of 77 = 75%** |
> | Listings that raised | 5 |
> | Median reduction | **4.3%** (mean 4.8%, max 17.6%) |
>
> "And on sold homes where we hold both a first asking price and a sale price (**n=142**): **48% sold below their first ask**, and **25% finished more than 5% away from it** — on a $1.4M home, more than $70,000."

⚠ **Denominator drift to watch.** The document conditions the 75% correctly ("with two or more recorded price points"), but the memory file `on_market_buyer_research_2026-08.md` restates it twice — once correctly ("75% of trackable live listings"), and once as **"it genuinely fires because 75% of listings change price"**, which is false. Use the conditioned form.

⚠ The n=142 figure has **no committed script** in `15_On_Market/`; I found no reproduction path.

### 1c. The +18% Robina asking-vs-valuation gap — audited as NOT reproducible
`/home/fields/Fields_Orchestrator/08_Seller-Book/Market_Data/DATA_SOURCES_NOTE.md`:

| Metric | Value |
|---|---|
| Median Domain Valuation | $1,320,000 |
| Median Asking Price | $1,552,000 |
| **Overpricing Gap** | **+18%** |

DOM: well-priced (<valuation) **23 days**; overpriced (>15% above) **100+ days**; extreme **150+ days**.

Stated caveats in that file: Domain valuations used as a *proxy* for fair market value; DOM contaminated by relistings; 2025 incomplete. **The reproduce command points at `/Users/projects/Documents/Fields_HypeBeast/…` — a macOS path that does not exist on this VM.** The synopsis flags this explicitly: *"it is **not currently reproducible**; re-run it before publishing."*

### 1d. Sale-vs-Domain-valuation distribution (this is NOT list-to-sale — read the definition)
`/home/fields/Fields_Orchestrator/output/positioning_research/phase_2/study_2_8_pricing.json`, `domain_valuation_comparison` = `(sale_price / domain_valuation_mid − 1) × 100`:

| Suburb | n | median | mean | p25 / p75 | sold above | sold below |
|---|---|---|---|---|---|---|
| Robina | 168 | **−6.9%** | −4.9 | −9.1 / −2.6 | 17.3% | **81.5%** |
| Varsity Lakes | 178 | **−11.8%** | −11.5 | −18.7 / −6.2 | 7.9% | **91.0%** |
| Burleigh Waters | 187 | **−5.0%** | −3.9 | −7.6 / −3.9 | 10.2% | **89.8%** |

⚠ This is sale price vs an AVM, not vs list price. It also sits under the audit finding in `SYNOPSIS_higher_price_evidence.md` §8.3: `domain_valuation_at_listing` is **misnamed** — 703/766 (91.8%) were captured on or after the sale date, median +266 days, and Domain ingests sold prices, so it was scored with hindsight. The clean subset is **n=21**. Verdict recorded verbatim: *"**We have no valid Fields-vs-Domain comparison in either direction.**"*

### 1e. The Playbook's "Price Positioning by Suburb" table does not mean what it appears to mean
The playbook table (Robina 16d below-market / 28d at / 29d above; VL 24/20/24; BW 30/30/37) comes from the same JSON. I read the generator, `/home/fields/Fields_Orchestrator/scripts/positioning_research/phase_2_bivariate.py:677–706`: `position = (price / median_price_for_that_bedroom_count − 1) × 100`. **It is price relative to the bedroom-cohort median price — i.e. how expensive the home is, not how it was priced against its own value.** And every correlation is null: Robina Spearman r=0.094 p=0.3076 n=119; Varsity Lakes r=−0.066 p=0.4463 n=134; Burleigh Waters r=0.06 p=0.4853 n=137. Do not cite this table as evidence about pricing strategy.

---

## 2. The pricing framework in Positioning Playbook v5.0

File: `/home/fields/Fields_Orchestrator/12_Marketing/02_Drive_Research/FIELDS_POSITIONING_PLAYBOOK_v5_0_ACADEMIC_EVIDENCE_EDITION.md`, Part 3, lines 111–290. (`FIELDS_POSITIONING_PLAYBOOK_v5.0.md` is byte-identical, 44,370 bytes.) Header: *"Based on 2,153 sold properties + 14 academic papers + 9 external research streams"*, dated 2026-04-04.

**The role it assigns the list price is ANCHOR, not attraction.** Verbatim:

- **Finding 1 — "List at 1-5% Above True Market Value (HIGH CONFIDENCE)."** Synthesis verbatim: *"The sweet spot is narrow. List at 1-5% above true value to create negotiation room and **anchor upward**. Beyond 5%, the TOM penalty starts to outweigh the anchoring benefit. Beyond 10%, it becomes actively destructive."*
- **Finding 3** verbatim: *"In residential real estate (unlike auctions), there are seldom enough buyers to create a 'herding effect.' **The anchoring hypothesis dominates. Higher starting prices produce higher final sale prices in private treaty.**"*

**THE FIELDS PRICING FRAMEWORK, verbatim, 5 steps:**
1. **Step 1 — Establish True Market Value.** "Use our reconciled valuation (comparable-sales weighted average)… our data shows Domain overestimates by 5-12% in our suburbs."
2. **Step 2 — Set the List Price at True Value + 2-4%.** Normal market +2-4% ("This is the negotiation buffer"); hot market (suburb DOM <20d) "at value or even −2%"; cold market (DOM >45d) "at value or −2%. Speed matters more than anchoring in weak markets."
3. **Step 3 — Bracket Optimisation.** "Position the price at the TOP of a portal search bracket, never the bottom of the next one." Worked: valuation $1.28M, +3% = $1.318M → price **$1,295,000**, not $1,315,000. *(This step is the only pure attraction argument in the framework.)*
4. **Step 4 — Make It Precise.** "$1,295,000 not $1,300,000. Cardella & Seiler (2016) proves precise prices anchor tighter and yield higher final sale prices."
5. **Step 5 — Express as a Range.** "Display as a range: $1,245,000 - $1,295,000. The low end sits within the bracket below (captures those buyers too). The high end is precise and slightly below the bracket boundary."

Suburb adjustments: Robina **+1-3%** (homogeneous, punished harder); Varsity Lakes **+2-4%**; Burleigh Waters **+3-5%** ("Levitt & Syverson effect strongest here — agents advise $2.0M when the seller could get $2.1M").

**"What NOT To Do" (verbatim, 5 items):** never overprice >10%; **"Never use 'Contact Agent' — 72% of buyers skip it, 20-30% less engagement"**; never underprice to create urgency; **"Never do incremental small reductions — one decisive 5%+ cut at 4 weeks, or withdraw and relist"**; never use round numbers ("$1,400,000 invites bigger discounts than $1,415,000").

⚠ **The playbook is in direct tension with your claim and with Fields' own appraisal product.** The playbook says list *above* true value (+2-4%) as a negotiation buffer. The shipped appraisal template (`/home/fields/Fields_Orchestrator/scripts/appraisal_template/render.py:1548–1570`) does the opposite: **"Recommended listing price" is set at the LOWER end of the derived range; "Target sale price" is the UPPER end.** Verbatim from the template copy:

> "The listing price sits in the lower end of the derived $X – $Y range. The target sits in the upper end. The **$A – $B gap** between them is **intentional** — it is the stretch room buyers reach through competitive bidding, not the price the seller hopes to defend through negotiation. *Multiple interested buyers move from the listing price toward the target. A single buyer moves the other way.*"

That template copy is the single strongest internal artefact supporting your claim — it is an explicit statement that list ≠ expected sale — but it contradicts Playbook v5.0 Step 2. Nobody has reconciled the two.

---

## 3. Academic findings on the list price as ANCHOR / CEILING

All verbatim as the files state them.

| Study | What the Fields files say | Where |
|---|---|---|
| **Haurin, Haurin, Nadauld & Sanders (2010)**, *Real Estate Econ* 38(4):659–685 | Listed in the playbook's 14-paper set as **"list price as upper bound on offers."** The synopsis: *"In a private-treaty market this is the single most important qualification to the statement: whatever else the listing price is doing, **it is capping the outcome**."* | Playbook src #10; `SYNOPSIS_listing_price_is_attraction_tool.md` §3.2, ref 9 |
| ⚠ **Caveat** | The one-line gloss is **all Fields holds**. No effect size, sample or quote anywhere. The PDF is on disk at `12_Marketing/01_Research_Articles/Haurin_et_al_2010_List_Prices_Sale_Prices_Marketing_Time.pdf` but has not been read into any note. **Do not quote a number from Haurin 2010.** | — |
| **Northcraft & Neale (1987)**, *OBHDP* 39(1):84–97 | *"Manipulated listing-price anchors influenced both students and experienced real-estate agents inspecting identical properties. Crucially, **agents claimed not to use the listed price — but their appraisals tracked the manipulation**."* Elsewhere: "19% acknowledgement" (agents admitting they used it). | `12_Marketing/Pricing_Strategy/Anchoring_Effect/README.md`; `logs/fix-history/2026-05-06.md:160` |
| **Merlo, Ortalo-Magné & Rust (2015)** | Only ever a gloss: **"Dynamic pricing strategy; list price stickiness"** / *"sellers do not adjust freely."* | Playbook src #7; synopsis §3.5, ref 14 |
| ⚠ **Caveat** | **No PDF, no sample, no effect size, no journal** anywhere in the repo. `Market_Data/ACADEMIC_REFERENCES.md` instead lists **Merlo & Ortalo-Magné (2004), "Bargaining Over Residential Real Estate: Evidence from England", *J. Urban Econ* 56(2):192–216** — a different paper. **Not quotable beyond the gloss.** | — |
| **Knight (2002)**, *Real Estate Econ* 30(2):213–237 | *"**38.4% of listed properties undergo price changes.** Homes with large percentage changes in list price take longer AND sell at lower prices. Getting the initial price right matters more than any subsequent adjustment."* And verbatim: *"Sellers who initially overprice their homes and subsequently reduce their asking prices receive lower selling prices than sellers who price their homes correctly from the start."* | Playbook Finding 2; synopsis §3.5 |
| ⚠ | The book's own reference list gives the citation as *JREFE* 24(1-2):93–119; the research file gives *Real Estate Economics* 30(2):213–237. Two different citations in circulation. | `SYNOPSIS_higher_price_evidence.md` §2 vs `Pricing_Strategy/README.md` |
| **Genesove & Mayer (2001)**, *QJE* 116(4):1233–1260 | *"Sellers facing nominal losses set **higher asking prices** and achieve **lower sale probabilities**."* Loss aversion magnitudes recorded elsewhere as **25–35% / 3–18%**. | synopsis §3.6; `logs/fix-history/2026-05-06.md:160` |
| ⚠ **Hard restriction** | `Session_03…md`: *"**Genesove & Mayer carries no magnitude here** … no percentage, no market, no period — **the hosted PDF has not been read for this draft**, and the registry entry carries the finding without the numbers." (Open item 10.) The 25–35%/3–18% figures are a single 2026-05-06 log line and are not corroborated in any research file. | `11_House_Mini_Site/Version_Two/Session_03…md:593`, `:818`, `:1199` |
| **Bucchianeri & Minson (2013)**, *JEBO* 89:76–92, 14,000+ transactions | Verbatim: *"Higher listing prices DO anchor higher sale prices, but the effect is tiny: **overpricing by 10-20% yields only 0.05-0.07% additional sale price. The anchoring benefit does NOT compensate for the TOM penalty.**"* | Playbook Finding 1 |
| **Anglin, Rutherford & Springer (2003)**, *JREFE* 26(1):95–111 | *"**Each 10% increase in list price above market value increases time on market by approximately 20–30%**; overpricers take multiple reductions, each eroding confidence."* | synopsis §3.5 |
| **Cardella & Seiler (2016)** | *"High-precise pricing (precise number above the round) produced highest final sale prices and largest seller share of the surplus."* Experimental conditions: buyer reservation value held at $205,000; **Rounded $200,000 / Just Below $199,000 / High Precise $201,326 / Low Precise $198,674.** Playbook calls it *"the single most actionable academic finding in this entire playbook"* and notes the effect *"persists even among real estate professionals."* | Anchoring_Effect README; `SYNOPSIS_higher_price_evidence.md` A3 |
| ⚠ | Journal citation disputed: book says *JREFE* 52(4):434–461, research file says *J. Economic Psychology* 52(C):71–90. Flagged twice as "verify before reuse". | — |
| **Nikiforou, Dimopoulos & Sivitanides (2022)**, 538 transactions, Cyprus | *"In transparent markets (where sold prices are published — like Australia), the optimal Degree of Overpricing (DOP) is approximately **1.5%**. **A 1% increase in DOP increases the probability of selling within 30 days by 1.23%.**"* | Playbook Finding 1 |
| ⚠ | **Excluded from shipping copy**: *"The paper is `[A]` but **is not located on file** and is not in `references.ts`… which is exactly why it does not ship on an unverified reference." (Open item 3.)* | `Session_03…md` |
| **Beracha & Seiler (2014)**, *JREFE* | Just-below ($999,000) draws the largest negotiated discount but nets **+2.5–3% higher sale prices** vs round. Flagged as **directly conflicting** with Cardella & Seiler; playbook resolves as "format vs position". | Playbook Finding 6 |
| **Taylor (1999)**, *RES* 66(3):555–578 | >10% overpricing → **2–5× longer** on market; TOM stigma "self-reinforcing". | Playbook Finding 2 |
| **Zillow Research (2017/2019)** | "Homes where sale price was 10% below list price spent **5x** as long on market. **After 2 months, homes sell for 5% less than listing price.**" / 12%+ over → **~50% less likely to sell within 60 days** (25,000 sales). | Playbook Finding 2; synopsis §5 |
| **CoreLogic Australia** | "Properties listed 10-15% above eventual sale price spend **2-3x longer** on market." | Playbook Finding 2 |
| **Khezr (2015)**, *Applied Economics* 47(29):3049–3060 | **25,000+ Sydney sales** — overpriced homes take longer and sell for less. | `SYNOPSIS_higher_price_evidence.md` A1 |

**The asymmetry disclosure Fields itself imposes** (`Session_03…md`, Card 4 rules, verbatim):

> "**Nothing we hold documents a cost of launching materially below the market**, and Bucchianeri & Minson is not that evidence — it finds underpricing does *not* reliably manufacture a bidding war, which is a null result about a tactic, not a measured penalty. Writing 'in either direction' described the evidence as more complete than it is… The permitted line is: **'the evidence is clearest about launching above what buyers can justify.'**"

---

## 4. Price-reduction / repricing data

- **Knight (2002): 38.4% of listed properties undergo price changes** (external benchmark).
- **Fields live inventory:** 58/77 = 75% reduced, median 4.3%, mean 4.8%, max 17.6% (conditioned on ≥2 price points) — `BUYER_TO_SELLER_BRIDGE.md` §1.4.
- **Fields event log:** 130 reduction events / 98 properties, **median cut 3.29%**, 2026-03-21→2026-08-06 — E4 finding.
- **Effect on DOM:** *"sold homes that cut their price ran a median **68 days vs 37** for those that didn't."* ⚠ **Caveat stated at source:** `price_history[]` exists on **270/1549 sold docs but only 32 with ≥2 PRICED events** (many first events are "Auction"/"EOI" with null price); 64 withdrawn, 48 with a priced event; `days_on_market` is NULL on withdrawn. — `memory/adjusted_comparables_evidence.md` §7.
- **Coverage improvement logged:** `logs/fix-history/2026-08-05.md:218` — adding `_extract_asking_price_history()` raised asking-price coverage across the 555-property candidate pool from **42 to 84**; "56 of those… previously had no guide at all, and **11 had a price reduction that was completely invisible**."
- **Live public page is wrong by 5.5×:** `market-insights.mjs:503` caps the query at `.limit(20)`, so the public Price Adjustments panel reported "20 changes (30d), 4 reductions" for Robina when the DB held **121 events / 22 reductions**; Varsity Lakes 103/15, Burleigh Waters 50/8 (E4 Finding 3, VERIFIED). Do not quote the public page.
- **Accuracy incident, directly on point:** Fields published *"$1,700,000 in Robina: How 16 Collingwood Avenue Beat the Suburb Median by 11.8%"* about a home that **opened as EOI, advertised $1,949,000, cut to $1,749,000, sold $1,700,000 after 127 days** — and called the reduced price "the guide" (9 mentions). Fix logged: *"How It Sold must read `price_history`, not just `listing_price`"* — otherwise any reduced campaign reads as a win.
- ⚠ **A structural warning on repricing:** `scripts/backend_enrichment/generate_sold_analysis.py:149` — *"`listing_price` is deliberately NOT in the price chain. It is the ASKING price"* — Fields' own code treats asking ≠ sale as a correctness invariant.

---

## 5. "Offers Over" / price guides / Form 6 floor / "Contact Agent"

`/home/fields/Fields_Orchestrator/15_On_Market/` exists. Primary sources: `01_Research/04_price_transparency_and_underquoting.md` (542 lines) and `04_Evidence/own_inventory_price_opacity_2026-08-10.md`.

**Measured on own live data, 2026-08-10, n=205 for-sale listings across Robina / Varsity Lakes / Burleigh Waters. Two independent classifications:**

| Strand 04 | n | % | | Evidence file (reclassified by legal meaning) | n | % |
|---|---:|---:|---|---|---:|---:|
| Single displayed price | 52 | 25.4% | | A single price | 40 | 19.5% |
| Explicit price range | 4 | 2.0% | | A range / price guide | 3 | 1.5% |
| "Offers over $X" (a floor) | 77 | 37.6% | | "Offers Over" — Form 6 floor | 87 | 42.4% |
| No numeric figure anywhere | 72 | 35.1% | | No number at all | 75 | 36.6% |

Headline conclusion, verbatim: **"79% of live listings in our three suburbs do not state an estimate of value."** Auction is **4.9%** of listings — *"Any product framing that treats this as an auction issue will address 5% of the market."* **Exactly one** of 205 listings displayed a genuine range in the headline ("PRICE GUIDE: 1.35 to 1.45M", 9 Gainsborough Dr, Varsity Lakes).

**How buyers read it, per the file:**
- *"'**Offers over $X**' is not an estimate of value. Queensland OFT guidance is explicit: 'If you use an offers-over price, it should be the minimum amount the vendor is willing to accept.' The figure comes from the seller's Form 6 appointment… So 'Offers over' is a **floor derived from the seller's instruction**, and tells the buyer nothing about the ceiling."*
- **72% of buyers skip a listing without a price** (REA Property Seeker, n>6,000); REA calls it *"the number one source of dissatisfaction on our platform."* HouseSeeker puts it at 81% — flagged as **lower-confidence, vendor-published**.
- Legal frame: POA 2014 (Qld) **s 216(2)(c)** bans a price guide on auction property (540 PU × $172.70 = **$93,258**); **s 216(3)** extends the gag to non-auction sales where the seller instructs non-disclosure. **s 216(6)**: the CMA goes to the seller; the buyer can only get it with the seller's written approval.

**⭐ The "blind price" finding (original, verified 2026-08-10): 12 of 12 sampled no-price Domain listings carried a numeric price in the page JSON** (`priceDetails.rawValues` / `exactPriceV2`) — e.g. Auction listings showing $1,100,000 and $1,399,000; "Contact Agent" showing $1,600,000. Cross-validated: 9 Gainsborough Dr advertising "1.35 to 1.45M" carries `exactPriceV2: 1,400,000` — exactly the midpoint. ⚠ Two explicit caveats: *"The bracket is the **agent's** number, not evidence of value"*, and republishing raises portal ToU/copyright questions — **"Do not republish the portal's hidden 'blind price'… without advice."**

**External list-vs-sale benchmarks in the same file** (Australian, not Gold Coast):
- Guardian/Spachus (26 Oct 2023 – 5 Jul 2024): final price >10% above highest pre-sale guide in **Sydney 20% / Perth 18%** of sales; **65% of Sydney houses sold at auction**.
- Homer (6 months to ~May 2026, Sydney): **median sale $117,500 above the top of the advertised range; 49.8% above guide, 39.7% below, 10.5% at guide**; Sydney overshoots guides by 4–9%.
- SMH/Homer May 2026: the 50 worst-scoring NSW agents guided **16.2% below eventual sale price** on average; the 50 worst in Victoria guided **7.1% above**.
- CPRC Victoria (n=500 buyers): **34% of properties purchased sold above the top of the indicative price**; 24% by <10%, 5% by 10–20%, 2% by >20%.
- **⭐ Guardian 2024, the finding most on point for your claim:** *"The final sales price was higher than the price guide for **92%** of sales, but it was only higher than the automated estimate for **44%** of properties."* File's reading: *"not because the model is precise, but because **the guide is a marketing instrument and the model isn't**."*

⚠ **Do-not-claim warnings in this file:** *"a sale above a guide is **not** proof of underquoting"*; *"Fields must never assert or imply that a named agent underquoted"*; *"**do not build an agent scorecard**"* (RealAs took two cease-and-desists for "most inaccurate agents"; Homer survives by framing it as *"the average gap between two key publicly available pricing markers"*). Also: POA ss 207–209 apply to representations about "the value of the property" with a **reverse onus** (s 209(5)) and **14-day compelled substantiation** (s 217).

Memory file `on_market_buyer_research_2026-08.md` exists at the path you gave and matches. It adds: *"The live page currently ships **'19.7% above the local trend — Overpriced'** — remove it"*, and the three-layer staleness bug: **58 of 113 listings with editorial (51%) argue against a price the seller has already moved off**, worst case 129 days.

---

## 6. Range vs single figure, and `valuation_method_comparables.md`

The memory file (2026-07-27, Will) verbatim:

> **"we don't use that model any more — we use the comparables method. That is what the editorial is looking at."**
> "**The valuation we present (editorial + public) is the comparable-sales METHOD: a RANGE built from adjusted comparable sale prices — never a single figure.**"
> Hard rule (`generate_property_ai_analysis.py` lines 1222 / 1354): **"NEVER quote a single valuation figure — always the range. 'The range IS the valuation.'"**
> `valuation_data.confidence.reconciled_valuation` is the **DEPRECATED** single weighted midpoint.
> ⚠ Staleness: `valuation_data` is recomputed and **overwritten with no history** — e.g. 6 Moorhen's published "comps average $1,754,364" had moved to $1,903,585; 27 Florabella "$1,238K" → $1,274,188. **Recompute before reusing any published figure.**
> ⚠ CLAUDE.md still centres `reconciled_valuation` — documented drift, unresolved.

**What the range actually is** (`/home/fields/Fields_Orchestrator/16_Valuation/methodology/03-the-range.md`, verified 2026-08-07 against 641 sales in envelope):

> "A **flat ±12% of the point estimate**… **It is not a confidence interval, and it must never be described as one.**"

| what we print | band on $1.6M | contains the eventual sale |
|---|---|---|
| ±12%, as shipped | $384,000 | **58%** |
| ±16.4% (per-suburb offsets) | $524,000 | 80% |
| ±18.9% (uncorrected) | $604,000 | 80% |

> "So **roughly four sales in ten fall outside the band we publish**, not one in ten. A genuine 90% band would need about **±26.4%**."

Two live pages previously claimed "90% confidence interval"; both corrected. **"Do not reintroduce this language anywhere."**

Related figures for context: Fields vs Domain on the same property (n=78) — **median absolute disagreement 7.9%, mean 11.7%, >5% on 72%, >10% on 42%, 90th pct 33.6%** (≈$110k on a $1.4M home). Domain's own published range is **a fixed ±≈13.8%** (median width 27.6%, 25th/75th 27.2%/28.0%). The binding caveat, verbatim: *"**We CANNOT claim to be more accurate** — our band is also flat (±12%) and holds only 61% of the time. The differentiator is transparency (working shown + published error rate), never accuracy."*

---

## Bottom line for your claim

**Quotable and reasonably solid:**
- Median first-ask→sale gap **−2.5%**, n=54 verified pairs, 2026-03-21→2026-08-06 (worst −12.8%).
- Median price cut **3.29%** (130 events / 98 properties) or **4.3%** (58/77 live listings with ≥2 price points).
- **48% of sold homes (n=142) sold below their first ask; 25% finished >5% away from it.**
- **79% of live listings (n=205) do not state an estimate of value; 42.4% show an "Offers Over" Form 6 floor**, which QLD OFT defines as the seller's minimum, not an estimate.
- Guardian 2024: sale exceeded the agent's guide **92%** of the time vs the AVM **44%** — the cleanest external proof that a guide is a marketing instrument.
- Knight (2002): **38.4%** of listings reprice; repricers sell for less than correctly-priced-from-day-one.

**Do not claim without qualification:**
- "30% of listings cut their price" — **invalid denominator**, I verified the tracker only writes an event on change.
- "75% of listings change price" — the 75% is conditioned on ≥2 recorded price points (58/77), not all listings.
- The **+18% Robina asking-vs-valuation gap and its 23d/100d/150d DOM** — **not reproducible** (dead macOS path), Domain used as a value proxy, DOM contaminated by relistings.
- Any **DOM** figure from the 2,153-property corpus — native coverage **0.8%**, model CV R² **0.006**.
- The Playbook's "Price Positioning by Suburb" table — it measures price vs bedroom-cohort median, and all three correlations are non-significant (p = 0.31, 0.45, 0.49).
- **Sale-vs-Domain** figures (−6.9% / −11.8% / −5.0%) — benchmark contaminated, clean subset n=21, official verdict: no valid comparison in either direction.
- Any effect size for **Haurin 2010**, **Merlo/Ortalo-Magné/Rust 2015**, or **Genesove & Mayer 2001** — Fields holds one-line glosses only, and Session 3 explicitly bans magnitudes on Genesove & Mayer.
- Nikiforou's **1.5% optimal DOP** — the paper is not on file and is banned from shipping copy.

**The claim's own biggest problem, per Fields' own audit:** in a 92% private-treaty market the list price is *also* an anchor and a practical ceiling on offers (Haurin 2010; Northcraft & Neale 1987; Bucchianeri & Minson 2013 — anchoring real but **0.05–0.07% per 10–20% overprice**). Stating "attraction tool, not expected sale price" without that qualification is what produces the underpricing failure mode, and the book, the playbook (Step 2: list at +2-4%) and the appraisal template (list at the *bottom* of the range) currently give three different answers.
