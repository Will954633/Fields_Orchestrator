# CEO Agent Expansion — Upgraded Roles, Context, and Capabilities

> **Date:** 2026-03-30
> **Status:** Approved for implementation
> **Trigger:** Agents proved their value in focus system review. Time to expand their scope and capabilities.

---

## Role Changes

### Chief of Staff → Chief of Staff + CFO

The Chief of Staff agent already synthesises across all agents. Expanding its scope to include financial oversight:

**New CFO responsibilities:**
- Track monthly burn rate (Anthropic, Google, OpenAI, ad spend, infrastructure)
- Flag when spending exceeds projections or budget caps
- Track revenue progress against Q3 targets
- Monitor grind backlog: what admin/accounting tasks are overdue and by how long?
- Tax deadline awareness: flag milestones for 2025 (May) and 2026 (September) tax returns
- When proposing sprint priorities, factor in financial constraints

**Why Chief of Staff and not a new agent:** Adding a 6th agent increases cost and coordination overhead. The Chief of Staff already runs after specialists and synthesises — financial context is a natural extension of its synthesis role.

### Product Agent → Product Lead

**Expanded ownership:**
- Owns conversion surface specs (lead capture designs, CTA copy, placement)
- Owns measurement plans for each surface (PostHog event schema, conversion targets)
- Owns Friday sprint decision memos (continue/cut/double-down/defer)
- Produces founder call script and lead-quality rubric
- Researches cross-industry case studies for every product challenge

### Growth Agent → Growth Lead + Ad Memo Owner

**Expanded ownership:**
- Owns the weekly ad performance memo (specific pause/scale/create recommendations)
- Owns the content engagement report (which types drove most engagement)
- Owns the cost-per-lead tracking and funnel analysis
- Produces Facebook content brief data inputs (trending topics, best-performing formats)

### Engineering Agent → Engineering Lead + Infra Owner

**Expanded ownership:**
- Owns the morning analyser script (maintenance, iteration)
- Owns backup scraper development plan and weekly progress report
- Owns the proposal status tracking system
- Owns infrastructure cost monitoring (Cosmos RU, Netlify builds, VM costs)

---

## New Context Sources

### 1. Knowledge Base Access

**What:** Export a KB summary to agent context daily.

**Implementation:** Add to `ceo-context-export.py`:
```python
# Generate KB summary
kb_summary = subprocess.run(
    ["python3", "scripts/search-kb.py", "strategy marketing real estate business", "--max", "20"],
    capture_output=True, text=True, cwd=ORCHESTRATOR_DIR
).stdout

# Also include KB category listing
kb_categories = {}
for category_dir in Path("/home/fields/knowledge-base/").iterdir():
    if category_dir.is_dir():
        count = len(list(category_dir.glob("*.json")))
        kb_categories[category_dir.name] = count
```

**Export path:** `context/knowledge-base/kb_summary.md` + `context/knowledge-base/kb_categories.json`

**Agent directive addition:** "Before proposing strategy changes, search the knowledge base context for relevant prior strategy documents, meeting notes, and book excerpts. The KB contains Kara Johnson's consultation notes, YouTube strategy books, marketing frameworks, and Will's business model decisions."

### 2. Accounting Data

**What:** Monthly financial summary exported to context.

**Implementation:** Add to `ceo-context-export.py`:
```python
# Pull accounting summary from system_monitor or accounting system
# For now: static summary updated monthly, later: auto-generated from ledger data
accounting_summary = {
    "entities": ["William Simpson Personal", "Maxamra Trust", "Rossmax Pty Ltd"],
    "monthly_burn": {
        "ad_spend_projected": 2377.56,  # from ad metrics
        "infrastructure": {
            "cosmos_db": "~$30/month (serverless)",
            "gcp_vms": "~$80/month (2 VMs)",
            "netlify": "free tier",
            "anthropic_api": "pull from billing",
            "openai_api": "pull from billing",
            "google_ads_api": "free (basic access)"
        },
        "ai_compute": {
            "anthropic_max": "subscription",
            "openai_codex": "~$18/month (CEO agents)"
        }
    },
    "tax_status": {
        "2025_return": "overdue - target May 2026",
        "2026_return": "target September 2026",
        "payg": "amount TBD"
    },
    "grind_backlog": {
        "overdue": ["2025 tax return", "PAYG amount", "bank reconciliation"],
        "in_progress": ["Ray White invoice tracking", "API spend monitoring"],
        "scheduled": ["WISE integration", "monthly book-keeping rhythm"]
    },
    "revenue": "pre-revenue"
}
```

**Export path:** `context/financial/accounting_summary.json`

