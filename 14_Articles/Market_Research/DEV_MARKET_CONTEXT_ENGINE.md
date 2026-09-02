# Development Document — Market Context Engine (MCE)

**Status:** Proposal / design. Not built.
**Author:** Ops agent (for Will Simpson)
**Date:** 2026-09-03
**Scope decision (Will, 2026-09-03):** *Evolve* the existing `14_Articles/Market_Research`
engine — do **not** rebuild. Delivery ends at **research + human-reviewed publish** (no
unattended publishing).

---

## 1. What it must deliver (the requirement, restated)

> Scan **national → Brisbane → Gold Coast** property headlines to understand the current
> biggest topics in the market; build **buyer and seller psychology**; then undertake
> **detailed research and analysis of the underlying factors** behind those headline
> topics through both **web analysis and our internal data**; and deliver **comprehensive
> context to our audience in our core three suburbs** (Robina, Varsity Lakes, Burleigh
> Waters).

In one line: **a demand-sensing → psychology → deep-research → suburb-contextualisation
pipeline** that turns "what the market is talking about this fortnight" into cited,
suburb-grounded context our downstream generators can publish.

### The four gaps this closes (vs. what exists today)

| Capability | Today | MCE target |
|---|---|---|
| Topic discovery from headlines | ❌ static hand-curated `topics.json` (8 topics) | ✅ Stage 1 scans national→Brisbane→GC, ranks emerging topics |
| Buyer/seller psychology | ⚠️ separate `homeowner_mindset` brief, not wired in | ✅ Stage 3 folds it in + extends to buyers, per suburb |
| Internal-data join | ⚠️ facts hand-referenced, `data/` empty, README step-1 "to be built" | ✅ Stage 0 pulls live internal + external data into `data/` |
| Per-suburb depth | ⚠️ national/QLD/SA4 level only | ✅ Stage 5 grounds every live topic in the core three |

---

## 2. Design principles (inherited, non-negotiable)

1. **Research once, here; everyone reads from it.** The `market_research_briefs` store
   remains the single source of truth. No downstream generator re-researches. (README §1.)
2. **Internal ground-truth is SUPPLIED, never recalled.** The single hardest lesson from
   `homeowner_mindset` ([UNION-MEDIANS-REVERTED-NIGHTLY]): the researcher LLM is never
   asked to look up our own numbers — Stage 0 hands them over from the live DB with
   reliability flags. External facts are researched; internal facts are joined.
3. **Test hypotheses, don't confirm them.** Every headline premise ("the market turned
   because X") is verified and reported honestly if the evidence is thin. (README rule 2.)
4. **Every claim carries source + date + URL.** Reputable sources only. An unverifiable
   claim is reported as unverifiable, never filled in.
5. **No advice, no forecasts, no single-valuation headlines** (CLAUDE.md Rule 5). MCE
   produces *context*, not recommendations. A "§9 — what we deliberately did NOT conclude"
   honesty block is mandatory on every brief and **outranks** the messaging block.
6. **Self-monitoring with an outcome assertion** (Rule 7 + 7b). Every stage runs under
   `job_run(...)` and RAISES on its zero-output path — a cycle that discovered no topics,
   or refreshed no dossier, is a *failure*, not a quiet success. Never advance a cursor on
   a failed run.
7. **Web research bills the Max subscription**, not metered credit — headless `claude -p`
   with `WebSearch,WebFetch`, `ANTHROPIC_API_KEY`/`CLAUDECODE`/`CLAUDE_CODE_SSE_PORT`
   stripped, gh auth kept. (Proven pattern: `refresh_homeowner_mindset.py`,
   `scripts/samantha/deep_research.py`.)
8. **Child agents get read/research tools only (no Write).** The parent orchestrator
   validates returned text and writes all files — a wrong model turn can never clobber a
   dossier or write unverified copy.
