# House Mini-Site — Development Plan

**Version:** 1.0 · **Date:** 2026-05-14 · **Status:** Build-ready engineering brief
**Parent docs:** [Design.md](Design.md) · [Content-Plan.md](Content-Plan.md) · [README.md](README.md) (v0.3 state)

---

## 1. Scope

This document is the engineering counterpart to [Design.md](Design.md) and [Content-Plan.md](Content-Plan.md). It specifies:

1. The architecture (where each piece lives, how data flows).
2. The data model (`system_monitor.property_reports` extended schema).
3. The components (what's built, what's new).
4. The APIs (Netlify functions, refresh scripts).
5. The personalisation pipeline (slot-resolution engine).
6. The state-transition machinery (under-review → final → living).
7. The build sequence (sprint plan with deliverables).
8. Telemetry and success metrics.

This document assumes the v0.3 state described in [README.md](README.md). Everything below is incremental.

---

## 2. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          PUBLIC WEBSITE (Netlify)                          │
│                                                                            │
│  /seller-questions/             [Phase 2 — Fears Library hub]              │
│  /seller-questions/<slug>       [Phase 2 — 15 pages, SEO-indexed]          │
│  /analyse-your-home             [v0 — exists, needs form-submit wiring]    │
│  /your-home/<slug>              [v0.3 — needs new tabs + slot resolver]    │
└────────────────────┬───────────────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────────┐    ┌────────────────────────────────────────────────────┐
│ Netlify Functions │    │              ORCHESTRATOR VM                       │
│                  │    │                                                    │
│  property-       │    │  refresh_property_reports.py    [cron, nightly]    │
│  report-         │◄───┤  resolve_property_report.py     [on-demand]        │
│  activity.mjs    │    │  build_property_report.py       [on form-submit]   │
│                  │    │  trigger_print_appraisal.py     [on state→final]   │
│  property-       │    │                                                    │
│  report.mjs      │◄───┤                                                    │
│  [NEW — full doc]│    └────────────────────────────────────────────────────┘
│                  │                          │
│  analyse-your-   │                          ▼
│  home-submit.mjs │            ┌─────────────────────────────────┐
│  [NEW — gate]    │◄───────────┤      Azure Cosmos DB             │
└──────────────────┘            │                                  │
                                │  system_monitor.property_reports │
                                │  Gold_Coast.<suburb>             │
                                │  property_data.*                 │
                                │  precomputed_market_charts       │
                                │  precomputed_indexed_prices      │
                                └──────────────────────────────────┘
