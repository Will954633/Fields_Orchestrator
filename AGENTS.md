# AGENTS.md — Fields Estate Orchestrator VM

You are a coding agent operating on the Fields Estate orchestrator VM (Google Cloud, australia-southeast1-b).
Working directory: `/home/fields/Fields_Orchestrator`
Current date context: check `/home/fields/Fields_Orchestrator/OPS_STATUS.md` for live system state.

---

## ⚡ MANDATORY — NO EXCEPTIONS

These are non-negotiable. A task is NOT complete until all applicable steps below are done.

### ⚡ 1. FIX HISTORY — after EVERY code change, bug fix, or script repair

Do this automatically. Do not wait to be asked.

```bash
# Get AEST date
DATE=$(TZ=Australia/Brisbane date +%Y-%m-%d)
TIME=$(TZ=Australia/Brisbane date +%H:%M)
FILE="logs/fix-history/${DATE}.md"
mkdir -p logs/fix-history
```

Append to `logs/fix-history/YYYY-MM-DD.md`:
```
## [PROBLEM-ID] Short description — HH:MM AEST
**Symptom:** What was broken.
**Root cause:** Why it was broken.
**Fix:** What you changed and why.
**Files:** List of files modified.
**Recurrence:** First occurrence / Nth occurrence
```

**Triggers:** Any time you edit a file to fix a bug, repair a script, or change behaviour.

---

### ⚡ 2. PUSH TO GITHUB — after EVERY file you create or modify

Do this automatically. Do not wait to be asked. Code that only exists on this VM is not backed up.

`git push` HANGS on this VM — ALWAYS use `gh api`:

```bash
# Existing file:
SHA=$(gh api 'repos/OWNER/REPO/contents/PATH' --jq '.sha')
CONTENT=$(base64 -w0 < /local/path/to/file)
gh api 'repos/OWNER/REPO/contents/PATH' \
  --method PUT --field message="fix: description" --field content="$CONTENT" --field sha="$SHA"

# New file (no sha needed):
CONTENT=$(base64 -w0 < /local/path/to/file)
gh api 'repos/OWNER/REPO/contents/PATH' \
  --method PUT --field message="add: description" --field content="$CONTENT"
```

Repo routing:
- `Fields_Orchestrator/` files → `Will954633/Fields_Orchestrator`
- `Feilds_Website/01_Website/` files → `Will954633/Website_Version_Feb_2026` (strip `01_Website/` prefix)

NEVER push: `.env`, credentials, `node_modules/`, `__pycache__/`, `logs/`, `*.sqlite`

**Triggers:** Every time you write or edit any file.

---

### ⚡ 3. AD DECISION LOG — after EVERY advertising change

Write to `system_monitor.ad_decisions` in MongoDB before ending the session.
Fields: `date`, `type`, `title`, `hypothesis`, `findings`, `data_snapshot`, `tags`, `reasoning`, `created_at`.

**Triggers:** Creating, pausing, enabling, or changing any Facebook or Google Ads campaign/adset/ad/budget.

---

### ⚡ 4. WEBSITE CHANGE LOG — after EVERY website file push

```bash
# Always log the deploy:
python3 scripts/website-deploy-tracker.py log --commit <SHA> --files "path" --message "desc"
# If the change is testable (not just a typo fix):
python3 scripts/website-change-log.py log --title "desc" --type bug_fix --hypothesis "expected effect"
```

**Triggers:** Any push to `Will954633/Website_Version_Feb_2026`.

---

## CRITICAL DATABASE RULES

### Unified Gold_Coast database
- **ONE database: `Gold_Coast`** — all property data lives here
- `Gold_Coast_Currently_For_Sale` and `Gold_Coast_Recently_Sold` are **DEPRECATED** — read-only, do NOT write
- Active listings: always filter `{"listing_status": "for_sale"}` — without this you hit ~40K cadastral records instead of ~268 listings (this caused a 6-hour runaway query)
- Sold properties: filter `{"listing_status": "sold"}`
- A property is enriched when it has a `valuation_data` field

### Connection
```python
from pymongo import MongoClient
import yaml
with open("/home/fields/Fields_Orchestrator/config/settings.yaml") as f:
    cfg = yaml.safe_load(f)
client = MongoClient(cfg["mongodb"]["uri"])
# OR from env:
import os; client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"])
```
Always: `source /home/fields/Fields_Orchestrator/.env` and `source /home/fields/venv/bin/activate`

### Cosmos DB (Serverless ~5000 RU/s)
- Retry on `OperationFailure` code 16500 — use `cosmos_retry.py` decorator
- Cache `list_collection_names()` at init — do NOT call it in loops
- 300ms delay between property lookups in batch operations

---

## PIPELINE ARCHITECTURE

### Process order
```
101 → 102* → 103 → 104* → 110 → 105 → 106 → 108 → 6 → 11 → 12 → 13 → 14 → 16 → 15 → 17 → 19 → 18 → 109 → 107
```
(*Sunday only)

| Phase | Steps | Purpose |
|-------|-------|---------|
| 1 | 101, 102 | curl_cffi scrape Domain.com.au → Gold_Coast DB |
| 2 | 103, 104 | Sold monitoring (in-place status update) |
| 2.5 | 110 | Download images → Azure Blob |
| 3 | 105, 106, 108 | GPT-4 Vision photo + floor plan analysis |
| 4 | 6 | Comparable-sales valuation model |
| 5 | 11–19 | Backend enrichment (dims, medians, insights, narrative) |
| 6–7 | 109, 107 | Coverage check + DB audit |

