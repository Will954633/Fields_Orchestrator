# CLAUDE.md — Fields Estate VM Agent

Working directory: `/home/fields/Fields_Orchestrator`

---

## Mandatory Rules

These rules apply to EVERY session. They are not optional.

### 1. Fix History Logging

After every bug fix, script repair, or code change — write a log entry.

- **Location:** `logs/fix-history/YYYY-MM-DD.md` (AEST date)
- **Format:**
  ```
  ## [PROBLEM-ID] Short description — HH:MM AEST
  **Symptom:** What was broken.
  **Root cause:** Why it was broken.
  **Fix:** What you changed and why.
  **Files:** List of files modified.
  **Recurrence:** First / Nth (check: grep -h "^## \[" logs/fix-history/*.md | sed 's/ — .*//' | sort | uniq -d)
  ```
- At session start, read the last 2-3 fix-history files to spot recurring issues.

### 2. Push All Code to GitHub

GitHub is disaster recovery. No change is complete until pushed. Code that only exists on the VM is not safe.

- **Orchestrator files** → `Will954633/Fields_Orchestrator`
- **Website files** → `Will954633/Website_Version_Feb_2026`
- **Automation files** → `Will954633/fields-automation`
- **Never push:** `.env`, credentials, `node_modules/`, `__pycache__/`, logs, `config/settings.yaml` (contains Cosmos URI)
- **git push hangs on this VM** — always use `gh api`:
  ```bash
  # Update existing file:
  SHA=$(gh api 'repos/OWNER/REPO/contents/PATH' --jq '.sha')
  CONTENT=$(base64 -w0 < /local/path/to/file)
  gh api 'repos/OWNER/REPO/contents/PATH' \
    --method PUT --field message="description" --field content="$CONTENT" --field sha="$SHA"

  # New file (no sha):
  CONTENT=$(base64 -w0 < /local/path/to/file)
  gh api 'repos/OWNER/REPO/contents/PATH' \
    --method PUT --field message="add: description" --field content="$CONTENT"
  ```
- For large files (>100KB), use Python to build JSON payload + `--input`:
  ```bash
  python3 -c "import json,base64; ..." > /tmp/payload.json
  gh api 'repos/OWNER/REPO/contents/PATH' --method PUT --input /tmp/payload.json
  ```

### 3. Ad Decision Logging

Every Facebook or Google Ads campaign create/modify/pause/enable/delete → write to `system_monitor.ad_decisions`:
```python
{"date": "YYYY-MM-DD", "type": "new_campaign|pause|enable|budget_change|...",
 "title": "Short description", "hypothesis": "Why we expect this to work",
 "findings": ["Data points"], "data_snapshot": {}, "tags": ["google_ads"],
 "reasoning": "Decision rationale", "created_at": "ISO timestamp"}
```

### 4. Website Change Logging & Visual Verification

After pushing any website file:
1. Log deploy: `python3 scripts/website-deploy-tracker.py log --commit SHA --files "..." --message "..."`
2. If testable: `python3 scripts/website-change-log.py log --title "..." --type TYPE --hypothesis "..." --files "..." --pages "/..." --commit SHA`
3. Screenshot affected pages: `node scripts/site-inspector.js --url /AFFECTED_PAGE`
4. Read the screenshot PNG to verify rendering (multimodal vision)
5. Check console.log for JS errors, network-errors.log for failed API calls

### 5. Editorial Content Rules

All public-facing content (articles, Facebook posts, chart narratives, market summaries):
- **No advice:** NEVER tell readers what to do. No "you should sell", "consider buying", "now is a good time". Data only — reader draws conclusions. Liability risk.
- **No predictions:** Report indicators, use conditional language ("if X, data suggests Y"), never "prices will fall".
- **No single valuation in headlines:** Use comparable ranges, not single figures. Single figures OK inside Valuation Guide tab.
- **Value framing:** Every property trade-off is value, not a flaw. A seller should read our content and think we'd position their property honestly.
- **Factual accuracy:** Always cite data source + limitations. Exact transaction prices (never rounded). Verify "all/none/every" claims.
- **Valuation data in Facebook content (updated 2026-07-27):** We now back our valuation data publicly in Facebook **ads** — because we already publish it on-site. Allowed: comparable **ranges** and **gaps/savings** (differences, e.g. "$98K hiding in plain sight", "comps say $1.75M–$1.98M"). Still forbidden: a **single-property valuation figure** stated as the home's worth in a headline (the "No single valuation in headlines" rule above still stands). **Mandatory pre-flight:** any ad carrying a $ claim must point to a landing page that visibly shows the valuation methodology + confidence disclaimer (property pages already do; `/for-sale-v3` needs a one-line disclaimer added). Organic FB posts remain conservative unless Will says otherwise.
- **Forbidden words:** "stunning", "nestled", "boasting", "rare opportunity", "robust market"
- **Number format:** `$1,250,000` not "$1.25m", suburbs always capitalised

