# D — Autocomplete Qualifiers: what Australians actually append to a home/address search

**Date:** 2026-08-06 · **Author:** research agent (Fields Orchestrator VM)
**Question:** We know 99% of Google impressions to our address pages are bare addresses with no qualifier. When someone *does* add a qualifier, what is it? Autocomplete is the best free proxy for the underlying question.

**Headline:** Address-level autocomplete produces **no qualifiers at all** — it is structurally incapable of answering the question as posed. The qualifier space only exists one level up, at generic own-home phrasings, and there it is dominated by **valuation**, with a large and under-appreciated second cluster of **"tell me a fact / risk about my house"** (flood, heritage, asbestos, construction, orientation, solar).

---

## 1. Method

### Endpoint (primary)
```
https://suggestqueries.google.com/complete/search?client=firefox&gl=au&hl=en&q=<urlencoded>
```
Verified equivalent (spot-checked, same payload shape):
```
https://www.google.com/complete/search?client=chrome&gl=au&hl=en&q=<urlencoded>
```
Python + `requests`, desktop Chrome UA, **1.0 s sleep between requests**, 3 retries per query.

### Volume & blocking
| Metric | Value |
|---|---|
| Total HTTP requests issued | **772** |
| HTTP errors / 429 / blocks | **0** |
| Queries returning ≥1 suggestion | 401 |
| Queries returning empty `[]` | 371 |
| Distinct cached queries (incl. probe phase) | 802 |

**No blocking occurred. The Bright Data Web Unlocker fallback was NOT used and was not needed.**

### ⚠️ Localisation caveat (material — read before trusting any AU claim below)
`gl=au` barely localises this endpoint. Controlled test on the same seed `how much is my house w`:

| Params | Result |
|---|---|
| `gl=au&hl=en` | worth · worth **australia** · worth **domain** · worth now · worth roughly · worth estimate · worth **nz** · worth for insurance purposes · worth **westpac** · worth calculator |
| `gl=au&hl=en-AU&cr=countryAU` | …identical except `worth uk` replaces `worth nz` |
| **no `gl` at all** | **identical to the `cr=countryAU` variant** |

The suggestion pool is effectively **globally pooled with AU-flavoured items mixed in**, not an Australian-only corpus. Every "Australian intent" reading below is therefore an *inference* from AU-marked tokens (australia, qld, domain, westpac, commbank, corelogic, suburb names), not a guarantee. I report the AU-marked fraction explicitly everywhere rather than presenting the whole harvest as Australian.

### Seed list (all alphabet-expanded: bare seed, seed + trailing space, then seed + each of a–z = 28 queries per seed)

**Real addresses** (6, pulled from `Gold_Coast` collections `robina` / `varsity_lakes` / `burleigh_waters`, filtered `listing_status: for_sale`), each tested in **5 forms** in a probe phase and then **2 forms** alphabet-expanded (`"<street>, <suburb>, QLD <pc> "` and `"<street> <suburb> "`):

- 20 Chantilly Place, Robina, QLD 4226
- 17 Springvale Street, Robina, QLD 4226
- 7 Winton Terrace, Varsity Lakes, QLD 4227
- 8 Morea Court, Varsity Lakes, QLD 4227
- 38 Beaconsfield Drive, Burleigh Waters, QLD 4220
- 6 Joy Avenue, Burleigh Waters, QLD 4220

**Generic own-home seeds (13):** `my house ` · `my home ` · `how much is my house ` · `what is my house ` · `is my house ` · `my property ` · `what's my home ` · `house valuation ` · `property value ` · `who owns ` · `how much did ` · `what did my neighbour ` · `sold price `

**Suburb seeds (3):** `robina house prices ` · `burleigh waters property ` · `varsity lakes homes `

### Analysis rule (important for honesty)
Google frequently returns suggestions that **do not preserve the seed stem** (e.g. seed `how much is my house b` → `how much is bounce house rental` — it silently dropped "my"). Counting those as qualifiers would badly inflate the result. **Only prefix-preserving suggestions are counted as qualifiers.** Of 3,621 raw returned strings from generic/suburb seeds, **2,666 were prefix-preserving and 955 (26%) were off-seed drift and discarded.**

---

