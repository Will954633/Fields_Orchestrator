# Off-Market Discovery — Production Port Scope

**Goal:** ship the Discovery Experience (the scroll prototype, `page/discovery.html`) as the
live `/off-market/:slug` page, generated per-address by our engine.

**Guiding architecture:** reuse the *exact* precompute→Cosmos→React pattern the current
off-market page already uses (`offmarket_intel`, `offmarket_positioning` are computed on the
VM and read by the React loader). The Discovery deck becomes a **third precomputed layer**
that sits downstream of those two — it consumes their output plus our new engine layers
(discovery angle, POI cluster, wait-time, green-space adjacency, comparable deltas, personas,
insights, tiered valuation) and emits one render-ready JSON document per house.

The engine is **fully deterministic — no LLM** — so precompute is cheap and cacheable.

---

## 1. JSON schema — `offmarket_discovery` document (one per slug)

Design rule: the JSON carries **final, filled text** (copy.yaml stays the single source of
copy; Python fills it). **React is presentation-only** — it maps `card.type` → a component and
styles it; it never owns any copy. Conditional pieces (insight, wait-time, rarity, boundary
line) are simply absent when not applicable, and the component renders nothing.

```jsonc
{
  "slug": "8-corina-close-robina",
  "suburb_key": "robina",
  "address": "8 Corina Close, Robina QLD 4226",
  "address_short": "8 Corina Close",
  "suburb_display": "Robina",
  "lead_angle": "parkland",
  "hero_image": null,              // production: aerial/best photo URL (Phase 2)
  "generated_at": "2026-07-31T…",
  "engine_version": "disc-v1",
  "source_hash": "sha1:…",        // of the inputs → skip rebuild when unchanged
  "cards": [
    { "type": "recognition", "n": 1,
      "headline": "We found your home.",
      "address": "8 Corina Close, Robina",
      "lede": "We've analysed it. The results were interesting.",
      "credibility": [ {"fig":"39","text":"property characteristics analysed"},
                       {"fig":"2,922","text":"recent nearby sales reviewed"},
                       {"fig":"12,000+","text":"homes compared"} ],
      "next": "What was interesting?" },

    { "type": "hook", "n": 2, "answer": "Here's what stood out.",
      "headline": "There's one thing right at your boundary that very few homes nearby can claim — and it keeps quietly removing your competition.",
      "body": "Most property websites compare homes on basic features — beds, baths, a price guess. We looked deeper.",
      "cta_label": "Show me what makes it different",
      "next": "So what did you find?" },

    { "type": "reveal", "n": 3, "answer": "Your backdrop is the story.",
      "lead": [ {"t":"Your rear boundary backs onto "}, {"t":"Dexter Park","em":true},
                {"t":" — green space that can't be built out."} ],  // em → accent span
      "features_intro": "What sits in front of it",
      "features": ["4 bedrooms","single-level living","a premium finish throughout"],
      "boundary_line": null,        // present on non-parkland leads
      "rarity": "Of the 106 homes nearby that share your core combination, only 14 are also this close to a park, childcare, a café and a supermarket — all at once.",
      "doorstep_intro": "And at your doorstep",
      "doorstep": [ {"dist":"249m","name":"Scottsdale Reserve"}, … ],
      "insight": null,
      "next": "Why does that matter?" },

    { "type": "explanation", "n": 4, "answer": "Why that backdrop matters",
      "headline": "A buyer can renovate a house. They can't manufacture a park at the back fence.",
      "close": "Homes that border protected green space are a fixed, tightly-held set.",
      "filters": null,              // {intro, items[]} on scarcity leads
      "wait": null,                 // {intro, line, disclaimer} when rare-on-the-ground
      "next": "So who am I actually competing with?" },

    { "type": "competition", "n": 5, "answer": "…",
      "headline": "Most agents find three similar sales…",
      "funnel": [ {"label":"Homes in Robina","value":"12,000"},
                  {"label":"For sale across the area","value":"230"},
                  {"label":"Comparable to yours","value":"6","final":true} ],
      "none_note": null, "next": "…" },

    { "type": "comparable", "n": 6, "answer": "The obvious comparison can mislead you.",
      "comp": {"address":"84 Nardoo Street","price":"$1,486,138","distance_m":380,
               "deltas":["78m² more land","45m² more floor area","built 9 years later"]},
      "looks":"Looks like the same home.", "reveal_intro":"But against yours",
      "close":"Same street, different home. The headline number was never the comparison.",
      "insight":"Worth knowing: across local sales, each extra bedroom has been worth $255,000–$607,000 …",
      "next":"So what will buyers actually pay for in mine?" },

    { "type": "value_drivers", "n": 7, "answer":"Here's what carries the price.",
      "strengthens": {"intro":"What strengthens your position","items":["bedroom count"]},
      "negotiate":   {"intro":"Where a buyer may focus","items":["no pool"]},
      "close":"Knowing both is how you hold your number.",
      "insight":"Buyers love a pool — but across 2,153 local sales it added only about 1–4% …",
      "next":"And who is that buyer?" },

    { "type": "buyer", "n": 8, "answer":"Someone is already looking for a home like yours.",
      "portrait":"A downsizer ready to leave stairs and a big garden behind, after an easy single-level home in Robina.",
      "fit":"What a cheaper home can't give them: a single level, no stairs to manage, Dexter Park to wander at the door and a home already done to a high standard.",
      "reframe":"Right now it's your home. To them, it's the one they've been waiting for.",
      "next":"So where does that put its value?" },

    { "type": "valuation", "n": 9, "answer":"Based on everything we've analysed…",
      "likely_intro":"Most likely selling position", "anchor":"Around $1.35 million",
      "range_intro":"Most comparable homes sold between", "range":"$1,178,609 – $1,500,048",
      "range_note":"This range reflects homes with similar characteristics …",
      "basis":["49 adjusted comparable sales","the competing homes buyers would actually consider",
               "feature-by-feature adjustments","current market conditions"],
      "tier_caveat": null,          // present on exterior_evidence / thin tiers
      "closing":"Our analysis identifies where your home is most likely to sit …",
      "next":"If I ever did sell — how would you position it?" },

    { "type": "strategy", "n": 10, "answer":"If you decided to sell, here's what we'd do.",
      "frame_line":"A Robina low-maintenance, single-level home.",
      "lead_line":"We'd lead on the four-bedroom layout and single-level living …",
      "avoid":["a feature-scarcity play"],
      "cta_label":"Build my complete selling strategy" }
  ],
  "build_notes": { "discovery_scores": {"parkland":9}, "gaps": [] }   // never rendered
}
```

