# Working list — advantages, user needs, and a section framework for `/off-market/:slug`

**Status:** Working document. Companion to `01_USER_JOBS_AND_GAPS.md`.
**Compiled:** 2026-08-06 · everything below is traceable to `../Research/` or to a measured run in `../Prototypes/`.

---

## 0. The constraint that shapes everything — it is LATENCY, not coverage

> ⚠ **Corrected 2026-08-06.** An earlier version of this section said we hold a valuation
> for only 0.3–0.7% of off-market homes and that a range-led page would be "blank on 99.4%
> of addresses". **Both halves were wrong.** The 0.3–0.7% is a *cache-hit rate*, not a
> capability limit — **valuations are built on demand** (`fields-valuation-api` +
> `fields-valuation-poller`, both running). And the follow-up attribute check that appeared
> to show ~0% coverage was a query bug: fields were projected away that the resolvers read.
> Measured on full documents, coverage is good.

**Attribute coverage — can we value it at all?** (400-doc sample per suburb, off-market houses)

| Suburb | Land size | Floor area | Both | + beds & baths |
|---|---|---|---|---|
| Robina | 99.0% | 83.8% | **83.5%** | 52.5% |
| Varsity Lakes | 98.8% | 65.2% | **65.2%** | 70.0% |
| Burleigh Waters | 100.0% | 93.8% | **93.8%** | 65.2% |

**Most off-market homes can be valued.** Beds/baths is the thinner field (52–70%) and is
what the agent-method comparison in §2 would need; land and floor area, which the
adjustment engine needs, are near-universal.

**The real constraint is how long it takes.** All 10 on-demand requests ever made:

| | Range | Typical |
|---|---|---|
| Queue wait | 3–31s (one 30-hour outlier, poller down) | ~15s |
| Compute | 23–98s | ~50s |
| **End to end** | | **~30–90 seconds** |

Historical success 6/10 — but the four failures were all March 2026 and the four most
recent all completed. **n=10 total. The path works and is essentially unexercised.**

**So the design question is not "do we have a number", it is "will they wait a minute".**
And the behavioural answer is no: median final dwell **6.3s**, 87.5% single-pageview,
47–57% never advance past the first card.

**The resolution, and it is a happy one: fire the build on page load, not on a press.**
§0 and §2 then *are* the loading state — and §2 ("why the numbers you've seen disagree")
is both the content the visitor needs to be shown before a range means anything, and
roughly a minute of reading. The narrative requirement and the technical requirement
coincide. Precedent exists: the V3 deck already starts a mini-site build on the neon press
(`[V3-BUILD-STARTS-ON-PRESS]`), and `property_build_requests` is an async build-and-poll
queue already in production.

**What this does still require:**
- A defined state for the 6–35% with insufficient attributes, and for a build that fails
  or overruns. That state is a minority, not the majority — but it is not rare.
- Load testing. Ten requests in the service's lifetime is not evidence it survives traffic,
  and a page that fires a ~50s compute on every arrival is a different load profile
  entirely.

---

## 1. Advantage register — what we can actually claim

Graded: **EARNED** = measured, defensible today · **STRUCTURAL** = true by construction,
can't be falsified by a backtest · **PENDING** = real but blocked on a fix.

