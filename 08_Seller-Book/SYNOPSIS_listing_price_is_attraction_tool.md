# "The listing price is a buyer attraction tool — not your expected selling price"

**A synopsis of the research, evidence and commentary on this statement across *Before You List* and the wider Fields evidence base**

Companion to [SYNOPSIS_higher_price_evidence.md](SYNOPSIS_higher_price_evidence.md). Sources: `output/seller_book_draft_v4.md`; `08_Seller-Book/Market_Data/`; `12_Marketing/02_Drive_Research/FIELDS_POSITIONING_PLAYBOOK_v5_0_ACADEMIC_EVIDENCE_EDITION.md`; `15_On_Market/01_Research/` and `04_Evidence/`; `16_Valuation/methodology/`; `scripts/appraisal_template/render.py`; `system_monitor.price_change_events`.

---

## Verdict up front

**The statement is the book's own thesis, almost word for word — and it is half right. The half that is wrong is the expensive half.**

It is a correct, well-evidenced corrective to the mistake it targets: sellers treating the asking price as their hoped-for sale price and inflating it to leave negotiating room. Six independent studies say that fails.

It is wrong if read as *"the listing price doesn't determine what you get."* In a private-treaty market — **95% of southern Gold Coast listings** — the listing price is also an **anchor** and behaves in practice as a **ceiling on offers**. The book says so itself, two pages after making the attraction argument.

**And Fields currently gives three different answers to this question across three shipped products:**

| Artefact | What it says the listing price is | Where to set it |
|---|---|---|
| **The book** (Ch 4) | "a marketing tool… not the sale price" | Inside the valuation range, precise, above the round number |
| **Positioning Playbook v5.0** (Step 2) | an **anchor** — *"the anchoring hypothesis dominates"* | **True value +2–4%** ("the negotiation buffer") |
| **The appraisal template** (shipped) | explicitly **not** the expected sale price | **The bottom of the range**; target sale price is the top |

Nobody has reconciled them. That is the single most important thing to fix before this statement goes into public copy.

**The version the evidence actually supports:**

> The listing price is the primary tool for deciding **which buyers ever see your home**. It is not a prediction of the sale price, and it is not a negotiating cushion. But it also anchors the negotiation and, in private treaty, functions as a practical ceiling on offers — so it must be set close to true value, not high to leave room and not low to attract.

---

## 1. The book states the claim directly

Chapter 4, immediately after the Federal Place overpricing case study:

> "The seller's mistake wasn't wanting a high price. Everyone wants a high price. The mistake was **confusing the asking price with the sale price**. They're different things, and the relationship between them is more complex than 'list high, negotiate down.'"

> **"The asking price is a marketing tool. The sale price is the outcome. They are not the same thing. Confusing them is where most overpricing mistakes begin."**

That bolded sentence is the statement, with "marketing tool" in place of "buyer attraction tool". It is set as a pull-quote in the printed book.

The book's model is three deliberately separated numbers: **valuation** (what the comparables say) → **listing price** (a marketing decision derived from it) → **sale price** (the outcome). The statement is the second arrow.

**Fields' own code treats this as a correctness invariant.** `scripts/backend_enrichment/generate_sold_analysis.py:149` carries the comment: *"`listing_price` is deliberately NOT in the price chain. It is the ASKING price."*

---

## 2. Evidence FOR — the listing price's job is to determine who sees the home

### 2.1 The mechanical case: portal search brackets

The book's clearest support is plumbing, not psychology. Chapter 4, *Price Brackets and Portal Visibility*:

- Common Gold Coast search brackets: $1,000,000–$1,250,000, $1,250,000–$1,500,000, $1,500,000–$2,000,000.
- **"A home listed at $1,510,000 is invisible to that buyer. A home listed at $1,495,000 appears in their search."**
- And then, in one sentence, the entire statement: **"The difference between visibility and invisibility is $15,000 in listing price — which may or may not be $15,000 in achievable sale price."**

Strategy: *"identify your natural buyer pool, find the bracket they're searching in, and price within that bracket."* Top of the correct bracket beats bottom of the one above — a $1,485,000 home is seen by every buyer in the $1.25–1.5M range including those hoping to spend $1,350,000 who might stretch; at $1,510,000 it becomes "the cheapest option and perceived as the least desirable" in the bracket above.

The listing price here is pure audience selection, explicitly decoupled from achievable value.

### 2.2 The listing price as a filter, before anyone forms a view on the home

