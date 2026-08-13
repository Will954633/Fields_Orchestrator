# /your-home Mini-Site — AI Dependency Audit & Sub-2-Second Build Strategy

**Date:** 2026-08-12 · **Subject:** `https://fieldsestate.com.au/your-home/25-huntingdale-crescent-robina`
**Goal:** a newly submitted address produces a `/your-home` report in **under 2 seconds**.
**Scope:** `scripts/property_reports/` (15,816 lines, 47 modules) + the off-market and
valuation prior art.

---

## 0. The target

**Today: median 384 s, max 1,953 s** (n=37 `build_mode: "full"` docs,
`build_completed_at − build_started_at`). A seller waits 6 minutes at the median, up to 33.

**Required: 2 s.** That is a ~200× reduction, and it is not reachable by optimising the
current pipeline. It is reachable by *moving the pipeline off the submit path entirely*.

> **The build is a cache-fill problem, not an optimisation problem.**
> Nothing about a property depends on the seller's submission. The submission supplies one
> fact — the address — and we already hold every other fact about all 24,463 addresses in
> the target market. So the report can be built *before* the seller arrives.

**Measured proof this works:** rendering a full report from a cached fact bundle takes
**0.15 s**, including Python interpreter startup. That leaves ~1.8 s of headroom.

---

## 1. The corpus already exists

The off-market engine (`15_Off-Market/Page_Redesign_V2/`) already precomputes
deterministic fact bundles, **with zero LLM calls**, over exactly our target market:

```
robina           9,187        26,303 bundles
burleigh_waters  6,402        152 MB total (~5.8 KB each)
varsity_lakes    6,233
nerang           3,333
```

That is **89% of the 24,463 addressable target addresses already harvested.**

### Measured fill across a random 1,500-bundle sample

| Field | Filled | Note |
|---|---|---|
| `proximity` (POIs / walking) | **99.1%** | ⭐ this is the 83–172 s Overpass step — **already done** |
| `scarcity` | **100%** | |
| `valuation` | 65.6% | |
| `positioning` / `buyer` / `value_drivers` | 50.2% | |
| `subject.land_sqm` | 66.4% | |
| `subject.bedrooms` | 60.3% | |
| `subject.floor_sqm` | **37.6%** | ⚠️ structural gap — see §5 |

The architecture is a clean two-phase split, and its own docstrings state the contract:

- `fact_bundle.py:1-21` — *"the EXPENSIVE half… cached to `bundles/<slug>.json`, so the
  copy/assembly layer can be re-run infinitely… **NO LLM. Every field here is
  deterministic**"* — measured 4.54 s cold per address.
- `assemble.py:1-19` — *"the CHEAP, deterministic half. **No DB, no LLM, no network.**"* —
  measured **0.15 s**.
- `copy_v4.yaml` / `copy.yaml` — YAML sentence templates, `{}`-filled from the bundle.
  Its copy rules (`:12-16`) already encode our editorial constraints: *every number gets a
  translation line; a claim with no source should not render at all; ranges in millions,
  never to the dollar.*

A second proof exists in `15_Off-Market/Units/scripts/` — 8 files, 2,382 lines, zero AI,
governed by one rule (`unit_page_data.py:13`): **"facts are assembled HERE, once.
Renderers format; they never compute."**

---

## 2. The 2-second budget

### What runs at submit time

| Step | Cost |
|---|---|
| address → `suburb_key` + `property_id` (indexed lookup) | ~10 ms |
| load precomputed bundle | ~20 ms |
| render every slot from templates | **~160 ms** (measured) |
| write the `property_reports` doc | ~50 ms |
| **total** | **~250 ms** |

### What must move off the submit path — measured, worst offenders first

| Step | Current cost | Where it goes |
|---|---|---|
| `walking_distances` (Overpass + Mapbox) | **83–172 s** | already 99.1% precomputed as `proximity` |
| 6 LLM text narratives | **90–400 s** | **templates → 0 ms** (§3) |
| `on_demand_valuation` | **~22 s** | nightly; also fix the missing projection (§4) |
| 5 generative vision calls + N classifier calls | ~30–60 s | nightly/one-off batch — **the AI can stay** (§3b) |
| Nominatim geocode in `competitor_matcher` | up to 6.6 s (1.1 s × ≤6) | precompute coordinates |

