# House Mini-Site — Design Document

**Version:** 1.0 · **Date:** 2026-05-14 · **Status:** Pre-build brief
**Parent docs:** [Concept.md](Concept.md) · [Opportunity-Report.md](Opportunity-Report.md) · [README.md](README.md) (v0.3 state)
**Source design system:** [`09_Appraisals/Version_Four/`](../09_Appraisals/Version_Four/)
**Source content:** [`08_Seller-Book/`](../08_Seller-Book/) (Before You List, v4.6)

---

## 1. Design Brief

> **A seller enters their address. Within 60 seconds, they are reading a living, hyper-local document that systematically dismantles every one of the 15 fears that has been keeping them awake. By the time the printed appraisal arrives on their doorstep three days later, choosing any other agent feels irrational.**

The mini-site is *not* a digital brochure. It is a **personalised seller-fear engine** that turns the book, the appraisal, the comp engine and the suburb data into one continuous experience anchored to the subject property.

Three filters apply to every design decision:

1. **Does it answer one of the 15 fears?** If not, cut it.
2. **Does it reference the subject property specifically?** If it could be lifted into someone else's report unchanged, it isn't doing enough work.
3. **Could a competing agent (with all the same source material) reproduce it for the same address in the same time?** If yes, our moat just shrank.

---

## 2. The Three Readers (carry-over from V4 strategy)

Every page renders in three readable layers simultaneously. This is the same model V4 print uses — applied to the web.

| Reader | Time | What they take away |
|---|---|---|
| **A — The Skim-Reader** | 60 sec | Hero + tab headlines + the "1 of N" share moment + valuation range |
| **B — The Compare-Shopper** | 10 min | Comp table, scarcity stack, methodology notes, agent comparison block |
| **C — The Deep-Reader** | 60+ min | Full prose, citations, embedded book chapters, methodology callouts |

**Design implication:** every section has a headline (5-second layer), a sub-headline + callout (60-second layer), and prose with citations (full-depth layer). Most agent sites operate on one layer. We operate on three.

---

## 3. Information Architecture

### 3.1 Routes

| URL | Page | Audience | Indexed |
|---|---|---|---|
| `/seller-questions` | Fears Library hub | Cold traffic (FB, Google) | Yes |
| `/seller-questions/<fear-slug>` | One per top 15 fears | Cold traffic | Yes |
| `/analyse-your-home` | Address gate (address only — no email) | Warm intent | Yes |
| `/your-home/<slug>` | Personalised mini-site | Opted-in seller | **No** (`noindex,nofollow`) |
| `/your-home/<slug>?return=1` | Return visit | Re-engaged seller | No |

**Important — the gate is single-field.** A seller enters their address and nothing else. No email, no phone, no name. The print appraisal is the contact channel: we have their address, so we send the report to their door. This is the lowest possible friction at the funnel's most important step, and it dictates several downstream design decisions (re-engagement, state-change notifications, the role of the mini-site itself as the only digital touchpoint).

### 3.2 Tab Structure (mini-site only)

The mini-site is one URL with hash-routed tabs. Order is the journey order — not random.

```
/your-home/<slug>#home          The hook + your home, named
/your-home/<slug>#valuation     What it's worth + why we know
/your-home/<slug>#buyers        Who will pay the premium
/your-home/<slug>#positioning   How we will sell it
/your-home/<slug>#market        What you're selling into
/your-home/<slug>#process       The selling process (the fears)
/your-home/<slug>#next          What happens next
```

Seven tabs map to the V4 print structure (six spreads + Next), with two additions: **Process** (where most book content lives) and **Market** (where time-sensitive data lives).

**Mapping to v0.3 tabs:**
- v0.3 `home` → unchanged
- v0.3 `valuation` → unchanged
- v0.3 `market` → split into **Market** (data) + **Buyers** (avatars) + **Positioning** (how)
- v0.3 `next` → unchanged
- **NEW: Process** — the seller-fears tab, where most book content lives

---

