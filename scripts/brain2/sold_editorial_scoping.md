# Sold-Property Editorial — Scoping Document

**Author:** Ops agent · **Date:** 2026-07-17 · **Status:** Draft for Will's review
**Related:** `brain2_seo_demand_engine_roadmap`, `seo_indexation_baseline`, `canonical_attribute_layer`, for-sale editorial (`scripts/backend_enrichment/generate_property_ai_analysis.py`)

---

## 1. Why this, why now

Organic SEO traffic is climbing (property-page Google hits: 1 → 3 → 5/day over Jul 15–17) and **it lands overwhelmingly on sold pages**, not for-sale pages. The live sitemap makes the reason obvious:

| Sitemap `/property/` URLs | Count | Share |
|---|---|---|
| **sold** | 1,370 | **86%** |
| for_sale | 222 | 14% |
| withdrawn | 2 | <1% |

For-sale pages are ephemeral — a listing exists for weeks, then becomes a sold page at the *same* URL. Google indexation takes weeks, so by the time a `/property/<slug>` ranks and gets clicked, the property has usually already sold. **The durable, ever-growing, indexable surface is the sold corpus** (sold pages re-enabled in the sitemap 2026-07-16 as the Brain 2 demand-engine pilot).

Today those 1,370 sold pages render bare — valuation data only, no editorial. The for-sale editorial pipeline (`ai_analysis`) is scoped `listing_status: for_sale` and `property_type: House`, and it costs ~12 min of Opus multi-agent per property. **That approach cannot scale to 1,370+ pages, and shouldn't — sold pages are retrospective factual content that deterministic Python can do better, cheaper, and more compliantly.**

## 2. Objective & hard constraints

Build a **`sold_analysis`** layer that gives every sold page genuinely insightful, data-grounded content.

**Constraints (Will, 2026-07-17):**
1. **Zero marginal cost** — built *mostly if not entirely* in Python. No per-property LLM call in the core path.
2. **Scalable** — runs over 1,370+ pages (and every future sold listing) nightly, idempotent, cheap.
3. **Insightful** — not a stat dump. The intelligence comes from *comparison and context*, computed automatically.
4. **Compliant** — data-only, no advice, no predictions, exact figures, cited sources (see §6).

**Why zero-LLM is achievable here:** a sold page is a *closed, historical fact set* — price, date, days on market, condition, comparables. There is nothing to "reason" or predict; there is a right answer for every claim. That is exactly the shape deterministic templates excel at, and it removes hallucination risk by construction.

## 3. Data foundation (measured, not assumed)

Coverage across **1,588 sold+slug properties** in target-region suburbs (scan 2026-07-17):

| Field | Coverage | Notes |
|---|---|---|
| `sold_date` | 99% | anchor for recency + market-context |
| beds / baths | 98% | segment key |
| **sold price** | **93%** | in `sale_price` / `listing_price` strings (parse `$X`), NOT the empty `sold_price` field |
| photo analysis (`property_valuation_data`) | 71% | condition scores, renovation, materials — the "quality" layer |
| `property_type == House` | 62% | + 189 Townhouse, 126 Unit, 26 Duplex, 18 Villa |
| `days_on_market` | 37% | campaign-speed insight where present |
| floor area (`floor_plan_analysis`) | 17% | $/sqm + size-percentile where present |

**Design implication:** insights are **tiered by data availability**. A property with price + date + beds always gets a solid page; photo-analysis and floor-area insights layer in when present. The engine never asserts a claim whose source field is missing — it simply omits that module.

**Benchmark data is free and self-referential.** We already hold 1,489 sold prices. Suburb/segment medians, percentiles, $/sqm bands and DOM distributions are computed *from our own corpus* in-process — no external API, no cost. (Example, measured live: Robina Houses n=336, median $1,473,500, p25 $1,310,000, p75 $1,710,000, DOM median 26 days.)

## 4. The method — a deterministic insight engine

Three layers, all pure Python.

### 4a. Benchmark layer (compute once per run, cache in memory)
For each `(suburb, property_type)` segment, and for `(suburb, property_type, bed_band)`:
- price: median, mean, p10/p25/p75/p90, count, rolling-12-month median
- $/sqm distribution (where floor area present)
- days-on-market distribution
- price trend: median by quarter (for "how the suburb moved around this sale")

