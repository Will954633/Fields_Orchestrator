# ADDENDUM — PropertyChat corpus (closes gap §1.2 item 3)

**Parent document:** `EVIDENCE_consumer_voice.md`
**Compiled:** 2026-08-06
**Source:** `sources/propertychat_raw.json` — 35 threads / 335 posts, harvested via Bright Data Web Unlocker
**Harvest script:** `harvest_reddit_propertychat.py`

> **Why this addendum exists.** The parent document's §1.2 lists three unreachable sources. This closes one of them (PropertyChat, HTTP 403) and materially changes **four** of the parent's conclusions. Reddit remains open — see §6.

---

## 0. Access — what changed and why

`propertychat.com.au` returns **HTTP 403** to a direct fetch from this VM and to WebFetch. It returns **HTTP 200** through the **Bright Data Web Unlocker** already provisioned in `.env` (`BRIGHTDATA_API_KEY` / `BRIGHTDATA_ZONE`), the same route `shared/domain_fetch.py` uses for Domain's Akamai block. The earlier session had no reason to know that workaround generalises beyond Domain.

**Date coverage:** 2007 (15 posts) · 2016–17 (106) · 2019–2022 (92) · 2023 (29) · 2024 (39) · 2025 (33) · 2026 (21). **93 posts are 2024 or later**, so this is current voice, not only archive.

**Two parser bugs were found and fixed before any quote below was extracted.** Both would have produced confident, wrong citations, so they are recorded here as a caution for anyone re-running this:
1. A whole-page date scan matched the forum's *recent activity sidebar*, stamping every historical post with the harvest date — a 2007 thread appeared to be from 2026-08-05. Post dates must be read from within each `<li id="post-N">` block.
2. XenForo renders an inline quote of another member as a `<div>`, not a nested `<blockquote>`. Tag-stripping therefore left **one member's words sitting inside another member's post**. In a quotation-based evidence document that is a misattribution, not a formatting glitch.

**Audience caveat.** PropertyChat is a forum of *property investors* — more sophisticated and more transactional than the general buyer. It is a good source for mechanism ("here is how the estimate is wrong") and a poor source for prevalence ("this is what most Australians feel"). Weight accordingly; do not merge its frequencies with ProductReview's.

---

## 1. §3.3 (estimates are wrong) — CORROBORATED, and the mechanism is now much sharper

The parent document already rates this DOMINANT. PropertyChat does not just add volume — it supplies the **controlled comparison** that ProductReview reviewers only gesture at.

**Identical properties, different estimates — the cleanest evidence in either document:**

