# `/off-market/:slug` — the flow

**Status:** Draft flow for V4. **Compiled:** 2026-08-06.
**Reads with:** `04_ADVANTAGES_AND_SECTIONS.md` (advantages A1–A12, limitations L1–L3, kill list) and `03_CLAIMS_REGISTER.md` (what may be said publicly).

**The job, in one sentence** — the best formulation in the research:

> *"Show me what my home may be worth, explain why, and help me understand what that could mean for my options — privately, without assuming I am ready to sell."*

**How they arrive.** One entrance: **93.6% Google, 0% internal referral.** A bare address with no qualifier — because Google never offers one (89.5% of address autocompletes return empty, zero semantic qualifiers). **The page must answer without being asked.** No menu, no tabs.

---

## Coverage — which sections can always run

The hardest design problem is what the page does when per-address data is thin. It resolves
better than expected: **three sections are universal and never fail.**

| § | Section | Depends on | Coverage |
|---|---|---|---|
| 0 | This is your home | address + last sale | ~100% / **70–91%** |
| 1 | What it may be worth | attributes + on-demand build | **65–94%**, ~30–90s |
| **2** | **Why the numbers disagree** | **nothing per-address** | **100%** ✅ |
| 3 | The sales we used | §1 | follows §1 |
| **4** | **How this was made, how wrong it can be** | **nothing per-address** | **100%** ✅ |
| 5 | Why a lender's number differs | §1 + category explainer | follows §1 |
| **6** | **What's changed in this market** | suburb-level | **100%** ✅ |
| 7 | Is this home exposed | council/hazard data | Burleigh Waters only |
| 8 | Claim it | nothing | 100% |

**So the page always has substance.** §2, §4 and §6 carry it when the address is thin.

---

# The flow

## §0 — This is your home
**First screen. Must stand alone: 47–57% never advance past it.**

Four things, in this order:

1. **The address, confirmed.** Not *"we found your home"* — see below.
2. **One hard, checkable, address-specific fact.** *"Last recorded sale $175,000, October 1990. Held 35.7 years."* This exact snippet ranked us **#3, above Domain at #4**; a boilerplate snippet on a comparable page ranked #6. Specific and checkable beats persuasive.
3. **What's coming** — one line, because the valuation is building behind this screen.
4. **"Nobody calls unless you ask."**

> ⚠ **Two hard rules here.**
> **Never "We found your home"** — currently shipped as card 0. Across 5,685 Reddit posts there is **not one positive reaction** to an unsolicited "we noticed your property" approach; there are three hostility artefacts, including a 62-comment thread asking *"are they allowed to grab our PII from public land records?"* The owner should feel they **arrived**, not that they were located.
> **The privacy line belongs here, not at the end.** The anxiety is present on arrival — *"Am I declaring that I am selling?"* Reassurance in the claim step reassures nobody: 87.5% of sessions are a single pageview. **This is only sayable if it is an operational rule, not copy.**

---

## §1 — What we can say it may be worth
**A range, never a single figure (Rule 5). Built on demand while they read §0 and §2.**

- The adjusted-comparables range, with the number of sales behind it.
- The **date it was computed** — portals never state one, and *"Domain estimates and REA always lag (3-4 months)"* (A8).
- Median age of the comparable set. Ours have averaged 7.6 months; we hold every date and never show it.

**No confidence label.** `high` 56.0% vs `medium` 57.5% range-hit — non-discriminating (C12).

**When it can't run** (attributes too thin, build fails or overruns): say so plainly and go
to §2, which needs nothing. Do not fake a number and do not apologise at length.

---

## §2 — Why the numbers you've seen disagree
**The pivot of the whole page, and it never fails.**

They have already seen three automated estimates before clicking — all four off-market SERPs
we captured carried them (property.com.au $1,836,000; propertyvalue.com.au $1,800,000–$2,000,000).
This section explains why those numbers, and any appraisal they've had, disagree.

The measured content (n=512 sold homes):

- **Three comparable sales can justify valuations a third of a home's value apart** — median spread **32.9%**, a median **$469,000** — and that spread exceeds 20% of the home's value on **77%** of properties.
- **A near-perfect comparable is usually already in the set.** A draw within 2% of the eventual sale price exists on **73.6%** of homes; the worst available draw is more than 20% wrong on **73.4%**. *The right answer is nearly always there. The method just can't tell you which one it is.*

**This earns everything after it.** Without §2, §3 is a boast; with it, §3 is the obvious response.

> ⚠ **Tone.** This criticises a *method*, never people — and Fields is a licensed agency that
> could use that method. Frame as *"here is why we don't do it that way."* Never *"agents are
> unreliable."* It also names nobody and uses only public sales data.
> ⚠ Do **not** pair this with any accuracy claim. Against the agent method we are a dead heat
> (a random three-comp draw beats us **exactly 50.0%** of the time). The claim is
> **determinacy**, not accuracy.

