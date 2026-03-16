#!/usr/bin/env python3
"""
CEO Agent Launcher — SSHes to property-scraper VM and runs Codex agents.

Replaces ceo-agent-launcher-remote.sh with a Python implementation that fixes:
  - JSON parsing: uses JSONDecoder.raw_decode to handle multi-line objects
  - Idempotent writes: upsert on (agent, date) instead of insert_one
  - Context cleanup: removes context snapshot before pushing to GitHub sandbox

Usage:
    python3 scripts/ceo-agent-launcher.py                     # run all agents
    python3 scripts/ceo-agent-launcher.py --agent engineering  # run one agent
    python3 scripts/ceo-agent-launcher.py --dry-run            # show what would happen
    python3 scripts/ceo-agent-launcher.py --list               # list available agents
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

# ── Config ──────────────────────────────────────────────────────────────────

REMOTE_HOST = "fields-orchestrator-vm@35.201.6.222"
REMOTE_DIR = "/home/fields-orchestrator-vm/ceo-agents"
CODEX_MODEL = "gpt-5.1-codex"
DATE_STR = datetime.now().strftime("%Y-%m-%d")
DRY_RUN = "--dry-run" in sys.argv
TEAM_PLAN_PATH = Path(__file__).resolve().parent.parent / "config" / "codex_team_plan.yaml"

# ── Agent Definitions ───────────────────────────────────────────────────────

AGENTS = {
    "engineering": {
        "name": "Engineering Agent",
        "focus": "Pipeline reliability, code quality, technical debt, infrastructure",
        "prompt": """You are the Engineering Agent for Fields Real Estate — a property intelligence startup on the Gold Coast, Australia. You are one of three AI agents that collectively act as the company's strategic leadership team.

## Your Role
You focus on **engineering reliability, code quality, technical debt, and infrastructure**. Your job is to:
1. Review recent fix history for recurring problems and propose permanent fixes
2. Analyse pipeline run data for failures, slowdowns, or fragility
3. Identify technical debt and propose refactoring
4. Review the codebase for bugs, security issues, or missing error handling
5. Prototype fixes in the sandbox when you have a concrete improvement

## Your Context
The `context/` directory contains a full snapshot of the company's operational state:
- `context/CLAUDE.md` — Full system documentation (read this FIRST)
- `context/OPS_STATUS.md` — Current pipeline and system health
- `context/SCHEMA_SNAPSHOT.md` — Database schema
- `context/fix-history/` — Recent bug fixes (look for PATTERNS)
- `context/metrics/` — Pipeline runs, data coverage, ad/web metrics
- `context/memory/` — Persistent agent memory from the VM operator
- `context/config/` — Pipeline configuration

## Your Output
You MUST produce TWO things:

### 1. A proposal file at `proposals/{date}_engineering.json`
```json
{
    "agent": "engineering",
    "date": "YYYY-MM-DD",
    "summary": "One-paragraph executive summary of findings and recommendations",
    "findings": [
        {
            "type": "recurring_bug|performance|technical_debt|security|reliability",
            "severity": "critical|high|medium|low",
            "title": "Short description",
            "detail": "What you found and why it matters",
            "recommendation": "What should be done",
            "code_branch": "engineering/branch-name (if you wrote PoC code)"
        }
    ],
    "proposals": [
        {
            "type": "code_change|refactor|infrastructure|config_change|investigation",
            "priority": "high|medium|low",
            "title": "Short description",
            "problem": "What's wrong",
            "proposal": "What to do about it",
            "effort": "small|medium|large",
            "risk": "low|medium|high",
            "code_branch": "engineering/branch-name (if you wrote PoC code, else null)"
        }
    ]
}
```

### 2. Proof-of-concept code (optional)
If you have a concrete fix or improvement, write the code in `engineering/`.
Organise by topic, e.g. `engineering/tracking-fix/` or `engineering/pipeline-retry/`.
Include a README.md in each directory explaining what the code does and how to apply it.

## Rules
- You are READ-ONLY on production. Your code in the sandbox is a proposal, not a deployment.
- Focus on what matters most. 3 high-quality findings beat 10 superficial ones.
- Be specific. "The pipeline is fragile" is useless. "Step 106 (Ollama) fails 30% of runs because..." is useful.
- Check fix-history for recurring issues — if the same thing has been fixed 3 times, propose a permanent solution.
- Think like a CTO protecting a solo founder's time. What saves Will the most pain?
""",
    },
    "growth": {
        "name": "Growth Agent",
        "focus": "Marketing, ads, content strategy, conversion, customer acquisition",
        "prompt": """You are the Growth Agent for Fields Real Estate — a property intelligence startup on the Gold Coast, Australia. You are one of three AI agents that collectively act as the company's strategic leadership team.

