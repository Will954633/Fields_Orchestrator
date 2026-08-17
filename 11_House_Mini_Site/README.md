# House Mini Site

The per-property seller report at `/your-home/<slug>`, reached from **Analyse Your Home**.

*Reorganised 2026-08-05 — V1 build material and V2 session material had been sharing one
flat folder. **Version 1.5 shipped 2026-08-16** and is what the funnel now builds.*

---

## Structure

| Folder | What |
|---|---|
| **`Version_One/`** | The shipped tabbed report — plans, design, content, case studies, the PMF gap analysis, and the scripts and assets that built it |
| **`Version_1.5/`** | ⭐ **The current build.** Deterministic — same report, no AI. Start here |
| **`Version_Two/`** | The guided-session rebuild. Start at `00_SESSION_SYSTEM.md` |
| **`_shared/`** | Spans all generations — the direct-mail generator, the off-market flow reference, the adjusted-comparables evidence |

Loose at this level: `AI_DEPENDENCY_AUDIT_AND_DETERMINISTIC_STRATEGY.md` (the audit behind
V1.5) · `corpus_cost_model.py` (corpus AI + imagery costs).

---

# Version 1.5 — the deterministic build (CURRENT)

**Live and default since 2026-08-16.** A new address submitted through Analyse Your Home is
built by this path.

V1.5 is **not a new UI and not a new codebase**. It is the same report, produced by the same
pipeline, in a different **build mode** — every LLM call replaced by a deterministic Python
template. There is no "V1.5 folder of code": the code is the live pipeline in
`scripts/property_reports/`.

### What changed, measured

| | V1 (full AI) | **V1.5** |
|---|---|---|
| Build a new address | 266–611 s (median 384 s, max 1,953 s) | **6–42 s** |
| Model calls per build | 11 | **0** |
| Slots produced | 12 | **12** |
| Page load | ~4 s | ~4 s |

The AI removal itself was worth ~1 second. **The speed came from infrastructure**, not from
dropping models — see §3.

---

## 1. How a report is built

```
/analyse-your-home  (address form)
      │
      ▼
POST /api/v1/analyse-your-home-submit         netlify/functions/analyse-your-home-submit.mjs
      │   writes a `stub` doc to system_monitor.property_reports
      │   build_mode defaults to "no_llm"      ← the line that decides what a seller gets
      ▼
/analyse-your-home/building/<slug>            src/pages/AnalyseYourHomePage/BuildingPage.tsx
      │   polls /api/v1/property-report-progress every 1.5 s
      ▼
fields-property-report-poller  (systemd)      scripts/property_reports/poller.py
      │   finds stubs >5 s old, runs SlotResolver
      ▼
state: under_review  ->  redirect to /your-home/<slug>
```

**Two places decide the build mode and they must agree:**

| Layer | Setting |
|---|---|
| `analyse-your-home-submit.mjs:310` | `body.build_mode === 'full' ? 'full' : 'no_llm'` |
| `slot_resolver.py` (`SlotResolver.__init__`) | `self.no_llm = report_doc.get("build_mode") != "full"` |

⚠ On 2026-08-16 only the resolver was flipped, and the funnel stayed on the AI path because
the submit endpoint still wrote `'full'` on every submission. Both ends have to change.
`build_mode: "full"` opts an individual report back into the LLM chain.

