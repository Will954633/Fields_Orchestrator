# /off-market V5 — Development Plan

**Status:** Draft for developer hand-over
**Author:** Ops agent (with Will)
**Date:** 2026-08-21
**Deliverable this doc describes:** a per-property off-market page ("V5") that reuses the current homepage's ladder layout and colour scheme, at a **new opt-in route**, with **v4 left live and untouched**.

---

## 0. TL;DR for the developer

V5 is **the homepage (`BrowsePage`) restructured as a per-property page.** The homepage already ships the exact "ladder" UI, the colour theme, the header, and most of the rails Will wants. V5 = fork the *page composition* + reuse the *shared primitives* (`Rail`, `RailCard`, `theme.css`, `SiteHeader`) + add a subject-property header (borrowed from v4) + 3 new/adapted rails + a downloads section.

- **Do NOT build from scratch.** ~70% already exists. See §2 for the copy-vs-scratch analysis.
- **Do NOT edit the live homepage or v4.** V5 is a new page component behind a query-param branch.
- **Route:** render `OffMarketV5` from the existing `/off-market/:slug` loader when `?v5=1` is present (mirrors the existing `?v4=0` rollback pattern). v4 stays the default. Details in §3.
- Net-new backend work is small: **one endpoint change** ("New this week" radius-expansion-to-minimum-3). Everything else has data + APIs today.
- Net-new content: **the "three valuations" explainer** (editorial, net-new), and the **market-update report** (greenfield — placeholder only for now).

---

## 1. What Will asked for (verbatim intent) → mapped to code

| # | Will's requirement | Reality in the codebase | Work |
|---|---|---|---|
| 1 | Same colour scheme + format as home page | Homepage = `BrowsePage`; theme in `src/styles/theme.css` (grass/copper/birch, dark-forced). | **Reuse** theme + `Rail`. No fork. |
| 2 | Burger on the **right**, Fields logo on the **left** (swap current) | Current `SiteHeader`: on mobile burger is **left**, logo after it; on desktop there is **no burger** (full nav). | **Swap** order + add a V5 header variant that shows the burger drawer at all breakpoints. See §4. |
| 3 | Same dropdown options as now | `MobileNav` drawer already defines the full IA (Insights / Market Intelligence / Homes for Sale / Your Home / About). | **Reuse** `MobileNav` as-is. |
| 4 | Replace "Every home read properly" opener with subject-home header (address, beds, baths… like v4) | v4 `HeroSection` already renders exactly this from the property doc. | **Reuse** v4 `HeroSection` (or a trimmed variant). See §5. |
| 5 | Ladder 1 = "Listings near you" (same as home) | Homepage rail `#rail-near`; endpoint `listings-near.mjs` exists. | **Reuse**. |
| 6 | Ladder 2 = "New this week" (new-to-market this week, **min 3**, expand radius until 3) | 7-day filter exists (`first_listed_timestamp` → `context_pill`), but **no radius expansion**. | **Build** expansion logic (backend). See §6. |
| 7 | Valuation ladder = swipeable walkthrough of the **subject** property's valuation (range, ~3 adjusted comps), explainer appended | Data exists in `valuation_data`; v4 already renders this inline (`WhichSection`, `AnswerBlock`, `ComparablesSection`→`ValuationEvidence`, `DispersionSection`). `Rail` provides the swipe. | **Reuse v4 components in a `Rail`**; the one real build is a compact comp-card variant. No new backend. See §7. |
| 8 | "Why you've probably seen three different valuations" | v4's `WhichSection` + `DispersionSection` already say this, verbatim & frozen. | **Reuse**, appended to the §7 rail — not a separate ladder. See §8. |
| 9 | Ladder = Market update report (still being built — placeholder) | No downloadable market-update report exists anywhere. | **Placeholder rail now**; greenfield later. See §9. |
| 10 | Ladder = News and Research (same as home) | Homepage rail `#rail-news` → `/news`. | **Reuse**. |
| 11 | Bottom "Your home" (leave as is) → link to **mini-site v1.5** | Homepage `#rail-yourhome` currently links to `/analyse-your-home`. | **Reuse** the rail, **re-point** its CTA to the v1.5 mini-site for this subject. See §10. |
| 12 | Below that: "My downloads" = property report (from v4) + market update report | v4 `ReportSection` + `offmarket-report-request.mjs` exist; market-update report does not. | **New Downloads section** wrapping the existing report + a "coming soon" slot. See §11. |

