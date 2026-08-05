# EVIDENCE — What People Searching Their Own Address on Google Actually Want

**Purpose.** The central question for the Off-Market page redesign (V4): someone types a bare residential address into Google and lands on `/off-market/:slug`. What do they want to know?

**Status:** internal research synthesis. Compiled 2026-08-06.

> **Provenance note.** `EVIDENCE_first_party_fields_data.md:129` cross-referenced this file as an existing sibling. **It did not exist** — not on disk, not in the repo. The 2026-08-05 research session cited it without producing it, and that session is also the one that wedged the VM twice with a runaway grep (`logs/fix-history/2026-08-06.md` → `[UGREP-REGEX-VM-LOCKUP]`). This file now fills that gap from four fresh evidence streams.

**Underlying streams — read these for full method, counts and caveats:**
| | Stream | File |
|---|---|---|
| A | Live Google SERPs for 12 real addresses | `research_intent/A_serp_intent.md` |
| B | Reddit stated motivations (5,685 posts) | `research_intent/B_reddit_motivation.md` |
| C | First-party PostHog behaviour | `research_intent/C_first_party_behaviour.md` |
| D | Google autocomplete qualifier space (772 requests) | `research_intent/D_autocomplete_qualifiers.md` |

---

## 1. The finding that explains everything else: the empty query is *forced*, not chosen

`EVIDENCE_first_party_fields_data.md` establishes that **99% of Google impressions to our address pages are bare-address queries** with no qualifier. It treats this as an observation. **Stream D found the mechanism**, and it changes what the observation means.

Google's autocomplete has a **frequency floor, and individual addresses fall below it.** Across 354 address-form queries alphabet-expanded a–z:

| Seed specificity | Empty autocomplete response |
|---|---|
| Generic (`my house `, `property value `) | 0–4% |
| Suburb + category (`robina house prices `) | 54–75% |
| **Full street address** | **89.5%** |

Of the 37 non-empty address responses, **zero contained a semantic qualifier** — only self-echo, postcode completion, or same-named streets overseas. In the entire a–z sweep across six real addresses, **exactly one letter ever completed: `q` → "qld 4226"**.

**So the searcher is not withholding intent. Google never offers them a way to express it.** There is no "…value" or "…sold price" chip to click, so they type the address and expect the destination to anticipate the question.

> **Design consequence #1, and the most important one in this document:** the page must *answer without being asked*. Every design that waits for the visitor to declare what they want — a menu, a tab bar, a "what would you like to know?" prompt — is asking them to do the thing Google has already proven they will not do. Corroborated by first-party behaviour: the `offmarket_menu_*` probe has fired **9 times total** (stream C).

---

## 2. Google models a bare address as an *entity*, not a question

Stream A fetched 12 real SERPs (4 sold, 4 for-sale, 4 off-market) across our three suburbs.

**There is no "People Also Ask" on a bare-address SERP — zero across all 12.** This was control-validated: two control queries (`how much is my house worth`, `robina qld 4226 property prices`) run through the identical pipeline each returned 4 PAA questions. So the absence is a genuine property of address SERPs, not a scraping artefact.

The only intent model Google states is **"People also search for"** (9/12 SERPs, 22 suggestions). Every one was `<exact address> + modifier`:

| Modifier | Count |
|---|---|
| for sale | 8 |
| history | 4 |
| owner | 4 |
| rent | 3 |
| **price** | **2** |
| reviews | 1 |

**Price ranks 5th of 6.** The dominant refinement is *availability* — and **5 of the 8 `for sale` refinements were on addresses that are not for sale.**

⚠️ **Do not over-read this table.** n=22 suggestions from 12 SERPs. It is directionally useful and it converges with §3 and §4 on price-not-being-primary, but the `owner` count is contradicted by two independent sources (§6.2) and should not be treated as demand.

---

## 3. What people say they want: a tiebreaker, not a number

Stream B mined 5,685 Reddit posts. Its headline reframes the brief.

**Almost nobody narrates the search itself** — 1 post in 5,685 describes typing an address into Google, and it was their *parents'* address. The recurring shape is instead:

> **Someone was given a number by a bank, an agent, or a website; they don't trust it; they go looking for a second number.**

The sharpest single artefact is an owner who listed **six public estimates of their own house spanning $382,000–$704,000 — an 84% spread — and concluded *"I have no idea."***

