# Withdrawn & Expired Listings as a Prospecting Channel — Brain 1 Synthesis

**Built:** 2026-08-10 · **Source:** Brain 1 coaching-corpus knowledge graph (9,145 units) via
`scripts/samantha/brain1_deep.py`, four deep queries, map-reduce synthesis · **Companion briefs:**
`01-winning-expired-withdrawn-listings.md`, `02-seller-psychology-after-failure.md`,
`03-long-nurture-not-ready-yet.md`, `04-why-it-did-not-sell-conversation.md`

---

## How to read this document

Every claim below carries an **EVIDENCE GRADE**. The corpus is a body of *coaching*, not research.
Most of it is uncited assertion by practitioners selling a training product. Grading it is not
pedantry — it is the difference between a strategy and a folklore transcription.

| Grade | Meaning |
|---|---|
| **A — Measured** | A dataset or study with a stated n, named in the unit. |
| **B — Cited secondhand** | A coach recalling an external study, no link, no verification possible. |
| **C — Practitioner, multi-source** | ≥2 independent practitioners/libraries converge from operating experience. The strongest grade the corpus routinely reaches. |
| **D — Practitioner, single source** | One practitioner describing what worked for them. |
| **E — Unsourced assertion** | A number or universal claim with no method, no n, no attribution. Coaching folklore. |
| **F — Circular** | Fields' own material, re-ingested into the corpus from Google Drive, cited back as if independent. **Not evidence.** |
| **V — Fields-verified** | Checked against Fields' own systems on 2026-08-10. |

**Source concentration.** Across the three briefs measured, 537 citations resolve to:
RealEstate_Gym (Tom Panos) **314 (58%)**, eXp Realty US **86 (16%)**, Sell It (Serhant) 39,
KB books 38, Agent School 28, BLAC SALT AU 24. **This is one Australian coach's doctrine with a
US brokerage-webinar chorus.** It is not an industry consensus and must never be reported as one.

---

## PART 1 — The findings that most change how Fields should approach this channel

### F1. The channel is small, real, and already computable at Fields — ~20–35 homes/month

**Grade: V (Fields-verified, 2026-08-10).** `listing_status: "withdrawn"` across the four target
collections: **robina 28 · burleigh_waters 22 · varsity_lakes 18 · nerang 0 = 68 total**, all
carrying `withdrawn_date`, `withdrawn_detected_at`, and full enrichment. By month:
2026-03: 2 · 04: 7 · 05: 1 · 06: 15 · 07: 35 · 08: 8 (partial). Detection began ~March 2026
(pipeline step 104, `scripts/detect_withdrawn.py`), so the earlier months are detection ramp, not
market signal.

**Why it changes the approach:** this is a *20–35 homes/month* channel, not a *thousand-home*
channel. Everything the corpus recommends that is expensive per-home (handwritten card, phone call,
personal visit) is affordable at this volume, and everything Fields would normally reach for
(bulk automation) is over-engineered for it. **The correct instinct here is the opposite of the
letterbox programme's:** low volume, high effort per home.

---

### F2. There is a timing trigger, three sources converge on it, and Fields can compute it exactly

**Grade: C (practitioner, multi-source — three independent units, no measurement behind any of them).**

- **Withdrawn → day 45.** Josh Tesolin: *"I'd go at the 45 day... I wouldn't say anything bad about
  the agent. They're going to do that to themselves"* (**u2653**, RealEstate_Gym).
- **Expired → day 50.** Tom Panos: *"after 50 days, they're psychologically looking for another
  real estate agent. You want to be on that shopping list"* (**u0507**, RealEstate_Gym,
  *One Page Business Plan*).
- **Expired → day 60–90.** *"expired listings are back again anything at day 60 from day 90 they're
  interviewing for their next agents"* (**u2186**, RealEstate_Gym).
  ⚠ Brief 01 attributed this quote to **u2202**; it is in **u2186**. Corrected here.
- **Corroborating shape:** *"It's gone 45, 60, 90 days and the home hasn't sold"* (**u2205**).

