# The Home Hub — User Jobs, Competitor Failures, and Where Fields Can Actually Win

**Status:** Internal evidence dossier. **Not for publication.** See `03_CLAIMS_REGISTER.md` before any of this reaches public copy.
**Compiled:** 2026-08-06 (AEST)
**Purpose:** The V4 `/off-market/:slug` redesign turns the page into a landing page for **"Your Home's Hub"** — a claim-your-home product for a specific address. This document assembles the best evidence we hold that the Hub answers questions competitor products do not, organised by the **job the visitor is trying to do** rather than by research source.

**Evidence base:** the eleven files in `../Research/`. Every claim below carries a pointer. Where two files disagree, both readings are given.

---

## How to read this

**Grades used throughout:**

| Grade | Meaning |
|---|---|
| **P** | Primary — company filing, regulator, portal's own page, our own database |
| **J** | Named journalism or industry press with author and date |
| **V** | Consumer verbatim, attributable to a named handle at a dated URL |
| **B** | Our own measured behaviour (PostHog / GSC / Mongo) |
| **INF** | Inference or argument by this document, not a sourced claim |

**Two standing cautions.**

1. **Complaint frequency is not problem value.** `EVIDENCE_consumer_voice.md` §4.8 makes this point against its own data: filter complaints are the highest-*count* theme and probably the lowest-*value* one, while thin listings produced almost no complaints and a doubling of search duration. Rank by consequence, not by volume.
2. **Nearly every consumer corpus here is self-selected or topic-sampled.** ProductReview draws people angry enough to seek out a complaint site; PropertyChat is investors, not the general public; the Reddit corpus is explicitly "indicative of relative emphasis within this sample only… not population estimates." No percentage in this document describes "Australians."

---

## 0. The thesis in one paragraph

Australia's portals are not broken as browsing tools — 480,000+ app-store ratings averaging 4.5–4.8 refute that outright (`consumer_voice` §3.0). They are broken as **answering** tools, and the specific failure is that they produce **numbers without adjudication**. A homeowner can already read three competing automated estimates off the Google results page before clicking anything (`own_address_search_intent` §6.1.2). What nobody supplies is a reason to believe one over another — and the reason nobody supplies it is structural: REA earns roughly four in five dollars from selling placement to agents and vendors, earns nothing from consumers, owns the estimate (PropTrack), owns the surfaces (realestate.com.au and property.com.au), and reports a homeowner's engagement with that estimate to shareholders as a **"seller lead delivered to our customers,"** with better-paying agents receiving 36% more of them (`structural_conflict` A1/A3/C3). **The Hub is the same feature under the opposite business model.** That sentence is the entire pitch, and every element of it comes from REA's own disclosures.

---

## 1. Three findings that constrain everything downstream

### 1.1 The *feature* gap is closed in Australia. Do not pitch on novelty.

This is the single most important constraint on V4 copy, and the easiest thing to get wrong.

| Capability | Already exists in AU? | Evidence |
|---|---|---|
| Estimate on every address including off-market | **Yes** — Domain Home Price Guide, REA realEstimate (PropTrack), property.com.au, view.com.au, propertyvalue.com.au | `international_comparison` §6.1 [J/P] |
| Claim-your-home / owner dashboard | **Yes** — REA Property Owner Dashboard | `international_comparison` §6.2 [J] |
| Owner correcting property attributes | **Yes** — and owners are actively encouraged to, because it feeds the estimate | `GTP_market_analysis` L1492 [T] |
| Privacy reassurance on address search | **Yes** — REA "prominently reassures users that their address will not be shared with third parties" | `GTP_market_analysis` L1460 [T] |

REA's published usage: **3 million properties tracked by their owners**; **600,000 owners viewed their dashboard in a single month**, up 43% YoY; and **40% of REA listings were tracked by their owner before going to market** (`international_comparison` §6.2 [J], ⚠ the "October" year is unpinned in the retrieved snippet — verify before external use). REA's filings show owner-tracked properties rising 3.8m → **4.5m** FY24→FY25 (`structural_conflict` C3 [P]).

**Any sentence beginning "no one in Australia does this" is false and checkable in thirty seconds.** The novelty is not the feature. It is the accountability, the workings, and the absence of a lead-resale motive.

### 1.2 The job is adjudication, not valuation

The strongest single artefact in the entire evidence base, quoted in full because its power is in the list:

> "Hi all I have been trying to estimate what my property is worth. Below are the estimates for one of my properties from 5 different estimate sites. The lowest - $382k, highest $704k. Domain $470k, $545k, $620k Real estate.com $420,000 - $540,000 Propertyvalue.com.au : $445,000 - $533,000 Vali.com.au : $576, $640, $704k CommBank: We estimate your market price as $448,000. It may range between $382,000 and $466,000. Onthehouse.com.au $450-500k **When brokers ask me what my house is worth, I have no idea, given the range of estimates.**"
> — r/AusProperty, 2022-03-31, via `research_intent/B_reddit_motivation.md` [V]

An **84% spread** on one house. The stated outcome is not "I picked one." It is "I have no idea."

A seventh estimate adds nothing to that person's life. **The unmet job is a defensible reason to prefer one figure — which is a method problem, not a data problem, and it is exactly what an adjusted-comparables approach with visible workings can do and a black-box AVM structurally cannot.**

Corroborated independently three ways:
- **PropertyChat's controlled comparison.** Two near-identical adjacent apartments; the *smaller* one valued **$137k higher** by REA, and the two portals rank them in opposite orders (`ADDENDUM_propertychat` §1 [V]).
- **Autocomplete's trust hedges.** `actually worth`, `really worth`, `fair market value` — people encoding distrust into the query itself. Plus a distinctively Australian pattern of naming an institution: `domain`, `corelogic`/`cotality`, `westpac`, `commbank`, `anz` (`research_intent/D` [P]).
- **The SERP.** All 12 SERPs carry a dollar figure before any click; automated estimates on 10/12, and on off-market addresses **4/4** — property.com.au `$1,836,000`, propertyvalue.com.au `$1,800,000 – $2,000,000` (`research_intent/A` [P]).

### 1.3 The conflict is structural, primary-sourced, and unavailable to any incumbent

From REA Group's own ASX filings (`structural_conflict` A1, A3, C3 — all [P]):

