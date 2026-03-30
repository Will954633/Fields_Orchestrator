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
AGENT_MEMORY_DIR = ORCHESTRATOR_DIR / "ceo-agent-memory"
DRY_RUN = "--dry-run" in sys.argv

SHA_CACHE: dict[str, str] = {}
EXPORT_RECORDS: list[dict[str, Any]] = []
EXPORT_ERRORS: list[str] = []

REQUIRED_JSON_EXPORTS = {
    "metrics/orchestrator_health.json": "Tuesday CEO reviews must verify daily and weekly orchestrator health.",
    "metrics/ad_performance_7d.json": "Ad telemetry is required for growth analysis.",
    "metrics/website_metrics_7d.json": "Website telemetry from PostHog — visitor sessions, sources, experiments.",
    "metrics/data_coverage.json": "Coverage telemetry is required for product and data-trust analysis.",
    "metrics/active_listings.json": "Listing counts are required for product and growth context.",
    "metrics/recent_pipeline_runs.json": "Pipeline run history is required for engineering analysis.",
    "experiments/experiment_results_7d.json": "Per-variant experiment outcomes from PostHog — required for product and growth analysis.",
}

REQUIRED_EXPORT_VALIDATORS = {
    "metrics/orchestrator_health.json": lambda payload: bool(payload.get("daily") and payload.get("weekly")),
    "metrics/ad_performance_7d.json": lambda payload: bool(payload.get("facebook") or payload.get("google")),
    "metrics/website_metrics_7d.json": lambda payload: bool(payload.get("source") == "posthog"),
    "metrics/data_coverage.json": lambda payload: bool(payload.get("enrichment")),
    "metrics/active_listings.json": lambda payload: bool(payload.get("counts")),
    "metrics/recent_pipeline_runs.json": lambda payload: bool(payload.get("runs")),
    "experiments/experiment_results_7d.json": lambda payload: bool(payload.get("source") == "posthog" and payload.get("experiments")),
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
        "search-console --days N",
        "proposal-outcomes --days N --limit N",
        "timeline --days N",
    ],
    "guardrails": [
        "No writes to MongoDB.",
        "No shell execution outside the approved broker commands.",
        "Results should be cited back to exported evidence files where possible.",
    ],
}


_CREDENTIAL_PATTERNS = [
    # Azure Cosmos / MongoDB connection strings
    re.compile(r'mongodb(\+srv)?://[^\s"\']+'),
    re.compile(r'AccountEndpoint=https?://[^\s"\']+'),
    # Generic connection-string-style secrets (key=value with base64-ish values)
    re.compile(r'AccountKey=[A-Za-z0-9+/=]{20,}'),
    # Bare base64 keys that look like Azure primary/secondary keys (44+ chars)
    re.compile(r'(?<=["\'])([A-Za-z0-9+/]{40,}={0,2})(?=["\'])'),
]


def scrub_credentials(content: str) -> str:
    """Remove connection strings and credential-like values from source code before export."""
    scrubbed = content
    for pattern in _CREDENTIAL_PATTERNS:
        scrubbed = pattern.sub("[CREDENTIAL_SCRUBBED]", scrubbed)
    return scrubbed


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