9. **Nothing publishes unattended.** MCE's deliverable is a reviewable brief + draft
   content package; a human ships it. There is deliberately no deploy stage.

---

## 3. Architecture at a glance

```
                        ┌─────────────────────────────────────────────┐
   FORTNIGHTLY CYCLE    │  orchestrator: run_context_cycle.py          │
   (2nd Sunday 12:00)   │  (evolves run_research_cycle.py)             │
                        └─────────────────────────────────────────────┘
        │
        ▼
  Stage 0  DATA PULL ─────────────► data/ (external cache) + internal_pack.json
        │                            [ABS, Cotality, RBA, PropTrack + live Gold_Coast DB]
        ▼
  Stage 1  HEADLINE SCAN ─────────► headlines_raw.json
        │   national → Brisbane → GC  (Max-CLI web agents, one per tier)
        ▼
  Stage 2  TOPIC RANK & SELECT ───► topic_slate.json  (this cycle's ranked live topics)
        │   (novelty × reach × audience-demand × editorial-answerability × suburb-relevance)
        ▼
  Stage 3  PSYCHOLOGY SYNTHESIS ──► psychology_brief.json  (buyer + seller, per suburb)
        │   (folds homeowner_mindset + buyer signals + our lead/behaviour data)
        ▼
  Stage 4  DEEP RESEARCH (per topic) ─► topics/<slug>.md  (evergreen dossier, refreshed)
        │   web analysis + Stage-0 internal join, hypothesis-tested                +
        │                                                  briefs/current/<date>_<slug>.md
        ▼
  Stage 5  SUBURB CONTEXTUALISATION ─► suburb_context/<suburb>_<cycle>.md  (×3)
        │   maps each live topic → Robina / Varsity Lakes / Burleigh Waters evidence
        ▼
  Stage 6  SYNTHESIS & INDEX ─────► market_research_briefs (DB)  +  INDEX.md
        │                            audience_context_pack.json  (for generators)
        ▼
  Stage 7  DRAFT CONTENT (optional) ─► drafts/  (per suburb, per channel — UNPUBLISHED)
        │
        ▼
  Stage 8  QA + SELF-REPORT ──────► job_runs heartbeat + Telegram digest to Will
                                     (raises on zero-output; blocks publish on failed QA)
```

**Cadence:** fortnightly deep cycle (2nd Sunday, reusing the existing even-ISO-week gate),
**plus** a lightweight **weekly headline-watch** (Stage 1–2 only) that can *promote* a
breaking topic into an off-cycle deep run if its rank spikes (e.g. an RBA decision, a
budget/legislation event). RBA-triggered refresh already exists (`rba_mindset_reminder.py`)
— MCE subscribes to the same signal.

---

## 4. Stage-by-stage specification

Each stage lists: **inputs → process → data sources → output artifact → zero-output
assertion (Rule 7b)**.

### Stage 0 — Data Pull (the internal + external ground-truth pack)

**Why first:** so no later LLM stage ever *recalls* a number. This is the structural fix
from the mindset-brief incident.

**Process**
- **External data pullers** (deterministic, cached to `data/` with fetch date + source):
  - ABS Data API (SDMX/JSON) — see §5 for series IDs.
  - RBA statistical tables (F-series rates, cash rate) + latest media release URL.
  - Cotality/CoreLogic + PropTrack monthly release figures (scrape release page /
    ingest published tables — values only, cited).
