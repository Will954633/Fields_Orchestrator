#!/usr/bin/env python3
"""
CEO Context Export — Daily data bundle for CEO agent system.

Exports a read-only snapshot of all company data to the fields-ceo-context GitHub repo.
Codex agents clone this repo at task start for full context.

Usage:
    python3 scripts/ceo-context-export.py           # full export
    python3 scripts/ceo-context-export.py --dry-run  # show what would be exported
"""

import os
import sys
import json
import yaml
import base64
import subprocess
import glob
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

REPO = "Will954633/fields-ceo-context"
ORCHESTRATOR_DIR = "/home/fields/Fields_Orchestrator"
MEMORY_DIR = "/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory"
WEBSITE_DIR = "/home/fields/Feilds_Website/01_Website"

DRY_RUN = "--dry-run" in sys.argv

# SHA cache: populated once per run to avoid a separate GET call per file
_SHA_CACHE: dict = {}


def load_sha_cache() -> None:
    """Fetch all file SHAs from the repo in one API call (git tree)."""
    global _SHA_CACHE
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/git/trees/main?recursive=1",
         "--jq", '.tree[] | select(.type == "blob") | "\(.path)\t\(.sha)"'],
        capture_output=True, text=True, timeout=60,
    )
    _SHA_CACHE = {}
    for line in result.stdout.splitlines():
        if "\t" in line:
            path, sha = line.split("\t", 1)
            _SHA_CACHE[path] = sha.strip()
    print(f"  Loaded {len(_SHA_CACHE)} file SHAs from repo")


# ── Helpers ─────────────────────────────────────────────────────────────────

def gh_api_put(repo_path, local_content, message):
    """Push content to GitHub repo via gh api. Returns commit SHA or None."""
    if DRY_RUN:
        print(f"  [dry-run] Would push: {repo_path} ({len(local_content)} bytes)")
        return "dry-run"

    content_b64 = base64.b64encode(local_content.encode("utf-8")).decode("utf-8")

    # Use cached SHA — avoids a per-file GET call (saved by load_sha_cache at run start)
    sha = _SHA_CACHE.get(repo_path)

    # For large files, use --input with a temp JSON file to avoid arg list too long
    import tempfile as _tempfile
    payload = {"message": message, "content": content_b64}
    if sha:
        payload["sha"] = sha

    try:
        with _tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name

        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/contents/{repo_path}",
             "--method", "PUT", "--input", tmp_path, "--jq", ".commit.sha"],
            capture_output=True, text=True, timeout=120
        )
        os.unlink(tmp_path)

        if result.returncode == 0:
            commit = result.stdout.strip()
            print(f"  ✓ {repo_path} → {commit[:8]}")
            return commit
        else:
            print(f"  ✗ {repo_path}: {result.stderr.strip()[:200]}")
            return None
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        print(f"  ✗ {repo_path}: {e}")
        return None


def read_file(path, max_bytes=500_000):
    """Read a file, truncating if too large."""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        if len(content) > max_bytes:
            content = content[:max_bytes] + f"\n\n... [TRUNCATED at {max_bytes} bytes] ..."
        return content
    except Exception as e:
        return f"[Error reading {path}: {e}]"