---

## 3. What actually has to change about AI

### 3a. The requirement is "no *synchronous* AI", not "no AI"

This is the key distinction, and it makes the job smaller than it first appears. Anything
precomputed is free at submit time regardless of how it was produced.

### 3b. Vision AI can stay — it is per-address and static

A house's roof, cladding and lot shape do not change nightly. The 5 vision calls are a
**one-off backfill**, not a recurring cost:

- Satellite analysis is currently **9%** filled, street view **1%** — so this is a real
  backfill job of ~24,463 × 2 Gemini Flash calls, roughly **$30–50** and a weekend of
  wall-clock at 6-way parallelism.
- Two of them should still be replaced on *cost* grounds, not speed:
  **V2**, the floor-plan classifier, fires **15–30 calls per property at `max_tokens=8`**
  to answer YES/NO — `floor_plans_v2_extracted` already answers it for 83% of properties,
  and the residual is separable with a PIL whiteness/edge-density heuristic (floor plans
  are near-monochrome line art). **V4**, the logo-detection pass, has its output re-gated
  by hand-written geometry rules anyway (`_accept_llm_box`, `:340-346`) — a strong hint we
  don't trust it. Widen the existing HSV colour-badge detector instead.
- **V6 `satellite_annotation.detect_features` is dead code** — ~250 lines, zero callers.
  Delete it; it is a trap for the next reader.

### 3c. Text LLMs must go — because they make the corpus unaffordable

This is the causal chain that makes templating *necessary*, rather than merely nicer:

> A 2-second build requires a precomputed corpus.
> A precomputed corpus requires building 24,463 reports.
> At ~6 LLM calls each, that is **~17 days of compute single-threaded** (~25 hours at
> 16-way parallelism) **with a 30% positioning failure rate** — and it must be repeated
> whenever market data moves.
> With templates it is **~82 minutes**, and cheap enough to re-run nightly.

**Text templating is the enabling condition for everything else.**

Three further arguments, all evidenced in-repo:

1. **Editorial safety becomes structural.** `your_street_narrative.py:11-14` templates
   deliberately, because the street-level claim is legally sensitive, "to keep the
   editorial rules inviolable". The LLM path, by contrast, emitted a CLAUDE.md-forbidden
   word three times running and lost the slot.
2. **The facts are already computed; the LLM only joins them.**
   `scarcity_features.py:114-222` stores a written `phrase` per feature (`"813 m² of
   land"`, `"a pool"`); `scarcity_narrative.py:172-178` **pre-assembles the entire
   combination string**; `buyers_narrative._reconcile_numbers` (`:310-413`) then
   **overwrites every number the model produced**. The digits are already 100%
   deterministic.
3. **One reader per page.** `positioning_object.py:13-20`: *"Because each mini-site is
   seen by exactly one reader (their own home), templated rendering is fine and
   desirable."* Nobody compares two reports.

And it fixes a live quality bug: **the prose never refreshes.** The nightly job re-runs
only the competitor matcher (`slot_resolver.py:969-1029`), so narratives keep their
build-day figures while the data underneath updates every night.

### 3d. The reference implementations to extend

| Module | Lines | LLM | What it proves |
|---|---|---|---|
| `positioning_object.py` | 528 | **0** | 7-frame archetype scoring + rendered prose. Fills **48/105 docs with 0 errors**, vs the LLM slot it parallels at 72 with **22 errors**. The deterministic version has *better coverage than the AI one, today, in production.* |
| `your_street_narrative.py` | 181 | **0** | 5-variant prose, deadband logic, confidence rider, `method: "deterministic-v1"` |
| `precompute_valuations.py` | 4,385 | **0** | `generate_adjustment_narrative` (`:1816`) — a working template narrative generator. Median 196 ms/property |
| `cohort_premiums.py` | 587 | **0** | fully templated `verdict` sentences (`:417-421`) |
| `competitor_matcher.py` | 1,042 | **0** | `_difference_line` (`:584`) writes real sentences |