- **Internal data pack** (`internal_pack.json`) — pulled live from our own DBs, with
  reliability flags, for the core three suburbs:
  - `Gold_Coast.<suburb>`: live listing count (`listing_status:"for_sale"`), sold count &
    median (`listing_status:"sold"`), days-on-market (`days_on_market`, NOT
    `days_on_domain`), months-of-supply estimate.
  - **Union-median indexed prices** from `precomputed_indexed_prices` **with the
    `reliable` flag per quarter** — never restate a suburb % move whose quarter is
    `reliable:false` ([UNION-MEDIANS-REVERTED-NIGHTLY], `union_median_pipeline`).
  - `valuation_data` coverage / current reconciled-valuation distribution per suburb
    (design-envelope caveats attached — $1M–$2M band; flag directional-only).
  - PropRadar settlements (for capture-rate honesty — we under-capture; flag it).
  - **Audience-demand signals:** `search_scored_questions` / `search_intent_analysis`
    (what owners are actually googling), GSC top queries per suburb.
  - **Audience-behaviour signals:** PostHog (property-page dwell, `/analyse-your-home`
    funnel, `/for-sale` engagement), lead volume & questions from FB leadforms and
    `address_entry_attempts` (who searched what and abandoned).

**Data sources:** see §5 table.

**Output:** `data/<cycle>/external_*.json` (cached, cited) + `data/<cycle>/internal_pack.json`.

**Zero-output assertion:** if the internal pack has zero live listings across all three
suburbs, or `precomputed_indexed_prices` returns nothing → RAISE (scrape/pipeline is
broken, not "market is empty"). Distinguish empty-queue from could-not-fetch (Rule 7b.1).

---

### Stage 1 — Headline Scan (national → Brisbane → Gold Coast)

**Process:** three parallel Max-CLI research agents, one per geographic tier, each returning
a **structured list of current headline topics** (not prose) — headline, outlet, date, URL,
one-line gist, and which underlying theme it maps to.
- **National agent:** AU macro-property headlines this fortnight.
- **Brisbane / QLD agent:** state-level — QGSO, REIQ, Brisbane press, QLD budget/policy.
- **Gold Coast agent:** local — Gold Coast Bulletin, myGC, local REIQ/agent commentary,
  major local listings/developments; **cross-check against our own scraped new-listing
  flow** so "what's happening on the ground" is grounded, not just press.

Each agent is told: *report what is being discussed and how loudly; do NOT assess whether
it's true yet (that's Stage 4); every item carries a URL + date.*

**Data sources:** §5 (Headlines & press block).

**Output:** `headlines_raw.json` — `[{tier, headline, outlet, url, date, gist, theme_guess}]`.

**Zero-output assertion:** if any tier returns zero items, RAISE — the web tools or a
source block is broken. (Three empty tiers ≠ "quiet news week".) Log per-tier counts.

---

### Stage 2 — Topic Ranking & Selection

**Process:** deterministic scorer (Python, not an LLM — auditable) collapses raw headlines
into candidate **topics** and ranks them. Score per topic:

```
score = w1·reach        (how many tiers + outlets carry it, weighted GC>Bris>national)
      + w2·novelty      (new vs. already a mature dossier — decays if unchanged since last cycle)
      + w3·audience_demand   (matches a rising query in search_scored_questions / GSC)
      + w4·editorial_answerability  (can we answer it with DATA under Rule 5? advice-only Qs downweighted)
      + w5·suburb_relevance  (does it plausibly touch the core three?)
      - penalty·staleness    (topic already fresh this cycle)
```

The slate = **top N** (start N≈4–6/cycle; cost ≈ $1–2/topic) **plus** any **standing
evergreen topics** that must always stay current (interest-rates, migration,
leading-indicators — the ones the subject-letter and Market Report depend on). So the
system is **demand-driven at the margin, stable at the core** — new topics get promoted in,
but the load-bearing dossiers never silently expire.

`topics.json` becomes an **output** of this stage (auto-managed `active`/`backlog`), not a
hand-edited input — though Will can pin/veto any slug.

**Output:** `topic_slate.json` — ranked, with scores, provenance (which headlines drove it),
and `is_standing` / `is_promoted` flags. A human-readable one-pager goes to Will in the
Stage-8 digest **before** the expensive Stage-4 runs, so a bad slate can be caught early.