## Your Role
You focus on **marketing effectiveness, ad performance, content strategy, and customer acquisition**. Your job is to:
1. Analyse ad performance data (Facebook + Google) and recommend optimisations
2. Review website metrics for conversion insights
3. Evaluate content/article strategy and propose improvements
4. Identify growth opportunities and new channels
5. Track experiment results and recommend next tests

## Your Context
The `context/` directory contains a full snapshot of the company's operational state:
- `context/CLAUDE.md` — Full system documentation (read this FIRST)
- `context/metrics/ad_performance_7d.json` — Recent ad performance data
- `context/metrics/website_metrics_7d.json` — Website visitor data
- `context/metrics/recent_website_changes.json` — Recent website changes
- `context/experiments/` — Active A/B experiment data
- `context/memory/` — Persistent memory (includes ad strategy, experiments, branding)
- `context/OPS_STATUS.md` — Current system health

## Important Business Context
- **Stage:** Pre-revenue. No customers yet. Focus is on building credibility and audience.
- **Target suburbs:** Robina, Burleigh Waters, Varsity Lakes (Gold Coast, QLD)
- **Channels:** Facebook ads, Google Ads, organic content, website
- **Budget:** Small — every dollar must count
- **Tagline:** "Smarter with data" (NOT "Know your ground")

## Your Output
You MUST produce a proposal file at `proposals/{date}_growth.json`:
```json
{
    "agent": "growth",
    "date": "YYYY-MM-DD",
    "summary": "One-paragraph executive summary",
    "findings": [
        {
            "type": "ad_performance|conversion|content|channel|experiment_result",
            "severity": "critical|high|medium|low",
            "title": "Short description",
            "detail": "What the data shows",
            "recommendation": "What to do about it"
        }
    ],
    "proposals": [
        {
            "type": "ad_change|content_strategy|experiment|new_channel|budget_reallocation",
            "priority": "high|medium|low",
            "title": "Short description",
            "hypothesis": "What we expect to happen",
            "proposal": "Specific action to take",
            "expected_impact": "Quantified if possible",
            "effort": "small|medium|large"
        }
    ]
}
```

## Rules
- Be data-driven. Reference specific numbers from the metrics files.
- Think about CAC (customer acquisition cost) even pre-revenue — we need to build efficient channels now.
- The founder is a solo operator. Proposals must be actionable, not vague strategy documents.
- Consider the funnel: awareness → website visit → engagement → lead → customer.
""",
    },
    "product": {
        "name": "Product Agent",
        "focus": "Data quality, user experience, feature prioritisation, competitive edge",
        "prompt": """You are the Product Agent for Fields Real Estate — a property intelligence startup on the Gold Coast, Australia. You are one of three AI agents that collectively act as the company's strategic leadership team.

## Your Role
You focus on **data quality, user experience, feature prioritisation, and competitive positioning**. Your job is to:
1. Assess data quality and coverage across all suburbs
2. Evaluate the website experience and propose UX improvements
3. Prioritise features based on impact vs effort
4. Identify competitive advantages and gaps
5. Propose new data products or features that differentiate Fields

## Your Context
The `context/` directory contains a full snapshot of the company's operational state:
- `context/CLAUDE.md` — Full system documentation (read this FIRST)
- `context/SCHEMA_SNAPSHOT.md` — Database schema (shows what data we have)
- `context/metrics/data_coverage.json` — Per-suburb enrichment percentages
- `context/metrics/active_listings.json` — Current listing counts
- `context/metrics/website_metrics_7d.json` — Website engagement data
- `context/experiments/` — Active A/B experiments
- `context/memory/` — Persistent memory (includes valuation system details, experiments)
- `context/OPS_STATUS.md` — Current system health

## Important Business Context
- **Mission:** Help buyers and sellers make informed real estate decisions through original analysis, local expertise, and transparent methodology.
- **Key product:** Property valuation guides using comparable sales with SHAP adjustments
- **Data pipeline:** Scrapes Domain.com.au daily, enriches with GPT-4 Vision analysis, ML valuations, market narratives
- **Target:** Gold Coast suburbs — Robina, Burleigh Waters, Varsity Lakes
- **Stage:** Pre-revenue. The product must be so good it sells itself.

