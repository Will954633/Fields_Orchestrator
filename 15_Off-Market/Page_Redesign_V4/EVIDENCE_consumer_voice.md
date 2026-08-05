# EVIDENCE — Primary Consumer Voice on Australian Property Portals

**Scope:** realestate.com.au (REA), domain.com.au, property.com.au
**Purpose:** Evidence base for the Off-Market page redesign (V4). Real complaints in real people's words, with links.
**Compiled:** 2026-08-05
**Compiled by:** Fields ops agent (automated research session)

> **Reading rule for this document.** Every quote below is reproduced as found at the source URL. Where a source only allowed a paraphrase, it is explicitly marked `[PARAPHRASE]`. Where a number could not be traced to a primary publisher, it is flagged in §4. Do not quote anything from §4 in public-facing material.

---

## 1. Method — what was searched, and what could not be reached

### 1.1 Sources successfully harvested

| Source | Access method | Status |
|---|---|---|
| ProductReview.com.au — realestate.com.au listing (pages 1–6) | WebFetch | ✅ Full review text |
| ProductReview.com.au — domain.com.au listing | WebFetch | ✅ Full review text |
| Apple App Store AU — realestate.com.au app (id404667893) | WebFetch | ✅ Rating + review text |
| Apple App Store AU — Domain app (id319908646) | WebFetch | ✅ Rating + review text |
| Google Play — REA & Domain apps | WebSearch snippets | ⚠️ Ratings only, review text not retrieved |
| Whirlpool forums (`forums.whirlpool.net.au/archive/*`) | WebFetch | ✅ Full thread text — 4 threads |
| Elite Agent (industry press) | WebFetch | ✅ |
| Real Estate Business / REB (industry press) | WebFetch | ✅ |
| CHOICE.com.au | WebFetch | ✅ |
| Yahoo Finance AU | WebFetch | ✅ |
| The Conversation / Univ. of Sydney | WebFetch | ✅ |
| Compare the Market + PRD Research | WebFetch | ✅ |
| NSW Fair Trading / NSW Gov, Consumer Affairs Victoria / Vic Premier | WebSearch | ✅ |
| Climate Council | WebSearch | ✅ |

### 1.2 Sources that could NOT be reached — material limitations

These are honest gaps, not omissions:

1. **Reddit is entirely inaccessible from this environment.** `reddit.com`, `old.reddit.com`, `api.reddit.com` and the `.json` endpoints are all blocked — WebFetch refuses the host, and direct `curl` from the VM returns a Reddit interstitial page rather than content. Six different search strategies (`site:reddit.com` queries, natural-language queries naming subreddits, Google-search fetch) returned **zero** Reddit threads. **Consequence: r/AusFinance, r/AusProperty, r/australia, r/melbourne, r/sydney and r/brisbane are entirely unrepresented in this document.** Given Reddit is likely the single richest vein of unfiltered buyer voice, this is the largest gap in the evidence base. See §5.1 for how to close it.
2. **Trustpilot returns HTTP 403** to WebFetch on both `trustpilot.com` and `au.trustpilot.com`. Trustpilot scores below are taken from **search-engine snippets of Trustpilot's own page titles** and are marked as such — they are indicative, not fetched-and-verified. Two different snippets gave 2.1 and 2.2 for REA, so treat as "approximately 2.1–2.2".
3. ~~**PropertyChat.com.au returns HTTP 403.** A directly relevant thread ("Accuracy of PropTrack data in realestate.com.au valuations [NSW]") was identified but could not be read.~~
   ✅ **CLOSED 2026-08-06** — reachable via the Bright Data Web Unlocker already in `.env`. 35 threads / 335 posts harvested, including that exact thread. See **`EVIDENCE_consumer_voice_ADDENDUM_propertychat.md`**, which **revises §4.6 and reframes §3.1 of this document** — read it before quoting either.
4. **Google Play review text could not be extracted** — the page body truncates before the review section. Only aggregate ratings were obtainable.
5. **No published AVM accuracy statistics were found for PropTrack Estimate or Domain Home Price Guide.** This is itself a finding — see §4.1.

### 1.3 Search strategy (for reproducibility)

Approximately 24 distinct queries were run across WebSearch and WebFetch, covering: portal names × ("reviews" | "complaints" | "app store"); ("underquoting" | "price guide" | "no price" | "contact agent") × (state regulator | forum | news); ("AVM" | "estimate accuracy" | "home price guide") × (PropTrack | Domain | CoreLogic); portal audience/traffic metrics × (Ipsos iris | REA | CoStar); ("strata fees" | "flood risk" | "floor plan" | "school catchment" | "agent spam" | "sponsored listing") × listings/complaints.

---

## 2. Quantitative data

**Staleness convention:** 🟢 = 2024 or later · 🟡 = 2023 · 🔴 = pre-2023, treat as stale · ⚠️ = source not independently verified

### 2.1 Review-site and app-store ratings — note the enormous divergence