Notes:
- **Omission = absence.** A card whose data is thin simply drops fields (or the whole card, e.g. no comparable). React renders only what's present — same "never fake" rule as the markdown.
- **`lead` as a token array** lets React apply the accent span (`em`) without parsing HTML — safer than an HTML string.
- Cards keep their order and `n`; the chapter number is `n`, no internal labels ("The Hook") ever leave the engine.

## 2. Cosmos collection — `system_monitor.offmarket_discovery`

- One document per off-market house, `_id` or unique index on **`slug`**.
- Sits alongside `offmarket_intel` / `offmarket_positioning` (same DB, same access pattern).
- Fields: the JSON above + `generated_at`, `engine_version`, `source_hash`, `viewed_at`
  (bumped by the loader so the nightly refresh can prioritise viewed homes).
- **Read path (SSR):** the off-market loader (`db.server.ts` / `off-market.$slug.tsx`) reads
  this doc by slug — same firewall path already used for `offmarket_intel`.

## 3. The builder / nightly batch

**Architecture: on-demand build + cache + nightly refresh** — NOT precompute-all. Rationale:
~17k eligible houses vs ~17 views/day, so we only ever build what's actually looked at, plus a
nightly top-up. This mirrors the existing `offmarket_intel_poller` on-demand model.

- **New script `scripts/offmarket_discovery_build.py`** — `--slug X` builds one deck:
  runs our `fact_bundle.build()` + a new `assemble.emit_json()` → upserts
  `offmarket_discovery`. Flags: `--all-stale`, `--delta`, `--viewed`.
  - Reuses everything: `fact_bundle.py`, `poi_rarity.py`, `wait_time.py`, `green_space.py`
    (OSM polygon cache already on the VM), and the deterministic resolvers
    (`compute_intel`, `positioning_object`, `slot_resolver` valuation tiers).
  - **New code needed:** `assemble.emit_json()` — the card renderers currently build markdown
    `parts`; add a parallel path that builds the typed card dicts above. (Main dev item.)
