# INCIDENT — Live site publishes adverse pricing verdicts on 25 agencies' listings

**Found:** 2026-08-20, while preparing the 93 Burleigh Street buyer-acquisition campaign
**Status:** 🔴 Live and public. Nothing changed yet — awaiting Will's go/no-go.
**Scope:** Site-wide. Not specific to 93 Burleigh Street.

---

## Why this surfaced now

Fields has just entered a buyer-acquisition conjunction with Tyler Benson (Coomera Realty) for
93 Burleigh Street, on terms that include *"any advertising or promotional material I create for the
property will be cleared with you before it is published."*

Checking whether we already had a page for that property revealed that we do — and that it publishes
a verdict on his pricing that he has never seen. Scoping the mechanism showed the same two defects
affect **25 agencies** across the live site.

The whole conjunction strategy depends on listing agents believing Fields is alongside them rather
than evaluating them. This is the single most direct contradiction of that available.

---

## Defect A — "Overpriced / X% above the local trend" on suppressed valuations

### What renders

`ValuationScatterPlot.tsx:739-756` prints the gap string (`:136-141`) and the positioning badge
(`:164-175`). **The only gate is `summary.insufficient_data`.** There is no check on
`directional_only`, `reconciled_valuation`, or `directional_reason`.

Data reaches it untouched: `netlify/functions/valuation.mjs:583-611` spreads the stored
`valuation_data` verbatim when `computed_at` is under 168h old. Nothing is stripped.

Second surface: `properties-for-sale.mjs:224-225` emits the same fields as `valuation_positioning` /
`value_gap_pct` (`:310-311`) to the `/for-sale` cards, the Discover feed
(`DiscoverCard.tsx:54,63`) and the "Above Valuation" filter (`PropertyFilters.tsx:94`). Waterfront is
excluded there; directional is not.

### The near-miss that makes it worse

`HowToValuePage.tsx:181-183` **does** detect `directional_only` and has a properly hedged directional
branch at `:293-381`. But that branch is guarded by `if (isDirectionalOnly && range)` — and the
design envelope suppresses **both** the estimate and the range, so `range` is always `null` for
exactly these properties. Execution falls through to `:383-390`, which renders the bare scatter plot
and badge with no caveat at all.

**The properties with the least defensible valuation receive the least qualified verdict.**

### Blast radius (live `for_sale`, all `Gold_Coast` collections)

- 203 live listings carry `summary.positioning`
- Distribution: overpriced **76**, slightly_overpriced 26, fair 34, underpriced 33, good_value 16, null 18
- **Adverse verdict AND suppressed valuation: 51** (41 overpriced + 10 slightly_overpriced)
- **All 51 have `range: null`, so all 51 hit the unhedged branch**
- **25 distinct agencies** affected (32 across all `overpriced` listings)

| Gap | Address | Agency / Agent |
|---:|---|---|
| 36.2% | 1 Seahawk Crescent, Burleigh Waters | COASTAL ° Palm Beach / Ed Cherry |
| 35.4% | 2 Eagle Avenue, Burleigh Waters | Realty Blue / Mick Brace |
| 35.3% | 24 Tropicana Circuit, Burleigh Waters | PRD Burleigh Heads / Braiden Smith |
| 29.9% | 6 Avocet Avenue, Burleigh Waters | One Agency Burleigh-Miami / Danny O'Donnell |
| 27.8% | 8 Gum Court, Burleigh Waters | One Agency Burleigh-Miami / Danny O'Donnell |
| 27.8% | 13 Tattler Way, Burleigh Waters | Realty Blue / Ben Burns |
| 25.2% | 1708/116 Laver Drive, Robina | Ray White Robina / Orren Topolansky |
| 20.5% | 70 Burleigh Street, Burleigh Waters | Realty Blue / Mick Brace |
| 10.9% | 74 Harrier Drive, Burleigh Waters | Kollosche / Lee McFarlane |
| **8.7%** | **93 Burleigh Street** | **Coomera Realty / Tyler Benson** |

Multi-listing exposure: Harcourts Property Hub (7), COASTAL ° family (8), Ray White family (6),
Realty Blue (5), One Agency Burleigh-Miami (3), Image Property Gold Coast (3), plus Kollosche and PRD.

### And for many of them the number is meaningless, not merely unsupported

Where a listing has a non-numeric price string (`"Submit All Offers!"`, `"Contact Agent"`,
`"Auction"`), `parse_price` returns `None`, `subject_price` falls back to **the median of the comps**
(`precompute_valuations.py:3713-3721`), and `compute_value_gap` (`:3344-3387`) compares that median
to a regression built from **the same comps**. The badge compares the comp set to itself. There is
no asking price for the listing to be "over". 93 Burleigh is one of these.

---

## Defect B — Non-published editorial served by the public API

### Mechanism

`netlify/functions/property.mjs:439-442`:

```js
ai_analysis:
  (listingStatus === 'sold' || listingStatus === 'withdrawn')
    ? null
    : (propertyDoc.ai_analysis || null),
```