```

**Key principles:**
- **All slot resolution server-side.** No `{slot_name}` ever lands in browser HTML unfilled.
- **Frontend is stateless.** It reads one document and renders. No business logic in React.
- **DB is the single source of truth.** TS fixtures are fallback only.
- **Print is downstream.** Print appraisal generation triggers off DB state, never frontend.

---

## 3. Data Model

### 3.1 The `system_monitor.property_reports` document

The v0.3 schema is minimal. Below is the full schema needed for the design described in [Design.md](Design.md). The new fields are marked `[NEW]`.

```javascript
{
  // ─── Identity ──────────────────────────────────────────────
  _id: ObjectId,
  slug: "13-terrace-court-merrimac",       // primary lookup key
  address: "13 Terrace Court, Merrimac QLD 4226",  // [NEW]
  suburb_canonical: "merrimac",            // [NEW] for DB joins
  postcode: "4226",                        // [NEW]
  lat: -28.0612, lng: 153.3851,            // [NEW] for map + isochrones

  // ─── State machine ─────────────────────────────────────────
  state: "under_review" | "final" | "living",   // [NEW] — currently inferred
  state_transitioned_at: {                       // [NEW]
    stub: ISODate,
    under_review: ISODate,
    final: ISODate,
    living: ISODate
  },
  print_appraisal: {                              // [NEW]
    queued_at: ISODate,
    dispatched_at: ISODate,
    delivered_at: ISODate,
    tracking_ref: string
  },

  // ─── Owner ─────────────────────────────────────────────────
  // Contact fields are ALL optional. The address gate captures nothing else.
  // email/phone are only present if the seller voluntarily provides them
  // via in-mini-site capture (e.g. "remind me when valuation is ready").
  owner: {                                  // [NEW]
    email: string | null,                   // optional — voluntary, post-submit
    phone: string | null,                   // optional — voluntary
    contact_captured_at: ISODate | null,    // when email/phone provided
    contact_capture_source: "reminder_optin" | "print_delivery_sms" | null,
    device_token: string,                   // localStorage-issued, anon
    first_visit_at: ISODate,
    last_visit_at: ISODate,
    visit_count: int,
    avatar_inferred: "stressed_upgrader" | "reluctant_seller" | "savvy_investor"
  },

  // ─── Property facts ────────────────────────────────────────
  property: {                               // [NEW] — denormalised for render
    bed: int, bath: int, car: int,
    land_area_sqm: int,
    internal_area_sqm: int,
    property_type: "house" | "unit" | "townhouse",
    year_built: int | null,
    photos: [{ url, role: "hero" | "kitchen" | "satellite" | ... }],
    cadastral: { lot, plan, council }
  },

  // ─── Valuation ─────────────────────────────────────────────
  valuation: {
    model_range: { low, high },             // CatBoost ballpark (always)
    reconciled: {                            // only in final state
      listing_price_range: { low, high },
      target_sale_price_range: { low, high },
      confidence_level: "High" | "Medium" | "Low",
      confidence_interval_90: { low, high },
      comps: [
        {
          address, sale_date, sale_price,
          adjustments: [{ name, direction, amount, rationale }],
          adjusted_value,
          weight,
          source_link
        }
      ],
      methodology_notes: string,
      reviewed_by: "mac" | "will",
      reviewed_at: ISODate
    }
  },

  // ─── Personalisation slot cache ────────────────────────────
  slots: {                                  // [NEW] — pre-resolved at refresh time
    n_competitors: int,
    n_active_agents: int,
    n_specialists: int,
    best_comp: { address, price, date, agent },
    dom_sell: int, dom_buy: int,
    next_suburb: string,
    investor_pct: float, yield_pct: float,
    growth_pct: float, years: int, est_purchase_year: int,
    auction_pct: float, clearance_rate: float,
    fsbo_range: { low, high }, commission_range: { low, high }, crossover: int,
    peak_months: [string], next_window_start: ISODate, next_window_end: ISODate,
    target_inspections: int, target_enquiries: int, target_offers: int,
    // ... any slot used in Content-Plan.md §5
    rea_share: float, domain_share: float, fb_share: float, google_share: float,
    reach_estimate: int,
    condition_grade: "A" | "B" | "C" | "D",
    top_three_prep_opportunities: [string],
    data_pull_date: ISODate
  },

  // ─── Activity feed ─────────────────────────────────────────
  activity: [
    {
      date: ISODate,
      kind: "stub_created" | "comp_selected" | "new_listing" | "sold" |
            "market_state" | "valuation_published" | "print_queued" |
            "print_dispatched" | "print_delivered" | "article" | ...,
      headline: string,
      detail: string,
      source: { collection, id } | null
    }
  ],
  activity_refreshed_at: ISODate,

  // ─── Scarcity ──────────────────────────────────────────────
  scarcity: {                               // [NEW] — for ShareMoment + Home tab
    headline: "One of only four homes in Merrimac with...",
    feature_combination: [string],
    cohort_size_6mo: int,
    cohort_size_12mo: int,
    cohort_size_total: int,
    median_premium_pct: float
  },

  // ─── Market context ────────────────────────────────────────
  market: {                                 // [NEW] — denormalised per refresh
    fci: float,
    median_dom: int,
    active_listings: int,
    wage_growth_yoy: float,
    indexed_price_subject_suburb: [{ month, value }],   // 60-month series
    indexed_price_gc_avg: [{ month, value }],
    competitor_listings: [
      { address, price, bed, bath, days_on_market, photo, link }
    ]
  },

  // ─── Buyers (S02 mapping) ──────────────────────────────────
  buyers: {                                 // [NEW]
    avatars: [
      { name, archetype, why_they_pay_premium, where_they_live_now }
    ]
  },

  // ─── Positioning (S05 mapping) ─────────────────────────────
  positioning: {                            // [NEW]
    editorial_prose: string,  // Opus-generated, ~200 words
    photography_plan: [string],
    forbidden_words_audit: { passed: bool, last_run: ISODate }
  },

  // ─── Process content (the 10 fear sections) ────────────────
  process_sections_order: [                 // [NEW] — driven by avatar
    "settlement", "sell_first_buy_first", "tax", "tenant",
    "cost_of_sale", "property_prep", "contract_terms",
    "fsbo", "agent_scorecard", "finance_fall_through"
  ],

  // ─── Audit trail ───────────────────────────────────────────
  created_at: ISODate,
  updated_at: ISODate,
  schema_version: 2                          // bump on each schema change
}
```

**Indexes:**
- `{ slug: 1 }` (unique) — primary lookup
- `{ "owner.device_token": 1 }` — for anonymous return-visit detection
- `{ "owner.email": 1 }` (sparse) — only meaningful for the subset who voluntarily provided one
- `{ state: 1, "owner.last_visit_at": -1 }` — for ops queue ordering
- `{ "print_appraisal.dispatched_at": -1 }` — for delivery tracking

---

### 3.2 Why slots cache server-side

Slot values come from at least four DB collections (`Gold_Coast.<suburb>`, `precomputed_market_charts`, `precomputed_indexed_prices`, `property_reports`). Doing those queries on each page load is wasteful and slow.

The strategy: **resolve once at refresh time, cache in `property_reports.slots`, re-resolve nightly via `refresh_property_reports.py`.** The Netlify function reads one document. Page renders in <100ms.

---

## 4. Components

### 4.1 Existing (v0.3, no changes)

| Component | File | Status |
|---|---|---|
| `YourHomePage` | `pages/YourHomePage/YourHomePage.tsx` | Shell — extend tab list |
| `HeroSection` | `components/HeroSection.tsx` | Reuse |
| `ActivityFeed` | `components/ActivityFeed.tsx` | Reuse |
| `ShareMoment` | `components/ShareMoment.tsx` | Reuse |
| `YourHomeTab` | `tabs/YourHomeTab.tsx` | Reuse |
| `ValuationTab` | `tabs/ValuationTab.tsx` | Reuse — both states already supported |
| `MarketTab` | `tabs/MarketTab.tsx` | Refactor — split into Market + Buyers + Positioning |
| `NextTab` | `tabs/NextTab.tsx` | Extend — add walk-away + print delivery card |

### 4.2 New (Phase 1-3)

| Component | File | Phase | Purpose |
|---|---|---|---|
| `BuyersTab` | `tabs/BuyersTab.tsx` | 2 | S02 mapping — avatars + why-they-pay |
| `PositioningTab` | `tabs/PositioningTab.tsx` | 2 | S05 mapping — editorial prose + photography + 4 levers |
| `ProcessTab` | `tabs/ProcessTab.tsx` | 1 | Container for the 10 fear sections |
| `FearSection` | `components/FearSection.tsx` | 1 | Reusable thesis/applied-to-your-home block |
| `CompetitorMap` | `components/CompetitorMap.tsx` | 3 | Mapbox interactive — currently a JPG |
| `WalkAwayCard` | `components/WalkAwayCard.tsx` | 1 | Front-of-Next-tab promise card |
| `PrintDeliveryStatusCard` | `components/PrintDeliveryStatusCard.tsx` | 1 | Countdown + SMS opt-in |
| `FamilyShareButton` | `components/FamilyShareButton.tsx` | 2 | Scroll-triggered share-to-partner prompt |
| `CitationStrip` | `components/CitationStrip.tsx` | 1 | Reusable foot-of-section attribution block |
| `ChartImage` | `components/ChartImage.tsx` | 1 | Lazy-loaded book chart with caption |
| `CostOfSaleCalculator` | `components/CostOfSaleCalculator.tsx` | 1 | Interactive line-item for fear #10 |
| `MarketStateGrid` | `components/MarketStateGrid.tsx` | 1 | The 4-up tile grid (FCI / DOM / stock / wage) |

### 4.3 `FearSection` component contract

The single most-reused component in the new tab. Spec:

```typescript
interface FearSectionProps {
  id: string;                       // anchor + URL hash
  fearNumber: number;               // 1-15
  headline: string;
  subhead: string;
  thesis: {
    body: string;                   // markdown, server-rendered
    chartId?: string;               // optional — loads from book chart library
  };
  applied: {
    body: string;                   // markdown with slots already resolved
    statBlocks?: StatBlock[];       // optional small-number callouts
  };
  citation: {
    sources: string[];
    lastReviewed: string;           // ISO date
  };
  cta?: {
    label: string;
    href: string;
  };
}
```

Renders as the universal pattern from [Content-Plan.md §2](Content-Plan.md). Always two columns on desktop, stacked on mobile. Citation strip always at the foot.

---

## 5. APIs

### 5.1 Netlify functions

| Function | Method | Path | Purpose | Status |
|---|---|---|---|---|
| `analyse-your-home-submit` | POST | `/api/v1/analyse-your-home` | Accept address + email, geocode, create stub doc, return slug | **NEW** |
| `property-report` | GET | `/api/v1/property-report?slug=...` | Return full report doc (single fetch for whole page) | **NEW** |
| `property-report-activity` | GET | `/api/v1/property-report-activity?slug=...` | Return activity feed only (lighter) | Exists (v0.3) |
| `property-report-event` | POST | `/api/v1/property-report-event` | Receive analytics event (visit, scroll-depth, share-click) | **NEW** |
| `print-status-subscribe` | POST | `/api/v1/print-status-subscribe` | SMS opt-in for delivery notification | **NEW** |

### 5.2 `analyse-your-home-submit` contract

**Single-field gate. Address is the only required input.** No email, no phone, no name.

```typescript
POST /api/v1/analyse-your-home
Content-Type: application/json

