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
import re
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
FOUNDER_REQUESTS_DIR = ORCHESTRATOR_DIR / "ceo-founder-requests"
DRY_RUN = "--dry-run" in sys.argv

SHA_CACHE: dict[str, str] = {}
EXPORT_RECORDS: list[dict[str, Any]] = []
EXPORT_ERRORS: list[str] = []

REQUIRED_JSON_EXPORTS = {
    "metrics/orchestrator_health.json": "Tuesday CEO reviews must verify daily and weekly orchestrator health.",
    "metrics/ad_performance_7d.json": "Ad telemetry is required for growth analysis.",
    "metrics/website_metrics_7d.json": "Website telemetry is required for experiment and funnel analysis.",
    "metrics/data_coverage.json": "Coverage telemetry is required for product and data-trust analysis.",
    "metrics/active_listings.json": "Listing counts are required for product and growth context.",
    "metrics/recent_pipeline_runs.json": "Pipeline run history is required for engineering analysis.",
}

REQUIRED_EXPORT_VALIDATORS = {
    "metrics/orchestrator_health.json": lambda payload: bool(payload.get("daily") and payload.get("weekly")),
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
        "orchestrator-health",
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


def validate_ad_to_session_coherence(metrics: dict) -> None:
    """Warn when paid ad clicks exist but website metrics show zero paid sessions."""
    ad_payload = metrics.get("metrics/ad_performance_7d.json") or {}
    web_payload = metrics.get("metrics/website_metrics_7d.json") or {}

    # Sum paid clicks across platforms
    ad_clicks = 0
    for platform in ("facebook", "google"):
        platform_data = ad_payload.get(platform)
        if isinstance(platform_data, dict):
            ad_clicks += platform_data.get("clicks", 0)
        elif isinstance(platform_data, list):
            ad_clicks += sum(row.get("clicks", 0) for row in platform_data if isinstance(row, dict))

    # Sum paid sessions from website metrics
    paid_sessions = 0
    rows = web_payload.get("rows") if isinstance(web_payload, dict) else web_payload
    if isinstance(rows, list):
        for row in rows:
            sources = row.get("sources", {}) if isinstance(row, dict) else {}
            paid_sessions += sources.get("facebook", 0) + sources.get("google", 0)

    if ad_clicks > 10 and paid_sessions == 0:
        warning = f"⚠️  COHERENCE WARNING: {ad_clicks} paid ad clicks in 7d but 0 paid website sessions — attribution may be broken"
        print(f"  {warning}")
        EXPORT_ERRORS.append(warning)


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


def refresh_live_data_sources() -> None:
    """Run data collectors before export so CEO agents get fresh data, not stale snapshots."""
    print("\n🔄 Refreshing live data sources before export...")

    collectors = [
        {
            "name": "website-metrics-collector (backfill today)",
            "cmd": ["/home/fields/venv/bin/python3", "scripts/website-metrics-collector.py", "--backfill", "1"],
            "timeout": 180,
        },
        {
            "name": "api-health-check",
            "cmd": ["/home/fields/venv/bin/python3", "scripts/api-health-check.py"],
            "timeout": 120,
        },
        {
            "name": "write-scraper-health",
            "cmd": ["/home/fields/venv/bin/python3", "write-scraper-health.py"],
            "timeout": 120,
        },
    ]
    for coll in collectors:
        try:
            result = run_command(coll["cmd"], cwd=ORCHESTRATOR_DIR, timeout=coll["timeout"])
            status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
            print(f"  {coll['name']}: {status}")
            if result.returncode != 0 and result.stderr:
                print(f"    stderr: {result.stderr.strip()[:200]}")
        except Exception as exc:
            print(f"  {coll['name']}: FAILED ({exc})")


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


def _parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    raw = read_file(path)
    if not raw.startswith("---\n"):
        return {}, raw

    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.DOTALL)
    if not match:
        return {}, raw

    try:
        meta = yaml.safe_load(match.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    body = match.group(2)
    return meta, body


def _extract_title(path: Path, meta: dict[str, Any], body: str) -> str:
    if meta.get("title"):
        return str(meta["title"]).strip()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return path.stem.replace("-", " ")


def _extract_summary(body: str, limit: int = 220) -> str:
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
        if len(" ".join(lines)) >= limit:
            break
    summary = " ".join(lines)
    if len(summary) > limit:
        return summary[: limit - 3].rstrip() + "..."
    return summary


def export_founder_requests() -> None:
    print("\n📬 Exporting founder request threads...")
    if not FOUNDER_REQUESTS_DIR.exists():
        print("  [no founder request directory]")
        return

    readme_path = FOUNDER_REQUESTS_DIR / "README.md"
    if readme_path.exists():
        gh_api_put("founder-requests/README.md", read_file(readme_path), "update: founder requests readme")

    open_dir = FOUNDER_REQUESTS_DIR / "open"
    responses_dir = FOUNDER_REQUESTS_DIR / "responses"
    closed_dir = FOUNDER_REQUESTS_DIR / "closed"

    open_files = sorted(open_dir.glob("*.md")) if open_dir.exists() else []
    response_files = sorted(responses_dir.glob("*.md")) if responses_dir.exists() else []

    response_map: dict[str, Path] = {path.stem: path for path in response_files}
    threads: list[dict[str, Any]] = []

    for folder_name, folder in (("open", open_dir), ("responses", responses_dir), ("closed", closed_dir)):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name == "README.md" or path.name.upper().startswith("TEMPLATE"):
                continue
            gh_api_put(f"founder-requests/{folder_name}/{path.name}", read_file(path), f"update: founder request {folder_name}/{path.name}")

    for path in open_files:
        if path.name.upper().startswith("TEMPLATE"):
            continue
        meta, body = _parse_frontmatter(path)
        response_path = response_map.get(path.stem)
        latest_update = datetime.fromtimestamp(path.stat().st_mtime)
        if response_path is not None:
            response_mtime = datetime.fromtimestamp(response_path.stat().st_mtime)
            if response_mtime > latest_update:
                latest_update = response_mtime
        threads.append(
            {
                "id": str(meta.get("id") or path.stem),
                "request_file": f"founder-requests/open/{path.name}",
                "response_file": f"founder-requests/responses/{response_path.name}" if response_path else None,
                "title": _extract_title(path, meta, body),
                "area": meta.get("area"),
                "priority": meta.get("priority"),
                "status": meta.get("status", "open"),
                "type": meta.get("type"),
                "owner": meta.get("owner"),
                "created_at": meta.get("created_at"),
                "latest_update": latest_update.isoformat(),
                "summary": _extract_summary(body),
            }
        )

    threads.sort(key=lambda row: (str(row.get("priority") or ""), str(row.get("latest_update") or "")), reverse=True)
    gh_api_put("founder-requests/index.json", dumps_json({"generated_at": datetime.now().isoformat(), "open_threads": threads}), "update: founder requests index")


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
        "metrics/orchestrator_health.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "orchestrator-health"]),
        "metrics/active_listings.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "active-listings"]),
        "metrics/recent_pipeline_runs.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "pipeline-runs", "--days", "7", "--limit", "20"]),
        "metrics/ad_performance_7d.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "ad-metrics", "--days", "7", "--limit", "50"]),
        "metrics/website_metrics_7d.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "website-metrics", "--days", "7"]),
        "metrics/data_coverage.json": query_json(["/home/fields/venv/bin/python3", "-c", _coverage_query_script()]),
        "metrics/ops_summary.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "ops-summary"]),
        "metrics/cost_summary_30d.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "cost-summary", "--days", "30"]),
        "metrics/timeline_14d.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "timeline", "--days", "14"]),
        "memory/proposal_outcomes.json": query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "proposal-outcomes", "--days", "30", "--limit", "100"]),
        "tools/read_only_query_contract.json": READ_ONLY_TOOL_CONTRACT,
    }
    structured = query_json(["/home/fields/venv/bin/python3", "-c", _structured_memory_script()])
    metrics["memory/structured_memory.json"] = structured
    metrics["experiments/active_experiments.json"] = structured.get("active_experiments", [])
    metrics["metrics/recent_website_changes.json"] = structured.get("recent_website_changes", {})
    metrics["metrics/recent_proposals.json"] = structured.get("recent_proposals", [])

    # Cross-metric coherence check before uploading
    validate_ad_to_session_coherence(metrics)

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
import time
sys.path.insert(0, '/home/fields/Fields_Orchestrator/scripts')
from ceo_agent_lib import get_client, retry_cosmos_read, to_jsonable