### Key facts
- **Chrome-free**: ALL steps use `curl_cffi` with `impersonate="chrome120"` — no Selenium/Chrome
- Domain.com.au serves all data in `__NEXT_DATA__` JSON — no JS rendering needed
- Schedule: 20:30 AEST daily
- Manual trigger: `python3 src/orchestrator_daemon.py --run-now`

### Services
```bash
sudo systemctl status fields-orchestrator     # Main pipeline
sudo systemctl status fields-trigger-poller   # Manual triggers
sudo systemctl status fields-claude-agent     # Repair agent
```

---

## WEBSITE

- **Repo:** `Will954633/Website_Version_Feb_2026` (repo root = `01_Website/` locally)
- **Deploy:** GitHub push → Netlify auto-deploys. Never `netlify deploy --prod` directly
- **Stack:** React 19 + TypeScript + Vite + Netlify Functions (Node.js) + Azure Cosmos DB
- **Force rebuild:** `curl -s -X POST https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d`
- **Env var for DB:** `COSMOS_CONNECTION_STRING` (NOT `MONGO_URI`)
- **v2 functions:** use `export const config = { path: "/api/v1/..." }` for routing
- **Visual verification:** After any change → `node scripts/site-inspector.js --url /PAGE`

---

## ARTICLE SYSTEM (Ghost is DEPRECATED)

- Articles stored in `system_monitor.content_articles` MongoDB collection
- Push script: `python3 scripts/push-ghost-draft.py --title "..." --md-file article.md`
- Delete script: `python3 scripts/delete-ghost-article.py <id>`
- Netlify deploy hook: `https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d`
- Do NOT use Ghost APIs — subscription expired, locked out

---

## ENVIRONMENT

- Credentials: `/home/fields/Fields_Orchestrator/.env` (COSMOS_CONNECTION_STRING, OPENAI_API_KEY, etc.)
- Python venv: `/home/fields/venv` — always activate before running scripts
- GitHub CLI `gh` is authenticated for `Will954633`
- VM timezone: `Australia/Brisbane` (AEST = UTC+10, no DST)
- Schema reference: read `SCHEMA_SNAPSHOT.md` before writing any MongoDB query

---

## SCHEMA SNAPSHOT

Before writing any MongoDB query, read:
```
cat /home/fields/Fields_Orchestrator/SCHEMA_SNAPSHOT.md
```

---

## [AUTO-SYNCED MEMORY — regenerated by sync-memory-to-codex.py — do not edit below]

_Run `python3 scripts/sync-memory-to-codex.py` to refresh this section from Claude's memory._

<!-- MEMORY_SECTION_START -->
_Last synced: 2026-03-18 01:30 AEST_


### Founder Truths

- **Tagline:** Smarter with data
- **Mission:** Help buyers and sellers make informed real estate decisions through original analysis, local expertise, and transparent methodology.
- **Primary database:** `Gold_Coast`
- No production DB writes from the remote CEO VM.
- No direct deploys from the remote CEO VM.
- No direct ad changes from the remote CEO VM.
- Chief of Staff must synthesize only after successful specialist runs or explicitly degraded inputs.
- Blank telemetry exports are a blocking context failure, not an acceptable warning.
- All proposal findings should state confidence, evidence freshness, blocked_by, and data_gaps.
- Tuesday CEO reviews must explicitly check both the latest daily orchestrator run and the most recent weekly all-suburbs orchestrator run.
- Every CEO growth review must check both Facebook Ads and Google Ads and alert the founder to anything material.


### CEO Agent Proposals — Action Required

> These are findings and proposals from the management agent team. Pending items need implementation.


#### PRODUCT Agent — 2026-03-17 [⚠️ PENDING]

Tonight's 21:54 AEST ops snapshot still shows the valuation pipeline stalled (Step 106/15 failures), only 180 of 50,422 active listings enriched (0.36%), three core suburbs with zero coverage despite dozens of live properties, and the buyer experience degraded by a 404 sold-comps API plus missing website telemetry—Fields cannot currently prove its data advantage to a Robina/Burleigh/VL buyer.

**Findings:**

- `[HIGH]` **Merrimac/Mudgeeraba/Reedy Creek missing from the product** — OPS coverage shows these three suburbs at 0 listings (status unknown, last updated 'never') and scraper health hasn't run since 2026-03-06, yet active_listings.json lists 12, 23, and 20 live propertie
- `[HIGH]` **Sold comps API 404 removes proof from valuation guides** — Website API health shows /api/v1/properties/recently-sold returning 404 (checked 24 minutes before the snapshot) while its health endpoint is green, meaning the property pages and valuation flows cann
- `[MEDIUM]` **Website telemetry + active experiment exports are empty** — context/metrics/website_metrics_7d.json and context/experiments/active_experiments.json are 0-byte files even though the /for-sale and /discover experiments launched on 2026-03-16, so the product team
- `[CRITICAL]` **Valuation enrichment blocked by repeated Step 106/15 failures** — OPS (2026-03-17 21:54 AEST) shows Step 106 (Ollama floor plan analysis) failing 1h ago and Step 15 (Calculate Property Insights) failing twice in the last day, and the watchdog log recorded Step 108 o