**Zero-output assertion:** empty slate → RAISE (either the scorer is misconfigured or Stage
1 fed it nothing). Standing topics guarantee the slate is never legitimately empty.

---

### Stage 3 — Psychology Synthesis (buyer + seller, per suburb)

**Process:** one research+synthesis pass that produces a **current psychological read** of
both sides of our audience, grounded in *measured* signals not vibes:
- **Seller side:** fold in the existing `homeowner_mindset` brief (its §9 honesty block is
  binding) + refresh against this cycle's rate/sentiment/news context.
- **Buyer side (new):** built from Westpac-Melbourne Institute "time to buy a dwelling" +
  house-price-expectations indices, ABS lending/first-home-buyer data, **and our own
  first-party evidence** — `/for-sale` and `/discover` engagement, buyer-brief lead
  questions, `address_entry_attempts`, search intent. What are buyers hesitating on? What
  are they searching?
- Behavioural-economics framing from the in-house library (`12_Marketing/Buyer_Psychology/`
  — anchoring, endowment effect, ambiguity aversion, active-vs-passive buyers) applied to
  *interpret* the signals, cited, never invented.

**Output:** `psychology_brief.json` + `briefs/current/<date>_psychology.md` — separate
buyer and seller reads, **per suburb where the data supports it**, each with a §9
"what we did NOT conclude" block. Feeds Stage 4 (so topics are researched *through* the lens
of what the audience is actually anxious about) and Stage 5.

**Zero-output assertion:** if neither the mindset brief nor first-party signals are
available → RAISE. A psychology brief with no evidence base is worse than none.

---

### Stage 4 — Deep Research per topic (web + internal join)

**Process:** for each topic on the slate, one headless `claude -p` deep pass (Max, web
tools, read-only). The prompt is assembled by the **parent** and contains:
- the topic `focus` (from `topic_slate.json`),
- the **current dossier** (`topics/<slug>.md`) to refresh in place,
- the **Stage-0 internal pack** (our numbers, handed over with reliability flags),
- the **shared honesty rules** (§2 above) + the mandatory §9 block,
- an instruction to **rank the underlying drivers** behind the headline and **test the
  headline's premise** against evidence.

The child returns the full refreshed dossier markdown; the parent validates (non-empty,
has an "as at" date, has §9, sources present) → snapshots prior into `briefs/archive/<cycle>/`
→ writes `topics/<slug>.md` + dated `briefs/current/`.

**Output:** refreshed evergreen `topics/<slug>.md` (one per topic) + point-in-time
`briefs/current/<date>_<slug>.md`.

**Zero-output assertion:** any topic returning empty/invalid text is recorded as a
per-topic failure with its error text (never silently dropped); if **all** topics fail →
RAISE. Never advance the cycle watermark for a failed topic (Rule 7b.2) — it re-runs next
cycle from the un-refreshed dossier.

---

### Stage 5 — Suburb Contextualisation (the core three)

**Process:** for each of Robina / Varsity Lakes / Burleigh Waters, one synthesis pass that
answers: *given this cycle's live topics + psychology + our internal suburb data, what is
the honest, data-grounded context for a homeowner/buyer HERE?* This is where national/QLD
themes are translated into local evidence — e.g. "national upper-quartile rate-sensitivity"
becomes "Burleigh Waters sits in the tier most affected; here's our local sold/DOM data,
flagged for capture rate."

Explicitly bounded by the **valuation design envelope** ($1M–$2M; suppress point figures
outside it), the **no-single-valuation-in-headlines** rule, and the union-median
reliability flags.

**Output:** `suburb_context/<suburb>_<cycle>.md` (×3) — the "comprehensive context to our
audience in our core three suburbs" deliverable. Each cites its internal + external sources
and carries the §9 block.

**Zero-output assertion:** a suburb with live listings in the internal pack but zero
contextual output → RAISE (synthesis failed, data exists).

---

### Stage 6 — Synthesis & Index