## 2. FINDING 1 — Address-level autocomplete produces ZERO qualifiers

This was tested properly and the answer is unambiguous.

**354 address-form queries issued. 317 returned an empty list (89.5%).**

Of the 37 non-empty responses, **not one** appended a semantic qualifier. Every returned string was either the address echoing itself, a geographic completion (suburb/state/postcode), or a *different* address elsewhere in the world.

| Address | Queries | Non-empty | Semantic qualifiers |
|---|---|---|---|
| 17 Springvale Street, Robina | 59 | 8 (14%) | **0** |
| 7 Winton Terrace, Varsity Lakes | 59 | 8 (14%) | **0** |
| 8 Morea Court, Varsity Lakes | 59 | 8 (14%) | **0** |
| 38 Beaconsfield Drive, Burleigh Waters | 59 | 8 (14%) | **0** |
| 20 Chantilly Place, Robina | 59 | 4 (7%) | **0** |
| 6 Joy Avenue, Burleigh Waters | 59 | 1 (2%) | **0** |

**Across the entire a–z expansion, exactly one letter ever completed anything: `q`** — and it completed to the postcode, not a qualifier:

```
'17 Springvale Street Robina q'          -> ['17 springvale street robina qld 4226']
'38 Beaconsfield Drive Burleigh Waters q'-> ['38 beaconsfield drive burleigh waters qld 4220']
'7 Winton Terrace Varsity Lakes q'       -> ['7 winton terrace varsity lakes qld 4227']
'8 Morea Court Varsity Lakes q'          -> ['8 morea court varsity lakes qld 4227', 'largest inland lakes in michigan by volume']
```

Letters `a`–`p` and `r`–`z` returned `[]` for **every one of the six addresses, in both address forms**. There is no `… sold`, no `… value`, no `… worth`, no `… owner`, no `… rates`.

Representative full responses (these are the complete lists, not excerpts):
```
'38 Beaconsfield Drive, Burleigh Waters, QLD 4220'  -> ['38 beaconsfield drive burleigh waters qld 4220']
'7 Winton Terrace, Varsity Lakes, QLD 4227 '        -> ['7 winton terrace varsity lakes qld 4227']
'20 Chantilly Place, Robina '                       -> ['20 chantilly place robina']
'6 Joy Avenue, Burleigh Waters, QLD 4220'           -> []      ← empty
'6 Joy Avenue Burleigh Waters QLD'                  -> []      ← empty
'17 Springvale Street'  -> ['17 springvale street robina qld 4226', '17 springvale street robina',
                            '17 springvale street', '17 springvale road ballywalter',
                            '17 springvale rd reading ma', '17 springvale road', '17 springvale avenue',
                            '17 springvale road nashua', '17 springvale ave frenchs forest',
                            '17 springvale road vic 3171']
```

Note the last one: when you shorten to *street-level* the list fills up — but it fills with **other Springvale Streets around the world**, i.e. geographic disambiguation, still not intent.

### The specificity gradient (this is the real structural finding)

Autocomplete coverage collapses as the query gets more specific. Measured on the alphabet expansions:

| Seed type | Queries | % returning empty | Total suggestions returned |
|---|---|---|---|
| Generic own-home (e.g. `how much is my house `) | 28 each | **0–4%** | ~270–280 each |
| Suburb + category (`varsity lakes homes `) | 28 | **54%** | 67 |
| Suburb + category (`burleigh waters property `) | 28 | **64%** | 49 |
| Suburb + category (`robina house prices `) | 28 | **75%** | 36 |
| **Full street address** | 354 | **89.5%** | 51 (all geographic) |

Google's suggestion index is a **popularity index with a frequency floor**. A specific residential address is queried by a handful of people a year — far below the floor — so no suggestion is ever stored, whatever the qualifier. Even three-word suburb phrases like `robina house prices ` mostly fall below it: only 4 qualified expansions survived across all three suburb seeds (`burleigh waters property for sale / growth / market / prices`, `varsity lakes homes for sale`).

**Implication for the V4 page redesign:** you cannot use autocomplete to learn what people want to know about *a specific address*. The absence is not evidence that people have no questions — it is evidence that **no single address is searched often enough to register**. This is consistent with, and explains, the 99%-bare-address impression profile: people type the address and expect the page to anticipate the question, because Google itself never offers them a qualifier to click.