> "A buyer looking at properties in the $1,250,000 to $1,400,000 range in Robina has perhaps 15 to 20 options on any given Saturday. They have time to inspect maybe four or five… A property listed at $1,450,000 that is worth $1,300,000 doesn't appear on their shortlist — **not because they can't afford $1,450,000**, but because other properties at that price are clearly better value. The overpriced listing is **invisible to its natural buyer pool and uncompetitive in the pool it's been placed into**."

The buyer never evaluates the property. The listing price alone removed it. That is an attraction-tool failure, not a valuation failure.

### 2.3 A price — any price — is the price of admission

**72% of buyers skip a listing without a displayed price** (REA Property Seeker, n > 6,000). REA calls it *"the number one source of dissatisfaction on our platform."* A vendor-published figure from HouseSeeker puts it at 81% — flagged internally as lower-confidence.

Positioning Playbook v5.0's "What NOT To Do" list is blunt: **"Never use 'Contact Agent' — 72% of buyers skip it, 20–30% less engagement."**

Underpinned by the ambiguity-aversion literature: **Ellsberg (1961)**, **Frisch & Baron (1988)**, **Fox & Tversky (1995)** (aversion rises with stakes), **Gneezy, List & Wu (2006)** (uncertain prospects valued *below the worst guaranteed outcome*).

### 2.4 The one direct measurement of the attraction function

**Nikiforou, Dimopoulos & Sivitanides (2022)**, *J. European Real Estate Research*, 538 transactions, Cyprus — the only study in the base that measures the listing price's attraction effect separately from its price effect:

- In transparent markets where sold prices are published (i.e. Australia), the **optimal Degree of Overpricing is ~1.5%**.
- **Each 1% increase in Degree of Overpricing raises the probability of selling within 30 days by 1.23%.**

That second figure is the statement quantified — a dial that moves buyer response, measured independently of price achieved.

> ⚠ **Do not publish this figure.** The paper is not held on file and is not in `references.ts`; it is explicitly excluded from shipping copy for exactly that reason. Usable for internal reasoning only until the PDF is obtained.

### 2.5 The listing price as a signal rather than a number

**Cardella & Seiler (2016)** treat the listing price as communication. Four conditions: precise not round; above the round number not below; small deliberate gap; and — the tell — **the property must present at the upper end of its comparable range**. The listing price only performs if the rest of the campaign backs it. Their experimental design held buyer reservation value at $205,000 and tested Rounded $200,000 / Just Below $199,000 / High Precise $201,326 / Low Precise $198,674. The effect **persists among real estate professionals**.

The book's translation: *"The round number says 'we think it's worth about $1.4 million.' The precise number says 'we've analysed the comparables… and arrived at $1,415,000.'"*

> ⚠ Journal citation disputed: the book gives *JREFE* 52(4), 434–461; the internal research file gives *Journal of Economic Psychology* 52(C), 71–90. Verify before reuse.

### 2.6 The book's own two cases show list ≠ sale in both directions

| | Listed | Sold | Gap | Days |
|---|---|---|---|---|
| Federal Place, Robina (real) | $1,450,000 | $1,290,000 | **−$160,000** | 97 |
| Sarah & Mark, Robina (composite) | $1,415,000 | $1,420,000 | **+$5,000** | 13/16 |

The listing price predicted neither outcome. Its *accuracy relative to true value* predicted both.

### 2.7 What the Gold Coast data actually shows about list vs sale

This is the empirical core of the claim, and it did not make it into the book.

**Verified against production** (`system_monitor.price_change_events`, writer `scripts/track_price_changes.py`, 786 events / 322 distinct properties, 2026-03-21 → 2026-08-06):

- **130 price-reduction events across 98 distinct properties** (Robina 61, Burleigh Waters 38, Varsity Lakes 31). **Median reduction 3.29%.**
- Of properties with both a parsed first asking price and a sale price (**n = 54**): **median first-ask → sale gap −2.5%; worst −12.8%.**
- Worked examples: 16 Collingwood Ave, Robina $1,949,000 → $1,700,000 (−12.8%); 3/4 Ben Lexcen Pl, Robina $895,000 → $815,000 (−8.9%); 29 Lantau Cr, Varsity Lakes $1,249,000 → $1,150,000 (−7.9%).

**On live Fields listings with two or more recorded price points** (`15_On_Market/02_Synthesis/BUYER_TO_SELLER_BRIDGE.md` §1.4):

| Reduced their price | **58 of 77 = 75%** |
|---|---|
| Raised | 5 |
| Median reduction | **4.3%** (mean 4.8%, max 17.6%) |

