# Application map — what goes where, and why

**Compiled:** 2026-08-06. **Target:** the ten sections in `05_PAGE_FLOW.md`.
**Sources:** the live V3 deck · the shipped `/your-home` report · the V2 session spec · the research in `../Research/`.

Every element that survives, where it lands, why, and whether it can be built today.
**State:** ✅ shipped and reusable · ◐ built elsewhere, needs porting · ⚙ needs building · ⛔ blocked.

---

## The target, at a glance

| § | Section | Carries |
|---|---|---|
| 0 | Arrival | Three questions · hard fact · privacy line |
| 1 | The range | Range + anchor · dated · honest limits · postal ask |
| 2 | The working | Funnel · comparables · obvious-comp · scarcity + emblem · review ask |
| 3 | How it's made, how wrong | Method · no-hindsight · error rate · what this isn't |
| 4 | Why you've seen other numbers | Dispersion (512 homes) |
| 5 | What it's done since you bought it | Gain trajectory |
| 6 | If someone else gave you a number | Lender explainer · upper bound |
| 7 | What's moving | Competitors · change log · buyer portrait · two-true-things |
| 8 | What sits under it | Flood and overlays |
| 9 | What you can do | Data record · correction · claim |

---

## A · From the live V3 deck

| # | Element | → | Why | State |
|---|---|---|---|---|
| A1 | **Chained question** (`answer` → `headline` → `next`, in the reader's voice) | **All ten** | The strongest structural device in the deck. The reader never decides whether to continue — they are handed the question they already had. Written out as a designed sequence in `05_PAGE_FLOW.md` | ✅ |
| A2 | **Curiosity gap** — name that something exists, withhold what it is | **§2 opening** | Textbook information gap. ⚠ **Applied to the feature, not the number.** V3 delays the valuation to card 07 of 9; on our funnel that is ~1 session in 7. The hook was always about the boundary | ✅ copy exists, 12 angle variants |
| A3 | **Emblem system** — `angle_media.yaml`, `lead_angle` → drawing → caption | **§2**, beside the feature reveal | Personalisation at scale: **87% of 18,070 decks** already carry one. Scraperboard flora/fauna, captioned to the actual feature (*"The bushland at your boundary"*) | ✅ |
| A4 | **Detach transition** — one element leaves the drawing and comes to rest beside the next copy | **§2 → §3** | Makes the scroll feel authored rather than paginated. Only pandanus/dog/golfflag have one; the rest are an open question in `PLAN.md` | ◐ 3 of 8 |
| A5 | **`text_only` discipline** — six angles get no drawing on purpose | **Design rule** | *"An image on a card that is not claiming a physical feature would be the only decorative element on the page."* The restraint is as valuable as the ornament | ✅ |
| A6 | **`_obvious_comp`** — closest sale by distance, then material deltas (land ≥50 m², floor ≥20 m², build ≥8 yrs) | **§2**, ahead of §4 | **The sharpest device in the deck.** Pre-empts the objection they arrived with — *"but number 14 sold for…"* — and proves the method on the one comparison they care most about | ✅ |
| A7 | **`poi_rarity` conditional line** — *"of the 35 that share your combination, only 6 are also this close to a school, a park and childcare"* | **§2** | Narrows honestly in one sentence; turns a common combination into a rare one without overstating | ✅ live in deck; harness not promoted |
| A8 | **`scarcity_features`** — anchors (cohort-relative) vs differentiators (uncounted) | **§2** | Explains *where in the range* the home sits — which is J1, our best-evidenced need. Cannot be inflated by missing data by construction | ✅ |
| A9 | **Two-sided value drivers** — *"↑ land / ↓ no pool. Knowing both is how you hold your number."* | **§2** | Volunteering the weakness is the trust move; *"hold your number"* reframes it as preparable rather than a flaw | ✅ |
| A10 | **Buyer portrait + `_persona_fit`** — a behaviour, not a demographic | **§7** | ⚠ No independent *search* support as a topic — but this is the **human expression of the scarcity result**, from the same POI/feature data. Keep it attached to scarcity, never standalone | ✅ |
| A11 | **The reframe** — *"Right now it's your home. To them, it's the one they've been waiting for."* | **§7 close** | The emotional peak. The only non-data line, and it earns its place because the evidence came first. **One per page, after the proof** | ✅ |
| A12 | **`_anchor`** — central figure rounded to $50k, spelled in millions | **§1** | *"Around $1.65 million"* reads as a considered position; an exact figure reads as false precision. Range stays the headline (Rule 5) | ✅ |
| A13 | **Honest-limits paragraph** — *"no interior photography… what a desk can't see is the inside… that's why this range is deliberately wide"* | **§1** | Suppression-as-credential, already shipped. Explains the width instead of apologising for it | ✅ |
| A14 | **Credibility counts** — 29 characteristics, 2,933 sales, 12,000+ homes compared | **§2 funnel**, not §0 | Proof of work. Moved out of the opener: it is *our* effort, and §0 belongs to *their* questions | ✅ |
| — | ⛔ Matrix intro · glass-shatter outro · neon CTA · signal/alien audio | **Dropped** | Per Will. Also off-register for a reader whose state is *anxiety about being wrong* | — |

---

## B · From the shipped `/your-home` report

| # | Element | → | Why | State |
|---|---|---|---|---|
| B1 | **`SoWhat`** — no number ships without a translation line | **Voice + every §** | *"The product is data-first when the reader is fear-first."* Our draft failed this repeatedly | ✅ |
| B2 | **`CitationStrip`** — *"if a claim doesn't have a source, the block should not have rendered"* | **Voice** | Absolute rule, cheap to honour | ✅ |
| B3 | **`FearSection` thesis / applied** column split | **Layout** | Better axis than free/locked: moving right gets *more* personal, so the page deepens rather than withholds | ✅ |
| B4 | **`ValuationEvidence`** L1 evidence card / L2 comparable cards / L3 adjustment grid | **§2** | This *is* §2, rendering today from engine output, with distance and a plain-English narrative per comp | ✅ |
| B5 | **`RankedComparison` funnel** — animated, *"honest theatre: every step is a computation that genuinely ran"* | **§2** | Watching the filtering beats reading its result | ✅ |
| B6 | **`DataRecordDrawer`** — every data point held, grouped and sourced | **§9** | The precondition for the correction ask — you can only correct what you can see | ✅ |
| B7 | **`StatutoryCMA`** — s 215 CMA of record + *"as at / valid until"* | **§1** | ⚠ **Compliance, not decoration.** §1 gives a homeowner a likely sale price and Fields is a licensed agency | ✅ component / ⛔ question unresolved |
| B8 | **`WhatChangedBanner`** + durable change log | **§7 (30-day, ungated)** and **claim (since-you-last-looked)** | The log accrues per property regardless of claiming — so the public half is free and the personal half is a genuine reason to claim | ✅ |
| B9 | **`MatchCards`** — explicit *how it differs from yours* per competitor | **§7** | *"Frames the row as COMPARISON, not as a list of alternatives"* | ✅ |
| B10 | **`LiveMarketStatus`** nightly status bar | **§7** | Makes the page read as maintained, not generated once | ✅ |
| B11 | **`PendingPlaceholder`** | **§1** | A named, dated wait reads as work happening; a spinner reads as a slow page | ✅ |
| — | ⛔ `PositionAtAGlance` | **Dropped** | Two of its four questions are the buyer/competition angles with no independent support; adopting the shape imports them unexamined |
| — | ⛔ `SeasonalityStrip` | **Dropped** | Timing is a seller-journey question — the mini-site itself puts it on the Process tab |
| — | ⛔ `ShareMoment` | **Dropped** | 94% view exactly one address — *"the signature of a private self-check."* Sharing assumes an audience this reader is avoiding |

---

## C · From the V2 session spec

| # | Element | → | Why | State |
|---|---|---|---|---|
| C1 | **"The three questions"** — *"You may be trying to answer three questions privately…"* | **§0** | Names what they came for without making them say it. Serves the conclusion both products were missing: *"they understand what is happening in my life."* Hedge is load-bearing | ⚙ |
| C2 | **Never make the reader admit intent** | **Voice** | Nothing asks whether they are selling; no section may imply it | ⚙ |
| C3 | **Two true things that point in different directions** | **§7** | Shows the ambiguity instead of announcing we won't resolve it. *"The reader draws the inference. We never state it."* | ⚙ |
| C4 | **Suppression as a credential** — *"saying why a number is missing is worth more than the number"* | **§1 fallback** | Converts the majority no-range state from apology into the strongest proof on the page that we don't invent numbers | ⚙ |
| C5 | **Print spec** — A4→A5, four sides, **no CTA anywhere** | **§1 postal ask** | *"The moment it mentions appraisals or selling services it reads as solicitation"* | ✅ spec |

---

## D · From the research

| # | Finding | → | Why |
|---|---|---|---|
| D1 | Zero positive reactions to unsolicited "we found your property" across 5,685 posts | **§0** — kill *"We found your home"* | The most evidenced-harmful line we currently ship |
| D2 | *"Am I declaring that I am selling?"*; 87.5% single-pageview | **§0** — privacy on the first screen | Reassurance at the end reassures nobody |
| D3 | Dispersion, n=512: median **$469,000** spread; near-perfect comp exists on **73.6%** | **§4** | Explains the competing estimates already above us on their results page |
| D4 | Narrowing, n=512: median **38.8%**, narrows nine times in ten | **§3** | The defensible version of the $610k→$274k example |
| D5 | No AU portal publishes an error rate; Zillow's own published accuracy was its legal defence | **§3** | Rare, cheap, and armour |
| D6 | `high` 56.0% vs `medium` 57.5% range-hit | **§1, §3** — no confidence label | Non-discriminating; publishing one repeats the failure we criticise |
| D7 | `does burleigh waters flood` — **546**, 2.5× the next item | **§8** | People don't complain to the portal, they go to Google |
| D8 | Market direction ≈ **670** combined persistence | **§7** | Largest adjacent topic by a distance |
| D9 | Equity Checker ~115 posts, largest persona, unserved | **§6** | Answerable as a category explainer, with no financial inference about them |
| D10 | Sale history: 144 autocomplete, `history` 4× in refinements, our #3-above-Domain snippet | **§0 fact, §5 trajectory** | Moderate support — enough for a section, not enough to headline |
| D11 | `for_sale_gate` has converted **2 people** lifetime; postal reach 176 vs 29 | **All asks** | Post or SMS, never a login |
| D12 | REA books owner engagement as *"seller leads delivered to our customers"*, Pro tier gets 36% more | **§9** | The sharpest contrast we own, from their own filings |

---

## Section assembly

**§0 Arrival** — three questions [C1] · hard fact [D10] · privacy line [D2] · never "we found you" [D1] · closes *"So what is it worth?"* [A1]

**§1 The range** — range + anchor [A12] · computed-on date · comp-set age · honest limits [A13] · no label [D6] · `PendingPlaceholder` [B11] · fallback as credential [C4] · s 215 [B7] · **ask: post it** [C5, D11]

**§2 The working** — curiosity gap [A2] · funnel [B5] + counts [A14] · `ValuationEvidence` [B4] · **obvious-comp** [A6] · scarcity [A8] + rarity line [A7] + emblem [A3] · two-sided drivers [A9] · detach out [A4] · **ask: review this** [D11]

**§3 How it's made** — method · no-hindsight · narrowing [D4] · error rate [D5] · what this isn't · **ask: send the method**

**§4 Why other numbers differ** — dispersion [D3], opening on what they just watched happen in §2

**§5 Since you bought it** — gain trajectory [D10] · corroborates §1 by a second route

**§6 If someone else gave you a number** — lender explainer [D9] · upper bound · **ask: in writing**

**§7 What's moving** — live bar [B10] · competitors [B9] · change log 30-day [B8] · buyer portrait [A10] + reframe [A11] · two true things [C3] · suppression reason · **ask: tell me when it changes**

**§8 What sits under it** — flood [D7] · source + limitation

**§9 What you can do** — `DataRecordDrawer` [B6] · correction · no-lead contrast [D12] · **ask: correct / claim**

---

## Blocking before any of it ships

| # | Blocker | Blocks |
|---|---|---|
| 1 | **Ratify the intent-alert rule.** `offmarket-intent-alert.mjs` already tells Will when someone reaches the end having asked for nothing. *"The alert does not break this promise; acting on it would."* | §0 and §9 — *"nobody calls unless you ask"* appears twice and is load-bearing both times |
| 2 | **`device_token` write gap** — a reader from a printed QR has no token, so the answer is silently discarded while they see a success state | Any posted piece that invites a reply |
| 3 | **s 215 CMA question** | §1 |
| 4 | **Confidence-label calibration** | Any stated confidence |
| 5 | **Pin one error-rate figure** (11.1% vs 11.6%) with sample and date | §3 |
| 6 | **`adjusted_price` persistence** — verify whether the blocker is off-market-path-specific, since `/your-home` renders adjusted prices today | §2 |
| 7 | **Scarcity approval doesn't scale** — mini-site gates it behind a `ConsultantBadge`; 26,297 pages can't be hand-approved | §2 |
| 8 | **Load-test the on-demand valuation** — 10 requests in its lifetime, and the page would fire a ~50s compute per arrival | §1 |
| 9 | **Verify the pool contradiction** — deck card 03 lists *"a pool"*, card 05 lists *"no pool"* | §2 |

## Still open

- **Mobile.** Ten stacked value-then-ask blocks could read as ten paywalls. Prototype before building.
- **Does §4 land as honest or as attack?** It criticises a method Fields is licensed to use.
- **Detach elements for five of eight emblems** — the transition currently only works for three.