| # | Advantage | Grade | The evidence | Where it belongs |
|---|---|---|---|---|
| **A1** | **The same inputs always give the same answer.** An agent's three-comp valuation is indeterminate: median spread between the best and worst defensible answer for one home is **32.9% of its value — $469,000** — exceeding 20% on **77%** of homes | **EARNED** | `RESULT_dispersion_512.md` §2, n=512 | §3 "why numbers disagree" |
| **A2** | **The right answer is usually already in the comp set — the method just can't find it.** A near-perfect draw (<2% error) exists on **73.6%** of homes; the worst available draw is >20% wrong on **73.4%** | **EARNED** | same | §3 — this is the sharpest single line we own |
| **A3** | **You can see every sale we used and what each was adjusted for, in dollars.** 12 Kilburn St $1,300,000 → $1,521,873: one more bedroom +$113,110, 53 sqm more floor +$95,034, comparable better renovated −$48,016 | **STRUCTURAL** | `Adjusted-Comparables-Evidence.md`; Moorabbin run | §4 "the working" |
| **A4** | **Adjusting narrows the range ~40%**, and narrows it at all **nine times in ten** (median 38.8%, 91.0% narrow, median $351,000 → $204,805) | **EARNED** | `RESULT_dispersion_512.md` §3b, n=512 | §4 |
| **A5** | **We publish our error rate.** No Australian consumer portal publishes one; Zillow and Redfin both do | **STRUCTURAL** | `international_comparison` §6.5 | §5 "what we get wrong" |
| **A6** | **Nobody is paying to change what you see, and your interest in your own home is not sold on.** REA reports owner engagement to shareholders as *"valuable seller leads delivered to our customers"*; Pro-tier agents get **36% more**. Fields is the agency, so there is no third party being handed the address | **STRUCTURAL** | `structural_conflict` C3 [P] | §9 |
| | ⚠ **Revised 2026-08-06.** Previously read *"nothing here becomes a lead"*. The page **is** a lead surface and the business depends on it; outreach is physical mail to the property, not cold calling. **No promise about contact is made in either direction.** The differentiator was never *"we won't contact you"* — it is *"we don't sell you to whoever pays most"*, which survives the model intact | | | |
| **A7** | **Wrong facts can be corrected, and you see the number move.** Nobody offers this — *"over 20 emails and they wouldn't change it"* | **STRUCTURAL** (unbuilt) | `consumer_voice` §3.9 | §6 claim step |
| **A8** | **An estimate that's dated and re-anchored.** Portal estimates carry no computed-on date; *"Domain estimates and REA always lag (3-4 months)"* | **PENDING** | `ADDENDUM_propertychat` §1; our own lag analysis | §2 / §5 |
| **A9** | Address-level flood and hazard context | **PENDING** | `does burleigh waters flood` = most persistent suggestion in our corpus, 546, 2.5× the next | §5 |
| **A10** | **We price renovation and condition explicitly, in dollars.** On Moorabbin: renovation level 4 vs 2 = **−$96,032**; interior condition 8 vs 7 = **−$95,500**. That is a direct answer to *"does this work add value?"* — the Reno Payback persona (~21 posts) and `house valuation after renovation` | **STRUCTURAL** | Moorabbin adjustment lines; `research_intent/D` cat A, `B` P4 | §4, and a natural return-visit hook |
| **A11** | **No hindsight.** Comparables are drawn only from sales dated *before* the subject, and the subject is excluded by `_id`. Nobody states this, and it is the difference between a forecast and a recollection — the exact flaw that invalidated our own Domain benchmark | **STRUCTURAL** | `valuation_backtest.sold_before_subject()`; fix-history `[DOMAIN-BENCHMARK-CONTAMINATED]` | §4 / §5 |
| **A12** | **The selection is shown, not just the selection's output** — "8 included of 32 assessed". Evidence of work, and the honest form of "we looked at everything" | **STRUCTURAL** | backtest returns `included_points` + `all_points` | §3 |

### ⚠ L — limitations that bound the claims above

| # | Limitation | Bounds |
|---|---|---|
| **L1** | **Our comparable pool is Domain-derived and inherits its under-capture.** Sold sources in the pool are `domain_sold_listings_backfill`, `selenium_sold_scraper_12months`, `curlffi_suburb_scraper`, `parallel_suburb_scraper` — all Domain-origin, deduped. Domain captures roughly **53–66%** of actual sales (`data_source_undercapture_reset`). The onthehouse union applies to **medians**, not to the comp pool | **Bounds A2 directly.** "The right answer is usually already in the comp set" is measured *within our pool*. Where the true best comparable was never captured, neither method could have found it. Do not claim comprehensiveness |
| **L2** | Time adjustment is computed but **not composed** with feature adjustments | Bounds A4 — the 38.8% median narrowing is feature-adjustment only. Composing time in would move it, direction unknown |
| **L3** | **No radius filter exists** — distance is only a weight, decaying to zero at 5 km. Comps have reached **2.57 km** while copy said "near your street" | Bounds A3 and any "nearby" language |

## 1b. Kill list — do not build a section on any of these

| Claim | Why it's dead |
|---|---|
| More accurate than an agent appraisal | Dead heat — a random agent triple beats us **exactly 50.0%** of the time |
| More accurate than a portal | No valid measurement exists; our benchmark was contaminated (91.8% captured on/after the sale) |
| Our range is narrower than an agent's | False — three comps always span less than eight |
| Any confidence label | `high` 56.0% vs `medium` 57.5% — non-discriminating |
| "Domain systematically overvalues" | Artefact of scrape lag (r = −0.955 by suburb). Live in a published article; correction pending |
| "We found your home" / any located-you framing | Zero positive reactions to unsolicited approaches across 5,685 Reddit posts |
| Who owns / occupies the home | Zero demand evidence; direct privacy trigger |
| A single valuation figure as what the home is worth | Rule 5 |