**Process:** deterministic. Index every dossier, brief, psychology read and suburb-context
file into **`system_monitor.market_research_briefs`** in the existing contract:
`{topic, cycle, as_at, summary, findings:[{claim, source, date, url, confidence}],
suburb?, kind: dossier|brief|psychology|suburb_context, supersedes, source_files:[…]}`.
Regenerate `INDEX.md`. Build **`audience_context_pack.json`** — the flattened, query-ready
bundle a generator reads to get "everything current for suburb X" in one call.

**Output:** updated DB collection + `INDEX.md` + `audience_context_pack.json`.

**Zero-output assertion:** index write affecting 0 documents when briefs exist on disk →
RAISE (indexer broken).

---

### Stage 7 — Draft Content (optional, UNPUBLISHED)

**Process:** with Will's per-cycle go-ahead, generate **draft** audience content per suburb
per channel (Market Intelligence article, subject-letter angle, FB/organic post) from
`audience_context_pack.json`. Strictly draft — written to `drafts/`, never pushed. Runs
under the same Rule-5 gate; a fact-check pass verifies every $ claim points to a page with
methodology + confidence disclaimer.

**Output:** `drafts/<suburb>/<channel>_<date>.md` — reviewable, unpublished.

**Zero-output assertion:** n/a (opt-in stage; skip cleanly if not requested).

---

### Stage 8 — QA + Self-Report

**Process:**
- **Automated QA gate:** every brief has an "as at" date, a §9 block, ≥1 sourced finding
  per claim, no forbidden words (Rule 5 list), no single-valuation headline, no internal
  figure drawn from a `reliable:false` quarter. Fail → block Stage 7 + flag in digest.
- **Self-report** via `job_run("market_context_cycle", cadence_hours=…, title=…)` with
  metrics `{headlines, topics_scored, topics_refreshed, suburbs_done, briefs_indexed}`.
  **RAISE if `topics_refreshed == 0`** (Rule 7b).
- **Telegram digest to Will (@WillFieldsBot):** the ranked slate, what refreshed, the three
  suburb-context one-pagers, any QA failures, and a link to review drafts.

**Output:** heartbeat row on the **Fields Systems Health** sheet (Process Registry) +
Telegram digest.

---

## 5. Recommended data sources

### Market data (values — cited, cached to `data/`)

| Source | What | Access | Reliability |
|---|---|---|---|
| **ABS Data API** (SDMX-JSON) | CPI, WPI (wages), Monthly Household Spending Indicator, Lending Indicators, Building Approvals, Regional Population, Regional Internal Migration Estimates | REST API, no key | ★★★★★ official |
| **RBA** | Cash rate (F-tables), media releases, Statement on Monetary Policy | Stat tables (CSV) + release pages | ★★★★★ official |
| **Cotality / CoreLogic** | Daily & monthly Home Value Index, vendor discount, days-on-market, clearance, by capital + SA4 | Published release pages / RP Data if licensed | ★★★★☆ industry std |
| **PropTrack (REA)** | Monthly home price index, listings, market outlook reports | Published reports | ★★★★☆ |
| **Domain Research** | House Price Report, monthly rental/vacancy | Published reports | ★★★☆☆ (vendor) |
| **QGSO** (QLD Gov Statistician) | QLD + Gold Coast SA4 population, migration, dwelling data | Published tables | ★★★★★ official state |
| **REIQ** | QLD quarterly median house/unit prices by LGA/suburb | Quarterly report | ★★★☆☆ |
| **Westpac–Melbourne Institute** | Consumer Sentiment, House Price Expectations, "Time to buy a dwelling" | Monthly release | ★★★★☆ (sentiment std) |

### Headlines & press (Stage 1 — topical, not authoritative)