**Why it changes the approach:** Fields stores `withdrawn_date` on every withdrawn document. A
day-45 trigger is a `$match` and a cron, not a behaviour change. This is the single most directly
buildable finding in the whole sweep — and note it is a *trigger*, which is precisely the class of
thing that has silently failed before (the off-market intent trigger does not fire). It must ship
with a Rule 7b outcome assertion: *"N homes crossed day 45 this week and 0 touches were generated"*
is a failure, not an empty queue.

**Caveat that must travel with it:** all three numbers are one practitioner's felt sense of when a
vendor gets frustrated. There is no measurement anywhere in the corpus behind 45, 50, or 60.

---

### F3. "Approach as the buyer's advocate, not the listing-hunter" — and for Fields this is not a pose

**Grade: C (practitioner, multi-source — Agent School + two RealEstate_Gym practitioners).**

- Mat Steinwede: *"Don't chase an expired listing, another agent's listing to get their listing.
  Chase them to help them buy... when they are on your turf, you can actually have a good
  question-based presentation and find out where they're at"* (**u0864**).
- Leonidas Proestos: *"I started noticing a lot of listings on the market that have been on for 60
  days. And I just saw the golden opportunity there"* → *"I'd either call them or doorknob them.
  And I would try to help them on their transactions journey"* (**u2474**).
- *"You go there more from a buyer's perspective first"* (**u0798**).

**Why it changes the approach:** every agent using this frame is *pretending* to be a buyer's
advocate as a way in. Fields is buyer-first by constitution — the business model is literally
"build buyer audience with free data; revenue from sellers." The corpus's best-regarded opening
gambit is a description of what Fields already is. This is the highest strategy-fit finding in the
sweep and it should determine the tone of every asset in this channel: *we help you understand what
the market did to your home*, not *we would like to sell your home*.

---

### F4. Never criticise the previous agent — and the corpus's reason is self-interest, not manners

**Grade: C (multi-source, and zero-downside regardless of grade).**

- *"I wouldn't say anything bad about the agent. They're going to do that to themselves"* (**u2653**).
- *"You will win the argument, but you will lose the listing"* (**u2394**).
- *"I don't use the CMA because I don't really believe the other agent is as good as me"* — the
  coached move is case studies and social proof, **not** direct criticism (**u2532**).
- Serhant-side: *"Both agents have a fiduciary responsibility to work for their client's best
  interest, but that doesn't mean that they have to work against each other"* (**u2837**).

The corpus's safe substitute is to attribute the previous approach to **since-changed market
conditions** or **the fee/service model the seller chose** — *"Markets don't dictate your results.
Markets dictate your strategy"* (**u2805**); *"In a hot market... sometimes just going through the
motions gets a place sold. But in a tough market... you can't just be a tour guide"* (**u2940**).

**Why it changes the approach:** Fields' whole content posture already forbids attacking anyone.
But this finding adds a specific prohibition that is easy to violate accidentally: an
evidence-led "here is what the campaign got wrong" analysis *reads as* an attack on the last agent
even if no agent is named. The safe form is the market-verdict form (F5).

---

### F5. The anti-insult device the corpus reaches for is *data as a neutral third party* — which is Fields' product

**Grade: C (multi-source) for the technique; the underlying pricing claims are D/E.**

- *"You're using data as the third party. You're not saying, I think it's worth that"* (**u0545**).
- *"be more doctor, less sales person... They use X-rays. What do we do in real estate? We use data.
  Data is your friend"* (**u0513**).
- *"It's not me saying it, it's coming from the buyers"* (**u902075**).
- *"People won't reduce price based on two things. Service or evidence"* (**u0110**, Agent School).
- Visual comparables: *"let them see where they think they should be priced. And if anybody thought
  their house was worth more... they're going to plainly see that they would be the most expensive
  house on the market"* (**u902237**, eXp US).

**Why it changes the approach:** the corpus asks the agent to *manufacture* neutrality — to stand
behind a spreadsheet so the hard message isn't personally theirs. Fields does not have to
manufacture it; Fields *is* the third party. The un-copyable version of **u902237** is a computed
per-address position against live competition, not an eyeballed one. **Hard constraint:** this must
obey CLAUDE.md Rule 5 and the valuation design envelope — comparable **ranges** not single figures,
methodology and confidence disclaimer attached, and no recommendation of any action.

---

### F6. Engineer the seller's self-diagnosis. Never deliver the verdict.