## 4. Tab-by-Tab Section Map

Every section below is a content block. Each block has a slot in the React component tree, a data source, and a personalisation rule.

### 4.1 `#home` — *Your Home, Named*

| Block | Purpose | Personalised? | Source |
|---|---|---|---|
| Hero (cinematic photo + scrim + emotional headline) | Hook | Property photo + first-line addressing the subject | Listing photos / blob storage |
| Activity feed | Living-dashboard signal | Yes — items reference subject + comps | `system_monitor.property_reports.activity[]` |
| "One of N" Share Moment | The single most screenshotable card | Yes — N derived from comp engine | Scarcity analysis |
| Stat tiles (4-up) | Land area, internal area, bed/bath, satellite | Yes | Cadastral + listing |
| Photo gallery | Memory + emotional anchor | Yes | Blob storage |
| Inventory of competition | Live count of direct rivals | Yes | `Gold_Coast.<suburb>` filtered by price ±15% and bed match |
| POI proximity strip | Walking distance to top 5 | Yes | Mapbox isochrones / pre-computed |

### 4.2 `#valuation` — *What It's Worth, and Why We Know*

Already at v0.3. Two states.

**Under-review state (Days 0–3):**
- Working range (CatBoost ballpark, presented as a *range only*)
- Methodology block (the comparable-sales workflow, the 1,689-estimate backtest result)
- ETA banner ("Mac is reviewing your home — final valuation by [date]")
- "1 of 4" share moment (works even pre-review because scarcity is property-feature-driven)

**Final state (Day 3+):**
- Listing price + target sale price (range, never single figure in headline)
- The four-condition precise-pricing checklist (V4 page 11)
- Six named comps, line-itemised with adjustments
- 11.4% MAE vs Domain's 15.0% (trust transfer)
- Inspection caveat ("we'd refine this after walking through")
- Methodology callout linking to book Ch 1

**Fears addressed:** #6 (Property Valuation), #15 (Selling Strategy), #1 (Agent trust, indirectly).

### 4.3 `#buyers` — *Who Pays the Premium* (NEW, from V4 S02)

| Block | Purpose | Source |
|---|---|---|
| The thesis | "Scarcity changes what buyers will pay" headline | V4 S02 left page |
| Persona cards (2-3) | Specific buyer avatars for this property | Per-suburb avatar library (we have the research) |
| Why these buyers | What feature combination they want | Subject property scarcity + Halo positioning research |
| Where they live now | Geographic catchment (interstate / local / upgrader) | DB query against historical buyer origin |

**Fears addressed:** #15 (Selling Strategy), #11 (Listing Platforms).

### 4.4 `#positioning` — *How We Will Sell It* (NEW, from V4 S05)

| Block | Purpose | Source |
|---|---|---|
| The contrast | Standard vs Fields positioning side-by-side | V4 S05 right page |
| The four levers | Photography, copy, scarcity language, timing | Book Ch 5 |
| Property-specific positioning prose | 200-word editorial about *this home* | Opus pipeline (existing `/property/:id` system) |
| Forbidden-word audit | "We will never write the words..." | Editorial rules block |

**Fears addressed:** #1 (Agent over-promise), #8 (Home improvements / what to fix), #13 (FSBO — implicitly, we show what an agent does that a private seller can't).

### 4.5 `#market` — *What You're Selling Into*

| Block | Purpose | Source |
|---|---|---|
| Market state tile grid | FCI, days on market, stock, wage growth, active listings | `precomputed_market_charts` + `precomputed_indexed_prices` |
| Active competitor map | Plotted on interactive map | `Gold_Coast.<suburb>` filter for_sale |
| Scarcity stack | Sold-cohort premiums for property's feature combo | Subject property analysis |
| Seasonality recommendation | Best listing window for this property type | Book Ch 2 heatmap, filtered by suburb |
| Auction vs Private Treaty | Per-property recommendation | Book Ch 3 + DB query for method-of-sale outcomes by feature |
| Most-similar recent sale | Anchor case study | Comp engine top result |