---

## 2. Architecture decision: copy the homepage vs build from scratch

**Recommendation: fork the *page*, reuse the *primitives*. Do not start from scratch; do not fork everything.**

### Option A — Start from scratch ❌
- Rebuilds `Rail`, `RailCard`, the header, and re-derives the theme. All of that already exists and is battle-tested (SSR crawl handling, IntersectionObserver photo deferral, scroll-snap arrows).
- Guarantees visual drift from the homepage — which directly violates requirement #1 ("same colour scheme and format").
- Highest effort, highest risk. Rejected.

### Option B — Copy the whole homepage folder into a new folder and edit ⚠️
- Fast to start, but **duplicates shared primitives** (`Rail`, `RailCard`, `SiteHeader`, theme). Two copies drift: a future homepage fix (e.g. a Rail scroll bug) won't reach V5. This is exactly the maintenance trap the Aug-2026 rebuild consolidated away.
- Acceptable only for the *page-level* file, not the shared components.

### Option C — Fork the page, import the primitives ✅ (recommended)
- **Reuse by import (no copy):** `src/components/Rail/*`, `src/components/RailCard.tsx`, `src/components/SiteFooter/*`, `src/styles/theme.css`, `src/components/MobileNav/*`, `src/types/browse.ts`. These are already generic.
- **Fork (new files):** the page composition (`BrowsePage.tsx` → new `OffMarketV5.tsx` / `pages/OffMarketPage/v5/`), because the section order, the per-property subject header, and the downloads section differ enough that prop-flagging the homepage would make it a tangle.
- **New components:** `SubjectHero` (reuse/adapt v4 `HeroSection`), `ValuationCard`, `ThreeValuationsRail`, `MarketUpdatePlaceholderRail`, `DownloadsSection`, and a `SiteHeaderV5` variant (logo-left / burger-right).
- **New/changed backend:** one endpoint (§6).

Net effect: V5 inherits every homepage look-and-feel fix automatically, and only the genuinely-new surfaces are new code.

> **Reused vs new component ledger** (build this table into the PR description):
> - **Import as-is:** `Rail`, `RailCard` (`ListingCard`/`ArticleCard`/`FactCard`/`LockedCard`), `SiteFooter`, `MobileNav`, `theme.css`, `browse.ts` types, `SubscribeModal`, `UnlockModal`/`DetailSheet` (if the near/your-home gating is kept).
> - **New:** `pages/OffMarketPage/v5/OffMarketV5.tsx`, `SubjectHero.tsx`, `ValuationCard.tsx`, `ThreeValuationsRail.tsx`, `MarketUpdatePlaceholderRail.tsx`, `DownloadsSection.tsx`, `SiteHeaderV5.tsx`.

---

## 3. Routing & how a visitor reaches V5

The live route is **`/off-market/:slug`** (hyphenated; `slug` = `url_slug`, e.g. `21-royal-links-drive-robina`). The loader in `src/routes/off-market.$slug.tsx` already picks between `OffMarketV4`, the discovery deck, and the classic teaser via a priority chain in `OffMarketRoute` (≈ lines 969–1025), gated by query params (`?v4=0` rolls back v4).

**Plan:** add a V5 branch that is **opt-in and highest-priority only when explicitly requested**, so v4 stays the untouched default:

1. In the loader, read `v5Param = url.searchParams.get("v5")`. When `v5Param === "1"`, set `ld.v5 = true` and ensure the loader still builds the full `property` payload (it already does for v4) plus the extra data V5 needs (valuation, near, new-this-week — see §12).
2. In `OffMarketRoute`, **before** the v4 check, add: `if (ld.v5 && v5Eligible(property)) return <OffMarketV5 data={ld} />;`.
3. `v5Eligible` mirrors `v4Eligible` initially (has a resolvable subject property; inside `V4_SUBURBS` = Robina / Varsity Lakes / Burleigh Waters so valuation accuracy holds).

**Why a query param, not a new URL segment:** it reuses the entire loader (property resolution, redirect guards, twin-listing dedup) with zero duplication, and matches the existing `?v4=` convention the team already uses for safe rollout. If Will later wants a shareable clean URL, add `route("off-market-home/:slug", …)` that internally sets `v5=1` — but that's a follow-up, not needed for the mockup.