### Build one by hand

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator
python3 -m scripts.property_reports.build_property_report --slug <slug> --force
```

⚠ **Restart the poller after editing any resolver module** — it caches imports, so a fix
lands but new submissions resolve with the old code:
`sudo systemctl restart fields-property-report-poller`

⚠ **`scripts/property_reports/` is untracked in local git.** It lives on GitHub only via
`scripts/push_website_files.py`. `git status` will not show your changes.

⚠ **Currently-listed homes are refused** (`state: currently_listed`). The mini-site is for
off-market sellers; a home already on the market with another agent is out of scope.

---

## 2. The twelve slots, and what writes each

| Slot | Producer | AI? |
|---|---|---|
| `comps` | engine output reshaping | no |
| `competitor_matches` | `competitor_matcher.py` — 8-axis weighted similarity, adaptive aperture rings | no |
| `statutory_cma` | `statutory_cma.py` — PO Act Sch 2 rules engine | no |
| `scarcity` | `scarcity_features.py` + **`scarcity_headline.py`** | **templated** |
| `market_narrative` | **`market_paragraph.py`** | **templated** |
| `positioning` | `positioning_object.py` + **`positioning_template.py`** | **templated** |
| `positioning_thesis` | `positioning_object.py` | no |
| `buyers` | **`personas_template.py`** (`resolve_buyers_template`) | **templated** |
| `case_studies` | `case_study_dynamic.py` with `skip_narrative=True` | no |
| `walking_distance` | `nearby_pois.py` over the pre-harvested POI set | no |
| `your_street` | `your_street_narrative.py` | no |
| `seasonality` | `precompute_seasonality.py`, refreshed nightly | no |

`sale_narrative` exists in the schema but **no build produces it** — it is a manual CLI
(`generate_sale_narrative.py`) present on 1 of 105 documents.

### The template modules

All follow `your_street_narrative.py`: tagged `method: "deterministic-v1"`, `model: None`,
and **they return `None` rather than emit a claim they cannot support**.

- **`scarcity_headline.py`** — the hero. The model was never composing here: `FEATURE_RULES`
  already stores a finished `phrase` per feature, the sentence frame was dictated verbatim
  in the prompt, and the closing line was already a Python constant.
- **`market_paragraph.py`** — ten scalars, a four-beat structure the prompt already
  specified. Returns None below 50 words rather than present two numbers as an analysis.
- **`positioning_template.py`** — dresses `positioning_object`, which already computes the
  winning archetype, the price-driver/buyer-driver split, the anti-frames and the
  forbidden-claim list.
- **`personas_template.py`** — the six buyer archetypes were enumerated *verbatim in the old
  system prompt*; they are Python now. Channel copy is fixed: Fields has no email list, no
  newsletter, no school noticeboards, no print mailers.

**Why templating is safer here, not just cheaper.** Editorial rules become structural — a
forbidden word cannot occur because it is not in the vocabulary. The LLM positioning slot
was erroring on **22 of 105 documents** and silently taking `personas` and `buyers` down
with it, because both nested under `if pos.get("frame")`.

---

## 3. Where the build time actually goes

The templates cost ~1 s combined. The 143 s → 19 s came from infrastructure:

| Step | Was | Now |
|---|---|---|
| Overpass POI lookup | **67.1 s** (all three mirrors exhausting) | 0 s — reads pre-harvested `Gold_Coast_POIs.pois` |
| Hero vision call | 6.7 s | 0 s — was firing a Gemini request in the no-AI mode |
| Competitor map | 42.4 s | 0.3 s — unblocked once Overpass stopped stalling |
| `on_demand_valuation` load | 60.7 MB / 2.74 s | 25.8 MB / 1.22 s (exclusion projection; output byte-identical) |
| Occupancy classifier | ~10 s | ~10 s — **kept**, see below |

**Occupancy is deliberately still on the build path.** It decides owner-occupier vs
investor, which gates whether printed appraisal material is posted to a tenanted address.
That is a safety interlock, not waste.

**Perceived time ≠ build time.** `BuildingPage.tsx` reveals 20 steps with a minimum hold
each. Once `build_state === "complete"` the hold drops to 220 ms so a fast build is not
followed by slow theatre.

---

## 4. Valuation — two engines, routed by dwelling class

`SlotResolver.working_valuation_range()`:

```
Tier 0  attached dwelling -> Gold_Coast.unit_valuations   (unit engine, cron 04:30)
Tier 1  house -> valuation_data.confidence.range          (comparable-sales engine, cron 02:10)
Tier 1b on-demand engine run (houses only, ~22 s)
Tier 2  exterior evidence
Tier 3  suburb median band
```

⚠ **Attached dwellings never enter the house tiers.** Until 2026-08-14 there was no dwelling
gate and a unit fell through to Tier 3, whose query filtered on bedrooms and *not* property
type — so a 3-bedroom unit was valued against 3-bedroom **houses**. Measured on a real
report: **+37.5%**. Classification uses the shared `shared/dwelling_type.classify_dwelling`,
never a local regex, and `property_type` alone is unreliable (a strata villa is often typed
"House").

⚠ **The unit engine's `publishable` flag is honoured.** Every Burleigh Waters unit currently
fails it; 1,302 carry a point estimate that must not render.

**Coverage:** 87/106 reports (82%) carry a working range. The nightly job picks up a
valuation computed after a report was built (`SlotResolver.refresh_valuation_slot()`) — Tier
0/1 only, so it never synthesises a figure for a report that legitimately has none.

---

## 5. ⚠ The fixture-clone hazard — read before touching the frontend

`stubFromDoc()` in `YourHomePage.tsx` **deep-clones a demo property** (13 Terrace Court,
Merrimac) and overlays what the resolver produced. Every guard is "overlay if we have data",
with no else — so **missing data silently means borrowed data**.

Four instances reached real sellers in three days:

| Date | Leak |
|---|---|
| 08-12 | Hero scarcity claim — a six-bedroom Merrimac line on a four-bedroom Robina home |
| 08-14 | Working range — **$1,900,000–$2,100,000 on 44 of 106 reports**, the demo's number |
| 08-14 | Process tab's "For your home" pane quoting a cost-of-sale; `methodNotes` citing "Merrimac's 46-sale cohort"; market tiles printing Merrimac's counts under the reader's suburb |
| 08-14 | Seasonality — the demo's southern-GC series while the doc held Robina's own |

**`blankPropertyClaims()` now runs before every overlay** and empties each field carrying a
property-specific claim. Anything an overlay does not fill renders as absent.

**If you add a field to the fixture, add it to `blankPropertyClaims()`.** Otherwise it
becomes the fifth instance.

---

## 6. Known gaps

- **Corpus precompute not built.** Build time varies 6–42 s depending on whether the
  valuation was precomputed and whether occupancy needs a live fetch. The off-market engine
  (`15_Off-Market/Page_Redesign_V2/`) already renders a cached bundle in **0.15 s** across
  26,303 properties — that is the pattern to adopt.
- **19 reports have no valuation** — 16 genuinely unvalued, 3 whose subject cannot be matched
  by address.
- **A cadastral-only address has not been tested end to end.** Every verified build had a
  precomputed valuation and good data. That is the case a real off-market seller is most
  likely to be.
- **Valuation engine volatility** — one property moved **+33.8% in 3.5 weeks** from 7 extra
  comparables, against a published ±12.2% band. Logged, not fixed.
- **`case_studies` prose** is absent by design; the card ships data-only.

---

## 7. Related reading

- `Version_1.5/README.md` · `Version_1.5/COMPLETION_REPORT.md` — the build and an honest account of what was and wasn't achieved
- `AI_DEPENDENCY_AUDIT_AND_DETERMINISTIC_STRATEGY.md` — the 16 AI call sites and the plan
- `15_Off-Market/Page_Redesign_V2/` — `fact_bundle.py` → `copy.yaml` → `assemble.py`
- `15_Off-Market/Units/scripts/` — the unit engine, and `check_renderer_consistency.py`
- `16_Valuation/README.md` — constraints any template layer must respect
- `logs/fix-history/2026-08-14.md` — every change this week, with root causes

---

# Version One — what shipped

A nine-tab report: `01 Your Home's Data` · `02 Competition` · `03 Valuation` ·
`04 The Right Buyer` · `05 Process Decisions`, plus Agent, FAQ, Messages and Next Steps.

Code lives at `/home/fields/Feilds_Website/01_Website/src/pages/YourHomePage/`.

**Read first:** `Version_One/README.md` (engineering state) · `Version_One/Design.md` (IA
and design brief) · `Version_One/Content-Plan.md` (copy conventions) ·
`Version_One/Gap_Analysis_11th_Jun/12_MINISITE_PMF_ANALYSIS.md` (the honest verdict).
