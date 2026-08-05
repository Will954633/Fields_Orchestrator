# A — What Google Actually Shows for a Bare Residential Address

**Research date:** 2026-08-06 (AEST)
**Scope:** 12 real Gold Coast addresses from Fields' own database (Robina, Varsity Lakes, Burleigh Waters), fetched as live Google SERPs.
**Purpose:** 99% of Google impressions to Fields' `/property/` pages are bare-address queries with no qualifier. The query string carries zero intent signal. This document records what Google itself puts on that SERP — because the SERP *is* Google's model of the intent, and it is also the competitive set for the click.

---

## 1. Method

**Fetch.** This VM's IP is blocked by Google, so all SERPs were pulled through **Bright Data Web Unlocker** (`zone=web_unlocker2`) via `POST https://api.brightdata.com/request`, `format: raw`, against
`https://www.google.com/search?q=<query>&gl=au&hl=en&num=20`.
Retry up to 3×, 180 s timeout, upstream status read from the `x-brd-status-code` response header.

**Queries.** Bare address only — `<number> <street> <street-type> <suburb>`, lowercase, no state, no postcode, no qualifier. This mirrors the real Search Console pattern (e.g. `126 dunlin drive burleigh waters`).

**Parsing.** Google returns a JS-lite SERP whose result markup is partly deferred inside `window.jsl.dh("id","<escaped html>")` JS string literals. `decode.py` unescapes those payloads and flattens them into one HTML document; `parse_serps.py` then extracts structure with BeautifulSoup/lxml. **All parsing was done in Python** — no shell `grep` was run over the HTML (VM safety rule).

On several SERP variants the `<h3>` result anchor href is an obfuscated `/goto?url=…` redirect, so the **publisher domain is read from the rendered `<cite>`**, not from the href.

**Artefacts (all traceable):**

| Path | Contents |
|---|---|
| `…/Page_Redesign_V4/sources/serp/*.html` | 14 raw Google SERPs exactly as returned |
| `…/sources/serp/decoded/*.html` | same, with deferred JS payloads unescaped |
| `…/sources/serp/queries.json` | the 12 addresses + their DB status |
| `…/sources/serp/parsed.json` | structured extraction (organic, related, features, prices) |
| `…/sources/serp/fetch_serps.py`, `decode.py`, `parse_serps.py` | reproducible pipeline |

### The 12 addresses

Selected from `Gold_Coast` collections `robina`, `varsity_lakes`, `burleigh_waters`. Off-market = **no `listing_status` field at all** (cadastral/off-market record) — this is the exact population the `/off-market` pages serve.

| # | Query used | Suburb | DB state |
|---|---|---|---|
| 01 | `13 waitara place robina` | Robina | **sold** 2026-08-03, $1,610,000 |
| 02 | `20 chantilly place robina` | Robina | **for sale** — Expression of Interest |
| 03 | `17 springvale street robina` | Robina | **for sale** — Auction |
| 04 | `5 chantilly place robina` | Robina | **off-market** (cadastral only) |
| 05 | `16 marciana crescent varsity lakes` | Varsity Lakes | **sold** 2026-07-31, $1,225,000 |
| 06 | `25 pristine court varsity lakes` | Varsity Lakes | **sold** 2026-07-27, $1,477,500 |
| 07 | `7 winton terrace varsity lakes` | Varsity Lakes | **for sale** — contact agent |
| 08 | `11 placid court varsity lakes` | Varsity Lakes | **off-market** (cadastral only) |
| 09 | `5 fulmar place burleigh waters` | Burleigh Waters | **sold** 2026-08-03, $1,840,000 |
| 10 | `38 beaconsfield drive burleigh waters` | Burleigh Waters | **for sale** — offers over $2,100,000 |
| 11 | `28 wedgebill parade burleigh waters` | Burleigh Waters | **off-market** (cadastral only) |
| 12 | `30 whitehead drive burleigh waters` | Burleigh Waters | **off-market** (cadastral only) |

4 sold / 4 for-sale / 4 off-market; 4 per suburb. All 12 are houses.

### Fetch failures — honest note

Two of the twelve failed on the first pass with upstream `x-brd-status-code: 502` and an empty body (`08_offmarket_varsitylakes_11-placid-court`, `09_sold_burleighwaters_5-fulmar-place`). Both succeeded on a second run a few minutes later with `200`. **Final state: 12/12 fetched successfully.** No SERP in this report is inferred or reconstructed.

### Control fetches — validating the negative finding