> ⚠️ Keep the loader's existing redirect gates intact (for-sale/under-contract/sold → `/property/:slug`; PropRadar currently-listed → `/building/:slug`; twin-listing 301). V5 must sit *after* those, exactly where v4 sits.

---

## 4. Header (logo-left / burger-right) — `SiteHeaderV5`

Current `SiteHeader` (`src/components/SiteHeader/SiteHeader.tsx`): `.inner` is `flex; justify-content: space-between`, DOM order = **`<MobileNav/>` (burger) → `.brand` (logo) → desktop `.nav`**. Burger is `display:none` above 740px.

Will wants **logo left, burger right** (this is the conventional arrangement — his instinct is correct; the current reversed order has no documented rationale, just how it was built). Also, per requirement #3, V5 should expose the **burger drawer at all breakpoints** (Will refers to "the same dropdown options as we currently have", i.e. the `MobileNav` drawer, not the desktop inline nav).

**Build `SiteHeaderV5.tsx`** (new file; leave `SiteHeader` untouched):
- DOM/flex order: **`.brand` (logo, left) → spacer → `<MobileNav/>` (burger, right)**.
- Remove the `display:none >740px` on the burger for this variant so the drawer is the primary nav on desktop too. **Drop the desktop inline `.nav` entirely** (Will, 2026-08-21) — the burger drawer is the only nav at all breakpoints, for a cleaner "app-like" off-market surface.
- Keep the grass masthead (`--fields-grass #22382c`), the birch logo SVG (`assets/fields/fields-hero-birch.svg`), and the copper focus ring — identical tokens, so it reads as the same brand.
- `MobileNav` is reused **unchanged**; its drawer IA already matches requirement #3. If the drawer's "open from left" animation looks wrong with a right-side burger, flip its transform origin to open from the right (CSS-only change, scope it to a `data-side="right"` prop to avoid touching the homepage's usage).

**Acceptance:** on desktop and mobile, logo sits top-left, burger top-right, tapping the burger opens the existing accordion drawer with the current options.

---

## 5. Subject-property header (replaces "Every home, read properly")

Reuse v4's `HeroSection` (`src/pages/OffMarketPage/v4/HeroSection.tsx`) — it already renders exactly what Will described:
- Aerial with title boundary (`aerial_boundary_url ?? cadastral_photo_url`)
- `<h1>` street address, "{suburb}, QLD"
- Facts row: **land m², bedrooms, bathrooms, floor m²**
- "Last recorded sale: $X in {month year}"

All fields come from the loader's `property` payload (already built for v4), sourced from the `Gold_Coast` per-suburb collections via `findPropertyById`. **No client fetch.**