**On sold homes where both a first asking price and a sale price are held (n = 142): 48% sold below their first ask, and 25% finished more than 5% away from it** — on a $1.4M home, more than $70,000.

**External Australian benchmarks** (`15_On_Market/01_Research/04_price_transparency_and_underquoting.md`):

- **⭐ Guardian (2024) — the cleanest external proof of the claim:** *"The final sales price was higher than the price guide for **92%** of sales, but it was only higher than the automated estimate for **44%** of properties."* The file's reading: *"not because the model is precise, but because **the guide is a marketing instrument and the model isn't**."*
- **Homer** (6 months to ~May 2026, Sydney): median sale **$117,500 above the top of the advertised range**; 49.8% above guide, 39.7% below, 10.5% at guide.
- **CPRC Victoria** (n = 500 buyers): **34% of properties purchased sold above the top of the indicative price** — 24% by <10%, 5% by 10–20%, 2% by >20%.
- **Guardian/Spachus** (Oct 2023 – Jul 2024): final price >10% above the highest pre-sale guide in **20% of Sydney and 18% of Perth** sales.

> ⚠ Denominator traps, both verified. **"30% of tracked listings cut their price" is invalid** — `track_price_changes.py` only writes an event when the price *changes*, so the 322 denominator is already conditioned on change. **"75% of listings change price" is also wrong** — the 75% is 58/77 listings *with ≥2 recorded price points*. Use the conditioned form in both cases.

### 2.8 The Gold Coast market barely publishes a listing price at all

Measured on Fields' own live inventory, 2026-08-10, **n = 205 for-sale listings** across Robina, Varsity Lakes and Burleigh Waters (`15_On_Market/04_Evidence/own_inventory_price_opacity_2026-08-10.md`):

| Classification (by legal meaning) | n | % |
|---|---:|---:|
| A single displayed price | 40 | 19.5% |
| A range / genuine price guide | 3 | 1.5% |
| **"Offers Over $X" — a Form 6 floor** | **87** | **42.4%** |
| No number at all | 75 | 36.6% |

**Headline: 79% of live listings in the three suburbs do not state an estimate of value.** Exactly **one** of 205 displayed a genuine range in the headline ("PRICE GUIDE: 1.35 to 1.45M", 9 Gainsborough Dr, Varsity Lakes).

This is the strongest available support for the claim, because it shows the market itself does not treat the listing price as an expected sale price:

> *"'**Offers over $X**' is not an estimate of value. Queensland OFT guidance is explicit: 'If you use an offers-over price, it should be the minimum amount the vendor is willing to accept.' The figure comes from the seller's Form 6 appointment… So 'Offers over' is a **floor derived from the seller's instruction**, and tells the buyer nothing about the ceiling."*

**Auction is only 4.9% of these listings** — *"Any product framing that treats this as an auction issue will address 5% of the market."* (The book says 8%, from a different and larger sample.)

**The "blind price" finding** (original, verified 2026-08-10): **12 of 12 sampled no-price Domain listings carried a numeric price in the page JSON** (`priceDetails.rawValues` / `exactPriceV2`) — Auction listings showing $1,100,000 and $1,399,000; "Contact Agent" showing $1,600,000. Cross-validated: the one listing advertising "1.35 to 1.45M" carries `exactPriceV2: 1,400,000`, exactly the midpoint. So a number exists behind almost every "no price" listing — it is simply not shown to the buyer.
> ⚠ Two caveats at source: *"The bracket is the **agent's** number, not evidence of value"*, and republishing it raises portal ToU/copyright questions — **"Do not republish the portal's hidden 'blind price' without advice."**

**The legal frame** (Property Occupations Act 2014 (Qld)): **s 216(2)(c)** bans a price guide on auction property (540 penalty units × $172.70 = **$93,258**); **s 216(3)** extends the gag to non-auction sales where the seller instructs non-disclosure; **s 216(6)** means the CMA goes to the seller, and a buyer can only obtain it with the seller's written approval. So in Queensland the absence of an expected sale price is partly a matter of law, not just marketing.

### 2.9 The strategic frame the whole book is built on

Chapter 7: *"The goal is to concentrate as many qualified buyers as possible into the same narrow window of time."* Chapter 4: *"When multiple buyers want the same property, they stop negotiating against the seller and start negotiating against each other."* Under that model the listing price is a funnel input, not a claim about value — which is the statement.

---

## 3. Evidence AGAINST — the listing price is also an anchor, and in private treaty a ceiling

### 3.1 The book contradicts itself two pages later

Chapter 4, *The Underpricing Question*:

> **"When a buyer sees a property priced attractively, their instinct is not to offer more than the asking price. Their instinct is to offer the asking price, or slightly below, and negotiate from there. The anchor works in the buyer's favour, not the seller's."**

If the asking price were purely an attraction tool, a low one would draw a crowd who would bid it up. The book says explicitly that this does not happen in private treaty — because the asking price **is** the anchor, and in practice the top of the range. The book never reconciles the two sentences; both are in the same chapter.

### 3.2 The listing price is an upper bound on offers

**Haurin, Haurin, Nadauld & Sanders (2010)**, *Real Estate Economics* 38(4), 659–685 — held in the Positioning Playbook's 14-paper set as **"list price as upper bound on offers."** In a 95%-private-treaty market this is the single most important qualification: whatever else the listing price is doing, it is capping the outcome.

> ⚠ **The one-line gloss is all Fields holds.** No effect size, sample or quotation anywhere. The PDF is on disk (`12_Marketing/01_Research_Articles/Haurin_et_al_2010_List_Prices_Sale_Prices_Marketing_Time.pdf`) but has never been read into a note. **Do not quote a number from Haurin 2010.**

### 3.3 Anchoring is real — small, and in the seller's favour

**Bucchianeri & Minson (2013)**, *JEBO* 89, 76–92, 14,000+ US transactions. Verbatim from the playbook:

> "Higher listing prices DO anchor higher sale prices, but **the effect is tiny: overpricing by 10-20% yields only 0.05-0.07% additional sale price. The anchoring benefit does NOT compensate for the TOM penalty.**"

The listing price transmits to the sale price — weakly, but non-zero and in the right direction. It is not inert. The reason not to inflate it is that the time-on-market penalty is far larger, not that the listing price has no price effect.

### 3.4 Anchoring works on professionals, who deny it

**Northcraft & Neale (1987)**, *OBHDP* 39(1), 84–97: *"Manipulated listing-price anchors influenced both students and experienced real-estate agents inspecting identical properties. Crucially, **agents claimed not to use the listed price — but their appraisals tracked the manipulation**."* (Recorded acknowledgement rate: 19%.)

The listing price does not merely attract buyers; it moves the price judgement of everyone who sees it, including the valuer and the competing agent.

### 3.5 The dial is sticky and expensive to turn

- **Knight (2002)** — **38.4% of listed properties undergo price changes**; large changes bring *both* longer time on market *and* lower final price. *"Sellers who initially overprice their homes and subsequently reduce their asking prices receive lower selling prices than sellers who price their homes correctly from the start."* ⚠ Citation in dispute: the book gives *JREFE* 24(1-2), 93–119; the research file gives *Real Estate Economics* 30(2), 213–237.
- **Taylor (1999)**, *RES* 66(3), 555–578 — time-on-market stigma; >10% overpricing is 2–5× slower. You do not get a clean second attempt.
- **Anglin, Rutherford & Springer (2003)**, *JREFE* 26(1), 95–111 — **each 10% above market value adds ~20–30% to time on market**; overpricers take multiple reductions, each eroding confidence.
- **Merlo, Ortalo-Magné & Rust (2015)** — list price stickiness; sellers do not adjust freely. ⚠ Fields holds a one-line gloss only; no PDF, sample, effect size or journal. The reference file instead holds **Merlo & Ortalo-Magné (2004)**, *J. Urban Economics* 56(2), 192–216 — a different paper. Not quotable beyond the gloss.
- **Zillow Research** — homes selling 10% below list spent **5× as long** on market; after two months homes sell **5% below list**; 12%+ over → ~50% less likely to sell within 60 days.
- **CoreLogic Australia** — listed 10–15% above eventual sale price → **2–3× longer** on market.

A pure "attraction tool" would be a low-stakes lever you could re-tune. The evidence says it is a one-shot decision with asymmetric downside.

### 3.6 Most sellers aren't setting it as a marketing decision at all

**Genesove & Mayer (2001)**, *QJE* 116(4), 1233–1260 — sellers facing nominal losses set **higher asking prices and achieve lower sale probabilities**. The listing price is frequently an expression of the seller's cost basis and loss aversion, not a strategy. This is the real starting condition the statement is trying to correct.

> ⚠ **Fields holds no magnitude for this paper** and has explicitly banned quoting one: *"Genesove & Mayer carries no magnitude here… the hosted PDF has not been read for this draft."* A 2026-05-06 log line citing 25–35% / 3–18% is uncorroborated. Use the direction only.

### 3.7 A conflicting result on format

