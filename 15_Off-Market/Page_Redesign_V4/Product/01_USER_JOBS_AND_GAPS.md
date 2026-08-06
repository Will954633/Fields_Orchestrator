# The Home Hub — Owner Jobs, Competitor Failures, and Where Fields Can Actually Win

**Status:** Internal evidence dossier. **Not for publication.** See `03_CLAIMS_REGISTER.md` before any of this reaches public copy.
**Compiled:** 2026-08-06 (AEST) · **Rescoped:** 2026-08-06 after scope drift into buyer/listing jobs
**Evidence base:** the eleven files in `../Research/`. Every claim carries a pointer. Where two files disagree, both readings are given.

---

## SCOPE — read this before adding anything

**In scope.** The `/off-market/:slug` page as a landing page for **one specific address**, whose single job is to convert **the owner of that home** into claiming it and creating their **Home Hub**. Everything in this document must answer: *what does the owner of this house want to know about this house, and what would make them claim it?*

**Out of scope.** Buyer jobs, listing jobs, and anything about homes that are on the market:

- "Can I get this house?" / availability
- "Is this listing overpriced?" — an off-market home **has no asking price**
- Price guides, underquoting, auction rules, search filters, listing depth tiers
- Anything whose subject is a *property for sale* rather than *a home someone lives in*

**One exception, tightly bounded.** Listing-side evidence is admissible **only** where it establishes *who pays the incumbents and what that buys* — because that is the argument for why an owner should not trust them about their own home. It appears in §1.3 and nowhere else. It never becomes a user job.

**Why this boundary matters.** The off-market page's whole premise is a home that is *not* for sale. The moment a job assumes an asking price or a buyer, it is describing a different product.

---

## How to read this

| Grade | Meaning |
|---|---|
| **P** | Primary — company filing, regulator, portal's own page, our own database |
| **J** | Named journalism or industry press with author and date |
| **V** | Consumer verbatim, attributable to a named handle at a dated URL |
| **B** | Our own measured behaviour (PostHog / GSC / Mongo) |
| **INF** | Inference by this document, not a sourced claim |

**Two standing cautions.**

1. **Complaint frequency is not problem value.** `EVIDENCE_consumer_voice.md` §4.8 makes this point against its own data: filter complaints are the highest-*count* theme and probably the lowest-*value* one, while thin listings produced almost no complaints and a doubling of search duration.
2. **Nearly every consumer corpus here is self-selected or topic-sampled.** ProductReview draws people angry enough to seek out a complaint site; PropertyChat is investors; the Reddit corpus is explicitly *"indicative of relative emphasis within this sample only… not population estimates."* No percentage here describes "Australians."

---

## 0. The thesis in one paragraph

Australia's portals are not broken as browsing tools — 480,000+ app-store ratings averaging 4.5–4.8 refute that outright (`consumer_voice` §3.0). They are broken as **answering** tools, and for a homeowner the specific failure is that they produce **numbers about your home without adjudication**. An owner can already read three competing automated estimates of their own house off the Google results page before clicking anything (`research_intent/A`). What nobody supplies is a reason to believe one over another — and the reason nobody supplies it is structural: REA earns roughly four in five dollars from agents and vendors, earns nothing from consumers, owns the estimate (PropTrack), owns the surfaces (realestate.com.au and property.com.au), and reports a homeowner's engagement with that estimate to shareholders as a **"seller lead delivered to our customers,"** with better-paying agents receiving 36% more of them (`structural_conflict` A1/A3/C3). **The Hub is the same feature under the opposite business model.** Every element of that sentence comes from REA's own disclosures.

---

## 1. Three findings that constrain everything downstream

### 1.1 The *feature* gap is closed in Australia. Do not pitch on novelty.

The easiest thing to get wrong, and checkable in thirty seconds by anyone reading our copy.

| Capability | Already exists in AU? | Evidence |
|---|---|---|
| Estimate on any address including off-market | **Yes** — Domain Home Price Guide, REA realEstimate (PropTrack), property.com.au, view.com.au, propertyvalue.com.au | `international_comparison` §6.1 [J/P] |
| Claim-your-home / owner dashboard | **Yes** — REA Property Owner Dashboard | `international_comparison` §6.2 [J] |
| Owner correcting property attributes | **Yes** — and owners are encouraged to, because it feeds the estimate | `GTP_market_analysis` L1492 [T] |
| Privacy reassurance on address search | **Yes** — REA "prominently reassures users that their address will not be shared with third parties" | `GTP_market_analysis` L1460 [T] |

REA's published usage: **3 million properties tracked by their owners**; **600,000 owners viewed their dashboard in a single month**, up 43% YoY; and **40% of REA listings were tracked by their owner before going to market** (`international_comparison` §6.2 [J] — ⚠ the "October" year is unpinned in the retrieved snippet, verify before external use). REA's filings show owner-tracked properties rising 3.8m → **4.5m** FY24→FY25 [P].