Request:
{
  address: string,            // REQUIRED — the only field that gates
  source?: string             // optional — FB ad / organic / referral / utm tags
}

Response (200):
{
  slug: string,
  redirect_url: "/your-home/13-terrace-court-merrimac",
  state: "under_review",
  eta_final_by: ISODate,      // address + 3 business days
  device_token: string        // issued by server, persisted in localStorage
}

Response (400):
{
  error: "address_not_geocodable" | "outside_service_area"
}

Response (409):
{
  error: "slug_already_exists",
  existing_slug: string,
  redirect_url: string
}
```

**Important behaviours:**
- The function **must complete in < 5 seconds.** Geocode, DB write, return. No blocking on slot resolution.
- Slot resolution kicks off **asynchronously** via a queued message to `build_property_report.py`.
- Service area validation: postcode in {4220, 4226, 4227} for v1. Reject elsewhere with friendly message.
- Duplicate check by canonicalised address — different submissions of "13 Terrace Court" and "13 Terrace Ct" resolve to same slug. Re-submission on the same device returns the existing slug.
- `device_token` is an opaque UUID issued server-side and stored in `localStorage` by the frontend. It is the only way to recognise a returning visitor — there is no email login.

### 5.2.1 `property-report-contact-capture` contract

A separate endpoint for **voluntary** contact provision *after* the mini-site exists. Triggered by in-page CTAs (`#next` reminder card, print-delivery SMS opt-in, etc.). Never required.