---

## 3. FINDING 2 — The qualifier space (generic own-home seeds)

**1,833 in-scope prefix-preserving unique suggestions. 1,624 (88.6%) survive the foreign-market filter. Only 168 (10.3% of usable) carry an explicit Australian marker.**

Frequency note: with alphabet expansion, a suggestion's "count" is *how many seed-letters surfaced it*, **not search volume**. Ordering within a Google response is a weak popularity proxy; I preserve that order and do not claim volumes.

### Intent categories, ranked by breadth of qualifier space

| # | Intent category | Unique suggestions |
|---|---|---|
| A | **Valuation — what is it worth** | **432** |
| B | **Sale history — what did it/they sell for** | 144 |
| K | Tool/mechanics — *how do I get this* | 85 |
| G | **Risk / hazard / physical facts about my house** | **71** |
| J | Market direction / forecast | 36 |
| D | Statutory / rates / land value / tax / legal event | 33 |
| F | Neighbour / local comparison | 32 |
| I | Mortgage / equity / insurance / rebuild | 25 |
| C | Ownership / title / boundaries | 18 |
| E | Rent / yield / tenancy | 17 |
| H | Selling process / agent / fees | 14 |

---

### A. VALUATION — "what is it worth" (432) — dominant by a wide margin

Literal suggestions, in Google's returned order:
```
how much is my house worth
how much is my house worth australia          [AU]
how much is my house worth domain             [AU]
how much is my house worth roughly
how much is my house worth now
how much is my house worth estimate
how much is my house worth for insurance purposes
how much is my house worth westpac            [AU]
how much is my house worth calculator
how much is my house valued at
how much is my house actually worth
how much is my house really worth
how much is my house currently worth
how much is my house and land worth
how much is my house appraised for
how much is my house assessed for
what is my house worth
what is my house worth now
what is my house worth domain                 [AU]
what is my house worth qld                    [AU]
what is my house worth perth                  [AU]
what is my house value
what is my house value now
what is my house valuation
what is my house market value
what is my house current value
what is my house currently worth
what is my house assessed value
what's my home worth
what's my home worth domain                   [AU]
what's my home worth today
what's my home worth now
what's my home worth calculator
what's my home worth by address               ← note: "by address"
what's my home's current value
what's my home's current market value
what's my home's fair market value
what's my home estimated value
what's my home market value
what's my home value free
my house value / my house valuation / my house worth
my house value domain                         [AU]
my house value australia                      [AU]
my house price estimate / my house estimate
my property value / my property worth / my property price
my property value australia                   [AU]
my property value domain                      [AU]
my property estimated value / my property value estimate
my property value online / my property value free
property value estimate / calculator / check / search / report / checker
property value calculator australia           [AU]
property value estimator australia            [AU]
property value estimate westpac               [AU]
property value estimate commbank              [AU]
property value estimate domain                [AU]
property value corelogic / by corelogic       [AU]
property value cotality / by cotality
property value anz / cba / commbank / aussie / bank of melbourne  [AU]
property value by address / by suburb
house valuation calculator / estimate / cost / free / online free
house valuation australia / brisbane / sydney / adelaide / canberra / hobart / gold coast  [AU]
house valuation domain / anz / cba / commbank / bendigo  [AU]
house valuation by address / by postcode
house valuation after renovation / after extension
house valuation for mortgage
```

**Reading:** valuation is not one question, it is four distinguishable sub-questions:
1. **the number** ("worth", "value", "how much")
2. **the trust qualifier** — "*actually* worth", "*really* worth", "*roughly*", "estimate", "**fair market** value", "**current** value". People are explicitly hedging against the number they expect to be given.
3. **the source** — `domain`, `corelogic`/`cotality`, `westpac`, `commbank`, `anz`, `cba`, `bank of melbourne`, `aussie`. Australians attach an **institution** to the valuation question. This is the single most AU-distinctive pattern in the harvest.
4. **the access route** — "calculator", "free", "online", "by address", "report".

### B. SALE HISTORY — "what did it sell for" (144)

The highest-signal, lowest-noise finding in the whole harvest. The seed `what did my neighbour ` returned only **two** prefix-preserving suggestions in the entire a–z sweep (18% of its letters returned empty) — and both are exactly on-intent:

```
what did my neighbours house sell for
what did my neighbour pay for their house
```

That is the *complete* set. Narrow, but unambiguous: when the neighbour question is asked at all, it is asked about **price paid**, not about the neighbour.

From `sold price `:
```
sold price history
sold price withheld                ← distinctly Australian pain point (Domain/REA withhold prices)
sold price search / check / data / today
sold price near me
sold prices in my area
sold price map
sold price by address
sold price domain                  [AU]
sold price nsw / sydney / melbourne / perth   [AU]
sold price property / of property / of house / of homes
sold price median / sold price median meaning
sold price commercial property
```
⚠️ This seed is the **most UK-contaminated** in the harvest: `sold prices bristol/birmingham/brighton/cardiff/coventry/edinburgh/glasgow/leeds/liverpool/exeter/derby/…`, `sold price rightmove`, `sold price zoopla`, `sold price land registry`, `sold price gov uk`. "Sold price" is a *British* search idiom (HM Land Registry publishes them). Australians appear to use "sold" + suburb instead. Treat the AU subset only.

### G. RISK / HAZARD / PHYSICAL FACTS (71) — the under-appreciated cluster

The seed `is my house ` is almost entirely **non-valuation**. It is people asking Google to tell them a *fact* about their own home:

```
is my house in a flood zone
is my house in a flood zone nsw          [AU]
is my house at risk of flooding
is my house likely to flood
is my house liable to flooding
is my house in a bushfire zone
is my house in a fire zone
is my house heritage listed              [AU]
is my house heritage listed qld          [AU]
is my house heritage listed nsw / victoria  [AU]
is my house asbestos
is my house brick veneer
is my house double brick
is my house brick or brick veneer
is my house brick or stone
is my house made of brick or stone
is my house good for solar
is my house good for solar map
is my house a good candidate for solar
is my house eligible for solar panels
is my house east facing
is my house east or west facing
is my house north facing
is my house facing south
is my house connected to nbn
is my house nbn ready / nbn connected
is my house fttp / fttp or fttn
is my house gas or electric
is my house earthquake safe
is my house an asset for aged pension    [AU]
is my house in a conservation area
what is my house made of
what is my house built on
what is my house built out of
what is my house roof made of
what is my house flood zone
what is my house elevation
what is my house facing
what is my house orientation
what is my house energy rating
how much is my house above sea level
my house always smells musty / my house feels damp
```

**This matters for Fields specifically.** "Does Burleigh Waters flood" is already the single most-returned suggestion in our own stored corpus (546 occurrences — see §4). Flood/hazard is not a footnote to the valuation question; it is a **parallel first-order question** that the same homeowner has about the same address. An address page that answers only "what is it worth" answers roughly half of what this evidence says people want.

### F. NEIGHBOUR / LOCAL COMPARISON (32) — the "by address / near me" pattern
```
what did my neighbour pay for their house
what's my home worth by address
house valuation by address
house valuation by postcode
house valuation near me / house valuations near me
house valuation in my area
house valuation map
property value by address
property value search by address
property value history by address
property value by suburb
property value growth by suburb
property value increase by suburb
property value map / lookup map / heat map
property value near me
sold prices in my area
sold price near me
sold price map
my property boundary map / my property lines map / my property map
```
The recurring modifiers are **`by address`**, **`near me`**, **`in my area`**, **`map`**. People want the answer *keyed to a location and shown in context of its surroundings* — which is precisely the address-page + comparables shape.

### D. STATUTORY / RATES / LAND VALUE / TAX / LEGAL EVENT (33)
```
what is my house zoning / my property zoning / my house zoning
what is my house rateable value
what is my house annual value
what is my house tax band
my property rates / my property tax / my property tax bill
property value rates / property value tax / property value vs tax assessment
house valuation for probate / probate purposes
house valuation for divorce
house valuation for separation
house valuation for cgt purposes
house valuation for capital gains tax     [AU]
house valuation for tax purposes
is my house subject to capital gains tax  [AU]
is my house an asset / considered an asset / an asset for aged pension  [AU]
is my house a listed building / listed building / in a conservation area
```
**Life-event triggers are explicit:** probate, divorce, separation, CGT, aged pension. These are valuation *reasons*, not valuation *methods*.

