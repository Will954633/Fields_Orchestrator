# Application map — the `/your-home` mini-site, audited in full

**Compiled:** 2026-08-06. **Subject:** the report built when an address is submitted at
`/analyse-your-home`. Front end `01_Website/src/pages/YourHomePage/` (9 tabs, ~35 components);
build `scripts/property_reports/` (45 modules) + `SlotResolver` + a systemd poller.
**Target:** the ten sections in `05_PAGE_FLOW.md`. **Companion to:** `07_APPLICATION_MAP.md` (V3 deck).

**State:** ✅ shipped, reusable · ◐ needs porting · ⚙ needs building · ⛔ out of scope.

> Supersedes the partial pass in `06_MINISITE_ASSETS.md`, which covered ~15 of ~80 assets.

---

## 1 · The five best things in it

Ranked by what they'd add to the off-market page.

### 1.1 `StatusBadge` — per-number provenance ⭐ the biggest single win

> *"Every important number on the mini-site should carry an honest status: reviewed by a human,
> still under review, auto-generated, updated overnight, an estimate only. **This turns
> provisional data into honesty rather than a weakness** — the seller always knows how much
> weight a figure can bear."*

**This generalises "suppression as a credential" from a fallback into a system.** Our page has
wildly uneven coverage — a range on some addresses, floor area missing on others, flood only in
Burleigh Waters. A per-number status badge makes that variance *legible* instead of invisible,
and it is the honest alternative to the confidence label we've had to ban.

**→ Every § carrying a figure.** ✅

### 1.2 `SlotResolver`'s never-half-fill rule

> *"One method per slot. Each method is independent — if it raises or returns None, the field is
> left null and the frontend hides the relevant block. **We never half-fill a field with
> garbage.**"*

The architectural answer to our coverage problem: independent slots, silent absence, no
degraded content. Paired with 1.1, absence becomes visible where it matters and invisible where
it doesn't.

**→ Architecture for all ten sections.** ✅

### 1.3 `canonical_resolver.py` — the golden record with provenance

> *"The same fact lives in several fields across a property doc (floor area in 4+ places, pool
> in 2+), none authoritative."*

Config-driven source priority (`config/canonical_attributes.yaml`) producing one canonical value
**plus where it came from**. This is what makes §9's correction ask answerable — you cannot
accept a correction to a fact that exists in four places with no precedence.

**→ §2, §9.** ✅

### 1.4 `verify_claim.py` — reproducibility as a product

> *"Converts 'we think it's rare' into 'here is where every number came from'."*

An evidence chain per attribute. It is the machinery behind the traceability claim, and it means
a challenged number can be reconstructed rather than defended.

**→ §2, §3.** ✅

### 1.5 `DynamicCaseStudy` (CS0) — "a home like yours, recently sold"

A complete, owner-addressed case study of a real nearby sale: photo gallery mirrored to our blob,
sale-history timeline, the market it sold into, a condition read, floor plan, and a **written
analysis addressed to the subject owner** — why that sale means what it means *for their home*.

Pairs with the deck's `_obvious_comp` (which says *why the obvious comparison misleads*). One
disqualifies a comparison, the other works one through properly.

**→ §2, after the obvious-comp.** ✅

---

## 2 · Front-end components