**Proposed fixes:**

- `[HIGH]` **RU-aware valuation queue and Step 15 guardrails** — 
- `[HIGH]` **Emergency rescrape for Merrimac/Mudgeeraba/Reedy Creek** — 
- `[MEDIUM]` **Rebuild sold-comps API + timeline module** — 
- `[MEDIUM]` **Suburb data reliability badges** — 

> To mark implemented: update `status` to `'completed'` in `system_monitor.ceo_proposals` where `agent='{p.get('agent')}'` and `date='{date}'`


#### GROWTH Agent — 2026-03-17 [⚠️ PENDING]

Paid Search is still feeding verification bots, our exported KPI files are empty, the recently-sold API is failing, and we have an unused scarcity story (only 121 listings across Robina, Burleigh Waters, and Varsity Lakes), so we need to pause spend, repair measurement, and push data-led content before scaling acquisition.

**Findings:**

- `[HIGH]` **No KPI data captured in the context snapshot** — The current bundle shows ad_performance_7d.json, website_metrics_7d.json, and recent_website_changes.json as 0-byte files (all stamped 12:05 AEST on 17 Mar), leaving us without spend, CTR, CVR, or cha
- `[HIGH]` **Recently-sold API is down** — /api/v1/recently-sold has been returning 404s while 13 of 14 endpoints are green, so any page or CTA that leans on sold comps is broken right now.
- `[MEDIUM]` **Target-suburb inventory sits at just 121 listings** — Active listings count shows Robina 46, Burleigh Waters 40, and Varsity Lakes 35 homes on market (121 total), giving us a scarcity narrative that matches the 'Smarter with data' promise but isn’t being
- `[CRITICAL]` **Google Ads clicks are still 100% bots** — The 2026-03-17 fix log shows 77 Google Ads clicks ($78.39) produced 111 sessions from just 11 AWS IPs and even logged 32 fake "conversions" from a page-view tag, so no humans reached the form despite 

**Proposed fixes:**

- `[HIGH]` **Bot-proof Google Search before reactivation** — 
- `[MEDIUM]` **Daily metrics health-check run** — 
- `[MEDIUM]` **Weekly Gold Coast Inventory Pulse** — 

> To mark implemented: update `status` to `'completed'` in `system_monitor.ceo_proposals` where `agent='{p.get('agent')}'` and `date='{date}'`


#### ENGINEERING Agent — 2026-03-17 [⚠️ PENDING]

Floor-plan enrichment (step 106) is still silently skipping work after Cosmos DB throttling, step 15 keeps tripping the watchdog because any single 429 marks the run as failed, and the public /api/v1/properties/recently-sold route continues to 404 even while its health check is green, leaving us blind on both enrichment coverage and sold-proof APIs.

**Findings:**

- `[HIGH]` **Step 106 exits 'successfully' after Cosmos throttling** — OPS shows every nightly run executing step 106 three times with a long failure sandwiched between two 7-second 'successes,' and it remains on the last-24h failure list (context/OPS_STATUS.md:16-38). T
- `[HIGH]` **Step 15 fails on single 429 despite completing work** — Step 15 shows two failures per run around a brief success and accounts for two of the three failures logged in the past day (context/OPS_STATUS.md:27-38). The 15 Mar watchdog traces show calculate_pro
- `[HIGH]` **/api/v1/properties/recently-sold still 404s while health is green** — OPS API health shows the data route returning 404 (checked 24 minutes ago) even while /api/v1/recently-sold/health returns 200 (context/OPS_STATUS.md:81-96). This regression breaks every sold property

**Proposed fixes:**

- `[HIGH]` **Harden floor-plan analyzer against Cosmos 429s** — 
- `[HIGH]` **Make Property Insights tolerant to transient 429s** — 
- `[HIGH]` **Restore sold API and add contract probes** — 

> To mark implemented: update `status` to `'completed'` in `system_monitor.ceo_proposals` where `agent='{p.get('agent')}'` and `date='{date}'`


#### CHIEF_OF_STAFF Agent — 2026-03-17 [⚠️ PENDING]

Cosmos-throttled enrichment, empty KPI exports, and a 404 sold-comps API are the shared blockers, so founder time today has to prioritise getting reliable data back before adding any new UX or paid growth bets.

**Findings:**

- `[HIGH]` **Coverage gap across three core suburbs** — Product reports Merrimac, Mudgeeraba, and Reedy Creek stuck at zero listings with last updates recorded as 'never' despite dozens of active homes in the listings snapshot.
- `[HIGH]` **Telemetry exports are empty** — Growth shows ad_performance_7d.json, website_metrics_7d.json, and recent_website_changes.json as zero-byte files, so no one can validate ads, experiments, or ops SLAs.
- `[HIGH]` **Sold-comps API returns 404 while health is green** — All three agents cite /api/v1/properties/recently-sold failing even as /api/v1/recently-sold/health reports 200, breaking buyer proof modules without any alerting.
- `[HIGH]` **Google Ads traffic is still bot-only** — Growth notes $78.39 of spend on 2026-03-17 produced 111 AWS sessions and fake conversions even after prior fixes.
- `[CRITICAL]` **Cosmos throttling keeps Steps 106/15 failing** — Engineering and product both highlight repeating ❌ statuses for floor-plan analysis and property insights plus watchdog entries where 0/121 properties receive valuation_data.

