# 93 Burleigh Street, Burleigh Waters — Buyer Acquisition Campaign

**Listing agent:** Tyler Benson, Coomera Realty (conjunction — Fields supplies buyers only)
**Property `_id`:** `690bd81b8b8f546592617fbb` — `Gold_Coast.burleigh_waters`
**Domain:** https://www.domain.com.au/93-burleigh-street-burleigh-waters-qld-4220-2020668300
**Plan started:** 2026-08-20

---

## 0. Blockers — resolve before spending a dollar

### 0.1 ✅ RESOLVED — not under offer. But the *advertising* may still say it is.

**Will confirmed 2026-08-20: the property is not under any offer.** Tyler has engaged us to find
buyers. No contract, no backup-offer timeframe, no runway constraint. This section is cleared as a
blocker.

**What it turns into instead — possibly the highest-value finding in this document.**

Our scrape of the listing's own description, `last_updated: 2026-08-19 20:45`, reads:

> "Under Negotiation - Final Submissions **Despite the existence of a current contract** this property
> remains open to further negotiations with a secondary buyer under limited time frame. Submit all
> offers before its too late."

`under_contract_detected_at: 2026-05-13`. That contract evidently fell over — but if the copy was
never rewritten, **the live advertisement is still telling every buyer they would be a backup offer
on a property that already has a contract.**

Consider what that does to a buyer who finds the listing today:

- "There's already a contract" → *I'm second in line, why bother inspecting*
- "Limited time frame" → *I can't do my diligence properly*
- "Submit all offers before its too late" → *pressure, with no price to anchor to*

Combined with the price guide being pulled on 6 August (§2.3), the listing currently offers a buyer
**no price and an apparent existing contract**. That is close to the worst possible combination for
generating enquiry, and it would explain the 163 days far better than anything about the house.

**✅ Checked against the live page 2026-08-20 — the concern was unfounded. Do not raise it with
Tyler.** Fetched via `shared/domain_fetch.py` (Bright Data Web Unlocker; direct curl_cffi is
Akamai-blocked from this VM), HTTP 200, 564,766 bytes, parsed from `__NEXT_DATA__` →
`listingByIdV2`:

- `listingByIdV2.status` = **LIVE**; `listingSummary.status` = `live`; `soldDetails` = null
- `listingsMap["2020668300"].listingModel.tags` = **null** — no `underOffer` tag. Good control: two
  other listings in the same payload (2020908795, 2021035855) *do* carry `tags.key = "underOffer"` /
  `tagText = "UNDER OFFER"`. This one does not.
- "Under Negotiation", "current contract", "secondary buyer" — **all absent**. The word "contract"
  does not appear anywhere in the headline or description.

Tyler has already rewritten the copy. Our stored `agents_description` is stale.

### ⚠ But that raises a pipeline question

Our record's `last_updated` is **2026-08-19 20:45** — last night's run — and it still holds the old
"Under Negotiation" text. Either the copy changed within the last ~17 hours, or **the nightly scrape
is not refreshing `agents_description`**. The second would mean stale listing copy across the
database. Worth an hour to determine which. See §1 task 1.6.

### 0.2 "Res B, 6m relaxation" does not match our council data

Our zoning record (`zoning_data`, enriched 2026-03-25, lot 187 RP128164):

| Field | Value |
|---|---|
| Zone | **Low density residential** |
| Zone precinct | *(empty)* |
| Cadastral area | 822.6 m² |

No "Res B", no recorded relaxation. Tyler's information may still be correct — a siting/height
relaxation is a property-specific approval that would not appear in a zone layer — but **we cannot
advertise it until we see the document.** A development claim we cannot evidence is the single
fastest way to lose the agent relationship and attract a complaint.

**Action:** request from Tyler the actual documents (see §1.1).

### 0.3 There is a flood overlay, and the ground sits below the designated level

Also from `zoning_data`:

| Field | Value |
|---|---|
| Flood overlay | **true** — "Flood Assessment Required" |
| Designated flood level | 4.18 m |
| Ground level | 4.03 m |
| Freeboard | **−0.15 m** (ground is 0.15 m *below* designated level) |
| Modelled depth | `<30cm` |
| ICA insurance flood zones | **none of the five** — not frequent, not 1%, not rare |

