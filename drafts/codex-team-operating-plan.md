# Codex Team Operating Plan
**Created:** 17 March 2026  
**Purpose:** Define the full AI team structure for the second Google VM running Codex, including roles, cadence, handoffs, guardrails, and rollout order.

## 1. Goal

Use the second VM as a dedicated management and analysis environment, not a production executor.

The Codex VM should:
- read exported company context
- inspect the sandbox repo
- produce proposals, plans, and proof-of-concept code
- surface the highest-leverage actions for Will

The Codex VM should not:
- write directly to production databases
- deploy code to production
- modify ads directly
- act as a hidden automation layer without review

That separation is the point. The orchestrator VM remains the system of record and the production executor. The Codex VM becomes the strategic team room.

## 2. VM Split

### Orchestrator VM
- Owns production code, cron, MongoDB access, website logging, ad workflows, and live repairs
- Exports the daily context bundle
- Receives approved proposals and implemented fixes
- Stores proposal records in `system_monitor.ceo_proposals`

### Codex VM
- Pulls the context repo and sandbox repo
- Runs multi-agent analysis in an isolated workspace
- Writes proposal JSON files and optional PoC code
- Pushes proposals back to the sandbox repo only

## 3. Team Structure

The full team should be designed as an eight-role org, but only four roles should run daily at first.

### Command Layer

#### 1. Chief of Staff
- Purpose: Convert many agent outputs into one founder-ready operating brief.
- Core question: What are the 1 to 3 actions that matter most today?
- Daily output: `proposals/YYYY-MM-DD_chief_of_staff.json`
- Runs: after all daily specialist agents finish
- Status: planned, not yet automated

### Daily Core Team

#### 2. Engineering Agent
- Purpose: Reliability, pipeline failures, technical debt, infra risk, fragile code paths
- Current status: implemented
- Daily output: `proposals/YYYY-MM-DD_engineering.json`

#### 3. Product Agent
- Purpose: Data quality, user experience, feature prioritisation, differentiation
- Current status: implemented
- Daily output: `proposals/YYYY-MM-DD_product.json`

#### 4. Growth Agent
- Purpose: Ads, landing pages, funnel health, experiment ideas, content distribution
- Current status: implemented
- Daily output: `proposals/YYYY-MM-DD_growth.json`

#### 5. Data Quality Agent
- Purpose: Listing coverage, enrichment gaps, schema drift, stale data, trust risks
- Core question: Where is bad or missing data undermining the product?
- Daily output: `proposals/YYYY-MM-DD_data_quality.json`
- Status: recommended next role to add

### Triggered / Weekly Specialists

#### 6. QA / Release Agent
- Purpose: Review website and API changes before release, check test gaps and regression risk
- Trigger: website changes, Netlify function changes, pipeline refactors
- Weekly output or event-driven output
- Status: phase 2

#### 7. Content / SEO Agent
- Purpose: Article pipeline, topical authority, search intent coverage, landing-page content gaps
- Trigger: weekly content planning or article backlog review
- Status: phase 2

#### 8. Market Intelligence Agent
- Purpose: Competitor tracking, suburb opportunity mapping, product positioning, external shifts
- Trigger: weekly strategy review
- Status: phase 2

## 4. Recommended Rollout

### Phase 1: Run Now
- Engineering
- Product
- Growth
- Chief of Staff

This is the smallest complete leadership loop. Three specialists generate raw proposals. Chief of Staff ranks and consolidates them into one daily brief.

### Phase 2: Add After 1 Week of Stable Runs
- Data Quality

Add this next because product trust is downstream of data quality, and current OPS state already shows coverage and freshness issues.

### Phase 3: Add On Demand
- QA / Release
- Content / SEO
- Market Intelligence

These roles should not run daily until the base loop is stable and useful.

## 5. Daily Operating Cadence

### 02:03 AEST
- Orchestrator VM exports fresh context to `fields-ceo-context`

### 02:15 AEST
- Codex VM pulls latest `context` and `sandbox`
- Preflight checks:
  - required files exist
  - today’s context date matches
  - repo pull succeeded
  - previous run is not still active

### 02:20 AEST
- Engineering, Product, Growth run in parallel
- Data Quality joins here once enabled

