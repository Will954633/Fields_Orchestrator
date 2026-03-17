#!/usr/bin/env python3
"""
CEO Context Export — Daily data bundle for CEO agent system.

Exports a read-only snapshot of company state to the fields-ceo-context repo.
The export now fails closed when critical telemetry is missing or empty.
"""

from __future__ import annotations

import base64
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from ceo_agent_lib import dumps_json, load_env_file, load_founder_truths, to_jsonable


REPO = "Will954633/fields-ceo-context"
ORCHESTRATOR_DIR = Path("/home/fields/Fields_Orchestrator")
MEMORY_DIR = Path("/home/projects/.claude/projects/-home-fields-Fields-Orchestrator/memory")
WEBSITE_DIR = Path("/home/fields/Feilds_Website/01_Website")
DRY_RUN = "--dry-run" in sys.argv

SHA_CACHE: dict[str, str] = {}
EXPORT_RECORDS: list[dict[str, Any]] = []
EXPORT_ERRORS: list[str] = []

REQUIRED_JSON_EXPORTS = {
    "metrics/ad_performance_7d.json": "Ad telemetry is required for growth analysis.",
    "metrics/website_metrics_7d.json": "Website telemetry is required for experiment and funnel analysis.",
    "metrics/data_coverage.json": "Coverage telemetry is required for product and data-trust analysis.",
    "metrics/active_listings.json": "Listing counts are required for product and growth context.",
    "metrics/recent_pipeline_runs.json": "Pipeline run history is required for engineering analysis.",
}

REQUIRED_EXPORT_VALIDATORS = {
    "metrics/ad_performance_7d.json": lambda payload: bool(payload.get("facebook") or payload.get("google")),
    "metrics/website_metrics_7d.json": lambda payload: bool(payload.get("rows")),
    "metrics/data_coverage.json": lambda payload: bool(payload),
    "metrics/active_listings.json": lambda payload: bool(payload.get("counts")),
    "metrics/recent_pipeline_runs.json": lambda payload: bool(payload.get("runs")),
}

CODE_TARGETS = [
    ORCHESTRATOR_DIR / "scripts" / "refresh-ops-context.py",
    ORCHESTRATOR_DIR / "scripts" / "api-health-check.py",
    WEBSITE_DIR / "netlify" / "functions" / "recently-sold.mjs",
    WEBSITE_DIR / "src" / "services" / "recentlySoldService.ts",
]

READ_ONLY_TOOL_CONTRACT = {
    "name": "ceo-query-broker",
    "mode": "read_only",
    "purpose": "Approved live queries for ops, timelines, proposal outcomes, and founder truths.",
    "commands": [
        "founder-truths",
        "ops-summary",
        "collection-counts",
        "pipeline-runs --days N --limit N",
        "website-metrics --days N",
        "ad-metrics --days N --limit N",
        "proposal-outcomes --days N --limit N",
        "timeline --days N",
    ],
    "guardrails": [
        "No writes to MongoDB.",
        "No shell execution outside the approved broker commands.",
        "Results should be cited back to exported evidence files where possible.",
    ],
}


def now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S AEST")


def record_export(repo_path: str, content: str | None, *, required: bool = False, reason: str | None = None, error: str | None = None) -> None:
    record = {
        "path": repo_path,
        "required": required,
        "reason": reason,
        "bytes": len(content.encode("utf-8")) if content is not None else 0,
        "status": "ok" if error is None else "error",
        "error": error,
    }
    EXPORT_RECORDS.append(record)
    if error:
        EXPORT_ERRORS.append(f"{repo_path}: {error}")


def gh_api_put(repo_path: str, local_content: str, message: str, *, required: bool = False, reason: str | None = None) -> str | None:
    if DRY_RUN:
        print(f"  [dry-run] Would push: {repo_path} ({len(local_content)} bytes)")
        record_export(repo_path, local_content, required=required, reason=reason)
        return "dry-run"

    content_b64 = base64.b64encode(local_content.encode("utf-8")).decode("utf-8")
    sha = SHA_CACHE.get(repo_path)

    import tempfile

    payload = {"message": message, "content": content_b64}
    if sha:
        payload["sha"] = sha

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name

        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/contents/{repo_path}", "--method", "PUT", "--input", tmp_path, "--jq", ".commit.sha"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        os.unlink(tmp_path)
        tmp_path = None

        if result.returncode == 0:
            commit = result.stdout.strip()
            SHA_CACHE[repo_path] = commit
            print(f"  ✓ {repo_path} → {commit[:8]}")
            record_export(repo_path, local_content, required=required, reason=reason)
            return commit

        error = result.stderr.strip()[:300]
        print(f"  ✗ {repo_path}: {error}")
        record_export(repo_path, local_content, required=required, reason=reason, error=error)
        return None
    except Exception as exc:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        error = str(exc)
        print(f"  ✗ {repo_path}: {error}")
        record_export(repo_path, local_content, required=required, reason=reason, error=error)
        return None