> **Design consequence #2:** the unmet job is **adjudication, not valuation**. A seventh estimate adds nothing. What no incumbent supplies is a reason to believe one figure over another. This is precisely what an adjusted-comparables method with visible workings can do and a black-box AVM structurally cannot — and it is independently corroborated by the PropertyChat corpus (`EVIDENCE_consumer_voice_ADDENDUM_propertychat.md` §1: two identical adjacent units valued $137k apart; a Domain estimate labelled *"high accuracy"* whose range excluded the actual sale price).

**Personas, ranked by evidence strength** (frequencies are indicative — the corpus is topic-sampled, not a random sample):

| Strength | Persona | The question behind it | ~n |
|---|---|---|---|
| **Strong** | Equity Checker | "How much can I borrow / have I got 20%?" — includes a documented workflow of playing a listing site's top-of-range against a bank | ~115 |
| **Strong** | Comparable Hunter | "What did genuinely similar homes actually sell for?" | ~53 |
| **Strong** | Pre-Sale Sizer-Upper | "If I sold, what would I walk away with?" | ~51 |
| **Strong** | Agent-Number Sceptic | "The agent said X — is that real or is it a listing tactic?" | ~39 |
| Moderate | AVM Sceptic | "This estimate on *my* home is wrong/volatile — why?" | 16 + upgraded by RSS |
| Moderate | Reno Payback | "Does this work add value?" | ~21 |
| Moderate | Tool Shopper | "Which estimate site is least bad?" | ~21 |
| Moderate | Flood/Overlay Checker | "Is this property exposed?" (SEQ-specific) | ~11 |
| Weak | Neighbour Benchmarker | "Number 14 sold — what does that make mine?" (the sale is the **trigger**, never gossip) | ~6 |
| Weak | Unsolicited-Approach Reactor / Privacy-Uneasy / Price-Opacity | — | ~5 each |

⚠️ **r/GoldCoast is an honest null.** Its property talk is rental affordability, not valuation. Reddit is the wrong instrument for validating *Gold Coast homeowner* intent specifically; first-party data (§5) is better for that.

---

## 4. The qualifier space: what people type when they *can* express intent

Stream D harvested 1,624 usable suggestions (772 requests, zero blocking).

**A. Valuation (432) — dominant, and it splits four ways:**
1. The plain number.
2. **A trust hedge** — `actually worth`, `really worth`, `fair market value`. Direct linguistic evidence of distrust; converges exactly with §3.
3. **A named institution** — `domain`, `corelogic`/`cotality`, `westpac`, `commbank`, `anz`. The most Australia-distinctive pattern found, and further evidence that the job is *reconciling competing sources*.
4. Access route — `calculator`, `free`, `by address`.

**B. Sale history (144).** `what did my neighbour ` returned only **two** suggestions in the entire sweep — both exactly on-intent: *"what did my neighbours house sell for"*, *"what did my neighbour pay for their house"*. Also `sold price withheld`, a distinctly Australian pain point. ⚠️ `sold price` is a **British** idiom (Land Registry) and is the most UK-contaminated seed — discount it.

**G. Risk / hazard / physical facts (71) — the under-appreciated cluster.** `is my house ` is almost *entirely non-valuation*: flood zone, bushfire, heritage listed, asbestos, brick veneer, solar suitability, orientation, NBN.

**This is independently and emphatically corroborated in our own stored corpus.** Verified directly during this synthesis:

| Suggestion | Persistence |
|---|---|
| **`does burleigh waters flood`** | **546** |
| `gold coast property market forecast` | 219 |
| `robina median house price` | 200 |
| `burleigh waters median house price` | 199 |

`does burleigh waters flood` is the **single most persistent suggestion in the entire corpus, at 2.5× the next item** — and it is one of only two flood suggestions that exist (`does varsity lakes flood`, 44; Robina does not appear). It is also the only *question-form* entry near the top; everything above 140 is commercial/browse phrasing.

> **Design consequence #3:** for Burleigh Waters specifically, flood exposure may be a **larger** address-level question than price. We already hold `config/flood_context_burleigh_waters.md`. This also resolves an apparent contradiction with `EVIDENCE_consumer_voice.md` §4.5, which found *no consumer complaining that a listing omitted flood risk*: people don't complain to the portal — **they go to Google instead.** Absence of complaint was mistaken for absence of demand.
>
> ⚠️ Persistence is *not* search volume (see §7). Treat 546 as a strong signal that warrants direct measurement, not as a volume figure.

---

## 5. What our own visitors actually do

Stream C, PostHog, 2026-05-08 → 2026-08-06. Small-n throughout: whole site 2,277 pageviews / 1,467 people.

