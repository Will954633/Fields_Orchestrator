# Q2 2026 Rewrite — Problem Register

**Opened:** 1 August 2026 · **Owner:** Will + Claude
**Purpose:** Every problem identified during the Q2 rewrite context pass, ordered so we can work through them methodically. Update status inline as we go.

**Status key:** `OPEN` · `IN PROGRESS` · `DONE` · `DECIDED` (a judgement call, not a fix)
**Confidence key:** `CONFIRMED` (verified against live data/logs) · `SUSPECTED` (evidence points there, not proven)

---

## P1 — Data truth (blocks writing any copy)

The numbers *are* the story, so nothing gets written until this section closes.

### P1.1 — No canonical "Fields median" · `OPEN` · CONFIRMED
`Gold_Coast.precomputed_indexed_prices` carries two legitimate price series and a summary scalar.
Three of our own documents each picked a different one for the same quarter:

| Doc | Robina | Burleigh Waters | Varsity Lakes | Measure taken |
|---|---|---|---|---|
| Research doc (30 Jul) | $1,456,067 | $1,623,820 | $1,417,960 | single-quarter, 27 Jul freeze |
| Live pipeline (1 Aug) | $1,456,067 | $1,625,976 | $1,403,541 | single-quarter, current |
| Editorial outline (28 Jul) | $1,450,000 | $1,710,000 | $1,350,000 | `rolling_12m_median_price` scalar |
| Rendered PDF (24 Jul) | $1,500,000 | $1,790,000 | $1,484,000 | trailing-12m, 24 Jul vintage |

**Fix:** pick one measure, document it, enforce it across issue + website + research briefs.

### P1.2 — PropRadar calibration corrupts the Burleigh Waters median · `OPEN` · CONFIRMED
**Third and final diagnosis, settled by external validation (REA), 1 Aug.**

realestate.com.au publishes Burleigh Waters at **$1,910,000 on 195 house sales over the preceding
12 months** — the same methodology as our `rolling_12m_median_series`.

| Source | n (12mo) | Median | vs REA |
|---|---|---|---|
| **Ours, raw/uncalibrated** | 143 | **$1,905,500** | **−0.24%** |
| REA | 195 | $1,910,000 | — |
| PropRadar (what we publish) | 240 | $1,710,000 | **−10.5%** |

Two independent samples (n=143, n=195) agree within 0.24%. **Our raw median is correct;
PropRadar's is the outlier.** PropRadar reports 45 *more* house sales than REA at a 10% lower
median, and its `unit_price` for Burleigh Waters is `null` despite 75 recorded unit sales —
its house/unit classification for this suburb is demonstrably broken, so cheaper attached stock
is very likely landing in the house bucket.

Factors: Robina 0.9707, Varsity Lakes 0.9561, **Burleigh Waters 0.9084** — BW is the outlier, so
this is a suburb-specific data fault, not a systematic methodology gap.

**Two compounding errors in `recalibrate_charts.py`:**
1. `:53` `anchor = sum(raws[-4:]) / 4.0` — a **mean of four quarterly medians**, used as a proxy
   for a 12-month median. Not the same statistic. BW: anchor $1,882,500 vs true $1,905,500.
2. The anchor is then compared to a PropRadar median measuring a different population.

**Live impact:** the page publishes Burleigh Waters at $1,625,976; the REA-comparable figure is
**$1,790,000**. Understated ~9% (~$164,000), and propagated to `latest_price`, `baseline_price`
and every quarter in the series.

**Fix direction:** use PropRadar for **counts/completeness** (its strength — settlement-based) and
our own data for **medians** (validated against REA). Stop overwriting `rolling_12m_median_price`.

*(Superseded diagnoses, kept for honesty: (a) "the scalar is stale" — wrong, it is deliberately
overwritten; (b) "the scalar is calibrated and the series is the defect" — wrong, the series is
the one that validates externally.)*

`scripts/propradar/recalibrate_charts.py` (cron `30 5 1 * *`, 30 min after the precompute at
`0 5 1 * *`) rebases our under-captured Domain data to PropRadar's settlement-complete anchor. It
scales `indexed_series[].median_price` and `transaction_count` (`:56-79`) and hard-sets
`rolling_12m_median_price` to PropRadar's own 12-month median (`:80-81`). It **never touches
`rolling_12m_median_series[].rolling_median`**.

Verified — scalar ÷ rolling-series = the calibration factor exactly:

| Suburb | rolling_12m series | scalar | implied factor |
|---|---|---|---|
| Robina | $1,485,000 | $1,450,000 | 0.9764 |
| Burleigh Waters | $1,905,500 | $1,710,000 | 0.8974 |
| Varsity Lakes | $1,400,000 | $1,350,000 | 0.9643 |

So **the scalar is the calibrated number and the series is the defect.** `MedianPriceChart` plots
the calibrated quarterly line and the *uncalibrated* rolling line on the same axes — Burleigh
Waters' rolling line floats ~10% high as pure artefact, live on the source of truth.
**Fix:** apply the calibration factor to `rolling_12m_median_series` in `recalibrate_charts.py`.

### P1.2b — Google and humans see different medians · `OPEN` · CONFIRMED
SSR JSON-LD / FAQ headline uses `indexed_series[last].median_price` (`db.server.ts:552`);
the visible "Current (12m)" tile uses the scalar (`MedianPriceChart.tsx:103,190`). Burleigh
Waters: structured data says $1,625,976, the screen says $1,710,000.

### P1.2c — Is `transaction_count` actually being calibrated? · `OPEN` · SUSPECTED
`recalibrate_charts.py:69-79` claims to scale `transaction_count`, yet the live page still shows
Robina Q2 2026 = 43 sales — the same as the raw series — while PropRadar capture is 61.8%.
Either the scaling isn't landing or it's applied on a different basis. **Goes straight to P1.3.**

### P1.2d — `market-insights` GET has write side-effects · `OPEN` · CONFIRMED
`market-insights.mjs:407-413, 467-478` upserts `absorption_rate_snapshots` on read.

### P1.2e — `precompute_gold_coast_aggregate.py` may never have run · `OPEN` · SUSPECTED
Cron `0 5 2 * *`; no log file exists at its configured path. Writes the `gold_coast` roll-up
`_id`s that `market-insights.mjs:196` falls back to.

### P1.2f — Source-of-truth cadence is MONTHLY, not nightly · `OPEN` · CONFIRMED
All precomputes run 1st of month, 05:00–05:52 AEST. Last run **1 Aug 05:00–05:52** — so the data
behind a Q2 issue is one day old right now. Good timing; but the report must state the cadence.
*(Active listings were flagged as possibly unscheduled — checked, and they are current to
31 July. Not broken.)*

### P1.3 — ANSWERED: published volumes are materially overstated in decline · `CONFIRMED` 1 Aug
The OnTheHouse ingest (`[ONTHEHOUSE-PARALLEL-INGEST]`, 1 Aug 17:10) gives a second transaction
source and settles this. **Domain's capture rate decays for recent quarters:**

| Suburb | Q4 2025 | Q1 2026 | Q2 2026 |
|---|---|---|---|
| Robina | 89% | 39% | 43% |
| Burleigh Waters | 67% | 49% | 57% |
| Varsity Lakes | 106% | 64% | 67% |

`recalibrate_charts.py` applies a **single uniform** `transaction_count` factor (1.72 / 1.69 /
1.60), which assumes capture is constant over time. It is not — so calibration shifts the level
but preserves the decay as if it were a market signal.

**Decline Q4 2025 → Q2 2026, published vs OnTheHouse:**

| Suburb | Published | OnTheHouse |
|---|---|---|
| Robina | 129 → 43 = **−67%** | 84 → 58 = **−31%** |
| Burleigh Waters | 63 → 44 = **−30%** | 55 → 46 = **−16%** |
| Varsity Lakes | 86 → 22 = **−74%** | 51 → 21 = **−59%** |

Volume *is* falling, but roughly **half** as steeply as we publish. And the year-on-year claims
in the Q2 issue and the research doc (Robina 98→43, BW 112→44) rest entirely on Domain data whose
capture decays — **those YoY volume figures are not publishable.** OnTheHouse only reaches back to
Aug 2025, so YoY cannot yet be verified at all; its own Q2 2026 is likely still filling in too.

*(Original entry below, kept for the record.)*
### P1.3-orig — Volume-collapse claim unverified · `SUPERSEDED` · SUSPECTED
Q2 2025 → Q2 2026: Robina 98→43, Burleigh Waters 112→44, Varsity Lakes 53→22. Consistent across
every source — but the decline begins Q1 2026 and deepens into Q2, which is the exact shape
settlement/reporting lag produces. Burleigh Waters Q2 moved n=43→44 between 27 Jul and 1 Aug,
i.e. still filling in. **This blocks the proposed cover.**
**Test:** fill-in curve — compare a fixed quarter's `transaction_count` across vintages
(27 Jul `market_pulse` freeze vs live vs PropRadar reference).