```typescript
POST /api/v1/property-report-contact-capture
Content-Type: application/json

Request:
{
  slug: string,               // required
  device_token: string,       // required, validated against doc
  email?: string,             // either email or phone required
  phone?: string,
  source: "reminder_optin" | "print_delivery_sms" | "family_share"
}

Response (200): { success: true }
Response (403): { error: "device_token_mismatch" }
```

This is the **only** path by which `owner.email` or `owner.phone` ever populate. The address gate never collects them.

### 5.3 `property-report` contract

```typescript
GET /api/v1/property-report?slug=13-terrace-court-merrimac

Response (200):
{
  ...entire property_reports doc, stripped of internal fields
}

Response (404):
{
  error: "not_found"
}
```

Single fetch. Page loads from this. Total payload target: <50KB compressed.

---

## 6. Personalisation Pipeline

### 6.1 Slot resolver

A new Python module — `scripts/property_reports/slot_resolver.py` — runs the slot-resolution queries.

```python
class SlotResolver:
    def __init__(self, property_doc):
        self.property = property_doc
        self.db = get_gold_coast_db()
        self.market_db = get_market_db()

    def resolve_all(self) -> dict:
        return {
            'n_competitors': self._count_competitors(),
            'n_active_agents': self._count_active_agents(),
            'best_comp': self._select_best_comp(),
            'dom_sell': self._median_dom_in_bracket(),
            'growth_pct': self._suburb_growth_pct(),
            # ... one method per slot
        }

    def _count_competitors(self):
        return self.db[self.property['suburb_canonical']].count_documents({
            'listing_status': 'for_sale',
            'bedrooms': self.property['bed'],
            'price.value': {
                '$gte': self.property['valuation']['model_range']['low'] * 0.85,
                '$lte': self.property['valuation']['model_range']['high'] * 1.15
            }
        })

    # ... etc.
```