- **On-demand trigger:** when the SSR loader finds no fresh `offmarket_discovery`, it enqueues
  a build (reuse the `valuation_requests`-style queue → a poller builds it) and the page falls
  back to the **current** `OffMarketDeck` until the doc lands (never a blank page).
- **Nightly:** `--delta` rebuilds docs whose `source_hash` changed (new sale / new valuation /
  new intel) plus any `viewed_at` in the last N days. Wrapped in `job_run(cadence_hours=24)`
  (CLAUDE.md Rule 7) so it self-reports on the Systems Health board.
- **Change detection:** `source_hash` = hash of (valuation computed_at, offmarket_intel
  updated_at, offmarket_positioning updated_at, subject feature snapshot, sold-window date).
  Unchanged → skip.

## 4. React rendering

- **New component tree** `src/pages/OffMarketPage/discovery/`:
  - `DiscoveryDeck.tsx` — takes the JSON, maps `card.type` → a card component, wires the
    scroll-reveal (`IntersectionObserver` hook), the fixed chrome (logo + site menu, progress
    rail).
  - One component per card type (`RecognitionCard`, `HookCard`, `RevealCard`,
    `CompetitionCard`, `ComparableCard`, `ValueDriversCard`, `BuyerCard`, `ValuationCard`,
    `StrategyCard`) — direct ports of the prototype sections.
  - `discovery.module.css` — the brand tokens (birch cream + copper on black), type scale,
    reveal keyframes. Ported from `page/discovery.html`.
- **Loader** (`off-market.$slug.tsx`): read `offmarket_discovery`; if present → render
  `DiscoveryDeck`; if absent → enqueue build + render the current deck (graceful fallback).
- **Keep the indexation gate** we shipped (house-only + waterfront + sale-history noindex in
  `meta()`) — unchanged; the discovery deck inherits it.
- **SSR + SEO:** the JSON is read at SSR time, so the deck's text is server-rendered for
  crawlers (no client-fetch flash). Real sale-history content keeps the page indexable.
- **Rollout behind a PostHog flag** `offmarket_discovery_v1` (existing flag pattern) — A/B the
  new scroll deck vs the current swipe deck, measured on the real problem: hero→first-card
  retention (currently −62%) and deck depth / `offmarket_qualify`.

---

## Key decisions to confirm
1. **On-demand + cache + nightly refresh** (recommended) vs precompute-all. → on-demand.
2. **Fallback = the current deck** while a discovery doc builds (recommended) vs a loading state.
3. **JSON = filled text** (React presentation-only; copy.yaml the single source) vs structured
   data (React owns copy). → filled text.
4. **Flag-gated A/B rollout** vs hard cutover. → flag-gated.

## Phases
- **P0 (engine):** `assemble.emit_json()` + `offmarket_discovery_build.py` + collection + index.
  Seed the 10 batch homes; validate JSON against the prototype.
- **P1 (React):** `DiscoveryDeck` + card components + CSS module; loader reads the doc; flag off.
- **P2 (wire + rollout):** on-demand queue + nightly `--delta` (job_run); loader fallback;
  turn the flag on for a small % and watch retention.
- **P3 (assets):** real hero aerial/photo + responsive `srcset` + lazy-load (Phase-2 `hero_image`).

## Out of scope (this port)
- The `/analyse-your-home` conditional flow (left as-is, per Will).
- Golf/bushland premium delight (research pathway dropped).
- The in-card "See why" expansion (deferred).