### P1.11 — Dwelling-type filter: fix exists in comps, never carried to market metrics · `OPEN` · CONFIRMED
Unit-style addresses inside `property_type: House` sold records — Robina 19/387 (4.9%),
Burleigh Waters 9/318 (2.8%), Varsity Lakes 27/273 (9.9%). Leaked records are cheap
(median $942k–$1,107k vs house medians $1.3–1.9M), so they drag the median **down 1.1–1.7%**.

**Caveat — the address test over-flags.** OnTheHouse independently types 12/12 of the matched
flagged addresses as "House" too. Many are genuinely detached houses on strata/community title,
which is common in QLD. So this is a comp-quality signal, not proof of misclassification.

**Bigger hole: the `None` bucket.** Sold records with no `property_type` at all — Robina 45,
Burleigh Waters 14, **Varsity Lakes 50**. Silently excluded from every house query; VL loses ~15%
of its sold records invisibly. Silent exclusion is worse than leakage because nothing reports it.

**The asymmetry that matters:**
- `precompute_valuations.py:254-261` — comps use the **unit-numbered address as the strongest
  signal**, `property_type` only as fallback, plus an explicit `misclassified_dwelling` exclusion
  (`:3053`). Correct design. **Comps are protected.**
- `precompute_indexed_price_data.py:212-213` — market metrics filter on the **type field only**.
  No address test. **Market metrics are not protected.**

**Fix:** port `_property_type_bucket()` from the valuation script into the precompute, and make
the `None` bucket a reported number rather than a silent drop.

*Note: leakage pushes medians down 1.1–1.7% while Domain sampling bias pushes them up 1.1–6.8%,
so the two partially cancel. Two errors offsetting is not accuracy — fix both, don't rely on it.*

### P1.4 — Sold-data under-capture 53–66% · `OPEN` · CONFIRMED
`sold_volume_reconciliation`, single doc, 29 Jul: Robina 239/387 = 61.8%; Burleigh Waters
158/240 = 65.8%; Varsity Lakes 109/205 = 53.2%. Volume and months-of-supply are unreliable at
these capture rates; DOM and growth are less affected.

### P1.5 — Bulk Domain history pull never ran · `OPEN` · CONFIRMED
No process running, no `job_runs` heartbeat, no output. VM rebooted 08:04 on 1 Aug, which would
have killed any detached run. Nothing written since the 29 Jul `monthly_sold_refresh`.

### P1.6 — Nightly step 12 reports success while writing zero · `OPEN` · CONFIRMED
Ran 31 Jul 23:14–23:18, exit 0, `"success": true`. Actual output:
`Pass 3 complete: 0 transactions written, 0 new Gold_Coast docs created, 71 no profile page`.
All 71 were **units**, which lack Domain property-profile pages — so this reads as a **scoping
bug** (units fed to a house-profile scraper), not a broken scraper. Confirmed the scraper works:
a live dry-run pulled a real timeline for 1 Aruma Avenue, Burleigh Waters.
**Also:** a step that writes 0 records must not exit 0.

### P1.7 — Orchestrator references a deleted script · `OPEN` · CONFIRMED
`03_For_Sale_Coverage/enrich_property_timeline.py` is deleted from disk (git `D`) while step 12
still points at it. Working sibling: `scripts/refresh_property_timelines.py`.

### P1.8 — Rule 7 violation on the history job · `OPEN` · CONFIRMED
The bulk pull was launched without a `job_run()` wrapper, so there is no record it ever started.
This is precisely the failure class CLAUDE.md Rule 7 exists to close.

### P1.9 — No data-vintage record per issue · `OPEN` · CONFIRMED
The series revises after publication: Burleigh Waters' trailing Q2 median was $1,790,000 at
render (24 Jul) and $1,905,500 today — **6.5% in eight days**. We kept no record of what vintage
we published. The `manifest.json` specified in `strategy/07_production_playbook.md` was never built.

---

## P2 — Editorial architecture (the rewrite itself)

### P2.1 — The Conviction Index leads the cover · `OPEN`
94.4 is unfalsifiable to a reader — they cannot check it against anything they know, in a
category where agents rank third-least-trusted profession in Australia. It asks for trust before
we have earned it. **Direction:** demote to ~p6–7 as "how we scored the quarter"; keep computing
it every quarter (the time series is the moat and the continuity spine). Never on the cover.