**Any sentence beginning "no one in Australia does this" is false.** The novelty is not the feature. It is the accountability, the workings, and the absence of a lead-resale motive.

### 1.2 The job is adjudication, not valuation

The strongest single artefact in the evidence base, quoted in full because its power is in the list:

> "Hi all I have been trying to estimate what my property is worth. Below are the estimates for one of my properties from 5 different estimate sites. The lowest - $382k, highest $704k. Domain $470k, $545k, $620k Real estate.com $420,000 - $540,000 Propertyvalue.com.au : $445,000 - $533,000 Vali.com.au : $576, $640, $704k CommBank: We estimate your market price as $448,000. It may range between $382,000 and $466,000. Onthehouse.com.au $450-500k **When brokers ask me what my house is worth, I have no idea, given the range of estimates.**"
> — r/AusProperty, 2022-03-31, via `research_intent/B` [V]

An **84% spread** on one house. The stated outcome is not "I picked one." It is "I have no idea."

A seventh estimate adds nothing to that person's life. **The unmet job is a defensible reason to prefer one figure — a method problem, not a data problem, and exactly what adjusted comparables with visible workings can do and a black-box AVM structurally cannot.**

**We hold a worked proof that our method does exactly this job.** `11_House_Mini_Site/_shared/Adjusted-Comparables-Evidence.md` (2026-08-05) — subject **26 Moorabbin Place, Robina**, sold 6 July 2026 for **$1,620,000**; 8 comparables selected from 32, every one sold *before* the subject, the subject's own sale excluded:

| | Low | High | Spread |
|---|---|---|---|
| Raw sale prices | $1,300,000 | $1,910,000 | **$610,000** |
| Adjusted for property differences | $1,398,872 | $1,673,126 | **$274,254** |

A **55% narrowing**, with the actual sale price falling inside the adjusted band. The sharpest illustration: the cheapest and dearest raw comparables — **$610,000 apart** — land **$43,939 apart** once adjusted (12 Kilburn Street $1,300,000 → $1,521,873; 31 Huntingdale Crescent $1,910,000 → $1,565,812), and every adjustment is itemised in dollars: one more bedroom +$113,110, 53 sqm more floor area +$95,034, better renovation −$96,032, extra bathroom −$89,036, second storey −$50,000.

> *"Three bedrooms, two bathrooms, sold nearby" is a match on labels. It gave a $610,000 range. Pricing what is actually different between the houses narrowed it to $274,000.*

**This is a statement about method, and only about method.** See C10/C11 in §5 — it is **n=1**, it compares our method against naive label-matching rather than against any portal, and a tighter spread is precision, not accuracy. Do not let it drift into a superiority claim.

Corroborated three independent ways:
- **PropertyChat's controlled comparison.** Two near-identical adjacent apartments; the *smaller* one valued **$137k higher** by REA, and the two portals rank them in opposite orders (`ADDENDUM_propertychat` §1 [V]).
- **Autocomplete's trust hedges.** `actually worth`, `really worth`, `fair market value` — distrust encoded into the query. Plus a distinctively Australian habit of naming an institution: `domain`, `corelogic`/`cotality`, `westpac`, `commbank`, `anz` (`research_intent/D` [P]).
- **The SERP itself.** Automated estimates appear on **4 of 4** off-market address SERPs — property.com.au `$1,836,000`, propertyvalue.com.au `$1,800,000 – $2,000,000` (`research_intent/A` [P]). *"Nobody has real facts about an off-market house, so everybody guesses — and Google surfaces the guesses. That is the vacuum."*

### 1.3 The conflict is structural, primary-sourced, and unavailable to any incumbent

*This is the one place listing-side evidence is admitted, because it establishes who pays.*

From REA Group's own ASX filings (`structural_conflict` A1, A3, C3 — all [P]):