### C. OWNERSHIP / TITLE (18) — and a clear negative result
```
what is my house lot number
what is my house lot size
what is my house parcel number
what is my house title number
is my house freehold / leasehold / freehold or leasehold / joint tenancy
my property deed / my property dimensions / my property floor plan / my property boundaries
```
**Negative finding on `who owns `:** the a–z sweep returned 260 prefix-preserving suggestions and they are **entirely corporate** — `who owns coles`, `who owns woolworths`, `who owns bunnings`, `who owns domain`, `who owns optus`, `who owns anthropic`, `who owns bluey`… **Not a single one refers to a residential property or address.** "Who owns [a house]" is not a live public search pattern in this data. If the V4 page plans an ownership/title angle, autocomplete gives it **no support**.

**Negative finding on `how much did `:** likewise 260 suggestions, entirely entertainment/celebrity/corporate (`how much did avatar make`, `how much did elon musk pay for twitter`, `how much did el jannah sell for`). Zero property. The "how much did [X] sell for" frame exists in the language but is not attached to houses at generic level — it only appears when the seed already contains "my neighbour" (category B).

### K. TOOL / MECHANICS (85) — how they expect to get the answer
```
house valuation online / online free / free
house valuation calculator
house valuation how does it work
house valuation what do they check
house valuation how long does it take
house valuation certificate
property value check / checker / search / report / free / free online
property value app / api / data / finder
my property value online / my property value free
what is my house value online
sold price search / check
```
`house valuation how does it work` and `house valuation what do they check` are direct evidence of **methodology curiosity** — which is exactly the transparency angle Fields already leads with.

### E, H, I, J — thinner but present
- **Rent/yield (17):** `how much is my house to rent`, `how much is my house rent worth`, `is my house for rent`, `my property for rent`.
- **Selling process (14):** thin at generic level — mostly `my property for sale`, `is my house going to sell`, `is my house for sale`.
- **Mortgage/equity/insurance (25):** `what is my house equity`, `how much is my house payment`, `how much is my house insurance`, `how much is my house rebuild cost`, `how much is my house worth for insurance purposes`, `what is my house buying power`, `what is my house budget`.
- **Market direction (36):** `property value dropping / going down / decrease / down / forecast / growth / graph / guide`, `property value history`.

### Noise the reader should know about
- `my house ` bare is dominated by **"My House" the Australian furniture retailer** (`my house parramatta`, `my house top ryde`, `my house store near me`) and **"My Kitchen Rules"-adjacent TV** (`my house rules 2026`). Not property intent.
- `what is my house ` is heavily polluted by **Harry Potter house quizzes**, **astrology houses**, and **US congressional districts** (`what is my house district texas`). Filtered out of the category counts above.
- `my home ` is dominated by an Indian developer brand ("My Home Group", `my home bhooja price`, `my home krishe rent`) and utility logins.

---

## 4. Cross-check against the corpora we already hold

### 4a. `system_monitor.search_paa_questions` — **NOT usable as frequency data**

| Metric | Value |
|---|---|
| Documents | **37,350** |
| **Unique questions** | **1,011** |
| Inflation factor | **36.9×** |
| Distinct collection dates | **50** (2026-03-14 → 2026-08-04) |
| Distinct `seed_query` values | **23** |
| `depth` field | `'0'` for **100%** of docs |
| `question` actually starts with its stored `prefix` | **65.0%** |

**The user's suspicion is confirmed, and the mechanism is now identified.** 522 of the 1,011 unique questions appear **exactly 50 times** — and there are **exactly 50 distinct collection dates**. The "50×" is simply *the same 23 seeds re-scraped once per day for 50 days*. It is a **re-collection counter, not a popularity signal**. Any ranking built on these counts is ranking "how long has this been in the scrape set", nothing more.

Two further integrity problems:
- `depth` is `0` for every single document — the intended recursive PAA expansion **never ran**. This is a flat one-level scrape mislabelled as a depth-tracked crawl.
- The `prefix` field disagrees with the question 35% of the time (e.g. `prefix: 'why'` attached to `question: 'what is real estate agent fees'`), so `prefix` cannot be used to segment intent.