**Grade: C (multi-source: eXp US + BLAC SALT AU + RealEstate_Gym).**

- *"Go in being a detective and come out being a doctor"* — because *"when it comes to these types
  of sellers, they already tried to sell and they failed"* (**u900945**).
- *"When you ask questions, you learn when you make statements, they judge you"* (**u901749**).
- The move that extracts an indictment of the last campaign without you saying anything:
  *"Do you feel in the negotiations, do you feel they could have got more money from you? Yeah...
  most people will say, yeah, yeah, I reckon we would have gone another 10 or 20 grand"*
  (**u900953**, BLAC SALT AU — *"On the third question, you usually get to their genuine reason"*).
- *"Real estate agents go into prescription mode before diagnosing"* (**u1604**).

**Why it changes the approach:** this is the strongest argument in the sweep for a **self-service
page over a letter that tells them**. A mailed piece that says "your home didn't sell because it was
overpriced" violates F4 and F6 simultaneously. A page that shows them where their asking price sat
against everything that *did* sell, and lets them draw the conclusion, satisfies both — and happens
to be the only version compatible with Fields' no-advice editorial rule.

---

### F7. Disengagement is terminal, and it has a clock — the window is short

**Grade: D (single source, Agent School) for the mechanism; C for the surrounding decay timings.**

- *"The emotional cutoff is very real"* and *"once they disconnect, they pretty much don't come
  back"* (**u0119**, Agent School, *The Real Estate Growth System*). Same unit: *"Their language
  changes as they get to that point."*
- The decay clock the owner has already lived through: *"The first two weeks are the most important,
  then the interest drops off"* (**u0055**); *"by week four your property is stale"* (**u2493**);
  *"after 14 days... it tapers off very quickly"* (**u2267**).
- Non-relist paths are real: *"I see them in two months time on the market with another agent"*
  (**u2393**) is the common case, but the corpus also documents owners who simply hold.

**Why it changes the approach:** it argues *against* the instinct to be respectful by waiting. If
the cutoff is real, a withdrawn owner contacted at month 6 may be unreachable in a sense that has
nothing to do with their address. Combined with F2, the operating window is roughly **day 45 to
day ~120**.

⚠ **Discarded from this finding:** brief 02 supported the "anxiety arrives in week 2–3 — *Did we
choose the wrong agent?*" claim with **k02077**, which is **Fields' own "Before You List" seller
book** re-ingested from Drive. That is grade **F, circular**, and is excluded here. The
Agent-School emotional-cutoff finding stands on its own.

---

### F8. Recency beats loyalty — the previous agent is structurally anchored to the failure

**Grade: C (multi-source within RealEstate_Gym's peak-end family; the psychology itself is
established outside the corpus).**

- *"Recency trumps loyalty"* (**u1440**).
- *"Peak end effect is a scientific validated concept that people will remember the end more than
  anything else"* (**u2509**); *"the nine things he did really well were all forgotten because what
  we remember was the most recent experience"* (**u1992**).

**Why it changes the approach:** the failed campaign *is* the owner's most recent experience of
their incumbent agent, so the switch is close to structurally guaranteed. Fields does not need to
win an argument against the previous agent (F4) — it needs to be *the visible presence at the
moment of re-entry*. That is an availability problem, not a persuasion problem, and availability is
the thing a platform can do and a person cannot.

---

### F9. The decision is often made before any meeting — the most strategically important number in the sweep

**Grade: B (cited secondhand, and weakly — a coach recalling an ~8-year-old study of ~300 sellers).**

> *"They've probably made a decision to use you... CoreLogic did a study about eight years ago and
> they actually asked a whole bunch, about 300 sellers and 60% of them said, we actually selected
> the agent who we're gonna use before we met them."* (**u901781**, BLAC SALT AU)

⚠ Brief 03 cited this as **u1781**. That unit is a different RealEstate_Gym unit about hunger and
desire and **does not contain this quote**. Corrected here. The `u9####` → `u####` truncation
appeared four separate times across the sweep (see Part 3).