def export_agent_memory() -> None:
    """Export per-agent persistent memory files (Recommendation 2: OpenClaw pattern)."""
    print("\n🧠 Exporting agent memory files...")
    if not AGENT_MEMORY_DIR.exists():
        print("  [no agent memory directory]")
        return
    for agent_dir in sorted(AGENT_MEMORY_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        for path in sorted(agent_dir.glob("*.md")):
            repo_path = f"agent-memory/{agent_id}/{path.name}"
            gh_api_put(repo_path, read_file(path), f"update: agent memory {agent_id}/{path.name}")


def export_founder_truths() -> None:
    print("\n🧭 Exporting founder truths...")
    truths = load_founder_truths()
    gh_api_put("memory/founder_truths.json", dumps_json(truths), "update: founder truths")


def _cleanup_stale_process_runs() -> None:
    """Mark process_runs stuck in 'running' for >4 hours as failed_stale.

    Without this, zombie records accumulate from interrupted pipeline runs and
    cause the CEO agents to report phantom duplicate steps indefinitely.
    """
    from ceo_agent_lib import get_client

    MAX_RUNNING_HOURS = 4
    try:
        client = get_client()
        sm = client["system_monitor"]
        cutoff = datetime.now() - timedelta(hours=MAX_RUNNING_HOURS)

        # Find all records stuck in "running"
        stale = list(sm["process_runs"].find({"status": "running"}).limit(200))

        cleaned = 0
        for rec in stale:
            started = rec.get("started_at")
            # If no started_at, or started more than MAX_RUNNING_HOURS ago → stale
            is_stale = started is None
            if started and isinstance(started, datetime) and started < cutoff:
                is_stale = True
            elif started and isinstance(started, str):
                try:
                    if datetime.fromisoformat(started.replace("Z", "+00:00")).replace(tzinfo=None) < cutoff:
                        is_stale = True
                except Exception:
                    is_stale = True

            if is_stale:
                sm["process_runs"].update_one(
                    {"_id": rec["_id"]},
                    {"$set": {
                        "status": "failed_stale",
                        "cleaned_at": datetime.now().isoformat(),
                        "clean_reason": f"Stuck in running for >{MAX_RUNNING_HOURS}h. Auto-cleaned by CEO pre-flight.",
                    }},
                )
                cleaned += 1

        client.close()
        if cleaned:
            print(f"  stale-run cleanup: marked {cleaned} zombie running records as failed_stale")
        else:
            print(f"  stale-run cleanup: no zombie records found")
    except Exception as exc:
        print(f"  stale-run cleanup: FAILED ({exc})")


def refresh_live_data_sources() -> None:
    """Run data collectors and cleanup before export so CEO agents get fresh, accurate data."""
    print("\n🔄 Refreshing live data sources before export...")

    # Step 0: Clean up stale process_runs records first — prevents phantom duplicate steps
    _cleanup_stale_process_runs()

    collectors = [
        # website-metrics-collector REMOVED 2026-03-19: replaced by PostHog
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
    metrics["experiments/experiment_results_7d.json"] = query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "experiment-results", "--days", "7"])
    try:
        metrics["metrics/search_console_7d.json"] = query_json(["/home/fields/venv/bin/python3", "scripts/ceo-query-broker.py", "search-console", "--days", "7"])
    except Exception as exc:
        print(f"  ⚠ Search Console export failed (non-critical): {exc}")
        metrics["metrics/search_console_7d.json"] = {"source": "google_search_console", "error": str(exc)[:200], "queries": [], "pages": []}
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
enrichment = {}
for coll in sorted(retry_cosmos_read(lambda: db_gc.list_collection_names())):
    if coll.startswith('system') or coll in skip:
        continue
    total = retry_cosmos_read(lambda coll_name=coll: db_gc[coll_name].count_documents({'listing_status': 'for_sale'}))
    if total == 0:
        continue
    enriched = retry_cosmos_read(lambda coll_name=coll: db_gc[coll_name].count_documents({'listing_status': 'for_sale', 'valuation_data': {'$exists': True}}))
    enrichment[coll] = {
        'active': total,
        'enriched': enriched,
        'enrichment_pct': round(enriched / total * 100, 1) if total else 0,
    }
    time.sleep(0.12)

# Also fetch scrape coverage from system_monitor.data_integrity (step 109 output)
db_sm = client['system_monitor']
scrape_coverage = {}
try:
    for doc in retry_cosmos_read(lambda: list(db_sm['data_integrity'].find({'check_type': 'data_coverage'}))):
        suburb = doc.get('suburb')
        if not suburb:
            continue
        scrape_coverage[suburb] = {
            'status': doc.get('status', 'unknown'),
            'db_count': doc.get('total_listings'),
            'checked_at': str(doc.get('checked_at', '')),
        }
except Exception:
    pass

result = {
    'metric_type': 'enrichment_and_scrape_coverage',
    'note': 'enrichment = listings with valuation_data; scrape_coverage = DB count vs live Domain.com.au (from step 109)',
    'enrichment': enrichment,
    'scrape_coverage': scrape_coverage,
}
print(json.dumps(to_jsonable(result)))
client.close()
"""


def _structured_memory_script() -> str:
    return """
