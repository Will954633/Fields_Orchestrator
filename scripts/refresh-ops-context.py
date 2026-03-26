#!/usr/bin/env python3
"""
refresh-ops-context.py
Generates OPS_STATUS.md — a live snapshot of the Fields ops dashboard data.

Reads from:
  - system_monitor.process_runs       (orchestrator pipeline runs + step status)
  - system_monitor.api_health_checks  (website endpoint health)
  - system_monitor.data_integrity     (property data coverage per suburb)
  - system_monitor.repair_requests    (pending repair queue)
  - system_monitor.article_events     (Ghost publish + Netlify build events)
  - Gold_Coast_Currently_For_Sale.*   (active listing counts per suburb)
  - property_data.properties_for_sale (enriched property counts)

Output: /home/fields/Fields_Orchestrator/OPS_STATUS.md

Run automatically: cron every 15 minutes + after each pipeline run
Usage: python3 /home/fields/Fields_Orchestrator/scripts/refresh-ops-context.py
"""

import os
import sys
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Connection ──────────────────────────────────────────────────────────────

def load_env():
    """Load .env from orchestrator directory."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    v = v.strip().strip("'\"")
                    os.environ.setdefault(k.strip(), v)

def get_client():
    load_env()
    uri = (
        os.environ.get("COSMOS_CONNECTION_STRING")
        or os.environ.get("MONGODB_URI")
    )
    if not uri:
        raise RuntimeError("No MongoDB URI found in environment")
    from pymongo import MongoClient
    return MongoClient(
        uri,
        tls=True,
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=8000,
        socketTimeoutMS=10000,
    )

# ── Helpers ──────────────────────────────────────────────────────────────────

def now_aest():
    """Current time in AEST (UTC+10)."""
    return datetime.now(timezone(timedelta(hours=10)))

def fmt_dt(dt, tz_offset=10):
    """Format a datetime (or ISO string) as human-readable AEST."""
    if dt is None:
        return "never"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return str(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    aest = dt.astimezone(timezone(timedelta(hours=tz_offset)))
    return aest.strftime("%Y-%m-%d %H:%M AEST")

def age_str(dt):
    """Return human-readable age like '2h 15m ago' or '3d ago'."""
    if dt is None:
        return "unknown"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h {m}m ago"
    d = secs // 86400
    h = (secs % 86400) // 3600
    return f"{d}d {h}h ago"

def status_icon(status):
    """Map status string to icon."""
    s = (status or "").lower()
    if s in ("success", "completed", "ok", "green", "active", "healthy"):
        return "✅"
    if s in ("failed", "error", "red", "critical"):
        return "❌"
    if s in ("running", "in_progress"):
        return "⏳"
    if s in ("warn", "amber", "warning"):
        return "⚠️"
    if s in ("stale",):
        return "🕐"
    if s in ("skipped", "unknown", "pending"):
        return "⬜"
    return "•"

# ── Data fetchers ────────────────────────────────────────────────────────────

def fetch_orchestrator_status(db):
    """Get last pipeline run + step summary."""
    col = db["system_monitor"]["process_runs"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=36)

    # Most recent orchestrator run entry
    last_pipeline = col.find_one(
        {"system": "orchestrator", "pipeline": "orchestrator_daily"},
        sort=[("started_at", -1)]
    )

    # All steps from the last 36h — exclude stale zombie records
    recent_steps = list(
        col.find(
            {
                "system": "orchestrator",
                "started_at": {"$gte": cutoff},
                "status": {"$nin": ["failed_stale"]},
            },
        ).sort("started_at", -1).limit(200)
    )

    # Group by date to reconstruct the most recent run
    by_date = {}
    for step in recent_steps:
        dt = step.get("started_at")
        if dt:
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                except Exception:
                    continue
            date_key = dt.astimezone(timezone(timedelta(hours=10))).strftime("%Y-%m-%d")
            by_date.setdefault(date_key, []).append(step)

    latest_date = max(by_date.keys()) if by_date else None
    latest_steps = sorted(
        by_date.get(latest_date, []),
        key=lambda s: s.get("process_id", 0)
    )

    # Summary counts
    total = len(latest_steps)
    failed = sum(1 for s in latest_steps if s.get("status") == "failed")
    running = sum(1 for s in latest_steps if s.get("status") == "running")
    success = sum(1 for s in latest_steps if s.get("status") in ("success", "completed"))

    return {
        "last_pipeline_run": last_pipeline,
        "latest_date": latest_date,
        "steps": latest_steps,
        "total_steps": total,
        "success": success,
        "failed": failed,
        "running": running,
    }

FOUNDER_HEALTH_CONTRACTS = [
    "/api/v1/properties/for-sale",
    "/api/v1/properties/recently-sold",
    "/api/v1/address-search",
    "/api/v1/analyse-property",
]


def fetch_api_health(db):
    """Get latest health check per endpoint."""
    col = db["system_monitor"]["api_health_checks"]
    # Only fetch checks from the last 24h (prevents stale legacy records from dominating)
    # Use naive datetime since Cosmos stores naive datetimes
    recent_cutoff = datetime.utcnow() - timedelta(hours=24)
    docs = list(col.find({"checked_at": {"$gte": recent_cutoff}}).limit(200))
    docs.sort(key=lambda d: d.get("checked_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    # Latest per endpoint
    seen = {}
    for doc in docs:
        ep = doc.get("endpoint", "unknown")
        if ep not in seen:
            seen[ep] = doc
    results = list(seen.values())
    results.sort(key=lambda d: d.get("endpoint", ""))

    # Freshness gate: mark any check older than 12h as stale
    stale_cutoff = datetime.utcnow() - timedelta(hours=12)
    for r in results:
        checked = r.get("checked_at")
        if isinstance(checked, datetime) and checked.replace(tzinfo=None) < stale_cutoff:
            r["healthy"] = False
            r["stale"] = True

    # Separate founder-contract endpoints from internal/other endpoints
    contract_eps = []
    other_eps = []
    seen_contracts = set()
    for r in results:
        ep = r.get("endpoint", "")
        # Match if the endpoint starts with any founder contract path
        matched = False
        for contract in FOUNDER_HEALTH_CONTRACTS:
            if ep.startswith(contract):
                contract_eps.append(r)
                seen_contracts.add(contract)
                matched = True
                break
        if not matched:
            other_eps.append(r)

    # Mark missing founder contracts as stale/unknown
    for contract in FOUNDER_HEALTH_CONTRACTS:
        if contract not in seen_contracts:
            contract_eps.append({
                "endpoint": contract,
                "healthy": False,
                "stale": True,
                "status_code": "no_data",
                "checked_at": None,
            })

    healthy = sum(1 for r in results if r.get("healthy"))
    unhealthy = sum(1 for r in results if not r.get("healthy"))
    return {
        "endpoints": results,
        "contract_endpoints": contract_eps,
        "other_endpoints": other_eps,
        "healthy": healthy,
        "unhealthy": unhealthy,
    }

def fetch_data_coverage(db):
    """Get suburb-level data coverage."""
    col = db["system_monitor"]["data_integrity"]
    docs = list(col.find({}).limit(500))
    docs.sort(key=lambda d: d.get("checked_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    latest = {}
    for doc in docs:
        name = doc.get("check_name", "")
        if name not in latest:
            latest[name] = doc
    suburb_docs = [
        d for d in latest.values()
        if d.get("check_type") == "data_coverage" and d.get("suburb")
    ]
    # Freshness gate: mark any coverage check older than 12h as stale
    stale_cutoff = datetime.utcnow() - timedelta(hours=12)
    for doc in suburb_docs:
        checked = doc.get("checked_at")
        if checked is None:
            doc["status"] = "stale"
        elif isinstance(checked, datetime) and checked.replace(tzinfo=None) < stale_cutoff:
            doc["status"] = "stale"
    suburb_docs.sort(key=lambda d: d.get("suburb", ""))
    return suburb_docs

def fetch_repair_queue(db):
    """Get pending repair requests."""
    col = db["system_monitor"]["repair_requests"]
    docs = list(col.find({}).limit(100))
    docs.sort(key=lambda d: d.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    pending = [d for d in docs if d.get("status") == "pending"]
    recent = docs[:10]
    return {"pending": pending, "recent": recent}

def fetch_article_events(db):
    """Get recent Ghost publish + Netlify build events."""
    col = db["system_monitor"]["article_events"]
    docs = list(col.find({}).limit(100))
    docs.sort(key=lambda d: d.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    publishes = [d for d in docs if d.get("event_type") == "ghost_publish"][:10]
    builds = [d for d in docs if d.get("event_type") == "netlify_build"][:5]
    return {"publishes": publishes, "builds": builds}

def fetch_scraper_health(db):
    """Get scraper health / last scrape time per suburb."""
    col = db["system_monitor"]["scraper_health"]
    try:
        docs = list(col.find({}).limit(500))
        docs.sort(key=lambda d: d.get("checked_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        # Latest per suburb
        seen = {}
        for doc in docs:
            suburb = doc.get("suburb", "unknown")
            if suburb not in seen:
                seen[suburb] = doc
        return list(seen.values())
    except Exception:
        return []

def fetch_listing_counts(client):
    """Count active listings and enrichment per suburb from Gold_Coast.

    Dynamically discovers all suburb collections (excludes known non-suburb
    collections like suburb_median_prices, suburb_statistics, etc.).
    """
    # Non-suburb collections to skip
    SKIP_COLLECTIONS = {
        "suburb_median_prices", "suburb_statistics", "change_detection_snapshots",
        "address_search_index", "precomputed_indexed_prices",
        "system.indexes", "system_monitor",
    }
    TARGET_SUBURBS = {"robina", "burleigh_waters", "varsity_lakes"}
    counts = {}
    enrichment = {}
    try:
        db = client["Gold_Coast"]
        all_collections = db.list_collection_names()
        suburb_collections = sorted(
            c for c in all_collections
            if c not in SKIP_COLLECTIONS and not c.startswith("system.")
        )
        for suburb in suburb_collections:
            try:
                count = db[suburb].count_documents({"listing_status": "for_sale"})
                if count == 0:
                    continue  # skip suburbs with no active listings
                display = suburb.replace("_", " ").title()
                counts[display] = count
                # Track enrichment for all suburbs (highlight target suburbs)
                enriched_count = db[suburb].count_documents({"listing_status": "for_sale", "valuation_data": {"$exists": True}})
                enrichment[display] = {"active": count, "enriched": enriched_count, "target": suburb in TARGET_SUBURBS}
            except Exception:
                display = suburb.replace("_", " ").title()
                counts[display] = "?"
    except Exception:
        pass

    # Total enriched across target suburbs
    counts["_enriched"] = sum(e["enriched"] for e in enrichment.values() if isinstance(e, dict))
    counts["_enrichment"] = enrichment
    counts["_suburb_count"] = len([v for v in counts.values() if isinstance(v, int)])

    return counts

def fetch_website_deploys(db):
    """Get recent website deploy events from the deploy tracker."""
    col = db["system_monitor"]["website_deploy_events"]
    try:
        docs = list(col.find().limit(20))
        # Sort in Python since Cosmos may lack the index
        docs.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
        return docs[:10]
    except Exception:
        return []


def fetch_errors(db):
    """Get recent errors (last 24h)."""
    col = db["system_monitor"]["process_runs"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    docs = list(
        col.find(
            {"started_at": {"$gte": cutoff}, "status": "failed"},
        ).limit(50)
    )
    docs.sort(key=lambda d: d.get("started_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return docs

# ── Markdown renderer ────────────────────────────────────────────────────────

def render_ops_status(orch, api, coverage, repairs, articles, listing_counts, errors, scraper, deploys=None):
    now = now_aest()
    lines = []

    def h(level, text):
        lines.append(f"\n{'#' * level} {text}")

    def sep():
        lines.append("")

    # Header
    lines.append(f"# OPS_STATUS — Fields Estate Live Dashboard Snapshot")
    lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M AEST')} (auto-refreshes every 15 minutes)")
    lines.append(f"**Source:** MongoDB `system_monitor` database (same data as https://fieldsestate.com.au/ops)")
    lines.append(f"\n> This file is auto-generated. Do not edit manually.")

    # ── 1. Orchestrator Pipeline ─────────────────────────────────────────────
    h(2, "1. Orchestrator Pipeline")

    lp = orch.get("last_pipeline_run")
    date = orch.get("latest_date", "unknown")
    total = orch["total_steps"]
    success = orch["success"]
    failed = orch["failed"]
    running = orch["running"]

    # Derive pipeline status from step results (more reliable than pipeline-level record on Cosmos)
    if failed > 0:
        overall = "failed"
    elif running > 0:
        overall = "running"
    elif success == total and total > 0:
        overall = "ok"
    else:
        overall = "unknown"

    lines.append(f"**Last run date:** {date}  ")
    lines.append(f"**Pipeline status:** {status_icon(overall)} {overall}  ")
    lines.append(f"**Steps:** {success}/{total} succeeded, {failed} failed, {running} running  ")

    # Try to show start time from the earliest step or pipeline record
    start_ref = lp if lp and lp.get("started_at") else None
    if not start_ref and orch["steps"]:
        earliest = min((s for s in orch["steps"] if s.get("started_at")), key=lambda s: s["started_at"], default=None)
        if earliest:
            start_ref = earliest
    if start_ref and start_ref.get("started_at"):
        lines.append(f"**Started:** {fmt_dt(start_ref['started_at'])} ({age_str(start_ref['started_at'])})  ")

    if orch["steps"]:
        lines.append("\n**Step-by-step status (most recent run):**")
        lines.append("| # | Step | Status | Duration | Errors |")
        lines.append("|---|------|--------|----------|--------|")
        for step in orch["steps"]:
            pid = step.get("process_id", "?")
            name = step.get("process_name", "unknown")[:45]
            st = step.get("status", "?")
            dur = step.get("duration_seconds")
            dur_str = f"{dur:.0f}s" if dur else "—"
            err_count = step.get("error_count", 0) or 0
            icon = status_icon(st)
            lines.append(f"| {pid} | {name} | {icon} {st} | {dur_str} | {err_count} |")

    # ── 2. Recent Errors ─────────────────────────────────────────────────────
    h(2, "2. Recent Errors (Last 24h)")
    if errors:
        lines.append(f"**{len(errors)} failed steps in last 24h:**")
        for e in errors[:10]:
            name = e.get("process_name", "unknown")
            started = age_str(e.get("started_at"))
            err_msgs = e.get("errors", [])
            lines.append(f"\n**❌ {name}** ({started})")
            for em in (err_msgs[:3] if err_msgs else []):
                msg = (em.get("message") or str(em))[:120]
                lines.append(f"  - {msg}")
    else:
        lines.append("✅ No failed steps in the last 24 hours.")

    # ── 3. Active Listings ───────────────────────────────────────────────────
    h(2, "3. Active Listings Database")

    enriched = listing_counts.pop("_enriched", "?")
    enrichment = listing_counts.pop("_enrichment", {})
    suburb_count = listing_counts.pop("_suburb_count", "?")
    total_listings = sum(v for v in listing_counts.values() if isinstance(v, int))
    total_enriched = sum(e["enriched"] for e in enrichment.values() if isinstance(e, dict))
    target_enriched = sum(e["enriched"] for e in enrichment.values() if isinstance(e, dict) and e.get("target"))
    target_active = sum(e["active"] for e in enrichment.values() if isinstance(e, dict) and e.get("target"))
    enrichment_pct = round(total_enriched / total_listings * 100, 1) if total_listings else 0
    lines.append(f"**Total active listings (Gold_Coast, {suburb_count} suburbs):** {total_listings}")
    lines.append(f"**Enriched properties (with valuation_data, all suburbs):** {total_enriched}/{total_listings} ({enrichment_pct}%)")
    lines.append(f"**Target suburb enrichment (Robina, Burleigh Waters, Varsity Lakes):** {target_enriched}/{target_active}")
    sep()
    lines.append("| Suburb | Active Listings | Enriched | Enrichment % |")
    lines.append("|--------|----------------|----------|--------------|")
    for suburb, count in sorted(listing_counts.items()):
        enr = enrichment.get(suburb)
        if enr:
            pct = round(enr["enriched"] / enr["active"] * 100, 1) if enr["active"] else 0
            marker = " ⭐" if enr.get("target") else ""
            lines.append(f"| {suburb}{marker} | {count} | {enr['enriched']}/{enr['active']} | {pct}% |")
        else:
            lines.append(f"| {suburb} | {count} | — | — |")

    # ── 4. Data Coverage ─────────────────────────────────────────────────────
    h(2, "4. Scrape Coverage by Suburb")
    lines.append("*Measures **scrape completeness** — whether our DB listing count matches the live Domain.com.au count (checked by step 109). 'Critical' means Domain shows more listings than we have scraped. This is different from enrichment % above — a suburb can be fully scraped but not fully enriched, or vice versa.*\n")
    if coverage:
        stale_count = sum(1 for d in coverage if d.get("status") == "stale")
        if stale_count > 0:
            lines.append(f"🕐 **STALE DATA — {stale_count}/{len(coverage)} suburbs have coverage data older than 12 hours. Process 109 may not have run recently.**\n")
        lines.append("| Suburb | Status | Listings | Last Updated | Checked |")
        lines.append("|--------|--------|----------|--------------|---------|")
        for doc in coverage:
            suburb = doc.get("suburb", "?")
            st = doc.get("status", "?")
            icon = status_icon(st)
            total_l = doc.get("total_listings", "?")
            last_upd = fmt_dt(doc.get("last_listing_update"))
            checked = age_str(doc.get("checked_at"))
            cov = doc.get("coverage", {})
            cov_str = ", ".join(f"{k}:{v}" for k, v in cov.items()) if cov else "—"
            lines.append(f"| {suburb} | {icon} {st} | {total_l} | {last_upd} | {checked} |")
    else:
        lines.append("⚠️ No data coverage records found.")

    # ── 5. Scraper Health ────────────────────────────────────────────────────
    h(2, "5. Scraper Health")
    lines.append("*Measures **freshness** — when each suburb was last scraped. A suburb can be 'healthy' (recently scraped) but still 'critical' in Data Coverage if some listings were missed.*\n")
    if scraper:
        lines.append("| Suburb | Last Scrape | Staleness | Status |")
        lines.append("|--------|-------------|-----------|--------|")
        for doc in scraper:
            suburb = doc.get("suburb", "?")
            last_scrape = doc.get("last_scrape_time") or doc.get("last_scraped_at") or doc.get("checked_at")
            age = age_str(last_scrape)
            st = doc.get("status", "?")
            icon = status_icon(st)
            stale_hours = doc.get("staleness_hours", "?")
            lines.append(f"| {suburb} | {fmt_dt(last_scrape)} | {age} | {icon} {st} |")
    else:
        lines.append("ℹ️ No scraper health records in system_monitor. The orchestrator writes these after each scrape.")

    # ── 6. API Health ────────────────────────────────────────────────────────
    h(2, "6. Website API Health")
    healthy_count = api["healthy"]
    unhealthy_count = api["unhealthy"]
    total_count = healthy_count + unhealthy_count
    overall_icon = "✅" if unhealthy_count == 0 else "❌"
    lines.append(f"**Summary:** {overall_icon} {healthy_count}/{total_count} endpoints healthy")

    # Founder-contract endpoints (buyer-facing — these are the ones that matter)
    contract_eps = api.get("contract_endpoints", [])
    if contract_eps:
        contract_healthy = sum(1 for e in contract_eps if e.get("healthy"))
        contract_total = len(contract_eps)
        contract_icon = "✅" if contract_healthy == contract_total else "❌"
        lines.append(f"\n**Buyer-facing contract:** {contract_icon} {contract_healthy}/{contract_total} healthy")
        lines.append("\n| Buyer-Facing Endpoint | Status | Response | Last Checked |")
        lines.append("|----------------------|--------|----------|--------------|")
        for ep in contract_eps:
            endpoint = ep.get("endpoint", "?")
            healthy = ep.get("healthy", False)
            is_stale = ep.get("stale", False)
            icon = "⚠️" if is_stale else ("✅" if healthy else "❌")
            status_code = "stale" if is_stale else ep.get("status_code", "?")
            resp_ms = ep.get("response_ms")
            issue = ep.get("contract_issue") or ep.get("validation_error")
            resp_str = issue or (f"{resp_ms:.0f}ms" if resp_ms else "—")
            checked = age_str(ep.get("checked_at"))
            lines.append(f"| `{endpoint}` | {icon} {status_code} | {resp_str} | {checked} |")

    # Other/internal endpoints
    other_eps = api.get("other_endpoints", [])
    if other_eps:
        lines.append(f"\n**Other endpoints ({len(other_eps)}):**")
        lines.append("\n| Endpoint | Status | Response | Last Checked |")
        lines.append("|----------|--------|----------|--------------|")
        for ep in other_eps[:15]:
            endpoint = ep.get("endpoint", "?")
            healthy = ep.get("healthy", False)
            is_stale = ep.get("stale", False)
            icon = "⚠️" if is_stale else ("✅" if healthy else "❌")
            status_code = "stale" if is_stale else ep.get("status_code", "?")
            resp_ms = ep.get("response_ms")
            issue = ep.get("contract_issue") or ep.get("validation_error")
            resp_str = issue or (f"{resp_ms:.0f}ms" if resp_ms else "—")
            checked = age_str(ep.get("checked_at"))
            lines.append(f"| `{endpoint}` | {icon} {status_code} | {resp_str} | {checked} |")

    if not api["endpoints"]:
        lines.append("ℹ️ No API health check data yet.")

    # ── 7. Article Pipeline + Website Deploys ────────────────────────────────
    h(2, "7. Article Pipeline & Website Deploys")

    # Website deploy events (from deploy tracker — authoritative source)
    if deploys:
        last_deploy = deploys[0]
        deploy_ts = last_deploy.get("timestamp")
        lines.append(f"**Last website deploy:** ✅ {last_deploy.get('message', 'unknown')[:80]} ({age_str(deploy_ts)})")
        lines.append(f"  Commit: `{last_deploy.get('commit_sha', '?')[:12]}`")
        lines.append(f"\n**Recent deploys (last 5):**")
        for d in deploys[:5]:
            msg = (d.get("message") or "no message")[:60]
            ts = age_str(d.get("timestamp"))
            sha = (d.get("commit_sha") or "?")[:8]
            files = d.get("files_changed", [])
            file_count = len(files) if isinstance(files, list) else "?"
            lines.append(f"  - `{sha}` {msg} — {ts} ({file_count} files)")
    else:
        lines.append("ℹ️ No website deploy events recorded.")

    sep()
    pubs = articles["publishes"]
    builds = articles["builds"]

    if pubs:
        last_pub = pubs[0]
        lines.append(f"**Last article published:** {last_pub.get('post_title', 'Unknown')} ({age_str(last_pub.get('timestamp'))})")
        lines.append("\n**Recent publications (last 10):**")
        for p in pubs:
            title = p.get("post_title") or p.get("post_slug") or "Unknown"
            ts = age_str(p.get("published_at") or p.get("timestamp"))
            lines.append(f"  - {title} — {ts}")
    else:
        lines.append("ℹ️ No article publish events recorded yet.")

    if builds:
        last_build = builds[0]
        build_icon = status_icon(last_build.get("status"))
        lines.append(f"\n**Last Netlify build (article_events):** {build_icon} {last_build.get('status', '?')} ({age_str(last_build.get('timestamp'))})")
        if deploys:
            lines.append("  *(Note: website_deploy_events above is the authoritative deploy source)*")
    sep()

    # ── 8. Repair Queue ──────────────────────────────────────────────────────
    h(2, "8. Repair Queue")
    pending = repairs["pending"]
    recent = repairs["recent"]

    if pending:
        lines.append(f"**⚠️ {len(pending)} pending repair request(s):**")
        for req in pending[:5]:
            title = req.get("title") or req.get("description") or "Untitled"
            created = age_str(req.get("created_at"))
            lines.append(f"  - [{created}] {title}")
    else:
        lines.append("✅ No pending repair requests.")

    if recent and not pending:
        last = recent[0]
        title = last.get("title") or last.get("description") or "Untitled"
        st = last.get("status", "?")
        lines.append(f"  Last request: {status_icon(st)} {title} — {st} ({age_str(last.get('created_at'))})")

    # ── Footer ───────────────────────────────────────────────────────────────
    sep()
    lines.append("---")
    lines.append(f"*Auto-generated by refresh-ops-context.py at {now.strftime('%Y-%m-%d %H:%M AEST')}*")
    lines.append(f"*To refresh manually: `python3 /home/fields/Fields_Orchestrator/scripts/refresh-ops-context.py`*")

    return "\n".join(lines)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    output_path = Path(__file__).parent.parent / "OPS_STATUS.md"

    print(f"[refresh-ops-context] Starting at {now_aest().strftime('%H:%M AEST')}")

    try:
        client = get_client()
        db = client  # pass client, not a single db — we query multiple dbs

        print("  Fetching orchestrator status...")
        orch = fetch_orchestrator_status(client)

        print("  Fetching API health...")
        api = fetch_api_health(client)

        print("  Fetching data coverage...")
        coverage = fetch_data_coverage(client)

        print("  Fetching repair queue...")
        repairs = fetch_repair_queue(client)

        print("  Fetching article events...")
        articles = fetch_article_events(client)

        print("  Fetching scraper health...")
        scraper = fetch_scraper_health(client)

        print("  Fetching listing counts...")
        listing_counts = fetch_listing_counts(client)

        print("  Fetching recent errors...")
        errors = fetch_errors(client)

        print("  Fetching website deploys...")
        deploys = fetch_website_deploys(client)

        print("  Rendering OPS_STATUS.md...")
        content = render_ops_status(
            orch=orch,
            api=api,
            coverage=coverage,
            repairs=repairs,
            articles=articles,
            listing_counts=listing_counts,
            errors=errors,
            scraper=scraper,
            deploys=deploys,
        )

        output_path.write_text(content, encoding="utf-8")
        print(f"  ✅ Written to {output_path}")
        print(f"  Lines: {content.count(chr(10))}, Size: {len(content)} bytes")

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"  ❌ Error: {e}", file=sys.stderr)
        # Write a minimal error file so CLAUDE.md reference always resolves
        output_path.write_text(
            f"# OPS_STATUS — Error\n\n"
            f"**Failed to generate at {now_aest().strftime('%Y-%m-%d %H:%M AEST')}**\n\n"
            f"```\n{error_msg[:2000]}\n```\n\n"
            f"Run `python3 /home/fields/Fields_Orchestrator/scripts/refresh-ops-context.py` to retry.\n",
            encoding="utf-8"
        )
        sys.exit(1)

if __name__ == "__main__":
    main()