Because the headline finding below is an *absence*, two control queries were fetched through the identical pipeline to prove the pipeline can see the feature when Google serves it:

- `how much is my house worth` → **4 People Also Ask questions extracted**
- `robina qld 4226 property prices` → **4 People Also Ask questions extracted**

So the pipeline detects PAA. Absence of PAA on the 12 address SERPs is a real property of those SERPs, not a scraping artefact.

---

## 2. HEADLINE: there is no "People Also Ask" on a bare-address SERP

**Count: 0 People Also Ask questions across all 12 SERPs. Zero. On every one.**
The literal string `People also ask` does not appear in any of the 12 documents.

There is therefore no consolidated, frequency-ranked PAA list to report, and none is fabricated here.

This is itself the most important artefact in the study, and it is not a null result — it is a positive statement about how Google reads the query:

> Google does **not** treat a bare address as a *question*. It treats it as an **entity lookup**. PAA fires when Google believes the user has an informational question it can decompose (both controls prove this — `how much is my house worth` gets "Can I check the value of my house?", "How to check the valuation of a property?"). A bare address gets no PAA because Google's model is "this person named a *thing*; show them the thing."

Practical consequence for the `/off-market` redesign: **the page is not answering a question. It is resolving an entity.** The winning page is the one that most completely *is* the address — not the one that best answers "what is this house worth?".

---

## 3. What Google shows instead: "People also search for"

In place of PAA, 9 of 12 SERPs carried a **"People also search for"** block. This is Google's *only* stated model of the intent behind a bare-address query, and it is remarkably consistent.

**Every single suggestion, on every SERP, was `<the exact queried address> + one modifier`.** Not one suggestion pivoted to the suburb, the street, the agent, or a generic property question. Google's read is: this person wants *more about this specific address*, along one of a small set of axes.

### Consolidated, frequency-ranked modifiers (22 suggestions across 9 SERPs)

| Rank | Modifier | Count | Appears on |
|---|---|---|---|
| 1 | **`… for sale`** | **8** | sold 2, for-sale 3, off-market 3 |
| 2 | **`… history`** | **4** | sold 1, for-sale 1, off-market 2 |
| 2= | **`… owner`** | **4** | sold 1, for-sale 2, off-market 1 |
| 4 | **`… rent`** / `… for rent` | **3** | sold 1, for-sale 1, off-market 1 |
| 5 | **`… price`** | **2** | sold 2 |
| 6 | **`… reviews`** | **1** | for-sale 1 |

### Verbatim, per SERP

| SERP | Kind | "People also search for" (verbatim) |
|---|---|---|
| 01 `13 waitara place robina` | sold | `13 waitara place robina for sale` · `13 waitara place robina history` · `13 waitara place robina owner` |
| 02 `20 chantilly place robina` | for sale | `20 chantilly place robina for sale` · `20 chantilly place robina rent` · `20 chantilly place robina reviews` |
| 03 `17 springvale street robina` | for sale | `17 springvale street robina for sale` · `17 springvale street robina history` · `17 springvale street robina owner` |
| 04 `5 chantilly place robina` | off-market | `5 chantilly place robina for sale` · `5 chantilly place robina history` |
| 05 `16 marciana crescent varsity lakes` | sold | `16 marciana crescent varsity lakes for sale` · `16 marciana crescent varsity lakes price` |
| 06 `25 pristine court varsity lakes` | sold | `25 pristine court varsity lakes price` · `25 pristine court varsity lakes rent` |
| 07 `7 winton terrace varsity lakes` | for sale | `7 winton terrace varsity lakes for sale` · `7 winton terrace varsity lakes owner` |
| 08 `11 placid court varsity lakes` | off-market | `11 placid court varsity lakes for sale` · `11 placid court varsity lakes history` · `11 placid court varsity lakes owner` |
| 09 `5 fulmar place burleigh waters` | sold | *(none shown)* |
| 10 `38 beaconsfield drive burleigh waters` | for sale | *(none shown)* |
| 11 `28 wedgebill parade burleigh waters` | off-market | `28 wedgebill parade burleigh waters for rent` · `28 wedgebill parade burleigh waters for sale` |
| 12 `30 whitehead drive burleigh waters` | off-market | *(none shown)* |

**Reading it.** The dominant refinement is **availability** (`for sale` / `rent` — 11 of 22, exactly half). Second is **provenance and identity** (`history`, `owner` — 8 of 22). **Price is a distant fifth (2 of 22)** and appeared only on sold addresses.

