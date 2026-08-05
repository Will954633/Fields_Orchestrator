# Competitor Capability Matrix — owner-facing address products

**Status:** Internal. **Compiled:** 2026-08-06 · **Rescoped:** 2026-08-06. **Companion to:** `01_USER_JOBS_AND_GAPS.md`
**Purpose:** One table, maintained separately from the dossier because it will be referenced constantly and edited independently.

**Scope.** Capabilities aimed at **the owner of a home that is not for sale**. Listing-side capabilities — price guides, depth tiers, search ranking — are confined to §A2 and admitted only as evidence of *who pays the incumbents*. See the SCOPE block in `01_USER_JOBS_AND_GAPS.md`.

**Ownership note before reading any row.** `realestate.com.au`, `property.com.au` and `PropTrack` are **all REA Group** [P — REA FY25 / H1 FY26 ASX announcements]. `onthehouse.com.au` and `propertyvalue.com.au` are **both Cotality** (formerly CoreLogic, rebranded 24 Mar 2025). `domain.com.au` has been **CoStar-owned since 27 Aug 2025**. So the five Australian "second opinions" a homeowner might consult are **three companies**, and a consumer checking "another site" for a second view on an REA-listed property may well be checking REA's own data again.

**Legend:** ✅ shipped · ◐ partial / gated / not consumer-facing · ❌ absent · ⚠ absent by choice, with a known reason

---

## A1. Owner-facing capabilities — Australian incumbents vs Fields

| Capability | REA (realestate + property.com.au) | Domain | Cotality (onthehouse / propertyvalue) | **Fields today** | **Fields possible** | Evidence |
|---|---|---|---|---|---|---|
| Estimate on any address incl. off-market | ✅ realEstimate (PropTrack) | ✅ Home Price Guide | ✅ | ◐ range where comps allow | ✅ | `international_comparison` §6.1 |
| Owner claim / tracking dashboard | ✅ 3M properties tracked; 600k monthly viewers; 40% of listings owner-tracked pre-market | ✅ tracked properties | ❌ | ❌ | ✅ **the V4 product** | `international_comparison` §6.2 |
| Owner can correct attributes | ✅ — and is encouraged to, because it feeds the estimate | ◐ | ❌ | ❌ | ✅ | `GTP_market_analysis` L1492 |
| **Correction actually acted on** | ❌ *"over 20 emails… they couldn't or wouldn't change it"* | ❌ *"absolutely no response whatsoever"* | ❌ | ❌ | ✅ **strongest claim-your-home argument** | `consumer_voice` §3.9; `ADDENDUM` §5.1 |
| **Published median error rate** | ❌ nothing consumer-facing; PropTrack markets accuracy to lenders only | ❌ forecast std-dev exposed to **B2B Insight** only | ❌ | ◐ 11.1% held, not published | ✅ | `international_comparison` §6.5; `consumer_voice` §4.1 |
| Confidence label on the estimate | ✅ "confidence rating" | ✅ Low/Mid/High band | ◐ | ⚠ **held back — labels inverted in backtest** | ✅ after calibration | `GTP_market_analysis` L1026; `ADDENDUM` §1 |
| **Calibrated** confidence (band contains the sale price) | ❌ *"'high' accuracy… low estimate is 90k less than we paid"* | ❌ same artefact | ❌ | ❌ not yet measured | ✅ **prerequisite, not follow-up** | `ADDENDUM` §1 |
| Show the comparable set used | ❌ | ❌ | ❌ | ◐ set shown; per-comp adjustments **not persisted** | ✅ | `GTP_market_analysis` L1051–1066 |
| Explain why the estimate moved | ❌ tracking shows movement, never the reason | ❌ | ❌ | ❌ | ✅ **"the living answer is defensible"** | `GTP_market_analysis` L1582 |
| Estimate-stability metric | ❌ | ❌ | ❌ | ❌ (data exists) | ✅ | `consumer_voice` §5.4 |
| **Tell an owner whether a number they've been given is supportable** (agent appraisal, bank valuation) | ❌ — supplies another unexplained number | ❌ | ❌ | ◐ where comps allow | ✅ **the sharpest fit for our method** | dossier J2 |
| Address-level flood / hazard | ❌ Domain publishes flood *research*, not address-level risk | ❌ | ❌ | ◐ suburb context for Burleigh Waters | ✅ where council data allows | `international_comparison` §6.4 |
| Running costs (rates, water, energy) | ❌ | ❌ | ❌ | ❌ | ◐ rates derivable; energy needs a rating regime | `international_comparison` §6.3, §7 |
| Full address-keyed history of the home | ◐ undermined by "price withheld" | ◐ | ◐ | ◐ | ✅ **better than Redfin** — keying to the address defeats the delist-and-relist reset | `international_comparison` §7 |
| **Owner's use of the estimate sold as a lead** | ✅ seller leads +55% FY25; *"valuable seller leads delivered to our customers"*; Pro tier gets **36% more** | ✅ same model | ◐ | ⚠ **never — this is the positioning** | — | `structural_conflict` C3 |
| Consumer-paid revenue line | ❌ **none exists** | ❌ | — | — | — | `structural_conflict` A1 |