---

## §3 — The sales we used, and what we changed
**Traceability made visible. Its job is to be seen to exist, not to be read.**

- Every comparable, with its sale price and its adjusted price.
- Every adjustment as a dollar line: *one more bedroom +$113,110 · 53 sqm more floor area +$95,034 · comparable better renovated −$48,016*.
- **"8 included of 32 assessed"** (A12) — the honest form of "we looked at everything".
- **Adjusting narrows the range about 40%**, and narrows it at all **nine times in ten** (median 38.8%, n=512). Never quote the $610,000 → $274,000 example as typical — it is the 73rd percentile.

> ⚠ **Design.** Only 13.9% of visitors click anything; cards are skimmed at 1.5–2.3s. The
> *visible existence* of the working, one click away, does the persuading. A step-by-step wall
> gets scrolled past by exactly the people it was written for.
> ⚠ **Blocked:** `adjusted_price` and component adjustments are **not persisted** — a stated
> release blocker. This section cannot render until they are.
> ⚠ **L3:** no radius filter exists; comparables have reached 2.57 km. Do not write "near your
> street" unless the distance supports it — show the distance instead.

---

## §4 — How this was made, and how wrong it can be
**Universal. The only demand signal we have validated in market.**

Your own article on estimate accuracy outperformed on Facebook — that is real, tested
appetite for this exact topic. Plus 85 autocomplete suggestions for tool/mechanics
(`house valuation how does it work`, `what do they check`), the Tool Shopper persona (~21),
and the trust hedges (`actually worth`, `really worth`).

Content:

- **How the method works**, plainly. What a comparable is, why it gets adjusted.
- **No hindsight (A11)** — comparables are drawn only from sales *before* the subject; nobody states this, and it is the exact flaw that invalidated our own Domain benchmark.
- **Our error rate, published.** No Australian consumer portal publishes one; Zillow and Redfin both do.
- **What this is not** — *"an online estimate isn't a valuation — they're price estimates and they provide indicative averages"* (Vince Mangioni, UTS, via CHOICE). The distinction between an automated estimate, an agent appraisal and a certified valuation. This is the safest available framing of our own output **and** a liability boundary for the probate / divorce / CGT / aged-pension use cases (33 suggestions).

> ⚠ Pin one error-rate figure with its sample and date before publishing — 11.1% and 11.6%
> are both in circulation. Never frame as better than any portal (C1).

---

## §5 — Why a lender's number is different from this one
**Serves the largest persona in the research — on what it actually asks for.**

The **Equity Checker is the single largest Reddit persona (~115 posts)**. Read what they
actually say:

> *"Check the upper end value of your home on sites like domain and property. Call your bank
> and request an updated AVM. **Try to hit the maximum number the bank will accept**… you may
> have changed your LVR which may in turn allow you to negotiate better rates."*

> *"Anyone else had an experience where **the bank undervalued their property**? And not by
> just 1-3% but by a lot?… an apartment in our building — IDENTICAL to ours — sold for $100k
> more than our recent bank valuation."*

> *"Right now I'm pulling loan balances manually and using Domain estimates to get a rough
> equity figure… **how often are you actually updating your property valuations?**"*

Their job is **current and prospective**: get a defensible number, check it against what a
lender said, know how fresh it is. So this section is:

- **The upper bound of the range, stated plainly** — not buried. It is the number they came for.
- **The computed-on date**, answering *"how often are you actually updating"* (A8).
- **Why a lender's figure differs** — a bank AVM answers a different question (security against a loan, deliberately conservative) than a market appraisal. This is a **category explainer**, so it needs no information about their finances at all.

> ⚠ **The privacy boundary runs through here.** Their equity, loan balance or LVR is
> **derived financial inference — banned (C11)**. The one clear privacy violation in the whole
> corpus was exactly this: *"what absolutely floored me was they had even estimated **what we
> owe on it**."* We explain the *category difference*. We never compute their position.

### ⚠ On `CapitalGainChart.tsx` — built, and NOT justified by this persona

`CapitalGainChart.tsx` exists and is good work: a fan chart from purchase price to today's
low/high range, shaped by the suburb's real quarterly index growth, straight segments between
actual quarterly points because curve-fitting *"would imply false precision."* It is wired
into `OffMarketDeck` (the ladder), not the live `DiscoveryDeck`. Data coverage is fine —
`scraped_data.property_timeline`, **70.4% / 83.2% / 90.8%**.

