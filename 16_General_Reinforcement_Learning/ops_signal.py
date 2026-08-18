#!/usr/bin/env python3
"""
ops_signal.py — the OPS sensor: what on the health board is actually broken, how long
it has been broken, and which failures are plausibly self-resolving.

Sibling to onsite_friction_signal.py. Where that one answers "what is broken for a
VISITOR", this answers "what is broken in the MACHINE" — the Fields Systems Health
board (Process Registry + Pipeline Processes), which on 2026-08-05 needed a human to
sit down for two hours and read 69 heartbeats to separate 29 deliberately-paused jobs
from 3 real failures.

It does NOT judge or fix anything. It calls main_site_health_check.collect() in-process
(the exact same collectors that build the sheet, so the sensor can never disagree with
the board) and emits every non-OK row with:

  - page / name / scope / status / detail          <- what the board says
  - failing_since + failing_days                   <- from mainsite_health_snapshots.fields[].last_changed,
                                                      so a 3-week rot is distinguishable from last night's blip
  - repair_class                                   <- a COARSE, MECHANICAL hint (see _classify), never a verdict

`repair_class` exists only to help the agent triage in priority order. It is deliberately
keyword-based and deliberately dumb: it must never be trusted over reading the actual log.
TRANSIENT in particular is a hypothesis ("this smells like a timeout, a re-run may clear
it"), NOT permission to assume the job is fine.

Writes system_monitor.rl_ops_signal (_id="latest" + timestamped history), same shape as
every other RL sensor. Rule 7 heartbeat as `rl_ops_signal`.

Usage:
    python3 ops_signal.py            # collect + write
    python3 ops_signal.py --dry-run  # print, don't write
"""
import argparse
import os
import sys
from datetime import datetime, timezone

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from shared.db import get_client  # noqa: E402

# The pages this sensor is responsible for. Process Registry = "is every process
# alive"; Pipeline Processes = "did each nightly step achieve its outcome, not just
# exit 0". Both were widened/repaired on 2026-08-05; see fix-history
# [HEALTH-BOARD-PAUSED-VS-DEAD] / [HEALTH-PIPELINE-OUTCOMES] / [MONITOR-FITNESS-PROBES].
PAGES = ("Process Registry", "Pipeline Processes")

# Statuses that represent something the agent may need to act on. KNOWN-GAP is
# EXCLUDED on purpose: it means a human has already acknowledged this row (a paused
# job, an awaited first run). Surfacing them here would invite the agent to "resolve"
# things that are not broken.
ACTIONABLE = ("ERROR", "STALE", "MISSING", "UNKNOWN-FRESHNESS")


def _evidence(row, sm, log_paths):
    """Attach the FACTS that discriminate between superficially-identical rows.

    Rationale (first ops cycle, 2026-08-05): three rows were all tagged RAISING and
    all three turned out to be different things — one genuine transient, one whose
    log merely predated a fix that had already landed, and one probe-window artefact.
    The keyword hint could not tell them apart and the agent had to open three logs
    to find out.

    The single fact that separates them is the job's OWN heartbeat: if job_runs says
    the last run succeeded while the board says ERROR, the probe is looking at stale
    evidence, not a live failure. That is a fact, not a guess, so it belongs here
    rather than in the hint.
    """
    ev = {}
    name = (row.get("name") or "").strip()
    scope = (row.get("scope") or "").strip()

    # Self-reported rows render under their heartbeat `title` — an EXACT match is
    # safe. Deliberately no fuzzy/stem matching: a wrongly-paired heartbeat would
    # assert "this job is actually fine" about a different job, which is worse
    # than attaching nothing (checked 2026-08-05 — log-stem matching mispaired
    # "Brain 3 ops nightly" onto nightly_lead_chain).
    if scope == "self-reported (auto)":
        try:
            hb = sm["job_runs"].find_one({"title": name})
        except Exception:
            hb = None
        if hb:
            ev["heartbeat"] = {"job": hb.get("job"), "status": hb.get("status"),
                               "run_at": str(hb.get("run_at"))}

    # For log-freshness rows the discriminator is IN the log and needs no mapping:
    # did the job recover after its last traceback? That single fact separates the
    # three cases that all render identically as "Traceback found in last run's log
    # tail" — a live failure, a job that has since self-healed, and a log whose last
    # write predates a fix that already landed.
    cand = log_paths.get(name)
    if cand:
        p = cand if cand.startswith("/") else os.path.join(ORCH, "logs", cand)
        if os.path.exists(p):
            ev["log_path"] = p
            mt = datetime.fromtimestamp(os.path.getmtime(p), tz=timezone.utc)
            ev["log_mtime"] = mt.isoformat()
            ev["log_age_hours"] = round((datetime.now(timezone.utc) - mt).total_seconds() / 3600, 1)
            try:
                with open(p, "rb") as f:
                    f.seek(max(0, os.path.getsize(p) - 60000), os.SEEK_SET)
                    tail = f.read().decode("utf-8", errors="ignore").splitlines()
                last_tb = max((i for i, l in enumerate(tail)
                               if "Traceback (most recent call last)" in l), default=None)
                if last_tb is not None:
                    after = tail[last_tb:]
                    ev["lines_after_last_traceback"] = len(after) - 1
                    # Deliberately broad: any of these appearing AFTER the last
                    # traceback is evidence of a subsequent completed run. It is a
                    # POINTER, not proof — the agent must still read the log.
                    ev["completion_markers_after_last_traceback"] = sum(
                        1 for l in after[1:] if any(m in l for m in (
                            "Done:", "Done.", "OK:", "complete", "Complete",
                            "success", "updated", "refreshed", "saved")))
            except Exception:
                pass
    if scope:
        ev["scope"] = scope
    return ev


