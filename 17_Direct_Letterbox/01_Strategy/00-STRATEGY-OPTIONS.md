# Direct-mail strategy — five options

**2026-08-08** · For Will. Decision document.

Read with: [`01-WHAT-THE-EVIDENCE-SUPPORTS.md`](01-WHAT-THE-EVIDENCE-SUPPORTS.md) ·
[`02-AS-BUILT-REALITY.md`](02-AS-BUILT-REALITY.md) ·
[`03-PSYCHOLOGICAL-ARCHITECTURE.md`](03-PSYCHOLOGICAL-ARCHITECTURE.md) ·
[`04-LEGAL-AND-ETHICAL-GATES.md`](04-LEGAL-AND-ETHICAL-GATES.md) ·
[`05-IS-DIRECT-MAIL-DECAYING.md`](05-IS-DIRECT-MAIL-DECAYING.md)

---

## The four things that should change your priors before you read the options

**1. The trigger you think is running is not running.** The engagement threshold that classifies an
owner as a lead — 6 cards, 45 seconds, Telegram alert — is real code that **nothing calls.** DeckV3
became the default on 2026-08-04 and never wired it up; `offmarket_intent_signals` has no document
after that date. What actually creates a lead today is a nightly PostHog query for *the page having
loaded*. There is no depth condition anywhere. Any option below that says "engagement-triggered"
requires a small build first.

**2. The premise that weekly is best does not survive the evidence.** Weekly stacks each piece
inside the previous one's response window (mail stays live in-home 7.6 days; modelled response peaks
around three weeks), a sender's own mailings cannibalise each other at ~63%, and the only measured
tolerance figure is **one piece per month per sender**. **Fortnightly-to-monthly is the defensible
band.** There is exactly one structure that justifies fortnightly, and it is Option 3.

**3. The thing that actually works is not frequency, format or persuasion. It is that the piece is
about *their address*.** Generic mail moves behaviour ~0.5pp. Mail carrying the recipient's own
record moves it **+4.9pp** — about 10×. An RCT on 300,000 insurance customers found that printing
**last year's premium** lifted action 3.2pp while simplification, bullets and helpful leaflets did
nothing, and a follow-up reminder two weeks later did nothing. **Content specificity beats frequency
by roughly 16×.** Fields' entire asset is per-address specificity. Spend there.

**4. ⚠ But "we'll tell you what your home is worth" has already decayed as a proposition — and the
reason is us.** An Australian operator, on why the price-drive letter stopped working: *"they're
just not having the same hit rate that they used to… a lot of people can find out roughly what their
home is worth very quickly by lots of different websites and so needing an agent to give them a
price update for the most part is it's not really what people are after anymore."* **The number is
not scarce. The working is.** A mailer that leads with a figure competes with a free instant estimate
and loses. A mailer that leads with *named, dated sales you can look up yourself, each adjusted, with
the adjustment shown, and an honest statement of how little four sales can settle* is competing with
nothing. This promotes the `anchor` variant — *you already have a number for this address; where did
it come from?* — from one of six to **the opening piece.**

---

## Option 0 — the gate in front of all five

Not an alternative. Whichever option you pick, these come first, and none of them costs postage.

| # | Do | Why |
|---|---|---|
| 1 | **Instrument inbound** — a tracked number, a form, an email capture | Lifetime hard-evidenced inbound contacts: **1**. Until this exists, every claim about whether mail worked is unfalsifiable, which is the exact critique that sinks the whole farming category |
| 2 | **Define and reserve a holdout** — matched addresses that get nothing | **Nobody has ever published a controlled test of homeowner farming mail.** Not JICMAIL, not the ANA, not one coach, not one Australian operator. With a holdout, Fields' result becomes the best Australian data in existence. Without one, it becomes another anecdote |
| 3 | **Write the kill criterion down before you spend** | Farming doctrine is built so failure never counts — every zero is answered with "you stopped too early." Pre-registering the number is the only defence against that |
| 4 | **Take POA ss 22 / 97 / 215 / 222 and the privacy s 6D question to a lawyer** | **s 222(1) may reach the live website, not just the mailer.** See the legal doc. This one is worth doing regardless of this project |
| 5 | **Fix the orphaned intent trigger** (or accept page-view as the trigger and say so) | Otherwise "engagement-triggered" is a description of nothing |

---