Guardrail (from `canonical_attribute_layer`): **rarity/percentile is always sample-relative, never census**, and every benchmark carries its `n`. Segments below a minimum `n` (e.g. 8) fall back to the parent segment and the copy widens accordingly ("across Robina house sales" vs "across 3-bed Robina houses").

### 4b. Per-property insight modules
Each module is a pure function: `(property, benchmarks) → Insight | None`. It returns `None` when its inputs are missing. An `Insight` carries `{claim_text, evidence: {field: value}, tier, confidence}` so every sentence is traceable to source fields (feeds §6 verification).

| # | Module | Inputs | Example output (data-only) |
|---|---|---|---|
| 1 | **Price vs market** | sold_price, segment benchmark | "Sold for $1,520,000 — $46,500 above the Robina house median at the time, in the 55th percentile of 336 house sales." |
| 2 | **Price journey** | price_history, sale_price | "First listed at $1,595,000, sold at $1,520,000 — a $75,000 (4.7%) movement over the campaign." |
| 3 | **Campaign speed** | days_on_market vs DOM dist | "On market 16 days versus a Robina house median of 26." |
| 4 | **Size** | floor_area vs $/sqm + size dist | "224 sqm internal — larger than ~70% of houses sold in the segment; $6,786/sqm vs a segment median of $6,400." |
| 5 | **Condition & finish** | property_valuation_data | "Photo analysis: fully renovated, kitchen 9/10, stone benchtops, pool in good condition." (materials/scores only — never renovation year/cost) |
| 6 | **Configuration** | beds/baths/car/land | "5 bed / 3 bath / 2 car on 620 sqm — a larger-format home for the segment." |
| 7 | **Location factors** | geo, POIs, beach dist | "650 m to the nearest primary school; 4.2 km to Burleigh Beach." (distance facts only — no catchment claims, per `school_catchment_feature`) |
| 8 | **Flood context** | flood overlay | "No flood overlay on the GCCC City Plan for this lot." (cite GCCC; never "never floods", per `flood_data_burleigh`) |
| 9 | **Comparable set** | valuation_data comps | "Three houses within 500 m sold between $1.40M–$1.61M in the same period." |
| 10 | **Market timing** | sold_date vs quarterly medians | "Sold in Q2 2026, when the Robina house median sat around $1.47M." |

### 4c. Selection, ranking & assembly
- Run all modules; keep those returning an `Insight`.
- **Rank by notability** — a deterministic score favouring: distance from median (a well-above/below-median sale is interesting), fast/slow campaign, strong renovation signal, unusual size. This is what makes the page *insightful* rather than a template read: the 3–5 genuinely notable facts float to the top per property, automatically.
- Assemble into a fixed content model (§5): a headline built from the top insight, a 2–3 sentence factual summary stitched from the top-ranked insights via sentence templates with conditional connectors, then the full insight list.
- Deterministic headline templates keyed on the top insight type (e.g. above-median + fast-sale → "Sold in 16 days, $46,500 above the Robina median"). No single-valuation-in-headline violations because sold price is a *transacted fact*, not a valuation estimate (§6).

## 5. Content model (`sold_analysis` field)

```json
{
  "version": 1,
  "generated_at": "ISO",
  "generator": "generate_sold_analysis.py@<git-sha>",
  "status": "published",           // deterministic + verified → auto-publish (see §6)
  "headline": "Sold in 16 days, $46,500 above the Robina house median",
  "summary": "2–3 sentence factual paragraph, stitched from top insights.",
  "insights": [ { "type": "price_vs_market", "text": "...", "evidence": {...}, "tier": 1 } ],
  "benchmarks_used": { "segment": "robina|House|5bd", "n": 41, "median": 1620000 },
  "sources": ["Domain sold record", "Fields photo analysis", "GCCC City Plan"],
  "data_completeness": 0.78
}
```

Frontend: mirror the for-sale gate — `PropertyPage.tsx` renders `sold_analysis` when `listing_status === 'sold'` (parallel to the `ai_analysis?.status === 'published'` path at `PropertyPage.tsx:311`). One new render branch; reuse existing insight components.

## 6. Editorial compliance (easier for sold than for-sale)