**Fears addressed:** #7 (Market Analysis), #14 (Market Timing), #12 (Auction Process), #6 (Valuation).

### 4.6 `#process` — *The Selling Process* (NEW — the fears tab)

This is the new tab. It holds the content that addresses the 9 fears the V4 print intentionally doesn't cover. The book covers most of them. The job here is to **make book content feel property-specific**.

| Section | Fears addressed | Source |
|---|---|---|
| Same-day settlement playbook | #2 Legal Requirements | Book Ch 8 + subject-property dates |
| Sell first vs buy first | #4 Mortgage Considerations | Book Ch 8 + mortgage broker content we already have |
| Cost-of-sale calculator | #10 Selling Costs | Book Ch 6 + Ch 7 + subject-property estimated commission |
| Property-prep checklist | #8 Home Improvements | Book App A + room-by-room from listing photos |
| Tax considerations (PPOR vs IP) | #3 Tax Implications | Book content + the existing CGT research we have |
| Tenant-in-place selling | #5 Tenant Considerations | Book content + investor sale data |
| Contract terms walk-through | #9 Contract Terms | Book Ch 8 |
| FSBO honest comparison | #13 Private Sale | Book Ch 6 commission vs outcome analysis |
| Agent selection scorecard | #1 Agent Selection | Book Ch 6 + V4 S06 trust spread |
| Finance fall-through risk | #15 Selling Strategy | Book Ch 7 |

**Design pattern for each section:**

```
┌────────────────────────────────────────────────────────────────┐
│  [Fear restated in seller's own words]                         │
│  e.g. "Will the buyer's finance fall through?"                 │
│                                                                │
│  [One-sentence reframe]                                        │
│  e.g. "It happens in ~7% of GC sales. Here is what we do."     │
│                                                                │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │ DATA / CHART        │  │ APPLIED TO YOUR HOME            │  │
│  │ (from book)         │  │ "For 13 Terrace Court, our      │  │
│  │ Chart 7-1: Active   │  │ first-7-days plan reaches X     │  │
│  │ vs passive buyers   │  │ active buyers in your price     │  │
│  │                     │  │ bracket within 5km..."          │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
│                                                                │
│  [Citation strip] · Source: book Ch 7 · Last reviewed: [date]  │
│                                                                │
│  ▸ Read the full chapter in Before You List →                  │
└────────────────────────────────────────────────────────────────┘
```

Every fear section follows this two-column **thesis / applied-to-your-home** pattern. It is the same pattern V4 print uses across the six spreads. **Consistency is what makes the document feel authored.**

### 4.7 `#next` — *What Happens Next*

Already at v0.3. Three-step ladder (Review → Conversation → Decide), book-conversation card, printed-appraisal ETA, library links. Add:

- **The walk-away promise** (front and centre, not buried).
- **The print delivery moment** — countdown to dispatch, opt-in for "send me a photo when it ships" SMS.
- **Family-share button** — the prompt that says *"This is a long read. Want to send it to your partner?"*

**Fears addressed:** #1 (Agent selection — through the walk-away), all (by closing with calm).

---

## 5. The State Machine

The mini-site has four states. The same URL, very different content.

```
       ┌────────────────────┐
       │  STATE 0 — STUB    │  Created on /analyse-your-home submission.
       │  (T = 0 to 60s)    │  Address only. Most blocks placeholdered.
       └─────────┬──────────┘  Activity feed: "We received your address."
                 ▼
       ┌────────────────────┐
       │  STATE 1 — UNDER   │  Auto-generated content from address alone.
       │  REVIEW            │  (T = 1 min to 3 days)
       └─────────┬──────────┘  Valuation in working-range mode.
                 ▼              Activity feed: comp selected, market shifted.
       ┌────────────────────┐
       │  STATE 2 — FINAL   │  Human-pass valuation published. Print queued.
       │  (T = day 3+)      │  Activity feed: print dispatched.
       └─────────┬──────────┘
                 ▼
       ┌────────────────────┐
       │  STATE 3 — LIVING  │  Print delivered. Continues to refresh nightly.
       │  (T = day 5+ ∞)    │  New comps appear. Market state updates.
       └────────────────────┘  Most sellers visit 3-6 times over 90 days.
```