**Why it changes the approach:** if the agent choice largely precedes the meeting, then the value of
being present *before* the withdrawal — as the address's ambient data relationship — outranks the
quality of any pitch delivered after it. This is the finding that most favours Fields' existing
address-level model over a reactive day-45 campaign. **But it is grade B at best**: secondhand,
undated in the unit, un-locatable, and self-serving for the coach making it. Do not put this number
in any public asset.

---

### F10. The conversion horizon is 6–18 months, not 45 days — which contradicts how this channel is usually imagined

**Grade: D (single practitioner, US brokerage webinar) for the specific window; C for the general
long-nurture pattern.**

- *"All of the money is between month six and month 18... all of the money is in being able to carry
  and nurture for longer than 6 months which is what most agents are not willing to do"*
  (**u901289**, eXp Realty US / Sisu).
- The observed cadence of top performers: *"Every single one of them does a weekly email. Every
  single one of them does a call every quarter"* (**u2562**, Andrew Bell's cohort — practitioner
  observation across a group, the closest the corpus gets to a survey).
- Multi-year conversions are presented as normal: *"A listing is the remuneration for good follow-up
  work. It took 11 years"* (**u1437**); Serhant's five-year drip closing a $17M deal (**u2854**).

**Why it changes the approach:** the day-45 trigger (F2) opens the relationship; it does not close
anything. The channel must be resourced as a **6–18 month nurture of ~20–35 new homes per month**
(so ~150–600 live at any time), not a monthly campaign with a monthly conversion expectation. Any
success metric measured at 90 days will read as failure and get the channel killed prematurely.

**Tension to hold:** F7 says disengagement is terminal and fast; F10 says conversion is slow. The
resolution the corpus implies — start early, stay light, expect nothing for a year.

---

### F11. Price is the diagnosis in ~8 of 10 cases — so the evidence Fields already produces is aimed at the actual cause

**Grade: D–E (single practitioner for the 8/10 figure; multi-source for the qualitative claim).**

- *"There are three things that I always teach our team. It's pricing, presentation and marketing"*
  and *"In eight out of ten instances, it's going to be price-related"* (**u1280**, John McGraw).
- *"If the property is not sold in a few weeks, it's either the marketing is poor or the price is too
  high"* (**u0700**). *"If the property isn't selling, the truth is simple, guys. It's overpriced"*
  (**u900058**, eXp US).
- *"if you promote it correctly, if you price it correctly and if it's not sold by that sort of 60,
  70 day mark, something's wrong... You've got the wrong agent"* (**u0452**, Josh Tesolin).

**"8 out of 10" has no method behind it** — it is one team leader's impression, stated as a
statistic. Use the qualitative claim, never the number.

---

### F12. How you framed success predetermines who gets blamed for failure

**Grade: D (single source, eXp US) — but it is a structural argument, not a claim about the world.**

> *"if you lead with marketing and the home doesn't sell, you have set the expectations to your
> seller that they're going to come back and say, 'You told me you were a great marketer, so now do
> more marketing.' ... if you lead with price and the home doesn't sell, it's always always the
> price."* (**u900629**, eXp Realty US, *The LAB*)

**Why it changes the approach:** Fields leads with *data and valuation evidence*. By this logic, if
a Fields-influenced campaign fails, the blame lands on **Fields' data**. That is a real exposure
given the valuation design envelope ($1M–$2M detached only), the ±12% band that contains the sale
price ~61% of the time, and the non-monotonic confidence tiers. **A failed seller is, by definition,
someone already burned by an over-promise (F13) — they are the least forgiving audience Fields
could choose for a number.** Every figure in this channel must be a range with its limitations
stated, or the channel manufactures its own second betrayal.

---

### F13. The grievance to speak to is *silence and over-promising*, not price

**Grade: C (multi-source: RealEstate_Gym + eXp US + Serhant).**

- *"Most of the time people have an unpleasant experience with a real estate agent. It's usually
  because of communication"* (**u2133**).
- *"Silence destroys trust and the seller's perception is that if you aren't calling, you aren't
  working"* (**u901618**, eXp US). Serhant: *"Silence makes you a liar"* (**u1062**).
- The buy-the-listing betrayal: *"She's been the market for a week... the agent's already trying to
  condition me to drop my clock"* (**u2507**).