---

## 4. Complete AI call-site inventory

**16 sites. 14 wired, 13 live, 1 dead.**

### Text — 8 sites → Claude Max CLI (alias `sonnet`)

Every `MODEL = "claude-opus-4-x"` constant is dead; `EDITORIAL_MODEL` overrides them all
(`_claude_backend.py:88`).

| # | Function | File:line | Slot | Replace |
|---|---|---|---|---|
| T1 | `resolve_market_narrative` | `market_narrative.py:167` | `market_narrative` | **EASY** — 10 scalars, prompt already prescribes a 4-beat structure (~60 lines) |
| T2 | `_draft_owner_narrative` | `case_study_dynamic.py:403` | `case_studies.dynamic.narrative` | **MEDIUM** — card already ships without prose by design (`:572-583`) |
| T3 | `resolve_scarcity_narrative` | `scarcity_narrative.py:330` | `scarcity` | **EASY** — 460/582 lines already deterministic (~40 lines) |
| T4 | `resolve_positioning_narrative` | `positioning_narrative.py:302` | `positioning` | **MIXED** — see below |
| T5 | `resolve_personas` | `personas_narrative.py:310` | `positioning.personas` | **MEDIUM** — 6 archetypes already enumerated in the prompt (`:61-68`) |
| T6 | `resolve_buyers_narrative` | `buyers_narrative.py:449` | `buyers` | **MEDIUM** — numbers already forced |
| T7 | `generate_sale_narrative` | `generate_sale_narrative.py:207` | `sale_narrative` | **DELETE** — unwired, 1/105 docs, superseded |
| T8 | `draft_case_analysis` | `draft_case_analysis.py` | `case_study_library` | **KEEP** — 5 records, human-gated |

**T4 field by field:** `frame`, `vocabulary.use`, `vocabulary.avoid`, `avoidNote`,
`photography`, `genericParagraph` are all **EASY** —
`positioning_object._build_forbidden` (`:302-312`) already computes the avoid list.
`tradeOffs` needs ~12–15 triples. **`sampleParagraph` is the one genuine hold-out** — it
demonstrates writing craft, shown beside `genericParagraph` as the contrast. It is also
precomputable, so it can keep an LLM without costing submit-time latency.

### Vision — 8 sites → **all Gemini 2.5 Flash on Vertex**

Regardless of the model named in code (`claude_vision.py:215` short-circuits to Gemini).
The `model` provenance stored on **117 documents is false**.

| # | Function | File:line | Cached? | Action |
|---|---|---|---|---|
| V1 | `score_and_pick_hero` | `hero_photo.py:154` | ❌ | precompute; local classifier |
| V2 | `_classify_one` | `inline_floor_plan.py:134` | partial | **replace** — 15–30 calls @ `max_tokens=8` |
| V3 | `analyse_floor_plan` | `inline_floor_plan.py:284` | ❌ | **keep**, precompute |
| V4 | `_detect_branding_regions_claude` | `floor_plan_debrand.py:306` | ❌ | **drop** — output already re-gated |
| V5 | `analyse_satellite_image` | `step117:343` | ✅ 9% | **keep**, backfill |
| V6 | `detect_features` | `satellite_annotation.py:380` | — | ☠️ **DEAD — delete** |
| V7 | `analyse_street_view` | `inline_street_view.py:226` | ✅ 1% | **keep**, backfill |
| V8 | `_call_gpt` | `on_demand_valuation.py:154` | ✅ | **keep**, precompute |

---

## 4b. Corpus AI budget — decided by evidence, not preference

**Hard constraint: $250 total to pre-populate ~15,000 properties.**

### Doing everything costs $464 — and the biggest line item is not AI

| | |
|---|---|
| AI (Gemini 2.5 Flash) | $329.32 |
| Image fetch (Google Maps) | $135.00 |
| **FULL EVERYTHING** | **$464.32** |

Street View Static is billed at **$7 per 1,000 requests** — $105 for the corpus, more than
any model call. Static Maps satellite tiles are $2/1,000 ($30). *Both are list prices —
confirm against current Google Maps Platform terms; a per-SKU monthly free allowance may
absorb much of a backfill spread over two months.*