| # | Component | → | Why | State |
|---|---|---|---|---|
| Y1 | **`StatusBadge`** | all § | Per-number provenance — see 1.1 | ✅ |
| Y2 | **`SoWhat`** | voice | *No stat ships without a translation line.* Data-first vs fear-first | ✅ |
| Y3 | **`CitationStrip`** | voice | *If a claim has no source, the block should not render* | ✅ |
| Y4 | **`FearSection`** thesis/applied | layout | Better axis than free/locked — moving right gets more personal | ✅ |
| Y5 | **`ValuationEvidence`** L1/L2/L3 | §2 | The working, already rendering from engine output | ✅ |
| Y6 | **`RankedComparison`** funnel | §2 | *"Honest theatre: every step is a computation that genuinely ran"* | ✅ |
| Y7 | **`EvidenceMap`** | §2 | Comparables plotted against the subject, **numbered pins matching the cards below** so the reader moves between map and card. Spatial proof of "near" — and it fixes L3, where comps at 2.57 km were described as "near your street" | ✅ |
| Y8 | **`DynamicCaseStudy`** | §2 | See 1.5 | ✅ |
| Y9 | **`CaseStudiesPanel`** | §2 | Wrapper: CS0 dynamic + the static library | ✅ |
| Y10 | **`DataRecordDrawer`** | §9 | Every data point held, grouped and sourced — the precondition for correction | ✅ |
| Y11 | **`WhatChangedBanner`** | §7 + claim | First-load digest / return delta, with the honest-widening sub-line | ✅ |
| Y12 | **`LiveMarketStatus`** | §7 | *"Live, checked nightly"* — reads as maintained, not generated once | ✅ |
| Y13 | **`MatchCards`** | §7 | Explicit `differenceVsSubject` — *"COMPARISON, not a list of alternatives"* | ✅ |
| Y14 | **`CompetitorMap`** | §7 | Three marker tiers — subject copper/pulsing, combinatorial match sun-yellow, general competitor grey. **The visual hierarchy IS the scarcity argument** | ✅ |
| Y15 | **`ActivityFeed`** | §7 / claim | Reverse-chronological: new listings, comp sales, sales, market moves | ✅ |
| Y16 | **`StatutoryCMA`** | §1 | s 215 compliance + *"as at / valid until"* | ✅ / ⛔ question open |
| Y17 | **`PendingPlaceholder`** | §1 | Named, dated wait state | ✅ |
| Y18 | **`HeroSection`** slot-awareness | §0 | *"If pending, show a neutral address-led headline that doesn't make any uncommon-feature claims yet."* Graceful degradation, already solved | ✅ |
| Y19 | **`SummaryStrip`** | sticky | Address · range · competitors · updated, pinned under the header — *"the value never scrolls away"* | ✅ |
| Y20 | **`ResearchLibrary`** | §3 | *"The Source Layer, made visible… every claim has a footnote."* Its own note on the moat: replicating it means *"buying access to dozens of journals and hosting them — a six-month project, sustained"* | ✅ |
| Y21 | **`SoftCta`** | all asks | *"Phrased as a question, never 'call me'. Soft CTAs only, one per tab, no hard seller CTA."* **This is the rule our six asks must obey** | ✅ |
| Y22 | **`BookReviewButton`** | §2 review ask | A **working contact capture**: modal takes email *or* phone, preferred times, a note → `property-report-book-review` → emails Will. Replaced every `mailto:` | ✅ |
| Y23 | **`ShareButton`** | §1 or §2 | ⚠ **Reverses my earlier call.** I dropped `ShareMoment` as off-register for a private self-check — correctly. But this is different: *"send the report to a partner / friend / 'what does mum think' second opinion."* **Second-opinion seeking is J1, the best-evidenced job we have.** Sharing with a partner is not broadcasting to neighbours | ✅ |
| Y24 | **`ConsultantBadge`** | §2 | Distinguishes resolver-generated from human-approved. ⚠ Cannot scale to 26,297 pages — but `StatusBadge` (Y1) is the scalable form of the same idea | ✅ / ⚠ |
| Y25 | **`ChartImage`** | §3, §7 | 17 authored charts as static PNGs on the CDN — no bundle weight | ✅ |
| Y26 | **`ReportHeader` / `ReportFooter`** | shell | *"So the report feels like a personal document, not a page inside the corporate site"* | ✅ |
| Y27 | **`TabHero`** | — | Per-section full-bleed photo hero. Useful if V4 gets section heroes | ◐ |
| Y28 | **`MarketStateSection`** | §7 | Suburb pill + forward-indicator grid + gated narrative | ✅ |
| Y29 | **`SeasonalityStrip`** | ⛔ | Timing is a seller-journey question; mini-site itself puts it on Process | ⛔ |
| Y30 | **`PositionAtAGlance`** | ⛔ | Two of four questions are the unsupported buyer/competition angles | ⛔ |
| Y31 | **`ShareMoment`** | ⛔ | Broadcast-shaped scarcity card. Off-register — see Y23 for the version that isn't | ⛔ |
| Y32 | **`PlanQuestion` / `ProcessPlanSection`** | ⛔ / pattern | Seller plan-building. **But the interaction model transfers:** debounced POST, saves as you go, pre-loads on return. ⚠ Carries the `device_token` defect | ⛔ / ◐ |

---

## 3 · Tabs

| Tab | → | Why |
|---|---|---|
| **01 Your Home's Data** | §0, §2, §9 | Address, features, the data record, `your_street_narrative` |
| **02 Competition** | §7 | Live status, competitor map, ranked comparison, match cards |
| **03 Valuation** | §1, §2, §3 | Range, evidence map, comparable cards, adjustment grid, case studies, market state |
| **04 The Right Buyer** | §2 (scarcity), §7 (portrait) | *"Demand → strategy"*, opening on the **scarcity thesis** — confirming scarcity is the load-bearing argument, not the buyer |
| **05 The Process** | ⛔ | Seller decision-building — the deeper path |
| **Your Agent** | ⛔ | *"A listing decision is human"* — the consultant's biggest gap. Real, but it belongs downstream: our reader isn't choosing an agent |
| **FAQ** | ⚙ partial | *"The questions sellers actually search for at 11pm."* Ours are different questions but the framing is right |
| **Messages** | ⚙ | A private two-way channel — **a contact mechanism that isn't a form.** Worth considering against our six asks |
| **What Happens Next** | ⛔ | Seller ladder |

---

## 4 · The build layer — 45 modules