import json
import sys
sys.path.insert(0, '/home/fields/Fields_Orchestrator/scripts')
from ceo_agent_lib import get_client, now_aest, to_jsonable, load_founder_truths

client = get_client()
sm = client['system_monitor']
cutoff_14 = (now_aest().strftime('%Y-%m-%d'))

# Load known resolved issues so we can tag stale proposals
founder_truths = load_founder_truths()
resolved_items = founder_truths.get('known_resolved_issues', {}).get('items', [])
resolved_ids = {item['id'] for item in resolved_items}
resolved_keywords = {}
for item in resolved_items:
    # Build keyword-to-id map from descriptions for fuzzy matching
    desc_lower = item.get('description', '').lower()
    resolved_keywords[item['id']] = {
        'resolved': item.get('resolved', ''),
        'description': item.get('description', ''),
        'keywords': set(desc_lower.split()),
    }

def _matches_resolved(text):
    # Check if text references a known resolved issue. Returns list of matched IDs.
    if not text:
        return []
    text_lower = text.lower()
    matches = []
    # Direct ID match
    for rid in resolved_ids:
        if rid.replace('_', ' ') in text_lower or rid in text_lower:
            matches.append(rid)
    # Key phrase matching
    phrase_map = {
        'recently_sold_route': ['recently-sold', 'recently sold route', 'sold route', 'sold-route'],
        'ops_counts_inflated': ['ops counts', 'inflated counts', 'listing_status filter'],
        'step_106_zombies': ['step 106 zombie', 'orphaned process_runs', 'concurrent step 106'],
        'facebook_attribution': ['facebook attribution', 'fb attribution', 'self-referral'],
        'google_ads_attribution': ['google ads attribution', 'gclid', 'gad_source'],
        'experiment_variant_race': ['variant race', 'active_variants null', '$setOnInsert race'],
    }
    for rid, phrases in phrase_map.items():
        if rid in matches:
            continue
        for phrase in phrases:
            if phrase in text_lower:
                matches.append(rid)
                break
    return matches

def tag_stale_proposals(proposals):
    # Annotate proposals whose findings reference known resolved issues.
    for prop in proposals:
        stale_refs = []
        # Check findings
        for finding in prop.get('findings', []):
            title = finding.get('title', '')
            detail = finding.get('detail', '')
            rec = finding.get('recommendation', '')
            matched = _matches_resolved(f'{title} {detail} {rec}')
            if matched:
                finding['_resolved_upstream'] = matched
                finding['_staleness_note'] = f'References resolved issue(s): {", ".join(matched)}. Verify fix is holding rather than re-flagging.'
                stale_refs.extend(matched)
        # Check proposals list
        for p in prop.get('proposals', []):
            problem = p.get('problem', '')
            proposal_text = p.get('proposal', '')
            title = p.get('title', '')
            matched = _matches_resolved(f'{title} {problem} {proposal_text}')
            if matched:
                p['_resolved_upstream'] = matched
                p['_staleness_note'] = f'References resolved issue(s): {", ".join(matched)}. Verify fix is holding rather than re-flagging.'
                stale_refs.extend(matched)
        if stale_refs:
            prop['_has_stale_references'] = True
            prop['_stale_issue_ids'] = list(set(stale_refs))
    return proposals

recent_proposals = list(sm['ceo_proposals'].find({'agent': {'$ne': 'system'}}, {'_id': 0}).limit(50))
recent_proposals.sort(key=lambda row: (row.get('date', ''), str(row.get('updated_at', ''))), reverse=True)
recent_proposals = tag_stale_proposals(recent_proposals[:20])

recent_outcomes = list(sm['ceo_proposal_outcomes'].find({}, {'_id': 0}).limit(100))
recent_outcomes.sort(key=lambda row: (row.get('date', ''), str(row.get('updated_at', ''))), reverse=True)
recent_changes = {
    'deploys': list(sm['website_deploy_events'].find({}, {'_id': 0}).limit(50)),
    'changes': list(sm['website_change_log'].find({}, {'_id': 0}).limit(50)),
}
recent_changes['deploys'].sort(key=lambda row: row.get('timestamp', ''), reverse=True)
recent_changes['changes'].sort(key=lambda row: row.get('created_at', ''), reverse=True)
# Experiments now managed by PostHog feature flags (migrated 2026-03-19)
# PostHog experiment data is in metrics/website_metrics_7d.json instead
active_experiments = [{"note": "A/B experiments managed via PostHog feature flags since 2026-03-19. See metrics/website_metrics_7d.json for flag configs."}]

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