---

## 2. User needs → what answers them

Ordered by evidence strength. "Validated" marks needs with independent demand signal.

| Need, in their words | Evidence | What answers it | Advantage |
|---|---|---|---|
| **"Six numbers and no way to choose."** *"When brokers ask me what my house is worth, I have no idea, given the range of estimates"* — 84% spread on one home | Reddit; PropertyChat identical units $137k apart | Show *why* numbers disagree, then show ours with its working | A1, A2, A3 |
| **"How accurate are these estimates really?"** ✅ **Validated** — our own article on this outperformed on Facebook | FB performance; autocomplete trust hedges `actually worth`, `really worth` | Publish our error rate and its limits | A5, A8 |
| **"No explanation of how they got there."** The opening line of that same article, and the part that resonated | Article; *"zero transparency about how they're calculated"* | The comp set, itemised | A3, A4 |
| **"It moved $100k and nobody will tell me why."** *"dropped 40k increased 50k and dropped 40k"* | `consumer_voice` §3.3 | Date the estimate; explain movement | A8 |
| **"It's wrong about my house and there's no way to fix it."** *"still shows as vacant land"* | `consumer_voice` §3.9 | Correction that visibly changes the working | A7 |
| **"Will an agent call me? Am I declaring I'm selling?"** | `GTP_market_analysis` L1617; 62-comment PII thread | Answer first, ask nothing, never contact | A6 |
| **"Is my home exposed?"** flood, bushfire, heritage, asbestos | `does burleigh waters flood` 546 persistence | Address-level hazard with source + limits | A9 |
| **"What could I actually walk away with?"** Equity Checker ~115 posts | Reddit personas | ⚠ **Out of scope for launch** — collides with the privacy line (derived financial inference) | — |

### Added by the 2026-08-06 completeness audit — valuation needs the framework was missing

| Need, in their words | Evidence | What answers it | Advantage | Status |
|---|---|---|---|---|
| **"How does a valuation actually work? What do they check?"** | `research_intent/D` cat K = **85** suggestions; `house valuation how does it work`, `house valuation what do they check` | A plain explainer of the method **as a topic**, separate from this home's working. People want to understand the process before they trust an output of it | A3, A11, A12 | **GAP — no section owns this.** Candidate: fold into §3 as a short "how this was done" preamble |
| **"Why does the bank's number differ from the market number?"** | **Equity Checker is the single largest persona (~115)**; the named-institution pattern (`westpac`, `commbank`, `anz`, `corelogic`) is *"the most AU-distinctive pattern found"* | Explain that a lender AVM answers a different question (security for a loan) than a market appraisal. **No derived financial inference needed** — this is a category explainer, not their equity | A1, A11 | **GAP.** Answers the biggest persona without crossing the privacy line that put J7 out of scope |
| **"Does this renovation add value?"** | Reno Payback ~21; `house valuation after renovation` | We already price renovation level and interior condition as explicit dollar lines | **A10** | **GAP — and it is a strong return-visit hook** |
| **"I need a valuation *for* something"** — probate, divorce, separation, CGT, capital gains, aged pension, mortgage | `research_intent/D` cat D = 33; *"Life-event triggers are explicit"* | State plainly what this is and is not usable for. Links to `statutory_cma_layer` | — | **GAP.** Also a liability boundary, not just a content gap |
| **"Which estimate site is least bad?"** | Tool Shopper ~21 | Partly answered by §2 (dispersion), but never addressed directly | A1, A5 | Partial |
| **"Is an online estimate even a valuation?"** | CHOICE / Vince Mangioni (UTS): *"an online estimate isn't a valuation — rather, they're price estimates and they provide indicative averages"* | Name the difference between an AVM, an agent appraisal, and a certified valuation. Protects us and answers a real confusion | A5 | **GAP — and the safest possible framing for our own output** |
| **"How current is this evidence?"** | `Rique`: *"Domain estimates and REA always lag (3-4 months)"*; our own comps averaged **7.6 months** old | Show comp dates and the set's median age. Cheap, and it is exactly the disclosure A8 is about | A8, L2 | **GAP — trivially available, we already hold the dates** |

---