Per-call costs below are **MEASURED** — real Vertex calls with the production prompts,
reading `usageMetadata` (2026-08-12). Reproduce with `corpus_cost_model.py`.

| Call | Input tok | Output tok | Unit | ×15k |
|---|---|---|---|---|
| Satellite analysis | 3,063 (1,773 text + 1,290 image) | 829 | $0.00299 | $44.87 |
| Street view analysis | 2,294 (1,004 text + 1,290 image) | 493 | $0.00192 | $28.81 |

### Does vision actually move the valuation? Measured: barely

Ablation over **2,100 live valuations / 11,623 comparables**, stripping vision-derived
adjustment lines:

| stripped | mean \|shift\| | median \|shift\| |
|---|---|---|
| **all vision** | **3.41%** | **2.51%** |
| photo-vision only | 3.21% | 2.41% |
| **satellite only** | **0.40%** | **0.00%** |

Context: method MAE **8.05%**, published band **±12.2%**. The entire vision layer is worth
~$54,000 of movement on a $1.6 M home, against a band of $391,904.

Corroborated by `16_Valuation/` prior work: satellite as an accuracy lever measured
**9.09% MAE with vs 9.20% without** (n=588), and **blinding the subject's photo-derived
quality attributes *improved* MAE, 10.22% → 9.93%**. Three vision adjustments —
`kitchen`, `renovation`, `renovation_quality` — are already retired
(`precompute_valuations.py:2273`, verified) with optimal multipliers of 0.00.

**Street View has no code path into the valuation at all** — `inline_features.py` appears
in `precompute_valuations.py` only inside a comment (`:2405`, verified). It is 100%
narrative, at 0.2% coverage today.

**The one genuinely load-bearing vision output is `pool_present`** — removing it costs
+0.74 pp MAE, second only to land size, and it is *under*-adjusted (optimal multiplier
1.25). It is also the cheapest possible vision task: one binary question against one
aerial tile.

### Decision

| Process | Verdict | Saved |
|---|---|---|
| Street view fetch + analysis | **DROP** — zero valuation impact, 100% narrative | $134 |
| Satellite narrative analysis | **DROP** — 0.00% median shift | $45 |
| Floor-plan classifier (per-photo) | **DROP** — 83% already answered by `floor_plans_v2_extracted` | $128 |
| Hero AI pick | **DROP** — PIL heuristic | $64 |
| Photo condition backfill | **DROP** — optimal multiplier 0.50, half noise | $46 |
| Logo debrand generative | **DROP** — widen existing HSV detector | $6 |
| Floor-plan OCR | **DROP** — supplies floor area on 1.3% of houses | — |
| **Satellite tile fetch** | **KEEP** — display + deterministic lot-boundary overlay | |
| **Pool check on the tile** | **KEEP** — the only load-bearing vision output | |

```
Satellite tile fetch (display + lot overlay)   $30.00
Pool check on aerial tile (one question)        $6.73
                                               ------
TOTAL UP-FRONT                                 $36.73   = 15% of budget
```

Everything else moves **behind a button** (§6b). At current volume (~105 reports in four
months) on-demand enrichment costs single-digit dollars per month.

### 🚨 BLOCKER — fix before building any corpus

`pool` is hardened against unknown-vs-known asymmetry
(`precompute_valuations.py:1429-1443`); **`water_views` and `cladding` are not** (verified
`:1487-1495`, `:1501-1510`):

```python
s_water = 1 if subject_features.get('water_views') else 0   # unknown → "no view"
s_clad  = subject_features.get('cladding_level', 2)         # unknown → "below stone"
```

Comparables are *listed* homes with 73–97% vision coverage. Subjects in a 15k off-market
corpus will mostly have **none**. Every un-analysed subject is therefore silently marked
down against analysed comps — up to **$120,000** on water views alone. This is the measured
**+2.10% systematic downward drag**, and it *worsens* at corpus scale.