**Beracha & Seiler (2014)**, *JREFE* — "just below" pricing ($999,000) attracts the *largest* buyer-negotiated discount but, because it embeds a higher initial overprice, can net **+2.5% to +3% higher sale prices** than round pricing. Flagged internally as directly conflicting with Cardella & Seiler; the playbook resolves it as "format vs position." Relevant here as a case where the listing price is deliberately set as an attraction device with a known give-back — and still determines the sale price.

### 3.8 The asymmetry Fields imposes on itself

From the mini-site content rules, verbatim — the most careful sentence anyone at Fields has written on this:

> "**Nothing we hold documents a cost of launching materially below the market**, and Bucchianeri & Minson is not that evidence — it finds underpricing does *not* reliably manufacture a bidding war, which is a null result about a tactic, not a measured penalty. Writing 'in either direction' described the evidence as more complete than it is… The permitted line is: **'the evidence is clearest about launching above what buyers can justify.'**"

That is the honest boundary. The evidence against overpricing is strong and quantified. The evidence against *under*pricing is a null result about a tactic, not a measured penalty.

---

## 4. Where the statement is unambiguously true: it depends on the method of sale

The book never draws this distinction, but its own mechanisms require it.

| | Auction (QLD) | Private treaty |
|---|---|---|
| Is there a listing price? | **No** — s 216(2)(c) POA prohibits a price guide | Yes, though 79% show no value estimate |
| Is it an expected sale price? | Not applicable | Functions as a practical ceiling on offers |
| Statement's accuracy | **Fully true** — the price field is a method label doing pure (negative) attraction work | **Half true** — it selects the audience *and* anchors the outcome |
| Share of southern GC listings | **4.9%** measured on own inventory (book says 8%) | ~95% |

The cost of the auction version: 72% of buyers scroll past. Removing the price entirely maximises ambiguity and minimises attraction — the opposite of what an "attraction tool" framing would recommend.

---

## 5. Fields' three products currently give three different answers

### 5.1 Positioning Playbook v5.0 — the listing price is an **anchor**, set *above* value

Part 3, *The Fields Pricing Framework* (2,153 sold properties + 14 academic papers, dated 2026-04-04). Its Finding 3, verbatim:

> "In residential real estate (unlike auctions), there are seldom enough buyers to create a 'herding effect.' **The anchoring hypothesis dominates. Higher starting prices produce higher final sale prices in private treaty.**"

Finding 1: *"List at 1-5% above true value to create negotiation room and **anchor upward**. Beyond 5%, the TOM penalty starts to outweigh the anchoring benefit. Beyond 10%, it becomes actively destructive."*

The five steps:

1. **Establish true market value** — the reconciled comparable-sales valuation.
2. **Set the list price at true value +2–4%** — *"This is the negotiation buffer."* Hot market (suburb DOM <20d): at value or −2%. Cold market (DOM >45d): at value or −2%, because *"speed matters more than anchoring in weak markets."*
3. **Bracket optimisation** — *"Position the price at the TOP of a portal search bracket, never the bottom of the next one."* Worked: valuation $1.28M, +3% = $1.318M → price **$1,295,000**, not $1,315,000. *(This is the only pure attraction argument in the framework, and it overrides step 2.)*
4. **Make it precise** — $1,295,000 not $1,300,000.
5. **Express as a range** — *"$1,245,000 – $1,295,000. The low end sits within the bracket below (captures those buyers too). The high end is precise and slightly below the bracket boundary."*

Suburb adjustments: Robina **+1–3%** (homogeneous, punished harder); Varsity Lakes **+2–4%**; Burleigh Waters **+3–5%**.

"What NOT to do": never overprice >10%; never "Contact Agent"; never underprice to create urgency; **"Never do incremental small reductions — one decisive 5%+ cut at 4 weeks, or withdraw and relist"**; never round numbers.

### 5.2 The shipped appraisal template — the listing price is the **bottom** of the range

`scripts/appraisal_template/render.py:1548–1570`, live copy:

> "The listing price sits in the **lower end** of the derived $X – $Y range. The target sits in the **upper end**. The **$A – $B gap** between them is **intentional** — it is the stretch room buyers reach through competitive bidding, not the price the seller hopes to defend through negotiation. *Multiple interested buyers move from the listing price toward the target. A single buyer moves the other way.*"

**This is the strongest internal artefact supporting the statement** — an explicit, shipped declaration that the listing price is not the expected sale price, with a stated mechanism for why. It also directly contradicts Playbook Step 2, which sets the list price *above* true value as a negotiation buffer.