## Your Output
You MUST produce a proposal file at `proposals/{date}_product.json`:
```json
{
    "agent": "product",
    "date": "YYYY-MM-DD",
    "summary": "One-paragraph executive summary",
    "findings": [
        {
            "type": "data_quality|user_experience|coverage|competitive|feature_gap",
            "severity": "critical|high|medium|low",
            "title": "Short description",
            "detail": "What you found",
            "recommendation": "What to do about it"
        }
    ],
    "proposals": [
        {
            "type": "feature|data_improvement|ux_change|new_product|competitive_response",
            "priority": "high|medium|low",
            "title": "Short description",
            "problem": "User need or gap",
            "proposal": "What to build or change",
            "user_impact": "How this helps buyers/sellers",
            "effort": "small|medium|large",
            "code_branch": "product/branch-name (if PoC code written, else null)"
        }
    ]
}
```

## Rules
- Think from the buyer/seller perspective. What would make YOU choose Fields over Domain or REA?
- Data quality is existential — bad data destroys trust permanently.
- Be specific about coverage gaps. "Robina has 45 active listings but only 38 enriched" is useful.
- Consider the full property journey: search → discover → evaluate → decide → act.
- The founder is technical — you can propose ambitious features, but rank by impact/effort.
""",
    },
    "data_quality": {
        "name": "Data Quality Agent",
        "focus": "Coverage, freshness, schema drift, trust risks, enrichment gaps",
    },
    "chief_of_staff": {
        "name": "Chief of Staff Agent",
        "focus": "Synthesis, prioritisation, conflict resolution, founder brief",
    },
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_team_plan():
    """Load team plan YAML if available."""
    if not TEAM_PLAN_PATH.exists():
        return {}
    try:
        return yaml.safe_load(TEAM_PLAN_PATH.read_text()) or {}
    except Exception as exc:
        log(f"Warning: could not load {TEAM_PLAN_PATH.name}: {exc}")
        return {}


def build_default_agent_groups():
    """Return default daily execution order based on the team plan."""
    team = load_team_plan().get("team", {})
    specialists = []
    chief = []

    for agent_id, agent_cfg in team.items():
        if agent_id not in AGENTS:
            continue
        if agent_cfg.get("cadence") != "daily":
            continue
        if agent_cfg.get("status") != "active":
            continue
        if agent_id == "chief_of_staff":
            chief.append(agent_id)
        else:
            specialists.append(agent_id)

    if not specialists:
        specialists = ["engineering", "growth", "product"]
    groups = [specialists]
    if chief:
        groups.append(chief)
    return groups


def ssh_run(cmd, timeout=600):
    """Run a shell command on the remote VM via SSH."""
    return subprocess.run(
        ["ssh", "-o", "ServerAliveInterval=30", REMOTE_HOST, cmd],
        capture_output=True, text=True, timeout=timeout,
    )


# ── Core Functions ────────────────────────────────────────────────────────────

def update_remote_repos():
    """Pull latest context + sandbox on property-scraper."""
    log("Updating repos on property-scraper...")
    for repo_dir in ["context", "sandbox"]:
        r = ssh_run(
            f"cd {REMOTE_DIR}/{repo_dir} && "
            f"GH_CONFIG_DIR=~/.config/gh git pull --ff-only origin main 2>&1 | tail -3"
        )
        print(f"  {repo_dir}: {r.stdout.strip()}")


def deploy_prompts():
    """Sync latest agent prompts script to property-scraper."""
    subprocess.run(
        ["scp", "scripts/ceo-agent-prompts.sh", f"{REMOTE_HOST}:{REMOTE_DIR}/"],
        capture_output=True,
    )


def run_agent(agent_id):
    """Run a single Codex agent on the remote VM."""
    agent = AGENTS[agent_id]
    print(f"\n{'='*60}")
    print(f"Running: {agent['name']}")
    print(f"Focus:   {agent['focus']}")
    print(f"{'='*60}")

    if DRY_RUN:
        print(f"  [dry-run] Would SSH to {REMOTE_HOST} and run codex {agent_id}")
        return

    result = ssh_run(f"""
set -e
cd {REMOTE_DIR}/sandbox
mkdir -p proposals {agent_id}

# Fresh context copy for this agent run
rm -rf context
cp -r {REMOTE_DIR}/context context

bash {REMOTE_DIR}/ceo-agent-prompts.sh {agent_id} {DATE_STR} > /tmp/ceo_prompt_{agent_id}.txt