| # | Module | → | Why | State |
|---|---|---|---|---|
| R1 | `slot_resolver.py` | architecture | Never half-fill — see 1.2 | ✅ |
| R2 | `canonical_resolver.py` | §2, §9 | Golden record + provenance — see 1.3 | ✅ |
| R3 | `verify_claim.py` | §2, §3 | Reproducibility — see 1.4 | ✅ |
| R4 | `scarcity_features.py` | §2 | Anchors vs differentiators, cohort-relative, uninflatable | ✅ |
| R5 | `scarcity_narrative.py` | §2 | Opus turns the stack into hero strings. *"No longer leads with a single rare feature — it names the COMBINATION"* | ✅ |
| R6 | `walking_distances.py` | §2 | OSM Overpass POIs + **Mapbox Directions for real walking routes**, not straight-line. *"161m Sawgrass Park"* is a walk, not a radius | ✅ |
| R7 | `nearby_pois.py` | §2 | The POI layer behind rarity and the buyer portrait | ✅ |
| R8 | `cohort_premiums.py` | §2 | Each feature priced against the suburb's last-24-month sold cohort — the dollar value of an anchor | ✅ |
| R9 | `competitor_matcher.py` | §7 | The substitute set | ✅ |
| R10 | `comparable_feed.py` | §2 | The comparable set | ✅ |
| R11 | `build_events.py` | §7 | The durable change log | ✅ |
| R12 | `case_study_dynamic.py` + `build_case_study.py` + `draft_case_analysis.py` | §2 | CS0 — see 1.5 | ✅ |
| R13 | `statutory_cma.py` | §1 | The CMA of record | ✅ |
| R14 | `your_street_narrative.py` | §2 | Deterministic street-premium prose from `precompute_valuations` output. **Deterministic, so no LLM cost or drift** | ✅ |
| R15 | `positioning_narrative.py` | §2 | Angle + reasoning + vocabulary anchored to verifiable facts | ✅ |
| R16 | `personas_narrative.py` | §7 | Three personas most likely to pay top of range | ✅ |
| R17 | `buyers_narrative.py` | §7 | Thesis, catchment, campaign math — shares upstream context with R15/R16 **so the sections cohere** | ✅ |
| R18 | `market_narrative.py` | §7 | Market state prose | ✅ |
| R19 | `hero_photo.py`, `mirror_report_photos.py` | §0, §2 | Photo sourcing + blob mirroring (ORB-safe) | ✅ |
| R20 | `inline_satellite.py`, `inline_street_view.py`, `satellite_annotation.py`, `lot_boundary.py` | §2 | Aerial/street imagery + annotation + boundary — **the visual evidence for a home with no interior photography** | ✅ |
| R21 | `inline_floor_plan.py`, `floor_plan_debrand.py` | §2 | Floor plan with competitor branding removed | ✅ |
| R22 | `occupancy_classifier.py` | ⚠ | Owner-occupied vs rented. **Do not surface** — occupancy inference is exactly the C13/C11 privacy line | ⛔ |
| R23 | `refresh_feature_evidence.py` | §2 | Keeps feature evidence current | ✅ |
| R24 | `poller.py` | §1 | systemd service picking up stub docs ≥5s old — **the async build pattern our 30–90s valuation needs** | ✅ |
| R25 | `messages.py` | ask | Two-way channel backend | ✅ |
| R26 | `valuation_format.py` | §1 | Consistent money/range formatting | ✅ |
| R27 | `inline_features.py`, `inline_scrape.py`, `backfill_stated_floor_area.py` | §1 | Attribute filling — directly raises the 65–94% ceiling | ✅ |

---

## 5 · What this changes in the plan

1. **`StatusBadge` becomes a foundation, not a nice-to-have.** It is the honest, scalable answer to uneven coverage *and* to the banned confidence label. Add to §1's dependency list.
2. **`ShareButton` goes back in.** I ruled out sharing on the private-self-check evidence; that reasoning holds for broadcast, not for *"what does mum think"*. Second-opinion seeking is the best-evidenced job we have.
3. **`EvidenceMap` fixes L3 for free.** Numbered pins make distance visible, so we stop having to write around comparables 2.57 km away.
4. **`BookReviewButton` is a working capture path** — email *or* phone, plus a note. The §2 review ask should reuse it rather than build a form.
5. **The scarcity thesis opens the Buyer tab**, not the buyer. Independent confirmation that scarcity is the load-bearing argument and the persona is its expression.
6. **`poller.py` is the pattern for our async valuation** — stub doc, poller, resolver, render when ready.
7. **`occupancy_classifier.py` exists and must stay off the page.** Worth recording as an explicit never, given it would be trivial to surface.

## 6 · Blockers this audit adds

| # | Blocker | Blocks |
|---|---|---|
| 10 | **`canonical_resolver` must run for off-market subjects** — corrections are meaningless without a golden record and a source priority | §9 |
| 11 | **Mapbox cost at scale.** `EvidenceMap`, `CompetitorMap` and `walking_distances` all hit paid Mapbox APIs. 70 reports is not 26,297 pages | §2, §7 |
| 12 | **Opus-written narratives × 26,297.** R5/R15/R16/R17 are LLM calls per property. `your_street_narrative` (R14) shows the deterministic alternative — decide which sections must be written and which can be computed | §2, §7 |
