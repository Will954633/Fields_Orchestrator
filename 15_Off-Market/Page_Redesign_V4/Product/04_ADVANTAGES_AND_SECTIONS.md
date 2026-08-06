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
| **A6** | **Nobody is paying to change what you see, and nothing here becomes a lead.** REA reports owner engagement to shareholders as *"valuable seller leads delivered to our customers"*; Pro-tier agents get **36% more** | **STRUCTURAL** | `structural_conflict` C3 [P] | §6 claim step |
| **A7** | **Wrong facts can be corrected, and you see the number move.** Nobody offers this — *"over 20 emails and they wouldn't change it"* | **STRUCTURAL** (unbuilt) | `consumer_voice` §3.9 | §6 claim step |
| **A8** | **An estimate that's dated and re-anchored.** Portal estimates carry no computed-on date; *"Domain estimates and REA always lag (3-4 months)"* | **PENDING** | `ADDENDUM_propertychat` §1; our own lag analysis | §2 / §5 |
| **A9** | Address-level flood and hazard context | **PENDING** | `does burleigh waters flood` = most persistent suggestion in our corpus, 546, 2.5× the next | §5 |

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
| **6** | **Claim it** | Correction + control + an explicit, operationally true "nobody calls unless you ask" | That claiming is the price of entry — it never is | A6, A7 |

**The spine, in one line:** §2 earns the right to §3. Dispersion is *why how a number was
made matters*; the working is *what we do about it*. Without §2, §3 is a boast; with it,
§3 is the obvious response.

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
4. **Make "nobody calls unless you ask" an operational rule** — otherwise A6 and §6 are
   unsayable.
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