## 3. Section framework

Numbered by the order the visitor meets them. **Each section must survive being the last
thing they see** — 47–57% never advance past the first, 87.5% are single-pageview.

| § | Section | Its one job | Must not assume | Advantage |
|---|---|---|---|---|
| **0** | **This is your home, and here is a hard fact about it** | Resolve the entity and prove we know something specific and checkable. *"Last recorded sale $175,000, Oct 1990. Held 35.7 years."* This exact snippet ranked us **#3, above Domain**; our boilerplate page ranked #6 | A valuation. Any "we found you" framing | — |
| **1** | **What we can say about its value** | The range — built on demand, arriving while they read §2. Honest substitute where attributes are too thin or the build fails | That it is ready instantly (~30–90s), or that attributes exist (6–35% too thin) | A3 |
| **2** | **Why the numbers you've seen disagree** | The dispersion story. Three comparable sales can justify valuations **a third of a home's value apart**. This is the "why it matters" that earns everything after it | That they've had an agent appraisal — many haven't | A1, A2 |
| **3** | **The sales we used, and what we changed** | Traceability made visible. Every comp, every adjustment, in dollars | That anyone reads it — see §4 below | A3, A4 |
| **4** | **What we get wrong** | Publish the error rate and the limits. Pre-empts the attack and is the thing no AU portal does | A confidence label | A5 |
| **5** | **What a model can't see about this address** | Flood/hazard, position, the address-specific facts. Rule 5: data, source, limitation, no advice | Council data exists everywhere — it doesn't | A9 |
| **6** | **Claim it** | Correction + control + "we don't sell you to anyone" (no contact promise — see the decision note) | That claiming is the price of entry — it never is | A6, A7 |

**The spine, in one line:** §2 earns the right to §3. Dispersion is *why how a number was
made matters*; the working is *what we do about it*. Without §2, §3 is a boast; with it,
§3 is the obvious response.

---

## 3b. What comes next, after the valuation layer

### ⚠ First, a rule about our own data

**Deck dwell and funnel figures cannot be used as evidence of topic preference.** They are
confounded three ways and `research_intent/C` §limitation 6 says so itself:

1. **Position is ours, not theirs.** The card order was chosen by us. Content and position
   cannot be separated.
2. **Survivorship.** `buyer` (9.0s) and `valuation` (11.7s) sit at positions 6–8, reached by
   ~15% of sessions. The dwell is measured on the most engaged minority.
3. **Dwell is ambiguous** — long can mean dense or confusing as easily as interesting.

They remain valid for *"did this card get read at all"* and for comparing arms of the same
position. **They are not a ranking of what users want to know.** Any sequencing claim must
rest on evidence that never touched our page.

### Independent evidence only

| Topic | Autocomplete category (`D`) | Stored persistence | Google refinements (`A`, n=22) | Reddit personas (`B`) | Other |
|---|---|---|---|---|---|
| **Valuation** | **432 — dominant** | — | price 2 | Comparable Hunter ~53, Agent-Number Sceptic ~39, AVM Sceptic ~16 | trust hedges `actually/really worth` |
| **How valuation works / how accurate** | 85 (tool/mechanics) | — | — | Tool Shopper ~21 | ✅ **our own FB article on this outperformed** |
| **Market direction** | 36 | **~670** — forecast 219, next-5-years 183, crash prediction 147, crash 121 | — | — | — |
| **Risk / hazard** | 71 | **546** — `does burleigh waters flood`, 2.5× the next item | — | Flood/Overlay ~11 | — |
| **Sale history** | 144 | — | history 4 | ⚠ **zero** stated demand | ✅ our history snippet ranked **#3, above Domain** |
| **Equity / lender numbers** | 25 | — | — | **Equity Checker ~115 — largest persona** | named-institution pattern |
| **Buyer / who competes** | ❌ **not a category** | ❌ none | ❌ none | ❌ **not a persona** | only the discredited dwell figure |

### The order the independent evidence supports

1. **How the number was made, and how accurate it is.** Still the valuation layer, not a new
   one — 85 tool/mechanics suggestions, the Tool Shopper persona, the trust hedges, and the
   one demand signal we have actually validated in market (the Facebook article).
2. **What's changed, and where this market is heading.** The largest adjacent topic by
   persistence (~670). ⚠ Rule 5: report indicators, never forecast.