### P2.2 — Page order follows our logic, not the reader's · `OPEN`
Current: index → prices → activity → policy → suburbs → evidence → macro.
Reader priority (per the research doc): *have I missed my window?* → *if I sell, can I afford to
move?* → *what is my house worth?* → *who do I trust?*

### P2.3 — Two of the four top reader fears are absent · `OPEN`
Onward-purchase ("I'll sell fine but I can't buy back in") and agent distrust appear **nowhere**
in the eight pages. The most prominent "so what" is the tax spread on p5 — an *investor* issue
for an owner-occupier audience.

### P2.4 — Burleigh Waters "two opposite stories" · `RESOLVED` · CONFIRMED
Not two honest readings — one reading and one artefact.

The "trailing median is accelerating (+5.6%)" claim we printed rests on
`rolling_12m_median_series`, which **P1.2 shows is uncalibrated**. Applying Burleigh Waters'
0.8974 factor collapses it. The claim is an artefact of the missing calibration step.

The **−16% off peak** reading comes from `indexed_series`, which is scaled *uniformly* across
every quarter — so percentage changes are invariant to calibration. That reading is robust.

**Conclusion: the research doc was right and the published PDF was wrong.** Burleigh Waters came
off its Q4 2025 peak. We publish that, plainly. (See P4.4 — this is now a decision about candour,
not about which statistic to trust.)

### P2.5 — The strongest material is buried · `OPEN`
The Camberwell Circuit open on p2 — real sale, real hammer price, real date — is the best thing
in the issue and it sits behind the index.

### P2.6 — The lead number needs selection criteria · `OPEN`
Will's instinct: lead with one prominent number, chosen fresh each issue, and some issues lead
with a sentence instead. Needs documented criteria so it is a decision, not a mood:
(a) the reader can verify it against their own experience; (b) it describes *their position*, not
our cleverness; (c) it needs no definition; (d) it moved meaningfully since last issue.

### P2.7 — No continuity between issues · `OPEN`
Q2 posed three open questions ("which gives first — sellers or buyers?", "can Burleigh Waters
hold?", "the 11 August RBA decision") with nowhere to land. The only continuity present is
continuity of *the index*, not of *the reader's question*.

---

## P3 — Process build (the durable deliverable)

None of these are broken — they don't exist yet. Target: `10_Market_Report/process/`.

| # | Artifact | Purpose | Status |
|---|---|---|---|
| P3.1 | `00_QUARTERLY_PROCESS.md` | Master cycle with dated gates | `OPEN` |
| P3.2 | `01_sentiment_research_brief.md` | Parameterised deep-research prompt, comparable quarter-to-quarter | `OPEN` |
| P3.3 | `02_editorial_council.md` | Agenda for the Will+Claude session that sets the issue | `OPEN` |
| P3.4 | `03_issue_spec.md` (per issue) | Output of the council; the writing contract | `OPEN` |
| P3.5 | `04_evidence_pack.md` | Data lock + case-study selection criteria (chosen to prove a claim, not because we have photos) | `OPEN` |
| P3.6 | `05_continuity_ledger.md` | Claims made + questions left open per issue; next issue grades them | `OPEN` |
| P3.7 | Pre-render QA gate | Editorial rules check + numbers reconciliation across all sources | `OPEN` |

---

## P4 — Decisions needed from Will

| # | Decision | Why it matters |
|---|---|---|
| P4.1 | 8-page Market Pulse or 36-page Quarterly? | `INTEGRATION.md` calls the 36-page canonical; it was re-rendered 1 Aug. Very different amounts of copy. |
| P4.2 | Distribution — printed/posted, emailed PDF, or site-gated? | Determines how hard page one must work. |
| P4.3 | Is Q2 still the right issue to ship? | Data closes 30 Jun; the 11 Aug RBA decision could re-rate the macro frame within days of shipping. |
| P4.4 | How honest on Burleigh Waters? | If the −16% reading leads, we publish a real retreat in our most premium suburb — maximally trust-building, minimally comfortable. |

---

## Suggested order of attack

1. **P4.1 + P4.3** — cheap, and they scope everything downstream.
2. **P1.5–P1.8** — relaunch the history pull correctly (wrapped, scoped to houses, self-reporting). Long-running, so start it early and let it work while we do the rest.
3. **P1.3** — the fill-in curve. Settles whether the volume story is real. Gates the cover.
4. **P1.1 + P1.2 + P1.9** — canonical measure, stale scalar, vintage manifest. Closes data truth.
5. **P3.1–P3.6** — build the process while the data settles.
6. **P2.x** — the rewrite, driven by the issue spec the process produces.
7. **P3.7** — QA gate, then render.