**Geographic composition (measured on the 1,011 unique questions):**

| Bucket | Unique | % |
|---|---|---|
| AU-marked | 171 | 16.9% |
| **Explicitly non-AU-marked** | **111** | **11.0%** |
| Geo-neutral | 729 | 72.1% |

Top foreign markers: `realtor` (25), `uk` (19), `florida` (14), `california` (11), `ontario` (10), `texas` (7), `nz` (4), `malaysia` (4), `dubai` (3), `philippines` (2), `south africa` (2), `scotland` (2), `spain` (2), `ireland` (2).

**Honest verdict on contamination:** the *explicit* foreign contamination is **11%**, which is **lower than feared** — the corpus is not majority-Californian. But that headline understates the problem, for two reasons:

1. **The 72% "geo-neutral" bulk is not neutral in practice.** Its vocabulary is American/British: `realtor`, `as is`, `for cash`, `closing`, `estate agent`. Strings like `can i sell my house without a realtor`, `how to sell my house as is fast`, `can i sell my house as is for cash` are US-market idioms that happen to contain no place name. Counting them as "usable Australian intent" would be wrong.
2. **The seed set is off-topic for this research question.** All 23 seeds are about the **selling transaction**, not about an address or a home's value:

   | seed_query | docs |
   |---|---|
   | sell my house | 4,969 |
   | property valuation | 3,779 |
   | real estate agent fees | 2,988 |
   | building and pest inspection | 2,905 |
   | choose a real estate agent | 2,653 |
   | capital gains tax property | 2,650 |
   | best time to sell house | 2,487 |
   | sell house as is | 2,378 |
   | sell house fast | 1,942 |
   | interest rates property | 1,812 |
   | cost of selling a house | 1,802 |
   | stamp duty queensland | 1,491 |
   | … (11 more, all transaction/agent framed) | |

   Only **241 of 1,011** unique questions touch own-home/address value intent at all, and much of that is definitional or career noise (`what is property valuation job`, `what is property valuation meaning`, `what is property valuation certificate`, `where can i study property valuation in south africa`, `how much property valuation for australia student visa`).

**Usable fraction for *this* research question:**

| Filter | Unique | % of 1,011 |
|---|---|---|
| Contains a property-value term | 654 | 64.7% |
| …AND not explicitly foreign-marked | 582 | 57.6% |
| **…AND explicitly Australian-marked** | **79** | **7.8%** |

> **Verdict:** `search_paa_questions` is **~1,011 questions pretending to be 37,350**, gathered from 23 transaction-framed seeds, with a broken depth crawl, an unreliable `prefix` field, and counts that are collection repeats. Use it as an **unweighted idea list** (deduplicate to 1,011 first) for *selling-process* content. Do **not** quote its counts as demand, and do **not** treat it as evidence of Australian address-level intent — on the strictest reading only **~8%** qualifies.

Genuinely usable AU-marked examples (these *are* real and on-topic):
`how much is real estate agent commission in qld` · `what are the costs of selling a house in qld` · `how much stamp duty qld house` · `when is the best time to sell house in brisbane` · `how much capital gains tax on property australia`

### 4b. `system_monitor.search_suggestions` — **materially better, same counting caveat**

| Metric | Value |
|---|---|
| Documents | **17,841** |
| Distinct `seed_query` | **360** |
| Distinct collection dates | **50** |
| Suggestion strings extracted | 84,819 |
| **Unique suggestion strings** | **2,267** |
| Parse failures | **0/17,841** |

360 seeds × ~50 dates = 17,841 docs. **Identical re-collection artefact** — a suggestion appearing "50×" appeared once per daily scrape. Counts are *persistence*, not volume. (They do carry weak signal: a string that survived all 50 days is a stable suggestion, whereas one appearing 3× is transient. That is a legitimate but much weaker claim than "popular".)

**Geographic composition — much healthier than the PAA set,** because the seeds are suburb-scoped:

| Bucket | Unique | % | Doc-weighted % |
|---|---|---|---|
| **AU-marked** | **1,366** | **60.3%** | 65.2% |
| Non-AU-marked | 145 | **6.4%** | 5.4% |
| Geo-neutral | 756 | 33.3% | 29.4% |