- Group revenue FY25 **$1,673m**; Australian residential listing advertising alone **$1,156.2m = 69.1%**; residential + commercial **$1,374m = 82.1%**.
- **There is no consumer-paid revenue line.** REA's word for agents throughout its results announcements is *"customers."*
- Growth is price, not volume: H1 FY26 residential revenue **+7% while national listings fell 6%**, on **+14% buy yield**.
- REA owns **PropTrack** (the estimate), **realestate.com.au and property.com.au** (the two surfaces where an owner looks it up), and **CampaignAgent** (which lends vendors the money to pay REA's own advertising fees).
- Seller leads YoY: **+37% FY24, +55% FY25, +38% H1 FY26.**
- CEO Owen Wilson, FY25: *"Our particular focus on **engaging owners** helped drive a significant increase in **valuable seller leads delivered to our customers**."*
- Lead volume is tiered by agent spend: *"Pro customers received 36% more seller leads than those on a flexi subscription"* [J].

**Read plainly: REA's claim-your-home product is a lead-generation funnel, and the company describes it as one to shareholders.** A consumer spontaneously identified the same shape from outside, on REA-owned PropTrack publishing research that advertising on REA is worth +4.3%: *"So realestate.com.au did a study into themselves and found that their website gets you a better result than not using their website? Bit of a conflict of interest there don't you think?"* (`ADDENDUM_propertychat` §5.3 [V]).

**Discipline note.** `structural_conflict`'s own inference section is emphatic that *"they therefore withhold information from consumers"* does **not** follow from the revenue model and is undocumented. What *is* documented is (a) ranking by payment and (b) lead monetisation of consumer curiosity. Use those two. They are enough, and they are the only listing-side facts this document carries forward.

---

## 2. How the owner reaches the page

Not a user job — a distribution fact, and it constrains the design as hard as any job below.

- **The page has exactly one entrance.** `/off-market/:slug` arrivals: **93.6% Google, 6.4% direct, 0% internal referral, 0% Facebook** (`research_intent/C` [B]). The redesign cannot assume the visitor has seen any other Fields page. They have not.
- **The query carries no intent.** 99% of Google impressions to our address pages are **bare-address queries** with no qualifier — and `research_intent/D` found the mechanism: **89.5% of 354 address-form autocomplete queries return empty**, and of the 37 non-empty responses **not one** appended a semantic qualifier. Across a full a–z sweep on six real addresses, exactly one letter ever completed: `q` → "qld 4226". **Google never offers a way to express intent, so the owner types the address and expects the page to anticipate the question.**
- **Zero People Also Ask across all 12 address SERPs**, control-validated (two control queries through the identical pipeline returned 4 PAA each). Google models a bare address as an **entity**, not a question.
- **The off-market SERP is weak, and that is our opening.** Only **40%** of top-10 results are about the queried house — against 82% for sold and 78% for-sale addresses. 43% drift to neighbours and the street; 18% are unrelated, including `11 Placid Court, Narangba QLD 4504`, 80 km away, at position 6 (`research_intent/A`).
- **A specific checkable fact already beat domain authority.** We rank **#3, above Domain at #4**, on one off-market address — on the snippet *"Last recorded sale. $175,000. Oct 1990. Held for 35.7 yrs"* — while a page whose snippet was boilerplate (*"Property report with valuation, comparable sales, and market intelligence"*) ranked #6.

**Design consequences:** answer without being asked; no menu, no tabs; lead with a hard address-specific fact, not marketing copy and not a valuation figure.

---

## 3. The owner's jobs

Seven jobs. Each carries: the job in the owner's words · what they get today · where it fails · what Fields can do **today / partially / not yet** · what that means for the page · what would falsify it.

---

### J1 — "Six numbers and no way to choose between them"

**In their words.** The 84% spread post (§1.2) [V]. And a first-time seller on the southern Gold Coast holding four numbers on one address — bank **$930K**, agent pre-appraisal **$925K**, guide **up to $950K**, market offers **$885–900K** — plus a named near-identical comparable at **$870K** they are *manually adjusting* for view, land size, carport and covered outdoor area:

> "…that just seems crazy given that my place is worth a lot more than the similar one in land and improvements/extras. Plus I have the amazing view and it had none… I'm older, so I am concerned that if I screw this up, I screw up things for myself going forward."
> — r/AusProperty, 2025-12-09, via `research_intent/B` [V]

That is our comparables method, performed by an anxious amateur, at the worst moment of their life. Note the fear: not losing money — **being the person who got it wrong.**

**What they get today.** Three to six point estimates or ranges, all unexplained, from PropTrack/REA, Domain, property.com.au, propertyvalue.com.au, onthehouse.com.au, and their bank. **Three of those are one company** (`structural_conflict` A3 [P]).

**Where it fails.** No portal shows which sales the number was built from, what adjustments were made, or why they disagree. `Rique`, 2024-02-07: *"I find that Domain estimates and REA always **lag (3-4 months)**"* [V].

**What Fields can do.**
- **Today:** show the comparable set and the count reviewed vs retained (e.g. 41 reviewed, 8 retained); publish the method's **11.1% historical error rate**.
- **Partially:** a comparable **range** exists on only **7% of sold addresses** (221/2,947), **44%** for-sale, **23%** under-contract (`first_party_fields_data` §4 [B]). **The binding constraint on the whole product.**
- **Not yet:** the per-comparable working. `adjusted_price`, component adjustments and weights **are not persisted**, so the block cannot render — *"a genuine release blocker."*

**What the page must do.** Show *reconciliation*, not another figure. Design the **no-range state as the primary state** — 93% of sold addresses, not an edge case.

**Falsifier.** If a range-present page shows no better trust or onward action than a range-absent one, the "show the workings" thesis weakens. Never A/B tested.

---

### J2 — "Someone told me a number. Is it real?"

*This replaces an earlier out-of-scope job about listings being overpriced. The owner-side version is the appraisal or bank valuation they have just been handed.*

**In their words.** The **Agent-Number Sceptic** is one of the four strongest Reddit personas (~39 posts), alongside the **Equity Checker** (~115) and **Pre-Sale Sizer-Upper** (~51):

> "Help! I don't fully trust my REA so unsure what to do about setting a reserve. Our REA originally estimated our place as worth 800-900k (presumably to get us to pick him) Opens started and his tactic was to tell people 700-800k…"
> — r/AusProperty, 2024-11-06 [V]

> "The agent had a quick look around and a short chat, then basically said our place is worth about what it was 4 years ag…"
> — *"Left feeling flat after a property appraisal, looking for some perspective"*, r/AusProperty, 2026-07-08 [V]

> "Anyone else had an experience where the bank undervalued their property? And not by just 1-3% but by a lot?… an apartment in our building - IDENTICAL to ours (just without the balcony, so likely inferior) sold for $100k more than our recent bank valuation."
> — r/AusProperty, 2026-02-10 [V]

The pattern `research_intent/B` names as the strongest shape in the whole corpus: **someone has been given a number by an institution, does not trust it, and goes looking for a second number to check it against.** A twenty-minute walkthrough produced a figure that landed badly and the owner went to strangers on the internet the same day. *"That is precisely the moment an address page can intercept."*

**What they get today.** Another unexplained number, from a company whose accounting treats their curiosity as a seller lead.

**Where it fails.** The owner cannot audit either number. They have no comparable set, no adjustments, and no way to tell whether the agent's figure is a valuation or a listing tactic.

**What Fields can do.** **This is the sharpest fit for our method that exists.** Adjusted comparables with visible workings is precisely the instrument for checking a number someone else gave you. Subject to J1's coverage ceiling, and to Rule 5 — a range and its working, never a single figure, never advice about what to do with it.

**What the page must do.** Position the Hub as the **second opinion with its workings shown**, not as a first number. That is a different promise from every incumbent, and it is the one the evidence asks for.

**Falsifier.** If our range routinely sits inside the spread of the numbers they already have, we are the seventh estimate — the thing §1.2 says is worthless. The value is entirely in the *auditability*, not the figure.

---

### J3 — "It moved $100k and nobody will tell me why"

**In their words.**

> "In the last 3 months my house has dropped 40k increased 50k and dropped 40k, is this even possible" — `Mr G` (WA) [V]
> "Most terrible algorithms. My property went down by about 700k in 1 Month." — `Bilal N.` [V]
> "My house keeps going down while neighbour house keeps going up. Both properties exact same size block." — `Bilal N.` (NSW) [V]

Distrust is not fixed by a *flattering* number:

> "We've owned our property for 11 months now and apparently has gone up 100k in value since. **Is this reliable estimate because it just seems... unbelievable.**"
> — r/AusProperty, 2026-01-18 [V]

**What they get today.** REA positions owner tracking around *monitoring* estimated value and recent local sales. The value moves; no explanation is attached.

**Where it fails.** The grievance is almost never "the number is imprecise." It is **(a) volatility**, **(b) relative injustice** — why is my neighbour's higher on an identical block — and **(c) no recourse** (`consumer_voice` §3.3).

**What Fields can do.**
- **Today:** we hold historical valuation runs. A stability metric — *"our estimate for an unchanged home moved less than X% median over 12 months"* — is computable now and is a claim no portal makes.
- **Not yet:** a per-address change narrative ("this moved because 12 Something St sold in April").

**What the page must do.** This is the clearest argument for a **Hub** rather than a page. Per the session review: *"REA explicitly positions owner tracking around monitoring estimated value and recent local sales… **The static answer is valuable; the living answer is defensible.**"* A hub whose job is to narrate its own movements is the sharpest form of "adjudication, not valuation" — and it is the reason an owner would ever come back.

**Falsifier.** If our own estimates prove as volatile as theirs, the claim inverts into an attack surface. **Measure before saying it.**

---

### J4 — "It's wrong about my house and there is no way to fix it"

**In their words.**

> "I contacted them to get a true reflection and after over 20 emails back and forward they said they couldn't or wouldn't change it." — `Stephen B.` [V]
> "Our home is stunning and has everything you could ever want, yet it still shows as vacant land." — `SCL` (QLD) [V]
> "We are the owners of a house that has incorrectly been listed as sold for an incorrect price." — `Robert K.` [V]
> "Type the address in Google and it will bring up 3 real estate websites for that address. **The photo of the house is the one next door.** I drove past to confirm this." — r/AusProperty, 2026-07-12 [V]

And the version that is commercial harm, not annoyance:

> "The undervalued estimate value **puts pressure on the seller to come down to their estimate**… The site refused to remove their massively undervalued estimate when asked to do so. **They advised that I needed a real estate agent to value my property.**"
> — `tilt10`, 2023-03-09, PropertyChat [V]

The portal's remedy for a wrong number about your home was to route you into its revenue funnel.

**What they get today.** Attribute editing exists on REA and feeds the estimate. What does not exist is a *response* — every reviewer in this cluster reports nobody replied.

**Where it fails.** Two distinct failures: no correction pathway for facts, and no recourse on the estimate. `research_intent/B` names the second-order cost precisely: incoherent status or history on an address page *"does not read as 'bad data' — it reads as 'something is wrong with this house.' A listing-status bug is a trust bug."*

**What Fields can do.** **This is the strongest argument for *claiming* specifically.** Claiming means the owner corrects a fact and **watches the working change in front of them** — which has never been offered. Not yet built.

**What the page must do.** Make correction visible and consequential. Our own data quality is a prerequisite: `research_intent/C` records a visitor who spent three sessions and ~50 keystrokes over an hour failing to reach `120 Glen Eagles Drive, Robina`, never trying the two-word form, never getting a result.

**Falsifier.** If corrections arrive at a volume we cannot verify, the pathway is a liability. Needs a moderation model before launch.

---

### J5 — "Is my home exposed?"

**In their words.** `does burleigh waters flood` is the **single most persistent suggestion in our entire stored corpus at 546 — 2.5× the next item (219)** — and the only question-form entry near the top (`own_address_search_intent` §4). Independently, the `is my house ` autocomplete seed is almost entirely non-valuation: flood zone, bushfire, heritage listed, asbestos, brick veneer, elevation, orientation, solar suitability, NBN (`research_intent/D`, 71 suggestions).

> "Houses throughout multiple LGA in SEQ now have insurance costs 10-20k+ a year… **Yet houses 4m below the flood level are selling for 90-95% of those that don't.**"
> — r/AusProperty, 2026-05-21 [V]

**This resolves an apparent contradiction in our own evidence.** `consumer_voice` §4.5 found **no** consumer complaining that a listing omitted flood risk, across three independent source families. The resolution: **people don't complain to the portal — they go to Google instead.** Absence of complaint was mistaken for absence of demand.

**What they get today.** Nothing at address level. UK listings show surface-water flood risk as a regulated standard (NTS Material Information Part C, Nov 2023), alongside council tax band, EPC, broadband and mobile signal. *"Australia is an outlier among comparable countries in not having reliable public data on property-level flood risk."* Queensland's Property Level Flood Information Portal is opt-in, 39 councils.

**What Fields can do.** We already hold `config/flood_context_burleigh_waters.md`. Suburb-level context today; address-level where council data supports it. Rule 5 applies — data, source, limitations, no advice, no reassurance.

**Cautionary precedent.** Trulia built crime layers, showcased them at the White House in 2012, and **withdrew them in early 2022** on fairness grounds; Redfin declined outright. Not every "more data" feature is a win. Flood is defensible on measurement grounds where crime is not — but the source and its limits must be on the page.

**Falsifier.** Persistence is not volume. 546 is a signal warranting direct measurement, not a demand figure.

---

### J6 — "Let me look without being caught"

**The job that most threatens the V4 concept, and it deserves the most care.**

**In their words.**

> "Has anybody else noticed a TON of letterbox drops from people asking to buy your house… **The purchase prices I've seen for my place is insane too, no way am I selling however.**"
> — r/GoldCoast, 2021-08-25, 47 upvotes, 42 comments [V]

> "…**are they allowed to grab our PII from public land records and craft a false statement like this legally?** I feel like this surely should conflict with the Privacy act..."
> — r/AusProperty, 2025-04-08, 62 comments [V]

> "I've had 3 different agents calling me casually 'how is house x going for you?'. **How do they know I own this property and where are they getting my phone number?**"
> — r/AusProperty, 2026-05-05 [V]

**`research_intent/B` searched specifically for positive reactions to unsolicited approaches and found none: "The corpus contains zero posts where an unsolicited approach produced a positive response. A 'we found your house' framing carries real risk on this evidence."**

**Our shipped card 0 is headlined "We found your home."** (`offmarket_discovery`, `engine_version: disc-v1`.) That is a direct, evidenced conflict with the strongest negative finding in the corpus, and the most actionable single item in this document.

**The tension resolves more precisely than "privacy is a risk."** `research_intent/B` also searched for discomfort that a public page about one's address exists and found **none** — *"Not one post expresses discomfort that a public page about their address exists."* PropertyChat's majority view agrees: *"every property in Australia is listed like that now, it's public information."* The discomfort is about two specific things:

1. **Being contacted.** *"Will an agent call me? Am I declaring that I am selling? Will my details be passed around? Can I look without being pursued?"* REA's own address product prominently reassures users their address won't be shared — because this expectation is mainstream.
2. **Derived financial inference.** The one clear privacy violation in the corpus is not the estimate but what sat beside it: *"what absolutely floored me was they had even estimated **what we owe on it**"* (`Fernfurn`, PropertyChat [V]). And socially: *"My family won't be happy and will absolutely think that I've lost the plot when they see the price."*

**What this means for a claim-your-home product.** Claiming is, by construction, identifying yourself — the thing this job is trying to avoid. Survivable only if claiming **confers control instead of extracting it**:

- **The page answers first, in full, before any ask.** Claiming is never the price of entry.
- **"Nobody calls unless you ask" must be an operational rule, not copy.** *"May be one of the most commercially valuable lines in the entire Fields experience — provided it is absolutely true operationally."*
- **Public-record side of the line only.** No equity estimate, no implied mortgage balance.
- **Change the opening.** The owner should feel they arrived, not that they were located.

**And the strongest superiority claim we have lives here:** claiming your home on realestate.com.au converts you into a seller lead delivered to whichever agent pays most, and REA reports the growth rate to shareholders. Claiming with Fields costs nothing and contacts no one. Defensible entirely from their own filings.

---

### J7 — "Could a move actually work from here?"

**In their words.** The strongest Reddit persona by volume is the **Equity Checker (~115 posts)**:

> "Check the upper end value of your home on sites like domain and property. Call your bank and request an updated AVM. **Try to hit the maximum number the bank will accept**… you may have changed your LVR which may in turn allow you to negotiate better rates…"
> — r/AusFinance, 2026-05-21 [V]

> "Right now I'm pulling loan balances manually and using Domain estimates to get a rough equity figure. It works, but it's not exactly a clean picture."
> — r/AusProperty, 2026-04-13 [V]

From our own homeowner work, the highest-emotional-weight concern is the re-entry problem — *"If I sell, I won't be able to get back in"* — which the session review notes is *"primarily a logistics problem, not simply a valuation problem."*

**Where it fails.** Nobody joins the value of the home to the feasibility of the move.

**What Fields can do.** **Not yet, and the review's warning should be respected.** The mini-site V2 Session 2 is our attempt, and it was flagged for conflating sale-value band with buying budget while ignoring mortgage balance, sale costs, transfer duty, borrowing capacity and cash reserves — *"This could be confronting or misleading."*

**Scope note.** This is the job where the Hub eventually earns a returning visitor, and it is also where it could most easily mislead. It collides directly with J6's privacy line, since equity inference is exactly what triggered the one clear privacy complaint we hold. **V4+ item, not a launch item.**

---

## 4. Who is actually on the page — and why the copy cannot assume

Our own data cannot distinguish the visitor at all. `research_intent/C`: *"Owner, neighbour, prospective buyer, valuer, nosy local — nothing in the data distinguishes them."* The only direct probe, the `offmarket_menu_*` chips, has fired **nine times in total**.

The session review names seven plausible searchers: owner checking value · owner considering a move · financially curious owner · **correcting owner** · neighbour · prospective buyer · tenant/former resident/family member — and warns that *"searching the address is a strong property-connection signal, but it is not definitive proof of ownership or selling intent."*

**Direct evidence that a share of arrivals are not owners.** Google's refinement data across the 12 address SERPs ranks `for sale` the top modifier (8 of 22) — and **5 of those 8 were on addresses that are not for sale**. Somebody is asking availability questions about unavailable houses. That is a buyer, and it is out of scope as a *job* (§SCOPE) — but it is squarely in scope as a **constraint on the copy**: a page that addresses the reader as "the owner of this home" will be wrong for some of its audience, and the ones it's wrong about are exactly the ones most likely to find "we found your home" alarming. ⚠ n=22 from 12 SERPs; directional, not precise.

**Two evidence-backed resolutions:**

- **Ownership lookup is NOT a job.** Google lists `owner` 4× in refinements, but two independent sources kill it: the `who owns ` autocomplete sweep returned 260 suggestions, **all corporate** (Coles, Bunnings, Optus), zero residential; and "what did the current owner pay" returns **0 hits in 4,349 Reddit posts**. The `+owner` refinement is Google's generic entity template. **Do not build an ownership or occupancy surface on it.**
- **"Not selling" is not low intent.** *"A homeowner may have strong interest in value while having no immediate intention to list."* Zoopla's **6 million** MyHome users against ~24–25 million UK dwellings are overwhelmingly not selling. The Hub's audience is the 100% of homes, not the 3–5% transacting.

**Recommendation on the open question.** Build the Hub as a **persistent homeowner utility that is also the seller on-ramp** — not a seller on-ramp wearing a utility's clothes. The living answer is the defensible one (J3); the largest stated personas are equity and second-opinion, not listing (J2, J7); and a page that reads as a seller funnel triggers J6 directly. The mini-site V2 sessions remain the high-intent product downstream. **A decision for Will, recorded as a recommendation, not as settled.**

---

## 5. What we cannot deliver yet — the honest constraint register

Any superiority claim must survive this list. Every item is from our own records.

| # | Constraint | Evidence | Consequence |
|---|---|---|---|
| C1 | **Comparable range exists on 7% of sold addresses** (221/2,947), 44% for-sale, 23% under-contract | `first_party_fields_data` §4 [B] | Any layout assuming a range is blank on 93% of sold pages. **Coverage, not design, is the ceiling** |
| C2 | **Confidence labels are inverted in parts of the backtest and must not be published** | `GTP_market_analysis` L1026 | Publishing now would repeat the exact failure we criticise |
| C3 | A "high accuracy" Domain band that **excluded the actual sale price** | `ADDENDUM_propertychat` §1 [V] | An uncalibrated label is **worse than none**. `valuation_backtest.py` must show what share of real sales fall inside each stated band **before** any label ships |
| C4 | `adjusted_price`, component adjustments and weights **not persisted** | `GTP_market_analysis` L1051–1066 | The "show the working" block cannot render. *"A genuine release blocker"* |
| C5 | **Address search tolerates neither spacing nor typos**; ~⅓ of typed addresses fall outside our three suburbs | `research_intent/C` [B] | One visitor failed across three sessions on a two-word street name. `result_count` populated on 5 of 184 events — we cannot measure the failure rate |
| C6 | **Samantha persists nothing** | `research_intent/C` [B] | Zero real visitor questions exist to mine. The richest source of address-level intent is discarded at runtime |
| C7 | **PostHog holds zero break-glass events** since launch despite `BreakGlass.tsx` calling `phCapture` | `own_address_search_intent` §8 | A feature shipped to learn something cannot report |
| C8 | All off-market behavioural rates rest on **17 days**, n=266 people | `research_intent/C` | Nothing about the deck is statistically settled, including the arm gap |
| C9 | `sale_price` stored as a **string**; confidence values are `very_low` with an underscore, plus `directional` | `first_party_fields_data` §5 [B] | Numeric Mongo predicates silently match nothing |
| **C10** | ⚠ **CORRECTED 2026-08-06 — we have NO valid Fields-vs-Domain accuracy comparison, in either direction.** This entry previously stated as settled fact that Domain beats us (Robina 11.6% vs 6.9%; Burleigh Waters 13.7% vs 8.1%). **That benchmark is contaminated.** `domain_valuation_at_listing` is misnamed — it is snapshotted at sold-detection, and **703 of 766 records (91.8%) were captured on or after the sale date, median +266 days**. Domain ingests sold prices, so those figures had the answer. Fields is held strictly out-of-sample by `sold_before_subject()`. We benchmarked a forecast against hindsight. On the only clean subset (captured before the sale, **n=21**) Domain is **worse** — 14.3% mean MAE — but n=21 cannot replace the claim with its opposite | Capture path `sold_backfill/search_based_sold_monitor.py:456-474`; timing measured 2026-08-06; fix-history `[DOMAIN-BENCHMARK-CONTAMINATED]` [B] | **This removes a comparison; it does not reverse one.** C1 in the claims register still stands — never claim superiority over any portal — but now because **no valid measurement exists**, not because we lose. Note the correction flatters us, so treat it with more scepticism, not less. The only route to a real answer is the prospective study in `Adjusted-Comparables-Evidence.md` §6: capture platform valuations for off-market homes **before** they list, then wait. The supported angle remains **calibration**, not accuracy — automated ranges, ours included, are overconfident |
| **C11** | The 55% narrowing is **n=1** and the two adjustments are **not composed** | `Adjusted-Comparables-Evidence.md` §5 | Before any campaign: run across all 262 eligible sold homes and quote the **median** narrowing, not this example. The $274,254 figure is feature adjustment on the *raw* price; time adjustment alone narrows $610,000 → $402,335; **the composed figure is unverified and must not be quoted** |
| **C12** | Our own stated error rate is unsettled — **11.1%** appears in the mini-site session copy, **11.6%** in the 2026-08-05 Robina backtest | `GTP_market_analysis`; `Adjusted-Comparables-Evidence.md` §3 | Pin one figure, with its sample and date, before publishing any of it (claims register A1). Relativities move — re-check against the latest weekly backtest |

---

## 6. Where the evidence contradicts the page we have shipped

Each is a measured or quoted conflict with `offmarket_discovery` / `disc-v1`.

| # | Shipped behaviour | Evidence against | Action |
|---|---|---|---|
| S1 | Card 0 headline **"We found your home."** | Zero positive reactions to unsolicited "we found your property" framing across 5,685 Reddit posts; three verbatim hostility artefacts (J6) | **Rewrite.** Highest-priority copy change in V4 |
| S2 | `valuation` (11.7s dwell) and `buyer` (9.0s) sit at **positions 6 and 7** | Cards 1–5 are skimmed at **1.5–2.3s median** — scroll-past speed. Only ~17% / 14.5% of sessions reach the two cards anyone stops on | **Front-load.** The IA is inverted |
| S3 | The deck asks the visitor to advance | **47–57% never advance past card 0**; 56.9% of `deck_exit` sessions exited at `max_index_reached = 0` | **Card 0 must stand alone as a complete answer** |
| S4 | A menu / "what would you like to know?" affordance | `offmarket_menu_*` fired **9 times total**; Google never offers a qualifier (§2), so the owner has no practice declaring intent | **Answer without being asked.** No menu, no tabs |
| S5 | Boilerplate meta description | Our boilerplate page ranked **#6**; our specific-fact page ranked **#3, above Domain** | **Lead with a hard, checkable, address-specific fact** |
| S6 | No search box on the off-market page | Zero `address_search` events originate from an off-market page — **no evidence at all** about what these visitors would type | Instrument it, or accept the blind spot knowingly |

---

## 7. Two cautions the evidence insists on

**There is no delight anywhere in this corpus.** `research_intent/B`: *"Every emotional reaction to a value in the corpus is negative or anxious… **Zero delight.**"* This cuts against the V2 `Core_concept.md` ambition of "moments" and "reframing" — *"Actually… my home has strengths I never realised."* No evidence supports that response existing. The evidenced emotional state is **anxiety about being wrong** (see the Gold Coast seller in J1: *"I screw up things for myself going forward"*). A page designed to delight may be designing for a feeling nobody reports having.

**The field is crowding.** At least six per-address data products appeared in the Reddit corpus in 2026 alone — Property Mate, dwell-wise.com.au, PropCheck, Homer, PropCred, Glasshouse. Evidence of *perceived* demand and of competition, not of validated demand. We are not first.

---

## 8. Evidence gaps, ranked

| # | Gap | Why it matters | Cost |
|---|---|---|---|
| G1 | **Nobody has looked inside REA's Property Owner Dashboard or Domain's tracked-property view** | The spine of a "our Hub fixes theirs" argument, entirely missing. We have shareholder metrics and overseas help pages, and no feature-level account of what an Australian owner actually gets | Low — manual walkthrough, or Bright Data |
| G2 | **Reddit is still blocked** | Largest hole in consumer voice. Three routes, all needing Will: Bright Data KYC (best coverage) · paid PullPush (archive to 2025-05-19 only) · official Reddit API app (cleanest if KYC unwanted). ⚠ PullPush issued an explicit refusal that was respected, not circumvented | Will's decision |
| G3 | **Are they owners, neighbours or buyers?** | Still inferred, never confirmed — and §4 shows a real share are not owners. One post-view question settles it | Very low — highest value per unit of effort |
| G4 | **Is the exit satisfaction or failure?** | 13.9% click-through and 87.5% single-pageview have identical telemetry for "found it and left happy" and "didn't find it" | Low |
| G5 | **Does a range beat a point estimate** for trust and onward action? | Never A/B tested. The whole "show the workings" thesis rests on it | Medium |
| G6 | **Actual search volume for `does burleigh waters flood`** | Persistence (546) is not volume | Low |
| G7 | **Claims needing a browser check** before publication | (a) paid placement carries no consumer-facing label; (b) portals withdraw the estimate when a home goes to market; (c) our estimate-stability metric, unmeasured | Trivial — and blocking |

---

## 9. Open decisions for Will

1. **Is the Hub a persistent homeowner utility or a seller on-ramp?** Recommendation in §4: persistent utility that is *also* the on-ramp.
2. **How do we unblock Reddit?** Three options in G2.
3. **Do we do the incumbent-dashboard teardown (G1) before writing public copy?** Recommendation: yes. It is the missing spine.
4. **Does "nobody calls unless you ask" become an operational rule?** If yes, possibly the most valuable line in the product. If no, it cannot be said at all.

---

## Appendix — source map

| Source file | What it carries |
|---|---|
| `EVIDENCE_consumer_voice.md` | ProductReview / app store / Whirlpool / regulator corpus; the 4.8-vs-1.9 divergence; the negative findings in §4 |
| `EVIDENCE_consumer_voice_ADDENDUM_propertychat.md` | 35 threads / 335 posts; the identical-units comparison; the "high accuracy" band that excluded the sale price; the privacy artefact |
| `EVIDENCE_structural_conflict.md` | REA/Domain filings, ownership map, ACCC, CoStar; **read its inference section before quoting anything** |
| `EVIDENCE_international_comparison.md` | Zillow / Redfin / Rightmove / Zoopla feature and accuracy evidence; the AU capability audit |
| `EVIDENCE_first_party_fields_data.md` | GSC + PostHog baseline; **the coverage ceiling**; measurement traps |
| `EVIDENCE_own_address_search_intent.md` | Synthesis of streams A–D; design consequences; flood persistence |
| `research_intent/A_serp_intent.md` | 12 live SERPs; zero PAA; the 40% off-market relevance finding |
| `research_intent/B_reddit_motivation.md` | 4,349 corpus + 1,336 RSS posts; personas; the 84% spread; **zero positive unsolicited-approach reactions**; zero delight |
| `research_intent/C_first_party_behaviour.md` | PostHog deck funnel, dwell, arms, address-search failure, Samantha instrumentation gap |
| `research_intent/D_autocomplete_qualifiers.md` | 772 requests; the address-level qualifier void; the risk/hazard cluster; `who owns` negative finding |
| `GTP_market_analysis.md` | ⚠ **Misnamed.** A GPT critique transcript of the mini-site V2 sessions plus one address-intent section. No competitor grievance evidence. Suggest renaming `GPT_minisite_session_critique.md` |

**Companion documents:** `02_COMPETITOR_CAPABILITY_MATRIX.md` · `03_CLAIMS_REGISTER.md`