**Agent directive (Chief of Staff/CFO):** "Review the financial summary daily. Flag: (1) if monthly burn is trending above $3,000, (2) if any grind task has been overdue for >2 weeks, (3) if tax deadlines are approaching without preparation progress. Factor financial constraints into sprint priority recommendations."

### 3. Case Study Knowledge Base

**What:** A persistent, growing repository of case studies and benchmarks that agents find during research.

**Implementation:** New repo `Will954633/fields-ceo-knowledge` or directory in `ceo-agent-memory/shared/`

**Structure:**
```
ceo-agent-knowledge/
├── case_studies/
│   ├── noah_escobar_youtube_leads.md
│   ├── realtor_com_browse_to_action.md
│   ├── magri_cabinets_zero_to_leads.md
│   ├── unbounce_landing_page_benchmarks.md
│   └── ... (growing)
├── benchmarks/
│   ├── real_estate_conversion_rates.md
│   ├── facebook_engagement_benchmarks.md
│   ├── youtube_retention_benchmarks.md
│   └── ... (growing)
├── competitor_analysis/
│   ├── gold_coast_youtube_channels.md
│   └── ...
└── INDEX.md  ← auto-generated, lists all entries with one-line summaries
```

**Agent directive:** "After finding a relevant case study or benchmark during research, write it to `ceo-agent-knowledge/case_studies/` or `ceo-agent-knowledge/benchmarks/` in structured format. Future runs can reference this accumulated intelligence. Always check existing entries before re-researching a topic."

This compounds: after 30 daily runs, the agents will have ~30-50 case studies, benchmark sets, and competitor analyses — all indexed and searchable.

---

## Updated Agent Prompt Changes

### Engineering Agent — Add to prompt:
```
## Infrastructure & Morning Analyser Ownership
You own the morning focus analyser script at scripts/morning-focus-analyser.py.
Review its output quality weekly. If it's not triaging accurately, propose fixes.
You own backup scraper development. Report coverage progress weekly.
You own infrastructure cost monitoring: check context/financial/ for cost data.

## Knowledge Base Context
Read context/knowledge-base/kb_summary.md for relevant strategy and technical docs.
Read context/knowledge-base/kb_categories.json to know what's available.
```

### Product Agent — Add to prompt:
```
## Product Lead Ownership
You own conversion surface specifications. For every capture surface, produce:
- Exact copy (headline, subhead, CTA label)
- Event schema (impression, expand, submit_start, submit_success)
- Success metric and target (e.g., 5-8% conversion per Unbounce benchmark)
- Friday decision memo: continue/cut/double-down/defer

You own the case study library. After finding relevant research, save it to
ceo-agent-knowledge/case_studies/ so future runs can reference it.

Read context/knowledge-base/ for strategy docs, Kara Johnson notes, and book excerpts.
Read context/focus/case_studies.md for previously collected case studies.
```

### Growth Agent — Add to prompt:
```
## Growth Lead Ownership
You own the weekly ad performance memo. Every run, produce:
- Specific ad IDs to pause/scale/create
- Cost-per-lead tracking
- Budget reallocation recommendations
- Content engagement summary: which types drove most comments/shares/clicks?

Read context/financial/accounting_summary.json for budget constraints.
Read context/knowledge-base/ for marketing strategy docs.
```

### Chief of Staff — Add to prompt:
```
## CFO Responsibilities (NEW)
In addition to synthesising agent proposals:
- Review context/financial/accounting_summary.json every run
- Flag: monthly burn trending above $3,000, grind tasks overdue >2 weeks, tax deadlines approaching
- Factor financial constraints into sprint priority recommendations
- Track revenue progress against Q3 targets
- When recommending sprint priorities, consider: what is the cost of delay? What is the cost of action?

Read context/knowledge-base/ for strategy context.
Read context/focus/ for sprint plan, milestones, and Q3 countdown.
```

---

## Implementation Steps

| Step | What | Effort | Priority |
|------|------|--------|----------|
| 1 | Update `ceo-context-export.py` to export focus/, financial/, knowledge-base/ | 1 session | P0 |
| 2 | Update `ceo-agent-prompts.sh` with expanded role directives | 0.5 session | P0 |
| 3 | Create `ceo-agent-knowledge/` directory structure on sandbox repo | 0.5 session | P1 |
| 4 | Seed case study files from today's agent review findings | 0.5 session | P1 |
| 5 | Add accounting summary generation to context export | 0.5 session | P1 |
| 6 | Add KB summary generation to context export | 0.5 session | P1 |
| 7 | Update `codex_team_plan.yaml` with new role definitions | 0.5 session | P2 |

Steps 1-2 are already being built by background agents in this session.