**Decision for the developer:** either import v4 `HeroSection` directly, or fork a lighter `SubjectHero.tsx` if V5 wants a shorter hero (Will's brief lists only address + beds/baths + "etc", so the v4 hero is a superset — safe to reuse and trim later). Recommend importing v4 `HeroSection` for the mockup to minimise new code.

---

## 6. Ladder — "New this week" (min 3, expanding radius) — the one real backend task

**What exists:** a `daysOnMarket <= 7` filter (`BrowsePage.tsx:74`, `decision-feed-v3.mjs:1494`), driven by the DB field **`first_listed_timestamp`** (string, absolute — the source of truth; the stored `days_on_market` counter is unreliable, a stored `0` means "never computed", so derive days from the timestamp). Companion fields: `first_listed_date`, `first_listed_full`.

**What's missing:** `listings-near.mjs` uses a **fixed** radius (default 5 km, cap 25 km) and returns whatever falls inside — possibly zero. There is **no "expand until ≥3" loop** anywhere.

**Build:** extend `listings-near.mjs` (or add `new-this-week.mjs`) with:
1. Filter: `listing_status:'for_sale'` **AND** `ai_analysis.status:'published'` **AND** derived-days-on-market ≤ 7 (compute from `first_listed_timestamp`, not the raw counter).
2. Anchor = the subject property's lat/lng.
3. **Radius expansion loop:** start at e.g. 3 km; if `< MIN_RESULTS` (=3), step out (3→5→8→12→20→25 km) until `≥3` fresh listings or the 25 km cap is hit.
4. Return `{ anchor, radiusKmUsed, total, listings[] }` with `distanceKm` per card, so the rail can show a "within N km" note.
5. **Zero-result honesty (Rule 7b/8 discipline):** if the cap is hit and still `<3`, return what was found plus an explicit `expandedToCapWithoutMinimum: true` flag — the rail then shows "Only N new this week within 25 km", never a silent empty rail implying nothing is happening.

Cards reuse `ListingCard` (existing). Rail `href` → `/for-sale-v3`.

> Scope note: the search only walks the ~8 `FEATURED_SUBURBS` today. For the three target suburbs that's fine; document it so nobody assumes national coverage.

---

## 7. Ladder — Subject-property valuation walkthrough (swipeable, ending with the explainer)

**Decided with Will (2026-08-21):** this rail is **not** a set of nearby-home valuations. It is a **guided, swipeable walkthrough of OUR comparable-sales valuation of the *subject* property** — a sequence of cards the user swipes through, ~3 adjusted comparables shown, and **the "why you've seen different valuations" explainer cards appended to the end of the same rail** (not a separate ladder). Will already does this inline in v4; v5 re-expresses it as a horizontal swipe rail.

### 7.1 The "swipe" mechanic — reuse `Rail`, NOT the V3 deck
Important correction from investigation: **the V3 "deck" (`DeckV3.tsx`) is not a swipe deck.** It's vertical full-viewport scroll with an `IntersectionObserver` reveal, and it is tightly bound to its route (intro/outro media loaded from `public/off-market-v3/`, service-area gating, the neon offer card, global `document.head`/`window` scripts, a full PostHog lifecycle, and literal-class-name CSS contracts). It is **not embeddable** as a rail. Do not try to reuse the deck shell.

The **homepage `Rail` component already IS a horizontal scroll-snap** — i.e. swipe-on-mobile, arrows-on-desktop — and renders all children into SSR HTML. That is the correct container for this walkthrough. So: **a `Rail` of purpose-built valuation cards**, in sequence. (What IS worth borrowing from V3 is the per-type card *copy patterns* in `CardBodyV3` — the `comparable`/`valuation` card shapes — as a reference for tone, not the shell.)

### 7.2 Card sequence (left → right in the rail)
1. **Framing card** — reuse v4's `WhichSection` copy (zero-prop static, lives in `v4/HeroSection.tsx`): *"You've probably already seen two different values for this home. So which one should you believe?… rather than give you a third unexplained number, we'll show you what the evidence actually supports."* This sets up the whole rail. Drop-in as a card.
2. **Our range card** — adapt v4's `AnswerBlock` (`v4/AnswerBlock.tsx`, `data`-only): the **range** (`$low – $high`) as the headline, with the reconciled centre as the secondary "the evidence centres around ~$X — rounded deliberately, because the width is the honest part." **Suppression is built in and must be preserved** — see 7.4.
3. **3 adjusted-comparable cards — one comp per card** (Will, 2026-08-21), each adjusted to the subject home, showing that comp's sale price, distance/recency, and its per-feature adjustments. Source of truth is `ComparablesSection` → `ValuationEvidence` (see 7.3). Show the 3 highest-weighted comps.
4. **Explainer cards (appended)** — reuse v4's `DispersionSection` (`v4/ClosingSections.tsx`, zero-prop static): *"Why three sites can give you three different values"* + the tested-dispersion finding (**$469,000** typical high-low gap, **n=512**, **73.6%**) + "so which should you believe? Look at the evidence behind it." This is the "three different valuations" explainer Will referenced — it belongs **here at the tail of this rail**, not as its own ladder. See the ⚠ frozen-copy constraint in 7.5.

### 7.3 The comparables — reuse `ComparablesSection` / `ValuationEvidence`, expect a compact-variant fork
v4's `ComparablesSection` (`v4/ComparablesSection.tsx`) is a thin `data`-only wrapper that delegates to the shipped **`ValuationEvidence`** component (`src/pages/YourHomePage/components/ValuationEvidence.tsx`, ~1,068 lines, `context="offmarket"`). Its own doc comment says *"THIS REUSES A SHIPPED COMPONENT ON PURPOSE… Do not rebuild this one."* It reads `data.evidence.comparables[]` (adjusted comps, incl. per-comp `id`, per-feature adjustment provenance, weights, verified flags) and `data.evidence.confidence.nTotal`.

⚠️ **The one real front-end cost in this rail:** `ValuationEvidence` renders a **full-width page section with a lightbox**, not a compact swipe tile. To put ~3 comps into rail cards, either (a) extend its existing `context` mechanism with a compact `context="rail"` variant, or (b) fork a slim comp-card that reuses its adjustment data model but not its full layout. **Reuse the logic/data model; do not rebuild the adjustment provenance.** Budget this as the main layout task of Phase 3.

### 7.4 Data (all exists — no new backend)
Fields verified live on `Gold_Coast.robina`, `listing_status:"for_sale"`:

| Card element | Field | Fill |
|---|---|---|
| Range low / high | `valuation_data.confidence.range.{low,high}` | 56% |
| Reconciled centre | `valuation_data.confidence.reconciled_valuation` | 100% |
| Confidence label | `valuation_data.confidence.confidence` | 100% |
| Adjusted comps | `valuation_data.adjusted_comparables[]` (`.address`, `.adjusted_price`, `.adjustments.*`) | 81% |
| Comp sales | `valuation_data.valuation_breakdown.comparable_sales[]` (`.address`, `.sale_price`, `.sale_date`, `.distance_km`) | 74% |

`AnswerBlock` reads a normalised `data.valuation` (`v.low/high/point/method/n_comps`) and `ComparablesSection` reads `data.evidence` — both are already assembled by the v4 loader path, so the `?v5=1` loader gets them for free.

### 7.5 Guardrails (correct, load-bearing — read before touching copy)
- **Suppression is METHOD-gated, not attribute-gated.** There is no `directional_only`/`waterfront` boolean these components branch on. `AnswerBlock` gates the accuracy/error-rate copy on `v.method === "engine"` (via `accuracyFor()`, which returns null otherwise), and renders the range only when `v.low/v.high` exist. Waterfront / uncalibrated suburbs (e.g. Burleigh Waters is deliberately absent from the accuracy table because adjusting makes it worse there) fall into the non-engine branch and naturally suppress the measured-error claim. **Keep these components' internal gating intact — don't re-implement suppression from a guessed flag.**
- **`DispersionSection` copy is FROZEN.** Set by Will 2026-08-10 and shipped verbatim; every figure ($469k, n=512, 73.6%) traces to `RESULT_dispersion_512.md`. **Do not paraphrase.** Reuse the component as-is.
- **Competitor naming — use the NEUTRAL variant for v5 (Will, 2026-08-21).** `DispersionSection` names competitors behind a not-tested disclaimer. For v5, render a **competitor-neutral variant**: keep the frozen mechanism copy and the tested figures ($469k / n=512 / 73.6%) verbatim, but **strip the competitor-naming footnote**. Implement as a prop/flag on the component (e.g. `nameCompetitors={false}`) rather than a copy fork, so the two variants can't drift. The named version stays behind a separate, explicitly-approved switch.
- **Editorial (CLAUDE.md §5):** the range is the headline; a single figure must not be the card's *headline* ("No single valuation in headlines" — the reconciled centre is allowed *inside* a card, as property pages already do). Never call the ±12% band a "confidence interval" — it contains the sale price ~61% of the time; use "comparable-sales range".

---

## 8. "Why you've probably seen different valuations" — folded into §7

**Decided with Will (2026-08-21): this is NOT a separate ladder.** The explainer cards are **appended to the tail of the valuation walkthrough rail (§7.2 card 4 / §7.5)**, reusing v4's existing, already-live `WhichSection` (pre-number framing) and `DispersionSection` (the quantified "why three sites disagree", $469k / n=512). No net-new copy to write — it already exists and is frozen. The only reason to revisit a *separate* data-driven version later is if Domain's own valuation gets backfilled (`domain_valuation_at_listing` is currently ~6% filled), which would let the explainer show three *actual* competing numbers for this specific home. Treat that as a future enhancement, not part of this build.

---

## 9. Ladder — Market update report (placeholder)

**No downloadable market-update report exists anywhere in the codebase** (v4 only has inline `TimingSection`/`WhatsChangedSection`). Treat as **greenfield**.

For the mockup: a `MarketUpdatePlaceholderRail.tsx` — a single "Coming soon" card styled like a real rail item, with a disabled/"Notify me" affordance. Wire nothing to a generator yet. This keeps the layout honest and shows Will the intended slot. The real report (content + PDF generation, mirroring the off-market report pipeline) is a separate scoped project.

---

## 10. Ladder — News and Research + bottom "Your home"

- **News and Research:** reuse the homepage `#rail-news` pattern verbatim — `ArticleCard`s from `loadArticleIndex()`, rail `href="/news"`. Zero new work.
- **"Your home" (bottom):** reuse `#rail-yourhome` rail as-is (address-gated `FactCard`s), **but re-point its primary CTA** from `/analyse-your-home` to the **v1.5 mini-site** for this subject property. Confirmed target (Will, 2026-08-21): **`/your-home/:slug`** — e.g. `https://fieldsestate.com.au/your-home/24-bothwell-street-robina`.
  - ⚠️ **The link MUST carry the HMAC `?k=` key** (confirmed in code, 2026-08-21). `/your-home/:slug` has no route loader; its report data is fetched client-side from `/api/v1/property-report?slug=…&k=…`, and `withReportLinkKey()` reads `k` from the current URL — a missing `k` returns **404 by design** (memory: `report_link_key_gate`), unless a device token proves prior ownership. So the CTA href is **`/your-home/${slug}?k=${key}`**.
  - The v5 SSR loader derives `key` server-side with `reportLinkKey(slug)` (HMAC-SHA256 of the slug under `REPORT_LINK_SECRET`, `netlify/functions/db.mjs`) and passes it to the rail — **exactly** the pattern v4's direct-test redirect already uses (`off-market.$slug.tsx:396–431`). Copy that. Keep the link builder a shared util so the two call sites can't diverge.

---

## 11. "My downloads" section (bottom-most)

New `DownloadsSection.tsx` below "Your home". Two items:

1. **Property Positioning Report** — the existing v4 downloadable. Reuse `ReportSection` logic / `offmarket-report-request.mjs` (`POST/GET /api/v1/offmarket-report-request?slug=…`). Most requests return `completed` immediately (8,291 covers pre-warmed). Honor `hasReport()` gate (`valuation.method === "engine"`; no PDF for declined/waterfront). **No auth/no key** — by design it collects no contact info; keep that.
2. **Market update report** — the §9 placeholder ("coming soon" / notify).

Present them as two download cards in one section. If Will wants a real "My downloads" that persists across visits, that implies identity (device token / lead token) — out of scope for the mockup; note it as a follow-up (memory: `report_ownership_device_token`).

---

## 12. Loader / data-flow summary (what the V5 loader must assemble)

The `?v5=1` branch of the existing `off-market.$slug.tsx` loader should return a payload containing:

| Data | Source | Status |
|---|---|---|
| Subject property (address/beds/baths/land/floor/aerial/last sale) | `findPropertyById(slug)` → `Gold_Coast` collections (already built for v4) | ✅ exists |
| Subject valuation (range/mid/comps) | `valuation_data` on the doc (or `valuation.mjs`) | ✅ exists |
| Listings near you | `listings-near.mjs` (`/api/v1/listings-near`) | ✅ exists |
| New this week (min 3, expanding) | **extended** `listings-near`/`new-this-week` | 🔨 §6 |
| Nearby valuations (for §7 rail) | `properties-for-sale.mjs` flattened valuation fields | ✅ exists |
| Articles (News & Research) | `loadArticleIndex()` client-side (as homepage does) | ✅ exists |
| Three-valuations copy | static editorial content (net-new) | ✍️ §8 |
| Report status | `offmarket-report-request.mjs` (client poll) | ✅ exists |

Prefer SSR loader data for the subject + rails that must be crawlable (the `Rail` renders all children into SSR HTML for PageRank — keep that property). Articles and report-status can stay client-side as they are today.

---

## 13. Section order (final page composition, top → bottom)

1. `SiteHeaderV5` (logo left, burger right, drawer at all breakpoints — no inline nav)
2. `SubjectHero` (address, beds/baths/land/floor, last sale, aerial)
3. Rail — **Listings near you**
4. Rail — **New this week** (min 3, expanding radius)
5. Rail — **Your valuation** (swipeable walkthrough of the subject: framing → range → ~3 adjusted comps → "why you've seen different valuations" explainer cards appended) — §7
6. Rail — **Market update report** (placeholder)
7. Rail — **News and Research**
8. Rail — **Your home** → `/your-home/:slug` v1.5 mini-site CTA
9. `DownloadsSection` — Property report + Market update report
10. `SiteFooter` (reused)

---

## 14. Build phases & estimate

**Phase 1 — Scaffold & route (0.5 day)**
- Add `?v5=1` branch + `v5Eligible` in `off-market.$slug.tsx`; new `pages/OffMarketPage/v5/OffMarketV5.tsx` rendering `SubjectHero` + placeholder rails. Verify it renders behind `?v5=1` without touching v4.

**Phase 2 — Header + reuse rails (1 day)**
- `SiteHeaderV5` (logo-left/burger-right, drawer everywhere). Wire Listings-near, News & Research, Your home (re-pointed), reusing homepage rails.

**Phase 3 — Valuation walkthrough rail (1.5–2 days — the biggest FE task)**
- `Rail` of valuation cards: drop in `WhichSection` + `AnswerBlock` + `DispersionSection` (reuse, preserve gating/frozen copy), and the compact ~3-comp cards — the one genuine build here is the **compact variant of `ValuationEvidence`** (§7.3: extend `context` or slim fork; reuse the adjustment data model, not the full lightbox layout). Confirm competitor-naming flag with Will before enabling (§7.5).

**Phase 4 — New-this-week backend (0.5–1 day)**
- Radius-expansion endpoint + zero-result honesty flag; wire the rail.

**Phase 5 — Downloads + placeholder (0.5 day)**
- `DownloadsSection` reusing the report request flow; market-update "coming soon".

**Phase 6 — QA (0.5 day)**
- SSR crawl check (all rail children in HTML), dark-theme parity with homepage, burger-drawer nav on mobile + desktop, valuation suppression on a non-engine/uncalibrated-suburb property (range + comps show, measured-error copy hidden), `?v5=0`/absent → v4 unaffected. Screenshot-verify per CLAUDE.md §4.

**Rough total: ~5–6 dev-days** for the mockup (the valuation-walkthrough rail is the largest piece; excludes the real market-update report generator and any Domain-valuation backfill, which are separate initiatives).

---

## 15. Decisions locked & remaining questions

**Locked with Will, 2026-08-21:**
1. ✅ **Valuation rail** = swipeable walkthrough of the **subject** property (framing → range → ~3 adjusted comps → explainer), reusing the `Rail` scroll-snap. Not nearby-home valuations. (§7)
2. ✅ **Nav** = burger drawer only, at all breakpoints; drop the inline desktop nav. (§4)
3. ✅ **"Your home" CTA** → `/your-home/:slug` v1.5 mini-site. (§10)
4. ✅ **"Three valuations" explainer** = reuse v4's existing `WhichSection` + `DispersionSection`, appended to the tail of the valuation rail. Not a separate ladder, not net-new copy. (§7, §8)

**Also locked, 2026-08-21:**
5. ✅ **Competitor naming** — use a **competitor-neutral variant** of `DispersionSection` for v5 (keep the frozen figures/mechanism copy; strip the competitor-naming footnote). The named-competitor version stays a separate, later, explicitly-approved decision. (§7.5)
6. ✅ **Comps** — **one comparable per card** (3 cards), matching the swipe-through feel. (§7.2)
7. ✅ **URL** — `?v5=1` on `/off-market/:slug` is sufficient; a shareable `/off-market-home/:slug` is a possible later follow-up, not in scope. (§3)

**B — resolved (confirmed in code):** `/your-home/:slug` has **no route loader**; the report *data* is fetched client-side from `/api/v1/property-report?slug=…&k=…`, and a missing `k` returns **404 by design** (unless a device token proves prior ownership). So the v5 "Your home" link **must append the HMAC `?k=`**. v5's SSR loader derives it server-side via `reportLinkKey()` (`netlify/functions/db.mjs`, `REPORT_LINK_SECRET`) and builds `/your-home/${slug}?k=${key}` — the same thing v4's direct-test redirect already does (`off-market.$slug.tsx:396–431`). No open items remain.

---

## 16. Guardrails (non-negotiables baked into the plan)

- **Do not edit the live homepage or v4.** V5 is additive; v4 remains the default.
- **Reuse `theme.css` tokens** (grass/copper/birch) — never hardcode colours — so V5 stays visually identical to the homepage.
- **Valuation display rules** (§7): honor waterfront/directional suppression; no single figure in a headline; never call the ±12% band a confidence interval.
- **Editorial rules** (§8): the three-valuations copy is public-facing — data-only, no advice, cite method + limits.
- **SSR crawlability:** keep `Rail`'s "all children in SSR HTML" behaviour for the subject + rails.
- **Honesty on empty rails** (§6): expanded-to-cap-without-minimum must be surfaced, not silently empty.