The pool fix comment names the defect class exactly: *"the same defect class as the
zero-bedroom default fixed the same day."* Apply the same skip-when-either-side-unknown
treatment to `water_views`, `cladding`, `stories` and `ac_type` **before** pre-populating
anything.

### Second bug — floor-plan vision is 100% discarded in the report path

`inline_features.py:153` passes `fpa.get("internal_floor_area")` — a **dict**
(`{'value': 248, 'unit': 'm2', …}`) — to `_resolve_numeric()`, which has no dict branch
(verified `:85-98`) and returns `None` for all 434 documents that have it. The adjacent
ollama line unwraps `.get("value")`; `precompute_valuations.resolve_numeric()` does too.
One-line fix; affects display, not the valuation number.

---

## 5. Honest gaps — read before committing

1. **`build_mode: "no_llm"` has never run on `/your-home`.** All 32 such documents are
   `state: "offmarket"`. The branches exist (`slot_resolver.py:81` and gates at
   `:150, :219, :254, :438, :608, :664, :759`) but are **unproven for this page**.
2. **Floor area is missing on 62% of addresses** (`subject.floor_sqm` 37.6%). Per
   `16_Valuation/README.md` it is the largest adjustment, and 48.7% of off-market homes
   lack it entirely. **Half of all sellers cannot be given a valuation range at all** —
   this is structural, not a pipeline bug. The template layer needs a first-class "we
   can't put a range on this" path, not an error state. `copy_v4.yaml` already has two
   (thin data vs out-of-envelope).
3. **~4% of submissions fall outside the precomputed suburbs** (reedy_creek, merrimac,
   worongary, mudgeeraba). Needs either a wider corpus or the cold-miss path (§6).
4. **Vision backfill is real work** — satellite 9%, street view 1% filled today.
5. **`on_demand_valuation._load_sold_comparables_scoped` (`:587`) has no projection** —
   it pulls **2,264 docs / 164 MB per build** for a computation needing ~30 fields.
6. **The builder has no self-monitoring.** Neither `poller.py` nor
   `build_property_report.py` wraps anything in `job_run(...)`. This is how 22 positioning
   failures accumulated invisibly — a Rule 7/7b violation.
7. **A live one-line bug.** `positioning_narrative.py:248` feeds `vocab["avoidNote"]` —
   the field where the model *names the hype words it avoided* — into the forbidden-word
   scan. Model writes "avoid phrases like 'rare opportunity'"; validator finds "rare
   opportunity"; slot dies. Observed 2026-08-10: ~352 s burned, three tabs lost, because
   `personas` and `buyers` nest inside `if pos.get("frame")` (`:783`, `:854`).

---

## 6. Target architecture

```
┌─ NIGHTLY / ONE-OFF (off the submit path — AI allowed here) ──────────┐
│                                                                      │
│  STATIC layer (per address, rarely changes)   ── one-off backfill    │
│    cadastre · lot polygon · POIs/proximity · satellite · street      │
│    view · floor plan · hero pick                                     │
│                                                                      │
│  MARKET layer (changes nightly)               ── incremental         │
│    comparables · competitor set · cohort premiums · valuation ·      │
│    scarcity counts · market state                                    │
│    ⤷ cohort/market stats computed ONCE PER SUBURB, reused across     │
│      ~10,000 addresses                                               │
│                                                                      │
│                    ▼ writes report_bundle/<slug>                     │
└──────────────────────────────────────────────────────────────────────┘
                             │
┌─ ON SUBMIT (~250 ms) ──────▼─────────────────────────────────────────┐
│  address lookup → load bundle → render templates → write doc         │
│  NO network. NO LLM. NO vision. NO Overpass.                         │
└──────────────────────────────────────────────────────────────────────┘
```

### 6b. Bifurcation — instant page, enrichment on request

Everything dropped from the corpus build in §4b is *narrative and visual value*, not
valuation value. So it moves behind an explicit user action rather than being deleted:

| Tier | Content | Cost | When |
|---|---|---|---|
| **0 — instant** | valuation + comps + scarcity + positioning + market + POIs + aerial with lot overlay | **$0.0024/property** | precomputed, renders in ~250 ms |
| **1 — on request** | street view read, photo condition read, floor-plan rooms | ~$0.02 per press | homeowner presses a button |