## The five options at a glance

| | **1. Warm Trigger** | **2. Bounded Farm** | **3. Event Ripple** | **4. Standing Report** | **5. Rationed Artefact** |
|---|---|---|---|---|---|
| **Who** | The 223 who looked up their own address | 1,200 homes, one bounded area | The 40–80 homes around a live listing | A fixed panel of ~1,000 | ~40/month, hand-picked |
| **Because** | *You came to us* (never said aloud) | *You live here* | *Something just happened near you* | *This is your quarterly* | *You engaged; here is the real thing* |
| **Cadence** | Monthly ×6 | Monthly ×6, then annual cycle | **Fortnightly**, event-length | Quarterly, indefinite | On trigger, once |
| **Volume/yr** | ~1,500 pieces | ~7,200 | ~2,900 (capped) | ~4,000 | ~480 |
| **Cost/yr** | **~$3,800** | ~$18,000 | ~$7,200 | ~$10,000 | ~$3,000 |
| **Evidence** | **Strongest** | Weakest | Novel — no precedent | **Best-quality** | Practitioner only |
| **Build** | Small | Medium | **Largest** | Medium | **Smallest** |
| **First signal** | 4–8 weeks | 3–6 months | 6–10 weeks | 3 months | 2–4 weeks |
| **Main risk** | Reads as surveillance | Cost with no signal for months | Cuts across the listing agent | Slow, dull, needs 2 years | Volume too low to learn |

Costing assumes **~$2.50 all-in per addressed piece** (PreSort $1.53–1.90 + print/VDP $0.60–1.20 +
envelope). **This needs a real quote from Pronto Direct before anything is committed.**

⚠ **A cost trap worth knowing now.** Promo Post at ~$0.83–1.10 is 40%+ cheaper than PreSort — but
its **minimum is 4,000 pieces per lodgement.** A 1,200-home farm mailed monthly never reaches it. To
get Promo Post pricing you must either mail ~4,000 homes at once (which breaks the saturation logic
that justifies the farm) or batch several suburbs' waves into one lodgement day. **The doctrine's
farm size and Australia Post's cheap tier are in direct conflict**, and nobody in the coaching corpus
has ever had to think about it because they are all American.

---

## Option 1 — The Warm Trigger

> **We write to people who came looking for their own address.**

**The population.** 283 leads have already been created from off-market page engagement between
2026-07-20 and 2026-08-07 — **223 with a street-number address** — and they accumulate at roughly
**16/day for free**, off 92% organic search traffic that is compounding ~4× per month. In about two
months that reaches the 1,000-home farm size the coaching corpus converges on, **without a dollar of
acquisition spend.**

**Why this is the strongest option on the evidence.** Cold addressed mail responds at **0.9%**. Warm
responds at **7.2%** — an **8× swing, larger than any creative, format or cadence effect measured
anywhere.** These people are not warm in the classic sense (no relationship, no enquiry), but they
are not cold either: they searched for their own address and read a page about it. Nothing else on
this page moves the list toward warm. This option *is* the list moving toward warm.

**The sequence.** Six pieces, monthly, each a different Owner-Subject Article variant — six
compositions of identical data passing identical gates, which makes it an unusually clean creative
test. Suggested order, escalating self-relevance:

1. `anchor` — *you already have a number for this address; where did it come from?* (ranked fear #3)
2. `anomaly` — *two sales near you point to very different numbers* (prediction error)
3. `timing` — *half sold within 34 days; which half would yours be?*
4. `features` — *what are your land, condition and floor area actually worth?*
5. `contradiction` — *the national numbers and your street disagree*
6. `report` — the plain statement of the finding (also the control)

**What must be built.** Owner-Subject Article → PDF path · per-address `asset_code` + QR (the
tracking rail already works, it has simply never been pointed at an address) · postal-address
normalisation on `lead_worklist` (today the address is a display string) · suppression list ·
lodgement-day re-validation · a mail vendor.

**The thing that would kill it.** Copy that reveals we watched them. Not "you visited our page" —
**anything** that a reader could reconstruct into surveillance. This population is uniquely
sensitive precisely because they came privately. Get this wrong and the best list in the business
becomes the worst.

**Kill criterion.** Six pieces to ~250 addresses, ~$3,800, with a 25% holdout. If the mailed group
does not produce **at least 3 inbound contacts more than the holdout** by month 8, stop.

---

## Option 2 — The Bounded Farm

> **We saturate one area until we are the obvious name in it.**

**The doctrine.** Farm size 1,000–2,000 is the strongest multi-voice finding in Brain 1 — about ten
separately named agents converge on it — with the failure mode named repeatedly: *"I was trying to
dominate too big of an area… four suburbs… 20,000 properties."* Fields currently has **26,297 decks
and zero homes touched**: maximum breadth at zero depth, the exact inverse of the doctrine.

Steve Robertson's eXp blueprint independently arrives at **six mailers a year to ≤750 homes** — the
same figure as the Gerber & Green RCT ceiling (~6 mailings before diminishing returns), reached from
the opposite direction. That convergence is the only place coaching doctrine and controlled evidence
agree on a number.

**Pick the farm by turnover, not by affection.** Brad Korn: *"that gated community with 50, 60, 100
homes… there's no more than five or six of them selling a year. That is not a neighborhood you want
to spend your time marketing to."* **Fields can compute annual turnover per street from its own sold
data.** This is a query, not a guess, and it is the single most defensible thing in the option.

**The honest problem.** This is the **weakest-evidenced** option on the page. There is no academic
study, no MLS analysis, no brokerage cohort data and no controlled test of real-estate farming
anywhere. The two vendors who publish numbers disagree by an order of magnitude on the same strategy
in the same year ($1,285 vs $5,000–15,000 per listing). And the doctrine is constructed so it cannot
fail: every zero is answered with *"you stopped too early."*

**Kill criterion.** This is the option that most needs one, and it must be set against the holdout,
not against zero. Pre-register it or do not start.

---

## Option 3 — The Event Ripple ⭐ *the novel one*

> **A house near you is on the market. Nobody knows what it will sell for — including us. We will
> tell you what happens.**

This is Will's `Houses_Surrounding_A_Just_Listed.md` idea, and after all the research it is the most
interesting thing in this folder. It is also the only option with **no precedent anywhere** — which
is both its appeal and its risk.

**Why it is structurally different from everything else.** Every other mail programme in existence
faces the same problem: to keep someone reading across a sequence you must either repeat yourself
(which measures null — 5, 9 and 12-piece advocacy sequences produced flat nulls) or withhold
something (which is manipulation, and is blocked by our own shipped TEASE guardrail).

**A live sale escapes the dilemma.** The loop stays open because *the world* has not closed it, not
because we are sitting on the answer. Each piece reports something that genuinely did not exist when
the last one was written. That is the Zeigarnik effect obtained honestly — and it is the **only**
structure that justifies a fortnightly cadence, because fortnightly *new information* is not
repetition at all.

It is also the **Law of Because** made automatic — *"The reason I'm writing is because 27 Smith
Street has just come onto the market"* — a genuine, specific, dated reason we did not manufacture.
Fields holds every sale event in four suburbs plus 53,313 historical events, so it can generate one
for any address, at a scale no individual agent can reach.

**The sequence, hung on the real timeline:**

| Piece | Trigger | Carries |
|---|---|---|
| 1 | Listing goes live | *This just listed near you. Here is what it is, and here are the four sales the market will judge it against — each adjusted to **your** home* |
| 2 | +2 weeks | What has changed: price adjustments, days on market, how the comparable set has moved |
| 3 | Under offer / sold | **The number.** The loop closes with a real transaction |
| 4 | +2 weeks | What that sale did to the evidence around **your** address — the adjusted range, before and after |

Piece 4 is the payoff and the reason to do this at all: *"how this sale changed your home's value"*
is a sentence almost nobody in Australian real estate can write truthfully, and Fields can, per
address, automatically.

**Volume must be capped, hard.** There are ~1,400–1,700 listings a year in catchment. At 60
neighbours × 4 pieces that is **340,000–400,000 pieces a year.** Cap it: **3 events per month, 60
homes each, 4 pieces** ≈ 2,880 pieces/year ≈ $7,200. Choose events inside the Option 2 farm and the
two compose into one programme.

**⚠ The risk that is specific to this option.** You are writing to the neighbours about a home
another agent is currently selling. Beyond the obvious relationship friction, **POA s 216 and
dispute risk with the appointed agent is an open legal question** (W4, question 15). Get it answered
before piece 1. The safer variant mails only on **sold** and **withdrawn** events, which loses the
live-loop mechanic but removes the conflict entirely.

**⭐ The upgrade that makes this the strongest option, not just the most interesting.**

Brain 1's sequencing query surfaced the cleanest micro-conversion in the whole corpus, and it is
built for exactly this structure:

> *"if they say 'I'm going to come to the open', you can then say, **'would you like me to let you
> know what it sells for?'**"* (u1730)

**Put that opt-in on piece 1.** *"We'll write to you when 27 Smith Street sells, and tell you what
it means for yours."* One yes, no phone number, no email — just a tick and a return path.

That single move changes the economics and the legal position at once:

| Before | After the opt-in |
|---|---|
| Cold list — **0.9%** response | **Solicited** — the warm band is **7.2%**, an 8× swing |
| APP 7.3 "impracticable to obtain consent" — the weakest link in the whole legal analysis | **Consent obtained**, in writing, per address |
| WRRA / POA "unsolicited" addressing paradox | Largely dissolves — they asked |
| Endowment framing asserted | *Their* subscription, actually |

It also matches the corpus's other finding — **that the documented print sequence is
event-triggered, not calendar-triggered** — and Fields' own measured reality that the public will
not surrender a phone or an email but *will* engage with an address. Pieces 2–4 then arrive because
the recipient **asked** for them, which is the only version of this programme that is unambiguously
welcome.

**This makes Option 3 the cheapest available route from cold to warm**, and warm is the single
largest lever in the entire evidence base.

**Kill criterion.** Six events (~720 pieces, ~$1,800) with a matched holdout of streets that get
nothing. Two things to read: the **opt-in rate on piece 1** (that is the real number — it decides
whether the rest of the programme is solicited or not), and whether **piece 4 out-scans pieces 1–3.**
If piece 4 does not, the payoff structure is not working and the thesis is wrong.

---

## Option 4 — The Standing Report

> **The same homes get the same report, four times a year, indefinitely.**

**The evidence case is the best on the page and it is not close.** Opower's home energy reports —
recurring personalised multi-page reports mailed to homeowners about **their own home** — were
randomised across 600,000+ households (8.6 million by 2015), produced sustained behaviour change,
and showed **no habituation across 60 consecutive months.** Effects persisted after the mailing
stopped. This is our exact structure, and it is the only place in the entire research file where
someone has actually measured a programme like the one we are proposing.

**Four operational transfers, all of which contradict a natural instinct:**

1. **A one-shot mailer decays to nothing in about three months, and a two-year programme is 2.5–4.2×
   more cost-effective than a short one. Fund a cadence or don't start.**
2. **Targeting beats creative** — top decile 6.3% effect vs bottom decile ~0%; profiling raised the
   effect 74% and cut cost-per-outcome 43%. Spend the effort choosing *who*, not polishing *what*.
3. **Effects peak ~10 days after arrival.** Measure at 10–21 days, not at 48 hours.
4. **Discount any pilot result by 30–50%** — the effect shrank at every step away from the
   hand-picked initial sites (3–6× → 2.0% → **1.31%** at full scale).

**The honest caveats.** Opower had three things Fields does not: a billing relationship, an
unambiguously legitimate data holding, and a regulator paying for the postage. And the comparison
*is* the product — 49% said they would like the report **less** without the neighbour comparison,
which is precisely the element the backlash evidence tells us to avoid at the individual level. Our
version of "comparison" must be **sold transactions**, which are public record, never living
neighbours.

**The number that should sit on the wall:** 34% of Opower recipients had weakly negative willingness
to pay for the report while only 0.08–3.3% ever opted out. **A quiet mailbox is inertia, not
consent.** Instrument annoyance separately.

**Kill criterion.** This option's honest horizon is **two years**. If you are not prepared to fund
eight quarters, the evidence says do not start — a short run of this is the one design the research
explicitly says wastes money.

---

## Option 5 — The Rationed Artefact

> **Everything stays free online. The one physical, personal, expensive thing is earned.**

The coaching corpus's single most concrete artefact is Steinwede's CMA: a 3-day process,
personalised, **a picture of their house on the covering letter**, capped at **≤10 per day by hand**,
with the claim *"You will have no competition after a period of time."* Fields generated **183 in a
day** and holds 3,037 computed appraisals. **We have industrialised the highest-value artefact in
the corpus.**

This option takes the corpus's other instruction seriously — *"ration it… you get one chance to do
this really well later"* — and resolves it the way the lead-funnel verdict proposed: **ungate the
analysis, keep the artefact.** The on-page data stays free and open. The heavy, posted, personally
signed pack is the earned escalation, sent only to people who did something.

**⭐ Brain 1 independently validates this split, and it settles a real fight.** The corpus carries a
genuine cross-source contradiction — give-give-give (Panos *and* Serhant, separately) against
*"the more value you give away for free, the less valuable you are"* (Voss/Shull). They are not
disagreeing about the same variable: **give freely as a long-horizon nurture act, withhold the
bespoke deep-dive as spec work at the point of a live listing decision until there is commitment.**
That is the only position consistent with every source in the corpus, and it is exactly this option
paired with an ungated on-page analysis. See [`05-IS-DIRECT-MAIL-DECAYING.md`](05-IS-DIRECT-MAIL-DECAYING.md) §2b.

**Why it is on the list despite thin evidence.** It is the **smallest build** — the V4 appraisal
PDFs already render, 184 of them exist on disk. It is the cheapest to trial. And it is the only
option where the physical object is meant to be *rare*, which is the one property none of the others
have.

**Why it probably is not the whole answer.** ~480 pieces a year at n=40/month will take a very long
time to produce a readable signal, and its entire evidence base is one practitioner, extensively
repeated across two libraries under two different names. (⚠ Brain 1 correction: u0048 and u0737 are
**both Mat Steinwede** — same person, two libraries. Do not read as two sources agreeing.)

---

## Two targeting lists that cost nothing, and are in none of the options above

Both surfaced late, from the Australian channel. Both are **one database query**, need no browsing
data, and can be layered onto any option as its list.

**A. Homes bought 12–36 months ago.**

> *"When buyers resell, 80% do not use the agent they bought off… the highest I've seen is 50% sell
> within 12 to 36 months… if there was 100 sales in your service area last year… at least 20 of them
> are going to come to market 12 months from when they bought the property."*

Unsourced, and the stated tax reasoning is shaky. But Fields holds sale dates for every property in
four suburbs plus **53,313 historical sale events** — "bought 12–36 months ago" is a one-line
filter. And the buyer has **no incumbent agent relationship to displace**, which is the constraint
that makes most seller prospecting hard. Cheapest hypothesis on the page to test.

**B. Withdrawn and expired listings, re-checked monthly for six months.**

Brain 1 names expired/withdrawn as the **#1 cold-start channel** — *"my number one way to jumpstart
your career"* — for the obvious reason that these are demonstrated, motivated sellers inside a
45–90 day window. eXp's version is the follow-up discipline: *"if they list with somebody else, I
have a follow-up campaign that… reminds me every month for six months to keep checking their
listing."*

**This is a data-identification problem, which is the one thing Fields is structurally better at
than any individual agent.** The withdrawn-detection pipeline already exists (steps 103/104/111).

**C. And one more, free because we have no boards of our own:** mail around **other agents'** sold
events, not just our own. The corpus justifies it with an unsourced 60/40 split, but the logic
stands on its own — and since Fields has no signboards anywhere, it is the *only* version of this
play available to us. We hold every agent's events.

---

## What composes with what

Options 1–5 are not mutually exclusive. Three combinations are coherent:

| Combination | The logic |
|---|---|
| **1 + 5** ⭐ | Monthly article sequence to warm engagers; the heavy posted appraisal reserved for the ones who scan or return. Cheapest, fastest, best-evidenced. **~$6,800/yr** |
| **2 + 3** | Choose one bounded farm, then let real listing events inside it generate the fortnightly rungs. The event ripple gives the farm the *because* it otherwise lacks. **~$25,000/yr** |
| **4 + 1** | Standing quarterly report as the floor, the warm trigger sequence layered on top when someone looks themselves up |

**Arms that bolt onto any option** (each needs its own code and its own holdout):

- **Fridge magnet.** Zero evidence — the "78% recall after 12 months" figure traces to companies
  that sell magnets. But the artwork is **already print-ready** (CMYK vector, 4 products,
  manufacturer spec), it fits a C5 envelope, and it is a coherent hypothesis: measured mail lifespan
  is **7.6 days**, and the selling trigger is unpredictable, so an object that defeats that clock is
  worth testing. **Ship it as a tracked experiment with its own QR destination, not as a tactic.**
  Recommendation from the original scoping stands: **hold it back as a reward for engagement** rather
  than spending a long-lived asset on a cold contact.
- **Quarterly report** as the annual high-effort rung. Generic (41 pp, print-ready), so it does not
  carry the per-address personalisation that does the work — it is a credibility object, not a
  response device.
- **Handwritten address / hand-signed.** OR 1.25 and OR 1.24 — real, replicated, modest. Feasible at
  pilot scale, not at 1,200/month. **Skip stamps** — that one is a well-powered null.

### One format decision is already settled — it goes in an envelope

Three independent lines agree, two of them controlled:

- **Cochrane/Edwards 2009 RCT:** double postcard vs one page in an envelope, **OR 0.47** — roughly
  halved response.
- **Canada Post's own neuroscience** ranked the postcard **worst of five physical formats**, below
  email-on-a-phone — a pro-mail study contradicting the pro-postcard folklore.
- **An Australian operator watching what physically happens:** *"my one isn't there… because we put
  ours in an envelope, whereas the rest of theirs are printing them and just sticking it in the
  letterbox. Which means that of these tenants… they were never taking it inside. It just stayed in
  the letterbox, whereas mine made it inside."*

The same operator reports switching from mass unaddressed drops to **a monthly enveloped market
report** and going from *"maybe one a year from drops"* to *"consistently getting probably three
prizes a month."* Self-reported, no control — but it is precisely the hypothesis this programme
would test.

**This kills the postcard concept in `00_SCOPING.md`.** It is also the cheapest decision here,
because it costs nothing to make correctly at the start and everything to discover later.

---

## Recommendation

**Run Option 1 + 5, inside Option 0's gates, and prototype Option 3 on sold-only events.**

The reasoning is short:

- **Option 1 is the only option whose population is getting better for free.** 16 addresses a day, off
  organic search that is compounding 4× a month. Warm beats cold by 8×, and this is the only lever on
  the page that touches that variable.
- **It is also the cheapest thing that can produce a readable result** — ~$3,800 and eight weeks
  against ~$18,000 and six months.
- **Option 3 has been upgraded and is now arguably the lead, not the prototype.** With the
  *"would you like me to let you know what it sells for?"* opt-in on piece 1, it becomes the
  **cheapest route from cold to warm that exists on this page** — and warm is an 8× swing. It also
  converts the programme from unsolicited to solicited, which repairs the weakest link in the legal
  analysis (APP 7.3 impracticability) rather than arguing around it. Prototype it on **sold and
  withdrawn events only**, which sidesteps the appointed-agent conflict entirely while keeping the
  mechanic intact.
- **Note what Options 1 and 3 have in common, because it is the actual strategy:** both work by
  making the list warmer rather than bigger. Option 1 harvests warmth that organic search is already
  generating for free; Option 3 manufactures it with a single tick-box. Everything else on this page
  spends money mailing strangers.
- **Option 2 stays available.** Nothing about starting warm forecloses the farm; the farm forecloses
  nothing either. But spending $18,000 on the weakest-evidenced option while a free warm list
  accumulates untouched is the wrong order.

**And the number that should frame the whole decision:** roughly 1,400–1,700 listings a year in
catchment, at ~$30,800 gross commission each. **Fifteen listings — a 1% share — is about $460,000.**
Against a $4,000–18,000 programme, this does not have to work *well*. It has to work *at all*, and
we have to be able to tell whether it did.

That last clause is the whole of Option 0.

---

## The three questions only you can answer

1. **Is the trigger "they looked up their own address", or "they engaged deeply"?** The first works
   today and gives ~16 addresses/day. The second needs a build and yields far fewer, better ones.
   This decides the volume of everything.
2. **How long are you prepared to fund before the first listing?** The corpus says 3–6 months to a
   first inbound appraisal request and ~2 years to a named household listing. Opower says a two-year
   programme is 2.5–4.2× more cost-effective than a short one. **If the answer is under 12 months,
   Option 5 alone is the honest choice** — everything else needs a runway it would not have.
3. **Are you comfortable posting unsolicited mail about someone's home to an address we obtained by
   scraping?** Not the legal question — the legal question goes to a lawyer. The brand question.
   Every option here rests on it, and it is the one thing no amount of research can settle for you.
