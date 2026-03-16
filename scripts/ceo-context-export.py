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


# ── Helpers ─────────────────────────────────────────────────────────────────

def gh_api_put(repo_path, local_content, message):
    """Push content to GitHub repo via gh api. Returns commit SHA or None."""
    if DRY_RUN:
        print(f"  [dry-run] Would push: {repo_path} ({len(local_content)} bytes)")
        return "dry-run"

    content_b64 = base64.b64encode(local_content.encode("utf-8")).decode("utf-8")

    # Check if file exists (get SHA for update)
    sha = None
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/contents/{repo_path}", "--jq", ".sha"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            sha = result.stdout.strip()
    except Exception:
        pass

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


def export_metrics():
    """Export key metrics from MongoDB."""
    print("\n📈 Exporting metrics...")

    # --- Active listing counts ---
    listing_counts = query_mongodb("""
db = client['Gold_Coast']
collections = [c for c in db.list_collection_names() if not c.startswith('system') and c not in ('suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots')]
result = {}
for coll in sorted(collections):
    count = db[coll].count_documents({'listing_status': 'for_sale'})
    if count > 0:
        result[coll] = count
print(json.dumps(result, indent=2))
""")
    gh_api_put("metrics/active_listings.json", listing_counts, "update: active listing counts")

    # --- Recent pipeline runs ---
    pipeline_runs = query_mongodb("""
db = client['system_monitor']
runs = list(db['orchestrator_runs'].find({}, {'_id': 0}).sort('started_at', -1).limit(7))
for r in runs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
print(json.dumps(runs, indent=2, default=str))
""")
    gh_api_put("metrics/recent_pipeline_runs.json", pipeline_runs, "update: recent pipeline runs")

    # --- Ad performance summary (last 7 days) ---
    ad_metrics = query_mongodb("""
from datetime import datetime, timedelta
db = client['system_monitor']
cutoff = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')

# Facebook
fb = list(db['ad_daily_metrics'].find({'date': {'$gte': cutoff}}, {'_id': 0}).sort('date', -1).limit(50))
for r in fb:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()

# Google
goog = list(db['google_ads_daily_metrics'].find({'date': {'$gte': cutoff}}, {'_id': 0}).sort('date', -1).limit(50))
for r in goog:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()

print(json.dumps({'facebook': fb, 'google': goog}, indent=2, default=str))
""")
    gh_api_put("metrics/ad_performance_7d.json", ad_metrics, "update: ad performance (7d)")

    # --- Website metrics (last 7 days) ---
    web_metrics = query_mongodb("""
from datetime import datetime, timedelta
db = client['system_monitor']
cutoff = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
docs = list(db['website_daily_metrics'].find({'date': {'$gte': cutoff}}, {'_id': 0}).sort('date', -1))
for r in docs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
print(json.dumps(docs, indent=2, default=str))
""")
    gh_api_put("metrics/website_metrics_7d.json", web_metrics, "update: website metrics (7d)")

    # --- Data coverage / enrichment status ---
    coverage = query_mongodb("""
db = client['Gold_Coast']
collections = [c for c in db.list_collection_names() if not c.startswith('system') and c not in ('suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots')]
result = {}
for coll in sorted(collections):
    total = db[coll].count_documents({'listing_status': 'for_sale'})
    if total == 0:
        continue
    enriched = db[coll].count_documents({'listing_status': 'for_sale', 'valuation_data': {'$exists': True}})
    result[coll] = {'active': total, 'enriched': enriched, 'pct': round(enriched/total*100, 1) if total else 0}
print(json.dumps(result, indent=2))
""")
    gh_api_put("metrics/data_coverage.json", coverage, "update: data coverage stats")

    # --- CEO proposals (for agent awareness of prior proposals) ---
    proposals = query_mongodb("""
db = client['system_monitor']
docs = list(db['ceo_proposals'].find({}, {'_id': 0}).sort('date', -1).limit(20))
for r in docs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
print(json.dumps(docs, indent=2, default=str))
""")
    gh_api_put("metrics/recent_proposals.json", proposals, "update: recent CEO proposals")


def export_experiments():
    """Export active experiment status."""
    print("\n🧪 Exporting experiment data...")
    experiments = query_mongodb("""
db = client['system_monitor']
docs = list(db['website_experiments'].find({}, {'_id': 0}))
for r in docs:
    for k, v in r.items():
        if hasattr(v, 'isoformat'):
            r[k] = v.isoformat()
print(json.dumps(docs, indent=2, default=str))
""")
    gh_api_put("experiments/active_experiments.json", experiments, "update: active experiments")


def export_recent_changes():
    """Export recent website changes and deploy events."""
    print("\n🚀 Exporting recent changes...")
    changes = query_mongodb("""
from datetime import datetime, timedelta
db = client['system_monitor']
cutoff = (datetime.utcnow() - timedelta(days=14)).isoformat()

deploys = list(db['website_deploy_events'].find({'timestamp': {'$gte': cutoff}}, {'_id': 0}).sort('timestamp', -1).limit(20))
changes = list(db['website_change_log'].find({}, {'_id': 0}).sort('created_at', -1).limit(20))

for doc in deploys + changes:
    for k, v in doc.items():
        if hasattr(v, 'isoformat'):
            doc[k] = v.isoformat()

print(json.dumps({'deploys': deploys, 'changes': changes}, indent=2, default=str))
""")
    gh_api_put("metrics/recent_website_changes.json", changes, "update: recent website changes")


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

    export_claude_md()
    export_memory()
    export_ops_status()
    export_schema()
    export_fix_history()
    export_pipeline_config()
    export_metrics()
    export_experiments()
    export_recent_changes()
    export_git_activity()
    export_timestamp()

    print("\n✅ Context export complete.")


if __name__ == "__main__":
    main()
