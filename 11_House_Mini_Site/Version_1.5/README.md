# Version 1.5 — the deterministic `/your-home` build

**Status: working, viewable, not the default.** Built 2026-08-12/13.

V1.5 is **not a new UI and not a new codebase**. It is the same nine-tab report as
Version One, produced by the same pipeline, running in a different **build mode** — with
the LLM prose replaced by deterministic Python templates.

> There is no "V1.5 folder of code". This directory holds the documentation. The code is
> the live pipeline in `scripts/property_reports/`, plus two new modules. That is
> deliberate: V1.5 is a *mode*, so it shares every deterministic component with V1 rather
> than forking it.

**See it:**

| | URL |
|---|---|
| V1 (full AI) | `https://fieldsestate.com.au/your-home/25-huntingdale-crescent-robina` |
| **V1.5 (deterministic)** | `https://fieldsestate.com.au/your-home/25-huntingdale-crescent-robina-nollm` |

Same property, same data, built both ways. The V1.5 doc is `is_test: true`, unlinked and
noindex.

---

## 1. Why it exists

The goal is a `/your-home` report for a newly submitted address **in under 2 seconds**.
Today a full build takes a **median of 384 s** (max 1,953 s, n=37) — a seller waits 6 to 33
minutes.

Two things were learned early and both changed the plan:

1. **Removing AI does not make the *page* faster.** There is zero AI on the request path;
   all AI output is pre-baked into Mongo. The page is slow for unrelated infrastructure
   reasons (see §7).
2. **Removing AI does not, by itself, make the *build* fast either.** A no_llm build still
   takes 79–145 s, and almost none of that is AI (§4).

What AI removal actually buys is that **the corpus becomes affordable to precompute**. At
~6 LLM calls per report, pre-building 24,463 addresses is ~17 days of compute with a 30%
failure rate on one slot; with templates it is ~82 minutes and can be re-run nightly. That
is the causal chain: templates → affordable corpus → sub-2-second build.

Full reasoning, costings and measurements:
`11_House_Mini_Site/AI_DEPENDENCY_AUDIT_AND_DETERMINISTIC_STRATEGY.md`.

---

## 2. How to build one

`build_mode` is a **field on the report document**, not a CLI flag.

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator

# mark a report deterministic
python3 - <<'PY'
from shared.db import get_client
get_client()['system_monitor'].property_reports.update_one(
    {'slug': '<slug>'}, {'$set': {'build_mode': 'no_llm'}})
PY