That last point deserves emphasis because it cuts against the intuitive read. A bare-address searcher, per Google's own refinement data, is *not* primarily asking "what is it worth". They are asking **"is it available, and who has it / what happened to it"**.

`… owner` appearing 4 times — on both sold and off-market addresses — is the most commercially loaded signal in the dataset. Somebody is trying to work out **who owns this house**.

---

## 4. Who ranks for a bare-address query

Total 120 organic results across 12 SERPs (top 10 each). Position 1 was taken by `realestate.com.au` on 8/12 SERPs and `property.com.au` on 3/12; `domain.com.au` took position 1 once (SERP 08, an off-market address).

### Domain frequency and position

| Domain | Results | Best pos | Median pos | sold / for-sale / off-market |
|---|---|---|---|---|
| **realestate.com.au** | **27** | 1 | 3.0 | 9 / 8 / 10 |
| **property.com.au** | **20** | 1 | 3.0 | 6 / 6 / 8 |
| **domain.com.au** | **17** | 1 | 5.0 | 7 / 5 / 5 |
| **onthehouse.com.au** | **10** | 4 | 7.0 | 4 / 4 / 2 |
| coastal.com.au (local agency) | 7 | 3 | 8.0 | 2 / 1 / 4 |
| propertyvalue.com.au (CoreLogic) | 4 | 6 | 7.5 | 0 / 3 / 1 |
| propertyhub.harcourts.com.au | 4 | 5 | 6.0 | 0 / 2 / 2 |
| **allhomes.com.au** | 3 | 4 | 6.0 | 2 / 0 / 1 |
| quietlistings.com.au | 2 | 4 | 4.5 | 1 / 1 / 0 |
| view.com.au | 2 | 6 | 6.5 | 1 / 1 / 0 |
| **fieldsestate.com.au** | **2** | **3** | 4.5 | **0 / 1 / 1** |
| zillow.com (wrong-country match) | 2 | 10 | 10.0 | 0 / 2 / 0 |
| remaxgc.com.au | 2 | 8 | 8.5 | 0 / 0 / 2 |
| **homely.com.au** | 1 | 9 | 9.0 | 1 / 0 / 0 |
| Instagram (agent reel) | 1 | 6 | 6.0 | 1 / 0 / 0 |
| Facebook (agent post) | 1 | 7 | 7.0 | 1 / 0 / 0 |
| youtube.com (agent walkthrough) | 1 | 7 | 7.0 | 0 / 1 / 0 |
| rent.com.au | 1 | 2 | 2.0 | 0 / 0 / 1 |
| soho.ai | 1 | 7 | 7.0 | 1 / 0 / 0 |
| *various single-agency sites* | 11 | 2 | — | mixed |

### Specifically on the domains asked about

