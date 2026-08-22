# 93 Burleigh Street — Campaign Content

**Price:** $1,915,000 (Will's direction 2026-08-20; above Tyler's stated $1.9m floor)
**Channels:** Facebook Marketplace + Facebook Groups, Fields' own channels
**Listing agent:** Tyler Benson / Sophie Watts, Coomera Realty — named in every asset
**Inspection:** Saturday 22 August 2026, 1:00–1:30pm

---

## 1. ⭐ THE FINDING — the floor plan nobody read

The floor plan has been in our database since 2026-06-11 and was **never parsed**
(`floor_plan_analysed: false`). It shows something the Domain advertisement does not mention
anywhere:

### The ground floor is a self-contained second living space

| Room | Size |
|---|---|
| Multi-Purpose Room | **6.3 × 5.1 m** (32.1 m²) |
| **Kitchenette** | **3.1 × 2.6 m** |
| Bathroom | full, ground floor |
| Laundry | adjacent |
| Second Multi-Purpose Room | 5.4 × 3.4 m (18.4 m²) |
| Store | 2.3 × 2.1 m |

A 32 m² room with **its own kitchenette, its own bathroom and a laundry**, downstairs, separate
from the four bedrooms upstairs.

The Domain copy says only: *"the home currently offers four bedrooms upstairs along with a
functional kitchen, dining and living area."* The kitchenette is never mentioned. Neither
multi-purpose room is mentioned. **The single most differentiating feature of this house is absent
from its own advertisement.**

⚠ **Language discipline.** Do **not** say "granny flat", "dual occupancy", "legal dual living",
"second dwelling" or "rentable". Those are planning claims we have not verified and the zone is Low
density residential. Describe **only what the floor plan draws**: a kitchenette, a bathroom, a
laundry and a large room on the ground floor. Let the buyer draw the conclusion — Rule 5.

### Other things the floor plan settles

| Item | Finding |
|---|---|
| **Floor area** | Internal **220 m²** · alfresco/porch/carport 67 m² · workshed 44 m² · **total 331 m²**. Domain's "203 m²" is neither. |
| **Workshed** | **7.0 × 6.2 m = 44 m²**, confirmed and dimensioned |
| **Covered alfresco** | **8.0 × 3.5 m** (28 m²) — our DB records `alfresco_present: false`. **Our data is wrong.** |
| **Fencing** | Site plan labels "Fenced Grass Yard" — our DB records `fence_type: none`. **Also wrong.** |
| **Parking** | Double carport 6.2 × 5.7 m **plus** driveway parking — reconciles `car_spaces: 4` vs `2` |
| **Lot shape** | Frontage 19.9 m, rear 18.4 m, depth 40.9 m one side / 49.0 m the other — a wedge, not a rectangle |
| **Master** | 4.2 × 3.2 m with ensuite. Others 3.8 × 2.8, 3.2 × 3.2, 2.8 × 2.7 |

🔴 **Do not publish the "larger than 99% of Burleigh Waters properties (331 m² vs 170 m² median)"
insight.** Our `property_insights.floor_area` compares this property's **331 m² total including shed,
carport and alfresco** against other homes' **internal** area. It is apples to oranges and a buyer
who checks will catch it. The honest internal comparison is **220 m²**.

---

## 2. Verified fact base

Everything below is checked. Anything not on this list does not go in an ad.

**Land & structure**
- 822 m² (cadastral 822.415 m², QSCF; floor plan states 822 m²) · Lot 187 RP128164 · freehold
- Built 1975 · two storey · brick, tile roof
- Internal 220 m² · total 331 m² incl. alfresco, carport, workshed
- 4 bedrooms upstairs (master with ensuite) · 3 bathrooms · 2 multi-purpose rooms + kitchenette down
- Workshed 7.0 × 6.2 m · double carport 6.2 × 5.7 m · covered alfresco 8.0 × 3.5 m
- Zone: **Low density residential** (Gold Coast City Plan)