**Critical rules:**
- Every query uses `listing_status` filter (per CLAUDE.md — Cosmos query rule).
- Cache `list_collection_names()` at init (per memory file).
- Use `cosmos_retry()` wrapper for write-heavy operations.
- If a slot cannot resolve, store `None` — never an empty string. Frontend hides blocks with `None` slots.

### 6.2 Avatar inference

A small rules engine. Inputs: property type, price tier, listing history, recent rental activity. Output: one of three avatars. Output drives `process_sections_order` and the section emphasis in the `#process` tab.

```python
def infer_avatar(property_doc, market_context):
    is_likely_investor = (
        property_doc['property']['property_type'] == 'unit' or
        property_doc.get('rental_history', {}).get('was_recently_rented') or
        property_doc.get('cadastral', {}).get('multi_let_signal')
    )
    is_likely_distressed = (
        property_doc.get('listing_status_history', {}).get('agent_churn', 0) > 1 or
        property_doc.get('days_since_first_listed', 0) > 90 or
        property_doc.get('price_history', {}).get('reductions', 0) > 0
    )
    is_likely_upgrader = (
        property_doc['property']['bed'] >= 4 and
        property_doc['property']['property_type'] == 'house' and
        property_doc['suburb_canonical'] in ('robina', 'burleigh_waters', 'varsity_lakes')
    )

    if is_likely_investor:
        return 'savvy_investor'
    if is_likely_distressed:
        return 'reluctant_seller'
    if is_likely_upgrader:
        return 'stressed_upgrader'
    return 'stressed_upgrader'  # default
```

The avatar inference is **soft**: every section is still present in the mini-site. The avatar only changes *order* and *prominence*, not what content exists.

### 6.3 Slot substitution

Server-side, at refresh time. The pattern:

```python
def substitute(template: str, slots: dict) -> str:
    """Replace {slot_name} with slot value. Hide block if any slot resolves to None."""
    if any(slots.get(name) is None
           for name in extract_slots(template)):
        return None  # signal to frontend to hide
    return template.format(**slots)
```

Slot-substituted strings are stored in `property_reports.process_sections[i].applied.body` (already-rendered) so the frontend just reads and displays.

---

## 7. State Transitions

### 7.1 `under_review` → `final`

Triggered by Mac (or Will) marking the valuation reviewed. Mechanism:

1. New ops dashboard tab: **Property Reports Queue**. Shows all reports in `under_review` state, sorted by `state_transitioned_at.under_review` desc.
2. Each row has a "Review" button → opens valuation editor.
3. Editor allows: adjusting comps, setting listing price + target sale price range, adding methodology notes, signing off.
4. On sign-off:
   - `state` → `"final"`
   - `valuation.reconciled` populated
   - `print_appraisal.queued_at` set to now
   - Activity feed prepended with "Valuation finalised — printed copy goes to press today"
   - **If `owner.email` was voluntarily captured:** email notification sent
   - **Otherwise:** no digital notification. The print arrival is the notification. The activity-feed item is visible on next visit.

### 7.2 `final` → `living`

Automatic, triggered by `print_appraisal.delivered_at`. Living state is the default for any report past delivery. No content change — only telemetry classifications differ.

### 7.3 Print appraisal trigger

```python
# scripts/property_reports/trigger_print_appraisal.py
# Runs when state transitions to "final"
def trigger_print(slug):
    report = db.property_reports.find_one({'slug': slug})
    pdf_path = generate_pdf(report)  # uses existing V4 print pipeline
    queue_courier(pdf_path, report['address'])
    db.property_reports.update_one(
        {'slug': slug},
        {'$set': {'print_appraisal.queued_at': now()}}
    )
```

The PDF generation reuses the V4 InDesign template (or HTML print template) — same content as the mini-site, just laid out for print. Both editions are *rendered from the same `property_reports` doc*.

---

## 8. Build Sequence

### Phase 0 — Wire the funnel (Week 1, 3-4 days)

**Single most important deliverable.** Without this nothing else works.