---

## A2. Listing-side — admitted only as evidence of who pays

**Not capabilities we compete on.** These rows exist because they establish the incentive structure behind everything in A1 — the argument for why an owner should not trust an incumbent about their own home. **Do not turn any of these into a Hub feature or a user job.**

| Fact | REA | Domain | Why it's here |
|---|---|---|---|
| Search order determined by who paid | Standard→Feature→Highlight→Premiere→Premiere+→Luxe; default sort "Featured", formula unpublished | Basic→Branded→Silver→Gold→Platinum→Platinum Edge | The clearest evidenced form of "the customer is the agent" |
| Paid placement labelled to the consumer | ❌ no label found ⚠ **absence-of-evidence — verify in a browser** | ❌ same | Ranking by payment is undisclosed at the point of use |
| Owner's estimate withdrawn once the home lists | reportedly — *"They all just happen to hide it. Every one of them."* ⚠ **unverified** | same | The estimate disappears at the moment it matters most to the person who lives there. Owner-relevant, but a *listing* event — out of Hub scope until verified |
| "Only show properties with a price" filter | ✅ shipped 2024 | ◐ | ⚠ **dates one of our criticisms.** Do not claim portals won't let you filter out no-price listings |

**Explicitly dropped from this matrix as out of scope:** flagging a *listing* as overpriced against comparables. It remains a real, globally absent, structurally incumbent-proof capability (`international_comparison` §5.4) — but an off-market home has no asking price, so it belongs to a for-sale product, not the Hub. Recorded here so it isn't lost.

---

## B. Overseas benchmarks — what proves the capability is possible