client = get_client()
db_gc = client['Gold_Coast']
skip = {'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots'}
coverage = {}
for coll in sorted(retry_cosmos_read(lambda: db_gc.list_collection_names())):
    if coll.startswith('system') or coll in skip:
        continue
    total = retry_cosmos_read(lambda coll_name=coll: db_gc[coll_name].count_documents({'listing_status': 'for_sale'}))
    if total == 0:
        continue
    enriched = retry_cosmos_read(lambda coll_name=coll: db_gc[coll_name].count_documents({'listing_status': 'for_sale', 'valuation_data': {'$exists': True}}))
    coverage[coll] = {
        'active': total,
        'enriched': enriched,
        'pct': round(enriched / total * 100, 1) if total else 0,
    }
    time.sleep(0.12)
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


BACKUP_SCRAPER_HOST = "fields-orchestrator-vm@35.201.6.222"
BACKUP_SCRAPER_DIR = "/home/projects/scraper"
BACKUP_SCRAPER_SCRIPTS = [
    "url_tracking_run.py",
    "continuous_monitor.py",
    "hybrid_extraction_poc.py",
    "robust_extractor.py",
    "url_tracker.py",
    "direct_agency_scraper.py",
    "gpt_verifier.py",
    "selfhosted_searxng_search.py",
    "launcher.py",
    "status.sh",
    "start_scraper.sh",
    "run_scraper.sh",
    "stop_scraper.sh",
    "coverage_comparison.py",
    "property_timelines.py",
]