Both halves are true and both matter. A development application will require flood assessment. But
the insurance industry's own model does **not** place this address in any of its five flood
probability bands — i.e. it assesses the location as lower risk than the council planning overlay
implies.

This is a genuine Fields asset. Every buyer who searched the address has seen a flood overlay and
walked. Nobody has explained it to them. We already hold
`config/flood_context_burleigh_waters.md` for exactly this.

**Do not** treat this as something to omit. Handle it head-on, sourced, with the ICA distinction —
that is the honest framing and it is also the persuasive one.

### 0.4 🔴 Our own live page is currently disparaging Tyler's listing

The page already exists: **https://fieldsestate.com.au/property/93-burleigh-street-burleigh-waters**
(200; the `_id` URL 301s to it). It is live now, indexable now, and it is publishing this:

1. A badge on the quality chart reading **"8.7% above the local trend" / "Overpriced"** — a
   judgement derived from a valuation our own engine **suppressed as out-of-envelope**. There is no
   defensible number behind it.
2. The public API `/api/property/:id` returns the **entire `ai_analysis` object regardless of its
   status**. This property's editorial is `status: rejected` (rejected 2026-07-21, reason field
   empty) so the frontend hides it — but the backend still ships it to any browser that asks. Its
   headline reads *"93 Burleigh Street: A $1.99M Guide Published After the Contract Was Signed"* and
   its verdict asserts the guide price *"sits roughly 13-14% above what comparable sales in the
   immediate area currently support"*.

This is precisely the fear in the right-hand column of the agent's worry table — *"Will he undermine
my pricing/message?"* — and we are doing it, publicly, today, on the listing we have just asked to
partner on. It is also a month stale: the editorial cites a $1.99m guide and 331 m² floor area, both
of which have since changed.

**This is independent of whether the campaign proceeds and should be fixed regardless.** Scope is
being checked now — the badge and the API over-fetch are almost certainly site-wide, not specific to
this property, which means other named agents' listings are affected too.

**Also found:** the page renders **only the hero image**. We hold 62 photos; the API caps at 30; no
gallery component appears in the DOM at all. For a campaign page whose entire thesis is "the current
advertising communicates the property badly", shipping one image is self-defeating.

---

## 1. Task list

### Phase 1 — Facts we do not yet have (blocking)

| # | Task | Owner | Blocks |
|---|---|---|---|
| 1.1 | **Get the documents from Tyler**: contract status; the Res B / 6m relaxation approval; survey/site plan; full B&P report; any prior DA; title search; sewer & stormwater; rates notice (if vendor permits) | Will | Everything |
| 1.2 | **Written conjunction agreement** signed before publishing — confirms fee basis, approval-before-publish, and that Fields retains relationships it independently generates | Will | Publishing |
| 1.3 | **Site visit**: photograph/video what the current campaign communicates badly — shed interior, side access, downstairs configuration, actual condition, street presence, walk to beach | Will | Creative |
| 1.4 | Confirm the **car space count**. Our data disagrees with itself: `car_spaces: 4` at top level, `scraped_data.features.car_spaces: 2` | Fields | Any spec claim |
| 1.5 | Confirm **floor area**. Three sources disagree: Domain 203 m², our photo-derived total 331 m² (220 internal + 67 external), plus an onthehouse figure | Fields | Any spec claim |

### Phase 2 — Data and valuation

| # | Task | Status |
|---|---|---|
| 2.1 | **Our valuation engine returns no number for this property** — see §2 below. Decide what we can honestly publish | ⚠ Open |
| 2.2 | Audit comparable selection — the engine chose 8 comps, median distance ~1.6 km, none on Burleigh Street | Agent running |
| 2.3 | Land scarcity statistics — how many 800 m²+ houses are actually for sale near Burleigh, and what big blocks sell for | Agent running |
| 2.4 | Resolve the three-way price contradiction (§2.2) | ⚠ Open |
| 2.5 | Extract the floor plan — `floor_plan_analysed: false`, `floor_plans_v2_extracted: []`. We have 1 floor plan image and have never parsed it. Room dimensions would support the "teenagers / WFH / dual-living" thesis | Not started |