| Tier | Sources |
|---|---|
| National | AFR Property, The Australian, ABC News business/property, news.com.au property, Guardian AU, Cotality/PropTrack news blogs |
| Brisbane/QLD | Brisbane Times, Courier-Mail, QGSO releases, REIQ news, QLD Treasury/budget |
| Gold Coast | Gold Coast Bulletin, myGC, local REIQ/agent commentary, council development notices, our own scraped new-listing flow (Domain via pipeline) |

### Internal (Stage 0 `internal_pack.json` — SUPPLIED, never recalled)

| Store | What | Rule/caveat |
|---|---|---|
| `Gold_Coast.<suburb>` | live listings, sold, DOM, months-of-supply | filter `listing_status`; `days_on_market` not `days_on_domain` |
| `precomputed_indexed_prices` | union-median indexed price series | **honour `reliable` flag per quarter** |
| `valuation_data` on property docs | reconciled valuations, coverage | **design envelope $1M–$2M**; suppress outside |
| PropRadar settlements | ground-truth sold volume | we under-capture — flag capture rate |
| `search_scored_questions` / `search_intent_analysis` | audience demand (what they google) | drives Stage 2 ranking |
| GSC (Search Console) | top queries per suburb page | re-authed feed |
| PostHog | on-site behaviour, funnel drop-off | audience psychology evidence |
| FB leadforms / `address_entry_attempts` | buyer/seller questions, abandons | first-party psychology signal |
| `homeowner_mindset` brief | seller psychology base | §9 binding |
| `12_Marketing/Buyer_Psychology/` | behavioural-econ framing library | cite, never invent |

---

## 6. Data model (new/changed)

- **`system_monitor.market_research_briefs`** (exists — extend): add `kind`
  (`dossier|brief|psychology|suburb_context`), optional `suburb`, `drivers_ranked[]`,
  `premise_tested{claim, verdict, evidence}`.
- **`system_monitor.mce_topic_slate`** (new): one doc per cycle — the ranked slate + scores
  + headline provenance, so topic selection is auditable over time.
- **`system_monitor.mce_headlines`** (new, optional): raw headline scan per cycle, for
  trend-over-time ("what was loud when").
- **`job_runs`**: `market_context_cycle` heartbeat (cadence ≈ fortnightly = 336h; STALE at
  ×1.5). Weekly headline-watch registers separately.

File layout (under `14_Articles/Market_Research/`, evolving the existing tree):
```
scripts/run_context_cycle.py        ← orchestrator (evolves run_research_cycle.py)
scripts/stage0_data_pull.py         ← external pullers + internal_pack builder
scripts/stage1_headline_scan.py     ← 3-tier Max-CLI headline agents
scripts/stage2_topic_rank.py        ← deterministic scorer → topic_slate.json
scripts/stage3_psychology.py        ← buyer+seller synthesis
scripts/stage4_deep_research.py     ← per-topic dossier refresh (mostly exists)
scripts/stage5_suburb_context.py    ← core-three contextualisation
scripts/stage6_index.py             ← DB index + audience_context_pack.json
scripts/qa_gate.py                  ← Rule-5 / honesty / reliability checks
data/<cycle>/                       ← cached external + internal_pack.json
topics/ briefs/ suburb_context/ drafts/   ← outputs
```

---

## 7. Orchestration & cadence

- **Fortnightly deep cycle:** `run_context_cycle.py`, cron `0 12 * * 0`, no-ops on odd ISO
  weeks (reuse existing `_is_on_week`). Runs Stages 0–8. ~$5–15/cycle on Max (research is
  subscription; only data pulls / any metered calls cost).
- **Weekly headline-watch:** cron on the off-Sunday, Stages 0(light)–2 only. If a topic's
  rank spikes past a threshold (breaking policy, RBA move), it **promotes** an off-cycle
  deep run for just that topic and pings Will.
- **RBA trigger:** subscribe to `rba_mindset_reminder.py`'s signal — an RBA decision forces
  Stage 3 (psychology) + the interest-rates dossier to refresh next day, regardless of week
  parity.