def export_backup_scraper() -> None:
    """Export backup scraper status, recent logs, and code from property-scraper VM."""
    print("\n🕷️ Exporting backup scraper context from property-scraper VM...")

    def ssh_cmd(cmd: str, timeout: int = 30) -> str:
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", BACKUP_SCRAPER_HOST, cmd],
                capture_output=True, text=True, timeout=timeout,
            )
            return result.stdout.strip() if result.returncode == 0 else f"[SSH error: {result.stderr.strip()[:200]}]"
        except Exception as exc:
            return f"[SSH exception: {exc}]"

    # 1. Scraper status
    status = ssh_cmd(f"sudo bash {BACKUP_SCRAPER_DIR}/status.sh")
    gh_api_put("backup-scraper/status.txt", status, "update: backup scraper status")

    # 2. Recent log (last 200 lines)
    log_tail = ssh_cmd(f"sudo tail -200 {BACKUP_SCRAPER_DIR}/scraper.log", timeout=15)
    gh_api_put("backup-scraper/recent_log.txt", log_tail, "update: backup scraper recent log")

    # 3. Discovered URLs summary
    url_summary = ssh_cmd(f"sudo find {BACKUP_SCRAPER_DIR}/discovered_urls -name '*.json' -exec wc -l {{}} + 2>/dev/null | tail -10")
    gh_api_put("backup-scraper/discovered_urls_summary.txt", url_summary, "update: backup scraper URL discovery summary")

    # 4. Export key code files
    for script in BACKUP_SCRAPER_SCRIPTS:
        content = ssh_cmd(f"sudo cat {BACKUP_SCRAPER_DIR}/{script}", timeout=15)
        if content and not content.startswith("[SSH"):
            gh_api_put(f"backup-scraper/code/{script}", content, f"update: backup scraper {script}")

    # 5. CLAUDE.md from the scraper project (if exists)
    claude_md = ssh_cmd(f"sudo cat {BACKUP_SCRAPER_DIR}/CLAUDE.md 2>/dev/null")
    if claude_md and not claude_md.startswith("[SSH"):
        gh_api_put("backup-scraper/CLAUDE.md", claude_md, "update: backup scraper CLAUDE.md")

    # 6. Directory listing
    dir_listing = ssh_cmd(f"sudo ls -la {BACKUP_SCRAPER_DIR}/")
    gh_api_put("backup-scraper/directory_listing.txt", dir_listing, "update: backup scraper directory listing")


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
    refresh_live_data_sources()
    export_claude_md()
    export_memory()
    export_founder_truths()
    export_founder_requests()
    export_ops_status()
    export_schema()
    export_fix_history()
    export_pipeline_config()
    export_metrics_and_memory()
    export_code_context()
    export_backup_scraper()
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