3. **Is this home exposed** — flood and hazard, 546 persistence plus 71 suggestions.
4. **Sale history** — strong *ranking* and *credibility* value, weak stated demand. Per
   `own_address_search_intent` §6.3 the working hypothesis is that it performs because it is
   specific and checkable, not because history is the job. Use it as the §0 hard fact rather
   than as a section.
5. **Then the selling path** — GPT: *"The selling journey is not the initial product. It is
   the deeper path that becomes relevant once Fields has answered the address search better
   than anyone else."*

### ⚠ The buyer / competition layer has no independent support

It is absent from the autocomplete categories, the stored corpus, Google's refinements and
the Reddit personas. **The only evidence for it was the deck dwell figure, which is
discredited above.** It may still be good product — it is differentiating and it feeds the
seller path — but **it is a Fields-invented interest, not a user-expressed one**, and it must
not be described as research-backed. If it stays, it should be positioned as a test with a
stated hypothesis, not as an answer to a known want.

### One correction GPT gets right and this document had wrong

**Privacy belongs on the first screen.** GPT's opening layer includes *"This is private and
no one calls unless asked"*. §6 in the framework below puts it in the claim step — where
87.5% of visitors never arrive. The anxiety is present at arrival (*"Am I declaring that I am
selling?"*), so reassurance at the end reassures nobody. **Move it to §0.**

⚠ GPT's first screen also wants the value range immediately, which collides with the 30–90s
build (§0 of this document). Either pre-warm, or the first screen carries the hard fact plus
the privacy line and the range lands a layer later. Decide deliberately.

---

## 4. Design rules the behaviour data imposes

1. **Answer without being asked.** No menu, no tabs. `offmarket_menu_*` has fired **9 times
   total**, and Google never offers a qualifier — 89.5% of address autocompletes return
   empty, so the visitor has no practice declaring intent.
2. **§0 must stand alone as a complete answer.** 47–57% never advance.
3. **Front-load value.** `valuation` (11.7s dwell) and `buyer` (9.0s) are the only cards
   anyone stops on, and they currently sit at positions 6 and 7 where ~15% arrive. Cards
   1–5 are skimmed at 1.5–2.3s.
4. **Transparency is a signal, not content.** 13.9% click anything. The *visible existence*
   of the working, one click away, does the work — a step-by-step wall gets scrolled past
   by exactly the people it was written for.
5. **Lead with a hard checkable fact, never marketing copy.** Evidenced by our own SERP
   positions.
6. **No delight.** *"Every emotional reaction to a value in the corpus is negative or
   anxious… Zero delight."* The state to design for is **anxiety about being wrong**.

---

## 5. Dependencies, in build order

1. **Load-test the on-demand valuation path** — it has served 10 requests in its lifetime;
   the page would fire a ~50s compute on every arrival. Also decide pre-warm vs on-load.
2. **Fix calibration** — 56.8% range-hit, labels non-discriminating. Blocks any stated range
   or confidence in §1/§4.
3. **Persist `adjusted_price` + component adjustments** — §3 cannot render without it.
   Currently a stated release blocker.
4. ~~Make "nobody calls unless you ask" an operational rule~~ — **withdrawn 2026-08-06.** ⚠ **DECISION 2026-08-06 (Will): the page makes NO promise about contact, in either direction.** The page is a lead surface and the business depends on it. A promise the model cannot keep is worse than no promise — and `offmarket-intent-alert.mjs` already fires on reaching the end of a deck. Outreach is **physical mail to the property address**, not cold calling. What replaces the promise is stronger and stays true: **"we don't sell you to whoever pays most"** — REA books owner engagement as a *"seller lead delivered to our customers"* with Pro-tier agents getting 36% more, and Fields is the agency, so there is no third party being handed the address.
5. **Correct the Domain accuracy article** — currently live, and §4's credibility depends on
   us not having a broken accuracy claim published elsewhere.
6. **Fix address search** — no whitespace/typo tolerance; ~⅓ of typed addresses are outside
   coverage.

---

## 6. Open questions

- Is §2 (dispersion) too adversarial for a page an owner arrives at cold? It criticises a
  method Fields itself is licensed to practise. Framing as *"here's why we don't do it that
  way"* is honest; framing it as *"agents are unreliable"* is not, and Will is an agent.
- Does §1's no-range state have a genuinely non-embarrassing form? It is the majority state
  and nothing has been designed for it.
- Does the corrected accuracy story (estimates are undated, not systematically wrong) carry
  the same Facebook demand the original article did?