def load_sha_cache() -> None:
    if DRY_RUN:
        print("  [dry-run] Skipping SHA cache fetch")
        return
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/git/trees/main?recursive=1", "--jq", '.tree[] | select(.type == "blob") | "\(.path)\t\(.sha)"'],
        capture_output=True,
        text=True,
        timeout=60,
    )
    SHA_CACHE.clear()
    for line in result.stdout.splitlines():
        if "\t" in line:
            path, sha = line.split("\t", 1)
            SHA_CACHE[path] = sha.strip()
    print(f"  Loaded {len(SHA_CACHE)} file SHAs from repo")


def read_file(path: Path, max_bytes: int = 500_000) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_bytes:
            content = content[:max_bytes] + f"\n\n... [TRUNCATED at {max_bytes} bytes] ..."
        return content
    except Exception as exc:
        return f"[Error reading {path}: {exc}]"


def run_command(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None, timeout=timeout)


def query_json(command: list[str], *, timeout: int = 120) -> Any:
    result = run_command(command, cwd=ORCHESTRATOR_DIR, timeout=timeout)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or f"command failed: {' '.join(command)}")
    raw = (result.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"command returned empty output: {' '.join(command)}")
    return json.loads(raw)


def is_empty_payload(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0 or all(is_empty_payload(v) for v in value.values())
    return False


def is_valid_required_export(repo_path: str, payload: Any) -> bool:
    validator = REQUIRED_EXPORT_VALIDATORS.get(repo_path)
    if validator is not None:
        try:
            return bool(validator(payload))
        except Exception:
            return False
    return not is_empty_payload(payload)


def export_text_file(local_path: Path, repo_path: str, message: str) -> None:
    gh_api_put(repo_path, read_file(local_path), message)


def export_memory() -> None:
    print("\n📝 Exporting memory files...")
    for path in sorted(MEMORY_DIR.glob("*")):
        gh_api_put(f"memory/{path.name}", read_file(path), f"update: memory/{path.name}")


def export_founder_truths() -> None:
    print("\n🧭 Exporting founder truths...")
    truths = load_founder_truths()
    gh_api_put("memory/founder_truths.json", dumps_json(truths), "update: founder truths")


def export_ops_status() -> None:
    print("\n📊 Exporting OPS_STATUS.md...")
    run_command(["/home/fields/venv/bin/python3", str(ORCHESTRATOR_DIR / "scripts" / "refresh-ops-context.py")], cwd=ORCHESTRATOR_DIR, timeout=120)
    gh_api_put("OPS_STATUS.md", read_file(ORCHESTRATOR_DIR / "OPS_STATUS.md"), "update: ops status snapshot")


def export_schema() -> None:
    print("\n🗄️ Exporting SCHEMA_SNAPSHOT.md...")
    gh_api_put("SCHEMA_SNAPSHOT.md", read_file(ORCHESTRATOR_DIR / "SCHEMA_SNAPSHOT.md"), "update: schema snapshot")


def export_fix_history() -> None:
    print("\n🔧 Exporting fix history...")
    fix_dir = ORCHESTRATOR_DIR / "logs" / "fix-history"
    if not fix_dir.exists():
        print("  [no fix history directory]")
        return
    cutoff = datetime.now() - timedelta(days=14)
    for path in sorted(fix_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        try:
            if datetime.strptime(path.stem, "%Y-%m-%d") >= cutoff:
                gh_api_put(f"fix-history/{path.name}", read_file(path), f"update: fix history {path.name}")
        except ValueError:
            continue


def export_pipeline_config() -> None:
    print("\n⚙️ Exporting pipeline config...")
    gh_api_put("config/process_commands.yaml", read_file(ORCHESTRATOR_DIR / "config" / "process_commands.yaml"), "update: pipeline process commands")
    settings = yaml.safe_load((ORCHESTRATOR_DIR / "config" / "settings.yaml").read_text(encoding="utf-8"))
    if "mongodb" in settings and "uri" in settings["mongodb"]:
        settings["mongodb"]["uri"] = "[REDACTED]"
    gh_api_put("config/settings.yaml", yaml.dump(settings, default_flow_style=False), "update: pipeline settings (sanitised)")
    gh_api_put("config/codex_team_plan.yaml", read_file(ORCHESTRATOR_DIR / "config" / "codex_team_plan.yaml"), "update: codex team plan")
    gh_api_put("config/ceo_founder_truths.yaml", read_file(ORCHESTRATOR_DIR / "config" / "ceo_founder_truths.yaml"), "update: founder truths config")


def export_metrics_and_memory() -> None:
    print("\n📈 Exporting metrics, timelines, and structured memory...")
    metrics = {
        "metrics/active_listings.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "active-listings"]),
        "metrics/recent_pipeline_runs.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "pipeline-runs", "--days", "7", "--limit", "20"]),
        "metrics/ad_performance_7d.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "ad-metrics", "--days", "7", "--limit", "50"]),
        "metrics/website_metrics_7d.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "website-metrics", "--days", "7"]),
        "metrics/data_coverage.json": query_json(["/home/fields/venv/bin/python3", "-c", _coverage_query_script()]),
        "metrics/ops_summary.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "ops-summary"]),
        "metrics/timeline_14d.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "timeline", "--days", "14"]),
        "memory/proposal_outcomes.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "proposal-outcomes", "--days", "30", "--limit", "100"]),
        "tools/read_only_query_contract.json": READ_ONLY_TOOL_CONTRACT,
    }
    structured = query_json(["/home/fields/venv/bin/python3", "-c", _structured_memory_script()])
    metrics["memory/structured_memory.json"] = structured
    metrics["experiments/active_experiments.json"] = structured.get("active_experiments", [])
    metrics["metrics/recent_website_changes.json"] = structured.get("recent_website_changes", {})
    metrics["metrics/recent_proposals.json"] = structured.get("recent_proposals", [])

    for repo_path, payload in metrics.items():
        reason = REQUIRED_JSON_EXPORTS.get(repo_path)
        required = repo_path in REQUIRED_JSON_EXPORTS
        serialized = dumps_json(payload)
        if required and not is_valid_required_export(repo_path, payload):
            error = f"required export is empty: {reason}"
            print(f"  ✗ {repo_path}: {error}")
            record_export(repo_path, serialized, required=True, reason=reason, error=error)
            continue
        gh_api_put(repo_path, serialized, f"update: {Path(repo_path).name}", required=required, reason=reason)


def _coverage_query_script() -> str:
    return """
import json
import os
import sys
sys.path.insert(0, '/home/fields/Fields_Orchestrator/scripts')
from ceo_agent_lib import get_client, to_jsonable

client = get_client()
db_gc = client['Gold_Coast']
skip = {'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots'}
coverage = {}
for coll in sorted(db_gc.list_collection_names()):
    if coll.startswith('system') or coll in skip:
        continue
    total = db_gc[coll].count_documents({'listing_status': 'for_sale'})
    if total == 0:
        continue
    enriched = db_gc[coll].count_documents({'listing_status': 'for_sale', 'valuation_data': {'$exists': True}})
    coverage[coll] = {
        'active': total,
        'enriched': enriched,
        'pct': round(enriched / total * 100, 1) if total else 0,
    }
print(json.dumps(to_jsonable(coverage)))
client.close()
"""


def _structured_memory_script() -> str:
    return """
import json
import sys
sys.path.insert(0, '/home/fields/Fields_Orchestrator/scripts')
from ceo_agent_lib import get_client, now_aest, to_jsonable

client = get_client()
sm = client['system_monitor']
cutoff_14 = (now_aest().strftime('%Y-%m-%d'))

recent_proposals = list(sm['ceo_proposals'].find({'agent': {'$ne': 'system'}}, {'_id': 0}).limit(50))
recent_proposals.sort(key=lambda row: (row.get('date', ''), str(row.get('updated_at', ''))), reverse=True)
recent_outcomes = list(sm['ceo_proposal_outcomes'].find({}, {'_id': 0}).limit(100))
recent_outcomes.sort(key=lambda row: (row.get('date', ''), str(row.get('updated_at', ''))), reverse=True)
recent_changes = {
    'deploys': list(sm['website_deploy_events'].find({}, {'_id': 0}).limit(50)),
    'changes': list(sm['website_change_log'].find({}, {'_id': 0}).limit(50)),
}
recent_changes['deploys'].sort(key=lambda row: row.get('timestamp', ''), reverse=True)
recent_changes['changes'].sort(key=lambda row: row.get('created_at', ''), reverse=True)
active_experiments = list(sm['website_experiments'].find({'status': 'active'}, {'_id': 0}))

memory_rows = list(sm['ceo_memory'].find({}, {'_id': 0}).limit(400))
memory_rows.sort(key=lambda row: str(row.get('last_seen', '')), reverse=True)
recurring_issues = {}
for row in memory_rows:
    if row.get('record_type') not in {'finding', 'incident'}:
        continue
    title = row.get('title')
    if not title:
        continue
    recurring_issues[title] = {
        'times_seen': row.get('times_seen', 0),
        'first_seen': row.get('first_seen'),
        'last_seen': row.get('last_seen'),
        'latest_source': row.get('source'),
    }

payload = {
    'generated_at': now_aest().isoformat(),
    'recent_proposals': to_jsonable(recent_proposals[:20]),
    'recent_outcomes': to_jsonable(recent_outcomes[:50]),
    'recent_website_changes': to_jsonable(recent_changes),
    'active_experiments': to_jsonable(active_experiments),
    'structured_memory': to_jsonable(memory_rows[:200]),
    'recurring_issues': to_jsonable(recurring_issues),
}
print(json.dumps(payload))
client.close()
"""


def export_code_context() -> None:
    print("\n🧩 Exporting targeted code context...")
    targets = []
    for path in CODE_TARGETS:
        if not path.exists():
            continue
        rel = path.relative_to(ORCHESTRATOR_DIR if str(path).startswith(str(ORCHESTRATOR_DIR)) else WEBSITE_DIR)
        repo_path = f"code/{str(rel).replace(os.sep, '__')}"
        content = read_file(path, max_bytes=120_000)
        gh_api_put(repo_path, content, f"update: code context {path.name}")
        targets.append(
            {
                "source_path": str(path),
                "context_path": repo_path,
                "reason": "Hot-path code implicated by current OPS failures and public API regressions.",
            }
        )
    gh_api_put("code/targets.json", dumps_json(targets), "update: code context index")


def export_git_activity() -> None:
    print("\n📋 Exporting git activity...")
    repos = {"Fields_Orchestrator": ORCHESTRATOR_DIR}
    activity = {}
    for name, path in repos.items():
        result = run_command(["git", "log", "--oneline", "--since=14 days ago", "-n", "30"], cwd=path, timeout=15)
        activity[name] = (result.stdout or "").strip() or "[no commits]"

    if DRY_RUN:
        activity["Website"] = "[dry-run] skipped GitHub API query"
    else:
        result = run_command(
            ["gh", "api", "repos/Will954633/Website_Version_Feb_2026/commits", "--jq", '.[:20] | .[] | .sha[:7] + " " + (.commit.message | split("\\n")[0])'],
            timeout=30,
        )
        activity["Website"] = (result.stdout or "").strip() or "[no commits]"

    content = "\n".join(f"## {name}\n```\n{log}\n```\n" for name, log in activity.items())
    gh_api_put("metrics/git_activity.md", f"# Git Activity (last 14 days)\n\n{content}", "update: git activity")


def export_claude_md() -> None:
    print("\n📖 Exporting CLAUDE.md...")
    gh_api_put("CLAUDE.md", read_file(ORCHESTRATOR_DIR / "CLAUDE.md"), "update: CLAUDE.md reference")


def build_manifest() -> dict[str, Any]:
    required_failures = []
    for record in EXPORT_RECORDS:
        if record["required"] and (record["status"] != "ok" or record["bytes"] == 0):
            required_failures.append(
                {
                    "path": record["path"],
                    "reason": record["reason"],
                    "error": record["error"] or "required export missing or empty",
                }
            )
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "degraded": bool(required_failures),
        "required_failures": required_failures,
        "errors": EXPORT_ERRORS,
        "records": EXPORT_RECORDS,
        "required_exports": REQUIRED_JSON_EXPORTS,
    }
    return manifest


def export_manifest_and_timestamp() -> dict[str, Any]:
    manifest = build_manifest()
    print("\n🧾 Exporting context manifest...")
    gh_api_put("CONTEXT_MANIFEST.json", dumps_json(manifest), "update: context manifest")
    status_line = "DEGRADED" if manifest["degraded"] else "HEALTHY"
    gh_api_put("LAST_EXPORT.txt", f"Last exported: {now_label()}\nStatus: {status_line}\n", "update: export timestamp")
    return manifest


def main() -> None:
    load_env_file()
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}CEO Context Export — {now_label()}")
    print(f"Target repo: {REPO}")

    load_sha_cache()
    export_claude_md()
    export_memory()
    export_founder_truths()
    export_ops_status()
    export_schema()
    export_fix_history()
    export_pipeline_config()
    export_metrics_and_memory()
    export_code_context()
    export_git_activity()
    manifest = export_manifest_and_timestamp()

    if manifest["degraded"]:
        print("\n❌ Context export complete, but required inputs are degraded.")
        for failure in manifest["required_failures"]:
            print(f"  - {failure['path']}: {failure['error']}")
        sys.exit(1)

    print("\n✅ Context export complete.")


if __name__ == "__main__":
    main()