def _classify(name, scope, detail):
    """Coarse mechanical triage hint. Keyword-based and intentionally dumb — the agent
    must confirm against the real log before acting on any of these."""
    d = (detail or "").lower()
    n = f"{name} {scope}".lower()
    if any(k in d for k in ("504", "503", "timeout", "timed out", "gateway",
                            "temporarily unavailable", "rate limit", "too busy",
                            "connection reset", "cursornotfound", "16500")):
        return "TRANSIENT"          # hypothesis: a re-run may clear it
    if "log file not found" in d:
        return "NEVER_RAN"
    if "may not be firing" in d or "not updated in" in d:
        return "NOT_FIRING"         # scheduled but silent -> cron/schedule problem
    if "traceback" in d:
        return "RAISING"            # code-level failure
    if "cannot verify" in d or "unknown" in n:
        return "UNVERIFIABLE"       # the probe cannot see the outcome
    return "UNCLASSIFIED"


def collect():
    import main_site_health_check as hc

    client = get_client()
    now = datetime.now(timezone.utc)
    rows = hc.collect(client, now, {})

    sm = client["system_monitor"]
    # Row-name -> log file, straight from the health check's own registry, so the
    # sensor never drifts from what the probe is actually reading.
    log_paths = {e[0]: e[2] for e in getattr(hc, "_REGISTRY_LOG_JOBS", []) if len(e) > 2}
    # last_changed per field key ("Page::Name::Scope") tells us how long a row has
    # been in its current state — the difference between "broke last night" and
    # "has been red for three weeks and nobody noticed".
    since = {}
    snap = sm["mainsite_health_snapshots"].find_one(sort=[("_id", -1)])
    for key, meta in (snap or {}).get("fields", {}).items():
        if isinstance(meta, dict) and meta.get("last_changed"):
            since[key] = meta["last_changed"]

    items, counts = [], {}
    for r in rows:
        page = r.get("page")
        if page not in PAGES:
            continue
        st = r.get("status")
        counts[st] = counts.get(st, 0) + 1
        if st not in ACTIONABLE:
            continue
        name, scope = r.get("name"), r.get("scope") or ""
        key = f"{page}::{name}::{scope}"
        lc = since.get(key)
        days = None
        if lc:
            try:
                ts = datetime.fromisoformat(str(lc).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                days = round((now - ts).total_seconds() / 86400, 1)
            except Exception:
                pass
        item = {
            "page": page, "name": name, "scope": scope, "status": st,
            "detail": (r.get("detail") or "")[:400],
            "failing_since": str(lc) if lc else None,
            "failing_days": days,
            "repair_class": _classify(name, scope, r.get("detail")),
        }
        item["evidence"] = _evidence(item, sm, log_paths)
        items.append(item)

    # Worst first, then longest-broken first.
    order = {"ERROR": 0, "MISSING": 1, "STALE": 2, "UNKNOWN-FRESHNESS": 3}
    items.sort(key=lambda i: (order.get(i["status"], 9), -(i["failing_days"] or 0)))

    by_class = {}
    for i in items:
        by_class[i["repair_class"]] = by_class.get(i["repair_class"], 0) + 1

    return {
        "_id": "latest",
        "generated_at": now,
        "pages": list(PAGES),
        "row_counts_by_status": counts,
        "actionable_total": len(items),
        "actionable_by_class": by_class,
        "items": items,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    doc = collect()
    print(f"ops_signal: {doc['actionable_total']} actionable across {', '.join(PAGES)}")
    print(f"  by status: {doc['row_counts_by_status']}")
    print(f"  by class : {doc['actionable_by_class']}")
    for i in doc["items"]:
        age = f"{i['failing_days']}d" if i["failing_days"] is not None else "?"
        e = i.get("evidence") or {}
        note = ""
        if e.get("completion_markers_after_last_traceback"):
            note = (f"  [log shows {e['completion_markers_after_last_traceback']} completion marker(s) "
                    f"AFTER the last traceback — may have self-healed]")
        elif e.get("log_age_hours") is not None and e["log_age_hours"] > 48:
            note = f"  [log last written {e['log_age_hours'] / 24:.1f}d ago — may predate a fix]"
        print(f"  [{i['status']:8}] {i['repair_class']:13} {age:>6}  {i['name']} :: {i['detail'][:70]}{note}")

    if args.dry_run:
        return 0

    sm = get_client()["system_monitor"]
    sm["rl_ops_signal"].replace_one({"_id": "latest"}, doc, upsert=True)
    hist = dict(doc)
    hist.pop("_id", None)
    sm["rl_ops_signal"].insert_one(hist)

    try:
        from job_status import record_job_result
        record_job_result(
            "rl_ops_signal", "success",
            detail=(f"{doc['actionable_total']} actionable "
                    f"({', '.join(f'{k} {v}' for k, v in sorted(doc['actionable_by_class'].items()))})"),
            cadence_hours=168, title="Ops — health-board sensor (what is broken)",
            actionable=doc["actionable_total"],
        )
    except Exception as e:
        print(f"(job_status record failed: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