Tier 1 is the honest place for this content anyway: it is *about the homeowner's own
house*, it is the part they are most likely to want on demand, and asking costs them one
tap. At ~105 reports in four months, Tier 1 costs single-digit dollars per month even if
every reader presses every button.

The existing `slot_status` + `PendingPlaceholder` machinery already supports exactly this
— a slot marked `pending` renders a placeholder rather than an empty tab.

**Cold miss** (address outside the corpus): render a Tier-1 report immediately from
cadastral + `address_search_index` data — still under 2 s — mark the richer slots
`building`, and enqueue background enrichment. This is what `PendingPlaceholder` and the
existing `slot_status` machinery already support.

**Nightly cost estimate:** the market layer is the only recurring work, and its per-suburb
statistics amortise across ~10,000 addresses each. At ~200 ms marginal per address,
24,463 addresses ≈ **82 minutes single-threaded**, ~10 minutes at 8 workers.
`precompute_valuations.py` already proves the pattern with a 7-day fingerprint skip
(`_should_skip_valuation`, `:4153`) — that night: 22 processed, 190 skipped, 0 errors.

---

## 7. Sequencing

**Phase 1 — correctness & instrumentation (~half a day).** Independent of everything else.
1. Fix the `avoidNote` validator bug (one line; recovers ~30% of positioning failures).
2. Delete dead vision code in `satellite_annotation.py` (~250 lines).
3. Fix the two wrong-key gates (`hero_photo.py:112`, `inline_floor_plan.py:164`) — today,
   removing a dead OpenAI credential silently disables two features with a
   `logger.warning` and a "successful" build. Rule 7b hazard.
4. Fix the false `model` provenance on 117 documents.
5. Wrap the build in `job_run(..., cadence_hours=…)` with a 7b outcome assertion — the
   zero-output path is "bundle written with every slot empty".

**Phase 2 — prove the deterministic path on `/your-home` (~2 days).**
6. Run `build_mode: "no_llm"` end-to-end on a real `/your-home` address. It has never
   executed on this path; find out what breaks before building on it.
7. Add the projection + per-process cache to `on_demand_valuation` (~22 s → sub-second).
8. Port `check_renderer_consistency.py` from `Units/` so React and the markdown review
   copy can never disagree on a figure.

**Phase 3 — template the text layer (the enabling work).**
9. T1 `market_narrative` and T3 `scarcity_narrative` first — both **EASY**, ~100 lines
   combined, and T3 already has a `no_llm` path (`slot_resolver.py:667-681`).
10. Then T5, T6, T4-minus-`sampleParagraph`, T2. Delete T7.
    *Model each on `your_street_narrative.py`; extend `positioning_object.render.*`.*

**Phase 4 — build the corpus.**
11. Extend `fact_bundle.py` to cover every `/your-home` slot (it currently covers the
    off-market deck's subset), then batch it across all 24,463 target addresses.
12. Backfill vision (satellite 9% → ~100%, street view 1% → ~100%) as an offline job.
13. Move `walking_distances` off the build path — 99.1% is already in `proximity`.

**Phase 5 — flip the switch.** Submit-time = load bundle + render. Add the cold-miss
Tier-1 path. Target **~250 ms**.

---

## 8. Decisions for Will

1. **Corpus scope.** 24,463 addresses covers ~96% of submissions. Widening to
   merrimac/mudgeeraba/reedy_creek/worongary/carrara pushes toward ~50–60K. Where do we
   stop, and is the Tier-1 cold-miss path acceptable for the tail?
2. **Vision backfill.** ~$30–50 and a weekend for full coverage. Worth it, or do we ship
   with satellite/street view only where they already exist and let the rest fill in?
3. **`sampleParagraph`.** The one field where a template will read as a template — and it
   sits beside a deliberately-generic paragraph to prove we write better. Since it is
   precomputed, keeping an LLM there costs no latency. Keep it?
4. **The floor-area gap is the real product constraint.** 62% of addresses have no floor
   area, so no range. Fixing that moves the report's value more than any latency work.