### Phase 3 — The property page

| # | Task | Status |
|---|---|---|
| 3.1 | Check whether a live `/property/` page already exists and what it renders — this property is `for_sale` and already carries a full `ai_analysis` | Agent running |
| 3.2 | Decide: reuse the standard property page, or build a **campaign page** with the §4 structure (the case for it, the compromises, the numbers) | Blocked on 3.1 |
| 3.3 | Page must carry: listing-agent attribution to Tyler / Coomera Realty, valuation methodology + confidence disclaimer (mandatory pre-flight for any ad carrying a $ claim), flood explainer, B&P position | — |
| 3.4 | Lead capture with explicit consent language — Fields may contact you about this and other suitable properties | — |
| 3.5 | Tyler approves the page before it goes live | — |

### Phase 4 — Distribution

| # | Channel | Note |
|---|---|---|
| 4.1 | **Facebook Marketplace** | Meta removed real-estate Marketplace listing for business Pages in 2023 — this would have to run from a personal profile, and a cloned listing under an unfamiliar name reads as a scam. Test it, but it is not the lead channel. Verify current Meta policy before building. |
| 4.2 | **Facebook Groups** | Likely stronger. Match the property to the community: renovation groups, tradie/4WD/boating groups (the shed), local Burleigh groups, Brisbane→Coast relocation groups. Different reason to enquire in each. |
| 4.3 | **Paid Meta** | Housing sits in Meta's Special Ad Category — restricted targeting. Plan for that. |
| 4.4 | **YouTube** | Analysis, not a listing walkthrough. "What does $1.9m actually buy near Burleigh Beach?" |
| 4.5 | **Direct to builders / developers** | Only after 1.1 confirms the planning position. Spreadsheet and site plan, not lifestyle creative. |

### Phase 5 — Measurement

| # | Task |
|---|---|
| 5.1 | Instrument the page so we learn **which buyer thesis converts**, not which creative gets clicks |
| 5.2 | Qualification script that captures: renting vs owning, need-to-sell-first, what ruled it out |
| 5.3 | Route qualified buyers into the CRM as Fields-originated relationships |

---

## 2. What our valuation engine actually says

### 2.1 It refuses to produce a number — and that is correct behaviour

`valuation_data` computed 2026-08-16:

```
reconciled_valuation : null
range                : null
confidence           : "directional"
directional_only     : true
directional_reason   : "above_design_ceiling"
positioning          : "overpriced"   (value_gap 8.7%)
NPUI median          : $1,680,864
n_comps              : 48 considered, 8 included, 21 verified
std_dev              : $997,595   (cv 0.358)
```

The comparable-sales method has a design envelope of **$1.0m–$2.0m for detached houses**. Above the
ceiling, `precompute_valuations.py` deliberately suppresses **both** the point estimate and the
range, because a weighted mean of adjusted comparables can never exceed its priciest comparable and
so regresses toward the middle of a mid-market pool.

**Consequence: we cannot publish a Fields valuation figure for 93 Burleigh Street.** Not "we choose
not to" — the engine has no defensible number to give. Anything we published would be us overriding
our own guardrail.

What we *can* publish, honestly:
- The **adjusted comparable sales themselves**, with the per-feature adjustments shown
- Land-rate arithmetic ($/m²), which is transparent and checkable
- Scarcity statistics (Phase 2.3) — a count, not an opinion
- What comparable big-land Burleigh Waters properties have actually transacted for

Note the coefficient of variation on the comp set is **0.358** — a very wide spread. That is itself
the story: this property does not have a tight comparable set, which is part of why the market has
struggled to price it in 163 days.

### 2.1b CORRECTION — the engine's real comps, and why "Overpriced" is meaningless

An earlier reading of this file quoted `valuation_breakdown.comparable_sales` (20 Silkyoak, 5 Prinia,
105 Mattocks …, averaging ~$1.68m). **That is an NPUI display set the valuation is not computed
from** (`precompute_valuations.py:4236-4243`). Its prices are also time-adjusted, not actual — it
shows 12 Ridgewood at $1,934,328 when the house sold for **$1,450,000**.