- Which is why the seller shifts to process: *"It's the process, not the promise of a price that's
  going to have you solve for top dollar"* (**u2440**); *"People want a plan... they do not
  necessarily want the best real estate agent they just want the one that can explain their plan
  the best"* (**u2281**).

**Why it changes the approach:** the copy for this channel should not open on price at all. It
should open on the thing the owner actually resents — being left in the dark — and offer the
opposite: continuous, unrequested, unconditional information about their own home. That is a
description of a Fields product, and it sidesteps F4 entirely because it criticises nobody.

---

### F14. The corpus contains **no conversion rate** for this channel — and says so

**Grade: n/a (documented absence).** Brief 01 states plainly: no validated expired/withdrawn
conversion rate exists in these units. The nearest figures are general prospecting strike rates from
unrelated contexts. **Any business case Fields writes for this channel is therefore modelling from
zero.** The corpus tells you *how*; it cannot tell you *whether*, or at what rate.

---

## PART 2 — What does NOT transfer to Fields
*(no agent workforce, no cold-call floor, data platform not a person)*

The corpus assumes a licensed human agent with a car, a phone floor, and a kitchen table to sit at.
Roughly half of the method depends on that assumption. Listing these honestly is more useful than
the findings above, because these are the parts a keen reading would otherwise try to build.

### 2a. The closing step is structurally out of reach

- *"You can't win a listing without being in someone's house eyeball to eyeball"* (**u0220**);
  *"No agency agreements... unless you face-to-face"* (**u0747**); the pre-filled contract at the
  kitchen table (**u901001**). **Fields has no one to put in the room.** Every path in the corpus
  terminates in an appointment. Fields' realistic maximum is to *manufacture and warm the lead up to
  that appointment* — and there is currently no one on the other side of it.
  **This is the channel's unresolved dependency, and it should be named in the scoping doc before
  anything is built.**

### 2b. The phone is the corpus's conversion instrument. Fields has almost no phone numbers.

- *"Phone call is highest... but at the end of the day, it's not going to become a listing till you
  have that final conversation, which gets you into the door"* (**u2633**); *"Those that pick up the
  phone sell the most"* (**u0557**).
- The US daily-sprint cadence — *"I'm calling them every single day for 15 calls... it can take 13
  to 27 touch points to make contact"* (**u901996**) — presumes an ISA team or a dedicated caller.
- **Fields-verified counter-fact:** `lead_worklist` holds 297 non-test leads with **3 phone numbers**
  (per `17_Direct_Letterbox/00_SCOPING.md`, [VERIFIED]). There is no calling capability, and the
  channel cannot be designed as though there is.

### 2c. Door-knocking, handwritten cards, and physical presence

- The door-knock opener (**u0241**), the rejection-seeking knock (**u2202**), the handwritten card
  the corpus rates above nearly every other touch — *"The handwritten card will never, ever, ever be
  replaced by AI. Never"* (**u900380**), *"your cut through is going to be nine times out of ten much
  much better"* (**u900852**), *"20 just-to-note cards per week will put you in the elite level"*
  (**u900339**).
- **The corpus's own logic says automating these destroys them.** Its warning about the "bulk mass
  SMS" tell (**u900382**) applies directly. At 20–35 homes/month (F1), a genuinely handwritten card is
  *affordable* — but it requires a human hand, which is a Will-hours decision, not an engineering
  one.

### 2d. The whole fee/commission objection family is irrelevant

- *"in the absence of value, people will select you on fee"* (**u901225**); *"That extra five grand
  that you're saved with the other agent on a commission basis..."* (**u1470**); *"Your net figure...
  is a lot better, even though my fees dearer"* (**u1831**); *"The cheapest agent and the best agent
  is generally not the same agent"* (**u901744**).
- Fields charges the seller no commission and is not competing on fee. A large, well-developed slice
  of the corpus's expired-listing method is answering an objection Fields will never receive.

### 2e. The buyer-network proof

- *"I've sold quite a few off market this way... I have about 40 buyers in market shape"* (**u2411**);
  *"If you don't bring buyers through before you've got it listed, what's the evidence that you've
  actually got buyers?"* (**u2549**).