# build it
python3 -m scripts.property_reports.build_property_report --slug <slug> --force
```

⚠ **This is out of date as of 2026-08-16 — the default is now INVERTED.**
`slot_resolver.py:104` reads `self.no_llm = report_doc.get("build_mode") != "full"`,
so a missing `build_mode` (what a fresh submit writes) is **deterministic**, and
you must opt IN to the LLM chain with `build_mode: "full"`. The comment there
explains why: "a new mode that only applies when someone remembers to set a flag
is a mode that never applies."

Measured across the live collection 2026-08-19 — `no_llm` median **4.5 s** (p90
22.6 s, n=132) vs `full` median **354 s** (p90 576 s, n=42). If you are reading a
report built before 2026-08-16 with no `build_mode`, it is a **full-AI** build and
its build time is not comparable. See [[offmarket_direct_test_round2]].

⚠ **Restart the poller after editing any resolver module** — it caches imports, so a fix
lands but new submissions resolve with the old code:
`sudo systemctl restart fields-property-report-poller`

⚠ **`scripts/property_reports/` is untracked in local git.** It lives on GitHub only via
`gh api` / `scripts/push_website_files.py`. `git status` will not show your changes.

---

## 3. What it produces

Measured on `25 Huntingdale Crescent, Robina` — a best case, all 12 slots approved in V1.

| | V1 (full AI) | V1.5 (deterministic) |
|---|---|---|
| Slots approved | 12 | **9** |
| BSON | 205,321 | **134,719** (66%) |
| API payload | 153.5 KB | **121.3 KB** |
| Page height | 10,321 px | 6,948 px (67%) |
| Model calls | 6 LLM + 5 vision | **~1** (see §6, a bug) |
| AI cost | — | **~$0.004** |

**Kept (9):** `comps` · `competitor_matches` · `statutory_cma` · `scarcity` ·
`market_narrative` · `positioning_thesis` · `walking_distance` · `seasonality` ·
`your_street`

**Lost (4):** `positioning` · `buyers` · `case_studies` · `sale_narrative`
**Gained (1):** `your_street` (V1 never ran it on this doc)

Two of those slots — `scarcity` and `market_narrative` — are approved *because* V1.5
templates them. Before the templates were written, V1.5 scored 7/12.

---

## 4. Where the build time actually goes

Measured on a fresh V1.5 build. **None of this is AI:**

| Step | Cost | Where it belongs |
|---|---|---|
| Photo mirroring to blob | ~111 s | nightly |
| Overpass POI lookups | ~91 s | 99.1% already precomputed in the off-market `proximity` bundles |
| `on_demand_valuation` | ~22 s | nightly — and it has **no projection** (pulls 2,264 docs / 164 MB per build) |
| Comparable feed / sold dedup | ~33 s | nightly |
| Process startup | ~8 s | removed by a precompute/render split |
| Hero vision call | ~5.7 s | **bug — should not run at all in no_llm (§6)** |

Total 79–145 s depending on what is already cached. Every one of these is precomputable,
which is what makes the ~250 ms target reachable — the off-market engine already renders a
cached bundle in **0.15 s** (`15_Off-Market/Page_Redesign_V2/assemble.py`).

---

## 5. Core files

### New in V1.5

| File | What |
|---|---|
| `scripts/property_reports/scarcity_headline.py` | Deterministic scarcity hero — `headline`, `combinatorialMatch`, `walkingDistanceMonopoly`, `closingLine`. Replaces the Opus `scarcity_narrative`. |
| `scripts/property_reports/market_paragraph.py` | Deterministic suburb market paragraph, 50–90 words. Replaces the Opus `market_narrative`. |
| `11_House_Mini_Site/AI_DEPENDENCY_AUDIT_AND_DETERMINISTIC_STRATEGY.md` | The full audit: 16 AI call sites, costs, corpus plan. |
| `11_House_Mini_Site/corpus_cost_model.py` | Reproducible corpus AI/imagery cost model. |

Both new modules follow `your_street_narrative.py`: tagged `method: "deterministic-v1"`,
`model: None`, and **return `None` rather than emit a claim they cannot support** (thin
feature stack; sub-50-word market read). Editorial rules are structural — no forbidden word
exists in the vocabulary, and the K-of-N receipt can only describe the *counted* anchors.

### Modified for V1.5

| File | Change |
|---|---|
| `scripts/property_reports/slot_resolver.py` | Wires both templates into the `no_llm` path; only approves `scarcity` when a headline exists |
| `scripts/property_reports/poller.py` | `job_run` per build with a Rule 7b assertion + 30-min daemon heartbeat |
| `scripts/property_reports/positioning_narrative.py` | `avoidNote` no longer scanned for forbidden words |
| `scripts/property_reports/inline_features.py` | `_resolve_numeric` unwraps the `{"value": N}` envelope |
| `scripts/property_reports/satellite_annotation.py` | −301 lines of unreachable vision code |
| `.../YourHomePage/components/HeroSection.tsx` | Hero requires real scarcity copy, not just an approved slot |

### The deterministic layer V1.5 stands on (pre-existing, no AI)

These already had no model in the loop and do the heavy lifting:

`positioning_object.py` (archetype scoring + rendered prose) · `your_street_narrative.py`
(the pattern both new modules copy) · `scarcity_features.py` (writes the feature `phrase`
fragments) · `cohort_premiums.py` · `competitor_matcher.py` · `statutory_cma.py` ·
`comparable_feed.py` · `walking_distances.py` · `nearby_pois.py` · `inline_features.py` ·
`build_case_study.py` · `lot_boundary.py` · `canonical_resolver.py` ·
`occupancy_classifier.py` · `mirror_report_photos.py` · `valuation_format.py`

Plus the valuation engine itself — `Feilds_Website/07_Valuation_Comps/precompute_valuations.py`,
4,480 lines, **zero AI**, including its own template narrative generator.

### Frontend (unchanged by V1.5 except the hero guard)

`/home/fields/Feilds_Website/01_Website/src/pages/YourHomePage/` — `YourHomePage.tsx`,
`tabs/`, `components/`, `data/homeFixture.ts`.

---

## 6. Known defects and gotchas

1. **`no_llm` does not gate the hero vision call.** `hero_photo.score_and_pick_hero` still
   runs (~5.7 s + a Gemini call) in a mode that is meant to make none. Same for
   `on_demand_valuation`'s photo pass. Confirmed live.
2. **`stubFromDoc()` still deep-clones the Merrimac demo fixture** and overlays only the
   fields the resolver produced. The hero instance is fixed; **the general class is not** —
   any un-overlaid field can still show another property's content. This is the single
   biggest correctness risk in the corpus plan.
3. **Vision `model` provenance is false on 117 documents** — they record `gpt-4o`,
   `claude-sonnet-4-6` or `claude-opus-4-8`; every one actually ran `gemini-2.5-flash`.
4. **Two wrong-key gates** (`hero_photo.py:112`, `inline_floor_plan.py:164`) check for
   `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` before making a *Gemini* call. Removing a dead
   credential would silently disable both features with a `logger.warning` and a
   "successful" build.
5. **`valuation_backtest.py` is nondeterministic** — repeated identical runs differ by ~$6
   on MAE. No A/B below ~0.05 pp is readable.
6. **`case_studies` sits `pending`** in V1.5 — the card ships data-only by design, but the
   slot is not approved.

---

## 7. Not V1.5's problem (but blocks the 2-second goal)

Page **load** is separate from build. Measured:

- `getFreshClient()` opens a new Cosmos connection per request from a US-region function to
  an Australia-East database: **2.42 s, every request, no warm path**. A pooled function on
  the same site serves in **0.105 s**.
- The client waterfall re-reads the *same document by the same slug*: **+2.13 s**.
- `mapbox-gl` is eagerly preloaded (447 KB gz / 1.66 MB parsed) for a map on a non-default tab.

---

## 8. What's left

**A. Close the last prose gap** — `positioning` (keep an LLM only for `sampleParagraph`),
`personas` (the 6 archetypes are already enumerated in the prompt — move them to Python),
`buyers` (numbers are already forced by `_reconcile_numbers`). Delete `sale_narrative`.

**B. Build time → ~250 ms** — move photo mirroring, POIs, comparables and the valuation load
off the submit path; fix the `on_demand_valuation` projection; gate the hero call.

**C. The corpus** — extend `15_Off-Market/Page_Redesign_V2/fact_bundle.py` to cover the
`/your-home` slots and batch it across the 24,463 target addresses. 89% are already
harvested (26,303 bundles, 152 MB), with `proximity` filled on 99.1%.

**D. Vision budget — $36.73** (satellite tile + a pool-only check). Street view, photo
condition and floor plans move behind a Tier-1 "show me more" button, which Will confirmed
ships at launch. Doing everything instead costs $464, of which $105 is Street View *imagery*
before a single token.

**E. Blocked** — the valuation release (unknown-attribute hardening + recalibration + page
tables) is measured and written but held. See
`16_Valuation/experiments/2026-08-12-unknown-attribute-hardening.md`.

---

## 9. Related reading

- `11_House_Mini_Site/AI_DEPENDENCY_AUDIT_AND_DETERMINISTIC_STRATEGY.md` — the audit and plan
- `11_House_Mini_Site/Version_One/README.md` — what V1 shipped
- `15_Off-Market/Page_Redesign_V2/` — `fact_bundle.py` → `copy.yaml` → `assemble.py`, the
  two-phase architecture V1.5 should adopt (26,303 properties, renders in 0.15 s)
- `15_Off-Market/Units/scripts/` — *"facts are assembled HERE, once. Renderers format; they
  never compute."* Includes `check_renderer_consistency.py`, worth porting
- `16_Valuation/README.md` — the constraints any template layer must respect
- `logs/fix-history/2026-08-12.md` — every change, with root causes