The comps that actually drove the number are `adjusted_comparables`, and they are a completely
different, closer, far more expensive set:

| Comp | Land | Sold | Adjusted | Dist |
|---|---:|---:|---:|---:|
| 5 Bluejay St | 683 | $2,200,000 | $2,805,956 | 0.07 |
| 6 Skua St | 612 | $2,000,000 | $2,710,551 | 0.27 |
| 9 Skua St | 612 | $2,700,000 | $3,063,128 | 0.32 |
| 56 Banksia Bwy | 685 | $1,965,000 | $2,597,181 | 0.39 |
| 14 Eagle Ave | 617 | $2,450,000 | $2,594,744 | 0.71 |
| 8 Dabchick Dr | 613 | $2,408,888 | $2,754,591 | 0.74 |
| 36 Kingfisher Cr | 678 | $2,400,000 | $2,888,797 | 0.80 |
| 8 Seahawk Cr | 1,011 | $2,800,000 | $2,787,405 | 0.86 |

The suppressed `reconciled_valuation` was **$2,788,742** (calibrated ≈$2,767,826) — **38% above** the
$2.0m ceiling. So the engine did not think this property was cheap. It thought it was worth $2.77m
and then refused to say so.

**Why that $2.77m is not usable, and not merely "out of envelope":**

Every comp except one is 130–210 m² *smaller* than the subject (median comp **647.5 m²** vs 822 m²).
**Land size is not a selection criterion anywhere in the engine** — no term in `calculate_weight`
(`:1951-1952`), none in `quality_score` (`:2027-2036`), and `in_cohort` only splits at 5,000 m², so
822 m² and 400 m² are the same cohort. Land is applied *after* selection as a flat $/m² correction
(`:1393-1398`). That single extrapolation is doing almost all the work: 6 Skua Street sold for
$2.0m and was adjusted to $2.71m, essentially by valuing an extra ~210 m² at full house-site rate.
Marginal backyard land does not trade at base-site rate. This is the mechanism, and it inflates.

### 🔴 "Overpriced / 8.7% above the local trend" is a self-referential artefact

`price` on this listing is the string `"Submit All Offers!"`, so `parse_price` returns `None`. With
no list price, `subject_price` falls through to **the median of the filtered comps**
(`:3713-3721`), and `compute_value_gap` (`:3344-3387`) then compares that median against an NPUI
regression **built from the same comps**.

The badge is comparing the comp set to itself. **There is no asking price for this listing to be
"over".** It is not a contested judgement about Tyler's pricing — it is a number with no referent,
published as a verdict on a named agent's listing.

### Engine defects found (site-wide, not specific to this property)

| # | Defect | Effect |
|---|---|---|
| 1 | `:3495` — sold pool sliced `[:60]` **in source order, before any similarity filter** | Of 32 eligible dry 3-5 bed ≥800 m² sales, **24 discarded**. The first 60 are 100% `recently_sold`; all 40 `target_market_12m` records fall outside. Valuations depend on database return order. |
| 2 | `:851-865` — dedup regex `,?\s*qld\s*\d{4}\s*$` fails on malformed `target_market_12m` addresses (`"44 Auk Avenue Burleigh, Waters, QLD 4220"`) | Duplicates survive and **double-weight**. 44 Auk, 76 Dipper, 6 Penguin, 5 Leafy, 8 Seychelles, 12 Swift all appear twice. |
| 3 | Land size absent from comp selection entirely | Large-block subjects comped against 400–620 m² blocks, patched by linear $/m². |
| 4 | `:3549-3566` — `water_view` pooled with `dry` by design | **76 Dipper Drive, $5,100,000, canal-adjacent**, sits in this dry 1975 house's pool at **$7,699,365 adjusted** — the pool maximum. |
| 5 | `:3469` — hard 12-month cutoff | **85 Burleigh Street** (928 m², $3,475,000) missed by **8 days**. |
| 6 | No list price → `subject_price` = median of comps → circular `value_gap` | The "overpriced" artefact above. Affects every listing with a non-numeric price string. |