- **`/off-market/:slug` has exactly one entrance: 93.6% Google, 6.4% direct, 0% internal referral, 0% Facebook.** It lives or dies on the bare-address SERP, which makes §1–2 directly load-bearing.
- It is only **17 days old** (314 pv / 266 people since 2026-07-20) yet already runs ~6× the daily rate of `/property/:id`.
- **Only 13.9% of off-market visitors click anything at all**; **87.5% of sessions are a single pageview.**
- **47–57% of deck sessions never advance past the first card.**
- **The two cards that hold attention are buried.** Median dwell: cards 1–5 skimmed at 1.5–2.3s; `buyer` **9.0s** and `valuation` **11.7s** — at positions **6 and 7, reached by only ~15% of sessions.**
- Most-clicked copy on the page: **"See what it may be worth"** (9 clicks / 8 people).
- Time-to-first-scroll: property 7s, off-market 10s — vs articles 24s and market-metrics 52s. Address pages get scanned 3–5× sooner.

> **Design consequence #4:** the deck's information architecture is inverted. The only proven-engaging content sits behind five cards that half the audience never advances past.

**⚠️ Correction to a sibling document.** `EVIDENCE_first_party_fields_data.md` §2 states the only on-page clicks were value questions ("What is X worth in 2026?", "Is X overpriced?") and calls this "the clearest revealed-preference signal we have." It is **17 clicks from exactly 3 people**, one session each; site navigation out-clicks the entire FAQ block. The *direction* survives — "See what it may be worth" is the top-clicked copy — but that doc overstates its weight. That doc's "2 second median time-to-first-scroll" also re-measures here at 7s (property) / 10s (off-market).

**One concrete defect, not a finding.** On 2026-07-30 a visitor spent three sessions and ~50 keystrokes cycling 15+ spellings — `120 Gleneages`, `120 leneages`, `120 Gleneasgle`, `Robion`, `Robin` — trying to reach **120 Glen Eagles Drive, Robina**. They never tried the two-word form; no result ever returned. Our address matching tolerates neither spacing nor typos, and a visitor who tried three times still failed. ~⅓ of typed addresses are outside our three suburbs. (See memory `address_search_whitespace_matching`.)

---

## 6. Where the streams agree — and where they don't

### 6.1 Convergent (high confidence — 3+ independent sources)
1. **The job is adjudication, not another number.** Reddit's 84%-spread artefact (§3) + autocomplete's trust-hedge and named-institution patterns (§4) + PropertyChat's identical-units evidence.
2. **Price is not the primary stated question, and is already commoditised.** SERP ranks price 5th of 6; **all 12 SERPs show a dollar figure before any click**, with automated estimates on **4/4 off-market SERPs** (property.com.au $1,836,000; CoreLogic $1,800,000–$2,000,000; Domain $2.45M). Leading with a valuation number enters a race we cannot win — and Rule 5 forbids the single-figure headline anyway. Both point the same way.
3. **Specific verifiable facts outrank generic marketing.** `fieldsestate.com.au` ranked **#3 on an off-market SERP, above Domain at #4**, on the snippet *"Last recorded sale. $175,000. Oct 1990. Held for 35.7 yrs"* — while our for-sale page ranked #6 on boilerplate *"Property report with valuation, comparable sales, and market intelligence."*

### 6.2 Contradictory — resolved
**"Owner" / "who owns this address" is NOT a real job**, despite Google listing `owner` 4× in People-also-search-for. Two independent sources kill it:
- Autocomplete `who owns ` → 260 suggestions, **all corporate** (Coles, Bunnings, Optus). Zero residential.
- Reddit → *"what did the current owner pay"* returns **zero** relevant hits in 5,685 posts. No nosiness framing anywhere.

**Resolution:** the `+owner` refinement is Google's generic entity template, not evidence of demand. **Do not build an ownership/occupancy surface on it.**

### 6.3 Contradictory — unresolved, flagged as hypothesis
**Sale history earns rankings and clicks while nobody says they want it.** Google ranks `history` 4× (§2) and our history-fact snippet ranked #3 (§6.1.3) — yet Reddit shows zero stated demand for what the current owner paid (§6.2).

**Working hypothesis:** the fact performs because it is **specific, verifiable and unique to that address** — properties that make it a good *ranking* and *credibility* asset — not because sale history is the job. If true, the design lesson is "lead with a hard, checkable, address-specific fact", and the fact happening to be history is incidental. **This is a hypothesis, not a finding.** It is testable and should be tested before the redesign commits to it.

---

## 7. Evidence quality — what to distrust

