#!/usr/bin/env python3
"""
refresh_article_data.py -- keep the owner-subject article's data current, and make
staleness LOUD instead of silent.

The article renders from five context files. Three refresh from live sources; two
are human-maintained:

  labour_context.json        <- update_labour_context.py   (ABS Data API)
  arbitrage_context.json     <- build_arbitrage.py         (onthehouse)
  comparison_examples.json   <- build_comparison_examples.py (Google Street View)
  macro_context.json         <- update_macro_context.py recomputes `derived` from the
                                human-entered Cotality history (no external fetch)
  fundamentals_context.json  <- human-maintained (migration/affordability + the
                                lead/lag research figures); not auto-refreshed

This orchestrator runs the refreshers, then ASSERTS each file is fresh. It is the
single scheduled entry point, self-reported via job_status (CLAUDE.md Rule 7); it
RAISES if a required file failed to refresh or is older than its staleness bound
(Rule 7b) -- so a dead ABS pull or an onthehouse block surfaces on the health board
rather than quietly feeding the mail-out last month's numbers.

  python3 refresh_article_data.py             # scheduled run
  python3 refresh_article_data.py --no-heartbeat
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))
PY = sys.executable

# (script, extra-args, output file, timestamp field, max-age-days) — required=True
# means a stale/missing file is a hard error (Rule 7b). Comparison/arbitrage tolerate
# a longer age (Street View + block sizes barely move); labour must stay current.
REFRESHERS = [
    ("update_macro_context.py", ["--no-heartbeat"], "macro_context.json",
     "derived.computed_at", 40, True),
    ("update_labour_context.py", ["--no-heartbeat"], "labour_context.json",
     "retrieved_at", 45, True),
    ("build_arbitrage.py", [], "arbitrage_context.json", "retrieved_at", 60, False),
    ("build_comparison_examples.py", [], "comparison_examples.json", "retrieved_at",
     120, False),
]


def _clean_env() -> dict:
    return dict(os.environ)


def _dig(d, dotted):
    for k in dotted.split("."):
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d


def _age_days(path, field):
    try:
        with open(path) as fh:
            ts = _dig(json.load(fh), field)
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except (OSError, ValueError, TypeError, KeyError):
        return None


def run() -> dict:
    ran, failures, stale = [], [], []
    for script, args, out, field, max_age, required in REFRESHERS:
        path = os.path.join(HERE, out)
        try:
            r = subprocess.run([PY, os.path.join(HERE, script), *args],
                               cwd=HERE, env=_clean_env(), capture_output=True,
                               text=True, timeout=600)
            if r.returncode != 0:
                (failures if required else ran).append(
                    f"{script}: exit {r.returncode} ({r.stderr.strip()[-160:]})")
                if not required:
                    print(f"  ! {script} failed (non-required): {r.stderr[-160:]}",
                          file=sys.stderr)
            else:
                ran.append(script)
        except Exception as e:                                 # noqa: BLE001
            (failures if required else ran).append(f"{script}: {type(e).__name__}: {e}")

        age = _age_days(path, field)
        if age is None:
            (failures if required else stale).append(f"{out}: no readable timestamp")
        elif age > max_age:
            (failures if required else stale).append(
                f"{out}: {age:.0f}d old (max {max_age})")
        print(f"  {out}: age {age:.1f}d (max {max_age})"
              if age is not None else f"  {out}: NO TIMESTAMP", file=sys.stderr)

    # Rule 7b: a required refresh that failed or a required file that is stale is an
    # error, not a quiet success. Provisional macro figures are surfaced separately.
    prov = _dig(_safe_json(os.path.join(HERE, "macro_context.json")),
                "derived.uses_provisional")
    res = {"ran": ran, "failures": failures, "stale": stale,
           "macro_uses_provisional": bool(prov)}
    if failures:
        raise RuntimeError("article data refresh failed: " + "; ".join(failures))
    return res


def _safe_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-heartbeat", action="store_true")
    a = ap.parse_args()

    if a.no_heartbeat:
        res = run()
        print(json.dumps(res, indent=2), file=sys.stderr)
        return 0
    try:
        from job_status import job_run
    except Exception:
        run(); return 0
    with job_run("owner_article_data_refresh", cadence_hours=168,
                 title="Owner-article data refresh") as beat:
        res = run()
        beat.metrics = {"refreshed": len(res["ran"]),
                        "uses_provisional_macro": int(res["macro_uses_provisional"])}
        beat.detail = (f"{len(res['ran'])} refreshed"
                       + (" · macro still provisional" if res["macro_uses_provisional"]
                          else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