| Task | Files | Effort |
|---|---|---|
| Strip `AnalyseYourHomePage.tsx` to single-field (address only) | `01_Website/src/pages/AnalyseYourHomePage/` | 0.25 day |
| Create `analyse-your-home-submit.mjs` Netlify function (address-only contract) | `netlify/functions/analyse-your-home-submit.mjs` | 1 day |
| Wire the form to call it + handle redirect + persist `device_token` to localStorage | `01_Website/src/pages/AnalyseYourHomePage/` | 0.5 day |
| Add geocoding step (Mapbox forward geocode) | within Netlify function | 0.25 day |
| Create stub doc + slug generation logic + device_token issuance | within Netlify function | 0.5 day |
| Queue `build_property_report.py` job | new pub/sub or DB-poll pattern | 1 day |
| Add `Property Reports Queue` to `/ops` dashboard | new monitor tab | 0.75 day |

Acceptance: address submission → redirect to `/your-home/<slug>` showing v0.3 fixture content with the seller's submitted address inserted. Stub doc visible in `system_monitor.property_reports`. `device_token` issued and persisted.

### Phase 1 — Process tab + fear sections (Week 2-3, 7-9 days)

| Task | Files | Effort |
|---|---|---|
| `FearSection.tsx` component | new | 0.5 day |
| `CitationStrip.tsx` component | new | 0.25 day |
| `ChartImage.tsx` component (lazy-load + caption) | new | 0.25 day |
| `ProcessTab.tsx` container | new | 0.5 day |
| Wire `homeFixture.ts` to support `process_sections[]` array | extend | 0.5 day |
| Author 10 fear-section content blocks (per [Content-Plan.md](Content-Plan.md)) | DB seed + content | 3-4 days |
| `CostOfSaleCalculator.tsx` (interactive) | new | 1 day |
| Avatar inference module | `scripts/property_reports/avatar.py` | 0.5 day |
| Section ordering by avatar | wire into Process tab | 0.25 day |
| Add `#process` tab nav | `YourHomePage.tsx` | 0.25 day |
| Editorial audit pass against forbidden-words list | manual + automated | 0.5 day |

Acceptance: `/your-home/13-terrace-court-merrimac#process` renders 10 fear sections with thesis/applied/citation pattern, slot-substituted, avatar-ordered.

### Phase 2 — Buyers + Positioning tabs (Week 3-4, 4-5 days)

| Task | Files | Effort |
|---|---|---|
| Split current `MarketTab.tsx` into 3 tabs | refactor | 1 day |
| `BuyersTab.tsx` — persona cards | new | 1 day |
| `PositioningTab.tsx` — contrast + 4 levers + editorial prose | new | 1 day |
| Port Opus editorial prose pipeline to mini-site context | `scripts/property_reports/positioning_prose.py` | 1 day |
| `FamilyShareButton.tsx` + scroll-trigger | new | 0.5 day |
| OG image generation for share moments | Netlify function | 0.5 day |

Acceptance: `#buyers` and `#positioning` tabs render with per-suburb persona library + per-property editorial prose. Family share button fires at 40% scroll depth.

### Phase 3 — Slot resolver + DB refresh upgrades (Week 4-5, 3-4 days)

| Task | Files | Effort |
|---|---|---|
| `slot_resolver.py` with one method per slot | `scripts/property_reports/slot_resolver.py` | 2 days |
| Extend `refresh_property_reports.py` to call slot resolver | extend | 0.5 day |
| Migrate schema to v2 (add new fields) | DB migration script | 0.5 day |
| Backfill existing fixture doc to new schema | data fix | 0.25 day |
| `property-report.mjs` Netlify function | new | 0.5 day |
| Migrate `YourHomePage` to fetch full doc from new endpoint | refactor | 0.5 day |

Acceptance: removing `homeFixture.ts` would not break the page — all data flows from DB.

### Phase 4 — Print pipeline + state machine (Week 5-6, 4-5 days)

| Task | Files | Effort |
|---|---|---|
| Property Reports Queue editor in `/ops` | new monitor handler | 1.5 days |
| Valuation editor UI (Mac/Will-facing) | new ops page | 1.5 days |
| State transition machinery | extend orchestrator | 0.5 day |
| `trigger_print_appraisal.py` | new | 0.5 day |
| Print HTML → PDF generation reusing V4 template | extend existing book-PDF pipeline | 1 day |
| `property-report-contact-capture.mjs` Netlify function | new | 0.5 day |
| In-mini-site voluntary contact CTAs (reminder card + SMS opt-in) | new components | 0.5 day |
| Conditional email flow on state transitions (only if email present) | extend `scripts/fields-email.py` | 0.5 day |
| Day-1 postcard generation + dispatch (optional, recommended) | new — uses address | 0.75 day |
| `PrintDeliveryStatusCard.tsx` + voluntary SMS opt-in | new | 0.5 day |