- **`search_paa_questions` (37,350 docs) is not usable as frequency data.** It contains only **1,011 unique questions** (36.9× inflation): 522 appear exactly 50 times against exactly 50 distinct collection dates, so the count is a **re-collection counter, not popularity**. `depth` is `'0'` on 100% of docs (the recursive crawl never ran) and `prefix` disagrees with the question 35% of the time. Strictly usable AU property-value intent: **7.8%**. Do not quote frequencies from it.
- **`search_suggestions` (17,841) is materially better** — 60.3% AU-marked, 6.4% foreign, ~31% property-value relevant — but has the same seeds×days artefact, so counts are **persistence, not demand**. Two structural blind spots exposed by the live harvest: **neighbour/comparison = 0** and **ownership = 0**, because no seed ever pointed at them.
- **`gl=au` barely works.** A controlled test showed `gl=au&hl=en-AU&cr=countryAU` returns results identical to passing no `gl` at all. Stream D reports AU-marked fractions rather than claiming an "Australian" harvest.
- **`search_reddit_posts` has two traps:** the `date` field is the *ingest* date, not the post date (20% of the corpus is a 2012–2025 backfill misdated to March 2026), and `selftext` truncates at 500 chars. Stream B re-verified all 62 cited posts against source.
- **Reddit RSS rate-limited at 58%** (29 of 50 requests HTTP 429); r/AusFinance and r/AusRenovation feeds were entirely unavailable, and 5 search queries were lost — including `land valuation notice`, which is why the rates-notice negative finding is the weakest one.
- **All first-party off-market rates rest on 17 days** and n=266 people.
- **n=12 SERPs** supports the 82/78/40 relevance contrast but **not** precise modifier percentages.

---

## 8. What this means for the V4 off-market page

Ordered by evidence strength.

1. **Answer before being asked; no menu, no tabs.** (§1, §5 — the `offmarket_menu_*` probe fired 9 times total.)
2. **Front-load `valuation` and `buyer`.** They are the only cards that hold attention (11.7s / 9.0s) and they sit where ~85% of sessions never reach. (§5)
3. **Card 0 must stand alone as a complete answer.** 47–57% never advance. Treat everything after it as optional depth.
4. **Lead with a hard, address-specific, checkable fact — not a valuation figure and not marketing copy.** This is what already earned us #3 above Domain. (§6.1.3)
5. **Do not headline a single valuation number.** Commoditised before the click, contrary to the adjudication job, and forbidden by Rule 5. Show the *reconciliation* instead — why our range is more credible — which is the unmet job. (§3, §6.1)
6. **Add flood/overlay exposure for Burleigh Waters.** Plausibly a bigger address-level question than price there; we already hold the context file. Must follow Rule 5 (data + source + limitations, no advice). (§4)
7. **Design the no-range state as the primary state.** A comparable range exists on only **7% of sold addresses** (221/2,947, `EVIDENCE_first_party_fields_data.md` §4). Any layout assuming a range is blank on 93% of sold pages.
8. **The off-market SERP is the winnable one.** Only **40%** of off-market results are about the address typed (vs 82% sold / 78% for-sale); 43% drift to neighbours and 18% are unrelated (including wrong-state matches). This is where relevance beats domain authority.
9. **Fix address search** — whitespace/typo tolerance, and a non-dead-end for out-of-area addresses (~⅓ of input). (§5)
10. **Do not build an ownership or occupancy surface.** (§6.2)

**Two things to fix so the next iteration can be measured at all:**
- **Samantha persists nothing.** The only record of a chat turn is a Telegram message to Will, which the Bot API cannot read back — so there are **zero real visitor questions to mine**. The single richest possible source of address-level intent is currently being discarded at runtime.
- **PostHog holds zero break-glass events** since launch despite `BreakGlass.tsx` calling `phCapture`. The feature shipped specifically to learn whether anyone engages, and cannot currently tell us.

---

## 9. Open questions this research could not settle

1. **Are they owners, neighbours or buyers?** Still inferred, never confirmed. One post-view question would settle it and is the highest-value cheap instrument available.
2. **Is the exit satisfaction or failure?** 13.9% click-through and 87.5% single-pageview have identical telemetry for "found it and left happy" and "didn't find it".
3. **Is the arm gap real?** `discovery`/`recognition` 71.7% first-card advance (n=60) vs `ladder_dark`/`hero` 32.9% (n=82) — but the arms ran over different periods. Hypothesis, not result.
4. **Does §6.3 hold** — is it the *specificity* of the fact that works, or history itself?
5. **Does showing a range beat a point estimate** for trust and onward action? Never A/B tested.
6. **Actual search volume for `does burleigh waters flood`** — persistence is not volume; measure it directly.