**Proposed fixes:**

- `[HIGH]` **RU-aware enrichment restart** — 
- `[HIGH]` **Telemetry export hardening** — 
- `[HIGH]` **Sold API + contract probe fix** — 
- `[MEDIUM]` **Bot-proof Google Ads relaunch** — 

> To mark implemented: update `status` to `'completed'` in `system_monitor.ceo_proposals` where `agent='{p.get('agent')}'` and `date='{date}'`


#### ENGINEERING Agent — 2026-03-16 [⚠️ PENDING]

Floor-plan enrichment is still falling over under Cosmos DB throttling, Calculate Property Insights reports failure on every transient write error, the public recently-sold API endpoint is 404ing while its health check passes, and scraper health telemetry has been stale since the curl_cffi migration — these gaps are burning pipeline time, hiding missing data, and breaking consumer endpoints.

**Findings:**

- `[HIGH]` **Floor plan analysis silently skips work when Cosmos throttles** — Step 106 has triggered at least two watchdog escalations today and five failures in the last 24h; the auto-repair summary shows get_floor_plan_stats() and get_properties_needing_floor_plan_analysis() 
- `[HIGH]` **Calculate Property Insights marks the whole step failed on any single error** — Process 15 calls monitor.finish(status='success' if total_errors == 0 else 'failed') at line ~609, so even one Cosmos write error makes the watchdog think the step failed despite the script completing
- `[MEDIUM]` **`/api/v1/properties/recently-sold` has regressed to 404** — The ops probe now records 404s for /api/v1/properties/recently-sold even though /api/v1/recently-sold/health still returns 200, which means the primary listing endpoint disappeared (likely after the S
- `[MEDIUM]` **Scraper health dashboard has been frozen since curl_cffi migration** — Even though step 101 succeeded at 638s tonight, the Scraper Health table still shows the last run for every suburb on 2026-03-06–03-04, so the ops dashboard can no longer tell if scrapes are actually 

**Proposed fixes:**

- `[HIGH]` **Add RU-aware retry layer to floor-plan analysis** — 
- `[MEDIUM]` **Harden Calculate Property Insights error handling** — 
- `[MEDIUM]` **Restore `/api/v1/properties/recently-sold` contract** — 
- `[MEDIUM]` **Emit scraper heartbeat metrics from curl_cffi** — 

> To mark implemented: update `status` to `'completed'` in `system_monitor.ceo_proposals` where `agent='{p.get('agent')}'` and `date='{date}'`


### User Feedback & Corrections

#### Facebook Ads Scientific Experimentation Playbook

# Facebook Ads — Scientific Experimentation Playbook

**This is the master process. Every ad session MUST follow this workflow. No ad changes without documentation.**

---

## 1. SESSION START — Read State

Before touching anything, load current state:

```python
source /home/fields/venv/bin/activate
python3 << 'EOF'
import os
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv('/home/fields/Fields_Orchestrator/.env')
client = MongoClient(os.environ['COSMOS_CONNECTION_STRING'])
sm = client['system_monitor']

# 1. Read last 5 decisions
decisions = list(sm['ad_decisions'].find().sort('_id', -1).limit(5))
for d in decisions:
    print(f"{d['_id']} [{d['type']}] {d['title']}")

# 2. Read active experiments
experiments = list(sm['ad_experiments'].find({'status': 'active'}))
print(f"\nActive experiments: {len(experiments)}")
for e in experiments:
    print(f"  {e['_id']}: {e.get('hypothesis','?')}")

# 3. Account snapshot
profiles = list(sm['ad_profiles'].find())
active = [p for p in profiles if p.get('effective_status') == 'ACTIVE']
total_spend = sum((p.get('lifetime',{}).get('spend_aud',0) or 0) for p in profiles)
attrs = list(sm['ad_attribution'].find({'_id': {'$ne': 'summary'}}))
total_sessions = sum(a.get('sessions',0) for a in attrs)
print(f"\nAccount: {len(profiles)} ads ({len(active)} active), ${total_spend:.2f} lifetime, {total_sessions} sessions")
client.close()
EOF
```

Also run: `python3 scripts/ad-review-dump.py --summary` for the quick overview.

---

## 2. DATA RETRIEVAL — Where Everything Lives

All data in `system_monitor` database in Cosmos DB:

| Collection | What | Key fields | Updated |
|---|---|---|---|
| `ad_profiles` | Per-ad snapshot: creative, targeting, 7d/30d/lifetime metrics | `_id`=ad_id, `creative`, `targeting`, `lifetime`, `last_7d` | 2x/day (overwritten) |
| `ad_daily_metrics` | Per-ad per-day granular metrics — **PERMANENT** | `_id`=`{ad_id}_{date}`, `spend_aud`, `impressions`, `clicks`, `link_clicks`, `reach` | 2x/day (upsert, never delete) |
| `ad_demographics` | Age x gender breakdowns | `_id`=`{ad_id}_demographics`, `segments` | Nightly |
| `ad_placements` | Platform x position | `_id`=`{ad_id}_placements`, `placements` | Nightly |
| `ad_attribution` | Website sessions per ad | `_id`=ad_id, `sessions`, `engagement_rate`, `bounce_rate`, `avg_duration_seconds`, `properties_viewed_count` | Nightly |
| `ad_decisions` | **ALL changes, reasoning, learnings** | `_id`=`{date}_{seq}`, `type`, `title`, `reasoning`, `learning`, `ads_affected` | Manual (every session) |
| `ad_experiments` | Structured experiments with snapshots | `_id`=experiment name, `hypothesis`, `status`, `snapshots` | Via ad-experiment-log.py |
| `facebook_ads_history` | Daily account-level snapshot | `_id`=date | Daily |

### Scripts
- `scripts/fb-metrics-collector.py` — Fetches from Facebook API → writes to all metric collections
- `scripts/fb-attribution-builder.py` — Joins ads with website sessions from CRM_All_Data
- `scripts/ad-review-dump.py` — Interactive review tool (`--summary`, `--active`, `--id <ID>`, `--top N`, `--sort sessions`)
- `scripts/ad-experiment-log.py` — Experiment lifecycle (`log`, `snapshot`, `review`, `close`, `list`)
- `scripts/classify_ad_creatives.py` — Vision AI classification of ad images (NOT YET WORKING — needs API credits)

### Cron (all AEST)
- 12:00 — `fb-metrics-collector.py --quick`
- 23:00 — `fb-metrics-collector.py` (full)
- 23:15 — `fb-attribution-builder.py`

---

## 3. ANALYSIS FRAMEWORK — How to Evaluate

**Primary metric: Cost per website session** — this is what matters. Impressions and clicks are vanity.

### Tier 1 metrics (decision-making)
- **Cost per session** — lower is better. Calculated from `ad_attribution.sessions` / `ad_profiles.lifetime.spend_aud`
- **Engagement rate** — % of sessions that are "engaged" or "deep" (not bounce/light)
- **Average session duration** — how long people stay
- **Properties viewed** — did they actually look at property pages?

### Tier 2 metrics (diagnostic)
- **CTR** — click-through rate (are people interested?)
- **Link clicks** — actual website clicks (not post reactions)
- **CPC (link)** — cost per link click
- **CPM** — cost per 1000 impressions (audience efficiency)
- **Frequency** — impressions/reach (>3 means ad fatigue)

### Tier 3 metrics (segmentation)
- Demographics: which age/gender segments convert?
- Placements: feed vs stories vs reels vs audience network?
- Image category: property_photo vs aerial_photo vs lifestyle_photo vs data_chart
- Emotional tone: informational vs aspirational vs analytical
- Content type: property-specific vs market-overview vs data-driven

### Key Performance Benchmarks (established 2026-03-13)
- Account average cost/session: $10.79
- Best campaign (Watch this sale): $2.31/session
- Best single ad ("Someone Bought This Home"): $0.70/session
- Informational tone: $6.90/session
- Aspirational tone: $37.79/session
- Aerial photos: $0.79/link click
- Lifestyle photos: DEAD ($157/session)

---

## 4. THE EXPERIMENTATION CYCLE

### Step 1: Hypothesize
Based on current data, form a specific, testable hypothesis:
- "Property-specific stories will outperform suburb-overview content by >50% on cost/session"
- "Aerial photos with informational text will get lower CPC than property photos"
- NOT vague: "Let's try different ads" ← this is not a hypothesis

### Step 2: Design
- **Variable:** What exactly are we changing? (ONE variable per experiment)
- **Control:** What stays the same?
- **Budget:** How much to spend on this test?
- **Duration:** How long to run before measuring? (minimum 7 days, ideally 14)
- **Success criteria:** What number would confirm or reject the hypothesis?

### Step 3: Implement
- Create the ads in Facebook Ads Manager
- Log the experiment in `ad_experiments`:
  ```bash
  python3 scripts/ad-experiment-log.py log "experiment-name" \
    --hypothesis "Property stories will beat suburb overviews by 50% on cost/session" \
    --variable "ad creative type" \
    --control "Is Now a Good Time to Buy: Burleigh Waters" \
    --treatment "Someone Bought This Home 18 Months Ago" \
    --budget 50 --duration 14
  ```

### Step 4: Document the decision
- IMMEDIATELY write to `ad_decisions` (see Section 5)

### Step 5: Wait
- Do NOT check daily. Minimum 7 days before any analysis.
- Take a snapshot at midpoint: `python3 scripts/ad-experiment-log.py snapshot "experiment-name"`

### Step 6: Analyze
- Pull the daily metrics for test vs control
- Compare on Tier 1 metrics
- Check if result is meaningful (need >20 sessions to draw conclusions)
- Segment by demographics/placements for deeper insight

### Step 7: Decide
- Close the experiment with a verdict:
  ```bash
  python3 scripts/ad-experiment-log.py close "experiment-name" \
    --verdict "confirmed" --learnings "Property stories 3x cheaper per session"
  ```
- Document the decision in `ad_decisions`
- Apply the learning: scale winners, kill losers

### Step 8: Next hypothesis
- Use the learning to form the next experiment
- The cycle continues

---

## 5. MANDATORY DOCUMENTATION — ad_decisions

**Every ad change gets a decision log. No exceptions.**

```python
from datetime import datetime, timezone, timedelta
AEST = timezone(timedelta(hours=10))
now = datetime.now(AEST)
date_str = now.strftime("%Y-%m-%d")

# Find next sequence number for today
existing = list(sm['ad_decisions'].find({"date": date_str}))
seq = len(existing) + 1

decision = {
    "_id": f"{date_str}_{seq:03d}",
    "date": date_str,
    "time_aest": now.strftime("%H:%M"),
    "created_at": now.isoformat(),
    "type": "...",          # audit | experiment | pruning | structural_change | budget_change | creative_change | infrastructure
    "title": "...",         # Short description
    "summary": "...",       # What happened
    "action": "...",        # What was done
    "reasoning": "...",     # WHY (most important field)
    "learning": "...",      # What we learned (for completed experiments / failed approaches)
    "ads_affected": [...],  # List of ad names/IDs
    "data_snapshot": {...}, # Key numbers at time of decision
    "tags": [...],          # For querying later
}
sm['ad_decisions'].insert_one(decision)
```

### Decision types:
- **audit** — periodic review of account performance
- **experiment** — starting a new test
- **pruning** — killing underperformers
- **structural_change** — moving ads between campaigns, changing campaign structure
- **budget_change** — adjusting budgets
- **creative_change** — new ad creative, text changes
- **infrastructure** — changes to data collection, scripts, etc.

---

## 6. ESTABLISHED LEARNINGS (do not re-test)

These are confirmed findings. Do not waste budget re-testing:

1. **Sell-focused content does not work on Facebook.** $49 spent, 0 sessions. Passive Facebook browsers are not in sell-mode. (2026-03-13)
2. **Lifestyle photos are dead.** $157 spent, 1 session. Do not use lifestyle/aspirational imagery. (2026-03-13)
3. **Aspirational tone costs 5x more than informational.** $37.79 vs $6.90 per session. Always lead with data. (2026-03-13)
4. **Property-specific stories outperform generic market content.** Watch this sale at $2.31/session vs Is Now Good Time at $8.62. (2026-03-13)
5. **Aerial photos get the cheapest link clicks** at $0.79/click. (2026-03-13)
6. **No valuation references in any Facebook post** — user policy, not a performance finding. (2026-03-11)
7. **OFFSITE_CONVERSIONS (pixel CONTENT_VIEW) is the correct optimization goal for website traffic.** POST_ENGAGEMENT optimizes for likes/comments — people who never leave Facebook. The optimization goal is the single biggest lever: $2.31/session (OFFSITE_CONVERSIONS) vs $8.62/session (POST_ENGAGEMENT). Always use OFFSITE_CONVERSIONS when the goal is website visits. (2026-03-13)
8. **Broad targeting + Advantage Audience outperforms custom audience targeting.** Watch this sale (no custom audiences, just neighborhoods + Advantage Audience) beats Is Now Good Time (custom audiences: Robina/VL Buyers, Lookalike). Let Facebook's algorithm find the right people. (2026-03-13)

---

## 7. CURRENT STATE (update each session)

**Last audit:** 2026-03-13
**Active campaigns:** Engagement: Is Now a Good Time to Buy, Engagement: Watch this sale, Engagement: How it Sold, Awareness: Fields Photography, Enagagement: Evergreen, Page Likes: Property Data Posts
**Paused/killed:** Engagement: Analyst (deleted 2026-03-13), Engagement: Is Now a Good Time to Sell (paused), V01_Traffic (paused), Engagement: Construction (paused)
**Active experiments:**
1. **Experiment #1: Property Stories** (started 2026-03-13, review ~Mar 27) — 3 new property-specific story ads (Water Views $1.49M, Robina 6mo flip, Sunbird St auction) in Watch this sale adset. Hypothesis: property stories will outperform suburb overviews by >50% on cost/session.
2. **Experiment #2: Landing Page — Article vs Product** (started 2026-03-13, review ~Mar 27) — "Upper Limit Test: Burleigh Waters" ad duplicated with URL pointing to `/property/69a96c6b7d351715fda97f4c` instead of article page. Hypothesis: direct-to-property landing pages will have higher engagement than article landing pages.
3. **Experiment #3: Optimization Goal Isolation** (started 2026-03-13, review ~Mar 27) — "Is Now a Good Time to Buy: BW" duplicated from POST_ENGAGEMENT adset into OFFSITE_CONVERSIONS adset. Hypothesis: same content will achieve >50% lower cost/session under OFFSITE_CONVERSIONS.

**Total lifetime spend:** $517.79
**Total sessions:** 48
**Best performer:** "Someone Bought This Home 18 Months Ago" — $0.70/session
**11 decisions logged** in `ad_decisions` collection on 2026-03-13

---

## 8. CROSS-REFERENCE: User's Ads Manager Snapshot

User exported Ads Manager data to `/home/fields/Fields_Orchestrator/drafts/ads-snapshot-13th-march.md` on 2026-03-13. Use this to cross-reference API data with what user sees in the UI when discrepancies arise.

#### Fields Estate slogan correction

The Fields Estate slogan/tagline is **"Smarter with data"** — not "Know your ground".

CLAUDE.md Section 6 (Editorial Voice) lists "Know your ground" as the tagline, but Will corrected this on 2026-03-14. Always use "Smarter with data" in any brand-facing output (ads, images, footers, etc.).


### Project State & Decisions

#### Active A/B Experiments (March 2026)

## Experiment 1: /for-sale Page A/B Test
- **Key:** `for_sale_page_v1`
- **Variants:** `control`, `test_a` (data intelligence cards — PRIMARY), `test_b` (buyer intent filters), `test_c` (engagement & conversion)
- **Split:** 25/25/25/25 deterministic by visitor_id hash
- **Started:** 2026-03-16
- **Why:** FB ads promise data intelligence but page shows generic cards. Test A delivers on the ad promise.
- **Traffic source:** 2 FB campaigns (~$42/day, ~217 LPVs/day) + 3 Google Search campaigns (Robina/VL/BW, 0 impressions as of launch)
- **Preview:** `?variant=control|test_a|test_b|test_c` (QA only, not for ad URLs)

## Experiment 2: /discover Scroll vs Swipe
- **Key:** `discover_mode_v1`
- **Variants:** `scroll` (Instagram-style vertical feed), `swipe` (Tinder-style one-at-a-time)
- **Split:** 50/50 deterministic by visitor_id hash
- **Started:** 2026-03-16
- **Why:** Testing discovery-first browsing funnel for Facebook users in "browse mode"
- **Preview:** `?mode=scroll|swipe` (QA only)
- **Categories:** `?category=prestige_pools|family_4bed|under_1m|waterfront|big_land|renovated|just_sold`
- **Algorithm:** useDiscoveryAlgorithm hook — 7-dimension preference vector, learns from view time/saves/more-like-this

## Data Locations
- **Session tracking:** `CRM_All_Data.sessions` — `active_variants` field on each session + per-page events in `pages[]`
- **Visitor tracking:** `CRM_All_Data.visitors` — aggregated by IP
- **Daily aggregates:** `system_monitor.website_daily_metrics` → `experiments` field
- **Ad decisions:** `system_monitor.ad_decisions` — search by tags
- **Metrics collector:** `scripts/website-metrics-collector.py` (cron 23:30 AEST)

## Full Documentation
- `/home/fields/Fields_Orchestrator/drafts/experiment-documentation.md` — complete experiment doc with hypotheses, analysis queries, key files, when to conclude
- `/home/fields/Fields_Orchestrator/drafts/for-sale-ab-test-plan.md` — original /for-sale plan (detailed)

**How to apply:** When user asks about experiments, results, or analysis — read the full doc. Minimum sample: 800 sessions (Exp 1) / 300 sessions (Exp 2). Expected timeline: ~15 days (Exp 1) / ~6 days (Exp 2).

#### CEO Agent System

Three AI agents (Engineering, Growth, Product) collectively act as strategic advisors. They analyse company data and produce proposals but CANNOT modify production systems.

**Why:** Solo founder needs strategic oversight without hiring — agents review fix history, metrics, experiments, and data quality daily and surface actionable recommendations.

**How to apply:** Review proposals in `system_monitor.ceo_proposals` or the sandbox repo. Implement approved proposals via Claude IDE on the orchestrator VM.

## Architecture
- **Compute:** Codex CLI on `property-scraper` VM (35.201.6.222, user: `fields-orchestrator-vm`)
- **Context:** `Will954633/fields-ceo-context` — daily snapshot from orchestrator VM
- **Sandbox:** `Will954633/fields-ceo-sandbox` — proposals + PoC code
- **Proposals:** `system_monitor.ceo_proposals` MongoDB collection
- **Model:** `gpt-5.4` via Codex CLI (authenticated via `codex login --with-api-key`)

## Daily Flow (cron on orchestrator VM)
1. **02:03 AEST** — `ceo-context-export.py` exports data bundle to `fields-ceo-context` repo
2. **02:33 AEST** — `ceo-agent-launcher.py` SSHs to property-scraper, runs agents via `codex exec`
3. Agents read context, produce `proposals/<date>_<agent>.json`
4. Proposals pushed to GitHub sandbox repo + MongoDB

## Key Scripts
- `scripts/ceo-context-export.py` — bundles CLAUDE.md, OPS_STATUS, fix history, metrics, schema, memory
- `scripts/ceo-agent-launcher.py` — SSH orchestrator that triggers agents on property-scraper
- `scripts/ceo-agent-prompts.sh` — generates role-specific prompts (deployed on property-scraper at `~/ceo-agents/`)

## SSH Access
```bash
ssh fields-orchestrator-vm@35.201.6.222  # or internal: 10.152.0.3 (didn't work, use external)
```

## Manual Run
```bash
# From orchestrator VM:
python3 scripts/ceo-agent-launcher.py --agent engineering  # single agent
python3 scripts/ceo-agent-launcher.py              # all three

# Directly on property-scraper:
cd ~/ceo-agents/sandbox && codex exec -m gpt-5.4 --full-auto "$(bash ~/ceo-agents/ceo-agent-prompts.sh engineering 2026-03-16)"
```

## Cost
~123K tokens per agent run ≈ ~$0.20/agent ≈ ~$0.60/day for all three ≈ ~$18/month

#### Website Intelligence System

**Website Intelligence system built 2026-03-16** — full scientific tracking of website changes and visitor behavior.

## Collections (all in `system_monitor`)
- `website_daily_metrics` — one doc/day, aggregated from CRM_All_Data.sessions (cron 23:30 AEST, 90-day retention)
- `website_change_log` — audit trail of website changes with baseline + impact snapshots
- `website_deploy_events` — every website file push logged with commit SHA + files
- `website_experiments` — A/B tests with variant tracking, baseline/progress/verdict

## Scripts (all in `scripts/`)
- `website-metrics-collector.py` — daily cron, reads sessions, writes daily aggregates. Supports `--backfill N`, `--print`, `--date`
- `website-change-log.py` — log/review/list/pending subcommands. Auto-captures 7-day baseline on `log`
- `website-deploy-tracker.py` — log/list subcommands. Called after every `gh api` push of website files
- `website-experiment-log.py` — create/snapshot/review/close/list/history. Mirrors ad-experiment-log.py exactly
- `website-review-dump.py` — full performance review dump. Supports `--days`, `--page`, `--changes`, `--experiments`, `--json`

## Frontend
- `visitorTracker.ts` has `getVariant(key, variants)` — deterministic hash of visitor_id, included as `active_variants` in every tracking event
- `system-monitor.mjs` has `website-changes` and `website-metrics-trend` endpoints
- `OpsPage.tsx` has "Website Intelligence" panel showing daily trend, change log, active experiments

## CLAUDE.md Mandatory Workflow
After every website file push: (1) log deploy event, (2) log change if testable, (3) snapshot experiments if affected.
Review cadence: `pending` check for 7+ day unreviewed changes, `review` for before/after comparison.

## Traceability Chain
`website_change_log` (what+why) → `website_deploy_events` (when) → `website_daily_metrics` (before/after metrics) → `review` command (delta analysis)

**Why:** Enables linking specific code changes to visitor behavior shifts. Required for website A/B testing and data-driven optimization.
**How to apply:** Always log website changes. Review pending changes weekly. Use experiments for any UI hypothesis.


### External References

#### Facebook Ad Review System

## Quick Start — Ad Review
```bash
source /home/fields/venv/bin/activate && set -a && source /home/fields/Fields_Orchestrator/.env && set +a
python3 scripts/ad-review-dump.py --summary          # Account overview
python3 scripts/ad-review-dump.py --active --top 10   # Top 10 active by spend
python3 scripts/ad-review-dump.py --id <AD_ID>        # Deep dive single ad
python3 scripts/ad-review-dump.py --active --sort sessions  # Sort by website sessions
python3 scripts/ad-review-dump.py --json              # Machine-readable output
```

## MongoDB Collections (all in `system_monitor` database)

| Collection | What | Updated by | Schedule |
|-----------|------|-----------|----------|
| `ad_profiles` | Per-ad profile: creative, targeting, 7d/14d/30d/lifetime metrics, attribution summary | fb-metrics-collector.py | 12:00 + 23:00 AEST |
| `ad_daily_metrics` | Per-ad per-day metrics (spend, impressions, clicks, CTR, CPC, CPM, reach, link clicks) | fb-metrics-collector.py | 12:00 + 23:00 AEST |
| `ad_demographics` | Per-ad age/gender breakdown | fb-metrics-collector.py | 23:00 AEST only |
| `ad_placements` | Per-ad platform/position breakdown | fb-metrics-collector.py | 23:00 AEST only |
| `ad_attribution` | Per-ad website outcomes (sessions, engagement, entry pages, properties viewed, geo, cost/session) | fb-attribution-builder.py | 23:15 AEST |
| `facebook_ads` | Legacy latest-snapshot (backward compat) | fb-metrics-collector.py | 12:00 + 23:00 AEST |

## Website Session Attribution
- Sessions in `CRM_All_Data.sessions` with `utm.content` = Facebook ad_id
- `utm.term` = adset_id, `utm.campaign` = campaign_id
- Engagement levels: bounce / light / engaged / deep
- Visitor tracking via `ip_raw` → `CRM_All_Data.visitors` (geo, device, return visits)

## Key Queries for Interactive Reviews
```python
from pymongo import MongoClient
client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"])
sm = client["system_monitor"]

# All active ad profiles with attribution
profiles = list(sm["ad_profiles"].find({"effective_status": "ACTIVE"}))
attrs = {a["_id"]: a for a in sm["ad_attribution"].find({"_id": {"$ne": "summary"}})}

# Daily trend for a specific ad
daily = list(sm["ad_daily_metrics"].find({"ad_id": AD_ID}).sort("date", 1))

# Sessions from a specific ad
sessions = list(client["CRM_All_Data"]["sessions"].find({"utm.content": AD_ID}))

# Account-level attribution summary
summary = sm["ad_attribution"].find_one({"_id": "summary"})
```

## Ops Dashboard API
- `GET /api/monitor/ad-profiles` — list all ads (slim, with sparkline data)
- `GET /api/monitor/ad-profiles?status=ACTIVE` — active only
- `GET /api/monitor/ad-profiles?sort=sessions` — sort by website sessions
- `GET /api/monitor/ad-profiles?id=<AD_ID>` — single ad full detail (profile + attribution + demographics + placements)

## Cron Schedule
- 12:00 AEST — `fb-metrics-collector.py --quick` (metrics only, no demographics)
- 23:00 AEST — `fb-metrics-collector.py` (full: metrics + demographics + placements)
- 23:15 AEST — `fb-attribution-builder.py` (joins ad data with website sessions)

## When to Review Ads
User prefers interactive reviews (not automated daily suggestions). Ads need time to run — don't review daily. When user asks, run `ad-review-dump.py` and analyze the output together.

<!-- MEMORY_SECTION_END -->