The only condition is listing status; `status` is never inspected. **The correct pattern is six lines
below**, at `:445-448`, where `sold_analysis` is gated on `status === 'published'`.

The React gates (`PropertyPage.tsx:674, 781, 826, 968-971`) are client-side hides, not withholds. The
SSR route is clean (`src/routes/property.$id.tsx:99-102` gates correctly and emits only a sanitised
`has_ai_analysis` boolean at `:238`). The leak is exclusively the public, uncredentialed, cacheable
`/api/property/:id` response.

Verified live: `GET /api/property/690bd81b8b8f546592617fbb` → `ai_analysis` present, `status:
"rejected"`, 33,267 bytes.

### Counts (live `for_sale`)

| `ai_analysis.status` | Count | Served? |
|---|---:|---|
| published | 79 | intended |
| rejected | 12 | **leaked** |
| suppressed_waterfront | 12 | **leaked** |
| skipped_waterfront | 10 | **leaked** |
| needs_review | 6 | **leaked** |
| draft | 2 | **leaked** |

**42 live pages serve non-published editorial. 16 contain adverse pricing claims naming an agent.**

Note the waterfront cases are properties where `property.mjs:460-462` *deliberately* withholds
`reconciled_valuation` — the valuation is suppressed, and the prose about it is not.

### Verbatim, all publicly retrievable right now

> **70 Burleigh Street** — Realty Blue / Mick Brace (`suppressed_waterfront`):
> "Listed 27 May 2026 at $5,995,000, this Burleigh Street rebuild is priced roughly **$3 million
> above** what Burleigh Waters' own comparable sales can currently prove."

> **4 Cape Martin Lane, Varsity Lakes** — Amir Prestige Group / Justin Haynes:
> "This property, even at the low end of its comparable range, sits roughly **37% above** that
> current typical price"

> **6 Cottesloe Drive, Robina** — Amir Prestige Group / Omar Amir-Mian (an `h2` heading):
> "Comparable sales point to $1,245,000–$1,476,000 for this spec — the $1,550,000 ask sits above
> that range"

> **819 Legend Trail, Robina** — Harcourts Property Hub / Isaac Genc:
> "The current guide of Offers over $2,700,000 sits above the top of that range and above both
> adjusted comparables — a premium of roughly $190,000 to $320,000..."

> **47 Tullamarine Drive, Robina** — COASTAL ° Robina / Niki Smith (`rejected`):
> "The vendor is asking buyers to pay a premium of roughly $260,000–$650,000 above these benchmarks"

> **415/33 Lakefront Crescent, Varsity Lakes** — Harcourts Property Hub / Mitch Harrop (`rejected`):
> "$87,000 above the adjusted comparable figure at the current $719,000 ask"

> **93 Burleigh Street** — Coomera Realty / Tyler Benson (`rejected`):
> "The model's overall read is that the $1,990,000 guide sits roughly **13–14% above** what
> comparable evidence supports once condition, renovation level and finishes are factored in."

Several of these were **rejected by review** — i.e. a human decided not to publish them, and they
went out anyway.

---

## Proposed containment — two server-side one-liners

Both are in Netlify functions, no frontend dependency, independently shippable.

**Fix B** (`property.mjs:439-442`) — mirror the line beneath it:

```js
ai_analysis:
  (listingStatus === 'sold' || listingStatus === 'withdrawn')
    ? null
    : (propertyDoc.ai_analysis?.status === 'published' ? propertyDoc.ai_analysis : null),
```

Behaviour-neutral for the 79 published listings (the frontend already renders only those). Closes all
42 leaks.

**Fix A** (`valuation.mjs:589-611`) — in the precomputed branch, null out `summary.positioning` and
`summary.value_gap_pct` when `confidence.directional_only === true || confidence.reconciled_valuation
== null`. Kills the badge on all 51 pages in one deploy. The `positioningLabel ? … : null` guard at
`ValuationScatterPlot.tsx:749` already handles null; `formatPct(null)` returns `"n/a"`, so the pct
`<span>` at `:747-750` needs a guard too or it renders an "n/a" chip.

Then extend `properties-for-sale.mjs:224-225`'s existing `_listWaterfront` guard to cover
directional/suppressed, so cards, feed and filter agree with the property page.

**Not containment, but the right end state:** change `HowToValuePage.tsx:293` from
`if (isDirectionalOnly && range)` to `if (isDirectionalOnly)` and write copy for the no-range case, so
these properties get honest directional framing rather than nothing. Bigger change; do it second.

---

## After shipping

Per CLAUDE.md Rule 4: log the deploy via `website-deploy-tracker.py`, screenshot the affected pages
with `site-inspector.js`, and read the PNGs to confirm the badge is gone and layout is intact.
Then a fix-history entry under `logs/fix-history/2026-08-20.md`.

Re-verify with the same queries that produced the 51 and 42 counts — both should go to zero.

## Open question for Will

The 76 `overpriced` listings that are **not** directional still publish an adverse verdict on a named
agent's listing. Those numbers are inside the engine's design envelope and so are defensible in a way
the 51 are not — but "defensible" and "wise, while asking those agents to partner with us" are
different questions. Worth a separate decision.