Acceptance: Mac can review a property in `/ops`, sign off, and the seller receives an email + the print PDF gets queued.

### Phase 5 — Interactive map + living dashboard polish (Week 6-7, 3-4 days)

| Task | Files | Effort |
|---|---|---|
| `CompetitorMap.tsx` with Mapbox | new | 1.5 days |
| Map data layer endpoint | extend `property-report.mjs` | 0.5 day |
| Return-visit detection + welcome variation | session token + cookies | 0.5 day |
| `WalkAwayCard.tsx` at top of `#next` | new | 0.25 day |
| Living-dashboard activity item generators (nightly) | extend `refresh_property_reports.py` | 1 day |

Acceptance: a seller visiting their report on day 2 sees a different welcome card than day 1, the competitor map is interactive, and the activity feed has gained 1-2 fresh items overnight.

### Phase 6 — Telemetry + ops dashboard (Week 7-8, 2-3 days)

| Task | Files | Effort |
|---|---|---|
| `property-report-event.mjs` for analytics ingest | new | 0.5 day |
| PostHog event taxonomy | wire up | 0.5 day |
| Funnel dashboard on `/ops` (events from §10 below) | new monitor tab | 1.5 days |

Acceptance: every event from §10 fires correctly and is visible on `/ops`.

**Total estimated effort: ~28-35 days of work** across 7-8 weeks. Faster if Will is full-time on it; slower with concurrent fires.

---

## 9. Editorial Compliance Pipeline

Every block of new content must pass through:

```
1. Forbidden-words filter (regex against the project forbidden-word list)
2. Number-format linter (no rounded valuations in headlines, no "$1.3M" style)
3. Citation check (every claim has a {source}; if not, block fails)
4. Advice/prediction linter (matches against "you should", "will" + future tense)
5. Value-framing check (subjective; manual pass during Phase 1)
```

A simple Python module — `scripts/property_reports/editorial_audit.py` — handles 1-4 automatically. The audit runs on every content insert/update. Failed audits are written to `system_monitor.property_reports_audit_log` for review.

---

## 10. Telemetry (PostHog events)

All events route through PostHog (per project standards).

| Event | Trigger | Properties |
|---|---|---|
| `fears_library_view` | `/seller-questions/<slug>` view | `fear_slug`, `referrer_source` |
| `analyse_your_home_view` | `/analyse-your-home` view | `referrer_fear`, `device_type` |
| `analyse_your_home_submit` | Address-only form submit | `suburb`, `referrer_fear`, `time_to_submit` |
| `microsite_first_session` | First visit to `/your-home/<slug>` | `slug`, `state`, `device_type`, `device_token` |
| `microsite_tab_view` | Tab change | `slug`, `tab`, `time_on_previous_tab` |
| `microsite_fear_section_view` | Scroll past fear section threshold | `slug`, `fear_id`, `viewport_dwell_ms` |
| `microsite_share_click` | Share button | `slug`, `share_target`, `card_type` |
| `microsite_return_session` | Return visit (matched via `device_token`) | `slug`, `visit_count`, `days_since_first` |
| `contact_captured` | Voluntary email/phone provided in mini-site | `slug`, `source`, `field` |
| `valuation_final_published` | Mac signs off | `slug`, `time_to_review_hours` |
| `print_appraisal_queued` | Trigger | `slug` |
| `print_appraisal_dispatched` | Courier confirmation | `slug`, `delivery_eta` |
| `print_appraisal_delivered` | Manual or courier confirmation | `slug` |
| `consultation_booked` | Calendar booking | `slug`, `time_since_first_visit_days` |
| `listing_instructed` | Listing system event | `slug`, `time_since_first_visit_days`, `commission_estimate` |

**Funnel report (on `/ops`):**

```
analyse_your_home_view → submit (target: 8%)
submit → microsite_first_session (target: 95%)
first_session → valuation_final_published (target: 100%, time: <72h)
final_published → print_appraisal_dispatched (target: 100%, time: <24h)
print_delivered → consultation_booked (target: 25%, time: <30d)
consultation → listing_instructed (target: 60%, time: <30d)
```

Track these weekly. Adjust copy, page structure, ad creative based on which step leaks.

---

## 11. Performance Targets