> "I own 2 identical units next door to each other, they even share a wall. realestate.com.au tells me 1 is 40k more expensive than the other."
> — `LibGS`, 2020-05-26, [Estimated value difference between Domain and Realestate.com.au](https://www.propertychat.com.au/community/threads/estimated-value-difference-between-domain-and-realestate-com-au.45936/)

> "I own an apartment and there is virtually an identical next door... The one next door is around 10sqm **smaller** than mine. Mine has a REA value of $715k. Domain says $710k. The one next door has an REA value of **$852k**. Domain says $685k."
> — `Yamas`, 2020-06-05, same thread

That second quote is the strongest single artefact in the corpus: for two near-identical neighbouring apartments, REA and Domain disagree with each other **and** rank them in opposite orders — and the *smaller* one is valued $137k higher by REA.

**The two portals disagree with each other on the same property:**

> "Domain: $475-615k vs. Realestate: $900K - 1.15M. What would be the reason for this?"
> — `spoon`, 2020-05-25, same thread

**A "high accuracy" label on a range that excludes the actual sale price:**

> "Domain shows it was sold mid 2022 for 430k. It gives a **'high' accuracy** estimate of — Low 340k Mid 395k High 450k. So the low estimate is 90k less than we paid and the high estimate is 20k higher than we paid. Crazy!"
> — `wylie`, 2024-06-13, [How can there be such a discrepancy between valuation estimates?](https://www.propertychat.com.au/community/threads/how-can-there-be-such-a-discrepancy-between-valuation-estimates.77703/)

> "for a block we've just created and are building on, the UCV is $1m and estimated sale range with **'medium confidence'** is $275k to $350k."
> — `wylie`, 2020-06-11, [absolutely gob-smacked](https://www.propertychat.com.au/community/threads/absolutely-gob-smacked.52676/)

**→ DIRECT IMPLICATION FOR FIELDS.** The parent doc (§3.3) concludes that showing comparables and adjustment reasoning fixes this. These two quotes add a constraint it misses: **a confidence label that is not empirically calibrated actively destroys trust.** A range labelled "high accuracy" that does not contain the transacted price is worse than no label — it converts an inaccuracy into a demonstrated false claim. Before Fields displays any confidence level publicly, `scripts/valuation_backtest.py` must show what proportion of *actual* sales fall inside each stated band. This is a prerequisite to the §5.3 publication plan, not a follow-up to it.

**Other corroboration (brief):**
- "Domain and realestate.com give wildly wrong estimates" — `LibGS`, 2020-05-26
- "estimated values out by $300,000 in Brisbane and Perth" — `Propin`, 2024-06-15
- "I looked up my house and Domain it doesnt even show my home. It's a different property." — `Paul@PAS`, 2024-06-14
- "On The House has my house sold at half the price it is worth and it hasnt been sold." — `Ruby Tuesday`, 2024-06-14
- "I find that Domain estimates and REA always **lag (3-4 months)**" — `Rique`, 2024-02-07, [the PropTrack thread §1.2 could not reach](https://www.propertychat.com.au/community/threads/accuracy-of-proptrack-data-in-realestate-com-au-valuations.75688/)

---

## 2. §3.1 (no price) — NEW MECHANISM: the portal *holds* the price and withholds it

This is the most consequential new finding in the addendum, and it changes the parent document's framing of its own DOMINANT theme.

The parent doc treats "Contact Agent" as **agents declining to supply a price**. PropertyChat documents, repeatedly and independently, that **realestate.com.au holds a numeric price for effectively every "Contact Agent" listing** — it must, because price-range filtering works on those listings — and simply does not display it.

> "For potential buyers who want to get around the no price guide issue, there is a way to do it without having to reach out to the agent... open up realestate.com.au on the property... Command-Option-U. It will bring up all this background coding..."
> — `Properwin`, 2025-02-28, ["Hack" to find price range on realestate.com.au when not listed](https://www.propertychat.com.au/community/threads/hack-to-find-price-range-on-realestate-com-au-when-not-listed.82006/)

> "You can also adjust the price range in the filter section and see when property is included in the results."
> — `Firefly99`, same thread

> "I use a Chrome extension called 'Property Seeker' and it shows the price range automatically."
> — `mrdobalina`, same thread

> "Embedded meta data for a price guide. I imagine Fair Trading know this and any lowball searches could already attract Fair Trading concerns."
> — `Paul@PAS`, same thread

> "Listings all have to have a $figure and house type categories otherwise it will be untagged and show up on everyone's search..."
> — `DC Document`, same thread

**Independent corroboration:** the mortgage broker `Properwin` is quoting is **Kobe Clarke-Jacobs** — the same person the parent document already quotes from Yahoo Finance (§3.1). Two unrelated sources, same mechanism.

**→ This reframes §3.1.** "The agent won't tell you the price" is a weaker claim than "the portal knows the price, uses it to sort you into search results, and shows it to the agent's advantage but not yours." The second is a **structural conflict** finding and probably belongs in `EVIDENCE_structural_conflict.md` as well.

⚠️ **Verify before publishing.** Every quote above is a forum user's claim about a third party's product internals. It is consistent across five posters and matches a named broker's public statement, but Fields should reproduce the behaviour directly (inspect a live "Contact Agent" listing's embedded data; confirm price-band filtering returns it) before asserting it publicly. Do not publish on forum testimony alone.

---

## 3. NEW THEME — estimates are suppressed exactly when a buyer most needs them

Not present anywhere in the parent document.

> "The listing software Realestate & Domain both **remove the estimated price for properties which are currently on the market**. If it is a property not on the market, it will give you a price estimation."
> — `DC Document`, 2024-07-22, [Why no price?](https://www.propertychat.com.au/community/threads/why-no-price.79034/)

> "Hard to believe an independent real estate website couldn't continue showing the estimate while a house is on the market. **They all just happen to hide it. Every one of them.**"
> — `alexpreston`, 2024-07-22, same thread

**→ STRATEGICALLY THE MOST IMPORTANT FINDING FOR THE V4 PAGE.** The independent estimate exists for a home right up until the moment it goes to market — the one moment a buyer is actually deciding what to pay — and is then withdrawn across every portal simultaneously. If verified, this is the sharpest available articulation of "the portals are browsing tools, not answering tools" (parent §6), and it defines a capability gap Fields can occupy directly.

⚠️ Same verification caveat as §2 — reproduce it against live listings before it appears in public copy.

---

## 4. §4.6 ("is this priced fairly?") — UPGRADE from *inferred* to *directly articulated*

The parent document's §4.6 states no consumer was found articulating this need, and treats it as "strongly implied, never stated." **That conclusion should now be revised.** PropertyChat contains an entire recurring thread *genre* of people asking other humans the question the portals won't answer:

> "What will you pay for the following properties — [two Domain listings]. I have realized that the price estimate reports from CoreLogic and different banks are **almost always inaccurate**. Posting the properties here to understand the public sentiment and what people are willing to pay for the advertised property."
> — `KeepHustling`, 2023-03-13, [Price Estimation [NSW]](https://www.propertychat.com.au/community/threads/price-estimation.71208/)

> "I'm looking at a few properties with what I believe have unrealistic asking prices... Asking price 970k for one of them but domain and realestate.com have them at around the 650k to 900k... I think a fare price would be low 800s. Will need to engage a valuer I suppose?"
> — `Property Baron`, 2020-06-24

Thread titles in the corpus of this genre include *"How much would you pay/what's this property worth now? [VIC]"* and *"Price Estimation [NSW]"*.

**→ Revised finding:** consumers *do* articulate "is this priced fairly?" — but they ask **other people**, not the portal, and they do so **after** explicitly rejecting the portal's automated estimate as unreliable. That is a stronger and more actionable finding than the parent's "latent need", because it identifies both the demand and the substitute currently absorbing it.

---

## 5. Additional findings

### 5.1 NEW — the estimate as commercial injury to a *seller* (relevant: Fields is seller-funded)

> "The undervalued estimate value **puts pressure on the seller to come down to their estimate**... The site refused to remove their massively undervalued estimate when asked to do so. They advised that I needed a real estate agent to value my property."
> — `tilt10`, 2023-03-09, [How to Remove undervalued Estimate values from Real Estate sites](https://www.propertychat.com.au/community/threads/how-to-remove-undervalued-estimate-values-from-real-estate-sites.71162/)

> "Who gave them the right to even rate my home and publicly display their inaccurate and downgrading 'guestimates'??? If it is low confidence, ie they dont know..."
> — `Kholod45`, 2026-07-23, same thread — **the most recent post in the corpus**

Balancing counterpoint, kept deliberately:
> "I wonder if sellers would feel the same when the estimate showing is way more than market value?"
> — `Lindsay_W`, 2026-07-23, same thread

The parent doc frames wrong estimates as homeowner *annoyance*. For a seller mid-campaign it is a **live commercial harm**, with **no removal pathway** — and note the portal's reported response was to direct them to an agent, i.e. into the revenue funnel.

### 5.2 §3.5 (stale/wrong data) — NEW MECHANISM: agent-inflated *sold* prices

> "I've known agents to report an **inflated sold price** to try to influence the local market where they've got a lot of other listings... A recent sale was listed as sold, well above the actual sale price. The client called the agent on it because they'd attended the auction."
> — `Peter_Tersteeg`, 2024-06-11, [Real estate "contact agent" price](https://www.propertychat.com.au/community/threads/real-estate-contact-agent-price.77652/)

> "rely on the SOLD prices as quoted on sites such as domain.com and realestate.com, a word of warning: DON'T!! THEY ARE NOT NECESSARILY ACCURATE."
> — `Jacque`, 2007-02-23 🔴 — cited only to show the complaint is ~19 years old, not as current evidence

Sold prices are the **input to every AVM**, including ours. This is a data-integrity risk for Fields, not only a competitor criticism — it argues for the existing preference for verified/multi-source sold data (`union_median_pipeline`, `onthehouse_scraping`).

### 5.3 Off-market — directly relevant to the V4 page

> "So realestate.com.au did a study into themselves and found that their website gets you a better result than not using their website? **Bit of a conflict of interest there don't you think?**"
> — `10khours`, 2023-07-24, [Off-market home sales usually result in lower prices, research finds](https://www.propertychat.com.au/community/threads/off-market-home-sales-usually-result-in-lower-prices-research-finds.73082/)

This is a consumer spontaneously identifying the exact structural conflict — REA-owned PropTrack publishing research concluding that advertising on REA is worth +4.3%. Belongs in `EVIDENCE_structural_conflict.md`.

> "99% of those 'off market' listings then end up on REA and Domain anyway once the vendor has gauged the levels of interest."
> — `MB18`, 2024-10-12

> "A lot of property changes hands and nobody even knows."
> — `Ruby Tuesday`, 2025-08-12

### 5.4 ⚠️ NEW RISK SIGNAL — privacy backlash at being shown your own home

Not in the parent document, and it cuts **against** the off-market product, so it is recorded prominently rather than buried:

> "Typed in the address under search just in case there was a listing of it and up came a domain listing, not only with pictures, but an estimate of what it is worth. **Bit of an invasion of privacy**... what absolutely floored me was they had even estimated **what we owe on it**."
> — `Fernfurn`, 2020-06-11, [absolutely gob-smacked](https://www.propertychat.com.au/community/threads/absolutely-gob-smacked.52676/)

Fields' off-market discovery deck shows people data about their own homes. This is direct evidence that some owners experience exactly that as a violation — particularly *inferred financial* data (Domain's estimated outstanding loan). The lesson is not "don't do it" (`Terry_w`'s reply, "every property in Australia is listed like that now, it's public information", is the majority view) but: **derived financial inference is where the line got crossed**, and Fields should stay on the public-record side of it.

### 5.5 Negative findings — CONFIRMED, matching the parent document
- **§4.3 strata / body corporate fees in listings** — searched; **no complaint found**. Parent's negative finding holds across a second independent source.
- **§4.4 running costs (rates, insurance)** — same; **not found**.
- **§4.5 flood / bushfire / hazard data on listings** — same; **not found in consumer voice**.

Three independent source families (ProductReview, app stores, PropertyChat) now agree these are *not* live consumer grievances. Treat as settled unless Reddit overturns it.

### 5.6 Product change post-dating the parent document
> "realestate.com now has a button to **'only show properties with a price'**"
> — `itchyfeet`, 2024-07-22, [Why no price?](https://www.propertychat.com.au/community/threads/why-no-price.79034/)

REA appears to have shipped the exact filter the Domain app reviewer `FyrStrike` requested in the parent doc §3.1. Any Fields claim that "portals won't even let you filter out no-price listings" is **out of date** — verify current behaviour before asserting it.

Same post, supporting `EVIDENCE_international_comparison.md`:
> "I also deal a lot with rightmove.com in UK. There ALL properties have prices."

---

## 6. Reddit — STILL OPEN, and now a decision for Will

Parent §1.2 item 1 and §5.1 are **not** closed. Status after this session:

| Route | Result |
|---|---|
| `reddit.com` direct from VM | **403** |
| WebFetch | Refuses the host |
| Bright Data Web Unlocker | **Refused** — *"not available for immediate residential (no KYC) access mode in accordance with robots.txt"*; requires completing Bright Data's KYC form |
| redlib / libreddit mirrors (4 tested) | Behind Anubis bot-checks; Bright Data does not clear them either |
| **PullPush archive API** | **Worked initially, then blocked us** |

PullPush (`api.pullpush.io`) is a free Reddit archive that initially returned full comment and submission bodies with full-text search — a viable route for everything up to **2025-05-19** (it holds nothing newer; verified by querying `after=` Jun 2025, Aug 2025 and Jan 2026, all zero). It now returns HTTP 429 to every request with:

> `"Rate limit exceeded. This website does not provide free scraping resources for agents. Please contact the administrator on Discord if you're interested in a paid scraping service."`

**No Reddit data was retained.** An initial run collected ~281 records but had 127 requests silently rate-limited — it would have written a plausible-looking file missing most of the corpus — so it was discarded rather than kept.

**This is a deliberate access-control decision by the operator, not a transient limit, and it was not worked around.** Routing PullPush through Bright Data to evade it would be circumventing an explicit refusal.

**Three options, all requiring Will's decision:**

1. **Complete Bright Data KYC** (form at `brightdata.com/cp/kyc`) → unlocks `reddit.com` directly through infrastructure already paid for. Gets **current** Reddit including the last 15 months. Best coverage.
2. **Pay PullPush** via their Discord → archive access to 2025-05-19 only; still leaves the recent window dark.
3. **Reddit's official API** — free tier, needs an app registered under a Reddit account. Legitimate, rate-limited but sufficient for research volume, and covers current content. Probably the cleanest route if KYC is unwanted.

Until one is done, every §5.1 expectation in the parent document stands unresolved — **including** whether §4.3/§4.4 convert from "not found" to "found". Note §5.5 above: PropertyChat *agreed* with the parent's negative findings, which makes it somewhat less likely Reddit overturns them, but does not settle it.