**But it answers a retrospective question — "how much has my home grown since I bought it" —
and not one of the ~115 Equity Checker posts asks it.** They ask for a current number, a
check against a lender, and how fresh it is. An earlier draft of this document justified the
chart with this persona; that was reaching for a component because it was available rather
than because it was wanted.

**It is in the same category as the buyer/competition card: a Fields-invented interest with
no independent support.** The nearest evidence is sale history (144 autocomplete suggestions,
`history` 4× in Google refinements, our #3-above-Domain snippet) — but per
`own_address_search_intent` §6.3 the working hypothesis is that history performs because it
is *specific and checkable*, not because history is the job. Extending a single last-sale fact
into a growth narrative is a further step with nothing behind it.

**Recommendation:** keep the last-sale fact in §0 where it is evidenced. Do not ship the chart
as a section in V4 on this rationale. If it ships, ship it as a stated test — like the buyer
card — not as an answer to a known want.

---

## §6 — What's changed, and where this market is heading
**Universal, and the largest adjacent topic by a distance.**

Persistence in our stored corpus: `gold coast property market forecast` **219**,
`forecast for next 5 years` **183**, `crash prediction` **147**, `crash` **121** — roughly
**670 combined**, rivalling flood.

This is also the "living answer" — the reason to come back. *"The static answer is valuable;
the living answer is defensible."* And it directly answers the loudest volatility grievance:
*"dropped 40k increased 50k and dropped 40k, is this even possible."*

> ⚠ **Rule 5 binds hardest here.** Report indicators. Use conditional language. **Never** a
> prediction, never "prices will fall", never advice. The demand is for a forecast; what we
> may supply is evidence. Say which is which.

---

## §7 — Is this home exposed
`does burleigh waters flood` is the **most persistent suggestion in our entire corpus at 546
— 2.5× the next item** — and the only question-form entry near the top. Plus 71 hazard
suggestions (`is my house in a flood zone`, bushfire, heritage, asbestos).

This also resolves an apparent contradiction: `consumer_voice` §4.5 found *no* consumer
complaining that a listing omitted flood risk. They don't complain to the portal — **they go
to Google instead.**

Rule 5: data, source, limitation. No advice, no reassurance. Burleigh Waters only for now
(`config/flood_context_burleigh_waters.md`).

> ⚠ Precedent worth respecting: Trulia built crime layers, showcased them at the White House
> in 2012, and withdrew them in early 2022 on fairness grounds. Flood is defensible on
> measurement grounds where crime is not — but the source and its limits go on the page.

---

## §8 — Claim it
Correction, control, and nothing extracted.

- **Fix what's wrong and watch the number move (A7).** Nobody offers this — *"over 20 emails and they wouldn't change it"*; a seller with an undervalued estimate was told to go hire an agent.
- **Nothing here becomes a lead (A6).** REA reports owner engagement to shareholders as *"valuable seller leads delivered to our customers"*, with Pro-tier agents receiving **36% more**. Claiming with us contacts no one. Defensible entirely from their own filings.
- **Claiming is never the price of entry.** The page has already answered by this point.

---

## → The deeper path
Only once the address question is genuinely answered:

> *"The selling journey is not the initial product. It is the deeper path that becomes
> relevant once Fields has answered the address search better than anyone else."*

Hands off to the mini-site V2 sessions. **The Hub is the utility; the mini-site is the
on-ramp; the handoff is here** — which also settles the utility-vs-seller-funnel question.

---

## What is built, and what blocks it

| | State |
|---|---|
| §0 hard fact | Built — already ranking |
| §1 range | On-demand path works; **10 requests in its lifetime, needs load testing** |
| §2 dispersion | **Measured, not built** — `RESULT_dispersion_512.md` |
| §3 working | **Blocked** — `adjusted_price` not persisted |
| §4 methodology | Error rate exists; **figure needs pinning**, labels must be stripped |
| §5 lender explainer | **Not built.** `CapitalGainChart.tsx` exists but is not justified by this persona — see §5 |
| §6 market direction | Data exists; Rule 5 framing needed |
| §7 flood | Burleigh Waters context file exists; other suburbs absent |
| §8 claim | **Not built**, and needs "nobody calls" to be an operational rule |

## Open questions

1. **Pre-warm or on-load build?** GPT wants the range on the first screen; the build takes 30–90s. §0+§2 as the loading state is the cheap answer, pre-warming the better one.
2. **Does §2 land as honest or as attack?** It criticises a method Fields is licensed to use.
3. **Does the capital gain chart have a home at all?** Built, unjustified by the Equity Checker, no independent support. Park it or ship it as a labelled test. Separately, renovation and condition are explicit dollar lines (A10), so "come back when you've done the kitchen" is available as a return hook — also untested.
4. **Does the corrected accuracy story** (estimates are undated, not systematically wrong) carry the Facebook demand the original article did?