### 5.3 The book — the listing price sits *inside* the valuation range

Sarah & Mark: valuation $1,380,000–$1,430,000 → listed **$1,415,000**. Inside the range, near the top, precise, above the round number, small gap, in the right search bracket.

### 5.4 The reconciliation problem

- The **book** puts the listing price inside the valuation range.
- The **playbook** puts it 2–4% above true value.
- The **appraisal template** puts it at the bottom of the range, with the top reserved as the target.

All three cite the same literature. They cannot all be right, and a seller reading two of them would price the same house three different ways. This should be resolved before the statement is used in customer-facing copy.

---

## 6. The three ways sellers get this wrong

**1. Treating the listing price as the expected sale price, inflated.** "List high, we can always come down." The failure mode the statement exists to prevent.
→ Taylor: 2–5× longer. Zillow: 12%+ over → ~50% less likely to sell within 60 days. Knight: reductions produce lower final prices than correct day-one pricing. Anglin: +20–30% time on market per 10% overprice.
→ Federal Place listed $1,450,000 against comparables of $1,280,000–$1,320,000 → sold $1,290,000 after 97 days, an estimated **$20,000–$30,000** below a correct day-one campaign.

**2. Treating the listing price as pure attraction, set low.** What over-applying this statement produces.
→ Bucchianeri & Minson: *"Pricing the house too low may result in a quick sale but at a price lower than might have been achieved with a more selective pool of buyers"*; and *"there are seldom enough buyers to create a 'herding effect'"* — fatal in a 95%-private-treaty market.
→ The book: *"The anchor works in the buyer's favour, not the seller's."* The stated exception, extreme undersupply, is dismissed: *"like planning your retirement around winning the lottery."*
→ ⚠ But note §3.8: Fields holds **no measured penalty** for underpricing, only a null result about the tactic. Do not claim a cost figure.

**3. Setting it round, or hiding it entirely.** A pure attraction framing has no view on $1,400,000 vs $1,415,000, and no view on showing a number at all.
→ Cardella & Seiler: precise-above-round produces the highest final sale prices and smallest negotiation discounts. Playbook: *"$1,400,000 invites bigger discounts than $1,415,000."*
→ REA: 72% skip a listing with no price; "Contact Agent" costs 20–30% engagement.

---

## 7. What the statement should be replaced with

The book's operational answer, from Sarah & Mark, is more precise than the slogan and survives every check. Listed at **$1,415,000** because it is (a) precise, (b) above the round $1,400,000, (c) by a small deliberate gap, (d) supported by a property presenting at the top of its comparable range, and (e) inside the $1,250,000–$1,500,000 search bracket where the natural buyer pool searches.

That is a listing price doing attraction work — audience selection, signalling, bracket placement — **while sitting inside the valuation range rather than above it.** Both jobs at once. The agent's line to Mark makes the anchoring role explicit:

> "Then you negotiate from a position of strength. Your listing price is supported by the data… When a seller lists at $1,450,000 and gets an offer at $1,380,000, the buyer already knows the listing price is inflated. **The negotiation starts with the buyer feeling like they've caught you out.**"

The listing price is not the expected sale price. It is also not free of consequence for the sale price. **It is the number that decides who shows up, and sets the frame they negotiate inside.**

---

## 8. A note on ranges, since Fields sells one

Directly relevant, because Fields' answer to "the listing price is not the expected sale price" is to publish a *range* instead of a figure.

- **`memory/valuation_method_comparables.md`** (Will, 2026-07-27): *"The valuation we present is the comparable-sales METHOD: a **RANGE** built from adjusted comparable sale prices — **never a single figure**."* Hard rule in `generate_property_ai_analysis.py`: *"NEVER quote a single valuation figure — always the range. **The range IS the valuation.**"* `valuation_data.confidence.reconciled_valuation` — the single weighted midpoint — is **deprecated**. ⚠ CLAUDE.md still centres `reconciled_valuation`; documented drift, unresolved.
- **What the range actually is** (`16_Valuation/methodology/03-the-range.md`, verified against 641 in-envelope sales): *"A **flat ±12% of the point estimate**… **It is not a confidence interval, and it must never be described as one.**"*

| Band | Width on $1.6M | Contains the eventual sale |
|---|---|---|
| ±12%, as shipped | $384,000 | **58%** |
| ±16.4% | $524,000 | 80% |
| ±26.4% | — | 90% |

> *"**Roughly four sales in ten fall outside the band we publish**, not one in ten."* Two live pages previously claimed a "90% confidence interval"; both corrected. **Do not reintroduce that language.**