| Metric | Value | Source | Date | Flag |
|---|---|---|---|---|
| realestate.com.au — ProductReview.com.au | **1.9 / 5** from **306 reviews**; 30% positive / 4% neutral / **66% negative** | [productreview.com.au](https://www.productreview.com.au/listings/realestate-com-au) | accessed 2026-08-05 | 🟢 |
| domain.com.au — ProductReview.com.au | **1.5 / 5** from **129 reviews**; 19% positive / 7% neutral / **74% negative** | [productreview.com.au](https://www.productreview.com.au/listings/domain-com-au) | accessed 2026-08-05 | 🟢 |
| realestate.com.au — Apple App Store (AU) | **4.8 / 5** from **291,000 ratings** | [apps.apple.com](https://apps.apple.com/au/app/realestate-com-au-property/id404667893) | accessed 2026-08-05 | 🟢 |
| Domain — Apple App Store (AU) | **4.7 / 5** from **116,000 ratings** | [apps.apple.com](https://apps.apple.com/au/app/domain-real-estate-property/id319908646) | accessed 2026-08-05 | 🟢 |
| realestate.com.au — Google Play | **4.5 / 5** from **76.2K reviews**; **5M+ downloads** | [play.google.com](https://play.google.com/store/apps/details?id=au.com.realestate.app) | accessed 2026-08-05 | 🟢 |
| Domain — Google Play | **4.4 / 5** from **44.1K reviews** | [play.google.com](https://play.google.com/store/apps/details?id=com.fairfax.domain) | accessed 2026-08-05 | 🟢 |
| realestate.com.au — Trustpilot | **~2.1–2.2 / 5** ("Poor") | [trustpilot.com](https://www.trustpilot.com/review/realestate.com.au) | accessed 2026-08-05 | 🟢 ⚠️ snippet only, 403 on fetch |
| property.com.au — Trustpilot | **1.9 / 5** ("Poor") | [au.trustpilot.com](https://au.trustpilot.com/review/property.com.au) | accessed 2026-08-05 | 🟢 ⚠️ snippet only, 403 on fetch |

> **This divergence is the single most important quantitative finding in this document.** REA scores 1.9/5 on ProductReview and 4.8/5 on the App Store — from the *same population*. See §3.0.

### 2.2 Audience and reach

| Metric | Value | Source | Date | Flag |
|---|---|---|---|---|
| realestate.com.au average monthly unique audience | **12.7 million Australians** | Ipsos iris Online Audience Measurement (P14+), via [Elite Agent](https://eliteagent.com/realestate-com-au-strengthens-leadership-with-record-audiences-in-q1/) | Jul–Dec 2025 avg | 🟢 |
| realestate.com.au peak monthly audience | **record 13 million** | [Elite Agent](https://eliteagent.com/a-record-13-million-australians-turn-to-realestate-com-au/) | 2025 | 🟢 |
| realestate.com.au app visits | **69.3 million visits** in the month | Ipsos iris via Elite Agent | Oct 2025 | 🟢 |
| Average time on realestate.com.au | **38 minutes** per month (2025) / **40 minutes** per visit (2024 figure) | Ipsos iris; REA via [Australian Property Update](https://australianpropertyupdate.com.au/apu/property-buyers-demanding-more-information-and-taking-their-time) | 2024–2025 | 🟢 ⚠️ two different denominators reported; do not conflate |
| Domain residential platforms reach | **9 million Australians** | [CoStar Group](https://www.costargroup.com/press-room/2025/australias-fastest-growing-property-portals-domains-residential-platforms-reach-9m) | 2025 | 🟢 |
| Total Australians using a home/property site or app | **~14 million** in July | [Ipsos iris](https://iris-au.ipsos.com/the-great-australian-dream-close-to-14-million-australians-used-a-home-and-property-website-or-app-in-july-as-people-start-to-plan-their-next-real-estate-move-ipsos-iris-data/) | 2025 | 🟢 |

### 2.3 Buyer frustration — REA's own survey (the strongest data in this file)

**Source: REA Group *Property Seeker Survey* 2024, n = 13,400+ Australians, conducted by Starburst Insights, published 28 October 2024.** This is the portal's own research, which makes it very hard to dispute.

| Metric | Value | Source | Flag |
|---|---|---|---|
| Buyers who would **skip a property that doesn't show a price** | **72%** | [Elite Agent, 26 Oct 2023](https://eliteagent.com/buyers-seek-transparency-72-per-cent-skip-properties-without-prices-listed/) | 🟡 (2023 wave) |
| Buyers who want **clarity on price more than anything else** before even inspecting | **55%** | [REB, 28 Oct 2024](https://www.realestatebusiness.com.au/marketing/28906-biggest-ever-home-hunter-survey-reveals-what-aussies-want-from-listings) | 🟢 |
| Increased confidence bidding/offering once price is known | **"just over four out of five" (80%+)** per REB; **76%** per Australian Property Update | REB / APU | 🟢 ⚠️ **two sources report different figures for what appears to be the same statistic — use "roughly four in five" and cite both** |
| Listings that include **more than five property features** | **only 22%** | [REB, 28 Oct 2024](https://www.realestatebusiness.com.au/marketing/28906-biggest-ever-home-hunter-survey-reveals-what-aussies-want-from-listings) | 🟢 |
| Sellers who would **choose a different agent** if pricing was withheld | **54%** | [Elite Agent](https://eliteagent.com/buyers-seek-transparency-72-per-cent-skip-properties-without-prices-listed/) | 🟡 |
| REA listings **tracked by their owner** before going to market | **40%** | [Elite Agent](https://eliteagent.com/buyers-seek-transparency-72-per-cent-skip-properties-without-prices-listed/) | 🟡 |
| Average time to buy a property | **23 weeks (2022) → 34 weeks (2023) → 44 weeks (2024)** | REA via [APU](https://australianpropertyupdate.com.au/apu/property-buyers-demanding-more-information-and-taking-their-time) | 🟢 |
| Days on market | 27 → **34 days** (Sept 2024) | REA via APU | 🟢 |

### 2.4 Price-guide availability

| Metric | Value | Source | Flag |
|---|---|---|---|
| Brisbane property ads showing an **asking price/range** | **17%** (vs Sydney 29%, Melbourne 57%) | [Compare the Market / PRD Research](https://www.comparethemarket.com.au/news/why-brisbane-buyers-are-kept-in-the-dark-over-house-prices/), 23 Sep 2021. Sample: 1,020 ads (340 per city; 170 × 3-bed + 170 × 4-bed) | 🔴 **STALE — 2021.** Directionally the most Gold-Coast-relevant number we have, but must be re-measured before use. |
| Brisbane ads listed as **auction** (no price) | **41%** (vs Sydney 33%, Melbourne 19%) | same | 🔴 |
| QLD legal position | Under the **Property Occupations Act 2014**, an agent is **prohibited from giving any price guide** for a property going to auction | [Armstrong Legal](https://www.armstronglegal.com.au/commercial-law/qld/consumer-law/qld-misleading-property-price-guides/) | 🟢 (law still current) |
| Victoria | Only state that **legally requires** a selling price on listings; ranges capped at 10% spread | [Yahoo Finance AU, 1 Feb 2025](https://au.finance.yahoo.com/news/property-hack-to-get-around-frustrating-real-estate-price-tactic-should-be-illegal-190033901.html) | 🟢 |

### 2.5 Underquoting enforcement

| Metric | Value | Source | Flag |
|---|---|---|---|
| NSW — penalty notices for underquoting issued | **100+** in 2024 | [NSW Fair Trading Strategy & Priorities Annual Report 2024-25](https://www.nsw.gov.au/departments-and-agencies/fair-trading/news/nsw-fair-trading-publishes-its-strategy-and-priorities-annual-report-2024-2025) | 🟢 |
| NSW — property-sector enforcement 2024-25 | **2,200+ inspections; $1.58M in fines; 55 licences suspended; 29 cancelled; 16,000 agents retrained** | same | 🟢 |
| NSW — underquoting penalty (proposed increase) | **$22,000 → $110,000** (or 3× the agent's commission, whichever greater) | [NSW Government](https://www.nsw.gov.au/ministerial-releases/nsw-cracks-down-on-underquoting-tough-new-laws) | 🟢 |
| VIC — Underquoting Taskforce, cumulative | **$3 million** total fines; **8,800+ complaints**; 3,200+ campaigns monitored; 500+ auctions attended; 400+ official warnings; 260+ fines | [Premier of Victoria](https://www.premier.vic.gov.au/underquoting-taskforce-ramps-enforcement-action) | 🟢 |
| VIC — 2024-25 (to Q3) | 500 campaigns monitored; 67 auctions; **64 warnings; 29 infringements; $338,000+ in fines** | same | 🟢 |
| VIC — earlier total | **$1.8 million** in underquoting fines | [Real Estate Business](https://www.realestatebusiness.com.au/industry/29605-victorian-agents-hit-with-1-8m-in-fines-for-underquoting) | 🟡/🔴 undated in snippet |

> **Interpretation note:** 8,800 complaints in Victoria alone is a very large number relative to 29 infringements in a year. The gap between complaint volume and enforcement outcome is itself the story — consumers report it constantly and almost nothing happens.

### 2.6 Advertising cost / portal economics (why the portal serves agents)

| Metric | Value | Source | Flag |
|---|---|---|---|
| Countries where the **seller pays advertising separately** from agent commission | **Australia, Sweden, New Zealand only** | James Graham, Univ. of Sydney, [The Conversation, 17 Sep 2024](https://theconversation.com/advertising-a-house-is-ridiculously-expensive-in-australia-could-that-be-affecting-the-property-market-239111) | 🟢 |
| REA "Premier" listing quoted to a vendor | **$2,509** | Whirlpool user `Lamp Post`, [25 Sep 2024](https://forums.whirlpool.net.au/archive/30x1r10r) | 🟢 |
| REA "Luxe" tier | **$2.6k +++**, on top of existing premium tiers | Whirlpool user `pm4life`, 11 Oct 2024 | 🟢 |
| REA vs Domain per-listing cost (one vendor's quote) | **$1,538 REA vs $803 Domain** | ProductReview user `Anza`, ~2025 | 🟢 ⚠️ single anecdote |
| Max REA listing price reported | **"as high as $4,000"** | Guardian Australia, cited by Whirlpool user `Quokka T`, 26 Sep 2024 | 🟢 ⚠️ second-hand citation; original Guardian article not directly fetched |

### 2.7 Risk data absent from listings

| Metric | Value | Source | Flag |
|---|---|---|---|
| Australian homes at flood risk today | **1 in 6** | [Climate Council Property Value Report](https://www.climatecouncil.org.au/resources/property-value-report-how-climate-change-could-worsen-australias-42-billion-flood-risk/) | 🟢 |
| Value destroyed by flood risk | **$42.2 billion**; QLD alone **$19 billion** (as at April 2025) | same | 🟢 |
| Typical 3-bed/2-bath house discount from flood risk | **$75,500 less** | same | 🟢 |
| Climate Council's own conclusion | *"to date, there has been limited detail available to individual homeowners on what the risk to their greatest asset already is"* — calls for **standardised risk disclosure** | same | 🟢 |

---

## 3. Complaint themes, ranked by frequency

Frequency scale: **DOMINANT** (appears across 4+ independent source types, repeatedly) · **RECURRING** (multiple sources, multiple years) · **ISOLATED** (1–2 mentions).

---

### 3.0 THE META-FINDING: two completely different consumer populations

Before any individual theme — the ratings divergence in §2.1 must frame everything below.

| Platform | REA score | n |
|---|---|---|
| Apple App Store (AU) | **4.8 / 5** | 291,000 |
| Google Play | **4.5 / 5** | 76,200 |
| ProductReview.com.au | **1.9 / 5** | 306 |
| Trustpilot | ~2.1–2.2 / 5 | (small) |

**What this means for the redesign:** the portals are not *failing* at the job most people think they're doing. Hundreds of thousands of casual users rate the browsing app 4.5–4.8. The 1.9 scores come from a self-selecting minority who went out of their way to find a complaint site — i.e. people with an **unresolved, high-stakes grievance**. Those grievances cluster tightly and consistently (below), and they are almost entirely about **information the portal does not give them**, not about the app being hard to use.

The opportunity is not "build a nicer property search". It is "answer the questions the 1.9-star cohort is angry about" — which the 4.8-star cohort would also value but has never been offered.

---

### 3.1 DOMINANT — No price / "Contact Agent", and price guides that mean nothing

This is the **single most substantiated theme in the entire document**, and uniquely, it is confirmed by the portal itself.

**REA's own executive, on the record:**
> "listings that don't have pricing displayed remain **the number one source of dissatisfaction on our platform**"
> — Melina Cruickshank, REA Group, [Elite Agent, 26 Oct 2023](https://eliteagent.com/buyers-seek-transparency-72-per-cent-skip-properties-without-prices-listed/) · industry press quoting portal executive

> "They just assume it's out of their price range."
> — Melina Cruickshank, same source

Consumer verbatim from REA's own research:
> "we want prices mandated on our listings"
> — verbatim consumer research response, quoted in [Elite Agent](https://eliteagent.com/buyers-seek-transparency-72-per-cent-skip-properties-without-prices-listed/), 26 Oct 2023

**Forum voice (Whirlpool, "Real Estate Websites not showing prices"):**
> "I have noticed a trend where real estate agents hardly ever publish the price on Domain and Realestate."
> — `kowcop`, 15 Oct 2025, [forums.whirlpool.net.au/archive/3yqqmpll](https://forums.whirlpool.net.au/archive/3yqqmpll) · forum

> "On the flip side when I was looking for a house it drove me nuts the prices weren't listed!"
> — `Lammiwinks`, 24 Oct 2025, same thread · forum

> "I often ring agents from a private number, and tell them to let me know the price so I don't waste fuel travelling to an open."
> — `Bear33`, 25 Oct 2025, same thread · forum

**News/expert voice:**
> "Honestly, it should be illegal that they can't actually tell you what the prices are online."
> "You don't go into Woolies and go to buy a block of chocolate and you don't know what the price is until you go to the register."
> — Kobe Clarke-Jacobs, mortgage broker and former buyer's advocate, [Yahoo Finance AU, 1 Feb 2025](https://au.finance.yahoo.com/news/property-hack-to-get-around-frustrating-real-estate-price-tactic-should-be-illegal-190033901.html) · news

**Product feature request, unprompted (Domain iOS App Store):**
> "Option to turn off properties with no numerical purchase price entered... I want to filter all thousand out!"
> — `FyrStrike`, review titled *"Needs better filtering options"*, 10 Jan 2023, [Apple App Store](https://apps.apple.com/au/app/domain-real-estate-property/id319908646) · app store

**Frequency: DOMINANT.** Confirmed by portal executive statement, portal-commissioned survey (n=13,400), independent news, forums, app-store reviews, and consumer bodies. Every source type agrees. **Nothing in this research contradicts it.**

---

### 3.2 DOMINANT — Underquoting: the guide is a lure, and buyers pay real money to discover it

> "by the time you get to an auction, you've already paid to have the building/pest reports and contract review – to then see a property passed in for a price above the guide."
> — `cuteseal`, 1 Feb 2021, [Whirlpool: "What steps do I need to take to stop underquoting?"](https://forums.whirlpool.net.au/archive/38wn5q89) · forum

> "everyone is wasting time and money so that the agent can attract more bidders."
> — `Gaff`, 3 Feb 2021, same thread · forum

> "General rule of thumb in Sydney, take the highest quoted range, add 10% and that is the likely minimum selling price the owner would consider."
> — `megadrive`, 30 Jan 2021, same thread · forum

> "There is no law or consumer protection in relation to what can define an estimated selling price! This is the issue."
> — `RandomPerson`, 30 Jan 2021, same thread · forum

> "to be able to prove an agent is underquoting it takes a lot of evidence and there are relatively easy workarounds for agents to avoid being caught out."
> — `SydneyCider`, 30 Jan 2021, same thread · forum

> "Went to auction around March, price guide 2.5, sold for 3.2. A mate sold around that time too, he was expecting 2.5 and sold for 2.9."
> — `Caru`, 16 Aug 2021, [Whirlpool: "The property price estimates"](https://forums.whirlpool.net.au/archive/9m010y77) · forum

> "Watch the prices in this place. Ticket price is not the real price."
> — `ilyeq2`, ~2025, [ProductReview — Domain](https://www.productreview.com.au/listings/domain-com-au) · review site

NSW Fair Trading states the purpose of the laws in exactly the buyer's terms: they exist so that *"buyers don't waste money and time on property inspections, getting reports and attending auctions for properties that will likely be out of their price range"* ([NSW Fair Trading underquoting guidance](https://www.fairtrading.nsw.gov.au/housing-and-property/property-professionals/working-as-a-property-agent/underquoting)).

**Frequency: DOMINANT.** Forums (multiple threads, 2021→2025), consumer bodies in three states, CHOICE, news, and $3M+ in Victorian fines and 8,800+ complaints. The Whirlpool quotes are from 2021 and are 🔴 stale as *dated* evidence, but the 2024-25 regulator statistics confirm the behaviour is current.

---

### 3.3 DOMINANT — "The automated estimate on my own house is wildly wrong"

The most emotionally charged theme in the review corpus, and highly relevant to any Fields valuation surface.

**On Domain:**
> "Their home price estimates can be incorrect by hundreds of thousands of dollars. Beware."
> — `PSm`, ~2025, [ProductReview — Domain](https://www.productreview.com.au/listings/domain-com-au) · review site

> "Their property valuations are wildly inaccurate... can be hundreds of thousands of dollars off."
> — `Ladybird`, ~2026 (5 months prior to access) · same

> "Most terrible algorithms. My property went down by about 700k in 1 Month."
> — `Bilal N.`, ~2024 · same

> "Valued my property at $550,000 less than an identical unit 2 floors below me."
> — `Tracy S`, ~2024 · same

> "Domain has the impertinence to put wildly inaccurate valuations on properties"
> — `Mac`, ~2024 · same

> "This site is a waste of time and grossly inaccurate in terms of house values."
> — `J.M.C`, ~2025 · same

**On realestate.com.au:**
> "This websites estimates are so far off as others have stated. I contacted them to get a true reflection and after over 20 emails back and forward they said they couldn't or wouldn't change it."
> — `Stephen B.`, ~2023, [ProductReview — REA p.3](https://www.productreview.com.au/listings/realestate-com-au?page=3) · review site

> "In the last 3 months my house has dropped 40k increased 50k and dropped 40k, is this even possible"
> — `Mr G` (WA), ~2022 · same

> "My house keeps going down while neighbour house keeps going up. Both properties exact same size block."
> — `Bilal N.` (NSW), ~2023 · same

> "My property estimate value was too low. The variance in sales estimate advertised is 300K... 18 months later nothing has been done to correct the value."
> — `Very Unhappy Customer`, ~2022 · same

> "Our home is stunning and has everything you could ever want, yet it still shows as vacant land."
> — `SCL` (QLD), ~2022 · same

> "The apartment in the photo is not the apartment the 'estimated value' relates to... No person has inspected the property."
> — `Neil` (QLD), ~2020, [ProductReview — REA p.4](https://www.productreview.com.au/listings/realestate-com-au?page=4) · review site

**Forum, more measured:**
> "The price estimates are built on good data but the models are shockingly bad."
> — `dreamrunner`, 10 Aug 2021, [Whirlpool](https://forums.whirlpool.net.au/archive/9m010y77) · forum

> "estimates are usually based off figures that are a few months old. Add to that they are very rough guides."
> — `ColdRain`, 2 Aug 2021 · same

**Expert framing (CHOICE, 🔴 2017 — stale but conceptually intact):**
> "an online estimate isn't a valuation – rather, they're price estimates and they provide indicative averages"
> — Vince Mangioni, Assoc. Prof., UTS, [CHOICE](https://www.choice.com.au/money/property/buying/articles/property-valuations-and-price-estimates)

> "an acceptable margin of error is plus or minus 10%"
> — Tyrone Hodge, then-Chair, Australian Property Institute, same source

**Frequency: DOMINANT.** The largest single cluster of ProductReview complaints for *both* portals.

**Critical nuance for Fields:** the specific grievance is almost never "the number is imprecise." It is **(a) volatility** — the estimate swinging six figures month to month with no explanation; **(b) relative injustice** — "why is my neighbour's higher than mine when my block is identical"; and **(c) no recourse** — "20 emails and they wouldn't change it". A confidence range alone does not fix this. **Showing the comparables and the adjustment reasoning does.** This directly validates the existing Fields adjusted-comparables approach over a single reconciled figure.

---

### 3.4 DOMINANT — Filters that don't work; results that ignore what you asked for

The most numerically frequent complaint by raw count across ProductReview.

> "Typed in specific suburb. Filter is useless! Got virtually every other suburb except the one i was looking for."
> — `Ron B.`, ~2025, [ProductReview — REA p.2](https://www.productreview.com.au/listings/realestate-com-au?page=2) · review site

> "Search properties under $300,000 and it gives you several pages of properties selling for over $1,000,000"
> — `Disgusted`, ~2024 · same

> "I put in my town to see what houses are up for sale and they bring up every house that is know where near our town it is useless"
> — `Brett`, ~2026, [ProductReview — Domain](https://www.productreview.com.au/listings/domain-com-au) · review site

> "Terrible website, filters do nothing and the search only returns 50% that realestate.com finds."
> — `simon p.`, ~2025 · same

> "The app is almost impossible to navigate. Filters NEVER work."
> — `Baloo`, ~2026 · same

> "Useless website. Filters are a waist of time."
> — `Ron B.`, ~2025 · same

> "You can't refine your search. If you put some filters on listing mode and then go on map view mode, all the filters are deactivated."
> — `Diane P.` (NSW), ~2021, [ProductReview — REA p.4](https://www.productreview.com.au/listings/realestate-com-au?page=4) · review site

> "Filter to exclude under contract/offer does not work... No options to exclude auctions... Viewing properties within specific values shows auction listings."
> — `John` (QLD), ~2021 · same

> "You have the option to un-tick the 'retirement living' in the settings. Doesn't work. You still receive countless 60's only housing."
> — `Simon`, ~2021 · same

> "Can't find anywhere where you can put in land size as acres or ha, just m2 which is hopeless."
> — `sunny_brighton`, ~2021 · same

**Frequency: DOMINANT** by volume — but see the caution in §3.9.

---

### 3.5 RECURRING — Listings stay live after sale / under contract; stale and "fake" listings

> "99% of the properties on this website are already sold. It is a glorified marketing website for real estate agents."
> — `Niko Ros`, ~2025, [ProductReview — REA](https://www.productreview.com.au/listings/realestate-com-au) · review site

> "A lot of listings are obviously fake and just fishing for contact details... many listings that are over a year old"
> — `dmac09876`, review titled *"Has many old and fake listings..."*, 26 Apr 2025, [Domain iOS App Store](https://apps.apple.com/au/app/domain-real-estate-property/id319908646) · app store

> "Sick and tired of looking for home and constantly been told by agents that homes are under contract or sold."
> — `Jenny` (QLD), ~2023, [ProductReview — REA p.3](https://www.productreview.com.au/listings/realestate-com-au?page=3) · review site

> "So sick of agents not updating the listing's. If they are under offer or under contract please add this information."
> — `Biomanoz` (QLD), ~2023 · same

> "Almost nothing is actually available. Almost everything is under contract."
> — `CT407` (QLD), ~2023 · same

> "Properties already under contract (despite using the filter to not show them), yet they still occupy all the premium search results."
> — `Anzai` (NSW), ~2022 · same

> "Don't advertise objects that are not available."
> — `Andrew`, ~2023 · same

**Domain's own help documentation confirms the mechanism:** sold listings are permitted to remain for 72 hours, and *"sometimes the listing is marked as Sold, but the agency has left the listing as For Sale with a 'SOLD' label on it"* — which Domain states violates its own terms and conditions ([Domain Help: Why are there old listings on Domain?](https://help.domain.com.au/hc/en-au/articles/360016962573-Why-are-there-old-listings-on-Domain)).

**Frequency: RECURRING**, strongly concentrated in Queensland reviewers — directly relevant to the Gold Coast market.

---

### 3.6 RECURRING — Enquiring gets you harvested; the "no price" tactic exists to farm contacts

The link between §3.1 and this theme is explicit in the forum voice — buyers understand *exactly* why the price is hidden.

> "what that really means is he gets a whole heap of contacts that he can constantly ring and hassle, put on his data base for future sales once yours has been sold."
> — `Bull69dozer`, 25 Oct 2025, [Whirlpool](https://forums.whirlpool.net.au/archive/3yqqmpll) · forum

`[PARAPHRASE]` Forum user `Catacaustic` in the same thread identified the core strategy as agents wanting buyer contact information before revealing prices, so they can "pick and choose who they think will spend the most money."

> "As soon as I started using app, I started getting spam calls from Bolivia, Bostwana, Congo and other countries" ... "started getting emails from real estate developers which I have never subscribed to"
> — `Sabbu` (NSW, Verified), ~2020, [ProductReview — REA p.5](https://www.productreview.com.au/listings/realestate-com-au?page=5) · review site

> "I am getting emails from agents that i most certainly HAVE not contacted... I have reported them to the ACMA with proof"
> — `will12`, ~2018, same page · review site

> "When asking via Realestate.com.au they email the agent to advise that you want an appraisal, but do not reveal any more information. They request the agent to spend hundreds of dollars to just get the sellers contact details."
> — `Joe bloggs` (QLD), ~2019, same page · review site

**Frequency: RECURRING.** Verified in principle by REA's own commercial model (agents pay for the lead). The `Joe bloggs` quote is the clearest single articulation that **the consumer is the product**.

---

### 3.7 RECURRING — Ad clutter and paid placement pushing results around

> "Realestate.com.au is so slow to load seems like the web site has so much pop up back ground advertising"
> — `Mike` (VIC), ~2020, [ProductReview — REA p.5](https://www.productreview.com.au/listings/realestate-com-au?page=5) · review site

> "Terrible, ad choked, poorly formatted, incredibly slow to load. Uses too much power and drops out because of ads."
> — `Frank Morris` (WA), ~2019 · same

> "Too many adverts, considering how much a seller pays to advertise on RE.com"
> — `inside story` (QLD), ~2019 · same

> "Endless buffering, while advertising initiates... I believe it's the animated ads that take up so much space"
> — `Googler816`, ~2019 · same

**On the paid-tier model (Whirlpool, "REA Online Listing Cost"):**
> "Just got a quote from our REA to list on realestate.com.au: Premier: $2,509"
> — `Lamp Post`, 25 Sep 2024, [forums.whirlpool.net.au/archive/30x1r10r](https://forums.whirlpool.net.au/archive/30x1r10r) · forum

`[PARAPHRASE]` `pm4life` (27 Sep 2024) described REA's model as charging "thousands per listing at $0 marginal cost" and dismissed premium tier marketing as "a perception thing" — and (11 Oct 2024) admitted personally scrolling past premium placements when searching.

`[PARAPHRASE]` `Winston Wolfe` (27 Sep 2024) characterised the REA/Domain duopoly as "bigger... than Coles and Woolworth."

**Academic corroboration:**
> realestate.com.au faces "little competition", has "significantly increased its fees" in recent years, and has been "thwarting disruptive innovations from smaller competitors" — with sellers facing "a lack of alternative platforms offering comparable reach".
> — James Graham, Senior Lecturer in Economics, University of Sydney, [The Conversation, 17 Sep 2024](https://theconversation.com/advertising-a-house-is-ridiculously-expensive-in-australia-could-that-be-affecting-the-property-market-239111) · academic/news

**Frequency: RECURRING.** Note the ad-clutter complaints skew 6–8 years old; the paid-placement/cost complaints are current (2024–25).

---

### 3.8 RECURRING — "This platform serves agents, not me"

The most strategically important qualitative theme.

> "99% of the properties on this website are already sold. It is a **glorified marketing website for real estate agents**."
> — `Niko Ros`, ~2025, [ProductReview — REA](https://www.productreview.com.au/listings/realestate-com-au) · review site

> "Negative reviews for the agents are not displaying to the people. This is dishonesty at best. Misleading people."
> — `Janaka`, ~2025 · same

> "Tried to leave a review about a negative experience with a real estate agent, my review has never been posted"
> — `Rob`, ~2025, [p.2](https://www.productreview.com.au/listings/realestate-com-au?page=2) · review site

> "after having a bad experience with an agent, I left a negative review... only let 5 star postive reviews be up loaded"
> — `Luke W.`, ~2024 · same

> "I randomly searched more than 50 agents... they all had 5-stars! They either had 5-stars or no stars"
> — `Sandro L.`, ~2024 · same

`[PARAPHRASE]` `Kàlmán K.` (~2026) alleged removal of documented agent reviews and suppression of negative feedback because the platform's revenue comes from agent subscribers.

`[PARAPHRASE]` `Dasisnichtgut` (~2024) reported a property being advertised without the owner's consent, creating safety concerns, and accused the platform of prioritising agents over homeowners.

> "Wouldn't give me information about my own ad that I paid for. Ripping people off with overpriced ads"
> — `James`, ~2025, [p.2](https://www.productreview.com.au/listings/realestate-com-au?page=2) · review site

**Frequency: RECURRING and rising** — the agent-review-suppression sub-theme appears repeatedly across 2024–2026 and is the sharpest articulation of misaligned incentives. **Note: these are allegations by reviewers, not established fact. Do not restate as fact in public material.**

---

### 3.9 RECURRING — Wrong data about *my* property, with no way to correct it

Distinct from §3.3 (estimates) — this is factual data being wrong.

> "Domain has listed wrong information about my property... they still haven't done anything about it."
> — `Anon`, ~2025, [ProductReview — Domain](https://www.productreview.com.au/listings/domain-com-au) · review site

> "They have my property listed as sold... I have never had contact with this company."
> — `Geo`, ~2025 · same

> "We are the owners of a house that has incorrectly been listed as sold for an incorrect price."
> — `Robert K.`, ~2025 · same

> "My property has been listed on Domain with a sold price $20000 more than we actually paid... absolutely no response whatsoever."
> — `Linda`, ~2023 · same

> "These clowns can't even get addresses right. A photo of my property was shown under a non-existant address"
> — `Peta H.`, ~2025, [ProductReview — REA p.2](https://www.productreview.com.au/listings/realestate-com-au?page=2) · review site

**Frequency: RECURRING**, and notably concentrated in the *most recent* Domain reviews. The common thread is **no correction pathway** — every one of these reviewers says nobody responded.

---

### 3.10 ISOLATED-to-RECURRING — Missing floor plans and thin listing content

Weaker in raw consumer voice than expected, but **strongly supported by REA's own data.**

> "PLEASE whenever possible, add the floor plan... If one can do it for most apartments, why not all properties?"
> — `Feone` (NSW), ~2021, [ProductReview — REA p.4](https://www.productreview.com.au/listings/realestate-com-au?page=4) · review site

**The quantitative case is far stronger than the anecdotal one:**
- **Only 22% of listings include more than five property features** — REA Property Seeker Survey 2024, n=13,400 ([REB, 28 Oct 2024](https://www.realestatebusiness.com.au/marketing/28906-biggest-ever-home-hunter-survey-reveals-what-aussies-want-from-listings)).
- Buyers actively want, and are not reliably given: *"the property's sale history, public transport options and the year the property was built"* (same source), plus building history, local services, school zones, crime rates, natural hazards, and inspection/auction attendance numbers ([APU](https://australianpropertyupdate.com.au/apu/property-buyers-demanding-more-information-and-taking-their-time)).
- Buyer search duration nearly doubled from 23 weeks (2022) to **44 weeks (2024)** — REA attributes this to buyers *"slowing down and undertaking more research"*, having moved from *"fear of missing out"* to *"fear of a better option"*.

**Frequency: ISOLATED in consumer voice, DOMINANT in survey data.** Consumers apparently don't articulate "there's no floor plan" as a complaint — they just take 44 weeks instead of 23. That is a *behavioural* signal, not a stated one.

---

### 3.11 ISOLATED — Misleading photography

> "The apartment in the photo is not the apartment the 'estimated value' relates to."
> — `Neil` (QLD), ~2020, [ProductReview — REA p.4](https://www.productreview.com.au/listings/realestate-com-au?page=4) · review site

Broad complaints about wide-angle real-estate photography distorting room size exist ([DPReview forum](https://www.dpreview.com/forums/thread/4560743), [Maria Killam](https://mariakillam.com/the-problem-with-wide-angled-photos/)) but are **overwhelmingly US-sourced and photographer-sourced, not Australian buyer-sourced.**

**Frequency: ISOLATED in Australian consumer voice.** Treat "buyers complain about misleading photos" as **not established** for the Australian market on this evidence.

---

## 4. Themes probed but NOT substantiated

These are deliberate negative findings. Each was actively searched for and each result is a useful constraint.

### 4.1 ❌ Published AVM accuracy statistics for PropTrack Estimate or Domain Home Price Guide — DO NOT EXIST publicly

Five separate searches found **no published median absolute percentage error, no "% within 10%", no "% within 20%", and no forecast-standard-deviation figures** for PropTrack Estimate, the Domain Home Price Guide, or the CoreLogic/Cotality AVM. Broker Daily quotes PropTrack product leaders claiming *"incredible accuracy in our predictions"* with no supporting number.

The only accuracy benchmarks located are:
- *"an acceptable margin of error is plus or minus 10%"* — Tyrone Hodge, then-Chair, Australian Property Institute, [CHOICE](https://www.choice.com.au/money/property/buying/articles/property-valuations-and-price-estimates), **last updated 4 May 2017** 🔴 **STALE**. This is a *professional valuation* tolerance, not an AVM accuracy measurement.
- A **defunct competitor's** marketing claim: RealAs said it could *"predict prices within 10% of the sale price 90% of the time"* — and CHOICE explicitly appended: *"We haven't rigorously tested their claims."*
- The commonly repeated "AVMs are accurate within ±10% for well-traded properties with high confidence scores" appears in SEO/blog content with **no traceable primary study**.

> **This is a strategic finding, not just a gap.** The market leaders publish audience numbers to two decimal places and **publish nothing about how wrong their estimates are.** Meanwhile §3.3 shows their estimate accuracy is the loudest complaint they receive. Any operator that publishes a genuine, methodologically honest backtest is doing something no incumbent does. It also means Fields has **no external benchmark to compare against** — a Fields accuracy claim cannot be framed as "better than PropTrack," because no PropTrack figure exists to beat. (This is consistent with the existing `valuation_backtest_claim_constraints` rule.)

### 4.2 ❌ "More than half of Australian listings hide the price" / "70% in Sydney East and inner Melbourne" — UNSOURCED

Widely repeated. Traced to [re4u.com.au, "The Contact Agent Trap", 23 Mar 2026](https://www.re4u.com.au/p/the-contact-agent-trap), authored by "RE4U Editorial Team". On direct examination, that article provides **no citation, no data provider, no methodology and no link** for any of:
- "More than half of Australian property listings don't show a price"
- "upwards of 70% of listings hide the price entirely" (Sydney Eastern Suburbs, inner Melbourne)
- "buyers in markets dominated by hidden pricing pay between 5% and 10% more" — attributed only to *"research from several property analytics firms"* (unnamed)

**Do not use these numbers.** The only *sourced* price-availability data located is the [Compare the Market / PRD study](https://www.comparethemarket.com.au/news/why-brisbane-buyers-are-kept-in-the-dark-over-house-prices/) — and that is from **September 2021** 🔴.

### 4.3 ❌ Consumer complaints about missing strata / body corporate fees in listings — NOT FOUND

Extensively searched. Abundant *advisory* content exists telling buyers to check strata levies before purchase, but **no consumer complaint was located anywhere** — ProductReview, app stores, Whirlpool, or news — saying "the listing didn't show the body corporate fees." Either buyers accept this is found in the contract/strata report stage, or the complaint exists in channels this research could not reach (Reddit). **Theme is unverified — do not assume it is a live grievance.**

### 4.4 ❌ Consumer complaints about missing running costs (council rates, insurance) — NOT FOUND

Same as above. No consumer voice located. Note this is *adjacent* to a confirmed finding — buyers do want "natural hazards" and cost-relevant context per the REA survey — but the specific "show me the rates and insurance" complaint is **not substantiated**.

### 4.5 ❌ Australian consumer complaints about missing flood/bushfire/easement data on listings — NOT FOUND in consumer voice

The *need* is very well established from the supply side: the [Climate Council](https://www.climatecouncil.org.au/resources/property-value-report-how-climate-change-could-worsen-australias-42-billion-flood-risk/) explicitly says *"to date, there has been limited detail available to individual homeowners on what the risk to their greatest asset already is"* and calls for standardised risk disclosure; 1 in 6 homes are flood-exposed; QLD carries $19bn of the $42.2bn impact. REA's own survey lists "natural hazards" among things buyers research.

But **no Australian buyer was found complaining that a listing omitted flood risk.** One near-miss: ProductReview user `SLB` complained an *agent* failed to disclose conservation overlays costing "thousands more" — an agent-disclosure complaint, not a portal-data complaint.

Also worth noting as a caution: **Zillow added First Street climate-risk data to US listings in 2024 and subsequently removed it** after complaints it harmed sales ([Yahoo](https://www.yahoo.com/news/articles/zillow-deletes-climate-risk-data-182756268.html)). No evidence was found that REA or Domain has ever shipped comparable risk data on Australian listing pages.

### 4.6 ❌ "Is this priced fairly?" and "honest comparison between similar homes" — NO DIRECT CONSUMER ARTICULATION FOUND

> ⚠️ **SUPERSEDED 2026-08-06.** The PropertyChat corpus contains people asking this question directly and repeatedly — as a recurring thread genre ("Price Estimation [NSW]", "How much would you pay/what's this property worth now?"), and explicitly *after* rejecting the portals' automated estimates. The need is **articulated, not merely inferred**; consumers just direct it at other humans rather than at the portal. See ADDENDUM §4. The reasoning below is retained because the behavioural evidence still stands.

No consumer was found using language like "I want to know if this is priced fairly" or "compare this to similar homes honestly." **However, this is arguably the strongest *inferred* finding in the document.** Consumers never name the missing capability; they only describe symptoms of its absence:
- 55% want price clarity *before inspecting* (§2.3)
- 72% skip listings with no price (§2.3)
- "take the highest quoted range, add 10%" — buyers building private heuristics because the portal won't answer (§3.2)
- "Valued my property at $550,000 less than an identical unit 2 floors below me" — a *comparison* grievance expressed as an estimate grievance (§3.3)
- Search duration 23 → 44 weeks (§3.10)

Treat as **strongly implied, never stated.** This is normal for latent needs, but it means it cannot be evidenced with a quote — only with the behavioural pattern.

### 4.7 ⚠️ "The apps are terrible" — REFUTED as a general claim

See §3.0. REA iOS **4.8/5 from 291,000 ratings**; Domain iOS **4.7/5 from 116,000**; REA Android **4.5/5 from 76,200**. The App Store review sample retrieved for REA was predominantly *positive* ("The developers did an amazing job! The experience is beautiful and thoughtfully designed." — `henrytofu`, 4 Feb 2022). **Any pitch premised on "the portals' apps are bad" is contradicted by 480,000+ ratings.** The portals are good at browsing and bad at *answering*. That distinction must be preserved.

### 4.8 ⚠️ Filter complaints (§3.4) are the highest-*count* theme but may be the lowest-*value* one

Two cautions. First, many filter complaints date from 2019–2022 and may be fixed. Second, they are the easiest thing for a frustrated user to articulate — high count is partly an artefact of low articulation cost. Contrast §3.10, where the real deficiency (thin listings) produced almost *no* complaints but a doubling of search duration. **Complaint frequency is not a proxy for problem value.**

### 4.9 ❌ property.com.au — essentially no consumer voice exists

property.com.au has **no ProductReview listing at all**. The only signal located is a Trustpilot score of **1.9/5** ("Poor"), obtained via search snippet only (403 on fetch), with review text unretrieved. Contextually, property.com.au appears to be a **directory powered by realestate.com.au** rather than an independent portal ([The Real Estate Voice](https://www.therealestatevoice.com.au/property-com-au/)) — 🔴 **this ownership/relationship claim is low-confidence and should be verified before use.** Separately, CoStar (which completed its ~A$3bn Domain acquisition on 27 Aug 2025) bought the **homes.com.au** domain for a reported A$22.8M, so the portal landscape is actively shifting.

**Conclusion: property.com.au is not a meaningful source of consumer voice and should be dropped from the research frame.**

---

## 5. Evidence gaps — what we would need to measure ourselves

### 5.1 Reddit — the biggest hole (HIGH priority, ~~LOW~~ **BLOCKED — needs a Will decision**)

> **Status 2026-08-06:** attempted and **not resolved**. Bright Data refuses `reddit.com` without completed KYC; all redlib mirrors are behind bot-checks; the PullPush archive API worked briefly then blocked us with *"This website does not provide free scraping resources for agents"* — an explicit refusal that was respected, not circumvented. No Reddit data was retained. Three options (Bright Data KYC / paid PullPush / Reddit's official API) are laid out in **ADDENDUM §6**. Everything below still stands as the plan once access exists.

Zero Reddit evidence is in this document (§1.2). Reddit is where unfiltered Australian buyer voice actually lives, and its absence means the themes above are skewed toward people angry enough to use a formal review site. **Action:** run these searches from an unblocked machine — r/AusProperty, r/AusFinance, r/australia, r/melbourne, r/sydney, r/brisbane for: `underquoting`, `price guide`, `contact agent`, `realestate.com.au`, `Domain estimate`, `PropTrack estimate`, `property value estimate wrong`. Expect §3.3 and §3.6 to strengthen and §4.3/§4.4 to possibly convert from "not found" to "found".

### 5.2 Current price-guide availability on the Gold Coast (HIGH priority, LOW cost — we already have the data)
The only sourced figure is 🔴 2021 and Brisbane-wide. **Fields already holds ~270 active listings and full scrape history in `Gold_Coast`.** We can compute directly and publish as original research: *what % of Robina / Varsity Lakes / Burleigh Waters listings currently show a numeric price vs "Contact Agent" vs auction-no-guide*, split by price band and property type, as a monthly time series. Nobody else publishes this. It would be a genuinely novel, defensible, editorially-safe data asset.

### 5.3 Our own AVM accuracy, published (HIGH priority, MEDIUM cost)
Per §4.1 no incumbent publishes accuracy. `scripts/valuation_backtest.py` already exists. **Action:** produce median absolute percentage error and % within 5/10/20% on held-out sold properties, with sample size, date range, suburb and property-type breakdown, and explicit statement of what the model cannot do. Publish it. Constraint: per existing memory rule, **never frame as "more accurate than Domain/PropTrack"** — no comparable published figure exists, so such a claim is unfalsifiable and unsafe.

### 5.4 Estimate volatility — the real grievance (HIGH priority, LOW cost)
§3.3 shows the anger is about *swing* and *relative injustice*, not point error. We hold historical valuation runs. **Action:** measure month-to-month movement of our own estimates on unchanged properties. A stability metric ("our estimate for an unchanged home moved less than X% median over 12 months") speaks directly to `Mr G`'s "dropped 40k increased 50k and dropped 40k" and is a claim no portal can currently make.

### 5.5 Listing staleness (MEDIUM priority, LOW cost — we already measure it)
§3.5 is a strongly Queensland-weighted complaint and Fields already runs step 109 coverage checks and sold-detection. **Action:** quantify how long sold/under-contract listings persist as "for sale" on the major portals for our three suburbs. This converts a widely-felt but unquantified grievance into a number.

### 5.6 What buyers actually ask — our own funnel (MEDIUM priority, LOW cost)
§4.6 shows "is this priced fairly?" is never articulated by consumers. We have PostHog, Samantha chat logs, and the off-market discovery deck analytics. **Action:** analyse actual free-text questions asked of Samantha and search/scroll/dwell behaviour on property pages. This is the only route to evidencing a latent need, and existing memory already notes 99% of property-page visitors arrive via a bare-address Google query — i.e. they want to know about *one specific home*, which is precisely the "is this priced fairly?" question in disguise.

### 5.7 Lower-priority verification
- Retrieve Trustpilot review *text* for REA/Domain/property.com.au from an unblocked machine (§1.2, item 2).
- Retrieve Google Play review text (§1.2, item 4).
- Retrieve the PropertyChat PropTrack-accuracy thread (§1.2, item 3).
- Fetch the original Guardian Australia article on REA advertising fees directly rather than via the Whirlpool citation (§2.6).
- Verify the property.com.au ↔ realestate.com.au ownership relationship (§4.9).
- Confirm whether the REA "roughly four in five / 76% / 80%+" confidence statistic has one canonical value (§2.3).

---

## 6. One-paragraph synthesis

The portals are **not broken as browsing tools** — 480,000+ app-store ratings averaging 4.5–4.8 refute that outright. They are broken as **answering tools**, and the evidence for that is unusually strong because *REA itself publishes it*: listings without prices are, in their own executive's words, "the number one source of dissatisfaction on our platform"; 72% of buyers skip a listing with no price; only 22% of listings carry more than five features; and the time to buy a home has nearly doubled from 23 to 44 weeks as buyers grind through research the portal won't do for them. The loudest unprompted consumer grievance — hundreds of reviews across both portals — is that the automated estimate on their own home is wrong, volatile, unjust relative to the neighbour's, and uncorrectable; and neither portal publishes a single accuracy statistic. **The gap is not search. The gap is a defensible, transparent, correctable answer to "what is this home actually worth, and why."**
