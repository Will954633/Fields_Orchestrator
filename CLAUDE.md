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
- **No valuation references in Facebook posts** — user not confident in accuracy for public-facing posts yet.
- **Forbidden words:** "stunning", "nestled", "boasting", "rare opportunity", "robust market"
- **Number format:** `$1,250,000` not "$1.25m", suburbs always capitalised

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

Operations agent on `fields-orchestrator-vm` (GCP, australia-southeast1-b, e2-medium, IP: 35.189.1.73). Full bash access — read/edit files, run scripts, query databases, deploy via GitHub.

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
| `/` | MarketIntelligencePage | Newspaper-style articles by suburb (nav: "News") |
| `/market-metrics/:suburb` | MarketMetricsPage | Data charts by category (nav: "Market Intelligence") |
| `/for-sale` | ForSalePage | Active property listings |
| `/property/:id` | PropertyPage | Property detail + editorial + valuation |
| `/analyse-your-home` | AnalyseYourHomePage | Conversion landing page |
| `/market-intelligence/:suburb` | MarketIntelligencePage | Same as homepage, explicit suburb |
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
- **Confidence:** 90% CI via `1.645 * weighted_std_dev`, level = High/Medium/Low/Very Low
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
- **Model:** Claude Opus 4.6 for all agents
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
- **Pixels:** `1491613936314260` (Fields, primary) + `137811233253065` (Content, passive)
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