- ⚠ **Staleness:** `valuation_data` is recomputed and overwritten with no history. Published figures drift — 6 Moorhen's "comps average $1,754,364" had moved to $1,903,585. **Recompute before reusing any published figure.**

---

## 9. References bearing on this statement

**Supporting the "attraction tool" half**

1. **Nikiforou, A., Dimopoulos, T. & Sivitanides, P. (2022).** *J. European Real Estate Research.* 538 transactions, Cyprus. — Optimal Degree of Overpricing ~1.5%; +1% DOP → +1.23% probability of selling within 30 days. ⚠ Not on file; banned from shipping copy.
2. **Cardella, E. & Seiler, M.J. (2016).** "The Effect of Listing Price Strategy on Real Estate Negotiations." — Precise-above-round yields highest final sale prices, smallest negotiation discounts; persists among professionals. ⚠ Journal disputed (*JREFE* 52(4), 434–461 vs *J. Economic Psychology* 52(C), 71–90).
3. **Ellsberg, D. (1961).** *QJE* 75(4), 643–669. — Ambiguity aversion.
4. **Frisch, D. & Baron, J. (1988).** *J. Behavioral Decision Making* 1(3), 149–157.
5. **Fox, C.R. & Tversky, A. (1995).** *QJE* 110(3), 585–603. — Aversion rises with stakes.
6. **Gneezy, U., List, J.A. & Wu, G. (2006).** *QJE* 121(4), 1283–1309.
7. **REA Group / REA Property Seeker** (n > 6,000; also cited as REA Group 2014 in Queensland Parliament *Property Occupations Act 2014* review submissions). — 72% of buyers skip listings without a displayed price; "the number one source of dissatisfaction on our platform."
8. **The Guardian (2024).** — Final sale price exceeded the agent's price guide in **92%** of sales, but exceeded the automated estimate in only **44%**.
9. **Homer** (6 months to ~May 2026, Sydney). — Median sale **$117,500 above the top of the advertised range**; 49.8% above guide, 39.7% below, 10.5% at guide.
10. **CPRC Victoria** (n = 500 buyers). — 34% of properties purchased sold above the top of the indicative price.
11. **Guardian / Spachus** (Oct 2023 – Jul 2024). — Final price >10% above the highest pre-sale guide in 20% of Sydney and 18% of Perth sales.

**Qualifying or contradicting it**

12. **Bucchianeri, G.W. & Minson, J.A. (2013).** *JEBO* 89, 76–92. 14,000+ transactions. — Anchoring real but tiny (0.05–0.07% extra sale price per 10–20% overprice); no herding effect in private treaty.
13. **Haurin, D., Haurin, J., Nadauld, T. & Sanders, A. (2010).** *Real Estate Economics* 38(4), 659–685. — **List price as upper bound on offers.** ⚠ Gloss only; no effect size held.
14. **Northcraft, G.B. & Neale, M.A. (1987).** *OBHDP* 39(1), 84–97. — Listing-price anchors moved experienced agents' appraisals; agents denied using them.
15. **Knight, J.R. (2002).** — **38.4% of listings reprice**; repricers sell for less than correctly-priced-from-day-one. ⚠ Citation disputed.
16. **Taylor, C.R. (1999).** *Review of Economic Studies* 66(3), 555–578. — Time-on-market stigma; >10% over is 2–5× slower.
17. **Anglin, P.M., Rutherford, R. & Springer, T.M. (2003).** *JREFE* 26(1), 95–111. — Each 10% above market value → +20–30% time on market.
18. **Merlo, A., Ortalo-Magné, F. & Rust, J. (2015).** — List price stickiness. ⚠ Gloss only; no PDF or journal held. Fields instead holds **Merlo & Ortalo-Magné (2004)**, *J. Urban Economics* 56(2), 192–216.
19. **Genesove, D. & Mayer, C. (2001).** *QJE* 116(4), 1233–1260. — Loss-averse sellers set higher asking prices, achieve lower sale probabilities. ⚠ No magnitude held; quoting one is banned internally.
20. **Beracha, E. & Seiler, M.J. (2014).** *JREFE.* — Just-below pricing draws the largest negotiated discount but can net +2.5–3% vs round; conflicts with Cardella & Seiler.
21. **Haurin, D. (1988).** *Real Estate Economics* 16(4), 396–410. — Optimal list price ≈ expected market value.
22. **Khezr, P. (2015).** *Applied Economics* 47(29), 3049–3060. 25,000+ Sydney sales. — Overpriced homes take longer and sell for less.
23. **Zillow Research (2017/2019).** — 10% below list → 5× as long on market; after 2 months homes sell 5% below list; 12%+ over → ~50% less likely to sell within 60 days.
24. **CoreLogic Australia.** — 10–15% above eventual sale price → 2–3× longer on market.