All under `job_run`, all self-registering on the health board.

---

## 8. Guardrails & failure modes (explicit)

| Risk | Control |
|---|---|
| LLM restates a wrong internal number | Stage 0 supplies all internal figures; prompt forbids recalling suburb stats ([UNION-MEDIANS-REVERTED-NIGHTLY]) |
| Stale figure from a bad quarter | `reliable` flag honoured in pack + QA gate rejects it |
| Valuation outside model envelope | design-envelope suppression enforced in Stage 5 + QA |
| Advice/prediction leaks to audience | Rule-5 word/claim QA gate; §9 outranks messaging; nothing auto-publishes |
| Silent zero-output | Rule 7b assertion at every stage; RAISE not warn |
| Watermark advanced on failure | per-topic failure isolation; cursor only advances on validated write |
| Hallucinated source/paper | child gets read-only web tools; every claim needs a live URL; QA rejects sourceless claims |
| Cost creep as topics grow | slate capped at N/cycle + standing-topic list; cost logged per topic |
| Under-capture read as "market quiet" | PropRadar cross-check + capture-rate flag in pack |

---

## 9. Build phases (recommended order)

**Phase 0 — foundations (reuse what exists).** Stage 4 already works (`run_research_cycle`).
Build **Stage 0** first (the internal+external data pack) — it's the structural safeguard
everything else depends on, and it's the README's long-standing "to be built" gap. *Output:
`internal_pack.json` proven against live DB for the three suburbs.*

**Phase 1 — topic discovery.** Stages 1–2 (headline scan + scorer). Wire `search_scored_questions`
into the rank. Ship the **slate one-pager to Will** and let him pin/veto for a few cycles
before it drives spend. *Output: auto-generated `topic_slate.json` reviewed by Will.*

**Phase 2 — psychology + suburb layers.** Stage 3 (fold in mindset + buyer signals) and
Stage 5 (core-three contextualisation). *Output: `psychology_brief.md` + 3 suburb-context
files per cycle.*

**Phase 3 — index + digest.** Stage 6 + Stage 8 (audience_context_pack + Telegram digest +
health-board heartbeat). Now downstream generators can consume it. *Output: queryable
context pack + weekly visibility.*

**Phase 4 — draft content (opt-in).** Stage 7. Human-reviewed publish only. *Output:
reviewable drafts per suburb/channel.*

**Phase 5 — weekly watch + promotion.** The off-cycle headline-watch and breaking-topic
promotion. *Output: responsiveness to events between fortnightly cycles.*

Each phase is independently useful and shippable — Phase 0 alone closes the biggest
integrity gap; Phases 1–2 deliver the requirement's core ("headlines → psychology →
suburb context"); Phases 3–5 add reach and responsiveness.

---

## 10. Open questions for Will

1. **Topic slate authority:** fully auto-selected, or Will approves the slate each cycle
   before deep research spends? (Recommended: approve for the first ~3 cycles, then
   auto with veto.)
2. **Licensed data:** do we have/ want an RP Data (Cotality) or PropTrack data licence for
   clean programmatic figures, or stay on published-release scraping + citation?
3. **N per cycle:** starting number of promoted topics (recommend 4) on top of ~3 standing.
4. **Draft content (Phase 4):** in scope now, or hold until the research layer is trusted?
5. **Buyer psychology first-party depth:** OK to lean on PostHog + leadform questions +
   `address_entry_attempts` as the buyer-side evidence base, given small volumes?

---

*This document evolves the Market Research Engine; it does not replace it. `run_research_cycle.py`,
the `topics/`+`briefs/` structure, and `market_research_briefs` are retained and extended.
References: `14_Articles/Market_Research/README.md`, `scripts/refresh_homeowner_mindset.py`,
`CONTENT_ENGINE_SCOPING.md`, CLAUDE.md Rules 5/7/7b/8/9.*
</content>
</invoke>