- Failed sellers specifically demand proof of live demand. Fields has *audience* (traffic,
  off-market deck engagement, ~91% Google organic) but **not a qualified-buyer register**. Claiming
  buyers Fields cannot produce would recreate exactly the over-promise that made this person a
  failed seller (F12/F13). The honest substitute is observed demand data — search and page-level
  interest in that address and its comparables — clearly labelled as interest, not buyers.

### 2f. Tonality, silence, and real-time emotional reading

- *"the tonality of someone that's asking a question, what's been going on there? And then all you do
  is shut up"* (**u2174**); *"The power of silence... the longer the pause, the more credible your
  answer is"* (**u2087**); *"the most dominant energy will rule... if you stay really centered in
  calmness"* (**u0503**); mirroring (**u0087**).
- **A text channel has no pause.** Fields' chat layer can carry the *questions* as qualification;
  it cannot carry the method, and the corpus is explicit that the method *is* the tonality.

### 2g. US market mechanics that have no Australian equivalent

The eXp Realty US material (16% of citations) assumes an **MLS with an expired-listing feed**, Zillow
Flex lead ponds with hot/pond splits owned by virtual assistants (**u902043**, **u902044**), stepped
CRM cadences run by an ISA (**u901288**), and US pricing conventions (*"$350K not $349K"* for search
brackets, **u901571**). None of it ports. Australia has no expired feed — **which is precisely why
F1 matters: Fields already detects withdrawal itself, and that detection is an asset the US
playbooks take for granted and Australian agents largely lack.**

### 2h. The volume assumptions

*"500 call connections per week"* (**u1685** — *note: the anniversary quote below is in **u901685**; these are two different real units sharing a numeric stem*), 20 cards/week (**u900339**), 3,500 letterbox drops
per week. These describe a full-time prospecting operation. Fields is a sole operator with an
automation layer. Cadence numbers from the corpus should be read as *shape* (weekly-ish, then
quarterly, with an annual floor), never as targets.

### 2i. The one thing the corpus itself says is un-copyable

Its most-repeated success factor is not a technique: *"vendors... are looking for a good human being
to show up"* (**u2055**); *"People forget what you say but they never forget the feeling that's
transferred"* (**u1709**); *"When you smile with someone, when you're humble... it disarms people"*
(**u1206**). Fields can make the *diagnosis* unbeatable and the *presence* continuous. The moment
where insult is actually caused or avoided stays human.

---

## PART 3 — Verification, corrections, and what was discarded

### Provenance sweep (independent of `brain1_verify.py`)

Every unit id cited across the four briefs was resolved against `brain1_build/package.json`
(9,145 units).

- **Fabricated ids: 0.** Every cited id resolves to a real unit.
- **Self-citation loop (prior Brain 1 output re-ingested from Drive): 0 detected.** No cited unit
  carries an embedded `u####` inside a quote string — the durable tell. The three
  `external:drive/` units cited (**i2109697108**, **i3582445599**, **i8831617832**) are genuine
  academic PDFs sitting in the Seller_Book_V2 Drive folder (Christie et al. 2008 on the emotional
  economy of housing; an Australian spatial agent-based market model; a listing-price-strategy
  paper), **not** prior Brain 1 briefs. They are the highest-grade material in the sweep, though
  ingestion fidelity is unverified.

### ⚠ Circular evidence — Fields' own book cited as if independent (grade F)

Nine citations across briefs 02 and 04 resolve to **"Before You List — Fields seller book"**, which
is in the corpus because it was ingested from Drive. Brief 02 additionally attributed two of them
to **Ryan Serhant**, who did not write them:

| Unit | Wrongly presented as | Actually |
|---|---|---|
| **k02039** | *"Ryan Serhant's material"* — "You're feeling vulnerable because you are vulnerable" | Fields' seller book |
| **k02077** | *"Serhant's campaign material"* — the week-2 anxiety curve | Fields' seller book |
| **k02081** | independent evidence — *"1,689 automated estimates... 89% overvaluation rate"* | Fields' own analysis |
| **k02070, k02072, k02076, k02053, k02054, k02047, k02040** | corpus evidence | Fields' seller book |

**None of these may be used as corroboration for a Fields decision.** They are Fields asserting
something, stored, retrieved, and handed back as if a coach had said it. `brain1_verify.py` cannot
catch this class — the text really is in the corpus. **k01957** (*Real Estate Valuation
Variance.docx*, the auction-vs-private-treaty claim) is of uncertain authorship and is treated the
same way pending a provenance check.