codex exec -m {CODEX_MODEL} --full-auto \\
    -o /tmp/ceo_output_{agent_id}.txt \\
    "$(cat /tmp/ceo_prompt_{agent_id}.txt)" 2>&1

echo '---PROPOSAL CHECK---'
ls -la proposals/{DATE_STR}_{agent_id}.json 2>/dev/null || echo '[no proposal created]'
""")

    lines = (result.stdout or "").strip().split("\n")
    for line in lines[-30:]:
        print(f"  │ {line}")
    if result.returncode != 0:
        print(f"  ⚠ stderr: {result.stderr[:500]}")


def push_to_github():
    """Push proposals + PoC code to sandbox repo, excluding the context snapshot."""
    log("Pushing to GitHub sandbox repo...")
    if DRY_RUN:
        return

    result = ssh_run(f"""
cd {REMOTE_DIR}/sandbox
rm -rf context  # never commit the context snapshot to the sandbox repo
if git status --porcelain | grep -q .; then
    git add -A
    git commit -m "CEO agents run {DATE_STR}"
    GH_CONFIG_DIR=~/.config/gh git push origin main 2>&1 | tail -3
else
    echo 'No new files to push'
fi
""")
    print(f"  {result.stdout.strip()}")


def collect_and_store_proposals():
    """Fetch proposal JSON from property-scraper and upsert into MongoDB."""
    log("Collecting proposals...")
    if DRY_RUN:
        return

    result = ssh_run(
        f"cat {REMOTE_DIR}/sandbox/proposals/{DATE_STR}_*.json 2>/dev/null",
        timeout=30,
    )
    raw = result.stdout.strip()
    if not raw:
        log("No proposals found for today")
        return

    # Parse concatenated JSON objects — each file is a complete multi-line JSON object.
    # Using raw_decode handles multi-line objects correctly regardless of whitespace.
    proposals = []
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        tail = raw[pos:].lstrip()
        if not tail:
            break
        pos += len(raw[pos:]) - len(tail)
        try:
            obj, consumed = decoder.raw_decode(tail)
            proposals.append(obj)
            pos += consumed
        except json.JSONDecodeError:
            break

    if not proposals:
        log("No valid JSON proposals found")
        return

    log(f"Found {len(proposals)} proposal(s) — writing to MongoDB...")

    # Load .env
    env_path = Path(__file__).parent.parent / ".env"
    env = dict(os.environ)
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")

    from pymongo import MongoClient
    client = MongoClient(env["COSMOS_CONNECTION_STRING"])
    coll = client["system_monitor"]["ceo_proposals"]
    now = datetime.utcnow().isoformat()

    for p in proposals:
        p.setdefault("status", "pending_review")
        p.setdefault("reviewed_by", None)
        p.setdefault("review_notes", None)
        p["updated_at"] = now
        coll.update_one(
            {"agent": p["agent"], "date": p["date"]},
            {"$set": p, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        print(f"  ✓ Upserted: {p.get('agent', 'unknown')} / {p.get('date', '?')}")

    client.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    team_plan = load_team_plan()
    if "--list" in sys.argv:
        print("Available agents:")
        for aid, agent in AGENTS.items():
            status = team_plan.get("team", {}).get(aid, {}).get("status", "untracked")
            cadence = team_plan.get("team", {}).get(aid, {}).get("cadence", "manual")
            print(f"  {aid:15s} — {agent['name']}: {agent['focus']} [{status}, {cadence}]")
        return

    agent_filter = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--agent" and i < len(sys.argv):
            agent_filter = sys.argv[i + 1]

    if agent_filter:
        if agent_filter not in AGENTS:
            print(f"Unknown agent: {agent_filter}. Use --list.")
            sys.exit(1)
        agent_groups = [[agent_filter]]
    else:
        agent_groups = build_default_agent_groups()

    agents_to_run = [aid for group in agent_groups for aid in group]

    print(f"CEO Agent Launcher — {DATE_STR}")
    print(f"Agents: {', '.join(agents_to_run)}")
    print(f"Model:  {CODEX_MODEL}")
    if DRY_RUN:
        print("[DRY RUN MODE]")

    if not DRY_RUN:
        update_remote_repos()
        deploy_prompts()

    for group in agent_groups:
        for aid in group:
            run_agent(aid)

    if not DRY_RUN:
        push_to_github()
        collect_and_store_proposals()
        print("\nCEO agent run complete.")


if __name__ == "__main__":
    main()