These affect every valuation on the site, so fixing them is Will's call, not a background task.

### 2.2 Three sources give three different answers — publish none of them

| Source | Estimate | Date |
|---|---|---|
| Domain AVM (stored on our record) | **$2.23m – $2.91m**, mid $2.57m, "High" accuracy | 2025-11-03 |
| PropTrack (from earlier research) | $1.80m – $2.05m, mid $1.926m | Aug 2026 |
| Fields engine | *suppressed — above design ceiling* | 2026-08-16 |
| Vendor position (via Tyler) | offers from $1.9m | Aug 2026 |
| Public price guide history | "Offers over $1,990,000" (24 Jun), withdrawn 6 Aug | — |

Domain's own AVM sitting ~35% above the vendor's asking position is worth understanding, but it is
nine months old and it is not evidence we should repeat.

### 2.3 Price guide history is a useful signal

```
2026-03-20  CONTACT AGENT                    (initial)
2026-06-13  Contact Agent For Price Guide
2026-06-24  Offers over $1,990,000
2026-08-06  SUBMIT ALL OFFERS!
2026-08-17  Submit All Offers!
```

The listing ran **three and a half months without any public price** before publishing $1,990,000 —
then pulled the number again six weeks later. A meaningful share of those 8,335 page views happened
while a buyer could not find out what the vendor wanted. That is a much better explanation for 163
days on market than "buyers don't like the house", and it is fixable by us.

---

## 2.4 The scarcity numbers — this is the campaign

All figures from our own database, 2026-08-20. Field names confirmed per Rule 8. **Land size has no
single field** — it coalesces `land_size_sqm` → `onthehouse_data.land_size_sqm` →
`scraped_data_v2.land_area_sqm` → `floor_plan_analysis.total_land_area.value`. Where multiple
sources existed for these listings they agreed exactly.

### Every 800 m²+ house for sale in Burleigh Waters — 8 of 45

| Land | Address | Asking |
|---:|---|---|
| 921 | 8 Gum Court | Expressions of Interest |
| 877 | 38 Beaconsfield Drive | Offers Over $2,100,000 |
| 860 | 140 Honeyeater Drive | $2,895,000 + |
| **840** | **70 Burleigh Street** | **Offers Over $5,995,000** |
| 828 | 47 Kingfisher Crescent | Offers Over $2,750,000 |
| **822** | **93 Burleigh Street** | **Submit All Offers!** |
| 812 | 16 Manakin Avenue | Offers Over $1,949,000 |
| 802 | 166 Dunlin Drive | Interest Above $3,050,000 |

**Of the eight, only one publishes a number under $2m** (16 Manakin, and it is an "Offers Over" —
a floor, not a price). 93 Burleigh publishes no number at all.

### What 800 m²+ blocks actually sell for here

Sold houses ≥800 m² in Burleigh Waters, last 24 months, sale date parseable (n=50):

| | |
|---|---|
| Minimum | $1,450,000 |
| **Median** | **$2,402,500** |
| Maximum | $5,100,000 |
| Sold under $2m | **5 of 50** |

**This is the strongest hook we have, and it needs no valuation.** At $1.9m the buyer is entering
big-block Burleigh Waters near the bottom of a 24-month distribution whose midpoint is $2.4m. It is a
count and a median — checkable, sourced, and entirely inside the no-advice rule.

It also flatly contradicts the "Overpriced / 8.7% above local trend" badge on our own live page
(§0.4). The engine's comp set averages ~$1.68m at 1.5–2.2 km distance; the ≥800 m² sold median is
$2.40m. That gap is the comp-selection question in task 2.2.

### Mandatory caveats before any of this is published

- **"Sold" is a floor, not a census.** 114 Burleigh Street sold for $2,350,000 (2025-01-29) but
  carries `listing_status: null` — the sale exists only in its timeline array and is invisible to
  any `{"listing_status": "sold"}` query. Phrase every claim as *"sales in our database"*.
- **19 further ≥800 m² sales have no date** and are excluded from the n=50 window — including several
  of the largest ($5.1m, $4.55m, $4.2m, and 85 Burleigh Street at $3,475,000). The window
  **understates** the top end. Never say "the highest was $5.1m"; say "of sales we can date".