### Citation errors found and repaired

| Brief | Cited | Correct | Nature |
|---|---|---|---|
| 04 | u102, u158, u700, u890, u953 | u0102, u0158, u0700, u900890, u900953 | Zero-padding / `u9####` truncation. **Repaired in file.** |
| 03 | u1781 (CoreLogic 60%) | **u901781** | Quote absent from u1781. Corrected in this synthesis. |
| 03 | u1685 (anniversary <5–10%) | **u901685** | Quote absent from u1685. Corrected in this synthesis. |
| 01 | u2202 (day-60 expired interview) | **u2186** | Quote is in u2186. Corrected in this synthesis. |

**A systematic failure mode is visible here:** the map-reduce step drops the leading `9`/`0` from
`u9####` and `u0###` ids, silently converting an eXp-Realty-US or BLAC-SALT-AU citation into an
unrelated RealEstate_Gym one. **The full verifier run puts the true scale far above the four cases
I found by hand: 38 truncations in brief 03 alone** (u1413→u901413, u1414→u901414, u0179→u900179,
u0380→u900380, u0382→u900382, u1750→u901750, u1940→u901940, u1943→u901943, …), 12 in brief 04, 4 in
brief 02. **Any future Brain 1 brief must be run through an id-existence check *and* a per-quote
location check**, because a truncated id usually still resolves to a real-but-wrong unit and so
passes an existence check silently.

⚠ **The correction must be made per quote, in both directions.** `u1685` and `u901685` are *both*
real units: the anniversary-card quote is in **u901685**, but *"500 call connections per week"* is
in **u1685**. A blanket rewrite in either direction manufactures new misattributions — and did so
once in this sweep before being caught.

**Why the source-concentration figure at the top of this document understates the problem:** because
truncation converts `u9####` → `u####`, the raw citation tally *over-counts RealEstate_Gym and
under-counts eXp Realty (US) and BLAC SALT (AU)*. The real split is less Panos-dominated and more
US-webinar than the 58% figure suggests — which makes the "not an industry consensus" warning
stronger, not weaker, since much of the apparent Australian corroboration is US brokerage content.

### Discarded as unverifiable

1. **`"expired listings over 60-day filter"` (u2174)** — presented in brief 01 as a quotation. It is
   not a quote; it is a Haiku-extracted **entity label** on that unit ("Listings over 60 days
   filter"). Discarded as a quotation; the underlying fact (that this agent filtered on 60+ day
   listings) is fine as a paraphrase.
2. **All named speaker attributions.** Speaker names in this corpus are Haiku-extracted entities and
   are frequently garbled — the same person appears as *"Josh Tessolin/Tedeschi"*, *"Josh Tessla"*,
   *"Josh Tesslan"*. Brief 01 attributed **u2202** to both Alex Jordan and Bayron Atherton in
   different paragraphs (the entity list says Alex Jordan). **Never attribute a quote to a named
   practitioner in anything public.**
3. **Brief 01's label "US RealEstate_Gym"** for the `u9####` units. They are **eXp Realty (US)**
   brokerage webinars and **BLAC SALT (AU)** sessions — different organisations, different market,
   different regulatory regime. The mislabel makes single-source US webinar content look like
   corroboration of the Australian doctrine. Corrected throughout this synthesis.
4. **Every bare statistic in the corpus.** *83% of sellers expect more than asking* (**u900890**,
   US webinar); *38 touches/year → 3–6% conversion* (**u900912**); *$10–15k prior marketing spend*
   (**u0164**); *8 out of 10 price-related* (**u1280**); *<5–10% of agents do anniversary cards*
   (**u901685**); *90% conversion on mail + phone follow-up*. All grade **E** — no method, no n, no
   source, and every one of them told to an audience being sold coaching. Usable as hypotheses.
   **Never publishable, and never a business-case input.**
5. **Any claim about *whether* this channel converts.** The corpus contains no rate (F14).

### ⛔ The publish gate itself was broken — found and fixed during this sweep