| Filter | Unique | % |
|---|---|---|
| Contains a property-value term | 792 | 34.9% |
| …AND not foreign-marked (**usable**) | 712 | 31.4% |
| …AND explicitly AU-marked | 352 | 15.5% |

`intent` labels present: sell (4,921), fear (4,088), decision (1,588), buy (1,349), value (1,299), research (1,150), hope (899), invest (798), economic (699), relocation (600), rent (450). `suburb` is `null` on 12,599 of 17,841 (70.6%) — only the 5,242 suburb-scoped docs carry it.

**Top suggestions in the stored corpus (occurrence = days-persisted):**
```
546  does burleigh waters flood        ← by far #1
219  gold coast property market forecast
200  robina median house price
199  burleigh waters median house price
197  varsity lakes houses for sale
183  gold coast property market forecast for next 5 years
175  burleigh waters property prices
173  robina property prices
149  varsity lakes shops
149  varsity lakes directions
147  gold coast property market crash prediction
121  gold coast property market crash
115  varsity lakes property value
```

> **Verdict:** `search_suggestions` is the **usable** corpus of the two — 60% AU-marked, 6% foreign, cleanly parseable, suburb-scoped. Roughly **31% (712 of 2,267 unique)** is directly property-value relevant. Deduplicate to 2,267 before use and treat counts as persistence, not demand.

### 4c. Two gaps in the stored corpora that this harvest exposes

Running the same category regexes over `search_suggestions`:

- **NEIGHBOUR / COMPARISON = 0.** Not one of the 2,267 unique stored suggestions expresses neighbour or same-street comparison — yet the live harvest returned `what did my neighbours house sell for` and `what did my neighbour pay for their house` as the only two things anyone asks after `what did my neighbour`. The stored corpus **cannot see this intent because no seed was ever pointed at it.**
- **OWNERSHIP = 4, all false positives** (`for sale by owner`, `tenants rights qld when owner is selling`). Consistent with this harvest's finding that address-level ownership is not a live search pattern.

Conversely the stored corpus's #1 result — `does burleigh waters flood` (546) — **independently corroborates** category G above from a completely different seed direction. Flood/hazard intent is the most robust non-valuation finding across both datasets.

---

## 5. What this evidence does and does not support

**Supported:**
- Valuation is the dominant qualifier space, and Australians attach an **institution** to it (`domain`, `corelogic`/`cotality`, `westpac`, `commbank`, `anz`, `cba`). Naming your method and source is aligned with how people actually phrase the question.
- People hedge the valuation question explicitly — *actually* worth, *really* worth, *roughly*, *fair market* value, *estimate*. Confidence/range framing matches the language.
- **Flood, heritage, asbestos, construction type, orientation and solar suitability are a first-order intent cluster**, not an afterthought — evidenced independently in both the live harvest (`is my house ` seed, 71 suggestions) and our stored corpus (`does burleigh waters flood`, the single most persistent suggestion we hold).
- `by address`, `near me`, `in my area`, `map` are the recurring access modifiers.
- Life events (probate, divorce, separation, CGT, aged pension) are explicit valuation triggers.
- `house valuation how does it work` / `what do they check` — methodology curiosity is real.

**NOT supported (do not build on these):**
- Any claim about what qualifiers people attach **to a specific address**. Autocomplete returns nothing at address level; this research cannot answer that question and neither can any autocomplete-based method.
- "Who owns this house" as a consumer search pattern — zero evidence, 260 counter-examples all corporate.
- Any **volume or ranking** claim from `search_paa_questions` or `search_suggestions` counts — those are collection repeats.
- Any claim that the harvested pool is Australian consumer intent *as a whole* — only 10.3% of usable live suggestions carry an AU marker, and `gl=au` demonstrably barely localises this endpoint.

---

## 6. Reproduction

Scripts and raw data (scratchpad, not committed):
- `harvest_ac.py` — harvester, 4 phases, resumable JSON cache
- `ac_results.json` — all 802 raw query→suggestion pairs
- `analyse2.py` / `strict.json` — prefix-preserving qualifier extraction
- `corpus_audit.py` — MongoDB corpus audit

Re-run: `python3 harvest_ac.py all` (~20 min at 1 req/s), then `python3 analyse2.py`.