| Domain | Appears on | Positions seen |
|---|---|---|
| realestate.com.au | **12/12 SERPs** | 1 (×8), 2, 3, 4, 5, 6, 8, 9, 10 |
| property.com.au | **12/12** | 1 (×3), 2, 3, 4, 6, 7, 8, 9, 10 |
| domain.com.au | **12/12** | 1 (×1), 3, 4, 5, 6, 8, 9, 10 |
| onthehouse.com.au | 9/12 | 4, 5, 7, 8, 9 |
| allhomes.com.au | 3/12 | 4, 6, 7 |
| homely.com.au | 1/12 | 9 |
| **fieldsestate.com.au** | **2/12** | **3** (off-market #11), **6** (for-sale #02) |

### Fields' two appearances, verbatim

- **#11 `28 wedgebill parade burleigh waters` — position 3**, above domain.com.au (4).
  `28 Wedgebill Parade, Burleigh Waters — Off-Market Report`
  → `https://fieldsestate.com.au/off-market/28-wedgebill-parade-burleigh-waters`
  Snippet Google chose: *"Off-market Burleigh Waters. 28 Wedgebill Parade. Burleigh Waters QLD 4220. 603 m² land House. Last recorded sale. $175,000. Oct 1990. Held for. 35.7 yrs. since …"*

- **#02 `20 chantilly place robina` — position 6.**
  `20 Chantilly Place, Robina, QLD 4226 — Property For Sale`
  → `https://fieldsestate.com.au/property/20-chantilly-place-robina`
  Snippet: *"20 Chantilly Place, Robina, QLD 4226 — 5 bed, 2 bath, Offers above $1950000. Property report with valuation, comparable sales, and market intelligence."*

Note the contrast. On the off-market page Google pulled **specific, unique facts** (land size, last recorded sale $175,000 in Oct 1990, held 35.7 years) and ranked it **3rd — ahead of Domain**. On the for-sale page Google pulled a **generic boilerplate sentence** ("Property report with valuation, comparable sales, and market intelligence") and ranked it 6th. The first page said something no one else said; the second said what everyone says.

### Fields is absent from all 4 sold SERPs

`fieldsestate.com.au` did not appear on any of the four sold-address SERPs (01, 05, 06, 09), despite Fields holding sold data for all four. Those SERPs were saturated by portals plus, on #09, **agent social content — an Instagram reel at position 6 and a Facebook post at position 7**, both from the listing agent. A freshly-sold address pulls in social/video results that a portal page does not compete with.

---

## 5. SERP features present

| Feature | Count / 12 | Notes |
|---|---|---|
| **Address map card + Street View** | **12 / 12** | Every single SERP. A single-location card (Street View thumbnail, formatted address, Directions, Share) — *not* a 3-pack of businesses. |
| Map card above result #1 | 6 / 12 | 01, 02, 04, 07, 08, 11 → skews **off-market**; card sits above #1 on 3 of 4 off-market SERPs |
| Map card after results 1–4 | 6 / 12 | 03, 05, 06, 09, 10, 12 |
| **People Also Ask** | **0 / 12** | see §2 |
| People also search for | 9 / 12 | see §3 |
| Sponsored / paid | **1 / 12** | SERP 07 only. Verbatim: *"Sponsored result — 7 Winton Terrace, Varsity Lakes QLD 4227 — Domain — Found the perfect property? Make it your new home with Domain. 1M+ visits in past month."* **Domain paid to be sponsored on a bare-address query for a currently-listed home.** |
| Image pack | 0 / 12 | |
| Video/social results inline | 1 / 12 | SERP 09 (Instagram + Facebook, agent-published) |
| AI Overview | 0 / 12 detected | **Caveat below** |
| Classic knowledge panel (entity card, right rail) | 0 / 12 | the address card is the only entity treatment |

**Caveat on AI Overview.** Bright Data returns a JS-lite SERP variant. PAA *is* rendered in this variant (proven by both controls), so the PAA=0 finding is solid. AI Overview rendering in this variant was **not** independently validated, so "0/12 AI Overview" should be treated as *unconfirmed*, not proven. Everything else in this section was directly observed in the HTML.

**The map card is the single most reliable feature.** 12/12. Google always confirms the address exists and shows the house from the street — before or immediately after the first result. Whatever else is uncertain, the searcher always sees the building.

---

## 6. Does Google show a price/valuation figure directly in a snippet?

**Yes — on 12/12 SERPs, at least one snippet contains a dollar figure.** This is worth being blunt about: **price is already fully commoditised on this SERP before the user clicks anything.**

Classification of the figures shown:

| Figure type | SERPs showing it | Who supplies it |
|---|---|---|
| **Automated estimate / "Estimated Value"** | **10 / 12** | property.com.au (7), propertyvalue.com.au/CoreLogic (4), domain.com.au (2) |
| Historical sold price | 8 / 12 | realestate.com.au (7), domain.com.au (3), propertyvalue.com.au (1) |
| Current asking price | 5 / 12 | realestate.com.au, property.com.au, domain.com.au, view.com.au, quietlistings.com.au, spachus.com.au, **fieldsestate.com.au** |

Concrete examples pulled verbatim from snippets:

- **Off-market #04:** property.com.au *"The property has a $1,836,000 estimated value."* · propertyvalue.com.au *"Estimated Value $1,800,000 - $2,000,000 Date of estimated value: 20 Apr 2026"* · realestate.com.au *"It was sold in 2016 for $670,…"*
- **Off-market #11:** property.com.au *"$2,244,000"* estimate · domain.com.au *"an est… $2.45"* · Fields *"Last recorded sale. $175,000. Oct 1990."*
- **Off-market #08:** property.com.au *"11 Placid Court, Varsity Lakes, Off market $1,834,000 estimated value"*
- **Off-market #12:** property.com.au *"$2,189,000"*

**Two conclusions the redesign has to absorb.**

1. **A number alone is not a differentiator.** For an off-market address, the searcher can already read *three competing automated estimates* off the SERP without clicking. Leading an off-market page with "here's our estimate" enters a race Fields cannot win on brand and cannot win on being first — it can only win on being *shown its working*.

2. **Estimates are more prevalent on off-market SERPs than sold-price facts.** On the four off-market SERPs, "estimated value" figures appeared on **4/4**; on the four sold SERPs, only **2/4**. Nobody has real facts about an off-market house, so everybody guesses — and Google surfaces the guesses. That is the vacuum.

---

## 7. Does the SERP reveal what the searcher wants?

**Yes — but it says something different from what we might have assumed.**

Google's own signals, in order of evidential strength:

1. **No PAA (12/12).** Google does not model this as a question. It is an **entity lookup**. The searcher named a thing and expects the thing.
2. **Map + Street View card (12/12).** Google's first-order answer to "what is this?" is *"here is the physical building, and here is where it is."* The visual identity of the property is the primary confirmation the user is looking for.
3. **"People also search for" (9/12, 22 suggestions, 100% address-scoped).** The follow-on axes are, in order: **availability** (`for sale` / `rent`, 11) → **provenance & identity** (`history`, `owner`, 8) → **price** (2) → **reviews** (1).
4. **Every result title on the page is the address itself.** The competitive set is not "articles about property"; it is "pages that *are* this address".

**So what does Google think the intent is?**
*"Tell me everything about this specific building — starting with whether I can get it, then what has happened to it and who is behind it. Price is table stakes, already answered on the SERP, and not what I refine toward."*

**Where this diverges from the obvious assumption.** The intuitive read of a bare-address query is "they want the valuation". The refinement data does not support that. Only 2 of 22 suggestions carry a price modifier, and both were on sold addresses (where a real transacted number exists and is genuinely findable). Meanwhile `for sale` is the #1 modifier **including on addresses that are not for sale** — 3 of the 8 `for sale` refinements were on off-market addresses, and 2 more were on already-sold ones. People are asking availability questions about houses that are not available.

That is the whole Fields opening. **The bare-address searcher's real question is "can I get this house?" and every incumbent answers "no / not listed / here's an estimate instead".**

---

## 8. How the SERP changes between sold / for-sale / off-market

This is the most decision-relevant section, because the `/off-market` pages target the third case.

### Quantitative: does the top 10 actually talk about *this* address?

Each of the 120 results was classified as (a) about the **exact queried address**, (b) about the **street or a neighbouring house**, or (c) **unrelated** (wrong suburb/state, agency landing page, suburb index).

| Address state | Exact address | Street / neighbour drift | Unrelated | n |
|---|---|---|---|---|
| **Sold** | **33 (82%)** | 6 | 1 | 40 |
| **For sale** | **31 (78%)** | 5 | 4 | 40 |
| **Off-market** | **16 (40%)** | **17 (43%)** | 7 (18%) | 40 |

**This is the finding.** For a sold or listed address, 8 in 10 results are genuinely about that house. **For an off-market address, only 4 in 10 are — and Google fills the other six slots with the neighbours, the street, the suburb, an agency ad, or the wrong state entirely.**

Worked examples of the drift on off-market SERPs:

- **#04 `5 chantilly place robina`** — only 4 of 10 about #5. The rest: a Domain *street profile* for Chantilly Pl, a listing for **#20** Chantilly Place, property pages for **#6** and **#11** Chantilly Place, and a RE/MAX "Real Estate Agents Robina" suburb page.
- **#08 `11 placid court varsity lakes`** — only **2 of 10** about #11. The rest: **#14** Placid Court, **#17** Placid Court, a street-level onthehouse page, two agency landing pages, and **`11 Placid Court, Narangba QLD 4504`** — the same house number and street name in a completely different town 80 km away, ranked at position 6.
- **#12 `30 whitehead drive burleigh waters`** — includes `30 Whitehead Street, Singleton WA 6175` at position 10.
- **#11 `28 wedgebill parade burleigh waters`** — Fields' own off-market page took position 3 precisely *because* it had real, address-specific facts to state (last sale $175,000, Oct 1990, held 35.7 years) in a results set where four other slots were street/agency filler.

### Qualitative differences

| | **Sold** | **For sale** | **Off-market** |
|---|---|---|---|
| Result #1 | realestate.com.au (3/4) | realestate.com.au (2/4), property.com.au (2/4) | realestate.com.au (3/4), domain.com.au (1/4) |
| Address-specific coverage | high (82%) | high (78%) | **low (40%)** |
| Map card placement | mostly *after* result 1 (3/4) | mixed | **above result 1 (3/4)** — Google leads with the building because it has little text to lead with |
| Agent/agency pages | present (Ray White, Opal, Coastal) | strong (Ray White, Harcourts, Coastal, agency-branded pages) | **present but generic** — "Best Real Estate Agents Burleigh Waters", "Real Estate Agents Robina QLD 4226": suburb-level agency landing pages, not this house |
| Social / video results | **yes** (#09: Instagram reel pos 6, Facebook post pos 7, both the listing agent) | one YouTube walkthrough, one Instagram post | **none** |
| Paid ads | none | **1** (Domain sponsored, #07) | none |
| "Estimated value" figures in snippets | 2/4 | 3/4 | **4/4** |
| Real transacted price in snippet | 3/4 (recent, exact) | 2/4 (historical) | 3/4 — but **stale**: 2016 for $670k, 1990 for $175k, 2023 for $1,610,000 |
| Wrong-location results in top 10 | 0 | 2 (both Zillow, US) | 2 (Narangba QLD, Singleton WA) |
| Off-topic drift | minimal | minimal | **heavy** |

### What this means for the `/off-market` redesign

1. **The off-market SERP has a 60% vacancy rate.** Six of ten slots are occupied by content that is not about the house the user typed. There is no equivalent opening on sold or for-sale SERPs, where the portals genuinely own the answer. **Off-market is the only one of the three where Fields can win on relevance rather than on domain authority** — and SERP #11 (Fields at position 3, above Domain) is live proof it already happens when the page carries unique facts.

2. **Uniqueness of fact is what earned the ranking and the snippet.** Google chose "$175,000. Oct 1990. Held for 35.7 yrs" as the snippet for the off-market page, and generic marketing boilerplate for the for-sale page — and ranked them 3rd and 6th respectively. The off-market page should be built to expose facts nobody else states about this specific building: last recorded sale and *when*, tenure length, land size, structural attributes, occupancy signals. Not another estimate.

3. **Do not lead with a valuation number.** Three competitors already show one on the same screen, for free, and Google's own refinement data ranks price 5th out of 6 intents. Leading with a figure puts Fields into a commodity comparison it cannot win, and — per Fields' own editorial rules — a single-figure headline valuation is forbidden anyway. The SERP evidence and the house rule point the same direction.

4. **Answer the availability question head-on.** `for sale` is the #1 refinement and fires *even on addresses that are not for sale*. The off-market page should state plainly and early: this home is not currently listed, here is the last time it was, here is how long it has been held. That is the literal question and no incumbent answers it.

5. **`owner` and `history` together (8 of 22) outrank price 4:1.** Provenance — who has held it, for how long, what has happened to it — is the second-strongest intent and is nearly unserved. A visible ownership/tenure timeline is the highest-leverage content block available.

6. **Match the visual.** Google leads the off-market SERP with a Street View card on 3 of 4 SERPs. The user's first mental image of the address is a street-level photograph of the house. The page should open on the same image so recognition is instant — the click and the landing should feel continuous.

7. **Own the street, not just the house.** Because Google is *already* filling off-market SERPs with street-profile and neighbour pages (17 of 40 results), street-level content is a legitimate secondary surface Google is actively demanding and only Domain/property.com.au currently supply.

---

## 9. Limitations — stated plainly

- **n = 12.** Sufficient to establish a consistent SERP *shape* and to support the 82% / 78% / 40% contrast, which is large and directionally unambiguous. Not sufficient for precise percentages on the "People also search for" modifier mix (22 observations).
- SERPs were fetched **de-personalised via a proxy** (`gl=au&hl=en`), no logged-in user, no location precision beyond country. A real Gold Coast resident on mobile may see a somewhat different mix — most plausibly *more* local/map weighting, not less.
- Fetched **desktop-shaped, JS-lite** HTML. PAA is proven to render in this variant (both controls); AI Overview is not proven either way, so the 0/12 AI Overview count is flagged unconfirmed.
- Single point in time (2026-08-06). SERP composition for recently-transacted addresses moves quickly — SERP #09 already carried a Facebook post from "1 day ago".
- All 12 addresses are **houses**. Units/apartments were not tested and may behave differently (strata complexes often have building-level pages that houses do not).
- Off-market classification is Fields' own DB state (`listing_status` absent). SERP #12 revealed `30 whitehead drive burleigh waters` is **currently listed for rent** at $1,450/week (realestate.com.au pos 3, domain.com.au pos 5, rent.com.au pos 2) — off-market *for sale* is not the same as off-market entirely, and the redesign should not assume an unlisted house is a quiet one.