`brain1_verify.py` loaded **4 annotation files** while the graph is built from **6**. Missing:
`/home/fields/brain1_yt/annotations.jsonl` (2,292 units — the entire **eXp Realty (US)** and
**BLAC SALT (AU)** corpus, the `u9#####` ids) and `/home/fields/brain_drive/annotations_b1.jsonl`.

**Consequence: every quote from those libraries was reported `NOT_FOUND` — the verifier's verdict
for "fabricated".** On brief 01 that was **41 false fabrications**, dropping its headline fidelity
to 64.0%. All 7 sampled "fabrications" were re-located at coverage **1.00** in exactly the unit the
brief cited.

This is the same class of defect the memory already records for the graph builder ("the graph is
built from four sources, not one") — the corpus grew, this list did not. The file's own comment
warned of precisely this outcome for the KB files. **Fixed 2026-08-10** in
`scripts/samantha/brain1_verify.py`: both files added, with a comment tying the list to
`brain1_graph.py` / `brain_drive_nightly.py`. Unit coverage went 9,525 → 12,662.

**A publish gate that cries wolf is worse than no gate**, because the next person reads 64% and
stops believing it.

### Final fidelity — all four briefs, fixed gate

| Brief | Spans | Verified | MISATTRIB | NOT_FOUND | Fidelity |
|---|---|---|---|---|---|
| 01 winning expired/withdrawn | 129 | 123 | 1 | 4 | **96.1%** |
| 02 seller psychology | 129 | 114 | 4 | 8 | **90.5%** |
| 03 long nurture | 142 | 95 | 41 | 4 | **67.9%** |
| 04 why it didn't sell | 115 | 102 | 12 | 0 | **89.5%** |

**Brief 03 is the one to distrust.** Its 41 misattributions are almost entirely the truncation bug,
which means its citations systematically point at the wrong *library* — the nurture-cadence
material it presents as Australian coaching doctrine is substantially **US brokerage webinar**
content. Its findings survive; its attributions do not. **Treat every `u####` id in brief 03 as
unverified until re-located.**

Residual faults in briefs 01/02/04 were inspected individually and are benign: markdown fragments
parsed as quotes, the synthesis's own prose, paraphrases rendered in quote marks
(*"law of because calling principle"*, *"letter → call → conversation → thank you"*), and the
already-flagged entity-label pseudo-quote.

### This synthesis's own citations

All **73** distinctive quotes used in this document were checked per-quote against the fixed unit
index. **68 verified at coverage ≥0.9.** Five were wrong and are now corrected in place:
`u2075`→**u902075**, `u1749`→**u901749**, `u0380`→**u900380**, `u0382`→**u900382**, and
`u901685`→**u1685** for the 500-calls figure (the both-directions case above).

⚠ Note for anyone re-running the gate on *this* file: `brain1_verify.py` scores meta-documents
badly. A document that quotes citations in order to discuss them gets its own correction tables
re-flagged as errors (a run against an earlier draft returned 62.5%, roughly half of it artefact).
**Read the failure list, never the percentage.**

---

## PART 4 — The one-paragraph answer

Withdrawn and expired homes are the highest-intent prospect available to Fields and, at ~20–35 per
month across the target suburbs, a small enough cohort to treat individually. The corpus's method is
consistent across its independent sources: contact at roughly **day 45**, approach as the owner's
**buyer-side advocate** rather than a listing-hunter, **say nothing about the previous agent**, let
**data act as the neutral third party** so the owner reaches the "it was the price" verdict
themselves, speak to the grievance that actually stings — **silence and over-promising** — and then
hold the relationship for **6–18 months** without expecting anything. Almost all of that is buildable
at Fields and some of it is genuinely advantaged, because Fields detects the withdrawal itself, is
buyer-first in fact rather than as a gambit, and can be continuously present at an address in a way
no individual agent can. But the corpus's method **terminates in a face-to-face appointment Fields
has no one to attend**, its conversion instrument is a **phone Fields cannot staff**, its
highest-cut-through touch is a **handwritten card automation would ruin**, and it offers **no
conversion rate at all** — so this channel should be scoped as a lead-warming instrument with an
unresolved human dependency at the end of it, and every number in it must be a range with its
limits stated, because the audience is by definition people who were already burned once by a
confident figure.