**Fields original research**

25. **`system_monitor.price_change_events`** (786 events / 322 properties, 2026-03-21 → 2026-08-06, verified against production). — 130 reduction events across 98 properties; **median reduction 3.29%**; **n = 54 first-ask→sale pairs, median gap −2.5%, worst −12.8%**.
26. **`15_On_Market/02_Synthesis/BUYER_TO_SELLER_BRIDGE.md` §1.4.** — 58/77 (75%) of live listings *with ≥2 price points* reduced; median 4.3%, mean 4.8%, max 17.6%. **n = 142 sold homes: 48% sold below first ask, 25% finished >5% away.** ⚠ No committed reproduction script for the n=142 figure.
27. **`15_On_Market/04_Evidence/own_inventory_price_opacity_2026-08-10.md`** (n = 205 live listings). — **79% state no estimate of value**; 42.4% "Offers Over" (Form 6 floor); 36.6% no number; 1.5% a genuine range; auction 4.9%. Plus the **blind-price finding**: 12/12 no-price Domain listings carry a numeric price in page JSON.
28. **`16_Valuation/methodology/03-the-range.md`** (641 in-envelope sales). — Published range is a **flat ±12%**, containing the eventual sale **58%** of the time; a true 90% band needs ±26.4%.
29. **Fields Estate (2026). Domain Valuation Accuracy Study.** 1,689 estimates; 89% overvalued. ⚠ Benchmark since found contaminated — see companion synopsis §8.3.
30. **`Market_Data/DATA_SOURCES_NOTE.md`.** — Robina median Domain valuation $1,320,000 vs median asking $1,552,000, a **+18% gap**; well-priced 23 days vs overpriced (>15%) 100+ days. ⚠ **Not reproducible** — see §10.

---

## 10. Caveats before this is used publicly

1. **Disclose the anchoring/ceiling qualification** or the statement invites failure mode 2 (§6). And resolve the three-way contradiction in §5 first — the book, the playbook and the appraisal template currently disagree on where to set the price.
2. **The +18% Robina gap (ref 30) is not currently reproducible.** Its reproduce command points at a macOS path that does not exist on this VM; Domain is used as a value proxy; DOM is contaminated by relistings. Re-run before publishing.
3. **Denominator discipline.** Do not say "30% of listings cut their price" (the tracker only writes an event on change) or "75% of listings change price" (that is 58/77 listings with ≥2 price points).
4. **Do not quote effect sizes for Haurin (2010), Merlo/Ortalo-Magné/Rust (2015) or Genesove & Mayer (2001).** Fields holds one-line glosses only, and magnitudes on Genesove & Mayer are explicitly banned.
5. **Do not publish Nikiforou's 1.5%** until the paper is on file.
6. **All days-on-market figures are weakly sourced.** Native `time_on_market_days` coverage in the positioning corpus is 0.8%; the DOM model's cross-validated R² is 0.006. `price_history[]` exists on 270/1549 sold docs but only **32 with ≥2 priced events**. Use DOM directionally, never precisely.
7. **Do not cite sale-vs-Domain figures** (−6.9% Robina / −11.8% Varsity Lakes / −5.0% Burleigh Waters). The benchmark is contaminated; clean subset n=21; official verdict: *"We have no valid Fields-vs-Domain comparison in either direction."*
8. **Do not cite the Playbook's "Price Positioning by Suburb" table.** It measures price against the bedroom-cohort median (i.e. how expensive the home is), not against its own value, and all three correlations are non-significant (p = 0.31, 0.45, 0.49).
9. **Do not quote the live public Price Adjustments panel.** `market-insights.mjs:503` caps the query at `.limit(20)`, undercounting by up to 5.5× — it reported "20 changes, 4 reductions" for Robina when the database held 121 events / 22 reductions.
10. **Legal.** A sale above a guide is **not** proof of underquoting. Never assert or imply that a named agent underquoted, and **do not build an agent scorecard** — POA ss 207–209 apply to representations about "the value of the property" with a **reverse onus** (s 209(5)) and 14-day compelled substantiation (s 217). RealAs received two cease-and-desists for a "most inaccurate agents" product.
11. **Editorial rules** (`CLAUDE.md` §5): this is a data statement, not advice. Report what the research found; never tell a reader what to list at.