| Metric | Target | Notes |
|---|---|---|
| First Contentful Paint (mini-site) | < 1.5s on 4G | Critical — mobile-first |
| Time-to-Interactive | < 3s on 4G | |
| `/api/v1/property-report` response | < 400ms p95 | DB read of one doc, cached |
| `analyse-your-home-submit` response | < 5s p99 | Geocode + DB write |
| Lighthouse (mobile) | ≥ 90 across all four | We currently score well on similar pages |
| Image weight (per page) | < 2MB total | Hero + below-fold lazy-loaded |

---

## 12. Risks & Open Questions

### Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Slot resolver fails on edge-case property | Med | Low (block hides) | Default `None` handling at every slot |
| Mac review queue grows faster than capacity | Med | Med | Hard cap on weekly submissions; explicit waitlist UI |
| Print PDF generation diverges from web version | Low | High (brand) | Single source of truth: both render from `property_reports` doc |
| Cosmos DB RU exhaustion during peak | Low | Med | `cosmos_retry()` everywhere, slot cache pre-resolves |
| Editorial slip — forbidden word ships to a live mini-site | Med | High | Automated audit on every insert; manual sample audit weekly |
| FB ad → submit conversion lower than target | Med | Med | A/B test landing fear messaging; iterate ad copy. Note: address-only gate should *raise* submit rate vs typical multi-field forms |
| Print fulfilment vendor lead time blows day-5 promise | Med | High | Decide print partner before Phase 4; have backup |
| Seller submits address, never returns to mini-site before print arrives | High | Low | Print delivery IS the re-engagement event. Day-1 postcard with URL as a secondary nudge. We accept this — the printed report does the work regardless of mini-site visits |
| Seller submits address, prints arrives, no way to follow up digitally | Med | Med | Voluntary email/phone capture inside mini-site + at print delivery (QR code on print → SMS opt-in). Acceptable: we earn the email by being worth contacting |
| Seller loses URL and can't find report again | Med | Low | Bookmark prompt on first visit + URL printed on Day-1 postcard + URL printed on physical appraisal. Three independent recovery channels |

### Open Questions (engineering)

1. **Print PDF pipeline** — extend existing book-PDF pipeline (matplotlib + Jinja + WeasyPrint) or commission InDesign templates per the V4 print spec? My recommendation: HTML/CSS print template now (fast), InDesign later if quality demands it.
2. **Geocoding provider** — Mapbox vs Google. Mapbox already used in some Fields work, simpler licensing. Recommend Mapbox.
3. **Slug collision strategy** — duplicate addresses (e.g. two "12 Main Street" cases in different sub-divisions) — append a short hash. Acceptable trade-off in URL aesthetics for uniqueness.
4. **State `living` vs `final`** — does the distinction matter to the UI, or only to telemetry? My recommendation: telemetry-only. UI shows same content past day 3.
5. **Schema version bumps** — do we run forward-migrations on every refresh, or block reads until manually migrated? My recommendation: forward-migrate at read time, log every migration.
6. **Auth on `/your-home/<slug>`** — is the URL truly secret, or does it require auth? My recommendation: URL-is-the-key (no auth) but `noindex,nofollow` + send only via email — same model as Calendly.

---

## 13. Definition of Done (per phase)

A phase is complete when:

- All listed tasks are deployed to production (Netlify + Cosmos).
- All editorial-audit checks pass for new content.
- Telemetry events from §10 are firing correctly.
- A walk-through with Will produces no surprises.
- Documentation in [Design.md](Design.md), [Content-Plan.md](Content-Plan.md), and this file matches the deployed state.

---

## 14. The Build-Order Decision

If forced to ship only **one phase**, ship Phase 0. The funnel is the unlock.

If forced to ship **two phases**, add Phase 1. The `#process` tab is the new value the site delivers that v0.3 does not.

If forced to ship **three phases**, add Phase 4. Without state transitions and print delivery, the engine has no closer.

Everything beyond Phase 4 compounds returns but is not load-bearing.

---

## 15. Next Action

1. Will reviews [Design.md](Design.md), [Content-Plan.md](Content-Plan.md), and this file. Flags anything wrong.
2. Will decides on the print fulfilment partner (open question #1 in Phase 4).
3. Engineering begins Phase 0.

That's the only critical path. Everything else can be reordered.

---

*Filed: `11_House_Mini_Site/Development-Plan.md` · Owner: Will Simpson · Updated 2026-05-14*
