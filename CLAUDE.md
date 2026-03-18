# CLAUDE.md — Fields Estate VM Agent

This file gives the Claude Code agent running on this VM full context about all systems.
Working directory: `/home/fields/Fields_Orchestrator`

---

## ⚡ MANDATORY: FIX HISTORY LOGGING

**Every time you fix a bug, repair a script, or change any code — you MUST write a log entry. Do this automatically, without being asked.**

Log location: `/home/fields/Fields_Orchestrator/logs/fix-history/YYYY-MM-DD.md` (one file per day, AEST date).

**Format — append to the file (create it if it doesn't exist):**
```markdown
## [PROBLEM-ID] Short description — HH:MM AEST

**Symptom:** What was broken / what the user saw.
**Root cause:** Why it was broken.
**Fix:** What you changed and why.
**Files:** List of files modified.
**Recurrence:** First occurrence / Nth occurrence (check audit command below).
```

**Audit for recurring problems:**
```bash
grep -h "^## \[" logs/fix-history/*.md | sed 's/ — .*//' | sort | uniq -d
```

**When to write:** After every fix, before ending the session. Also at session start, read the last 2–3 fix-history files to spot recurring issues.

---

## ⚡ MANDATORY: AD DECISION LOGGING

**Every time you create, modify, pause, enable, or delete a Facebook or Google Ads campaign, ad set, or ad — you MUST write a decision log entry to MongoDB. Do this automatically, without being asked.**

**Collection:** `system_monitor.ad_decisions`

**Format — insert one document per decision:**
```python
{
    "date": "YYYY-MM-DD",
    "type": "new_campaign|pause|enable|budget_change|copy_test|audit|creative_change",
    "title": "Short description of what changed",
    "hypothesis": "Why we expect this to work / what we're testing",
    "findings": ["Bullet point data that informed this decision"],
    "data_snapshot": {
        # Relevant metrics, campaign IDs, budget figures, keyword data
    },
    "tags": ["google_ads", "facebook_ads", "campaign_name", etc.],
    "reasoning": "Why this decision was made — connects to strategy",
    "created_at": "ISO timestamp"
}
```

**When to write:**
- Creating a new campaign (Google or Facebook)
- Enabling or pausing a campaign
- Changing budget, keywords, ad copy, or targeting
- A/B test setup or conclusion
- Any audit or performance review that leads to action

**What this enables:** Complete institutional memory of every advertising decision, so we can trace what worked, what didn't, and why we made each choice. The `ad-review-dump.py` and `ad-experiment-log.py` scripts read this data.

**Related scripts:**
- `scripts/google-ads-metrics-collector.py` — Collects Google Ads metrics daily (cron: 12:15 + 23:10 AEST)
- `scripts/fb-metrics-collector.py` — Collects Facebook Ads metrics daily (cron: 12:00 + 23:00 AEST)
- `scripts/ad-experiment-log.py` — Log and track A/B experiments
- `scripts/ad-review-dump.py` — Interactive ad performance review
- `scripts/google_ads_manager.py` — Create/manage Google Ads campaigns

**Monitoring collections:**
| Collection | Platform | Purpose |
|---|---|---|
| `ad_decisions` | Both | Audit log of all advertising decisions |
| `ad_daily_metrics` | Facebook | Per-ad daily performance |
| `ad_profiles` | Facebook | Per-ad creative, targeting, aggregates |
| `ad_demographics` | Facebook | Age × gender breakdowns |
| `ad_placements` | Facebook | Platform × position performance |
| `ad_attribution` | Facebook | Website session attribution |
| `ad_experiments` | Facebook | A/B test tracking |
| `google_ads_daily_metrics` | Google | Per-campaign daily performance |
| `google_ads_profiles` | Google | Per-campaign config + aggregates |
| `google_ads_keywords` | Google | Keyword performance per 7d window |
| `google_ads` | Google | Latest snapshot |

---

## ⚡ MANDATORY: PUSH ALL CODE CHANGES TO GITHUB

**GitHub is our backup and source of truth. Every time you create, modify, or fix a file — you MUST push it to the appropriate GitHub repo. Do this automatically, without being asked. Code that only exists on the VM is not safe.**

### Rules
1. **No change is complete until it's in GitHub.** Editing a file locally is only half the job — always push it.
2. **Website files** (`Feilds_Website/01_Website/`) → push to `Will954633/Website_Version_Feb_2026` (see Section 4 for path mapping).
3. **Orchestrator files** (`Fields_Orchestrator/`) → push to the `Fields_Orchestrator` repo (this repo).
4. **Automation/article files** → push to `Will954633/fields-automation`.
5. **Scraper and valuation files** → push to their respective repos if they exist, or to `Fields_Orchestrator` as a fallback.
6. **New files count too** — if you create a new script, config, or utility, it must be pushed. Don't assume it will be backed up later.
7. **Exclude from push:** `.env` files, credentials, `node_modules/`, `__pycache__/`, log files, and any file containing secrets.

### How to push (git push hangs on this VM — always use `gh api`):
```bash
# Update existing file:
SHA=$(gh api 'repos/OWNER/REPO/contents/PATH' --jq '.sha')
CONTENT=$(base64 -w0 < /local/path/to/file)
gh api 'repos/OWNER/REPO/contents/PATH' \
  --method PUT --field message="description of change" --field content="$CONTENT" --field sha="$SHA"

# New file (no sha needed):
CONTENT=$(base64 -w0 < /local/path/to/file)
gh api 'repos/OWNER/REPO/contents/PATH' \
  --method PUT --field message="add: description" --field content="$CONTENT"
```

### Why this matters
This VM is a single point of failure. If it goes down, we lose everything that isn't in GitHub. Treat GitHub as the disaster recovery backup for all code on this machine.

---

## ⚡ MANDATORY: WEBSITE CHANGE LOGGING

**Every time you push a website file to GitHub, you MUST log the deployment and (if applicable) the change. Do this automatically, without being asked.**

### After every website file push:
```bash
# 1. Log the deploy event (always)
python3 scripts/website-deploy-tracker.py log \
    --commit <COMMIT_SHA> \
    --files "path/to/file1.tsx,path/to/file2.css" \
    --message "Short description of change"

# 2. If the change has a hypothesis or is testable (not just a bug fix):
python3 scripts/website-change-log.py log \
    --title "Short description" \
    --type layout_change \
    --hypothesis "Expected impact on visitor behavior" \
    --files "file1.tsx,file2.css" \
    --pages "/for-sale,/property" \
    --commit <COMMIT_SHA> \
    --tags "cta,conversion"

# 3. If there's an active A/B experiment on affected pages:
python3 scripts/website-experiment-log.py snapshot --experiment <ID>
```

### Change types: `layout_change`, `copy_change`, `new_page`, `bug_fix`, `performance`, `style_change`, `feature`, `config`

### Review cadence:
```bash
# Check for changes needing review (7+ days old, no impact assessment):
python3 scripts/website-change-log.py pending

# Review a change (captures post-change metrics + compares to baseline):
python3 scripts/website-change-log.py review --change <ID>

# Full website performance dump:
python3 scripts/website-review-dump.py
```

### Why this matters
Without logging changes, we can't link visitor behavior shifts to specific code changes. This is how we build institutional knowledge about what works and what doesn't on the website.

---

## ⚡ MANDATORY: VISUAL VERIFICATION OF WEBSITE CHANGES

**After ANY change to website files (`Feilds_Website/01_Website/`, `netlify/functions/`, `src/`, `public/`), you MUST visually verify the affected page(s) before considering the task done. Do this automatically, without being asked.**

### How
```bash
# Inspect the affected page (wait for Netlify deploy to finish first)
node /home/fields/Fields_Orchestrator/scripts/site-inspector.js --url /AFFECTED_PAGE

# Then read the screenshot to verify rendering:
#   Read /tmp/site-inspect/<page-slug>/screenshot.png
# And check for console errors:
#   Read /tmp/site-inspect/<page-slug>/console.log
```

### When to inspect
| Trigger | What to inspect |
|---------|----------------|
| Changed a Netlify function | The page(s) that call that API |
| Changed a React component | The page(s) that render that component |
| Changed CSS/styles | Affected page in **both** desktop and `--mobile` viewports |
| Debugging a visual/rendering bug | Screenshot **before** and **after** your fix |
| User says "it looks wrong" or "broken layout" | Screenshot the page they're referring to |
| Deploying any frontend change | All affected pages |

### What to check in the screenshot
- Page renders without blank/white sections
- Text is readable, not overlapping
- Images and charts load (not placeholder boxes)
- Layout matches expected design (no broken grids)
- Console log has no JavaScript errors
- Network errors log is empty (no failed API calls)

### Quick reference
```bash
# Single page
node scripts/site-inspector.js --url /for-sale

# Mobile viewport
node scripts/site-inspector.js --url /for-sale --mobile

# Multiple pages
node scripts/site-inspector.js --url /for-sale,/market,/property/SOME_ID

# Specific element
node scripts/site-inspector.js --url /for-sale --element ".property-card"

# Scripted interaction flow
node scripts/site-inspector.js --url /for-sale --actions-file /tmp/site-actions.json

# Write artifacts to a dedicated run directory
node scripts/site-inspector.js --url /for-sale --output-dir /tmp/site-inspect/for-sale-debug

# Diagnostics only
node scripts/site-inspector.js --url /for-sale --preflight-only

# Output is always at /tmp/site-inspect/<slug>/
#   screenshot.png, page-text.txt, console.log, network-errors.log, page-info.json
#   action-log.json (when --actions-file is used)
```

---

## ⚡ LIVE OPS STATUS — READ THIS FIRST

> **`OPS_STATUS.md`** in this directory is auto-generated every 15 minutes and contains a live snapshot of all systems — exactly what you see at https://fieldsestate.com.au/ops. **Read it at the start of every session** to get current pipeline status, errors, data coverage, and API health.

```bash
cat /home/fields/Fields_Orchestrator/OPS_STATUS.md
# Or refresh it first:
python3 /home/fields/Fields_Orchestrator/scripts/refresh-ops-context.py && cat /home/fields/Fields_Orchestrator/OPS_STATUS.md
```

The file includes:
- Orchestrator pipeline: last run date, step-by-step status (✅/❌/⏳), failed steps
- Active listing counts per suburb (Robina, Burleigh Waters, Varsity Lakes, etc.)
- Website API health (all endpoints, response times, last checked)
- Data coverage status per suburb
- Scraper health (last scrape time per suburb)
- Article pipeline (last Ghost publish, last Netlify build)
- Repair queue (any pending repair requests)
- Recent errors (last 24h)

## 1. THE BUSINESS

**Fields Real Estate** is a property intelligence platform founded by **Will Simpson**, based on the Gold Coast, Queensland, Australia.

**Mission:** "We help buyers and sellers make informed real estate decisions through original analysis, local expertise, and transparent methodology."

**What we do:** We build and publish high-quality property data — valuations, market analysis, suburb intelligence, sales breakdowns — and distribute it via Facebook, YouTube, and Google advertising to attract buyers and sellers in our target market.

**Stage:** Early. We have not yet acquired our first customer. The focus right now is building the data infrastructure, content pipeline, and website to the point where the product speaks for itself. Every system we build is aimed at making the data more accurate, more useful, and more accessible than anything else available to buyers and sellers in our suburbs.

**Target market suburbs:**
- **Robina** — established master-planned community, strong unit and house market
- **Burleigh Waters** — premium family suburb, high demand, limited supply
- **Varsity Lakes** — lake-fronting properties, younger demographic, growth suburb

All three suburbs are in the southern Gold Coast corridor, approximately 20–30 minutes from the Gold Coast CBD (Surfers Paradise) and 50 minutes from Brisbane via the M1.

**Who you're working for:** Will Simpson (`will@fieldsestate.com.au`). He is the sole operator — developer, analyst, and founder. When making decisions about what to build or fix, think about what moves the needle for a solo operator trying to impress buyers and sellers with data quality and transparency.

---

## 2. WHO YOU ARE

You are the Fields Estate operations agent running on `fields-orchestrator-vm` (Google Cloud, australia-southeast1-b, e2-medium, IP: 35.189.1.73). You have full bash access to this VM and can read/edit files, run scripts, query the database, and deploy code to production via GitHub.

You are accessed via the Claude Code terminal at `https://vm.fieldsestate.com.au`, embedded in the ops dashboard at `https://fieldsestate.com.au/ops`.

---

## 2. FILESYSTEM LAYOUT ON THIS VM

```
/home/fields/
├── Fields_Orchestrator/        ← YOU ARE HERE (working dir)
│   ├── src/                    ← Orchestrator Python source
│   ├── config/
│   │   ├── settings.yaml       ← MongoDB URI, schedule, feature flags
│   │   └── process_commands.yaml ← All pipeline process definitions
│   ├── logs/                   ← orchestrator.log, claude-agent.log
│   ├── logs/runs/              ← Per-run structured logs (stdout/stderr per step)
│   ├── scripts/                ← Utility bash scripts
│   ├── claude-agent.py         ← Headless repair agent (polls MongoDB)
│   ├── repair-agent.py         ← Enrichment repair agent
│   ├── trigger-poller.py       ← Manual trigger executor
│   └── claude-terminal/        ← THIS TERMINAL SERVER
│       └── server.js           ← xterm.js + node-pty WebSocket bridge
├── Feilds_Website/             ← Full website codebase (mirrors GitHub)
│   ├── 01_Website → see Section 4
│   ├── 03_For_Sale_Coverage/   ← Property insights scripts
│   ├── 07_Valuation_Comps/     ← Valuation model scripts
│   ├── 08_Market_Narrative_Engine/ ← Market narrative precompute
│   └── 10_Floor_Plans/         ← Floor plan processing
├── Property_Data_Scraping/     ← Selenium scrapers
│   └── 03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/
│       └── run_complete_suburb_scrape.py  ← Main scraper
└── Property_Valuation/
    └── 04_Production_Valuation/ ← ML valuation model
```

---

## 3. ORCHESTRATOR PIPELINE

### Services
```bash
sudo systemctl status fields-orchestrator     # Main pipeline daemon
sudo systemctl status fields-trigger-poller   # Manual trigger executor
sudo systemctl status fields-claude-agent     # Headless repair agent
sudo systemctl status fields-terminal         # THIS terminal (xterm.js server)
sudo systemctl status ollama                  # LLaVA vision model
```

### Logs
```bash
tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log
tail -f /home/fields/Fields_Orchestrator/logs/claude-agent.log
bash /home/fields/Fields_Orchestrator/scripts/check_last_run.sh
# Per-step detail:
ls /home/fields/Fields_Orchestrator/logs/runs/ | tail -5
cat /home/fields/Fields_Orchestrator/logs/runs/<run-dir>/run_summary.json
```

### Pipeline Process Order
```
101 → 102* → 103 → 104* → 110 → 105 → 106 → 108 → 6 → 11 → 12 → 13 → 14 → 16 → 15 → 17 → 19 → 18 → 109 → 107
```
(*Sunday only)

| Phase | Processes | What it does |
|-------|-----------|--------------|
| 1 | 101, 102 | Selenium scrape Domain.com.au → `Gold_Coast_Currently_For_Sale` |
| 2 | 103, 104 | Sold monitoring → move records to `Gold_Coast_Recently_Sold` |
| 2.5 | 110 | Download property images → Azure Blob Storage |
| 3 | 105, 106, 108 | GPT-4 Vision photo + floor plan analysis |
| 4 | 6 | ML valuation model |
| 5 | 11–19 | Backend enrichment (room dims, suburb medians, insights, market narrative) |
| 6 | 109 | Coverage check vs live Domain count |
| 7 | 107 | Database audit (misplaced properties) |

### Manual Trigger
```bash
python3 /home/fields/Fields_Orchestrator/src/orchestrator_daemon.py --run-now
```

### Key Config Files
- `/home/fields/Fields_Orchestrator/config/settings.yaml` — schedule (20:30 AEST), MongoDB URI, target suburbs
- `/home/fields/Fields_Orchestrator/config/process_commands.yaml` — all process definitions

---

## 4. WEBSITE CODEBASE

**GitHub Repo:** `Will954633/Website_Version_Feb_2026`
**Live site:** `https://fieldsestate.com.au`
**Netlify site ID:** `43e4ad42-a75a-4dc7-be22-67fcda0ec98b`

### CRITICAL: Deployment Workflow
**ALL changes → GitHub first → Netlify auto-deploys. Never use `netlify deploy --prod` directly.**

```bash
# Push a file to GitHub (git push/fetch HANGS on this VM — always use gh api):
SHA=$(gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' --jq '.sha')
CONTENT=$(base64 -w0 < /home/fields/Feilds_Website/01_Website/LOCAL_PATH)
gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' \
  --method PUT --field message="msg" --field content="$CONTENT" --field sha="$SHA" --jq '.commit.sha'

# New file (no sha needed):
CONTENT=$(base64 -w0 < /home/fields/Feilds_Website/01_Website/LOCAL_PATH)
gh api 'repos/Will954633/Website_Version_Feb_2026/contents/PATH' \
  --method PUT --field message="msg" --field content="$CONTENT" --jq '.commit.sha'

# Force Netlify rebuild if needed:
curl -s -X POST https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d
```

### GitHub Repo Path Mapping
Website files sit at the **repo root**, not under `01_Website/`:
- `01_Website/netlify.toml` → `netlify.toml`
- `01_Website/src/...` → `src/...`
- `01_Website/netlify/functions/...` → `netlify/functions/...`
- `01_Website/public/...` → `public/...`
- `01_Website/scripts/...` → `scripts/...`

### Tech Stack
- React 19 + TypeScript + Vite + React Router 7
- Netlify Functions (Node.js serverless) for all APIs
- Azure Cosmos DB (MongoDB API) for data
- CSS Modules for styling

### Key Pages
| Page | Route | Purpose |
|------|-------|---------|
| ForSalePage | `/for-sale` | Active property listings |
| PropertyPage | `/property/:id` | Property detail + report |
| ValuePage | `/value/:id` | Valuation + NPUI scatter plot |
| MarketIntelligencePage | `/market` | Market charts + narrative |
| OpsPage | `/ops` | System monitor dashboard |
| ArticlePage | `/articles/:slug` | Ghost CMS articles |

### Key Netlify Functions
All in `netlify/functions/`, served at `/api/v1/` or `/api/monitor/`:
- `properties-for-sale.mjs` — Active listings + enrichment cross-reference
- `property.mjs` — Individual property data
- `valuation.mjs` — Valuation + NPUI data (pre-computed from `valuation_data` field)
- `market-narrative.mjs` — Market charts + narrative text
- `system-monitor.mjs` — All ops dashboard APIs
- `address-search.mjs` — Property address autocomplete

### Database Architecture
- `Gold_Coast_Currently_For_Sale` — Active listings per suburb. **Collections are lowercase_with_underscores** (e.g. `robina`, `burleigh_waters`, `varsity_lakes`). Use `db.list_collection_names()` to see all.
- `property_data.properties_for_sale` — Enriched data (154 properties with analysis)
- `system_monitor` — Ops monitoring collections

---

## 5. OPS DASHBOARD (`https://fieldsestate.com.au/ops`)

All panels are served by `netlify/functions/system-monitor.mjs`:

| Panel | API Endpoint | What it shows |
|-------|-------------|---------------|
| DB Validation | `GET /api/monitor/db-validation` | Live DB probes per pipeline step |
| Orchestrator | `GET /api/monitor/orchestrator` | Last 10 runs, per-step status |
| Web APIs | `GET /api/monitor/api-health` | Endpoint health + response times |
| Data Coverage | `GET /api/monitor/data-integrity` | Per-suburb enrichment % |
| Scraper Health | `GET /api/monitor/scraper-health` | Last scrape age per suburb |
| Audit Log | `GET /api/monitor/audit-log` | 14-day listing count history |
| Manual Triggers | `POST /api/monitor/trigger` | Enqueue pipeline process to VM |
| Repair Queue | `GET/POST /api/monitor/repair-queue` | Claude repair agent queue |
| Frontend Errors | `GET /api/monitor/website-errors` | Last 24h client errors |
| Article Pipeline | `GET /api/monitor/article-pipeline` | Ghost + Netlify build history |
| Article Workflows | `GET /api/monitor/article-workflows` | GitHub Actions (fields-automation) |

Auth: All endpoints require `Authorization: Bearer <OPS_AUTH_TOKEN>`.

### THIS TERMINAL SERVER
- Service: `fields-terminal` (systemd)
- Code: `/home/fields/claude-terminal/server.js`
- Stack: Node.js + node-pty + xterm.js (browser) + WebSocket
- nginx proxies `https://vm.fieldsestate.com.au` → `https://127.0.0.1:7681`
- SSL cert: Let's Encrypt at `/etc/letsencrypt/live/vm.fieldsestate.com.au/`
- Self-signed fallback: `/etc/ttyd-ssl/` (used by node server directly)

---

## 6. ARTICLE GENERATION SYSTEM

**GitHub Repo:** `Will954633/fields-automation`
**Ghost CMS:** `https://fields-articles.ghost.io`
**Ghost webhook → Netlify build hook:** `https://api.netlify.com/build_hooks/699e5501757e99ddd5c4b99e`

### Pipelines (all in `fields-automation/pipeline/`)
| Script | Schedule | Output |
|--------|----------|--------|
| `run_how_it_sold.py` | Event-triggered | Articles about recent sales |
| `run_watch_this_sale.py` | Weekly Mon 7am AEST | Weekly listing spotlights |
| `run_light_rail.py` | Monthly (25-day guard) | Light Rail Stage 3 article |
| `run_is_now_good_time.py` | Quarterly (80-day guard) | 5 suburb buy-now articles + charts |
| `run_update_pass.py` | Monthly | Updates 12 major project articles |
| `run_annual_refresh.py` | 1 February | Updates 5 evergreen articles |

All triggered via GitHub Actions workflows in `Will954633/fields-automation/.github/workflows/`.

### Publishing
```bash
# Push generated articles to Ghost (run from fields-automation checkout):
python3 scripts/push_to_ghost.py              # all unpushed
python3 scripts/push_to_ghost.py --pipeline watch_this_sale
```

### Tag → Slot Mapping (website front page)
- `state-of-market` → priority 1 (lead story)
- `market-insight` → priority 2
- `watch-this-sale` → priority 3
- `how-it-sold` → priority 4

### Editorial Voice
- Tagline: "Know your ground"
- No: "stunning", "nestled", "boasting", "rare opportunity", "robust market"
- Numbers: `$1,250,000` not "$1.25m", suburbs always capitalised

---

## 7. DATABASE

**Azure Cosmos DB (MongoDB API)**
Connection string in: `/home/fields/Fields_Orchestrator/config/settings.yaml` and all `.env` files.

```python
# Connect from Python
from pymongo import MongoClient
import yaml
with open("/home/fields/Fields_Orchestrator/config/settings.yaml") as f:
    cfg = yaml.safe_load(f)
client = MongoClient(cfg["mongodb"]["uri"])
```

```bash
# Quick query from bash
node -e "
const {MongoClient} = require('mongodb');
require('dotenv').config({path:'/home/fields/Feilds_Website/01_Website/.env'});
const c = new MongoClient(process.env.COSMOS_CONNECTION_STRING);
c.connect().then(async () => {
  const db = c.db('Gold_Coast_Currently_For_Sale');
  console.log(await db.listCollections().toArray());
  c.close();
});
"
```

### Key Databases
| Database | Purpose |
|----------|---------|
| `Gold_Coast_Currently_For_Sale` | Active listings — collections are **lowercase_with_underscores**: `robina`, `burleigh_waters`, `varsity_lakes`, `burleigh_heads`, `mudgeeraba`, `reedy_creek`, `merrimac`, `worongary`, `carrara` (plus `suburb_median_prices`, `suburb_statistics`, `change_detection_snapshots`) |
| `Gold_Coast_Recently_Sold` | Sold properties (per-suburb collections) |
| `Gold_Coast` | Master data |
| `property_data` | Enriched data (`properties_for_sale` collection) |
| `system_monitor` | Ops monitoring data |

---

## 8. ENVIRONMENT & CREDENTIALS

All credentials are in `.env` files on this VM — never hardcode them in code.
- `/home/fields/Fields_Orchestrator/.env` — COSMOS_CONNECTION_STRING, OPENAI_API_KEY, etc.
- `/home/fields/Feilds_Website/01_Website/.env` — Website-specific env vars
- `/home/fields/Feilds_Website/07_Valuation_Comps/.env` — Valuation service env
- `ANTHROPIC_API_KEY` — set in `/etc/environment` and `~/.bashrc`

GitHub CLI (`gh`) is authenticated and ready. Use `gh api` for all GitHub operations (not `git push` — it hangs).

---

## 9. COMMON TASKS

### Fix a failing pipeline step
```bash
# 1. Check what failed
bash scripts/check_last_run.sh
# 2. Look at the step's detailed logs
cat logs/runs/<latest-run>/01_step_<id>_*/stderr.log
# 3. Fix the script, test it
python3 /path/to/script.py --test
# 4. If it's a website file, push to GitHub (see Section 4)
```

### Deploy a website fix
```bash
# Edit the file locally
vim /home/fields/Feilds_Website/01_Website/netlify/functions/some-function.mjs
# Push to GitHub
SHA=$(gh api 'repos/Will954633/Website_Version_Feb_2026/contents/netlify/functions/some-function.mjs' --jq '.sha')
CONTENT=$(base64 -w0 < /home/fields/Feilds_Website/01_Website/netlify/functions/some-function.mjs)
gh api 'repos/Will954633/Website_Version_Feb_2026/contents/netlify/functions/some-function.mjs' \
  --method PUT --field message="fix: description" --field content="$CONTENT" --field sha="$SHA"
# Netlify auto-deploys — check: https://app.netlify.com/sites/lambent-tapioca-86ef75/deploys
```

### Restart this terminal server
```bash
sudo systemctl restart fields-terminal
sudo journalctl -u fields-terminal -n 20
```

### Check what's running
```bash
sudo systemctl list-units --state=active | grep fields
ps aux | grep -E "orchestrator|claude|poller|ollama" | grep -v grep
```

---

## Database Schema Reference

**IMPORTANT:** Before writing any MongoDB query, always read the schema snapshot:

```
read /home/fields/Fields_Orchestrator/SCHEMA_SNAPSHOT.md
```

This file is auto-generated daily and contains every collection name, field name, field type, and an example document from all active databases. Using it prevents field name errors, wrong collection queries, and missing data assumptions.

Key facts:
- Connection string is in env var `COSMOS_CONNECTION_STRING`
- Python driver: `pymongo` (available in `/home/fields/venv`)
- Always `source /home/fields/Fields_Orchestrator/.env` before running Python DB scripts
- Always activate venv: `source /home/fields/venv/bin/activate`