### 02:35 AEST
- Chief of Staff reads all proposal outputs
- Produces one ranked operating brief with:
  - top priorities
  - items to implement today
  - items to defer
  - conflicts between agents
  - open questions for Will

### 02:40 AEST
- Sandbox repo push
- Proposal JSON upsert into `system_monitor.ceo_proposals`

### Morning Founder Review
- Will reviews only the Chief of Staff brief first
- Detailed agent proposals are supporting material, not the front door

## 6. Proposal Contract

Every agent proposal should contain:
- `agent`
- `date`
- `summary`
- `findings`
- `proposals`
- `status`
- `created_at`
- `updated_at`

Additional standard fields should be added across all agents:
- `priority_score` — 1 to 100
- `time_horizon` — `today|this_week|later`
- `depends_on` — list of proposal IDs or titles
- `blocks` — what this proposal unlocks
- `owner` — usually `will` or `codex_impl`
- `decision_required` — boolean

Chief of Staff should add:
- `daily_brief`
- `top_3`
- `do_not_do`
- `conflicts`
- `recommended_sequence`

## 7. Handoff Rules

### Engineering → Product
- When a reliability issue affects data trust or UX, Engineering flags Product explicitly.

### Product → Growth
- When product gaps weaken conversion, Product frames the user problem and Growth turns it into landing-page or funnel tests.

### Growth → Product
- When ad or landing-page data reveals promise mismatch, Growth opens a product-facing recommendation.

### Data Quality → Everyone
- Data Quality can veto optimistic product or growth recommendations if the underlying data is not trustworthy enough.

### Chief of Staff → Founder
- No raw agent flood.
- One short brief first.
- Supporting detail second.

## 8. Decision Rights

### Agents can do
- analyze
- rank
- propose
- write PoC code in sandbox
- identify blockers

### Agents cannot do
- ship to production
- edit ads directly
- write to production DB
- change cron or services on the orchestrator VM without explicit approval

### Founder decides
- what gets implemented
- what gets deferred
- when a specialist role becomes permanent
- whether a proposal becomes a tracked experiment

## 9. Success Metrics

The team is working if it produces fewer, better actions.

Track:
- proposals generated per day
- proposals accepted by Will
- accepted proposals implemented
- implemented proposals with measurable impact
- duplicate proposal rate
- false-positive proposal rate
- time saved for founder review

Target after 14 days:
- at least 60% of daily briefs contain 1 or more actionable items
- duplicate proposal rate under 20%
- founder review time under 10 minutes per day

## 10. Founder-Facing Output

The daily deliverable should read like this:

1. Top 3 actions for today
2. Why they matter now
3. What not to spend time on
4. Dependencies or risks
5. Links to underlying agent proposals

If the team produces five separate long reports without synthesis, it has failed.

## 11. Recommended File and Collection Model

### Sandbox repo
- `proposals/YYYY-MM-DD_engineering.json`
- `proposals/YYYY-MM-DD_product.json`
- `proposals/YYYY-MM-DD_growth.json`
- `proposals/YYYY-MM-DD_data_quality.json`
- `proposals/YYYY-MM-DD_chief_of_staff.json`
- `engineering/...`, `product/...`, `growth/...`, `data_quality/...` for PoC code

### MongoDB
- Continue using `system_monitor.ceo_proposals`
- Recommended later additions:
  - `system_monitor.ceo_runs`
  - `system_monitor.ceo_briefs`
  - `system_monitor.ceo_tasks`

These should wait until the proposal quality is proven.

## 12. Immediate Implementation Order

1. Keep the current three-agent launcher as the stable base.
2. Add a Chief of Staff role that reads other proposal files and writes one synthesis file.
3. Add Data Quality as the fourth specialist role.
4. Standardise proposal schema across all agents.
5. Add run metadata so failures are visible.
6. Add weekly specialist roles only after the daily loop proves useful.

## 13. Anti-Patterns

Do not:
- add six new agents at once
- let every agent run daily without a clear reason
- allow raw proposal spam into AGENTS memory without triage
- treat the Codex VM as a silent production executor
- optimise for volume of ideas over implementation rate

## 14. Bottom Line

The second VM should operate as a compact AI leadership team.

The right first version is not a giant org chart. It is:
- three working specialists
- one synthesis role
- one clear daily brief
- explicit separation from production

That gives Fields a real management loop without creating another uncontrolled system to maintain.