# Include resolved issues list so agents know what NOT to re-flag
known_resolved = [{'id': item['id'], 'resolved': item.get('resolved', ''), 'description': item.get('description', '')} for item in resolved_items]
data_context = founder_truths.get('data_context_notes', {}).get('items', [])

payload = {
    'generated_at': now_aest().isoformat(),
    'known_resolved_issues': known_resolved,
    'data_context_notes': data_context,
    'recent_proposals': to_jsonable(recent_proposals),
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

    # 4. Export key code files (credentials scrubbed)
    for script in BACKUP_SCRAPER_SCRIPTS:
        content = ssh_cmd(f"sudo cat {BACKUP_SCRAPER_DIR}/{script}", timeout=15)
        if content and not content.startswith("[SSH"):
            safe_content = scrub_credentials(content)
            gh_api_put(f"backup-scraper/code/{script}", safe_content, f"update: backup scraper {script}")

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


def export_focus_context() -> None:
    """Export sprint context, proposal feedback, grind status, leads, and KB summary to context/focus/."""
    print("\n🎯 Exporting focus context...")

    # 1. current_sprint.md — find the current sprint file based on date
    sprint_dir = ORCHESTRATOR_DIR / "07_Focus" / "sprints"
    sprint_content = None
    if sprint_dir.exists():
        sprint_files = sorted(sprint_dir.glob("sprint-*.md"))
        # Use the latest numbered sprint (highest number, excluding outline files)
        numbered = [f for f in sprint_files if re.match(r"sprint-\d+\.md$", f.name)]
        if numbered:
            current_sprint = numbered[-1]
            sprint_content = read_file(current_sprint)
            gh_api_put("context/focus/current_sprint.md", sprint_content, f"update: current sprint ({current_sprint.name})")
        else:
            gh_api_put("context/focus/current_sprint.md", "# Current Sprint\n\nNo numbered sprint files found.", "update: current sprint (empty)")
    else:
        gh_api_put("context/focus/current_sprint.md", "# Current Sprint\n\nSprint directory not yet created.", "update: current sprint (missing)")

    # 2. milestone_status.md — generate short status
    try:
        from datetime import date
        today = date.today()
        q3_start = date(2026, 7, 1)
        q3_days = (q3_start - today).days
        milestone_md = f"""# Milestone Status
Generated: {now_label()}

## Current Goal
Build buyer audience through data-driven property intelligence (pre-revenue phase).

## Current Milestone
Complete core suburb coverage (Robina, Varsity Lakes, Burleigh Waters) with enriched listings, valuations, and editorial content.

## Progress Indicators
- Pipeline: Running nightly at 20:30 AEST
- Target suburbs: 3 core (Robina, Varsity Lakes, Burleigh Waters)
- Stage: Pre-revenue, building data infrastructure

## Q3 2026 Countdown
**{q3_days} days** until Q3 2026 (1 July 2026)
"""
        # If we have sprint content, try to extract sprint goal
        if sprint_content:
            for line in sprint_content.splitlines():
                if "goal" in line.lower() and (":" in line or line.strip().startswith("#")):
                    milestone_md += f"\n## Sprint Goal (from sprint file)\n{line.strip()}\n"
                    break
        gh_api_put("context/focus/milestone_status.md", milestone_md, "update: milestone status")
    except Exception as exc:
        gh_api_put("context/focus/milestone_status.md", f"# Milestone Status\n\nError generating: {exc}", "update: milestone status (error)")

    # 3. yesterday_outcome.md — summarize latest fix-history
    try:
        fix_dir = ORCHESTRATOR_DIR / "logs" / "fix-history"
        yesterday_md = "# Yesterday's Outcomes\nGenerated: " + now_label() + "\n\n"
        if fix_dir.exists():
            fix_files = sorted([f for f in fix_dir.glob("*.md") if f.name != "README.md"])
            # Get the most recent file(s) — yesterday and today
            recent_fixes = fix_files[-2:] if len(fix_files) >= 2 else fix_files
            if recent_fixes:
                for fpath in recent_fixes:
                    yesterday_md += f"## {fpath.stem}\n\n"
                    content = read_file(fpath)
                    # Extract just the headings for a summary
                    headings = [line.strip() for line in content.splitlines() if line.strip().startswith("## [")]
                    if headings:
                        for h in headings:
                            yesterday_md += f"- {h}\n"
                    else:
                        yesterday_md += "(No structured entries found)\n"
                    yesterday_md += "\n"
            else:
                yesterday_md += "No fix-history files found.\n"
        else:
            yesterday_md += "Fix-history directory does not exist.\n"
        gh_api_put("context/focus/yesterday_outcome.md", yesterday_md, "update: yesterday outcome")
    except Exception as exc:
        gh_api_put("context/focus/yesterday_outcome.md", f"# Yesterday's Outcomes\n\nError: {exc}", "update: yesterday outcome (error)")

    # 4. proposal_decisions.md — query ceo_proposals for last 7 days
    try:
        from ceo_agent_lib import get_client, to_jsonable
        client = get_client()
        sm = client["system_monitor"]
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        proposals = list(sm["ceo_proposals"].find(
            {"date": {"$gte": cutoff}},
            {"_id": 0, "agent": 1, "date": 1, "title": 1, "approval_status": 1, "status": 1}
        ).limit(50))
        client.close()

        decisions_md = f"# Proposal Decisions (last 7 days)\nGenerated: {now_label()}\n\n"
        if proposals:
            has_approval = any(p.get("approval_status") for p in proposals)
            if not has_approval:
                decisions_md += "> **Note:** `approval_status` field not yet populated on any proposals. Status tracking not yet implemented.\n\n"
            decisions_md += f"| Date | Agent | Title | Status |\n|------|-------|-------|--------|\n"
            for p in sorted(proposals, key=lambda x: x.get("date", ""), reverse=True):
                status = p.get("approval_status") or p.get("status") or "no status"
                decisions_md += f"| {p.get('date', '?')} | {p.get('agent', '?')} | {p.get('title', 'untitled')[:60]} | {status} |\n"
        else:
            decisions_md += "No proposals found in the last 7 days.\n"
        gh_api_put("context/focus/proposal_decisions.md", decisions_md, "update: proposal decisions")
    except Exception as exc:
        gh_api_put("context/focus/proposal_decisions.md", f"# Proposal Decisions\n\nError querying proposals: {exc}", "update: proposal decisions (error)")

    # 5. grind_status.md — static list of grind backlog items
    grind_md = f"""# Grind Backlog Status
Generated: {now_label()}

These are operational/admin tasks that need attention but are not sprint work.

| Item | Category | Status |
|------|----------|--------|
| PAYG registration | Tax/Compliance | Pending |
| Tax return (2024-25) | Tax/Compliance | Pending |
| Ray White invoices | Finance | Pending |
| Bank reconciliation | Finance | Pending |
| WISE international transfers | Finance | Pending |
| API spend tracking (OpenAI, Anthropic, Azure) | Operations | Partially tracked via cost-collector.py |

> This is a static list. Update `ceo-context-export.py` when items are completed or new items are added.
"""
    gh_api_put("context/focus/grind_status.md", grind_md, "update: grind status")

    # 6. lead_metrics.md — query system_monitor.leads
    try:
        from ceo_agent_lib import get_client, to_jsonable
        client = get_client()
        sm = client["system_monitor"]
        leads_md = f"# Lead Metrics\nGenerated: {now_label()}\n\n"

        # Check if leads collection exists
        coll_names = sm.list_collection_names()
        if "leads" in coll_names:
            total_leads = sm["leads"].count_documents({})
            leads_md += f"**Total leads:** {total_leads}\n\n"

            if total_leads > 0:
                # Source breakdown
                pipeline = [{"$group": {"_id": "$source", "count": {"$sum": 1}}}]
                sources = list(sm["leads"].aggregate(pipeline))
                if sources:
                    leads_md += "## Sources\n| Source | Count |\n|--------|-------|\n"
                    for s in sorted(sources, key=lambda x: x.get("count", 0), reverse=True):
                        leads_md += f"| {s.get('_id', 'unknown')} | {s.get('count', 0)} |\n"
                    leads_md += "\n"

                # Latest lead
                latest = sm["leads"].find_one({}, sort=[("created_at", -1)])
                if latest:
                    leads_md += f"**Latest lead:** {latest.get('created_at', 'unknown timestamp')}\n"
            else:
                leads_md += "No leads recorded yet.\n"
        else:
            leads_md += "The `leads` collection does not exist yet. Lead tracking has not been implemented.\n"
        client.close()
        gh_api_put("context/focus/lead_metrics.md", leads_md, "update: lead metrics")
    except Exception as exc:
        gh_api_put("context/focus/lead_metrics.md", f"# Lead Metrics\n\nError: {exc}", "update: lead metrics (error)")

    # 7. kb_summary.md — summarize knowledge base categories and document counts
    try:
        kb_dir = Path("/home/fields/knowledge-base")
        kb_md = f"# Knowledge Base Summary\nGenerated: {now_label()}\n\n"
        if kb_dir.exists():
            categories = sorted([d.name for d in kb_dir.iterdir() if d.is_dir()])
            kb_md += f"**Categories:** {len(categories)}\n\n"
            kb_md += "| Category | Documents |\n|----------|----------|\n"
            total_docs = 0
            for cat in categories:
                cat_dir = kb_dir / cat
                doc_count = len(list(cat_dir.glob("*")))
                total_docs += doc_count
                kb_md += f"| {cat} | {doc_count} |\n"
            kb_md += f"\n**Total documents:** {total_docs}\n"
            kb_md += f"\n**Search:** `python3 scripts/search-kb.py \"query\" --max 5`\n"
        else:
            kb_md += "Knowledge base directory (`/home/fields/knowledge-base/`) not found.\n"
        gh_api_put("context/focus/kb_summary.md", kb_md, "update: kb summary")
    except Exception as exc:
        gh_api_put("context/focus/kb_summary.md", f"# Knowledge Base Summary\n\nError: {exc}", "update: kb summary (error)")

    # 8. agent_roles.md — sprint-aware role assignments
    agent_roles_md = f"""# Agent Role Directives
Generated: {now_label()}

These role assignments are sprint-aware. Each agent should operate within their defined scope.

## Engineering Agent
- **Primary:** Sprint enabler — unblock technical work for the current sprint
- **Secondary:** Backup scraper owner — monitor and maintain the property-scraper VM system
- **Focus:** Pipeline reliability, infrastructure, code quality, deployment

## Product Agent
- **Primary:** Milestone strategist — ensure product work aligns to current milestone
- **Secondary:** Conversion spec owner — define and validate conversion funnels
- **Research:** Find case studies for every product challenge (competitor analysis, UX patterns, pricing models)
- **Focus:** Feature prioritisation, user experience, data product quality

## Growth Agent
- **Primary:** Channel optimizer — maximize ROI across paid and organic channels
- **Secondary:** Ad memo owner — document all ad decisions with hypotheses and outcomes
- **Research:** Find case studies for growth tactics (attribution, audience building, content strategy)
- **Focus:** Facebook/Google ads, organic content, SEO, audience development

## Data Quality Agent
- **Primary:** Foundation guardian — ensure data accuracy, completeness, and freshness
- **Focus:** Coverage gaps, enrichment quality, valuation accuracy, scraper reliability

## Chief of Staff Agent
- **Primary:** Sprint commander — track sprint progress and flag blockers
- **Secondary:** Look-ahead engine — identify upcoming risks and opportunities
- **Tertiary:** Synthesis — connect dots across agent outputs and surface actionable insights
- **Focus:** Cross-agent coordination, milestone tracking, founder communication
"""
    gh_api_put("context/focus/agent_roles.md", agent_roles_md, "update: agent roles")

    # 9. content_research_data.md — trending keywords, top-performing content, ad history
    print("  📊 Exporting content research data...")
    try:
        from shared.db import get_client as _get_content_client
        _client = _get_content_client()
        _sm = _client["system_monitor"]
        _gc = _client["Gold_Coast"]

        content_md = f"# Content Research Data\nGenerated: {now_label()}\n\n"
        content_md += "Use this data when reviewing content briefs, suggesting topics, or evaluating what's working.\n\n"

        # --- YouTube keyword data ---
        content_md += "## YouTube Search Suggestions (Top 50 by relevance)\n\n"
        try:
            yt_suggestions = list(_sm["search_youtube_suggestions"].find(
                {"suggestion": {"$regex": "robina|burleigh|varsity|gold coast|property|house|sell|buy", "$options": "i"}},
                {"_id": 0, "query": 1, "suggestion": 1}
            ).limit(50))
            content_md += f"**Total YouTube suggestions in DB:** {_sm['search_youtube_suggestions'].count_documents({})}\n\n"
            if yt_suggestions:
                content_md += "| Seed Query | YouTube Autocomplete Suggestion |\n|-----------|-------------------------------|\n"
                for s in yt_suggestions:
                    content_md += f"| {s.get('query', '')} | {s.get('suggestion', '')} |\n"
            else:
                content_md += "(No matching suggestions found)\n"
        except Exception as e:
            content_md += f"(Error querying YouTube suggestions: {e})\n"

        # --- Google autocomplete / People Also Ask ---
        content_md += "\n## Google People Also Ask — Top Questions\n\n"
        try:
            paa = list(_sm["search_paa_questions"].find(
                {"question": {"$regex": "robina|burleigh|varsity|gold coast|property|house|sell|buy", "$options": "i"}},
                {"_id": 0, "question": 1, "source_query": 1}
            ).limit(30))
            content_md += f"**Total PAA questions in DB:** {_sm['search_paa_questions'].count_documents({})}\n\n"
            for q in paa:
                content_md += f"- {q.get('question', '')} *(from: {q.get('source_query', '')})*\n"
        except Exception as e:
            content_md += f"(Error: {e})\n"

        # --- Ad performance summary ---
        content_md += "\n## Facebook Ad Performance (Recent)\n\n"
        try:
            ad_profiles = list(_sm["ad_profiles"].find(
                {},
                {"_id": 0, "ad_name": 1, "campaign_name": 1, "status": 1, "creative.body": 1}
            ).limit(30))
            content_md += f"**Total ad profiles tracked:** {_sm['ad_profiles'].count_documents({})}\n\n"
            if ad_profiles:
                content_md += "| Campaign | Ad Name | Status |\n|----------|---------|--------|\n"
                for a in ad_profiles:
                    content_md += f"| {(a.get('campaign_name') or '')[:40]} | {(a.get('ad_name') or '')[:50]} | {a.get('status', '?')} |\n"
        except Exception as e:
            content_md += f"(Error: {e})\n"

        # --- Ad decisions / experiment history ---
        content_md += "\n## Ad Decisions Log (Last 10)\n\n"
        try:
            decisions = list(_sm["ad_decisions"].find(
                {},
                {"_id": 0, "date": 1, "type": 1, "title": 1, "findings": 1}
            ).sort("created_at", -1).limit(10))
            for d in decisions:
                content_md += f"### {d.get('date', '?')} — {d.get('title', '?')} ({d.get('type', '?')})\n"
                for f in (d.get("findings") or [])[:3]:
                    content_md += f"- {f}\n"
                content_md += "\n"
        except Exception as e:
            content_md += f"(Error: {e})\n"

        # --- Top articles by event count ---
        content_md += "\n## Article Performance (Top 15 by Events)\n\n"
        try:
            article_stats = list(_sm["article_events"].aggregate([
                {"$group": {"_id": "$slug", "views": {"$sum": 1}}},
                {"$sort": {"views": -1}},
                {"$limit": 15}
            ]))
            if article_stats:
                content_md += "| Article Slug | Events |\n|-------------|--------|\n"
                for a in article_stats:
                    content_md += f"| {a['_id']} | {a['views']} |\n"
        except Exception as e:
            content_md += f"(Error: {e})\n"

        # --- Published articles list ---
        content_md += "\n## Published Articles\n\n"
        try:
            articles = list(_sm["content_articles"].find(
                {"status": "published"},
                {"_id": 0, "title": 1, "slug": 1, "suburb": 1}
            ).limit(25))
            content_md += f"**Total published:** {_sm['content_articles'].count_documents({'status': 'published'})}\n\n"
            for a in articles:
                content_md += f"- [{a.get('title', '?')}] — /{a.get('slug', '?')} ({a.get('suburb', 'general')})\n"
        except Exception as e:
            content_md += f"(Error: {e})\n"

        # --- Facebook organic post performance ---
        content_md += "\n## Facebook Organic Post Templates & History\n\n"
        try:
            post_count = _sm["fb_page_posts"].count_documents({})
            content_md += f"**Total organic posts tracked:** {post_count}\n\n"
            # Get recent posts with engagement
            recent_posts = list(_sm["fb_page_posts"].find(
                {},
                {"_id": 0, "template_type": 1, "reach": 1, "engagement": 1, "clicks": 1, "posted_at": 1}
            ).sort("posted_at", -1).limit(15))
            if recent_posts:
                content_md += "| Date | Template | Reach | Engagement | Clicks |\n|------|----------|-------|------------|--------|\n"
                for p in recent_posts:
                    posted = str(p.get("posted_at", ""))[:10]
                    content_md += f"| {posted} | {p.get('template_type', '?')} | {p.get('reach', '?')} | {p.get('engagement', '?')} | {p.get('clicks', '?')} |\n"
        except Exception as e:
            content_md += f"(Error: {e})\n"

        # --- Website page performance from PostHog metrics ---
        content_md += "\n## Website Pages (from recent metrics)\n\n"
        content_md += "Key pages on fieldsestate.com.au:\n"
        content_md += "- `/` — Market Intelligence homepage (articles by suburb)\n"
        content_md += "- `/for-sale` — Active property listings grid\n"
        content_md += "- `/for-sale-v2` — Decision Feed (prototype, curated property stream)\n"
        content_md += "- `/property/:id` — Individual property pages with valuation + AI editorial\n"
        content_md += "- `/market-metrics/:suburb` — Interactive data charts (6 tabs: Sell Now, Buy Now, Crash Risk, Overview, Direction, Comparison)\n"
        content_md += "- `/analyse-your-home` — Seller lead capture page\n"
        content_md += "- `/articles/:slug` — Self-hosted articles\n"
        content_md += "- `/discover` — Swipe/scroll property feed (experimental)\n"
        content_md += "\nEach market-metrics tab came from a high-performing autocomplete keyword. Each tab is a potential YouTube video.\n"

        # --- Search intent analysis summary ---
        content_md += "\n## Search Intent Analysis\n\n"
        try:
            analyses = list(_sm["search_intent_analysis"].find({}, {"_id": 0}).sort("created_at", -1).limit(1))
            if analyses:
                content_md += f"**Latest analysis available.** Run `python3 scripts/search-intent-analyser.py --report` for full output.\n"
            else:
                content_md += "No search intent analyses found. Run `python3 scripts/search-intent-analyser.py` to generate.\n"
            content_md += f"\n**Data sources:** {_sm['search_suggestions'].count_documents({})} autocomplete suggestions, "
            content_md += f"{_sm['search_youtube_suggestions'].count_documents({})} YouTube suggestions, "
            content_md += f"{_sm['search_paa_questions'].count_documents({})} PAA questions, "
            content_md += f"{_sm['search_reddit_posts'].count_documents({})} Reddit posts\n"
        except Exception as e:
            content_md += f"(Error: {e})\n"

        content_md += "\n---\n\n**When reviewing content:** Cross-reference this data. What are people searching for? What content already exists? What ads work? What articles get views? Content should answer real questions, not invent topics.\n"

        gh_api_put("context/focus/content_research_data.md", content_md, "update: content research data")

    except Exception as exc:
        gh_api_put("context/focus/content_research_data.md", f"# Content Research Data\n\nError: {exc}", "update: content research data (error)")


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
    export_agent_memory()
    export_founder_truths()
    export_founder_requests()
    export_ops_status()
    export_schema()
    export_fix_history()
    export_pipeline_config()
    export_metrics_and_memory()
    export_code_context()
    export_focus_context()
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