- **16 of 45 houses for sale publish no numeric price** (Auction ×4, EOI ×7, Contact Agent ×3, …).
  Any "only X asking under $2m" claim must be worded *"of those that publish a price"*.
- **Exclude two bad land figures**: 2 Beaconsfield Drive (3,409 m²) and 12/20-24 Barbet Place
  (3,322 m²) are whole-complex site areas. 117 Burleigh Street's 290 m² against a $2.59m sale is
  also implausible — treat as suspect.
- **Burleigh Heads has zero for-sale coverage** (9,459 docs, none `for_sale` — not a target suburb).
  We have no denominator. Make no "X of Y in Burleigh Heads" claim.
- **Condition is not controlled for.** The $4–5m sales are near-certainly new builds on those blocks.
  The median is a *land-and-location* argument, not a claim that 93 Burleigh is worth $2.4m.

### Burleigh Street itself

Both previously cited sales confirmed from our data: **148 Burleigh Street** $2,050,000 / 850 m² /
2025-05-17, and **114 Burleigh Street** $2,350,000 / 733 m² / 2025-01-29 (Jan, not "2025" generally).

Also on the street: 85 ($3,475,000, 928 m²), 64 ($2,750,000, 932 m², 2024-09-12), 174 ($2,500,000,
830 m², 2024-09-26), 160 ($2,500,000, 833 m², 2025-03-05), 126 ($1,700,000, 709 m²), 138
($1,572,000, 676 m²).

And **70 Burleigh Street is asking Offers Over $5,995,000 on 840 m²** — same street, 18 m² more land,
three times the price. Worth understanding why (waterfront? new build?) before it appears in any
creative, because a buyer will find it in thirty seconds.

---

## 3. Data assets we already hold

| Asset | Detail |
|---|---|
| Photography | 62 property images in blob storage, 32 cadastral photos |
| Aerial | Lot-boundary aerial rendered 2026-08-13 (`aerial_boundary_url`) |
| Satellite analysis | Categories + narrative, Opus-verified |
| Floor plan | 1 image — **not yet parsed** (task 2.5) |
| Editorial | Full `ai_analysis` (25 fields) already generated |
| Condition assessment | Room-by-room from 20 analysed photos — overall condition **"fair"**, score 5/10, renovation level **"original"**, 20+ years since renovation, no pool, no fence, carport not garage, laminate kitchen |
| Location | `nearby_pois`, `osm_location_features`, 891 m to postcode centroid |
| Cadastral | Lot 187 RP128164, freehold, 822.415 m² calculated, ±0.1 m accuracy |
| History | Last sold **$615,000, Aug 2013**, 26 days on market |
| Rental | Domain estimate $1,905/wk, 3.85% yield |

The 2013 sale at $615,000 is worth handling carefully. It is a fact and it is public, but leading
with it invites "they're making $1.3m" rather than "this is what Burleigh land did in twelve years".

---

## 4. Campaign page structure (proposed)

Not a listing clone. REA has already shown the listing proposition 8,335 times.

1. **The case for it** — 822 m², ~1 km to Burleigh Beach, usable house, clean B&P, real shed
2. **The compromises** — original 1970s condition, no pool, flood overlay explained properly
3. **The numbers** — adjusted comparables, land rate, scarcity count, what big blocks transact for
4. **Who it suits** — renovator, future builder, shed/boat buyer, teen-family, land-banker
5. **Who it doesn't** — anyone who wants it finished
6. **Inspect / ask** — into Tyler, with Fields qualifying first

Section 5 is not a throwaway. Telling a buyer who should *not* buy it is what makes sections 1–4
credible, and it is the difference between a Fields analysis and an advertisement.

---

## 5. Open questions for Will

1. Contract status — the single biggest one (§0.1)
2. Are we cleared to state publicly that B&P is complete and clear? Only with the report in hand
3. Is Tyler comfortable with us publishing the "circumstances have changed / vendor is now ready to
   decide" framing, in his words and with his approval?
4. Fee basis agreed with Tyler, or still to negotiate?