- Group revenue FY25 **$1,673m**; Australian residential listing advertising alone **$1,156.2m = 69.1%**; residential + commercial listing advertising **$1,374m = 82.1%**.
- **There is no consumer-paid revenue line.** REA's word for agents throughout its results announcements is *"customers."*
- Growth is price, not volume: H1 FY26 residential revenue **+7% while national listings fell 6%**, on **+14% buy yield**.
- REA owns **PropTrack** (the estimate), **realestate.com.au and property.com.au** (the two consumer surfaces where an owner looks it up), and **CampaignAgent** (which lends vendors the money to pay REA's own advertising fees).
- Seller leads YoY: **+37% FY24, +55% FY25, +38% H1 FY26.**
- CEO Owen Wilson, FY25: *"Our particular focus on **engaging owners** helped drive a significant increase in **valuable seller leads delivered to our customers**."*
- Lead volume is tiered by agent spend: *"Pro customers received 36% more seller leads than those on a flexi subscription"* [J].

**Read plainly: REA's claim-your-home product is a lead-generation funnel, and the company describes it as one to shareholders.** A consumer spontaneously identified the same shape from the outside — on REA-owned PropTrack publishing research that advertising on REA is worth +4.3%: *"So realestate.com.au did a study into themselves and found that their website gets you a better result than not using their website? Bit of a conflict of interest there don't you think?"* (`ADDENDUM_propertychat` §5.3 [V]).

**Discipline note.** `structural_conflict`'s own inference section is emphatic that *"they therefore withhold information from consumers"* does **not** follow from the revenue model and is undocumented. What *is* documented is (a) ranking by payment and (b) lead monetisation of consumer curiosity. Use those two. They are enough.

---

## 2. The jobs

Eight jobs, ordered by evidence strength. Each carries: the job in the user's words · what they get today · where it fails · what Fields can do **today / partially / not yet** · what that means for the page · what would falsify it.

---

### J1 — "Six numbers and no way to choose between them"

**In their words.** The 84% spread post above [V]. And a first-time seller on the southern Gold Coast, 2025-12-09, holding four numbers on one address — bank **$930K**, agent pre-appraisal **$925K**, guide **up to $950K**, market offers **$885–900K** — plus a named near-identical comparable at **$870K** that they are *manually adjusting* for view, land size, carport and covered outdoor area:

> "Agents are saying the two higher ones are good offers and consider taking them but that just seems crazy given that my place is worth a lot more than the similar one in land and improvements/extras. Plus I have the amazing view and it had none… I'm older, so I am concerned that if I screw this up, I screw up things for myself going forward."
> — r/AusProperty, 2025-12-09, via `research_intent/B` [V]

That is our comparables method, performed by an anxious amateur, at the worst moment of their life. Note the fear: not losing money — **being the person who got it wrong.**

**What they get today.** Between three and six point estimates or ranges, all unexplained, from PropTrack/REA, Domain, property.com.au, propertyvalue.com.au (Cotality), onthehouse.com.au, and their bank. Three of those are the same company (`structural_conflict` A3 [P]).

**Where it fails.** No portal shows which sales the number was built from, what adjustments were made, or why they disagree. `Rique`, 2024-02-07: *"I find that Domain estimates and REA always **lag (3-4 months)**"* [V]. Reddit persona weights put **Comparable Hunter ~53 posts** and **Agent-Number Sceptic ~39** among the four strongest (`research_intent/B`).

**What Fields can do.**
- **Today:** show the comparable set, count reviewed vs retained (e.g. "41 sales reviewed, 8 retained"), and publish the method's **11.1% historical error rate** (`GTP_market_analysis` [P-internal]).
- **Partially:** a comparable **range** exists on only **7% of sold addresses** (221 / 2,947), **44%** of for-sale, **23%** of under-contract (`first_party_fields_data` §4 [B]). **This is the binding constraint on the whole product.**
- **Not yet:** the per-comparable working. `adjusted_price`, component adjustments and weights **are not persisted**, so the detailed block cannot render — described in the session review as *"a genuine release blocker"* (`GTP_market_analysis` L1051–1066).

**What the page must do.** Show *reconciliation*, not another figure. Design the **no-range state as the primary state** — it is 93% of sold addresses, not an edge case.

**Falsifier.** If a range-present page shows no better trust or onward action than a range-absent one, the whole "show the workings" thesis weakens. Never A/B tested (`first_party_fields_data` §7.4).

---

### J2 — "Is this priced fairly?"

**In their words.** Previously logged as a latent need never spoken aloud. **That was wrong**, and the correction matters:

> "What will you pay for the following properties — [two Domain listings]. I have realized that the price estimate reports from CoreLogic and different banks are **almost always inaccurate**. Posting the properties here to understand the public sentiment and what people are willing to pay."
> — `KeepHustling`, 2023-03-13, PropertyChat [V]

> "I'm looking at a few properties with what I believe have unrealistic asking prices… Asking price 970k for one of them but domain and realestate.com have them at around the 650k to 900k… I think a fare price would be low 800s."
> — `Property Baron`, 2020-06-24 [V]

People **do** articulate this. They ask *other humans*, after explicitly rejecting the portal's estimate (`ADDENDUM_propertychat` §4, which supersedes `consumer_voice` §4.6).

**What they get today.** Nothing. **No portal in any market flags a listing as overpriced against its own comparable analysis** — not Zillow, Redfin, Rightmove, Zoopla, REA or Domain (`international_comparison` §5.4, targeted search). Redfin publishes an editorial *how-to* teaching consumers to work it out themselves — a tacit admission the product doesn't.

**Where it fails.** The gap is not technical. Any portal showing an AVM beside an asking price is one subtraction away. **The reason it doesn't exist is that every major portal is funded by the agents who set those prices.**

**What Fields can do.** Feasible where a range exists (44% of for-sale). Bounded by Rule 5: no advice, no single-figure headline. The honest form is *"comps say $1.75M–$1.98M; asking is $2.15M"* — a gap, stated, reader draws the conclusion. That framing is already permitted in FB ads under the 2026-07-27 update.

**What the page must do.** This is **the** standout opportunity: the only capability found anywhere that is simultaneously feasible for us, globally absent, and structurally off-limits to incumbents. Treat it as the flagship, subject to J1's coverage ceiling.

**Falsifier.** If sustained flagging draws agent-side legal pressure we can't absorb, or if our range is wide enough that "overpriced" is unfalsifiable at our confidence levels. Both are live risks.

---

### J3 — "It moved $100k and nobody will tell me why"

**In their words.**

> "In the last 3 months my house has dropped 40k increased 50k and dropped 40k, is this even possible" — `Mr G` (WA) [V]
> "Most terrible algorithms. My property went down by about 700k in 1 Month." — `Bilal N.` [V]
> "My house keeps going down while neighbour house keeps going up. Both properties exact same size block." — `Bilal N.` (NSW) [V]

And note the direction — distrust is not fixed by a *flattering* number:

> "We've owned our property for 11 months now and apparently has gone up 100k in value since. **Is this reliable estimate because it just seems... unbelievable.**"
> — r/AusProperty, 2026-01-18, via `research_intent/B` [V]

**What they get today.** REA positions owner tracking around *monitoring* estimated value and recent local sales. The value moves; no explanation is attached.

**Where it fails.** The grievance is almost never "the number is imprecise." It is **(a) volatility**, **(b) relative injustice** — why is my neighbour's higher on an identical block — and **(c) no recourse** (`consumer_voice` §3.3).

**What Fields can do.**
- **Today:** we hold historical valuation runs. A stability metric — *"our estimate for an unchanged home moved less than X% median over 12 months"* — is computable now and is a claim no portal makes (`consumer_voice` §5.4).
- **Not yet:** a per-address change narrative ("this moved because 12 Something St sold in April").

**What the page must do.** This is the clearest argument for a **Hub** rather than a page. Per the session review: *"REA explicitly positions owner tracking around monitoring estimated value and recent local sales… **The static answer is valuable; the living answer is defensible.**"* (`GTP_market_analysis` L1582). A hub whose job is to narrate its own movements is the sharpest available form of "adjudication, not valuation."

**Falsifier.** If our own estimates prove as volatile as theirs, this claim inverts and becomes an attack surface. **Measure before we say it.**

---

### J4 — "It's wrong about my house and there is no way to fix it"

**In their words.**

> "I contacted them to get a true reflection and after over 20 emails back and forward they said they couldn't or wouldn't change it." — `Stephen B.` [V]
> "Our home is stunning and has everything you could ever want, yet it still shows as vacant land." — `SCL` (QLD) [V]
> "We are the owners of a house that has incorrectly been listed as sold for an incorrect price." — `Robert K.` [V]
> "Type the address in Google and it will bring up 3 real estate websites for that address. **The photo of the house is the one next door.** I drove past to confirm this." — r/AusProperty, 2026-07-12 [V]

And the seller version, which is commercial harm rather than annoyance:

> "The undervalued estimate value **puts pressure on the seller to come down to their estimate**… The site refused to remove their massively undervalued estimate when asked to do so. **They advised that I needed a real estate agent to value my property.**"
> — `tilt10`, 2023-03-09, PropertyChat [V]

The portal's remedy for a wrong number about your home was to route you into its revenue funnel.

**What they get today.** Attribute editing exists on REA (and feeds the estimate). What does not exist is a *response* — every reviewer in this cluster reports that nobody replied.

**Where it fails.** Two distinct failures: no correction pathway for facts, and no recourse for the estimate. `research_intent/B` names the second-order cost precisely: incoherent status or history on an address page *"does not read as 'bad data' — it reads as 'something is wrong with this house.' A listing-status bug is a trust bug."*

**What Fields can do.** **This is the strongest argument for *claiming* specifically.** Claiming means the owner can correct a fact and **watch the working change in front of them** — which is the thing that has never been offered. Not yet built.

**What the page must do.** Make correction visible and consequential, and show the owner what changed as a result. Data-quality on our own side is a prerequisite: `research_intent/C` records one visitor who spent three sessions and ~50 keystrokes over an hour failing to reach `120 Glen Eagles Drive, Robina` — never trying the two-word form, never getting a result.

**Falsifier.** If corrections arrive at a volume we cannot verify, the pathway becomes a liability rather than a feature. Needs a moderation model before launch.

---

### J5 — "Can I get this house?"

**In their words.** Google's own refinement data across 12 real address SERPs — every one of the 22 "People also search for" suggestions was `<exact address> + modifier`:

| Modifier | Count |
|---|---|
| **for sale** | **8** |
| history | 4 |
| owner | 4 |
| rent | 3 |
| **price** | **2** |
| reviews | 1 |

**5 of the 8 `for sale` refinements were on addresses that are not for sale.** Price ranks fifth of six (`research_intent/A`).

**Where it fails.** Every incumbent answers "no / not listed / here's an estimate instead." And for off-market addresses the results page barely functions: **only 40% of the top 10 are about the queried house** (vs 82% sold, 78% for-sale); 43% drift to neighbours and the street; 18% are unrelated, including `11 Placid Court, Narangba QLD 4504` — 80 km away, at position 6.

**What Fields can do.** **Today, and this is the most winnable surface we have.** We already rank **#3, above Domain at #4**, on one off-market address — on the snippet *"Last recorded sale. $175,000. Oct 1990. Held for 35.7 yrs"* — while our for-sale page ranked #6 on boilerplate *"Property report with valuation, comparable sales, and market intelligence."* The specific verifiable fact beat the marketing sentence. Off-market is where relevance beats domain authority.

**Caution.** ⚠ n=22 suggestions from 12 SERPs. Directional, not precise. And `for sale` intent on a *not-for-sale* home is ambiguous — it may be a buyer, not the owner. See §3.

**Falsifier.** §6.3 of `own_address_search_intent` flags the open question honestly: the history snippet may perform because it is **specific, verifiable and unique to the address**, not because sale history is the job. Testable, untested.

---

### J6 — "Is it exposed?"

**In their words.** `does burleigh waters flood` is the **single most persistent suggestion in our entire stored corpus at 546 — 2.5× the next item (219)** — and the only question-form entry near the top (`own_address_search_intent` §4). Independently, the `is my house ` autocomplete seed is almost entirely non-valuation: flood zone, bushfire, heritage listed, asbestos, brick veneer, elevation, orientation, solar suitability, NBN (`research_intent/D`, category G, 71 suggestions).

> "Houses throughout multiple LGA in SEQ now have insurance costs 10-20k+ a year… **Yet houses 4m below the flood level are selling for 90-95% of those that don't. It's also not a selling point in any of the hundreds of listings I checked.**"
> — r/AusProperty, 2026-05-21 [V]

**This resolves an apparent contradiction in our own evidence.** `consumer_voice` §4.5 found **no** consumer complaining that a listing omitted flood risk, across three independent source families. The resolution: **people don't complain to the portal — they go to Google instead.** Absence of complaint was mistaken for absence of demand.

**What they get today.** Nothing on the listing. UK listings show surface-water flood risk as a regulated standard (National Trading Standards Material Information Part C, guidance Nov 2023), alongside council tax band, EPC, broadband and mobile signal. *"Australia is an outlier among comparable countries in not having reliable public data on property-level flood risk"* (The Conversation, via `international_comparison` §6.4). Queensland's Property Level Flood Information Portal is opt-in, 39 councils. Flood is **not** a mandatory disclosure item under QLD's seller disclosure regime.

**What Fields can do.** We already hold `config/flood_context_burleigh_waters.md`. Suburb-level context today; address-level where council data supports it. Must follow Rule 5 — data, source, limitations, no advice.

**Cautionary precedent.** Trulia built crime layers, showcased them at the White House in 2012, and **withdrew them in early 2022** on fairness grounds; Redfin declined outright. Not every "more data" feature is a win. Flood is defensible on measurement grounds in a way crime is not — but the source and its limits must be on the page.

**Falsifier.** Persistence is not volume. 546 is a signal warranting direct measurement, not a demand figure (`own_address_search_intent` §7).

---

### J7 — "Let me look without being caught"

**This is the job that most threatens the V4 concept, and it deserves the most care.**

**In their words.**

> "Has anybody else noticed a TON of letterbox drops from people asking to buy your house… It's almost every 2nd day now. **The purchase prices I've seen for my place is insane too, no way am I selling however.**"
> — r/GoldCoast, 2021-08-25, 47 upvotes, 42 comments [V]

> "…**are they allowed to grab our PII from public land records and craft a false statement like this legally?** I feel like this surely should conflict with the Privacy act..."
> — r/AusProperty, 2025-04-08, 62 comments [V]

> "I've had 3 different agents calling me casually 'how is house x going for you?'. **How do they know I own this property and where are they getting my phone number?**"
> — r/AusProperty, 2026-05-05 [V]

**`research_intent/B` searched specifically for positive reactions to unsolicited approaches and found none: "The corpus contains zero posts where an unsolicited approach produced a positive response. A 'we found your house' framing carries real risk on this evidence."**

**Our shipped card 0 is headlined "We found your home."** (`offmarket_discovery`, `engine_version: disc-v1`.) That is a direct, evidenced conflict with the strongest negative finding in the corpus, and it is the most actionable single item in this document.

**The tension resolves more precisely than "privacy is a risk."** `research_intent/B` also searched for discomfort that a public page about one's address exists and found **none** — *"Not one post expresses discomfort that a public page about their address exists."* PropertyChat's majority view agrees: *"every property in Australia is listed like that now, it's public information."* The discomfort is about **two specific things**:

1. **Being contacted.** *"Will an agent call me? Am I declaring that I am selling? Will my details be passed around? Can I look without being pursued?"* (`GTP_market_analysis` L1617–1627.) REA's own address product prominently reassures users their address won't be shared — because this expectation is mainstream (L1460).
2. **Derived financial inference.** The one clear privacy violation in the corpus is not the estimate — it is what sat beside it: *"what absolutely floored me was they had even estimated **what we owe on it**"* (`Fernfurn`, PropertyChat [V]). And socially: *"My family won't be happy and will absolutely think that I've lost the plot when they see the price."*

**What this means for a claim-your-home product.** Claiming is, by construction, identifying yourself — which is the thing this job is trying to avoid. That is survivable only if claiming **confers control instead of extracting it**:

- **The page answers first, in full, before any ask.** Claiming is never the price of entry.
- **"Nobody calls unless you ask" must be an operational rule, not copy.** The session review is blunt: *"may be one of the most commercially valuable lines in the entire Fields experience — provided it is absolutely true operationally."*
- **Public-record side of the line only.** No derived financial inference — no equity estimate, no implied mortgage balance.
- **Change the opening.** Not "we found your home." The owner should feel they arrived, not that they were located.

**And the strongest superiority claim we have lives here:** claiming your home on realestate.com.au converts you into a seller lead delivered to whichever agent pays most — REA reports the growth rate to shareholders. Claiming with Fields costs you nothing and contacts no one. That contrast is defensible entirely from REA's own filings.

---

### J8 — "Could a move actually work from here?"

**In their words.** The strongest Reddit persona by volume is the **Equity Checker (~115 posts)**:

> "Check the upper end value of your home on sites like domain and property. Call your bank and request an updated AVM. **Try to hit the maximum number the bank will accept** (usually top price on domain or property). If you are successful you may have changed your LVR which may in turn allow you to negotiate better rates…"
> — r/AusFinance, 2026-05-21 [V]

> "Right now I'm pulling loan balances manually and using Domain estimates to get a rough equity figure. It works, but it's not exactly a clean picture."
> — r/AusProperty, 2026-04-13 [V]

Plus **Pre-Sale Sizer-Upper ~51**. And from our own homeowner work, the highest-emotional-weight concern is the re-entry problem — *"If I sell, I won't be able to get back in"* — which the session review notes is *"primarily a logistics problem, not simply a valuation problem"* (`GTP_market_analysis`).

**Where it fails.** Nobody joins the value of the home to the feasibility of the move. The mini-site V2 Session 2 is our attempt; the session review flagged that the current framing conflates sale-value band with buying budget and ignores mortgage balance, sale costs, transfer duty, borrowing capacity and cash reserves — *"This could be confronting or misleading."*

**What Fields can do.** **Not yet, and the review's warning should be respected.** This is where the Hub eventually earns a returning visitor, and it is also where we could most easily mislead. It is a V4+ item, not a launch item — and it collides directly with J7's privacy line, since equity inference is exactly what triggered the one clear privacy complaint we hold.

---

## 3. Who is actually on the page — and why the copy cannot assume

Our own data cannot distinguish the visitor at all. `research_intent/C`: *"Owner, neighbour, prospective buyer, valuer, nosy local — nothing in the data distinguishes them."* The only direct probe, the `offmarket_menu_*` chips, has fired **nine times in total**.

The session review names seven plausible searchers: owner checking value · owner considering a move · financially curious owner · **correcting owner** · neighbour · prospective buyer · tenant/former resident/family member — and warns that *"searching the address is a strong property-connection signal, but it is not definitive proof of ownership or selling intent."*

**Two evidence-backed resolutions:**

- **Ownership lookup is NOT a job.** Google lists `owner` 4× in refinements, but two independent sources kill it: the `who owns ` autocomplete sweep returned 260 suggestions, **all corporate** (Coles, Bunnings, Optus) with zero residential; and the buyer-side "what did the current owner pay" question returns **0 hits in 4,349 Reddit posts** and 1 of 1,336 in live RSS (an in-laws gifting post). The `+owner` refinement is Google's generic entity template. **Do not build an ownership or occupancy surface on it.**
- **"Not selling" is not low intent.** *"A homeowner may have strong interest in value while having no immediate intention to list"* (`GTP_market_analysis` L1537). Zoopla's **6 million** MyHome users against ~24–25 million UK dwellings are overwhelmingly not selling. The Hub's audience is the 100% of homes, not the 3–5% transacting.

**Recommendation on the open question.** Build the Hub as a **persistent homeowner utility that is also the seller on-ramp** — not a seller on-ramp wearing a utility's clothes. Three reasons: the living answer is the defensible one (§J3); the largest stated personas are equity and feasibility, not listing (§J8); and a page that reads as a seller funnel triggers J7 directly. The mini-site V2 sessions remain the high-intent product downstream. **This is a decision for Will, recorded here as a recommendation, not as settled.**

---

## 4. What we cannot deliver yet — the honest constraint register

Any superiority claim must survive this list. Every item is from our own records.

| # | Constraint | Evidence | Consequence |
|---|---|---|---|
| C1 | **Comparable range exists on 7% of sold addresses** (221/2,947), 44% for-sale, 23% under-contract | `first_party_fields_data` §4 [B] | Any layout assuming a range is blank on 93% of sold pages. **Coverage, not design, is the ceiling.** |
| C2 | **Confidence labels are inverted in parts of the backtest and must not be published** | `GTP_market_analysis` L1026 | Publishing a label now would repeat the exact failure we criticise (see C3) |
| C3 | A "high accuracy" Domain band that **excluded the actual sale price** | `ADDENDUM_propertychat` §1 [V] | An uncalibrated label is **worse than none** — it converts inaccuracy into a demonstrated false claim. `valuation_backtest.py` must show what share of real sales fall inside each stated band **before** any label ships |
| C4 | `adjusted_price`, component adjustments and weights **not persisted** | `GTP_market_analysis` L1051–1066 | The "show the working" block cannot render. Called *"a genuine release blocker"* |
| C5 | **Address search tolerates neither spacing nor typos**; ~⅓ of typed addresses fall outside our three suburbs | `research_intent/C` [B] | One visitor failed across three sessions and ~50 keystrokes on a two-word street name. `result_count` populated on 5 of 184 events — we cannot even measure the failure rate |
| C6 | **Samantha persists nothing** | `research_intent/C` [B] | Zero real visitor questions exist to mine. The richest possible source of address-level intent is discarded at runtime |
| C7 | **PostHog holds zero break-glass events** since launch despite `BreakGlass.tsx` calling `phCapture` | `own_address_search_intent` §8 | A feature shipped to learn something cannot report |
| C8 | All off-market behavioural rates rest on **17 days**, n=266 people | `research_intent/C` | Nothing about the deck is statistically settled, including the arm gap |
| C9 | `sale_price` stored as a **string**; confidence values are `very_low` with an underscore, plus `directional` | `first_party_fields_data` §5 [B] | Numeric Mongo predicates silently match nothing |

---

## 5. Where the evidence contradicts the page we have shipped

Not opinions — each is a measured or quoted conflict with `offmarket_discovery` / `disc-v1`.

| # | Shipped behaviour | Evidence against | Action |
|---|---|---|---|
| S1 | Card 0 headline **"We found your home."** | Zero positive reactions to unsolicited "we found your property" framing across 5,685 Reddit posts; three verbatim hostility artefacts (§J7) | **Rewrite.** Highest-priority copy change in V4 |
| S2 | `valuation` (11.7s dwell) and `buyer` (9.0s) sit at **positions 6 and 7** | Cards 1–5 are skimmed at **1.5–2.3s median** — scroll-past speed. Only ~17% / 14.5% of sessions reach the two cards anyone stops on | **Front-load.** The IA is inverted |
| S3 | The deck asks the visitor to advance | **47–57% never advance past card 0**; 56.9% of `deck_exit` sessions exited at `max_index_reached = 0` | **Card 0 must stand alone as a complete answer.** Everything after is optional depth |
| S4 | A menu / "what would you like to know?" affordance | `offmarket_menu_*` fired **9 times total**. Google never offers a qualifier (89.5% of address autocompletes return empty; zero semantic qualifiers), so the visitor has no practice declaring intent | **Answer without being asked.** No menu, no tabs |
| S5 | Boilerplate meta description | Our boilerplate page ranked **#6**; our specific-fact page ranked **#3, above Domain** | **Lead with a hard, checkable, address-specific fact** |
| S6 | No search box on the off-market page | Zero `address_search` events originate from an off-market page — we have **no evidence at all** about what these visitors would type | Instrument it, or accept the blind spot knowingly |

---

## 6. Two cautions the evidence insists on

**There is no delight anywhere in this corpus.** `research_intent/B`: *"Every emotional reaction to a value in the corpus is negative or anxious… **Zero delight.**"* This cuts directly against the V2 `Core_concept.md` ambition of "moments" and "reframing" — *"Actually… my home has strengths I never realised."* No evidence supports that response existing. The evidenced emotional state is **anxiety about being wrong**. A page designed to delight may be designing for a feeling nobody in the corpus reports having.

**The field is crowding.** At least six per-address data products appeared in the Reddit corpus in 2026 alone — Property Mate, dwell-wise.com.au, PropCheck, Homer, PropCred, Glasshouse. That is evidence of *perceived* demand and of competition, not of validated demand. We are not first.

---

## 7. Evidence gaps, ranked

| # | Gap | Why it matters | Cost |
|---|---|---|---|
| G1 | **Nobody has looked inside REA's Property Owner Dashboard or Domain's tracked-property view** | This is the spine of a "our Hub fixes theirs" argument and it is entirely missing. We have REA's shareholder metrics and Zillow/Zoopla help pages, and no feature-level account of what an Australian owner actually gets | Low — a manual walkthrough, or Bright Data |
| G2 | **Reddit is still blocked** | Largest hole in consumer voice. Three routes, all needing Will: Bright Data KYC (best coverage) · paid PullPush (archive to 2025-05-19 only) · official Reddit API app (cleanest if KYC unwanted). ⚠ PullPush issued an explicit refusal that was respected, not circumvented | Will's decision |
| G3 | **Are they owners, neighbours or buyers?** | Still inferred, never confirmed. One post-view question settles it | Very low — highest value per unit of effort |
| G4 | **Is the exit satisfaction or failure?** | 13.9% click-through and 87.5% single-pageview have identical telemetry for "found it and left happy" and "didn't find it" | Low |
| G5 | **Does a range beat a point estimate** for trust and onward action? | Never A/B tested. The entire "show the workings" thesis rests on it | Medium |
| G6 | **Actual search volume for `does burleigh waters flood`** | Persistence (546) is not volume | Low |
| G7 | **Current price-guide availability on the Gold Coast** | Only sourced figure is Brisbane-wide and from 2021. We hold the listings and the scrape history — we can compute and publish it as original research nobody else has | Low |
| G8 | **Claims needing a 60-second browser check** before publication | (a) paid placement carries no consumer-facing label; (b) portals withdraw the estimate when a home goes to market; (c) "Contact Agent" listings carry an embedded price; (d) REA's "only show properties with a price" filter now exists, which dates one of our criticisms | Trivial — and blocking |

---

## 8. Open decisions for Will

1. **Is the Hub a persistent homeowner utility or a seller on-ramp?** Recommendation in §3: persistent utility that is *also* the on-ramp. Determines the promise, the copy, and whether "not selling" reads as failure.
2. **How do we unblock Reddit?** Three options in G2.
3. **Do we do the incumbent-dashboard teardown (G1) before writing public-facing copy?** Recommendation: yes. It is the missing spine.
4. **Does "nobody calls unless you ask" become an operational rule?** If yes it is possibly the most valuable line in the product. If no, it cannot be said at all.

---

## Appendix — source map

| Source file | What it carries |
|---|---|
| `EVIDENCE_consumer_voice.md` | ProductReview / app store / Whirlpool / regulator corpus; the 4.8-vs-1.9 divergence; REA's own Property Seeker survey; the negative findings in §4 |
| `EVIDENCE_consumer_voice_ADDENDUM_propertychat.md` | 35 threads / 335 posts; the identical-units comparison; the "high accuracy" band that excluded the sale price; the privacy artefact; supersedes parent §4.6 |
| `EVIDENCE_structural_conflict.md` | REA/Domain filings, ownership map, ACCC, CoStar, paid-placement mechanics; **read its inference section before quoting anything** |
| `EVIDENCE_international_comparison.md` | Zillow / Redfin / Rightmove / Zoopla / Homes.com feature and accuracy evidence; the AU capability audit; the "nobody flags overpriced" finding |
| `EVIDENCE_first_party_fields_data.md` | GSC + PostHog baseline; **the coverage ceiling**; measurement traps |
| `EVIDENCE_own_address_search_intent.md` | Synthesis of streams A–D; design consequences; flood persistence |
| `research_intent/A_serp_intent.md` | 12 live SERPs; zero PAA; refinement modifiers; the 40% off-market relevance finding |
| `research_intent/B_reddit_motivation.md` | 4,349 corpus + 1,336 RSS posts; personas; the 84% spread; **zero positive unsolicited-approach reactions**; zero delight |
| `research_intent/C_first_party_behaviour.md` | PostHog deck funnel, dwell, arms, address-search failure, Samantha instrumentation gap |
| `research_intent/D_autocomplete_qualifiers.md` | 772 requests; the address-level qualifier void; the risk/hazard cluster; `who owns` negative finding |
| `GTP_market_analysis.md` | ⚠ **Misnamed.** Not market analysis — a GPT critique transcript of the mini-site V2 sessions plus one address-intent section. No competitor grievance evidence. Suggest renaming `GPT_minisite_session_critique.md` |

**Companion documents:** `02_COMPETITOR_CAPABILITY_MATRIX.md` · `03_CLAIMS_REGISTER.md`