| Capability | Who does it | The number | Transferable lesson |
|---|---|---|---|
| Published AVM accuracy | **Zillow** ~1.83% on-market / ~7.01% off-market, 104M homes; **Redfin** 1.85% / 7.27%, 92M homes (page dated Sept 2025) | Two independent portals, different data and models, both land ~2% / ~7% | That is the practical ceiling of a public AVM. **No AU portal publishes anything.** Zillow's published error rate was also its successful legal defence — `Andersen v. Zillow` dismissed Aug 2017 |
| Confidence shown as a visible range | **Zillow** Estimated Sale Range — worked example $260,503 on a $226,638–$307,394 band (±13–18%, openly shown) | — | Proof a consumer portal can show uncertainty without the product collapsing |
| Leading with model disagreement | **Realtor.com** — CoreLogic, Collateral Analytics and Quantarium plotted on one graph, since Mar 2020 | — | *"there is no single model that is perfect in every instance."* A major portal led with disagreement and was praised, not sued. ⚠ verify still live |
| Owner hub at scale | **Zoopla MyHome** — *"Over 6 million homeowners use Zoopla to track their home's value"* | 6M against ~24–25M UK dwellings | The audience is 100% of homes, not the 3–5% transacting. Zoopla publishes **no** accuracy figure — that gap exists even in the UK |
| Address-level sold history as public data | **HM Land Registry Price Paid** — 20M+ transactions back to Jan 1995, free, Open Government Licence v3.0, commercial use permitted | — | UK solved this at the **data** layer in 2012–13. Australia is attempting conduct regulation in 2026–27, and QLD quoted **$20,317** to extract sales data from QVAS |
| Risk + running costs as a listing standard | **Rightmove / Zoopla** under NTS Material Information Parts A/B/C (A in force 2022; B/C guidance Nov 2023) | Council tax band, EPC, tenure, broadband, Ofcom mobile signal, **flood risk** | The UK invented no new data. It mandated surfacing registries that already existed. **Australia has the same registries.** |
| Publishing what the industry didn't want published | **Redfin** — buyer-agent commissions on 700,000+ listings, 2021-02-08 | — | Only possible after the DOJ forced the door. An operator with no agent revenue needs no such permission |
| Demand/velocity signal | **Redfin Hot Homes**, since 2014-06-26, ≥70% probability of an offer within two weeks, calibrated per market | — | Twelve years live, outcomes published per city |
| ⚠ Feature built, promoted, then withdrawn | **Trulia** crime layers — White House showcase 2012, **removed early 2022** on bias grounds; Redfin declined outright | — | Not every "more data" feature is a win. Any neighbourhood-quality layer must be defensible on **measurement** grounds |

---

## C. The four capabilities where Fields can be genuinely differentiated

Filtered to those that are (i) feasible for us, (ii) absent from Australian incumbents, and (iii) structurally hard for an agent-funded business to ship.

| Rank | Capability | Owner job | Why incumbents won't | Our blocker |
|---|---|---|---|---|
| **1** | **A claim that doesn't sell you** — correction pathway, no lead resale, no contact unless asked | J4, J6 | REA reports owner engagement to shareholders *as* seller-lead growth. They cannot give this up; it is the revenue | Requires "nobody calls unless you ask" to be an operational rule, not copy |
| **2** | **Adjudicate a number someone else gave the owner** — show the comparable set and the adjustments | J1, J2 | A black-box AVM structurally cannot do it, and showing the working invites the accuracy question they don't answer | Coverage (7% of sold addresses); `adjusted_price` not persisted |
| **3** | **Published, calibrated accuracy** | J1, J2 | Their estimate accuracy is their loudest complaint and they publish nothing about it. Publishing would be publishing how wrong they are | Labels currently inverted in the backtest — **must be calibrated first** |
| **4** | **Explain why the number moved** | J3 | Their tracking product shows movement without explanation and monetises the visit, not the answer | Not built. Historical runs exist |

**Deliberately excluded from this list:** crime data (withdrawn by both major US portals on fairness grounds); ownership/occupancy surfaces (zero demand evidence — 260 `who owns` autocompletes, all corporate; 0 of 4,349 Reddit posts); energy ratings (needs an assessment regime we cannot create).

---

## Verification queue — claims in this matrix not yet confirmed first-hand

| # | Claim | How to verify | Blocking? |
|---|---|---|---|
| V1 | Paid placement carries no consumer-facing label | Load a REA and a Domain search results page in a browser | **Yes** for public use |
| V2 | Portals withdraw the estimate once a home is on the market | Check an off-market address's estimate, then the same address once listed | **Yes** |
| V3 | "Contact Agent" listings carry an embedded numeric price | Inspect page source; confirm price-band filtering returns the listing | **Yes** |
| V4 | REA's "only show properties with a price" filter exists | Load REA search filters | **Yes** — it dates one of our criticisms |
| V5 | Realtor.com's three-AVM display is still live | Load a Realtor.com Market Value tab | No |
| V6 | REA "600,000 dashboard views in October, +43% YoY" — which year? | Trace the Online Marketplaces source | No |
| **V7** | **What REA's Property Owner Dashboard and Domain's tracked-property view actually give an owner, feature by feature** | Manual walkthrough, or Bright Data | **Yes — this is gap G1 and the spine of the whole comparison** |