def query_mongodb(script):
    """Run a Python snippet against MongoDB, return output."""
    full_script = f"""
import sys, json, os
sys.path.insert(0, '/home/fields/Fields_Orchestrator')
os.chdir('/home/fields/Fields_Orchestrator')

# Load env
from dotenv import load_dotenv
load_dotenv('/home/fields/Fields_Orchestrator/.env')

from pymongo import MongoClient
uri = os.environ.get('COSMOS_CONNECTION_STRING', '')
client = MongoClient(uri)

{script}

client.close()
"""
    try:
        result = subprocess.run(
            ["/home/fields/venv/bin/python3", "-c", full_script],
            capture_output=True, text=True, timeout=120,
            cwd=ORCHESTRATOR_DIR
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[MongoDB query error: {e}]"


# ── Export Functions ────────────────────────────────────────────────────────

def export_memory():
    """Export all memory files."""
    print("\n📝 Exporting memory files...")
    for f in sorted(Path(MEMORY_DIR).glob("*")):
        content = read_file(f)
        gh_api_put(f"memory/{f.name}", content, f"update: memory/{f.name}")


def export_ops_status():
    """Export current OPS_STATUS.md."""
    print("\n📊 Exporting OPS_STATUS.md...")
    # Refresh it first
    subprocess.run(
        ["/home/fields/venv/bin/python3", f"{ORCHESTRATOR_DIR}/scripts/refresh-ops-context.py"],
        capture_output=True, timeout=120, cwd=ORCHESTRATOR_DIR
    )
    content = read_file(f"{ORCHESTRATOR_DIR}/OPS_STATUS.md")
    gh_api_put("OPS_STATUS.md", content, "update: ops status snapshot")


def export_schema():
    """Export database schema snapshot."""
    print("\n🗄️ Exporting SCHEMA_SNAPSHOT.md...")
    content = read_file(f"{ORCHESTRATOR_DIR}/SCHEMA_SNAPSHOT.md")
    gh_api_put("SCHEMA_SNAPSHOT.md", content, "update: schema snapshot")


def export_fix_history():
    """Export last 14 days of fix history."""
    print("\n🔧 Exporting fix history...")
    fix_dir = Path(f"{ORCHESTRATOR_DIR}/logs/fix-history")
    if not fix_dir.exists():
        print("  [no fix history directory]")
        return

    cutoff = datetime.now() - timedelta(days=14)
    for f in sorted(fix_dir.glob("*.md")):
        if f.name == "README.md":
            continue
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d")
            if file_date >= cutoff:
                content = read_file(f)
                gh_api_put(f"fix-history/{f.name}", content, f"update: fix history {f.name}")
        except ValueError:
            continue


def export_pipeline_config():
    """Export sanitised pipeline config (no credentials)."""
    print("\n⚙️ Exporting pipeline config...")

    # process_commands.yaml (no secrets)
    content = read_file(f"{ORCHESTRATOR_DIR}/config/process_commands.yaml")
    gh_api_put("config/process_commands.yaml", content, "update: pipeline process commands")

    # settings.yaml — strip MongoDB URI
    try:
        with open(f"{ORCHESTRATOR_DIR}/config/settings.yaml") as f:
            settings = yaml.safe_load(f)
        if "mongodb" in settings and "uri" in settings["mongodb"]:
            settings["mongodb"]["uri"] = "[REDACTED]"
        content = yaml.dump(settings, default_flow_style=False)
        gh_api_put("config/settings.yaml", content, "update: pipeline settings (sanitised)")
    except Exception as e:
        print(f"  ✗ settings.yaml: {e}")

    # codex team operating model
    try:
        content = read_file(f"{ORCHESTRATOR_DIR}/config/codex_team_plan.yaml")
        gh_api_put("config/codex_team_plan.yaml", content, "update: codex team plan")
    except Exception as e:
        print(f"  ✗ codex_team_plan.yaml: {e}")


def export_metrics():
    """Export all metrics, experiments, and recent changes — one MongoDB connection."""
    print("\n📈 Exporting metrics, experiments, and recent changes...")

    raw = query_mongodb("""
from datetime import datetime, timedelta

all_results = {}
skip_colls = {'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots'}

# --- Active listing counts ---
db_gc = client['Gold_Coast']
suburb_colls = sorted(
    c for c in db_gc.list_collection_names()
    if not c.startswith('system') and c not in skip_colls
)
listing_counts = {}
for coll in suburb_colls:
    count = db_gc[coll].count_documents({'listing_status': 'for_sale'})
    if count > 0:
        listing_counts[coll] = count
all_results['active_listings'] = json.dumps(listing_counts, indent=2)

# --- Recent pipeline runs ---
db_sm = client['system_monitor']
runs = list(db_sm['orchestrator_runs'].find({}, {'_id': 0}).sort('started_at', -1).limit(7))
for r in runs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
all_results['pipeline_runs'] = json.dumps(runs, indent=2, default=str)

# --- Ad performance (last 7 days) ---
cutoff_7d = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
fb = list(db_sm['ad_daily_metrics'].find({'date': {'$gte': cutoff_7d}}, {'_id': 0}).sort('date', -1).limit(50))
goog = list(db_sm['google_ads_daily_metrics'].find({'date': {'$gte': cutoff_7d}}, {'_id': 0}).sort('date', -1).limit(50))
for row in fb + goog:
    for k, v in row.items():
        if hasattr(v, 'isoformat'):
            row[k] = v.isoformat()
all_results['ad_performance_7d'] = json.dumps({'facebook': fb, 'google': goog}, indent=2, default=str)

# --- Website metrics (last 7 days) ---
web_docs = list(db_sm['website_daily_metrics'].find({'date': {'$gte': cutoff_7d}}, {'_id': 0}).sort('date', -1))
for r in web_docs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
all_results['website_metrics_7d'] = json.dumps(web_docs, indent=2, default=str)

# --- Data coverage ---
coverage = {}
for coll in suburb_colls:
    total = db_gc[coll].count_documents({'listing_status': 'for_sale'})
    if total == 0:
        continue
    enriched = db_gc[coll].count_documents({'listing_status': 'for_sale', 'valuation_data': {'$exists': True}})
    coverage[coll] = {'active': total, 'enriched': enriched, 'pct': round(enriched / total * 100, 1) if total else 0}
all_results['data_coverage'] = json.dumps(coverage, indent=2)

# --- Recent CEO proposals ---
proposal_docs = list(db_sm['ceo_proposals'].find({}, {'_id': 0}).sort('date', -1).limit(20))
for r in proposal_docs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
all_results['recent_proposals'] = json.dumps(proposal_docs, indent=2, default=str)

# --- Active experiments ---
exp_docs = list(db_sm['website_experiments'].find({}, {'_id': 0}))
for r in exp_docs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
all_results['experiments'] = json.dumps(exp_docs, indent=2, default=str)

# --- Recent website changes + deploys ---
cutoff_14d = (datetime.utcnow() - timedelta(days=14)).isoformat()
deploys = list(db_sm['website_deploy_events'].find({'timestamp': {'$gte': cutoff_14d}}, {'_id': 0}).sort('timestamp', -1).limit(20))
changes = list(db_sm['website_change_log'].find({}, {'_id': 0}).sort('created_at', -1).limit(20))
for doc in deploys + changes:
    for k, v in doc.items():
        if hasattr(v, 'isoformat'):
            doc[k] = v.isoformat()
all_results['recent_website_changes'] = json.dumps({'deploys': deploys, 'changes': changes}, indent=2, default=str)

print(json.dumps(all_results))
""")

    try:
        results = json.loads(raw)
    except Exception as e:
        print(f"  ✗ Failed to parse metric results: {e}\n  Raw: {raw[:300]}")
        return

    file_map = {
        "metrics/active_listings.json":         ("active_listings",        "update: active listing counts"),
        "metrics/recent_pipeline_runs.json":     ("pipeline_runs",          "update: recent pipeline runs"),
        "metrics/ad_performance_7d.json":        ("ad_performance_7d",      "update: ad performance (7d)"),
        "metrics/website_metrics_7d.json":       ("website_metrics_7d",     "update: website metrics (7d)"),
        "metrics/data_coverage.json":            ("data_coverage",          "update: data coverage stats"),
        "metrics/recent_proposals.json":         ("recent_proposals",       "update: recent CEO proposals"),
        "experiments/active_experiments.json":   ("experiments",            "update: active experiments"),
        "metrics/recent_website_changes.json":   ("recent_website_changes", "update: recent website changes"),
    }
    for repo_path, (key, msg) in file_map.items():
        gh_api_put(repo_path, results.get(key, "{}"), msg)


def export_git_activity():
    """Export recent git log from all repos."""
    print("\n📋 Exporting git activity...")

    repos = {
        "Fields_Orchestrator": "/home/fields/Fields_Orchestrator",
    }
    activity = {}
    for name, path in repos.items():
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--since=14 days ago", "-n", "30"],
                capture_output=True, text=True, timeout=10, cwd=path
            )
            activity[name] = result.stdout.strip()
        except Exception:
            activity[name] = "[error]"

    # Get website repo activity from GitHub
    try:
        result = subprocess.run(
            ["gh", "api", "repos/Will954633/Website_Version_Feb_2026/commits",
             "--jq", '.[:20] | .[] | .sha[:7] + " " + (.commit.message | split("\\n")[0])'],
            capture_output=True, text=True, timeout=30
        )
        activity["Website"] = result.stdout.strip()
    except Exception:
        activity["Website"] = "[error]"

    content = "\n".join(f"## {name}\n```\n{log}\n```\n" for name, log in activity.items())
    gh_api_put("metrics/git_activity.md", f"# Git Activity (last 14 days)\n\n{content}", "update: git activity")


def export_claude_md():
    """Export CLAUDE.md for agent reference."""
    print("\n📖 Exporting CLAUDE.md...")
    content = read_file(f"{ORCHESTRATOR_DIR}/CLAUDE.md")
    gh_api_put("CLAUDE.md", content, "update: CLAUDE.md reference")


def export_timestamp():
    """Write export timestamp."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S AEST")
    gh_api_put("LAST_EXPORT.txt", f"Last exported: {now}\n", "update: export timestamp")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}CEO Context Export — {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    print(f"Target repo: {REPO}")

    load_sha_cache()
    export_claude_md()
    export_memory()
    export_ops_status()
    export_schema()
    export_fix_history()
    export_pipeline_config()
    export_metrics()  # includes experiments + recent changes
    export_git_activity()
    export_timestamp()

    print("\n✅ Context export complete.")


if __name__ == "__main__":
    main()