Retrospective reporting sidesteps most liability surface, but the rules still bind:
- **No advice / no predictions** — nothing forward-looking. "Sold for X after Y days" is pure history. Templates contain zero directive verbs; a lint list (`should`, `consider`, `now is`, `negotiate`, `will`) is asserted-against at build time.
- **Exact figures** — sold prices exact, never rounded (`$1,520,000`).
- **Single-valuation-in-headline rule does not apply** — that rule guards *our valuation estimates*; a **transacted sale price is a fact**, and is what the reader searched for. Confirm this reading with Will.
- **Value framing** — trade-offs framed as value, never flaws (compact land = "low-maintenance", not "small").
- **Cite + limitation** — every claim names its source; benchmarks state `n`; missing data is omitted, never guessed.
- Honesty guardrails carried over: rarity sample-relative (`canonical_attribute_layer`), no catchment claims (`school_catchment_feature`), flood cites GCCC (`flood_data_burleigh`).

**Because output is deterministic and every claim is source-traced, the engine can auto-publish** — no human review queue (unlike for-sale `ai_analysis`). A build-time verification pass (below) is the gate instead.

## 7. Quality & verification

No LLM ⇒ no hallucination, but arithmetic/parse bugs are the risk. Mitigation:
- **Assertion layer** — every emitted `Insight.evidence` is re-checked against the source doc before write (e.g. the quoted price parses back to the same integer; percentile recomputes to the same bucket). A mismatch drops that insight, not the page. Extends the existing `scripts/property_reports/verify_claim.py` pattern.
- **Golden set** — ~20 hand-verified properties as a regression fixture; CI diff on template changes.
- **Completeness floor** — pages below a data-completeness threshold (e.g. price missing, 7% of corpus) get a minimal "sold on <date>" stub, not a fabricated analysis.

## 8. Architecture & integration

- **Script:** `scripts/backend_enrichment/generate_sold_analysis.py` — `--suburb`, `--slug`, `--backfill`, `--since <date>`, `--dry-run`. Idempotent; skips unchanged (hash of source fields → skip if `sold_analysis.source_hash` matches).
- **Orchestrator:** new nightly step after sold-detection (103/104) + photo analysis (105); processes newly-sold + any stale. Pure-Python, seconds per property, negligible RU.
- **Storage:** `sold_analysis` field on the property doc, parallel to `ai_analysis`.
- **Sitemap:** already includes sold pages (done 2026-07-16).
- **Frontend:** one render branch in `PropertyPage.tsx` + `property.mjs` already returns the whole doc.

## 9. Rollout

1. **Benchmark engine + 3 core modules** (price-vs-market, campaign-speed, configuration) over Robina Houses — validate against the golden set. Ship to ~336 pages.
2. **Add photo-analysis + size + comparable modules**; extend to Burleigh Waters + Varsity Lakes Houses.
3. **Non-house types** (Townhouse/Unit — 315 records) with segment-appropriate templates.
4. **Full corpus backfill** (1,370) + wire into nightly orchestrator for go-forward automation.
5. **Measure:** GSC impressions/clicks on sold URLs pre/post (`seo_indexation_check.py`), and PostHog on-page engagement.

## 10. Optional future enhancement — narrative polish at zero marginal cost

The core path is 100% Python. *If* the stitched summaries read too mechanically, an **optional** polish pass can rephrase the already-verified summary via the **Claude Max CLI** (`claude -p`), which is **flat-rate, not pay-as-you-go** (per `claude_max_cli_routing` — article gen already runs this way). That keeps marginal cost at zero. It would be gated: polish only the `summary` string, never introduce new facts, then re-run the §7 assertion layer to guarantee no claim drifted. **Not part of v1** — deterministic first, prove it, add polish only if needed.

## 11. Open questions for Will

1. **Sold price in headline** — confirm a transacted sale price is fair game in headlines (I read it as fact, not a valuation estimate — but you set the editorial line).
2. **Auto-publish** — OK for deterministic sold content to publish without a review queue, gated on the verification pass? (This is the whole scalability win.)
3. **Scope order** — Houses first (990), or all types together?
4. **Tone** — how much narrative vs. near-tabular? A sold "comp card" could be terser than a for-sale editorial.
5. **Buyer-first framing** — sold pages are strong buyer research tools ("what did this actually go for and why"). Any seller-facing CTA, or keep them purely informational for now?

---
*Appendix — worked example (real data, computed 2026-07-17): 4 Springvale Street, Robina, sold $1,520,000 (2025-11-24). Robina House benchmark n=336, median $1,473,500. Engine output → headline candidate "Sold $46,500 above the Robina house median"; price-vs-market insight "55th percentile of 336 sales"; campaign-speed omitted (no DOM). Zero LLM calls.*