**Design implication:** every block has a state-aware version. Some show placeholders in State 0. Some show "Mac is reviewing..." in State 1. Some only render in State 2+. This is a render-tree constraint, not a content constraint — every block exists in every state, the *fill* changes.

### 5.1 Re-engagement without email

Because we never ask for an email, the mini-site itself is the only digital touchpoint until the printed report arrives. State transitions cannot push a notification — the seller must return to the URL to see them. Three mitigations are built into the design:

1. **The printed appraisal IS the re-engagement event.** Day 5, regardless of whether they returned, a hand-delivered/couriered report arrives at the address. This is the most reliable re-engagement channel in the funnel and the one competitors structurally cannot copy at low cost.
2. **Voluntary contact capture inside the mini-site.** Embedded in `#next` and (more subtly) in the `under_review` banner: "Want a reminder when your final valuation is ready? Drop your email." Opt-in, never gated. A meaningful share of sellers will give it — but only after they've seen our work, not before.
3. **Day-1 postcard.** We have their address. A printed postcard with the mini-site URL and "Mac is reviewing your home — you can watch the progress here" goes in the post within 24 hours of submission. Costs ~$2 a unit. Doubles as a brand moment. Optional but recommended.

These are mitigations, not replacements for an email field. The strategic position is: **we earn the email by being worth re-contacting, not by gating the front door.**

---

## 6. Personalisation Engine

What changes between two different sellers' mini-sites? Everything below.

### 6.1 Inputs (what we know from address alone)

| Signal | Source | Used for |
|---|---|---|
| Suburb | Address geocode | Suburb-specific data feeds, book chapter selection |
| Cadastral lot size | Council data / `Gold_Coast.<suburb>` | Land-area-anchored prose |
| Listing history | `Gold_Coast.<suburb>` | If recently sold or for sale, photos + features known |
| Inferred property type | Cadastral + Domain match | House / unit / townhouse — drives avatar selection |
| Inferred avatar | Property type + price tier + listing context | Which fear ordering to show |
| Price bracket | CatBoost ballpark | Competitor inventory, comparable filtering |
| Time of submission | Server timestamp | Activity feed item phrasing ("we noticed you visited last night...") |
| Return visit number | Session token | Different welcome on visit 2, 4, 6 |

### 6.2 Personalisation Rules

**Rule 1 — Avatar-driven section ordering.** Halo identified three avatars. Each gets a different `#process` tab order:

- **Stressed Upgrader** (4220/4226/4227, house, $800K-$1.4M, owner-occupier): leads with Settlement, Sell-first-vs-buy-first, Property Prep.
- **Reluctant Seller** ($600K-$1.2M, forced-sale signals — older listing, agent churn): leads with Cost-of-sale, FSBO Honest Comparison, Agent Scorecard.
- **Savvy Investor** (unit, recent rental, $700K+, IP signals): leads with Tax Considerations, Tenant-in-place, Auction vs PT.

Same content, different prominence.

**Rule 2 — Subject-property substitution.** Every paragraph in every section has slots:

```
"For a {bed}-bedroom home like yours on {street},
priced in the {price_bracket} range, the active competition
right now is {n_competitors} homes within {radius}km..."
```

Slot substitution runs server-side before render. Never client-side (SEO, performance, security).

**Rule 3 — Suburb-specific data feeds.** Charts and stats automatically pull from the correct suburb's data:

- Burleigh Waters → flood context block included (the suburb's #1 search query is "does Burleigh Waters flood?")
- Robina → school catchment block + master-planned community context
- Varsity Lakes → lakefront premium block + young-demographic avatar emphasis

**Rule 4 — Time-aware activity feed.** Generates 2-3 items across Days 1-3:

- Day 1: "Mac selected six comparable sales today. Closest: [comp address]."
- Day 2: "A property similar to yours just hit the market at [address] — [price]. We've added it to your competitive set."
- Day 3: "Final valuation published. Printed copy goes to press tonight."

**Rule 5 — Return-visit progression.** First visit shows the *thesis*. Second visit highlights *what's changed* since last visit. Third visit prompts the *conversation* CTA more directly.

Return-visit detection without email requires a `localStorage` token issued at first load and a `last_visit_at` ping back to the server on each session. Anonymous, device-bound — a seller who opens the URL on a partner's phone gets the "first visit" experience again, which is acceptable (it is functionally a different reader).

### 6.3 What we will NOT personalise

- **Forbidden words list** — non-negotiable, every property gets the same audit.
- **Methodology disclosures** — same MAE, same comp count caveats, same confidence levels.
- **The walk-away promise** — identical for every seller. It is a brand promise, not a personalised one.
- **Editorial rules** — no advice, no predictions, no single-figure valuations regardless of avatar.

---

## 7. Visual System

We inherit the V4 design language wholesale. The web version is its sibling, not a port.

### 7.1 Typography

- **Headlines:** same display face as V4 print (TBC by designer — currently a serif display).
- **Body:** legible humanist sans, 17px base on desktop, 16px on mobile.
- **Mono:** numerics, citations, methodology notes — same mono face as V4.
- **Three-layer hierarchy:** Display (40-72px) → Subhead (22-28px) → Body (16-17px) → Caption (12-13px mono).

### 7.2 Colour

- **Background:** off-white (#FAF8F4 or similar — matches V4 print).
- **Body:** near-black (#1A1A1A).
- **Brand accent:** TBC (currently undefined — we should lock this on print first).
- **Citation grey:** muted (#6B6B6B).
- **Caution / market-shift:** subdued amber, never red.
- **No fluoro, no gradients, no shadows on cards.** V4 is editorial-magazine, not real-estate-website. The web must follow.

### 7.3 Layout

- **Max content width:** 1200px on desktop, full-bleed for hero only.
- **Two-column thesis/applied-to-your-home pattern** dominant in `#process` and `#buyers` and `#positioning`.
- **Image-led:** every section has at least one anchor image (property photo, satellite, chart, map).
- **Citation strip** at the foot of every section — small mono caps, sources named, last-reviewed date.

### 7.4 Charts

Every chart from the book (Ch 1-1, Ch 2-1, Ch 3-1, Ch 4-1, Ch 5-4, Ch 6-1, Ch 7-1, Ch 7-3) is available as PNG. Embed them inline, with the *applied-to-your-home* prose to the right of each one. Web-renderable versions can come later.

### 7.5 Components inherited from v0.3

- `HeroSection.tsx`, `ActivityFeed.tsx`, `ShareMoment.tsx`, `YourHomeTab.tsx`, `ValuationTab.tsx`, `MarketTab.tsx`, `NextTab.tsx`, `YourHomePage.module.css`.

### 7.6 Components to build (new)

- `BuyersTab.tsx` (S02 mapping)
- `PositioningTab.tsx` (S05 mapping)
- `ProcessTab.tsx` (NEW — the fears tab, container)
- `FearSection.tsx` (the reusable thesis/applied two-column block — 10 instances inside `ProcessTab`)
- `MarketStateGrid.tsx` (already partial — needs interactive map upgrade)
- `WalkAwayCard.tsx` (front-of-Next-tab card)
- `PrintDeliveryStatusCard.tsx` (countdown + SMS opt-in)
- `FamilyShareButton.tsx` (specific share prompt)

---

## 8. Editorial Voice & Compliance

These are non-negotiable. Every word must pass the existing project editorial rules (see `CLAUDE.md` §5).

- **No advice.** "We would" not "you should". Ever.
- **No predictions.** "The data shows" not "the market will".
- **No single-figure valuations in headlines.** Ranges only.
- **No forbidden words.** Stunning, nestled, boasting, rare opportunity, robust market — auto-rejected.
- **Exact transaction prices.** Never rounded — `$1,275,000` not `$1.3M`.
- **Suburbs capitalised.** Always.
- **Cite every claim.** If we can't link to a source, it doesn't ship.
- **Value framing.** Trade-offs are value, not flaws. The seller should read our work and think we'd position their property honestly.

**Auto-audit:** before any new content block lands on a mini-site, it runs through the existing editorial pipeline (used for property page editorials). Fail = block doesn't render. Pass = renders with a citation strip.

---

## 9. Mobile

~70% of sellers will open the link on mobile first (FB ad → tap → mobile browser). Desktop is the second-session experience (compare-shopper with partner).

**Mobile design constraints:**
- Tab navigation collapses to a sticky bottom bar.
- The thesis/applied two-column pattern stacks vertically — thesis first, applied-to-your-home second.
- Hero photo fills 80vh.
- Activity feed is collapsible (default-collapsed after first visit).
- Charts re-render at single-column width.
- "Share to family" prompt fires at scroll-depth = 40% on first session.

**Desktop additions (only):**
- The interactive competitor map.
- The side-by-side comp adjustment table.
- The full prose deep-read mode.

---

## 10. The Share Moment

Every mini-site has exactly one screenshotable card. This is the asset that travels through WhatsApp, text, Facebook, dinner-table conversation.

Current v0.3 example: *"This is one of only four homes in Merrimac with a north-facing pool, lake frontage, and a 700m²+ lot."*

**Design rules:**
- **Specific to the property** — the seller must feel ownership.
- **Specific numerically** — "one of four" beats "rare." Ellsberg's ambiguity aversion (Concept.md) applies in both directions: certainty is shareable.
- **Brand-light** — the watermark is small. The seller is the hero, not Fields.
- **Auto-generated as a PNG** — the share button generates a 1200×630 OG image, downloadable.

This card is the single most replicated artefact in the funnel. It is also the asset Facebook ads will reuse for retargeting.

---

## 11. Tabs Decision Matrix

If you want a one-screen reference for "what goes where":

```
                            Stressed   Reluctant  Savvy
Fear                        Upgrader   Seller     Investor    Tab
─────────────────────────────────────────────────────────────────────
1.  Agent Selection         med        HIGH       med         #next, #process
2.  Legal Requirements      HIGH       med        med         #process
3.  Tax Implications        low        low        HIGH        #process
4.  Mortgage / sell-first   HIGH       low        med         #process
5.  Tenant in place         low        low        HIGH        #process
6.  Property Valuation      HIGH       HIGH       HIGH        #valuation
7.  Market Analysis         med        med        HIGH        #market
8.  Home Improvements       med        HIGH       low         #process, #positioning
9.  Contract Terms          HIGH       HIGH       med         #process
10. Selling Costs           med        HIGH       med         #process
11. Listing Platforms       low        low        med         #positioning, #market
12. Auction Process         med        med        HIGH        #market
13. FSBO Comparison         low        HIGH       low         #process
14. Market Timing           med        low        HIGH        #market
15. Selling Strategy        med        med        med         #process, #positioning
```

This matrix drives the **avatar-based section ordering** in §6.2 Rule 1.

---

## 12. Success Criteria for the Design

The design is succeeding when, three months after launch, we can show:

1. **Median time-on-mini-site ≥ 18 minutes** (V4 print equivalent).
2. **Multi-session opens ≥ 3 per recipient** (sellers return).
3. **Share-card image generated by ≥ 30% of sessions** (the asset travels).
4. **`#process` tab visited by ≥ 60% of sessions** (the new fears tab earns its place).
5. **At least one seller per week emails an unprompted reaction to a specific section** (the prose lands).

If any of these miss, the brief failed — not the implementation.

---

*Filed: `11_House_Mini_Site/Design.md` · Owner: Will Simpson · Updated 2026-05-14*