**Location** (measured, `nearby_pois`)
- Lakeview Espresso Burleigh **88 m** · Lake View Park **138 m** · Burleigh Knoll Conservation Park **344 m**
- Closest school 0.86 km · closest childcare 0.51 km · closest supermarket 1.13 km
- 39 amenities within 1 km, 132 within 2 km
- ~1 km to Burleigh Beach (listing agent's claim — we have not independently measured it)

**Ownership history** (`transactions`)
- $140,000 (Oct 1989) · $170,000 (Apr 1991) · **$615,000 (Aug 2013)**

**Scarcity** (our database, 2026-08-20 — figures below are the RE-VERIFIED set; an earlier pass
reported 45 houses / n=50 sold / median $2,402,500 and those did **not** reproduce)
- **8 of 36** houses for sale in Burleigh Waters sit on 800 m²+ (the eight and their land sizes
  reproduced **exactly**; the denominator did not — 36 is what any type filter yields)
- **13 of 36** publish no price at all, so every "cheapest / lowest" claim is a claim about **23 houses**
- Sold 800 m²+ in Burleigh Waters, 24 months (n=**66**): min $1,450,000, median **$2,470,000**,
  max $5,100,000, **7 below $2,000,000**
- ⚠ The earlier "19 undated sales excluded" was an artefact of querying `sale_date` (missing on
  168 of 402 docs) instead of `sold_date` (populated on all sampled). Using `sold_date` there are
  **zero** undated records — **but nothing in the set predates September 2024.** "Past 24 months"
  and "everything we hold" are the same set. Never imply the window deliberately excluded older
  evidence; it excluded nothing.

### The single strongest claim we have

> **No Burleigh Waters house advertised below $1,915,000 sits on 800 m² or more. The largest is
> 762 m².**

Checked against all 23 priced houses. The nine advertised below $1,915,000 sit on 400, 400, 401,
430, 482, 643, 662, 713 and 762 m². This beats "cheapest" because it is a statement about the
**field**, not a ranking that one unpriced listing can overturn.

**Land rate:** $1,915,000 ÷ 822 m² = **$2,330/m²** — lowest of the eight. Others: 38 Beaconsfield
$2,394, 16 Manakin $2,400, 47 Kingfisher $3,321, 140 Honeyeater $3,366, 166 Dunlin $3,802,
70 Burleigh $7,136. ⚠ $/m² of land includes the house — 70 Burleigh's $7,136 is improvements, not
dirt. Indicative only.

### 🔴 Claims that are UNSAFE — do not use

| Claim | Why it fails |
|---|---|
| "The cheapest 800 m²+ house in Burleigh Waters" | 8 Gum Court (921 m²) is **Expressions of Interest** — price unknown, could be lower. Also 126 Dunlin Drive (982 m², under contract, "Contact Agent") and five withdrawn ≥800 m² listings that could relist. |
| "The only 800 m²+ house under $2,000,000" | Same EOI problem, plus seven recorded sales closed below $2,000,000. "Only" is indefensible. |
| Any percentile — "priced below 91% of large-block sales" | Sounds statistical; it is a share of an incomplete capture set. Numerator and denominator both soft. |
| "Below market" / "below what comparables support" | States a valuation. Rule 5 forbids it, and our engine suppressed its own estimate for this property. |
| "$34,000 below the next cheapest" *unqualified* | 16 Manakin is **Offers Over** $1,949,000 — a floor, not a ceiling. The real gap is unknowable, and 1.74% is within noise of any price adjustment. |

### Known data weaknesses a competitor could exploit

- **117 Burleigh Street** sold **$2,590,000 on 2025-06-11** recorded at **290 m²** — implausible on a
  street where 85, 148, 160 and 174 Burleigh Street are all 830–928 m². If its true size is ≥800 m²
  it is a **7th sale above threshold** that we wrongly excluded. It also has no `address` field, so
  it never surfaces in address searches. **Resolve before publishing any sold count.**
- **2 Beaconsfield Drive** at 3,409 m² is inside the sold set and drags the $/m² minimum from
  $1,498 to $616. Quote the minimum without excluding it and the figure is indefensible.
- **87 Dunlin Drive** (893 m²) is marked sold with price "Auction" — no figure. Any "only N sold
  below X" is falsifiable by a single uncaptured sale.
- **No `property_attributes` document** exists for 93 Burleigh, 16 Manakin, 38 Beaconsfield or
  8 Gum Court — so there is no condition or floor-area basis for saying these blocks are alike.
  Every rank above compares **land and price only**.

### Trade-offs — state them, don't bury them

Rule 5: every trade-off is value, not a flaw. But it must be *stated*.

| Trade-off | Honest framing |
|---|---|
| Original 1975 condition, unrenovated (condition "fair") | You are choosing the finishes, not inheriting someone else's |
| No pool — several neighbours have one | 822 m² and a wedge-shaped rear yard leaves the room to put one where you want it |
| **Fronts a through-road** — aerial shows a curved road with a painted 50 marking and moving traffic | Wide frontage and easy trailer/boat access straight to the shed. Say the road is there. |
| Rear yard is currently bare, cleared ground | Blank canvas — but it photographs badly, so show it and explain it |
| Flood overlay — assessment required for a development application | See §3 |

---

## 3. The flood section — our biggest single advantage

Every buyer who searched this address saw a flood overlay and moved on. Nobody has explained it.

**The facts, both halves:**
- Gold Coast City Plan flags a flood overlay; **a flood assessment is required for a development application**
- Designated flood level **4.18 m** · mapped ground level **4.03 m** — ground sits **0.15 m below**
- Modelled depth in a design flood event: **under 30 cm**
- The address falls in **none of the five ICA insurance flood probability zones** — not the 1-in-5-year band through to the 1-in-2000-year band

Source: Gold Coast City Council ArcGIS flood mapping; Insurance Council of Australia zone data.

**Framing:** the council's planning overlay is more conservative than the insurance industry's own
model. Both statements are true and a buyer deserves both. State the requirement, state the depth,
state the ICA position, cite the sources, and stop. **Never** present this as reassurance — present
it as the information the portals didn't give them.

⚠ Do not use in a Marketplace listing or a short-form group post. It needs the full page to be
handled responsibly. Link to it.

---

## 4. Facebook Marketplace

⚠ **Check before building:** Meta removed the ability for business Pages to create real-estate
Marketplace listings in 2023. This likely has to run from Will's personal profile. Verify current
policy first — a cloned property listing under an unfamiliar name also reads as a scam, which is the
main risk to manage here.

**Title:** `822m² in Burleigh Waters — 1km to Burleigh Beach — $1,915,000`

**Body:**

> 822m² block in Burleigh Waters, about 1km from Burleigh Beach.
>
> Two-storey brick home, built 1975, on a 19.9m frontage. Four bedrooms upstairs, master with
> ensuite. Downstairs there's a 6.3 x 5.1m multi-purpose room with its own kitchenette, bathroom and
> laundry — separate from the bedrooms upstairs.
>
> Also on the block:
> • Workshed 7.0 x 6.2m
> • Double carport plus driveway parking
> • Covered alfresco 8.0 x 3.5m
> • Fenced grass yard
>
> 220m² internal, 331m² total including the shed, carport and alfresco.
>
> It's original 1975 condition — the kitchen and bathrooms are unrenovated, and there's no pool.
> That's reflected in the price.
>
> For context, we checked every house currently for sale in Burleigh Waters. Eight are on 800m² or
> more — and no house advertised below this price sits on more than 762m².
>
> $1,915,000. Inspection Saturday 22 August, 1:00–1:30pm.
>
> Listed by Tyler Benson, Coomera Realty. I'm Will Simpson from Fields Real Estate — I'm helping find
> a buyer for this one. Full data, floor plan, flood mapping and comparable sales:
> [LINK]

---

## 5. Facebook Groups — five different reasons to enquire

Same property, five buyers. **Do not post the same text to five groups.**

### A. Renovation / property groups
> There's an 822m² block on Burleigh Street, about 1km from Burleigh Beach, that's been on the market
> since March.
>
> The house is original 1975 — brick, tile, unrenovated kitchen and bathrooms. Two storey. Four
> bedrooms upstairs.
>
> The part I found interesting is downstairs: a 6.3 x 5.1m room with its own kitchenette, bathroom
> and laundry. It isn't mentioned in the advertising at all — I only found it by reading the floor
> plan.
>
> 822m², $1,915,000. What would you do with it — renovate, or start again?

### B. Tradie / 4WD / boating / car groups — **lead with the shed**
> A 7 x 6.2 metre workshed. About 1km from Burleigh Beach.
>
> Freestanding, at the back of an 822m² block, with driveway access past a double carport — so you
> can get a boat or a trailer to it.
>
> The house is a 1975 four-bedroom that needs work, which is why the whole thing is $1,915,000
> instead of what a finished Burleigh house costs.
>
> How many places this close to Burleigh have a shed like that?

### C. Local Burleigh community groups — **soft, no hard sell**
> One of the older big blocks on Burleigh Street is on the market — 822m², built 1975, same family
> since 2013.
>
> We pulled the numbers on it: of the houses currently for sale in Burleigh Waters, eight are on
> 800m² or more — and none of the houses advertised below this one's price is on more than 762m².
>
> $1,915,000. Listed with Coomera Realty; I'm helping find a buyer.

### D. Brisbane → Gold Coast relocation groups
> What does $1,915,000 buy you 1km from Burleigh Beach?
>
> 822m². Four bedrooms up, a second living area with a kitchenette down, three bathrooms, a 7 x 6.2m
> shed and a double carport.
>
> Not renovated — it's a 1975 house in original condition. But you're 88 metres from a café, 138
> metres from a park, and about a kilometre from the sand.

### E. Extended-family / multigenerational angle
> Four bedrooms upstairs. Downstairs: a 6.3 x 5.1m room with its own kitchenette, bathroom and
> laundry.
>
> 822m² in Burleigh Waters, about 1km from the beach, $1,915,000.
>
> Worth a look if you've got teenagers, adult kids at home, or parents who need their own space.
>
> (It's a 1975 house in original condition — the trade-off is you'd be renovating.)

---

## 6. Rules for every asset

1. **Name Tyler Benson / Coomera Realty as listing agent.** Every asset. Non-negotiable.
2. **Tyler approves before publish.** Will's written undertaking.
3. **No "granny flat" / "dual living" / "rentable"** — describe the floor plan, not a planning outcome.
4. **No valuation figure.** Our engine suppressed its own estimate for this property. $1,915,000 is
   a listing price and may be stated as such; it is not a Fields valuation and must never be
   presented as one.
5. **No forbidden words:** stunning, nestled, boasting, rare opportunity, robust market.
6. **Exact numbers**, `$1,915,000` not "$1.9m"; suburbs capitalised.
7. **State the trade-offs.** Original condition, no pool, road frontage. A seller should read our
   content and think we'd position their home honestly — the Seller Test.
8. **No advice.** Never "you should buy", "now is the time", "priced to sell".

---

## 7. Still open

- Tyler's sign-off on $1,915,000 and on Fields displaying a price his own ad doesn't show
- Res B / 6m relaxation documentation — nothing development-related is publishable without it
- Full B&P report before any "building and pest is clear" claim
- Site visit: photograph the shed interior, the downstairs kitchenette space, side access, road frontage
- Fix `alfresco_present: false` and `fence_type: none` in our database — both contradicted by the floor plan
- Parse the floor plan properly into `parsed_rooms` so this is not a manual discovery next time