### 6. Market Pulse / Market Metrics Content Verification

After writing or editing ANY `system_monitor.market_pulse` content (summaries, `data_snapshot`, or `narrative.pillars`):
1. Run `python3 scripts/verify_market_metrics_live.py` (or `--suburb X --category Y` for a targeted re-check) — fetches the actual live rendered page via headless browser (client-fetched data included, not just SSR) and saves the full visible text per suburb/category.
2. **Read every saved file.** Check for internal consistency (the same stat — e.g. absorption rate, median price — shown differently in different sections of the SAME page) and staleness (dates/quarters that don't match the latest data). Do not just check the API response or the fields you personally wrote — a `market_pulse` document has multiple content layers (`summary`, `data_snapshot`, `narrative.pillars`) that can each go stale independently since a partial `$set` write only touches the fields it names.
3. Fix anything found, re-run the verification, confirm clean before considering the task done.

**Why this is mandatory, not optional:** on 2026-07-23, a full Market Pulse rewrite fixed the narrative text and confirmed it live via the API — but a THIRD content field (`narrative.pillars`, holding separate long-form AI-written paragraphs) was never touched, stayed stale since 2026-07-03, and produced a live page showing three different absorption-rate figures contradicting each other and citing quarters a year out of date. It was only caught because the user manually copy-pasted the entire rendered page back into the session. This step exists so that doesn't have to happen manually again.

### 7. Self-Monitoring for Every Ongoing Process (No Silent Failures)

Whenever you create a **new script/process/system that runs on an ongoing basis** (any cron job, systemd daemon, scheduled/looping task, or anything expected to run again on a schedule), it MUST self-report its status so it can never fail silently. This is not optional and applies the moment the process is created — not "later".

**How (use the shared helper — do not reinvent):**
```python
from job_status import job_run   # scripts/job_status.py
with job_run("my_process", cadence_hours=24, title="Human-Readable Name") as beat:
    ...do the work...
    beat.detail  = "one-line success summary"      # optional
    beat.metrics = {"rows": 123, "indexed_pct": 62}  # optional
# clean exit -> records status=success; ANY exception -> records status=error
# (with traceback) and re-raises. Passing cadence_hours SELF-REGISTERS the job.
```
Passing `cadence_hours` writes a `self_registered` heartbeat to `system_monitor.job_runs`, which the generic `collect_self_reported_jobs` collector in `scripts/main_site_health_check.py` renders **automatically** on the **"Fields Systems Health"** sheet (Process Registry page) — `https://docs.google.com/spreadsheets/d/1Oa7uZv0shzsxftDYJJ3WErxhr7OZMf_SOxRFawbSgTk/edit`. **OK** = ran within cadence; **STALE** = last run older than `cadence_hours × 1.5` (cron stopped firing); **ERROR** = last run raised. No bespoke renderer or sheet-auth code per script — the one call is the whole contract.

**⚠ 7b. THE HEARTBEAT MUST ASSERT AN OUTCOME, NOT MERELY THAT NOTHING THREW.**

`job_run` records success on any clean exit. That is not enough: a job which runs to completion having
achieved **nothing** is indistinguishable from one that worked. So for every ongoing process, identify
its **zero-output path** and `raise` on it.

```python
with job_run("my_process", cadence_hours=24, title="…") as beat:
    result = do_the_work()
    beat.metrics = {"processed": result.n, "failures": len(result.failed)}
    if result.n == 0 and work_was_expected:      # <-- the assertion
        raise RuntimeError("processed 0 items; upstream is broken, not empty")
    beat.detail = f"{result.n} processed"
```

Three rules that follow from it:

1. **Distinguish "no work to do" from "could not do the work."** An empty queue is success. An empty
   *result* where input existed is failure. If your code cannot tell these apart, that is the bug —
   fix it before the heartbeat.
2. **Never advance a watermark / cursor / `last_run` on a failed run.** Doing so makes one night's
   failure permanent, because the next run's "since last time" window excludes everything the failed
   run dropped.
3. **Record the error text.** A handler that returns `{"status": "error"}` and a caller that counts only
   successes throws away the one thing needed to diagnose it.

**Checklist when shipping any ongoing process:**
1. Wrap the run body in `job_run(name, cadence_hours=…, title=…)` (or, if a plain function fits better, call `record_job_result(name, "success"/"error", cadence_hours=…, …)` on both paths).
2. **Add the outcome assertion (7b)** — name the zero-output path and raise on it.
3. **Load your own environment.** Call `load_env()` in the script rather than trusting the caller; a cron line missing `set -a` exports nothing, and `shared.db` will still connect via `config/settings.yaml` so the job looks healthy while every credential-dependent call fails.
4. **Run it once at creation** so a real heartbeat exists (a job that never ran even once has no row — the first run seeds it; the wrapper records even a failed first run).
5. Verify it appears on the Process Registry page of the Systems Health sheet before considering the task done.
6. If it warrants a richer, dedicated view (like a data dashboard), still keep the heartbeat — the health sheet is the single "is everything running?" board.

**Why this is mandatory, not optional:** we have repeatedly had processes die silently and go unnoticed for days-to-weeks (the daily sitemap push failing every day 2026-07-20→22; three GitHub Actions failing for up to 5 weeks; the lead worklist frozen 9 days). Every such incident was invisible because the process had no self-check.

**And why 7b exists:** on 2026-08-07 an audit found three live jobs that had a heartbeat and were *still* invisible, because each reported success while doing nothing. `build_listed_property` recorded `"queue drained"` through **11 consecutive total failures** for a week (`[BUILDER-ENV-EXPORT-GAP]`). `google_indexing submit-new` submitted **0 URLs on 9 straight nights — 757 dropped** — discarded the API error, and advanced its watermark each time so every failed batch became permanently unrecoverable (`[INDEXING-SILENT-ZERO]`). `offmarket_intel_poller` swallowed sub-resolver exceptions, wrote `status: "done"`, cleared the error field and never retried, leaving 231 public deck pages permanently missing content the database claims completed. Rule 7 alone did not catch any of the three. 7b is the part that does.

### 8. Never Infer Absence From a Guessed Field Name

**A query returning zero is evidence about the name you typed, not about the data.**
Before writing *or reporting* any claim that data is missing — "no aerials", "nothing has
coordinates", "that field is empty" — look at what the documents actually contain.

```bash
# START HERE. Searches every database, and expands your word into the vocabulary
# THIS schema uses (aerial -> satellite, photo -> image, coords -> georeference).
python3 scripts/db_fields.py --find aerial

# Is this exact path real? Prints fill count; on zero, prints what DOES exist.
python3 scripts/db_fields.py Gold_Coast robina --check aerial_image_url

# Every field in one collection, with fill counts, scoped to live listings.
python3 scripts/db_fields.py Gold_Coast robina --grep image \
    --query '{"listing_status": "for_sale"}'
```

Rules that follow:

1. **Never put a field name into a query from memory or intuition.** Confirm it first.
   Plausible-sounding names — `aerial_image_url`, `image_url`, `latitude` — are exactly
   the ones that return zero while the data sits there under another name.
2. **Do not grep the index for your own word and stop.** `grep -i aerial
   SCHEMA_PATHS.tsv` returns **one irrelevant hit**; the 14,531 aerials live under
   `satellite_analysis.satellite_image_url`. A literal search for your own guess just
   confirms your own assumption. Use `--find`, which expands the vocabulary.
3. **Absence from `SCHEMA_SNAPSHOT.md` proves nothing.** That file is **top-level fields
   only**. Nested paths — `satellite_analysis.satellite_image_url`,
   `transactions[].price` — are in `SCHEMA_PATHS.tsv`, one line each, all depths, with a
   fill count. Both are regenerated daily by `generate_schema_snapshot.py`.
4. **Report a zero as a wrong name, not as missing data.** Say "there is no field called
   X — the related paths are A, B, C". Never "this data does not exist" — that is a
   claim you have not tested.
5. **Scope the sample.** `Gold_Coast.robina` is ~12,000 documents, mostly cadastral
   stubs; a field on every live listing still shows single-digit fill against the whole
   collection. Low fill is not absence either — pass `--query`.

**Why this is mandatory:** on 2026-08-09 a query for `aerial_image_url` returned zero and
was reported as "no aerials exist in the database". **14,531 documents had one** — the
guessed name had simply never existed. The safeguard that should have caught it,
`SCHEMA_SNAPSHOT.md`, could not: it sampled the **first 5 documents** of each collection
(the oldest, all one shape) and walked only the top level, so it listed **75 fields for
`Gold_Coast.robina`, where live listings carry 233 top-level keys and 2,523 total paths**
— and the omission was biased toward precisely the enrichment fields being asked about.
Both halves are fixed now (`shared/doc_shape.py`: random `$sample`, full recursion
through nested objects and arrays, a fill count on every path), but tooling only helps if
it runs *before* the conclusion is written. See `logs/fix-history/2026-08-09.md`
`[FIELD-NAME-GUESS-FALSE-ABSENCE]`.

This is Rule 7b applied to reads: **an empty result must assert an outcome, not merely
fail to throw.** "No documents matched" and "I asked the wrong question" produce the
identical output, and only one of them is an answer.

### 9. Never Name Parallelisable Work Without Dispatching It

**Work you identify but do not act on dies with the session.** When you notice something
that is (a) independent of the current thread, (b) well-bounded, and (c) not blocked on a
decision from Will — dispatch it. Do not append it to a list of things you found and
didn't touch.

Never end a turn having *named* such work without either dispatching it or saying, in one
line, why you didn't. "Two live defects I found but haven't touched" is the failure this
rule exists to stop: both were independent, both were bounded, and one of them was worth
more traffic than the feature work it was mentioned in passing beside.

**Two tiers — pick by whether it must outlive the session:**

1. **In-session (default).** Fire background agents in a single message so they run
   concurrently and report back into this transcript. Right for anything that finishes
   inside the session and informs what you're currently doing.

2. **Out-of-session — `scripts/spawn_task.py`.** Queues a brief onto
   `system_monitor.spawned_tasks`; `spawn_worker.py` runs it as a separate headless
   `claude -p` session on Max (concurrency 2) and reports to Will via Telegram. Right when
   the work should survive the session, deserves fresh context, or is not yours to finish.
   Pick up prior handoffs with `python3 scripts/spawn_status.py --pending`.

**⚠ The brief is the whole game, and the validator cannot save you.** A spawned session has
zero context and cannot ask a follow-up. `spawn_task.py` enforces that the five fields are
*present and substantial* — it cannot check they are *true*. On 2026-08-13 the very first
example brief written for it cited a repro command (`scripts/check_sitemap_urls.py`) that
does not exist; the shape gate passed it. **Verify the repro command runs before you queue
it**, or you have handed a session an hour of chasing your own fiction.

**⚠ Scope discipline.** `investigate` (diagnosis, no Write/Edit) is the default and should
stay it. `patch` edits only inside a git worktree. There is deliberately no `deploy` scope —
website deploys, ad changes and publishing never run unattended. A spawned session's
deliverable is a verified diagnosis and a reviewable diff; Will ships it. Do not add a
`--dangerously-skip-permissions` path to this system: one already exists at
`worker-agent/run-worker-agent.sh:73` and it is not a precedent to extend.

---

## The Business

**Fields Real Estate** — property intelligence platform, Gold Coast, Queensland.
Founded by **Will Simpson** (`will@fieldsestate.com.au`), sole operator.

**Mission:** Help buyers and sellers make informed decisions through original analysis, local expertise, transparent methodology.

**Tagline:** "Smarter with data"

**Business model:** Buyer-first, seller-funded. Build buyer audience with free data/valuations/intelligence. Revenue from sellers (pre-sale reports) and agents (leads, tools). Decision filter: does this help buyers? If yes, it eventually serves sellers too.

**Stage:** Pre-revenue. Building data infrastructure, content, and website. No customers yet.

**Target suburbs** (southern Gold Coast, 20-30 min from Surfers Paradise):
- **Robina** (4226) — master-planned, strong unit + house market
- **Varsity Lakes** (4227) — lake-fronting, younger demographic, growth
- **Burleigh Waters** (4220) — premium family suburb, high demand, limited supply

---

## Who You Are

Operations agent on `fields-orchestrator-vm` (GCP, australia-southeast1-b, **e2-standard-4** — 4 vCPU / 16 GB, upsized from e2-standard-2 on 2026-08-01 to stop memory-driven lockouts; the RAM is genuinely needed, the extra cores are not, see fix-history [BRIDGE-REGEX-CPU-BURN] — IP: 34.40.230.132). Full bash access — read/edit files, run scripts, query databases, deploy via GitHub.

Accessed via Claude Code terminal at `https://vm.fieldsestate.com.au`, embedded in ops dashboard at `https://fieldsestate.com.au/ops`.

---

## Live Ops Status

**Read `OPS_STATUS.md` at the start of every session** — auto-generated every 15 min:
```bash
cat OPS_STATUS.md
# Or refresh first:
python3 scripts/refresh-ops-context.py && cat OPS_STATUS.md
```

---

## Filesystem Layout

```
/home/fields/
├── Fields_Orchestrator/         ← YOU ARE HERE
│   ├── src/                     ← Orchestrator Python (21 modules, ~6600 lines)
│   ├── shared/                  ← Shared Python libs (db.py, env.py, monitor_client.py)
│   ├── config/settings.yaml     ← MongoDB URI, schedule, target suburbs
│   ├── config/process_commands.yaml ← All 30 pipeline process definitions
│   ├── scripts/                 ← 80+ utility scripts (enrichment, metrics, ads, articles)
│   ├── logs/                    ← orchestrator.log, fix-history/
│   ├── logs/runs/               ← Per-run structured logs
│   ├── watchdog.py              ← Self-healing watchdog
│   ├── trigger-poller.py        ← Manual trigger executor
│   └── repair-agent.py          ← Enrichment repair agent
├── Feilds_Website/01_Website/   ← Website codebase (React 19 + Vite + Netlify)
│   ├── src/                     ← React components, pages, utils
│   ├── netlify/functions/       ← 30 serverless API functions (~13K lines)
│   └── netlify/functions/monitor/ ← Extracted ops dashboard handlers
├── Property_Data_Scraping/      ← curl_cffi scrapers (Chrome-free since 2026-03-13)
└── Property_Valuation/          ← Comparable-sales valuation model
```

---

## Database

**Azure Cosmos DB (MongoDB API)** — Serverless tier (~5000 RU/s burst limit).

Connection: `COSMOS_CONNECTION_STRING` env var (in `.env` files, `config/settings.yaml`).

```python
# Python
from shared.db import get_client, get_db, get_gold_coast_db
client = get_client()
db = get_gold_coast_db()

# Or via mongo_client_factory (older pattern)
from src.mongo_client_factory import get_mongo_client, get_database, cosmos_retry
```

### Key Databases

| Database | Purpose |
|----------|---------|
| `Gold_Coast` | **Unified database** — all property data. Collections are `lowercase_with_underscores` (e.g. `robina`, `burleigh_waters`). Contains ~40K cadastral records + ~270 active listings + ~2K sold records. |
| `property_data` | Enriched data (`properties_for_sale` collection with valuation_data) |
| `system_monitor` | Ops monitoring, ad metrics, article storage, proposals, triggers |

### Critical Query Rules

- **Active listings:** ALWAYS filter `{"listing_status": "for_sale"}` — without this, queries hit ALL ~40K cadastral records
- **Sold properties:** Filter `{"listing_status": "sold"}`
- **Enriched:** Property has a `valuation_data` field (written by step 6)
- **Cosmos DB 16500:** Use `cosmos_retry()` wrapper for any write-heavy operations (RU exhaustion)

### Deprecated (read-only, do NOT write)
- `Gold_Coast_Currently_For_Sale` — consolidated into `Gold_Coast` on 2026-03-05
- `Gold_Coast_Recently_Sold` — consolidated into `Gold_Coast` on 2026-03-05

---

## Orchestrator Pipeline

**Schedule:** 20:30 AEST nightly. Target market daily, other suburbs Sunday only.

### Services
```bash
sudo systemctl status fields-orchestrator     # Main pipeline daemon
sudo systemctl status fields-trigger-poller   # Manual trigger executor
sudo systemctl status fields-watchdog         # Self-healing watchdog
sudo systemctl status fields-valuation-api    # On-demand valuation service
sudo systemctl status fields-valuation-poller # Valuation request poller
sudo systemctl status fields-ceo-telegram     # CEO Telegram bridge
sudo systemctl status fields-builder-telegram # Builder Telegram bridge
```

### Pipeline Phases (30 processes)

| Phase | Steps | What |
|-------|-------|------|
| 1: Scraping | 101, 102* | curl_cffi scrape Domain.com.au → `Gold_Coast` |
| 2: Sold | 103, 104*, 111, 113-115 | Sold detection, withdrawn, price tracking |
| 2.5: Images | 110*, 112, 116 | Blob storage, property type classification, data quality |
| 3: Visual | 105, 106, 108, 117 | GPT-4 photo/floor plan/satellite analysis |
| 4: Valuation | 6 | Comparable-sales ML valuation model |
| 5: Enrichment | 11-19 | Room dims, timelines, insights, narrative, reports |
| 6: Coverage | 109 | Coverage check vs live Domain count |
| 7: Audit | 107 | Database audit (misplaced properties) |

*Sunday only

### Logs
```bash
tail -f logs/orchestrator.log
bash scripts/check_last_run.sh
cat logs/runs/<latest>/run_summary.json
```

### Manual Trigger
```bash
python3 src/orchestrator_daemon.py --run-now
```

---

## Website

**Live:** `https://fieldsestate.com.au`
**Repo:** `Will954633/Website_Version_Feb_2026`
**Stack:** React 19 + TypeScript + Vite + React Router 7, Netlify Functions (Node.js), CSS Modules
**Deploy:** Push to GitHub → Netlify auto-deploys. Never use `netlify deploy --prod`.

### Navigation (as of 2026-03-27)
News | Market Intelligence | Properties | Analyse Your Home | Why Fields? | Subscribe

### Key Routes

| Route | Page | Purpose |
|-------|------|---------|
| `/` | MarketIntelligencePage | News & Research: newspaper-style articles (nav: "News and Research") |
| `/news/:suburb` | MarketIntelligencePage | News & Research, explicit suburb (was `/market-intelligence/:suburb` until 2026-07-31) |
| `/market-intelligence/:suburb/:category?` | MarketMetricsPage | Data charts by category (nav: "Market Intelligence"). Moved here from `/market-metrics` on 2026-07-31 |
| `/market-metrics/:suburb/:category?` | — | Legacy → **301 redirect** to `/market-intelligence/:suburb/:category?` |
| `/for-sale` | ForSalePage | Active property listings |
| `/property/:id` | PropertyPage | Property detail + editorial + valuation |
| `/analyse-your-home` | AnalyseYourHomePage | Conversion landing page |
| `/articles/:slug` | ArticlePage | Self-hosted articles |
| `/discover` | DiscoverPage | Swipe/scroll property feed |
| `/ops` | OpsPage | System monitor dashboard |

### GitHub Path Mapping
Website files sit at **repo root**, not under `01_Website/`:
- Local `01_Website/src/...` → GitHub `src/...`
- Local `01_Website/netlify/functions/...` → GitHub `netlify/functions/...`

### Shared Utilities (created 2026-03-27)
- `netlify/functions/db.mjs` — Cosmos connection pooling, retry, CORS, response helpers, auth
- `netlify/functions/shared-utils.mjs` — parsePriceString, haversineKm, isWaterfront, suburb normalization
- `netlify/functions/monitor/db-validation.mjs` — extracted from system-monitor.mjs
- `src/utils/suburbNormalize.ts` — canonical frontend suburb normalization

### Key Netlify Functions
- `properties-for-sale.mjs` — Active listings API
- `property.mjs` — Single property detail
- `valuation.mjs` — Valuation + NPUI scatter data
- `market-narrative.mjs` — Market charts + narrative
- `market-insights.mjs` — Data Insights Strip metrics
- `system-monitor.mjs` — All ops dashboard APIs (auth required: Bearer OPS_AUTH_TOKEN)

---

## Valuation System

The figure shown on property pages is the **`reconciled_valuation`** — a weighted average of adjusted comparable sale prices (NOT the CatBoost ML model).

- **Script:** `/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py`
- **Method:** Select 3-8 high-quality comparable sales → adjust each for floor area, condition, location → weighted mean
- **Weights:** adjustment quality, accuracy, proximity, verification, recency, data quality
- **⚠ DESIGN ENVELOPE — detached houses, $1,000,000–$2,000,000.** The method cannot leave this band: a weighted mean of adjusted comparables can never exceed its priciest comparable, and the pool is dominated by mid-market sales, so it regresses to the middle. Measured 2026-08-06 over 9,232 valued houses: **our highest valuation of all 9,232 was $2,494,914**, while real sold houses reach $5,100,000 and 7.5% of sales clear $2.5M. Outside the envelope `precompute_valuations.py` sets `directional_only` and suppresses **both** the point estimate and the range (`_ENVELOPE_MIN`/`_ENVELOPE_MAX`); comps and per-feature adjustments are kept. A ceiling-pinned home is indistinguishable from a correct one in our own output, so never infer one from the number.
- **Range:** a flat **±12%** of the estimate — NOT a statistical CI, and the code says so. It contains the actual sale price **61%** of the time across all bands (67% inside the envelope), so **never call it a "90% confidence range"** or say "~10% fall outside". A true 90% band needs ±26.4% (the measured P90 error).
- **Confidence level** (High/Medium/Low/Very Low) is **not calibrated across all bands** — within-10% ran high 55%, medium 46%, low 56%, very_low 61%, i.e. non-monotonic. It behaves better *inside* the envelope (high 61% vs medium 56%). Do not render the bare tier to a reader; `confidence_reason` states the why and is a fact.
- **⚠ Accuracy figures:** always run the backtest with `--price-filter none` for off-market work. The default `sale` anchor prunes comparables using the subject's own sale price — target leakage. Scoped to the envelope: **MAE 10.5%, median 8.2%, within-10% 59%** (Robina, n=278). Unscoped/all-types: 12.3% / 9.3% / 52%.
- **Stored:** `valuation_data.confidence` field on each property document
- **Display:** `ConfidenceDisplay` component in `HowToValuePage`
- The CatBoost `iteration_08_valuation` is a separate, inferior model — do not confuse them
- **Backtest script:** `scripts/valuation_backtest.py`

---

## Article System (Self-Hosted)

Ghost CMS is **deprecated** (subscription expired). Articles are self-hosted in MongoDB.

- **Storage:** `system_monitor.content_articles`
- **Management:** Ops dashboard → Article Manager tab
- **API:** CRUD in `system-monitor.mjs` (content-articles, content-article-create, etc.)
- **Build-time fetch:** `fetch-articles.js` → `articles.json`
- **Push:** `python3 scripts/push-ghost-draft.py --title "Title" --md-file article.md [--publish]`
- **Delete:** `python3 scripts/delete-ghost-article.py <id> [--list | --search "keyword"]`
- **Auto-generated:** `Will954633/fields-automation` repo, 12 GitHub Actions workflows
- **Deploy hook:** `https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d`

---

## AI Property Editorial System

Multi-agent pipeline generating editorial content for property pages.

- **Script:** `scripts/backend_enrichment/generate_property_ai_analysis.py`
- **Model:** Claude Opus 4.8 for all agents, on the **Claude Max subscription** (`USE_CLAUDE_MAX=1`; step 120 clears `ANTHROPIC_BACKEND` so `make_client` uses Max, not OpenRouter — it checks that var *before* `use_max`). Model pinned by full id in `claude_max_client._model_alias` (bare `opus` collapses to a stale tier on this Max account). Migrated 2026-07-30, see fix-history `[EDITORIAL-MAX-OPUS48]`.
- **Vision sub-step:** the `satellite_verify` agent is a vision call and can't run on the Max CLI (text-only) — it routes through `shared/claude_vision.py` → **Gemini via Vertex** (`VISION_BACKEND=gemini_vertex`, GCP `fields-estate` billing), like every other vision task.
- **Pipeline:** Price/Property/Market agents → Editor → Reflection → Fact-Check → Draft 2 → Verify (max 3 retries)
- **Output:** `ai_analysis` field on property document, status: draft/published/failed_factcheck
- **Review:** Ops dashboard → Editorial Review tab
- **Run:** `--address "X"` (single), `--new-listings` (last 7d), `--force`
- **Config:** `config/property_editorial_prompt.md`, `config/flood_context_burleigh_waters.md`

---

## Facebook & Google Ads

### Facebook
- **Ad Account:** `act_1463563608441065`, **Page:** `889412530933297`
- **Token:** `.env` as `FACEBOOK_ADS_TOKEN` (expires ~60 days)
- **Pixels:** `1491613936314260` (Fields, primary) — the only one. `137811233253065` (Content) was dropped from CAPI 2026-07-15 (token lacks permission, every call 400'd) and removed from the browser 2026-08-05.
- **Metrics:** `fb-metrics-collector.py` (2x/day at 12:00 + 23:00 AEST)
- **Ad experimentation:** MUST follow `fb_ads_experimentation_playbook.md` (memory file)
- **Established learnings (do not re-test):** Sell-focused content dead, lifestyle photos dead, OFFSITE_CONVERSIONS is the #1 lever, broad targeting beats custom audiences

### Google
- **MCC:** 127-641-8198, **Ad Account:** 997-572-4211
- **Developer Token:** `.env` as `GOOGLE_ADS_DEVELOPER_TOKEN` (Basic Access)
- **Manager:** `scripts/google_ads_manager.py` (create, list, pause, enable, report, keywords)
- **Safety caps:** $50/day per campaign, $500/month total, all campaigns start PAUSED
- **Metrics:** `google-ads-metrics-collector.py` (2x/day at 12:15 + 23:10 AEST)

### Organic Facebook
- **2x/day posting:** 06:30 + 17:00 AEST via `fb-content-scheduler.py`
- **Templates:** `fb-page-post.py` — 14 templates
- **Photos:** `fb-photo-manager.py` — Sunday sync from `Will954633/fields-local-photography`

---

## Analytics

**PostHog** (migrated 2026-03-19, replaced custom CRM tracker):
- Init: `src/utils/posthog.ts`, pageviews via `posthog.capture("$pageview")`
- Feature flags: `for_sale_page_v1`, `discover_mode_v1`
- Also kept: GA4, Facebook Pixel, Meta Conversions API, Google Ads tags, Contentsquare

---

## CEO Agent System

Three AI agents (Engineering, Growth, Product) analyse data daily and produce proposals.

- **Compute:** Codex CLI on property-scraper VM (35.201.6.222)
- **Cron:** 00:03 context export, 00:33 agent launcher
- **Proposals:** `system_monitor.ceo_proposals` + `Will954633/fields-ceo-sandbox`
- **Manual:** `bash scripts/ceo-agent-launcher-remote.sh [engineering|growth|product]`

---

## Market Pulse (Monthly)

Monthly market metrics summaries written collaboratively (Will + Claude in VS Code).

- **Reminder:** 1st @ 08:00 AEST via Telegram (@WillFieldsBot)
- **Fallback:** Auto-generated on 3rd @ 06:00 AEST if manual not done
- **Data:** `python3 scripts/manual_market_pulse.py --show-data`
- **Storage:** `system_monitor.market_pulse` (source: "manual" vs "auto")

---

## Monthly Maintenance Checks

### Crash-Risk Chart Data (1st of month)
- Sales volume chart merges 3 sources with property-type filter risk
- After monthly recompute, verify filters are working (March 2026: phantom surge from unfiltered source)
- `CrashRiskSection.tsx` has **hardcoded data claims** — update manually when chart data changes

### Market Pulse Summaries (1st-3rd of month)
- Collaborative write with Will, or auto-fallback on 3rd

---

## Google Drive (MCP)

You have **full read/write access to Google Drive** via MCP tools (configured in `.mcp.json`).

**Server:** Custom MCP at `mcp-servers/gdrive/index.mjs` — uses OAuth2 with auto token refresh.

### Available Tools

| Tool | Purpose |
|------|---------|
| `search` | Find files by query (natural language or raw Drive syntax) |
| `list_folder` | Browse folder contents by ID (default: root) |
| `read_file` | Read text content (Docs → Markdown, Sheets → CSV, capped 512KB) |
| `read_file_metadata` | Get file info (size, parents, links, dates) |
| `create_file` | Create files or Google Docs in a folder |
| `update_file` | Update file content (works with Google Docs) |
| `create_folder` | Create folders |
| `move_file` | Move between folders |
| `copy_file` | Duplicate files |
| `delete_file` | Trash (not permanent delete) |
| `download_file` | Save Drive file to local VM path |
| `upload_file` | Push local file to Drive |

### Key Folders

| Folder | ID | Contents |
|--------|----|----------|
| Research | `1AYkf2FPojjKTTPFjx8CkkqX9nXCsM1h9` | Property positioning research & analysis |
| Seller Book | `1Ga_UdxLQQIAeYtKdqGH2V1w5POI5DL67` | Seller book project files |
| Seller Book V2 source | `1pkV-EkTmq4qzVTdG8abVN-ggRiMmkOeo` | 26 V2 source files |

### Usage Notes

- For Google Docs, `create_file` with `mimeType: "application/vnd.google-apps.document"` — content as plain text/markdown
- `read_file` exports Docs as Markdown and Sheets as CSV automatically
- Search supports raw Drive query syntax: `name contains 'report' and mimeType='application/pdf'`
- Credentials at `/home/fields/.gdrive-oauth.keys.json` + `/home/fields/.gdrive-server-credentials.json`

---

## Environment & Credentials

All credentials in `.env` files — never hardcode.
- `/home/fields/Fields_Orchestrator/.env` — COSMOS_CONNECTION_STRING, OPENAI_API_KEY, FB/Google tokens
- `/home/fields/Feilds_Website/01_Website/.env` — Website env vars
- `ANTHROPIC_API_KEY` in `/etc/environment` and `~/.bashrc`
- `GH_CONFIG_DIR=/home/projects/.config/gh` — GitHub CLI auth (fine-grained PAT for `Will954633`)

```bash
# Activate venv for Python scripts
source /home/fields/venv/bin/activate
# Load env vars
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
```

---

## Database Schema Reference

Before writing MongoDB queries, read:
```bash
cat /home/fields/Fields_Orchestrator/SCHEMA_SNAPSHOT.md
```
Auto-generated daily — contains every collection, field name, type, and example document.

---

## Common Tasks

### Fix a failing pipeline step
```bash
bash scripts/check_last_run.sh
cat logs/runs/<latest>/01_step_<id>_*/stderr.log
# Fix, test, push to GitHub
```

### Deploy a website fix
```bash
# Edit locally, push to GitHub (Netlify auto-deploys)
SHA=$(gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' --jq '.sha')
CONTENT=$(base64 -w0 < /home/fields/Feilds_Website/01_Website/LOCAL_PATH)
gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' \
  --method PUT --field message="fix: description" --field content="$CONTENT" --field sha="$SHA"
# Then log deploy + visually verify (mandatory)
```

### Check what's running
```bash
sudo systemctl list-units --state=active | grep fields
ps aux | grep -E "orchestrator|watchdog|poller|ollama" | grep -v grep
```
